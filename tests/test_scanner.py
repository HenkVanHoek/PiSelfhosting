# tests/test_scanner.py
import socket
from unittest.mock import MagicMock, patch

from src.pi_scanner import PiScanner


@patch("src.pi_scanner.subprocess.run")
def test_scan_handles_no_devices_found(mock_run):
    """Tests that the scanner returns an empty list when nmap finds no hosts."""
    mock_run.return_value = MagicMock(
        stdout="Nmap done: 0 IP addresses (0 hosts up) scanned",
        stderr="",
        returncode=0,
    )
    found_pis = PiScanner.scan("192.168.1.0/24")
    assert found_pis == []


@patch("src.pi_scanner.subprocess.run")
def test_scan_handles_nmap_error(mock_run):
    """Tests that the scanner handles a non-zero exit code from nmap."""
    mock_run.return_value = MagicMock(stdout="", stderr="Some nmap error", returncode=1)
    found_pis = PiScanner.scan("192.168.1.0/24")
    assert found_pis == []


@patch("src.pi_scanner.socket.socket")
def test_is_port_open_success(mock_socket_class):
    """Tests _is_port_open returns True when the port is open."""
    mock_sock_instance = mock_socket_class.return_value
    mock_sock_instance.connect_ex.return_value = 0  # 0 means success
    assert PiScanner._is_port_open("127.0.0.1", 22) is True
    mock_sock_instance.connect_ex.assert_called_once_with(("127.0.0.1", 22))


@patch("src.pi_scanner.socket.socket")
def test_is_port_open_failure(mock_socket_class):
    """Tests _is_port_open returns False when the port is closed."""
    mock_sock_instance = mock_socket_class.return_value
    mock_sock_instance.connect_ex.return_value = 111  # Connection refused
    assert PiScanner._is_port_open("127.0.0.1", 22) is False


@patch("src.pi_scanner.socket.socket")
def test_is_port_open_invalid_host(mock_socket_class):
    """Tests _is_port_open handles invalid hostnames gracefully."""
    mock_sock_instance = mock_socket_class.return_value
    mock_sock_instance.connect_ex.side_effect = socket.gaierror
    assert PiScanner._is_port_open("invalid-hostname", 22) is False
