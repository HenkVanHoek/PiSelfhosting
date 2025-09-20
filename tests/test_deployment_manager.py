from src.managers.component_manager import ComponentManager
from src.managers.deployment_manager import DeploymentManager


class TestDeploymentManager:
    def test_deployment_initialization(self, tmp_path):
        """
        Tests that the DeploymentManager can be initialized.
        """
        # --- FIX: Create a dummy metadata file for the test ---
        metadata_file = tmp_path / "components_metadata.json"
        metadata_file.write_text('{"components": {}}')

        # --- FIX: Provide both required arguments to ComponentManager ---
        component_manager = ComponentManager(
            templates_path=str(tmp_path),
            metadata_file_path=str(metadata_file),
        )

        deployment_manager = DeploymentManager(component_manager=component_manager)
        assert deployment_manager is not None
