import unittest
from unittest.mock import MagicMock, patch

from configurator_app.app import create_app


class AppTestCase(unittest.TestCase):
    """Base test case for the Flask application."""

    def setUp(self):
        # 1. Setup the datetime mock first, explicitly chaining the mocks.
        mock_now_return = MagicMock()
        mock_now_return.strftime.return_value = "2025-01-01 12:00:00"

        self.patcher_datetime = patch("configurator_app.app.datetime")
        self.mock_datetime = self.patcher_datetime.start()
        # Ensure the mocked datetime.now() returns the mock object with strftime
        self.mock_datetime.now.return_value = mock_now_return

        self.patcher_scanner = patch("configurator_app.app.PiScanner")
        self.patcher_deployment = patch("configurator_app.app.DeploymentManager")
        self.patcher_component = patch("configurator_app.app.ComponentManager")
        self.patcher_setup = patch("configurator_app.app.SetupManager")

        self.mock_pi_scanner = self.patcher_scanner.start()
        self.mock_deployment_manager = self.patcher_deployment.start()
        self.mock_component_manager = self.patcher_component.start()
        self.mock_setup_manager = self.patcher_setup.start()

        self.mocks = {
            "scanner": self.mock_pi_scanner,
            "deployment": self.mock_deployment_manager,
            "component": self.mock_component_manager,
            "setup": self.mock_setup_manager,
        }

        # The Flask app instance is created here
        app = create_app()
        app.config.update({"TESTING": True, "WTF_CSRF_ENABLED": False})
        self.client = app.test_client()
        # Store the application instance itself for direct access to helper funcs/data
        self.app_instance = app

    def tearDown(self):
        self.patcher_scanner.stop()
        self.patcher_deployment.stop()
        self.patcher_component.stop()
        self.patcher_setup.stop()
        self.patcher_datetime.stop()

    def test_index_route(self):
        """Test that the index route returns a 200 OK status."""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)


# START OF REFACTOR:
# New test class dedicated to the system analyzer endpoint.
# Old tests for removed endpoints are deleted.


