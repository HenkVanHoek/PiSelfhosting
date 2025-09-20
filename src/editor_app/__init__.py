import logging
import os
from pathlib import Path

from flask import Flask

from ..managers.component_manager import ComponentManager
from .app import editor_bp


def create_app():
    """Create and configure an instance of the Flask application."""
    editor_app = Flask(__name__, template_folder="templates", static_folder="static")

    # Determine the project root directory
    project_root = Path(__file__).parent.parent.parent
    component_templates_dir = project_root / "component_templates"

    # --- FIX: Define the correct path to the metadata file ---
    metadata_file = project_root / "config" / "components_metadata.json"

    # Load secret key from environment
    editor_app.secret_key = os.getenv(
        "SECRET_KEY", "piselfhosting-component-editor-secret-key"
    )

    # --- FIX: Pass both the templates path and the metadata file path ---
    component_manager = ComponentManager(
        templates_path=str(component_templates_dir),
        metadata_file_path=str(metadata_file),
    )

    # Store managers in the app config for access in blueprints
    editor_app.config["COMPONENT_MANAGER"] = component_manager
    logging.info(f"Component Manager initialized with metadata: {metadata_file}")

    # Register blueprints
    editor_app.register_blueprint(editor_bp)
    logging.info("Editor blueprint registered.")

    return editor_app
