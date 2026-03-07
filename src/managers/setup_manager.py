# src/managers/setup_manager.py
import logging
from pathlib import Path
from typing import Any, Dict

from managers.component_reader import ComponentReader

logger = logging.getLogger(__name__)


class SetupManager:
    """
    Handles the initial setup and directory structure for the self-hosting environment.
    Uses ComponentReader to validate component existence during setup tasks.
    """

    def __init__(self, component_manager: ComponentReader, output_dir: Path):
        """
        Initialize the SetupManager.
        """
        self.reader = component_manager
        self.output_dir = output_dir

    def initialize_environment(self) -> bool:
        """
        Creates the necessary base directories for the deployment.
        """
        try:
            if not self.output_dir.exists():
                self.output_dir.mkdir(parents=True, exist_ok=True)
                logger.info(f"Created base directory at {self.output_dir}")

            # Create a sub-folder for logs
            log_dir = self.output_dir / "logs"
            log_dir.mkdir(exist_ok=True)

            return True
        except Exception as e:
            logger.error(f"Failed to initialize environment: {e}")
            return False

    def verify_component_setup(self, component_id: str) -> bool:
        """
        Checks if a component exists in the metadata before attempting setup.
        """
        details = self.reader.get_component_details(component_id)
        if not details:
            logger.warning(f"Component {component_id} not found in metadata.")
            return False

        logger.info(f"Verified component {component_id} for setup.")
        return True

    def get_setup_report(self) -> Dict[str, Any]:
        """
        Returns a summary of the current environment setup.
        """
        return {
            "base_path": str(self.output_dir),
            "status": "ready" if self.output_dir.exists() else "uninitialized",
            "components_available": len(self.reader.get_all_components()),
        }
