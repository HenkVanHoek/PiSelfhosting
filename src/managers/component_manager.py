import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ComponentManager:
    """Manages component metadata and template files."""

    def __init__(self, templates_path: str, metadata_file_path: str):
        self.templates_path = Path(templates_path)
        self.metadata_file = Path(metadata_file_path)
        self._components_data = self._load_metadata()

    def _load_metadata(self) -> Dict[str, Any]:
        """Loads the main components metadata file."""
        try:
            with open(self.metadata_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.error(f"Error loading metadata: {e}")
            return {"_piselfhosting": {}, "components": {}}

    def _save_metadata(self):
        """Saves the current components data back to the JSON file."""
        with open(self.metadata_file, "w", encoding="utf-8") as f:
            json.dump(self._components_data, f, indent=2, sort_keys=True)

    def get_all_components(self) -> List[Dict[str, Any]]:
        """Returns a list of all components with their essential data."""
        components = self._components_data.get("components", {})
        return [
            {"id": comp_id, **comp_data} for comp_id, comp_data in components.items()
        ]

    def get_component_details(self, component_id: str) -> Optional[Dict[str, Any]]:
        """Returns the full details for a single component."""
        return self._components_data.get("components", {}).get(component_id)

    def get_docker_service_name(self, component_id: str) -> str:
        """Gets the docker service name for a component."""
        component_details = self.get_component_details(component_id)
        if component_details:
            return component_details.get("docker_service_name", component_id)
        return component_id

    def update_component_metadata(self, component_id: str, update_data: Dict[str, Any]):
        """Updates the metadata for a component and handles dynamic group creation."""
        components = self._components_data.setdefault("components", {})
        if component_id not in components:
            raise KeyError(f"Component '{component_id}' not found.")

        new_group_id = update_data.get("group")
        if new_group_id:
            piselfhosting_meta = self._components_data.setdefault("_piselfhosting", {})
            group_rules = piselfhosting_meta.setdefault("group_rules", {})

            if new_group_id not in group_rules:
                group_rules[new_group_id] = {
                    "name": new_group_id.replace("_", " ").title(),
                    "is_exclusive": False,
                }
                piselfhosting_meta.setdefault("group_order", []).append(new_group_id)

        components[component_id].update(update_data)
        self._save_metadata()

    def get_piselfhosting_meta(self) -> Dict[str, Any]:
        """Returns the _piselfhosting metadata block."""
        return self._components_data.get("_piselfhosting", {})

    def update_group_order(self, new_order: List[str]):
        """Updates the group_order list in the metadata."""
        piselfhosting_meta = self._components_data.setdefault("_piselfhosting", {})
        piselfhosting_meta["group_order"] = new_order
        self._save_metadata()

    # --- NEW: Method to save the component sort order ---
    def update_components_order(self, new_order: List[str]):
        """Updates the components_order list in the metadata."""
        piselfhosting_meta = self._components_data.setdefault("_piselfhosting", {})
        piselfhosting_meta["components_order"] = new_order
        self._save_metadata()

    def _get_component_config_path(self, component_id: str) -> Path:
        return self.templates_path / component_id / "template-config"

    def update_component_variables(
        self, component_id: str, variables_data: Dict[str, Any]
    ):
        config_path = self._get_component_config_path(component_id)
        if not config_path.exists():
            config_path.mkdir(parents=True)
        with open(config_path / "variables.json", "w", encoding="utf-8") as f:
            json.dump(variables_data, f, indent=2, sort_keys=True)

    def get_component_template_content(self, component_id: str) -> str:
        template_file = (
            self.templates_path / component_id / "docker-compose.template.yml"
        )
        try:
            with open(template_file, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            return f"# Template for {component_id} not found.\n"

    def update_component_template_content(self, component_id: str, content: str):
        component_path = self.templates_path / component_id
        if not component_path.exists():
            component_path.mkdir(parents=True)
        with open(
            component_path / "docker-compose.template.yml", "w", encoding="utf-8"
        ) as f:
            f.write(content)
