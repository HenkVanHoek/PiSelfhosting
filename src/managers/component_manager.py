import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

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
        self, component_id: str, template_content: str, variables: List[Dict[str, Any]]
    ) -> None:
        """
        Validates a component's template and variables.
        This is a placeholder for future validation logic.
        """
        # Placeholder for future validation logic

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

        # NOTE: Symmetrical conflict checks
        # (if A conflicts with B, B must conflict with A)
        # are intentionally omitted here to favor a simpler,
        # more flexible data contract.
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
        return [
            "traefik.enable=true",
            f"traefik.http.routers.{component_id}.entrypoints=" f"websecure",
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

    def render_component_template(
        self,
        component_id: str,
        context: Dict[str, Any],
    ) -> str:
        """
        Loads a component's docker-compose template, injects the necessary
        Traefik labels into the context if supported, and renders the template.
        """
        component_details = self.get_component_details(component_id)
        if not component_details:
            logger.error(f"Component '{component_id}' not found for rendering.")
            return f"# ERROR: Component '{component_id}' not found."

        template_content = self.get_component_template_content(component_id)
        template = Template(template_content)

        # 1. Prepare Traefik Labels if supported
        has_traefik_support = component_details.get("has_traefik_support", False)
        traefik_internal_port = component_details.get("traefik_internal_port")
        traefik_host = context.get("TRAEFIK_HOST")
        fqdn_suffix = context.get("FQDN_SUFFIX")

        if (
            has_traefik_support
            and isinstance(traefik_internal_port, int)
            and traefik_host is not None
            and fqdn_suffix is not None
        ):
            traefik_labels = self._get_traefik_labels(
                component_id=component_id,
                traefik_host=str(traefik_host),
                fqdn_suffix=str(fqdn_suffix),
                traefik_internal_port=traefik_internal_port,
            )
            # Add to the context for the Jinja template to use
            context["traefik_labels"] = traefik_labels
        else:
            # Ensure traefik_labels is present but empty if not supported
            context["traefik_labels"] = []

        # 2. Render the template
        try:
            rendered_content = template.render(context)
            return rendered_content
        except Exception as e:
            logger.error(f"Error rendering template for {component_id}: {e}")
            return f"# ERROR: Template rendering failed for {component_id}: {e}"
