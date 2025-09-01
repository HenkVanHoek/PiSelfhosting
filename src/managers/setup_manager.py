import logging
import os
import re
from pathlib import Path

import jinja2
import yaml
from jinja2 import Environment, FileSystemLoader

logger = logging.getLogger(__name__)


class DockerComposeYAMLLoader(yaml.SafeLoader):
    def construct_scalar(self, node):
        # Preserve the style (quotes) from the input
        value = super().construct_scalar(node)
        if isinstance(node, yaml.ScalarNode):
            style = node.style
            if style in ['"', "'"] and isinstance(value, str):
                # Only preserve quotes for port mappings
                if re.match(r"^\d+:\d+(/[a-z]+)?$", value):
                    return f'"{value}"'  # Explicitly add quotes
        return value


class DockerComposeYAMLDumper(yaml.SafeDumper):
    @staticmethod
    def represent_str(dumper, data):
        # Match both simple port mappings (8080:80) and
        # those with protocols (8080:80/tcp)
        if isinstance(data, str) and (
            re.match(r"^\d+:\d+$", data)  # Simple port mapping
            or re.match(r"^\d+:\d+/[a-z]+$", data)  # Port with protocol
        ):
            # Force double quotes for port mappings
            return dumper.represent_scalar("tag:yaml.org,2002:str",
                                         data, style='"')
        return super(DockerComposeYAMLDumper, dumper).represent_str(data)


DockerComposeYAMLDumper.add_representer(str,
                                        DockerComposeYAMLDumper.represent_str)


class SetupManager:
    """Manages the generation of setup files."""

    DOCKER_COMPOSE_TEMPLATE = "docker-compose.template.yml"

    def __init__(self, component_manager):
        self.component_manager = component_manager
        self.output_dir = "output"  # Default output directory
        self.docker_compose_path = f"{self.output_dir}/docker-compose.yml"

    def generate_all_files(self, selected_components, env_vars):
        """
        Generates docker-compose.yml and other necessary configuration files
        from the selected components and their dependencies.

        Args:
            selected_components: List of component IDs to generate files for
            env_vars: Dictionary of environment variables
        """
        logger.info(
            f"Starting file generation for components: {', '.join(selected_components)}"
        )
        logger.info(f"Environment variables: {env_vars}")

        full_component_list = self._resolve_dependencies(selected_components)
        logger.info(
            "Full component list with dependencies: %s", ", ".join(full_component_list)
        )

        compose_data = {"version": "3.8", "services": {}, "volumes": {}, "networks": {}}

        for component_id in full_component_list:
            details = self.component_manager.get_component_details(component_id)
            if not details:
                logger.warning(
                    f"No details found for " f"component '{component_id}'. Skipping."
                )
                continue

            template_path = self.component_manager.config.get_component_template_path(
                component_id
            )
            jinja_env = Environment(loader=FileSystemLoader(str(template_path)))

            try:
                logger.info(f"Processing docker-compose template for {component_id}")
                self._merge_docker_compose_template(
                    component_id, jinja_env, compose_data, env_vars
                )
            except (jinja2.TemplateNotFound, yaml.YAMLError) as e:
                logger.debug(
                    f"Error processing "
                    f"docker-compose template for {component_id}: {e}"
                )

            if "other_files" in details:
                self._generate_other_files(component_id, details, jinja_env, env_vars)

        if not compose_data["services"]:
            logger.warning(
                "No Docker configurations processed;" " no file will be generated."
            )
            return

        try:
            Path(self.docker_compose_path).parent.mkdir(parents=True, exist_ok=True)
            with open(self.docker_compose_path, "w") as f:
                yaml.dump(
                    compose_data,
                    f,
                    Dumper=DockerComposeYAMLDumper,
                    default_flow_style=False,
                    sort_keys=False,
                    width=float("inf"),
                )
            logger.info(
                "Successfully generated " "docker-compose.yml at %s",
                self.docker_compose_path,
            )
        except IOError as e:
            logger.error(f"Failed to write docker-compose file: {e}")
            raise

    def _resolve_dependencies(self, selected_components):
        """
        Gets a full list of components including all dependencies.

        Args:
            selected_components: List of component IDs to resolve dependencies for

        Returns:
            list: Ordered list of components with their dependencies
        """
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

        # Get component order from metadata if available
        order = (
            self.component_manager.get_all_components()
            .get("_piselfhosting", {})
            .get("components_order", [])
        )

        # Sort components based on predefined order, putting unordered components first
        return sorted(
            list(resolved), key=lambda x: order.index(x) if x in order else -1
        )

    @staticmethod
    def _merge_docker_compose_template(comp_id, jinja_env, compose_data, env_vars):
        """
        Loads a component's docker-compose template and merges it.

        Args:
            comp_id: Component ID
            jinja_env: Jinja2 Environment instance
            compose_data: Dictionary to merge the template data into
            env_vars: Environment variables for template rendering
        """
        try:
            template = jinja_env.get_template(SetupManager.DOCKER_COMPOSE_TEMPLATE)
            rendered_content = template.render(env_vars)
            component_compose = yaml.safe_load(rendered_content)

            if component_compose:
                compose_data["services"].update(component_compose.get("services", {}))
                compose_data["volumes"].update(component_compose.get("volumes", {}))
                compose_data["networks"].update(component_compose.get("networks", {}))
        except (jinja2.TemplateNotFound, yaml.YAMLError) as e:
            logger.error(
                f"Failed to process " f"docker-compose template for {comp_id}: {e}"
            )

    def _generate_other_files(self, component_id, details, jinja_env, env_vars):
        """
        Generates other configuration files for a component.

        Args:
            component_id: Component ID
            details: Component details dictionary
            jinja_env: Jinja2 Environment instance
            env_vars: Environment variables for template rendering
        """
        other_files = details.get("other_files", [])

        for file_config in other_files:
            template_name = file_config.get("template")
            output_path = file_config.get("destination")

            if not template_name or not output_path:
                logger.warning(
                    f"Incomplete file configuration for {component_id}: {file_config}"
                )
                continue

            try:
                template = jinja_env.get_template(template_name)
                rendered_content = template.render(env_vars)

                # Ensure output directory exists
                full_output_path = os.path.join(self.output_dir, output_path)
                os.makedirs(os.path.dirname(full_output_path), exist_ok=True)

                # Write the rendered content
                with open(full_output_path, "w") as f:
                    f.write(rendered_content)

                logger.info(f"Generated {output_path} for component {component_id}")

            except (jinja2.TemplateNotFound, IOError) as e:
                logger.error(
                    f"Failed to generate {output_path} for {component_id}: {e}"
                )
