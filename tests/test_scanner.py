import socket
from unittest.mock import MagicMock, patch

# Directly import the public function from the module
from src.pi_scanner import is_port_open


@patch("src.pi_scanner.socket.socket")
def test_is_port_open_success(mock_socket_class):
    """Tests is_port_open returns True when the port is open."""
    # Configure the mock to work correctly with a 'with' statement
    mock_sock_instance = MagicMock()
    mock_sock_instance.connect_ex.return_value = 0  # 0 means success
    mock_socket_class.return_value.__enter__.return_value = mock_sock_instance

    # Call the function directly
    assert is_port_open("127.0.0.1", 22) is True
    mock_sock_instance.connect_ex.assert_called_once_with(("127.0.0.1", 22))


@patch("src.pi_scanner.socket.socket")
def test_is_port_open_failure(mock_socket_class):
    """Tests is_port_open returns False when the port is closed."""
    mock_sock_instance = MagicMock()
    mock_sock_instance.connect_ex.return_value = 111  # Connection refused
    mock_socket_class.return_value.__enter__.return_value = mock_sock_instance

    assert is_port_open("127.0.0.1", 22) is False
    mock_sock_instance.connect_ex.assert_called_once_with(("127.0.0.1", 22))


@patch("src.pi_scanner.socket.socket")
def test_is_port_open_invalid_host(mock_socket_class):
    """Tests is_port_open handles invalid hostnames gracefully."""
    mock_sock_instance = MagicMock()
    # Simulate an error being raised when trying to connect
    mock_sock_instance.connect_ex.side_effect = socket.gaierror
    mock_socket_class.return_value.__enter__.return_value = mock_sock_instance

    assert is_port_open("invalid-hostname", 22) is False
