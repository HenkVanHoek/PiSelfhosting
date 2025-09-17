import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

# Import the class we are testing
from managers.setup_manager import SetupManager


class TestSetupManager(unittest.TestCase):
    """Unit tests for the SetupManager class."""

    def setUp(self):
        """Set up a mock ComponentManager for each test."""
        self.patcher_component_manager = patch(
            "managers.setup_manager.ComponentManager"
        )
        self.mock_component_manager = self.patcher_component_manager.start()

    def tearDown(self):
        """Stop all patchers after each test."""
        self.patcher_component_manager.stop()

    def test_prep_dploy_packg_isolates_list_rendering_saves_correctly(
        self,
    ):
        """
        Verify 'selected_components' is not rendered but saved correctly.
        """
        # --- 1. ARRANGE ---
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            output_dir = temp_path / "output"
            template_base_dir = temp_path / "component_templates"

            self.mock_component_manager.get_component_details.return_value = {
                "name": "Test Component"
            }
            self.mock_component_manager.metadata_file = str(
                temp_path / "config/components_metadata.json"
            )

            component_template_dir = template_base_dir / "test-component"
            component_template_dir.mkdir(parents=True)
            with open(component_template_dir / "docker-compose.template.yml", "w") as f:
                f.write(
                    """
services:
  test-component:
    image: test/image
    ports:
      - "{{ TEST_PORT }}:80"
volumes:
  test_data:
    name: piselfhosting-test-data
"""
                )

            # --- MODIFIED: Pass Path object to satisfy type hints ---
            self.setup_manager = SetupManager(
                component_manager=self.mock_component_manager, output_dir=output_dir
            )
            self.setup_manager.template_base_path = template_base_dir

            selected_components = ["test-component"]
            user_variables = {"TEST_PORT": "8080"}
            managed_devices = [{"ip": "192.168.1.100"}]

            # --- 2. ACT ---
            success, result_path = self.setup_manager.prepare_deployment_package(
                selected_components, user_variables, managed_devices
            )

            # --- 3. ASSERT ---
            self.assertTrue(success)
            self.assertEqual(str(output_dir), result_path)

            context_path = output_dir / "deployment_context.json"
            self.assertTrue(context_path.exists())
            with open(context_path, "r") as f:
                context_data = json.load(f)

            self.assertIn("selected_components", context_data)
            self.assertEqual(context_data["selected_components"], ["test-component"])
            self.assertEqual(context_data["TEST_PORT"], "8080")

            compose_path = output_dir / "docker-compose.yml"
            self.assertTrue(compose_path.exists())
            with open(compose_path, "r") as f:
                compose_data = yaml.safe_load(f)

            self.assertIn("services", compose_data)
            self.assertIn("test-component", compose_data["services"])
            self.assertEqual(
                compose_data["services"]["test-component"]["ports"], ["8080:80"]
            )


if __name__ == "__main__":
    unittest.main()
