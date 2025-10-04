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
from utils.resource_utils import resource_path

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


def analyze_snapshot(components, snapshot, is_reinstallation):
    """
    Helper function to analyze the system snapshot against the requested
    components and return a categorized list of conflicts and warnings.
    """
    conflicts = {"ports": [], "volumes": []}
    warnings = []
    used_ports = {
        p["port"]: p["process_name"] for p in snapshot.get("native_processes", [])
    }
    for container in snapshot.get("containers", []):
        port_mappings = re.findall(r"0\.0\.0\.0:(\d+)->", container.get("ports", ""))
        for port in port_mappings:
            used_ports[int(port)] = f"docker container ({container.get('name')})"
    existing_volumes = set()
    for container in snapshot.get("containers", []):
        mounts = container.get("mounts", "").split(",")
        for mount in mounts:
            if ":" in mount:
                host_path = mount.split(":")[0]
                if "." not in Path(host_path).name:
                    existing_volumes.add(host_path)
    for component in components:
        comp_name = component.get("name")
        # Use component ID for reliable string matching
        comp_id = component.get("id", comp_name).lower()

        # DEFINITIVE FIX: Create a clean ID for robust,
        # cross-version container name matching
        comp_id_clean = comp_id.replace("-", "")

        for port_str in component.get("ports", []):
            match = re.match(r"(\d+):", port_str)
            if match:
                port = int(match.group(1))
                if port in used_ports:
                    conflicting_service = used_ports[port]

                    # Store a clean version of the conflicting service string for
                    # comparison
                    conflicting_service_clean = conflicting_service.lower().replace(
                        "-", ""
                    )

                    conflict_type = "UNEXPECTED_DOCKER_CONFLICT"
                    if "docker" not in conflicting_service:
                        conflict_type = "DANGEROUS_NATIVE_PROCESS_CONFLICT"
                    # CRITICAL FIX: Robust Re-use check for PiSelfhosting containers.
                    # 1. Check if it is a docker container.
                    # 2. Check if the clean component ID is in the clean
                    # conflicting service name.
                    # 3. Check if we are in a reinstallation context.
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
        for volume_str in component.get("volumes", []):
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
    if ram.get("total_mb", 0) > 0 and ram.get("used_mb", 0) / ram.get("total_mb") > 0.9:
        warnings.append(
            {
                "type": "RAM",
                "message": "The target system is using over 90% of its RAM.",
            }
        )
    return conflicts, warnings


