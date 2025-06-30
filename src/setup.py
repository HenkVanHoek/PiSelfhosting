# src/setup.py (FINAL, VERIFIED COMPLETE AND CORRECT VERSION - ALL ENGLISH)
import os
import configparser
import jinja2
import yaml
import json
import sys # Importeer sys voor stderr

# Global FHS-compliant data root for all services
GLOBAL_DATA_ROOT = "/opt/piselfhosting/data"

# Define the expected path for components_list.txt relative to the project root
COMPONENTS_LIST_FILENAME = "components_list.txt"
SELECTED_COMPONENTS_FILENAME = "selected_components.txt"
DOCKER_COMPOSE_TEMPLATES_DIR = "templates"  # Path to the templates directory (relative to project root)
DOCKER_COMPOSE_OUTPUT_DIR = "docker"  # Path where generated docker-compose files will be stored (relative to project root)

# Name for the unified Docker Compose file
UNIFIED_DOCKER_COMPOSE_FILENAME = "docker-compose.yml"


def get_project_root():
    """
    Determines the root directory of the PiSelfhosting project.
    Assumes this script (setup.py) is located in the 'src' subdirectory
    and the project root is one level up from 'src'.
    """
    _current_script_dir = os.path.dirname(os.path.abspath(__file__))  # Renamed to avoid shadowing
    project_root = os.path.dirname(_current_script_dir)
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


