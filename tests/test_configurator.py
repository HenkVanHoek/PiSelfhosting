import json
from unittest.mock import MagicMock, patch

import pytest

from configurator_app.app import create_app
from src.component_manager import ComponentManager

# from flask import session


@pytest.fixture
def mock_component_manager():
    """
    Fixture to create a mock ComponentManager with some default data.
    This prevents tests from needing a real 'components_metadata.json' file.
    """
    # Create an instance of a MagicMock that can be configured per-test
    manager = MagicMock(spec=ComponentManager)

    # Define some default components to be returned by the mock
    manager.get_all_components.return_value = {
        "comp1": {"name": "Component 1", "description": "First component."},
        "comp2": {"name": "Component 2", "description": "Second component."},
    }
    manager.get_uniqueness_groups.return_value = {}
    manager.get_component_details.return_value = {}

    return manager


@pytest.fixture
def mock_pi_scanner(mocker):
    """
    Fixture to patch the PiScanner class.
    This prevents tests from performing real network scans.
    """
    # We patch the PiScanner where it's imported and used in the app
    return mocker.patch("configurator_app.app.PiScanner")


@pytest.fixture
def app(mock_component_manager, mock_pi_scanner):
    """
    Fixture to create the Flask app instance for testing.
    Injects the mocked ComponentManager.
    """
    # Pass the mock manager to the app factory
    app = create_app(component_manager=mock_component_manager)

    # Configure testing mode on the app's config object
    app.config["TESTING"] = True

    # Set a secret key for session handling in tests
    app.config["SECRET_KEY"] = "test-secret-key"
    return app


@pytest.fixture
def client(app):
    """
    Fixture to create a test client for the Flask app.
    This client can be used to make requests to the app's endpoints.
    """
    return app.test_client()


# --- Route Tests ---


def test_index_redirects_to_select_pi_when_no_ip_in_session(client, mock_pi_scanner):
    """
    GIVEN a Flask client
    WHEN the '/' page is requested and no IP is in the session
    THEN check that the 'select_pi.html' template is rendered.
    """
    # Configure the mock to return a value for subnet detection
    mock_pi_scanner.detect_subnet.return_value = "192.168.1.0/24"
    response = client.get("/")

    # Assert that the response is successful and contains expected text
    assert response.status_code == 200
    assert b"Step 1: Find Your Pi" in response.data


def test_index_shows_components_when_ip_is_in_session(client):
    """
    GIVEN a Flask client with a target IP in the session
    WHEN the '/' page is requested
    THEN check that the 'select_components.html' template is
    rendered with component data.
    """
    # Use the client's session transaction to set the target IP
    with client.session_transaction() as sess:
        sess["target_pi_ip"] = "192.168.1.101"

    response = client.get("/")

    # Assert that the response is successful and contains expected text
    assert response.status_code == 200
    assert b"Step 2: Select Components" in response.data


def test_scan_network_success(client, mock_pi_scanner):
    """
    GIVEN a mocked PiScanner
    WHEN a POST request is made to '/scan'
    THEN check that the scanner is called and returns JSON data.
    """
    # Configure the mock to return a successful scan result
    mock_pi_scanner.scan.return_value = (
        [{"ip": "192.168.1.101", "mac": "b8:27:eb:xx:xx:xx"}],
        "Nmap output",
        "",
    )
    # Configure the mock to return device details
    # Note: We configure the *mock class instance* for instance methods
    mock_pi_scanner.return_value.get_device_details.return_value = {
        "serial": "12345",
        "model": "Pi 4",
    }

    response = client.post(
        "/scan",
        json={
            "subnet": "192.168.1.0/24",
            "username": "pi",
            "password": "raspberry",
        },
    )

    # Assert that the response is successful and contains the correct data
    assert response.status_code == 200
    data = json.loads(response.data)
    assert "pis" in data
    assert len(data["pis"]) == 1
    assert data["pis"][0]["ip"] == "192.168.1.101"
    assert data["pis"][0]["details"]["model"] == "Pi 4"


def test_scan_network_nmap_error(client, mock_pi_scanner):
    """
    GIVEN a mocked PiScanner that returns an error
    WHEN a POST request is made to '/scan'
    THEN check that a 500 error is returned.
    """
    # Configure the mock to simulate an nmap error
    mock_pi_scanner.scan.return_value = ([], "", "nmap error")

    response = client.post(
        "/scan", json={"subnet": "192.168.1.0/24", "username": "pi", "password": "a"}
    )
    assert response.status_code == 500
    assert b"nmap error" in response.data


