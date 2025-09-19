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


class DeploymentManager:
    """Manages the deployment process to remote devices via SSH."""

    def __init__(self, component_manager: ComponentManager):
        self.component_manager = component_manager
        logging.info("DeploymentManager initialized.")

    @staticmethod
    def _log_update(
        tasks_dict: Dict[str, Any], task_id: str, log_text: str, is_step: bool = False
    ) -> None:
        """A centralized helper to add timestamped log entries."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        for line in log_text.strip().splitlines():
            if is_step:
                full_message = f"[{timestamp}] {line}"
            else:
                full_message = f"[{timestamp}]   {line}"
            tasks_dict[task_id]["logs"].append(full_message)
        tasks_dict[task_id]["last_update"] = time.time()

    def _perform_cleanup(
        self,
        ssh: SSHManager,
        components_to_clean: List[str],
        log_callback: Callable[..., None],
    ) -> None:
        """
        Stops, removes, and deletes the named volumes for the specified components
        using a reliable, convention-based naming scheme.
        """
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
            )

        log_callback("--- Pre-Flight Cleanup Finished ---", is_step=True)

    def start_deployment(
        self,
        task_id: str,
        tasks_dict: Dict[str, Any],
        output_path: str,
        managed_devices: List[Dict[str, Any]],
        components_to_clean: List[str],
    ) -> None:
        overall_success = True

        def log_callback(text: str, is_step: bool = False) -> None:
            self._log_update(tasks_dict, task_id, text, is_step)

        log_callback("Deployment process initiated...", is_step=True)

        if not managed_devices:
            log_callback(
                "ERROR: No managed devices were provided for deployment.", is_step=True
            )
            tasks_dict[task_id]["status"] = "failed"
            return

        first_device, *_ = managed_devices
        ip = first_device.get("ip")
        username = first_device.get("username")
        password = first_device.get("password")

        if not all([ip, username, password]):
            log_callback("WARN: Skipping device with incomplete details.", is_step=True)
            tasks_dict[task_id]["status"] = "failed"
            return

        log_callback(f"--- Processing device: {ip} ---", is_step=True)
        ssh = SSHManager(hostname=ip, username=username, password=password)
        connected, connect_message = ssh.connect()
        if not connected:
            log_callback(
                f"ERROR: Failed to connect to {ip}: {connect_message}", is_step=True
            )
            tasks_dict[task_id]["status"] = "failed"
            return

        remote_tmp_tarball = f"/tmp/deployment-{task_id}.tar.gz"  # nosec B108
        local_output_path = Path(output_path)
        try:
            self._perform_cleanup(ssh, components_to_clean, log_callback)

            log_callback("Discovering remote home directory...", is_step=True)
            exit_code, remote_home_dir = ssh.execute_command(
                "echo $HOME", lambda _: None
            )
            if exit_code != 0 or not remote_home_dir:
                log_callback(
                    "FATAL ERROR: Could not determine remote home directory.",
                    is_step=True,
                )
                overall_success = False

            if overall_success:
                remote_deployment_dir = (
                    Path(remote_home_dir) / "piselfhosting_deployment"
                )

                log_callback(
                    "Creating and uploading deployment archive...", is_step=True
                )
                tarball_path = local_output_path / "deployment.tar.gz"
                with tarfile.open(tarball_path, "w:gz") as tar:
                    tar.add(local_output_path, arcname=os.path.basename(output_path))
                # --- THE DEFINITIVE FIX: Use a unique variable name ---
                with open(tarball_path, "rb") as tarball_file:
                    content = tarball_file.read()
                ssh.upload_content(content, remote_tmp_tarball)
                os.remove(tarball_path)

                log_callback("Extracting remote archive...", is_step=True)
                ssh.execute_command(f"mkdir -p {remote_deployment_dir}", lambda _: None)
                ssh.execute_command(
                    (
                        f"tar -xzf {remote_tmp_tarball} -C "
                        f"{remote_deployment_dir} --strip-components=1"
                    ),
                    log_callback,
                )

                log_callback("Executing deployment...", is_step=True)
                exit_code, _ = ssh.execute_command(
                    f"cd {remote_deployment_dir} && docker compose up -d", log_callback
                )
                if exit_code != 0:
                    log_callback("ERROR: Deployment command failed.", is_step=True)
                    overall_success = False

            if overall_success:
                log_callback(
                    "Discovering web interfaces for deployed services...", is_step=True
                )
                try:
                    context_path = local_output_path / "deployment_context.json"
                    # --- THE DEFINITIVE FIX: Use a unique variable name ---
                    with open(context_path, "r", encoding="utf-8") as context_file:
                        deployment_context = json.load(context_file)

                    service_links = []
                    all_components = self.component_manager.get_all_components_dict()

                    compose_path = local_output_path / "docker-compose.yml"
                    # --- THE DEFINITIVE FIX: Use a unique variable name ---
                    with open(compose_path, "r", encoding="utf-8") as compose_file:
                        compose_data = yaml.safe_load(compose_file)

                    for s_name, s_def in compose_data.get("services", {}).items():
                        component_id = None
                        for label in s_def.get("labels", []):
                            if label.startswith("piselfhosting.component.id="):
                                _, value = label.split("=", 1)
                                component_id = value
                                break

                        if not component_id:
                            continue

                        component_meta = all_components.get(component_id)
                        if not component_meta or not component_meta.get("has_ui"):
                            continue

                        port_variable_name = None
                        if component_meta.get("required_variables"):
                            for var in component_meta["required_variables"]:
                                var_id = var.get("id", "")
                                if var.get("type") == "port" and (
                                    "WEB" in var_id or "HTTP" in var_id
                                ):
                                    port_variable_name = var_id
                                    break

                        if port_variable_name:
                            final_port = deployment_context.get(port_variable_name)
                            if final_port:
                                protocol = component_meta.get("protocol", "http")
                                url = f"{protocol}://{ip}:{final_port}"
                                service_links.append(
                                    {
                                        "name": component_meta.get(
                                            "name", component_id
                                        ),
                                        "url": url,
                                    }
                                )

                    if service_links:
                        tasks_dict[task_id]["service_links"] = service_links
                        log_callback(
                            f"SUCCESS: Found {len(service_links)} web UIs.",
                            is_step=True,
                        )
                    else:
                        log_callback("WARN: No web UIs were discovered.", is_step=True)

                except Exception as e:
                    log_callback(f"FATAL: Discovery error: {e}", is_step=True)

        finally:
            log_callback("Cleaning up remote archive...", is_step=True)
            ssh.execute_command(f"rm {remote_tmp_tarball}", lambda _: None)
            log_callback("Closing final SSH connection.", is_step=True)
            ssh.close()

        tasks_dict[task_id]["status"] = "completed" if overall_success else "failed"
