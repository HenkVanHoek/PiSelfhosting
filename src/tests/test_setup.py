# tests/test_setup.py
import pytest
import os
import sys
import json
import yaml
from unittest.mock import patch, MagicMock

# Adjust the path to import setup.py from src/
# Assuming tests/test_setup.py is at the same level as src/
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))
import setup as pisetup

# Constants from setup.py
COMPONENTS_LIST_FILENAME = pisetup.COMPONENTS_LIST_FILENAME
SELECTED_COMPONENTS_FILENAME = pisetup.SELECTED_COMPONENTS_FILENAME
DOCKER_COMPOSE_TEMPLATES_DIR = pisetup.DOCKER_COMPOSE_TEMPLATES_DIR
DOCKER_COMPOSE_OUTPUT_DIR = pisetup.DOCKER_COMPOSE_OUTPUT_DIR
UNIFIED_DOCKER_COMPOSE_FILENAME = pisetup.UNIFIED_DOCKER_COMPOSE_FILENAME
GLOBAL_DATA_ROOT = pisetup.GLOBAL_DATA_ROOT


@pytest.fixture
def mock_project_structure(tmp_path):
    """
    Creates a temporary project structure mirroring PiSelfhosting:
    - project_root/
      - src/
        - setup.py (symbolic link for testing)
      - templates/
        - dashy/
          - docker-compose.template.yml
          - template-config/
            - conf.yml
        - mosquitto/
          - docker-compose.template.yml
          - template-config/
            - mosquitto.conf
        - phpmyadmin/
          - docker-compose.template.yml
          - template-config/
            - config.inc.php
      - components_list.txt
      - selected_components.txt
    """
    project_root = tmp_path

    # Create src directory and a dummy setup.py inside it for pathing
    src_dir = project_root / "src"
    src_dir.mkdir()
    # Create a dummy setup.py in src/
    (src_dir / "setup.py").write_text("# dummy setup.py for testing")

    # Create templates directory
    templates_dir = project_root / DOCKER_COMPOSE_TEMPLATES_DIR
    templates_dir.mkdir()

    # Create Dashy templates
    dashy_template_dir = templates_dir / "dashy"
    dashy_template_dir.mkdir()
    (dashy_template_dir / "docker-compose.template.yml").write_text(
        """
services:
  dashy:
    container_name: piselfhosting-dashy
    image: lissy93/dashy:2.1.1
    ports:
      - "8080:80"
    volumes:
      - "{{DATA_ROOT}}/dashy/config:/app/public/conf"
    environment:
      - PUID={{PUID}}
      - PGID={{PGID}}
      - TZ={{TZ}}
    extra_hosts:
      - "{{DOMAIN}}:{{HOST_IP}}"
    networks:
      - piselfhosting_net
networks:
  piselfhosting_net:
    external: true
        """
    )
    dashy_config_template_dir = dashy_template_dir / "template-config"
    dashy_config_template_dir.mkdir()
    (dashy_config_template_dir / "conf.yml").write_text(
        """
pageInfo:
  title: {{DOMAIN}} Dashboard
sections:
  - name: Main
    items:
      - title: My Test App
        icon: fas fa-rocket
        url: http://{{HOST_IP}}:8080
        """
    )

    # Create Mosquitto templates
    mosquitto_template_dir = templates_dir / "mosquitto"
    mosquitto_template_dir.mkdir()
    (mosquitto_template_dir / "docker-compose.template.yml").write_text(
        """
services:
  mosquitto:
    container_name: piselfhosting-mosquitto
    image: eclipse-mosquitto:latest
    ports:
      - "1883:1883"
    volumes:
      - "{{DATA_ROOT}}/mosquitto/config:/mosquitto/config"
      - "{{DATA_ROOT}}/mosquitto/data:/mosquitto/data"
      - "{{DATA_ROOT}}/mosquitto/log:/mosquitto/log"
    networks:
      - piselfhosting_net
networks:
  piselfhosting_net:
    external: true
        """
    )
    mosquitto_config_template_dir = mosquitto_template_dir / "template-config"
    mosquitto_config_template_dir.mkdir()
    (mosquitto_config_template_dir / "mosquitto.conf").write_text(
        """
persistence true
persistence_location {{DATA_ROOT}}/mosquitto/data/
log_dest file {{DATA_ROOT}}/mosquitto/log/mosquitto.log
listener 1883
allow_anonymous false
password_file /mosquitto/config/passwords
"""
    )

    # Create phpMyAdmin templates
    phpmyadmin_template_dir = templates_dir / "phpmyadmin"
    phpmyadmin_template_dir.mkdir()
    (phpmyadmin_template_dir / "docker-compose.template.yml").write_text(
        """
services:
  phpmyadmin:
    container_name: piselfhosting-phpmyadmin
    image: phpmyadmin/phpmyadmin:latest
    environment:
      PMA_HOST: {{PMA_HOST}}
      PMA_USER: {{DB_USER}}
      PMA_PASSWORD: {{DB_PASS}}
      UPLOAD_LIMIT: 200M
      MEMORY_LIMIT: 256M
      MYSQL_ROOT_PASSWORD: {{DB_PASS}}
      PHPMYADMIN_CONFIG_DIR: /etc/phpmyadmin/config.d
      BLOWFISH_SECRET: "{{PHPMYADMIN_BLOWFISH_SECRET}}"
    ports:
      - "8081:80"
    networks:
      - piselfhosting_net
networks:
  piselfhosting_net:
    external: true
        """
    )
    phpmyadmin_config_template_dir = phpmyadmin_template_dir / "template-config"
    phpmyadmin_config_template_dir.mkdir()
    (phpmyadmin_config_template_dir / "config.inc.php").write_text(
        """
<?php
$cfg['blowfish_secret'] = '{{PHPMYADMIN_BLOWFISH_SECRET}}';
$cfg['Servers'][1]['host'] = '{{PMA_HOST}}';
$cfg['Servers'][1]['user'] = '{{DB_USER}}';
$cfg['Servers'][1]['password'] = '{{DB_PASS}}';
$cfg['UploadDir'] = '';
$cfg['SaveDir'] = '';
?>
"""
    )


    # Create components_list.txt
    (project_root / COMPONENTS_LIST_FILENAME).write_text(
        """
[PiSelfhosting]
components_order = dashy, mosquitto, phpmyadmin, frigate

[dashy]
description = A self-hosted dashboard for your services.
has_ui = True
ui_port = 8080
icon = fas fa-tachometer-alt
protocol = http

[mosquitto]
description = MQTT broker.
has_ui = False

[phpmyadmin]
description = Web interface for MySQL/MariaDB.
has_ui = True
ui_port = 8081
icon = fas fa-database
protocol = http

[frigate]
description = NVR with AI object detection.
has_ui = True
ui_port = 5000
icon = fas fa-video
protocol = http
        """
    )

    # Create selected_components.txt (initially empty)
    (project_root / SELECTED_COMPONENTS_FILENAME).write_text("")

    # Patch get_project_root to return our temporary project_root
    with patch('pisetup.get_project_root', return_value=str(project_root)):
        yield project_root


