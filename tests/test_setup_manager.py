import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

import yaml

# Import the class we are testing
from managers.setup_manager import SetupManager


class TestSetupManager(unittest.TestCase):
    """Unit tests for the SetupManager class."""

    def setUp(self):
        """Set up a mock ComponentManager for each test."""
        # We use MagicMock to allow for mocking any method on the fly.
        self.mock_component_manager = MagicMock()
        # Set up mocks for methods called by the SetupManager.
        self.mock_component_manager.sort_components_by_master_order.side_effect = (
            lambda components: components
        )
        self.mock_component_manager.get_docker_service_name.side_effect = (
            lambda cid: cid.replace("-", "")
        )

    def test_prepare_deployment_package_with_label_injection(self):
        """
        Verify prepare_deployment_package renders templates, injects identity
        labels, and returns success correctly.
        """
        # --- 1. ARRANGE ---
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            output_dir = temp_path / "output"
            template_base_dir = temp_path / "component_templates"

            # Mock the component details that the SetupManager will request.
            self.mock_component_manager.get_component_details.return_value = {
                "name": "Test Component"
            }

            component_template_dir = template_base_dir / "test-component"
            component_template_dir.mkdir(parents=True, exist_ok=True)
            with open(component_template_dir / "docker-compose.template.yml", "w") as f:
                f.write(
                    """
services:
  test-service:
    image: test/image
    ports:
      - "{{ TEST_PORT }}:80"
"""
                )

            setup_manager = SetupManager(
                component_manager=self.mock_component_manager, output_dir=output_dir
            )
            setup_manager.template_base_path = template_base_dir

            selected_components = ["test-component"]
            user_variables = {"TEST_PORT": "8080"}
            managed_devices = [{"ip": "192.168.1.100"}]

            # --- 2. ACT ---
            # --- FIX: Capture the correct (success, errors) tuple ---
            success, errors = setup_manager.prepare_deployment_package(
                selected_components, user_variables, managed_devices
            )

            # --- 3. ASSERT ---
            self.assertTrue(success)
            # --- FIX: Assert that the errors list is empty ---
            self.assertEqual([], errors)

            # Verify deployment context was written correctly
            context_path = output_dir / "deployment_context.json"
            self.assertTrue(context_path.exists())
            with open(context_path, "r") as f:
                context_data = json.load(f)
            self.assertEqual(context_data["TEST_PORT"], "8080")

            # Verify docker-compose.yml was written and processed correctly
            compose_path = output_dir / "docker-compose.yml"
            self.assertTrue(compose_path.exists())
            with open(compose_path, "r") as f:
                compose_data = yaml.safe_load(f)

            self.assertIn("services", compose_data)
            self.assertIn("test-service", compose_data["services"])

            # --- NEW: Assert that our critical identity label was injected ---
            service_labels = compose_data["services"]["test-service"]["labels"]
            self.assertIn("piselfhosting.component.id=test-component", service_labels)


if __name__ == "__main__":
    unittest.main()
