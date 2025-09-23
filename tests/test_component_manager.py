import json
from pathlib import Path
from typing import Any, Dict, List

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

    def test_initialization_with_variable_enrichment(self, tmp_path: Path):
        """
        Verify that on startup, the manager loads variables from a component's
        variables.json file, overwriting any stale data in the main metadata.
        """
        # 1. Set up the main metadata file
        metadata_file = tmp_path / "components_metadata.json"
        initial_content = {
            "components": {
                "comp-with-vars": {
                    "name": "Component With Variables",
                    "has_configuration": True,
                    "required_variables": [],  # Stale/empty data
                },
                "comp-no-vars": {
                    "name": "Component Without Variables",
                    "has_configuration": False,
                },
            }
        }
        metadata_file.write_text(json.dumps(initial_content))

        # 2. Set up the templates directory and the variables.json file
        templates_dir = tmp_path
        comp_config_path = templates_dir / "comp-with-vars" / "template-config"
        comp_config_path.mkdir(parents=True)
        variables_content = {
            "variables": [{"id": "TEST_VAR", "label": "Test Variable"}]
        }
        (comp_config_path / "variables.json").write_text(json.dumps(variables_content))

        # 3. Initialize the manager
        manager = ComponentManager(
            templates_path=str(templates_dir), metadata_file_path=str(metadata_file)
        )

        # 4. Assert that the variables were loaded correctly
        details = manager.get_component_details("comp-with-vars")
        assert details is not None
        assert "required_variables" in details
        assert len(details["required_variables"]) == 1
        assert details["required_variables"][0]["id"] == "TEST_VAR"

    def test_get_uniqueness_groups(self, tmp_path: Path):
        """
        Verify that the get_uniqueness_groups method correctly extracts the
        group_rules dictionary from the metadata.
        """
        metadata_file = tmp_path / "components_metadata.json"
        mock_group_rules = {
            "dashboard": {"name": "Dashboard", "is_exclusive": True},
            "dns_blocker": {"name": "DNS Blocker", "is_exclusive": True},
        }
        initial_content = {
            "_piselfhosting": {"group_rules": mock_group_rules},
            "components": {},
        }
        metadata_file.write_text(json.dumps(initial_content))
        manager = ComponentManager(
            templates_path=str(tmp_path), metadata_file_path=str(metadata_file)
        )
        result = manager.get_uniqueness_groups()
        assert result == mock_group_rules

    def test_sort_components_by_master_order(self, tmp_path: Path):
        """
        Verify that the sorting method correctly orders a list of component IDs
        according to the master order defined in the metadata.
        """
        metadata_file = tmp_path / "components_metadata.json"
        master_order = ["portainer", "homarr", "pi-hole"]
        initial_content = {
            "_piselfhosting": {"components_order": master_order},
            "components": {},
        }
        metadata_file.write_text(json.dumps(initial_content))
        manager = ComponentManager(
            templates_path=str(tmp_path), metadata_file_path=str(metadata_file)
        )
        unsorted_list = ["pi-hole", "portainer"]
        sorted_list = manager.sort_components_by_master_order(unsorted_list)
        assert sorted_list == ["portainer", "pi-hole"]

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
        saved_data = json.loads(metadata_file.read_text())
        assert "comp-to-delete" not in saved_data["components"]
        assert "comp-to-delete" not in saved_data["_piselfhosting"]["components_order"]
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

    def test_validate_template_rejects_obsolete_version_key(self, tmp_path: Path):
        """
        Verify the validator raises a ValueError if the template contains
        the obsolete top-level 'version' key.
        """
        metadata_file = tmp_path / "components_metadata.json"
        metadata_file.write_text('{"components": {"test-comp": {}}}')
        manager = ComponentManager(
            templates_path=str(tmp_path), metadata_file_path=str(metadata_file)
        )

        invalid_template = "version: '3.8'\nservices:\n  app:\n    image: a:b"
        variables: List[Dict[str, Any]] = []

        with pytest.raises(ValueError, match="obsolete top-level 'version' key"):
            manager.validate_component_configuration(
                "test-comp", invalid_template, variables
            )

    def test_validate_template_rejects_undefined_variable(self, tmp_path: Path):
        """
        Verify the validator raises a ValueError if the template uses a
        variable that is not defined in the variables list.
        """
        metadata_file = tmp_path / "components_metadata.json"
        metadata_file.write_text('{"components": {"test-comp": {}}}')
        manager = ComponentManager(
            templates_path=str(tmp_path), metadata_file_path=str(metadata_file)
        )

        invalid_template = "services:\n  app:\n    image: my-app:{{ UNDEFINED_VAR }}"
        defined_variables: List[Dict[str, Any]] = []

        with pytest.raises(
            ValueError, match="Template uses undefined variable: 'UNDEFINED_VAR'"
        ):
            manager.validate_component_configuration(
                "test-comp", invalid_template, defined_variables
            )

    def test_validate_template_rejects_unused_variable(self, tmp_path: Path):
        """
        Verify the validator raises a ValueError if a variable is defined
        but is not used in the template.
        """
        metadata_file = tmp_path / "components_metadata.json"
        metadata_file.write_text('{"components": {"test-comp": {}}}')
        manager = ComponentManager(
            templates_path=str(tmp_path), metadata_file_path=str(metadata_file)
        )

        template = "services:\n  app:\n    image: my-app:latest"
        defined_variables: List[Dict[str, Any]] = [
            {"id": "UNUSED_VAR", "label": "Unused Variable"}
        ]

        with pytest.raises(
            ValueError, match="Variable 'UNUSED_VAR' is defined but not used"
        ):
            manager.validate_component_configuration(
                "test-comp", template, defined_variables
            )