@pytest.fixture(autouse=True)
def cleanup_env_vars():
    """Fixture to clean up environment variables set during tests."""
    original_env = os.environ.copy()
    yield
    # Restore original environment variables
    for key, value in original_env.items():
        os.environ[key] = value
    # Remove any new variables set during tests
    for key in list(os.environ.keys()):
        if key not in original_env:
            del os.environ[key]

# --- Test get_project_root ---
def test_get_project_root(tmp_path):
    # Simulate src/setup.py location
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    dummy_setup_file = src_dir / "setup.py"
    dummy_setup_file.write_text("import os\ndef get_project_root(): return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))")

    with patch('os.path.abspath', return_value=str(dummy_setup_file)):
        with patch('os.path.dirname', side_effect=[str(src_dir), str(tmp_path)]):
            assert pisetup.get_project_root() == str(tmp_path)


# --- Test parse_components_list ---
def test_parse_components_list_valid(mock_project_structure):
    components_list_path = mock_project_structure / COMPONENTS_LIST_FILENAME
    result = pisetup.parse_components_list(file_path=str(components_list_path))

    assert "components_order" in result
    assert "all_component_data" in result
    assert result["components_order"] == ["dashy", "mosquitto", "phpmyadmin", "frigate"]

    assert "dashy" in result["all_component_data"]
    assert result["all_component_data"]["dashy"]["name"] == "dashy"
    assert result["all_component_data"]["dashy"]["has_ui"] == "True"
    assert result["all_component_data"]["dashy"]["ui_port"] == "8080"

    assert "mosquitto" in result["all_component_data"]
    assert result["all_component_data"]["mosquitto"]["name"] == "mosquitto"
    assert result["all_component_data"]["mosquitto"]["has_ui"] == "False"
    assert "ui_port" not in result["all_component_data"]["mosquitto"] # Ensure ui_port is not set for has_ui=False

    assert "phpmyadmin" in result["all_component_data"]
    assert result["all_component_data"]["phpmyadmin"]["name"] == "phpmyadmin"
    assert result["all_component_data"]["phpmyadmin"]["has_ui"] == "True"
    assert result["all_component_data"]["phpmyadmin"]["ui_port"] == "8081"

    assert "frigate" in result["all_component_data"]
    assert result["all_component_data"]["frigate"]["name"] == "frigate"
    assert result["all_component_data"]["frigate"]["has_ui"] == "True"
    assert result["all_component_data"]["frigate"]["ui_port"] == "5000"


