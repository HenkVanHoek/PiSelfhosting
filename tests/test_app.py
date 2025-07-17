# tests/test_app.py
import re
from unittest.mock import MagicMock, patch

import pytest
from flask import session

# Assuming your Flask app and factories are in 'src.configurator_app.app'
from configurator_app.app import create_app
from managers.component_manager import ComponentManager
from managers.setup_manager import SetupManager


@pytest.fixture
def mock_component_manager():
    """Fixture to create a mock ComponentManager."""
    mock_manager = MagicMock(spec=ComponentManager)
    # Define the mock data that the manager will return
    mock_manager.get_all_components.return_value = {
        "comp1": {
            "name": "Component 1",
            "default": True,
            "uniqueness_group": "group_a",
        },
        "comp2": {
            "name": "Component 2",
            "default": False,
            "uniqueness_group": "group_a",
        },
        "comp3": {
            "name": "Component 3",
            "default": True,
            "uniqueness_group": "group_b",
        },
        "comp4": {
            "name": "Component 4",
            "default": False,
            "uniqueness_group": "group_b",
        },
    }
    mock_manager.get_uniqueness_groups.return_value = {
        "group_a": ["comp1", "comp2"],
        "group_b": ["comp3", "comp4"],
    }
    return mock_manager


@pytest.fixture
def mock_setup_manager():
    """Fixture to create a mock SetupManager."""
    return MagicMock(spec=SetupManager)


@pytest.fixture
def client(mock_component_manager, mock_setup_manager):
    """Factory to create a Flask app for tests, with mocked managers."""
    # Pass the mock manager to the app factory
    app = create_app(
        component_manager_instance=mock_component_manager,
        setup_manager_instance=mock_setup_manager,
    )
    app.config["TESTING"] = True
    # Provide a secret key for session management during tests
    app.config["SECRET_KEY"] = "test-secret-key"
    with app.test_client() as client:
        yield client


def test_index_get(client, mock_component_manager):
    """Test the main page (GET request)."""
    response = client.get("/")
    assert response.status_code == 200
    mock_component_manager.get_all_components.assert_called_once()
    mock_component_manager.get_uniqueness_groups.assert_called_once()

    data = response.data.decode()

    # Robust check for checked boxes, ignoring whitespace issues.
    # We find the input tag and check if 'checked' is present.
    comp1_input = re.search(r'<input[^>]+id="check-comp1"[^>]*>', data).group(0)
    assert "checked" in comp1_input

    comp2_input = re.search(r'<input[^>]+id="check-comp2"[^>]*>', data).group(0)
    assert "checked" not in comp2_input

    comp3_input = re.search(r'<input[^>]+id="check-comp3"[^>]*>', data).group(0)
    assert "checked" in comp3_input

    comp4_input = re.search(r'<input[^>]+id="check-comp4"[^>]*>', data).group(0)
    assert "checked" not in comp4_input


def test_index_post_success(client, mock_setup_manager):
    """Test successful form submission."""
    response = client.post(
        "/", data={"selected_components": ["comp1", "comp3"]}, follow_redirects=True
    )
    assert response.status_code == 200  # After redirect
    mock_setup_manager.generate_all_files.assert_called_once()
    assert b"Configuration files generated successfully!" in response.data


def test_index_post_no_selection(client, mock_setup_manager):
    """Test form submission with no components selected."""
    response = client.post("/", data={}, follow_redirects=True)
    assert response.status_code == 200  # After redirect
    mock_setup_manager.generate_all_files.assert_not_called()
    assert b"Please select at least one component." in response.data


@patch("configurator_app.app.PiScanner")
def test_scan_pis_success(mock_scanner, client):
    """Test the /scan-pis endpoint successfully."""
    mock_scanner_instance = mock_scanner.return_value
    mock_scanner_instance.scan.return_value = [{"ip": "192.168.1.10", "mac": "ab:cd"}]

    response = client.post(
        "/scan-pis",
        json={"subnet": "192.168.1.0/24", "username": "user", "password": "pass"},
    )
    assert response.status_code == 200
    assert response.json == [{"ip": "192.168.1.10", "mac": "ab:cd"}]


def test_scan_pis_missing_params(client):
    """Test the /scan-pis endpoint with missing parameters."""
    response = client.post("/scan-pis", json={"subnet": "192.168.1.0/24"})
    assert response.status_code == 400


def test_set_ip_address_success(client):
    """Test the /set-ip endpoint successfully."""
    response = client.post("/set-ip", json={"ip": "192.168.1.10"})
    assert response.status_code == 200
    assert response.json == {"message": "IP address set successfully"}
    # Check the session variable to ensure it's correctly set.
    assert session["target_ip"] == "192.168.1.10"


def test_set_ip_address_no_ip(client):
    """Test the /set-ip endpoint with no IP provided."""
    response = client.post("/set-ip", json={})
    assert response.status_code == 400
