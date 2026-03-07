# tests/editor_app/test_editor_app.py
import json
import unittest
from unittest.mock import patch

from src.editor_app.app import create_app


class EditorAppTestCase(unittest.TestCase):
    def setUp(self):
        """Set up test client and mock the new CQRS managers."""
        # 1. Patch the new managers in the editor_app.app module
        self.patcher_reader = patch("src.editor_app.app.ComponentReader")
        self.patcher_writer = patch("src.editor_app.app.ComponentWriter")

        self.mock_reader_class = self.patcher_reader.start()
        self.mock_writer_class = self.patcher_writer.start()

        # 2. Get the instances (what create_app will actually use)
        self.mock_reader = self.mock_reader_class.return_value
        self.mock_writer = self.mock_writer_class.return_value

        # 3. Initialize app with testing config
        self.app = create_app({"TESTING": True})
        self.client = self.app.test_client()

    def tearDown(self):
        self.patcher_reader.stop()
        self.patcher_writer.stop()

    def test_list_components_api(self):
        """Test the GET /api/components endpoint."""
        # Setup: Return a real list, not a MagicMock, to avoid JSON errors
        self.mock_reader.get_all_components.return_value = {"nginx": {"name": "Nginx"}}

        response = self.client.get("/api/components")
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.data)
        self.assertIn("nginx", data)
        self.assertEqual(data["nginx"]["name"], "Nginx")

    def test_update_variables_success(self):
        """Test PUT /api/components/<id>/variables."""
        self.mock_writer.update_component_variables.return_value = True

        payload = [{"name": "PORT", "value": "80"}]
        response = self.client.put(
            "/api/components/nginx/variables",
            data=json.dumps(payload),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.mock_writer.update_component_variables.assert_called_once_with(
            "nginx", payload
        )

    def test_add_component_success(self):
        """Test POST /api/components."""
        self.mock_writer.create_component_skeleton.return_value = True

        payload = {"id": "ghost", "meta": {"name": "Ghost"}}
        response = self.client.post(
            "/api/components", data=json.dumps(payload), content_type="application/json"
        )

        self.assertEqual(response.status_code, 201)
        self.mock_writer.create_component_skeleton.assert_called_once()
