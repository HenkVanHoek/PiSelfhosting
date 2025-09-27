import json
from pathlib import Path
from unittest.mock import ANY, MagicMock, patch

import pytest
import yaml

from src.managers.component_manager import ComponentManager
from src.managers.deployment_manager import DeploymentManager


class TestDeploymentManager:
    def test_deployment_initialization(self, tmp_path):
        """
        Tests that the DeploymentManager can be initialized.
        """
        metadata_file = tmp_path / "components_metadata.json"
        metadata_file.write_text('{"components": {}}')

        component_manager = ComponentManager(
            templates_path=str(tmp_path),
            metadata_file_path=str(metadata_file),
        )

        deployment_manager = DeploymentManager(component_manager=component_manager)
        assert deployment_manager is not None

    def test_discover_links_deduplicates_init_containers(self, tmp_path: Path):
        """
        Verify that _discover_service_links correctly generates only one link
        for a component that has both a main service and an init service.
        """
        # --- ARRANGE ---
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        # 1. Create mock metadata with the critical 'docker_service_name' pointer
        metadata_file = tmp_path / "components_metadata.json"
        metadata_content = {
            "components": {
                "traefik": {
                    "id": "traefik",
                    "name": "Traefik Proxy",
                    "has_ui": True,
                    "docker_service_name": "traefik-main",
                    "ui_port_variable": "TRAEFIK_WEB_PORT",
                    "protocol": "http",
                }
            }
        }
        metadata_file.write_text(json.dumps(metadata_content))

        # 2. Create mock context with the final port value
        context_file = output_dir / "deployment_context.json"
        context_content = {"TRAEFIK_WEB_PORT": "8080"}
        context_file.write_text(json.dumps(context_content))

        # 3. Create mock compose file with two services for the same component
        compose_file = output_dir / "docker-compose.yml"
        compose_content = {
            "services": {
                "traefik-init": {
                    "image": "busybox",
                    "labels": ["piselfhosting.component.id=traefik"],
                },
                "traefik-main": {
                    "image": "traefik:v3.0",
                    "labels": ["piselfhosting.component.id=traefik"],
                },
            }
        }
        compose_file.write_text(yaml.dump(compose_content))

        # 4. Set up the managers
        component_manager = ComponentManager(
            templates_path=str(tmp_path),
            metadata_file_path=str(metadata_file),
        )
        deployment_manager = DeploymentManager(component_manager=component_manager)
        log_callback = MagicMock()

        # --- ACT ---
        service_links = deployment_manager._discover_service_links(
            ip="192.168.1.100",
            local_output_path=output_dir,
            log_callback=log_callback,
        )

        # --- ASSERT ---
        assert service_links is not None
        assert len(service_links) == 1
        link = service_links[0]
        assert link["name"] == "Traefik Proxy"
        assert link["url"] == "http://192.168.1.100:8080"


@pytest.fixture
def mock_ssh_manager():
    """Fixture to provide a mocked SSHManager instance."""
    mock_ssh = MagicMock()
    mock_ssh.connect.return_value = (True, "Connected")
    # Simulate the 'echo $HOME' command returning a path
    mock_ssh.execute_command.side_effect = [
        (0, ""),  # docker stop
        (0, ""),  # docker rm
        (0, "/home/pi"),  # echo $HOME
        (0, ""),  # mkdir
        (0, ""),  # tar
        (0, ""),  # rm tarball
        (0, ""),  # docker compose
    ]
    return mock_ssh


def test_start_deployment_happy_path(tmp_path: Path, mock_ssh_manager: MagicMock):
    """
    Tests the successful orchestration logic of the start_deployment method.
    """
    # --- ARRANGE ---
    # 1. Patch the SSHManager to be replaced by our mock
    with patch(
        "src.managers.deployment_manager.SSHManager", return_value=mock_ssh_manager
    ):
        # 2. Set up the component and deployment managers
        metadata_file = tmp_path / "components_metadata.json"
        metadata_file.write_text('{"components": {"homarr": {"id": "homarr"}}}')
        component_manager = ComponentManager(
            templates_path=str(tmp_path), metadata_file_path=str(metadata_file)
        )
        deployment_manager = DeploymentManager(component_manager=component_manager)

        # 3. Prepare the input arguments for start_deployment
        task_id = "test-task-123"
        tasks_dict = {task_id: {"status": "running", "logs": [], "service_links": []}}
        output_path = tmp_path / "output"
        output_path.mkdir()
        (output_path / "deployment_context.json").write_text("{}")
        (output_path / "docker-compose.yml").write_text("services: {}")

        managed_devices = [
            {"ip": "192.168.1.100", "username": "pi", "password": "raspberry"}
        ]
        components_to_clean = ["homarr"]
        components_to_restart = ["portainer"]

        # --- ACT ---
        deployment_manager.start_deployment(
            task_id,
            tasks_dict,
            str(output_path),
            managed_devices,
            components_to_clean,
            components_to_restart,
        )

        # --- ASSERT ---
        # Verify the orchestration flow by checking calls to the mock
        mock_ssh_manager.connect.assert_called_once()

        # START OF FIX: Replaced MagicMock() with ANY to correctly assert the call.
        # Check that the cleanup command for 'homarr' was called
        mock_ssh_manager.execute_command.assert_any_call(
            "docker stop piselfhosting-homarr", ANY, check_exit_code=False
        )
        mock_ssh_manager.execute_command.assert_any_call(
            "docker rm piselfhosting-homarr", ANY, check_exit_code=False
        )

        # Check that the core deployment commands were executed
        mock_ssh_manager.execute_command.assert_any_call("echo $HOME", ANY)
        remote_dir = "/home/pi/piselfhosting_deployment"
        mock_ssh_manager.execute_command.assert_any_call(
            f"cd {remote_dir} && docker compose up -d", ANY
        )
        # END OF FIX

        # Verify the process completes successfully
        assert tasks_dict[task_id]["status"] == "completed"
        mock_ssh_manager.close.assert_called_once()
