# src/setup.py (FINAL, VERIFIED COMPLETE AND CORRECT VERSION - ALL ENGLISH)
import os
import configparser
import jinja2
import yaml

# Global FHS-compliant data root for all services
GLOBAL_DATA_ROOT = "/opt/piselfhosting/data"

# Define the expected path for components_list.txt relative to the project root
COMPONENTS_LIST_FILENAME = "components_list.txt"
SELECTED_COMPONENTS_FILENAME = "selected_components.txt"
DOCKER_COMPOSE_TEMPLATES_DIR = "templates"  # Path to the templates directory (relative to project root)
DOCKER_COMPOSE_OUTPUT_DIR = "docker"  # Path where generated docker-compose files will be stored (relative to project root)

# NEW CONSTANT: Name for the unified Docker Compose file
UNIFIED_DOCKER_COMPOSE_FILENAME = "docker-compose.yml"


def get_project_root():
    """
    Determines the root directory of the PiSelfhosting project.
    Assumes this script (setup.py) is located in the 'src' subdirectory
    and the project root is one level up from 'src'.
    """
    current_script_dir = os.path.dirname(os.path.abspath(__file__))
    # This should be exactly one directory up from 'src'
    project_root = os.path.dirname(current_script_dir)
    return project_root


def parse_components_list(file_path=None):
    """
    Parses the components_list.txt file (INI-like format) and returns a dictionary
    where keys are component names and values are dictionaries of their properties.

    The 'COMPONENTS_ORDER' is extracted from the [PiSelfhosting] section.
    """
    if file_path is None:
        project_root = get_project_root()
        file_path = os.path.join(project_root, COMPONENTS_LIST_FILENAME)

    if not os.path.exists(file_path):
        raise FileNotFoundError(
            f"'{COMPONENTS_LIST_FILENAME}' not found at {file_path}. Please ensure it exists in the project root.")

    config = configparser.ConfigParser(allow_no_value=True, strict=False, comment_prefixes=('#', ';'))
    all_component_data = {}
    components_order = []

    try:
        config.read(file_path)

        # Get COMPONENTS_ORDER from the [PiSelfhosting] section
        if config.has_section('PiSelfhosting') and 'components_order' in config['PiSelfhosting']:
            order_str = config['PiSelfhosting']['components_order']
            components_order = [c.strip() for c in order_str.split(',') if c.strip()]

        # Process actual component sections, excluding [PiSelfhosting]
        for section in config.sections():
            if section == 'PiSelfhosting':  # Skip the metadata section
                continue

            component_name = section
            # Convert configparser's section (which is like a dict) to a regular dict
            component_properties = dict(config.items(section))

            # Ensure the 'name' property is explicitly set to the section name
            component_properties['name'] = component_name

            all_component_data[component_name] = component_properties

    except configparser.Error as config_err:
        print(f"Error parsing '{COMPONENTS_LIST_FILENAME}' with configparser: {config_err}")
        raise
    except Exception as err:
        print(f"An unexpected error occurred during parsing '{COMPONENTS_LIST_FILENAME}': {err}")
        raise

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
        # If the file doesn't exist, assume no components are selected yet (first run)
        print(f"Warning: '{SELECTED_COMPONENTS_FILENAME}' not found at {file_path}. Assuming no components selected.")
        return set()

    temp_selected_set = set()
    try:
        with open(file_path, 'r') as f:
            content = f.read().strip()
            if content:
                # Split by space, handle multiple spaces, and ensure no empty strings
                components = [c for c in content.split() if c]
                temp_selected_set.update(components)
    except Exception as err:
        print(f"Error reading or parsing '{SELECTED_COMPONENTS_FILENAME}': {err}")
        raise

    return temp_selected_set


