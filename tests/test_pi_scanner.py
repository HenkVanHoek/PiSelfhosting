# tests/test_pi_scanner.py
import pytest
from unittest.mock import patch, MagicMock
import sys
import os
import paramiko

# Ensure the 'src' directory is on the path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
src_path = os.path.join(project_root, 'src')
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from src.pi_scanner import PiScanner


@pytest.fixture
def mock_nmap_text_output():
    """Provides a fake nmap plain text output string for testing."""
    return """
Nmap scan report for 192.168.1.15
Host is up (0.0021s latency).
MAC Address: E4:5F:01:AA:BB:CC (Raspberry Pi Foundation)

Nmap scan report for 192.168.1.20
Host is up (0.0030s latency).
MAC Address: 00:1A:2B:3C:4D:5E (SomeOther Inc)
"""


@patch('src.pi_scanner.subprocess.run')
def test_scan_with_nmap_finds_pi(mock_run, mock_nmap_text_output):
    """
    Tests if the scanner can correctly parse mocked nmap plain text output.
    """
    # Configure the mock to return the plain text output
    mock_run.return_value = MagicMock(stdout=mock_nmap_text_output, stderr="", returncode=0)

    found_pis = PiScanner.scan('192.168.1.0/24')

    assert len(found_pis) == 1
    found_pi = found_pis[0]
    assert found_pi['ip'] == '192.168.1.15'
    # Assert that the MAC address was correctly lowercased by the scan method
    assert found_pi['mac'] is not None, "MAC-adres Not found. Returned value is None"

    assert found_pi['mac'].lower() == 'e4:5f:01:aa:bb:cc'


def test_scan_handles_nmap_not_found():
    """Tests that the scanner handles the case where nmap is not installed."""
    with patch('subprocess.run', side_effect=FileNotFoundError):
        found_pis = PiScanner.scan('192.168.1.0/24')
    assert found_pis == []


@patch('src.pi_scanner.PiScanner._is_port_open', return_value=True)
@patch('paramiko.SSHClient')
def test_get_device_details_success(mock_ssh_client_class, mock_is_port_open):
    """Tests successful retrieval of device details via SSH."""
    mock_ssh_instance = MagicMock()
    mock_ssh_client_class.return_value = mock_ssh_instance
    fake_output = (
        "Raspberry Pi 5 Model B\x00\n---\n"
        "8GiB\n---\n"
        "10000000abcdef\n---\n"
        '{"blockdevices":[{"name":"sda","size":"128G","type":"disk","mountpoint":"/"}]}'
    )
    mock_stdout = MagicMock()
    mock_stdout.read.return_value = fake_output.encode()
    mock_ssh_instance.exec_command.return_value = (None, mock_stdout, None)

    details = PiScanner.get_device_details('192.168.1.50', 'pi', 'raspberry')

    mock_is_port_open.assert_called_once_with('192.168.1.50', 22)
    mock_ssh_instance.connect.assert_called_once_with(
        hostname='192.168.1.50', username='pi', password='raspberry', timeout=5
    )
    assert details is not None
    assert details['model'] == 'Raspberry Pi 5 Model B'
    assert details['serial'] == '10000000abcdef'


@patch('src.pi_scanner.PiScanner._is_port_open', return_value=False)
@patch('paramiko.SSHClient')
def test_get_device_details_ssh_port_closed(mock_ssh_client_class, mock_is_port_open):
    """Tests that get_device_details skips SSH if the port is closed."""
    details = PiScanner.get_device_details('192.168.1.51', 'pi', 'raspberry')
    mock_is_port_open.assert_called_once_with('192.168.1.51', 22)
    mock_ssh_client_class.return_value.connect.assert_not_called()
    assert details is None


@pytest.mark.parametrize(
    "raised_exception",
    [paramiko.AuthenticationException, paramiko.SSHException, TimeoutError]
)
@patch('src.pi_scanner.PiScanner._is_port_open', return_value=True)
@patch('paramiko.SSHClient')
def test_get_device_details_ssh_connection_fails(mock_ssh_client_class, mock_is_port_open, raised_exception):
    """Tests that SSH connection failures are handled gracefully."""
    mock_ssh_instance = MagicMock()
    mock_ssh_client_class.return_value = mock_ssh_instance
    mock_ssh_instance.connect.side_effect = raised_exception

    details = PiScanner.get_device_details('192.168.1.52', 'user', 'pass')

    assert details is None
    mock_ssh_instance.close.assert_called_once()
