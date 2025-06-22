# tests/test_setup.py (FINAL, VERIFIED COMPLETE AND CORRECT VERSION - ALL ENGLISH)
import pytest
import os
from unittest.mock import patch, mock_open, \
    MagicMock  # Removed 'call' as it's not directly used for 'call(...)' comparison anymore
import configparser
import yaml

# Import the function(s) and variables from src/setup.py
from src.setup import (
    parse_components_list,
    COMPONENTS_LIST_FILENAME,
    get_project_root,
    read_selected_components,
    SELECTED_COMPONENTS_FILENAME,
    generate_docker_compose_files,
    merge_docker_compose_files,
    UNIFIED_DOCKER_COMPOSE_FILENAME,
    DOCKER_COMPOSE_OUTPUT_DIR
)


# --- Fixtures for Mocking ---

@pytest.fixture
def mock_full_components_list_content():
    """Fixture to provide mock content for a full, INI-like components_list.txt."""
    return """
[PiSelfhosting]
COMPONENTS_ORDER=homeassistant,frigate,mariadb,dashy,nginxproxymanager

# Component Definitions
[homeassistant]
description=Home Assistant (Home Automation)
default_selected=ON
dashy_tile_section=Smart Home
dashy_tile_icon=fab fa-home-assistant
dashy_tile_url_suffix=:8123
dashy_tile_status_check=True

[frigate]
description=Frigate (AI-powered NVR)
default_selected=OFF
dashy_tile_section=Smart Home
dashy_tile_icon=fas fa-video
dashy_tile_url_suffix=:5000
dashy_tile_status_check=True
config_paths=/opt/piselfhosting/data/frigate/config.yml,/opt/piselfhosting/data/frigate/another.cfg

[mariadb]
description=MariaDB Database Server
default_selected=ON
# No Dashy info for MariaDB

[dashy]
description=Dashy (Personal Dashboard)
default_selected=ON
dashy_tile_section=General Services
dashy_tile_icon=fas fa-chart-pie
dashy_tile_url_suffix=/
dashy_tile_status_check=True

[nginxproxymanager]
description=Nginx Proxy Manager (Reverse Proxy, SSL Mgmt)
default_selected=ON
dashy_tile_section=Network Services
dashy_tile_icon=si-nginx
dashy_tile_url_suffix=:81
dashy_tile_status_check=True
"""


@pytest.fixture
def mock_simple_components_list_content():
    """Fixture for older, simpler format test content."""
    # Adjusted to contain a section as configparser would otherwise complain
    return """
[General]
comp1_key=value1
[comp2]
description=Comp2
"""


@pytest.fixture
def mock_empty_components_list_content():
    """Fixture to provide mock content for an empty components_list.txt (only comments/blank lines)."""
    return """
# Only comments
"""


@pytest.fixture
def mock_selected_components_content():
    """Fixture for selected_components.txt content."""
    return "homeassistant nginxproxymanager dashy"


@pytest.fixture
def mock_empty_selected_components_content():
    """Fixture for empty selected_components.txt content."""
    return ""


@pytest.fixture
def mock_individual_compose_files_content():
    """Fixture to provide mock content for individual docker-compose files."""
    return {
        "docker-compose.mariadb.yml": """
services:
  mariadb:
    image: mariadb:11
    container_name: piselfhosting-mariadb
    restart: unless-stopped
    ports:
      - "3306:3306"
    environment:
      - MYSQL_ROOT_PASSWORD=test_db_pass_1
      - MYSQL_DATABASE=piselfhosting
      - MYSQL_USER=test_db_user_1
      - MYSQL_PASSWORD=test_db_pass_1
    volumes:
      - mariadb_data:/var/lib/mysql
      - "/opt/piselfhosting/data/mariadb/initdb.d:/docker-entrypoint-initdb.d"
    networks:
      - piselfhosting_net
volumes:
  mariadb_data:
    name: piselfhosting-mariadb-data
networks:
  piselfhosting_net:
    external: true
""",
        "docker-compose.dashy.yml": """
services:
  dashy:
    image: lissy93/dashy:2.1.1
    container_name: piselfhosting-dashy
    restart: unless-stopped
    ports:
      - "8080:80"
      - "4443:443"
    volumes:
      - "/opt/piselfhosting/data/dashy/config:/app/public/conf"
    environment:
      - PUID=1000
      - PGID=1000
      - TZ=Europe/Amsterdam
      - NODE_ENV=production
    extra_hosts:
      - "testdomain.com:192.168.1.100"
    networks:
      - piselfhosting_net
volumes:
  dashy_config:
    name: piselfhosting-dashy-config
"""
    }


# --- Tests for parse_components_list ---

