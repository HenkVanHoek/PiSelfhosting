# tests/test_setup.py
import pytest
import os
import configparser
from unittest.mock import patch, mock_open, call  # Ensure 'call' is imported

# Import the function(s) and variables from src/setup.py
from src.setup import parse_components_list, COMPONENTS_LIST_FILENAME, get_project_root, read_selected_components, \
    SELECTED_COMPONENTS_FILENAME


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
# No Dashy tile for direct DB access

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


# --- Tests for parse_components_list ---

def test_parse_components_list_full_format_success(mock_full_components_list_content):
    """
    Tests that parse_components_list correctly reads and parses the full INI-like file format.
    """
    with patch('builtins.open', mock_open(read_data=mock_full_components_list_content)) as mocked_file_open:
        with patch('os.path.exists', return_value=True):
            result = parse_components_list()

            assert result["components_order"] == ["homeassistant", "frigate", "mariadb", "dashy", "nginxproxymanager"]

            all_component_data = result["all_component_data"]
            assert "homeassistant" in all_component_data
            assert all_component_data["homeassistant"]["description"] == "Home Assistant (Home Automation)"
            assert all_component_data["homeassistant"]["default_selected"] == "ON"
            assert all_component_data["homeassistant"]["dashy_tile_url_suffix"] == ":8123"
            assert all_component_data["homeassistant"]["dashy_tile_status_check"] == "True"
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

            # Verify that open was called with the expected filename and encoding
            # Assuming parse_components_list uses encoding='utf-8' now.
            # If not, remove encoding='utf-8' or match locale.getpreferredencoding()
            mocked_file_open.assert_called_once_with(os.path.join(get_project_root(), COMPONENTS_LIST_FILENAME), 'r',
                                                     encoding='utf-8')


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
            assert "comp_b" in result["all_component_data"]
            assert result["all_component_data"]["comp_b"]["description"] == "B"

            # Assuming parse_components_list uses encoding='utf-8' now.
            # This asserts that open was called exactly with these arguments.
            mocked_file_open.assert_called_once_with(custom_path, 'r', encoding='utf-8')


def test_parse_components_list_io_error():
    """
    Tests that parse_components_list handles an IOError during file reading.
    (It re-raises the caught Exception after printing an error message).
    """
    # Mock os.path.exists to return True
    with patch('os.path.exists', return_value=True):
        # Mock 'builtins.open' to raise an IOError immediately upon opening
        # This will test the FileNotFoundError or a general IOError catch.
        with patch('builtins.open', side_effect=IOError("Permission denied during file open")):
            with pytest.raises(IOError) as excinfo:  # Expecting the original IOError
                parse_components_list()
            assert "Permission denied during file open" in str(excinfo.value)


# --- Tests for read_selected_components ---

def test_read_selected_components_success(mock_selected_components_content):
    """
    Tests that read_selected_components correctly reads and parses a valid file.
    """
    with patch('builtins.open', mock_open(read_data=mock_selected_components_content)) as mocked_file_open:
        with patch('os.path.exists', return_value=True):
            selected = read_selected_components()
            assert selected == {"homeassistant", "nginxproxymanager", "dashy"}
            mocked_file_open.assert_called_once_with(os.path.join(get_project_root(), SELECTED_COMPONENTS_FILENAME), 'r', encoding='utf-8')


def test_read_selected_components_file_not_found():
    """
    Tests that read_selected_components returns an empty set if the file does not exist.
    """
    with patch('os.path.exists', return_value=False):
        selected = read_selected_components()
        assert selected == set()


def test_read_selected_components_empty_file(mock_empty_selected_components_content):
    """
    Tests that read_selected_components returns an empty set for an empty file.
    """
    with patch('builtins.open', mock_open(read_data=mock_empty_selected_components_content)) as mocked_file_open:
        with patch('os.path.exists', return_value=True):
            selected = read_selected_components()
            assert selected == set()
            mocked_file_open.assert_called_once_with(os.path.join(get_project_root(), SELECTED_COMPONENTS_FILENAME), 'r', encoding='utf-8')


def test_read_selected_components_io_error():
    """
    Tests that read_selected_components handles an IOError during file reading.
    """
    with patch('builtins.open', side_effect=IOError("Disk full")) as mocked_file_open:
        with patch('os.path.exists', return_value=True):
            with pytest.raises(IOError) as excinfo:
                read_selected_components()
            assert "Disk full" in str(excinfo.value)
            mocked_file_open.assert_called_once_with(os.path.join(get_project_root(), SELECTED_COMPONENTS_FILENAME), 'r', encoding='utf-8')