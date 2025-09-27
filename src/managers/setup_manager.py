import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

import yaml
from dotenv import dotenv_values
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from managers.component_manager import ComponentManager
from utils.generation_logger import GenerationLogger

logger = logging.getLogger(__name__)


def represent_quoted_str(dumper, data):
    if isinstance(data, str) and re.match(r"^\d+:\d+(/[a-z]+)?$", data):
        # Enforce 88-character line limit
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style='"')
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


class DockerComposeYAMLDumper(yaml.SafeDumper):
    pass


DockerComposeYAMLDumper.add_representer(str, represent_quoted_str)


class SetupManager:
    DOCKER_COMPOSE_TEMPLATE = "docker-compose.template.yml"

    def __init__(
        self,
        component_manager: ComponentManager,
        output_dir: Any = None,
        template_base_path: Any = None,
    ) -> None:
        self.component_manager = component_manager
        self.output_dir = Path(output_dir) if output_dir else Path("output")
        if template_base_path:
            self.template_base_path = Path(template_base_path)
        else:
            self.template_base_path = (
                Path(__file__).parent.parent.parent / "component_templates"
            )
        self.docker_compose_path = self.output_dir / "docker-compose.yml"

    def prepare_deployment_package(
        self,
        selected_components: List[str],
        user_variables: Dict[str, Any],
        managed_devices: List[Dict[str, Any]],
    ) -> Tuple[bool, List[str]]:
        errors: List[str] = []
        self.output_dir.mkdir(parents=True, exist_ok=True)
        log = GenerationLogger(self.output_dir)

        log.log_list("Initial Components Selected by User", selected_components)

        project_root = self.template_base_path.parent
        dotenv_path = project_root / ".env"
        global_vars = dotenv_values(dotenv_path)
        log.log_dict("Global Variables Loaded from .env", global_vars)

        auto_vars = {}
        if managed_devices:
            first_device, *_ = managed_devices
            auto_vars["PISelfhosting_HOST_IP"] = first_device.get("ip", "127.0.0.1")
        else:
            auto_vars["PISelfhosting_HOST_IP"] = "127.0.0.1"
        auto_vars["PISelfhosting_DATA_PATH"] = "~/piselfhosting_data"

        try:
            full_component_list = self._resolve_dependencies(selected_components)
            log.log_list(
                "Full Component List (after dependency resolution)",
                full_component_list,
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
                    if "id" in var and "default" in var:
                        default_value = var["default"]
                        if isinstance(default_value, str) and default_value.startswith(
                            "{{ DOTENV."
                        ):
                            var_name_match = re.search(
                                r"{{\s*DOTENV\.(\w+)\s*}}", default_value
                            )
                            if var_name_match:
                                var_name = var_name_match.group(1)
                                if var_name in global_vars:
                                    default_vars[var["id"]] = global_vars[var_name]
                                else:
                                    errors.append(
                                        f"Error in {component_id}: Global variable "
                                        f"'{var_name}' is required but not found in "
                                        f"your .env file."
                                    )
                        else:
                            default_vars[var["id"]] = default_value

        if errors:
            log.write_log()
            return False, errors

        final_context = default_vars.copy()
        final_context.update(user_variables)
        final_context.update(auto_vars)

        log.log_variable_resolution(default_vars, user_variables, final_context)

        try:
            second_pass_context = final_context.copy()
            config_base_path = f"{auto_vars['PISelfhosting_DATA_PATH']}/config"
            second_pass_context["CONFIG_BASE_PATH"] = config_base_path
            second_pass_context["DOTENV"] = global_vars
            final_context["CONFIG_BASE_PATH"] = config_base_path
            final_context["DOTENV"] = global_vars
            jinja_env_pass2 = Environment(autoescape=True, undefined=StrictUndefined)
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
            with open(context_path, "w", encoding="utf-8") as f:
                json.dump(final_context, f, indent=2)
        except IOError as e:
            errors.append(f"Failed to write deployment context file: {e}")
            log.write_log()
            return False, errors

        compose_data: Dict[str, Any] = {"services": {}, "volumes": {}, "networks": {}}
        log.log_step("Template Rendering")
        for component_id in full_component_list:
            details = self.component_manager.get_component_details(component_id)
            if not details:
                errors.append(f"Component '{component_id}' not found in metadata.")
                continue
            try:
                component_render_context = final_context.copy()
                component_render_context.update(details)
                service_name = self.component_manager.get_docker_service_name(
                    component_id
                )
                component_render_context["service_name"] = service_name

                template_path = self.template_base_path / component_id
                if not template_path.exists():
                    raise FileNotFoundError(
                        f"Template directory not found at {template_path}"
                    )
                jinja_env = Environment(
                    loader=FileSystemLoader(str(template_path)),
                    autoescape=True,
                    undefined=StrictUndefined,
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
                errors.append(f"An unexpected error for component {component_id}: {e}")

        if not errors:
            try:
                with open(self.docker_compose_path, "w", encoding="utf-8") as f:
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
                unresolved_deps = [dep for dep in dependencies if dep not in visited]
                if not unresolved_deps:
                    stack.pop()
                    visited.add(comp_id)
                    if comp_id not in resolved:
                        resolved.append(comp_id)
                    visiting.remove(comp_id)
                else:
                    for dep_id in unresolved_deps:
                        if dep_id in visiting:
                            raise ValueError(
                                f"Circular dependency: '{dep_id}' and " f"'{comp_id}'"
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

            if not component_compose or "services" not in component_compose:
                return

            modified_services = {}
            for s_name, s_def in component_compose["services"].items():
                new_service_def = s_def.copy()

                labels = new_service_def.get("labels", [])
                if isinstance(labels, dict):
                    labels = [f"{k}={v}" for k, v in labels.items()]
                elif not isinstance(labels, list):
                    labels = []

                labels.append(f"piselfhosting.component.id={comp_id}")
                new_service_def["labels"] = labels
                modified_services[s_name] = new_service_def

            compose_data["services"].update(modified_services)
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
                with open(full_output_path, "w", encoding="utf-8") as f:
                    f.write(rendered_content)
            except Exception as e:
                errors.append(
                    f"Failed to generate {output_path_str} for " f"{component_id}: {e}"
                )
