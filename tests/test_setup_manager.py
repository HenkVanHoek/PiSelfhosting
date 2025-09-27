import json
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List
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

    # START OF FIX:
    def _run_deployment_and_get_results(
        self,
        selected: List[str],
        user_vars: Dict[str, Any],
        devices: List[Dict[str, Any]],
    ) -> tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Helper method to run a successful deployment and return the parsed
        compose and context files. This centralizes the common test execution
        and validation logic to avoid code duplication.
        """
        success, errors = self.setup_manager.prepare_deployment_package(
            selected, user_vars, devices
        )

        self.assertTrue(success, f"Deployment failed unexpectedly: {errors}")
        self.assertEqual([], errors)

        compose_path = self.output_dir / "docker-compose.yml"
        self.assertTrue(compose_path.exists())
        with open(compose_path, "r") as f:
            compose_data = yaml.safe_load(f)

        context_path = self.output_dir / "deployment_context.json"
        self.assertTrue(context_path.exists())
        with open(context_path, "r") as f:
            context_data = json.load(f)

        return compose_data, context_data

    # END OF FIX:

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

        # START OF FIX:
        compose_data, context = self._run_deployment_and_get_results(
            selected, user_vars, devices
        )
        # END OF FIX:

        self.assertEqual(context["TEST_PORT"], "8080")
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

        # START OF FIX:
        _, context = self._run_deployment_and_get_results(["service-a"], {}, [])
        # END OF FIX:

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

        # START OF FIX:
        self._run_deployment_and_get_results(
            ["other-file-comp"], {}, [{"ip": "192.168.1.50"}]
        )
        # END OF FIX:

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

        # START OF FIX:
        _, context = self._run_deployment_and_get_results(["traefik"], user_vars, [])
        # END OF FIX:

        self.assertEqual(context["LETSENCRYPT_EMAIL"], "user@example.com")

    def test_config_base_path_is_always_defined_and_rendered(self):
        """
        Verify that CONFIG_BASE_PATH is automatically generated and
        available for template rendering. This test simulates the exact
        failure condition of the 'vaultwarden' component.
        """
        self.mock_component_manager.get_component_details.return_value = {
            "name": "Vaultwarden"
        }
        self._create_component_template(
            "vaultwarden",
            """
services:
  vaultwarden:
    image: vaultwarden/server
    volumes:
      - "{{ CONFIG_BASE_PATH }}/vaultwarden:/data"
""",
        )
        selected = ["vaultwarden"]
        devices = [{"ip": "192.168.1.100"}]

        # START OF FIX:
        compose_data, context = self._run_deployment_and_get_results(
            selected, {}, devices
        )
        # END OF FIX:

        expected_volume = "~/piselfhosting_data/config/vaultwarden:/data"
        actual_volumes = compose_data["services"]["vaultwarden"]["volumes"]
        self.assertIn(expected_volume, actual_volumes)
        self.assertEqual(context["CONFIG_BASE_PATH"], "~/piselfhosting_data/config")

    def test_dotenv_macro_in_template_resolves_correctly(self):
        """
        Verify that a DOTENV macro used directly in a component template
        is resolved correctly. This validates that the entire DOTENV object
        is passed to the main rendering context.
        """
        with open(self.project_root_dir / ".env", "w") as f:
            f.write("SUPER_SECRET_TOKEN=abc-123-xyz")
        self.mock_component_manager.get_component_details.return_value = {
            "name": "Secure Service"
        }
        self._create_component_template(
            "secure-service",
            """
services:
  secure:
    image: my/secure-image
    environment:
      - ADMIN_TOKEN={{ DOTENV.SUPER_SECRET_TOKEN }}
""",
        )

        # START OF FIX:
        compose_data, context = self._run_deployment_and_get_results(
            ["secure-service"], {}, []
        )
        # END OF FIX:

        expected_env = "ADMIN_TOKEN=abc-123-xyz"
        actual_env = compose_data["services"]["secure"]["environment"]
        self.assertIn(expected_env, actual_env)
        self.assertEqual(context["DOTENV"]["SUPER_SECRET_TOKEN"], "abc-123-xyz")


if __name__ == "__main__":
    unittest.main()
# --- END OF FILE: tests/test_setup_manager.py ---
