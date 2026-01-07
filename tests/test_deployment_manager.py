# file: tests/test_deployment_manager.py
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

from managers.component_manager import ComponentManager
from managers.deployment_manager import DeploymentManager, ReportError


class TestDeploymentManager(unittest.TestCase):
    """Unit tests for the DeploymentManager class."""

    def setUp(self):
        """Set up a temporary directory for test artifacts."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)

    def tearDown(self):
        """Clean up the temporary directory."""
        self.temp_dir.cleanup()

    @patch.object(DeploymentManager, "_discover_service_links", return_value=[])
    @patch.object(DeploymentManager, "_transfer_and_extract_archive", return_value=True)
    @patch.object(
        DeploymentManager, "_check_live_service_conflicts", return_value=False
    )
    @patch.object(
        DeploymentManager,
        "_prepare_deployment_context",
        return_value={"selected_components_data": [], "global_vars": {}},
    )
    def test_start_deployment_happy_path(
        self,
        _mock_prepare_context: MagicMock,
        _mock_check_conflicts: MagicMock,
        _mock_transfer_archive: MagicMock,
        _mock_discover_links: MagicMock,
    ):
        """
        Tests the successful orchestration of the start_deployment method.
        """
        with patch("managers.deployment_manager.SSHManager") as mock_ssh_class:
            mock_ssh_instance = MagicMock()
            mock_ssh_instance.connect.return_value = (True, "Connected successfully")
            mock_ssh_class.return_value = mock_ssh_instance

            metadata_file = self.temp_path / "components_metadata.json"
            metadata_file.write_text('{"components": {"homarr": {"id": "homarr"}}}')
            component_manager = ComponentManager(
                templates_path=str(self.temp_path),
                metadata_file_path=str(metadata_file),
            )
            deployment_manager = DeploymentManager(component_manager)

            task_id = "test-task-123"
            tasks_dict: Dict[str, Dict[str, Any]] = {
                task_id: {
                    "status": "running",
                    "logs": [],
                    "service_links": [],
                    "errors": [],
                }
            }
            output_path = self.temp_path / "output"
            output_path.mkdir()
            (output_path / "deployment_context.json").write_text("{}")

            managed_devices = [
                {
                    "ip": "192.168.1.100",
                    "username": "pi",
                    "password": "raspberry",
                }
            ]
            components_to_clean: List[str] = ["homarr"]
            selected_components_data: List[Dict[str, Any]] = [{"id": "homarr"}]
            global_vars: Dict[str, Any] = {}

            def custom_execute_command(command: str, *_args: Any, **_kwargs: Any):
                # FIX: Return a valid path for 'echo $HOME'
                if command == "echo $HOME":
                    return 0, "/home/pi"
                # Keep other commands returning a non-empty string
                # to avoid false negatives
                return 0, "ok"

            mock_ssh_instance.execute_command.side_effect = custom_execute_command

            deployment_manager.start_deployment(
                task_id,
                tasks_dict,
                str(output_path),
                managed_devices,
                components_to_clean,
                [],
                selected_components_data,
                global_vars,
            )

            errors: List[ReportError] = tasks_dict[task_id]["errors"]
            self.assertFalse(errors, f"Deployment failed with errors: {errors}")
            self.assertEqual(tasks_dict[task_id]["status"], "completed")


if __name__ == "__main__":
    unittest.main()
