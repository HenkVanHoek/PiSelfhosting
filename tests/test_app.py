import unittest
from unittest.mock import patch

# Import the factory function from our application
from configurator_app.app import create_app


class AppTestCase(unittest.TestCase):
    """Unit tests for the Flask application using manual patching."""

    def setUp(self):
        """
        Set up the Flask app and test client. This is run before each test.
        """
        # --- THE CRITICAL FIX: Manually start all patches ---
        # We create a patcher for each manager we need to mock.
        self.patcher_scanner = patch('configurator_app.app.PiScanner')
        self.patcher_deployment = patch(
            'configurator_app.app.DeploymentManager')
        self.patcher_component = patch('configurator_app.app.ComponentManager')
        self.patcher_setup = patch('configurator_app.app.SetupManager')

        # Start the patchers and get the mock objects.
        self.mock_pi_scanner = self.patcher_scanner.start()
        self.mock_deployment_manager = self.patcher_deployment.start()
        self.mock_component_manager = self.patcher_component.start()
        self.mock_setup_manager = self.patcher_setup.start()

        # Store mocks for easy access in tests
        self.mocks = {
            "scanner": self.mock_pi_scanner,
            "deployment": self.mock_deployment_manager,
            "component": self.mock_component_manager,
            "setup": self.mock_setup_manager
        }

        # Create the app now that the mocks are firmly in place
        app = create_app()
        app.config.update({"TESTING": True, "WTF_CSRF_ENABLED": False})
        self.client = app.test_client()

    def tearDown(self):
        """
        Clean up by stopping all patches after each test.
        This is crucial to avoid tests interfering with each other.
        """
        self.patcher_scanner.stop()
        self.patcher_deployment.stop()
        self.patcher_component.stop()
        self.patcher_setup.stop()

    def test_index_route(self):
        """Test that the index route returns a 200 OK status."""
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)

    def test_scan_pis_success(self):
        """Test the /scan-pis endpoint with a successful scan."""
        mock_scanner_instance = self.mocks['scanner'].return_value
        mock_scanner_instance.scan.return_value = (["192.168.1.10"], [], None,
                                                   {})

        response = self.client.post('/scan-pis',
                                    json={'subnet': '192.168.1.0/24'})

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data['hosts'], ["192.168.1.10"])

    def test_set_ip_address_success(self):
        """Test setting a target IP address successfully."""
        response = self.client.post('/set-ip', json={'ip': '192.168.1.10'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['message'],
                         "IP address set successfully")

    def test_set_ip_address_no_ip(self):
        """Test the /set-ip endpoint without providing an IP."""
        response = self.client.post('/set-ip', json={})
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.get_json())


if __name__ == '__main__':
    unittest.main()