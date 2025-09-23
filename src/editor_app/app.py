import logging
from collections import defaultdict

from flask import Blueprint, Response, current_app, jsonify, render_template, request

editor_bp = Blueprint(
    "editor", __name__, template_folder="templates", static_folder="static"
)


@editor_bp.route("/")
def index():
    return render_template("editor.html")


def _sort_components(components, order_list):
    order_map = {comp_id: i for i, comp_id in enumerate(order_list)}
    ordered = [c for c in components if c["id"] in order_map]
    unordered = [c for c in components if c["id"] not in order_map]
    ordered.sort(key=lambda c: order_map[c["id"]])
    unordered.sort(key=lambda c: c.get("name") or c.get("id"))
    return ordered + unordered


@editor_bp.route("/api/components", methods=["GET", "POST"])
def get_or_create_components():
    component_manager = current_app.config["COMPONENT_MANAGER"]
    if request.method == "POST":
        try:
            data = request.get_json()
            comp_id = data.get("id")
            comp_name = data.get("name")
            if not comp_id or not comp_name:
                return jsonify({"error": "Component ID and Name are required"}), 400
            component_manager.create_component(comp_id, comp_name)
            return (
                jsonify({"message": f"Component '{comp_name}' created successfully"}),
                201,
            )
        except ValueError as e:
            return jsonify({"error": str(e)}), 409
        except Exception as e:
            logging.error(f"Failed to create component: {e}", exc_info=True)
            return jsonify({"error": "An unexpected server error occurred"}), 500
    # GET logic
    try:
        all_components = component_manager.get_all_components()
        meta = component_manager.get_piselfhosting_meta()
        default_group_id = meta.get("default_group", "general")
        group_order = meta.get("group_order", [])
        components_order = meta.get("components_order", [])
        group_rules = meta.get("group_rules", {})
        groups_map = defaultdict(lambda: {"components": []})
        for comp in all_components:
            group_id = comp.get("group") or default_group_id
            groups_map[group_id]["components"].append(
                {"id": comp.get("id"), "name": comp.get("name")}
            )
        sorted_groups = []
        for group_id in group_order:
            if group_id in groups_map:
                rule = group_rules.get(group_id, {})
                sorted_groups.append(
                    {
                        "id": group_id,
                        "name": rule.get("name", group_id.replace("_", " ").title()),
                        "is_exclusive": rule.get("is_exclusive", False),
                        "components": _sort_components(
                            groups_map.pop(group_id)["components"], components_order
                        ),
                    }
                )
        for group_id, data in sorted(groups_map.items()):
            rule = group_rules.get(group_id, {})
            sorted_groups.append(
                {
                    "id": group_id,
                    "name": rule.get("name", group_id.replace("_", " ").title()),
                    "is_exclusive": rule.get("is_exclusive", False),
                    "components": _sort_components(
                        data["components"], components_order
                    ),
                }
            )
        return jsonify({"groups": sorted_groups})
    except Exception as e:
        logging.error(f"Failed to get component list: {e}", exc_info=True)
        return jsonify({"error": "An unexpected server error occurred"}), 500


# --- DEFINITIVE FIX: Add the new validation endpoint ---
@editor_bp.route("/api/components/<string:component_id>/validate", methods=["POST"])
def validate_component_configuration(component_id: str):
    """API endpoint to validate a component's configuration."""
    component_manager = current_app.config["COMPONENT_MANAGER"]
    try:
        data = request.get_json(silent=True)
        if not data:
            return jsonify({"error": "Invalid or missing JSON payload"}), 400

        template_content = data.get("template_content", "")
        variables = data.get("variables", [])

        component_manager.validate_component_configuration(
            component_id, template_content, variables
        )
        return jsonify({"message": "Validation successful!"})
    except ValueError as e:
        # This catches validation rule failures and returns them as a user error.
        return jsonify({"error": f"Validation Failed: {e}"}), 400
    except Exception as e:
        logging.error(
            f"Failed to validate component {component_id}: {e}", exc_info=True
        )
        return jsonify({"error": "An unexpected server error occurred"}), 500


@editor_bp.route("/api/groups/<string:group_id>", methods=["DELETE"])
def delete_group(group_id: str):
    component_manager = current_app.config["COMPONENT_MANAGER"]
    try:
        component_manager.delete_group(group_id)
        return jsonify({"message": f"Group '{group_id}' deleted successfully"})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logging.error(f"Failed to delete group {group_id}: {e}", exc_info=True)
        return jsonify({"error": "An unexpected server error occurred"}), 500


