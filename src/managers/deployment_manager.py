import json
import logging
import os
import tarfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List

import yaml

from managers.component_manager import ComponentManager
from managers.ssh_manager import SSHManager

logger = logging.getLogger(__name__)


class DeploymentManager:
    """Manages the deployment process to remote devices via SSH."""

    def __init__(self, component_manager: ComponentManager):
        self.component_manager = component_manager
        logger.info("DeploymentManager initialized.")

    @staticmethod
    def _log_update(
        tasks_dict: Dict[str, Any], task_id: str, log_text: str, is_step: bool = False
    ) -> None:
        """A centralized helper to add timestamped log entries."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        for line in log_text.strip().splitlines():
            full_message = f"[{timestamp}] {'  ' if not is_step else ''}{line}"
            tasks_dict[task_id]["logs"].append(full_message)
        tasks_dict[task_id]["last_update"] = time.time()

    def _perform_cleanup(
        self,
        ssh: SSHManager,
        components_to_clean: List[str],
        log_callback: Callable[..., None],
    ) -> None:
        """Stops, removes containers and deletes associated named volumes."""
        if not components_to_clean:
            return

        log_callback("--- Starting Pre-Flight Cleanup ---", is_step=True)
        for component_id in components_to_clean:
            log_callback(f"Cleaning resources for '{component_id}'...")
            service_name = self.component_manager.get_docker_service_name(component_id)
            container_name = f"piselfhosting-{service_name}"
            ssh.execute_command(f"docker stop {container_name}", log_callback)
            ssh.execute_command(f"docker rm {container_name}", log_callback)

            volume_name_etc = f"piselfhosting-{service_name}-etc"
            volume_name_dnsmasq = f"piselfhosting-{service_name}-dnsmasq"
            ssh.execute_command(
                f"docker volume rm {volume_name_etc} {volume_name_dnsmasq}",
                log_callback,
                check_exit_code=False,  # Ignore errors if volumes do not exist
            )
        log_callback("--- Pre-Flight Cleanup Finished ---", is_step=True)

    def _discover_service_links(
        self,
        ip: str,
        local_output_path: Path,
        log_callback: Callable[..., None],
    ) -> List[Dict[str, str]]:
        """Reads deployment artifacts to discover and construct web UI links."""
        log_callback("Discovering web interfaces for services...", is_step=True)
        try:
            context_path = local_output_path / "deployment_context.json"
            with open(context_path, "r", encoding="utf-8") as f:
                deployment_context = json.load(f)

            compose_path = local_output_path / "docker-compose.yml"
            with open(compose_path, "r", encoding="utf-8") as f:
                compose_data = yaml.safe_load(f)

            all_components_list = self.component_manager.get_all_components()
            all_components_map = {c["id"]: c for c in all_components_list}

            service_links = []
            for s_def in compose_data.get("services", {}).values():
                component_id = next(
                    (
                        label.split("=", 1)[1]
                        for label in s_def.get("labels", [])
                        if label.startswith("piselfhosting.component.id=")
                    ),
                    None,
                )

                if not (
                    component_id
                    and (comp_meta := all_components_map.get(component_id))
                    and comp_meta.get("has_ui")
                ):
                    continue

                port_var = next(
                    (
                        var
                        for var in comp_meta.get("required_variables", [])
                        if var.get("type") == "port"
                        and ("WEB" in var.get("id", "") or "HTTP" in var.get("id", ""))
                    ),
                    None,
                )

                if port_var and (port := deployment_context.get(port_var["id"])):
                    protocol = comp_meta.get("protocol", "http")
                    url = f"{protocol}://{ip}:{port}"
                    service_links.append({"name": comp_meta.get("name"), "url": url})

            log_text = (
                f"SUCCESS: Found {len(service_links)} web UIs."
                if service_links
                else "WARN: No web UIs were discovered."
            )
            log_callback(log_text, is_step=True)
            return service_links

        except Exception as e:
            logger.error(f"Error discovering service links: {e}", exc_info=True)
            log_callback(f"FATAL: UI Discovery error: {e}", is_step=True)
            return []

    def _transfer_and_extract_archive(
        self,
        ssh: SSHManager,
        local_path: Path,
        remote_path: Path,
        task_id: str,
        log_callback: Callable[..., None],
    ) -> bool:
        """Creates, uploads, and extracts the deployment tarball."""
        log_callback("Creating and uploading deployment archive...", is_step=True)
        remote_tmp_tarball = f"/tmp/deployment-{task_id}.tar.gz"  # nosec B108
        tarball_path = local_path / f"deployment-{task_id}.tar.gz"

        try:
            with tarfile.open(tarball_path, "w:gz") as tar:
                tar.add(local_path, arcname=os.path.basename(local_path))
            with open(tarball_path, "rb") as f:
                ssh.upload_content(f.read(), remote_tmp_tarball)
        finally:
            if os.path.exists(tarball_path):
                os.remove(tarball_path)

        log_callback("Extracting remote archive...", is_step=True)
        ssh.execute_command(f"mkdir -p {remote_path}", log_callback)
        exit_code, _ = ssh.execute_command(
            f"tar -xzf {remote_tmp_tarball} -C {remote_path} --strip-components=1",
            log_callback,
        )
        ssh.execute_command(f"rm {remote_tmp_tarball}", log_callback)
        return exit_code == 0

    def start_deployment(
        self,
        task_id: str,
        tasks_dict: Dict[str, Any],
        output_path: str,
        managed_devices: List[Dict[str, Any]],
        components_to_clean: List[str],
    ) -> None:
        """Main entry point to orchestrate the deployment process."""

        # --- FIX: Converted lambda to a nested def to fix flake8 E731 ---
        def log_callback(text: str, is_step: bool = False) -> None:
            self._log_update(tasks_dict, task_id, text, is_step)

        log_callback("Deployment process initiated...", is_step=True)

        if not managed_devices or not (device := managed_devices[0]):
            log_callback("ERROR: No valid devices for deployment.", is_step=True)
            tasks_dict[task_id]["status"] = "failed"
            return

        ip, user, pwd = device.get("ip"), device.get("username"), device.get("password")
        if not all([ip, user, pwd]):
            log_callback("ERROR: Device details are incomplete.", is_step=True)
            tasks_dict[task_id]["status"] = "failed"
            return

        overall_success = False
        ssh = SSHManager(hostname=ip, username=user, password=pwd)
        log_callback(f"--- Processing device: {ip} ---", is_step=True)
        try:
            connected, msg = ssh.connect()
            if not connected:
                log_callback(f"ERROR: Failed to connect to {ip}: {msg}", is_step=True)
                return

            self._perform_cleanup(ssh, components_to_clean, log_callback)

            exit_code, home = ssh.execute_command("echo $HOME", log_callback)
            if exit_code != 0 or not home:
                log_callback("FATAL: Could not get remote home dir.", is_step=True)
                return

            remote_dir = Path(home) / "piselfhosting_deployment"
            if not self._transfer_and_extract_archive(
                ssh, Path(output_path), remote_dir, task_id, log_callback
            ):
                log_callback("FATAL: Archive transfer failed.", is_step=True)
                return

            log_callback("Executing deployment...", is_step=True)
            exit_code, _ = ssh.execute_command(
                f"cd {remote_dir} && docker compose up -d", log_callback
            )
            if exit_code != 0:
                log_callback("ERROR: Deployment command failed.", is_step=True)
                return

            # --- FIX: Added check for ip to satisfy mypy [arg-type] ---
            if not ip:
                log_callback(
                    "FATAL: IP address is missing, " "cannot discover links.",
                    is_step=True,
                )
                return

            links = self._discover_service_links(ip, Path(output_path), log_callback)
            if links:
                tasks_dict[task_id]["service_links"] = links

            overall_success = True

        except Exception as e:
            logger.error(f"Unexpected deployment error: {e}", exc_info=True)
            log_callback(f"FATAL: An unexpected error occurred: {e}", is_step=True)
        finally:
            log_callback("Closing SSH connection.", is_step=True)
            ssh.close()
            tasks_dict[task_id]["status"] = "completed" if overall_success else "failed"
