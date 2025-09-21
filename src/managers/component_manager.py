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

    def create_component(self, component_id: str, component_name: str):
        """Creates the folder structure and initial files for a new component."""
        components = self._components_data.setdefault("components", {})
        if component_id in components:
            raise ValueError(f"Component '{component_id}' already exists.")

        new_comp_path = self.templates_path / component_id
        new_comp_path.mkdir(exist_ok=True)
        (new_comp_path / "template-config").mkdir(exist_ok=True)
        (new_comp_path / "docker-compose.template.yml").write_text(
            f"version: '3.8'\n\nservices:\n  # Service for {component_name}\n"
        )
        (new_comp_path / "template-config" / "variables.json").write_text(
            json.dumps({"variables": []}, indent=2)
        )

        components[component_id] = {
            "name": component_name,
            "group": self.get_piselfhosting_meta().get("default_group", None),
            "description": "",
            "has_ui": False,
            "has_configuration": False,
            "depends_on": [],
            "required_variables": [],
        }
        self._save_metadata()

    def get_docker_service_name(self, component_id: str) -> str:
        component_details = self.get_component_details(component_id)
        if component_details:
            return component_details.get("docker_service_name", component_id)
        return component_id

    def update_component_metadata(self, component_id: str, update_data: Dict[str, Any]):
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

    def update_component_group(self, component_id: str, new_group_id: str):
        components = self._components_data.get("components", {})
        if component_id in components:
            components[component_id]["group"] = new_group_id
            self._save_metadata()
        else:
            raise KeyError(f"Component '{component_id}' not found.")

    def get_piselfhosting_meta(self) -> Dict[str, Any]:
        return self._components_data.get("_piselfhosting", {})

    def update_group_order(self, new_order: List[str]):
        piselfhosting_meta = self._components_data.setdefault("_piselfhosting", {})
        piselfhosting_meta["group_order"] = new_order
        self._save_metadata()

    def update_components_order(self, new_order: List[str]):
        piselfhosting_meta = self._components_data.setdefault("_piselfhosting", {})
        piselfhosting_meta["components_order"] = new_order
        self._save_metadata()

    # --- NEW: Method to delete a group if it's not in use ---
    def delete_group(self, group_id: str):
        """Deletes a group if no components are currently assigned to it."""
        all_components = self.get_all_components()
        is_in_use = any(comp.get("group") == group_id for comp in all_components)
        if is_in_use:
            raise ValueError(
                f"Group '{group_id}' is still in use and cannot be deleted."
            )

        piselfhosting_meta = self._components_data.setdefault("_piselfhosting", {})

        if (
            "group_rules" in piselfhosting_meta
            and group_id in piselfhosting_meta["group_rules"]
        ):
            del piselfhosting_meta["group_rules"][group_id]

        if (
            "group_order" in piselfhosting_meta
            and group_id in piselfhosting_meta["group_order"]
        ):
            piselfhosting_meta["group_order"].remove(group_id)

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

    def delete_component(self, component_id: str):
        """Deletes a component, its metadata, and its template files."""
        components = self._components_data.get("components", {})
        if component_id not in components:
            raise KeyError(f"Component '{component_id}' not found.")

        # 1. Remove from metadata
        del components[component_id]

        # 2. Remove from master order list
        piselfhosting_meta = self._components_data.get("_piselfhosting", {})
        if (
            "components_order" in piselfhosting_meta
            and component_id in piselfhosting_meta["components_order"]
        ):
            piselfhosting_meta["components_order"].remove(component_id)

        # 3. Delete the component's directory from the filesystem
        component_path = self.templates_path / component_id
        if component_path.exists() and component_path.is_dir():
            try:
                # Use rmtree to delete the directory and all its contents
                import shutil

                shutil.rmtree(component_path)
                logger.info(f"Deleted component directory: {component_path}")
            except OSError as e:
                logger.error(f"Error deleting directory {component_path}: {e}")
                # Re-add component to metadata if cleanup failed, to avoid data loss
                components[component_id] = self.get_component_details(component_id)
                self._save_metadata()
                raise e

        # 4. Save the updated metadata file
        self._save_metadata()
