# tests/test_component_manager.py
import json
import os
import sys
from unittest.mock import patch

import pytest

# Adjust the path to import setup.py from src/
current_test_file_dir = os.path.dirname(os.path.abspath(__file__))
project_root_from_test_dir = os.path.dirname(current_test_file_dir)
src_dir_path = os.path.join(project_root_from_test_dir, "src")

if src_dir_path not in sys.path:
    sys.path.insert(0, src_dir_path)

from component_manager import ComponentManager  # noqa: E402


@pytest.fixture
def mock_project_structure(tmp_path):
    """
    Creates a temporary project structure with the new components_metadata.json.
    """
    project_root = tmp_path

    # Create directories
    (project_root / "src").mkdir()
    templates_dir = project_root / "templates"
    templates_dir.mkdir()

    # Create a dummy template for dashy for testing generation
    dashy_template_dir = templates_dir / "dashy"
    dashy_template_dir.mkdir()
    (dashy_template_dir / "docker-compose.template.yml").write_text(
        "services:\n  dashy:\n    image: lissy93/dashy\n"
    )

    # --- Create components_metadata.json (the new source of truth) ---
    metadata_content = {
        "_piselfhosting": {"components_order": ["dashy", "mosquitto", "frigate"]},
        "dashy": {
            "name": "Dashy",
            "description": "A self-hosted dashboard.",
            "has_ui": True,
            "ui_port": 8080,
        },
        "mosquitto": {
            "name": "Mosquitto",
            "description": "MQTT broker.",
            "has_ui": False,
        },
        "frigate": {
            "name": "Frigate",
            "description": "NVR with AI object detection.",
            "has_ui": True,
            "ui_port": 5000,
        },
    }
    (project_root / "components_metadata.json").write_text(
        json.dumps(metadata_content, indent=2)
    )

    # Use patch to ensure ComponentManager uses the temp path as the project root
    with patch("component_manager.Path.exists", return_value=True), patch(
        "builtins.open",
        return_value=open(project_root / "components_metadata.json", "r"),
    ):
        yield project_root


def test_get_uniqueness_groups(mock_project_structure):
    """Tests that uniqueness groups are correctly identified."""
    # Add uniqueness groups to the mock metadata
    metadata_path = mock_project_structure / "components_metadata.json"
    with open(metadata_path, "r") as f:
        data = json.load(f)
    data["dashy"]["uniqueness_group"] = "dashboard"
    data["frigate"]["uniqueness_group"] = "nvr"
    with open(metadata_path, "w") as f:
        json.dump(data, f)

    manager = ComponentManager(metadata_path=metadata_path)
    groups = manager.get_uniqueness_groups()

    assert "dashboard" in groups
    assert "nvr" in groups
    assert groups["dashboard"] == ["dashy"]
    assert groups["nvr"] == ["frigate"]
