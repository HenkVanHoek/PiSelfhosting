import logging
import re
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader

from managers.component_manager import ComponentManager

logger = logging.getLogger(__name__)


# --- YAML Customization ---
def represent_quoted_str(dumper, data):
    """A PyYAML representer that forces quotes on port-like strings."""
    if isinstance(data, str) and re.match(r"^\d+:\d+(/[a-z]+)?$", data):
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style='"')
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


class DockerComposeYAMLDumper(yaml.SafeDumper):
    pass


DockerComposeYAMLDumper.add_representer(str, represent_quoted_str)


class SetupManager:
    """Manages the generation of setup files."""

    DOCKER_COMPOSE_TEMPLATE = "docker-compose.template.yml"

    def __init__(self, component_manager, output_dir=None, template_base_path=None):
        self.component_manager: ComponentManager = component_manager
        self.output_dir = Path(output_dir) if output_dir else Path("output")

        if template_base_path:
            self.template_base_path = Path(template_base_path)
        else:
            self.template_base_path = (
                Path(__file__).parent.parent.parent / "component_templates"
            )

        self.docker_compose_path = self.output_dir / "docker-compose.yml"

    def generate_all_files(self, selected_components, user_variables, managed_devices):
        errors = []
        logger.info(f"Starting file generation for: {', '.join(selected_components)}")

        auto_vars = {}
        if managed_devices:
            # NOTE: The managed_devices object is a LIST of dictionaries.
            # Always access the first element to get device properties.
            auto_vars["PISelfhosting_HOST_IP"] = managed_devices[0].get(
                "ip", "127.0.0.1"
            )
        else:
            auto_vars["PISelfhosting_HOST_IP"] = "127.0.0.1"

        auto_vars["PISelfhosting_DATA_PATH"] = "~/piselfhosting_data"

        try:
            full_component_list = self._resolve_dependencies(selected_components)
        except ValueError as e:
            return False, [str(e)]

        master_variable_context = {}
        for component_id in full_component_list:
            details = self.component_manager.get_component_details(component_id)
            if details and details.get("required_variables"):
                for var in details["required_variables"]:
                    if "name" in var and "default" in var:
                        master_variable_context[var["name"]] = var["default"]

        master_variable_context.update(user_variables)

        # --- THE DEFINITIVE, FINAL FIX ---
        # Perform a second, "self-rendering" pass to resolve nested variables.
        try:
            # 1. Define any global variables needed for the nested render.
            second_pass_context = auto_vars.copy()
            second_pass_context["CONFIG_BASE_PATH"] = (
                f"{auto_vars['PISelfhosting_DATA_PATH']}/config"
            )
            second_pass_context.update(master_variable_context)

            # 2. Create a simple Jinja environment for this pass.
            jinja_env_pass2 = Environment(autoescape=True)

            # 3. Iterate and render any values that are themselves templates.
            for key, value in master_variable_context.items():
                if isinstance(value, str) and "{{" in value and "}}" in value:
                    template = jinja_env_pass2.from_string(value)
                    master_variable_context[key] = template.render(
                        **second_pass_context
                    )
        except Exception as e:
            msg = f"An unexpected error occurred during nested variable rendering: {e}"
            logger.error(msg, exc_info=True)
            errors.append(msg)
            return False, errors

        base_render_context = {**auto_vars, **master_variable_context}

        compose_data = {"services": {}, "volumes": {}, "networks": {}}

        for component_id in full_component_list:
            details = self.component_manager.get_component_details(component_id)
            if not details:
                errors.append(f"Component '{component_id}' not found in metadata.")
                continue

            try:
                component_render_context = base_render_context.copy()
                details["id"] = component_id
                component_render_context.update(details)

                template_path = self.template_base_path / component_id

                if not template_path.exists():
                    raise FileNotFoundError(
                        f"Template directory not found at {template_path}"
                    )

                jinja_env = Environment(
                    loader=FileSystemLoader(str(template_path)), autoescape=True
                )

                self._merge_docker_compose_template(
                    component_id,
                    jinja_env,
                    compose_data,
                    component_render_context,
                    errors,
                )

                if "other_files" in details:
                    self._generate_other_files(
                        component_id,
                        details,
                        jinja_env,
                        component_render_context,
                        errors,
                    )

            except Exception as e:
                msg = f"An unexpected error occurred for component {component_id}: {e}"
                logger.error(msg, exc_info=True)
                errors.append(msg)

        if not errors:
            try:
                self.output_dir.mkdir(parents=True, exist_ok=True)
                with open(self.docker_compose_path, "w") as f:
                    yaml.dump(
                        compose_data,
                        f,
                        Dumper=DockerComposeYAMLDumper,
                        default_flow_style=False,
                        sort_keys=False,
                        width=float("inf"),
                    )
                logger.info(f"Successfully generated {self.docker_compose_path}")
            except IOError as e:
                errors.append(f"Failed to write docker-compose file: {e}")

        return not errors, errors

    def _resolve_dependencies(self, selected_components: list[str]) -> list[str]:
        resolved = []
        visited = set()

        for initial_comp_id in selected_components:
            stack = [initial_comp_id]
            visiting = {initial_comp_id}

            while stack:
                comp_id = stack[-1]

                if comp_id in visited:
                    stack.pop()
                    continue

                details = self.component_manager.get_component_details(comp_id)
                dependencies: list[str] = []
                if details:
                    deps = details.get("depends_on", [])
                    dependencies = [deps] if isinstance(deps, str) else deps

                unresolved_dependencies = [
                    dep for dep in dependencies if dep not in visited
                ]

                if not unresolved_dependencies:
                    stack.pop()
                    visited.add(comp_id)
                    if comp_id not in resolved:
                        resolved.append(comp_id)
                    visiting.remove(comp_id)
                else:
                    for dep_id in unresolved_dependencies:
                        if dep_id in visiting:
                            raise ValueError(
                                f"Circular dependency detected involving "
                                f"'{dep_id}' and '{comp_id}'"
                            )
                        stack.append(dep_id)
                        visiting.add(dep_id)

        return self.component_manager.sort_components_by_master_order(resolved)

    def _merge_docker_compose_template(
        self, comp_id, jinja_env, compose_data, context, errors
    ):
        try:
            template = jinja_env.get_template(self.DOCKER_COMPOSE_TEMPLATE)
            rendered_content = template.render(**context)
            component_compose = yaml.safe_load(rendered_content)
            if component_compose:
                compose_data["services"].update(component_compose.get("services", {}))
                compose_data["volumes"].update(component_compose.get("volumes", {}))
                compose_data["networks"].update(component_compose.get("networks", {}))
        except Exception as e:
            errors.append(f"Failed to process template for {comp_id}: {e}")

    def _generate_other_files(self, component_id, details, jinja_env, context, errors):
        for file_config in details.get("other_files", []):
            template_name = file_config.get("template")
            output_path_str = file_config.get("destination")
            if not template_name or not output_path_str:
                errors.append(
                    f"Incomplete file config for {component_id}: {file_config}"
                )
                continue
            try:
                template = jinja_env.get_template(template_name)
                rendered_content = template.render(**context)
                full_output_path = self.output_dir / output_path_str
                full_output_path.parent.mkdir(parents=True, exist_ok=True)
                with open(full_output_path, "w") as f:
                    f.write(rendered_content)
                logger.info(f"Generated {full_output_path}")
            except Exception as e:
                msg = f"Failed to generate {output_path_str} for {component_id}: {e}"
                logger.error(msg)
                errors.append(msg)
