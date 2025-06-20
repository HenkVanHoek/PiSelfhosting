# tests/test_interactive_selection.py
import pytest
import os
from unittest.mock import patch, mock_open
from src.setup import select_components_interactively_and_save, SELECTED_COMPONENTS_FILENAME, get_project_root


# Mock data for components_list.txt (as parsed by parse_components_list)
@pytest.fixture
def mock_parsed_components_data():
    return {
        "components_order": ["homeassistant", "frigate", "mariadb", "dashy", "nginxproxymanager"],
        "all_component_data": {
            "homeassistant": {"name": "homeassistant", "description": "Home Assistant (Home Automation)",
                              "default_selected": "ON"},
            "frigate": {"name": "frigate", "description": "Frigate (AI-powered NVR)", "default_selected": "OFF"},
            "mariadb": {"name": "mariadb", "description": "MariaDB Database Server", "default_selected": "ON"},
            "dashy": {"name": "dashy", "description": "Dashy (Personal Dashboard)", "default_selected": "ON"},
            "nginxproxymanager": {"name": "nginxproxymanager",
                                  "description": "Nginx Proxy Manager (Reverse Proxy, SSL Mgmt)",
                                  "default_selected": "ON"},
        }
    }


# Mock for read_selected_components to control initial state
@pytest.fixture
def mock_read_selected_components():
    with patch('src.setup.read_selected_components') as mock_read:
        yield mock_read


# Mock for open() to capture file writes
@pytest.fixture
def mock_file_write():
    with patch('builtins.open', new_callable=mock_open) as mock_file:
        yield mock_file


# --- Tests for select_components_interactively_and_save ---

def test_select_components_adds_new(mock_parsed_components_data, mock_read_selected_components, mock_file_write,
                                    capsys):
    """
    Tests selecting new components when starting from an empty selection.
    """
    mock_read_selected_components.return_value = set()  # Start with no components selected

    # Simulate user input: select Home Assistant (1) and Dashy (4), then press Enter
    user_inputs = iter(["1", "4", ""])
    with patch('builtins.input', side_effect=lambda msg: next(user_inputs)):
        selected_components = select_components_interactively_and_save(mock_parsed_components_data)

        # Assertions
        assert selected_components == {"homeassistant", "dashy"}

        # Verify file write content
        expected_content = "dashy homeassistant"  # sorted alphabetically
        mock_file_write.assert_called_once_with(os.path.join(get_project_root(), SELECTED_COMPONENTS_FILENAME), 'w',
                                                encoding='utf-8')
        mock_file_write().write.assert_called_once_with(expected_content)

        # Verify output messages (optional, but good for interactive functions)
        captured = capsys.readouterr()
        assert "homeassistant' selected." in captured.out
        assert "dashy' selected." in captured.out
        assert "Successfully saved selected components" in captured.out


def test_select_components_deselects_existing(mock_parsed_components_data, mock_read_selected_components,
                                              mock_file_write, capsys):
    """
    Tests deselecting components that were initially selected.
    """
    mock_read_selected_components.return_value = {"mariadb", "nginxproxymanager"}  # Start with some selected

    # Simulate user input: deselect MariaDB (3), then press Enter
    user_inputs = iter(["3", ""])
    with patch('builtins.input', side_effect=lambda msg: next(user_inputs)):
        selected_components = select_components_interactively_and_save(mock_parsed_components_data)

        # Assertions
        assert selected_components == {"nginxproxymanager"}

        # Verify file write content
        expected_content = "nginxproxymanager"
        mock_file_write.assert_called_once_with(os.path.join(get_project_root(), SELECTED_COMPONENTS_FILENAME), 'w',
                                                encoding='utf-8')
        mock_file_write().write.assert_called_once_with(expected_content)

        captured = capsys.readouterr()
        assert "mariadb' deselected." in captured.out


def test_select_components_no_change(mock_parsed_components_data, mock_read_selected_components, mock_file_write,
                                     capsys):
    """
    Tests confirming selection without making changes.
    """
    mock_read_selected_components.return_value = {"homeassistant", "dashy"}  # Start with some selected

    # Simulate user input: just press Enter
    user_inputs = iter([""])
    with patch('builtins.input', side_effect=lambda msg: next(user_inputs)):
        selected_components = select_components_interactively_and_save(mock_parsed_components_data)

        # Assertions
        assert selected_components == {"homeassistant", "dashy"}

        # Verify file write content (should still write the original selection)
        expected_content = "dashy homeassistant"  # sorted
        mock_file_write.assert_called_once_with(os.path.join(get_project_root(), SELECTED_COMPONENTS_FILENAME), 'w',
                                                encoding='utf-8')
        mock_file_write().write.assert_called_once_with(expected_content)


def test_select_components_invalid_input(mock_parsed_components_data, mock_read_selected_components, mock_file_write,
                                         capsys):
    """
    Tests handling of invalid input (non-numeric, out-of-range).
    """
    mock_read_selected_components.return_value = set()

    # Simulate user input: invalid, then out-of-range, then valid (1), then Enter
    user_inputs = iter(["abc", "99", "1", ""])
    with patch('builtins.input', side_effect=lambda msg: next(user_inputs)):
        selected_components = select_components_interactively_and_save(mock_parsed_components_data)

        assert selected_components == {"homeassistant"}

        captured = capsys.readouterr()
        assert "Error: Invalid input. Please enter numbers separated by spaces." in captured.out
        assert "Warning: Invalid number '99'." in captured.out
        assert "homeassistant' selected." in captured.out