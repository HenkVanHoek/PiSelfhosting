# /home/PiSelfhosting/scripts/dashy_tile_config_tool.py
# REFACTORED TO USE components_metadata.json

import os
import yaml
import sys
import json

# Define FHS-compliant paths (consistent with setup.py)
# Assumes this script runs on the host or in a tool container with access to these paths.
BASE_DIR = "/opt/piselfhosting"
DASHY_CONFIG_PATH = os.path.join(BASE_DIR, "data", "dashy", "config", "conf.yml")
METADATA_FILE = "/home/PiSelfhosting/components_metadata.json"  # Absolute path to metadata on host
SELECTED_COMPONENTS_FILE = "/home/PiSelfhosting/selected_components.txt"  # Absolute path on host


def get_env_variable(key, default=""):
    """Loads a variable from the container's environment."""
    return os.getenv(key, default)


def load_component_metadata():
    """Parses components_metadata.json and returns a dictionary of component data."""
    if not os.path.exists(METADATA_FILE):
        sys.stderr.write(f"Error: Metadata file not found at {METADATA_FILE}.\n")
        return {}
    try:
        with open(METADATA_FILE, 'r') as f:
            metadata = json.load(f)
            # Verwijder de interne _piselfhosting sleutel als die bestaat
            metadata.pop('_piselfhosting', None)
            return metadata
    except Exception as e:
        sys.stderr.write(f"Error reading or parsing {METADATA_FILE}: {e}\n")
        return {}


def get_selected_components():
    """Reads selected_components.txt and returns a set of selected component names."""
    if not os.path.exists(SELECTED_COMPONENTS_FILE):
        sys.stderr.write(f"Warning: {SELECTED_COMPONENTS_FILE} not found. No tiles will be generated.\n")
        return set()
    try:
        with open(SELECTED_COMPONENTS_FILE, 'r') as f:
            content = f.read().strip()
            return set(c for c in content.split(' ') if c)
    except Exception as e:
        sys.stderr.write(f"Warning: Could not read {SELECTED_COMPONENTS_FILE} ({e}).\n")
        return set()


def update_dashy_config():
    """
    Updates the Dashy conf.yml to add/update service tiles based on components_metadata.json.
    """
    host_ip = get_env_variable("HOST_IP")
    if not host_ip:
        sys.stderr.write("Error: HOST_IP environment variable not set. Cannot build tile URLs.\n")
        sys.exit(1)

    if not os.path.exists(os.path.dirname(DASHY_CONFIG_PATH)):
        print(f"Info: Dashy config directory not found. Creating it...")
        os.makedirs(os.path.dirname(DASHY_CONFIG_PATH), exist_ok=True)

    all_components_data = load_component_metadata()
    selected_components = get_selected_components()

    if not all_components_data:
        sys.stderr.write("Could not load component metadata. Aborting.\n")
        sys.exit(1)

    try:
        dashy_data = {}
        if os.path.exists(DASHY_CONFIG_PATH):
            with open(DASHY_CONFIG_PATH, 'r') as f:
                dashy_data = yaml.safe_load(f) or {}

        # Define a default, clean structure for the dashboard
        dashy_data['pageInfo'] = {
            'title': 'PiSelfhosting Dashboard',
            'navLinks': [{'title': 'GitHub', 'path': 'https://github.com/HenkVanHoek/PiSelfhosting'}]
        }
        dashy_data['appConfig'] = {'theme': 'material', 'layout': 'auto', 'language': 'en'}

        sections_dict = {}
        section_order = ['General Services', 'Smart Home', 'Network Services', 'Media', 'Utilities']

        for comp_name in selected_components:
            comp_info = all_components_data.get(comp_name)

            if not comp_info or not comp_info.get('has_ui', False):
                continue

            section_name = comp_info.get('dashy_section', 'Utilities')
            if section_name not in sections_dict:
                sections_dict[section_name] = {'name': section_name, 'icon': 'fas fa-box', 'items': []}

            protocol = comp_info.get('protocol', 'http')
            port = comp_info.get('ui_port')
            url = f"{protocol}://{host_ip}:{port}"

            tile = {
                'title': comp_info.get('name', comp_name),
                'description': comp_info.get('description', ''),
                'icon': comp_info.get('icon', 'fas fa-server'),
                'url': url,
                'statusCheck': True
            }

            sections_dict[section_name]['items'].append(tile)
            print(f"Info: Adding tile for '{comp_name}' to section '{section_name}'.")

        # Reconstruct sections in desired order
        final_sections = []
        for section_name in section_order:
            if section_name in sections_dict and sections_dict[section_name]['items']:
                section = sections_dict[section_name]
                section['items'].sort(key=lambda x: x['title'])
                final_sections.append(section)

        dashy_data['sections'] = final_sections

        with open(DASHY_CONFIG_PATH, 'w') as f:
            yaml.dump(dashy_data, f, indent=2, sort_keys=False)
        print(f"✅ Dashy conf.yml successfully updated at: {DASHY_CONFIG_PATH}")

    except Exception as e:
        sys.stderr.write(f"❌ An unexpected error occurred: {e}\n")
        sys.exit(1)


if __name__ == "__main__":
    update_dashy_config()