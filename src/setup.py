# src/setup.py

import os
import configparser
import sys
import yaml # We'll need this for loading/dumping YAML
import paramiko
from string import Template # For easy variable substitution

# Define the expected path for components_list.txt relative to the project root
COMPONENTS_LIST_FILENAME = "components_list.txt"
SELECTED_COMPONENTS_FILENAME = "selected_components.txt"

# --- (Keep your existing get_project_root, parse_components_list, read_selected_components functions) ---


def generate_docker_compose_file(all_components_data, selected_components_set, output_dir=None, template_dir=None):
    """
    Generates the unified docker-compose.yml file based on selected components
    and environment variables.
    """
    if output_dir is None:
        output_dir = os.path.join(get_project_root(), 'docker')
    if template_dir is None:
        template_dir = os.path.join(get_project_root(), 'scripts', 'template')

    os.makedirs(output_dir, exist_ok=True)

    final_compose_data = {"version": "3.8", "services": {}, "volumes": {}, "networks": {}}

    env_vars = {
        'DOMAIN': os.environ.get('DOMAIN', 'yourdomain.com'),
        'PUID': os.environ.get('PUID', '1000'),
        'PGID': os.environ.get('PGID', '1000'),
    }
    print(f"DEBUG: Environment variables for substitution: {env_vars}")  # Debug print

    # Ensure the 'all_component_data' is used for template lookup
    # In the test, we pass mock_parsed_components_data['all_component_data'] directly.
    # So, 'all_components_data' here is essentially 'all_component_data' from parse_components_list.

    for component_name in selected_components_set:
        template_path = os.path.join(template_dir, component_name, 'docker-compose.template.yml')

        if not os.path.exists(template_path):
            print(f"Warning: Template not found for '{component_name}' at {template_path}. Skipping.")
            continue

        try:
            with open(template_path, 'r', encoding='utf-8') as f:
                template_content = f.read()

            print(f"\nDEBUG: --- Processing {component_name} ---")  # Debug print
            print(f"DEBUG: Read template_content for {component_name}:\n{template_content}")  # Debug print

            template = Template(template_content)
            substituted_content = template.substitute(**env_vars)

            print(f"DEBUG: Substituted content for {component_name}:\n{substituted_content}")  # Debug print

            component_compose_fragment = yaml.safe_load(substituted_content)

            print(f"DEBUG: YAML fragment loaded for {component_name}:\n{component_compose_fragment}")  # Debug print

            # --- Critical Check and Merge ---
            if 'services' in component_compose_fragment:
                # Iterate through services in the fragment to add them
                for service_name, service_config in component_compose_fragment['services'].items():
                    final_compose_data['services'][service_name] = service_config
                print(f"DEBUG: Merged services for {component_name}.")  # Debug print
            else:
                print(f"Warning: No 'services' key found in template for {component_name}. Skipping service merge.")

            if 'volumes' in component_compose_fragment:
                final_compose_data['volumes'].update(component_compose_fragment['volumes'])
                print(f"DEBUG: Merged volumes for {component_name}.")  # Debug print
            if 'networks' in component_compose_fragment:
                final_compose_data['networks'].update(component_compose_fragment['networks'])
                print(f"DEBUG: Merged networks for {component_name}.")  # Debug print

        except FileNotFoundError:
            print(f"Error: Template file not found for {component_name} at {template_path}.")
            continue
        except yaml.YAMLError as e:
            print(f"Error parsing YAML template for {component_name} from {template_path}: {e}")
            continue
        except KeyError as e:
            print(
                f"Error: Missing environment variable '{e.args[0]}' in template for {component_name}. Please ensure it's set in your environment or provided in the script.")
            # It's better to raise this for configuration errors during development
            raise
        except Exception as e:
            print(f"An unexpected error occurred while processing template for {component_name}: {e}")
            continue

    # Print the final dictionary before dumping to YAML
    print(f"\nDEBUG: Final compose data before writing:\n{final_compose_data}")

    final_output_path = os.path.join(output_dir, 'docker-compose.yml')
    try:
        with open(final_output_path, 'w', encoding='utf-8') as f:
            # Using default_flow_style=False ensures block style YAML (readable)
            # sort_keys=False is crucial to maintain the order of keys, which helps with diffs
            yaml.dump(final_compose_data, f, default_flow_style=False, sort_keys=False)
        print(f"\nSuccessfully generated unified docker-compose.yml at '{final_output_path}'.")
    except Exception as e:
        print(f"Error writing unified docker-compose.yml to '{final_output_path}': {e}")
        raise

