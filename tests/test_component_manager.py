import json
from pathlib import Path

import pytest

from src.managers.component_manager import ComponentManager


@pytest.fixture
def manager_with_initial_data(tmp_path: Path):
    """Pytest fixture to create a ComponentManager with some initial data."""
    metadata_file = tmp_path / "components_metadata.json"
    templates_dir = tmp_path / "component_templates"
    templates_dir.mkdir()

    metadata_content = {
        "_piselfhosting": {"components_order": ["comp-b", "comp-a"]},
        "components": {
            "comp-a": {
                "name": "Component A",
                "docker_service_name": "service-a-special",
            },
            "comp-b": {"name": "Component B"},
        },
    }
    metadata_file.write_text(json.dumps(metadata_content))

    # Setup variables for comp-a
    comp_a_config_path = templates_dir / "comp-a" / "template-config"
    comp_a_config_path.mkdir(parents=True)
    variables_content = {"variables": [{"id": "VAR_A", "label": "Variable A"}]}
    (comp_a_config_path / "variables.json").write_text(json.dumps(variables_content))

    # Setup empty variables for comp-b
    comp_b_config_path = templates_dir / "comp-b" / "template-config"
    comp_b_config_path.mkdir(parents=True)
    (comp_b_config_path / "variables.json").write_text(json.dumps({"variables": []}))

    manager = ComponentManager(
        templates_path=str(templates_dir), metadata_file_path=str(metadata_file)
    )
    return manager, tmp_path


class TestComponentManager:
    def test_get_component_details_merges_data_correctly(
        self, manager_with_initial_data
    ):
        """
        Verify get_component_details correctly merges metadata and variables.
        """
        manager, _ = manager_with_initial_data

        details_a = manager.get_component_details("comp-a")
        assert details_a is not None
        assert details_a["name"] == "Component A"
        assert isinstance(details_a["required_variables"], list)
        assert len(details_a["required_variables"]) == 1
        # START OF FIX: Access the first element of the list
        first_variable = details_a["required_variables"][0]
        # END OF FIX
        assert first_variable["id"] == "VAR_A"

        details_b = manager.get_component_details("comp-b")
        assert details_b is not None
        assert details_b["name"] == "Component B"
        assert details_b["required_variables"] == []

    def test_update_component_variables_enforces_sst(self, manager_with_initial_data):
        """
        Verify update_component_variables ONLY writes to variables.json.
        """
        manager, tmp_path = manager_with_initial_data
        metadata_file = tmp_path / "components_metadata.json"
        templates_dir = tmp_path / "component_templates"
        comp_a_vars_file = (
            templates_dir / "comp-a" / "template-config" / "variables.json"
        )

        original_metadata_content = metadata_file.read_text()

        new_variables_payload = {
            "variables": [{"id": "NEW_VAR", "label": "New Variable"}]
        }

        manager.update_component_variables("comp-a", new_variables_payload)

        assert metadata_file.read_text() == original_metadata_content

        saved_vars_data = json.loads(comp_a_vars_file.read_text())
        assert saved_vars_data == new_variables_payload

        details = manager.get_component_details("comp-a")
        assert len(details["required_variables"]) == 1
        # START OF FIX: Access the first element of the list
        updated_variable = details["required_variables"][0]
        # END OF FIX
        assert updated_variable["id"] == "NEW_VAR"

    def test_get_docker_service_name(self, manager_with_initial_data):
        """
        Verify get_docker_service_name returns the specific name or defaults
        to the component ID.
        """
        manager, _ = manager_with_initial_data
        assert manager.get_docker_service_name("comp-a") == "service-a-special"
        assert manager.get_docker_service_name("comp-b") == "comp-b"

    def test_sort_components_by_master_order(self, manager_with_initial_data):
        """
        Verify components are sorted correctly based on the master order.
        """
        manager, _ = manager_with_initial_data
        unsorted_ids = ["comp-a", "comp-b"]
        sorted_ids = manager.sort_components_by_master_order(unsorted_ids)
        assert sorted_ids == ["comp-b", "comp-a"]

        # Test with an ID not in the master order (should appear at the end)
        unsorted_ids_with_new = ["comp-a", "new-comp", "comp-b"]
        sorted_ids_with_new = manager.sort_components_by_master_order(
            unsorted_ids_with_new
        )
        assert sorted_ids_with_new == ["comp-b", "comp-a", "new-comp"]
