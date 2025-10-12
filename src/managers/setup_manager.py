# file: src/managers/setup_manager.py
import datetime
import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined
from yaml.error import YAMLError

from managers.component_manager import ComponentManager
from utils.generation_logger import GenerationLogger

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


class SetupManager:
    """Manages the setup and configuration file generation process."""

    def __init__(self, component_manager: ComponentManager, output_dir: Path):
        """
        Initializes the SetupManager.
        """
        self.component_manager = component_manager
        self.output_dir = output_dir
        self.project_root = self.component_manager.templates_path.parent
        self.timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        self.final_package_path: Optional[Path] = None

    def _expand_user_paths_in_context(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Recursively finds and expands all string values starting with '~/'
        to an absolute path.
        """
        new_context = json.loads(json.dumps(context))

        def recurse_and_expand(obj):
            if isinstance(obj, dict):
                for key, value in obj.items():
                    obj[key] = recurse_and_expand(value)
            elif isinstance(obj, list):
                for i, item in enumerate(obj):
                    obj[i] = recurse_and_expand(item)
            elif isinstance(obj, str) and obj.startswith("~/"):
                return str(Path(obj).expanduser())
            return obj

        return recurse_and_expand(new_context)

    def _resolve_dependencies(self, selected_ids: List[str]) -> Dict[str, Any]:
        """
        Resolves the full list of components including all dependencies.

        This performs a topological sort to ensure components are processed
        in the correct order based on their `depends_on` metadata.
        """
        all_components_list = self.component_manager.get_all_components()
        all_components_map = {comp["id"]: comp for comp in all_components_list}

        resolved_order = []
        visiting = set()  # Tracks nodes in the current recursion stack
        resolved = set()  # Tracks all nodes that have been fully processed

        def visit(comp_id: str):
            # If already fully resolved, do nothing.
            if comp_id in resolved:
                return

            # DEFINITIVE FIX: If we encounter a node that is in the current
            # recursion stack, we have found a circular dependency.
            if comp_id in visiting:
                raise ValueError(f"Circular dependency detected involving '{comp_id}'")

            visiting.add(comp_id)

            component_data = all_components_map.get(comp_id)
            if component_data:
                dependencies = component_data.get("depends_on", [])
                for dep_id in dependencies:
                    visit(dep_id)

            # Backtrack: remove from the current recursion stack
            visiting.remove(comp_id)
            # Mark as fully resolved
            resolved.add(comp_id)
            resolved_order.append(comp_id)

        for component_id in selected_ids:
            if component_id not in resolved:
                visit(component_id)

        final_components_dict = {
            comp_id: all_components_map[comp_id]
            for comp_id in resolved_order
            if comp_id in all_components_map
        }
        return final_components_dict

    def _load_global_vars(self) -> Dict[str, Any]:
        """Loads global variables from the .env file."""
        env_path = self.project_root / ".env"
        if not env_path.exists():
            return {}
        variables = {}
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    match = re.match(r"([^=]+)=(.*)", line)
                    if match:
                        key, value = match.groups()
                        variables[key.strip()] = value.strip()
        return variables

    def _build_initial_context(
        self, components: Dict[str, Any], log: GenerationLogger
    ) -> Dict[str, Any]:
        """Builds the initial context dictionary for template rendering."""
        context: Dict[str, Any] = {"components": {}}
        for comp_id, comp_data in components.items():
            variables = {
                var["id"]: var.get("default")
                for var in comp_data.get("required_variables", [])
                if "default" in var
            }
            context["components"][comp_id] = {"variables": variables}
        log.log_initial_context(context)
        return context

    def _resolve_context_variables(
        self,
        context: Dict[str, Any],
        global_vars: Dict[str, Any],
        log: GenerationLogger,
    ) -> Dict[str, Any]:
        """Resolves variable placeholders in the context."""
        resolved_context = json.loads(json.dumps(context))
        components = resolved_context.get("components", {})
        for comp_id, comp_data in components.items():
            variables = comp_data.get("variables", {})
            for var_name, var_value in variables.items():
                if isinstance(var_value, str):
                    placeholders = re.findall(r"\$\{(.*?)}", var_value)
                    for placeholder in placeholders:
                        if placeholder.startswith("components."):
                            try:
                                # pylint: disable=eval-used
                                resolved_value = eval(  # nosec B307
                                    placeholder, {"components": components}
                                )
                                var_value = var_value.replace(
                                    f"${{{placeholder}}}", str(resolved_value)
                                )
                            except (NameError, KeyError) as e:
                                logging.warning(
                                    "Could not resolve placeholder %s: %s",
                                    placeholder,
                                    e,
                                )
                        elif placeholder in global_vars:
                            resolved_value = global_vars[placeholder]
                            var_value = var_value.replace(
                                f"${{{placeholder}}}", str(resolved_value)
                            )
                        else:
                            logging.warning("Unresolved placeholder: %s", placeholder)
                    variables[var_name] = var_value
        log.log_resolved_context(resolved_context)
        return resolved_context

    def _resolve_nested_variables(
        self,
        context: Dict[str, Any],
        global_vars: Dict[str, Any],
        log: GenerationLogger,
        max_depth: int = 5,
    ) -> Dict[str, Any]:
        """
        Iteratively resolves nested variables until no placeholders remain.
        """
        current_context = json.loads(json.dumps(context))
        for i in range(max_depth):
            context_str = json.dumps(current_context)
            if "${" in context_str:
                current_context = self._resolve_context_variables(
                    current_context, global_vars, log
                )
            else:
                break
        else:
            logging.warning(
                "Could not resolve all placeholders after %s passes.",
                max_depth,
            )
        log.log_final_context(current_context)
        return current_context

    def _merge_docker_compose_template(
        self,
        comp_id: str,
        compose_data: Dict[str, Any],
        context: Dict[str, Any],
        log: GenerationLogger,
    ) -> None:
        """
        Renders a component's docker-compose and merges the result, with
        enhanced error handling for YAML parsing.
        """
        rendered_content = self.component_manager.render_component_template(
            comp_id, context
        )
        log.log_raw_template_output(comp_id, rendered_content)
        try:
            component_compose = yaml.safe_load(rendered_content)
        except YAMLError as e:
            error_message = (
                f"YAML Parsing Failed for component '{comp_id}'. "
                f"This is a syntax error in the component's template, likely "
                f"due to incorrect indentation.\n"
                f"Parser error: {e}\n\n"
                f"--- Crashing Content ---\n{rendered_content}\n--- End Content ---"
            )
            raise ValueError(error_message) from e
        if component_compose:
            for key in ["services", "volumes", "networks"]:
                if key in component_compose:
                    if key not in compose_data:
                        compose_data[key] = {}
                    compose_data[key].update(component_compose[key])

    def _copy_template_configs(
        self,
        comp_id: str,
        context: Dict[str, Any],
        global_vars: Dict[str, Any],
    ) -> None:
        """
        Copies and renders template-config files for a component.
        """
        template_dir = self.component_manager.templates_path
        # Enable autoescaping to mitigate potential XSS vulnerabilities.
        jinja_env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            autoescape=True,
            trim_blocks=True,
            lstrip_blocks=True,
            undefined=StrictUndefined,
        )
        template_config_dir_name = "template-config"
        template_config_path = template_dir / comp_id / template_config_dir_name
        if template_config_path.is_dir():
            destination_dir = self.output_dir / "config" / comp_id
            destination_dir.mkdir(parents=True, exist_ok=True)
            for item in template_config_path.rglob("*"):
                if item.is_file():
                    relative_path = item.relative_to(template_dir)
                    try:
                        template = jinja_env.get_template(str(relative_path))
                        rendered_content = template.render(
                            **context, DOTENV=global_vars
                        )
                        dest_file_path = destination_dir / item.relative_to(
                            template_config_path
                        )
                        dest_file_path.parent.mkdir(parents=True, exist_ok=True)
                        with open(dest_file_path, "w", encoding="utf-8") as f:
                            f.write(rendered_content)
                    except Exception as e:
                        logging.error(
                            "Failed to render template %s: %s",
                            relative_path,
                            e,
                        )

    def prepare_deployment_package(
        self,
        selected_components: List[str],
        user_variables: Dict[str, Any],
    ) -> Tuple[bool, Optional[List[Dict[str, str]]]]:
        """
        Generates all necessary configuration files.
        """
        log = GenerationLogger(self.output_dir)
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            log.log_initial_components(selected_components)
            components = self._resolve_dependencies(selected_components)
            log.log_full_component_list(list(components.keys()))
            global_vars = self._load_global_vars()
            global_vars.update(user_variables)
            log.log_global_vars(global_vars)
            initial_context = self._build_initial_context(components, log)
            final_context = self._resolve_nested_variables(
                initial_context, global_vars, log
            )
            final_context = self._expand_user_paths_in_context(final_context)
            final_context.update(global_vars)
            log.log_section_header("Template Rendering")

            combined_compose: Dict[str, Any] = {
                "version": "3.8",
                "networks": {"piselfhosting_net": {"external": True}},
            }
            for component_id, component_data in components.items():
                log.log_entry("Processing component", f"Component ID: {component_id}")
                existing_services = set(combined_compose.get("services", {}).keys())
                self._merge_docker_compose_template(
                    component_id,
                    combined_compose,
                    final_context,
                    log,
                )
                current_services = set(combined_compose.get("services", {}).keys())
                newly_added_services = current_services - existing_services
                if (
                    component_data.get("has_traefik_support")
                    and component_id != "traefik"
                ):
                    for service_name in newly_added_services:
                        service_def = combined_compose["services"][service_name]
                        depends_on_config = service_def.setdefault("depends_on", [])
                        if isinstance(depends_on_config, list):
                            if "traefik" not in depends_on_config:
                                depends_on_config.append("traefik")
                        elif isinstance(depends_on_config, dict):
                            if "traefik" not in depends_on_config:
                                depends_on_config["traefik"] = {
                                    "condition": "service_started"
                                }
                self._copy_template_configs(component_id, final_context, global_vars)
            compose_path = self.output_dir / "docker-compose.yml"
            with open(compose_path, "w", encoding="utf-8") as f:
                yaml.dump(
                    combined_compose,
                    f,
                    default_flow_style=False,
                    sort_keys=False,
                )
            log.log_generated_file("docker-compose.yml", compose_path)
            log.write_log()
            return True, None
        except Exception as e:
            logging.error(
                "Fatal error in prepare_deployment_package: %s",
                e,
                exc_info=True,
            )
            log.log_entry(
                "FATAL ERROR",
                f"The generation process failed with an exception: {e}",
            )
            log.write_log()
            # --- START OF FIX: IMPROVED UI ERROR REPORTING ---
            # Check if the error is our detailed ValueError and use its message.
            if isinstance(e, ValueError):
                details = str(e)
            else:
                details = f"An unexpected error occurred: {e}"
            error_details = [
                {
                    "type": "GenerationError",
                    "summary": "File generation failed.",
                    "details": details,
                }
            ]
            # --- END OF FIX ---
            return False, error_details

    def get_deployment_package_path(self) -> Optional[Path]:
        """Returns path to the most recently generated deployment package."""
        return self.final_package_path
