import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, cast

import yaml
from jinja2 import Template

logger = logging.getLogger(__name__)


class ComponentManager:
    """Manages component metadata and template files."""

    def __init__(self, templates_path: str, metadata_file_path: str):
        self.templates_path = Path(templates_path)
        self.metadata_file = Path(metadata_file_path)
        self._components_data: Dict[str, Any] = self._load_metadata()
        self._variables_cache: Dict[str, List[Dict[str, Any]]] = (
            self._load_all_variables()
        )

    def _load_metadata(self) -> Dict[str, Any]:
        """Loads the main components metadata file."""
        try:
            with open(self.metadata_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.error(f"Error loading metadata: {e}")
            return {"_piselfhosting": {}, "components": {}}

    def _load_all_variables(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Scans all component directories for variables.json and loads them
        into a central cache.
        """
        variables: Dict[str, List[Dict[str, Any]]] = {}
        components = self._components_data.get("components", {})
        for comp_id in components:
            variables_file = (
                self.templates_path / comp_id / "template-config" / "variables.json"
            )
            if variables_file.exists():
                try:
                    with open(variables_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        variables[comp_id] = data.get("variables", [])
                except (json.JSONDecodeError, TypeError) as e:
                    logger.error(f"Error loading variables for {comp_id}: {e}")
                    variables[comp_id] = []
            else:
                variables[comp_id] = []
        return variables

    def _save_metadata(self):
        """Saves the current components data back to the JSON file."""
        with open(self.metadata_file, "w", encoding="utf-8") as f:
            json.dump(self._components_data, f, indent=2, sort_keys=True)

    def get_all_components(self) -> List[Dict[str, Any]]:
        """Returns a list of all components with their essential data."""
        components = self._components_data.get("components", {})
        all_comps: List[Dict[str, Any]] = []
        for comp_id, comp_data in components.items():
            full_data = comp_data.copy()
            full_data["id"] = comp_id
            full_data["required_variables"] = self._variables_cache.get(comp_id, [])
            all_comps.append(full_data)
        return all_comps

    def get_component_details(self, component_id: str) -> Optional[Dict[str, Any]]:
        """
        Returns the full details for a single component.
        """
        component_data = self._components_data.get("components", {}).get(component_id)
        if not component_data:
            return None
        details = component_data.copy()
        details["id"] = component_id
        details["required_variables"] = self._variables_cache.get(component_id, [])
        details["has_traefik_support"] = component_data.get(
            "has_traefik_support", False
        )
        details["traefik_internal_port"] = component_data.get(
            "traefik_internal_port", None
        )
        details["conflicts_with"] = component_data.get("conflicts_with", [])
        return details

    def validate_component_configuration(
        self,
        _component_id: str,
        template_content: str,
        _variables: List[Dict[str, Any]],
    ) -> None:
        """
        Validates a component's template and variables.
        """
        try:
            data = yaml.safe_load(template_content)
        except yaml.YAMLError as e:
            raise ValueError(
                f"YAML Parsing Failed: The template content is not valid YAML. "
                f"Error: {e}"
            )
        services = data.get("services", {})
        for service_name, service_data in services.items():
            container_name = service_data.get("container_name")
            if container_name:
                mandatory_prefix = "piselfhosting-"
                if not container_name.lower().startswith(mandatory_prefix):
                    raise ValueError(
                        f"Naming Violation: The container_name '{container_name}' "
                        f"for service '{service_name}' must begin with the "
                        f"mandatory prefix '{mandatory_prefix}'."
                    )

    def validate_metadata_conflicts(
        self, component_id: str, conflicts_with_list: List[str]
    ) -> None:
        """
        Validates the 'conflicts_with' list for a component.
        """
        if component_id in conflicts_with_list:
            raise ValueError(
                f"Self-Conflict Error: Component '{component_id}' cannot "
                "conflict with itself."
            )
        all_component_ids = set(self._components_data.get("components", {}).keys())
        non_existent_conflicts = [
            cid for cid in conflicts_with_list if cid not in all_component_ids
        ]
        if non_existent_conflicts:
            non_existent_str = ", ".join(non_existent_conflicts)
            raise ValueError(
                "Non-Existent ID Error: The following component ID(s) "
                f"listed in 'Conflicts With' do not exist: "
                f"{non_existent_str}."
            )

    def create_component(self, component_id: str, component_name: str):
        """Creates the folder structure and initial files for a new component."""
        components = self._components_data.setdefault("components", {})
        if component_id in components:
            raise ValueError(f"Component '{component_id}' already exists.")
        new_comp_path = self.templates_path / component_id
        new_comp_path.mkdir(exist_ok=True)
        (new_comp_path / "template-config").mkdir(exist_ok=True)
        (new_comp_path / "docker-compose.template.yml").write_text(
            f"services:\n  # Service for {component_name}\n"
        )
        (new_comp_path / "template-config" / "variables.json").write_text(
            json.dumps({"variables": []}, indent=2)
        )
        components[component_id] = {
            "name": component_name,
            "group": self.get_piselfhosting_meta().get("default_group", None),
            "description": "",
            "has_ui": False,
            "has_configuration": True,
            "depends_on": [],
            "conflicts_with": [],
        }
        self._save_metadata()
        self._variables_cache[component_id] = []

    def get_docker_service_name(self, component_id: str) -> str:
        """Gets the primary service name for a component's template."""
        component_details = self.get_component_details(component_id)
        if component_details:
            return component_details.get("docker_service_name", component_id)
        return component_id

    def update_component_metadata(self, component_id: str, update_data: Dict[str, Any]):
        components = self._components_data.setdefault("components", {})
        if component_id not in components:
            raise KeyError(f"Component '{component_id}' not found.")
        new_group_id = update_data.get("group")
        if new_group_id:
            piselfhosting_meta = self._components_data.setdefault("_piselfhosting", {})
            group_rules = piselfhosting_meta.setdefault("group_rules", {})
            if new_group_id not in group_rules:
                group_rules[new_group_id] = {
                    "name": new_group_id.replace("_", " ").title(),
                    "is_exclusive": False,
                }
                piselfhosting_meta.setdefault("group_order", []).append(new_group_id)
        components[component_id].update(update_data)
        self._save_metadata()

    def update_component_group(self, component_id: str, new_group_id: str):
        components = self._components_data.get("components", {})
        if component_id in components:
            components[component_id]["group"] = new_group_id
            self._save_metadata()
        else:
            raise KeyError(f"Component '{component_id}' not found.")

    def get_piselfhosting_meta(self) -> Dict[str, Any]:
        return self._components_data.get("_piselfhosting", {})

    def sort_components_by_master_order(self, component_ids: List[str]) -> List[str]:
        master_order = self.get_piselfhosting_meta().get("components_order", [])
        order_map = {comp_id: i for i, comp_id in enumerate(master_order)}
        return sorted(
            component_ids, key=lambda cid: order_map.get(cid, len(master_order))
        )

    def update_group_order(self, new_order: List[str]):
        piselfhosting_meta = self._components_data.setdefault("_piselfhosting", {})
        piselfhosting_meta["group_order"] = new_order
        self._save_metadata()

    def update_components_order(self, new_order: List[str]):
        piselfhosting_meta = self._components_data.setdefault("_piselfhosting", {})
        piselfhosting_meta["components_order"] = new_order
        self._save_metadata()

    def delete_group(self, group_id: str):
        all_components = self.get_all_components()
        is_in_use = any(comp.get("group") == group_id for comp in all_components)
        if is_in_use:
            raise ValueError(
                f"Group '{group_id}' is still in use and cannot be deleted."
            )
        piselfhosting_meta = self._components_data.setdefault("_piselfhosting", {})
        if (
            "group_rules" in piselfhosting_meta
            and group_id in piselfhosting_meta["group_rules"]
        ):
            del piselfhosting_meta["group_rules"][group_id]
        if (
            "group_order" in piselfhosting_meta
            and group_id in piselfhosting_meta["group_order"]
        ):
            piselfhosting_meta["group_order"].remove(group_id)
        self._save_metadata()

    def rename_group(self, group_id: str, new_name: str):
        """Renames the display name of an existing group."""
        piselfhosting_meta = self._components_data.setdefault("_piselfhosting", {})
        group_rules = piselfhosting_meta.setdefault("group_rules", {})
        if group_id not in group_rules:
            raise ValueError(f"Group '{group_id}' not found.")
        group_rules[group_id]["name"] = new_name
        self._save_metadata()

    def _get_component_config_path(self, component_id: str) -> Path:
        return self.templates_path / component_id / "template-config"

    def update_component_variables(
        self, component_id: str, variables_payload: Dict[str, Any]
    ):
        """
        Performs a non-destructive update of the variables.json file.
        """
        # --- START OF FIX: NON-DESTRUCTIVE READ-MERGE-WRITE ---
        config_path = self._get_component_config_path(component_id)
        variables_file = config_path / "variables.json"
        config_path.mkdir(parents=True, exist_ok=True)

        # 1. READ: Load the full original content of the file.
        # Default to an empty dict if the file doesn't exist.
        original_data = {}
        if variables_file.exists():
            try:
                with open(variables_file, "r", encoding="utf-8") as f:
                    original_data = json.load(f)
            except json.JSONDecodeError:
                # If file is corrupt, start fresh but log a warning.
                logger.warning(
                    "Could not parse existing variables.json for %s. "
                    "File will be overwritten.",
                    component_id,
                )

        # 2. MERGE: Update the 'variables' key with the new payload.
        # This preserves all other top-level keys like 'other_files'.
        original_data["variables"] = variables_payload.get("variables", [])

        # 3. WRITE: Save the entire merged data structure back to the file.
        with open(variables_file, "w", encoding="utf-8") as f:
            json.dump(original_data, f, indent=2, sort_keys=True)
        # --- END OF FIX ---

        # Update the in-memory cache to reflect the change.
        self._variables_cache[component_id] = original_data.get("variables", [])

    def get_component_template_content(self, component_id: str) -> str:
        template_file = (
            self.templates_path / component_id / "docker-compose.template.yml"
        )
        try:
            with open(template_file, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            return f"# Template for {component_id} not found.\n"

    def update_component_template_content(self, component_id: str, content: str):
        component_path = self.templates_path / component_id
        component_path.mkdir(parents=True, exist_ok=True)
        with open(
            component_path / "docker-compose.template.yml", "w", encoding="utf-8"
        ) as f:
            f.write(content)

    def delete_component(self, component_id: str):
        components = self._components_data.get("components", {})
        if component_id not in components:
            raise KeyError(f"Component '{component_id}' not found.")
        del components[component_id]
        piselfhosting_meta = self._components_data.get("_piselfhosting", {})
        if (
            "components_order" in piselfhosting_meta
            and component_id in piselfhosting_meta["components_order"]
        ):
            piselfhosting_meta["components_order"].remove(component_id)
        component_path = self.templates_path / component_id
        if component_path.exists() and component_path.is_dir():
            try:
                import shutil

                shutil.rmtree(component_path)
                logger.info(f"Deleted component directory: {component_path}")
            except OSError as e:
                logger.error(f"Error deleting directory {component_path}: {e}")
                self._save_metadata()
                raise e
        self._save_metadata()

    def _get_traefik_labels(
        self,
        component_id: str,
        traefik_host: str,
        fqdn_suffix: str,
        traefik_internal_port: int,
    ) -> List[str]:
        """
        Generates the standard Traefik labels for a service.
        """
        return [
            "traefik.enable=true",
            f"traefik.http.routers.{component_id}.entrypoints=websecure",
            (
                f"traefik.http.routers.{component_id}.rule="
                f"Host(`{traefik_host}.{fqdn_suffix}`)"
            ),
            f"traefik.http.routers.{component_id}.tls=true",
            (
                f"traefik.http.services.{component_id}.loadbalancer."
                f"server.port={traefik_internal_port}"
            ),
        ]

    def _get_traefik_labels_yaml_block(
        self,
        component_id: str,
        traefik_host: str,
        fqdn_suffix: str,
        traefik_internal_port: int,
    ) -> str:
        """
        Generates the standard Traefik labels as a fully formatted,
        indented YAML block string.
        """
        labels = self._get_traefik_labels(
            component_id, traefik_host, fqdn_suffix, traefik_internal_port
        )
        yaml_block = "\n".join(f"      - {label}" for label in labels)
        return yaml_block

    def render_component_template(
        self,
        component_id: str,
        context: Dict[str, Any],
    ) -> str:
        """
        Loads a component's template, injects Traefik labels, and renders it.
        Includes a brute-force fallback for stubborn variables.
        """
        # 1. Haal details op
        component_details = self.get_component_details(component_id)
        if not component_details:
            logger.error(f"Component '{component_id}' not found for rendering.")
            return "services: {}"

        # 2. Laad component defaults (alleen als ze nog niet in context zitten)
        component_variable_definitions = self._variables_cache.get(component_id, [])
        for var_def in component_variable_definitions:
            var_id = var_def.get("id")
            if var_id and var_id not in context and "default" in var_def:
                context[var_id] = var_def["default"]

        # Safety Net: Forceer de base path als hij mist
        if "CONFIG_BASE_PATH" not in context:
            context["CONFIG_BASE_PATH"] = "../piselfhosting_data"

        # 3. Laad template
        template_content = self.get_component_template_content(component_id)

        # 4. Traefik voorbereiding
        has_traefik_support = component_details.get("has_traefik_support", False)
        context["has_traefik_support"] = has_traefik_support
        context["component_id"] = component_id

        traefik_internal_port = component_details.get("traefik_internal_port")
        traefik_host = context.get("TRAEFIK_HOST")
        fqdn_suffix = context.get("FQDN_SUFFIX")

        excluded_ports: Set[int] = set()
        component_vars = component_details.get("required_variables", [])
        for var in component_vars:
            if var.get("type") == "port_exclude_traefik":
                var_id = var.get("id")
                val = context.get(var_id)
                try:
                    if val is not None:
                        excluded_ports.add(int(val))
                except (ValueError, TypeError):
                    pass

        is_internal_port_excluded = (
            isinstance(traefik_internal_port, int)
            and traefik_internal_port in excluded_ports
        )

        should_generate_labels = (
            has_traefik_support
            and isinstance(traefik_internal_port, int)
            and traefik_host is not None
            and fqdn_suffix is not None
            and not is_internal_port_excluded
        )

        if should_generate_labels:
            my_casted_traefik_internal_port = cast(int, traefik_internal_port)
            yaml_block = self._get_traefik_labels_yaml_block(
                component_id=component_id,
                traefik_host=str(traefik_host),
                fqdn_suffix=str(fqdn_suffix),
                traefik_internal_port=my_casted_traefik_internal_port,
            )
            context["traefik_labels_yaml"] = yaml_block
        else:
            context["traefik_labels_yaml"] = ""

        # 5. RENDERING (Met Brute Force Fallback)
        try:
            template = Template(template_content)
            rendered = template.render(**context)

            # --- BRUTE FORCE FIX ---
            # Als Jinja2 het niet gedaan heeft, doen we het zelf.
            if "{{ CONFIG_BASE_PATH }}" in rendered:
                logger.warning(
                    f"Jinja missed CONFIG_BASE_PATH in {component_id}. "
                    f"Using brute force replace."
                )
                base_path = str(
                    context.get("CONFIG_BASE_PATH", "../piselfhosting_data")
                )
                rendered = rendered.replace("{{ CONFIG_BASE_PATH }}", base_path)
            # -----------------------

            return rendered
        except Exception as e:
            logger.error(
                f"Error rendering template for {component_id}: {e}", exc_info=True
            )
            return f"# ERROR: Template rendering failed: {e}"

    def generate_deployment_artifacts(
        self,
        selected_components_data: List[Dict[str, Any]],
        global_vars: Dict[str, Any],
        output_path: Path,
    ) -> None:
        """
        Generates docker-compose.yml AND a .env file.
        Injects identification labels for the DeploymentManager.
        """
        logger.info("Starting deployment artifact generation.")
        output_path.mkdir(parents=True, exist_ok=True)

        docker_compose_data: Dict[str, Any] = {
            "services": {},
            "networks": {"piselfhosting-network": {"external": True}},
            "volumes": {},
        }

        deployment_context = global_vars.copy()

        # Forceer het pad (relatief voor de Pi)
        deployment_context["CONFIG_BASE_PATH"] = "../piselfhosting_data"

        component_ids = [
            comp_id
            for comp in selected_components_data
            if (comp_id := comp.get("id")) is not None
        ]
        sorted_ids = self.sort_components_by_master_order(component_ids)
        comp_data_map = {comp.get("id"): comp for comp in selected_components_data}

        for component_id in sorted_ids:
            component_data = comp_data_map.get(component_id)
            if not component_data:
                continue

            render_context = deployment_context.copy()
            rendered_yaml = self.render_component_template(component_id, render_context)

            try:
                comp_compose = yaml.safe_load(rendered_yaml)
                if not isinstance(comp_compose, dict):
                    comp_compose = {}
            except yaml.YAMLError:
                continue

            if "version" in comp_compose:
                docker_compose_data["version"] = comp_compose["version"]

            new_services = comp_compose.get("services", {})

            # --- FIX: Inject Component ID Label (De Sticker) ---
            # Dit zorgt ervoor dat de DeploymentManager later snapt wie wie is.
            for svc_name, svc_def in new_services.items():
                if "labels" not in svc_def:
                    svc_def["labels"] = []

                # We ondersteunen zowel lijst- als dictionary-formaat labels
                label_val = f"piselfhosting.component.id={component_id}"

                if isinstance(svc_def["labels"], list):
                    # Voorkom dubbele labels als we vaak regenereren
                    if label_val not in svc_def["labels"]:
                        svc_def["labels"].append(label_val)
                elif isinstance(svc_def["labels"], dict):
                    svc_def["labels"]["piselfhosting.component.id"] = component_id
            # ---------------------------------------------------

            docker_compose_data["services"].update(new_services)

            for net_name, net_def in comp_compose.get("networks", {}).items():
                if net_name not in docker_compose_data.get("networks", {}):
                    net_copy = net_def.copy()
                    net_copy.setdefault("external", False)
                    docker_compose_data["networks"][net_name] = net_copy

            docker_compose_data["volumes"].update(comp_compose.get("volumes", {}))

        logger.info("Writing final artifacts.")

        # 1. Write docker-compose.yml
        compose_path = output_path / "docker-compose.yml"
        with open(compose_path, "w", encoding="utf-8") as f:
            yaml.dump(docker_compose_data, f, sort_keys=False)

        # 2. Write deployment_context.json
        context_path = output_path / "deployment_context.json"
        with open(context_path, "w", encoding="utf-8") as f:
            json.dump(deployment_context, f, indent=2, sort_keys=True)

        # 3. Write .env
        env_path = output_path / ".env"
        with open(env_path, "w", encoding="utf-8") as f:
            for key, value in deployment_context.items():
                if isinstance(value, (str, int, float, bool)):
                    f.write(f"{key}={value}\n")

        logger.info("Artifact generation completed.")
