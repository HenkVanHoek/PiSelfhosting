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

    # START OF FIX: Add tests for the new /api/generate_auth_hash endpoint
    @patch("src.editor_app.app.generate_basic_auth_hash")
    def test_generate_auth_hash_api_success(self, mock_generate_hash):
        """
        Test the API endpoint for hash generation with a successful payload,
        checking the data contract.
        """
        mock_generated_string = "testuser:$2a$12$ABCDEFGHIJ.K/LMNOPQR.STUV.WXYZ0123"
        mock_generate_hash.return_value = mock_generated_string

        payload = {"username": "testuser", "password": "SecurePassword123"}

        response = self.client.post(
            "/api/generate_auth_hash",
            data=json.dumps(payload),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("hashed_user_string", response.json)
        self.assertEqual(response.json["hashed_user_string"], mock_generated_string)

        # Verify the utility function was called with the correct arguments
        mock_generate_hash.assert_called_once_with(
            payload["username"], payload["password"]
        )

    def test_generate_auth_hash_api_missing_data(self):
        """
        Test the API endpoint for hash generation when required data is missing.
        """
        # Case 1: Missing username
        response_missing_user = self.client.post(
            "/api/generate_auth_hash",
            data=json.dumps({"password": "p"}),
            content_type="application/json",
        )
        self.assertEqual(response_missing_user.status_code, 400)
        self.assertIn(
            "Username and password are required", response_missing_user.json["error"]
        )

        # Case 2: Missing password
        response_missing_pass = self.client.post(
            "/api/generate_auth_hash",
            data=json.dumps({"username": "u"}),
            content_type="application/json",
        )
        self.assertEqual(response_missing_pass.status_code, 400)
        self.assertIn(
            "Username and password are required", response_missing_pass.json["error"]
        )

    # END OF FIX: Add tests for the new /api/generate_auth_hash endpoint

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

    def test_rename_group_success(self):
        """Test the API endpoint for renaming a group successfully."""
        payload = {"name": "New Group Name"}
        response = self.client.put(
            "/api/groups/old-group-name/rename",
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.mock_component_manager.rename_group.assert_called_with(
            "old-group-name", "New Group Name"
        )
        self.assertIn("message", response.json)
        self.assertIn("renamed to 'New Group Name'", response.json["message"])

    def test_rename_group_missing_name(self):
        """Test renaming a group with a missing 'name' in the payload."""
        payload = {"wrong_key": "some value"}
        response = self.client.put(
            "/api/groups/a-group/rename",
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.json)
        self.assertIn("New name is required", response.json["error"])
        self.mock_component_manager.rename_group.assert_not_called()

    def test_rename_group_manager_error(self):
        """Test renaming a group when the manager raises a ValueError."""
        self.mock_component_manager.rename_group.side_effect = ValueError(
            "Group does not exist"
        )
        payload = {"name": "Any Name"}
        response = self.client.put(
            "/api/groups/non-existent-group/rename",
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.json)
        self.assertEqual(response.json["error"], "Group does not exist")

    def test_update_component_variables_with_required_field(self):
        """
        Test that the 'required' field is correctly processed when updating
        variables. An empty 'required' value should be omitted.
        """
        payload = {
            "variables": [
                {"id": "VAR1", "required": "always"},
                {"id": "VAR2", "required": ""},
                {"id": "VAR3"},
            ]
        }
        # START OF FIX:
        # The expected payload was corrected to match the actual, correct
        # behavior of the application, which is to remove the empty 'required'
        # key but keep the variable itself.
        expected_call_payload = {
            "variables": [
                {"id": "VAR1", "required": "always"},
                {"id": "VAR2"},
                {"id": "VAR3"},
            ]
        }
        # END OF FIX:

        response = self.client.put(
            "/api/components/some-comp/variables",
            data=json.dumps(payload),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.mock_component_manager.update_component_variables.assert_called_once_with(
            "some-comp", expected_call_payload
        )


if __name__ == "__main__":
    unittest.main()
