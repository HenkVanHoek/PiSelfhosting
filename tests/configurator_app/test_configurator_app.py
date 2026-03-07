# tests/configurator_app/test_configurator_app.py
import json
import unittest
from unittest.mock import patch

from src.configurator_app.app import create_app


class ConfiguratorAppTestCase(unittest.TestCase):
    def setUp(self):
        """Set up test client and mock new CQRS managers."""
        # Patching the new managers and the scanner
        self.patcher_reader = patch("src.configurator_app.app.ComponentReader")
        self.patcher_generator = patch("src.configurator_app.app.ArtifactGenerator")
        self.patcher_scanner = patch("src.configurator_app.app.PiScanner")
        self.patcher_deploy = patch("src.configurator_app.app.DeploymentManager")

        self.mock_reader_class = self.patcher_reader.start()
        self.mock_generator_class = self.patcher_generator.start()
        self.mock_scanner_class = self.patcher_scanner.start()
        self.mock_deploy_class = self.patcher_deploy.start()

        # Instances used by the app
        self.mock_reader = self.mock_reader_class.return_value
        self.mock_generator = self.mock_generator_class.return_value
        self.mock_scanner = self.mock_scanner_class.return_value
        self.mock_deploy = self.mock_deploy_class.return_value

        # Initialize App
        self.app = create_app({"TESTING": True, "SECRET_KEY": "test-key"})
        self.client = self.app.test_client()

    def tearDown(self):
        self.patcher_reader.stop()
        self.patcher_generator.stop()
        self.patcher_scanner.stop()
        self.patcher_deploy.stop()

    def test_get_components_api(self):
        """Test the GET /api/components endpoint."""
        self.mock_reader.get_all_components.return_value = {
            "pihole": {"name": "Pi-hole"}
        }
        response = self.client.get("/api/components")
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn("pihole", data)

    def test_scan_pis_success(self):
        """Test the network scanning endpoint."""
        self.mock_scanner.scan.return_value = [{"ip": "192.168.1.50", "hostname": "pi"}]
        response = self.client.get("/scan-pis")
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(len(data["hosts"]), 1)
        self.assertEqual(data["hosts"][0]["ip"], "192.168.1.50")

    def test_deploy_configuration_success(self):
        """Test POST /deploy-configuration without conflicts."""
        payload = {
            "selected_components": ["nginx"],
            "global_vars": {"domain": "home.lan"},
            "analysis_results": {"external_conflicts": {"ports": []}},
        }
        self.mock_generator.create_artifacts.return_value = True

        response = self.client.post(
            "/deploy-configuration",
            data=json.dumps(payload),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 202)
        data = json.loads(response.data)
        self.assertIn("task_id", data)
        self.mock_generator.create_artifacts.assert_called_once()

    def test_deploy_blocks_on_critical_conflict(self):
        """Test that deployment stops if a port conflict is detected."""
        payload = {
            "analysis_results": {
                "external_conflicts": {
                    "ports": [
                        {
                            "port": 80,
                            "conflict_type": "DANGEROUS_NATIVE_PROCESS_CONFLICT",
                            "proposed_service": "Nginx",
                        }
                    ]
                }
            }
        }

        response = self.client.post(
            "/deploy-configuration",
            data=json.dumps(payload),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        data = json.loads(response.data)
        self.assertIn("Critical conflicts", data["message"])
