import logging
from collections import defaultdict
from typing import Any, Dict, List, Union

from flask import Blueprint, Response, current_app, jsonify, render_template, request

from src.utils.auth_utils import generate_basic_auth_hash
from src.utils.resource_utils import get_global_template_context

editor_bp = Blueprint(
    "editor", __name__, template_folder="templates", static_folder="static"
)


@editor_bp.route("/")
def index() -> str:
    context = get_global_template_context()
    return render_template("editor.html", **context)


@editor_bp.route("/api/generate_auth_hash", methods=["POST"])
def generate_auth_hash() -> tuple[Response, int]:
    """
    API endpoint to generate a secure 'username:hashed_password' string
    for use in basic authentication systems like Traefik middleware.
    """
    try:
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({"error": "Invalid or missing JSON payload"}), 400

        # Unpack the inputs.
        username = data.get("username")
        password = data.get("password")

        if not username or not password:
            return jsonify({"error": "Username and password are required"}), 400

        # Generate the secure user string
        hashed_string = generate_basic_auth_hash(username, password)

        # For a clean API response, we return the raw, unescaped string.
        return jsonify({"hashed_user_string": hashed_string}), 200

    except Exception as e:
        logging.error(f"Failed to generate auth hash: {e}", exc_info=True)
        return jsonify({"error": "An unexpected server error occurred"}), 500


def _sort_components(
    components: List[Dict[str, str]], order_list: List[str]
) -> List[Dict[str, str]]:
    order_map = {comp_id: i for i, comp_id in enumerate(order_list)}
    ordered = [c for c in components if c["id"] in order_map]
    unordered = [c for c in components if c["id"] not in order_map]
    ordered.sort(key=lambda c: order_map[c["id"]])
    # Using 'or c.get("id") or ""' ensures the final return is always a str.
    unordered.sort(key=lambda c: c.get("name") or c.get("id") or "")
    return ordered + unordered


@editor_bp.route("/api/components", methods=["GET", "POST"])
def get_or_create_components() -> tuple[Response, int]:
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
        groups_map: defaultdict[str, Dict[str, Any]] = defaultdict(
            lambda: {"components": []}
        )
        for comp in all_components:
            group_id = comp.get("group") or default_group_id
            groups_map[group_id]["components"].append(
                {"id": comp.get("id"), "name": comp.get("name")}
            )
        sorted_groups: List[Dict[str, Any]] = []
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
        return jsonify({"groups": sorted_groups}), 200
    except Exception as e:
        logging.error(f"Failed to get component list: {e}", exc_info=True)
        return jsonify({"error": "An unexpected server error occurred"}), 500


@editor_bp.route("/api/components/<string:component_id>/validate", methods=["POST"])
def validate_component_configuration(component_id: str) -> tuple[Response, int]:
    """API endpoint to validate a component's template and variables."""
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
        return jsonify({"message": "Validation successful!"}), 200
    except ValueError as e:
        return jsonify({"error": f"Validation Failed: {e}"}), 400
    except Exception as e:
        logging.error(
            f"Failed to validate component {component_id}: {e}", exc_info=True
        )
        return jsonify({"error": "An unexpected server error occurred"}), 500


@editor_bp.route(
    "/api/components/<string:component_id>/validate_metadata_conflicts",
    methods=["POST"],
)
def validate_metadata_conflicts(component_id: str) -> tuple[Response, int]:
    """
    API endpoint to validate the 'conflicts_with' metadata field for a component.
    """
    component_manager = current_app.config["COMPONENT_MANAGER"]
    try:
        data = request.get_json(silent=True)
        if not data:
            return jsonify({"error": "Invalid or missing JSON payload"}), 400

        # Unpacking from payload, defaulting to an empty list
        conflicts_with = data.get("conflicts_with", [])
        if not isinstance(conflicts_with, list):
            return jsonify({"error": "Payload 'conflicts_with' must be a list."}), 400

        component_manager.validate_metadata_conflicts(component_id, conflicts_with)

        return jsonify({"message": "Metadata conflict validation successful!"}), 200
    except ValueError as e:
        # ValueError is raised by ComponentManager on failed conflict check
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logging.error(
            f"Failed to validate conflicts for {component_id}: {e}", exc_info=True
        )
        return jsonify({"error": "An unexpected server error occurred"}), 500


