import logging
import time
from typing import List, Dict, Any
from datetime import datetime
import os
from pathlib import Path
import yaml
import tarfile

from managers.ssh_manager import SSHManager


class DeploymentManager:
    """Manages the deployment process to remote devices via SSH."""

    def __init__(self, component_manager):
        self.component_manager = component_manager
        logging.info("DeploymentManager instance created.")

    def start_deployment(self, task_id: str, tasks_dict: Dict, output_path: str,
                         managed_devices: List[Dict[str, Any]]):
        overall_success = True

        def log_stream(log_text: str):
            timestamp = datetime.now().strftime('%H:%M:%S')
            for line in log_text.strip().splitlines():
                full_message = f"[{timestamp}]   {line}"
                tasks_dict[task_id]["logs"].append(full_message)
            tasks_dict[task_id]["last_update"] = time.time()

        def log_step(log_text: str):
            timestamp = datetime.now().strftime('%H:%M:%S')
            full_message = f"[{timestamp}] {log_text}"
            tasks_dict[task_id]["logs"].append(full_message)
            tasks_dict[task_id]["last_update"] = time.time()

        def dummy_callback(_log_text: str):
            pass

        log_step("Deployment process initiated...")
        log_step(f"Using configuration from: {output_path}")

        if not managed_devices:
            log_step("ERROR: No managed devices were provided for deployment.")
            tasks_dict[task_id]["status"] = "failed"
            return

        log_step(f"Deploying to {len(managed_devices)} device(s).")

        for device in managed_devices:
            ip = device.get("ip")
            username = device.get("username")
            password = device.get("password")

            if not all([ip, username, password]):
                log_step("WARN: Skipping device with incomplete details.")
                overall_success = False
                continue

            log_step(f"--- Processing device: {ip} ---")
            ssh = SSHManager(hostname=ip, username=username, password=password)
            connected, connect_message = ssh.connect()
            if not connected:
                log_step(f"ERROR: Failed to connect to {ip}: {connect_message}")
                overall_success = False
                ssh.close()
                continue
            log_step(f"Successfully connected to {ip}.")

            remote_tmp_tarball = f"/tmp/deployment-{task_id}.tar.gz"
            try:
                log_step("Discovering remote home directory...")
                exit_code, remote_home_dir = ssh.execute_command("echo $HOME",
                                                                 dummy_callback)
                if exit_code != 0 or not remote_home_dir:
                    log_step(
                        "FATAL ERROR: Could not determine remote home directory.")
                    overall_success = False
                    continue
                log_step(
                    f"SUCCESS: Remote home directory is '{remote_home_dir}'")

                log_step("Creating local deployment archive...")
                local_output_path = Path(output_path)
                tarball_path = local_output_path / "deployment.tar.gz"
                try:
                    with tarfile.open(tarball_path, "w:gz") as tar:
                        for item in os.listdir(local_output_path):
                            if item != "deployment.tar.gz":
                                tar.add(os.path.join(local_output_path, item),
                                        arcname=item)
                    log_step("SUCCESS: Local deployment archive created.")
                except Exception as e:
                    log_step(
                        f"FATAL ERROR: Could not create local tarball: {e}")
                    overall_success = False
                    continue

                log_step(
                    f"Uploading deployment archive to {remote_tmp_tarball}...")
                try:
                    with open(tarball_path, 'rb') as f:
                        content = f.read()
                    uploaded, msg = ssh.upload_content(content,
                                                       remote_tmp_tarball)
                    if not uploaded:
                        log_step(f"ERROR: Archive upload failed: {msg}")
                        overall_success = False
                        continue
                    log_step("SUCCESS: Archive uploaded successfully.")
                finally:
                    if os.path.exists(tarball_path):
                        os.remove(tarball_path)

                remote_deployment_dir = f"{remote_home_dir}/piselfhosting_deployment"
                log_step(
                    f"Ensuring remote deployment directory '{remote_deployment_dir}' exists...")
                exit_code, _ = ssh.execute_command(
                    f'mkdir -p {remote_deployment_dir}', dummy_callback)
                if exit_code != 0:
                    log_step(
                        "FATAL ERROR: Could not create remote deployment directory.")
                    overall_success = False
                    continue

                log_step("Extracting remote archive...")
                extract_command = f"tar -xzf {remote_tmp_tarball} -C {remote_deployment_dir}"
                exit_code, _ = ssh.execute_command(extract_command, log_stream)
                if exit_code != 0:
                    log_step("ERROR: Failed to extract remote archive.")
                    overall_success = False
                    continue

                log_step("SUCCESS: Remote archive extracted and prepared.")

                command = f"cd {remote_deployment_dir} && docker compose up -d"
                log_step(f"Executing deployment command: {command}")
                exit_code, _ = ssh.execute_command(command, log_stream)
                if exit_code != 0:
                    log_step("ERROR: Deployment command failed.")
                    overall_success = False

                if overall_success:
                    log_step(
                        "Discovering web interfaces for deployed services...")
                    try:
                        compose_path = Path(output_path) / "docker-compose.yml"
                        with open(compose_path, 'r') as f:
                            compose_data = yaml.safe_load(f)

                        service_links = []
                        all_components = self.component_manager.get_all_components_dict()

                        for service_name, service_config in compose_data.get(
                                "services", {}).items():
                            component_id = service_name.replace(
                                "piselfhosting-", "", 1)
                            component_meta = all_components.get(component_id)

                            if component_meta and "ui_port" in component_meta:
                                protocol = component_meta.get("protocol",
                                                              "http")
                                target_container_port = str(
                                    component_meta.get("ui_port"))
                                final_host_port = None
                                for port_mapping in service_config.get("ports",
                                                                       []):
                                    try:
                                        host_part, container_part = str(
                                            port_mapping).split(':')
                                        if container_part == target_container_port:
                                            final_host_port = host_part
                                            break
                                    except ValueError:
                                        continue

                                if final_host_port:
                                    service_url = f"{protocol}://{ip}:{final_host_port}"
                                    service_links.append({
                                        "name": component_meta.get("name",
                                                                   component_id),
                                        "url": service_url
                                    })

                        if service_links:
                            tasks_dict[task_id]["service_links"] = service_links
                            log_step(
                                f"SUCCESS: Found {len(service_links)} web interface(s).")
                    except Exception as e:
                        log_step(
                            f"WARN: Could not discover web interfaces: {e}")

            finally:
                log_step("Cleaning up remote archive...")
                ssh.execute_command(f"rm {remote_tmp_tarball}", dummy_callback)
                log_step("Closing final SSH connection.")
                ssh.close()

        log_step("--- Deployment process finished. ---")
        tasks_dict[task_id][
            "status"] = "completed" if overall_success else "failed"