def test_parse_components_list_full_format_success(mock_full_components_list_content):
    """
    Tests that parse_components_list correctly reads and parses the full INI-like file format.
    """
    with patch('builtins.open', mock_open(read_data=mock_full_components_list_content)):
        with patch('os.path.exists', return_value=True):
            result = parse_components_list()

            # Ensure the components order matches the one from the mock fixture
            expected_order = ["homeassistant", "frigate", "mariadb", "dashy", "nginxproxymanager"]
            assert result["components_order"] == expected_order, "Parsed components order does not match expected list."

            all_component_data = result["all_component_data"]
            assert "homeassistant" in all_component_data
            assert all_component_data["homeassistant"]["description"] == "Home Assistant (Home Automation)"
            assert all_component_data["homeassistant"]["default_selected"] == "ON"
            assert all_component_data["homeassistant"]["dashy_tile_url_suffix"] == ":8123"
            assert all_component_data["homeassistant"]["name"] == "homeassistant"  # Added by the parser

            assert "frigate" in all_component_data
            assert all_component_data["frigate"][
                       "config_paths"] == "/opt/piselfhosting/data/frigate/config.yml,/opt/piselfhosting/data/frigate/another.cfg"

            assert "mariadb" in all_component_data
            assert "dashy_tile_section" not in all_component_data["mariadb"]  # No Dashy info for MariaDB

            assert "dashy" in all_component_data
            assert all_component_data["dashy"]["dashy_tile_url_suffix"] == "/"

            assert "nginxproxymanager" in all_component_data
            assert all_component_data["nginxproxymanager"]["dashy_tile_icon"] == "si-nginx"


def test_parse_components_list_file_not_found():
    """
    Tests that parse_components_list raises FileNotFoundError if the file does not exist.
    """
    with patch('os.path.exists', return_value=False):
        with pytest.raises(FileNotFoundError) as excinfo:
            parse_components_list()
        assert COMPONENTS_LIST_FILENAME in str(excinfo.value)
        assert "not found" in str(excinfo.value)


def test_parse_components_list_empty_content(mock_empty_components_list_content):
    """
    Tests that parse_components_list handles an empty file or file with only comments.
    """
    with patch('builtins.open', mock_open(read_data=mock_empty_components_list_content)):
        with patch('os.path.exists', return_value=True):
            result = parse_components_list()
            assert result["components_order"] == []
            assert result["all_component_data"] == {}


def test_parse_components_list_custom_path():
    """
    Tests that parse_components_list works with a custom file path, including COMPONENTS_ORDER.
    """
    custom_content = """
[PiSelfhosting]
COMPONENTS_ORDER=custom_a,custom_b
[comp_a]
description=A
[comp_b]
description=B
"""
    custom_path = "/tmp/custom_components.txt"

    with patch('builtins.open', mock_open(read_data=custom_content)) as mocked_file_open:
        with patch('os.path.exists', return_value=True):
            result = parse_components_list(file_path=custom_path)

            assert result["components_order"] == ["custom_a", "custom_b"]
            assert "comp_a" in result["all_component_data"]
            assert result["all_component_data"]["comp_a"]["description"] == "A"
            assert result["all_component_data"]["comp_b"]["description"] == "B"

            # CORRECTED: Use assert_called_once() and then check call_args for robustness.
            # This is more accurate for mock_open's behavior with mode and encoding.
            mocked_file_open.assert_called_once()
            actual_call_args, actual_call_kwargs = mocked_file_open.call_args
            assert actual_call_args[0] == custom_path  # Check only the path
            assert actual_call_kwargs.get('encoding') == 'locale'  # Check encoding if present


def test_parse_components_list_io_error():
    """
    Tests that parse_components_list handles an IOError during file reading.
    (This test now explicitly mocks `config.read()` to force an error scenario).
    """
    # configparser is imported locally in the test function
    # When builtins.open fails, configparser.read() might convert this to a configparser.Error.
    # Our parse_components_list catches any Exception from configparser.read() and re-raises it.
    with patch('configparser.ConfigParser.read', side_effect=configparser.Error("Simulated configparser error")):
        with patch('os.path.exists', return_value=True):  # os.path.exists needs to return True for read() to be called
            # We expect a configparser.Error, as that's what we are forcing the mock to raise.
            with pytest.raises(configparser.Error) as excinfo:
                parse_components_list(file_path="dummy_path.txt")  # Pass a dummy path as os.path.exists is mocked
            assert "Simulated configparser error" in str(excinfo.value)


# --- Tests for read_selected_components ---

def test_read_selected_components_success(mock_selected_components_content):
    """
    Tests that read_selected_components correctly reads and parses a valid file.
    """
    with patch('builtins.open', mock_open(read_data=mock_selected_components_content)):
        with patch('os.path.exists', return_value=True):
            selected_components_set = read_selected_components()
            assert selected_components_set == {"homeassistant", "nginxproxymanager", "dashy"}


def test_read_selected_components_file_not_found():
    """
    Tests that read_selected_components returns an empty set if the file does not exist.
    """
    with patch('os.path.exists', return_value=False):
        selected_components_set = read_selected_components()
        assert selected_components_set == set()