class SystemAnalyzerTestCase(AppTestCase):
    """Test suite for the /api/v1/system/analyze endpoint."""

    # ... (All existing tests for SystemAnalyzerTestCase remain the same)

    def test_system_analyze_no_conflicts(self):
        """Test a clean run with no internal or external conflicts."""
        mock_scanner_instance = self.mocks["scanner"].return_value
        mock_scanner_instance.get_system_snapshot.return_value = (
            {
                "docker_is_active": True,
                "containers": [],
                "native_processes": [{"port": 22, "process_name": "sshd"}],
                "resources": {"ram": {"total_mb": 4096, "used_mb": 1024}},
            },
            None,
        )
        request_body = {
            "devices": [{"ip": "192.168.1.10", "username": "pi", "password": "pi"}],
            "components": [
                {"name": "portainer", "ports": ["9000:9000/tcp"], "volumes": []}
            ],
        }
        response = self.client.post("/api/v1/system/analyze", json=request_body)
        data = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["status"], "success")
        self.assertEqual(len(data["external_conflicts"]["ports"]), 0)
        self.assertEqual(len(data["resource_warnings"]), 0)

    def test_system_analyze_internal_port_conflict(self):
        """Test that a 400 error is returned for internal port conflicts."""
        request_body = {
            "devices": [{"ip": "192.168.1.10", "username": "pi", "password": "pi"}],
            "components": [
                {"name": "portainer", "ports": ["9000:9000/tcp"]},
                {"name": "pihole", "ports": ["9000:9000/tcp"]},
            ],
        }
        response = self.client.post("/api/v1/system/analyze", json=request_body)
        self.assertEqual(response.status_code, 400)
        self.assertIn("internal_conflicts", response.get_json())

    def test_system_analyze_dangerous_native_conflict(self):
        """Test detection of a conflict with a native system process."""
        mock_scanner_instance = self.mocks["scanner"].return_value
        mock_scanner_instance.get_system_snapshot.return_value = (
            {"native_processes": [{"port": 80, "process_name": "apache2"}]},
            None,
        )
        request_body = {
            "devices": [{"ip": "192.168.1.10", "username": "pi", "password": "pi"}],
            "components": [{"name": "pihole", "ports": ["80:80/tcp"]}],
        }
        response = self.client.post("/api/v1/system/analyze", json=request_body)
        data = response.get_json()
        self.assertEqual(len(data["external_conflicts"]["ports"]), 1)
        conflict = data["external_conflicts"]["ports"][0]
        self.assertEqual(conflict["port"], 80)
        self.assertEqual(conflict["conflict_type"], "DANGEROUS_NATIVE_PROCESS_CONFLICT")

    def test_system_analyze_expected_reinstallation(self):
        """Test correct identification of an expected reinstallation."""
        mock_scanner_instance = self.mocks["scanner"].return_value
        mock_scanner_instance.get_system_snapshot.return_value = (
            {"containers": [{"name": "portainer", "ports": "0.0.0.0:9000->9000/tcp"}]},
            None,
        )
        request_body = {
            "devices": [{"ip": "192.168.1.10", "username": "pi", "password": "pi"}],
            "components": [{"name": "portainer", "ports": ["9000:9000/tcp"]}],
            "is_reinstallation": True,
        }
        response = self.client.post("/api/v1/system/analyze", json=request_body)
        data = response.get_json()
        self.assertEqual(len(data["external_conflicts"]["ports"]), 1)
        conflict = data["external_conflicts"]["ports"][0]
        self.assertEqual(conflict["conflict_type"], "EXPECTED_REINSTALLATION")

    def test_system_analyze_unexpected_docker_conflict(self):
        """Test detection of a conflict with an unrelated Docker container."""
        mock_scanner_instance = self.mocks["scanner"].return_value
        mock_scanner_instance.get_system_snapshot.return_value = (
            {"containers": [{"name": "pihole", "ports": "0.0.0.0:80->80/tcp"}]},
            None,
        )
        request_body = {
            "devices": [{"ip": "192.168.1.10", "username": "pi", "password": "pi"}],
            "components": [{"name": "nginx", "ports": ["80:80/tcp"]}],
            "is_reinstallation": True,
        }
        response = self.client.post("/api/v1/system/analyze", json=request_body)
        data = response.get_json()
        self.assertEqual(len(data["external_conflicts"]["ports"]), 1)
        conflict = data["external_conflicts"]["ports"][0]
        self.assertEqual(conflict["conflict_type"], "UNEXPECTED_DOCKER_CONFLICT")

    def test_system_analyze_resource_warning(self):
        """Test that a resource warning is generated for high RAM usage."""
        mock_scanner_instance = self.mocks["scanner"].return_value
        mock_scanner_instance.get_system_snapshot.return_value = (
            {"resources": {"ram": {"total_mb": 1000, "used_mb": 950}}},
            None,
        )
        request_body = {
            "devices": [{"ip": "192.168.1.10", "username": "pi", "password": "pi"}],
            "components": [{"name": "portainer", "ports": ["9000:9000/tcp"]}],
        }
        response = self.client.post("/api/v1/system/analyze", json=request_body)
        data = response.get_json()
        self.assertEqual(len(data["resource_warnings"]), 1)
        self.assertEqual(data["resource_warnings"][0]["type"], "RAM")

    def test_system_analyze_snapshot_fails(self):
        """Test that a 500 error is returned if the snapshot fails."""
        mock_scanner_instance = self.mocks["scanner"].return_value
        mock_scanner_instance.get_system_snapshot.return_value = (
            None,
            "SSH connection failed.",
        )
        request_body = {
            "devices": [{"ip": "192.168.1.10", "username": "pi", "password": "pi"}],
            "components": [{"name": "portainer"}],
        }
        response = self.client.post("/api/v1/system/analyze", json=request_body)
        self.assertEqual(response.status_code, 500)
        self.assertIn("Failed to get system snapshot", response.get_json()["error"])


# END OF REFACTOR


