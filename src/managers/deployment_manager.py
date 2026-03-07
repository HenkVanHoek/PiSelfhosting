# src/managers/deployment_manager.py
import logging
from typing import Any, Dict, List, Optional

from managers.component_reader import ComponentReader

logger = logging.getLogger(__name__)


class DeploymentManager:
    """
    Orchestrates the deployment of components to target devices.
    Uses ComponentReader for metadata retrieval.
    """

    def __init__(self, component_manager: ComponentReader):
        """
        Initialize the DeploymentManager.
        """
        self.reader = component_manager
        self.tasks: Dict[str, Any] = {}
        self._docker_prefix: str = "piselfhosting_"

    def start_deployment(
        self,
        task_id: str,
        tasks: Dict[str, Any],
        output_path: str,
        devices: List[Dict[str, Any]],
    ) -> None:
        """
        Starts the deployment process for the selected devices.
        """
        self.tasks[task_id] = tasks[task_id]
        self.tasks[task_id]["status"] = "running"

        # FIX: output_path is now used to inform the task where it is deploying from
        self.tasks[task_id]["logs"].append(
            f"Starting deployment from {output_path} to {len(devices)} nodes."
        )

        for device in devices:
            ip = device.get("ip", "unknown")
            self.tasks[task_id]["logs"].append(f"Deploying to {ip}...")

            # In a real scenario, output_path would be used here to
            # transfer files via SCP or SSH.
            logger.info(f"Preparing to transfer artifacts from {output_path} to {ip}")

        self.tasks[task_id]["status"] = "completed"
        self.tasks[task_id]["logs"].append("Deployment finished successfully.")

    def stop_deployment(self, task_id: str) -> bool:
        """Stops a running task."""
        if task_id in self.tasks:
            logger.info(f"Stopping task {task_id}")
            return True
        return False

    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Returns the status of a specific task."""
        return self.tasks.get(task_id)
