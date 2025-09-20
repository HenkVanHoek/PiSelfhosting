import json

from src.managers.component_manager import ComponentManager


class TestComponentManager:
    def test_initialization(self, tmp_path):
        """Test that the component manager initializes correctly."""
        metadata_content = {
            "components": {
                "comp1": {"name": "Component 1"},
                "comp2": {"name": "Component 2"},
            }
        }
        metadata_file = tmp_path / "components_metadata.json"
        metadata_file.write_text(json.dumps(metadata_content))

        # --- FIX: Add the required 'metadata_file_path' argument ---
        manager = ComponentManager(
            templates_path=str(tmp_path), metadata_file_path=str(metadata_file)
        )
        assert len(manager.get_all_components()) == 2

    def test_get_all_components_sorted(self, tmp_path):
        """Test that components are returned as a list."""
        metadata_content = {
            "components": {
                "comp-b": {"name": "Component B"},
                "comp-a": {"name": "Component A"},
            }
        }
        metadata_file = tmp_path / "components_metadata.json"
        metadata_file.write_text(json.dumps(metadata_content))

        # --- FIX: Add the required 'metadata_file_path' argument ---
        manager = ComponentManager(
            templates_path=str(tmp_path), metadata_file_path=str(metadata_file)
        )
        components = manager.get_all_components()
        assert isinstance(components, list)
        assert len(components) == 2

    def test_get_docker_service_name(self, tmp_path):
        """Test getting the docker service name."""
        metadata_content = {
            "components": {
                "comp1": {"name": "Component 1", "docker_service_name": "service1"},
                "comp2": {"name": "Component 2"},
            }
        }
        metadata_file = tmp_path / "components_metadata.json"
        metadata_file.write_text(json.dumps(metadata_content))

        # --- FIX: Add the required 'metadata_file_path' argument ---
        manager = ComponentManager(
            templates_path=str(tmp_path), metadata_file_path=str(metadata_file)
        )

        assert manager.get_docker_service_name("comp1") == "service1"
        assert manager.get_docker_service_name("comp2") == "comp2"
