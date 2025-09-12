import logging
import re
from pathlib import Path

import jinja2
import yaml
from jinja2 import Environment, FileSystemLoader

logger = logging.getLogger(__name__)


# --- YAML Customization ---
def represent_quoted_str(dumper, data):
    if re.match(r"^\d+:\d+(/[a-z]+)?$", data):
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style='"')
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


class DockerComposeYAMLDumper(yaml.SafeDumper):
    pass


DockerComposeYAMLDumper.add_representer(str, represent_quoted_str)


class SetupManager:
    DOCKER_COMPOSE_TEMPLATE = "docker-compose.template.yml"

    def __init__(self, component_manager, output_dir=None):
        self.component_manager = component_manager
        self.output_dir = Path(output_dir) if output_dir else Path("output")
        self.docker_compose_path = self.output_dir / "docker-compose.yml"

    def generate_all_files(self, selected_components, env_vars,
                           managed_devices):
        errors = []
        logger.info(
            f"Starting file generation for: {', '.join(selected_components)}")

        auto_vars = {}
        if managed_devices:
            first_device = managed_devices
            auto_vars["PISelfhosting_HOST_IP"] = first_device[0].get("ip",
                                                                  "127.0.0.1")
        else:
            auto_vars["PISelfhosting_HOST_IP"] = "127.0.0.1"

        auto_vars["PISelfhosting_DATA_PATH"] = "~/piselfhosting_data"
        render_context = {**auto_vars, **env_vars}

        full_component_list = self._resolve_dependencies(selected_components)
        compose_data = {"services": {}, "volumes": {}, "networks": {}}

        for component_id in full_component_list:
            details = self.component_manager.get_component_details(component_id)
            if not details:
                errors.append(f"Component '{component_id}' not found.");
                continue
            try:
                template_path = self.component_manager.config.get_component_template_path(
                    component_id)
                jinja_env = Environment(
                    loader=FileSystemLoader(str(template_path)))
                self._merge_docker_compose_template(component_id, jinja_env,
                                                    compose_data,
                                                    render_context, errors)
                if "other_files" in details:
                    self._generate_other_files(component_id, details, jinja_env,
                                               render_context, errors)
            except Exception as e:
                msg = f"Unexpected error for component {component_id}: {e}"
                logger.error(msg, exc_info=True);
                errors.append(msg)

        if not compose_data["services"] and not errors:
            msg = "No valid services processed; docker-compose.yml not generated."
            logger.warning(msg);
            errors.append(msg)

        if errors: return False, errors

        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            with open(self.docker_compose_path, "w") as f:
                yaml.dump(compose_data, f, Dumper=DockerComposeYAMLDumper,
                          default_flow_style=False, sort_keys=False,
                          width=float("inf"))
            logger.info(f"Successfully generated {self.docker_compose_path}")
        except IOError as e:
            msg = f"Failed to write docker-compose file: {e}"
            logger.error(msg);
            errors.append(msg)
            return False, errors

        return True, []

    def _resolve_dependencies(self, selected_components):
        resolved, queue = set(), list(selected_components)
        while queue:
            comp_id = queue.pop(0)
            if comp_id in resolved: continue
            resolved.add(comp_id)
            details = self.component_manager.get_component_details(comp_id)
            if details and "depends_on" in details:
                deps = details["depends_on"]
                if isinstance(deps, str): deps = [deps]
                for dep in deps:
                    if dep not in resolved: queue.append(dep)
        order = self.component_manager.get_component_order()
        return sorted(list(resolved),
                      key=lambda x: order.index(x) if x in order else -1)

    @staticmethod
    def _merge_docker_compose_template(comp_id, jinja_env, compose_data,
                                       context, errors):
        try:
            template = jinja_env.get_template(
                SetupManager.DOCKER_COMPOSE_TEMPLATE)
            rendered_content = template.render(context)
            component_compose = yaml.safe_load(rendered_content)
            if component_compose:
                compose_data["services"].update(
                    component_compose.get("services", {}))
                compose_data["volumes"].update(
                    component_compose.get("volumes", {}))
                compose_data["networks"].update(
                    component_compose.get("networks", {}))
        except (jinja2.TemplateNotFound, yaml.YAMLError) as e:
            msg = f"Failed to process template for {comp_id}: {e}"
            logger.error(msg);
            errors.append(msg)

    def _generate_other_files(self, comp_id, details, jinja_env, context,
                              errors):
        for file_config in details.get("other_files", []):
            template_name, output_path_str = file_config[0].get(
                "template"), file_config[0].get("destination")
            if not template_name or not output_path_str:
                errors.append(
                    f"Incomplete file config for {comp_id}: {file_config}")
                continue
            try:
                template = jinja_env.get_template(template_name)
                rendered_content = template.render(context)
                full_output_path = self.output_dir / output_path_str
                full_output_path.parent.mkdir(parents=True, exist_ok=True)
                with open(full_output_path, "w") as f:
                    f.write(rendered_content)
                logger.info(f"Generated {full_output_path}")
            except (jinja2.TemplateNotFound, IOError) as e:
                msg = f"Failed to generate {output_path_str} for {comp_id}: {e}"
                logger.error(msg);
                errors.append(msg)