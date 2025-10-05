import json
from pathlib import Path
from typing import Any, Dict, List

import pytest
import yaml

from src.managers.component_manager import ComponentManager


@pytest.fixture
def manager_with_initial_data(tmp_path: Path):
    """Pytest fixture to create a ComponentManager with some initial data."""
    metadata_file = tmp_path / "components_metadata.json"
    templates_dir = tmp_path / "component_templates"
    templates_dir.mkdir()

    metadata_content = {
        "_piselfhosting": {
            # Ensures comp-b is processed before comp-a
            "components_order": ["comp-b", "comp-a", "comp-validate"],
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
            # NEW FIX: Add comp-validate for validation tests
            "comp-validate": {
                "name": "Component Validate",
                "has_traefik_support": True,
                "traefik_internal_port": 9000,
            },
        },
    }
    metadata_file.write_text(json.dumps(metadata_content))
    # Setup component files: comp-a (Traefik-enabled)
    comp_a_path = templates_dir / "comp-a"
    comp_a_config_path = comp_a_path / "template-config"
    comp_a_config_path.mkdir(parents=True)
    variables_content: Dict[str, List[Dict[str, Any]]] = {
        "variables": [{"id": "VAR_A", "label": "Variable A"}]
    }
    (comp_a_config_path / "variables.json").write_text(json.dumps(variables_content))
    # FIX: Add a custom network to comp-a to test merging
    comp_a_template = (
        "services:\n"
        "  service-a:\n"
        "    image: component-a-image\n"
        "    labels:\n"
        "{{ traefik_labels_yaml | safe }}\n"
        "    networks:\n"
        "      - custom-network\n"
        "networks:\n"
        "  custom-network: {}\n"
    )
    (comp_a_path / "docker-compose.template.yml").write_text(comp_a_template)

    # Setup component files: comp-b (No Traefik, uses ports)
    comp_b_path = templates_dir / "comp-b"
    comp_b_config_path = comp_b_path / "template-config"
    comp_b_config_path.mkdir(parents=True)
    (comp_b_config_path / "variables.json").write_text(json.dumps({"variables": []}))
    # FIX: Add a simple service definition for comp-b
    comp_b_template = (
        "services:\n"
        "  service-b:\n"
        "    image: component-b-image\n"
        # FIX (KISS): Change from flow-style list 'ports: [x]' to block-style
        # '- x' for better YAML parsing robustness with PyYAML.
        "    ports:\n"
        "      - {{ B_PORT }}:80"
    )
    (comp_b_path / "docker-compose.template.yml").write_text(comp_b_template)

    # START OF FIX: Setup component files: comp-c (defaults)
    comp_c_path = templates_dir / "comp-c"
    comp_c_config_path = comp_c_path / "template-config"
    comp_c_config_path.mkdir(parents=True)
    (comp_c_config_path / "variables.json").write_text(json.dumps({"variables": []}))
    comp_c_template = "services:\n  service-c: {}"
    (comp_c_path / "docker-compose.template.yml").write_text(comp_c_template)
    # END OF FIX:

    # NEW FIX: Setup component files: comp-validate for validation and exclusion tests
    comp_validate_path = templates_dir / "comp-validate"
    comp_validate_config_path = comp_validate_path / "template-config"
    comp_validate_config_path.mkdir(parents=True)

    # NEW FIX: Add variable for Traefik exclusion test
    vars_content: Dict[str, List[Dict[str, str]]] = {
        "variables": [
            {"id": "UI_PORT", "type": "port"},
            {"id": "EXCLUDE_PORT", "type": "port_exclude_traefik"},
        ]
    }
    (comp_validate_config_path / "variables.json").write_text(json.dumps(vars_content))

    # NEW FIX: Add template for Traefik exclusion test
    template_content = (
        "services:\n  app:\n"
        '    ports:\n      - "{{ UI_PORT }}:80"\n'
        "    labels:\n"
        "{{ traefik_labels_yaml | safe }}\n"
    )
    (comp_validate_path / "docker-compose.template.yml").write_text(template_content)

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

        new_variables_payload: Dict[str, List[Dict[str, str]]] = {
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

    # NEW TEST: Validation for mandatory container naming convention
    def test_validate_component_configuration_container_name_enforcement(
        self, manager_with_initial_data
    ):
        """
        Verify that validate_component_configuration raises an error when a
        container_name is explicitly set but lacks the piselfhosting- prefix.
        """
        manager, _ = manager_with_initial_data

        # 1. Test case: Invalid container_name
        invalid_template = (
            "version: '3'\n"
            "services:\n"
            "  app:\n"
            "    container_name: wrong-prefix-app\n"
        )
        with pytest.raises(ValueError, match="Naming Violation"):
            manager.validate_component_configuration(
                "comp-validate", invalid_template, []
            )

        # 2. Test case: Valid container_name
        valid_template = (
            "version: '3'\n"
            "services:\n"
            "  app:\n"
            "    container_name: piselfhosting-correct-app\n"
        )
        try:
            manager.validate_component_configuration(
                "comp-validate", valid_template, []
            )
        except ValueError as e:
            pytest.fail(f"Valid template raised unexpected error: {e}")

        # 3. Test case: No container_name (should pass and use implicit name)
        implicit_template = "version: '3'\nservices:\n  app:\n    image: test/image"
        try:
            manager.validate_component_configuration(
                "comp-validate", implicit_template, []
            )
        except ValueError as e:
            pytest.fail(f"Implicit template raised unexpected error: {e}")

    # NEW TEST: Traefik exclusion via a new variable type
    def test_render_component_template_traefik_port_is_excluded(
        self, manager_with_initial_data
    ):
        """
        Verify that Traefik labels are NOT generated if the traefik_internal_port
        is matched by a variable of type 'port_exclude_traefik'.
        """
        manager, _ = manager_with_initial_data

        # 1. Setup Component for Exclusion Test (comp-validate)
        # Metadata: has_traefik_support: True, traefik_internal_port: 9000
        # Variables: EXCLUDE_PORT (type: port_exclude_traefik)

        # Context where the EXCLUDE_PORT variable is set to the same value as the
        # component's traefik_internal_port (9000).
        context = {
            "TRAEFIK_HOST": "test",
            "FQDN_SUFFIX": "local",
            "UI_PORT": "9001",
            "EXCLUDE_PORT": "9000",
        }

        # Act: Render the template
        rendered_content = manager.render_component_template(
            "comp-validate", context.copy()
        )

        # Assert: The labels should NOT have been generated
        rendered_yaml = yaml.safe_load(rendered_content)
        service_validate = rendered_yaml["services"]["app"]
        # CRITICAL ASSERTION FIX: The labels block will now be entirely empty
        # because the logic sets traefik_labels_yaml to "".
        # PyYAML interprets an empty block as None or an empty dict.
        assert (
            service_validate.get("labels") is None
            or service_validate.get("labels") == {}
        )
        assert "traefik.enable=true" not in rendered_content

        # 2. Test case: Exclusion variable is set to a DIFFERENT port
        context_no_exclusion = {
            "TRAEFIK_HOST": "test",
            "FQDN_SUFFIX": "local",
            "UI_PORT": "9001",
            "EXCLUDE_PORT": "9999",
        }
        rendered_content_no_exclusion = manager.render_component_template(
            "comp-validate", context_no_exclusion.copy()
        )

        # Assert: The labels SHOULD have been generated
        rendered_yaml_no_exclusion = yaml.safe_load(rendered_content_no_exclusion)
        service_validate_no_exclusion = rendered_yaml_no_exclusion["services"]["app"]
        expected_label_part = (
            "traefik.http.services.comp-validate.loadbalancer.server.port=9000"
        )
        # The labels key should be a list containing the expected part
        assert isinstance(service_validate_no_exclusion["labels"], list)
        assert expected_label_part in service_validate_no_exclusion["labels"]
        assert "traefik.enable=true" in service_validate_no_exclusion["labels"]

    # START OF FIX: Update tests for correct YAML rendering/parsing behavior
    def test_render_component_template_with_traefik_support(
        self, manager_with_initial_data
    ):
        """
        Verify that Traefik labels are correctly generated, injected into the
        context, and rendered with valid YAML structure (using Component ID).
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

        # Assert: Load the rendered content to check for structural correctness
        rendered_yaml = yaml.safe_load(rendered_content)
        service_a = rendered_yaml["services"]["service-a"]

        # Check Traefik labels: The rendered output must be a Python list
        assert isinstance(service_a["labels"], list)
        expected_label_part = (
            "traefik.http.services.comp-a.loadbalancer.server.port=8080"
        )
        assert expected_label_part in service_a["labels"]
        assert "traefik.enable=true" in service_a["labels"]

    def test_render_component_template_without_traefik_support(
        self, manager_with_initial_data
    ):
        """
        Verify that Traefik labels are NOT rendered when the component explicitly
        does not have support, and the output remains valid YAML.
        """
        manager, _ = manager_with_initial_data
        context = {
            "TRAEFIK_HOST": "comp-b-host",
            "FQDN_SUFFIX": "mypi.local",
            "B_PORT": "8080",
        }
        rendered_content = manager.render_component_template("comp-b", context.copy())

        # CRITICAL ASSERTION FIX: Assert against the final, correct YAML output
        rendered_yaml = yaml.safe_load(rendered_content)
        service_b = rendered_yaml["services"]["service-b"]

        # Assert 1: The correct port was rendered
        assert service_b["ports"] == ["8080:80"]
        # Assert 2: No 'labels' key exists in the final YAML
        assert "labels" not in service_b

        # Assert 3: No Traefik-related data in the output string
        assert "traefik.enable=true" not in rendered_content
        # Assert 4: The context variable was resolved, but the
        # wrong string assert is gone.
        assert "8080:80" in rendered_content

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

        # CRITICAL ASSERTION FIX: Check against the rendered YAML
        rendered_yaml = yaml.safe_load(rendered_content)
        service_a = rendered_yaml["services"]["service-a"]

        # Labels should be None or an empty dict because
        # the logic sets traefik_labels_yaml to "".
        assert service_a.get("labels") is None or service_a.get("labels") == {}
        assert "traefik.enable=true" not in rendered_content

    # NEW TEST: Test the new generate_deployment_artifacts method
    def test_generate_deployment_artifacts_success(self, manager_with_initial_data):
        """
        Verify that generate_deployment_artifacts correctly renders, merges,
        injects Traefik labels, and saves the final docker-compose.yml and
        deployment_context.json.
        """
        manager, tmp_path = manager_with_initial_data
        output_path = tmp_path / "deployment_output"
        output_path.mkdir()

        # 1. Define Selected Components (Note: order is important for merging,
        # but the method sorts them by master_order: comp-b, comp-a, comp-validate)
        # We need full data here, but the data is pulled from the manager.
        selected_ids = ["comp-a", "comp-b", "comp-validate"]
        # CRITICAL FIX (v6.7): Break long list comprehension for PEP 8 (88-char limit)
        selected_components_data: List[Dict[str, Any]] = [
            manager.get_component_details(comp_id) for comp_id in selected_ids
        ]

        # 2. Define Resolved Variables (Global and Component-specific)
        global_vars = {
            # Global Traefik config for comp-a and comp-validate
            "TRAEFIK_HOST": "test-host",
            "FQDN_SUFFIX": "local",
            # Resolved variables for components
            "VAR_A": "resolved-a-value",  # from comp-a
            "B_PORT": "8080",  # from comp-b template, even if not in metadata
            "UI_PORT": "9001",  # from comp-validate
            "EXCLUDE_PORT": "9999",  # from comp-validate (no exclusion)
        }

        # 3. Act: Generate the artifacts
        manager.generate_deployment_artifacts(
            selected_components_data, global_vars, output_path
        )

        # 4. Assert Artifacts exist
        compose_path = output_path / "docker-compose.yml"
        context_path = output_path / "deployment_context.json"
        assert compose_path.exists()
        assert context_path.exists()

        # 5. Assert deployment_context.json content
        with open(context_path, "r") as f:
            saved_context = json.load(f)
        assert saved_context == global_vars
        print("DEBUG: saved_context: ", saved_context)
        # 6. Assert docker-compose.yml content
        with open(compose_path, "r") as f:
            compose_data = yaml.safe_load(f)
        print("DEBUG: compose_data", compose_data)
        # Verify base structure
        # CRITICAL FIX: Removed assertion on version number
        assert "version" not in compose_data  # Assert version key is absent
        assert len(compose_data["services"]) == 3  # service-a, service-b, app
        assert (
            len(compose_data["networks"]) == 2
        )  # piselfhosting-network, custom-network

        # Verify comp-a service (Traefik labels and custom network)
        service_a = compose_data["services"]["service-a"]
        # Assert Traefik labels were successfully injected and rendered as a
        # list of strings
        assert isinstance(service_a["labels"], list)
        expected_label_part_a = (
            "traefik.http.services.comp-a.loadbalancer.server.port=8080"
        )
        assert expected_label_part_a in service_a["labels"]

        # Verify comp-b service (No Traefik, port variable resolved)
        service_b = compose_data["services"]["service-b"]
        assert "labels" not in service_b
        assert service_b["ports"] == ["8080:80"]

        # Verify comp-validate service (Traefik labels, port variable resolved)
        service_validate = compose_data["services"]["app"]
        assert service_validate["ports"] == ["9001:80"]
        expected_label_part_validate = (
            "traefik.http.services.comp-validate.loadbalancer.server.port=9000"
        )
        assert expected_label_part_validate in service_validate["labels"]

        # Verify networks
        assert compose_data["networks"]["piselfhosting-network"]["external"] is True
        assert compose_data["networks"]["custom-network"] == {"external": False}
