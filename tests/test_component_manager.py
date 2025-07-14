import json

import pytest

# Correctie: Importeer vanuit de 'src' map
from src.component_manager import ComponentManager

# from pathlib import Path


@pytest.fixture
def mock_project_structure(tmp_path):
    """
    Creëert een tijdelijke projectstructuur met een componenten metadata bestand.
    Deze fixture wordt automatisch door pytest aangeroepen voor
    het initialiseren van een ComponentManager
    tests die het als argument hebben.
    """
    # Maak een tijdelijke map voor de configuratie
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    # Definieer de standaard metadata voor de tests
    metadata = {
        "_piselfhosting": {"components_order": ["dashy", "portainer", "frigate"]},
        "dashy": {
            "name": "Dashy",
            "description": "A self-hosted dashboard.",
            "uniqueness_group": None,
        },
        "portainer": {
            "name": "Portainer",
            "description": "Container management UI.",
            "uniqueness_group": "container_manager",
        },
        "frigate": {
            "name": "Frigate",
            "description": "NVR with AI.",
            "uniqueness_group": None,
        },
    }

    # Schrijf de metadata naar het JSON-bestand binnen de tijdelijke map
    metadata_path = config_dir / "components_metadata.json"
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f)

    # De ComponentManager verwacht het pad naar het *bestand*, dus dat geven we terug
    return metadata_path


def test_manager_loads_components_successfully(mock_project_structure):
    """Test dat de ComponentManager correct initialiseert met geldige metadata."""
    # De 'mock_project_structure' fixture wordt hier automatisch gebruikt
    manager = ComponentManager(metadata_path=mock_project_structure)

    all_components = manager.get_all_components()
    assert "dashy" in all_components
    assert "portainer" in all_components
    assert "_piselfhosting" in all_components


def test_get_component_details(mock_project_structure):
    """Test het ophalen van details voor een specifieke component."""
    manager = ComponentManager(metadata_path=mock_project_structure)

    # Test het ophalen van een geldige component
    details = manager.get_component_details("dashy")
    assert details is not None
    assert details["name"] == "Dashy"

    # Test het ophalen van een niet-bestaande component
    details_none = manager.get_component_details("non_existent_component")
    assert details_none is None


def test_manager_raises_file_not_found_on_init(tmp_path):
    """Test dat de manager een FileNotFoundError opwerpt als de metadata ontbreekt."""
    non_existent_path = tmp_path / "non_existent_file.json"
    with pytest.raises(FileNotFoundError):
        ComponentManager(metadata_path=non_existent_path)


def test_manager_raises_json_decode_error_on_init(tmp_path):
    """Test dat de manager een JSONDecodeError opwerpt voor een corrupt bestand."""
    bad_json_path = tmp_path / "bad.json"
    bad_json_path.write_text("{'key': 'value',}")  # Ongeldige JSON
    with pytest.raises(json.JSONDecodeError):
        ComponentManager(metadata_path=bad_json_path)


def test_get_uniqueness_groups(mock_project_structure):
    """Test of de uniqueness groups correct worden geïdentificeerd."""
    metadata_path = mock_project_structure

    with open(metadata_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    data["dashy"]["uniqueness_group"] = "dashboard"
    data["frigate"]["uniqueness_group"] = "nvr"

    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(data, f)

    manager = ComponentManager(metadata_path=metadata_path)
    groups = manager.get_uniqueness_groups()

    assert groups == {
        "dashboard": ["dashy"],
        "nvr": ["frigate"],
        "container_manager": ["portainer"],
    }
