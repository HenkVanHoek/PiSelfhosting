import json
from unittest.mock import MagicMock, patch

import pytest

# Ensure the app module can be found
from configurator_app.app import create_app


@pytest.fixture
def mock_paths(tmp_path):
    """Creates a dictionary of temporary paths for mock files."""
    config_dir = tmp_path / "config"
    template_dir = tmp_path / "templates"
    config_dir.mkdir()
    template_dir.mkdir()

    return {
        "root": tmp_path,
        "config_dir": config_dir,
        "template_dir": template_dir,
        "metadata_file": config_dir / "components_metadata.json",
        "default_components_file": config_dir / "default_selected_components.txt",
        "output_file": tmp_path / "selected_components.txt",
        "env_file": tmp_path / ".env",
    }


@pytest.fixture
def app(mock_paths):
    """Create and configure a new app instance for each test."""
    mock_components = {
        "_piselfhosting": {"components_order": ["portainer", "dashy"]},
        "dashy": {
            "name": "Dashy",
            "description": "A dashboard.",
            "dashy_section": "Dashboards",
            "uniqueness_group": None,
        },
        "portainer": {
            "name": "Portainer",
            "description": "Container management.",
            "dashy_section": "Utilities",
            "uniqueness_group": None,
        },
    }
    mock_paths["metadata_file"].write_text(json.dumps(mock_components))

    mock_paths["default_components_file"].write_text("dashy")

    # Create dummy template files
    (mock_paths["template_dir"] / "select_pi.html").write_text(
        "<h1>Step 1: Find Your Raspberry Pi</h1>"
    )

    select_components_template = """
    <h1>Step 2: Select Components for {{ pi_ip }}</h1>
    {% for group_name, component_list in grouped_components.items() %}
        <h2>{{ group_name }}</h2>
        {% for component in component_list %}
            <label>
                <input type="checkbox" name="components" value="{{ component.id }}"
                 data-component-id="{{ component.id }}"
                 {% if component.id in default_components %}checked{% endif %}>
                <strong>{{ component.data.name }}</strong>
            </label>
        {% endfor %}
    {% endfor %}
    """
    (mock_paths["template_dir"] / "select_components.html").write_text(
        select_components_template
    )

    (mock_paths["template_dir"] / "install_success.html").write_text(
        '<h1>Ready to Install</h1><a href="/live-log">Start Installation</a>'
    )
    (mock_paths["template_dir"] / "live_log.html").write_text(
        '<h1>Live Log</h1><pre id="log-output"></pre>'
    )

    app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret-key",
            "METADATA_FILE": str(mock_paths["metadata_file"]),
            "DEFAULT_COMPONENTS_FILE": str(mock_paths["default_components_file"]),
            "SELECTED_COMPONENTS_OUTPUT_FILE": str(mock_paths["output_file"]),
            "ENV_PATH": str(mock_paths["env_file"]),
        }
    )

    app.template_folder = str(mock_paths["template_dir"])
    yield app


@pytest.fixture
def client(app):
    """A test client for the app."""
    return app.test_client()


def test_index_redirects_to_select_pi_when_no_pi_in_session(client):
    """
    GIVEN a Flask client
    WHEN the '/' page is requested and no Pi IP is in the session
    THEN check that the "Select a Pi" page is rendered.
    """
    response = client.get("/")
    assert response.status_code == 200
    assert b"<h1>Step 1: Find Your Raspberry Pi</h1>" in response.data


def test_index_shows_components_and_checks_defaults_when_pi_in_session(client):
    """
    GIVEN a Flask client with a Pi IP in session
    WHEN the '/' page is requested
    THEN check that the components page is rendered and default components are checked.
    """
    with client.session_transaction() as sess:
        sess["target_pi_ip"] = "192.168.1.100"

    response = client.get("/")
    assert response.status_code == 200
    assert b"<h1>Step 2: Select Components for 192.168.1.100</h1>" in response.data
    assert b"Dashy" in response.data
    assert b"Portainer" in response.data

    assert (
        b'<input type="checkbox" '
        b'name="components" '
        b'value="dashy" '
        b'data-component-id="dashy"  checked>' in response.data
    )
    assert (
        b'<input type="checkbox" '
        b'name="components" '
        b'value="portainer" '
        b'data-component-id="portainer" >' in response.data
    )


