import json
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import ANY, MagicMock, patch

import pytest

from src.managers.component_manager import ComponentManager
from src.managers.deployment_manager import DeploymentManager, ReportError


@pytest.fixture
def mock_structured_error() -> ReportError:
    """Fixture to provide a standard structured error dictionary."""
    return {
        "type": "Validation:Test",
        "summary": "Mocked validation error.",
        "details": "Details of the mocked error.",
        "component_id": "test-comp",
    }


@pytest.fixture
def deployment_manager_setup(tmp_path: Path):
    """Fixture to set up ComponentManager and DeploymentManager."""
    metadata_file = tmp_path / "components_metadata.json"
    metadata_content = '{"components": {}}'
    metadata_file.write_text(metadata_content)

    component_manager = ComponentManager(
        templates_path=str(tmp_path), metadata_file_path=str(metadata_file)
    )
    deployment_manager = DeploymentManager(component_manager=component_manager)
    return deployment_manager


@pytest.fixture
def mock_ssh_manager():
    """
    Fixture to provide a mocked SSHManager instance.
    The execute_command side effect is removed here to enforce isolation and
    explicit definition within each test using it.
    """
    mock_ssh = MagicMock()
    mock_ssh.connect.return_value = (True, "Connected")
    mock_ssh.upload_content.return_value = (True, "")
    return mock_ssh


