import logging
import time
from typing import List, Dict, Any
from datetime import datetime
import os
from pathlib import Path
import yaml

from managers.ssh_manager import SSHManager


class DeploymentManager:
    def __init__(self, component_manager):
        self.component_manager = component_manager
        logging.info("DeploymentManager initialized.")

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
                log_step(f"WARN: Skipping device with incomplete details.")
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

            def _reconnect_ssh(reason: str):
                log_step(reason)
                ssh.close()
                time.sleep(2)
                new_ssh = SSHManager(hostname=ip, username=username,
                                     password=password)
                is_connected, reconnect_msg = new_ssh.connect()
                if not is_connected:
                    log_step(f"ERROR: Failed to reconnect: {reconnect_msg}")
                    return None
                log_step("SUCCESS: Reconnected successfully.")
                return new_ssh

            apparmor_was_stopped = False
            try:
                log_step("Checking AppArmor status...")
                exit_code, _ = ssh.execute_command(
                    "systemctl is-active apparmor", dummy_callback)
                if exit_code == 0:
                    log_step(
                        "AppArmor is active. Temporarily stopping for installation...")
                    apparmor_was_stopped = True
                    stop_cmd = f'echo "{password}" | sudo -S systemctl stop apparmor'
                    exit_code, _ = ssh.execute_command(stop_cmd, log_stream)
                    if exit_code != 0:
                        log_step("ERROR: Failed to stop AppArmor.")
                        overall_success = False
                        continue

                    reconnected_ssh = _reconnect_ssh(
                        "Reconnecting to apply new security context...")
                    if not reconnected_ssh:
                        overall_success = False
                        continue
                    ssh = reconnected_ssh

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

                exit_code, _ = ssh.execute_command("command -v curl",
                                                   dummy_callback)
                if exit_code != 0:
                    log_step("'curl' not found. Installing...")
                    exit_code, _ = ssh.execute_command(
                        f'echo "{password}" | sudo -S apt-get -y update',
                        log_stream)
                    if exit_code != 0:
                        log_step("ERROR: 'apt-get update' failed.")
                        overall_success = False
                        continue
                    exit_code, _ = ssh.execute_command(
                        f'echo "{password}" | sudo -S apt-get install -y curl',
                        log_stream)
                    if exit_code != 0:
                        log_step("ERROR: Failed to install 'curl'.")
                        overall_success = False
                        continue
                    log_step("SUCCESS: 'curl' has been installed.")

                exit_code, _ = ssh.execute_command("docker --version",
                                                   dummy_callback)
                if exit_code != 0:
                    log_step(
                        "Docker not found. Installing (this may take several minutes)...")
                    install_cmd = f'echo "{password}" | sudo -S sh -c "curl -sSL https://get.docker.com | sh"'
                    exit_code, _ = ssh.execute_command(install_cmd, log_stream)
                    if exit_code != 0:
                        log_step("ERROR: Docker installation script failed.")
                        overall_success = False
                        continue
                    perm_cmd = f'echo "{password}" | sudo -S usermod -aG docker {username}'
                    exit_code, _ = ssh.execute_command(perm_cmd, log_stream)
                    if exit_code != 0:
                        log_step("ERROR: Failed to add user to docker group.")
                        overall_success = False
                        continue

                    reconnected_ssh = _reconnect_ssh(
                        "Reconnecting session for new group permissions...")
                    if not reconnected_ssh:
                        overall_success = False
                        continue
                    ssh = reconnected_ssh

                exit_code, version_out = ssh.execute_command("docker --version",
                                                             dummy_callback)
                if exit_code != 0:
                    log_step(f"ERROR: Docker is still not accessible.")
                    overall_success = False
                    continue
                log_step(f"SUCCESS: Docker is ready. Version: {version_out}")

                log_step(
                    "Checking for shared Docker network 'piselfhosting_net'...")
                exit_code, _ = ssh.execute_command(
                    "docker network inspect piselfhosting_net", dummy_callback)
                if exit_code != 0:
                    log_step("Network not found. Creating it now...")
                    exit_code, _ = ssh.execute_command(
                        "docker network create piselfhosting_net", log_stream)
                    if exit_code != 0:
                        log_step("ERROR: Failed to create Docker network.")
                        overall_success = False
                        continue
                    log_step("SUCCESS: Shared Docker network created.")
                else:
                    log_step("SUCCESS: Shared Docker network already exists.")

                remote_deployment_dir = f"{remote_home_dir}/piselfhosting_deployment"
                remote_data_dir = f"{remote_home_dir}/piselfhosting_data"
                log_step(f"Ensuring remote directories exist...")
                exit_code, _ = ssh.execute_command(
                    f"mkdir -p {remote_deployment_dir}", dummy_callback)
                if exit_code != 0:
                    log_step(
                        "FATAL ERROR: Could not create remote deployment directory.")
                    overall_success = False
                    continue
                exit_code, _ = ssh.execute_command(
                    f"mkdir -p {remote_data_dir}", dummy_callback)
                if exit_code != 0:
                    log_step(
                        "FATAL ERROR: Could not create remote data directory.")
                    overall_success = False
                    continue

                log_step(
                    "Scanning for and uploading other configuration files...")
                local_output_path = Path(output_path)
                other_files_uploaded = True
                for local_file in local_output_path.rglob('*'):
                    if local_file.is_file() and local_file.name != 'docker-compose.yml':
                        relative_path = local_file.relative_to(
                            local_output_path)
                        remote_file_path = f"{remote_data_dir}/{relative_path}"
                        remote_file_dir = os.path.dirname(remote_file_path)

                        exit_code, _ = ssh.execute_command(
                            f"mkdir -p {remote_file_dir}", dummy_callback)
                        if exit_code != 0:
                            log_step(
                                f"ERROR: Could not create remote subdirectory: {remote_file_dir}")
                            overall_success = False
                            other_files_uploaded = False
                            break

                        log_step(f"  Uploading {relative_path}...")
                        try:
                            with open(local_file, 'rb') as f:
                                content = f.read()
                            uploaded, msg = ssh.upload_content(content,
                                                               remote_file_path)
                            if not uploaded:
                                log_step(
                                    f"  ERROR: Upload failed for {relative_path}: {msg}")
                                overall_success = False
                                other_files_uploaded = False
                                break
                        except Exception as e:
                            log_step(
                                f"  ERROR: Could not read local file {local_file}: {e}")
                            overall_success = False
                            other_files_uploaded = False
                            break
                if not other_files_uploaded:
                    continue

                local_compose_file_path = os.path.join(output_path,
                                                       "docker-compose.yml")
                try:
                    with open(local_compose_file_path, 'rb') as f:
                        compose_content = f.read()
                except Exception as e:
                    log_step(f"FATAL ERROR: Could not read local file: {e}")
                    overall_success = False
                    continue

                remote_compose_file = f"{remote_deployment_dir}/docker-compose.yml"
                log_step(
                    f"Uploading main compose file to {remote_compose_file}...")
                uploaded, msg = ssh.upload_content(compose_content,
                                                   remote_compose_file)
                if not uploaded:
                    log_step(f"ERROR: Content upload failed: {msg}")
                    overall_success = False
                    continue
                log_step("SUCCESS: Main compose file uploaded successfully.")

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
                                ui_port = str(component_meta.get("ui_port"))
                                host_port = None
                                for port_mapping in service_config.get("ports",
                                                                       []):
                                    try:
                                        # THE DEFINITIVE, FINAL, CORRECTED FIX using tuple unpacking
                                        current_host_port, current_container_port = str(
                                            port_mapping).split(':')
                                        if current_container_port == ui_port:
                                            host_port = current_host_port
                                            break
                                    except ValueError:
                                        log_step(
                                            f"WARN: Skipping invalid port mapping format: {port_mapping}")
                                        continue

                                if host_port:
                                    service_url = f"{protocol}://{ip}:{host_port}"
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
                if apparmor_was_stopped:
                    log_step("Re-enabling AppArmor service...")
                    start_cmd = f'echo "{password}" | sudo -S systemctl start apparmor'
                    exit_code, _ = ssh.execute_command(start_cmd, log_stream)
                    if exit_code == 0:
                        log_step("SUCCESS: AppArmor has been re-enabled.")
                    else:
                        log_step(
                            "WARN: Failed to re-enable AppArmor. Please check device manually.")

                log_step("Closing final SSH connection.")
                ssh.close()

        log_step("--- Deployment process finished. ---")
        tasks_dict[task_id][
            "status"] = "completed" if overall_success else "failed"