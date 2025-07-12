import pytest
import json
import os
from unittest.mock import patch, MagicMock

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
    mock_components = {
        "_piselfhosting": {
            "components_order": ["portainer", "dashy"]
        },
        "dashy": {
            "name": "Dashy",
            "description": "A dashboard.",
            "dashy_section": "Dashboards"
        },
        "portainer": {
            "name": "Portainer",
            "description": "Container management.",
            "dashy_section": "Utilities"
        }
    }
    mock_paths["metadata_file"].write_text(json.dumps(mock_components))

    # Create dummy template files
    (mock_paths["template_dir"] / "select_pi.html").write_text("<h1>Select a Pi</h1>")

    select_components_template = """
    <h1>Select Components</h1>
    <p>{{ pi_ip }}</p>
    {% for group_name, component_list in grouped_components.items() %}
        <h2>{{ group_name }}</h2>
        {% for component in component_list %}
            <p>{{ component.data.name }}</p>
        {% endfor %}
    {% endfor %}
    """
    (mock_paths["template_dir"] / "select_components.html").write_text(select_components_template)

    # --- CORRECTED: Mock templates now reflect the new installation flow ---
    # install_success.html should link to the live log page.
    # We use a hardcoded link for simplicity in the test.
    (mock_paths["template_dir"] / "install_success.html").write_text(
        '<h1>Ready to Install</h1><a href="/live-log">Start Installation</a>'
    )
    # live_log.html should contain the log output area.
    (mock_paths["template_dir"] / "live_log.html").write_text(
        '<h1>Live Log</h1><pre id="log-output"></pre>'
    )

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
    assert b"<h2>Dashboards</h2>" in response.data
    assert b"Dashy" in response.data
    assert b"<h2>Utilities</h2>" in response.data
    assert b"Portainer" in response.data


@patch('configurator_app.app.PiScanner.get_device_details')
@patch('configurator_app.app.PiScanner.scan')
def test_scan_network_endpoint(mock_scan, mock_get_details, client):
    """
    GIVEN mocked PiScanner methods
    WHEN the '/scan' endpoint is called
    THEN check that the scanner is called and returns a structured response.
    """
    mock_scan.return_value = [{'ip': '192.168.1.101', 'mac': 'e4:5f:01:aa:bb:cc'}]
    mock_get_details.return_value = {
        'model': 'Raspberry Pi 5', 'ram': '8GiB', 'serial': '10000000abcdef', 'disks': []
    }

    response = client.post('/scan', json={
        'subnet': '192.168.1.0/24',
        'username': 'pi',
        'password': 'raspberry'
    })

    assert response.status_code == 200
    mock_scan.assert_called_once_with(target_subnet='192.168.1.0/24')
    mock_get_details.assert_called_once_with('192.168.1.101', 'pi', 'raspberry')
    assert '10000000abcdef' in response.json['success']


def test_scan_network_fails_without_required_data(client):
    """
    GIVEN a Flask client
    WHEN the '/scan' endpoint is called without required data
    THEN check that a 400 Bad Request error is returned.
    """
    response = client.post('/scan', json={})
    assert response.status_code == 400
    assert response.json == {'error': 'Subnet and username are required.'}


def test_select_pi_saves_ip_and_redirects(client):
    """
    GIVEN a Flask client
    WHEN a POST request is made to '/select-pi' with an IP address
    THEN check that the IP is stored in the session and the user is redirected.
    """
    response = client.post('/select-pi', data={'pi_ip': '192.168.1.102'})

    assert response.status_code == 302
    assert response.headers['Location'] == '/'

    with client.session_transaction() as sess:
        assert sess['target_pi_ip'] == '192.168.1.102'


@patch('configurator_app.app.set_key')
def test_save_and_install_shows_success_page(mock_set_key, client, app, mock_paths):
    """
    GIVEN a mocked set_key function and a client with a Pi IP in session
    WHEN a POST request is made to '/save-and-install'
    THEN check that the success page with a link to the live log is shown.
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
    # --- CORRECTED: Check for the content of the new success page ---
    assert b'<h1>Ready to Install</h1>' in response.data
    assert b'<a href="/live-log">' in response.data

    # Verify that files were still written correctly
    output_file = mock_paths["output_file"]
    assert output_file.exists()
    assert "dashy" in output_file.read_text()

    env_path = str(mock_paths["env_file"])
    mock_set_key.assert_any_call(env_path, "PI_IP", '192.168.1.103')


# --- NEW TESTS FOR LIVE LOGGING ---

def test_live_log_page_renders(client):
    """
    GIVEN a Flask client
    WHEN the '/live-log' page is requested
    THEN check that the live log page is rendered correctly.
    """
    response = client.get('/live-log')
    assert response.status_code == 200
    assert b'<h1>Live Log</h1>' in response.data
    assert b'<pre id="log-output">' in response.data


@patch('configurator_app.app.os.path.exists', return_value=True)
@patch('configurator_app.app.subprocess.Popen')
def test_install_stream_success(mock_popen, mock_exists, client):
    """
    GIVEN a mocked subprocess.Popen that simulates a successful script run
    WHEN the '/install-stream' endpoint is called
    THEN check that it streams the subprocess output correctly in SSE format.
    """
    # --- Setup Mock ---
    mock_process = MagicMock()
    mock_process.stdout.readline.side_effect = [
        "Starting installation...\n",
        "Step 1: Doing something...\n",
        "Step 2: All done.\n",
        ""  # An empty string signifies the end of the stream for iter()
    ]
    mock_process.wait.return_value = 0  # Successful exit code
    mock_popen.return_value = mock_process

    # --- Call Endpoint ---
    response = client.get('/install-stream')

    # --- Assertions ---
    assert response.status_code == 200
    assert response.mimetype == 'text/event-stream'
    assert response.is_streamed

    streamed_data = response.data.decode('utf-8')
    expected_content = (
        "data: Starting installation...\n\n"
        "data: Step 1: Doing something...\n\n"
        "data: Step 2: All done.\n\n"
        "data: \n--- SCRIPT FINISHED (Exit Code: 0) ---\n\n"
    )
    assert streamed_data == expected_content
    mock_popen.assert_called_once()


@patch('configurator_app.app.os.path.exists', return_value=False)
def test_install_stream_script_not_found(mock_exists, client):
    """
    GIVEN the installer script does not exist (mocked by os.path.exists)
    WHEN the '/install-stream' endpoint is called
    THEN check that it returns a fatal error message in the stream.
    """
    response = client.get('/install-stream')
    assert response.status_code == 200
    streamed_data = response.data.decode('utf-8')

    assert "data: FATAL ERROR: Installer script not found" in streamed_data
    assert "data: --- SCRIPT FINISHED ---" in streamed_data