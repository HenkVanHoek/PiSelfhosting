# tests/test_configurator.py
import pytest
import json
from unittest.mock import patch
from configurator_app.app import create_app


@pytest.fixture
def app(tmp_path):
    """Create and configure a new app instance for each test."""

    # Define paths for all the dummy files our test app will need
    metadata_path = tmp_path / "components_metadata.json"
    template_path = tmp_path / "templates"

    # Create the necessary directories and files for the test
    template_path.mkdir()
    (template_path / "index.html").write_text(
        "<h1>PiSelfhosting Configurator</h1>{% for id, data in components.items() %}<p>{{ data.name }}</p>{% endfor %}")
    (template_path / "install_success.html").write_text("Success Page!")

    # Create a dummy metadata file for the app to load
    mock_components = {
        "dashy": {"name": "Dashy", "description": "A dashboard."}
    }
    metadata_path.write_text(json.dumps(mock_components))

    # Use the factory to create the app, passing all necessary paths in the test config
    app = create_app({
        'TESTING': True,
        'METADATA_FILE': str(metadata_path),
        # Flask's built-in loader uses the 'root_path' and this relative folder name
        'TEMPLATE_FOLDER': 'templates'
    })

    # Manually set the template folder to our temporary path for the test instance
    app.template_folder = str(template_path)

    yield app


@pytest.fixture
def client(app):
    """A test client for the app."""
    return app.test_client()


def test_index_page_loads_successfully(client):
    """Test the main page loads and shows components from the dummy metadata."""
    response = client.get('/')
    assert response.status_code == 200
    assert b"PiSelfhosting Configurator" in response.data
    assert b"Dashy" in response.data


def test_install_route(client, tmp_path):
    """Test that the install route writes the file and renders the success template."""
    selected_components_file = tmp_path / "selected_components.txt"

    # We can patch the config on the already created app instance for this test
    client.application.config['SELECTED_COMPONENTS_OUTPUT_FILE'] = str(selected_components_file)

    response = client.post('/install', data={'components': ['frigate', 'dashy']})

    assert response.status_code == 200
    assert b"Success Page!" in response.data
    assert selected_components_file.exists()

    content = selected_components_file.read_text()
    assert "frigate" in content
    assert "dashy" in content