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
            "has_ui": True,
            "ui_port": 8080,
        },
        "portainer": {
            "name": "Portainer",
            "description": "Container management UI.",
            "uniqueness_group": "container_manager",
            "has_ui": True,
            "ui_port": 9000,
        },
        "frigate": {
            "name": "Frigate",
            "description": "NVR with AI.",
            "uniqueness_group": None,
            "has_ui": False,
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


def test_generate_docs_creates_file_with_correct_content(
    mock_project_structure, tmp_path
):
    """
    Test that generate_docs() creates a documentation file with the expected
    Markdown content based on the component metadata.
    """
    # Define an output path for the documentation file
    docs_output_path = tmp_path / "SUPPORTED_COMPONENTS.md"

    # Initialize the manager with both metadata and a docs path
    manager = ComponentManager(
        metadata_path=mock_project_structure, docs_output_path=docs_output_path
    )

    # Run the documentation generation
    manager.generate_docs()

    # --- Assertions ---
    # 1. Check if the documentation file was actually created
    assert docs_output_path.exists()

    # 2. Read the content and check if it matches expectations
    content = docs_output_path.read_text(encoding="utf-8")

    # Check for the main title
    assert "# Supported Components" in content
    # Check for specific component sections and details
    assert "## Dashy" in content
    assert "**ID:** `dashy`" in content
    assert "A self-hosted dashboard." in content
    assert "- **Web Interface:** Yes (Port: 8080)" in content

    assert "## Portainer" in content
    assert "**ID:** `portainer`" in content
    assert "- **Web Interface:** Yes (Port: 9000)" in content

    assert "## Frigate" in content
    assert "**ID:** `frigate`" in content
    assert "- **Web Interface:** No" in content

    # Check that the components are in the order specified by `components_order`
    dashy_pos = content.find("## Dashy")
    portainer_pos = content.find("## Portainer")
    frigate_pos = content.find("## Frigate")
    assert 0 < dashy_pos < portainer_pos < frigate_pos
