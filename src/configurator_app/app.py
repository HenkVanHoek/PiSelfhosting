import logging
import os  # Needed for accessing environment variables (e.g., FLASK_SECRET_KEY)
from pathlib import Path

from appdirs import user_data_dir
from flask import (
    Flask,
    jsonify,
    render_template,
    request,
    session,
)

from managers.component_manager import ComponentManager
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
setup_manager.output_dir = OUTPUT_DIR


def create_app(
        component_manager_instance=component_manager,
        setup_manager_instance=setup_manager,
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

            if num_hosts_found == 0 and mac_addresses_found == 0 and detection_info.get(
                    'total_hosts_scanned', 0) > 0:
                permissions_error_detected = True

            return jsonify(
                {
                    "hosts": hosts,
                    "messages": messages,
                    "error": error,
                    "permissions_error": permissions_error_detected,
                    "detection_info": {
                        "success": detection_info.get("success"),
                        "method_used": detection_info.get("method_used"),
                        "detected_ip": detection_info.get("detected_ip"),
                        "subnet": detection_info.get("subnet"),
                    },
                }
            )

        except Exception as e:
            logging.error(f"Pi scanning failed: {e}")
            return (
                jsonify(
                    {"error": str(e),
                     "messages": [f"❌ Unexpected error: {str(e)}"]}
                ),
                500,
            )

    # RESTORED: The missing /set-ip route
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
            return jsonify(
                {"error": "Missing IP address, username, or password"}), 400

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

            variables = component_manager_instance.get_required_variables(
                selected_components
            )

            return jsonify({"required_variables": variables}), 200

        except Exception as e:
            logging.error(f"Failed to get required variables: {e}", exc_info=True)
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
                                 selected_components, env_vars)

            if not success:
                 # If generation fails, return a 400 error with the specific reasons.
                logging.error(f"File generation failed with errors: {errors}")

                return jsonify(
                {"error": "File generation failed.", "details": errors}), 400
            output_directory_path = str(setup_manager_instance.output_dir)
            return jsonify({"message":
                                "Configuration files generated successfully.",
                                 "output_path": output_directory_path}), 200

        except Exception as e:
            logging.error(f"Installation process failed: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500

    return flask_app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)