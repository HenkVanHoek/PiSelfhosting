import json
import logging
import os

try:
    from config_tools.config_manager import ConfigManager
except ImportError:
    class ConfigManager:
        pass

logger = logging.getLogger(__name__)

class ComponentManager:
    """Manages loading and querying of component metadata."""

    def __init__(self, metadata_file: str):
        self.config = ConfigManager()
        self.metadata_file = metadata_file
        self._components_data = self._load_metadata()
        self.components = self._components_data
        logger.info("ComponentManager initialized and metadata loaded.")

    def _load_metadata(self) -> dict:
        try:
            with open(self.metadata_file, "r") as f:
                return json.load(f)
        except FileNotFoundError:
            logger.error(f"Metadata file not found at: {self.metadata_file}")
            raise
        except json.JSONDecodeError:
            logger.error(f"Error decoding JSON from: {self.metadata_file}")
            raise

    def get_all_components(self) -> list[dict]:
        sorted_components_list = []
        added_component_ids = set()
        component_order = self._components_data.get("_piselfhosting", {}).get(
            "components_order", []
        )
        for comp_id in component_order:
            if comp_id in self._components_data:
                component_data = self._components_data[comp_id].copy()
                component_data['id'] = comp_id
                sorted_components_list.append(component_data)
                added_component_ids.add(comp_id)
        for comp_id, comp_data in self._components_data.items():
            if not comp_id.startswith("_") and comp_id not in added_component_ids:
                component_data_with_id = comp_data.copy()
                component_data_with_id['id'] = comp_id
                sorted_components_list.append(component_data_with_id)
        return sorted_components_list

    def get_component_order(self) -> list[str]:
        """Retrieves the component processing order from the metadata."""
        return self._components_data.get("_piselfhosting", {}).get(
            "components_order", []
        )

    def get_component_details(self, component_id: str) -> dict | None:
        return self._components_data.get(component_id)

    def get_dashy_section(self) -> str | None:
        return self._components_data.get("_piselfhosting", {}).get("dashy_section")

    def get_uniqueness_groups(self) -> dict[str, list]:
        groups = {}
        for comp_data in self.get_all_components():
            group_name = comp_data.get("uniqueness_group")
            if group_name:
                if group_name not in groups:
                    groups[group_name] = []
                groups[group_name].append(comp_data.get('id'))
        return groups

    def get_required_variables(self, component_ids: list[str]) -> list[dict]:
        """
        Finds all components that require configuration and consolidates
        their required variables from their 'config/variables.json' files.
        """
        all_variables = {}
        for comp_id in component_ids:
            details = self.get_component_details(comp_id)
            if not details or not details.get("has_configuration"):
                continue
            try:
                template_path = self.config.get_component_template_path(comp_id)
                variables_file_path = os.path.join(template_path, "config", "variables.json")
                if os.path.exists(variables_file_path):
                    with open(variables_file_path, "r") as f:
                        variables = json.load(f)
                        for var in variables:
                            if 'id' in var:
                                all_variables[var['id']] = var
            except (FileNotFoundError, json.JSONDecodeError, TypeError) as e:
                logger.error(f"Error processing variables for {comp_id}: {e}")
        return list(all_variables.values())

    def get_all_components_dict(self) -> dict:
        """
        Returns the raw components data, excluding private keys like '_piselfhosting'.
        This is useful for quick lookups by component ID.
        """
        return {k: v for k, v in self._components_data.items() if not k.startswith("_")}