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

        manager = ComponentManager(
            templates_path=str(tmp_path), metadata_file_path=str(metadata_file)
        )
        assert len(manager.get_all_components()) == 2

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

        manager = ComponentManager(
            templates_path=str(tmp_path), metadata_file_path=str(metadata_file)
        )
        assert manager.get_docker_service_name("comp1") == "service1"
        assert manager.get_docker_service_name("comp2") == "comp2"

    def test_update_components_order(self, tmp_path):
        """Test that the component order can be updated and saved."""
        metadata_file = tmp_path / "components_metadata.json"
        initial_content = {
            "_piselfhosting": {"components_order": ["comp1", "comp2"]},
            "components": {
                "comp1": {"name": "Component 1"},
                "comp2": {"name": "Component 2"},
            },
        }
        metadata_file.write_text(json.dumps(initial_content))

        manager = ComponentManager(
            templates_path=str(tmp_path), metadata_file_path=str(metadata_file)
        )

        new_order = ["comp2", "comp1"]
        manager.update_components_order(new_order)

        # Verify the file was saved with the new order
        saved_data = json.loads(metadata_file.read_text())
        assert saved_data["_piselfhosting"]["components_order"] == new_order
