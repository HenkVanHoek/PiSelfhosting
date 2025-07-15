import json
import logging
import os
import sys
from collections import defaultdict

from dotenv import set_key
from flask import (
    Flask,
    Response,
    jsonify,
    render_template,
    request,
    session,
    stream_with_context,
)

# Ensure the src directory is in the path for module imports
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(project_root, "src"))

import piselfhosting_installer  # noqa: E402
from component_manager import ComponentManager  # noqa: E402
from pi_scanner import PiScanner  # noqa: E402


def create_app(test_config=None):
    """Application Factory Function"""
    app = Flask(__name__)
    app.secret_key = os.urandom(24)

    # Configure logging
    if not app.debug or os.environ.get("FLASK_ENV") == "production":
        # In production, log to a file or a logging service
        # For simplicity, we'll still log to the console but at a higher level
        logging.basicConfig(
            level=logging.INFO, format="%(asctime)s %(levelname)s:%(name)s:%(message)s"
        )

    app.logger.info("Flask application starting up...")

    # --- Configuration ---
    app.config.from_mapping(
        METADATA_FILE=os.path.join(project_root, "config", "components_metadata.json"),
        DEFAULT_COMPONENTS_FILE=os.path.join(
            project_root, "config", "default_selected_components.txt"
        ),
        SELECTED_COMPONENTS_OUTPUT_FILE=os.path.join(
            project_root, "selected_components.txt"
        ),
        DOCS_OUTPUT_FILE=os.path.join(project_root, "SUPPORTED_COMPONENTS.md"),
        ENV_PATH=os.path.join(project_root, ".env"),
    )
    if test_config:
        app.config.from_mapping(test_config)

    manager = ComponentManager(
        app.config["METADATA_FILE"], docs_output_path=app.config["DOCS_OUTPUT_FILE"]
    )

    @app.route("/")
    def index():
        try:
            if "target_pi_ip" in session:
                all_components = manager.get_all_components()
                uniqueness_groups = manager.get_uniqueness_groups()
                grouped_components = defaultdict(list)
                order = all_components.get("_piselfhosting", {}).get(
                    "components_order", []
                )

                for component_id in order:
                    component_data = all_components.get(component_id)
                    if component_data:
                        section_name = component_data.get(
                            "dashy_section", "Uncategorized"
                        )
                        grouped_components[section_name].append(
                            {"id": component_id, "data": component_data}
                        )

                default_components = []
                try:
                    with open(app.config["DEFAULT_COMPONENTS_FILE"], "r") as f:
                        default_components = f.read().strip().split()
                except FileNotFoundError:
                    app.logger.warning(
                        f"Default components file not found at "
                        f"{app.config['DEFAULT_COMPONENTS_FILE']}. "
                        f"No components will be pre-selected."
                    )

                return render_template(
                    "select_components.html",
                    grouped_components=grouped_components,
                    pi_ip=session["target_pi_ip"],
                    uniqueness_groups=json.dumps(uniqueness_groups),
                    default_components=default_components,
                )
            else:
                detected_subnet = PiScanner.detect_subnet()
                return render_template(
                    "select_pi.html", detected_subnet=detected_subnet
                )
        except Exception:
            app.logger.error(
                "An unhandled exception occurred in the index route!", exc_info=True
            )
            raise

    @app.route("/scan", methods=["POST"])
    def scan_network():
        data = request.get_json()
        subnet = data.get("subnet")
        username = data.get("username")
        password = data.get("password")

        if not subnet or not username:
            return jsonify({"error": "Subnet and username are required."}), 400

        found_pis, stdout, stderr = PiScanner.scan(subnet=subnet)
        successful_details = {}

        for pi in found_pis:
            details = PiScanner.get_device_details(pi["ip"], username, password)
            if details and "serial" in details:
                # Use serial as a unique key for the device
                successful_details[details["serial"]] = {"ip": pi["ip"], **details}

        return jsonify(
            {
                "success": successful_details,
                "debug": {"stdout": stdout, "stderr": stderr},
            }
        )

    @app.route("/get-details", methods=["POST"])
    def get_details_for_ip():
        data = request.get_json()
        ip = data.get("ip")
        username = data.get("username")
        password = data.get("password")

        if not all([ip, username]):
            return jsonify({"error": "IP and username are required."}), 400

        details = PiScanner.get_device_details(ip, username, password)
        if details and "serial" in details:
            return jsonify({"success": {details["serial"]: {"ip": ip, **details}}})
        else:
            return jsonify({"error": f"Could not retrieve details for {ip}."}), 500

    @app.route("/select-pi", methods=["POST"])
    def select_pi():
        session["target_pi_ip"] = request.form.get("pi_ip")
        return {"status": "ok"}

    @app.route("/save-and-install", methods=["POST"])
    def save_and_install():
        if "target_pi_ip" not in session:
            return "Pi IP not set", 400

        selected_components = request.form.getlist("components")
        ssh_user = request.form.get("ssh_user")
        ssh_pass = request.form.get("ssh_pass")

        # Save selected components to a file
        output_file = app.config["SELECTED_COMPONENTS_OUTPUT_FILE"]
        with open(output_file, "w") as f:
            f.write(" ".join(selected_components))

        # Save credentials and IP to .env file
        env_path = app.config["ENV_PATH"]
        set_key(env_path, "PI_IP", session["target_pi_ip"])
        set_key(env_path, "SSH_USER", ssh_user)
        set_key(env_path, "SSH_PASSWORD", ssh_pass if ssh_pass else "")

        return render_template("install_success.html")

    @app.route("/install-stream")
    def install_stream():
        def generate():
            try:
                # --- FIX: The module is now imported at the top level ---
                for line in piselfhosting_installer.run_installation():
                    yield f"data: {line}\n\n"
                yield "data: --- SCRIPT FINISHED ---\n\n"
            except Exception as e:
                # Log the full traceback to the server console
                app.logger.error("Error during installation stream", exc_info=True)
                # Send a simplified error message to the client
                yield f"data: FATAL ERROR in web app: {e}\n\n"
                yield "data: --- SCRIPT FINISHED ---\n\n"

        return Response(stream_with_context(generate()), mimetype="text/event-stream")

    @app.route("/generate-docs")
    def generate_docs():
        manager.generate_docs()
        return "Documentation generated successfully!"

    return app


if __name__ == "__main__":
    new_app = create_app()
    new_app.run(debug=True, port=5001)
