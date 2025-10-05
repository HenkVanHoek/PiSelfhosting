import json
import logging
import os
import re
import tarfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Set

import yaml

from managers.component_manager import ComponentManager
from managers.ssh_manager import SSHManager

logger = logging.getLogger(__name__)

# New Type Alias for Structured Errors
ReportError = Dict[str, Any]


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

    def _report_error(
        self,
        tasks_dict: Dict[str, Any],
        task_id: str,
        error_type: str,
        summary: str,
        details: str,
        component_id: str = "N/A",
    ) -> None:
        """
        Records a structured error and logs a simplified FATAL message.
        Sets the task status to 'failed'.
        """
        # 1. Record structured error
        error_report: ReportError = {
            "type": error_type,
            "summary": summary,
            "details": details,
            "component_id": component_id,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        tasks_dict[task_id]["errors"].append(error_report)

        # 2. Log a simple FATAL message (for real-time feed)
        log_text = f"FATAL: [{error_type}] {summary}. Details: {details}"
        self._log_update(tasks_dict, task_id, log_text, is_step=True)

        # 3. Mark for failure (this will be handled in the calling function's return)
        # We explicitly set status to failed only when returning from start_deployment
        # to ensure the finally block is responsible for the final status.

    # START OF NEW METHODS FOR PRE-FLIGHT VALIDATION:

    @staticmethod
    def _extract_requested_ports(
        components: List[Dict[str, Any]],
    ) -> Set[int]:
        """
        Parses component metadata to extract a set of all host ports requested
        by the new deployment, ignoring Traefik internal ports.
        """
        requested_ports: Set[int] = set()

        for component in components:
            component_id = component.get("id")
            # Defensive Coding for Safety: Check if ports is a list
            ports_list = component.get("ports")
            if not isinstance(ports_list, list):
                continue

            for port_map_str in ports_list:
                # Port format is typically 'HOST_PORT:CONTAINER_PORT' or
                # 'HOST_PORT'. We only care about HOST_PORT.
                # Example: '80:80/tcp' or '8080'
                try:
                    # Unpacking-First Mandate: Get the first element (HOST_PORT)
                    # from the split string, if it exists.
                    host_port_str, *_ = port_map_str.split(":", 1)
                    # Remove protocol suffix if present (e.g., '/tcp')
                    host_port = int(host_port_str.split("/")[0])
                    requested_ports.add(host_port)
                except (ValueError, TypeError):
                    logger.warning(
                        f"Skipping malformed port string '{port_map_str}' for "
                        f"component '{component_id}'"
                    )

        return requested_ports

    def _check_live_service_conflicts(
        self,
        ssh: SSHManager,
        requested_components: List[Dict[str, Any]],
        tasks_dict: Dict[str, Any],
        task_id: str,
        log_callback: Callable[..., None],
    ) -> bool:
        """
        Connects to the Pi to check for conflicts with live services.
        Reports structured errors on conflict.
        Returns True if conflicts are found, False otherwise.
        """
        found_conflicts = False

        # 1. Gather Requested Resources
        requested_ports = self._extract_requested_ports(requested_components)
        # FIX: Removed unused local variable requested_service_names

        log_callback("Checking for live service conflicts...", is_step=True)

        # 2. Check for Port Conflicts (against ALL running containers)
        port_check_cmd = "docker ps --format '{{.Names}}|{{.Ports}}'"
        exit_code, output = ssh.execute_command(
            port_check_cmd, log_callback, check_exit_code=False
        )

        if exit_code == 0:
            live_ports: Set[int] = set()
            for line in output.splitlines():
                if not line or "|" not in line:
                    continue
                # Unpacking-First Mandate: Split into name and ports string
                container_name, ports_str, *_ = line.split("|", 1)

                for match in re.finditer(r":(\d+)->", ports_str):
                    try:
                        host_port_str, *_ = match.groups()
                        live_ports.add(int(host_port_str))
                    except (ValueError, IndexError):
                        continue

            conflict_ports = requested_ports.intersection(live_ports)
            if conflict_ports:
                summary = "Host port conflict detected."
                details = (
                    f"Ports {', '.join(map(str, conflict_ports))} are already "
                    f"in use by other running Docker containers on the device."
                )
                self._report_error(
                    tasks_dict, task_id, "LiveConflict:Port", summary, details
                )
                found_conflicts = True
        else:
            self._report_error(
                tasks_dict,
                task_id,
                "LiveCheck:Command",
                "Could not execute Docker command for port check.",
                f"Command: '{port_check_cmd}' failed with exit code {exit_code}.",
            )
            found_conflicts = True

        # 3. Check for Service Name Conflicts (against ALL existing
        # PiSelfhosting containers)
        name_check_cmd = (
            "docker ps -a --format '{{.Names}}' --filter "
            "'label=com.docker.compose.project=piselfhosting'"
        )
        exit_code, output = ssh.execute_command(
            name_check_cmd, log_callback, check_exit_code=False
        )

        if exit_code == 0:
            live_container_names: Set[str] = {
                name
                for name in output.splitlines()
                if name.startswith("piselfhosting-")
            }

            for component in requested_components:
                requested_id = component.get("id")
                # Use ComponentManager logic to get the correct service name
                requested_name = (
                    self.component_manager.get_docker_service_name(requested_id)
                    if requested_id
                    else None
                )

                if not requested_name:
                    continue

                prefix = f"piselfhosting-{requested_name}"
                if any(
                    container_name.startswith(prefix)
                    for container_name in live_container_names
                ):
                    summary = f"Service name '{requested_name}' conflict detected."
                    details = (
                        f"A container with the base name '{requested_name}' already "
                        "exists from a previous PiSelfhosting deployment (running or "
                        "stopped). Please perform a full cleanup first."
                    )
                    self._report_error(
                        tasks_dict,
                        task_id,
                        "LiveConflict:Name",
                        summary,
                        details,
                        # FIX: Cast to str to satisfy mypy (Any | None -> str)
                        str(component.get("id")),
                    )
                    found_conflicts = True
        else:
            self._report_error(
                tasks_dict,
                task_id,
                "LiveCheck:Command",
                "Could not execute Docker command for name check.",
                f"Command: '{name_check_cmd}' failed with exit code {exit_code}.",
            )
            found_conflicts = True

        if found_conflicts:
            log_callback("FATAL: Live conflict check failed.", is_step=True)
        else:
            log_callback("Live conflict check passed.", is_step=True)

        return found_conflicts

    def _validate_traefik_configuration(
        self, components: List[Dict[str, Any]], global_vars: Dict[str, Any]
    ) -> List[ReportError]:
        """
        Validates Traefik configuration for conflicts: duplicate internal ports
        or duplicate Traefik-derived hostnames.

        Returns a list of structured ReportError dictionaries.
        """
        errors: List[ReportError] = []
        used_internal_ports = set()
        used_hostnames = set()

        traefik_host_prefix = global_vars.get("TRAEFIK_HOST")
        fqdn_suffix = global_vars.get("FQDN_SUFFIX")

        for component in components:
            component_id = component.get("id", "unknown-id")
            # FIX: Removed unused local variable component_name
            has_traefik = component.get("has_traefik_support")

            if not has_traefik:
                continue

            # 1. Check for duplicate internal ports (required for Traefik)
            traefik_port = component.get("traefik_internal_port")
            if not traefik_port:
                errors.append(
                    {
                        "type": "Validation:Missing",
                        "summary": "Missing Traefik port.",
                        "details": (
                            "Component requires 'traefik_internal_port' but it "
                            "is missing."
                        ),
                        "component_id": component_id,
                    }
                )
                continue  # Cannot proceed with this component

            if traefik_port in used_internal_ports:
                errors.append(
                    {
                        "type": "Validation:DuplicatePort",
                        "summary": f"Duplicate Traefik internal port: {traefik_port}.",
                        "details": (
                            f"Another component already uses internal port "
                            f"{traefik_port} for Traefik routing."
                        ),
                        "component_id": component_id,
                    }
                )
            used_internal_ports.add(traefik_port)

            # 2. Check for duplicate Traefik-derived hostnames (if variables are set)
            if traefik_host_prefix and fqdn_suffix:
                # FIX: Default to component_id if docker_service_name is not present.
                hostname_prefix = component.get("docker_service_name", component_id)

                # Hostname is constructed as:
                # hostname_prefix.TRAEFIK_HOST.FQDN_SUFFIX
                hostname = (
                    f"{hostname_prefix}.{traefik_host_prefix}.{fqdn_suffix}"
                ).lower()
                if hostname in used_hostnames:
                    errors.append(
                        {
                            "type": "Validation:DuplicateHostname",
                            "summary": (
                                f"Duplicate Traefik-derived hostname: {hostname}."
                            ),
                            "details": (
                                "This hostname is generated from the component's "
                                "service name and global variables."
                            ),
                            "component_id": component_id,
                        }
                    )
                used_hostnames.add(hostname)

        return errors

    def _prepare_deployment_context(
        self,
        selected_components_data: List[Dict[str, Any]],
        global_vars: Dict[str, Any],
    ) -> Dict[str, Any] | List[ReportError]:
        """
        Orchestrates pre-deployment preparation and validation.

        Returns a dictionary containing deployment data on success, or a
        list of structured ReportError dictionaries on validation failure.
        """
        validation_errors = self._validate_traefik_configuration(
            selected_components_data, global_vars
        )
        if validation_errors:
            return validation_errors

        # Validation passed. Return the required data for the artifact
        # generation step in ComponentManager.
        return {
            "selected_components_data": selected_components_data,
            "global_vars": global_vars,
        }

    # END OF NEW METHODS FOR PRE-FLIGHT VALIDATION

    def _perform_cleanup(
        self,
        ssh: SSHManager,
        components_to_clean: List[str],
        log_callback: Callable[..., None],
    ) -> None:
        """
        Stops and removes containers for the given components, ignoring
        errors if they do not exist.
        """
        if not components_to_clean:
            return

        log_callback("--- Starting Pre-Flight Cleanup ---", is_step=True)
        for component_id in components_to_clean:
            log_callback(f"Cleaning resources for '{component_id}'...")
            service_name = self.component_manager.get_docker_service_name(component_id)
            container_name = f"piselfhosting-{service_name}"

            ssh.execute_command(
                f"docker stop {container_name}", log_callback, check_exit_code=False
            )
            ssh.execute_command(
                f"docker rm {container_name}", log_callback, check_exit_code=False
            )

        log_callback("--- Pre-Flight Cleanup Finished ---", is_step=True)

    def _discover_service_links(
        self,
        ip: str,
        local_output_path: Path,
        tasks_dict: Dict[str, Any],
        task_id: str,
        log_callback: Callable[..., None],
    ) -> List[Dict[str, str]]:
        """
        Reads deployment artifacts to discover and construct web UI links
        using the architecturally correct 'ui_port_variable' pointer.
        """
        log_callback("Discovering web interfaces for services...", is_step=True)
        try:
            context_path = local_output_path / "deployment_context.json"
            with open(context_path, "r", encoding="utf-8") as f:
                deployment_context = json.load(f)

            compose_path = local_output_path / "docker-compose.yml"
            with open(compose_path, "r", encoding="utf-8") as f:
                compose_data = yaml.safe_load(f)

            all_components_map = {
                c["id"]: c for c in self.component_manager.get_all_components()
            }

            service_links = []
            for service_name, s_def in compose_data.get("services", {}).items():
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

                primary_service = comp_meta.get("docker_service_name")
                if primary_service and primary_service != service_name:
                    continue

                port_variable_name = comp_meta.get("ui_port_variable")
                port = None

                if port_variable_name:
                    port = deployment_context.get(port_variable_name)
                elif "ui_port" in comp_meta:
                    port = comp_meta.get("ui_port")

                if port:
                    protocol = comp_meta.get("protocol", "http")
                    url = f"{protocol}://{ip}:{port}"
                    service_links.append({"name": comp_meta.get("name"), "url": url})

            # --- DEFINITIVE FIX: De-duplicate the list to solve the user's issue ---
            unique_links = []
            seen_urls = set()
            for link in service_links:
                if link["url"] not in seen_urls:
                    unique_links.append(link)
                    seen_urls.add(link["url"])
            service_links = unique_links

            log_text = (
                f"SUCCESS: Found {len(service_links)} web UIs."
                if service_links
                else "WARN: No web UIs were discovered."
            )
            log_callback(log_text, is_step=True)
            return service_links

        except Exception as e:
            logger.error(f"Error discovering service links: {e}", exc_info=True)
            # Refactor: Report error instead of just logging FATAL
            self._report_error(
                tasks_dict,
                task_id,
                "Discovery:Fatal",
                "UI Link Discovery Failed",
                f"Unexpected error while parsing artifacts: {e}",
            )
            return []

    def _transfer_and_extract_archive(
        self,
        ssh: SSHManager,
        local_path: Path,
        remote_path: Path,
        task_id: str,
        tasks_dict: Dict[str, Any],
        log_callback: Callable[..., None],
    ) -> bool:
        """Creates, uploads, and extracts the deployment tarball."""
        log_callback("Creating and uploading deployment archive...", is_step=True)
        # nosec B108 is tolerated here for a temporary file
        remote_tmp_tarball = f"/tmp/deployment-{task_id}.tar.gz"  # nosec B108
        tarball_path = local_path / f"deployment-{task_id}.tar.gz"

        try:
            with tarfile.open(tarball_path, "w:gz") as tar:
                tar.add(local_path, arcname=os.path.basename(local_path))
            # Refactor: Check for upload success and report error
            success, msg = ssh.upload_content(
                Path(tarball_path).read_bytes(), remote_tmp_tarball
            )
            if not success:
                self._report_error(
                    tasks_dict,
                    task_id,
                    "Transfer:Upload",
                    "Deployment archive upload failed.",
                    f"SFTP upload error: {msg}",
                )
                return False
        except Exception as e:
            self._report_error(
                tasks_dict,
                task_id,
                "Transfer:Archive",
                "Deployment archive creation/upload failed.",
                f"Local archiving or initial upload failed: {e}",
            )
            return False
        finally:
            if os.path.exists(tarball_path):
                os.remove(tarball_path)

        log_callback("Extracting remote archive...", is_step=True)
        ssh.execute_command(f"mkdir -p {remote_path}", log_callback)
        exit_code, _ = ssh.execute_command(
            f"tar -xzf {remote_tmp_tarball} -C {remote_path} --strip-components=1",
            log_callback,
        )

        if exit_code != 0:
            self._report_error(
                tasks_dict,
                task_id,
                "Transfer:Extract",
                "Remote archive extraction failed.",
                f"Command 'tar' failed with exit code {exit_code}",
            )
            ssh.execute_command(f"rm {remote_tmp_tarball}", log_callback)
            return False

        ssh.execute_command(f"rm {remote_tmp_tarball}", log_callback)
        return True

    def start_deployment(
        self,
        task_id: str,
        tasks_dict: Dict[str, Any],
        output_path: str,
        managed_devices: List[Dict[str, Any]],
        components_to_clean: List[str],
        components_to_restart: List[str],
        selected_components_data: List[Dict[str, Any]],
        global_vars: Dict[str, Any],
    ) -> None:
        """Main entry point to orchestrate the deployment process."""

        # Initialize structured error reporting
        tasks_dict[task_id]["errors"] = []

        def log_callback(text: str, is_step: bool = False) -> None:
            self._log_update(tasks_dict, task_id, text, is_step)

        # START OF PRE-FLIGHT LOGIC (Local Validation)
        log_callback("Starting pre-flight configuration validation...", is_step=True)
        deployment_data = self._prepare_deployment_context(
            selected_components_data, global_vars
        )

        if isinstance(deployment_data, list):
            # Refactor: Use structured reporting for validation failures
            log_callback(
                "FATAL: Pre-flight validation failed with the following errors:",
                is_step=True,
            )
            for error_report in deployment_data:
                self._report_error(
                    tasks_dict,
                    task_id,
                    error_report.get("type", "Validation:General"),
                    error_report.get("summary", "Configuration Validation Failed"),
                    error_report.get("details", "See summary."),
                    error_report.get("component_id", "N/A"),
                )
            tasks_dict[task_id]["status"] = "failed"
            return
        # END OF PRE-FLIGHT LOGIC (Local Validation)

        log_callback("Deployment process initiated...", is_step=True)
        if components_to_restart:
            log_callback(
                f"INFO: Restart requested for: {', '.join(components_to_restart)} "
                f"(logic not yet implemented).",
                is_step=False,
            )

        if not managed_devices:
            self._report_error(
                tasks_dict,
                task_id,
                "Device:Missing",
                "No valid devices selected for deployment.",
                "The managed_devices list is empty.",
            )
            tasks_dict[task_id]["status"] = "failed"
            return

        # Unpacking-First Mandate: Retrieve the single device from the list.
        device, *_ = managed_devices

        ip, user, pwd = (
            device.get("ip"),
            device.get("username"),
            device.get("password"),
        )
        if not all([ip, user, pwd]):
            self._report_error(
                tasks_dict,
                task_id,
                "Device:Incomplete",
                "Device details are incomplete.",
                "Missing IP, username, or password for the target device.",
            )
            tasks_dict[task_id]["status"] = "failed"
            return

        ssh = SSHManager(hostname=ip, username=user, password=pwd)
        log_callback(f"--- Processing device: {ip} ---", is_step=True)
        try:
            connected, msg = ssh.connect()
            if not connected:
                self._report_error(
                    tasks_dict,
                    task_id,
                    "SSH:Connect",
                    f"Failed to connect to device {ip}.",
                    f"Connection error: {msg}",
                )
                return

            # START OF LIVE CONFLICT CHECK (Post-Connection)
            # Refactor: Pass task info to the helper
            found_conflicts = self._check_live_service_conflicts(
                ssh, selected_components_data, tasks_dict, task_id, log_callback
            )
            if found_conflicts:
                # Errors were reported internally by the helper
                return
            # END OF LIVE CONFLICT CHECK

            # The live conflict check passed, proceed with cleanup and deployment.
            self._perform_cleanup(ssh, components_to_clean, log_callback)

            # ARCHITECTURAL PEER-NOTE: The next step, file generation, is logically
            # part of the ComponentManager, not DeploymentManager.
            log_callback(
                "Configuration validated. Requesting artifact generation from "
                "ComponentManager...",
                is_step=True,
            )
            try:
                # The actual file generation call in ComponentManager.
                self.component_manager.generate_deployment_artifacts(
                    deployment_data["selected_components_data"],
                    deployment_data["global_vars"],
                    Path(output_path),
                )
                log_callback(
                    "INFO: Deployment artifacts generated successfully.",
                    is_step=False,
                )
            except Exception as e:
                self._report_error(
                    tasks_dict,
                    task_id,
                    "Artifact:Generation",
                    "Deployment artifact generation failed.",
                    f"ComponentManager reported error: {e}",
                )
                return

            exit_code, home_output = ssh.execute_command("echo $HOME", log_callback)
            # Defensive Coding for Safety: Get the home directory from output.
            # FIX: Use strip() and check the stripped string to
            # avoid subtle splitlines bugs
            home = home_output.strip() if home_output else None

            if exit_code != 0 or not home:
                self._report_error(
                    tasks_dict,
                    task_id,
                    "SSH:Runtime",
                    "Could not determine remote home directory.",
                    f"'echo $HOME' failed with exit code {exit_code}.",
                )
                return

            remote_dir = Path(home) / "piselfhosting_deployment"
            # Refactor: Pass task info to the helper
            if not self._transfer_and_extract_archive(
                ssh, Path(output_path), remote_dir, task_id, tasks_dict, log_callback
            ):
                # Errors were reported internally by the helper
                return

            log_callback("Executing deployment...", is_step=True)
            exit_code, _ = ssh.execute_command(
                f"cd {remote_dir} && docker compose up -d", log_callback
            )
            if exit_code != 0:
                self._report_error(
                    tasks_dict,
                    task_id,
                    "Deployment:Runtime",
                    "Docker Compose deployment failed.",
                    (
                        "The 'docker compose up -d' command returned a non-zero exit "
                        f"code ({exit_code}). See logs for details."
                    ),
                )
                return

            if not ip:
                self._report_error(
                    tasks_dict,
                    task_id,
                    "Discovery:MissingIP",
                    "Cannot discover service links.",
                    "IP address for the target device is missing after deployment.",
                )
                return

            # Refactor: Pass task info to the helper
            links = self._discover_service_links(
                ip, Path(output_path), tasks_dict, task_id, log_callback
            )
            if links:
                tasks_dict[task_id]["service_links"] = links
            # Note: _discover_service_links reports its own error on exception.
            # We don't need to check its return value for failure here.

        except Exception as e:
            logger.error(f"Unexpected deployment error: {e}", exc_info=True)
            self._report_error(
                tasks_dict,
                task_id,
                "Deployment:Unhandled",
                "An unexpected fatal error occurred.",
                f"Python exception: {e}",
            )
        finally:
            log_callback("Closing SSH connection.", is_step=True)
            ssh.close()
            # Final status update ensures the structured errors are accounted for.
            if tasks_dict[task_id]["errors"]:
                tasks_dict[task_id]["status"] = "failed"
            else:
                tasks_dict[task_id]["status"] = "completed"
