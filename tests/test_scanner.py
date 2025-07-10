# tests/test_scanner.py
import pytest
from unittest.mock import patch, MagicMock
from src.pi_scanner import PiScanner


# Your existing tests are great!
def test_parse_nmap_output_identifies_pi():
    """
    Ensures that a known Raspberry Pi MAC address is correctly parsed from mock XML.
    """
    mock_xml = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE nmaprun>
    <nmaprun>
      <host>
        <status state="up"/>
        <address addr="192.168.1.50" addrtype="ipv4"/>
        <address addr="b8:27:eb:01:02:03" addrtype="mac" vendor="Raspberry Pi Foundation"/>
      </host>
      <host>
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


@patch('src.pi_scanner.subprocess.run')
def test_scan_handles_nmap_not_found(mock_subprocess_run):
    """
    Ensures the scan method returns an empty list and doesn't crash if nmap is not installed.
    """
    mock_subprocess_run.side_effect = FileNotFoundError

    # No need to instantiate the class for static methods
    devices = PiScanner.scan(target_subnet="192.168.1.0/24")

    assert devices == []


def test_parse_nmap_output_handles_empty_input():
    """
    Ensures the parser doesn't crash with empty or invalid XML.
    """
    assert PiScanner._parse_nmap_output("", ["b8:27:eb"]) == []
    assert PiScanner._parse_nmap_output("<nmaprun></nmaprun>", ["b8:27:eb"]) == []


def test_parse_nmap_output_handles_host_with_no_mac():
    """
    Ensures that a host found by nmap but missing a MAC address is gracefully ignored.
    """
    mock_xml = """
    <nmaprun>
      <host>
        <status state="up"/>
        <address addr="192.168.1.55" addrtype="ipv4"/>
      </host>
    </nmaprun>
    """
    devices = PiScanner._parse_nmap_output(mock_xml, ["b8:27:eb"])
    assert len(devices) == 0


@patch('paramiko.SSHClient')
def test_get_device_details_handles_auth_failure(mock_ssh_client):
    """
    Ensures get_device_details returns None on an AuthenticationException.
    """
    # Configure the mock to raise an exception when connect is called
    import paramiko
    mock_ssh_client.return_value.connect.side_effect = paramiko.AuthenticationException

    # We also need to mock the port check to allow the SSH attempt
    with patch('src.pi_scanner.PiScanner._is_port_open', return_value=True):
        details = PiScanner.get_device_details("192.168.1.99", "user", "badpass")

    assert details is None
