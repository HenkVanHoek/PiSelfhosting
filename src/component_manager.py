import json
import logging
from pathlib import Path

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
            raise FileNotFoundError(
                f"Required configuration file not found: {self.metadata_path}"
            )

        try:
            with open(self.metadata_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                logger.info(f"Successfully loaded metadata for {len(data)} components.")
                return data
        except json.JSONDecodeError as e:
            logger.critical(
                f"FATAL: Failed to parse JSON from '{self.metadata_path}'. Error: {e}"
            )
            raise  # Re-raise the exception to stop the application
        except IOError as e:
            logger.critical(f"Failed to read metadata file: {e}")
            raise

    def get_all_components(self):
        """Returns all loaded component data."""
        return self._components

    def get_component_details(self, component_id):
        """
        Returns the details for a specific component.

        Args:
            component_id (str): The ID of the component (e.g., 'dashy').

        Returns:
            dict: The component's data, or None if not found.
        """
        return self._components.get(component_id)

    def get_uniqueness_groups(self):
        """
        Parses all components and returns a dictionary of uniqueness groups
        and the components belonging to them.

        Example:
            {"dashboard": ["dashy", "homepage"], "monitoring": ["glances"]}
        """
        groups = {}
        for component_id, data in self._components.items():
            if group_name := data.get("uniqueness_group"):
                if group_name not in groups:
                    groups[group_name] = []
                groups[group_name].append(component_id)
        return groups

    def generate_docs(self):
        """
        Generates a Markdown document from the component metadata.
        """
        if not self.docs_output_path:
            logger.warning(
                "No documentation output path specified. Skipping generation."
            )
            return

        logger.info(f"Generating component documentation at: {self.docs_output_path}")

        # Exclude the special _piselfhosting key
        component_order = self._components.get("_piselfhosting", {}).get(
            "components_order", []
        )
        if not component_order:
            # Fallback to all keys except the special one if order is not defined
            component_order = [k for k in self._components if k != "_piselfhosting"]

        # noinspection PyListCreation
        doc_content = ["# Supported Components\n\n"]
        doc_content.append(
            "This document is auto-generated based on the available components in "
            "`config/components_metadata.json`.\n\n"
        )

        for component_id in component_order:
            comp = self._components.get(component_id)
            if not comp:
                continue

            doc_content.append(f"## {comp.get('name', component_id.title())}\n\n")
            doc_content.append(f"**ID:** `{component_id}`\n\n")
            doc_content.append(
                f"{comp.get('description', 'No description available.')}\n\n"
            )

            if comp.get("has_ui"):
                doc_content.append(
                    f"- **Web Interface:** Yes (Port: {comp.get('ui_port', 'N/A')})\n"
                )
            else:
                doc_content.append("- **Web Interface:** No\n")

            doc_content.append("\n---\n\n")

        try:
            with open(self.docs_output_path, "w", encoding="utf-8") as f:
                f.write("".join(doc_content))
            logger.info("Successfully generated documentation.")
        except IOError as e:
            logger.error(f"Failed to write documentation file: {e}")
