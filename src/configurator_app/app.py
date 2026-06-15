# src/configurator_app/app.py

import logging
import os
import re
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

from appdirs import user_data_dir
from flask import Flask, Response, jsonify, render_template, request, session

from managers.component_manager import ComponentManager
from managers.deployment_manager import DeploymentManager
from managers.setup_manager import SetupManager
from pi_scanner import PiScanner
from utils.resource_utils import get_components_paths

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


def safe_join(base_dir: Path, user_path: str) -> Path:
    """Safely join base dir and user path to prevent path traversal."""
    # 1. Strictly validate characters to prevent traversal strings like dot-dot
    if not re.match(r"^[a-zA-Z0-9_-]+$", user_path):
        raise ValueError(f"Invalid path component: {user_path}")
    # 2. Resolve to absolute path
    resolved_base = base_dir.resolve()
    resolved_target = (resolved_base / user_path).resolve()
    # 3. Double-check path starts with base_dir
    if not resolved_target.is_relative_to(resolved_base):
        raise ValueError(f"Path traversal detected: {user_path}")
    return resolved_target


def analyze_snapshot(components, snapshot, is_reinstallation):
    """Analyze system snapshot against components for conflicts/warnings."""
    conflicts = {"ports": [], "volumes": []}
    warnings = []
    used_ports = {
        p["port"]: p["process_name"] for p in snapshot.get("native_processes", [])
    }
    for container in snapshot.get("containers", []):
        ports_str = str(container.get("ports", ""))
        # Safe linear-time string scanning to avoid ReDoS polynomial backtracking
        for part in ports_str.replace(",", " ").split():
            if "0.0.0.0:" in part and "->" in part:
                try:
                    after_ip = part.split("0.0.0.0:")[1]
                    port_num_str = after_ip.split("->")[0]
                    if port_num_str.isdigit():
                        used_ports[int(port_num_str)] = (
                            f"docker container ({container.get('name')})"
                        )
                except IndexError:
                    continue

    existing_volumes = set()
    for container in snapshot.get("containers", []):
        mounts_val = container.get("mounts", "")
        mounts = str(mounts_val).split(",") if mounts_val else []
        for mount in mounts:
            if ":" in mount:
                host_path = mount.split(":")[0]
                if "." not in Path(host_path).name:
                    existing_volumes.add(host_path)

    for component in components:
        comp_name = str(component.get("name", "unknown"))
        comp_id = str(component.get("id", comp_name)).lower()
        comp_id_clean = comp_id.replace("-", "")

        for raw_port_str in component.get("ports", []):
            port_str = str(raw_port_str)
            # Safe linear matching of port layout
            if ":" in port_str:
                before_colon = port_str.split(":")[0]
                if before_colon.isdigit():
                    port = int(before_colon)
                    if port in used_ports:
                        conflicting_service = used_ports[port]
                        conflicting_service_clean = conflicting_service.lower().replace(
                            "-", ""
                        )

                        conflict_type = "UNEXPECTED_DOCKER_CONFLICT"
                        if "docker" not in conflicting_service:
                            conflict_type = "DANGEROUS_NATIVE_PROCESS_CONFLICT"
                        elif (
                            "docker container" in conflicting_service.lower()
                            and comp_id_clean in conflicting_service_clean
                            and is_reinstallation
                        ):
                            conflict_type = "EXPECTED_REINSTALLATION"

                        conflicts["ports"].append(
                            {
                                "port": port,
                                "conflict_type": conflict_type,
                                "conflicting_service": conflicting_service,
                                "proposed_service": comp_name,
                            }
                        )

        for raw_volume_str in component.get("volumes", []):
            volume_str = str(raw_volume_str)
            if ":" in volume_str:
                host_path = volume_str.split(":")[0]
                if host_path in existing_volumes:
                    conflicts["volumes"].append(
                        {
                            "volume_path": host_path,
                            "conflict_type": "EXISTING_VOLUME_CONFLICT",
                            "proposed_service": comp_name,
                        }
                    )

    ram = snapshot.get("resources", {}).get("ram", {})
    total_mb = int(ram.get("total_mb", 0))
    used_mb = int(ram.get("used_mb", 0))
    if total_mb > 0 and (used_mb / total_mb) > 0.9:
        warnings.append(
            {
                "type": "RAM",
                "message": "The target system is using over 90% of its RAM.",
            }
        )
    return conflicts, warnings


