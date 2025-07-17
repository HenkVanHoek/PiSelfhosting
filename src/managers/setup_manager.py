# src/managers/setup_manager.py
import logging
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader

logger = logging.getLogger(__name__)


class SetupManager:
    """Manages the generation of setup files."""

    def __init__(self, component_manager):
        self.component_manager = component_manager
        self.output_dir = "output"  # Default output directory
        self.docker_compose_path = f"{self.output_dir}/docker-compose.yml"

    def generate_all_files(self, selected_components, env_vars):
        """
        Generates a docker-compose.yml and other necessary configuration files
        from the selected components and their dependencies.

        Args:
            selected_components (list): A list of component IDs to include.
            env_vars (dict): A dictionary of environment variables for Jinja2 rendering.
        """
        logger.info(f"Starting file generation for: {', '.join(selected_components)}")

        full_component_list = self._resolve_dependencies(selected_components)
        logger.info(
            "Full component list with dependencies: %s", ", ".join(full_component_list)
        )

        compose_data = {"version": "3.8", "services": {}, "volumes": {}, "networks": {}}

        for component_id in full_component_list:
            details = self.component_manager.get_component_details(component_id)
            if not details:
                logger.warning(
                    f"No details found for component '{component_id}'. Skipping."
                )
                continue

            template_path = self.component_manager.config.get_component_template_path(
                component_id
            )
            jinja_env = Environment(loader=FileSystemLoader(str(template_path)))

            if "docker_compose" in details:
                self._merge_docker_compose_template(
                    component_id, details, jinja_env, compose_data, env_vars
                )

            if "other_files" in details:
                self._generate_other_files(component_id, details, jinja_env, env_vars)

        if not compose_data["services"]:
            logger.warning(
                "No Docker configurations processed; no file will be generated."
            )
            return

        try:
            # Ensure the output directory for docker-compose.yml exists
            Path(self.docker_compose_path).parent.mkdir(parents=True, exist_ok=True)
            with open(self.docker_compose_path, "w") as f:
                yaml.dump(compose_data, f, default_flow_style=False, sort_keys=False)
            logger.info(
                "Successfully generated docker-compose.yml at %s",
                self.docker_compose_path,
            )

        except IOError as e:
            logger.error(f"Failed to write docker-compose file: {e}")
            raise

    def _resolve_dependencies(self, selected_components):
        """Gets a full list of components including all dependencies."""
        resolved = set()
        queue = list(selected_components)

        while queue:
            comp_id = queue.pop(0)
            if comp_id in resolved:
                continue

            resolved.add(comp_id)
            details = self.component_manager.get_component_details(comp_id)

            if details and details.get("depends_on"):
                dependencies = details["depends_on"]
                if isinstance(dependencies, str):
                    dependencies = [dependencies]
                for dep in dependencies:
                    if dep not in resolved:
                        queue.append(dep)

        order = (
            self.component_manager.get_all_components()
            .get("_piselfhosting", {})
            .get("components_order", [])
        )
        return sorted(
            list(resolved), key=lambda x: order.index(x) if x in order else -1
        )

    @staticmethod
    def _merge_docker_compose_template(
        comp_id, details, jinja_env, compose_data, env_vars
    ):
        """Loads a component's docker-compose template and merges it."""
        template_name = details["docker_compose"]
        try:
            template = jinja_env.get_template(template_name)
            rendered_content = template.render(env_vars)
            component_compose = yaml.safe_load(rendered_content)

            if component_compose:
                compose_data["services"].update(component_compose.get("services", {}))
                compose_data["volumes"].update(component_compose.get("volumes", {}))
                compose_data["networks"].update(component_compose.get("networks", {}))

        except Exception as e:
            logger.error(
                f"Failed to process docker-compose template for {comp_id}: {e}"
            )

    def _generate_other_files(self, comp_id, details, jinja_env, env_vars):
        """Generates other config files for a component."""
        output_path_prefix = Path(self.output_dir)

        for file_info in details["other_files"]:
            template_name = file_info["template"]
            destination_path_str = file_info["destination"]

            try:
                template = jinja_env.get_template(template_name)
                rendered_content = template.render(env_vars)

                destination_path = output_path_prefix / destination_path_str
                destination_path.parent.mkdir(parents=True, exist_ok=True)

                with open(destination_path, "w") as f:
                    f.write(rendered_content)
                logger.info(
                    f"Generated config file for {comp_id} at {destination_path}"
                )

            except Exception as e:
                logger.error(
                    f"Failed to generate file '{template_name}' for {comp_id}: {e}"
                )
