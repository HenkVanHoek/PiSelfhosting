# tests/editor_app/test_editor_app_api.py

import json
import unittest
from unittest.mock import patch

from editor_app.app import create_app


class TestEditorAppAPI(unittest.TestCase):
    """Tests the editor application API endpoints."""

    def setUp(self):
        # Configure app in test mode
        self.app = create_app({"TESTING": True})
        self.client = self.app.test_client()

    @patch("editor_app.app.AIGenerator.generate_component_data")
    def test_ai_generate_endpoint_success(self, mock_generate):
        """Tests successful component generation via AI route."""
        mock_generate.return_value = {
            "metadata": {
                "name": "Caddy",
                "image_name": "caddy",
                "description": "web server",
                "group": "reverse_proxy",
                "has_ui": False,
                "has_configuration": True,
            },
            "docker_compose": "services:",
            "variables": [],
        }

        payload = {
            "repo_url": "https://github.com/caddyserver/caddy",
            "custom_instructions": "none",
            "api_key": "dummy_key",
        }

        response = self.client.post(
            "/api/ai/generate",
            data=json.dumps(payload),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        res_data = json.loads(response.data.decode("utf-8"))
        self.assertEqual(res_data["status"], "success")
        self.assertEqual(res_data["data"]["metadata"]["name"], "Caddy")
        mock_generate.assert_called_once_with(
            "https://github.com/caddyserver/caddy", "none"
        )

    def test_ai_generate_endpoint_missing_url(self):
        """Tests that missing repo_url returns a bad request error."""
        payload = {"custom_instructions": "none", "api_key": "dummy_key"}

        response = self.client.post(
            "/api/ai/generate",
            data=json.dumps(payload),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)

    @patch("editor_app.app.ComponentManager.create_component")
    @patch("editor_app.app.ComponentManager.update_component_metadata")
    @patch("editor_app.app.ComponentManager.update_component_template_content")
    @patch("editor_app.app.ComponentManager.update_component_variables")
    @patch("editor_app.app.ComponentManager._load_metadata")
    @patch("editor_app.app.ComponentManager._save_metadata")
    def test_save_ai_component_success(
        self,
        mock_save_meta,
        mock_load_meta,
        mock_update_vars,
        mock_update_template,
        mock_update_meta,
        mock_create,
    ):
        """Tests successful save of AI generated component."""
        mock_load_meta.return_value = {
            "_piselfhosting": {"components_order": []},
            "components": {},
        }

        payload = {
            "id": "caddy",
            "metadata": {
                "name": "Caddy",
                "image_name": "caddy",
                "description": "web server",
                "group": "reverse_proxy",
                "has_ui": False,
                "has_configuration": True,
            },
            "docker_compose": "services:",
            "variables": [],
            "config_templates": {"Caddyfile": "caddy/Caddyfile"},
        }

        # Mock the built-in open for writing config templates
        from unittest.mock import mock_open

        with patch("builtins.open", mock_open()):
            response = self.client.post(
                "/api/components/ai",
                data=json.dumps(payload),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 201)
        res_data = json.loads(response.data.decode("utf-8"))
        self.assertEqual(res_data["status"], "created")
        mock_create.assert_called_once_with("caddy", "Caddy")
        mock_update_meta.assert_called_once_with("caddy", payload["metadata"])
