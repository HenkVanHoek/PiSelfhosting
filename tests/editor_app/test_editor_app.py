import json
import unittest
from unittest.mock import MagicMock, patch

from src.editor_app import create_app


class EditorAppTestCase(unittest.TestCase):
    def setUp(self):
        """Set up a test client and mock the component manager."""
        # FIX: Patch the ComponentManager in its source
        # module (src.managers.component_manager)
        # to circumvent the AttributeError caused by the old patch path.
        self.patcher = patch("src.managers.component_manager.ComponentManager")
        mock_component_manager_class = self.patcher.start()
        self.mock_component_manager = mock_component_manager_class.return_value

        self.app = create_app()
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()
        self.app.config["COMPONENT_MANAGER"] = self.mock_component_manager

    def tearDown(self):
        """Stop the patcher after each test."""
        self.patcher.stop()

    def _post_json(self, url, payload):
        """Helper for standard JSON POST requests."""
        return self.client.post(
            url,
            data=json.dumps(payload),
            content_type="application/json",
        )

    def _put_json(self, url, payload):
        """Helper for standard JSON PUT requests."""
        return self.client.put(
            url,
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_index_route(self):
        """Test that the main editor page loads correctly."""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"PiSelfhosting Component Editor", response.data)

    @patch("src.editor_app.app.generate_basic_auth_hash")
    def test_generate_auth_hash_api_success(self, mock_generate_hash):
        """
        Test the API endpoint for hash generation with a successful payload,
        checking the data contract.
        """
        mock_generated_string = "testuser:$2a$12$ABCDEFGHIJ.K/LMNOPQR.STUV.WXYZ0123"
        mock_generate_hash.return_value = mock_generated_string

        payload = {"username": "testuser", "password": "SecurePassword123"}

        response = self._post_json("/api/generate_auth_hash", payload)

        self.assertEqual(response.status_code, 200)
        self.assertIn("hashed_user_string", response.json)
        self.assertEqual(response.json["hashed_user_string"], mock_generated_string)

        mock_generate_hash.assert_called_once_with(
            payload["username"], payload["password"]
        )

    def test_generate_auth_hash_api_missing_data(self):
        """
        Test the API endpoint for hash generation when required data is missing.
        """
        # Case 1: Missing username
        response_missing_user = self._post_json(
            "/api/generate_auth_hash", {"password": "p"}
        )
        self.assertEqual(response_missing_user.status_code, 400)
        self.assertIn(
            "Username and password are required", response_missing_user.json["error"]
        )

        # Case 2: Missing password
        response_missing_pass = self._post_json(
            "/api/generate_auth_hash", {"username": "u"}
        )
        self.assertEqual(response_missing_pass.status_code, 400)
        self.assertIn(
            "Username and password are required", response_missing_pass.json["error"]
        )

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

        response = self._post_json("/api/components/some-component/validate", payload)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Validation successful", response.json["message"])
        self.mock_component_manager.validate_component_configuration.assert_called_with(
            "some-component",
            "services: {}",
            [{"id": "VAR1"}],
        )

    def test_validate_component_configuration_failure(self):
        """Test validation endpoint when component manager raises ValueError."""
        self.mock_component_manager.validate_component_configuration.side_effect = (
            ValueError("Missing required variable: FOO")
        )
        payload = {"template_content": "...", "variables": []}

        response = self._post_json("/api/components/some-component/validate", payload)

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

    # START OF NEW FEATURE: Metadata Conflict Validation API Tests (TDD Red)

    def test_validate_metadata_conflicts_success(self):
        """
        Test the conflict validation endpoint with a valid payload, ensuring
        a 200 response and manager call.
        """
        component_id = "comp-a"
        conflicts_list = ["comp-b", "comp-c"]
        payload = {"conflicts_with": conflicts_list}
        self.mock_component_manager.validate_metadata_conflicts = MagicMock()

        response = self._post_json(
            f"/api/components/{component_id}/validate_metadata_conflicts", payload
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("successful", response.json["message"])
        self.mock_component_manager.validate_metadata_conflicts.assert_called_with(
            component_id, conflicts_list
        )

    def test_validate_metadata_conflicts_manager_valueerror(self):
        """
        Test the conflict validation endpoint when the manager raises a
        ValueError (e.g., for self-conflict or non-existent ID).
        """
        component_id = "comp-a"
        error_message = (
            "Self-Conflict Error: " "Component 'comp-a' cannot conflict with itself."
        )
        self.mock_component_manager.validate_metadata_conflicts.side_effect = (
            ValueError(error_message)
        )
        payload = {"conflicts_with": ["comp-a", "comp-b"]}

        response = self._post_json(
            f"/api/components/{component_id}/validate_metadata_conflicts", payload
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.json)
        self.assertEqual(response.json["error"], error_message)

    def test_validate_metadata_conflicts_bad_payload(self):
        """
        Test the conflict validation endpoint with missing or invalid payload
        data, including a non-list 'conflicts_with'.
        """
        component_id = "comp-a"
        # Case 1: Invalid JSON
        response_bad_json = self.client.post(
            f"/api/components/{component_id}/validate_metadata_conflicts",
            data="not json",
            content_type="application/json",
        )
        self.assertEqual(response_bad_json.status_code, 400)
        self.assertIn(
            "Invalid or missing JSON payload", response_bad_json.json["error"]
        )

        # Case 2: 'conflicts_with' is not a list
        response_bad_list = self._post_json(
            f"/api/components/{component_id}/validate_metadata_conflicts",
            {"conflicts_with": "comp-b"},
        )
        self.assertEqual(response_bad_list.status_code, 400)
        self.assertIn(
            "Payload 'conflicts_with' must be a list.", response_bad_list.json["error"]
        )
        self.mock_component_manager.validate_metadata_conflicts.assert_not_called()

    # END OF NEW FEATURE: Metadata Conflict Validation API Tests (TDD Red)

    def test_update_group_order_success(self):
        """Test the API endpoint for updating the group order."""
        new_order_payload = ["group_b", "general", "group_a"]
        response = self._put_json("/api/groups/order", new_order_payload)
        self.assertEqual(response.status_code, 200)
        self.mock_component_manager.update_group_order.assert_called_with(
            new_order_payload
        )

    def test_create_component_success(self):
        """Test the API endpoint for creating a new component."""
        payload = {"id": "new-component", "name": "New Component"}
        response = self._post_json("/api/components", payload)
        self.assertEqual(response.status_code, 201)
        self.mock_component_manager.create_component.assert_called_with(
            "new-component", "New Component"
        )

    def test_update_component_group_success(self):
        """Test the API endpoint for moving a component to a new group."""
        payload = {"group": "new-group-id"}
        response = self._put_json("/api/components/comp-a/group", payload)
        self.assertEqual(response.status_code, 200)
        self.mock_component_manager.update_component_group.assert_called_with(
            "comp-a",
            "new-group-id",
        )

    def test_update_component_metadata_with_traefik_fields(self):
        """
        Test the PUT endpoint for component metadata to ensure new Traefik
        fields are correctly type-cast before being saved.
        """
        component_id = "test-comp"
        # The frontend will send booleans/integers as strings
        payload = {
            "name": "Updated Name",
            "has_traefik_support": "true",  # Should be converted to True (bool)
            "traefik_internal_port": "8080",  # Should be converted to 8080 (int)
        }

        response = self._put_json(f"/api/components/{component_id}", payload)

        # 1. Assert successful response
        self.assertEqual(response.status_code, 200)

        # 2. Assert the ComponentManager was called with correctly typed data
        expected_call_data = {
            "name": "Updated Name",
            "has_traefik_support": True,  # Check for conversion
            "traefik_internal_port": 8080,  # Check for conversion
        }
        self.mock_component_manager.update_component_metadata.assert_called_with(
            component_id,
            expected_call_data,
        )

    def test_update_component_metadata_traefik_port_invalid(self):
        """
        Test the PUT endpoint for component metadata when the internal port
        is not a valid integer.
        """
        component_id = "test-comp"
        payload = {
            "name": "Updated Name",
            "traefik_internal_port": "not-a-port",
        }

        response = self._put_json(f"/api/components/{component_id}", payload)

        # Assert validation failure
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.json)
        self.assertIn(
            "Traefik Internal Port must be a valid integer.",
            response.json["error"],
        )
        self.mock_component_manager.update_component_metadata.assert_not_called()

    def test_delete_group_success(self):
        """Test the API endpoint for deleting an unused group."""
        response = self.client.delete("/api/groups/old-group")
        self.assertEqual(response.status_code, 200)
        self.mock_component_manager.delete_group.assert_called_with("old-group")
        self.assertIn("message", response.json)

    def test_delete_group_manager_error(self):
        """Test the delete group API when the manager raises a ValueError."""
        self.mock_component_manager.delete_group.side_effect = ValueError(
            "Group is not empty"
        )
        response = self.client.delete("/api/groups/non-empty-group")
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.json)
        self.assertEqual(response.json["error"], "Group is not empty")

    def test_delete_group_not_found(self):
        """Test the delete group API when the group is not found."""
        self.mock_component_manager.delete_group.side_effect = KeyError(
            "Group not found"
        )
        # Correctly assert 404 since the server now correctly returns 404
        response = self.client.delete("/api/groups/non-existent-group")
        self.assertEqual(response.status_code, 404)
        self.assertIn("error", response.json)
        self.assertEqual(response.json["error"], "Group not found")

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

        expected_call_payload = {
            "variables": [
                {"id": "VAR1", "required": "always"},
                {"id": "VAR2"},
                {"id": "VAR3"},
            ]
        }

        response = self._put_json("/api/components/some-comp/variables", payload)

        self.assertEqual(response.status_code, 200)
        self.mock_component_manager.update_component_variables.assert_called_once_with(
            "some-comp", expected_call_payload
        )

    def test_update_component_variables_keyerror(self):
        """Test update variables API when component is not found."""
        target_mock = self.mock_component_manager.update_component_variables
        target_mock.side_effect = KeyError("Component not found")
        payload = {"variables": []}
        response = self._put_json(
            "/api/components/non-existent-comp/variables", payload
        )
        self.assertEqual(response.status_code, 404)
        self.assertIn("Component not found", response.json["error"])

    def test_update_component_variables_bad_payload(self):
        """Test update variables API with a bad payload."""
        response = self.client.put(
            "/api/components/some-comp/variables",
            data="not json",
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Invalid payload", response.json["error"])

    def test_get_component_template_success(self):
        """Test the API endpoint for getting component template content."""
        expected_content = "services:\n  some-service:\n    image: latest"
        self.mock_component_manager.get_component_template_content.return_value = (
            expected_content
        )

        response = self.client.get("/api/components/some-comp/template")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.decode("utf-8"), expected_content)
        self.assertEqual(response.mimetype, "text/plain")
        self.mock_component_manager.get_component_template_content.assert_called_with(
            "some-comp"
        )

    def test_update_component_template_success(self):
        """Test the API endpoint for updating component template content."""
        new_content = "services:\n  new-service:\n    image: new-image"
        response = self.client.put(
            "/api/components/some-comp/template",
            data=new_content,
            content_type="text/plain",
        )
        self.assertEqual(response.status_code, 200)
        update_template_mock = (
            self.mock_component_manager.update_component_template_content
        )
        update_template_mock.assert_called_with(
            "some-comp",
            new_content,
        )

    def test_update_component_template_not_found(self):
        """Test updating template when the component is not found."""
        target_mock = self.mock_component_manager.update_component_template_content
        target_mock.side_effect = KeyError

        new_content = "services:\n" "  new-service:\n" "    image: new-image"
        response = self.client.put(
            "/api/components/non-existent-comp/template",
            data=new_content,
            content_type="text/plain",
        )
        self.assertEqual(response.status_code, 404)
        self.assertIn("Component not found", response.json["error"])


if __name__ == "__main__":
    unittest.main()