# --- FUNCTION FOR DOCKER COMPOSE GENERATION ---
def generate_docker_compose_files(all_component_data, selected_components):
    """
    Generates individual docker-compose.yml files for selected components based on templates,
    then merges them into a single docker-compose.yml.
    Reads DOMAIN, PUID, PGID, HOST_IP, DB_USER, DB_PASS, TZ, REMOTE_PROJECT_PATH from environment variables
    within the Docker container.
    """
    print("\n--- Generating Docker Compose files ---")
    project_root_in_container = get_project_root()  # This is /app (Docker container path)
    templates_path = os.path.join(project_root_in_container, DOCKER_COMPOSE_TEMPLATES_DIR)
    output_path_in_container = os.path.join(project_root_in_container,
                                            DOCKER_COMPOSE_OUTPUT_DIR)  # This is /app/docker (Docker container path)

    # Get the actual remote project path on the host from environment variable
    # This variable is passed by the piselfhosting_installer.py script.
    # It will be like /home/hvhoek/PiSelfhosting
    remote_host_project_path = os.getenv("REMOTE_PROJECT_PATH",
                                         "/home/pi/PiSelfhosting")  # Fallback to a common default
    # Construct the full path to the docker output directory on the host
    remote_host_docker_output_path = os.path.join(remote_host_project_path, DOCKER_COMPOSE_OUTPUT_DIR).replace('\\',
                                                                                                               '/')  # Ensure Linux path separators

    os.makedirs(output_path_in_container, exist_ok=True)

    # Setup Jinja2 environment
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(templates_path),
        trim_blocks=True,
        lstrip_blocks=True
    )

    # Read variables from environment variables (provided by piselfhosting_installer.py)
    domain_name = os.getenv("DOMAIN", "yourdomain.com")
    puid = os.getenv("PUID", "1000")
    pgid = os.getenv("PGID", "1000")
    host_ip = os.getenv("HOST_IP", "127.0.0.1")
    db_user = os.getenv("DB_USER", "piselfhosting_user")
    db_pass = os.getenv("DB_PASS", "secure_password")
    tz = os.getenv("TZ", "Europe/Amsterdam")
    admin_email = os.getenv("ADMIN_EMAIL", "admin@yourdomain.com")

    context = {
        "DOMAIN": domain_name,
        "PUID": puid,
        "PGID": pgid,
        "HOST_IP": host_ip,
        "DB_USER": db_user,
        "DB_PASS": db_pass,
        "TZ": tz,
        "ADMIN_EMAIL": admin_email,
        "DATA_ROOT": GLOBAL_DATA_ROOT,
        "TRAEFIK_DASHBOARD_DOMAIN": f"traefik.{domain_name}" if "traefik" in selected_components else ""
    }
    print(f"DEBUG: Environment variables for substitution: {context}")

    individual_generated_files = []  # Renamed for clarity

    for component_name in selected_components:
        if component_name not in all_component_data:
            print(
                f"Warning: Component '{component_name}' found in selected_components.txt but not in components_list.txt. Skipping.")
            continue

        template_file = os.path.join(component_name, "docker-compose.template.yml")
        output_file_name = f"docker-compose.{component_name}.yml"
        output_file_path_in_container = os.path.join(output_path_in_container, output_file_name)

        try:
            print(
                f"DEBUG: Jinja2 attempting to load template from absolute path: {os.path.join(templates_path, template_file)}")  # DEBUG PRINT
            template = env.get_template(template_file)

            # Print the SOURCE content snippet for debugging
            print(f"DEBUG: Successfully loaded template '{template_file}'. Source content snippet:\n{template.environment.loader.get_source(env, template_file)[0][:500]}...")

            rendered_content = template.render(context)

            # Print the RENDERED content snippet for debugging
            print(f"DEBUG: Rendered content snippet for '{component_name}':\n{rendered_content[:500]}...")

            with open(output_file_path_in_container, 'w') as f:
                f.write(rendered_content)
            print(f"Generated: {output_file_path_in_container}")
            individual_generated_files.append(output_file_path_in_container)

        except jinja2.exceptions.TemplateNotFound as err_temp:
            print(
                f"Warning: Template not found for '{component_name}' at {template_file}. Error: {err_temp}. Skipping.")
        except Exception as err:
            print(f"Error generating Docker Compose for '{component_name}': {err}")
            raise

    # Call the new merge function
    if individual_generated_files:
        unified_compose_path_in_container = os.path.join(output_path_in_container, UNIFIED_DOCKER_COMPOSE_FILENAME)
        unified_compose_path_on_host = os.path.join(remote_host_docker_output_path,
                                                    UNIFIED_DOCKER_COMPOSE_FILENAME).replace('\\', '/')

        # Pass the individual files and the container output path to the merge function
        merge_docker_compose_files(individual_generated_files, unified_compose_path_in_container)

        # MODIFIED PRINT STATEMENT: Show both container and host paths
        print(
            f"Successfully generated unified docker-compose.yml at '{unified_compose_path_in_container}' (container path).")
        print(f"You can find it on your Raspberry Pi at: '{unified_compose_path_on_host}' (host path).")

    else:
        print("No individual Docker Compose files generated to merge.")

    return individual_generated_files


