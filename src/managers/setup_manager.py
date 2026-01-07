import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Tuple

import yaml

from managers.component_manager import ComponentManager

logger = logging.getLogger(__name__)

# Define the location for global variables. This is the convention.
GLOBAL_ENV_FILE_NAME = ".env"


class SetupManager:
    """
    Manages the creation and preparation of the deployment package,
    including generating Docker Compose files and .env files.
    """

    def __init__(self, component_manager: ComponentManager, output_dir: Path):
        self.component_manager = component_manager
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"SetupManager initialized. Output directory: {self.output_dir}")

    def _generate_env_content(
        self, user_variables: Dict[str, str], component_context: Dict[str, Any]
    ) -> str:
        """
        Generates the content for the main .env file by merging user-provided
        variables and global configuration context.
        """
        # Start with a base set of standard context variables (like the output path)
        env_vars = {
            "CONFIG_BASE_PATH": str(self.output_dir),
            "COMPOSE_PROJECT_NAME": "piselfhosting",
            # Add any project-wide defaults here
        }

        # Merge in the global variables derived from the component context
        # (e.g., Traefik settings that are used globally)
        for key, value in component_context.items():
            if key.startswith("GLOBAL_"):
                env_vars[key.replace("GLOBAL_", "")] = str(value)

        # Merge in all user-provided variables (these have the highest precedence)
        env_vars.update(user_variables)

        # Format as .env file content
        content = [f"{key}={value}" for key, value in env_vars.items()]
        return "\n".join(content)

    def _generate_docker_compose(
        self,
        selected_components_data: List[Dict[str, Any]],
        global_vars: Dict[str, Any],
    ) -> str:
        """
        Generates the final, combined docker-compose.yml content.
        This includes rendering each component's template, stitching them
        together.
        """
        all_services: List[str] = []
        base_context = {**global_vars}  # Ensure global vars are in the base context

        for component_data in selected_components_data:
            component_id = component_data.get("id")
            if not component_id:
                logger.warning("Skipping component with missing ID.")
                continue

            # Generate the rendered template content for the component
            rendered_template = self.component_manager.render_component_template(
                component_id, base_context.copy()
            )

            # Extract the 'services' section from the rendered YAML
            try:
                comp_yaml = yaml.safe_load(rendered_template)
                services = comp_yaml.get("services", {})
                for service_name, service_data in services.items():
                    # Add a mandatory label for component ID (for deployment checks)
                    service_data.setdefault("labels", []).append(
                        f"piselfhosting.component.id={component_id}"
                    )
                    # Add the service definition (name and data) to the list
                    service_yaml = yaml.dump(
                        {service_name: service_data},
                        default_flow_style=False,
                        sort_keys=False,
                    )
                    all_services.append(service_yaml)
            except yaml.YAMLError as e:
                logger.error(
                    f"YAML parsing failed for component {component_id}'s template: {e}"
                )
                raise ValueError(f"Template YAML error in {component_id}: {e}")

        # Stitch all services together under the main 'services' key
        combined_services = "\n".join(all_services)
        base_compose = "version: '3.7'\nservices:\n"
        final_compose = base_compose + combined_services
        return final_compose

    def prepare_deployment_package(
        self,
        selected_components: List[str],
        user_variables: Dict[str, str],
        _managed_devices: List[Dict[str, Any]],
    ) -> Tuple[bool, List[str]]:
        """
        Main entry point to generate the deployment files.

        Returns:
            Tuple[bool, List[str]]: Success status and a list of errors.
        """
        errors: List[str] = []

        # 1. Gather all component data needed for template generation
        all_components = self.component_manager.get_all_components()
        all_components_dict = {c["id"]: c for c in all_components}

        selected_components_data: List[Dict[str, Any]] = [
            all_components_dict[comp_id]
            for comp_id in selected_components
            if comp_id in all_components_dict
        ]

        # 2. Extract GLOBAL variables from user_variables
        global_vars = {}
        component_specific_vars = {}
        for key, value in user_variables.items():
            if key.startswith("GLOBAL_"):
                global_vars[key] = value
            else:
                component_specific_vars[key] = value

        # 3. Validation Gate: Ensure all templates and variables are valid
        for comp_data in selected_components_data:
            comp_id = comp_data["id"]
            try:
                template_content = (
                    self.component_manager.get_component_template_content(comp_id)
                )
                comp_vars = comp_data.get("required_variables", [])

                self.component_manager.validate_component_configuration(
                    comp_id, template_content, comp_vars
                )
            except ValueError as e:
                errors.append(f"Validation Failed for {comp_id}: {str(e)}")
                return False, errors
            except Exception as e:
                errors.append(f"Validation Error for {comp_id}: {str(e)}")
                return False, errors

        # 4. Generate Files
        try:
            # Generate Docker Compose file
            compose_content = self._generate_docker_compose(
                selected_components_data, global_vars
            )
            (self.output_dir / "docker-compose.yml").write_text(
                compose_content, "utf-8"
            )

            # Generate .env file
            env_content = self._generate_env_content(
                component_specific_vars, global_vars
            )
            (self.output_dir / GLOBAL_ENV_FILE_NAME).write_text(env_content, "utf-8")

            # Generate deployment context file (used for service link discovery)
            context_file = self.output_dir / "deployment_context.json"
            context_file.write_text(json.dumps(global_vars, indent=2), "utf-8")

        except Exception as e:
            errors.append(f"File Generation Failed: {str(e)}")
            return False, errors

        return True, errors