def test_parse_components_list_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        pisetup.parse_components_list(file_path=str(tmp_path / "non_existent_list.txt"))


def test_parse_components_list_empty_file(mock_project_structure):
    empty_list_path = mock_project_structure / COMPONENTS_LIST_FILENAME
    empty_list_path.write_text("")
    result = pisetup.parse_components_list(file_path=str(empty_list_path))
    assert result["components_order"] == []
    assert result["all_component_data"] == {}


def test_parse_components_list_malformed_file(mock_project_structure):
    malformed_list_path = mock_project_structure / COMPONENTS_LIST_FILENAME
    malformed_list_path.write_text("invalid content [section")
    with pytest.raises(configparser.Error):
        pisetup.parse_components_list(file_path=str(malformed_list_path))


# --- Test read_selected_components ---
def test_read_selected_components_valid(mock_project_structure):
    selected_components_path = mock_project_structure / SELECTED_COMPONENTS_FILENAME
    selected_components_path.write_text("dashy mosquitto")
    selected = pisetup.read_selected_components(file_path=str(selected_components_path))
    assert selected == {"dashy", "mosquitto"}


def test_read_selected_components_empty_file(mock_project_structure):
    selected_components_path = mock_project_structure / SELECTED_COMPONENTS_FILENAME
    selected_components_path.write_text("")
    selected = pisetup.read_selected_components(file_path=str(selected_components_path))
    assert selected == set()


def test_read_selected_components_file_not_found(tmp_path, capsys):
    selected_components_path = tmp_path / SELECTED_COMPONENTS_FILENAME
    # Ensure the file does not exist
    if selected_components_path.exists():
        selected_components_path.unlink()

    selected = pisetup.read_selected_components(file_path=str(selected_components_path))
    assert selected == set()
    captured = capsys.readouterr()
    assert f"Warning: '{SELECTED_COMPONENTS_FILENAME}' not found at {selected_components_path}. Assuming no components selected." in captured.out


