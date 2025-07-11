import json
import logging
import sys
from pathlib import Path

# Get a logger instance that will use the central configuration from app.py
logger = logging.getLogger(__name__)


class ComponentManager:
    """
    Manages the loading, validation, and retrieval of component metadata
    from a JSON file.
    """

    def __init__(self, metadata_path, docs_output_path=None):
        """
        Initializes the ComponentManager by loading component data.

        Args:
            metadata_path (str or Path): The path to the components_metadata.json file.
            docs_output_path (str or Path, optional): Path to generate documentation.
        """
        self.metadata_path = Path(metadata_path)
        self.docs_output_path = Path(docs_output_path) if docs_output_path else None
        self._components = self._load_components()

        if self.docs_output_path:
            # This could be used by a separate script to auto-generate docs
            # self._generate_docs()
            pass

    def _load_components(self):
        """
        Loads and validates component data from the JSON file.
        If the file is not found or is invalid, it logs a critical error and
        raises an exception to halt the application, preventing it from
        running in a broken state.
        """
        logger.info(f"Attempting to load component metadata from: {self.metadata_path}")

        if not self.metadata_path.exists():
            logger.critical(
                f"FATAL: Metadata file not found at '{self.metadata_path}'. "
                f"The application cannot start without this file."
            )
            raise FileNotFoundError(f"Required configuration file not found: {self.metadata_path}")

        try:
            with open(self.metadata_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                logger.info(f"Successfully loaded metadata for {len(data)} components.")
                return data
        except json.JSONDecodeError as e:
            logger.critical(f"FATAL: Failed to parse JSON from '{self.metadata_path}'. Error: {e}")
            raise  # Re-raise the exception to stop the application
        except IOError as e:
            logger.critical(f"FATAL: Could not read file at '{self.metadata_path}'. Error: {e}")
            raise

    def get_all_components(self):
        """
        Returns the entire dictionary of loaded components.
        """
        return self._components

    def get_component_details(self, component_id):
        """
        Returns the metadata for a single component.

        Args:
            component_id (str): The ID of the component (e.g., 'portainer').

        Returns:
            dict: The dictionary of metadata for the component, or None if not found.
        """
        return self._components.get(component_id)

    def get_uniqueness_groups(self):
        """
        Scans all components and returns a dictionary of uniqueness groups.
        This is used to enforce rules like "only one reverse proxy can be selected".

        Returns:
            dict: A dictionary where keys are group names (e.g., 'reverse_proxy')
                  and values are lists of component IDs belonging to that group.
        """
        groups = {}
        for component_id, details in self._components.items():
            # Skip internal metadata entries like '_piselfhosting'
            if component_id.startswith('_'):
                continue

            group_name = details.get('uniqueness_group')
            if group_name:
                if group_name not in groups:
                    groups[group_name] = []
                groups[group_name].append(component_id)

        logger.debug(f"Identified uniqueness groups: {groups}")
        return groups