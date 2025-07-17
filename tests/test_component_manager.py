# tests/test_component_manager.py
import json
from unittest.mock import MagicMock

import pytest

# Updated import
from managers.component_manager import ComponentManager


@pytest.fixture
def mock_config_manager(monkeypatch):
    """Mocks the ConfigManager to prevent it from being instantiated during tests."""
    mock = MagicMock()
    # Updated path for the patch
    monkeypatch.setattr("managers.component_manager.ConfigManager", mock)
    return mock


@pytest.fixture
def mock_metadata_file(tmp_path):
    """Fixture to create a temporary metadata JSON file."""
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
    """Test that ComponentManager initializes correctly with a file."""
    manager = ComponentManager(metadata_file=mock_metadata_file)
    assert manager.components is not None
    assert "comp1" in manager.components
    # Check that ConfigManager was instantiated inside ComponentManager
    mock_config_manager.assert_called_once()


def test_get_all_components_sorted(mock_metadata_file, mock_config_manager):
    """Test that components are returned in the specified order."""
    manager = ComponentManager(metadata_file=mock_metadata_file)
    components = manager.get_all_components()
    component_keys = list(components.keys())
    # The _piselfhosting key is internal and should not be returned
    assert component_keys == ["comp1", "comp2", "dashy"]


def test_get_component_details(mock_metadata_file, mock_config_manager):
    """Test retrieving details for a specific component."""
    manager = ComponentManager(metadata_file=mock_metadata_file)
    details = manager.get_component_details("dashy")
    assert details is not None
    assert details["name"] == "Dashy"
    assert manager.get_component_details("non_existent_component") is None


def test_get_dashy_section(mock_metadata_file, mock_config_manager):
    """Test retrieving the dashy section."""
    manager = ComponentManager(metadata_file=mock_metadata_file)
    section = manager.get_dashy_section()
    assert section == "Services"


def test_loads_default_flag(mock_metadata_file, mock_config_manager):
    """Test that the 'default' flag is correctly loaded for each component."""
    manager = ComponentManager(metadata_file=mock_metadata_file)
    components = manager.get_all_components()
    assert components["comp1"].get("default") is True
    # If "default" is not present, .get() should return None, which is fine.
    # The application logic correctly interprets this as False.
    assert components["comp2"].get("default") is None
    assert components["dashy"].get("default") is False