def run_docker_compose_command(ssh_client, command, project_path=None):
    """
    Stub function for executing docker compose commands on a remote host via SSH.
    """
    if project_path is None:
        project_path = get_project_root() # Use get_project_root for default

    full_command = f"cd {project_path} && docker compose {command}"
    print(f"DEBUG: Executing remote command: {full_command}") # Debug print

    # Simulate SSH command execution (minimal stub)
    # In a real scenario, this would use ssh_client.exec_command
    # For the stub, we just return dummy values.
    # However, the test *patches* ssh_client.exec_command, so this
    # function will *use* the patched exec_command if it's called with the mock.

    # For the test to work, the stub needs to make the *actual* call
    # to the mocked ssh_client.exec_command.

    # This is how it should look in the real implementation to work with the mocks:
    stdin, stdout, stderr = ssh_client.exec_command(full_command, get_pty=True)

    stdout_output = []
    for line in iter(stdout.readline, ""):
        stdout_output.append(line.strip())

    stderr_output = stderr.read().strip() # read all stderr

    exit_status = stdout.channel.recv_exit_status()

    return exit_status == 0, "\n".join(stdout_output), stderr_output

def get_project_root():
    """
    Determines the root directory of the PiSelfhosting project.
    Assumes this script (setup.py) is located in the 'src' subdirectory
    and the project root is one level up from 'src'.
    """
    current_script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_script_dir)
    return project_root


def parse_components_list(file_path=None):
    """
    Parses the components_list.txt file (INI-like format) and returns a dictionary
    containing 'components_order' (list of component names) and 'all_component_data'
    (dictionary of component details).
    """
    if file_path is None:
        project_root = get_project_root()
        file_path = os.path.join(project_root, COMPONENTS_LIST_FILENAME)

    if not os.path.exists(file_path):
        raise FileNotFoundError(
            f"'{COMPONENTS_LIST_FILENAME}' not found at {file_path}. Please ensure it exists in the project root.")

    config = configparser.ConfigParser()
    config.optionxform = str

    components_order = []
    all_component_data = {}

    try:
        with open(file_path, 'r', encoding='utf-8') as f:  # Ensure encoding='utf-8'
            file_content = f.read()
            if not file_content.strip().startswith('[') and '[PiSelfhosting]' not in file_content:
                file_content = '[PiSelfhosting]\n' + file_content
            config.read_string(file_content)

        if 'PiSelfhosting' in config and 'COMPONENTS_ORDER' in config['PiSelfhosting']:
            order_string = config['PiSelfhosting']['COMPONENTS_ORDER']
            components_order = [c.strip() for c in order_string.split(',') if c.strip()]

        for section in config.sections():
            if section != 'PiSelfhosting':
                component_data = dict(config[section])
                component_data['name'] = section
                all_component_data[section] = component_data

    except configparser.Error as e:
        print(f"Error parsing '{COMPONENTS_LIST_FILENAME}' (INI format issue): {e}")
        raise
    except Exception as e:
        print(f"Error reading or parsing '{COMPONENTS_LIST_FILENAME}': {e}")
        raise

    return {
        "components_order": components_order,
        "all_component_data": all_component_data
    }


