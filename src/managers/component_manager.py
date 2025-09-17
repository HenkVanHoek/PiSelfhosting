import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class ComponentManager:
    """Manages loading and querying of component metadata."""

    def __init__(self, metadata_file: str):
        self.metadata_file = metadata_file
        self._components_data = self._load_metadata()
        self._enrich_components_with_variables()
        logger.info("ComponentManager initialized and all component data loaded.")

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

    def _enrich_components_with_variables(self):
        for comp_id, comp_details in self._components_data.items():
            if not comp_id.startswith("_") and comp_details.get("has_configuration"):
                try:
                    template_dir = (
                        Path(self.metadata_file).parent.parent
                        / "component_templates"
                        / comp_id
                    )
                    variables_file_path = (
                        template_dir / "template-config" / "variables.json"
                    )
                    if variables_file_path.exists():
                        with open(variables_file_path, "r") as f:
                            data = json.load(f)
                            self._components_data[comp_id]["required_variables"] = (
                                data.get("variables", [])
                            )
                    else:
                        self._components_data[comp_id]["required_variables"] = []
                except (FileNotFoundError, json.JSONDecodeError, TypeError) as e:
                    logger.error(f"Error processing variables for {comp_id}: {e}")
                    self._components_data[comp_id]["required_variables"] = []

    def get_component_order(self) -> list[str]:
        return self._components_data.get("_piselfhosting", {}).get(
            "components_order", []
        )

    def sort_components_by_master_order(self, component_ids: list[str]) -> list[str]:
        """Sorts a given list of component IDs based on the master order."""
        master_order = self.get_component_order()
        order_map = {comp_id: i for i, comp_id in enumerate(master_order)}
        return sorted(
            component_ids, key=lambda cid: order_map.get(cid, len(master_order))
        )

    def get_all_components(self) -> list[dict]:
        all_component_ids = [
            comp_id for comp_id in self._components_data if not comp_id.startswith("_")
        ]
        sorted_ids = self.sort_components_by_master_order(all_component_ids)
        sorted_components_list = []
        for comp_id in sorted_ids:
            component_data = self.get_component_details(comp_id)
            if component_data:
                new_data = component_data.copy()
                new_data["id"] = comp_id
                sorted_components_list.append(new_data)
        return sorted_components_list

    def get_component_details(self, component_id: str) -> dict | None:
        return self._components_data.get(component_id)

    # --- NEW METHOD ---
    # This is the new authoritative method for determining the Docker-safe
    # service name from a given component ID.
    @staticmethod
    def get_docker_service_name(component_id: str) -> str:
        """
        Sanitizes a component ID to be a valid Docker Compose service name.
        The current convention is to remove hyphens.
        """
        return component_id.replace("-", "")

    def get_uniqueness_groups(self) -> dict[str, list]:
        groups: dict[str, list] = {}
        for comp_data in self.get_all_components():
            group_name = comp_data.get("uniqueness_group")
            if group_name:
                if group_name not in groups:
                    groups[group_name] = []
                groups[group_name].append(comp_data.get("id"))
        return groups

    def get_all_components_dict(self) -> dict:
        return {k: v for k, v in self._components_data.items() if not k.startswith("_")}
