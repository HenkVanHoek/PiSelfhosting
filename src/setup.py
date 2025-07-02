# src/setup.py (REFACTORED TO USE A SINGLE JSON METADATA FILE)
import os
import jinja2
import yaml
import json
import sys

# Global FHS-compliant data root for all services
GLOBAL_DATA_ROOT = "/opt/piselfhosting/data"

# --- CONFIGURATION REFACTORED TO USE A SINGLE SOURCE OF TRUTH ---
# The components_metadata.json file is now the single source of truth for component data.
COMPONENTS_METADATA_FILENAME = "components_metadata.json"
SELECTED_COMPONENTS_FILENAME = "selected_components.txt"
DOCKER_COMPOSE_TEMPLATES_DIR = "templates"
DOCKER_COMPOSE_OUTPUT_DIR = "docker"

# Name for the unified Docker Compose file
UNIFIED_DOCKER_COMPOSE_FILENAME = "docker-compose.yml"


def get_project_root():
    """
    Determines the root directory of the PiSelfhosting project.
    """
    _current_script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(_current_script_dir)
    return project_root


def load_component_metadata(file_path=None):
    """
    Parses the components_metadata.json file and returns a dictionary
    containing the component order and all component data. This function
    replaces the old INI-based parser.
    """
    if file_path is None:
        project_root = get_project_root()
        file_path = os.path.join(project_root, COMPONENTS_METADATA_FILENAME)

    if not os.path.exists(file_path):
        error_msg = f"Error: '{COMPONENTS_METADATA_FILENAME}' not found at {file_path}.\n"
        sys.stderr.write(error_msg)
        raise FileNotFoundError(error_msg.strip())

    try:
        with open(file_path, 'r') as f:
            full_metadata = json.load(f)
    except json.JSONDecodeError as json_err:
        sys.stderr.write(f"Error parsing JSON from '{file_path}': {json_err}\n")
        raise

    # Extract the special _piselfhosting key for metadata about the project itself
    project_config = full_metadata.pop('_piselfhosting', {})
    components_order = project_config.get('components_order', [])

    # The rest of the dictionary is the component data
    all_component_data = full_metadata

    # If components_order is empty, populate it with all available components as a fallback
    if not components_order:
        components_order = list(all_component_data.keys())
        print(f"Warning: 'components_order' not found in '{COMPONENTS_METADATA_FILENAME}'. Using default key order.")

    # Ensure each component's data dictionary has a 'name' key for consistency
    for name, data in all_component_data.items():
        if 'name' not in data:
            data['name'] = name

    return {
        "components_order": components_order,
        "all_component_data": all_component_data
    }


def read_selected_components(file_path=None):
    """
    Reads the selected_components.txt file and returns a set of selected component names.
    Expected format: names separated by spaces, no quotes.
    """
    if file_path is None:
        project_root = get_project_root()
        file_path = os.path.join(project_root, SELECTED_COMPONENTS_FILENAME)

    if not os.path.exists(file_path):
        print(f"Warning: '{SELECTED_COMPONENTS_FILENAME}' not found at {file_path}. Assuming no components selected.")
        return set()

    temp_selected_set = set()
    try:
        with open(file_path, 'r') as f:
            content = f.read().strip()
            if content:
                components = [c for c in content.split() if c]
                temp_selected_set.update(components)
    except Exception as err:
        sys.stderr.write(f"Error reading or parsing '{SELECTED_COMPONENTS_FILENAME}': {err}\n")
        raise

    return temp_selected_set