@patch("configurator_app.app.PiScanner.get_device_details")
@patch("configurator_app.app.PiScanner.scan")
def test_scan_network_endpoint(mock_scan, mock_get_details, client):
    """
    GIVEN mocked PiScanner methods
    WHEN the '/scan' endpoint is called
    THEN check that the scanner is called and returns a structured response.
    """
    mock_scan.return_value = [{"ip": "192.168.1.101", "mac": "e4:5f:01:aa:bb:cc"}]
    mock_get_details.return_value = {
        "model": "Raspberry Pi 5",
        "ram": "8GiB",
        "serial": "10000000abcdef",
        "disks": [],
    }

    response = client.post(
        "/scan",
        json={"subnet": "192.168.1.0/24", "username": "pi", "password": "raspberry"},
    )

    assert response.status_code == 200
    mock_scan.assert_called_once_with(target_subnet="192.168.1.0/24")
    mock_get_details.assert_called_once_with("192.168.1.101", "pi", "raspberry")
    assert "10000000abcdef" in response.json["success"]


@patch("configurator_app.app.PiScanner.get_device_details")
def test_get_details_endpoint_success(mock_get_details, client):
    """
    GIVEN a mocked PiScanner.get_device_details
    WHEN the '/get-details' endpoint is called for a retry
    THEN check that it returns the correct device data on success.
    """
    mock_details = {"serial": "54321", "model": "Pi 4", "ram": "4GB", "disks": []}
    mock_get_details.return_value = mock_details

    response = client.post(
        "/get-details",
        json={
            "ip": "192.168.1.105",
            "mac": "11:22:33:44:55:66",
            "username": "new_user",
            "password": "new_password",
        },
    )

    assert response.status_code == 200
    data = response.get_json()
    assert "54321" in data["success"]
    assert data["success"]["54321"]["model"] == "Pi 4"
    mock_get_details.assert_called_once_with(
        "192.168.1.105", "new_user", "new_password"
    )


def test_select_pi_saves_ip_and_redirects(client):
    """
    GIVEN a Flask client
    WHEN a POST request is made to '/select-pi' with an IP address
    THEN check that the IP is stored in the session and the user is redirected.
    """
    response = client.post("/select-pi", data={"pi_ip": "192.168.1.102"})

    assert response.status_code == 302
    assert response.headers["Location"] == "/"

    with client.session_transaction() as sess:
        assert sess["target_pi_ip"] == "192.168.1.102"


@patch("configurator_app.app.set_key")
def test_save_and_install_shows_success_page(mock_set_key, client, mock_paths):
    """
    GIVEN a mocked set_key function and a client with a Pi IP in session
    WHEN a POST request is made to '/save-and-install'
    THEN check that the success page with a link to the live log is shown.
    """
    with client.session_transaction() as sess:
        sess["target_pi_ip"] = "192.168.1.103"

    form_data = {
        "components": ["dashy", "portainer"],
        "ssh_user": "pi",
        "ssh_pass": "raspberry",
    }

    response = client.post("/save-and-install", data=form_data)

    assert response.status_code == 200
    assert b"<h1>Ready to Install</h1>" in response.data
    assert b'<a href="/live-log">' in response.data

    output_file = mock_paths["output_file"]
    assert output_file.exists()
    assert "dashy portainer" in output_file.read_text()

    env_path = str(mock_paths["env_file"])
    mock_set_key.assert_any_call(env_path, "PI_IP", "192.168.1.103")


@patch("configurator_app.app.os.path.exists", return_value=True)
@patch("configurator_app.app.subprocess.Popen")
def test_install_stream_success(mock_popen, _mock_exists, client):
    """
    GIVEN a mocked subprocess.Popen that simulates a successful script run
    WHEN the '/install-stream' endpoint is called
    THEN check that it streams the subprocess output correctly in SSE format.
    """
    mock_process = MagicMock()
    mock_process.stdout.readline.side_effect = [
        "Starting installation...\n",
        "Step 1: Doing something...\n",
        "",
    ]
    mock_process.wait.return_value = 0
    mock_popen.return_value = mock_process

    response = client.get("/install-stream")

    assert response.status_code == 200
    assert response.mimetype == "text/event-stream"

    streamed_data = response.data.decode("utf-8")
    expected_content = (
        "data: Starting installation...\n\n"
        "data: Step 1: Doing something...\n\n"
        "data: \n--- SCRIPT FINISHED (Exit Code: 0) ---\n\n"
    )
    assert streamed_data == expected_content
