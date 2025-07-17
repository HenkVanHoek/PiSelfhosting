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

# Updated imports
from pi_scanner import PiScanner
from utils.resource_utils import resource_path

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
    flask_app.secret_key = os.environ.get(
        "FLASK_SECRET_KEY", "a-default-secret-key-for-development"
    )

    # --- Routes ---
    @flask_app.route("/", methods=["GET", "POST"])
    def index():
        if request.method == "POST":
            # Handle form submission for generating files
            selected_components = request.form.getlist("selected_components")
            env_vars = {}  # Placeholder for future environment variable handling

            if not selected_components:
                flash("Please select at least one component.", "warning")
                return redirect(url_for("index"))

            try:
                setup_manager_instance.generate_all_files(selected_components, env_vars)
                flash("Configuration files generated successfully!", "success")
            except Exception as e:
                flash(f"Error generating files: {e}", "danger")

            return redirect(url_for("index"))

        # For a GET request, render the main page
        all_components = component_manager_instance.get_all_components()
        uniqueness_groups = component_manager_instance.get_uniqueness_groups()
        # Get a list of component IDs that should be selected by default
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
        """AJAX endpoint to scan for Raspberry Pis on the network."""
        data = request.get_json()
        subnet = data.get("subnet")
        username = data.get("username")
        password = data.get("password")

        if not all([subnet, username, password]):
            return jsonify({"error": "Missing scan parameters"}), 400

        try:
            # Create a scanner instance with the credentials provided by the user.
            scanner = PiScanner(username=username, password=password)
            pis = scanner.scan(subnet=subnet)
            return jsonify(pis)
        except Exception as e:
            logging.error(f"Pi scanning failed: {e}")
            return jsonify({"error": str(e)}), 500

    @flask_app.route("/set-ip", methods=["POST"])
    def set_ip_address():
        """AJAX endpoint to store the selected Pi's IP address in the session."""
        data = request.get_json()
        ip = data.get("ip")
        if not ip:
            return jsonify({"error": "No IP address provided"}), 400

        session["target_ip"] = ip
        return jsonify({"message": "IP address set successfully"}), 200

    return flask_app


# Create the Flask app instance using the factory.
# This is the single 'app' instance that will be run or imported by a WSGI server.
app = create_app()

# --- Main Execution ---
if __name__ == "__main__":
    # Run the app directly for development.
    # For production, a WSGI server like Gunicorn would import the 'app' object.
    app.run(debug=True, host="0.0.0.0")