# --- FUNCTION FOR DOCKER COMPOSE AND CONFIG FILE GENERATION ---
def generate_docker_compose_files(all_component_data, selected_components):
    """
    Generates individual docker-compose.yml files for selected components based on templates.
    Also generates specific application config files for components.
    Then merges individual compose files into a single docker-compose.yml.
    Reads all necessary variables from environment variables.
    """
    print("\n--- Generating Docker Compose files and Configs ---")
    project_root_in_container = get_project_root()
    templates_root_path = os.path.join(project_root_in_container, DOCKER_COMPOSE_TEMPLATES_DIR)
    output_path_in_container = os.path.join(project_root_in_container, DOCKER_COMPOSE_OUTPUT_DIR)

    os.makedirs(output_path_in_container, exist_ok=True)
    generated_configs_temp_path = os.path.join(output_path_in_container, "generated_configs")
    os.makedirs(generated_configs_temp_path, exist_ok=True)

    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(templates_root_path),
        trim_blocks=True,
        lstrip_blocks=True
    )

    # Read variables from environment
    domain_name = os.getenv("DOMAIN", "yourdomain.com")
    puid = os.getenv("PUID", "1000")
    pgid = os.getenv("PGID", "1000")
    host_ip = os.getenv("HOST_IP", "127.0.0.1")
    db_user = os.getenv("DB_USER", "piselfhosting_user")
    db_pass = os.getenv("DB_PASS", "secure_password")
    tz = os.getenv("TZ", "Europe/Amsterdam")
    admin_email = os.getenv("ADMIN_EMAIL", "admin@yourdomain.com")
    phpmyadmin_blowfish_secret = os.getenv("PHPMYADMIN_BLOWFISH_SECRET", os.urandom(32).hex())
    pma_host = os.getenv("PMA_HOST", "mariadb")
    frigate_rtsp_password = os.getenv("FRIGATE_RTSP_PASSWORD", "change_me_frigate_rtsp_pass")

    context = {
        "DOMAIN": domain_name, "PUID": puid, "PGID": pgid, "HOST_IP": host_ip,
        "DB_USER": db_user, "DB_PASS": db_pass, "TZ": tz, "ADMIN_EMAIL": admin_email,
        "PHPMYADMIN_BLOWFISH_SECRET": phpmyadmin_blowfish_secret, "PMA_HOST": pma_host,
        "FRIGATE_RTSP_PASSWORD": frigate_rtsp_password, "DATA_ROOT": GLOBAL_DATA_ROOT,
        "TRAEFIK_DASHBOARD_DOMAIN": f"traefik.{domain_name}" if "traefik" in selected_components else ""
    }
    print(f"DEBUG: Environment variables for substitution: {context}")

    individual_generated_compose_files = []
    generated_config_files_to_move = {}

    for component_name in selected_components:
        if component_name not in all_component_data:
            print(
                f"Warning: Component '{component_name}' is selected but not found in '{COMPONENTS_METADATA_FILENAME}'. Skipping.")
            continue

        # Handle Docker Compose Template
        compose_template_path = os.path.join(component_name, "docker-compose.template.yml")
        compose_output_filename = f"docker-compose.{component_name}.yml"
        compose_output_full_path = os.path.join(output_path_in_container, compose_output_filename)

        try:
            template_compose = env.get_template(compose_template_path)
            rendered_content_compose = template_compose.render(context)
            with open(compose_output_full_path, 'w') as f:
                f.write(rendered_content_compose)
            print(f"Generated: {compose_output_full_path}")
            individual_generated_compose_files.append(compose_output_full_path)
        except jinja2.exceptions.TemplateNotFound:
            print(
                f"Warning: Compose Template not found for '{component_name}' at {compose_template_path}. Skipping compose file generation.")
        except Exception as err:
            sys.stderr.write(f"Error generating Docker Compose for '{component_name}': {err}\n")
            raise

        # --- Handle specific application config file templates ---
        component_meta = all_component_data.get(component_name, {})
        config_templates = component_meta.get("config_templates", {})

        for template_name, final_location in config_templates.items():
            final_config_filename = os.path.basename(final_location)
            template_path_full = os.path.join(templates_root_path, component_name, "template-config", template_name)
            final_fhs_config_path = os.path.join(GLOBAL_DATA_ROOT, final_location).replace('\\', '/')

            try:
                # noinspection PyTypeChecker
                rendered_config_content = env.get_template(
                    os.path.join(component_name, "template-config", template_name)).render(context)

                temp_output_dir = os.path.join(generated_configs_temp_path, component_name)
                os.makedirs(temp_output_dir, exist_ok=True)
                temp_output_path = os.path.join(temp_output_dir, final_config_filename)

                with open(temp_output_path, 'w') as f:
                    f.write(rendered_config_content)

                print(f"Generated config file for {component_name}: {temp_output_path}")
                generated_config_files_to_move[temp_output_path] = final_fhs_config_path
            except jinja2.exceptions.TemplateNotFound:
                print(
                    f"Warning: Config template '{template_name}' not found at {template_path_full}. Skipping config generation.")
            except Exception as err:
                sys.stderr.write(f"Error generating config '{template_name}' for {component_name}: {err}\n")
                raise

    # Merge generated docker-compose files
    if individual_generated_compose_files:
        unified_compose_path_in_container = os.path.join(output_path_in_container, UNIFIED_DOCKER_COMPOSE_FILENAME)
        merge_docker_compose_files(individual_generated_compose_files, unified_compose_path_in_container)
        print(f"Successfully generated unified docker-compose.yml at '{unified_compose_path_in_container}'.")
    else:
        print("No individual Docker Compose files generated to merge.")

    # CRUCIAL: Print this map as JSON as the absolute last thing to stdout.
    print(json.dumps(generated_config_files_to_move))


