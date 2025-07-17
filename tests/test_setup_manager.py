# tests/test_setup_manager.py
import json
from unittest.mock import patch

import pytest

from managers.component_manager import ComponentManager
from managers.setup_manager import SetupManager


@pytest.fixture
def mock_paths(tmp_path):
    """Creates a temporary directory structure for tests."""
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
    """Provides a ComponentManager instance pointed at mock metadata and templates."""
    # Create mock templates
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

    # Create mock metadata file with explicit docker_compose and other_files sections
    metadata_content = {
        "dashy": {
            "name": "Dashy",
            "has_ui": True,
            "ui_port": 8080,
            "docker_compose": "docker-compose.template.yml",
            "other_files": [
                {"template": "conf.template.yml", "destination": "dashy/conf.yml"}
            ],
        },
        "frigate": {
            "name": "Frigate",
            "has_ui": True,
            "ui_port": 5000,
            "depends_on": "mosquitto",
            "docker_compose": "docker-compose.template.yml",
        },
        "mosquitto": {
            "name": "Mosquitto",
            "has_ui": False,
            "docker_compose": "docker-compose.template.yml",
        },
        "_piselfhosting": {"components_order": ["dashy", "frigate", "mosquitto"]},
    }
    mock_paths["metadata"].write_text(json.dumps(metadata_content))

    # Patch ConfigManager and configure the mock BEFORE ComponentManager uses it.
    with patch("managers.component_manager.ConfigManager") as MockConfigManager:
        mock_config_instance = MockConfigManager.return_value

        # This side effect correctly returns the component-specific directory path
        def mock_get_path(component_id):
            return mock_paths["templates"] / component_id

        mock_config_instance.get_component_template_path.side_effect = mock_get_path

        # Now, instantiate the ComponentManager. It will use the pre-configured mock
        # to correctly load template contents during its initialization.
        manager = ComponentManager(metadata_file=str(mock_paths["metadata"]))
        yield manager


@pytest.fixture
def setup_manager_instance(component_manager_instance, mock_paths):
    """Provides a SetupManager instance with a mocked component manager."""
    manager = SetupManager(component_manager_instance)
    # Override the output directory to use the temporary one
    manager.output_dir = str(mock_paths["output"])
    manager.docker_compose_path = mock_paths["output"] / "docker-compose.yml"
    return manager


def test_generate_all_files(setup_manager_instance, mock_paths):
    """
    Test the generation of the docker-compose.yml file and other component files.
    """
    # Arrange
    selected = ["dashy", "frigate"]  # frigate depends on mosquitto
    env_vars = {"DASHY_TITLE": "My Awesome Dashboard"}

    # Act
    setup_manager_instance.generate_all_files(selected, env_vars)

    # Assert docker-compose.yml generation
    output_file = mock_paths["output"] / "docker-compose.yml"
    assert output_file.exists(), "docker-compose.yml was not created"

    content = output_file.read_text()
    assert "dashy:" in content
    assert "frigate:" in content
    assert "mosquitto:" in content  # Dependency included

    # Assert config file generation with Jinja rendering
    conf_output_file = mock_paths["output"] / "dashy" / "conf.yml"
    assert conf_output_file.exists(), "Dashy conf.yml was not created"

    conf_content = conf_output_file.read_text()
    assert "title: My Awesome Dashboard" in conf_content