# --- FUNCTION FOR DOCKER COMPOSE AND CONFIG FILE GENERATION ---
def generate_docker_compose_files(all_component_data, selected_components):
    """
    Generates individual docker-compose.yml files for selected components based on templates.
    Also generates specific application config files for components.
    Then merges individual compose files into a single docker-compose.yml.
    Reads all necessary variables from environment variables.
    """
    print("\n--- Generating Docker Compose files and Configs ---")
    project_root_in_container = get_project_root()  # This is /app (Docker container path)
    templates_root_path = os.path.join(project_root_in_container,
                                       DOCKER_COMPOSE_TEMPLATES_DIR)  # This is /app/templates
    output_path_in_container = os.path.join(project_root_in_container, DOCKER_COMPOSE_OUTPUT_DIR)  # This is /app/docker

    # Get the actual remote project path on the host from environment variable
    remote_host_project_path = os.getenv("REMOTE_PROJECT_PATH",
                                         "/home/pi/PiSelfhosting")  # Fallback to a common default
    remote_host_docker_output_path = os.path.join(remote_host_project_path, DOCKER_COMPOSE_OUTPUT_DIR).replace('\\',
                                                                                                               '/')  # Ensure Linux path separators

    # IMPORTANT: Ensure these directories exist BEFORE attempting to write files to them
    os.makedirs(output_path_in_container, exist_ok=True)
    generated_configs_temp_path = os.path.join(output_path_in_container, "generated_configs")
    os.makedirs(generated_configs_temp_path, exist_ok=True)


    # Setup Jinja2 environment
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(templates_root_path),  # Jinja2 loads from /app/templates
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
    phpmyadmin_blowfish_secret = os.getenv("PHPMYADMIN_BLOWFISH_SECRET", os.urandom(32).hex())
    pma_host = os.getenv("PMA_HOST", "mariadb")
    frigate_rtsp_password = os.getenv("FRIGATE_RTSP_PASSWORD", "change_me_frigate_rtsp_pass")

    context = {
        "DOMAIN": domain_name,
        "PUID": puid,
        "PGID": pgid,
        "HOST_IP": host_ip,
        "DB_USER": db_user,
        "DB_PASS": db_pass,
        "TZ": tz,
        "ADMIN_EMAIL": admin_email,
        "PHPMYADMIN_BLOWFISH_SECRET": phpmyadmin_blowfish_secret,
        "PMA_HOST": pma_host,
        "FRIGATE_RTSP_PASSWORD": frigate_rtsp_password,
        "DATA_ROOT": GLOBAL_DATA_ROOT,  # /opt/piselfhosting/data
        "TRAEFIK_DASHBOARD_DOMAIN": f"traefik.{domain_name}" if "traefik" in selected_components else ""  # Typo fixed
    }
    print(f"DEBUG: Environment variables for substitution: {context}")

    individual_generated_compose_files = []  # List to hold paths of generated docker-compose files
    generated_config_files_to_move = {}  # Dict to hold {temp_container_path: final_host_path} for config files

    for component_name in selected_components:
        if component_name not in all_component_data:
            print(
                f"Warning: Component '{component_name}' found in selected_components.txt but not in components_list.txt. Skipping.")
            continue

        # --- Handle Docker Compose Template ---
        # Convention: docker-compose.template.yml
        compose_template_path = os.path.join(component_name, "docker-compose.template.yml")
        compose_output_filename = f"docker-compose.{component_name}.yml"
        compose_output_full_path_in_container = os.path.join(output_path_in_container, compose_output_filename)

        try:
            print(
                f"DEBUG: Jinja2 attempting to load compose template: {os.path.join(templates_root_path, compose_template_path)}")
            template_compose = env.get_template(compose_template_path)

            print(
                f"DEBUG: Successfully loaded template '{compose_template_path}'. Source snippet:\n{template_compose.environment.loader.get_source(env, compose_template_path)[0][:500]}...")
            rendered_content_compose = template_compose.render(context)
            print(
                f"DEBUG: Rendered content snippet for '{component_name}' (Compose):\n{rendered_content_compose[:500]}...")

            with open(compose_output_full_path_in_container, 'w') as f:
                f.write(rendered_content_compose)
            print(f"Generated: {compose_output_full_path_in_container}")
            individual_generated_compose_files.append(compose_output_full_path_in_container)

        except jinja2.exceptions.TemplateNotFound as err_temp:
            print(
                f"Warning: Compose Template not found for '{component_name}' at {compose_template_path}. Error: {err_temp}. Skipping.")
        except Exception as err:
            # GEWIJZIGD: print naar sys.stderr
            sys.stderr.write(f"Error generating Docker Compose for '{component_name}': {err}\n")
            raise

        # --- Handle specific application config file templates ---
        # NEW NAMING CONVENTION: <filename>.<extension> inside <component>/template-config/

        # Mosquitto config file generation
        if component_name == "mosquitto":
            config_template_name = "mosquitto.conf"  # Template file name (now matches original filename in template-config)
            final_config_filename = "mosquitto.conf"  # Final name in FHS /data/
            template_path_full = os.path.join(templates_root_path, component_name, "template-config",
                                              config_template_name)
            final_fhs_config_path = os.path.join(GLOBAL_DATA_ROOT, component_name, "config",
                                                 final_config_filename).replace('\\', '/')

            # noinspection PyBroadException
            try:
                rendered_config_content = env.get_template(
                    os.path.join(component_name, "template-config", config_template_name)).render(context)

                temp_output_dir_for_component = os.path.join(generated_configs_temp_path, component_name)
                os.makedirs(temp_output_dir_for_component, exist_ok=True)  # Ensure component's temp dir

                temp_output_path_in_container_config = os.path.join(temp_output_dir_for_component,
                                                                    final_config_filename)
                with open(temp_output_path_in_container_config, 'w') as f:
                    f.write(rendered_config_content)

                print(
                    f"Generated Mosquitto config file (will be moved by installer): {temp_output_path_in_container_config}")
                generated_config_files_to_move[temp_output_path_in_container_config] = final_fhs_config_path

            except jinja2.exceptions.TemplateNotFound:
                print(
                    f"Warning: Config template '{config_template_name}' not found at {template_path_full}. Skipping config generation.")
            except Exception as err:
                # GEWIJZIGD: print naar sys.stderr
                sys.stderr.write(f"Error generating Mosquitto config: {err}\n")
                raise

        # phpMyAdmin config file generation
        elif component_name == "phpmyadmin":
            config_template_name = "config.inc.php"  # Template file name
            final_config_filename = "config.inc.php"  # Final name
            template_path_full = os.path.join(templates_root_path, component_name, "template-config",
                                              config_template_name)
            final_fhs_config_path = os.path.join(GLOBAL_DATA_ROOT, component_name, "config",
                                                 final_config_filename).replace('\\', '/')

            # noinspection PyBroadException
            try:
                # Initialize temp_output_path_in_container_config before try block
                temp_output_path_in_container_config = os.path.join(generated_configs_temp_path, component_name,
                                                                    final_config_filename)

                rendered_config_content = env.get_template(
                    os.path.join(component_name, "template-config", config_template_name)).render(context)

                temp_output_dir_for_component = os.path.join(generated_configs_temp_path, component_name)
                os.makedirs(temp_output_dir_for_component, exist_ok=True)  # Ensure component's temp dir

                with open(temp_output_path_in_container_config, 'w') as f:
                    f.write(rendered_config_content)

                print(
                    f"Generated phpMyAdmin config file (will be moved by installer): {temp_output_path_in_container_config}")
                generated_config_files_to_move[temp_output_path_in_container_config] = final_fhs_config_path

            except jinja2.exceptions.TemplateNotFound:
                print(
                    f"Warning: phpMyAdmin config template not found at {template_path_full}. Skipping config generation.")
            except Exception as err:  # noinspection PyBroadException
                # GEWIJZIGD: print naar sys.stderr
                sys.stderr.write(f"Error generating phpMyAdmin config: {err}\n")
                raise

        # Dashy config file generation
        elif component_name == "dashy":
            config_template_name = "conf.yml"  # Template file name (your existing one)
            final_config_filename = "conf.yml"  # Final name
            template_path_full = os.path.join(templates_root_path, component_name, "template-config",
                                              config_template_name)
            final_fhs_config_path = os.path.join(GLOBAL_DATA_ROOT, component_name, "config",
                                                 final_config_filename).replace('\\', '/')

            # noinspection PyBroadException
            try:
                # Initialize temp_output_path_in_container_config before try block
                temp_output_path_in_container_config = os.path.join(generated_configs_temp_path, component_name,
                                                                    final_config_filename)

                rendered_config_content = env.get_template(
                    os.path.join(component_name, "template-config", config_template_name)).render(context)

                temp_output_dir_for_component = os.path.join(generated_configs_temp_path, component_name)
                os.makedirs(temp_output_dir_for_component, exist_ok=True)  # Ensure component's temp dir

                with open(temp_output_path_in_container_config, 'w') as f:
                    f.write(rendered_config_content)

                print(
                    f"Generated Dashy config file (will be moved by installer): {temp_output_path_in_container_config}")
                generated_config_files_to_move[temp_output_path_in_container_config] = final_fhs_config_path

            except jinja2.exceptions.TemplateNotFound:
                print(f"Warning: Dashy config template not found at {template_path_full}. Skipping config generation.")
            except Exception as err:  # noinspection PyBroadException
                # GEWIJZIGD: print naar sys.stderr
                sys.stderr.write(f"Error generating Dashy config: {err}\n")
                raise

    # Call the merge function for Docker Compose files
    if individual_generated_compose_files:
        unified_compose_path_in_container = os.path.join(output_path_in_container, UNIFIED_DOCKER_COMPOSE_FILENAME)
        unified_compose_path_on_host = os.path.join(remote_host_docker_output_path,
                                                    UNIFIED_DOCKER_COMPOSE_FILENAME).replace('\\', '/')

        merge_docker_compose_files(individual_generated_compose_files, unified_compose_path_in_container)

        print(
            f"Successfully generated unified docker-compose.yml at '{unified_compose_path_in_container}' (container path).")
        print(f"You can find it on your Raspberry Pi at: '{unified_compose_path_on_host}' (host path).")

    else:
        print("No individual Docker Compose files generated to merge.")

    # generated_config_files_to_move is the map for the installer to use.
    # CRUCIAL: Print this map as JSON as the absolute last thing to stdout by setup.py.
    print(json.dumps(generated_config_files_to_move))