@editor_bp.route("/api/groups/order", methods=["PUT"])
def update_group_order():
    component_manager = current_app.config["COMPONENT_MANAGER"]
    try:
        new_order = request.get_json()
        if not isinstance(new_order, list):
            return jsonify({"error": "Invalid payload"}), 400
        component_manager.update_group_order(new_order)
        return jsonify({"message": "Group order updated successfully"})
    except Exception as e:
        logging.error(f"Failed to update group order: {e}", exc_info=True)
        return jsonify({"error": "An unexpected server error occurred"}), 500


@editor_bp.route("/api/components/order", methods=["PUT"])
def update_components_order():
    component_manager = current_app.config["COMPONENT_MANAGER"]
    try:
        new_order = request.get_json()
        if not isinstance(new_order, list):
            return jsonify({"error": "Invalid payload"}), 400
        component_manager.update_components_order(new_order)
        return jsonify({"message": "Component order updated successfully"})
    except Exception as e:
        logging.error(f"Failed to update component order: {e}", exc_info=True)
        return jsonify({"error": "An unexpected server error occurred"}), 500


@editor_bp.route("/api/components/<string:component_id>/group", methods=["PUT"])
def update_component_group(component_id: str):
    component_manager = current_app.config["COMPONENT_MANAGER"]
    try:
        data = request.get_json()
        new_group_id = data.get("group")
        if not new_group_id:
            return jsonify({"error": "Missing 'group' in payload"}), 400
        component_manager.update_component_group(component_id, new_group_id)
        return jsonify(
            {"message": f"Component '{component_id}' moved to group '{new_group_id}'"}
        )
    except KeyError:
        return jsonify({"error": "Component not found"}), 404
    except Exception as e:
        logging.error(
            f"Failed to update component group for {component_id}: {e}", exc_info=True
        )
        return jsonify({"error": "An unexpected server error occurred"}), 500


@editor_bp.route(
    "/api/components/<string:component_id>", methods=["GET", "PUT", "DELETE"]
)
def component_details(component_id: str):
    component_manager = current_app.config["COMPONENT_MANAGER"]
    if request.method == "PUT":
        try:
            update_data = request.get_json(silent=True)
            if update_data is None:
                return jsonify({"error": "Invalid payload"}), 400
            component_manager.update_component_metadata(component_id, update_data)
            return jsonify({"message": "Component updated successfully"})
        except KeyError:
            return jsonify({"error": "Component not found"}), 404
        except Exception as e:
            logging.error(
                f"Failed to update details for {component_id}: {e}", exc_info=True
            )
            return jsonify({"error": "An unexpected server error occurred"}), 500
    elif request.method == "DELETE":
        try:
            component_manager.delete_component(component_id)
            return jsonify(
                {"message": f"Component '{component_id}' deleted successfully"}
            )
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        except KeyError:
            return jsonify({"error": "Component not found"}), 404
        except Exception as e:
            logging.error(
                f"Failed to delete component {component_id}: {e}", exc_info=True
            )
            return jsonify({"error": "An unexpected server error occurred"}), 500
    else:  # GET logic
        try:
            details = component_manager.get_component_details(component_id)
            if details:
                details_copy = details.copy()
                details_copy["id"] = component_id
                return jsonify(details_copy)
            else:
                return jsonify({"error": "Component not found"}), 404
        except Exception as e:
            logging.error(
                f"Failed to get details for {component_id}: {e}", exc_info=True
            )
            return jsonify({"error": "An unexpected server error occurred"}), 500


@editor_bp.route("/api/components/<string:component_id>/variables", methods=["PUT"])
def update_component_variables(component_id: str):
    component_manager = current_app.config["COMPONENT_MANAGER"]
    try:
        variables_data = request.get_json(silent=True)
        if variables_data is None:
            return jsonify({"error": "Invalid payload"}), 400
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
    try:
        content = component_manager.get_component_template_content(component_id)
        return Response(content, mimetype="text/plain")
    except KeyError:
        return jsonify({"error": "Component not found"}), 404
    except Exception as e:
        logging.error(f"Failed to get template for {component_id}: {e}", exc_info=True)
        return jsonify({"error": "An unexpected server error occurred"}), 500
