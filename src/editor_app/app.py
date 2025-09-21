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
    """Helper function to sort components based on a preferred order list."""
    order_map = {comp_id: i for i, comp_id in enumerate(order_list)}

    # Separate components into ordered and unordered lists
    ordered = [c for c in components if c["id"] in order_map]
    unordered = [c for c in components if c["id"] not in order_map]

    # Sort each list individually
    ordered.sort(key=lambda c: order_map[c["id"]])
    unordered.sort(key=lambda c: c.get("name") or c.get("id"))

    return ordered + unordered


@editor_bp.route("/api/components", methods=["GET"])
def get_components():
    """API endpoint to get all components, structured and sorted by group."""
    component_manager = current_app.config["COMPONENT_MANAGER"]
    try:
        all_components = component_manager.get_all_components()
        meta = component_manager.get_piselfhosting_meta()
        default_group_id = meta.get("default_group", "general")
        group_order = meta.get("group_order", [])
        components_order = meta.get("components_order", [])  # Get component order
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
                        # --- NEW: Sort components within the group ---
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
                    # --- NEW: Sort components within the group ---
                    "components": _sort_components(
                        data["components"], components_order
                    ),
                }
            )

        return jsonify({"groups": sorted_groups})

    except Exception as e:
        logging.error(f"Failed to get component list: {e}", exc_info=True)
        return jsonify({"error": "An unexpected server error occurred"}), 500


@editor_bp.route("/api/groups/order", methods=["PUT"])
def update_group_order():
    component_manager = current_app.config["COMPONENT_MANAGER"]
    try:
        new_order = request.get_json()
        if not isinstance(new_order, list):
            return jsonify({"error": "Invalid payload, expected a list"}), 400

        component_manager.update_group_order(new_order)
        return jsonify({"message": "Group order updated successfully"})
    except Exception as e:
        logging.error(f"Failed to update group order: {e}", exc_info=True)
        return jsonify({"error": "An unexpected server error occurred"}), 500


# --- NEW: Endpoint to save the component sort order ---
@editor_bp.route("/api/components/order", methods=["PUT"])
def update_components_order():
    component_manager = current_app.config["COMPONENT_MANAGER"]
    try:
        new_order = request.get_json()
        if not isinstance(new_order, list):
            return jsonify({"error": "Invalid payload, expected a list"}), 400

        component_manager.update_components_order(new_order)
        return jsonify({"message": "Component order updated successfully"})
    except Exception as e:
        logging.error(f"Failed to update component order: {e}", exc_info=True)
        return jsonify({"error": "An unexpected server error occurred"}), 500


@editor_bp.route("/api/components/<string:component_id>", methods=["GET", "PUT"])
def component_details(component_id: str):
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