def read_selected_components(file_path=None):
    """
    Reads the selected_components.txt file and returns a set of selected component names.
    If the file does not exist, an empty set is returned.
    """
    if file_path is None:
        project_root = get_project_root()
        file_path = os.path.join(project_root, SELECTED_COMPONENTS_FILENAME)

    if not os.path.exists(file_path):
        print(f"'{SELECTED_COMPONENTS_FILENAME}' not found at {file_path}. Returning empty set.")
        return set()

    selected_components = set()
    try:
        with open(file_path, 'r', encoding='utf-8') as f:  # Ensure encoding='utf-8'
            content = f.read().strip()
            if content:
                selected_components.update(content.split())
    except Exception as e:
        print(f"Error reading or parsing '{SELECTED_COMPONENTS_FILENAME}': {e}")
        raise

    return selected_components


def select_components_interactively_and_save(components_data, selected_file_path=None):
    """
    Allows the user to interactively select components and saves their choices
    to the selected_components.txt file.

    Args:
        components_data (dict): Dictionary from parse_components_list containing
                                'components_order' and 'all_component_data'.
        selected_file_path (str, optional): Custom path for selected_components.txt.
                                            Defaults to project root.
    Returns:
        set: The set of newly selected components.
    """
    if selected_file_path is None:
        project_root = get_project_root()
        selected_file_path = os.path.join(project_root, SELECTED_COMPONENTS_FILENAME)

    components_order = components_data["components_order"]
    all_component_data = components_data["all_component_data"]

    current_selected = read_selected_components(selected_file_path)

    print("\n--- Select PiSelfhosting Components ---")
    print("Enter the numbers of the components you want to select/deselect.")
    print("Separate multiple numbers with spaces (e.g., '1 3 5').")
    print("Press Enter without input to finish selection.")
    print("Components marked with [x] are currently selected.")

    newly_selected = set(current_selected)  # Start with existing selection

    while True:
        print("\nAvailable Components:")
        for i, comp_name in enumerate(components_order):
            status = "[x]" if comp_name in newly_selected else "[ ]"
            description = all_component_data.get(comp_name, {}).get("description", "No description available.")
            print(f"{i + 1}. {status} {comp_name} - {description}")

        user_input = input("Your selection (numbers, space-separated, or Enter to confirm): ").strip()

        if not user_input:
            print("\nConfirming selection.")
            break

        try:
            choices = [int(num) for num in user_input.split()]
            for choice in choices:
                if 1 <= choice <= len(components_order):
                    comp_name = components_order[choice - 1]
                    if comp_name in newly_selected:
                        newly_selected.remove(comp_name)
                        print(f"'{comp_name}' deselected.")
                    else:
                        newly_selected.add(comp_name)
                        print(f"'{comp_name}' selected.")
                else:
                    print(
                        f"Warning: Invalid number '{choice}'. Please choose a number from 1 to {len(components_order)}.")
        except ValueError:
            print("Error: Invalid input. Please enter numbers separated by spaces.")

    # Save the selected components to file
    try:
        with open(selected_file_path, 'w', encoding='utf-8') as f:  # Ensure encoding='utf-8'
            f.write(" ".join(sorted(list(newly_selected))))  # Save as space-separated string
        print(f"\nSuccessfully saved selected components to '{selected_file_path}'.")
    except Exception as e:
        print(f"Error saving selected components to '{selected_file_path}': {e}")
        raise  # Re-raise the exception

    return newly_selected


# Example usage (for direct testing, can be removed later or guarded by if __name__ == "__main__":)
if __name__ == "__main__":
    print("Running setup.py directly for testing purposes...")
    try:
        # Test parse_components_list
        parsed_data = parse_components_list()
        print(f"Available components order: {parsed_data['components_order']}")
        print(f"All component data: {parsed_data['all_component_data']}")

        # Test read_selected_components
        selected_comps = read_selected_components()
        print(f"Initially selected components: {selected_comps}")

        # Test interactive selection and save
        final_selected = select_components_interactively_and_save(parsed_data)
        print(f"Final selected components: {final_selected}")

    except FileNotFoundError as e:
        print(e)
    except Exception as e:
        print(f"An unexpected error occurred: {e}")