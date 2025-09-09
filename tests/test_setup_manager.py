import json
from unittest.mock import patch

import pytest

from managers.component_manager import ComponentManager
from managers.setup_manager import SetupManager

@pytest.fixture
def mock_paths(tmp_path):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    templates_dir = tmp_path / "component_templates"
    templates_dir.mkdir()
    return {
        "metadata": tmp_path / "components_metadata.json",
        "output": output_dir,
        "templates": templates_dir,
    }

@pytest.fixture
def component_manager_instance(mock_paths):
    (mock_paths["templates"] / "dashy").mkdir()
    (mock_paths["templates"] / "dashy" / "docker-compose.template.yml").write_text(
        "services:\n  dashy:\n    image: lissy93/dashy\n"
    )
    (mock_paths["templates"] / "dashy" / "conf.template.yml").write_text(
        "appConfig:\n  title: {{ DASHY_TITLE | default('Pi Dashboard') }}\n"
    )
    (mock_paths["templates"] / "frigate").mkdir()
    (mock_paths["templates"] / "frigate" / "docker-compose.template.yml").write_text(
        "services:\n  frigate:\n    image: frigate/frigate\nvolumes:\n  frigate_data:\n"
    )
    (mock_paths["templates"] / "mosquitto").mkdir()
    (mock_paths["templates"] / "mosquitto" / "docker-compose.template.yml").write_text(
        "services:\n  mosquitto:\n    image: eclipse-mosquitto\n"
    )
    metadata_content = {
        "dashy": {
            "name": "Dashy",
            "docker_compose": "docker-compose.template.yml",
            "other_files": [
                {"template": "conf.template.yml", "destination": "dashy/conf.yml"}
            ],
        },
        "frigate": {
            "name": "Frigate",
            "depends_on": "mosquitto",
            "docker_compose": "docker-compose.template.yml",
        },
        "mosquitto": {
            "name": "Mosquitto",
            "docker_compose": "docker-compose.template.yml",
        },
        "_piselfhosting": {"components_order": ["dashy", "frigate", "mosquitto"]},
    }
    mock_paths["metadata"].write_text(json.dumps(metadata_content))

    with patch("managers.component_manager.ConfigManager") as MockConfigManager:
        mock_config_instance = MockConfigManager.return_value
        def mock_get_path(component_id):
            return mock_paths["templates"] / component_id
        mock_config_instance.get_component_template_path.side_effect = mock_get_path
        manager = ComponentManager(metadata_file=str(mock_paths["metadata"]))
        yield manager

@pytest.fixture
def setup_manager_instance(component_manager_instance, mock_paths):
    manager = SetupManager(
        component_manager_instance,
        output_dir=mock_paths["output"]
    )
    return manager

def test_generate_all_files(setup_manager_instance, mock_paths):
    selected = ["dashy", "frigate"]
    env_vars = {"DASHY_TITLE": "My Awesome Dashboard"}

    setup_manager_instance.generate_all_files(selected, env_vars)

    output_file = mock_paths["output"] / "docker-compose.yml"
    assert output_file.exists()
    content = output_file.read_text()
    assert "dashy:" in content
    assert "frigate:" in content
    assert "mosquitto:" in content

    conf_output_file = mock_paths["output"] / "dashy" / "conf.yml"
    assert conf_output_file.exists()
    conf_content = conf_output_file.read_text()
    assert "title: My Awesome Dashboard" in conf_content