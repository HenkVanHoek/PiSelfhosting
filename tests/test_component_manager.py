import json
from pathlib import Path

import pytest

from src.managers.component_manager import ComponentManager

# Import Template for mocking in tests if needed, but not strictly required yet
# from jinja2 import Template
#


@pytest.fixture
def manager_with_initial_data(tmp_path: Path):
    """Pytest fixture to create a ComponentManager with some initial data."""
    metadata_file = tmp_path / "components_metadata.json"
    templates_dir = tmp_path / "component_templates"
    templates_dir.mkdir()

    metadata_content = {
        "_piselfhosting": {
            "components_order": ["comp-b", "comp-a"],
            "group_order": ["group_one"],
            "group_rules": {
                "group_one": {"name": "Original Group Name", "is_exclusive": False}
            },
        },
        "components": {
            "comp-a": {
                "name": "Component A",
                "docker_service_name": "service-a-special",
                "group": "group_one",
                # START OF FIX: Add Traefik fields for testing the positive case
                "has_traefik_support": True,
                "traefik_internal_port": 8080,
                # END OF FIX:
            },
            "comp-b": {
                "name": "Component B",
                # START OF FIX: Explicitly set Traefik fields for the negative case
                "has_traefik_support": False,
                "traefik_internal_port": None,
                # END OF FIX:
            },
            # START OF FIX: Add comp-c without explicit Traefik fields (defaults)
            "comp-c": {"name": "Component C"},
            # END OF FIX:
        },
    }
    metadata_file.write_text(json.dumps(metadata_content))

    # Setup component files: comp-a
    comp_a_path = templates_dir / "comp-a"
    comp_a_config_path = comp_a_path / "template-config"
    comp_a_config_path.mkdir(parents=True)
    variables_content = {"variables": [{"id": "VAR_A", "label": "Variable A"}]}
    (comp_a_config_path / "variables.json").write_text(json.dumps(variables_content))
    # START OF FIX: Add dummy docker-compose.template.yml for render tests
    (comp_a_path / "docker-compose.template.yml").write_text(
        "version: '3'\nservices:\n  service-a:\n    labels: {{ traefik_labels }}"
    )
    # END OF FIX:

    # Setup component files: comp-b
    comp_b_path = templates_dir / "comp-b"
    comp_b_config_path = comp_b_path / "template-config"
    comp_b_config_path.mkdir(parents=True)
    (comp_b_config_path / "variables.json").write_text(json.dumps({"variables": []}))
    # START OF FIX: Add dummy docker-compose.template.yml for render tests
    (comp_b_path / "docker-compose.template.yml").write_text(
        "version: '3'\nservices:\n  service-b:\n    ports: ['8080:80']"
    )
    # END OF FIX:

    # START OF FIX: Setup component files: comp-c (defaults)
    comp_c_path = templates_dir / "comp-c"
    comp_c_config_path = comp_c_path / "template-config"
    comp_c_config_path.mkdir(parents=True)
    (comp_c_config_path / "variables.json").write_text(json.dumps({"variables": []}))
    (comp_c_path / "docker-compose.template.yml").write_text(
        "version: '3'\nservices:\n  service-c: {}"
    )
    # END OF FIX:

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
        assert details_a["has_traefik_support"] is True
        assert details_a["traefik_internal_port"] == 8080
        assert isinstance(details_a["required_variables"], list)
        assert len(details_a["required_variables"]) == 1
        # Unpacking-First Mandate
        first_variable = details_a["required_variables"][0]
        assert first_variable["id"] == "VAR_A"

        details_b = manager.get_component_details("comp-b")
        assert details_b is not None
        assert details_b["name"] == "Component B"
        assert details_b["has_traefik_support"] is False
        assert details_b["required_variables"] == []

        details_c = manager.get_component_details("comp-c")
        assert details_c is not None
        assert details_c["name"] == "Component C"
        # Test default value for missing keys
        assert details_c["has_traefik_support"] is False

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
        # Unpacking-First Mandate
        updated_variable = details["required_variables"][0]
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

    def test_rename_group_success(self, manager_with_initial_data):
        """Verify that renaming a group updates the metadata file correctly."""
        manager, tmp_path = manager_with_initial_data
        metadata_file = tmp_path / "components_metadata.json"

        manager.rename_group("group_one", "Renamed Group")

        # Verify by reloading the raw data
        data = json.loads(metadata_file.read_text())
        group_name = data["_piselfhosting"]["group_rules"]["group_one"]["name"]
        assert group_name == "Renamed Group"

    def test_rename_group_nonexistent(self, manager_with_initial_data):
        """Verify that renaming a nonexistent group raises a ValueError."""
        manager, _ = manager_with_initial_data
        with pytest.raises(ValueError, match="Group 'nonexistent-group' not found."):
            manager.rename_group("nonexistent-group", "Some Name")

    # START OF FIX: Add tests for Traefik label generation and rendering logic
    def test_render_component_template_with_traefik_support(
        self, manager_with_initial_data
    ):
        """
        Verify that Traefik labels are correctly generated, injected into the
        context, and rendered when the component has support.
        """
        manager, _ = manager_with_initial_data
        context = {
            "TRAEFIK_HOST": "comp-a-host",
            "FQDN_SUFFIX": "mypi.local",
            "USER_VARIABLE": "some_value",
        }
        rendered_content = manager.render_component_template(
            "comp-a", context.copy()
        )  # Use copy to check modifications

        # Assert the rendered content contains the correct labels as a list string
        expected_labels = [
            "traefik.enable=true",
            "traefik.http.routers.comp-a.entrypoints=websecure",
            "traefik.http.routers.comp-a.rule=Host(`comp-a-host.mypi.local`)",
            "traefik.http.routers.comp-a.tls=true",
            "traefik.http.services.comp-a.loadbalancer.server.port=8080",
        ]
        expected_line = f"    labels: {expected_labels}"
        assert expected_line in rendered_content
        assert (
            "some_value" not in rendered_content
        )  # Check that only necessary context is passed
        assert context.get("traefik_labels") is None  # Original context is not modified

        # Check the context inside render_component_template was correct
        # Since we cannot check the internal context, we rely on the rendered output.

    def test_render_component_template_without_traefik_support(
        self, manager_with_initial_data
    ):
        """
        Verify that Traefik labels are an empty list in the context and do not
        appear when the component explicitly does not have support.
        """
        manager, _ = manager_with_initial_data
        context = {
            "TRAEFIK_HOST": "comp-b-host",
            "FQDN_SUFFIX": "mypi.local",
        }
        rendered_content = manager.render_component_template("comp-b", context.copy())

        # The template for comp-b is different and should not contain 'labels: []'
        # The logic ensures 'traefik_labels' is an empty list in the context.
        # Check that no Traefik-related labels appear in the output.
        assert "traefik.enable=true" not in rendered_content
        assert "ports: ['8080:80']" in rendered_content

    def test_render_component_template_traefik_support_missing_variables(
        self, manager_with_initial_data
    ):
        """
        Verify that Traefik labels are NOT generated if critical context
        variables (like FQDN_SUFFIX) are missing, even if the component supports it.
        """
        manager, _ = manager_with_initial_data
        # Missing FQDN_SUFFIX
        context = {"TRAEFIK_HOST": "comp-a-host"}
        rendered_content = manager.render_component_template("comp-a", context.copy())

        # Labels should be an empty list in the context, resulting in 'labels: []'
        assert "labels: []" in rendered_content
        assert "traefik.enable=true" not in rendered_content