# START OF NEW TEST CLASS
class DeploymentGatekeeperTestCase(AppTestCase):
    """Test suite for the /deploy-configuration gatekeeping logic."""

    MOCK_DEVICE = {"ip": "192.168.1.10", "username": "pi", "password": "pi"}
    MOCK_OUTPUT_PATH = "/tmp/piselfhosting_output"

    def _get_base_request_body(self, analysis_results):
        return {
            "output_path": self.MOCK_OUTPUT_PATH,
            "devices": [self.MOCK_DEVICE],
            "analysis_results": analysis_results,
        }

    # FIX: Removed @patch("threading.Thread") and @patch.object(...)
    def test_deploy_configuration_success_no_conflicts(self):
        """Test deployment proceeds when there are no conflicts (empty list)."""
        # Patch the specific attribute that the route calls
        with patch.object(
            self.app_instance, "_map_analysis_to_report_errors", return_value=[]
        ):
            request_body = self._get_base_request_body(
                {"external_conflicts": {"ports": [], "volumes": []}}
            )

            response = self.client.post("/deploy-configuration", json=request_body)
            data = response.get_json()

            self.assertEqual(response.status_code, 202)
            self.assertIn("task_id", data)
            self.mocks["deployment"].return_value.start_deployment.assert_called_once()

    # FIX: Removed @patch("threading.Thread")
    def test_deploy_configuration_blocks_on_dangerous_native_conflict(self):
        """Test deployment is blocked by DANGEROUS_NATIVE_PROCESS_CONFLICT."""
        blocking_error = {
            "type": "Validation:PortConflict:DANGEROUS_NATIVE_PROCESS_CONFLICT",
            "summary": "Host port 80 conflict detected.",
            "details": "Port 80 is already in use by: 'apache2'.",
            "component_id": "pi-hole",
            "timestamp": "2025-01-01 12:00:00",
        }

        # Patch the specific attribute that the route calls
        with patch.object(
            self.app_instance,
            "_map_analysis_to_report_errors",
            return_value=[blocking_error],
        ):
            request_body = self._get_base_request_body(
                {"external_conflicts": {"ports": [{}], "volumes": []}}
            )

            response = self.client.post("/deploy-configuration", json=request_body)
            data = response.get_json()

            self.assertEqual(response.status_code, 400)
            self.assertIn("errors", data)
            self.assertEqual(len(data["errors"]), 1)
            self.assertEqual(data["errors"][0]["type"], blocking_error["type"])
            self.mocks["deployment"].return_value.start_deployment.assert_not_called()

    # FIX: Removed @patch("threading.Thread")
    def test_deploy_configuration_blocks_on_unexpected_docker_conflict(self):
        """Test deployment is blocked by UNEXPECTED_DOCKER_CONFLICT."""
        blocking_error = {
            "type": "Validation:PortConflict:UNEXPECTED_DOCKER_CONFLICT",
            "summary": "Host port 80 conflict detected.",
            "details": "Port 80 is already in use by: 'docker container (old-nginx)'.",
            "component_id": "new-nginx",
            "timestamp": "2025-01-01 12:00:00",
        }

        # Patch the specific attribute that the route calls
        with patch.object(
            self.app_instance,
            "_map_analysis_to_report_errors",
            return_value=[blocking_error],
        ):
            request_body = self._get_base_request_body(
                {"external_conflicts": {"ports": [{}], "volumes": []}}
            )

            response = self.client.post("/deploy-configuration", json=request_body)
            self.assertEqual(response.status_code, 400)
            self.mocks["deployment"].return_value.start_deployment.assert_not_called()

    # FIX: Removed @patch("threading.Thread")
    def test_deploy_configuration_proceeds_with_resource_warning(self):
        """Test deployment proceeds when only a resource warning is present."""
        expected_log_substring = "WARNING/INFO: Resource warning detected: RAM"
        non_blocking_error = {
            "type": "Warning:Resource:RAM",
            "summary": "Resource warning detected: RAM",
            "details": "RAM is over 90% used.",
            "component_id": "N/A",
            "timestamp": "2025-01-01 12:00:00",
        }

        # Patch the specific attribute that the route calls
        with patch.object(
            self.app_instance,
            "_map_analysis_to_report_errors",
            return_value=[non_blocking_error],
        ):
            request_body = self._get_base_request_body(
                {"external_conflicts": {"ports": [], "volumes": []}}
            )

            response = self.client.post("/deploy-configuration", json=request_body)
            data = response.get_json()

            self.assertEqual(response.status_code, 202)
            # FIX: assert_called_once() will now correctly pass
            self.mocks["deployment"].return_value.start_deployment.assert_called_once()

            # Verify the warning is added to the task's initial logs and errors
            task_id = data["task_id"]

            # Access the attached deployment_tasks dict
            task = self.app_instance.deployment_tasks.get(task_id)

            # Assert that the expected log is in the list of logs
            self.assertTrue(
                any(expected_log_substring in log for log in task["logs"]),
                f"Expected log '{expected_log_substring}' "
                f"not found in task logs: {task['logs']}",
            )
            self.assertEqual(len(task["errors"]), 1)
            self.assertEqual(task["errors"][0]["type"], non_blocking_error["type"])

    # FIX: Removed @patch("threading.Thread")
    def test_deploy_configuration_proceeds_with_expected_reinstallation(self):
        """Test deployment proceeds when only an expected
        reinstallation warning is present."""
        non_blocking_error = {
            "type": "Validation:PortConflict:EXPECTED_REINSTALLATION",
            "summary": "Port 9000 is already in use by portainer.",
            "details": "The conflict is with the same service and "
            "reinstallation is expected.",
            "component_id": "portainer",
            "timestamp": "2025-01-01 12:00:00",
        }

        # Patch the specific attribute that the route calls
        with patch.object(
            self.app_instance,
            "_map_analysis_to_report_errors",
            return_value=[non_blocking_error],
        ):
            request_body = self._get_base_request_body(
                {"external_conflicts": {"ports": [{}], "volumes": []}}
            )

            response = self.client.post("/deploy-configuration", json=request_body)
            self.assertEqual(response.status_code, 202)
            self.mocks["deployment"].return_value.start_deployment.assert_called_once()

    # Test the helper function _map_analysis_to_report_errors directly
    def test_map_analysis_to_report_errors_port_conflict(self):
        """Test mapping of a port conflict (native process)."""
        analysis_results = {
            "external_conflicts": {
                "ports": [
                    {
                        "port": 80,
                        "conflict_type": "DANGEROUS_NATIVE_PROCESS_CONFLICT",
                        "conflicting_service": "apache2",
                        "proposed_service": "Pi-hole",
                    }
                ],
                "volumes": [],
            },
            "resource_warnings": [],
        }
        # Access the helper function via the app instance created in setUp
        errors = self.app_instance._map_analysis_to_report_errors(
            analysis_results, self.MOCK_DEVICE["ip"]
        )

        (first_error,) = errors  # Unpack-First Mandate
        self.assertEqual(len(errors), 1)
        self.assertEqual(
            first_error["type"],
            "Validation:PortConflict:DANGEROUS_NATIVE_PROCESS_CONFLICT",
        )
        self.assertIn("Host port 80 conflict detected.", first_error["summary"])
        self.assertIn("Port 80 is already in use by: 'apache2'", first_error["details"])
        self.assertEqual(first_error["component_id"], "pi-hole")
        self.assertEqual(first_error["timestamp"], "2025-01-01 12:00:00")

    def test_map_analysis_to_report_errors_volume_conflict(self):
        """Test mapping of a volume conflict."""
        analysis_results = {
            "external_conflicts": {
                "ports": [],
                "volumes": [
                    {
                        "volume_path": "/mnt/data",
                        "conflict_type": "EXISTING_VOLUME_CONFLICT",
                        "proposed_service": "Nextcloud",
                    }
                ],
            },
            "resource_warnings": [],
        }
        # Access the helper function via the app instance created in setUp
        errors = self.app_instance._map_analysis_to_report_errors(
            analysis_results, self.MOCK_DEVICE["ip"]
        )

        (first_error,) = errors  # Unpack-First Mandate
        self.assertEqual(len(errors), 1)
        self.assertEqual(
            first_error["type"], "Validation:VolumeConflict:EXISTING_VOLUME_CONFLICT"
        )
        self.assertIn(
            "Host volume path conflict detected at '/mnt/data'", first_error["summary"]
        )
        self.assertIn("The path '/mnt/data' already exists", first_error["details"])
        self.assertEqual(first_error["component_id"], "nextcloud")
        self.assertEqual(first_error["timestamp"], "2025-01-01 12:00:00")

    def test_map_analysis_to_report_errors_resource_warning(self):
        """Test mapping of a resource warning."""
        analysis_results = {
            "external_conflicts": {"ports": [], "volumes": []},
            "resource_warnings": [
                {
                    "type": "RAM",
                    "message": "The target system is using over 90% of its RAM.",
                }
            ],
        }
        # Access the helper function via the app instance created in setUp
        errors = self.app_instance._map_analysis_to_report_errors(
            analysis_results, self.MOCK_DEVICE["ip"]
        )

        (first_error,) = errors  # Unpack-First Mandate
        self.assertEqual(len(errors), 1)
        self.assertEqual(first_error["type"], "Warning:Resource:RAM")
        self.assertIn("Resource warning detected: RAM", first_error["summary"])
        self.assertIn(
            "The resource analysis on 192.168.1.10 generated a warning",
            first_error["details"],
        )
        self.assertEqual(first_error["component_id"], "N/A")
        self.assertEqual(first_error["timestamp"], "2025-01-01 12:00:00")


# END OF NEW TEST CLASS


if __name__ == "__main__":
    unittest.main()
