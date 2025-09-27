import unittest
from unittest.mock import patch

from configurator_app.app import create_app


class AppTestCase(unittest.TestCase):
    """Base test case for the Flask application."""

    def setUp(self):
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

        app = create_app()
        app.config.update({"TESTING": True, "WTF_CSRF_ENABLED": False})
        self.client = app.test_client()

    def tearDown(self):
        self.patcher_scanner.stop()
        self.patcher_deployment.stop()
        self.patcher_component.stop()
        self.patcher_setup.stop()

    def test_index_route(self):
        """Test that the index route returns a 200 OK status."""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)


# START OF REFACTOR:
# New test class dedicated to the system analyzer endpoint.
# Old tests for removed endpoints are deleted.


class SystemAnalyzerTestCase(AppTestCase):
    """Test suite for the /api/v1/system/analyze endpoint."""

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

if __name__ == "__main__":
    unittest.main()
