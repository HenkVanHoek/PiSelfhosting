import json
from pathlib import Path
from unittest.mock import MagicMock

import yaml

from src.managers.component_manager import ComponentManager
from src.managers.deployment_manager import DeploymentManager


class TestDeploymentManager:
    def test_deployment_initialization(self, tmp_path):
        """
        Tests that the DeploymentManager can be initialized.
        """
        metadata_file = tmp_path / "components_metadata.json"
        metadata_file.write_text('{"components": {}}')

        component_manager = ComponentManager(
            templates_path=str(tmp_path),
            metadata_file_path=str(metadata_file),
        )

        deployment_manager = DeploymentManager(component_manager=component_manager)
        assert deployment_manager is not None

    def test_discover_links_deduplicates_init_containers(self, tmp_path: Path):
        """
        Verify that _discover_service_links correctly generates only one link
        for a component that has both a main service and an init service.
        """
        # --- ARRANGE ---
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        # 1. Create mock metadata with the critical 'docker_service_name' pointer
        metadata_file = tmp_path / "components_metadata.json"
        metadata_content = {
            "components": {
                "traefik": {
                    "name": "Traefik Proxy",
                    "has_ui": True,
                    "docker_service_name": "traefik-main",
                    "ui_port_variable": "TRAEFIK_WEB_PORT",
                    "protocol": "http",
                }
            }
        }
        metadata_file.write_text(json.dumps(metadata_content))

        # 2. Create mock context with the final port value
        context_file = output_dir / "deployment_context.json"
        context_content = {"TRAEFIK_WEB_PORT": "8080"}
        context_file.write_text(json.dumps(context_content))

        # 3. Create mock compose file with two services for the same component
        compose_file = output_dir / "docker-compose.yml"
        compose_content = {
            "services": {
                "traefik-init": {
                    "image": "busybox",
                    "labels": ["piselfhosting.component.id=traefik"],
                },
                "traefik-main": {
                    "image": "traefik:v3.0",
                    "labels": ["piselfhosting.component.id=traefik"],
                },
            }
        }
        compose_file.write_text(yaml.dump(compose_content))

        # 4. Set up the managers
        component_manager = ComponentManager(
            templates_path=str(tmp_path),
            metadata_file_path=str(metadata_file),
        )
        deployment_manager = DeploymentManager(component_manager=component_manager)
        log_callback = MagicMock()

        # --- ACT ---
        service_links = deployment_manager._discover_service_links(
            ip="192.168.1.100",
            local_output_path=output_dir,
            log_callback=log_callback,
        )

        # --- ASSERT ---
        assert service_links is not None
        # The core assertion: only ONE link should have been created
        assert len(service_links) == 1
        link = service_links
        assert link[0]["name"] == "Traefik Proxy"
        assert link[0]["url"] == "http://192.168.1.100:8080"
