import json
import logging
import os
import tarfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import yaml

from managers.component_manager import ComponentManager
from managers.ssh_manager import SSHManager


class DeploymentManager:
    """Manages the deployment process to remote devices via SSH."""

    def __init__(self, component_manager):
        self.component_manager: ComponentManager = component_manager
        logging.info("DeploymentManager initialized.")

    @staticmethod
    def _log_update(
        tasks_dict: Dict, task_id: str, log_text: str, is_step: bool = False
    ):
        """A centralized helper to add timestamped log entries."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        for line in log_text.strip().splitlines():
            if is_step:
                full_message = f"[{timestamp}] {line}"
            else:
                full_message = f"[{timestamp}]   {line}"
            tasks_dict[task_id]["logs"].append(full_message)
        tasks_dict[task_id]["last_update"] = time.time()

    # --- MODIFIED: Converted from @staticmethod to instance method ---
    # This change is necessary to allow access to self.component_manager.
    def _perform_cleanup(
        self, ssh: SSHManager, components_to_clean: List[str], log_callback
    ):
        """
        Stops, removes, and deletes the named volumes for
        the specified components using a reliable,
        convention-based naming scheme.
        """
        if not components_to_clean:
            return

        log_callback("--- Starting Pre-Flight Cleanup ---", is_step=True)

        for component_id in components_to_clean:
            log_callback(f"Cleaning resources for '{component_id}'...")

            # --- MODIFIED: Centralized Naming Logic ---
            # The method now calls the authoritative source in ComponentManager
            # instead of implementing its own sanitization logic.
            service_name = self.component_manager.get_docker_service_name(component_id)
            container_name = f"piselfhosting-{service_name}"

            ssh.execute_command(
                f"docker stop {container_name}", lambda chunk: log_callback(chunk)
            )
            ssh.execute_command(
                f"docker rm {container_name}", lambda chunk: log_callback(chunk)
            )

            volume_name_etc = f"piselfhosting-{service_name}-etc"
            volume_name_dnsmasq = f"piselfhosting-{service_name}-dnsmasq"
            ssh.execute_command(
                f"docker volume rm" f" {volume_name_etc} {volume_name_dnsmasq}",
                lambda chunk: log_callback(chunk),
            )

        log_callback("--- Pre-Flight Cleanup Finished ---", is_step=True)

    def start_deployment(
        self,
        task_id: str,
        tasks_dict: Dict,
        output_path: str,
        managed_devices: List[Dict[str, Any]],
        components_to_clean: List[str],
    ):
        overall_success = True

        def log_callback(text, is_step=False):
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
                f"ERROR: Failed to connect to" f" {ip}: {connect_message}", is_step=True
            )
            tasks_dict[task_id]["status"] = "failed"
            return

        log_callback("Creating secure temporary file on remote host...", is_step=True)
        exit_code, remote_tmp_tarball = ssh.execute_command("mktemp", lambda _: None)
        if exit_code != 0 or not remote_tmp_tarball:
            log_callback(
                "FATAL ERROR: Could not create " "remote temporary file.", is_step=True
            )
            tasks_dict[task_id]["status"] = "failed"
            ssh.close()
            return

        local_output_path = Path(output_path)
        try:
            # --- MODIFIED: Call is now an instance method call ---
            self._perform_cleanup(ssh, components_to_clean, log_callback)

            log_callback("Discovering remote home directory...", is_step=True)
            exit_code, remote_home_dir = ssh.execute_command(
                "echo $HOME", lambda _: None
            )
            if exit_code != 0 or not remote_home_dir:
                log_callback(
                    "FATAL ERROR: Could not determine " "remote home directory.",
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
                with open(tarball_path, "rb") as f:
                    content = f.read()
                ssh.upload_content(content, remote_tmp_tarball)
                os.remove(tarball_path)

                log_callback("Extracting remote archive...", is_step=True)
                ssh.execute_command(
                    f"mkdir -p " f"{remote_deployment_dir}", lambda _: None
                )
                ssh.execute_command(
                    f"tar -xzf "
                    f"{remote_tmp_tarball} -C {remote_deployment_dir} "
                    "--strip-components=1",
                    lambda chunk: log_callback(chunk),
                )

                log_callback("Executing deployment...", is_step=True)
                exit_code, _ = ssh.execute_command(
                    f"cd {remote_deployment_dir} && docker compose up -d",
                    lambda chunk: log_callback(chunk),
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
                    with open(context_path, "rb") as f:
                        deployment_context = json.load(f)

                    service_links = []
                    all_components = self.component_manager.get_all_components_dict()

                    compose_path = local_output_path / "docker-compose.yml"
                    with open(compose_path, "rb") as f:
                        compose_data = yaml.safe_load(f)

                    deployed_service_names = compose_data.get("services", {}).keys()

                    for service_name in deployed_service_names:
                        # --- MODIFIED: To correctly find the component metadata ---
                        # We must sanitize the service name from the compose file
                        # to look up its corresponding canonical component ID.
                        # This is the reverse operation of get_docker_service_name.
                        component_id_guess = service_name.replace(
                            "piselfhosting-", "", 1
                        )
                        component_meta = all_components.get(component_id_guess)
                        if not component_meta:  # Fallback for hyphenated names
                            component_meta = all_components.get(
                                component_id_guess.replace("pihole", "pi-hole")
                            )  # Example

                        if not (component_meta and component_meta.get("has_ui")):
                            continue

                        port_variable_name = None
                        if component_meta.get("required_variables"):
                            for var in component_meta["required_variables"]:
                                if var.get("type") == "port" and (
                                    "WEB" in var.get("name", "")
                                    or "HTTP" in var.get("name", "")
                                ):
                                    port_variable_name = var["name"]
                                    break

                        if port_variable_name:
                            final_host_port = deployment_context.get(port_variable_name)
                            if final_host_port:
                                protocol = component_meta.get("protocol", "http")
                                canonical_id = [
                                    k
                                    for k, v in all_components.items()
                                    if v == component_meta
                                ]
                                service_url = f"{protocol}://{ip}" f":{final_host_port}"
                                service_links.append(
                                    {
                                        "name": component_meta.get(
                                            "name", canonical_id
                                        ),
                                        "url": service_url,
                                    }
                                )

                    if service_links:
                        tasks_dict[task_id]["service_links"] = service_links
                        log_callback(
                            f"SUCCESS: Found {len(service_links)} "
                            f"web interface(s).",
                            is_step=True,
                        )
                except Exception as e:
                    log_callback(
                        f"WARN: Could not discover web interfaces:" f" {e}",
                        is_step=True,
                    )

        finally:
            log_callback("Cleaning up remote archive...", is_step=True)
            ssh.execute_command(f"rm {remote_tmp_tarball}", lambda _: None)
            log_callback("Closing final SSH connection.", is_step=True)
            ssh.close()

        tasks_dict[task_id]["status"] = "completed" if (overall_success) else "failed"
