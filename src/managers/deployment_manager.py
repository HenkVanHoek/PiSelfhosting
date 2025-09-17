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

    def _perform_cleanup(
        self,
        ssh: SSHManager,
        components_to_clean: List[str],
        log_callback,
        base_template_path: Path,
    ):
        """
        Stops, removes, and dynamically discovers and deletes the named
        volumes for the specified components.
        """
        if not components_to_clean:
            return
        log_callback("--- Starting Pre-Flight Cleanup ---", is_step=True)
        for component_id in components_to_clean:
            log_callback(f"Cleaning resources for '{component_id}'...")
            service_name = self.component_manager.get_docker_service_name(component_id)
            container_name = f"piselfhosting-{service_name}"
            ssh.execute_command(
                f"docker stop {container_name}", lambda chunk: log_callback(chunk)
            )
            ssh.execute_command(
                f"docker rm {container_name}", lambda chunk: log_callback(chunk)
            )
            volume_names_to_delete = []
            try:
                template_path = (
                    base_template_path / component_id / "docker-compose.template.yml"
                )
                if template_path.is_file():
                    with open(template_path, "r") as f:
                        component_compose = yaml.safe_load(f)
                        if component_compose and "volumes" in component_compose:
                            for vol_details in component_compose["volumes"].values():
                                if (
                                    isinstance(vol_details, dict)
                                    and "name" in vol_details
                                ):
                                    volume_names_to_delete.append(vol_details["name"])
            except Exception as e:
                log_callback(f"WARN: Could not parse volumes for '{component_id}': {e}")
            if volume_names_to_delete:
                volumes_str = " ".join(volume_names_to_delete)
                log_callback(f"Removing discovered volumes: {volumes_str}")
                ssh.execute_command(
                    f"docker volume rm {volumes_str}",
                    lambda chunk: log_callback(chunk),
                )
            else:
                log_callback(f"No named volumes found to clean for '{component_id}'.")
        log_callback("--- Pre-Flight Cleanup Finished ---", is_step=True)

    def start_deployment(
        self,
        task_id: str,
        tasks_dict: Dict,
        output_path: str,
        managed_devices: List[Dict[str, Any]],
        components_to_clean: List[str],
        components_to_restart: List[str],
    ):
        def log_callback(text, is_step=False):
            self._log_update(tasks_dict, task_id, text, is_step)

        log_callback("Deployment process initiated...", is_step=True)
        if not managed_devices:
            log_callback("ERROR: No devices selected for deployment.", is_step=True)
            tasks_dict[task_id]["status"] = "failed"
            return
        overall_success = True
        all_service_links = []
        local_output_path = Path(output_path)
        base_template_path = (
            Path(self.component_manager.metadata_file).parent.parent
            / "component_templates"
        )
        for device in managed_devices:
            ip = device.get("ip")
            username = device.get("username")
            password = device.get("password")
            hostname = device.get("hostname", ip)
            log_callback(f"--- Processing device: {hostname} ({ip}) ---", is_step=True)
            if not all([ip, username, password]):
                log_callback(
                    f"WARN: Skipping device {hostname} due to incomplete details.",
                    is_step=True,
                )
                overall_success = False
                continue
            ssh = SSHManager(hostname=ip, username=username, password=password)
            try:
                connected, connect_message = ssh.connect()
                if not connected:
                    log_callback(
                        f"ERROR: Failed to connect to {hostname}: {connect_message}",
                        is_step=True,
                    )
                    overall_success = False
                    continue
                self._perform_cleanup(
                    ssh, components_to_clean, log_callback, base_template_path
                )
                log_callback("Discovering remote home directory...", is_step=True)
                exit_code, remote_home_dir = ssh.execute_command(
                    "bash -lc 'echo $HOME'", lambda _: None
                )
                if exit_code != 0 or not remote_home_dir:
                    log_callback(
                        f"FATAL: Could not get home directory on {hostname}.",
                        is_step=True,
                    )
                    overall_success = False
                    continue
                remote_deployment_dir = (
                    Path(remote_home_dir) / "piselfhosting_deployment"
                )
                log_callback("Uploading deployment archive...", is_step=True)
                tarball_path = local_output_path / "deployment.tar.gz"
                with tarfile.open(tarball_path, "w:gz") as tar:
                    tar.add(local_output_path, arcname=os.path.basename(output_path))
                with open(tarball_path, "rb") as f:
                    content = f.read()
                exit_code, remote_tmp_tarball = ssh.execute_command(
                    "mktemp", lambda _: None
                )
                if exit_code != 0 or not remote_tmp_tarball:
                    log_callback(
                        f"FATAL: Could not create temp file on {hostname}.",
                        is_step=True,
                    )
                    overall_success = False
                    continue
                ssh.upload_content(content, remote_tmp_tarball)
                os.remove(tarball_path)
                log_callback("Extracting remote archive...", is_step=True)
                ssh.execute_command(f"mkdir -p {remote_deployment_dir}", lambda _: None)
                ssh.execute_command(
                    (
                        f"tar -xzf {remote_tmp_tarball} "
                        f"-C {remote_deployment_dir} --strip-components=1"
                    ),
                    lambda chunk: log_callback(chunk),
                )
                ssh.execute_command(f"rm {remote_tmp_tarball}", lambda _: None)
                log_callback("Ensuring shared Docker network exists...", is_step=True)
                ssh.execute_command(
                    "docker network create piselfhosting_net || true",
                    lambda chunk: log_callback(chunk),
                )
                log_callback("Executing deployment...", is_step=True)
                exit_code, _ = ssh.execute_command(
                    f"cd {remote_deployment_dir} && docker compose up -d",
                    lambda chunk: log_callback(chunk),
                )
                if exit_code != 0:
                    log_callback(
                        f"ERROR: 'docker compose up' failed on {hostname}.",
                        is_step=True,
                    )
                    overall_success = False
                    continue
                if components_to_restart:
                    log_callback("Performing user-requested restarts...", is_step=True)
                    for component_id in components_to_restart:
                        service_name = self.component_manager.get_docker_service_name(
                            component_id
                        )
                        container_name = f"piselfhosting-{service_name}"
                        log_callback(f"Restarting '{container_name}' on {hostname}...")
                        ssh.execute_command(
                            f"docker restart {container_name}",
                            lambda chunk: log_callback(chunk),
                        )
                log_callback(
                    f"Discovering web interfaces on {hostname}...", is_step=True
                )

                # --- MODIFIED: Replace assert with production-safe check ---
                # This check is logically redundant but satisfies both mypy and Bandit.
                if ip is None:
                    log_callback(
                        f"FATAL: Internal error - IP for {hostname} is None.",
                        is_step=True,
                    )
                    overall_success = False
                    continue

                device_links = self._discover_service_links(local_output_path, ip)
                if device_links:
                    all_service_links.extend(device_links)
            finally:
                log_callback(f"Closing connection to {hostname}.", is_step=True)
                ssh.close()
        if all_service_links:
            tasks_dict[task_id]["service_links"] = all_service_links
            log_callback(
                f"SUCCESS: Found {len(all_service_links)} web interfaces.", is_step=True
            )
        tasks_dict[task_id]["status"] = "completed" if overall_success else "failed"

    def _discover_service_links(
        self, local_output_path: Path, ip: str
    ) -> List[Dict[str, str]]:
        """
        Helper method to discover service links for a single device using
        an explicit variable mapping from the component metadata.
        """
        try:
            context_path = local_output_path / "deployment_context.json"
            with open(context_path, "rb") as f:
                deployment_context = json.load(f)
            all_components = self.component_manager.get_all_components_dict()
            selected_components = deployment_context.get("selected_components", [])
            discovered_links = []
            logging.info(f"Link Discovery for {ip}: Starting.")
            logging.info(
                f"Found {len(selected_components)} components in context: "
                f"{selected_components}"
            )
            for component_id in selected_components:
                logging.info(f"Processing component '{component_id}'.")
                component_meta = all_components.get(component_id)
                if not (component_meta and component_meta.get("has_ui")):
                    logging.info(f"Skipping '{component_id}' (no UI).")
                    continue
                port_variable_name = component_meta.get("ui_port_variable")
                if not port_variable_name:
                    logging.info(f"Skipping '{component_id}' (no 'ui_port_variable').")
                    continue
                logging.info(
                    f"Found port var '{port_variable_name}' for '{component_id}'."
                )
                final_host_port = deployment_context.get(port_variable_name)
                if final_host_port:
                    logging.info(
                        f"Resolved port for '{component_id}' to '{final_host_port}'."
                    )
                    protocol = component_meta.get("protocol", "http")
                    service_url = f"{protocol}://{ip}:{final_host_port}"
                    service_name_display = (
                        f"{component_meta.get('name', component_id)} on {ip}"
                    )
                    discovered_links.append(
                        {"name": service_name_display, "url": service_url}
                    )
                else:
                    logging.warning(
                        f"Could not find value for '{port_variable_name}' in context."
                    )
            logging.info(f"Finished for {ip}. Found {len(discovered_links)} links.")
            return discovered_links
        except Exception as e:
            logging.error(f"Could not discover web interfaces for IP {ip}: {e}")
            return []
