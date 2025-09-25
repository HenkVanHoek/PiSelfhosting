import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)


class ComponentManager:
    """Manages component metadata and template files."""

    def __init__(self, templates_path: str, metadata_file_path: str):
        self.templates_path = Path(templates_path)
        self.metadata_file = Path(metadata_file_path)
        self._components_data = self._load_metadata()
        # --- DEFINITIVE FIX: Load all variables into a separate cache ---
        self._variables_cache = self._load_all_variables()

    def _load_metadata(self) -> Dict[str, Any]:
        """Loads the main components metadata file."""
        try:
            with open(self.metadata_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.error(f"Error loading metadata: {e}")
            return {"_piselfhosting": {}, "components": {}}

    # --- DEFINITIVE FIX: Create a single source of truth for variables ---
    def _load_all_variables(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Scans all component directories for variables.json and loads them
        into a central cache. This is now the SST for variables.
        """
        variables = {}
        components = self._components_data.get("components", {})
        for comp_id in components:
            variables_file = self._get_component_config_path(comp_id) / "variables.json"
            if variables_file.exists():
                try:
                    with open(variables_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        variables[comp_id] = data.get("variables", [])
                except (json.JSONDecodeError, TypeError) as e:
                    logger.error(f"Error loading variables for {comp_id}: {e}")
                    variables[comp_id] = []
            else:
                variables[comp_id] = []
        return variables

    def _save_metadata(self):
        """Saves the current components data back to the JSON file."""
        with open(self.metadata_file, "w", encoding="utf-8") as f:
            json.dump(self._components_data, f, indent=2, sort_keys=True)

    def get_all_components(self) -> List[Dict[str, Any]]:
        """Returns a list of all components with their essential data."""
        components = self._components_data.get("components", {})
        # --- DEFINITIVE FIX: Merge variables on-the-fly for a complete view ---
        all_comps = []
        for comp_id, comp_data in components.items():
            full_data = comp_data.copy()
            full_data["id"] = comp_id
            full_data["required_variables"] = self._variables_cache.get(comp_id, [])
            all_comps.append(full_data)
        return all_comps

    def get_component_details(self, component_id: str) -> Optional[Dict[str, Any]]:
        """
        Returns the full details for a single component, merging metadata
        and variables from their respective sources.
        """
        component_data = self._components_data.get("components", {}).get(component_id)
        if not component_data:
            return None
        # --- DEFINITIVE FIX: Merge the SST for variables at read time ---
        details = component_data.copy()
        details["required_variables"] = self._variables_cache.get(component_id, [])
        return details

    def validate_component_configuration(
        self, component_id: str, template_content: str, variables: List[Dict[str, Any]]
    ):
        """
        Validates a component's template and variables against PiSelfhosting's
        architectural rules. Raises ValueError on failure.
        """
        _ = component_id
        try:
            template_data = yaml.safe_load(template_content)
        except yaml.YAMLError as e:
            raise ValueError(f"Template is not valid YAML: {e}") from e

        if not isinstance(template_data, dict):
            raise ValueError("Template must be a YAML mapping (dictionary).")

        if "version" in template_data:
            raise ValueError(
                "Template contains an obsolete top-level 'version' key. "
                "Please remove it to comply with the modern Compose Specification."
            )

        template_vars = set(re.findall(r"\{\{\s*(\w+)", template_content))
        defined_vars = {var["id"] for var in variables}

        piselfhosting_meta = self.get_piselfhosting_meta()
        global_vars = set(piselfhosting_meta.get("global_variables", []))
        allowed_vars = defined_vars.union(global_vars)

        for used_var in template_vars:
            if used_var == "component_version":
                continue
            if used_var not in allowed_vars:
                raise ValueError(f"Template uses undefined variable: '{used_var}'")

        for var_id in defined_vars:
            if var_id not in template_vars:
                raise ValueError(f"Variable '{var_id}' is defined but not used")

    def create_component(self, component_id: str, component_name: str):
        """Creates the folder structure and initial files for a new component."""
        components = self._components_data.setdefault("components", {})
        if component_id in components:
            raise ValueError(f"Component '{component_id}' already exists.")

        new_comp_path = self.templates_path / component_id
        new_comp_path.mkdir(exist_ok=True)
        (new_comp_path / "template-config").mkdir(exist_ok=True)
        (new_comp_path / "docker-compose.template.yml").write_text(
            f"services:\n  # Service for {component_name}\n"
        )
        (new_comp_path / "template-config" / "variables.json").write_text(
            json.dumps({"variables": []}, indent=2)
        )

        components[component_id] = {
            "name": component_name,
            "group": self.get_piselfhosting_meta().get("default_group", None),
            "description": "",
            "has_ui": False,
            "has_configuration": True,
            "depends_on": [],
        }
        self._save_metadata()
        # Refresh the variables cache to include the new empty list
        self._variables_cache[component_id] = []

    def get_docker_service_name(self, component_id: str) -> str:
        # Use the on-the-fly merged details
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

    def get_uniqueness_groups(self) -> Dict[str, Any]:
        piselfhosting_meta = self.get_piselfhosting_meta()
        return piselfhosting_meta.get("group_rules", {})

    def sort_components_by_master_order(self, component_ids: List[str]) -> List[str]:
        master_order = self.get_piselfhosting_meta().get("components_order", [])
        order_map = {comp_id: i for i, comp_id in enumerate(master_order)}
        return sorted(
            component_ids, key=lambda cid: order_map.get(cid, len(master_order))
        )

    def update_group_order(self, new_order: List[str]):
        piselfhosting_meta = self._components_data.setdefault("_piselfhosting", {})
        piselfhosting_meta["group_order"] = new_order
        self._save_metadata()

    def update_components_order(self, new_order: List[str]):
        piselfhosting_meta = self._components_data.setdefault("_piselfhosting", {})
        piselfhosting_meta["components_order"] = new_order
        self._save_metadata()

    def delete_group(self, group_id: str):
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
        # --- DEFINITIVE FIX: This method ONLY writes to variables.json ---
        config_path = self._get_component_config_path(component_id)
        config_path.mkdir(parents=True, exist_ok=True)
        with open(config_path / "variables.json", "w", encoding="utf-8") as f:
            json.dump(variables_data, f, indent=2, sort_keys=True)
        # Refresh the in-memory cache to reflect the change immediately.
        self._variables_cache[component_id] = variables_data.get("variables", [])

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
        component_path.mkdir(parents=True, exist_ok=True)
        with open(
            component_path / "docker-compose.template.yml", "w", encoding="utf-8"
        ) as f:
            f.write(content)

    def delete_component(self, component_id: str):
        components = self._components_data.get("components", {})
        if component_id not in components:
            raise KeyError(f"Component '{component_id}' not found.")
        del components[component_id]
        piselfhosting_meta = self._components_data.get("_piselfhosting", {})
        if (
            "components_order" in piselfhosting_meta
            and component_id in piselfhosting_meta["components_order"]
        ):
            piselfhosting_meta["components_order"].remove(component_id)
        component_path = self.templates_path / component_id
        if component_path.exists() and component_path.is_dir():
            try:
                import shutil

                shutil.rmtree(component_path)
                logger.info(f"Deleted component directory: {component_path}")
            except OSError as e:
                logger.error(f"Error deleting directory {component_path}: {e}")
                self._save_metadata()
                raise e
        self._save_metadata()
