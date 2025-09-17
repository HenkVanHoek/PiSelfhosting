import json
import logging
import re
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader

from managers.component_manager import ComponentManager
from utils.generation_logger import GenerationLogger

logger = logging.getLogger(__name__)


def represent_quoted_str(dumper, data):
    if isinstance(data, str) and re.match(r"^\d+:\d+(/[a-z]+)?$", data):
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style='"')
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


class DockerComposeYAMLDumper(yaml.SafeDumper):
    pass


DockerComposeYAMLDumper.add_representer(str, represent_quoted_str)


class SetupManager:
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
        self.output_dir.mkdir(parents=True, exist_ok=True)
        log = GenerationLogger(self.output_dir)

        log.log_list("Initial Components Selected by User", selected_components)

        auto_vars = {}
        if managed_devices:
            # --- THE DEFINITIVE, FINAL FIX (List Unpacking) ---
            # This robust pattern safely selects the first device from the list,
            # aligning with the architect's preferred, non-forgettable solution.
            first_device, *_ = managed_devices
            auto_vars["PISelfhosting_HOST_IP"] = first_device.get("ip", "127.0.0.1")
        else:
            auto_vars["PISelfhosting_HOST_IP"] = "127.0.0.1"
        auto_vars["PISelfhosting_DATA_PATH"] = "~/piselfhosting_data"

        try:
            full_component_list = self._resolve_dependencies(selected_components)
            log.log_list(
                "Full Component List (after dependency resolution)", full_component_list
            )
        except ValueError as e:
            errors.append(str(e))
            log.write_log()
            return False, errors

        default_vars = {}
        for component_id in full_component_list:
            details = self.component_manager.get_component_details(component_id)
            if details and details.get("required_variables"):
                for var in details["required_variables"]:
                    if "name" in var and "default" in var:
                        default_vars[var["name"]] = var["default"]

        final_context = default_vars.copy()
        final_context.update(user_variables)
        final_context.update(auto_vars)

        log.log_variable_resolution(default_vars, user_variables, final_context)

        try:
            second_pass_context = final_context.copy()
            second_pass_context["CONFIG_BASE_PATH"] = (
                f'{auto_vars["PISelfhosting_DATA_PATH"]}/config'
            )
            jinja_env_pass2 = Environment()  # nosec
            for key, value in final_context.items():
                if isinstance(value, str) and "{{" in value and "}}" in value:
                    template = jinja_env_pass2.from_string(value)
                    final_context[key] = template.render(**second_pass_context)
            log.log_dict("4. Final Context (After Nested Resolution)", final_context)
        except Exception as e:
            errors.append(f"An unexpected error during nested variable rendering: {e}")
            log.write_log()
            return False, errors

        try:
            context_path = self.output_dir / "deployment_context.json"
            with open(context_path, "w") as f:
                json.dump(final_context, f, indent=2)
        except IOError as e:
            errors.append(f"Failed to write deployment context file: {e}")
            log.write_log()
            return False, errors

        compose_data = {"services": {}, "volumes": {}, "networks": {}}
        log.log_step("Template Rendering")
        for component_id in full_component_list:
            details = self.component_manager.get_component_details(component_id)
            if not details:
                errors.append(f"Component '{component_id}' not found in metadata.")
                continue
            try:
                component_render_context = final_context.copy()
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
                errors.append(
                    f"An unexpected error occurred for component {component_id}: {e}"
                )

        if not errors:
            try:
                with open(self.docker_compose_path, "w") as f:
                    yaml.dump(
                        compose_data,
                        f,
                        Dumper=DockerComposeYAMLDumper,
                        default_flow_style=False,
                        sort_keys=False,
                        width=float("inf"),
                    )
            except IOError as e:
                errors.append(f"Failed to write docker-compose file: {e}")

        log.write_log()
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
                dependencies = []
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
                                "Circular dependency detected involving "
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
            except Exception as e:
                errors.append(
                    f"Failed to generate {output_path_str} for {component_id}: {e}"
                )
