# src/config_webapp.py
import logging
import os
from collections import defaultdict
from logging.handlers import RotatingFileHandler

from flask import (
    Flask,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from jinja2 import TemplateNotFound
from werkzeug.utils import secure_filename

from src.component_manager import ComponentManager
from src.pi_scanner import PiScanner
from src.setup_manager import SetupManager
from src.utils.ssh_utils import set_key

# Determine the absolute path to the project root
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def create_app(component_manager=None, scanner=None, setup_manager=None, testing=False):
    """
    Factory function to create the Flask application.
    This allows for different configurations, especially for testing.
    """
    app = Flask(
        __name__,
        template_folder=os.path.join(project_root, "configurator_app", "templates"),
        static_folder=os.path.join(project_root, "configurator_app", "static"),
    )

    # Configure the app for testing if the 'testing' flag is True
    app.config["TESTING"] = testing

    # --- Basic App Configuration ---
    app.config["SECRET_KEY"] = os.environ.get(
        "FLASK_SECRET_KEY", "a-default-secret-key-for-development"
    )
    app.config["UPLOAD_FOLDER"] = os.path.join(project_root, "uploads")
    app.config["ENV_PATH"] = os.path.join(project_root, ".env")
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    # --- Logging Configuration ---
    # Only configure logging handlers if not in testing mode to avoid clutter
    if not testing:
        log_dir = os.path.join(project_root, "logs")
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, "app.log")

        # Keep the log file size to 1MB, with 3 backup files
        file_handler = RotatingFileHandler(
            log_file, maxBytes=1024 * 1024, backupCount=3
        )
        file_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]"
            )
        )
        app.logger.addHandler(file_handler)
        app.logger.setLevel(logging.INFO)

    # --- Dependency Injection ---
    # Use provided instances or create new ones. This is key for testing.
    if component_manager is None:
        metadata_path = os.path.join(project_root, "src", "components_metadata.json")
        component_manager = ComponentManager(metadata_path)

    if scanner is None:
        scanner = PiScanner  # Use the class, not an instance

    if setup_manager is None:
        setup_manager = SetupManager(component_manager)

    # --- Route Definitions ---
    @app.route("/")
    def index():
        target_pi_ip = session.get("target_pi_ip")

        try:
            if not target_pi_ip:
                # If no IP is in the session, show the Pi selection page
                subnet = scanner.detect_subnet()
                return render_template("select_pi.html", subnet=subnet)
            else:
                # If an IP is in the session, show the component selection page
                all_components = component_manager.get_all_components()
                uniqueness_groups = component_manager.get_uniqueness_groups()

                # Group components by their 'dashy_section' for display
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

                return render_template(
                    "select_components.html",
                    grouped_components=dict(grouped_components),
                    uniqueness_groups=uniqueness_groups,
                    target_pi_ip=target_pi_ip,
                )
        except TemplateNotFound:
            app.logger.error(
                "Template 'select_pi.html' or 'select_components.html' not found."
            )
            return (
                "A required template was not found. Please check the installation.",
                500,
            )
        except Exception as e:
            app.logger.error(f"An unexpected error occurred: {e}")
            return "An unexpected error occurred on the server.", 500

    @app.route("/live-log")
    def live_log():
        """Placeholder for the live log page to allow URL building."""
        # This template can be very basic for now.
        return render_template("live_log.html")

    @app.route("/scan", methods=["POST"])
    def scan_network():
        data = request.get_json()
        subnet = data.get("subnet")
        username = data.get("username")
        password = data.get("password")

        if not subnet:
            return jsonify({"error": "Subnet is required."}), 400

        # Run the scan to find Pis
        found_pis, _, err = scanner.scan(subnet)

        if err:
            app.logger.error(f"Nmap scan failed: {err}")
            return jsonify({"error": err}), 500

        # For each found Pi, try to get more details
        detailed_pis = []
        scanner_instance = scanner(username, password)
        for pi in found_pis:
            details = scanner_instance.get_device_details(pi["ip"])
            pi_with_details = pi.copy()
            pi_with_details["details"] = details if details else "No details"
            detailed_pis.append(pi_with_details)

        return jsonify({"pis": detailed_pis})

    @app.route("/get-details", methods=["POST"])
    def get_details_for_ip():
        data = request.get_json()
        ip = data.get("ip")
        username = data.get("username")
        password = data.get("password")

        if not all([ip, username]):
            return jsonify({"error": "IP and username are required."}), 400

        # Create a scanner instance and get details
        scanner_instance = scanner(username, password)
        details = scanner_instance.get_device_details(ip)

        if details:
            return jsonify(details)
        else:
            return jsonify({"error": "Failed to get details for the Pi."}), 500

    @app.route("/set-ip", methods=["POST"])
    def set_ip_address():
        data = request.get_json()
        ip = data.get("ip")
        if not ip:
            return jsonify({"error": "IP address is required"}), 400
        session["target_pi_ip"] = ip
        return jsonify({"message": "IP address set successfully"})

    @app.route("/save-and-install", methods=["POST"])
    def save_and_install():
        if "target_pi_ip" not in session:
            flash("Your session has expired. Please select a Pi again.")
            return redirect(url_for("index"))

        # Extract data from the form
        selected_components = request.form.getlist("components")
        if not selected_components:
            return "At least one component must be selected.", 400

        env_vars = {
            key.replace("env_", ""): value
            for key, value in request.form.items()
            if key.startswith("env_")
        }
        ssh_user = request.form.get("ssh_user")
        ssh_pass = request.form.get("ssh_pass")

        # Save SSH credentials to .env file
        try:
            set_key(app.config["ENV_PATH"], "SSH_USER", ssh_user)
            set_key(app.config["ENV_PATH"], "SSH_PASSWORD", ssh_pass)
        except Exception as e:
            app.logger.error(f"Failed to save .env file: {e}")
            return "Failed to save credentials.", 500

        # Generate docker-compose.yml and other files
        setup_manager.generate_all_files(selected_components, env_vars)

        return render_template(
            "install_success.html",
            target_pi_ip=session["target_pi_ip"],
            ssh_user=ssh_user,
        )

    @app.route("/upload-key", methods=["POST"])
    def upload_key():
        if "ssh_key" not in request.files:
            flash("No file part in the request.")
            return redirect(request.url)

        file = request.files["ssh_key"]
        if file.filename == "":
            flash("No selected file.")
            return redirect(request.url)

        if file:
            filename = secure_filename(file.filename)
            # You might want to save it to a more secure, non-web-accessible location
            file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
            flash("Key uploaded successfully.")
            # Here you would typically add logic to use this key.
            # For now, we just confirm the upload.

        return redirect(url_for("index"))

    @app.route("/generate-docs", methods=["POST"])
    def generate_docs_endpoint():
        try:
            component_manager.generate_docs()
            flash("Documentation generated successfully!", "success")
        except Exception as e:
            app.logger.error(f"Error generating documentation: {e}")
            flash(f"Error generating documentation: {e}", "error")
        return redirect(url_for("index"))

    return app


# To run this app for development:
# flask --app config_webapp:create_app run
if __name__ == "__main__":
    flask_app = create_app()
    flask_app.run(debug=True, port=5001)
