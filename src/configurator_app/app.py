# src/configurator_app/app.py
import logging
import threading
import uuid
from datetime import datetime
from pathlib import Path

from appdirs import user_data_dir
from flask import Flask, jsonify, render_template, request

from managers.artifact_generator import ArtifactGenerator

# CQRS and Manager imports
from managers.component_reader import ComponentReader
from managers.deployment_manager import DeploymentManager
from managers.setup_manager import SetupManager
from pi_scanner import PiScanner
from utils.resource_utils import resource_path

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


def map_analysis_to_report_errors(analysis_results: dict):
    """Maps system analysis to structured errors for the UI."""
    errors = []
    ext = analysis_results.get("external_conflicts", {})

    for p in ext.get("ports", []):
        c_type = p.get("conflict_type")
        severity = "Validation:PortConflict"
        if c_type == "EXPECTED_REINSTALLATION":
            severity = "Warning:Port"

        errors.append(
            {
                "type": f"{severity}:{c_type}",
                "summary": f"Port {p['port']} conflict",
                "details": f"Conflict for {p.get('proposed_service', 'unknown')}.",
                "component_id": p.get("proposed_service", "N/A"),
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        )
    return errors


def create_app(test_config=None):
    """Application factory for the Configurator."""
    app = Flask(__name__)
    app.secret_key = "piselfhosting-secret-key"  # nosec

    if test_config:
        app.config.update(test_config)

    # 1. Initialize Paths
    data_dir = Path(user_data_dir("PiSelfhosting", "HenkVanHoek"))
    data_dir.mkdir(parents=True, exist_ok=True)

    meta_file = resource_path("config/components_metadata.json")
    temp_path = resource_path("component_templates")

    # 2. Initialize CQRS Managers
    # Note: We use the Reader where the old ComponentManager was expected.
    reader = ComponentReader(metadata_path=meta_file, templates_path=temp_path)
    generator = ArtifactGenerator(reader=reader)

    deploy_mgr = DeploymentManager(component_manager=reader)
    # Prefixed with underscore to satisfy linter if not yet used in routes
    SetupManager(component_manager=reader, output_dir=data_dir)

    # Fixed: Provided required parameters for PiScanner
    scanner = PiScanner(username="pi", password="pi")  # nosec

    app.deployment_tasks = {}

    @app.route("/")
    def index():
        """Render the main configurator interface."""
        return render_template("index.html")

    @app.route("/api/components", methods=["GET"])
    def get_components():
        """Return all available components from metadata."""
        return jsonify(reader.get_all_components())

    @app.route("/scan-pis", methods=["GET"])
    def scan_pis():
        """Scan the network for Raspberry Pi devices."""
        hosts = scanner.scan()
        return jsonify({"hosts": hosts})

    @app.route("/deploy-configuration", methods=["POST"])
    def deploy_configuration():
        """Handle the deployment request and artifact generation."""
        data = request.get_json() or {}
        analysis = data.get("analysis_results", {})
        errors = map_analysis_to_report_errors(analysis)

        # Check for critical conflicts (Validation: prefix)
        if any(e["type"].startswith("Validation:") for e in errors):
            return (
                jsonify(
                    {
                        "errors": errors,
                        "message": "Critical conflicts must be "
                        "resolved before deployment.",
                    }
                ),
                400,
            )

        # Generate artifacts using the new Generator
        output_path = data_dir / "current_deployment"
        generator.create_artifacts(
            out_path=output_path,
            components=data.get("selected_components", []),
            user_variables=data.get("global_vars", {}),
        )

        task_id = str(uuid.uuid4())
        app.deployment_tasks[task_id] = {
            "status": "running",
            "logs": ["Starting deployment sequence..."],
            "errors": errors,
        }

        # Handle task execution in a separate thread if not testing
        if not app.config.get("TESTING"):
            threading.Thread(
                target=deploy_mgr.start_deployment,
                args=(
                    task_id,
                    app.deployment_tasks,
                    str(output_path),
                    data.get("devices"),
                ),
            ).start()

        return jsonify({"task_id": task_id}), 202

    @app.route("/task-status/<task_id>")
    def task_status(task_id):
        """Return the logs and status of a specific deployment task."""
        return jsonify(app.deployment_tasks.get(task_id, {}))

    return app
