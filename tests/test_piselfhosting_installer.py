import pytest
import json
import os
from unittest.mock import patch, MagicMock
from flask import session, url_for

# Ensure the app module can be found
from configurator_app.app import create_app


@pytest.fixture
def mock_paths(tmp_path):
    """Creates a dictionary of temporary paths for mock files."""
    # Create subdirectories for config and templates
    config_dir = tmp_path / "config"
    template_dir = tmp_path / "templates"
    config_dir.mkdir()
    template_dir.mkdir()

    # Define paths for all the dummy files our test app will need
    return {
        "root": tmp_path,
        "config_dir": config_dir,
        "template_dir": template_dir,
        "metadata_file": config_dir / "components_metadata.json",
        "output_file": tmp_path / "selected_components.txt",
        "env_file": tmp_path / ".env",
    }


@pytest.fixture
def app(mock_paths):
    """Create and configure a new app instance for each test."""
    # Create a dummy metadata file for the app to load
    mock_components = {
        "dashy": {"name": "Dashy", "description": "A dashboard."},
        "portainer": {"name": "Portainer", "description": "Container management."}
    }
    mock_paths["metadata_file"].write_text(json.dumps(mock_components))

    # Create dummy template files
    (mock_paths["template_dir"] / "select_pi.html").write_text("<h1>Select a Pi</h1>")
    (mock_paths["template_dir"] / "select_components.html").write_text("<h1>Select Components</h1><p>{{ pi_ip }}</p>{% for c in components.values() %}<p>{{ c.name }}</p>{% endfor %}")
    (mock_paths["template_dir"] / "install_success.html").write_text("<h1>Installation Success</h1>")

    # Use the factory to create the app, passing all necessary paths in the test config
    app = create_app({
        'TESTING': True,
        'SECRET_KEY': 'test-secret-key',
        'METADATA_FILE': str(mock_paths["metadata_file"]),
        'SELECTED_COMPONENTS_OUTPUT_FILE': str(mock_paths["output_file"]),
        'ENV_PATH': str(mock_paths["env_file"]),
    })

    app.template_folder = str(mock_paths["template_dir"])
    yield app


@pytest.fixture
def client(app):
    """A test client for the app."""
    return app.test_client()


def test_index_redirects_to_select_pi_when_no_pi_in_session(client):
    """
    GIVEN a Flask client
    WHEN the '/' page is requested and no Pi IP is in the session
    THEN check that the "Select a Pi" page is rendered.
    """
    response = client.get('/')
    assert response.status_code == 200
    assert b"<h1>Select a Pi</h1>" in response.data


def test_index_shows_components_when_pi_in_session(client, app):
    """
    GIVEN a Flask client and app
    WHEN a Pi IP is added to the session and '/' is requested
    THEN check that the "Select Components" page is rendered with component data.
    """
    with client.session_transaction() as sess:
        sess['target_pi_ip'] = '192.168.1.100'

    response = client.get('/')
    assert response.status_code == 200
    assert b"<h1>Select Components</h1>" in response.data
    assert b"192.168.1.100" in response.data
    assert b"Dashy" in response.data


@patch('configurator_app.app.PiScanner.get_device_details')
@patch('configurator_app.app.PiScanner.scan')
def test_scan_network_endpoint(mock_scan, mock_get_details, client):
    """
    GIVEN mocked PiScanner methods
    WHEN the '/scan' endpoint is called
    THEN check that the scanner is called and returns a structured response.
    """
    # --- Setup Mocks ---
    # 1. Mock the initial scan to find one potential Pi
    mock_scan.return_value = [{'ip': '192.168.1.101', 'mac': 'e4:5f:01:aa:bb:cc'}]
    # 2. Mock the details retrieval for that Pi
    mock_get_details.return_value = {
        'model': 'Raspberry Pi 5', 'ram': '8GiB', 'serial': '10000000abcdef', 'disks': []
    }

    # --- Call Endpoint ---
    response = client.post('/scan', json={
        'subnet': '192.168.1.0/24',
        'username': 'pi',
        'password': 'raspberry'
    })

    # --- Assertions ---
    assert response.status_code == 200
    mock_scan.assert_called_once_with(target_subnet='192.168.1.0/24')
    mock_get_details.assert_called_once_with('192.168.1.101', 'pi', 'raspberry')

    # Assert the complex JSON structure is correct
    expected_json = {
        'success': {
            '10000000abcdef': {
                'model': 'Raspberry Pi 5',
                'ram': '8GiB',
                'serial': '10000000abcdef',
                'disks': [],
                'connections': [{'ip': '192.168.1.101', 'mac': 'e4:5f:01:aa:bb:cc'}]
            }
        },
        'failed': []
    }
    assert response.json == expected_json


def test_scan_network_fails_without_subnet(client):
    """
    GIVEN a Flask client
    WHEN the '/scan' endpoint is called without required data
    THEN check that a 400 Bad Request error is returned.
    """
    response = client.post('/scan', json={})
    assert response.status_code == 400
    assert response.json == {'error': 'Subnet, username, and password are required.'}


def test_select_pi_saves_ip_and_redirects(client):
    """
    GIVEN a Flask client
    WHEN a POST request is made to '/select-pi' with an IP address
    THEN check that the IP is stored in the session and the user is redirected.
    """
    response = client.post('/select-pi', data={'pi_ip': '192.168.1.102'})
    assert response.status_code == 302
    assert response.headers['Location'].endswith('/')
    with client.session_transaction() as sess:
        assert sess['target_pi_ip'] == '192.168.1.102'


@patch('configurator_app.app.set_key')
def test_save_and_install(mock_set_key, client, app, mock_paths):
    """
    GIVEN a mocked set_key function and a client with a Pi IP in session
    WHEN a POST request is made to '/save-and-install'
    THEN check that files are written and credentials are saved.
    """
    with client.session_transaction() as sess:
        sess['target_pi_ip'] = '192.168.1.103'

    form_data = {
        'components': ['dashy', 'portainer'],
        'ssh_user': 'pi',
        'ssh_pass': 'raspberry'
    }

    response = client.post('/save-and-install', data=form_data)

    assert response.status_code == 200
    assert b"<h1>Installation Success</h1>" in response.data

    output_file = mock_paths["output_file"]
    assert output_file.exists()
    content = output_file.read_text()
    assert "dashy" in content and "portainer" in content

    env_path = str(mock_paths["env_file"])
    mock_set_key.assert_any_call(env_path, "PI_IP", '192.168.1.103')
    mock_set_key.assert_any_call(env_path, "SSH_USER", 'pi')
    mock_set_key.assert_any_call(env_path, "SSH_PASSWORD", 'raspberry')
    assert mock_set_key.call_count == 3