import pytest
from unittest.mock import patch, MagicMock
import sys
import os

# Ensure the 'src' directory is on the path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
src_path = os.path.join(project_root, 'src')
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from src.pi_scanner import PiScanner


@pytest.fixture
def mock_nmap_xml_output():
    """Provides a fake nmap XML output string for testing."""
    # --- CORRECTED: Removed the leading blank line ---
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
</nmaprun>
"""


def test_scan_with_nmap_finds_pi(mock_nmap_xml_output):
    """
    Tests if the scanner can correctly parse mocked nmap XML output.
    """
    with patch('subprocess.run') as mock_run:
        mock_run.return_value = MagicMock(stdout=mock_nmap_xml_output, returncode=0)

        found_pis = PiScanner.scan('192.168.1.0/24')

    # --- Assertions ---
    assert len(found_pis) == 1

    found_pi = found_pis[0]
    assert found_pi['ip'] == '192.168.1.15'
    assert found_pi['mac'] == 'e4:5f:01:aa:bb:cc'


def test_scan_handles_nmap_not_found():
    """
    Tests that the scanner handles the case where nmap is not installed.
    """
    with patch('subprocess.run', side_effect=FileNotFoundError):
        found_pis = PiScanner.scan('192.168.1.0/24')

    assert found_pis == []