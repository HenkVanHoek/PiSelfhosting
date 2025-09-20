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
        except FileNotFoundError:
            logger.warning(f"Metadata file not found at {self.metadata_file}")
            return {"components": {}}
        except json.JSONDecodeError:
            logger.error(f"Error decoding JSON from {self.metadata_file}")
            return {"components": {}}

    def _save_metadata(self):
        """Saves the current components data back to the JSON file."""
        with open(self.metadata_file, "w", encoding="utf-8") as f:
            # --- FIX: This ensures the entire object is saved, preserving structure ---
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
        """Updates the metadata for a specific component."""
        components = self._components_data.setdefault("components", {})
        if component_id not in components:
            raise KeyError(f"Component '{component_id}' not found.")

        # --- FIX: Use update() to merge changes, not overwrite the whole object ---
        # This is safer and prevents accidental deletion of
        # keys like 'required_variables'
        components[component_id].update(update_data)
        self._save_metadata()

    def _get_component_config_path(self, component_id: str) -> Path:
        """Helper to get the path to a component's template-config folder."""
        return self.templates_path / component_id / "template-config"

    def update_component_variables(
        self, component_id: str, variables_data: Dict[str, Any]
    ):
        """Updates the variables.json for a component."""
        config_path = self._get_component_config_path(component_id)
        if not config_path.exists():
            config_path.mkdir(parents=True)
        variables_file = config_path / "variables.json"
        with open(variables_file, "w", encoding="utf-8") as f:
            json.dump(variables_data, f, indent=2, sort_keys=True)

    def get_component_template_content(self, component_id: str) -> str:
        """Reads the content of the docker-compose.template.yml for a component."""
        template_file = (
            self.templates_path / component_id / "docker-compose.template.yml"
        )
        try:
            with open(template_file, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            return f"# Template for {component_id} not found.\n"

    def update_component_template_content(self, component_id: str, content: str):
        """Writes new content to the docker-compose.template.yml for a component."""
        component_path = self.templates_path / component_id
        if not component_path.exists():
            component_path.mkdir(parents=True)
        template_file = component_path / "docker-compose.template.yml"
        with open(template_file, "w", encoding="utf-8") as f:
            f.write(content)
