import json

import pytest

# Correction: Import from the 'src' directory
from src.component_manager import ComponentManager


@pytest.fixture
def mock_project_structure(tmp_path):
    """
    Creates a temporary project structure with a component metadata file.
    This fixture is automatically called by pytest to initialize
    ComponentManager tests that have it as an argument.
    """
    # Create a temporary directory for the configuration
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    # Define the default metadata for the tests
    metadata = {
        "_piselfhosting": {"components_order": ["dashy", "portainer", "frigate"]},
        "dashy": {
            "name": "Dashy",
            "description": "A self-hosted dashboard.",
            "uniqueness_group": None,
        },
        "portainer": {
            "name": "Portainer",
            "description": "Container management UI.",
            "uniqueness_group": "container_manager",
        },
        "frigate": {
            "name": "Frigate",
            "description": "NVR with AI.",
            "uniqueness_group": None,
        },
    }

    # Write the metadata to the JSON file within the temporary directory
    metadata_path = config_dir / "components_metadata.json"
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f)

    # The ComponentManager expects the path to the *file*, so we return that
    return metadata_path


def test_manager_loads_components_successfully(mock_project_structure):
    """Test that the ComponentManager initializes correctly with valid metadata."""
    # The 'mock_project_structure' fixture is automatically used here
    manager = ComponentManager(metadata_path=mock_project_structure)

    all_components = manager.get_all_components()
    assert "dashy" in all_components
    assert "portainer" in all_components
    assert "_piselfhosting" in all_components


def test_get_component_details(mock_project_structure):
    """Test retrieving details for a specific component."""
    manager = ComponentManager(metadata_path=mock_project_structure)

    # Test retrieving a valid component
    details = manager.get_component_details("dashy")
    assert details is not None
    assert details["name"] == "Dashy"

    # Test retrieving a non-existent component
    details_none = manager.get_component_details("non_existent_component")
    assert details_none is None


def test_manager_raises_file_not_found_on_init(tmp_path):
    """Test that the manager raises a FileNotFoundError if the metadata is missing."""
    non_existent_path = tmp_path / "non_existent_file.json"
    with pytest.raises(FileNotFoundError):
        ComponentManager(metadata_path=non_existent_path)


def test_manager_raises_json_decode_error_on_init(tmp_path):
    """Test that the manager raises a JSONDecodeError for a corrupt file."""
    bad_json_path = tmp_path / "bad.json"
    bad_json_path.write_text("{'key': 'value',}")  # Invalid JSON
    with pytest.raises(json.JSONDecodeError):
        ComponentManager(metadata_path=bad_json_path)


def test_get_uniqueness_groups(mock_project_structure):
    """Test if the uniqueness groups are identified correctly."""
    metadata_path = mock_project_structure

    with open(metadata_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    data["dashy"]["uniqueness_group"] = "dashboard"
    data["frigate"]["uniqueness_group"] = "nvr"

    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(data, f)

    manager = ComponentManager(metadata_path=metadata_path)
    groups = manager.get_uniqueness_groups()

    assert groups == {
        "dashboard": ["dashy"],
        "nvr": ["frigate"],
        "container_manager": ["portainer"],
    }
