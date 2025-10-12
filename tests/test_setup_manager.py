# file: tests/test_setup_manager.py
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock

import yaml

from managers.setup_manager import SetupManager


class TestSetupManager(unittest.TestCase):
    """Unit tests for the SetupManager class."""

    def setUp(self):
        self.mock_component_manager = MagicMock()
        self.mock_component_manager.get_all_components.return_value = [
            {"id": "comp-a", "name": "Component A", "depends_on": ["comp-b"]},
            {"id": "comp-b", "name": "Component B", "depends_on": []},
            {"id": "test-component", "name": "Test Component", "depends_on": []},
            {"id": "service-a", "name": "Service A", "depends_on": []},
            {"id": "secure-service", "name": "Secure Service", "depends_on": []},
        ]

        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.output_dir = self.temp_path / "output"

        self.mock_component_manager.templates_path = (
            self.temp_path / "component_templates"
        )
        self.project_root_dir = self.temp_path

        self.setup_manager = SetupManager(
            component_manager=self.mock_component_manager, output_dir=self.output_dir
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def _run_deployment_and_get_results(
        self,
        selected: List[str],
        user_vars: Dict[str, Any],
    ) -> tuple[Dict[str, Any], Dict[str, Any]]:
        success, errors = self.setup_manager.prepare_deployment_package(
            selected, user_vars
        )
        self.assertTrue(success, f"Deployment failed unexpectedly: {errors}")
        self.assertIsNone(errors, "Errors should be None on success")

        compose_path = self.output_dir / "docker-compose.yml"
        self.assertTrue(compose_path.exists())
        with open(compose_path, "r") as f:
            compose_data = yaml.safe_load(f)
        return compose_data, {}

    def test_prepare_deployment_package_success(self):
        self.mock_component_manager.render_component_template.return_value = """
services:
  test-service:
    image: test/image
"""
        selected = ["test-component"]
        user_vars = {"TEST_PORT": "8080"}

        compose_data, _ = self._run_deployment_and_get_results(selected, user_vars)

        self.assertIn("test-service", compose_data["services"])
        self.assertEqual(
            compose_data["services"]["test-service"]["image"], "test/image"
        )

    def test_dependency_resolution_fails_on_circular_dependency(self):
        self.mock_component_manager.get_all_components.return_value = [
            {"id": "comp-a", "name": "Component A", "depends_on": ["comp-b"]},
            {"id": "comp-b", "name": "Component B", "depends_on": ["comp-a"]},
        ]
        success, errors = self.setup_manager.prepare_deployment_package(["comp-a"], {})
        self.assertFalse(success)
        self.assertIsNotNone(errors)
        error_details = "".join(e["details"] for e in errors)
        self.assertIn(
            "Circular dependency detected",
            error_details,
            msg=f"Expected substring not found in errors: {errors}",
        )

    def test_dotenv_variable_resolution_success(self):
        with open(self.project_root_dir / ".env", "w") as f:
            f.write("MY_API_KEY=my-secret-key-from-dotenv")

        self.mock_component_manager.get_all_components.return_value[2][
            "required_variables"
        ] = [{"id": "API_KEY", "default": "${MY_API_KEY}"}]
        self.mock_component_manager.render_component_template.return_value = (
            "services:\n  a:\n    image: foo"
        )

        self.setup_manager.prepare_deployment_package(["test-component"], {})

        # FIX: The user variables are now part of the final context update.
        # We assert that the correct context was passed to the renderer.
        call_args, _ = self.mock_component_manager.render_component_template.call_args
        final_context = call_args[1]
        self.assertEqual(final_context["MY_API_KEY"], "my-secret-key-from-dotenv")


if __name__ == "__main__":
    unittest.main()
