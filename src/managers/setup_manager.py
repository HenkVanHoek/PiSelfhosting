import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Tuple

import jinja2
import yaml

from managers.component_manager import ComponentManager

logger = logging.getLogger(__name__)


class SetupManager:
    """Handles the generation of deployment files based on user selections."""

    DOCKER_COMPOSE_TEMPLATE = "docker-compose.template.yml"

    def __init__(self, component_manager: ComponentManager, output_dir: Path):
        self.component_manager = component_manager
        self.output_dir = output_dir
        self.template_base_path = (
            Path(self.component_manager.metadata_file).parent.parent
            / "component_templates"
        )
        logging.info(
            f"SetupManager initialized. " f"Output directory: {self.output_dir}"
        )

    def prepare_deployment_package(
        self,
        selected_components: List[str],
        user_variables: Dict[str, Any],
        managed_devices: List[Dict[str, Any]],
    ) -> Tuple[bool, Any]:
        """
        Main entry point to generate all necessary
        configuration files for a deployment.
        """
        self.output_dir.mkdir(parents=True, exist_ok=True)
        errors = []
        # --- MODIFIED: Added autoescape to resolve Bandit security warning ---
        jinja_env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(self.template_base_path),
            autoescape=jinja2.select_autoescape(),
        )

        first_device, *_ = managed_devices
        render_context = {
            **user_variables,
            "PISelfhosting_HOST_IP": first_device.get("ip", "127.0.0.1"),
            "PISelfhosting_DATA_PATH": "~/piselfhosting_data",
        }

        try:
            template_str = json.dumps(render_context)
            template = jinja_env.from_string(template_str)
            rendered_str = template.render(render_context)
            final_context = json.loads(rendered_str)
        except Exception as e:
            errors.append(f"Error during nested variable resolution: {e}")
            return False, errors

        # --- MODIFIED: Added explicit type hint to resolve mypy error ---
        compose_data: Dict[str, Any] = {"services": {}, "volumes": {}, "networks": {}}

        for component_id in selected_components:
            details = self.component_manager.get_component_details(component_id)
            if not details:
                errors.append(
                    f"Could not find metadata for component:" f" {component_id}"
                )
                continue

            self._merge_docker_compose_template(
                component_id, jinja_env, compose_data, final_context, errors
            )

        if not errors:
            compose_path = self.output_dir / "docker-compose.yml"
            with open(compose_path, "w") as f:
                yaml.dump(compose_data, f, default_flow_style=False, sort_keys=False)

            final_context["selected_components"] = selected_components
            context_path = self.output_dir / "deployment_context.json"
            with open(context_path, "w") as f:
                json.dump(final_context, f, indent=2)

        if errors:
            return False, errors
        return True, str(self.output_dir)

    def _merge_docker_compose_template(
        self, comp_id, jinja_env, compose_data, context, errors
    ):
        try:
            template_path = Path(comp_id) / self.DOCKER_COMPOSE_TEMPLATE
            template = jinja_env.get_template(str(template_path))
            rendered_content = template.render(**context)
            component_compose = yaml.safe_load(rendered_content)
            if component_compose:
                compose_data["services"].update(component_compose.get("services", {}))
                compose_data["volumes"].update(component_compose.get("volumes", {}))
                compose_data["networks"].update(component_compose.get("networks", {}))
        except Exception as e:
            errors.append(f"Failed to process template for {comp_id}: {e}")
