import json
import logging
from collections import OrderedDict

# Assumption: ConfigManager is defined elsewhere and handles path configurations.
# It is mocked in all tests, so its concrete implementation is not critical here.
# We assume it exists for the application's runtime.
try:
    from config_tools.config_manager import ConfigManager
except ImportError:
    # Fallback to a dummy class if the module cannot be found,
    # as it is always mocked in practice (during tests).
    class ConfigManager:
        pass


logger = logging.getLogger(__name__)


class ComponentManager:
    """Manages loading and querying of component metadata."""

    def __init__(self, metadata_file: str):
        """
        Initializes the ComponentManager by loading the metadata.

        Args:
            metadata_file: The path to the components_metadata.json file.
        """
        self.config = ConfigManager()
        self.metadata_file = metadata_file
        self._components_data = self._load_metadata()
        # The test uses 'self.components' but the logic uses '_components_data'.
        # Aliasing for test compatibility while keeping internal logic consistent.
        self.components = self._components_data
        logger.info("ComponentManager initialized and metadata loaded.")

    def _load_metadata(self) -> dict:
        """Loads and parses the component metadata from the JSON file."""
        try:
            with open(self.metadata_file, "r") as f:
                return json.load(f)
        except FileNotFoundError:
            logger.error(f"Metadata file not found at: {self.metadata_file}")
            raise
        except json.JSONDecodeError:
            logger.error(f"Error decoding JSON from: {self.metadata_file}")
            raise

    def get_all_components(self) -> OrderedDict:
        """
        Returns an ordered dictionary of all components, sorted according
        to the 'components_order' key in the metadata.

        The internal '_piselfhosting' key is excluded from the result.
        """
        sorted_components = OrderedDict()
        # Fallback to an empty list if the order is not specified
        component_order = self._components_data.get("_piselfhosting", {}).get(
            "components_order", []
        )

        for comp_id in component_order:
            if comp_id in self._components_data:
                sorted_components[comp_id] = self._components_data[comp_id]

        # Add any components not listed in the sorting key to the end
        for comp_id, comp_data in self._components_data.items():
            if not comp_id.startswith("_") and comp_id not in sorted_components:
                sorted_components[comp_id] = comp_data

        return sorted_components

    def get_component_details(self, component_id: str) -> dict | None:
        """
        Retrieves the metadata for a single component.

        Args:
            component_id: The ID of the component to retrieve.

        Returns:
            A dictionary with the component's metadata, or None if not found.
        """
        return self._components_data.get(component_id)

    def get_dashy_section(self) -> str | None:
        """Retrieves the 'dashy_section' value from the metadata."""
        return self._components_data.get("_piselfhosting", {}).get("dashy_section")

    def get_uniqueness_groups(self) -> dict[str, list]:
        """
        Parses all components to find and group them by their 'uniqueness_group'.

        Returns:
            A dictionary where keys are group names and values are lists
            of component IDs belonging to that group.
        """
        groups = {}
        for comp_id, comp_data in self.get_all_components().items():
            group_name = comp_data.get("uniqueness_group")
            if group_name:
                if group_name not in groups:
                    groups[group_name] = []
                groups[group_name].append(comp_id)
        return groups
