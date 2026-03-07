# tests/test_component_reader.py
import json

from src.managers.component_reader import ComponentReader


def test_reader_retrieves_metadata(tmp_path):
    """
    Test if the reader correctly loads component data from the master JSON.
    """
    # Setup: Create temporary files
    meta_path = tmp_path / "metadata.json"
    temp_path = tmp_path / "templates"
    temp_path.mkdir()

    # Create dummy metadata
    data = {
        "components": {
            "traefik": {"name": "Traefik Proxy", "group": "core"},
            "pihole": {"name": "Pi-hole", "group": "network"},
        }
    }
    meta_path.write_text(json.dumps(data), encoding="utf-8")

    # Execute
    reader = ComponentReader(metadata_path=meta_path, templates_path=temp_path)

    # Verify
    components = reader.get_all_components()
    assert len(components) == 2
    assert components["traefik"]["name"] == "Traefik Proxy"
    assert reader.get_component_details("pihole")["group"] == "network"


def test_reader_loads_component_variables(tmp_path):
    """
    Test if the reader retrieves variables from the component's subdirectory.
    """
    meta_path = tmp_path / "metadata.json"
    meta_path.write_text(json.dumps({"components": {"app": {}}}), encoding="utf-8")

    # Setup component directory and variables.json
    temp_path = tmp_path / "templates"
    app_dir = temp_path / "app"
    app_dir.mkdir(parents=True)

    vars_data = [{"name": "API_KEY", "default": "secret"}]
    (app_dir / "variables.json").write_text(json.dumps(vars_data), encoding="utf-8")

    # Execute
    reader = ComponentReader(metadata_path=meta_path, templates_path=temp_path)
    variables = reader.get_component_variables("app")

    # Verify
    assert len(variables) == 1
    assert variables[0]["name"] == "API_KEY"
