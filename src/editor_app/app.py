import logging
from collections import defaultdict

from flask import Blueprint, Response, current_app, jsonify, render_template, request

editor_bp = Blueprint("editor", __name__, template_folder="templates")


@editor_bp.route("/")
def index():
    """Serve the main editor UI."""
    return render_template("editor.html")


# --- MODIFIED: This function now returns a grouped data structure ---
@editor_bp.route("/api/components", methods=["GET"])
def get_components():
    """
    API endpoint to get all components, structured by their uniqueness_group.
    """
    component_manager = current_app.config["COMPONENT_MANAGER"]
    try:
        all_components = component_manager.get_all_components()

        groups = defaultdict(lambda: {"name": "", "components": []})
        ungrouped = []

        for comp in all_components:
            group_name = comp.get("uniqueness_group")
            component_summary = {"id": comp.get("id"), "name": comp.get("name")}

            if group_name:
                groups[group_name]["name"] = group_name
                groups[group_name]["components"].append(component_summary)
            else:
                ungrouped.append(component_summary)

        # Sort groups by name and components by name within each group
        sorted_groups = sorted(groups.values(), key=lambda g: g["name"])
        for group in sorted_groups:
            group["components"].sort(key=lambda c: c["name"] or c["id"])

        ungrouped.sort(key=lambda c: c["name"] or c["id"])

        return jsonify({"groups": sorted_groups, "ungrouped": ungrouped})

    except Exception as e:
        logging.error(f"Failed to get component list: {e}", exc_info=True)
        return jsonify({"error": "An unexpected server error occurred"}), 500


@editor_bp.route("/api/components/<string:component_id>", methods=["GET", "PUT"])
def component_details(component_id: str):
    """
    Handles GET requests to fetch component details and PUT requests
    to update them.
    """
    component_manager = current_app.config["COMPONENT_MANAGER"]

    if request.method == "PUT":
        try:
            update_data = request.get_json(silent=True)
            if update_data is None:
                return jsonify({"error": "Invalid or missing JSON payload"}), 400

            component_manager.update_component_metadata(component_id, update_data)
            return jsonify({"message": "Component updated successfully"})
        except KeyError:
            return jsonify({"error": "Component not found"}), 404
        except Exception as e:
            logging.error(
                f"Failed to update details for {component_id}: {e}", exc_info=True
            )
            return jsonify({"error": "An unexpected server error occurred"}), 500

    # This is the GET logic
    try:
        details = component_manager.get_component_details(component_id)
        if details:
            details_copy = details.copy()
            details_copy["id"] = component_id
            return jsonify(details_copy)
        else:
            return jsonify({"error": "Component not found"}), 404
    except Exception as e:
        logging.error(f"Failed to get details for {component_id}: {e}", exc_info=True)
        return jsonify({"error": "An unexpected server error occurred"}), 500


@editor_bp.route("/api/components/<string:component_id>/variables", methods=["PUT"])
def update_component_variables(component_id: str):
    """Handles PUT requests to update the variables.json for a component."""
    component_manager = current_app.config["COMPONENT_MANAGER"]
    try:
        variables_data = request.get_json(silent=True)
        if variables_data is None:
            return jsonify({"error": "Invalid JSON payload"}), 400

        component_manager.update_component_variables(component_id, variables_data)
        return jsonify({"message": "Variables updated successfully"})
    except KeyError:
        return jsonify({"error": "Component not found"}), 404
    except Exception as e:
        logging.error(
            f"Failed to update variables for {component_id}: {e}", exc_info=True
        )
        return jsonify({"error": "An unexpected server error occurred"}), 500


@editor_bp.route(
    "/api/components/<string:component_id>/template", methods=["GET", "PUT"]
)
def component_template(component_id: str):
    """
    Handles GET requests to fetch and PUT requests to update the template file.
    """
    component_manager = current_app.config["COMPONENT_MANAGER"]

    if request.method == "PUT":
        try:
            template_content = request.get_data(as_text=True)
            component_manager.update_component_template_content(
                component_id, template_content
            )
            return jsonify({"message": "Template updated successfully"})
        except KeyError:
            return jsonify({"error": "Component not found"}), 404
        except Exception as e:
            logging.error(
                f"Failed to update template for {component_id}: {e}", exc_info=True
            )
            return jsonify({"error": "An unexpected server error occurred"}), 500

    # This is the GET logic
    try:
        content = component_manager.get_component_template_content(component_id)
        return Response(content, mimetype="text/plain")
    except KeyError:
        return jsonify({"error": "Component not found"}), 404
    except Exception as e:
        logging.error(f"Failed to get template for {component_id}: {e}", exc_info=True)
        return jsonify({"error": "An unexpected server error occurred"}), 500
