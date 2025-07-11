import pytest
import json
import os
import sys

# Ensure the 'src' directory is on the path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
src_path = os.path.join(project_root, 'src')
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from src.component_manager import ComponentManager

# A minimal, valid JSON structure for testing
VALID_METADATA = {
    "portainer": {
        "name": "Portainer",
        "uniqueness_group": None
    },
    "dashy": {
        "name": "Dashy",
        "uniqueness_group": "dashboard"
    },
    "heimdall": {
        "name": "Heimdall",
        "uniqueness_group": "dashboard"
    },
    "traefik": {
        "name": "Traefik",
        "uniqueness_group": "reverse_proxy"
    },
    "_piselfhosting": {
        "some_metadata": "value"
    }
}


def test_load_components_success(tmp_path):
    """
    Tests that the ComponentManager successfully loads a valid metadata file.
    """
    # Create a temporary metadata file
    metadata_file = tmp_path / "components.json"
    metadata_file.write_text(json.dumps(VALID_METADATA))

    # Initialize the manager
    manager = ComponentManager(metadata_path=metadata_file)

    # Assert that the components were loaded correctly
    assert manager.get_all_components() == VALID_METADATA
    assert manager.get_component_details("portainer")["name"] == "Portainer"


def test_load_components_file_not_found():
    """
    Tests that the ComponentManager raises FileNotFoundError for a missing file.
    """
    # Use a path that is guaranteed not to exist
    non_existent_file = "/path/to/a/very/unlikely/file.json"

    # Assert that the correct exception is raised
    with pytest.raises(FileNotFoundError, match="Required configuration file not found"):
        ComponentManager(metadata_path=non_existent_file)


def test_load_components_invalid_json(tmp_path):
    """
    Tests that the ComponentManager raises JSONDecodeError for a malformed file.
    """
    # Create a temporary file with invalid JSON
    metadata_file = tmp_path / "invalid.json"
    metadata_file.write_text("{'this is not valid json':}")

    # Assert that the correct exception is raised
    with pytest.raises(json.JSONDecodeError):
        ComponentManager(metadata_path=metadata_file)


def test_get_uniqueness_groups(tmp_path):
    """
    Tests that uniqueness groups are correctly identified and grouped.
    """
    metadata_file = tmp_path / "components.json"
    metadata_file.write_text(json.dumps(VALID_METADATA))

    manager = ComponentManager(metadata_path=metadata_file)
    groups = manager.get_uniqueness_groups()

    # Assert the structure and content of the groups
    assert "dashboard" in groups
    assert "reverse_proxy" in groups
    assert len(groups["dashboard"]) == 2
    assert "dashy" in groups["dashboard"]
    assert "heimdall" in groups["dashboard"]
    assert len(groups["reverse_proxy"]) == 1
    assert "traefik" in groups["reverse_proxy"]
    # Ensure internal keys are skipped
    assert "_piselfhosting" not in groups


def test_get_component_details_returns_none_for_missing_id(tmp_path):
    """
    Tests that get_component_details returns None for a non-existent component.
    """
    metadata_file = tmp_path / "components.json"
    metadata_file.write_text(json.dumps(VALID_METADATA))

    manager = ComponentManager(metadata_path=metadata_file)

    assert manager.get_component_details("non_existent_component") is None
