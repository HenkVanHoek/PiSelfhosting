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

@patch("configurator_app.app.PiScanner")
def test_scan_pis_success(mock_scanner_class, client):
    """Test the /scan-pis endpoint successfully."""
    mock_scanner_instance = mock_scanner_class.return_value
    # Updated to return 4 values matching the actual method signature
    mock_scanner_instance.scan.return_value = (
        [
            {
                "ip": "192.168.1.10",
                "mac": "ab:cd",
                "hostname": "raspberrypi",
                "vendor": "Raspberry Pi Foundation",
            }
        ],
        ["🔍 Scanning network..."],
        "",
        {"success": True, "method_used": "user_provided", "subnet": "192.168.1.0/24"},
    )

    response = client.post(
        "/scan-pis",
        json={"subnet": "192.168.1.0/24", "username": "user", "password": "pass"},
    )
    assert response.status_code == 200
    data = response.get_json()
    assert len(data["hosts"]) == 1
    assert data["hosts"][0]["ip"] == "192.168.1.10"


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
