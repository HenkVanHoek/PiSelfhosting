import logging
import os
import threading
import time
import uuid
from pathlib import Path

from appdirs import user_data_dir
from flask import (
    Flask,
    jsonify,
    render_template,
    request,
    session,
    Response,
)

from managers.component_manager import ComponentManager
from managers.deployment_manager import DeploymentManager
from managers.setup_manager import SetupManager
from pi_scanner import PiScanner
from utils.resource_utils import resource_path

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

# --- App Dependencies Initialization ---
metadata_path = resource_path(
    str(Path("config") / "components_metadata.json"))

APP_DATA_DIR = Path(user_data_dir("PiSelfhosting", "PiSelfhosting"))
OUTPUT_DIR = APP_DATA_DIR / "output"

component_manager = ComponentManager(metadata_file=metadata_path)
setup_manager = SetupManager(component_manager, output_dir=OUTPUT_DIR)

# THE CRITICAL FIX: Pass the component_manager to the DeploymentManager
deployment_manager = DeploymentManager(component_manager=component_manager)

setup_manager.output_dir = OUTPUT_DIR

DEPLOYMENT_TASKS = {}


def create_app(
        component_manager_instance=component_manager,
        setup_manager_instance=setup_manager,
        deployment_manager_instance=deployment_manager,
):
    """
    Factory function to create the Flask application.
    """
    flask_app = Flask(__name__, static_folder='static',
                      static_url_path='/static')

    logging.info(f"Application data directory: {APP_DATA_DIR}")

    flask_app.secret_key = os.environ.get(
        "FLASK_SECRET_KEY", "a-default-secret-key-for-development"
    )

    # --- Routes ---
    @flask_app.route("/", methods=["GET"])
    def index():
        return render_template("index.html")

    @flask_app.route("/scan-pis", methods=["POST"])
    def scan_pis():
        data = request.get_json()
        subnet = data.get("subnet")
        try:
            scanner = PiScanner(username="dummy", password="dummy")
            hosts, messages, error, detection_info = scanner.scan(subnet=subnet)
            if error:
                return jsonify({"error": error, "messages": messages}), 500
            permissions_error_detected = False
            num_hosts_found = len(hosts)
            mac_addresses_found = detection_info.get('mac_addresses_found', 0)
            if num_hosts_found == 0 and mac_addresses_found == 0 and detection_info.get('total_hosts_scanned', 0) > 0:
                permissions_error_detected = True
            return jsonify(
                {
                    "hosts": hosts, "messages": messages, "error": error,
                    "permissions_error": permissions_error_detected,
                    "detection_info": {
                        "success": detection_info.get("success"), "method_used": detection_info.get("method_used"),
                        "detected_ip": detection_info.get("detected_ip"), "subnet": detection_info.get("subnet"),
                    },
                }
            )
        except Exception as e:
            logging.error(f"Pi scanning failed: {e}")
            return jsonify({"error": str(e), "messages": [f"❌ Unexpected error: {str(e)}"]}), 500

    @flask_app.route("/set-ip", methods=["POST"])
    def set_ip_address():
        data = request.get_json()
        ip = data.get("ip")
        if not ip:
            return jsonify({"error": "No IP address provided"}), 400
        session["target_ip"] = ip
        return jsonify({"message": "IP address set successfully"}), 200

    @flask_app.route("/get-device-details", methods=["POST"])
    def get_device_details():
        data = request.get_json()
        ip_address = data.get("ip")
        username = data.get("username")
        password = data.get("password")
        if not all([ip_address, username, password]):
            return jsonify({"error": "Missing IP address, username, or password"}), 400
        try:
            scanner = PiScanner(username=username, password=password)
            details, error = scanner.get_device_details(ip_address)
            if error:
                return jsonify({"error": error}), 400
            if details:
                return jsonify({"details": details}), 200
            else:
                return jsonify({"error": "No device details retrieved"}), 400
        except Exception as e:
            logging.error(f"Device detail retrieval failed: {e}")
            return jsonify({"error": str(e)}), 500

    @flask_app.route("/get-available-software", methods=["POST"])
    def get_available_software():
        discovered_devices = request.get_json(force=True).get("devices", [])
        if not discovered_devices:
            return jsonify({"error": "No devices provided"}), 400
        try:
            all_components = component_manager_instance.get_all_components()
            return jsonify({"available_software": all_components}), 200
        except Exception as e:
            logging.error(f"Failed to get available software: {e}")
            return jsonify({"error": str(e)}), 500

    @flask_app.route("/get-software-groups", methods=["GET"])
    def get_software_groups():
        try:
            groups = component_manager_instance.get_uniqueness_groups()
            return jsonify({"groups": groups}), 200
        except Exception as e:
            logging.error(f"Failed to get software groups: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500

    @flask_app.route("/get-required-variables", methods=["POST"])
    def get_required_variables():
        try:
            data = request.get_json(force=True)
            if not data:
                return jsonify({"error": "Malformed JSON received"}), 400
            selected_components = data.get("selected_components")
            if selected_components is None:
                return jsonify({"error": "Missing selected_components"}), 400
            all_components_list = component_manager_instance.get_all_components()
            all_components_dict = {comp['id']: comp for comp in all_components_list}
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
            if not data:
                return jsonify({"error": "Malformed JSON received"}), 400
            selected_components = data.get("selected_components")
            if selected_components is None:
                return jsonify({"error": "Missing selected_components"}), 400
            for component_id in selected_components:
                template_path_str = component_manager_instance.config.get_component_template_path(component_id)
                template_path_obj = Path(template_path_str)
                if not template_path_obj.exists():
                    error_message = f"Validation failed: Template directory not found for '{component_id}'."
                    logging.warning(error_message)
                    return jsonify({"error": error_message, "component_id": component_id}), 400
            return jsonify({"message": "Selection is valid."}), 200
        except Exception as e:
            logging.error(f"Validation process failed: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500

    @flask_app.route("/start-installation", methods=["POST"])
    def start_installation():
        try:
            data = request.get_json(force=True)
            if not data:
                return jsonify({"error": "Malformed JSON received"}), 400
            selected_components = data.get("selected_components")
            managed_devices = data.get("devices")
            env_vars = data.get("env_vars", {})
            if selected_components is None or managed_devices is None:
                return jsonify({"error": "Missing selected_components or devices"}), 400
            success, errors = setup_manager_instance.generate_all_files(
                                 selected_components, env_vars, managed_devices)
            if not success:
                logging.error(f"File generation failed with errors: {errors}")
                return jsonify({"error": "File generation failed.", "details": errors}), 400
            output_directory_path = str(setup_manager_instance.output_dir)
            return jsonify({"message": "Configuration files generated successfully.", "output_path": output_directory_path}), 200
        except Exception as e:
            logging.error(f"Installation process failed: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500

    @flask_app.route("/deploy-configuration", methods=["POST"])
    def deploy_configuration():
        data = request.get_json(force=True)
        output_path = data.get("output_path")
        managed_devices = data.get("devices")
        if not output_path or not managed_devices:
            return jsonify({"error": "Missing output_path or devices"}), 400
        task_id = str(uuid.uuid4())
        DEPLOYMENT_TASKS[task_id] = {"status": "running", "logs": [], "last_update": time.time()}
        thread = threading.Thread(
            target=deployment_manager_instance.start_deployment,
            args=(task_id, DEPLOYMENT_TASKS, output_path, managed_devices)
        )
        thread.start()
        return jsonify({"task_id": task_id}), 202

    @flask_app.route("/stream-deployment/<task_id>")
    def stream_deployment(task_id):
        def generate():
            last_sent_index = 0
            while True:
                task = DEPLOYMENT_TASKS.get(task_id)
                if not task: break
                logs_to_send = task["logs"][last_sent_index:]
                for log_line in logs_to_send:
                    yield f"data: {log_line}\n\n"
                last_sent_index += len(logs_to_send)
                if task["status"] != "running": break
                time.sleep(0.5)
        return Response(generate(), mimetype="text/event-stream")

    @flask_app.route("/task-status/<task_id>")
    def task_status(task_id):
        task = DEPLOYMENT_TASKS.get(task_id)
        if not task:
            return jsonify({"error": "Task not found"}), 404
        return jsonify(task)

    return flask_app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, threaded=True)