def merge_docker_compose_files(file_paths, output_path):
    """
    Merges multiple Docker Compose YAML files into a single unified file.
    """
    print("\n--- Merging Docker Compose files ---")
    unified_compose_data = {'services': {}, 'volumes': {}, 'networks': {}}

    for file_path in file_paths:
        try:
            with open(file_path, 'r') as f:
                component_compose = yaml.safe_load(f)

            if not isinstance(component_compose, dict):
                print(f"Warning: {file_path} does not contain valid YAML. Skipping.")
                continue

            for section in ['services', 'volumes', 'networks']:
                if section in component_compose:
                    for key, value in component_compose[section].items():
                        if key not in unified_compose_data[section]:
                            unified_compose_data[section][key] = value
                        elif unified_compose_data[section][key] != value:
                            sys.stderr.write(
                                f"Warning: Conflicting definition for '{key}' in '{section}'. Keeping first one encountered.\n")

        except yaml.YAMLError as yaml_err:
            sys.stderr.write(f"Error parsing YAML from {file_path}: {yaml_err}. Skipping.\n")
        except Exception as err:
            sys.stderr.write(f"An unexpected error occurred during merge for {file_path}: {err}. Skipping.\n")

    try:
        with open(output_path, 'w') as f:
            yaml.dump(unified_compose_data, f, default_flow_style=False, sort_keys=False)
    except Exception as err:
        sys.stderr.write(f"Error writing unified docker-compose.yml to {output_path}: {err}\n")
        raise


if __name__ == "__main__":
    print("Running setup.py directly for testing purposes...")
    try:
        # For local testing, set a dummy remote project path if not set
        if 'REMOTE_PROJECT_PATH' not in os.environ:
            os.environ['REMOTE_PROJECT_PATH'] = get_project_root()

        # Load metadata from the new single source of truth
        parsed_data = load_component_metadata()

        print("\n--- Parsed Component Metadata ---")
        print(f"  Order: {parsed_data['components_order']}")
        # Optionally, print all component data for debugging
        # for name, props in parsed_data['all_component_data'].items():
        #     print(f"  Component: {name} -> {props}")

        selected_components_set = read_selected_components()
        print(f"\nSelected Components: {selected_components_set}")

        # Dummy environment variables for local testing
        if 'DOMAIN' not in os.environ: os.environ['DOMAIN'] = 'localtest.com'
        if 'PUID' not in os.environ: os.environ['PUID'] = '1000'
        # ... add other necessary env vars for testing if needed ...

        generate_docker_compose_files(
            parsed_data["all_component_data"],
            selected_components_set
        )
        print(f"\nSuccessfully generated config and compose files.")

    except FileNotFoundError as e:
        sys.stderr.write(f"FATAL: {e}\n")
    except Exception as e:
        sys.stderr.write(f"An unexpected fatal error occurred: {e}\n")