@editor_bp.route("/api/groups/<string:group_id>/rename", methods=["PUT"])
def rename_group(group_id: str) -> tuple[Response, int]:
    component_manager = current_app.config["COMPONENT_MANAGER"]
    try:
        data = request.get_json()
        new_name = data.get("name")
        if not new_name:
            return jsonify({"error": "New name is required"}), 400
        component_manager.rename_group(group_id, new_name)
        return (
            jsonify(
                {"message": f"Group '{group_id}' renamed to '{new_name}' successfully"}
            ),
            200,
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logging.error(f"Failed to rename group {group_id}: {e}", exc_info=True)
        return jsonify({"error": "An unexpected server error occurred"}), 500


@editor_bp.route("/api/groups/<string:group_id>", methods=["DELETE"])
def delete_group(group_id: str) -> tuple[Response, int]:
    component_manager = current_app.config["COMPONENT_MANAGER"]
    try:
        component_manager.delete_group(group_id)
        return jsonify({"message": f"Group '{group_id}' deleted successfully"}), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except KeyError:
        # Group not found in metadata
        return jsonify({"error": "Group not found"}), 404
    except Exception as e:
        logging.error(f"Failed to delete group {group_id}: {e}", exc_info=True)
        return jsonify({"error": "An unexpected server error occurred"}), 500


@editor_bp.route("/api/groups/order", methods=["PUT"])
def update_group_order() -> tuple[Response, int]:
    component_manager = current_app.config["COMPONENT_MANAGER"]
    try:
        new_order = request.get_json()
        if not isinstance(new_order, list):
            return jsonify({"error": "Invalid payload"}), 400
        component_manager.update_group_order(new_order)
        return jsonify({"message": "Group order updated successfully"}), 200
    except Exception as e:
        logging.error(f"Failed to update group order: {e}", exc_info=True)
        return jsonify({"error": "An unexpected server error occurred"}), 500


@editor_bp.route("/api/components/order", methods=["PUT"])
def update_components_order() -> tuple[Response, int]:
    component_manager = current_app.config["COMPONENT_MANAGER"]
    try:
        new_order = request.get_json()
        if not isinstance(new_order, list):
            return jsonify({"error": "Invalid payload"}), 400
        component_manager.update_components_order(new_order)
        return jsonify({"message": "Component order updated successfully"}), 200
    except Exception as e:
        logging.error(f"Failed to update component order: {e}", exc_info=True)
        return jsonify({"error": "An unexpected server error occurred"}), 500


@editor_bp.route("/api/components/<string:component_id>/group", methods=["PUT"])
def update_component_group(component_id: str) -> tuple[Response, int]:
    component_manager = current_app.config["COMPONENT_MANAGER"]
    try:
        data = request.get_json()
        new_group_id = data.get("group")
        if not new_group_id:
            return jsonify({"error": "Missing 'group' in payload"}), 400
        component_manager.update_component_group(component_id, new_group_id)
        return (
            jsonify(
                {
                    "message": f"Component '{component_id}' moved to"
                    f" group '{new_group_id}'"
                }
            ),
            200,
        )
    except KeyError:
        return jsonify({"error": "Component not found"}), 404
    except Exception as e:
        logging.error(
            f"Failed to update component " f"group for {component_id}: {e}",
            exc_info=True,
        )
        return jsonify({"error": "An unexpected server error occurred"}), 500


@editor_bp.route(
    "/api/components/<string:component_id>", methods=["GET", "PUT", "DELETE"]
)
def component_details(component_id: str) -> Union[tuple[Response, int], Response]:
    component_manager = current_app.config["COMPONENT_MANAGER"]
    if request.method == "PUT":
        try:
            update_data = request.get_json(silent=True)
            if update_data is None:
                return jsonify({"error": "Invalid payload"}), 400

            # Safely cast new Traefik metadata fields from string to correct type
            if "has_traefik_support" in update_data:
                # Ensure boolean conversion: "true" -> True, anything else -> False
                support_str = update_data["has_traefik_support"]
                is_supported = str(support_str).lower() == "true"
                update_data["has_traefik_support"] = is_supported

            if "traefik_internal_port" in update_data:
                port_val = update_data["traefik_internal_port"]
                try:
                    # 'null' or None means no specific port is set
                    if port_val is None or str(port_val).lower() == "null":
                        update_data["traefik_internal_port"] = None
                    else:
                        # Ensure port is an integer
                        update_data["traefik_internal_port"] = int(port_val)
                except ValueError:
                    return (
                        jsonify(
                            {"error": "Traefik Internal Port must be a valid integer."}
                        ),
                        400,
                    )

            component_manager.update_component_metadata(component_id, update_data)
            return jsonify({"message": "Component updated successfully"}), 200
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
            return (
                jsonify(
                    {"message": f"Component '{component_id}' deleted successfully"}
                ),
                200,
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
                return jsonify(details_copy), 200
            else:
                return jsonify({"error": "Component not found"}), 404
        except Exception as e:
            logging.error(
                f"Failed to get details for {component_id}: {e}", exc_info=True
            )
            return jsonify({"error": "An unexpected server error occurred"}), 500


@editor_bp.route("/api/components/<string:component_id>/variables", methods=["PUT"])
def update_component_variables(component_id: str) -> tuple[Response, int]:
    component_manager = current_app.config["COMPONENT_MANAGER"]
    try:
        payload = request.get_json(silent=True)
        if payload is None:
            return jsonify({"error": "Invalid payload"}), 400

        # To keep the final variables.json file clean, we remove the 'required'
        # key if its value is empty/falsey.
        variables_data = payload.get("variables", [])
        for var in variables_data:
            if "required" in var and not var["required"]:
                del var["required"]

        component_manager.update_component_variables(
            component_id, {"variables": variables_data}
        )
        return jsonify({"message": "Variables updated successfully"}), 200
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
def component_template(component_id: str) -> Union[Response, tuple[Response, int]]:
    component_manager = current_app.config["COMPONENT_MANAGER"]
    if request.method == "PUT":
        try:
            template_content = request.get_data(as_text=True)
            component_manager.update_component_template_content(
                component_id, template_content
            )
            return jsonify({"message": "Template updated successfully"}), 200
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
