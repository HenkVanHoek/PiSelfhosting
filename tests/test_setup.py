# tests/test_setup.py
import pytest
import os
import sys
import json
import yaml
from unittest.mock import patch

# Adjust the path to import setup.py from src/
current_test_file_dir = os.path.dirname(os.path.abspath(__file__))
project_root_from_test_dir = os.path.dirname(current_test_file_dir)
src_dir_path = os.path.join(project_root_from_test_dir, 'src')

if src_dir_path not in sys.path:
    sys.path.insert(0, src_dir_path)

import setup as pisetup

# --- Constants updated for the new structure ---
COMPONENTS_METADATA_FILENAME = pisetup.COMPONENTS_METADATA_FILENAME
SELECTED_COMPONENTS_FILENAME = pisetup.SELECTED_COMPONENTS_FILENAME
DOCKER_COMPOSE_TEMPLATES_DIR = pisetup.DOCKER_COMPOSE_TEMPLATES_DIR
DOCKER_COMPOSE_OUTPUT_DIR = pisetup.DOCKER_COMPOSE_OUTPUT_DIR
UNIFIED_DOCKER_COMPOSE_FILENAME = pisetup.UNIFIED_DOCKER_COMPOSE_FILENAME
GLOBAL_DATA_ROOT = pisetup.GLOBAL_DATA_ROOT


@pytest.fixture
def mock_project_structure(tmp_path):
    """
    Creates a temporary project structure with the new components_metadata.json.
    """
    project_root = tmp_path

    # Create directories
    (project_root / "src").mkdir()
    templates_dir = project_root / DOCKER_COMPOSE_TEMPLATES_DIR
    templates_dir.mkdir()

    # Create a dummy template for dashy for testing generation
    dashy_template_dir = templates_dir / "dashy"
    dashy_template_dir.mkdir()
    (dashy_template_dir / "docker-compose.template.yml").write_text(
        "services:\n  dashy:\n    image: lissy93/dashy\n"
    )

    # --- Create components_metadata.json (the new source of truth) ---
    metadata_content = {
        "_piselfhosting": {
            "components_order": ["dashy", "mosquitto", "frigate"]
        },
        "dashy": {
            "name": "Dashy",
            "description": "A self-hosted dashboard.",
            "has_ui": True,
            "ui_port": 8080
        },
        "mosquitto": {
            "name": "Mosquitto",
            "description": "MQTT broker.",
            "has_ui": False
        },
        "frigate": {
            "name": "Frigate",
            "description": "NVR with AI object detection.",
            "has_ui": True,
            "ui_port": 5000
        }
    }
    (project_root / COMPONENTS_METADATA_FILENAME).write_text(json.dumps(metadata_content, indent=2))

    # Create selected_components.txt
    (project_root / SELECTED_COMPONENTS_FILENAME).write_text("dashy")

    # Use patch to ensure setup.py uses the temp path as the project root
    with patch('setup.get_project_root', return_value=str(project_root)):
        yield project_root


# --- Tests for the NEW load_component_metadata function ---

def test_load_component_metadata_valid(mock_project_structure):
    """Tests parsing a valid components_metadata.json file."""
    metadata_path = mock_project_structure / COMPONENTS_METADATA_FILENAME
    result = pisetup.load_component_metadata(file_path=str(metadata_path))

    assert "components_order" in result
    assert "all_component_data" in result
    assert result["components_order"] == ["dashy", "mosquitto", "frigate"]

    assert "dashy" in result["all_component_data"]
    assert result["all_component_data"]["dashy"]["name"] == "Dashy"
    assert result["all_component_data"]["dashy"]["has_ui"] is True
    assert result["all_component_data"]["dashy"]["ui_port"] == 8080

    assert "mosquitto" in result["all_component_data"]
    assert result["all_component_data"]["mosquitto"]["has_ui"] is False


def test_load_component_metadata_file_not_found(tmp_path):
    """Tests handling of a missing components_metadata.json file."""
    with pytest.raises(FileNotFoundError):
        pisetup.load_component_metadata(file_path=str(tmp_path / "non_existent_metadata.json"))


def test_load_component_metadata_malformed_json(mock_project_structure):
    """Tests parsing a malformed JSON file."""
    malformed_path = mock_project_structure / COMPONENTS_METADATA_FILENAME
    malformed_path.write_text("{'invalid': 'json',}")  # Invalid JSON with single quotes
    with pytest.raises(json.JSONDecodeError):
        pisetup.load_component_metadata(file_path=str(malformed_path))


# --- Tests for other functions (updated to use new metadata loader) ---

def test_read_selected_components_valid(mock_project_structure):
    """Tests reading valid selected components from file."""
    selected_components_path = mock_project_structure / SELECTED_COMPONENTS_FILENAME
    selected_components_path.write_text("dashy mosquitto")
    selected = pisetup.read_selected_components(file_path=str(selected_components_path))
    assert selected == {"dashy", "mosquitto"}


def test_generate_docker_compose_files_single_component(mock_project_structure):
    """Tests Docker Compose generation for a single selected component."""
    # Set necessary environment variables for the template rendering
    os.environ['DOMAIN'] = 'test.com'

    # Load data using the NEW metadata function
    parsed_data = pisetup.load_component_metadata(file_path=str(mock_project_structure / COMPONENTS_METADATA_FILENAME))
    all_component_data = parsed_data["all_component_data"]
    selected_components = {"dashy"}

    pisetup.generate_docker_compose_files(all_component_data, selected_components)

    expected_docker_output_dir = mock_project_structure / DOCKER_COMPOSE_OUTPUT_DIR
    dashy_compose_path = expected_docker_output_dir / "docker-compose.dashy.yml"
    assert dashy_compose_path.exists()

    unified_compose_path = expected_docker_output_dir / UNIFIED_DOCKER_COMPOSE_FILENAME
    assert unified_compose_path.exists()
    unified_content = yaml.safe_load(unified_compose_path.read_text())
    assert "dashy" in unified_content["services"]


def test_generate_docker_compose_files_component_not_in_list(mock_project_structure, capsys):
    """Tests handling a selected component that is not defined in the metadata."""
    # Load data using the NEW metadata function
    parsed_data = pisetup.load_component_metadata(file_path=str(mock_project_structure / COMPONENTS_METADATA_FILENAME))
    all_component_data = parsed_data["all_component_data"]
    selected_components = {"dashy", "nonexistent_comp"}

    pisetup.generate_docker_compose_files(all_component_data, selected_components)

    captured = capsys.readouterr()
    # Assert the updated warning message
    assert "Warning: Component 'nonexistent_comp' is selected but not found in 'components_metadata.json'. Skipping." in captured.out