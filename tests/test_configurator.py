# tests/test_configurator.py
import os
import pytest
import json
from unittest.mock import patch

# Assume app.py and component_manager.py are in a directory named 'configurator_app'
# and this test is run from the project root.
from configurator_app.app import app


@pytest.fixture
def client(tmp_path):
    """
    A pytest fixture to set up the Flask test client and a temporary
    metadata file for testing.
    """
    # Create a temporary directory for the test to run in
    test_dir = tmp_path

    # Create a dummy metadata file that the app will load
    metadata_path = test_dir / "components_metadata.json"
    metadata_content = {
        "dashy": {"name": "Dashy", "description": "A dashboard."},
        "frigate": {"name": "Frigate", "description": "An NVR."}
    }
    with open(metadata_path, 'w') as f:
        json.dump(metadata_content, f)

    # Create a dummy executor script that the app will try to run
    (test_dir / "piselfhosting_installer.py").touch()

    # --- Patching ---
    # We need to tell the app where to find its files during the test
    with patch('configurator_app.app.METADATA_FILE', str(metadata_path)), \
            patch('configurator_app.app.SELECTED_COMPONENTS_OUTPUT_FILE', str(test_dir / "selected_components.txt")), \
            patch('configurator_app.app.EXECUTOR_SCRIPT', str(test_dir / "piselfhosting_installer.py")):
        app.config['TESTING'] = True
        with app.test_client() as test_client:
            yield test_client  # This is what the test functions will use


def test_index_page_loads_successfully(client):
    """
    Test 1 (RED/GREEN): Does the main page load correctly?
    """
    response = client.get('/')
    assert response.status_code == 200
    assert b"PiSelfhosting Configurator" in response.data
    assert b"Dashy" in response.data  # Check if component from dummy metadata is shown
    assert b"Frigate" in response.data


def test_install_creates_file_and_launches_script(client):
    """
    Test 2 (RED/GREEN): Does submitting the form generate the correct file
    and attempt to launch the installer script?
    """
    # Use patch to "catch" the call to launch a subprocess without actually running it
    with patch('subprocess.Popen') as mock_popen:
        # Simulate a user selecting 'frigate' and 'dashy' and clicking the button
        client.post('/install', data={
            'components': ['frigate', 'dashy']
        })

        # --- Assertions ---
        # 1. Was the subprocess command called exactly once?
        mock_popen.assert_called_once()

        # 2. Was the 'selected_components.txt' file created?
        output_file_path = client.application.config['SELECTED_COMPONENTS_OUTPUT_FILE']
        assert os.path.exists(output_file_path)

        # 3. Does the file have the correct content?
        with open(output_file_path, 'r') as f:
            content = f.read()
            # The order might vary, so check for both parts
            assert "dashy" in content
            assert "frigate" in content


def test_install_with_no_selection(client):
    """
    Test 3 (RED/GREEN): Does submitting with no components selected work correctly?
    """
    with patch('subprocess.Popen') as mock_popen:
        # Simulate a user clicking the button without checking any boxes
        client.post('/install', data={})

        # --- Assertions ---
        mock_popen.assert_called_once()

        output_file_path = client.application.config['SELECTED_COMPONENTS_OUTPUT_FILE']
        assert os.path.exists(output_file_path)

        # The file should be created but empty
        with open(output_file_path, 'r') as f:
            content = f.read()
            assert content == ""