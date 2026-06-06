# src/managers/deployment_manager.py
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import ansible_runner

logger = logging.getLogger(__name__)


class DeploymentManager:
    """
    Orchestrates the deployment of components to target devices using Ansible.
    Uses the locally generated artifacts as the Single Source of Truth (SST).
    """

    def __init__(self, component_manager: Any):
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
        components_to_clean: Optional[List[str]] = None,
        components_to_restart: Optional[List[str]] = None,
        selected_components_data: Optional[List[Dict[str, Any]]] = None,
        global_vars: Optional[Dict[str, str]] = None,
    ) -> None:
        """
        Executes the deployment by calling Ansible with the local artifact path.
        Now safely accepts additional configuration flags from the UI.
        """
        # Ensure default values if none are provided
        components_to_clean = components_to_clean or []
        components_to_restart = components_to_restart or []
        selected_components_data = selected_components_data or []
        global_vars = global_vars or {}

        self.tasks[task_id] = tasks[task_id]
        self.tasks[task_id]["status"] = "running"

        # Base directory for Ansible execution (project root) We calculate this
        # absolutely: deployment_manager.py -> managers -> src -> PiSelfhosting
        project_root = str(Path(__file__).resolve().parent.parent.parent)
        playbook_path = os.path.join(project_root, "ansible", "playbook.yml")

        for device in devices:
            ip = device.get("ip", "unknown")
            ssh_user = device.get("username", os.getenv("SSH_USER", "admin"))
            ssh_password = device.get("password")

            self.tasks[task_id]["logs"].append(f"Deploying unified config to {ip}...")

            if components_to_clean:
                self.tasks[task_id]["logs"].append(
                    f"INFO: Scheduled for clean install: "
                    f"{', '.join(components_to_clean)}"
                )
            if components_to_restart:
                self.tasks[task_id]["logs"].append(
                    f"INFO: Scheduled for post-install restart: "
                    f"{', '.join(components_to_restart)}"
                )

            try:
                # Prepare extravars for Ansible
                extravars = {
                    "ansible_user": ssh_user,
                    "local_output_path": output_path,
                    "components_to_clean": components_to_clean,
                    "components_to_restart": components_to_restart,
                    "selected_components_data": selected_components_data,
                    "global_vars": global_vars,
                }

                # Add password if we have it from the UI,
                # otherwise Ansible assumes SSH keys
                if ssh_password:
                    extravars["ansible_password"] = ssh_password
                    extravars["ansible_become_password"] = ssh_password

                # Execute Ansible and pass the local path and new flags as variables
                runner = ansible_runner.run(
                    private_data_dir=project_root,
                    playbook=playbook_path,
                    inventory={"all": {"hosts": {ip: {}}}},
                    extravars=extravars,
                    quiet=False,
                )

                for event in runner.events:
                    event_name = event.get("event")
                    event_data = event.get("event_data", {})

                    if event_name == "runner_on_ok":
                        task_name = event_data.get("task", "Unknown Task")
                        self.tasks[task_id]["logs"].append(f"OK: {task_name}")

                        # Catch warnings embedded in the task result
                        res = event_data.get("res", {})
                        if isinstance(res, dict):
                            for warning_msg in res.get("warnings", []):
                                self.tasks[task_id]["logs"].append(
                                    f"WARN: [{task_name}] {warning_msg}"
                                )

                    elif event_name in ["runner_on_failed", "runner_on_unreachable"]:
                        res = event_data.get("res", {})
                        err_msg = res.get("msg", "Unknown error")
                        self.tasks[task_id]["logs"].append(f"FAILED: {err_msg}")

                        # Catch detailed shell outputs, module failures or tracebacks
                        if isinstance(res, dict):
                            stderr = res.get("stderr")
                            if stderr:
                                self.tasks[task_id]["logs"].append(
                                    f"FAILED_STDERR: {stderr}"
                                )

                            module_stderr = res.get("module_stderr")
                            if module_stderr:
                                self.tasks[task_id]["logs"].append(
                                    f"MODULE_STDERR: {module_stderr}"
                                )

                            results = res.get("results")
                            if isinstance(results, list):
                                for r in results:
                                    if isinstance(r, dict) and r.get("failed", False):
                                        sub_msg = (
                                            r.get("msg")
                                            or r.get("stderr")
                                            or "Sub-task failed"
                                        )
                                        self.tasks[task_id]["logs"].append(
                                            f"SUB_FAILED: {sub_msg}"
                                        )

                    # Catch standalone global warnings (like Docker Compose
                    # parse errors)
                    elif event_name == "warning":
                        warn_msg = event_data.get("warning", "")
                        if warn_msg:
                            self.tasks[task_id]["logs"].append(f"WARN: {warn_msg}")

                if runner.status == "successful":
                    self.tasks[task_id]["logs"].append(
                        f"SUCCESS: Node {ip} deployed successfully."
                    )
                else:
                    self.tasks[task_id]["status"] = "failed"
                    self.tasks[task_id]["logs"].append(
                        f"ERROR: Deployment to {ip} did not complete successfully."
                    )

                    # Extract raw Ansible/runner stdout console to
                    # capture global crashes
                    # like Out of Memory (OOM) or syntax/process compilation issues.
                    if hasattr(runner, "stdout") and runner.stdout:
                        try:
                            runner.stdout.seek(0)
                            stdout_content = runner.stdout.read()
                            if stdout_content:
                                self.tasks[task_id]["logs"].append(
                                    "--- GLOBAL ANSIBLE CONSOLE OUTPUT ---"
                                )
                                # Grab the last few lines of the raw process stdout
                                raw_lines = stdout_content.splitlines()
                                last_lines = (
                                    raw_lines[-20:]
                                    if len(raw_lines) > 20
                                    else raw_lines
                                )
                                for line in last_lines:
                                    clean_line = line.strip()
                                    if clean_line:
                                        self.tasks[task_id]["logs"].append(
                                            f"CONSOLE: {clean_line}"
                                        )
                        except Exception as read_err:
                            logger.error(f"Failed to read runner stdout: {read_err}")

            except Exception as e:
                logger.error(f"Ansible execution error: {e}")
                self.tasks[task_id]["logs"].append(f"FATAL: {str(e)}")
                self.tasks[task_id]["status"] = "failed"

        if self.tasks[task_id]["status"] != "failed":
            self.tasks[task_id]["status"] = "completed"
            self.tasks[task_id]["logs"].append(
                "--- Global deployment sequence finished successfully ---"
            )

        # Update the final status in the shared dictionary so the UI polling sees it
        tasks[task_id] = self.tasks[task_id]