def map_analysis_to_report_errors(analysis_results: dict, target_ip: str) -> list[dict]:
    """Maps analysis results to standard ReportError structures."""
    errors = []
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conflicts = analysis_results.get("external_conflicts", {})

    port_conflicts = conflicts.get("ports", [])
    for conflict in port_conflicts:
        port = conflict.get("port")
        conflict_type = conflict.get("conflict_type")
        conflicting_service = conflict.get("conflicting_service")
        proposed_service = str(conflict.get("proposed_service", "N/A"))

        error_type = f"Validation:PortConflict:{conflict_type}"
        summary = f"Host port {port} conflict detected."
        details = (
            f"Port {port} is already in use by: '{conflicting_service}'. "
            f"The service '{proposed_service}' requires this port. "
            f"Conflict Type: {conflict_type}."
        )
        component_id = proposed_service.lower().replace(" ", "-")

        errors.append(
            {
                "type": error_type,
                "summary": summary,
                "details": details,
                "component_id": component_id,
                "timestamp": timestamp,
            }
        )

    volume_conflicts = conflicts.get("volumes", [])
    for conflict in volume_conflicts:
        volume_path = conflict.get("volume_path")
        conflict_type = conflict.get("conflict_type")
        proposed_service = str(conflict.get("proposed_service", "N/A"))

        error_type = f"Validation:VolumeConflict:{conflict_type}"
        summary = f"Host volume path conflict detected at '{volume_path}'."
        details = (
            f"The path '{volume_path}' already exists on the target system "
            f"({target_ip}) and is required for volume mounting by the service "
            f"'{proposed_service}'. Conflict Type: {conflict_type}. "
            f"This may lead to data corruption or permission issues."
        )
        component_id = proposed_service.lower().replace(" ", "-")

        errors.append(
            {
                "type": error_type,
                "summary": summary,
                "details": details,
                "component_id": component_id,
                "timestamp": timestamp,
            }
        )

    resource_warnings = analysis_results.get("resource_warnings", [])
    for warning in resource_warnings:
        warning_type = str(warning.get("type", "unknown"))
        message = str(warning.get("message", ""))

        error_type = f"Warning:Resource:{warning_type}"
        summary = f"Resource warning detected: {warning_type}"
        details = (
            f"The resource analysis on {target_ip} generated a warning: "
            f"{message}. Deployment may proceed, but performance may be impacted."
        )

        errors.append(
            {
                "type": error_type,
                "summary": summary,
                "details": details,
                "component_id": "N/A",
                "timestamp": timestamp,
            }
        )

    return errors