class TestDeploymentManager:
    def test_deployment_initialization(
        self, deployment_manager_setup: DeploymentManager
    ):
        """
        Tests that the DeploymentManager can be initialized.
        """
        assert deployment_manager_setup is not None

    # START OF REWRITTEN TEST
    def test_discover_service_links_direct_method(self, tmp_path: Path):
        """
        Verify that _discover_service_links correctly generates links using
        the direct method of reading component metadata and the context file,
        ignoring components without a UI.
        """
        # --- ARRANGE ---
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        # 1. Create mock context with the final port values
        context_file = output_dir / "deployment_context.json"
        context_content = {
            "HOMARR_WEB_PORT": "7575",
            "PORTAINER_WEB_PORT": "9443",
        }
        context_file.write_text(json.dumps(context_content))

        # 2. Define the components that were selected for deployment
        selected_components_data: List[Dict[str, Any]] = [
            {
                "id": "homarr",
                "name": "Homarr Dashboard",
                "has_ui": True,
                "ui_port_variable": "HOMARR_WEB_PORT",
                "protocol": "http",
            },
            {
                "id": "portainer",
                "name": "Portainer",
                "has_ui": True,
                "ui_port_variable": "PORTAINER_WEB_PORT",
                "protocol": "https",
            },
            {
                "id": "mariadb",
                "name": "MariaDB",
                "has_ui": False,
            },
        ]

        # 3. Set up the manager and mocks
        # A minimal ComponentManager is sufficient as it's not used by the method
        component_manager = MagicMock(spec=ComponentManager)
        deployment_manager = DeploymentManager(component_manager)
        log_callback = MagicMock()

        # --- ACT ---
        service_links = deployment_manager._discover_service_links(
            ip="192.168.1.100",
            local_output_path=output_dir,
            selected_components_data=selected_components_data,
            log_callback=log_callback,
        )

        # --- ASSERT ---
        assert service_links is not None
        assert len(service_links) == 2  # MariaDB should be ignored

        # Create a map for easier assertion
        links_map = {link["name"]: link["url"] for link in service_links}
        assert "Homarr Dashboard" in links_map
        assert links_map["Homarr Dashboard"] == "http://192.168.1.100:7575"
        assert "Portainer" in links_map
        assert links_map["Portainer"] == "https://192.168.1.100:9443"

        log_callback.assert_any_call("SUCCESS: Found 2 web UIs.", is_step=True)

    # END OF REWRITTEN TEST

    def test_extract_requested_ports(self, deployment_manager_setup: DeploymentManager):
        """
        Tests that _extract_requested_ports correctly parses host ports from
        various port string formats in component metadata.
        """
        # --- ARRANGE ---
        components: List[Dict[str, Any]] = [
            {
                "id": "comp_a",
                "ports": ["80:80/tcp", "443:443"],
            },
            {
                "id": "comp_b",
                "ports": ["8080", "9000/udp"],
            },
            {
                "id": "comp_c",
                "ports": ["invalid-port-string"],
            },
            {
                "id": "comp_d",
                "ports": None,
            },
        ]

        # --- ACT ---
        requested_ports = deployment_manager_setup._extract_requested_ports(components)

        # --- ASSERT ---
        expected_ports = {80, 443, 8080, 9000}
        assert requested_ports == expected_ports

    def test_start_deployment_live_conflict_failure(
        self, tmp_path: Path, mock_ssh_manager: MagicMock
    ):
        """
        Tests that deployment fails immediately when a live service conflict is
        detected and structured errors are reported.
        """
        # --- ARRANGE ---
        task_id = "fail-conflict-789"
        tasks_dict: Dict[str, Dict[str, Any]] = {
            task_id: {
                "status": "running",
                "logs": [],
                "service_links": [],
                "errors": [],
            }
        }
        output_path = tmp_path / "output"
        output_path.mkdir()
        # Create the necessary context file for the initial load
        (output_path / "deployment_context.json").write_text("{}")
        managed_devices = [
            {"ip": "192.168.1.100", "username": "pi", "password": "raspberry"}
        ]
        components_to_clean: List[str] = []
        selected_components_data: List[Dict[str, Any]] = [
            {"id": "nginx", "ports": ["80:80/tcp"]},
            {"id": "traefik"},
        ]

        metadata_file = tmp_path / "components_metadata.json"
        metadata_file.write_text('{"components": {}}')
        component_manager = ComponentManager(
            templates_path=str(tmp_path),
            metadata_file_path=str(metadata_file),
        )
        deployment_manager = DeploymentManager(component_manager)

        with patch(
            "src.managers.deployment_manager.SSHManager",
            return_value=mock_ssh_manager,
        ):
            mock_ssh_manager.execute_command.side_effect = [
                (0, "other-nginx-container|0.0.0.0:80->80/tcp"),
                (0, "piselfhosting-traefik-1\nother-container"),
            ]

            # --- ACT ---
            deployment_manager.start_deployment(
                task_id,
                tasks_dict,
                str(output_path),
                managed_devices,
                components_to_clean,
                [],
                selected_components_data,
            )

            # --- ASSERT ---
            mock_ssh_manager.connect.assert_called_once()
            mock_ssh_manager.close.assert_called_once()
            assert mock_ssh_manager.execute_command.call_count == 2
            assert tasks_dict[task_id]["status"] == "failed"
            errors: List[ReportError] = tasks_dict[task_id]["errors"]
            assert len(errors) == 2

            port_conflict = errors[0]
            assert port_conflict["type"] == "LiveConflict:Port"
            name_conflict = errors[1]
            assert name_conflict["type"] == "LiveConflict:Name"
            assert name_conflict["component_id"] == "traefik"

    @patch.object(
        DeploymentManager,
        "_prepare_deployment_context",
        return_value=[
            {
                "type": "Validation:Mock",
                "summary": "MOCK ERROR",
                "details": "MOCK DETAILS",
                "component_id": "MOCK-ID",
            }
        ],
    )
    @patch.object(
        DeploymentManager, "_check_live_service_conflicts", return_value=False
    )
    def test_start_deployment_pre_flight_failure(
        self,
        mock_check_conflicts: MagicMock,
        _mock_prepare_context: MagicMock,
        tmp_path: Path,
    ):
        """
        Tests that deployment fails immediately if pre-flight validation returns
        structured errors.
        """
        # --- ARRANGE ---
        task_id = "fail-task-456"
        tasks_dict: Dict[str, Dict[str, Any]] = {
            task_id: {
                "status": "running",
                "logs": [],
                "service_links": [],
                "errors": [],
            }
        }
        output_path = tmp_path / "output"
        output_path.mkdir()
        # Create the necessary context file for the initial load
        (output_path / "deployment_context.json").write_text("{}")
        managed_devices = [
            {"ip": "192.168.1.100", "username": "pi", "password": "raspberry"}
        ]
        selected_components_data: List[Dict[str, Any]] = [{"id": "comp_a"}]

        metadata_file = tmp_path / "components_metadata.json"
        metadata_file.write_text('{"components": {}}')
        component_manager = ComponentManager(
            templates_path=str(tmp_path),
            metadata_file_path=str(metadata_file),
        )
        deployment_manager = DeploymentManager(component_manager)

        with patch(
            "src.managers.deployment_manager.SSHManager"
        ) as mock_ssh_manager_class:
            # --- ACT ---
            deployment_manager.start_deployment(
                task_id,
                tasks_dict,
                str(output_path),
                managed_devices,
                [],
                [],
                selected_components_data,
            )

            # --- ASSERT ---
            _mock_prepare_context.assert_called_once()
            mock_check_conflicts.assert_not_called()
            mock_ssh_manager_class.assert_not_called()
            assert tasks_dict[task_id]["status"] == "failed"
            errors: List[ReportError] = tasks_dict[task_id]["errors"]
            assert len(errors) == 1
            (error_report,) = errors
            assert error_report["type"] == "Validation:Mock"
            assert error_report["summary"] == "MOCK ERROR"

    @patch.object(
        DeploymentManager,
        "_prepare_deployment_context",
        return_value={"selected_components_data": [], "global_vars": {}},
    )
    @patch.object(
        DeploymentManager, "_check_live_service_conflicts", return_value=False
    )
    @patch.object(DeploymentManager, "_transfer_and_extract_archive", return_value=True)
    # FIX: Update mock for the new discovery method signature
    @patch.object(DeploymentManager, "_discover_service_links", return_value=[])
    def test_start_deployment_happy_path(
        self,
        mock_discover_links: MagicMock,
        mock_transfer_archive: MagicMock,
        mock_check_conflicts: MagicMock,
        _mock_prepare_context: MagicMock,
        tmp_path: Path,
        mock_ssh_manager: MagicMock,
    ):
        """
        Tests the successful orchestration logic of the start_deployment method.
        """
        with patch(
            "src.managers.deployment_manager.SSHManager",
            return_value=mock_ssh_manager,
        ):
            metadata_file = tmp_path / "components_metadata.json"
            metadata_file.write_text('{"components": {"homarr": {"id": "homarr"}}}')
            component_manager = ComponentManager(
                templates_path=str(tmp_path),
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
            output_path = tmp_path / "output"
            output_path.mkdir()
            (output_path / "deployment_context.json").write_text("{}")

            managed_devices = [
                {"ip": "192.168.1.100", "username": "pi", "password": "raspberry"}
            ]
            components_to_clean: List[str] = ["homarr"]
            selected_components_data: List[Dict[str, Any]] = [{"id": "homarr"}]

            def custom_execute_command(command: str, *_args: Any, **_kwargs: Any):
                if command == "echo $HOME":
                    return 0, "/home/pi"
                return 0, ""

            mock_ssh_manager.execute_command.side_effect = custom_execute_command

            # --- ACT ---
            deployment_manager.start_deployment(
                task_id,
                tasks_dict,
                str(output_path),
                managed_devices,
                components_to_clean,
                [],
                selected_components_data,
            )

            # --- ASSERT ---
            errors: List[ReportError] = tasks_dict[task_id]["errors"]
            assert not errors
            mock_ssh_manager.connect.assert_called_once()
            mock_check_conflicts.assert_called_once()
            mock_transfer_archive.assert_called_once()
            # FIX: Assert the new signature of the mocked discovery method
            mock_discover_links.assert_called_once_with(
                "192.168.1.100",
                output_path,
                selected_components_data,
                ANY,
            )

            remote_dir = "/home/pi/piselfhosting_deployment"
            mock_ssh_manager.execute_command.assert_any_call(
                f"cd {remote_dir} && docker compose up -d", ANY
            )
            assert tasks_dict[task_id]["status"] == "completed"
            mock_ssh_manager.close.assert_called_once()

    def test_validate_traefik_configuration_no_conflicts(
        self, deployment_manager_setup: DeploymentManager
    ):
        """
        Tests that _validate_traefik_configuration returns an empty list
        for valid input.
        """
        components: List[Dict[str, Any]] = [
            {
                "id": "comp_a",
                "has_traefik_support": True,
                "traefik_internal_port": 80,
            },
            {
                "id": "comp_b",
                "has_traefik_support": True,
                "traefik_internal_port": 81,
            },
        ]
        global_vars = {"TRAEFIK_HOST": "app", "FQDN_SUFFIX": "local"}
        errors = deployment_manager_setup._validate_traefik_configuration(
            components, global_vars
        )
        assert not errors

    def test_validate_traefik_configuration_duplicate_port(
        self, deployment_manager_setup: DeploymentManager
    ):
        """
        Tests that _validate_traefik_configuration returns a structured error
        for duplicate internal ports.
        """
        components: List[Dict[str, Any]] = [
            {
                "id": "comp_a",
                "has_traefik_support": True,
                "traefik_internal_port": 80,
            },
            {
                "id": "comp_b",
                "has_traefik_support": True,
                "traefik_internal_port": 80,
            },
        ]
        global_vars = {"TRAEFIK_HOST": "app", "FQDN_SUFFIX": "local"}
        errors = deployment_manager_setup._validate_traefik_configuration(
            components, global_vars
        )
        assert len(errors) == 1
        (error_report,) = errors
        assert error_report["type"] == "Validation:DuplicatePort"
        assert error_report["component_id"] == "comp_b"

    def test_validate_traefik_configuration_duplicate_hostname(
        self, deployment_manager_setup: DeploymentManager
    ):
        """
        Tests that _validate_traefik_configuration returns a structured error
        for duplicate Traefik-derived hostnames.
        """
        components: List[Dict[str, Any]] = [
            {
                "id": "service-a",
                "has_traefik_support": True,
                "traefik_internal_port": 80,
            },
            {
                "id": "service-a",
                "has_traefik_support": True,
                "traefik_internal_port": 81,
            },
        ]
        global_vars = {"TRAEFIK_HOST": "app", "FQDN_SUFFIX": "local"}
        errors = deployment_manager_setup._validate_traefik_configuration(
            components, global_vars
        )
        assert len(errors) == 1
        (error_report,) = errors
        assert error_report["type"] == "Validation:DuplicateHostname"
        assert error_report["component_id"] == "service-a"
