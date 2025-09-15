import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml

from managers.setup_manager import SetupManager


class TestSetupManager(unittest.TestCase):
    """Final, correct tests for the SetupManager class."""

    def setUp(self):
        """Set up a mock ComponentManager and a temporary file system."""
        # We only need to patch the direct dependency, ComponentManager.
        self.patcher_component_manager = patch(
            "managers.setup_manager.ComponentManager"
        )
        self.mock_component_manager = self.patcher_component_manager.start()

        self.temp_dir = tempfile.TemporaryDirectory()
        self.project_root = Path(self.temp_dir.name)

        # Define the locations for our temporary templates and output
        self.template_base_dir = self.project_root / "component_templates"
        self.output_dir = self.project_root / "output"

        # Create the real, temporary template file the method needs
        template_path = self.template_base_dir / "portainer"
        template_path.mkdir(parents=True)
        (template_path / "docker-compose.template.yml").write_text(
            "services:\n  portainer:\n"
            "    image: portainer/portainer-ce:{{ PISelfhosting_HOST_IP }}"
        )

        # Create the SetupManager, injecting both the mock manager and
        # the real temporary template path
        self.setup_manager = SetupManager(
            component_manager=self.mock_component_manager,
            output_dir=self.output_dir,
            template_base_path=self.template_base_dir,
        )

    def tearDown(self):
        """Clean up resources after each test."""
        self.temp_dir.cleanup()
        self.patcher_component_manager.stop()

    def test_generate_all_files_with_real_template(self):
        """
        Test the successful generation of a docker-compose file using a real,
        temporary template file.
        """
        # --- ARRANGE ---
        self.setup_manager._resolve_dependencies = MagicMock(return_value=["portainer"])
        self.mock_component_manager.get_component_details.return_value = {
            "name": "Portainer",
            "required_variables": [],
        }

        # --- ACT ---
        # The managed_devices argument must be a LIST of dictionaries.
        success, errors = self.setup_manager.generate_all_files(
            selected_components=["portainer"],
            user_variables={},
            managed_devices=[{"ip": "192.168.1.10"}],
        )

        # --- ASSERT ---
        self.assertTrue(success, f"generate_all_files failed with errors: {errors}")

        expected_output_file = self.output_dir / "docker-compose.yml"
        self.assertTrue(expected_output_file.exists())

        with open(expected_output_file, "r") as f:
            content = yaml.safe_load(f)
        self.assertIn("portainer", content.get("services", {}))
        self.assertEqual(
            content["services"]["portainer"]["image"],
            "portainer/portainer-ce:192.168.1.10",
        )


if __name__ == "__main__":
    unittest.main()
