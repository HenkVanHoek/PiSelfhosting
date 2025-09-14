# src/setup.py
import json
import os
import sys

import jinja2
import yaml

# Global FHS-compliant data root for all services
GLOBAL_DATA_ROOT = "/opt/piselfhosting/data"

# --- CONFIGURATION REFACTORED TO USE A SINGLE SOURCE OF TRUTH ---
COMPONENTS_METADATA_FILENAME = "components_metadata.json"
SELECTED_COMPONENTS_FILENAME = "selected_components.txt"
DOCKER_COMPOSE_TEMPLATES_DIR = "templates"
DOCKER_COMPOSE_OUTPUT_DIR = "docker"
UNIFIED_DOCKER_COMPOSE_FILENAME = "docker-compose.yml"


def get_project_root():
    """Determines the root directory of the PiSelfhosting project."""
    _current_script_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(_current_script_dir)


def load_component_metadata(file_path=None):
    """
    Parses the components_metadata.json file and returns a dictionary
    containing the component order and all component data.
    """
    if file_path is None:
        project_root = get_project_root()
        file_path = os.path.join(project_root, COMPONENTS_METADATA_FILENAME)

    if not os.path.exists(file_path):
        error_msg = f"Error: '{COMPONENTS_METADATA_FILENAME}' not found at {file_path}."
        sys.stderr.write(error_msg + "\n")
        raise FileNotFoundError(error_msg)

    try:
        with open(file_path, "r") as f:
            full_metadata = json.load(f)
    except json.JSONDecodeError as json_err:
        sys.stderr.write(f"Error parsing JSON from '{file_path}': {json_err}\n")
        raise

    project_config = full_metadata.pop("_piselfhosting", {})
    components_order = project_config.get("components_order", [])
    all_component_data = full_metadata

    if not components_order:
        components_order = list(all_component_data.keys())
        print(
            (
                f"Warning: 'components_order' not found in "
                f"'{COMPONENTS_METADATA_FILENAME}'. Using default key order."
            )
        )

    for name, data in all_component_data.items():
        if "name" not in data:
            data["name"] = name

    return {
        "components_order": components_order,
        "all_component_data": all_component_data,
    }


def read_selected_components(file_path=None):
    """
    Reads the selected_components.txt file and returns a set of component names.
    """
    if file_path is None:
        project_root = get_project_root()
        file_path = os.path.join(project_root, SELECTED_COMPONENTS_FILENAME)

    if not os.path.exists(file_path):
        print(
            (
                f"Warning: '{SELECTED_COMPONENTS_FILENAME}' not found at {file_path}. "
                "Assuming no components selected."
            )
        )
        return set()

    try:
        with open(file_path, "r") as f:
            content = f.read().strip()
        return set(c for c in content.split() if c)
    except Exception as err:
        sys.stderr.write(
            f"Error reading or parsing '{SELECTED_COMPONENTS_FILENAME}': {err}\n"
        )
        raise


