# /home/PiSelfhosting/scripts/dashy_tile_config_tool.py

import os
import yaml
import sys

# Define base directory (consistent with your existing setup)
BASE_DIR = "/app/piselfhosting" # Changed for Docker container context
DASHY_CONFIG_PATH = os.path.join(BASE_DIR, "docker", "dashy", "config", "conf.yml")
COMPONENTS_LIST_FILE = os.path.join(BASE_DIR, "scripts", "components_list.txt")
SELECTED_COMPONENTS_FILE = os.path.join(BASE_DIR, "scripts", "selected_components.txt")


def get_env_variable(key):
    """Loads a variable from the container's environment."""
    return os.getenv(key, "")

def parse_components_list():
    """Parses components_list.txt and returns a dictionary of component data."""
    component_data = {}
    if not os.path.exists(COMPONENTS_LIST_FILE):
        print(f"Error: Component list file not found at {COMPONENTS_LIST_FILE}.")
        return {}

    current_component_name = ""
    with open(COMPONENTS_LIST_FILE, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            if line.startswith('[') and line.endswith(']'):
                current_component_name = line[1:-1]
                component_data[current_component_name] = {}
            elif '=' in line and current_component_name:
                key, value = line.split('=', 1)
                component_data[current_component_name][key.strip()] = value.strip()
    return component_data

def get_selected_components():
    """Reads selected_components.txt and returns a set of selected component names."""
    selected = set()
    if os.path.exists(SELECTED_COMPONENTS_FILE):
        try:
            with open(SELECTED_COMPONENTS_FILE, 'r') as f:
                content = f.read().strip()
                components = content.replace('"', '').split(' ')
                selected.update(c for c in components if c)
        except Exception as e:
            print(f"Warning: Could not read selected_components.txt ({e}). Assuming no components selected.")
    return selected

def update_dashy_config():
    """
    Updates the Dashy conf.yml to add/update common service tiles.
    """
    domain = get_env_variable("DOMAIN")
    if not domain:
        print("Error: DOMAIN variable not found in environment. Ensure .env is loaded correctly.")
        sys.exit(1)

    if not os.path.exists(DASHY_CONFIG_PATH):
        print(f"Warning: Dashy config file not found at {DASHY_CONFIG_PATH}. Cannot add tiles.")
        sys.exit(1)

    all_components_data = parse_components_list()
    selected_components = get_selected_components()

    # The 'docker' component is now 'docker-monitor' in components_list.txt.
    # So no special handling needed here for component name mapping.

    try:
        with open(DASHY_CONFIG_PATH, 'r') as f:
            dashy_data = yaml.safe_load(f)
            if dashy_data is None:
                dashy_data = {}

        print(f"Existing Dashy config loaded from {DASHY_CONFIG_PATH}")

        # Ensure pageInfo is correctly set in English
        dashy_data['pageInfo'] = {
            'title': 'PiSelfhosting Dashboard',
            'description': 'Overview of your self-hosted services',
            'navLinks': [
                {'title': 'GitHub', 'path': 'https://github.com/your-username/your-repo'}, # Adjust this
                {'title': 'Docs', 'path': 'https://dashy.to/docs/'}
            ],
            'footerText': 'Powered by Dashy'
        }

        # Ensure appConfig is correctly set, including language to English
        dashy_data['appConfig'] = {
            'theme': 'material', # You can change this later
            'layout': 'auto',
            'iconSize': 'medium',
            'language': 'en' # Set language to English explicitly
        }

        # Crucial step: Clear all existing sections to prevent duplicates
        # and ensure a clean, English-only section structure.
        dashy_data['sections'] = []

        # Define desired order of sections
        section_order = ['General Services', 'Smart Home', 'Network Services', 'Storage & Network']

        sections_dict = {
            'General Services': {'name': 'General Services', 'icon': 'fa-solid fa-server', 'items': []},
            'Smart Home': {'name': 'Smart Home', 'icon': 'fa-solid fa-house', 'items': []},
            'Network Services': {'name': 'Network Services', 'icon': 'fa-solid fa-network-wired', 'items': []},
            'Storage & Network': {'name': 'Storage & Network', 'icon': 'fa-solid fa-cloud', 'items': []},
        }

        for comp_name in selected_components:
            comp_info = all_components_data.get(comp_name, {})

            # --- Removed the specific 'if comp_name == 'docker':' block ---
            # --- The component name in components_list.txt is now 'docker-monitor',
            # --- so it will be processed like any other component using its config_paths.

            if comp_info.get('dashy_tile_section') and comp_info.get('dashy_tile_url_suffix'):
                section_name = comp_info['dashy_tile_section']

                if section_name not in sections_dict:
                    print(f"Warning: Component '{comp_name}' defines unknown Dashy section '{section_name}'. Adding it as a new section.")
                    sections_dict[section_name] = {'name': section_name, 'icon': 'fas fa-box', 'items': []}
                    if section_name not in section_order:
                        section_order.append(section_name)

                tile_url = f"http://{domain}{comp_info['dashy_tile_url_suffix']}"

                status_check = comp_info.get('dashy_tile_status_check', 'True').lower() == 'true'

                sections_dict[section_name]['items'].append({
                    'title': comp_info['description'].replace('(Web-based MariaDB Manager)', '').strip(),
                    'description': comp_info['description'],
                    'icon': comp_info['dashy_tile_icon'],
                    'url': tile_url,
                    'statusCheck': status_check
                })
                print(f"Info: Adding tile for '{comp_name}' to '{section_name}' section.")

        # Reconstruct sections in desired order
        final_sections = []
        for section_name in section_order:
            if section_name in sections_dict:
                section = sections_dict[section_name]
                section['items'].sort(key=lambda x: x['title'])
                if section['items']: # Only add section if it has items
                    final_sections.append(section)

        dashy_data['sections'] = final_sections


        with open(DASHY_CONFIG_PATH, 'w') as f:
            yaml.dump(dashy_data, f, indent=2, sort_keys=False)
        print(f"✅ Dashy conf.yml successfully updated at: {DASHY_CONFIG_PATH}")

    except yaml.YAMLError as e:
        print(f"❌ Error parsing or writing Dashy configuration ({e}). Cannot update Dashy tiles.")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected error updating Dashy configuration: {e}")
        sys.exit(1)

if __name__ == "__main__":
    update_dashy_config()
    # BASE_DIR_HOST is passed as an environment variable by the wrapper script
    host_base_dir = os.getenv('BASE_DIR_HOST', '/home/PiSelfhosting')
    print("Please restart Dashy to apply changes:")
    print(f"  bash {os.path.join(host_base_dir, 'scripts', 'restart-all.sh')} dashy")
    print("  (This script can be run at any time to synchronize Dashy tiles).")