# --- Test generate_docker_compose_files ---
@patch('os.makedirs') # Mock makedirs to prevent actual dir creation during context setup
def test_generate_docker_compose_files_single_component(mock_makedirs, mock_project_structure, capsys):
    # Setup environment variables for rendering
    os.environ['DOMAIN'] = 'test.com'
    os.environ['PUID'] = '1001'
    os.environ['PGID'] = '1001'
    os.environ['HOST_IP'] = '192.168.1.100'
    os.environ['TZ'] = 'America/New_York'
    os.environ['REMOTE_PROJECT_PATH'] = '/home/pi/test_piselfhosting'

    # Prepare data for the function call
    parsed_data = pisetup.parse_components_list(file_path=str(mock_project_structure / COMPONENTS_LIST_FILENAME))
    all_component_data = parsed_data["all_component_data"]
    selected_components = {"dashy"}

    # Run the function
    pisetup.generate_docker_compose_files(all_component_data, selected_components)

    # Check that output directories were attempted to be created
    expected_docker_output_dir = mock_project_structure / DOCKER_COMPOSE_OUTPUT_DIR
    expected_generated_configs_dir = expected_docker_output_dir / "generated_configs"
    mock_makedirs.assert_any_call(expected_docker_output_dir, exist_ok=True)
    mock_makedirs.assert_any_call(expected_generated_configs_dir, exist_ok=True)

    # Verify generated Docker Compose file
    dashy_compose_path = expected_docker_output_dir / "docker-compose.dashy.yml"
    assert dashy_compose_path.exists()
    dashy_compose_content = dashy_compose_path.read_text()
    assert "container_name: piselfhosting-dashy" in dashy_compose_content
    assert f"- \"{GLOBAL_DATA_ROOT}/dashy/config:/app/public/conf\"" in dashy_compose_content
    assert f"- PUID=1001" in dashy_compose_content
    assert f"- PGID=1001" in dashy_compose_content
    assert f"- TZ=America/New_York" in dashy_compose_content
    assert f"- test.com:192.168.1.100" in dashy_compose_content
    assert "networks:\n  piselfhosting_net:\n    external: true" in dashy_compose_content

    # Verify unified Docker Compose file (should contain only dashy)
    unified_compose_path = expected_docker_output_dir / UNIFIED_DOCKER_COMPOSE_FILENAME
    assert unified_compose_path.exists()
    unified_compose_content = yaml.safe_load(unified_compose_path.read_text())
    assert "dashy" in unified_compose_content["services"]
    assert "piselfhosting_net" in unified_compose_content["networks"]
    assert len(unified_compose_content["services"]) == 1

    # Verify Dashy config file was generated
    dashy_config_temp_path = expected_generated_configs_dir / "dashy" / "conf.yml"
    assert dashy_config_temp_path.exists()
    dashy_config_content = dashy_config_temp_path.read_text()
    assert f"title: test.com Dashboard" in dashy_config_content
    assert f"url: http://192.168.1.100:8080" in dashy_config_content

    # Capture stdout and check JSON output for generated_config_files_to_move
    captured = capsys.readouterr()
    json_output_line = [line for line in captured.out.splitlines() if line.strip().startswith('{') and line.strip().endswith('}')][-1]
    config_map = json.loads(json_output_line)
    expected_dashy_config_final_path = os.path.join(GLOBAL_DATA_ROOT, "dashy", "config", "conf.yml").replace('\\', '/')
    assert f"/app/docker/generated_configs/dashy/conf.yml" in config_map
    assert config_map[f"/app/docker/generated_configs/dashy/conf.yml"] == expected_dashy_config_final_path