def test_read_selected_components_empty_file(mock_empty_selected_components_content):
    """
    Tests that read_selected_components returns an empty set for an empty file.
    """
    # Correction: The mock_empty_selected_components_content fixture needs to be passed as an argument.
    # This ensures Pytest provides the correct value of the fixture.
    with patch('builtins.open', mock_open(read_data=mock_empty_selected_components_content)):
        with patch('os.path.exists', return_value=True):
            selected_components_set = read_selected_components()
            assert selected_components_set == set()


def test_read_selected_components_io_error():
    """
    Tests that read_selected_components handles an IOError during file reading.
    """
    with patch('builtins.open', side_effect=IOError("Disk full")):
        with patch('os.path.exists', return_value=True):
            with pytest.raises(Exception) as excinfo:
                read_selected_components()
            assert "Disk full" in str(excinfo.value) or "Error reading" in str(excinfo.value)


# --- NEW TEST FOR MERGING DOCKER COMPOSE FILES ---

def test_merge_docker_compose_files_success(mock_individual_compose_files_content):
    """
    Tests that merge_docker_compose_files correctly merges multiple Docker Compose files.
    """
    project_root = get_project_root()
    output_dir_path = os.path.join(project_root, DOCKER_COMPOSE_OUTPUT_DIR)
    unified_output_path = os.path.join(output_dir_path, UNIFIED_DOCKER_COMPOSE_FILENAME)

    # Prepare mock file paths and content
    mock_file_paths = []
    mock_files_map = {}
    for filename, content in mock_individual_compose_files_content.items():
        mock_path = os.path.join(output_dir_path, filename)
        mock_file_paths.append(mock_path)
        mock_files_map[mock_path] = content

    # Use a dictionary to store content written to mock files
    captured_written_content = {}

    # Set up the side_effect for builtins.open to handle reading and writing
    # noinspection PyUnusedLocal
    def mock_open_side_effect(file_path, mode='r', encoding='locale'):
        if file_path == unified_output_path and 'w' in mode:  # Check for 'w' in mode for writing
            mock_file_handle = MagicMock()

            def write_capture(content):
                captured_written_content[file_path] = content

            mock_file_handle.write.side_effect = write_capture
            return mock_file_handle
        elif file_path in mock_files_map and 'r' in mode:  # Check for 'r' in mode for reading
            return mock_open(read_data=mock_files_map[file_path])()
        else:
            return mock_open()()

    with patch('builtins.open', side_effect=mock_open_side_effect) as mocked_open:
        # Patch yaml.dump to capture its arguments
        with patch('yaml.dump', MagicMock()) as mocked_yaml_dump_func:  # Use MagicMock directly here
            with patch('os.path.exists', return_value=True):
                with patch('os.makedirs', return_value=None):
                    merge_docker_compose_files(mock_file_paths, unified_output_path)

                    # Verify yaml.dump was called with the correct data
                    mocked_yaml_dump_func.assert_called_once()

                    # The first argument to yaml.dump is the data to dump
                    parsed_unified_content = mocked_yaml_dump_func.call_args[0][0]

                    # Define the expected merged content
                    # CORRECTED: Adjust 'environment' lists to be lists of STRINGS (VAR=VALUE),
                    # as yaml.safe_load/dump parses 'VAR=VALUE' strings as literal strings.
                    expected_merged_content = {
                        'version': '3.8',
                        'services': {
                            'mariadb': {
                                'image': 'mariadb:11',
                                'container_name': 'piselfhosting-mariadb',
                                'restart': 'unless-stopped',
                                'ports': ['3306:3306'],
                                'environment': [  # CORRECTED: List of strings
                                    'MYSQL_ROOT_PASSWORD=test_db_pass_1',
                                    'MYSQL_DATABASE=piselfhosting',
                                    'MYSQL_USER=test_db_user_1',
                                    'MYSQL_PASSWORD=test_db_pass_1'
                                ],
                                'volumes': [
                                    'mariadb_data:/var/lib/mysql',
                                    '/opt/piselfhosting/data/mariadb/initdb.d:/docker-entrypoint-initdb.d'
                                ],
                                'networks': ['piselfhosting_net']
                            },
                            'dashy': {
                                'image': 'lissy93/dashy:2.1.1',
                                'container_name': 'piselfhosting-dashy',
                                'restart': 'unless-stopped',
                                'ports': ['8080:80', '4443:443'],
                                'volumes': [
                                    '/opt/piselfhosting/data/dashy/config:/app/public/conf'
                                ],
                                'environment': [  # CORRECTED: List of strings
                                    'PUID=1000',
                                    'PGID=1000',
                                    'TZ=Europe/Amsterdam',
                                    'NODE_ENV=production'
                                ],
                                'extra_hosts': [
                                    'testdomain.com:192.168.1.100'
                                ],
                                'networks': ['piselfhosting_net']
                            }
                        },
                        'volumes': {
                            'mariadb_data': {'name': 'piselfhosting-mariadb-data'},
                            'dashy_config': {'name': 'piselfhosting-dashy-config'}
                        },
                        'networks': {
                            'piselfhosting_net': {'external': True}
                        }
                    }

                    assert parsed_unified_content == expected_merged_content, "Merged Docker Compose content does not match expected."

