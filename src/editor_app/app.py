# src/editor_app/app.py

import logging
import os

from flask import Flask, abort, jsonify, render_template, request

from managers.component_manager import ComponentManager
from utils.resource_utils import resource_path

logging.basicConfig(level=logging.INFO)


def create_app(test_config=None):
    """Application factory for the Developer Editor."""
    app = Flask(__name__)

    # Crucial for testing: apply the test_config
    if test_config:
        app.config.update(test_config)

    meta_file = str(resource_path("config/components_metadata.json"))
    temp_path = str(resource_path("component_templates"))

    # Initialize the unified ComponentManager
    component_manager = ComponentManager(
        templates_path=temp_path, metadata_file_path=meta_file
    )

    @app.route("/")
    def index():
        return render_template("editor.html")

    @app.route("/api/components", methods=["GET"])
    def list_components():
        all_comps = component_manager.get_all_components()
        # Return mapped by ID dict for loadComponents frontend utility
        return jsonify({comp["id"]: comp for comp in all_comps}), 200

    @app.route("/api/components/<comp_id>", methods=["GET"])
    def get_component(comp_id):
        details = component_manager.get_component_details(comp_id)
        if details:
            return jsonify(details), 200
        abort(404, f"Component '{comp_id}' not found")

    @app.route("/api/components/<comp_id>", methods=["PUT"])
    def update_component(comp_id):
        data = request.get_json() or {}
        try:
            component_manager.update_component_metadata(comp_id, data)
            return jsonify({"status": "updated"}), 200
        except KeyError:
            abort(404, f"Component '{comp_id}' not found")
        except Exception as e:
            logging.error(
                f"Failed to update metadata for {comp_id}: {e}", exc_info=True
            )
            abort(500, "Internal error updating component metadata")

    @app.route("/api/components/<comp_id>/variables", methods=["PUT"])
    def update_vars(comp_id):
        payload = request.get_json() or {}
        if not isinstance(payload, dict):
            abort(400, "Payload must be a dictionary")

        try:
            component_manager.update_component_variables(comp_id, payload)
            return jsonify({"status": "updated"}), 200
        except Exception as e:
            logging.error(f"Failed to save variables for {comp_id}: {e}", exc_info=True)
            abort(500, "Internal error saving component variables")

    @app.route("/api/components", methods=["POST"])
    def add_component():
        data = request.get_json() or {}
        component_id = data.get("id")

        if not component_id or not isinstance(component_id, str):
            abort(400, "A valid Component ID string is required")

        meta = data.get("meta") or {}
        name = meta.get("name", component_id.capitalize())

        try:
            component_manager.create_component(component_id, name)
            if meta:
                component_manager.update_component_metadata(component_id, meta)
            return jsonify({"status": "created"}), 201
        except ValueError:
            abort(409, "Component already exists or invalid ID format")
        except Exception as e:
            logging.error(
                f"Failed to create component {component_id}: {e}", exc_info=True
            )
            abort(500, "Internal error creating component")

    @app.route("/api/components/<comp_id>", methods=["DELETE"])
    def delete_component(comp_id):
        try:
            component_manager.delete_component(comp_id)
            return jsonify({"status": "deleted"}), 200
        except KeyError:
            abort(404, f"Component '{comp_id}' not found")
        except Exception as e:
            logging.error(f"Failed to delete component {comp_id}: {e}", exc_info=True)
            abort(500, "Internal error deleting component")

    @app.route("/api/components/<comp_id>/template", methods=["GET"])
    def get_component_template(comp_id):
        try:
            content = component_manager.get_component_template_content(comp_id)
            return content, 200
        except Exception as e:
            logging.error(f"Failed to read template for {comp_id}: {e}", exc_info=True)
            abort(500, "Internal error reading component template")

    @app.route("/api/components/<comp_id>/template", methods=["PUT"])
    def update_component_template(comp_id):
        try:
            content = request.get_data(as_text=True)
            component_manager.update_component_template_content(comp_id, content)
            return jsonify({"status": "updated"}), 200
        except Exception as e:
            logging.error(f"Failed to save template for {comp_id}: {e}", exc_info=True)
            abort(500, "Internal error saving component template")

    @app.route("/api/components/<comp_id>/validate", methods=["POST"])
    def validate_component(comp_id):
        data = request.get_json() or {}
        template_content = data.get("template_content", "")
        variables = data.get("variables", [])
        try:
            component_manager.validate_component_configuration(
                comp_id, template_content, variables
            )
            return (
                jsonify(
                    {
                        "status": "valid",
                        "message": "Template validation successful!",
                    }
                ),
                200,
            )
        except ValueError as e:
            logging.warning(f"Validation failed for {comp_id}: {e}")
            return jsonify({"error": "Template validation failed"}), 400
        except Exception as e:
            logging.error(
                f"Unexpected validation error for {comp_id}: {e}", exc_info=True
            )
            abort(500, "Unexpected validation error occurred")

    @app.route(
        "/api/components/<comp_id>/validate_metadata_conflicts", methods=["POST"]
    )
    def validate_metadata_conflicts(comp_id):
        data = request.get_json() or {}
        conflicts_list = data.get("conflicts_with", [])
        try:
            component_manager.validate_metadata_conflicts(comp_id, conflicts_list)
            return jsonify({"status": "valid"}), 200
        except ValueError as e:
            logging.warning(f"Metadata conflicts validation failed: {e}")
            return jsonify({"error": "Metadata conflict validation failed"}), 400
        except Exception as e:
            logging.error(
                f"Unexpected validation error for {comp_id}: {e}", exc_info=True
            )
            abort(500, "Unexpected validation error occurred")

    @app.route("/api/components/<comp_id>/group", methods=["PUT"])
    def update_component_group_route(comp_id):
        data = request.get_json() or {}
        new_group = data.get("group")
        if not new_group or not isinstance(new_group, str):
            abort(400, "Group ID is required and must be a string")
        try:
            component_manager.update_component_group(comp_id, new_group)
            return jsonify({"status": "updated"}), 200
        except KeyError:
            abort(404, f"Component '{comp_id}' not found")
        except Exception as e:
            logging.error(f"Failed to update group for {comp_id}: {e}", exc_info=True)
            abort(500, "Internal error updating component group")

    @app.route("/api/components/order", methods=["PUT"])
    def update_components_order_route():
        new_order = request.get_json()
        if not isinstance(new_order, list):
            abort(400, "Payload must be a list of component IDs")
        try:
            component_manager.update_components_order(new_order)
            return jsonify({"status": "updated"}), 200
        except Exception as e:
            logging.error(f"Failed to update components order: {e}", exc_info=True)
            abort(500, "Internal error updating component ordering")

    @app.route("/api/groups/order", methods=["PUT"])
    def update_groups_order_route():
        new_order = request.get_json()
        if not isinstance(new_order, list):
            abort(400, "Payload must be a list of group IDs")
        try:
            component_manager.update_group_order(new_order)
            return jsonify({"status": "updated"}), 200
        except Exception as e:
            logging.error(f"Failed to update groups order: {e}", exc_info=True)
            abort(500, "Internal error updating groups order")

    @app.route("/api/groups/<group_id>/rename", methods=["PUT"])
    def rename_group_route(group_id):
        data = request.get_json() or {}
        new_name = data.get("name")
        if not new_name or not isinstance(new_name, str):
            abort(400, "New name is required and must be a string")
        try:
            component_manager.rename_group(group_id, new_name)
            return jsonify({"status": "updated"}), 200
        except ValueError:
            abort(404, "Group not found or rename failed")
        except Exception as e:
            logging.error(f"Failed to rename group {group_id}: {e}", exc_info=True)
            abort(500, "Internal error renaming group")

    @app.route("/api/groups/<group_id>", methods=["DELETE"])
    def delete_group_route(group_id):
        try:
            component_manager.delete_group(group_id)
            return jsonify({"status": "deleted"}), 200
        except ValueError:
            abort(400, "Failed to delete group")
        except Exception as e:
            logging.error(f"Failed to delete group {group_id}: {e}", exc_info=True)
            abort(500, "Internal error deleting group")

    @app.route("/api/groups", methods=["GET"])
    def list_groups():
        try:
            meta = component_manager.get_piselfhosting_meta()
            group_rules = meta.get("group_rules", {})
            return jsonify(group_rules), 200
        except Exception as e:
            logging.error(f"Failed to list groups: {e}", exc_info=True)
            abort(500, "Internal error listing groups")

    # --- NEW PACKAGE ROUTES ---
    @app.route("/api/packages", methods=["GET"])
    def list_packages():
        return jsonify(component_manager.get_all_packages()), 200

    @app.route("/api/packages/<pkg_id>", methods=["PUT"])
    def update_package(pkg_id):
        data = request.get_json() or {}
        raw_name = data.get("name")
        name = str(raw_name) if raw_name else pkg_id.capitalize()
        try:
            packages = component_manager.get_all_packages()
            if pkg_id not in packages:
                component_manager.create_package(pkg_id, name)
            component_manager.update_package_metadata(pkg_id, data)
            return jsonify({"status": "updated"}), 200
        except Exception as e:
            logging.error(f"Failed to update package {pkg_id}: {e}", exc_info=True)
            abort(400, "Failed to update package metadata")

    @app.route("/api/packages/<pkg_id>", methods=["DELETE"])
    def delete_package(pkg_id):
        try:
            component_manager.delete_package(pkg_id)
            return jsonify({"status": "deleted"}), 200
        except ValueError:
            abort(400, "Failed to delete package")
        except Exception as e:
            logging.error(f"Failed to delete package {pkg_id}: {e}", exc_info=True)
            abort(500, "Internal error deleting package")

    @app.route("/api/generate_auth_hash", methods=["POST"])
    def generate_auth_hash():
        data = request.get_json() or {}
        username = data.get("username")
        password = data.get("password")
        if (
            not username
            or not password
            or not isinstance(username, str)
            or not isinstance(password, str)
        ):
            abort(400, "Username and password are required and must be strings")

        try:
            import bcrypt

            # Htpasswd BCrypt string formatting
            hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
            hashed_str = f"{username}:{hashed.decode('utf-8')}"
        except ImportError:
            # Safe htpasswd fallback with standard hashlib SHA-1
            import base64
            import hashlib

            sha1_hash = hashlib.sha1(password.encode("utf-8")).digest()  # nosec B324
            hashed_str = (
                f"{username}:{{SHA}}" f"{base64.b64encode(sha1_hash).decode('utf-8')}"
            )

        return jsonify({"hashed_user_string": hashed_str}), 200

    return app


if __name__ == "__main__":
    editor_app = create_app()
    debug_mode = os.environ.get("FLASK_DEBUG", "False").lower() in ("true", "1")
    editor_app.run(host="0.0.0.0", port=5000, debug=debug_mode)  # nosec B104
