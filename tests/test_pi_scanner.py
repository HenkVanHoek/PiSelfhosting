# tests/test_pi_scanner.py
import pytest
from unittest.mock import patch, MagicMock
import sys
import os
import paramiko
import json

# Ensure the 'src' directory is on the path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
src_path = os.path.join(project_root, 'src')
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from src.pi_scanner import PiScanner


@pytest.fixture
def mock_nmap_xml_output():
    """Provides a fake nmap XML output string for testing."""
    # FIX: Removed the leading blank line.
    return """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE nmaprun>
<nmaprun scanner="nmap" args="nmap -sn -oX - 192.168.1.0/24" start="1672531200">
<host>
    <status state="up" reason="arp-response"/>
    <address addr="192.168.1.15" addrtype="ipv4"/>
    <address addr="E4:5F:01:AA:BB:CC" addrtype="mac" vendor="Raspberry Pi Foundation"/>
</host>
<host>
    <status state="up" reason="arp-response"/>
    <address addr="192.168.1.20" addrtype="ipv4"/>
    <address addr="00:1A:2B:3C:4D:5E" addrtype="mac" vendor="SomeOther Inc"/>
</host>
<runstats><finished time="1672531205" elapsed="5"/></runstats>
</nmaprun>"""


def test_scan_with_nmap_finds_pi(mock_nmap_xml_output):
    """Tests if the scanner can correctly parse mocked nmap XML output."""
    with patch('subprocess.run') as mock_run:
        mock_run.return_value = MagicMock(stdout=mock_nmap_xml_output, returncode=0)
        found_pis = PiScanner.scan('192.168.1.0/24')

    assert len(found_pis) == 1
    found_pi = found_pis[0]
    assert found_pi['ip'] == '192.168.1.15'
    assert found_pi['mac'] == 'e4:5f:01:aa:bb:cc'


def test_parse_nmap_output_identifies_pi():
    """Ensures that a known Raspberry Pi MAC address is correctly parsed from mock XML."""
    # FIX: Added the <status> tag, which the parsing logic requires.
    mock_xml = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE nmaprun>
<nmaprun>
  <host>
    <status state="up"/>
    <address addr="192.168.1.50" addrtype="ipv4"/>
    <address addr="b8:27:eb:01:02:03" addrtype="mac" vendor="Raspberry Pi Foundation"/>
  </host>
  <host>
    <status state="up"/>
    <address addr="192.168.1.51" addrtype="ipv4"/>
    <address addr="00:1a:2b:01:02:03" addrtype="mac" vendor="Some Other Vendor"/>
  </host>
</nmaprun>
"""
    pi_prefixes = ["b8:27:eb"]
    devices = PiScanner._parse_nmap_output(mock_xml, pi_prefixes)
    assert len(devices) == 1
    assert devices[0]['ip'] == '192.168.1.50'
    assert devices[0]['mac'] == 'b8:27:eb:01:02:03'


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


def test_parse_nmap_output_handles_host_with_no_mac():
    """Ensures that a host found by nmap but missing a MAC address is gracefully ignored."""
    mock_xml = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE nmaprun>
<nmaprun>
  <host>
    <status state="up"/>
    <address addr="192.168.1.55" addrtype="ipv4"/>
  </host>
</nmaprun>"""
    devices = PiScanner._parse_nmap_output(mock_xml, ["b8:27:eb"])
    assert len(devices) == 0