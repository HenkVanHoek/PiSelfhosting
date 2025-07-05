# tests/test_pi_scanner.py
import pytest
from unittest.mock import patch, MagicMock

# This import will fail initially
from src.pi_scanner import PiScanner


@pytest.fixture
def mock_scapy_scan_result():
    """
    Creates a fake network scan result, as if scapy had found two devices.
    One is a Raspberry Pi, the other is not.
    """
    # Mock for a Raspberry Pi device
    pi_response_packet = MagicMock()
    pi_response_packet.psrc = '192.168.1.15'  # IP address
    pi_response_packet.hwsrc = 'e4:5f:01:aa:bb:cc'  # A Pi MAC address

    # Mock for another, non-Pi device
    other_response_packet = MagicMock()
    other_response_packet.psrc = '192.168.1.20'
    other_response_packet.hwsrc = '00:1a:2b:3c:4d:5e'  # Not a Pi MAC address

    # scapy's srp function returns a tuple of (answered_list, unanswered_list)
    # Each item in the answered_list is a pair of (sent_packet, received_packet)
    answered_list = [
        (MagicMock(), pi_response_packet),
        (MagicMock(), other_response_packet)
    ]
    unanswered_list = MagicMock()

    return (answered_list, unanswered_list)


def test_scan_with_scapy_finds_pi(mock_scapy_scan_result):
    """
    Tests if the new scapy-based scanner can correctly parse a mocked scan result.
    """
    # We patch scapy's 'srp' function, which sends/receives packets.
    # When our code calls it, the mock will return our fake data instead.
    with patch('src.pi_scanner.srp', return_value=mock_scapy_scan_result):
        # Initialize our scanner and run the scan
        scanner = PiScanner()
        found_pis = scanner.scan('192.168.1.0/24')  # Subnet is still needed

    # --- Assertions ---
    # 1. The scanner should have found exactly one Pi.
    assert len(found_pis) == 1

    # 2. The details of the found Pi should be correct.
    found_pi = found_pis[0]
    assert found_pi['ip'] == '192.168.1.15'
    assert found_pi['mac'] == 'e4:5f:01:aa:bb:cc'