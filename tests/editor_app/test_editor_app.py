import json
import unittest
from unittest.mock import MagicMock, patch

from src.editor_app import create_app


class EditorAppTestCase(unittest.TestCase):
    def setUp(self):
        """Set up a test client and mock the component manager."""
        self.patcher = patch("src.editor_app.ComponentManager")
        mock_component_manager_class = self.patcher.start()
        self.mock_component_manager = mock_component_manager_class.return_value

        self.app = create_app()
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()
        self.app.config["COMPONENT_MANAGER"] = self.mock_component_manager

    def tearDown(self):
        """Stop the patcher after each test."""
        self.patcher.stop()

    def test_index_route(self):
        """Test that the main editor page loads correctly."""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"PiSelfhosting Component Editor", response.data)

    def test_get_components_api(self):
        """Test the API endpoint for getting grouped and sorted components."""
        self.mock_component_manager.get_all_components.return_value = [
            {"id": "comp-c", "name": "C Service", "group": "group_b"},
            {"id": "comp-z", "name": "Z Service", "group": None},
        ]
        self.mock_component_manager.get_piselfhosting_meta.return_value = {
            "default_group": "general",
            "group_order": ["group_b"],
            "components_order": [],
            "group_rules": {
                "group_b": {"name": "Group B"},
                "general": {"name": "General"},
            },
        }
        response = self.client.get("/api/components")
        self.assertEqual(response.status_code, 200)
        response_data = response.json
        self.assertEqual(len(response_data["groups"]), 2)

    def test_validate_component_configuration_success(self):
        """Test the component validation endpoint with a valid payload."""
        payload = {
            "template_content": "services: {}",
            "variables": [{"id": "VAR1"}],
        }
        self.mock_component_manager.validate_component_configuration = MagicMock()

        response = self.client.post(
            "/api/components/some-component/validate",
            data=json.dumps(payload),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Validation successful", response.json["message"])
        self.mock_component_manager.validate_component_configuration.assert_called_with(
            "some-component", "services: {}", [{"id": "VAR1"}]
        )

    def test_validate_component_configuration_failure(self):
        """Test validation endpoint when component manager raises ValueError."""
        self.mock_component_manager.validate_component_configuration.side_effect = (
            ValueError("Missing required variable: FOO")
        )
        payload = {"template_content": "...", "variables": []}

        response = self.client.post(
            "/api/components/some-component/validate",
            data=json.dumps(payload),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Validation Failed", response.json["error"])
        self.assertIn("Missing required variable: FOO", response.json["error"])

    def test_validate_component_configuration_bad_payload(self):
        """Test validation endpoint with a missing or invalid JSON payload."""
        response = self.client.post(
            "/api/components/some-component/validate",
            data="this is not json",
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Invalid or missing JSON payload", response.json["error"])

    def test_update_group_order_success(self):
        """Test the API endpoint for updating the group order."""
        new_order_payload = ["group_b", "general", "group_a"]
        response = self.client.put(
            "/api/groups/order",
            data=json.dumps(new_order_payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.mock_component_manager.update_group_order.assert_called_with(
            new_order_payload
        )

    def test_create_component_success(self):
        """Test the API endpoint for creating a new component."""
        payload = {"id": "new-component", "name": "New Component"}
        response = self.client.post(
            "/api/components",
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        self.mock_component_manager.create_component.assert_called_with(
            "new-component", "New Component"
        )

    def test_update_component_group_success(self):
        """Test the API endpoint for moving a component to a new group."""
        payload = {"group": "new-group-id"}
        response = self.client.put(
            "/api/components/comp-a/group",
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.mock_component_manager.update_component_group.assert_called_with(
            "comp-a", "new-group-id"
        )

    def test_delete_group_success(self):
        """Test the API endpoint for deleting an unused group."""
        response = self.client.delete("/api/groups/old-group")
        self.assertEqual(response.status_code, 200)
        self.mock_component_manager.delete_group.assert_called_with("old-group")
        self.assertIn("message", response.json)


if __name__ == "__main__":
    unittest.main()
