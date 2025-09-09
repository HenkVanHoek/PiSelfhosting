import json
from unittest.mock import MagicMock

import pytest

from managers.component_manager import ComponentManager

@pytest.fixture
def mock_config_manager(monkeypatch):
    mock = MagicMock()
    monkeypatch.setattr("managers.component_manager.ConfigManager", mock)
    return mock

@pytest.fixture
def mock_metadata_file(tmp_path):
    data = {
        "comp1": {"name": "Component 1", "description": "First comp", "default": True},
        "comp2": {"name": "Component 2", "description": "Second comp"},
        "dashy": {"name": "Dashy", "description": "A dashboard.", "default": False},
        "_piselfhosting": {
            "components_order": ["comp1", "comp2", "dashy"],
            "dashy_section": "Services",
        },
    }
    file_path = tmp_path / "components_metadata.json"
    file_path.write_text(json.dumps(data))
    return str(file_path)

def test_initialization_with_file(mock_metadata_file, mock_config_manager):
    manager = ComponentManager(metadata_file=mock_metadata_file)
    assert manager.components is not None
    assert "comp1" in manager.components
    mock_config_manager.assert_called_once()

def test_get_all_components_sorted(mock_metadata_file, mock_config_manager):
    manager = ComponentManager(metadata_file=mock_metadata_file)
    components = manager.get_all_components()
    assert isinstance(components, list)
    component_ids = [comp['id'] for comp in components]
    assert component_ids == ["comp1", "comp2", "dashy"]
    assert components[0]['name'] == "Component 1"

def test_get_component_details(mock_metadata_file, mock_config_manager):
    manager = ComponentManager(metadata_file=mock_metadata_file)
    details = manager.get_component_details("dashy")
    assert details is not None
    assert details["name"] == "Dashy"
    assert manager.get_component_details("non_existent_component") is None

def test_get_dashy_section(mock_metadata_file, mock_config_manager):
    manager = ComponentManager(metadata_file=mock_metadata_file)
    section = manager.get_dashy_section()
    assert section == "Services"

def test_loads_default_flag(mock_metadata_file, mock_config_manager):
    manager = ComponentManager(metadata_file=mock_metadata_file)
    components = manager.get_all_components()
    comp1 = next((c for c in components if c['id'] == 'comp1'), None)
    comp2 = next((c for c in components if c['id'] == 'comp2'), None)
    dashy = next((c for c in components if c['id'] == 'dashy'), None)
    assert comp1 is not None
    assert comp2 is not None
    assert dashy is not None
    assert comp1.get("default") is True
    assert comp2.get("default") is None
    assert dashy.get("default") is False