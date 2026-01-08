# file: tests/test_setup_manager.py
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

import yaml

from managers.setup_manager import SetupManager


class TestSetupManager(unittest.TestCase):
    """Unit tests for the SetupManager class."""

    def setUp(self):
        # Create a mock ComponentManager with data specific to set up testing
        self.mock_component_manager = MagicMock()
        self.mock_component_manager.get_all_components.return_value = [
            {"id": "setup-test-a", "name": "Setup A", "depends_on": []},
            {"id": "setup-test-b", "name": "Setup B", "depends_on": ["setup-test-a"]},
            {"id": "template-service", "name": "Template Service", "depends_on": []},
        ]

        # Prevent infinite loops in yaml.safe_load by returning valid empty YAML
        # instead of a MagicMock (which acts as an infinite iterator).
        # The new SetupManager expects a 'services' key in the rendered template.
        self.mock_component_manager.get_component_template_content.return_value = (
            "services: {}"
        )
        self.mock_component_manager.render_component_template.return_value = (
            "services: {}"
        )

        # Setup temporary directories for file generation output
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.output_dir = self.temp_path / "output_gen"

        self.mock_component_manager.templates_path = (
            self.temp_path / "component_templates"
        )

        self.setup_manager = SetupManager(
            component_manager=self.mock_component_manager, output_dir=self.output_dir
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_prepare_deployment_package_success(self):
        """
        Test that docker-compose.yml is generated correctly with valid inputs.
        """
        # Arrange
        # The new SetupManager parses this output, so it must be valid YAML structure
        self.mock_component_manager.render_component_template.return_value = """
services:
  generated-service:
    image: custom/image:latest
"""
        selected = ["template-service"]
        user_vars = {"TEST_VAR": "123"}

        # Act
        success, errors = self.setup_manager.prepare_deployment_package(
            selected, user_vars, []
        )

        # Assert Status
        self.assertTrue(success, f"Deployment failed unexpectedly: {errors}")
        self.assertEqual(errors, [], "Errors should be an empty list on success")

        # Assert File Content
        compose_path = self.output_dir / "docker-compose.yml"
        self.assertTrue(compose_path.exists())

        with open(compose_path, "r") as f:
            compose_data = yaml.safe_load(f)

        # This previously failed because 'services' was None.
        # Now it should be a dictionary containing 'generated-service'.
        self.assertIn("generated-service", compose_data["services"])
        self.assertEqual(
            compose_data["services"]["generated-service"]["image"],
            "custom/image:latest",
        )

        # Verify label injection (part of the new logic)
        labels = compose_data["services"]["generated-service"].get("labels", [])
        self.assertTrue(
            any("piselfhosting.component.id=template-service" in lbl for lbl in labels),
            "Component ID label was not injected correctly",
        )

    def test_variable_propagation_to_context(self):
        """
        Verifies that GLOBAL_ variables are passed to the template rendering context.
        """
        # Arrange
        user_vars = {"GLOBAL_API_KEY": "secret-12345"}

        # Inject a component that requires a variable
        components = self.mock_component_manager.get_all_components.return_value
        components[0]["required_variables"] = [
            {"id": "API_KEY", "default": "${GLOBAL_API_KEY}"}
        ]

        # Act
        self.setup_manager.prepare_deployment_package(["setup-test-a"], user_vars, [])

        # Assert
        # Strict compliance: Unpack args tuple first
        args, _ = self.mock_component_manager.render_component_template.call_args
        # args is typically (component_id, context)
        _, final_context = args

        self.assertIn("GLOBAL_API_KEY", final_context)
        self.assertEqual(final_context["GLOBAL_API_KEY"], "secret-12345")


if __name__ == "__main__":
    unittest.main()
