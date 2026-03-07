import json
import logging
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class ComponentWriter:
    """
    The Command side of the CQRS pattern.
    Responsible for all file system mutations and metadata updates.
    """

    def __init__(self, metadata_path: Path, templates_path: Path):
        self.metadata_file = metadata_path
        self.templates_path = templates_path

    def _save_json(self, file_path: Path, data: Any) -> bool:
        """Writes data to a JSON file with proper indentation."""
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, sort_keys=True)
            return True
        except IOError as e:
            logger.error(f"Could not save JSON to {file_path}: {e}")
            return False

    def update_component_variables(self, component_id: str, data: List[Dict]) -> bool:
        """Updates the variables.json for a specific component."""
        var_path = self.templates_path / component_id / "variables.json"
        return self._save_json(var_path, data)

    def create_component_skeleton(self, component_id: str, meta: Dict) -> bool:
        """Creates directory structure and initial files for a new component."""
        comp_dir = self.templates_path / component_id
        if comp_dir.exists():
            return False

        comp_dir.mkdir(parents=True)
        self._save_json(comp_dir / "variables.json", [])
        (comp_dir / "docker-compose.template.yml").write_text("services:\n")

        # Update master metadata
        with open(self.metadata_file, "r", encoding="utf-8") as f:
            full_meta = json.load(f)

        full_meta.setdefault("components", {})[component_id] = meta
        return self._save_json(self.metadata_file, full_meta)