# --- FUNCTION FOR MERGING DOCKER COMPOSE FILES ---
def merge_docker_compose_files(file_paths, output_path):
    """
    Merges multiple Docker Compose YAML files into a single unified file.
    Handles 'services', 'volumes', and 'networks' sections.
    """
    print("\n--- Merging Docker Compose files ---")
    unified_compose_data = {
        'version': '3.8',  # Default Docker Compose version
        'services': {},
        'volumes': {},
        'networks': {}
    }

    for file_path in file_paths:
        try:
            with open(file_path, 'r') as f:
                component_compose = yaml.safe_load(f)

            if not isinstance(component_compose, dict):
                print(f"Warning: {file_path} does not contain valid YAML dictionary. Skipping merge.")
                continue

            # Merge services
            if 'services' in component_compose:
                for service_name, service_config in component_compose['services'].items():
                    if service_name in unified_compose_data['services']:
                        print(
                            f"Warning: Duplicate service name '{service_name}' found in {file_path}. Overwriting with last one found.")
                    unified_compose_data['services'][service_name] = service_config

            # Merge volumes
            if 'volumes' in component_compose:
                for volume_name, volume_config in component_compose['volumes'].items():
                    if volume_name in unified_compose_data['volumes']:
                        # For volumes, it's safer to not overwrite if config differs
                        if unified_compose_data['volumes'][volume_name] != volume_config:
                            print(
                                f"Warning: Volume '{volume_name}' in {file_path} has conflicting definition. Keeping first one encountered.")
                        # Otherwise, if they are identical or new, add it.
                    unified_compose_data['volumes'][volume_name] = volume_config

            # Merge networks (assuming external: true is common, or define if not external)
            if 'networks' in component_compose:
                for network_name, network_config in component_compose['networks'].items():
                    if network_name in unified_compose_data['networks']:
                        if unified_compose_data['networks'][network_name] != network_config:
                            print(
                                f"Warning: Network '{network_name}' in {file_path} has conflicting definition. Keeping first one encountered.")
                    unified_compose_data['networks'][network_name] = network_config

        except yaml.YAMLError as yaml_err:
            print(f"Error parsing YAML from {file_path}: {yaml_err}. Skipping merge for this file.")
        except Exception as err:
            print(f"An unexpected error occurred during merge for {file_path}: {err}. Skipping.")

    # Write the unified data to the output file
    try:
        with open(output_path, 'w') as f:
            yaml.dump(unified_compose_data, f, default_flow_style=False,
                      sort_keys=False)  # sort_keys=False to preserve order
        # This print statement is now handled by the calling generate_docker_compose_files function
    except Exception as err:
        print(f"Error writing unified docker-compose.yml to {output_path}: {err}")
        raise


# Example usage (for direct testing/debugging of the script)
if __name__ == "__main__":
    print("Running setup.py directly for testing purposes...")
    try:
        # NOTE: When running locally (not in Docker), REMOTE_PROJECT_PATH environment variable
        # will not be set automatically. We'll set a dummy value for local testing context.
        # This ensures get_project_root() still points to PiSelfhosting/
        # And `remote_host_docker_output_path` can be constructed.
        current_script_dir = os.path.dirname(os.path.abspath(__file__))
        local_piselfhosting_root = os.path.dirname(current_script_dir)  # Should be ...\PiSelfhosting
        os.environ['REMOTE_PROJECT_PATH'] = os.getenv('REMOTE_PROJECT_PATH', local_piselfhosting_root)

        parsed_data = parse_components_list()
        print("\nParsed Components List:")
        print(f"  Order: {parsed_data['components_order']}")
        for name, props in parsed_data['all_component_data'].items():
            print(f"  Component: [{name}]")
            for key, value in props.items():
                print(f"    {key}: {value}")

        print("\nSelected Components:")
        selected_components_set = read_selected_components()
        print(f"  Selected: {selected_components_set}")

        # For local testing, ensure dummy environment variables are set for generation
        # These are usually passed by the installer in a real run.
        if 'DOMAIN' not in os.environ: os.environ['DOMAIN'] = 'localtest.com'
        if 'PUID' not in os.environ: os.environ['PUID'] = '1000'
        if 'PGID' not in os.environ: os.environ['PGID'] = '1000'
        if 'HOST_IP' not in os.environ: os.environ['HOST_IP'] = '127.0.0.1'
        if 'DB_USER' not in os.environ: os.environ['DB_USER'] = 'localdbuser'
        if 'DB_PASS' not in os.environ: os.environ['DB_PASS'] = 'localdbpass'
        if 'TZ' not in os.environ: os.environ['TZ'] = 'Europe/Amsterdam'
        if 'ADMIN_EMAIL' not in os.environ: os.environ['ADMIN_EMAIL'] = 'local@test.com'

        generated_files_list = generate_docker_compose_files(
            parsed_data["all_component_data"],
            selected_components_set
        )
        print(f"\nSuccessfully generated {len(generated_files_list)} individual Docker Compose files.")

    except FileNotFoundError as e:
        print(f"FileNotFoundError: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")