import json
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import ANY, MagicMock, patch

import pytest
import yaml

from src.managers.component_manager import ComponentManager
from src.managers.deployment_manager import DeploymentManager, ReportError


# --- NEW FIXTURE FOR MOCKING STRUCTURED ERRORS ---
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

    # Mock upload_content for happy path
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

    def test_discover_links_deduplicates_init_containers(self, tmp_path: Path):
        """
        Verify that _discover_service_links correctly generates only one link
        for a component that has both a main service and an init service.
        The main service name must match the component ID.
        """
        # --- ARRANGE ---
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        # 1. Create mock metadata with the component ID as the implied service name
        metadata_file = tmp_path / "components_metadata.json"
        metadata_content = {
            "components": {
                "traefik": {  # Component ID
                    "id": "traefik",
                    "name": "Traefik Proxy",
                    "has_ui": True,
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

        # 3. Create mock compose file: main service name must match the component ID
        compose_file = output_dir / "docker-compose.yml"
        compose_content = {
            "services": {
                "traefik-init": {
                    "image": "busybox",
                    "labels": ["piselfhosting.component.id=traefik"],
                },
                "traefik": {  # Main service name == component ID
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
        # Initialize tasks_dict for the method call
        task_id = "test-discover"
        # FIX: Explicit type hint to solve mypy error
        tasks_dict: Dict[str, Dict[str, Any]] = {task_id: {"errors": []}}

        # --- ACT ---
        # Update: Added tasks_dict and task_id arguments
        service_links = deployment_manager._discover_service_links(
            ip="192.168.1.100",
            local_output_path=output_dir,
            tasks_dict=tasks_dict,
            task_id=task_id,
            log_callback=log_callback,
        )

        # --- ASSERT ---
        assert service_links is not None
        assert len(service_links) == 1
        link = service_links[0]
        assert link["name"] == "Traefik Proxy"
        assert link["url"] == "http://192.168.1.100:8080"
        # New Assertion: No errors reported
        errors: List[ReportError] = tasks_dict[task_id]["errors"]
        assert errors == []

    def test_extract_requested_ports(self, deployment_manager_setup: DeploymentManager):
        """
        Tests that _extract_requested_ports correctly parses host ports from
        various port string formats in component metadata.
        """
        # --- ARRANGE ---
        # FIX: Explicitly type hint components to solve mypy error
        components: List[Dict[str, Any]] = [
            {
                "id": "comp_a",
                "ports": ["80:80/tcp", "443:443"],  # Standard format
            },
            {
                "id": "comp_b",
                "ports": ["8080", "9000/udp"],  # Only host port provided
            },
            {
                "id": "comp_c",
                "ports": ["invalid-port-string"],  # Should be ignored
            },
            {
                "id": "comp_d",
                "ports": None,  # Should be skipped by defensive code
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
        detected and structured errors are reported. Uses Component ID as
        the service name.
        """
        # --- ARRANGE ---
        task_id = "fail-conflict-789"
        # FIX: Explicit type hint to solve mypy error
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
        managed_devices = [
            {"ip": "192.168.1.100", "username": "pi", "password": "raspberry"}
        ]
        components_to_clean: List[str] = []
        # Component ID is now the service name
        # FIX: Explicit type hint to solve mypy error
        selected_components_data: List[Dict[str, Any]] = [
            {"id": "nginx", "ports": ["80:80/tcp"]},
            {"id": "traefik"},
        ]
        # FIX: Explicit type hint to solve mypy error
        global_vars: Dict[str, Any] = {}

        # 1. Set up the managers
        metadata_file = tmp_path / "components_metadata.json"
        metadata_file.write_text('{"components": {}}')
        component_manager = ComponentManager(
            templates_path=str(tmp_path), metadata_file_path=str(metadata_file)
        )
        deployment_manager = DeploymentManager(component_manager=component_manager)

        # 2. Mock SSH to simulate a port conflict and a name conflict
        with patch(
            "src.managers.deployment_manager.SSHManager", return_value=mock_ssh_manager
        ):
            # Override execute_command side_effect for the conflict check only
            mock_ssh_manager.execute_command.side_effect = [
                # 1. Port Check: Simulate port 80 being in use
                (
                    0,
                    "other-nginx-container|0.0.0.0:80->80/tcp",
                ),
                # 2. Name Check: Simulate a previous piselfhosting-traefik
                # container existing
                (
                    0,
                    "piselfhosting-traefik-1\nother-container",
                ),
                # If deployment continued,
                # the rest would follow, but it should exit here.
            ]

            # --- ACT ---
            deployment_manager.start_deployment(
                task_id,
                tasks_dict,
                str(output_path),
                managed_devices,
                components_to_clean,
                [],  # components_to_restart
                selected_components_data,
                global_vars,
            )

            # --- ASSERT ---
            # 1. Verify SSH was connected, but closed
            mock_ssh_manager.connect.assert_called_once()
            mock_ssh_manager.close.assert_called_once()
            # 2. Verify that two execution commands were
            # called (for the two live checks)
            assert mock_ssh_manager.execute_command.call_count == 2
            # 3. Verify status is failed
            assert tasks_dict[task_id]["status"] == "failed"
            # 4. Verify structured errors were reported (2 conflicts)
            # FIX: Explicitly type hint errors
            errors: List[ReportError] = tasks_dict[task_id]["errors"]
            assert len(errors) == 2

            # Assert Port Conflict Error (Component ID: N/A)
            port_conflict = errors[0]
            assert port_conflict["type"] == "LiveConflict:Port"
            assert "Host port conflict detected." in port_conflict["summary"]
            assert port_conflict["component_id"] == "N/A"

            # Assert Name Conflict Error (Component ID: traefik)
            name_conflict = errors[1]
            assert name_conflict["type"] == "LiveConflict:Name"
            assert (
                "Service name 'traefik' conflict detected." in name_conflict["summary"]
            )
            assert name_conflict["component_id"] == "traefik"

    @patch.object(
        DeploymentManager,
        "_prepare_deployment_context",
        # FIX: The mock must now return a list of structured errors on failure
        return_value=[
            {
                "type": "Validation:Mock",
                "summary": "MOCK ERROR",
                "details": "MOCK DETAILS",
                "component_id": "MOCK-ID",
            }
        ],
    )
    # Patch the helpers that now require the full tasks_dict/task_id signature
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
        structured errors, and verifies the errors list is populated.
        """
        # --- ARRANGE ---
        task_id = "fail-task-456"
        # FIX: Explicit type hint to solve mypy error
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
        managed_devices = [
            {"ip": "192.168.1.100", "username": "pi", "password": "raspberry"}
        ]
        components_to_clean: List[str] = []
        components_to_restart: List[str] = []
        # FIX: Explicit type hint to solve mypy error
        selected_components_data: List[Dict[str, Any]] = [{"id": "comp_a"}]
        # FIX: Explicit type hint to solve mypy error
        global_vars: Dict[str, Any] = {}

        # 1. Set up the managers (only needed for the call itself)
        metadata_file = tmp_path / "components_metadata.json"
        metadata_file.write_text('{"components": {}}')
        component_manager = ComponentManager(
            templates_path=str(tmp_path), metadata_file_path=str(metadata_file)
        )
        deployment_manager = DeploymentManager(component_manager=component_manager)

        with patch(
            "src.managers.deployment_manager.SSHManager"
        ) as mock_ssh_manager_class:
            # --- ACT ---
            deployment_manager.start_deployment(
                task_id,
                tasks_dict,
                str(output_path),
                managed_devices,
                components_to_clean,
                components_to_restart,
                selected_components_data,
                global_vars,
            )

            # --- ASSERT ---
            _mock_prepare_context.assert_called_once()
            # FIX: Conflict check should NOT be called on pre-flight failure
            mock_check_conflicts.assert_not_called()
            # Verify no SSH connection was attempted
            mock_ssh_manager_class.assert_not_called()
            # Verify status is failed
            assert tasks_dict[task_id]["status"] == "failed"

            # Verify structured errors were captured
            # FIX: Explicitly type hint errors
            errors: List[ReportError] = tasks_dict[task_id]["errors"]
            assert len(errors) == 1
            (error_report,) = errors

            # Assert data contract of the reported error
            assert error_report["type"] == "Validation:Mock"
            # CRITICAL FIX: Corrected assertion to match the mock's return value exactly
            assert error_report["summary"] == "MOCK ERROR"

            # Verify log was created (checks for _report_error's log)
            logs = tasks_dict[task_id]["logs"]
            assert "FATAL: [Validation:Mock] MOCK ERROR" in logs[2]
            assert "FATAL: Pre-flight validation failed" in logs[1]

    @patch.object(
        DeploymentManager,
        "_prepare_deployment_context",
        return_value={"selected_components_data": [], "global_vars": {}},
    )
    # Patch the helpers that now require the full tasks_dict/task_id signature
    @patch.object(
        DeploymentManager, "_check_live_service_conflicts", return_value=False
    )
    @patch.object(DeploymentManager, "_transfer_and_extract_archive", return_value=True)
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
        Tests the successful orchestration logic of the start_deployment method
        and verifies the final status is 'completed' with no structured errors.
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
            # FIX: Explicit type hint to solve mypy error
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
            (output_path / "docker-compose.yml").write_text("services: {}")

            managed_devices = [
                {"ip": "192.168.1.100", "username": "pi", "password": "raspberry"}
            ]
            components_to_clean: List[str] = ["homarr"]
            # FIX: Explicit type hint to solve mypy error
            selected_components_data: List[Dict[str, Any]] = [{"id": "homarr"}]
            # FIX: Explicit type hint to solve mypy error
            global_vars: Dict[str, Any] = {
                "TRAEFIK_HOST": "app",
                "FQDN_SUFFIX": "local",
            }

            # CRITICAL DEFENSIVE FIX: Use a custom side effect function to ensure
            # the 'echo $HOME' command, which is the 5th call, returns a clean,
            # guaranteed value, overriding any subtle mock parsing issues.

            # The 9 sequenced results for execute_command (excluding
            # echo $HOME's explicit return)
            success_side_effects = iter(
                [
                    (0, ""),  # 1. Port Check
                    (0, ""),  # 2. Name Check
                    (0, ""),  # 3. Cleanup: docker stop
                    (0, ""),  # 4. Cleanup: docker rm
                    # 5. Deployment: echo $HOME (handled below)
                    (0, ""),  # 6. Deployment: mkdir -p
                    (0, ""),  # 7. Deployment: tar extract
                    (0, ""),  # 8. Deployment: rm tarball
                    (0, ""),  # 9. Deployment: docker compose up -d
                ]
            )

            # FIX: Used *_args and **_kwargs to capture all arguments correctly
            def custom_execute_command(command: str, *_args: Any, **_kwargs: Any):
                # Guaranteed result for the problematic call
                if command == "echo $HOME":
                    return 0, "/home/pi"

                # All other commands use the sequenced iterator
                try:
                    return next(success_side_effects)
                except StopIteration:
                    return 0, ""

            mock_ssh_manager.execute_command.side_effect = custom_execute_command

            # --- ACT ---
            deployment_manager.start_deployment(
                task_id,
                tasks_dict,
                str(output_path),
                managed_devices,
                components_to_clean,
                [],  # components_to_restart
                selected_components_data,
                global_vars,
            )

            # --- ASSERT ---
            # 1. Verify structural integrity
            assert "errors" in tasks_dict[task_id]
            # FIX: Explicitly type hint errors
            errors: List[ReportError] = tasks_dict[task_id]["errors"]
            assert errors == []  # Critical assertion: Now correctly asserted

            # 2. Verify SSH orchestration flow
            mock_ssh_manager.connect.assert_called_once()

            # 3. Verify helper methods were called with new arguments
            mock_check_conflicts.assert_called_once()
            mock_transfer_archive.assert_called_once()
            mock_discover_links.assert_called_once()

            # The final deployment command call (docker compose up -d) is now mocked
            # by mock_ssh_manager.execute_command returning the 9th value (0, "")
            remote_dir = "/home/pi/piselfhosting_deployment"
            mock_ssh_manager.execute_command.assert_called_with(
                f"cd {remote_dir} && docker compose up -d", ANY
            )

            # 4. Verify the process completes successfully
            assert tasks_dict[task_id]["status"] == "completed"
            mock_ssh_manager.close.assert_called_once()

    # --- REFACTORED VALIDATION TESTS TO ASSERT STRUCTURED ERRORS ---

    def test_validate_traefik_configuration_no_conflicts(
        self, deployment_manager_setup: DeploymentManager
    ):
        """
        Tests that _validate_traefik_configuration returns an empty list
        for valid input.
        """
        # --- ARRANGE ---
        # Removed redundant 'docker_service_name'
        components: List[Dict[str, Any]] = [
            {
                "id": "comp_a",
                "name": "Component A",
                "has_traefik_support": True,
                "traefik_internal_port": 80,
            },
            {
                "id": "comp_b",
                "name": "Component B",
                "has_traefik_support": True,
                "traefik_internal_port": 81,
            },
            {
                "id": "comp_c",
                "name": "Component C",
                "has_traefik_support": False,
                "traefik_internal_port": 80,
            },
        ]
        global_vars = {"TRAEFIK_HOST": "app", "FQDN_SUFFIX": "local"}

        # --- ACT ---
        errors = deployment_manager_setup._validate_traefik_configuration(
            components, global_vars
        )

        # --- ASSERT ---
        assert errors == []

    def test_validate_traefik_configuration_duplicate_port(
        self, deployment_manager_setup: DeploymentManager
    ):
        """
        Tests that _validate_traefik_configuration returns a structured error
        for duplicate internal ports.
        """
        # --- ARRANGE ---
        # Removed redundant 'docker_service_name'
        components: List[Dict[str, Any]] = [
            {
                "id": "comp_a",
                "name": "Component A",
                "has_traefik_support": True,
                "traefik_internal_port": 80,
            },
            {
                "id": "comp_b",
                "name": "Component B",
                "has_traefik_support": True,
                "traefik_internal_port": 80,
            },
        ]
        global_vars = {"TRAEFIK_HOST": "app", "FQDN_SUFFIX": "local"}

        # --- ACT ---
        errors = deployment_manager_setup._validate_traefik_configuration(
            components, global_vars
        )

        # --- ASSERT ---
        assert len(errors) == 1
        (error_report,) = errors
        assert error_report["type"] == "Validation:DuplicatePort"
        assert error_report["component_id"] == "comp_b"
        assert "Duplicate Traefik internal port: 80." in error_report["summary"]

    def test_validate_traefik_configuration_duplicate_hostname(
        self, deployment_manager_setup: DeploymentManager
    ):
        """
        Tests that _validate_traefik_configuration returns a structured error
        for duplicate Traefik-derived hostnames (when component IDs are the same).
        """
        # --- ARRANGE ---
        # Component ID is the source of the hostname, so duplicate ID is the conflict.
        components: List[Dict[str, Any]] = [
            {
                "id": "service-a",
                "name": "Component A",
                "has_traefik_support": True,
                "traefik_internal_port": 80,
            },
            {
                "id": "service-a",  # The conflict is here, same ID as above.
                "name": "Component B",
                "has_traefik_support": True,
                "traefik_internal_port": 81,
            },
        ]
        global_vars = {"TRAEFIK_HOST": "app", "FQDN_SUFFIX": "local"}

        # --- ACT ---
        errors = deployment_manager_setup._validate_traefik_configuration(
            components, global_vars
        )

        # --- ASSERT ---
        # The fix in DeploymentManager ensures only 1 error (DuplicateHostname)
        # is returned, not the extraneous Validation:Missing one.
        assert len(errors) == 1

        (error_report,) = errors
        assert error_report["type"] == "Validation:DuplicateHostname"
        # The second component is the one that triggers the error check
        assert error_report["component_id"] == "service-a"
        assert "service-a.app.local." in error_report["summary"]
