import os
import sys

# --- Path Correction ---
# This block must run before any imports that depend on the project's root path.
# We modify sys.path to ensure that the 'src' module can be found, especially
# when the app is bundled as an executable.
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import json  # noqa: E402
import logging  # noqa: E402
from collections import defaultdict  # noqa: E402

from dotenv import set_key  # noqa: E402
from flask import (  # noqa: E402
    Flask,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from src.component_manager import ComponentManager  # noqa: E402
from src.pi_scanner import PiScanner  # noqa: E402


def create_app(test_config=None, component_manager=None):
    """Application Factory Function."""
    app = Flask(__name__)
    app.secret_key = os.urandom(24)

    # Configure logging
    if not app.debug or os.environ.get("FLASK_ENV") == "production":
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

    # FIX 1: Attach the manager to the app context.
    # This is a cleaner way to manage dependencies and resolves the linter warning.
    if component_manager:
        app.manager = component_manager
    else:
        app.manager = ComponentManager(
            app.config["METADATA_FILE"], docs_output_path=app.config["DOCS_OUTPUT_FILE"]
        )

    # --- Routes ---

    @app.route("/")
    def index():
        """
        Displays the component selection page if a Pi is selected,
        otherwise shows the Pi discovery page.
        """
        try:
            if "target_pi_ip" in session:
                # FIX 2: Use app.manager to access the component manager.
                all_components = app.manager.get_all_components()
                uniqueness_groups = app.manager.get_uniqueness_groups()
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
                        "Default components file not found. No components will be "
                        "pre-selected."
                    )

                return render_template(
                    "select_components.html",
                    grouped_components=grouped_components,
                    pi_ip=session["target_pi_ip"],
                    uniqueness_groups=json.dumps(uniqueness_groups),
                    default_components=default_components,
                )
            else:
                # If no IP is in the session, show the Pi selection page.
                subnet = PiScanner.detect_subnet()
                return render_template("select_pi.html", subnet=subnet)
        except Exception as e:
            app.logger.error(f"Error on index page: {e}", exc_info=True)
            return "An internal error occurred.", 500

    @app.route("/scan", methods=["POST"])
    def scan_network():
        """Scans the network for Raspberry Pi devices."""
        data = request.get_json()
        subnet = data.get("subnet")
        username = data.get("username")
        password = data.get("password")

        found_pis, stdout, stderr = PiScanner.scan(subnet)
        if stderr:
            app.logger.error(f"Nmap scan error: {stderr}")
            return jsonify({"error": f"Scan failed: {stderr}"}), 500

        detailed_pis = []
        scanner = PiScanner(username, password)
        for pi in found_pis:
            details = scanner.get_device_details(pi["ip"])
            pi_with_details = pi.copy()
            pi_with_details["details"] = details
            detailed_pis.append(pi_with_details)

        return jsonify({"pis": detailed_pis, "stdout": stdout, "stderr": stderr})

    @app.route("/get-details", methods=["POST"])
    def get_details_for_ip():
        """Gets hardware details for a specific IP address."""
        data = request.get_json()
        scanner = PiScanner(data.get("username"), data.get("password"))
        details = scanner.get_device_details(data.get("ip"))
        if details:
            return jsonify(details)
        else:
            return (
                jsonify({"error": "Failed to get details for the specified IP."}),
                500,
            )

    @app.route("/set-ip", methods=["POST"])
    def set_ip_address():
        """Saves the selected Raspberry Pi IP address to the session."""
        data = request.get_json()
        ip = data.get("ip")
        if not ip:
            return jsonify({"error": "IP address is required"}), 400
        session["target_pi_ip"] = ip
        return jsonify({"message": "IP address set successfully"})

    @app.route("/save-and-install", methods=["POST"])
    def save_and_install():
        """Saves selected components and credentials."""
        if "target_pi_ip" not in session:
            flash("Please select a Raspberry Pi first.", "warning")
            return redirect(url_for("index"))

        components = request.form.getlist("components")
        if not components:
            return "At least one component must be selected", 400

        # Save the list of selected components to a file
        output_file = app.config["SELECTED_COMPONENTS_OUTPUT_FILE"]
        with open(output_file, "w") as f:
            f.write(" ".join(components))
        app.logger.info(f"Selected components saved to {output_file}")

        # Save credentials to the .env file
        env_path = app.config["ENV_PATH"]
        ssh_user = request.form.get("ssh_user")
        ssh_pass = request.form.get("ssh_pass")
        set_key(env_path, "SSH_USER", ssh_user)
        set_key(env_path, "SSH_PASSWORD", ssh_pass)
        app.logger.info(f"Credentials saved to {env_path}")

        return render_template(
            "install_success.html",
            pi_ip=session["target_pi_ip"],
            components=components,
        )

    @app.route("/generate-docs", methods=["POST"])
    def generate_docs():
        """Endpoint to trigger documentation generation."""
        # Use app.manager to access the component manager
        app.manager.generate_docs()
        flash("Documentation generated successfully!", "success")
        # To prevent errors in tests, redirect to a known-good page
        return redirect(url_for("index"))

    # FIX 3: Ensure the factory function always returns the app instance.
    return app
