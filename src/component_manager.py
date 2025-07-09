import json
import sys
from pathlib import Path

# A custom exception for clearer validation errors.
class ValidationError(ValueError):
    pass

class ComponentManager:
    """
    Manages the component data for the project.

    This class handles loading, validating, adding, updating, and deleting
    components from a central JSON configuration file.

    It is designed to be used as a context manager. When used in a 'with'
    statement, it ensures that the component documentation is automatically
    regenerated and saved upon exiting the context, but only if a documentation
    output path is provided.
    """

    def __init__(self, file_path="components.json", docs_output_path=None):
        """
        Initializes the ComponentManager.

        Args:
            file_path (str): The path to the JSON file storing component data.
            docs_output_path (str, optional): The path where the component
                                             documentation table should be saved.
                                             If None, documentation is not generated.
        """
        self.file_path = Path(file_path)
        self.docs_output_path = Path(docs_output_path) if docs_output_path else None
        self.components_data = self._load_data()

    def __enter__(self):
        """
        Enters the context manager, allowing operations on the manager.
        This is called when the 'with' statement is initiated.
        """
        print("ComponentManager context entered. Operations can now be performed.")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Exits the context manager and triggers documentation generation.

        This method is reliably called when the 'with' block is exited,
        either normally or due to an exception. If a 'docs_output_path' was
        provided, it generates the component documentation table.

        Args:
            exc_type: The exception type if an exception occurred in the 'with' block.
            exc_val: The exception value.
            exc_tb: The traceback.
        """
        if self.docs_output_path:
            print(f"Exiting ComponentManager context. Generating component documentation...")
            try:
                self.generate_component_table(self.docs_output_path)
                print(f"Successfully generated component documentation at: {self.docs_output_path}")
            except Exception as e:
                # Log errors that occur during this cleanup phase.
                print(f"Error generating documentation in ComponentManager __exit__: {e}", file=sys.stderr)
        
        # Returning False (or None) ensures that if an exception happened
        # inside the 'with' block, it gets re-raised.
        return False

    def _load_data(self):
        """Loads component data from the JSON file."""
        if not self.file_path.exists():
            return {}
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"Error loading {self.file_path}: {e}", file=sys.stderr)
            return {}

    def _save_data(self):
        """Saves the current component data to the JSON file."""
        try:
            with open(self.file_path, 'w', encoding='utf-8') as f:
                json.dump(self.components_data, f, indent=4, sort_keys=True)
        except IOError as e:
            print(f"Error saving to {self.file_path}: {e}", file=sys.stderr)
            raise

    # --- CRUD Operations ---

    def add_component(self, component_id, data):
        """Adds a new component after performing validation."""
        self._validate_component_id(component_id, is_new=True)

        if data.get('has_ui'):
            self._validate_ui_port_uniqueness(data.get('ui_port'), component_id_being_edited=None)
            self._validate_dashy_tile_fields(data)

        if data.get('is_reverse_proxy'):
            self._validate_single_reverse_proxy(data.get('is_reverse_proxy'), component_id_being_edited=None)

        if not data.get('name'):
            raise ValueError("Component name is required.")

        self.components_data[component_id] = data
        self._save_data()
        print(f"Component '{component_id}' added successfully.")

    def update_component(self, component_id, data):
        """Updates an existing component after validation."""
        self._validate_component_id(component_id, is_new=False)
        # Add similar validation logic here as in add_component for updates.
        self.components_data[component_id].update(data)
        self._save_data()
        print(f"Component '{component_id}' updated successfully.")

    def remove_component(self, component_id):
        """Removes a component from the data."""
        self._validate_component_id(component_id, is_new=False)
        del self.components_data[component_id]
        self._save_data()
        print(f"Component '{component_id}' removed successfully.")

    def get_component(self, component_id):
        """Retrieves a single component's data."""
        return self.components_data.get(component_id)

    def get_all_components(self):
        """Returns all component data."""
        return self.components_data

    # --- Validation Methods ---

    def _validate_component_id(self, component_id, is_new):
        """Validates the component ID format and existence."""
        if not isinstance(component_id, str) or not component_id.strip():
            raise ValidationError("Component ID must be a non-empty string.")
        if is_new and component_id in self.components_data:
            raise ValidationError(f"Component ID '{component_id}' already exists.")
        if not is_new and component_id not in self.components_data:
            raise ValidationError(f"Component ID '{component_id}' not found.")

    def _validate_ui_port_uniqueness(self, ui_port, component_id_being_edited):
        """Ensures that the UI port is unique across all components."""
        if ui_port is None:
            return
        for cid, data in self.components_data.items():
            if cid == component_id_being_edited:
                continue
            if data.get('ui_port') == ui_port:
                raise ValidationError(f"UI Port '{ui_port}' is already in use by component '{cid}'.")

    def _validate_dashy_tile_fields(self, data):
        """Validates that Dashy-related fields are present if has_ui is true."""
        if data.get('has_ui') and not data.get('dashy_image_path'):
            raise ValidationError("A 'dashy_image_path' is required for components with a UI.")

    def _validate_single_reverse_proxy(self, is_reverse_proxy, component_id_being_edited):
        """Ensures that only one component is marked as the reverse proxy."""
        if not is_reverse_proxy:
            return
        for cid, data in self.components_data.items():
            if cid == component_id_being_edited:
                continue
            if data.get('is_reverse_proxy'):
                raise ValidationError(f"A reverse proxy ('{cid}') is already defined. Only one is allowed.")

    # --- Documentation Generation ---

    def generate_component_table(self, output_path: Path):
        """
        Generates a Markdown table of all components and saves it to a file.
        
        Args:
            output_path (Path): The path object where the markdown file will be saved.
        """
        if not self.components_data:
            print("No components to document.", file=sys.stderr)
            return

        sorted_components = sorted(self.components_data.items(), key=lambda item: item[1].get('name', '').lower())

        md = [
            "# Supported Components\n",
            "This document is auto-generated based on the available components in the project. "
            "It provides an overview of each component, its purpose, and key details.\n",
            "**Note:** Components marked as 'Unique' belong to a group where only one can be selected for installation at a time.\n",
            "| Component Name | Description | Category | Has UI | Unique (Group) |",
            "|:---------------|:------------|:---------|:-------|:---------------|"
        ]

        for _, data in sorted_components:
            name = data.get('name', 'N/A')
            description = data.get('description', 'No description available.')
            category = data.get('category', 'General')
            has_ui = "✅ Yes" if data.get('has_ui') else "❌ No"
            
            uniqueness_group = data.get('uniqueness_group')
            if uniqueness_group:
                unique_col = f"✅ Yes (`{uniqueness_group}`)"
            else:
                unique_col = "❌ No"
            
            md.append(f"| **{name}** | {description} | {category} | {has_ui} | {unique_col} |")

        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write("\n".join(md))
        except IOError as e:
            print(f"Fatal: Could not write documentation to {output_path}. Error: {e}", file=sys.stderr)
            raise