def create_app(test_config=None):
    """Factory function to create and configure the Flask application."""
    flask_app = Flask(__name__, static_folder="static", static_url_path="/static")

    # Apply testing configuration if provided
    if test_config:
        flask_app.config.update(test_config)

    flask_app.secret_key = os.environ.get(
        "FLASK_SECRET_KEY", "a-default-secret-key-for-development"
    )

    metadata_path_obj, templates_path_obj = get_components_paths()
    metadata_path = str(metadata_path_obj)
    templates_path = str(templates_path_obj)

    component_manager = ComponentManager(
        metadata_file_path=metadata_path, templates_path=templates_path
    )

    app_data_dir = Path(user_data_dir("PiSelfhosting", "PiSelfhosting"))
    output_dir = app_data_dir / "output"

    # noinspection PyTypeChecker
    setup_manager = SetupManager(component_manager, output_dir=output_dir)
    deployment_manager = DeploymentManager(component_manager=component_manager)

    flask_app.deployment_tasks = {}
    flask_app.map_analysis_to_report_errors = map_analysis_to_report_errors

    @flask_app.route("/", methods=["GET"])
    def index():
        return render_template("index.html")

    @flask_app.route("/help", methods=["GET"])
    def help_page():
        from utils.resource_utils import resource_path

        docs = {}
        for doc_name, filename in [
            ("Introduction", "README.md"),
            ("Contributing Guide", "CONTRIBUTING.md"),
            ("Helper Utilities", "UTILITIES.md"),
        ]:
            path = resource_path(filename)
            content = "Documentation file not found."
            if path.exists():
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        content = f.read()
                except Exception as e:
                    content = f"Error reading file: {e}"
            docs[doc_name] = content

        return render_template("help.html", docs=docs)

    @flask_app.route("/scan-pis", methods=["POST"])
    def scan_pis():
        data = request.get_json(silent=True) or {}
        discovery_method = data.get("discovery_method")
        if discovery_method == "direct_ip":
            target_ip = data.get("direct_target_ip", "").strip()
            if not target_ip:
                return (
                    jsonify({"error": "Direct IP target address cannot be blank."}),
                    400,
                )

            # If target_ip is a MAC address, resolve it by scanning the network
            if re.match(r"^([0-9a-fA-F]{2}[:-]){5}([0-9a-fA-F]{2})$", target_ip):
                subnet = data.get("subnet")
                if subnet is not None and not isinstance(subnet, str):
                    subnet = None
                try:
                    scanner = PiScanner(
                        username=os.environ.get("PI_SCANNER_USERNAME", "dummy"),
                        password=os.environ.get("PI_SCANNER_PASSWORD", "dummy"),
                    )
                    hosts, messages, error, detection_info = scanner.scan(subnet=subnet)
                    if error:
                        logging.error(
                            f"Scanner scan failed for MAC resolution: {error}"
                        )
                        return (
                            jsonify(
                                {
                                    "error": (
                                        "Failed to scan network to resolve "
                                        f"MAC address: {error}"
                                    ),
                                    "messages": messages,
                                }
                            ),
                            500,
                        )

                    search_mac = target_ip.replace("-", ":").lower()
                    resolved_host: dict | None = None
                    for h in hosts:
                        if h.get("mac", "").replace("-", ":").lower() == search_mac:
                            resolved_host = h
                            break

                    if resolved_host is None:
                        return (
                            jsonify(
                                {
                                    "error": (
                                        "Could not find any device with MAC "
                                        f"address {target_ip} on the network."
                                    ),
                                    "messages": messages
                                    + [f"Scanned network to find MAC: {target_ip}"],
                                }
                            ),
                            404,
                        )

                    resolved_ip = resolved_host["ip"]
                    logging.info(f"Resolved MAC {target_ip} to IP {resolved_ip}")
                    return jsonify(
                        {
                            "hosts": [
                                {
                                    "ip": resolved_ip,
                                    "mac": resolved_host.get("mac"),
                                    "vendor": resolved_host.get("vendor"),
                                    "hostname": resolved_host.get(
                                        "hostname", "remote-target"
                                    ),
                                    "status": "selected",
                                }
                            ],
                            "messages": messages
                            + [
                                "Resolved MAC address "
                                f"{target_ip} to IP address {resolved_ip}."
                            ],
                            "error": None,
                            "detection_info": detection_info,
                        }
                    )
                except Exception as e:
                    logging.error(f"MAC resolution failed: {e}", exc_info=True)
                    return (
                        jsonify(
                            {
                                "error": (
                                    "An unexpected error occurred "
                                    "resolving MAC address."
                                ),
                                "messages": [],
                            }
                        ),
                        500,
                    )

            print(
                "Antigravity bypass: Skipping subnet scan. "
                f"Directly targeting host: {target_ip}"
            )
            return jsonify(
                {
                    "hosts": [
                        {
                            "ip": target_ip,
                            "hostname": "remote-tailscale-target",
                            "status": "selected",
                        }
                    ],
                    "messages": [f"Directly targeting host: {target_ip}"],
                    "error": None,
                    "detection_info": {},
                }
            )

        subnet = data.get("subnet")
        if subnet is not None and not isinstance(subnet, str):
            subnet = None
        try:
            scanner = PiScanner(
                username=os.environ.get("PI_SCANNER_USERNAME", "dummy"),
                password=os.environ.get("PI_SCANNER_PASSWORD", "dummy"),
            )
            hosts, messages, error, detection_info = scanner.scan(subnet=subnet)
            if error:
                logging.error(f"Scanner scan failed: {error}")
                return (
                    jsonify({"error": "Network scan failed.", "messages": messages}),
                    500,
                )
            return jsonify(
                {
                    "hosts": hosts,
                    "messages": messages,
                    "error": error,
                    "detection_info": detection_info,
                }
            )
        except Exception as e:
            logging.error(f"Pi scanning failed: {e}", exc_info=True)
            return (
                jsonify(
                    {
                        "error": "An unexpected error occurred "
                        "during network scanning.",
                        "messages": [],
                    }
                ),
                500,
            )

    @flask_app.route("/set-ip", methods=["POST"])
    def set_ip_address():
        data = request.get_json() or {}
        ip = data.get("ip")
        if not ip or not isinstance(ip, str):
            return jsonify({"error": "No valid IP address provided"}), 400
        session["target_ip"] = ip
        return jsonify({"message": "IP address set successfully"}), 200

    @flask_app.route("/get-device-details", methods=["POST"])
    def get_device_details():
        data = request.get_json() or {}
        ip_address = data.get("ip")
        username = data.get("username")
        password = data.get("password")
        if (
            not isinstance(ip_address, str)
            or not isinstance(username, str)
            or not isinstance(password, str)
        ):
            return (
                jsonify({"error": "Missing or invalid IP, username, or password"}),
                400,
            )
        try:
            device_scanner = PiScanner(username=username, password=password)
            snapshot, error = device_scanner.get_system_snapshot(ip_address)
            if error:
                logging.error(f"Snapshot retrieval failed: {error}")
                return jsonify({"error": "Failed to retrieve device details."}), 400
            if snapshot:
                ram_total_mb = (
                    snapshot.get("resources", {}).get("ram", {}).get("total_mb", 0)
                )
                details = {
                    "model": snapshot.get("model"),
                    "serial": snapshot.get("serial"),
                    "os_version": snapshot.get("os_version", "Linux"),
                    "docker_is_active": snapshot.get("docker_is_active", False),
                    "ram": f"{ram_total_mb} MB",
                    "disks": [
                        {
                            "mounted_on": "/",
                            "size": snapshot.get("resources", {})
                            .get("disk", {})
                            .get("size"),
                            "pcent": snapshot.get("resources", {})
                            .get("disk", {})
                            .get("pcent"),
                        }
                    ],
                }
                return jsonify(details)
            else:
                return jsonify({"error": "No device details retrieved"}), 400
        except Exception as e:
            logging.error(
                f"Error getting details for IP {ip_address}: {e}", exc_info=True
            )
            return jsonify({"error": "An unexpected internal error occurred."}), 500

    @flask_app.route("/api/components", methods=["GET"])
    def api_components():
        try:
            all_components = component_manager.get_all_components()
            components_dict = {comp["id"]: comp for comp in all_components}
            return jsonify(components_dict), 200
        except Exception as e:
            logging.error(f"Failed to retrieve components: {e}", exc_info=True)
            return jsonify({"error": "Failed to retrieve components."}), 500

    @flask_app.route("/get-available-software", methods=["POST"])
    def get_available_software():
        try:
            all_components = component_manager.get_all_components()
            all_packages = component_manager.get_all_packages()
            return (
                jsonify(
                    {
                        "available_software": all_components,
                        "available_packages": all_packages,
                    }
                ),
                200,
            )
        except Exception as e:
            logging.error(f"Failed to get available software: {e}", exc_info=True)
            return jsonify({"error": "Failed to retrieve software list."}), 500

    @flask_app.route("/get-software-groups", methods=["GET"])
    def get_software_groups():
        try:
            all_components = component_manager.get_all_components()
            meta = component_manager.get_piselfhosting_meta()
            group_rules = meta.get("group_rules", {})
            group_order = meta.get("group_order", [])
            id_to_name_map = {
                gid: rules.get("name", gid.replace("_", " ").title())
                for gid, rules in group_rules.items()
            }
            id_to_exclusive_map = {
                gid: rules.get("is_exclusive", False)
                for gid, rules in group_rules.items()
            }
            components_by_group_id = {}
            for component in all_components:
                group_id = component.get("group")
                component_id = component.get("id")
                if group_id and component_id:
                    if group_id not in components_by_group_id:
                        components_by_group_id[group_id] = []
                    components_by_group_id[group_id].append(component_id)
            groups_to_components = {}
            for group_id in group_order:
                if group_id in components_by_group_id:
                    display_name = id_to_name_map.get(group_id, group_id)
                    is_exclusive = id_to_exclusive_map.get(group_id, False)
                    groups_to_components[display_name] = {
                        "is_exclusive": is_exclusive,
                        "components": components_by_group_id.pop(group_id),
                    }
            for group_id, comp_list in sorted(components_by_group_id.items()):
                display_name = id_to_name_map.get(group_id, group_id)
                is_exclusive = id_to_exclusive_map.get(group_id, False)
                groups_to_components[display_name] = {
                    "is_exclusive": is_exclusive,
                    "components": comp_list,
                }
            return jsonify({"groups": groups_to_components}), 200
        except Exception as e:
            logging.error(f"Failed to get software groups: {e}", exc_info=True)
            return jsonify({"error": "Failed to retrieve software groups."}), 500

    @flask_app.route("/get-required-variables", methods=["POST"])
    def get_required_variables():
        try:
            data = request.get_json(force=True) or {}
            selected_components = data.get("selected_components")
            if not isinstance(selected_components, list):
                return jsonify({"error": "Missing or invalid selected_components"}), 400

            all_components_list = component_manager.get_all_components()
            all_components_dict = {comp["id"]: comp for comp in all_components_list}
            components_for_ui = {}

            for component_id in selected_components:
                component_data = all_components_dict.get(component_id)
                if component_data:
                    vars_list = component_data.get("variables") or component_data.get(
                        "required_variables"
                    )
                    if vars_list:
                        components_for_ui[component_id] = {
                            "name": component_data.get("name", component_id),
                            "variables": vars_list,
                        }
            return jsonify({"components": components_for_ui}), 200
        except Exception as e:
            logging.error(f"Failed to get variables: {e}", exc_info=True)
            return (
                jsonify({"error": "Failed to retrieve configuration variables."}),
                500,
            )

    @flask_app.route("/validate-selection", methods=["POST"])
    def validate_selection():
        try:
            data = request.get_json(force=True) or {}
            selected_components = data.get("selected_components")
            if not isinstance(selected_components, list):
                return jsonify({"error": "Missing or invalid selected_components"}), 400

            base_template_path = templates_path_obj
            all_components_dict = {
                comp["id"]: comp for comp in component_manager.get_all_components()
            }

            for component_id in selected_components:
                # Mitigate Path Traversal / CWE-22 using safe_join helper
                try:
                    template_path_obj = safe_join(base_template_path, component_id)
                except ValueError:
                    logging.warning(
                        f"Validation failed for component ID: {component_id}"
                    )
                    return (
                        jsonify(
                            {
                                "error": "Invalid component ID format "
                                "or path traversal.",
                                "component_id": component_id,
                            }
                        ),
                        400,
                    )

                if not template_path_obj.exists():
                    return (
                        jsonify(
                            {
                                "error": f"Template directory "
                                f"missing: '{component_id}'.",
                                "component_id": component_id,
                            }
                        ),
                        400,
                    )
                component_data = all_components_dict.get(component_id)
                if component_data and component_data.get("has_configuration"):
                    variables_path = (
                        template_path_obj / "template-config" / "variables.json"
                    )
                    if not variables_path.is_file():
                        return (
                            jsonify(
                                {
                                    "error": f"'variables.json'"
                                    f" missing: '{component_id}'.",
                                    "component_id": component_id,
                                }
                            ),
                            400,
                        )
            return jsonify({"message": "Selection is valid."}), 200
        except Exception as e:
            logging.error(f"Validation process failed: {e}", exc_info=True)
            return jsonify({"error": "An unexpected validation error occurred."}), 500

    @flask_app.route("/api/v1/system/analyze", methods=["POST"])
    def system_analyze():
        data = request.get_json() or {}
        is_reinstallation = bool(data.get("is_reinstallation", False))
        devices = data.get("devices")
        raw_components = data.get("components")

        if not isinstance(devices, list) or not isinstance(raw_components, list):
            return jsonify({"error": "Missing 'devices' or 'components' list"}), 400

        enriched_components = []
        all_components_list = component_manager.get_all_components()
        all_components_dict = {comp["id"]: comp for comp in all_components_list}

        for raw_comp in raw_components:
            comp_id = raw_comp.get("id")
            meta = all_components_dict.get(comp_id, {})
            enriched_components.append(
                {
                    "id": comp_id,
                    "name": raw_comp.get("name", comp_id),
                    "ports": raw_comp.get("ports") or meta.get("ports", []),
                    "volumes": raw_comp.get("volumes") or meta.get("volumes", []),
                }
            )

        internal_port_map = {}
        for component in enriched_components:
            for port_str in component.get("ports", []):
                # Safe linear parsing to avoid ReDoS
                if ":" in port_str:
                    before_colon = port_str.split(":")[0]
                    if before_colon.isdigit():
                        port = before_colon
                        if port in internal_port_map:
                            return (
                                jsonify(
                                    {
                                        "status": "error",
                                        "internal_conflicts": [
                                            f"Port {port} is used by "
                                            f"'{internal_port_map[port]}' and "
                                            f"'{component.get('name')}'."
                                        ],
                                    }
                                ),
                                400,
                            )
                        internal_port_map[port] = component.get("name")

        device = devices[0]
        analysis_scanner = PiScanner(
            username=device.get("username"), password=device.get("password")
        )
        snapshot, err = analysis_scanner.get_system_snapshot(device.get("ip"))

        if err:
            return (
                jsonify({"error": "Failed to retrieve system details for analysis."}),
                500,
            )

        external_conflicts, resource_warnings = analyze_snapshot(
            enriched_components, snapshot, is_reinstallation
        )

        return (
            jsonify(
                {
                    "status": "success",
                    "internal_conflicts": [],
                    "external_conflicts": external_conflicts,
                    "resource_warnings": resource_warnings,
                }
            ),
            200,
        )

    @flask_app.route("/start-installation", methods=["POST"])
    def start_installation():
        try:
            data = request.get_json(force=True) or {}
            selected_components = data.get("selected_components")
            managed_devices = data.get("devices")
            user_variables = data.get("env_vars", {})

            if not isinstance(selected_components, list) or not isinstance(
                managed_devices, list
            ):
                return (
                    jsonify({"error": "Missing or invalid selection or devices"}),
                    400,
                )

            if not isinstance(user_variables, dict):
                user_variables = {}

            success, errors = setup_manager.prepare_deployment_package(
                selected_components, user_variables, managed_devices
            )
            if not success:
                logging.error(f"Installation preparation failed: {errors}")
                return jsonify({"error": "File generation failed."}), 400

            # Generate the unified docker-compose.yml and .env files
            all_components_list = component_manager.get_all_components()
            selected_components_data = [
                c for c in all_components_list if c.get("id") in selected_components
            ]
            component_manager.generate_deployment_artifacts(
                selected_components_data=selected_components_data,
                global_vars=user_variables,
                output_path=Path(setup_manager.output_dir),
            )

            return (
                jsonify(
                    {
                        "message": "Configuration files generated.",
                        "output_path": str(setup_manager.output_dir),
                    }
                ),
                200,
            )
        except Exception as e:
            logging.error(f"Installation failed: {e}", exc_info=True)
            return (
                jsonify(
                    {"error": "An unexpected deployment packaging error occurred."}
                ),
                500,
            )

    @flask_app.route("/deploy-configuration", methods=["POST"])
    def deploy_configuration():
        data = request.get_json(force=True) or {}
        output_path = data.get("output_path")
        managed_devices = data.get("devices", [])
        components_to_clean = data.get("components_to_clean", [])
        components_to_restart = data.get("components_to_restart", [])
        analysis_results = data.get("analysis_results", {})
        selected_components_data = data.get("selected_components_data", [])
        global_vars = data.get("global_vars", {})

        if not isinstance(output_path, str) or not isinstance(managed_devices, list):
            return jsonify({"error": "Missing or invalid output_path or devices"}), 400

        if not isinstance(components_to_clean, list):
            components_to_clean = []
        if not isinstance(components_to_restart, list):
            components_to_restart = []
        if not isinstance(analysis_results, dict):
            analysis_results = {}
        if not isinstance(selected_components_data, list):
            selected_components_data = []
        if not isinstance(global_vars, dict):
            global_vars = {}

        first_device = next(iter(managed_devices), {})
        if not first_device:
            return jsonify({"error": "No target device provided for deployment"}), 400

        target_ip = first_device.get("ip", "unknown")
        all_errors = flask_app.map_analysis_to_report_errors(
            analysis_results, target_ip
        )

        blocking_types = [
            "Validation:PortConflict:DANGEROUS_NATIVE_PROCESS_CONFLICT",
            "Validation:VolumeConflict:EXISTING_VOLUME_CONFLICT",
            "Validation:PortConflict:UNEXPECTED_DOCKER_CONFLICT",
        ]

        blocking_errors = [err for err in all_errors if err["type"] in blocking_types]

        if blocking_errors:
            logging.error(
                f"Blocking pre-deployment conflicts detected: "
                f"{len(blocking_errors)} errors."
            )
            return (
                jsonify(
                    {
                        "error": "Pre-deployment conflicts detected.",
                        "details": "Critical conflicts must be resolved first.",
                        "errors": blocking_errors,
                    }
                ),
                400,
            )

        task_id = uuid.uuid4().hex

        non_blocking_errors = [
            err for err in all_errors if err["type"] not in blocking_types
        ]
        logs_start = [
            f"WARNING/INFO: {err['summary']}. See task status for details."
            for err in non_blocking_errors
        ]

        flask_app.deployment_tasks[task_id] = {
            "status": "running",
            "logs": logs_start,
            "errors": non_blocking_errors,
        }

        flask_app.deployment_tasks[task_id]["logs"].append(
            "Starting deployment process..."
        )

        thread = threading.Thread(
            target=deployment_manager.start_deployment,
            args=(
                task_id,
                flask_app.deployment_tasks,
                output_path,
                managed_devices,
                components_to_clean,
                components_to_restart,
                selected_components_data,
                global_vars,
            ),
        )
        thread.start()
        return jsonify({"task_id": task_id}), 202

    @flask_app.route("/stream-deployment/<target_task_id>")
    def stream_deployment(target_task_id):
        def generate():
            last_sent_index = 0
            while True:
                task = flask_app.deployment_tasks.get(target_task_id)
                if not isinstance(task, dict):
                    break

                logs_to_send = task.get("logs", [])[last_sent_index:]
                for log_line in logs_to_send:
                    yield f"data: {log_line}\n\n"
                last_sent_index += len(logs_to_send)

                if task.get("status") != "running":
                    break
                time.sleep(0.5)

        return Response(generate(), mimetype="text/event-stream")

    @flask_app.route("/task-status/<target_task_id>")
    def task_status(target_task_id):
        task = flask_app.deployment_tasks.get(target_task_id)
        if not isinstance(task, dict):
            return jsonify({"error": "Task not found"}), 404
        return jsonify(task)

    return flask_app


if __name__ == "__main__":
    app = create_app()
    debug_mode = os.environ.get("FLASK_DEBUG", "False").lower() in ("true", "1")
    app.run(host="0.0.0.0", port=5001, debug=debug_mode)  # nosec B104
