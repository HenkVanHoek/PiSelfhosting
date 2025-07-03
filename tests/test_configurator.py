# tests/test_configurator.py
import os
import pytest
from unittest.mock import patch

# Assume app.py is in a directory named 'configurator_app'
from configurator_app.app import app


@pytest.fixture
def client():
    """A pytest fixture to set up the Flask test client."""
    app.config['TESTING'] = True
    with app.test_client() as test_client:
        yield test_client


def test_index_page_loads_successfully(client):
    """
    Test 1: Does the main page load correctly?
    We now 'mock' the component manager to pretend it loaded data.
    """
    # This mock pretends that the ComponentManager found two components.
    mock_components = {
        "dashy": {"name": "Dashy", "description": "A dashboard."},
        "frigate": {"name": "Frigate", "description": "An NVR."}
    }
    with patch('configurator_app.app.manager.get_all_components', return_value=mock_components):
        response = client.get('/')

    assert response.status_code == 200
    assert b"PiSelfhosting Configurator" in response.data
    assert b"Dashy" in response.data  # This will now pass
    assert b"Frigate" in response.data


def test_install_creates_file_and_launches_script(tmp_path):
    """
    Test 2: Does submitting the form generate the correct file and
    attempt to launch the installer script?
    This test now uses tmp_path to handle files cleanly.
    """
    # Define temporary file paths for this specific test
    selected_components_file = tmp_path / "selected_components.txt"
    executor_script = tmp_path / "piselfhosting_installer.py"
    executor_script.touch()  # Create a dummy file to launch

    # We patch the constants within app.py to point to our temporary files
    with patch('configurator_app.app.SELECTED_COMPONENTS_OUTPUT_FILE', str(selected_components_file)), \
            patch('configurator_app.app.EXECUTOR_SCRIPT', str(executor_script)), \
            patch('subprocess.Popen') as mock_popen:
        with app.test_client() as client:
            client.post('/install', data={'components': ['frigate', 'dashy']})

        # --- Assertions ---
        # 1. Was the installer script launch attempted?
        mock_popen.assert_called_once()

        # 2. Was the 'selected_components.txt' file created?
        assert selected_components_file.exists()

        # 3. Does the file have the correct content?
        content = selected_components_file.read_text()
        assert "dashy" in content
        assert "frigate" in content


def test_install_with_no_selection(tmp_path):
    """
    Test 3: Does submitting with no components selected work correctly?
    """
    selected_components_file = tmp_path / "selected_components.txt"
    executor_script = tmp_path / "piselfhosting_installer.py"
    executor_script.touch()

    with patch('configurator_app.app.SELECTED_COMPONENTS_OUTPUT_FILE', str(selected_components_file)), \
            patch('configurator_app.app.EXECUTOR_SCRIPT', str(executor_script)), \
            patch('subprocess.Popen') as mock_popen:
        with app.test_client() as client:
            client.post('/install', data={})

        # --- Assertions ---
        mock_popen.assert_called_once()
        assert selected_components_file.exists()

        # The file should be created but empty
        content = selected_components_file.read_text()
        assert content == ""