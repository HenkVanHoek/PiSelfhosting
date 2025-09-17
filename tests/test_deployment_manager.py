import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml

# Import the class we are testing
from managers.deployment_manager import DeploymentManager


class TestDeploymentManager(unittest.TestCase):
    """Unit tests for the DeploymentManager class."""

    def setUp(self):
        """Set up a mock ComponentManager and a temporary file system for each test."""
        self.patcher_component_manager = patch(
            "managers.deployment_manager.ComponentManager"
        )
        self.mock_component_manager = self.patcher_component_manager.start()

        self.patcher_ssh_manager = patch("managers.deployment_manager.SSHManager")
        self.mock_ssh_manager_class = self.patcher_ssh_manager.start()

        self.mock_ssh_instance = MagicMock()
        self.mock_ssh_manager_class.return_value = self.mock_ssh_instance

        self.deployment_manager = DeploymentManager(
            component_manager=self.mock_component_manager
        )

    def tearDown(self):
        """Stop all patchers after each test."""
        self.patcher_component_manager.stop()
        self.patcher_ssh_manager.stop()

    def test_clean_services_identifies_and_removes_resources(self):
        """
        Verify that the clean_services method correctly stops the container,
        removes it, and then removes its associated named volumes.
        """
        # --- 1. ARRANGE ---
        with tempfile.TemporaryDirectory() as temp_dir:
            remote_fs_path = Path(temp_dir)

            mock_pihole_metadata = {"name": "Pi-hole", "has_configuration": True}
            self.mock_component_manager.get_component_details.return_value = (
                mock_pihole_metadata
            )

            compose_template_content = {
                "services": {
                    "pi-hole": {
                        "container_name": "piselfhosting-pihole",
                        "volumes": [
                            "pihole_etc:/etc/pihole",
                            "pihole_dnsmasq:/etc/dnsmasq.d",
                        ],
                    }
                },
                "volumes": {
                    "pihole_etc": {"name": "piselfhosting-pihole-etc"},
                    "pihole_dnsmasq": {"name": "piselfhosting-pihole-dnsmasq"},
                },
            }
            remote_template_path = remote_fs_path / "component_templates" / "pi-hole"
            remote_template_path.mkdir(parents=True)
            with open(remote_template_path / "docker-compose.template.yml", "w") as f:
                yaml.dump(compose_template_content, f)

            executed_commands = []
            self.mock_ssh_instance.execute_command.side_effect = (
                lambda cmd, _: executed_commands.append(cmd)
            )

            # --- 2. ACT ---
            self.deployment_manager._perform_cleanup(
                self.mock_ssh_instance, ["pi-hole"], MagicMock()
            )

            # --- 3. ASSERT ---
            self.assertEqual(len(executed_commands), 3)
            self.assertIn("docker stop piselfhosting-pihole", executed_commands)
            self.assertIn("docker rm piselfhosting-pihole", executed_commands)
            self.assertIn(
                "docker volume rm piselfhosting-pihole-etc "
                "piselfhosting-pihole-dnsmasq",
                executed_commands,
            )


if __name__ == "__main__":
    unittest.main()
