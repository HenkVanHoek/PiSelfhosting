import json
import unittest
from unittest.mock import patch

from src.editor_app import create_app


class EditorAppTestCase(unittest.TestCase):
    def setUp(self):
        """Set up a test client and mock the component manager."""
        self.patcher = patch("src.editor_app.ComponentManager")
        # --- FIX: Renamed variable to lowercase to satisfy the linter ---
        mock_component_manager_class = self.patcher.start()
        self.mock_component_manager = mock_component_manager_class.return_value

        # Now, when create_app is called, it will use the mock
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

        # Ensure the app config uses the same mock instance.
        self.app.config["COMPONENT_MANAGER"] = self.mock_component_manager

    def tearDown(self):
        """Stop the patcher after each test."""
        self.patcher.stop()

    def test_index_route(self):
        """Test that the main editor page loads correctly."""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"PiSelfhosting Component Editor", response.data)

    def test_get_components_api_with_groups(self):
        """Test the API endpoint for getting grouped and sorted components."""
        mock_data = [
            {"id": "comp-c", "name": "C Service", "uniqueness_group": "group_b"},
            {"id": "comp-a", "name": "A Service", "uniqueness_group": "group_b"},
            {"id": "comp-z", "name": "Z Service"},
            {"id": "comp-d", "name": "D Service", "uniqueness_group": "group_a"},
        ]
        self.mock_component_manager.get_all_components.return_value = mock_data

        response = self.client.get("/api/components")
        self.assertEqual(response.status_code, 200)

        expected_json = {
            "groups": [
                {
                    "name": "group_a",
                    "components": [{"id": "comp-d", "name": "D Service"}],
                },
                {
                    "name": "group_b",
                    "components": [
                        {"id": "comp-a", "name": "A Service"},
                        {"id": "comp-c", "name": "C Service"},
                    ],
                },
            ],
            "ungrouped": [{"id": "comp-z", "name": "Z Service"}],
        }
        self.assertEqual(response.json, expected_json)

    def test_get_component_details_api_found(self):
        """Test getting details for an existing component."""
        mock_details = {"name": "Test Component", "description": "A test description"}
        self.mock_component_manager.get_component_details.return_value = mock_details

        response = self.client.get("/api/components/test-comp")
        self.assertEqual(response.status_code, 200)
        expected_data = mock_details.copy()
        expected_data["id"] = "test-comp"
        self.assertEqual(response.json, expected_data)

    def test_get_component_details_api_not_found(self):
        """Test getting details for a non-existent component."""
        self.mock_component_manager.get_component_details.return_value = None
        response = self.client.get("/api/components/not-found")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json, {"error": "Component not found"})

    def test_update_component_details_api_success(self):
        """Test updating component details successfully."""
        update_payload = {"name": "New Name", "description": "New Description"}
        response = self.client.put(
            "/api/components/existing-comp",
            data=json.dumps(update_payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {"message": "Component updated successfully"})
        self.mock_component_manager.update_component_metadata.assert_called_with(
            "existing-comp", update_payload
        )

    def test_update_component_variables_success(self):
        """Test the API for updating component variables successfully."""
        payload = {"variables": [{"id": "VAR1", "value": "test"}]}
        response = self.client.put(
            "/api/components/test-comp/variables",
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {"message": "Variables updated successfully"})
        self.mock_component_manager.update_component_variables.assert_called_with(
            "test-comp", payload
        )

    def test_get_component_template_success(self):
        """Test the API for getting a component template."""
        mock_content = "version: '3.8'\nservices:\n  myservice:\n    image: test"
        self.mock_component_manager.get_component_template_content.return_value = (
            mock_content
        )
        response = self.client.get("/api/components/test-comp/template")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.decode("utf-8"), mock_content)
        self.assertEqual(response.mimetype, "text/plain")

    def test_update_component_template_success(self):
        """Test the API for updating a component template."""
        new_content = "version: '3.9'\nservices:\n  newservice:\n    image: new"
        response = self.client.put(
            "/api/components/test-comp/template",
            data=new_content,
            content_type="text/plain",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {"message": "Template updated successfully"})

        mock_update_method = (
            self.mock_component_manager.update_component_template_content
        )
        mock_update_method.assert_called_with("test-comp", new_content)


if __name__ == "__main__":
    unittest.main()
