import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

import yaml

from managers.setup_manager import SetupManager


class TestSetupManager(unittest.TestCase):
    """Unit tests for the SetupManager class."""

    def setUp(self):
        """Set up a mock ComponentManager and temporary directories for each test."""
        self.mock_component_manager = MagicMock()
        self.mock_component_manager.sort_components_by_master_order.side_effect = (
            lambda components: components
        )
        self.mock_component_manager.get_docker_service_name.side_effect = (
            lambda cid: cid.replace("-", "")
        )

        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.output_dir = self.temp_path / "output"
        self.template_base_dir = self.temp_path / "component_templates"
        self.project_root_dir = self.template_base_dir.parent

        self.setup_manager = SetupManager(
            component_manager=self.mock_component_manager, output_dir=self.output_dir
        )
        self.setup_manager.template_base_path = self.template_base_dir

    def tearDown(self):
        """Clean up the temporary directory after each test."""
        self.temp_dir.cleanup()

    def _create_component_template(self, component_id, template_content):
        """Helper function to create a component template directory and file."""
        component_dir = self.template_base_dir / component_id
        component_dir.mkdir(parents=True, exist_ok=True)
        with open(component_dir / "docker-compose.template.yml", "w") as f:
            f.write(template_content)
        return component_dir

    def test_prepare_deployment_package_success_with_labels(self):
        """
        Verify prepare_deployment_package renders templates, injects identity
        labels, and returns success correctly.
        """
        self.mock_component_manager.get_component_details.return_value = {
            "name": "Test Component"
        }
        self._create_component_template(
            "test-component",
            """
services:
  test-service:
    image: test/image
    ports:
      - "{{ TEST_PORT }}:80"
""",
        )
        selected = ["test-component"]
        user_vars = {"TEST_PORT": "8080"}
        devices = [{"ip": "192.168.1.100"}]
        success, errors = self.setup_manager.prepare_deployment_package(
            selected, user_vars, devices
        )
        self.assertTrue(success)
        self.assertEqual([], errors)
        context_path = self.output_dir / "deployment_context.json"
        self.assertTrue(context_path.exists())
        with open(context_path, "r") as f:
            context = json.load(f)
        self.assertEqual(context["TEST_PORT"], "8080")
        compose_path = self.output_dir / "docker-compose.yml"
        self.assertTrue(compose_path.exists())
        with open(compose_path, "r") as f:
            compose_data = yaml.safe_load(f)
        service_labels = compose_data["services"]["test-service"]["labels"]
        self.assertIn("piselfhosting.component.id=test-component", service_labels)

    def test_dependency_resolution_fails_on_circular_dependency(self):
        """Verify that a circular dependency raises a ValueError."""
        details = {
            "comp-a": {"name": "Component A", "depends_on": ["comp-b"]},
            "comp-b": {"name": "Component B", "depends_on": ["comp-a"]},
        }
        self.mock_component_manager.get_component_details.side_effect = (
            lambda cid: details.get(cid)
        )
        success, errors = self.setup_manager.prepare_deployment_package(
            ["comp-a"], {}, []
        )
        self.assertFalse(success)
        self.assertTrue(
            any("Circular dependency" in e for e in errors),
            msg=f"Expected substring not found in errors: {errors}",
        )

    def test_dotenv_variable_resolution_success(self):
        """Verify that variables from .env are correctly resolved."""
        with open(self.project_root_dir / ".env", "w") as f:
            f.write("MY_API_KEY=my-secret-key-from-dotenv")
        details = {
            "id": "service-a",
            "required_variables": [
                {"id": "API_KEY", "default": "{{ DOTENV.MY_API_KEY }}"}
            ],
        }
        self.mock_component_manager.get_component_details.return_value = details
        self._create_component_template("service-a", "services:\n  a:\n    image: foo")
        success, errors = self.setup_manager.prepare_deployment_package(
            ["service-a"], {}, []
        )
        self.assertTrue(success)
        self.assertEqual([], errors)
        context_path = self.output_dir / "deployment_context.json"
        with open(context_path, "r") as f:
            context = json.load(f)
        self.assertEqual(context["API_KEY"], "my-secret-key-from-dotenv")

    def test_dotenv_variable_resolution_fails_if_missing(self):
        """Verify failure when a required DOTENV variable is not in the .env file."""
        (self.project_root_dir / ".env").touch()
        details = {
            "id": "service-a",
            "required_variables": [
                {"id": "API_KEY", "default": "{{ DOTENV.MISSING_KEY }}"}
            ],
        }
        self.mock_component_manager.get_component_details.return_value = details
        success, errors = self.setup_manager.prepare_deployment_package(
            ["service-a"], {}, []
        )
        self.assertFalse(success)
        error_string = " ".join(errors)
        self.assertIn("MISSING_KEY", error_string)
        self.assertIn("not found in your .env file", error_string)

    def test_template_rendering_error_for_missing_variable(self):
        """Verify failure when a template variable is not in the final context."""
        self.mock_component_manager.get_component_details.return_value = {
            "name": "Bad Component"
        }
        self._create_component_template(
            "bad-component",
            "services:\n  bad:\n    image: '{{ UNDEFINED_VAR }}'",
        )
        success, errors = self.setup_manager.prepare_deployment_package(
            ["bad-component"], {}, []
        )
        self.assertFalse(success)
        error_string = " ".join(errors)
        self.assertIn("Failed to process template", error_string)
        self.assertIn("'UNDEFINED_VAR' is undefined", error_string)

    def test_other_files_are_generated_correctly(self):
        """Verify that auxiliary files are generated from templates."""
        details = {
            "name": "Component With Other Files",
            "other_files": [
                {
                    "template": "config.ini.j2",
                    "destination": "config/my-service.ini",
                }
            ],
        }
        self.mock_component_manager.get_component_details.return_value = details
        component_dir = self._create_component_template(
            "other-file-comp", "services:\n  main:\n    image: foo"
        )
        with open(component_dir / "config.ini.j2", "w") as f:
            f.write("[settings]\napi_host={{ PISelfhosting_HOST_IP }}")
        success, errors = self.setup_manager.prepare_deployment_package(
            ["other-file-comp"], {}, [{"ip": "192.168.1.50"}]
        )
        self.assertTrue(success)
        self.assertEqual([], errors)
        generated_file = self.output_dir / "config/my-service.ini"
        self.assertTrue(generated_file.exists())
        with open(generated_file, "r") as f:
            content = f.read()
        self.assertIn("api_host=192.168.1.50", content)

    def test_user_provided_dotenv_macro_resolves_correctly(self):
        """
        Verify a DOTENV macro provided by a user (not from a default)
        is resolved in the second pass.
        """
        # ARRANGE
        with open(self.project_root_dir / ".env", "w") as f:
            f.write("USER_EMAIL=user@example.com")

        self.mock_component_manager.get_component_details.return_value = {
            "name": "traefik"
        }
        self._create_component_template(
            "traefik",
            "services:\n  traefik:\n    "
            'image: traefik\n    command: "--entrypoints.web.address=:80"',
        )
        user_vars = {"LETSENCRYPT_EMAIL": "{{ DOTENV.USER_EMAIL }}"}

        # ACT
        success, errors = self.setup_manager.prepare_deployment_package(
            ["traefik"], user_vars, []
        )

        # ASSERT
        self.assertTrue(success, f"Deployment failed with errors: {errors}")
        self.assertEqual([], errors)
        context_path = self.output_dir / "deployment_context.json"
        self.assertTrue(context_path.exists())
        with open(context_path, "r") as f:
            context = json.load(f)
        self.assertEqual(context["LETSENCRYPT_EMAIL"], "user@example.com")


if __name__ == "__main__":
    unittest.main()