def test_get_details_for_ip_success(client, mock_pi_scanner):
    """
    GIVEN a mocked PiScanner
    WHEN a POST request is made to '/get-details'
    THEN check that the scanner is called and returns JSON data.
    """
    # Configure the mock to return successful device details
    mock_pi_scanner.return_value.get_device_details.return_value = {
        "serial": "67890",
        "model": "Pi 3B+",
        "ram": "1GB",
        "disks": [],
    }

    response = client.post(
        "/get-details", json={"ip": "192.168.1.102", "username": "user", "password": ""}
    )
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["serial"] == "67890"


def test_get_details_for_ip_failure(client, mock_pi_scanner):
    """
    GIVEN a mocked PiScanner that fails to get details
    WHEN a POST request is made to '/get-details'
    THEN check that a 500 error is returned.
    """
    # Configure the mock to simulate a failure
    mock_pi_scanner.return_value.get_device_details.return_value = None

    response = client.post(
        "/get-details", json={"ip": "192.168.1.103", "username": "u", "password": "p"}
    )
    assert response.status_code == 500
    assert b"Failed to get details" in response.data


def test_set_ip_address_success(client):
    """
    GIVEN a client
    WHEN a POST request is made to '/set-ip'
    THEN check that the IP is stored in the session and returns success.
    """
    response = client.post("/set-ip", json={"ip": "192.168.1.104"})
    assert response.status_code == 200
    # FIX: Check session within the test client's context to avoid RuntimeError
    with client.session_transaction() as sess:
        assert sess.get("target_pi_ip") == "192.168.1.104"


def test_set_ip_address_no_ip(client):
    """
    GIVEN a client
    WHEN a POST request is made to '/set-ip' without an IP
    THEN check that a 400 error is returned.
    """
    response = client.post("/set-ip", json={})
    assert response.status_code == 400
    assert b"IP address is required" in response.data


@patch("configurator_app.app.set_key")
def test_save_and_install_success(mock_set_key, client, app):
    """
    GIVEN a client with a target IP in the session
    WHEN a POST request is made to '/save-and-install'
    THEN check that files and env vars are saved and the success template is rendered.
    """
    with client.session_transaction() as sess:
        sess["target_pi_ip"] = "192.168.1.105"

    # Add a dummy route for 'live_log' to prevent BuildError during template rendering
    if not any(rule.endpoint == "live_log" for rule in app.url_map.iter_rules()):

        @app.route("/live-log-dummy")
        def live_log():
            return "Dummy log page"

        # Point url_for to the dummy to avoid interfering with other tests
        with app.app_context():
            with app.test_request_context():
                import flask

                original_url_for = flask.url_for

                def patched_url_for(endpoint, **values):
                    if endpoint == "live_log":
                        return original_url_for("live_log", **values)
                    return original_url_for(endpoint, **values)

                flask.url_for = patched_url_for

    response = client.post(
        "/save-and-install",
        data={
            "components": ["comp1", "comp2"],
            "ssh_user": "test_user",
            "ssh_pass": "test_pass",
        },
    )

    assert response.status_code == 200
    assert b"Configuration Saved!" in response.data

    # FIX: Use the full path from the app config for the assertion
    env_path = app.config["ENV_PATH"]
    mock_set_key.assert_any_call(env_path, "SSH_USER", "test_user")
    mock_set_key.assert_any_call(env_path, "SSH_PASSWORD", "test_pass")


def test_save_and_install_no_ip(client):
    """
    GIVEN a client without a target IP in the session
    WHEN a POST request is made to '/save-and-install'
    THEN check that the user is redirected to the start page.
    """
    response = client.post("/save-and-install", data={"components": ["comp1"]})
    assert response.status_code == 302
    assert response.location == "/"


def test_save_and_install_no_components(client):
    """
    GIVEN a client with a target IP in the session
    WHEN a POST request is made to '/save-and-install' with no components
    THEN check that a 400 error is returned.
    """
    with client.session_transaction() as sess:
        sess["target_pi_ip"] = "192.168.1.106"

    response = client.post("/save-and-install", data={"components": []})
    assert response.status_code == 400
    assert b"At least one component must be selected" in response.data


# --- ComponentManager Interaction Test ---
def test_generate_docs_endpoint(client, mock_component_manager):
    """
    GIVEN a mocked ComponentManager
    WHEN the '/generate-docs' endpoint is requested
    THEN check that the documentation generation is called.
    """
    response = client.post("/generate-docs")
    # FIX: The endpoint redirects, so the status code should be 302
    assert response.status_code == 302
    assert response.location == "/"

    # Assert that the mock manager's method was called
    mock_component_manager.generate_docs.assert_called_once()
