import logging
import re
from pathlib import Path

import jinja2
import yaml
from jinja2 import Environment, FileSystemLoader

logger = logging.getLogger(__name__)


# --- YAML Customization ---

# This is a standalone function with an explicit signature that PyCharm understands.
def represent_quoted_str(dumper, data):
    """A PyYAML representer that forces quotes on port-like strings."""
    if re.match(r"^\d+:\d+(/[a-z]+)?$", data):
        return dumper.represent_scalar("tag:yaml.org,2002:str",
                                     data, style='"')
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


# The Dumper class can now be a simple subclass without custom methods.
class DockerComposeYAMLDumper(yaml.SafeDumper):
    pass


# We register our standalone function to handle all strings.
DockerComposeYAMLDumper.add_representer(str, represent_quoted_str)


class SetupManager:
    """Manages the generation of setup files."""

    DOCKER_COMPOSE_TEMPLATE = "docker-compose.template.yml"

    def __init__(self, component_manager, output_dir=None):
        self.component_manager = component_manager
        self.output_dir = Path(output_dir) if output_dir else Path("output")
        self.docker_compose_path = self.output_dir / "docker-compose.yml"

    def generate_all_files(self, selected_components, env_vars):
        """
        Generates all necessary configuration files.
        Returns a tuple: (bool_success, list_of_errors)
        """
        errors = []
        logger.info(f"Starting file generation for: {', '.join(selected_components)}")

        full_component_list = self._resolve_dependencies(selected_components)
        compose_data = {"version": "3.8", "services": {}, "volumes": {}, "networks": {}}

        for component_id in full_component_list:
            details = self.component_manager.get_component_details(component_id)
            if not details:
                errors.append(f"Component '{component_id}' not found in metadata.")
                continue

            try:
                template_path = self.component_manager.config.get_component_template_path(
                    component_id
                )
                jinja_env = Environment(loader=FileSystemLoader(str(template_path)))

                self._merge_docker_compose_template(
                    component_id, jinja_env, compose_data, env_vars, errors
                )

                if "other_files" in details:
                    self._generate_other_files(
                        component_id, details, jinja_env, env_vars, errors
                    )
            except Exception as e:
                msg = f"An unexpected error occurred for component {component_id}: {e}"
                logger.error(msg, exc_info=True)
                errors.append(msg)

        if not compose_data["services"] and not errors:
            msg = "No valid Docker services were processed. docker-compose.yml will not be generated."
            logger.warning(msg)
            errors.append(msg)

        if errors:
            return False, errors

        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            with open(self.docker_compose_path, "w") as f:
                yaml.dump(
                    compose_data, f, Dumper=DockerComposeYAMLDumper,
                    default_flow_style=False, sort_keys=False, width=float("inf")
                )
            logger.info(f"Successfully generated {self.docker_compose_path}")
        except IOError as e:
            msg = f"Failed to write docker-compose file: {e}"
            logger.error(msg)
            errors.append(msg)
            return False, errors

        return True, []

    def _resolve_dependencies(self, selected_components):
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

        order = self.component_manager.get_component_order()

        return sorted(
            list(resolved), key=lambda x: order.index(x) if x in order else -1
        )

    @staticmethod
    def _merge_docker_compose_template(comp_id, jinja_env, compose_data, env_vars, errors):
        try:
            template = jinja_env.get_template(SetupManager.DOCKER_COMPOSE_TEMPLATE)
            rendered_content = template.render(env_vars)
            component_compose = yaml.safe_load(rendered_content)

            if component_compose:
                compose_data["services"].update(component_compose.get("services", {}))
                compose_data["volumes"].update(component_compose.get("volumes", {}))
                compose_data["networks"].update(component_compose.get("networks", {}))
        except (jinja2.TemplateNotFound, yaml.YAMLError) as e:
            msg = f"Failed to process template for {comp_id}: {e}"
            logger.error(msg)
            errors.append(msg)

    def _generate_other_files(self, component_id, details, jinja_env, env_vars, errors):
        for file_config in details.get("other_files", []):
            template_name = file_config.get("template")
            output_path_str = file_config.get("destination")

            if not template_name or not output_path_str:
                errors.append(f"Incomplete file config for {component_id}: {file_config}")
                continue

            try:
                template = jinja_env.get_template(template_name)
                rendered_content = template.render(env_vars)
                full_output_path = self.output_dir / output_path_str
                full_output_path.parent.mkdir(parents=True, exist_ok=True)

                with open(full_output_path, "w") as f:
                    f.write(rendered_content)
                logger.info(f"Generated {full_output_path}")
            except (jinja2.TemplateNotFound, IOError) as e:
                msg = f"Failed to generate {output_path_str} for {component_id}: {e}"
                logger.error(msg)
                errors.append(msg)