@patch('os.makedirs')
def test_generate_docker_compose_files_multiple_components(mock_makedirs, mock_project_structure, capsys):
    os.environ['DOMAIN'] = 'multi.com'
    os.environ['PUID'] = '1002'
    os.environ['PGID'] = '1002'
    os.environ['HOST_IP'] = '192.168.1.101'
    os.environ['TZ'] = 'Europe/Berlin'
    os.environ['DB_USER'] = 'multi_user'
    os.environ['DB_PASS'] = 'multi_pass'
    os.environ['PMA_HOST'] = 'multi_mariadb'
    os.environ['PHPMYADMIN_BLOWFISH_SECRET'] = 'multiblowfish'
    os.environ['REMOTE_PROJECT_PATH'] = '/home/pi/multi_piselfhosting'


    parsed_data = pisetup.parse_components_list(file_path=str(mock_project_structure / COMPONENTS_LIST_FILENAME))
    all_component_data = parsed_data["all_component_data"]
    selected_components = {"dashy", "mosquitto", "phpmyadmin"}

    pisetup.generate_docker_compose_files(all_component_data, selected_components)

    expected_docker_output_dir = mock_project_structure / DOCKER_COMPOSE_OUTPUT_DIR

    # Check individual compose files
    assert (expected_docker_output_dir / "docker-compose.dashy.yml").exists()
    assert (expected_docker_output_dir / "docker-compose.mosquitto.yml").exists()
    assert (expected_docker_output_dir / "docker-compose.phpmyadmin.yml").exists()

    # Check unified compose file
    unified_compose_path = expected_docker_output_dir / UNIFIED_DOCKER_COMPOSE_FILENAME
    assert unified_compose_path.exists()
    unified_compose_content = yaml.safe_load(unified_compose_path.read_text())

    assert "dashy" in unified_compose_content["services"]
    assert "mosquitto" in unified_compose_content["services"]
    assert "phpmyadmin" in unified_compose_content["services"]
    assert len(unified_compose_content["services"]) == 3
    assert "piselfhosting_net" in unified_compose_content["networks"]

    # Check generated config files
    mosquitto_config_temp_path = expected_docker_output_dir / "generated_configs" / "mosquitto" / "mosquitto.conf"
    assert mosquitto_config_temp_path.exists()
    mosquitto_config_content = mosquitto_config_temp_path.read_text()
    assert f"persistence_location {GLOBAL_DATA_ROOT}/mosquitto/data/" in mosquitto_config_content

    phpmyadmin_config_temp_path = expected_docker_output_dir / "generated_configs" / "phpmyadmin" / "config.inc.php"
    assert phpmyadmin_config_temp_path.exists()
    phpmyadmin_config_content = phpmyadmin_config_temp_path.read_text()
    assert f"$cfg['blowfish_secret'] = 'multiblowfish';" in phpmyadmin_config_content
    assert f"$cfg['Servers'][1]['host'] = 'multi_mariadb';" in phpmyadmin_config_content
    assert f"$cfg['Servers'][1]['user'] = 'multi_user';" in phpmyadmin_config_content
    assert f"$cfg['Servers'][1]['password'] = 'multi_pass';" in phpmyadmin_config_content

    # Check JSON output map
    captured = capsys.readouterr()
    json_output_line = [line for line in captured.out.splitlines() if line.strip().startswith('{') and line.strip().endswith('}')][-1]
    config_map = json.loads(json_output_line)
    assert len(config_map) == 3 # dashy, mosquitto, phpmyadmin configs
    assert f"/app/docker/generated_configs/dashy/conf.yml" in config_map
    assert f"/app/docker/generated_configs/mosquitto/mosquitto.conf" in config_map
    assert f"/app/docker/generated_configs/phpmyadmin/config.inc.php" in config_map


@patch('os.makedirs')
def test_generate_docker_compose_files_no_selected_components(mock_makedirs, mock_project_structure, capsys):
    os.environ['REMOTE_PROJECT_PATH'] = '/home/pi/test_piselfhosting'
    parsed_data = pisetup.parse_components_list(file_path=str(mock_project_structure / COMPONENTS_LIST_FILENAME))
    all_component_data = parsed_data["all_component_data"]
    selected_components = set()

    pisetup.generate_docker_compose_files(all_component_data, selected_components)

    expected_docker_output_dir = mock_project_structure / DOCKER_COMPOSE_OUTPUT_DIR
    assert not (expected_docker_output_dir / UNIFIED_DOCKER_COMPOSE_FILENAME).exists()

    captured = capsys.readouterr()
    assert "No individual Docker Compose files generated to merge." in captured.out
    # The JSON output should still be an empty dictionary
    json_output_line = [line for line in captured.out.splitlines() if line.strip().startswith('{') and line.strip().endswith('}')][-1]
    config_map = json.loads(json_output_line)
    assert config_map == {}

@patch('os.makedirs')
def test_generate_docker_compose_files_component_not_in_list(mock_makedirs, mock_project_structure, capsys):
    os.environ['REMOTE_PROJECT_PATH'] = '/home/pi/test_piselfhosting'
    parsed_data = pisetup.parse_components_list(file_path=str(mock_project_structure / COMPONENTS_LIST_FILENAME))
    all_component_data = parsed_data["all_component_data"]
    selected_components = {"dashy", "nonexistent_comp"} # "nonexistent_comp" is not in components_list.txt

    pisetup.generate_docker_compose_files(all_component_data, selected_components)

    captured = capsys.readouterr()
    assert "Warning: Component 'nonexistent_comp' found in selected_components.txt but not in components_list.txt. Skipping." in captured.out
    # Only dashy should be processed and unified docker-compose created
    expected_docker_output_dir = mock_project_structure / DOCKER_COMPOSE_OUTPUT_DIR
    unified_compose_path = expected_docker_output_dir / UNIFIED_DOCKER_COMPOSE_FILENAME
    assert unified_compose_path.exists()
    unified_compose_content = yaml.safe_load(unified_compose_path.read_text())
    assert "dashy" in unified_compose_content["services"]
    assert "nonexistent_comp" not in unified_compose_content["services"]


