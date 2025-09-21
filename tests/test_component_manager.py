import json
from pathlib import Path

import pytest

from src.managers.component_manager import ComponentManager


class TestComponentManager:
    def test_initialization(self, tmp_path: Path):
        """Test that the component manager initializes correctly."""
        metadata_file = tmp_path / "components_metadata.json"
        metadata_file.write_text('{"components": {"comp1": {"name": "Component 1"}}}')
        manager = ComponentManager(
            templates_path=str(tmp_path), metadata_file_path=str(metadata_file)
        )
        assert len(manager.get_all_components()) == 1

    def test_update_components_order(self, tmp_path: Path):
        """Test that the component order can be updated and saved."""
        metadata_file = tmp_path / "components_metadata.json"
        initial_content = {
            "_piselfhosting": {"components_order": ["comp1", "comp2"]},
            "components": {"comp1": {}, "comp2": {}},
        }
        metadata_file.write_text(json.dumps(initial_content))
        manager = ComponentManager(
            templates_path=str(tmp_path), metadata_file_path=str(metadata_file)
        )
        new_order = ["comp2", "comp1"]
        manager.update_components_order(new_order)
        saved_data = json.loads(metadata_file.read_text())
        assert saved_data["_piselfhosting"]["components_order"] == new_order

    def test_create_component(self, tmp_path: Path):
        """Test that a new component's files and folders are created."""
        metadata_file = tmp_path / "components_metadata.json"
        metadata_file.write_text('{"components": {}}')
        manager = ComponentManager(
            templates_path=str(tmp_path), metadata_file_path=str(metadata_file)
        )
        manager.create_component("new-comp", "New Component")
        new_comp_path = tmp_path / "new-comp"
        assert new_comp_path.is_dir()
        saved_data = json.loads(metadata_file.read_text())
        assert "new-comp" in saved_data["components"]

    def test_delete_unused_group(self, tmp_path: Path):
        """Test that an unused group can be deleted."""
        metadata_file = tmp_path / "components_metadata.json"
        initial_content = {
            "_piselfhosting": {
                "group_order": ["group-a", "group-to-delete"],
                "group_rules": {
                    "group-a": {"name": "Group A"},
                    "group-to-delete": {"name": "Delete Me"},
                },
            },
            "components": {"comp1": {"name": "Component 1", "group": "group-a"}},
        }
        metadata_file.write_text(json.dumps(initial_content))
        manager = ComponentManager(
            templates_path=str(tmp_path), metadata_file_path=str(metadata_file)
        )

        manager.delete_group("group-to-delete")

        saved_data = json.loads(metadata_file.read_text())
        assert "group-to-delete" not in saved_data["_piselfhosting"]["group_order"]
        assert "group-to-delete" not in saved_data["_piselfhosting"]["group_rules"]

    def test_delete_used_group_raises_error(self, tmp_path: Path):
        """Test that deleting a group that is in use raises a ValueError."""
        metadata_file = tmp_path / "components_metadata.json"
        initial_content = {
            "_piselfhosting": {"group_rules": {"group-in-use": {"name": "In Use"}}},
            "components": {"comp1": {"name": "Component 1", "group": "group-in-use"}},
        }
        metadata_file.write_text(json.dumps(initial_content))
        manager = ComponentManager(
            templates_path=str(tmp_path), metadata_file_path=str(metadata_file)
        )

        with pytest.raises(ValueError, match="Group 'group-in-use' is still in use"):
            manager.delete_group("group-in-use")

    def test_delete_component_success(self, tmp_path: Path):
        """Test that a component is successfully deleted from metadata and disk."""
        metadata_file = tmp_path / "components_metadata.json"
        comp_dir = tmp_path / "comp-to-delete"
        comp_dir.mkdir()

        # Create a dummy template file to verify deletion
        (comp_dir / "docker-compose.template.yml").touch()

        initial_content = {
            "_piselfhosting": {"components_order": ["comp-to-delete"]},
            "components": {
                "comp-to-delete": {"name": "Component to Delete"},
                "comp-to-keep": {"name": "Component to Keep"},
            },
        }
        metadata_file.write_text(json.dumps(initial_content))

        manager = ComponentManager(
            templates_path=str(tmp_path), metadata_file_path=str(metadata_file)
        )

        manager.delete_component("comp-to-delete")

        # Verify metadata is updated
        saved_data = json.loads(metadata_file.read_text())
        assert "comp-to-delete" not in saved_data["components"]
        assert "comp-to-delete" not in saved_data["_piselfhosting"]["components_order"]

        # Verify component directory is deleted
        assert not comp_dir.exists()

    def test_delete_non_existent_component_raises_error(self, tmp_path: Path):
        """Test that deleting a non-existent component raises a KeyError."""
        metadata_file = tmp_path / "components_metadata.json"
        metadata_file.write_text('{"components": {}}')
        manager = ComponentManager(
            templates_path=str(tmp_path), metadata_file_path=str(metadata_file)
        )

        with pytest.raises(KeyError, match="Component 'non-existent-comp' not found."):
            manager.delete_component("non-existent-comp")
