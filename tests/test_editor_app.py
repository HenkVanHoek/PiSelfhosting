import json
import unittest
from unittest.mock import patch

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
            {"id": "comp-a", "name": "A Service", "group": "group_b"},
            {"id": "comp-z", "name": "Z Service", "group": None},
        ]
        self.mock_component_manager.get_piselfhosting_meta.return_value = {
            "default_group": "general",
            "group_order": ["group_b"],
            "components_order": ["comp-a", "comp-c"],
            "group_rules": {
                "group_b": {"name": "Group B"},
                "general": {"name": "General"},
            },
        }

        response = self.client.get("/api/components")
        self.assertEqual(response.status_code, 200)

        response_data = response.json
        self.assertEqual(len(response_data["groups"]), 2)
        self.assertEqual(response_data["groups"][0]["id"], "group_b")
        # Check that components are sorted correctly
        self.assertEqual(response_data["groups"][0]["components"][0]["id"], "comp-a")

    def test_update_component_details_api_success(self):
        """Test updating component details successfully."""
        update_payload = {"name": "New Name", "group": "new_group"}
        response = self.client.put(
            "/api/components/existing-comp",
            data=json.dumps(update_payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.mock_component_manager.update_component_metadata.assert_called_with(
            "existing-comp", update_payload
        )

    def test_update_group_order_success(self):
        """Test the API endpoint for updating the group order."""
        new_order_payload = ["group_b", "general", "group_a"]
        response = self.client.put(
            "/api/groups/order",
            data=json.dumps(new_order_payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {"message": "Group order updated successfully"})
        self.mock_component_manager.update_group_order.assert_called_with(
            new_order_payload
        )

    # --- NEW: Test for the component ordering endpoint ---
    def test_update_components_order_success(self):
        """Test the API endpoint for updating the component order."""
        new_order_payload = ["comp-z", "comp-a", "comp-c"]
        response = self.client.put(
            "/api/components/order",
            data=json.dumps(new_order_payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json, {"message": "Component order updated successfully"}
        )
        self.mock_component_manager.update_components_order.assert_called_with(
            new_order_payload
        )


if __name__ == "__main__":
    unittest.main()