def map_analysis_to_report_errors(analysis_results: dict, target_ip: str) -> list[dict]:
    """
    Maps analysis conflicts and warnings into the canonical ReportError contract.
    The ReportError contract includes: type, summary, details, component_id,
    timestamp.
    """
    errors = []
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conflicts = analysis_results.get("external_conflicts", {})

    # 1. Map Port Conflicts
    port_conflicts = conflicts.get("ports", [])
    for conflict in port_conflicts:
        port = conflict.get("port")
        conflict_type = conflict.get("conflict_type")
        conflicting_service = conflict.get("conflicting_service")
        # DEFENSIVE CODING: Use "N/A" if proposed_service is missing
        proposed_service = conflict.get("proposed_service", "N/A")

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

    # 2. Map Volume Conflicts
    volume_conflicts = conflicts.get("volumes", [])
    for conflict in volume_conflicts:
        volume_path = conflict.get("volume_path")
        conflict_type = conflict.get("conflict_type")
        # DEFENSIVE CODING: Use "N/A" if proposed_service is missing
        proposed_service = conflict.get("proposed_service", "N/A")

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

    # 3. Map Resource Warnings
    resource_warnings = analysis_results.get("resource_warnings", [])
    for warning in resource_warnings:
        warning_type = warning.get("type")
        message = warning.get("message")

        error_type = f"Warning:Resource:{warning_type}"
        summary = f"Resource warning detected: {warning_type}"
        details = (
            f"The resource analysis on {target_ip} generated a warning: "
            f"{message}. Deployment may proceed, but performance may be "
            f"impacted."
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


def create_app():
    """Factory function to create and configure the Flask application."""
    flask_app = Flask(__name__, static_folder="static", static_url_path="/static")
    flask_app.secret_key = os.environ.get(
        "FLASK_SECRET_KEY", "a-default-secret-key-for-development"
    )

    metadata_path = resource_path("config/components_metadata.json")
    templates_path = resource_path("component_templates")
    component_manager = ComponentManager(
        metadata_file_path=metadata_path, templates_path=templates_path
    )

    app_data_dir = Path(user_data_dir("PiSelfhosting", "PiSelfhosting"))
    output_dir = app_data_dir / "output"
    setup_manager = SetupManager(component_manager, output_dir=output_dir)
    deployment_manager = DeploymentManager(component_manager=component_manager)

    # 1. ATTACH THE TASK DICTIONARY TO THE APP INSTANCE
    flask_app.deployment_tasks = {}

    # 2. ATTACH THE HELPER FUNCTION TO THE APP INSTANCE
    # FIX: Renaming for PEP 8 compliance (no protected access outside class)
    flask_app.map_analysis_to_report_errors = map_analysis_to_report_errors

    @flask_app.route("/", methods=["GET"])
    def index():
        return render_template("index.html")

    @flask_app.route("/summary", methods=["GET"])
    def summary():
        return render_template("summary.html")

    @flask_app.route("/scan-pis", methods=["POST"])
    def scan_pis():
        data = request.get_json()
        subnet = data.get("subnet")
        try:
            scanner = PiScanner(
                username=os.environ.get("PI_SCANNER_USERNAME", "dummy"),
                password=os.environ.get("PI_SCANNER_PASSWORD", "dummy"),
            )
            hosts, messages, error, detection_info = scanner.scan(subnet=subnet)
            if error:
                return jsonify({"error": error, "messages": messages}), 500
            return jsonify(
                {
                    "hosts": hosts,
                    "messages": messages,
                    "error": error,
                    "detection_info": detection_info,
                }
            )
        except Exception as e:
            logging.error(f"Pi scanning failed: {e}")
            return (
                jsonify(
                    {"error": str(e), "messages": [f"❌ Unexpected error: {str(e)}"]}
                ),
                500,
            )

    @flask_app.route("/set-ip", methods=["POST"])
    def set_ip_address():
        data = request.get_json()
        ip = data.get("ip")
        if not ip:
            return jsonify({"error": "No IP address provided"}), 400
        session["target_ip"] = ip
        return jsonify({"message": "IP address set successfully"}), 200

    # START OF FIX:
    # The /get-device-details endpoint is restored. It now uses the powerful
    # get_system_snapshot method and extracts only the data needed for Step 2.
    @flask_app.route("/get-device-details", methods=["POST"])
    def get_device_details():
        data = request.get_json()
        ip_address = data.get("ip")
        username = data.get("username")
        password = data.get("password")
        if not all([ip_address, username, password]):
            return jsonify({"error": "Missing IP, username, or password"}), 400
        try:
            scanner = PiScanner(username=username, password=password)
            snapshot, error = scanner.get_system_snapshot(ip_address)
            if error:
                return jsonify({"error": error}), 400
            if snapshot:
                # Extract RAM details robustly and outside the f-string definition
                ram_total_mb = (
                    snapshot.get("resources", {}).get("ram", {}).get("total_mb", 0)
                )

                # Adapt the rich snapshot to the simple details format the UI expects
                details = {
                    "model": snapshot.get("model"),
                    "serial": snapshot.get("serial"),
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
                return jsonify({"details": details})
            else:
                return jsonify({"error": "No device details retrieved"}), 400
        except Exception as e:
            logging.error(f"Error in get_device_details for IP {ip_address}: {e}")
            return jsonify({"error": str(e)}), 500

    # END OF FIX

    @flask_app.route("/get-available-software", methods=["POST"])
    def get_available_software():
        _ = request.get_json(force=True).get("devices", [])
        try:
            all_components = component_manager.get_all_components()
            return jsonify({"available_software": all_components}), 200
        except Exception as e:
            logging.error(f"Failed to get available software: {e}")
            return jsonify({"error": str(e)}), 500

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
                    groups_to_components[display_name] = components_by_group_id.pop(
                        group_id
                    )
            for group_id, comp_list in sorted(components_by_group_id.items()):
                display_name = id_to_name_map.get(group_id, group_id)
                groups_to_components[display_name] = comp_list
            return jsonify({"groups": groups_to_components}), 200
        except Exception as e:
            logging.error(f"Failed to get software groups: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500

    @flask_app.route("/get-required-variables", methods=["POST"])
    def get_required_variables():
        try:
            data = request.get_json(force=True)
            selected_components = data.get("selected_components")
            if selected_components is None:
                return jsonify({"error": "Missing selected_components"}), 400
            all_components_list = component_manager.get_all_components()
            all_components_dict = {comp["id"]: comp for comp in all_components_list}
            components_for_ui = {}
            for component_id in selected_components:
                component_data = all_components_dict.get(component_id)
                if component_data and component_data.get("required_variables"):
                    components_for_ui[component_id] = {
                        "name": component_data.get("name", component_id),
                        "variables": component_data.get("required_variables", []),
                    }
            return jsonify({"components": components_for_ui}), 200
        except Exception as e:
            logging.error(f"Failed to get required variables: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500

    @flask_app.route("/validate-selection", methods=["POST"])
    def validate_selection():
        try:
            data = request.get_json(force=True)
            selected_components = data.get("selected_components")
            if selected_components is None:
                return jsonify({"error": "Missing selected_components"}), 400
            base_template_path = Path(resource_path("component_templates"))
            all_components_dict = {
                comp["id"]: comp for comp in component_manager.get_all_components()
            }
            for component_id in selected_components:
                template_path_obj = base_template_path / component_id
                if not template_path_obj.exists():
                    error_message = (
                        f"Validation failed: "
                        f"Template directory not "
                        f"found for '{component_id}'."
                    )
                    return (
                        jsonify({"error": error_message, "component_id": component_id}),
                        400,
                    )
                component_data = all_components_dict.get(component_id)
                if component_data and component_data.get("has_configuration"):
                    variables_path = (
                        template_path_obj / "template-config" / "variables.json"
                    )
                    if not variables_path.is_file():
                        error_message = (
                            f"Configuration integrity error: "
                            f"'variables.json' "
                            f"missing for '{component_id}'."
                        )
                        return (
                            jsonify(
                                {"error": error_message, "component_id": component_id}
                            ),
                            400,
                        )
            return jsonify({"message": "Selection is valid."}), 200
        except Exception as e:
            logging.error(f"Validation process failed: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500

    @flask_app.route("/api/v1/system/analyze", methods=["POST"])
    def system_analyze():
        data = request.get_json()
        if not data:
            return jsonify({"error": "Malformed JSON received"}), 400
        is_reinstallation = data.get("is_reinstallation", False)
        devices = data.get("devices")
        components = data.get("components")
        if not devices or components is None:
            return jsonify({"error": "Missing 'devices' or 'components' list"}), 400
        internal_port_map = {}
        for component in components:
            for port_str in component.get("ports", []):
                match = re.match(r"(\d+):", port_str)
                if match:
                    port = match.group(1)
                    if port in internal_port_map:
                        return (
                            jsonify(
                                {
                                    "status": "error",
                                    "internal_conflicts": [
                                        f"Port {port} is used by"
                                        f" both '{internal_port_map[port]}' "
                                        f"and '{component.get('name')}'."
                                    ],
                                }
                            ),
                            400,
                        )
                    internal_port_map[port] = component.get("name")
        device = devices[0]
        scanner = PiScanner(
            username=device.get("username"), password=device.get("password")
        )
        snapshot, err = scanner.get_system_snapshot(device.get("ip"))
        if err:
            return jsonify({"error": f"Failed to get system snapshot: {err}"}), 500
        # FIX: Call the renamed function
        external_conflicts, resource_warnings = analyze_snapshot(
            components, snapshot, is_reinstallation
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
            data = request.get_json(force=True)
            selected_components = data.get("selected_components")
            managed_devices = data.get("devices")
            user_variables = data.get("env_vars", {})
            if selected_components is None or managed_devices is None:
                return jsonify({"error": "Missing selection or devices"}), 400
            success, errors = setup_manager.prepare_deployment_package(
                selected_components, user_variables, managed_devices
            )
            if not success:
                return (
                    jsonify({"error": "File generation failed.", "details": errors}),
                    400,
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
            logging.error(f"Installation process failed: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500

    @flask_app.route("/deploy-configuration", methods=["POST"])
    def deploy_configuration():
        data = request.get_json(force=True)
        output_path = data.get("output_path")
        managed_devices = data.get("devices")
        components_to_clean = data.get("components_to_clean", [])
        components_to_restart = data.get("components_to_restart", [])
        analysis_results = data.get("analysis_results", {})

        # CRITICAL FIX: Retrieve the two missing arguments from the request body
        selected_components_data = data.get("selected_components_data", [])
        global_vars = data.get("global_vars", {})

        if not output_path or not managed_devices:
            return jsonify({"error": "Missing output_path or devices"}), 400

        # Unpack the first device for IP. Uses the Unpacking-First Mandate.
        first_device = next(iter(managed_devices), None)
        if first_device is None:
            return (
                jsonify({"error": "No target device provided for deployment"}),
                400,
            )
        target_ip = first_device.get("ip")

        # 1. Gatekeeping Logic: Map conflicts to ReportErrors
        # Use the attached helper function
        # FIX: Call the renamed function
        all_errors = flask_app.map_analysis_to_report_errors(
            analysis_results, target_ip
        )

        # 2. Check for blocking conflicts
        blocking_types = [
            "Validation:PortConflict:DANGEROUS_NATIVE_PROCESS_CONFLICT",
            "Validation:VolumeConflict:EXISTING_VOLUME_CONFLICT",
            "Validation:PortConflict:UNEXPECTED_DOCKER_CONFLICT",
        ]

        blocking_errors = [err for err in all_errors if err["type"] in blocking_types]

        if blocking_errors:
            # Deployment is gated. Return 400 with structured errors.
            logging.error(
                f"Blocking pre-deployment conflicts detected: "
                f"{len(blocking_errors)} errors."
            )
            return (
                jsonify(
                    {
                        "error": "Pre-deployment conflicts detected.",
                        "details": (
                            "Critical port or volume conflicts must be resolved "
                            "before deployment can start."
                        ),
                        "errors": blocking_errors,
                    }
                ),
                400,
            )

        # 3. If no blocking errors, proceed with deployment
        task_id = str(uuid.uuid4())

        # All non-blocking errors (e.g., warnings and expected reinstallations)
        # are added to the task's errors list for later status check, and
        # logged to the stream immediately.
        non_blocking_errors = [
            err for err in all_errors if err["type"] not in blocking_types
        ]
        logs_start = [
            f"WARNING/INFO: {err['summary']}. See task status for details."
            for err in non_blocking_errors
        ]

        # Use the attached deployment_tasks dictionary
        flask_app.deployment_tasks[task_id] = {
            "status": "running",
            "logs": logs_start,
            "errors": non_blocking_errors,
        }

        # Log that deployment is starting after checks
        flask_app.deployment_tasks[task_id]["logs"].append(
            "Starting deployment process..."
        )

        thread = threading.Thread(
            target=deployment_manager.start_deployment,
            args=(
                task_id,
                flask_app.deployment_tasks,  # Use the attached dictionary
                output_path,
                managed_devices,
                components_to_clean,
                components_to_restart,
                # CRITICAL FIX: Pass the missing arguments to the thread
                selected_components_data,
                global_vars,
            ),
        )
        thread.start()
        return jsonify({"task_id": task_id}), 202

    @flask_app.route("/stream-deployment/<task_id>")
    def stream_deployment(task_id):
        def generate():
            last_sent_index = 0
            while True:
                # Use the attached deployment_tasks dictionary
                task = flask_app.deployment_tasks.get(task_id)
                if not task:
                    break
                logs_to_send = task["logs"][last_sent_index:]
                for log_line in logs_to_send:
                    yield f"data: {log_line}\n\n"
                last_sent_index += len(logs_to_send)
                if task["status"] != "running":
                    break
                time.sleep(0.5)

        return Response(generate(), mimetype="text/event-stream")

    @flask_app.route("/task-status/<task_id>")
    def task_status(task_id):
        # Use the attached deployment_tasks dictionary
        task = flask_app.deployment_tasks.get(task_id)
        if not task:
            return jsonify({"error": "Task not found"}), 404
        return jsonify(task)

    return flask_app