# --- FUNCTION FOR MERGING DOCKER COMPOSE FILES ---
def merge_docker_compose_files(file_paths, output_path):
    """
    Merges multiple Docker Compose YAML files into a single unified file.
    Handles 'services', 'volumes', and 'networks' sections.
    """
    print("\n--- Merging Docker Compose files ---")
    unified_compose_data = {
        # 'version': '3.8', # Removed as it's obsolete in Docker Compose V2
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

            # Merge services (last one wins)
            if 'services' in component_compose:
                for service_name, service_config in component_compose['services'].items():
                    if service_name in unified_compose_data['services']:
                        print(
                            f"Warning: Duplicate service name '{service_name}' found in {file_path}. Overwriting with last one found.")
                    unified_compose_data['services'][service_name] = service_config

            # Merge volumes (first one wins)
            if 'volumes' in component_compose:
                for volume_name, volume_config in component_compose['volumes'].items():
                    # Only add if the volume is NOT already present
                    if volume_name not in unified_compose_data['volumes']:
                        unified_compose_data['volumes'][volume_name] = volume_config
                    else:
                        # If it exists, but conflicts, print a warning
                        if unified_compose_data['volumes'][volume_name] != volume_config:
                            sys.stderr.write( # Ensure it's sys.stderr.write
                                f"Warning: Volume '{volume_name}' in {file_path} has conflicting definition. Keeping first one encountered.\n")

            # Merge networks (first one wins)
            if 'networks' in component_compose:
                for network_name, network_config in component_compose['networks'].items():
                    # Only add if the network is NOT already present
                    if network_name not in unified_compose_data['networks']:
                        unified_compose_data['networks'][network_name] = network_config
                    else:
                        # If it exists, but conflicts, print a warning
                        if unified_compose_data['networks'][network_name] != network_config:
                            sys.stderr.write( # Ensure it's sys.stderr.write
                                f"Warning: Network '{network_name}' in {file_path} has conflicting definition. Keeping first one encountered.\n")

        except yaml.YAMLError as yaml_err:
            sys.stderr.write(f"Error parsing YAML from {file_path}: {yaml_err}. Skipping merge for this file.\n")
            continue
        except Exception as err:
            sys.stderr.write(f"An unexpected error occurred during merge for {file_path}: {err}. Skipping.\n")
            continue
    # Write the unified data to the output file
    try:
        with open(output_path, 'w') as f:
            yaml.dump(unified_compose_data, f, default_flow_style=False,
                      sort_keys=False)  # sort_keys=False to preserve order
    except Exception as err:
        # GEWIJZIGD: print naar sys.stderr
        sys.stderr.write(f"Error writing unified docker-compose.yml to {output_path}: {err}\n")
        raise


# Example usage (for direct testing/debugging of the script)
if __name__ == "__main__":
    print("Running setup.py directly for testing purposes...")
    try:
        # NOTE: When running locally (not in Docker), REMOTE_PROJECT_PATH environment variable
        # will not be set automatically. We'll set a dummy value for local testing context.
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
        if 'PHPMYADMIN_BLOWFISH_SECRET' not in os.environ: os.environ[
            'PHPMYADMIN_BLOWFISH_SECRET'] = 'local_blowfish_secret'
        if 'PMA_HOST' not in os.environ: os.environ['PMA_HOST'] = 'local_mariadb'
        if 'FRIGATE_RTSP_PASSWORD' not in os.environ: os.environ['FRIGATE_RTSP_PASSWORD'] = 'local_frigate_pass'

        generated_config_files_map_from_setup = generate_docker_compose_files(
            parsed_data["all_component_data"],
            selected_components_set
        )
        print(f"\nSuccessfully generated config and compose files.")

        # CRUCIAL: Print the map as JSON as the absolute last thing to stdout for the installer to parse.
        print(json.dumps(generated_config_files_map_from_setup))

    except FileNotFoundError as e:
        print(f"FileNotFoundError: {e}")
    except Exception as e:  # noinspection PyBroadException
        print(f"An unexpected error occurred: {e}")