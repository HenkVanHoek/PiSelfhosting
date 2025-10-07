import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, cast

import yaml  # <-- IMPORTED: PyYAML for YAML parsing
from jinja2 import Template

logger = logging.getLogger(__name__)


class ComponentManager:
    """MAnages component metadata and template files."""

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
        into a central cache. This is now the SST for variables.
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
        Returns the full details for a single component, merging metadata
        and variables from their respective sources.
        """
        component_data = self._components_data.get("components", {}).get(component_id)
        if not component_data:
            return None
        details = component_data.copy()
        details["id"] = component_id
        details["required_variables"] = self._variables_cache.get(component_id, [])
        # ADDED: Defensive retrieval of optional Traefik metadata fields (Issue #2)
        details["has_traefik_support"] = component_data.get(
            "has_traefik_support", False
        )
        details["traefik_internal_port"] = component_data.get(
            "traefik_internal_port", None
        )
        # START OF NEW FEATURE: Conflicts With
        details["conflicts_with"] = component_data.get("conflicts_with", [])
        # END OF NEW FEATURE: Conflicts With
        return details

    def validate_component_configuration(
        self,
        _component_id: str,
        template_content: str,
        _variables: List[Dict[str, Any]],
    ) -> None:
        """
        Validates a component's template and variables.

        CRITICAL VALIDATION: Ensures explicit 'container_name' fields adhere
        to the 'piselfhosting-' naming convention.
        """
        # 1. TEMPLATE VALIDATION: Enforce Naming Convention
        try:
            # Use safe_load to parse Jinja-templated YAML content
            data = yaml.safe_load(template_content)
        except yaml.YAMLError as e:
            # This is a critical parsing failure, indicating malformed YAML syntax
            raise ValueError(
                f"YAML Parsing Failed: The template content is not valid YAML. "
                f"Error: {e}"
            )

        services = data.get("services", {})
        for service_name, service_data in services.items():
            container_name = service_data.get("container_name")

            # Enforce the convention only if container_name is explicitly set
            if container_name:
                mandatory_prefix = "piselfhosting-"
                if not container_name.lower().startswith(mandatory_prefix):
                    raise ValueError(
                        f"Naming Violation: The container_name '{container_name}' "
                        f"for service '{service_name}' must begin with the "
                        f"mandatory prefix '{mandatory_prefix}'."
                        f" Please correct the template."
                    )

        # 2. Variable Validation (Placeholder)
        # Placeholder for future variable validation logic (e.g., checking types)

    def validate_metadata_conflicts(
        self, component_id: str, conflicts_with_list: List[str]
    ) -> None:
        """
        CRITICAL: Validates the 'conflicts_with' list for a component.

        This method checks for two critical metadata errors:
        1. Self-conflict: A component cannot conflict with itself.
        2. Non-existent ID: A conflict must refer to an actual component ID.

        Raises:
            ValueError: If a conflict rule is invalid.
        """
        # 1. Self-Conflict Check
        if component_id in conflicts_with_list:
            raise ValueError(
                f"Self-Conflict Error: Component '{component_id}' cannot "
                "conflict with itself. Please remove it from the list."
            )

        # 2. Non-existent ID Check
        all_component_ids = set(self._components_data.get("components", {}).keys())

        non_existent_conflicts = [
            cid for cid in conflicts_with_list if cid not in all_component_ids
        ]

        if non_existent_conflicts:
            non_existent_str = ", ".join(non_existent_conflicts)
            raise ValueError(
                "Non-Existent ID Error: The following component ID(s) "
                f"listed in 'Conflicts With' do not exist in the system: "
                f"{non_existent_str}. Please correct them."
            )

        # NOTE: Symmetrical conflict checks (if A conflicts with B, B must
        # conflict with A)
        # are intentionally omitted here to favor a simpler, more
        # flexible data contract.
        # This one-way check is sufficient for developer-facing validation.

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
            "conflicts_with": [],  # Initialize the new field
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
        self, component_id: str, variables_data: Dict[str, Any]
    ):
        config_path = self._get_component_config_path(component_id)
        config_path.mkdir(parents=True, exist_ok=True)
        with open(config_path / "variables.json", "w", encoding="utf-8") as f:
            json.dump(variables_data, f, indent=2, sort_keys=True)
        self._variables_cache[component_id] = variables_data.get("variables", [])

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
        Generates the standard Traefik labels for a service, substituting
        the component-specific and global variables.
        """
        # CRITICAL: Note the use of backticks in the rule template
        # for `{{ TRAEFIK_HOST }}.{{ FQDN_SUFFIX }}`.
        # The Traefik router/service ID must be the canonical component ID
        # to ensure unique routing.
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
        indented YAML block string suitable for direct injection into a template.
        """
        labels = self._get_traefik_labels(
            component_id, traefik_host, fqdn_suffix, traefik_internal_port
        )
        # Indentation: The template adds the initial indentation for 'labels:'
        # We need to add '      - ' before each label.
        yaml_block = "\n".join(f"      - {label}" for label in labels)
        return yaml_block

    def render_component_template(
        self,
        component_id: str,
        context: Dict[str, Any],
    ) -> str:
        """
        Loads a component's docker-compose template, injects the necessary
        Traefik labels into the context if supported, and renders the template.
        """
        logger.debug(f"Attempting to render template for component ID: {component_id}")
        component_details = self.get_component_details(component_id)
        if not component_details:
            logger.error(f"Component '{component_id}' not found for rendering.")
            # CRITICAL FIX (v6.7): Return a valid, minimal YAML document
            # (no version, just empty services) to prevent the ValueError crash
            # in generate_deployment_artifacts's yaml.safe_load.
            return "services: {}"

        template_content = self.get_component_template_content(component_id)
        template = Template(template_content)

        # 1. Prepare Traefik Labels if supported
        has_traefik_support = component_details.get("has_traefik_support", False)
        traefik_internal_port = component_details.get("traefik_internal_port")
        traefik_host = context.get("TRAEFIK_HOST")
        fqdn_suffix = context.get("FQDN_SUFFIX")

        # NEW LOGIC: Check for Port Exclusion based on new variable type
        excluded_ports: Set[int] = set()
        component_vars = component_details.get("required_variables", [])

        for var in component_vars:
            # Check the variable type for a Traefik exclusion flag.
            if var.get("type") == "port_exclude_traefik":
                var_id = var.get("id")
                # Attempt to retrieve the resolved value from the context.
                resolved_value = context.get(var_id)

                # Attempt to parse the resolved value as an integer port number.
                try:
                    if resolved_value is not None:
                        excluded_ports.add(int(resolved_value))
                except (ValueError, TypeError):
                    logger.warning(
                        f"Skipping non-integer port value '{resolved_value}' for "
                        f"excluded Traefik variable '{var_id}' in component "
                        f"'{component_id}'"
                    )

        is_internal_port_excluded = (
            isinstance(traefik_internal_port, int)
            and traefik_internal_port in excluded_ports
        )

        if is_internal_port_excluded:
            logger.info(
                f"Traefik port {traefik_internal_port} for {component_id} is "
                "excluded by user variable and will not receive labels."
            )

        # Perform the final check to determine if labels should be generated.
        should_generate_labels = (
            has_traefik_support
            and isinstance(traefik_internal_port, int)
            and traefik_host is not None
            and fqdn_suffix is not None
            and not is_internal_port_excluded
        )

        # CRITICAL FIX: Generate the entire YAML block in Python
        if should_generate_labels:
            my_casted_traefik_internal_port = cast(int, traefik_internal_port)
            yaml_block = self._get_traefik_labels_yaml_block(
                component_id=component_id,
                traefik_host=str(traefik_host),
                fqdn_suffix=str(fqdn_suffix),
                traefik_internal_port=my_casted_traefik_internal_port,
            )
            # Add to the context for the Jinja template to use
            context["traefik_labels_yaml"] = yaml_block
            logger.debug(
                f"Generated labels YAML block for {component_id}: " f"'{yaml_block}'"
            )
        else:
            # Ensure the placeholder is present but empty if not supported or excluded
            context["traefik_labels_yaml"] = ""
            logger.debug(
                f"No labels generated for {component_id}. traefik_labels_yaml=''"
            )

        # 2. Render the template
        try:
            # We now rely on the template to use the 'safe' filter on the already
            # formatted traefik_labels_yaml string.
            rendered_content = template.render(context)
            logger.debug(
                f"Successfully rendered {component_id}. Content size: "
                f"{len(rendered_content)}"
            )
            return rendered_content
        except Exception as e:
            logger.error(
                f"Error rendering template for {component_id}: {e}", exc_info=True
            )
            return f"# ERROR: Template rendering failed for {component_id}: {e}"

    # NEW METHOD: Deployment Artifact Generation
    def generate_deployment_artifacts(
        self,
        selected_components_data: List[Dict[str, Any]],
        global_vars: Dict[str, Any],
        output_path: Path,
    ) -> None:
        """
        Orchestrates the rendering of all selected component templates, merges
        them into a single docker-compose.yml, and saves the final context.

        Raises:
            ValueError: If a component's template cannot be parsed or merged.
        """
        logger.info("Starting deployment artifact generation.")
        # Ensure output directory exists
        output_path.mkdir(parents=True, exist_ok=True)

        # START OF FIX: Initialize volumes block
        docker_compose_data: Dict[str, Any] = {
            "services": {},
            "networks": {"piselfhosting-network": {"external": True}},
            "volumes": {},
        }
        # END OF FIX

        # The deployment context is a single source of truth for all resolved
        # variables, used later by Discovery methods.
        deployment_context = global_vars.copy()

        # 1. Sort the components by master order before processing
        component_ids = [
            comp_id
            for comp in selected_components_data
            if (comp_id := comp.get("id")) is not None
        ]
        logger.debug(f"Component IDs to process (unsorted): {component_ids}")
        sorted_ids = self.sort_components_by_master_order(component_ids)
        logger.debug(f"Component IDs to process (sorted): {sorted_ids}")

        # Create a map for quick lookup of component data
        comp_data_map = {comp.get("id"): comp for comp in selected_components_data}

        # 2. Iterate, Render, and Merge
        for component_id in sorted_ids:
            logger.debug(f"Processing component: {component_id}")

            component_data = comp_data_map.get(component_id)
            if not component_data:
                logger.warning(
                    f"Skipping component ID '{component_id}' as data is missing."
                )
                continue

            render_context = deployment_context.copy()
            rendered_yaml = self.render_component_template(component_id, render_context)
            logger.debug(f"Rendered YAML for {component_id}: {rendered_yaml[:100]}...")

            try:
                comp_compose = yaml.safe_load(rendered_yaml)
                if not isinstance(comp_compose, dict):
                    logger.error(
                        f"Rendered content for '{component_id}' is not a valid "
                        f"YAML dictionary. Content: {rendered_yaml}"
                    )
                    comp_compose = {}
            except yaml.YAMLError as e:
                logger.error(
                    f"FATAL: Failed to parse YAML for '{component_id}'. Skipping. "
                    f"Error: {e}",
                    exc_info=True,
                )
                continue

            # 3. Merge services, networks, and volumes
            new_services = comp_compose.get("services", {})
            new_networks = comp_compose.get("networks", {})
            # START OF FIX: Extract volumes from component's parsed YAML
            new_volumes = comp_compose.get("volumes", {})
            # END OF FIX

            if "version" in comp_compose:
                docker_compose_data["version"] = comp_compose["version"]

            docker_compose_data["services"].update(new_services)
            logger.debug(
                f"Merged {len(new_services)} services. Total services: "
                f"{len(docker_compose_data['services'])}"
            )

            for network_name, network_def in new_networks.items():
                if network_name not in docker_compose_data.get("networks", {}):
                    network_def.setdefault("external", False)
                    docker_compose_data["networks"][network_name] = network_def

            # START OF FIX: Merge the extracted volumes
            docker_compose_data["volumes"].update(new_volumes)
            logger.debug(
                f"Merged {len(new_volumes)} volumes. Total volumes: "
                f"{len(docker_compose_data['volumes'])}"
            )
            # END OF FIX

        # 4. Save Artifacts
        logger.info("Writing final artifacts.")
        compose_path = output_path / "docker-compose.yml"
        with open(compose_path, "w", encoding="utf-8") as f:
            yaml.dump(docker_compose_data, f, sort_keys=False)

        context_path = output_path / "deployment_context.json"
        with open(context_path, "w", encoding="utf-8") as f:
            json.dump(deployment_context, f, indent=2, sort_keys=True)

        logger.info("Artifact generation completed.")
