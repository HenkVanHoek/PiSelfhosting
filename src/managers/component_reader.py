import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ComponentReader:
    """
    The Query side of the CQRS pattern.
    Handles all read operations for component metadata and variables.
    """

    def __init__(self, metadata_path: Path, templates_path: Path):
        self.metadata_file = metadata_path
        self.templates_path = templates_path
        self._cached_metadata: Dict[str, Any] = self._load_json(self.metadata_file)

    def _load_json(self, file_path: Path) -> Dict[str, Any]:
        """Centralized JSON loader to ensure consistent error handling."""
        try:
            if not file_path.exists():
                logger.warning(f"File not found: {file_path}")
                return {}
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Failed to load JSON from {file_path}: {e}")
            return {}

    def get_all_components(self) -> Dict[str, Any]:
        """Returns all defined components from the master metadata."""
        return self._cached_metadata.get("components", {})

    def get_component_details(self, component_id: str) -> Optional[Dict[str, Any]]:
        """Returns metadata for a specific component ID."""
        return self.get_all_components().get(component_id)

    def get_component_variables(self, component_id: str) -> List[Dict[str, Any]]:
        """Reads the variables.json directly from the component directory."""
        var_path = self.templates_path / component_id / "variables.json"
        data = self._load_json(var_path)
        return data if isinstance(data, list) else []

    def get_template_path(self, component_id: str) -> Path:
        """Returns the path to the docker-compose template file."""
        return self.templates_path / component_id / "docker-compose.template.yml"