@patch('os.makedirs')
def test_generate_docker_compose_files_missing_template(mock_makedirs, mock_project_structure, capsys):
    os.environ['REMOTE_PROJECT_PATH'] = '/home/pi/test_piselfhosting'
    # Temporarily remove a template to simulate missing template scenario
    (mock_project_structure / DOCKER_COMPOSE_TEMPLATES_DIR / "mosquitto" / "docker-compose.template.yml").unlink()

    parsed_data = pisetup.parse_components_list(file_path=str(mock_project_structure / COMPONENTS_LIST_FILENAME))
    all_component_data = parsed_data["all_component_data"]
    selected_components = {"dashy", "mosquitto"}

    pisetup.generate_docker_compose_files(all_component_data, selected_components)

    captured = capsys.readouterr()
    assert "Warning: Compose Template not found for 'mosquitto'" in captured.out
    # Only dashy should be in the unified compose file
    expected_docker_output_dir = mock_project_structure / DOCKER_COMPOSE_OUTPUT_DIR
    unified_compose_path = expected_docker_output_dir / UNIFIED_DOCKER_COMPOSE_FILENAME
    assert unified_compose_path.exists()
    unified_compose_content = yaml.safe_load(unified_compose_path.read_text())
    assert "dashy" in unified_compose_content["services"]
    assert "mosquitto" not in unified_compose_content["services"]


# --- Test merge_docker_compose_files ---
def test_merge_docker_compose_files_basic(tmp_path):
    compose_file1 = tmp_path / "compose1.yml"
    compose_file1.write_text("""
services:
  service1:
    image: image1
    ports:
      - "80:80"
networks:
  mynet:
    external: true
""")
    compose_file2 = tmp_path / "compose2.yml"
    compose_file2.write_text("""
services:
  service2:
    image: image2
    volumes:
      - "vol2:/data"
volumes:
  vol2:
networks:
  anothernet:
    external: true
""")
    output_path = tmp_path / "unified-compose.yml"
    pisetup.merge_docker_compose_files([str(compose_file1), str(compose_file2)], str(output_path))

    assert output_path.exists()
    unified_content = yaml.safe_load(output_path.read_text())

    assert "service1" in unified_content["services"]
    assert "service2" in unified_content["services"]
    assert unified_content["services"]["service1"]["image"] == "image1"
    assert unified_content["services"]["service2"]["image"] == "image2"

    assert "vol2" in unified_content["volumes"]
    assert "mynet" in unified_content["networks"]
    assert "anothernet" in unified_content["networks"]


def test_merge_docker_compose_files_conflicting_services(tmp_path, capsys):
    compose_file1 = tmp_path / "compose1.yml"
    compose_file1.write_text("""
services:
  conflicting_service:
    image: image1
""")
    compose_file2 = tmp_path / "compose2.yml"
    compose_file2.write_text("""
services:
  conflicting_service:
    image: image2
""")
    output_path = tmp_path / "unified-compose.yml"
    pisetup.merge_docker_compose_files([str(compose_file1), str(compose_file2)], str(output_path))

    unified_content = yaml.safe_load(output_path.read_text())
    assert unified_content["services"]["conflicting_service"]["image"] == "image2" # Last one wins
    captured = capsys.readouterr()
    assert "Warning: Duplicate service name 'conflicting_service' found" in captured.out


