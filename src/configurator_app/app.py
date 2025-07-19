import logging
import os

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

from managers.component_manager import ComponentManager
from managers.setup_manager import SetupManager
from pi_scanner import PiScanner
from utils.resource_utils import resource_path

# import sys

# --- Basic Flask App Setup ---
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

# --- App Dependencies Initialization ---
# Use the robust resource_path function to locate the metadata file.
metadata_path = resource_path(os.path.join("config", "components_metadata.json"))

# Initialize managers that will be used by the app.
component_manager = ComponentManager(metadata_file=metadata_path)
setup_manager = SetupManager(component_manager)


def create_app(
    component_manager_instance=component_manager,
    setup_manager_instance=setup_manager,
):
    """
    Factory function to create the Flask application.
    This allows for dependency injection, which is great for testing.
    """
    # Use a different name internally to avoid shadowing the module-level 'app'
    flask_app = Flask(__name__)

    import os

    logging.info(f"Current working directory: {os.getcwd()}")
    logging.info(f"Application root path: {flask_app.root_path}")
    logging.info(
        f"Template folder path: {os.path.join(flask_app.root_path, 'templates')}"
    )

    flask_app.secret_key = os.environ.get(
        "FLASK_SECRET_KEY", "a-default-secret-key-for-development"
    )

    # --- Routes ---
    @flask_app.route("/", methods=["GET", "POST"])
    def index():
        if request.method == "POST":
            selected_components = request.form.getlist("selected_components")
            env_vars = {}
            if not selected_components:
                flash("Please select at least one component.", "warning")
                return redirect(url_for("index"))
            try:
                setup_manager_instance.generate_all_files(selected_components, env_vars)
                flash("Configuration files generated successfully!", "success")
            except Exception as e:
                flash(f"Error generating files: {e}", "danger")
            return redirect(url_for("index"))
        all_components = component_manager_instance.get_all_components()
        uniqueness_groups = component_manager_instance.get_uniqueness_groups()
        default_components = [
            comp_id
            for comp_id, comp_data in all_components.items()
            if comp_data.get("default", False)
        ]
        target_ip = session.get("target_ip")
        return render_template(
            "index.html",
            components=all_components,
            uniqueness_groups=uniqueness_groups,
            default_components=default_components,
            target_ip=target_ip,
        )

    @flask_app.route("/scan-pis", methods=["POST"])
    def scan_pis():
        data = request.get_json()
        subnet = data.get("subnet")
        username = data.get("username")
        password = data.get("password")
        if not all([subnet, username, password]):
            return jsonify({"error": "Missing scan parameters"}), 400
        try:
            scanner = PiScanner(username=username, password=password)
            pis = scanner.scan(subnet=subnet)
            return jsonify(pis)
        except Exception as e:
            logging.error(f"Pi scanning failed: {e}")
            return jsonify({"error": str(e)}), 500

    @flask_app.route("/set-ip", methods=["POST"])
    def set_ip_address():
        data = request.get_json()
        ip = data.get("ip")
        if not ip:
            return jsonify({"error": "No IP address provided"}), 400
        session["target_ip"] = ip
        return jsonify({"message": "IP address set successfully"}), 200

    return flask_app


# Create the application instance using the factory.
app = create_app()

# This block is for development only. Flask will now use the DEBUG
# configuration that was set inside the create_app factory.
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
