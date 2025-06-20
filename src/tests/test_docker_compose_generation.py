# tests/test_docker_compose_generation.py
import pytest
import os
from unittest.mock import patch, mock_open, call
import yaml  # We will use this to assert the YAML structure
import io  # Used for mocking file reads/writes with strings

# Import the functions from src/setup.py
from src.setup import (
    parse_components_list,
    read_selected_components,
    get_project_root,
    generate_docker_compose_file  # Now that it's implemented, we can import it
)


# --- Fixtures for Mocking Data ---

@pytest.fixture
def mock_parsed_components_data():
    """Mock return value for parse_components_list."""
    return {
        "components_order": ["homeassistant", "frigate", "mariadb"],
        "all_component_data": {
            "homeassistant": {
                "name": "homeassistant",
                "description": "Home Assistant (Home Automation)",
                "default_selected": "ON"
            },
            "frigate": {
                "name": "frigate",
                "description": "Frigate (AI-powered NVR)",
                "default_selected": "OFF"
            },
            "mariadb": {
                "name": "mariadb",
                "description": "MariaDB Database Server",
                "default_selected": "ON"
            }
        }
    }


@pytest.fixture
def mock_selected_components():
    """Mock return value for read_selected_components."""
    return {"homeassistant"}  # Only homeassistant is selected


@pytest.fixture
def mock_homeassistant_template_content():
    """Mock content for homeassistant's docker-compose.template.yml."""
    return """
services:
  homeassistant:
    container_name: homeassistant
    image: "ghcr.io/home-assistant/home-assistant:stable"
    volumes:
      - ./docker/homeassistant/config:/config
      - /etc/localtime:/etc/localtime:ro
    environment:
      - PUID=${PUID}
      - PGID=${PGID}
      - TZ=Europe/Amsterdam
    ports:
      - 8123:8123
    restart: unless-stopped
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.homeassistant.rule=Host(`homeassistant.${DOMAIN}`)"
      - "traefik.http.routers.homeassistant.entrypoints=websecure"
      - "traefik.http.routers.homeassistant.tls.certresolver=letsencrypt"
      - "traefik.http.services.homeassistant.loadbalancer.server.port=8123"
"""


@pytest.fixture
def expected_homeassistant_compose_content():
    """Expected content for the generated docker-compose.yml for homeassistant."""
    return """
version: "3.8"
services:
  homeassistant:
    container_name: homeassistant
    image: "ghcr.io/home-assistant/home-assistant:stable"
    volumes:
      - ./docker/homeassistant/config:/config
      - /etc/localtime:/etc/localtime:ro
    environment:
      - PUID=1000
      - PGID=1000
      - TZ=Europe/Amsterdam
    ports:
      - 8123:8123
    restart: unless-stopped
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.homeassistant.rule=Host(`homeassistant.henkenyvonne.nl`)"
      - "traefik.http.routers.homeassistant.entrypoints=websecure"
      - "traefik.http.routers.homeassistant.tls.certresolver=letsencrypt"
      - "traefik.http.services.homeassistant.loadbalancer.server.port=8123"
volumes: {}
networks: {}
"""


# --- Test for Docker Compose Generation ---

# We will patch get_project_root to ensure consistent paths for testing
@patch('src.setup.get_project_root', return_value='/mock/project/root')
# We will patch parse_components_list to control its return value
@patch('src.setup.parse_components_list')
# We will patch read_selected_components to control its return value
@patch('src.setup.read_selected_components')
# We will patch os.path.exists to control file existence checks
@patch('os.path.exists', return_value=True)
# We will patch builtins.open to control file reads and capture file writes
@patch('builtins.open', new_callable=mock_open)
# We will patch os.environ to control environment variables
@patch.dict(os.environ, {'DOMAIN': 'henkenyvonne.nl', 'PUID': '1000', 'PGID': '1000'}, clear=True)
# NEW PATCH: Mock os.makedirs to prevent actual directory creation
@patch('os.makedirs')
def test_generate_docker_compose_for_single_service(
        mock_makedirs,
        mock_open_file,  # This is the MagicMock for builtins.open
        mock_path_exists,
        mock_read_selected_components_func,
        mock_parse_components_list_func,
        mock_get_project_root_func,
        mock_parsed_components_data,
        mock_selected_components,
        mock_homeassistant_template_content,
        expected_homeassistant_compose_content
):
    """
    Tests that generate_docker_compose_file correctly creates a docker-compose.yml
    for a single selected service with variable substitution.
    """
    mock_parse_components_list_func.return_value = mock_parsed_components_data
    mock_read_selected_components_func.return_value = mock_selected_components

    # Create a StringIO object to capture what is written to the mocked file
    mock_file_content_buffer = io.StringIO()

    # Configure mock_open_file's side_effect
    # The first call (reading template) returns a StringIO with template content.
    # The second call (writing output) returns a mock file object whose .write method
    # will write to our mock_file_content_buffer.
    def open_side_effect(file_path, mode='r', **kwargs):
        if mode == 'r':
            if 'docker-compose.template.yml' in file_path and 'homeassistant' in file_path:
                return io.StringIO(mock_homeassistant_template_content)
        elif mode == 'w':
            # When open(..., 'w') is called, return a mock file object
            # whose write method appends to our buffer
            write_mock = mock_open_file.return_value  # The mock file object
            write_mock.write.side_effect = lambda content: mock_file_content_buffer.write(content)
            return write_mock
        raise ValueError(f"Unexpected open call: path={file_path}, mode={mode}")  # Or handle other modes

    mock_open_file.side_effect = open_side_effect

    # Call the actual function
    generate_docker_compose_file(mock_parsed_components_data['all_component_data'], mock_selected_components,
                                 output_dir='/mock/project/root',
                                 template_dir='/mock/project/root/scripts/template')

    # Assertions on the calls to mocked functions
    mock_makedirs.assert_called_once_with('/mock/project/root', exist_ok=True)

    template_path = os.path.normpath(
        os.path.join('/mock/project/root', 'scripts', 'template', 'homeassistant', 'docker-compose.template.yml'))

    found_template_read_call = False
    for call_obj in mock_open_file.call_args_list:
        called_path = os.path.normpath(call_obj[0][0])
        called_mode = call_obj[0][1]
        called_encoding = call_obj[1].get('encoding')
        if called_path == template_path and called_mode == 'r' and called_encoding == 'utf-8':
            found_template_read_call = True
            break
    assert found_template_read_call, f"Expected template read call not found for path: {template_path}"

    output_path = os.path.normpath(os.path.join('/mock/project/root', 'docker-compose.yml'))

    found_output_write_call = False
    for call_obj in mock_open_file.call_args_list:
        called_path = os.path.normpath(call_obj[0][0])
        called_mode = call_obj[0][1]
        called_encoding = call_obj[1].get('encoding')
        if called_path == output_path and called_mode == 'w' and called_encoding == 'utf-8':
            found_output_write_call = True
            break
    assert found_output_write_call, f"Expected output write call not found for path: {output_path}"

    # --- THIS IS THE CRUCIAL CHANGE ---
    written_content = mock_file_content_buffer.getvalue()  # Get content from our buffer

    assert yaml.safe_load(written_content) == yaml.safe_load(expected_homeassistant_compose_content)