def generate_docker_compose_files(all_component_data, selected_components):
    """
    Generates and merges Docker Compose files and application configs.
    """
    print("\n--- Generating Docker Compose files and Configs ---")
    project_root = get_project_root()
    templates_root = os.path.join(project_root, DOCKER_COMPOSE_TEMPLATES_DIR)
    output_root = os.path.join(project_root, DOCKER_COMPOSE_OUTPUT_DIR)
    generated_configs_temp = os.path.join(output_root, "generated_configs")

    os.makedirs(output_root, exist_ok=True)
    os.makedirs(generated_configs_temp, exist_ok=True)

    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(templates_root),
        trim_blocks=True,
        lstrip_blocks=True,
    )

    domain_name = os.getenv("DOMAIN", "yourdomain.com")
    context = {
        "DOMAIN": domain_name,
        "PUID": os.getenv("PUID", "1000"),
        "PGID": os.getenv("PGID", "1000"),
        "HOST_IP": os.getenv("HOST_IP", "127.0.0.1"),
        "DB_USER": os.getenv("DB_USER", "piselfhosting_user"),
        "DB_PASS": os.getenv("DB_PASS", "secure_password"),
        "TZ": os.getenv("TZ", "Europe/Amsterdam"),
        "ADMIN_EMAIL": os.getenv("ADMIN_EMAIL", "admin@yourdomain.com"),
        "PHPMYADMIN_BLOWFISH_SECRET": os.getenv(
            "PHPMYADMIN_BLOWFISH_SECRET", os.urandom(32).hex()
        ),
        "PMA_HOST": os.getenv("PMA_HOST", "mariadb"),
        "FRIGATE_RTSP_PASSWORD": os.getenv(
            "FRIGATE_RTSP_PASSWORD", "change_me_frigate_rtsp_pass"
        ),
        "DATA_ROOT": GLOBAL_DATA_ROOT,
        "TRAEFIK_DASHBOARD_DOMAIN": (
            f"traefik.{domain_name}" if "traefik" in selected_components else ""
        ),
    }

    generated_files = []
    configs_to_move = {}

    for name in selected_components:
        if name not in all_component_data:
            print(
                (
                    f"Warning: Component '{name}' is selected but not found in "
                    f"'{COMPONENTS_METADATA_FILENAME}'. Skipping."
                )
            )
            continue

        # Generate Docker Compose fragment
        compose_template_path = os.path.join(name, "docker-compose.template.yml")
        try:
            template = env.get_template(compose_template_path)
            rendered_content = template.render(context)
            output_path = os.path.join(output_root, f"docker-compose.{name}.yml")
            with open(output_path, "w") as f:
                f.write(rendered_content)
            generated_files.append(output_path)
        except jinja2.exceptions.TemplateNotFound:
            print(
                (
                    f"Warning: Compose Template not found for '{name}' at "
                    f"{compose_template_path}. Skipping compose file generation."
                )
            )
        except Exception as err:
            sys.stderr.write(f"Error generating Docker Compose for '{name}': {err}\n")
            raise

        # Handle specific application config file templates
        component_meta = all_component_data.get(name, {})
        config_templates = component_meta.get("config_templates", {})

        for template_name, final_location in config_templates.items():
            final_config_filename = os.path.basename(final_location)
            template_path_full = os.path.join(
                templates_root, name, "template-config", template_name
            )
            final_fhs_config_path = os.path.join(
                GLOBAL_DATA_ROOT, final_location
            ).replace("\\", "/")

            try:
                # noinspection PyTypeChecker
                rendered_config_content = env.get_template(
                    os.path.join(name, "template-config", template_name)
                ).render(context)

                temp_output_dir = os.path.join(generated_configs_temp, name)
                os.makedirs(temp_output_dir, exist_ok=True)
                temp_output_path = os.path.join(temp_output_dir, final_config_filename)

                with open(temp_output_path, "w") as f:
                    f.write(rendered_config_content)

                print(f"Generated config file for {name}: {temp_output_path}")
                configs_to_move[temp_output_path] = final_fhs_config_path
            except jinja2.exceptions.TemplateNotFound:
                print(
                    (
                        f"Warning: Config template '{template_name}' not found at "
                        f"{template_path_full}. Skipping config generation."
                    )
                )
            except Exception as err:
                sys.stderr.write(
                    f"Error generating config '{template_name}' for {name}: {err}\n"
                )
                raise

    # Merge generated docker-compose files
    if generated_files:
        unified_compose_path = os.path.join(
            output_root, UNIFIED_DOCKER_COMPOSE_FILENAME
        )
        merge_docker_compose_files(generated_files, unified_compose_path)
        print(
            (
                "Successfully generated unified docker-compose.yml at "
                f"'{unified_compose_path}'."
            )
        )
    else:
        print("No individual Docker Compose files generated to merge.")

    # CRUCIAL: Print this map as JSON as the absolute last thing to stdout.
    print(json.dumps(configs_to_move))


def merge_docker_compose_files(file_paths, output_path):
    """
    Merges multiple Docker Compose YAML files into a single unified file.
    """
    print("\n--- Merging Docker Compose files ---")
    unified_compose_data = {"services": {}, "volumes": {}, "networks": {}}

    for file_path in file_paths:
        try:
            with open(file_path, "r") as f:
                component_compose = yaml.safe_load(f)

            if not isinstance(component_compose, dict):
                print(f"Warning: {file_path} does not contain valid YAML. Skipping.")
                continue

            for section in ["services", "volumes", "networks"]:
                if section in component_compose:
                    for key, value in component_compose[section].items():
                        if key not in unified_compose_data[section]:
                            unified_compose_data[section][key] = value
                        elif unified_compose_data[section][key] != value:
                            sys.stderr.write(
                                (
                                    f"Warning: Conflicting definition for '{key}' in "
                                    f"'{section}'. Keeping first one encountered.\n"
                                )
                            )

        except yaml.YAMLError as yaml_err:
            sys.stderr.write(
                f"Error parsing YAML from {file_path}: {yaml_err}. Skipping.\n"
            )
        except Exception as err:
            sys.stderr.write(
                (
                    f"An unexpected error occurred during merge for {file_path}: "
                    f"{err}. Skipping.\n"
                )
            )

    try:
        with open(output_path, "w") as f:
            yaml.dump(
                unified_compose_data, f, default_flow_style=False, sort_keys=False
            )
    except Exception as err:
        sys.stderr.write(
            f"Error writing unified docker-compose.yml to {output_path}: {err}\n"
        )
        raise


def main():
    print("Running setup.py directly for testing purposes...")
    try:
        if "REMOTE_PROJECT_PATH" not in os.environ:
            os.environ["REMOTE_PROJECT_PATH"] = get_project_root()

        parsed_data = load_component_metadata()

        print("\n--- Parsed Component Metadata ---")
        print(f"  Order: {parsed_data['components_order']}")

        selected_components_set = read_selected_components()
        print(f"\nSelected Components: {selected_components_set}")

        if "DOMAIN" not in os.environ:
            os.environ["DOMAIN"] = "localtest.com"
        if "PUID" not in os.environ:
            os.environ["PUID"] = "1000"

        generate_docker_compose_files(
            parsed_data["all_component_data"], selected_components_set
        )
        # This is the corrected line (F541)
        print("\nSuccessfully generated config and compose files.")

    except FileNotFoundError as e:
        sys.stderr.write(f"FATAL: {e}\n")
    except Exception as e:
        sys.stderr.write(f"An unexpected fatal error occurred: {e}\n")


if __name__ == "__main__":
    main()
