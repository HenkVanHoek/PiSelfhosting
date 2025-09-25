import json
import textwrap
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
        "components": {
            "comp-a": {"name": "Component A", "has_configuration": True},
            "comp-b": {"name": "Component B", "has_configuration": False},
        }
    }
    metadata_file.write_text(json.dumps(metadata_content))

    comp_a_config_path = templates_dir / "comp-a" / "template-config"
    comp_a_config_path.mkdir(parents=True)
    variables_content = {"variables": [{"id": "VAR_A", "label": "Variable A"}]}
    (comp_a_config_path / "variables.json").write_text(json.dumps(variables_content))

    manager = ComponentManager(
        templates_path=str(templates_dir), metadata_file_path=str(metadata_file)
    )
    return manager, tmp_path


class TestComponentManager:
    def test_get_component_details_merges_data_correctly(
        self, manager_with_initial_data
    ):
        """
        Verify get_component_details correctly merges metadata and variables
        on the fly from their separate sources.
        """
        manager, _ = manager_with_initial_data

        details_a = manager.get_component_details("comp-a")
        assert details_a is not None
        assert details_a["name"] == "Component A"
        assert len(details_a["required_variables"]) == 1

        # --- DEFINITIVE FIX: Access the dictionary at index from the list ---
        first_variable = details_a["required_variables"][0]
        assert first_variable["id"] == "VAR_A"

        details_b = manager.get_component_details("comp-b")
        assert details_b is not None
        assert details_b["name"] == "Component B"
        assert details_b["required_variables"] == []

    def test_update_component_variables_enforces_sst(self, manager_with_initial_data):
        """
        Verify that update_component_variables ONLY writes to variables.json
        and does NOT modify the main metadata file, thus enforcing SST.
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

        # --- DEFINITIVE FIX: Access the dictionary at index from the list ---
        updated_variable = details["required_variables"][0]
        assert updated_variable["id"] == "NEW_VAR"

    def test_create_component_is_metadata_clean(self, tmp_path: Path):
        """
        Verify create_component creates an entry in metadata that is clean
        and does NOT contain the 'required_variables' key.
        """
        metadata_file = tmp_path / "components_metadata.json"
        templates_dir = tmp_path / "component_templates"
        templates_dir.mkdir()
        metadata_file.write_text('{"components": {}}')

        manager = ComponentManager(
            templates_path=str(templates_dir), metadata_file_path=str(metadata_file)
        )
        manager.create_component("new-comp", "New Component")

        new_comp_path = templates_dir / "new-comp"
        assert (new_comp_path / "template-config" / "variables.json").exists()

        saved_data = json.loads(metadata_file.read_text())
        assert "new-comp" in saved_data["components"]
        assert "required_variables" not in saved_data["components"]["new-comp"]

    def test_validator_allows_global_variables(self, tmp_path: Path):
        """
        Verify the validator correctly allows system-provided global
        variables during template validation.
        """
        metadata_file = tmp_path / "components_metadata.json"
        metadata_content = {
            "_piselfhosting": {
                "global_variables": ["PISelfhosting_HOST_IP", "service_name"]
            },
            "components": {"test-comp": {}},
        }
        metadata_file.write_text(json.dumps(metadata_content))
        manager = ComponentManager(
            templates_path=str(tmp_path), metadata_file_path=str(metadata_file)
        )

        # --- DEFINITIVE FIX: Quote the value containing Jinja2 syntax ---
        template = textwrap.dedent(
            """\
            services:
              app:
                image: my-app
                hostname: "{{ service_name }}-{{ PISelfhosting_HOST_IP }}"
            """
        )

        manager.validate_component_configuration("test-comp", template, [])

        bad_template = textwrap.dedent(
            """\
            services:
              app:
                image: "my-app:{{ UNDEFINED_VAR }}"
            """
        )
        with pytest.raises(ValueError, match="uses undefined variable"):
            manager.validate_component_configuration("test-comp", bad_template, [])
