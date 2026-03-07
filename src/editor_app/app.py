# src/editor_app/app.py
import logging

from flask import Flask, abort, jsonify, render_template, request

from managers.component_reader import ComponentReader
from managers.component_writer import ComponentWriter
from utils.resource_utils import resource_path

logging.basicConfig(level=logging.INFO)


def create_app(test_config=None):
    """Application factory for the Developer Editor."""
    app = Flask(__name__)

    # Crucial for testing: apply the test_config (which contains TESTING=True)
    if test_config:
        app.config.update(test_config)

    meta_file = resource_path("config/components_metadata.json")
    temp_path = resource_path("component_templates")

    # Initialize CQRS Managers
    reader = ComponentReader(metadata_path=meta_file, templates_path=temp_path)
    writer = ComponentWriter(metadata_path=meta_file, templates_path=temp_path)

    @app.route("/")
    def index():
        return render_template("editor.html")

    @app.route("/api/components", methods=["GET"])
    def list_components():
        return jsonify(reader.get_all_components())

    @app.route("/api/components/<comp_id>/variables", methods=["PUT"])
    def update_vars(comp_id):
        new_vars = request.get_json()
        if not isinstance(new_vars, list):
            abort(400, "Payload must be a list")

        if writer.update_component_variables(comp_id, new_vars):
            return jsonify({"status": "updated"}), 200
        abort(500, "Failed to save variables")

    @app.route("/api/components", methods=["POST"])
    def add_component():
        data = request.get_json() or {}
        if writer.create_component_skeleton(data.get("id"), data.get("meta")):
            return jsonify({"status": "created"}), 201
        abort(409, "Component already exists")

    return app