def test_merge_docker_compose_files_conflicting_volumes_networks(tmp_path, capsys):
    compose_file1 = tmp_path / "compose1.yml"
    compose_file1.write_text("""
volumes:
  my_volume:
    name: vol_from_1
networks:
  my_network:
    name: net_from_1
""")
    compose_file2 = tmp_path / "compose2.yml"
    compose_file2.write_text("""
volumes:
  my_volume:
    name: vol_from_2
networks:
  my_network:
    name: net_from_2
""")
    output_path = tmp_path / "unified-compose.yml"
    pisetup.merge_docker_compose_files([str(compose_file1), str(compose_file2)], str(output_path))

    unified_content = yaml.safe_load(output_path.read_text())
    assert unified_content["volumes"]["my_volume"]["name"] == "vol_from_1" # First one wins
    assert unified_content["networks"]["my_network"]["name"] == "net_from_1" # First one wins

    captured = capsys.readouterr()
    assert "Warning: Volume 'my_volume' in" in captured.out
    assert "Warning: Network 'my_network' in" in captured.out


def test_merge_docker_compose_files_empty_list(tmp_path):
    output_path = tmp_path / "unified-compose.yml"
    pisetup.merge_docker_compose_files([], str(output_path))
    assert output_path.exists()
    unified_content = yaml.safe_load(output_path.read_text())
    assert unified_content == {
        'services': {},
        'volumes': {},
        'networks': {}
    }


def test_merge_docker_compose_files_invalid_yaml(tmp_path, capsys):
    compose_file1 = tmp_path / "compose1.yml"
    compose_file1.write_text("services: - invalid: yaml") # Malformed YAML
    output_path = tmp_path / "unified-compose.yml"
    pisetup.merge_docker_compose_files([str(compose_file1)], str(output_path))
    captured = capsys.readouterr()
    assert "Error parsing YAML from" in captured.err # Should go to stderr due to exception
    assert not (tmp_path / "unified-compose.yml").exists() # Should not create an empty file from error


def test_generate_docker_compose_files_traefik_dashboard_domain(mock_project_structure, capsys):
    os.environ['DOMAIN'] = 'myhome.org'
    os.environ['PUID'] = '1000'
    os.environ['PGID'] = '1000'
    os.environ['HOST_IP'] = '192.168.1.5'
    os.environ['TZ'] = 'Europe/Amsterdam'
    os.environ['REMOTE_PROJECT_PATH'] = '/home/pi/test_piselfhosting'

    # Add a dummy Traefik template, even if its content isn't fully robust
    traefik_template_dir = mock_project_structure / DOCKER_COMPOSE_TEMPLATES_DIR / "traefik"
    traefik_template_dir.mkdir(exist_ok=True)
    (traefik_template_dir / "docker-compose.template.yml").write_text(
        """
services:
  traefik:
    image: traefik:latest
    container_name: piselfhosting-traefik
    command:
      - "--api.dashboard=true"
      - "--api.insecure=true"
    ports:
      - "80:80"
      - "8080:8080" # Dashboard port for insecure access
    networks:
      - piselfhosting_net
networks:
  piselfhosting_net:
    external: true
        """
    )
    # Update components_list.txt to include traefik
    components_list_path = mock_project_structure / COMPONENTS_LIST_FILENAME
    with open(components_list_path, 'a') as f:
        f.write("""
[traefik]
description = Edge Router for services.
has_ui = True
ui_port = 8080
icon = fas fa-traffic-light
protocol = http
        """)

    parsed_data = pisetup.parse_components_list(file_path=str(components_list_path))
    all_component_data = parsed_data["all_component_data"]
    selected_components = {"dashy", "traefik"}

    pisetup.generate_docker_compose_files(all_component_data, selected_components)

    # Check unified Docker Compose file for TRAEFIK_DASHBOARD_DOMAIN context
    unified_compose_path = mock_project_structure / DOCKER_COMPOSE_OUTPUT_DIR / UNIFIED_DOCKER_COMPOSE_FILENAME
    assert unified_compose_path.exists()
    unified_compose_content = yaml.safe_load(unified_compose_path.read_text())

    # The TRAEFIK_DASHBOARD_DOMAIN context variable itself is used in Jinja templates.
    # The actual 'traefik' service in the generated compose will contain a specific configuration related to it.
    # For this test, we verify that 'traefik.myhome.org' appears in the rendered output,
    # specifically in the context variables which are printed as DEBUG info by generate_docker_compose_files.
    captured = capsys.readouterr()
    assert "'TRAEFIK_DASHBOARD_DOMAIN': 'traefik.myhome.org'" in captured.out