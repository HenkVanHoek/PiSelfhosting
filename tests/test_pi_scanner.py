# import json
from unittest.mock import MagicMock, call, patch

import paramiko
import pytest

# Modified import: The public 'is_port_open' function is now imported
from src.pi_scanner import PiScanner

# , is_port_open)


@pytest.fixture
def mock_nmap_text_output():
    """Provides a realistic, multi-device nmap output string for tests."""
    return """
# Nmap 7.80 scan initiated Tue Jan 1 12:00:00 2024 as: nmap -sn -PR 192.168.1.0/24
Nmap scan report for 192.168.1.1
Host is up (0.0010s latency).
MAC Address: DC:A6:32:01:02:03 (Raspberry Pi Foundation)
Nmap scan report for 192.168.1.5
Host is up (0.020s latency).
MAC Address: AA:BB:CC:DD:EE:FF (Unknown Vendor)
Nmap scan report for 192.168.1.8
Host is up (0.0050s latency).
MAC Address: B8:27:EB:AA:BB:CC (Raspberry Pi Foundation)
# Nmap done at Tue Jan 1 12:01:00 2024 -- 256 IP addresses (3 hosts up)
scanned in 60.00 seconds
"""


class TestPiScanner:
    """Test suite for the PiScanner class."""

    def test_detect_subnet(self):
        """Tests subnet detection based on local IP."""
        with patch("socket.socket") as mock_socket:
            mock_socket.return_value.__enter__.return_value.getsockname.return_value = (
                "192.168.1.100",
                80,
            )
            assert PiScanner.detect_subnet() == "192.168.1.0/24"

    @patch("src.pi_scanner.subprocess.run")
    def test_scan_with_nmap_finds_pi(self, mock_run, mock_nmap_text_output):
        """
        Tests that the scanner correctly parses nmap output and identifies
        all devices with a valid Raspberry Pi MAC address prefix.
        """
        mock_run.return_value = MagicMock(
            stdout=mock_nmap_text_output, stderr="", returncode=0
        )
        found_pis = PiScanner.scan("192.168.1.0/24")

        assert len(found_pis) == 2
        found_pis_set = {tuple(p.items()) for p in found_pis}
        expected_pis_set = {
            (("ip", "192.168.1.1"), ("mac", "dc:a6:32:01:02:03")),
            (("ip", "192.168.1.8"), ("mac", "b8:27:eb:aa:bb:cc")),
        }
        assert found_pis_set == expected_pis_set

    @pytest.mark.parametrize(
        "key_auth_failure_exception",
        [
            paramiko.AuthenticationException("Key auth failed"),
            paramiko.SSHException("A generic SSH error occurred"),
        ],
    )
    @patch("src.pi_scanner.is_port_open", return_value=True)
    @patch("paramiko.SSHClient")
    def test_get_device_details_success_after_key_fail(
        self, mock_ssh_client_class, mock_is_port_open, key_auth_failure_exception
    ):
        """
        Tests successful retrieval of device details via password
        after a key-based authentication attempt fails.
        """
        mock_ssh_instance = MagicMock()
        mock_ssh_client_class.return_value = mock_ssh_instance
        mock_ssh_instance.connect.side_effect = [key_auth_failure_exception, None]

        fake_output = (
            "Raspberry Pi 5 Model B\x00---\n"
            "8GiB\x00---\n"
            "10000000abcdef\x00---\n"
            '{"blockdevices":[{"name":"sda","size":"128G","type":"disk"}]}'
        )
        mock_stdout = MagicMock()
        mock_stdout.read.return_value = fake_output.encode("utf-8")
        mock_stderr = MagicMock()
        mock_stderr.read.return_value = b""
        mock_ssh_instance.exec_command.return_value = (None, mock_stdout, mock_stderr)

        details = PiScanner.get_device_details("192.168.1.50", "pi", "raspberry")

        mock_is_port_open.assert_called_once_with("192.168.1.50", 22)
        assert mock_ssh_instance.connect.call_count == 2
        expected_calls = [
            call(hostname="192.168.1.50", username="pi", password=None, timeout=10),
            call(
                hostname="192.168.1.50", username="pi", password="raspberry", timeout=10
            ),
        ]
        mock_ssh_instance.connect.assert_has_calls(expected_calls, any_order=False)

        assert details is not None
        assert details["model"] == "Raspberry Pi 5 Model B"
        assert details["ram"] == "8GiB"
        assert details["serial"] == "10000000abcdef"
        assert len(details["disks"]) == 1

    @patch("src.pi_scanner.is_port_open", return_value=True)
    @patch("paramiko.SSHClient")
    def test_get_device_details_parse_error(
        self, mock_ssh_client_class, _mock_is_port_open, capsys
    ):
        """Tests that None is returned if the SSH command output cannot be parsed."""
        mock_ssh_instance = MagicMock()
        mock_ssh_client_class.return_value = mock_ssh_instance
        mock_ssh_instance.connect.return_value = None

        malformed_output = "Part1\n---\nPart2\n---\nPart3"  # Missing the 4th part
        mock_stdout = MagicMock()
        mock_stdout.read.return_value = malformed_output.encode("utf-8")

        mock_stderr = MagicMock()
        mock_stderr.read.return_value = b""
        mock_ssh_instance.exec_command.return_value = (None, mock_stdout, mock_stderr)

        details = PiScanner.get_device_details("192.168.1.50", "pi", "raspberry")
        assert details is None
        captured = capsys.readouterr()
        assert "Could not parse all details" in captured.out

    @patch("src.pi_scanner.is_port_open", return_value=False)
    def test_get_device_details_port_closed(self, mock_is_port_open):
        """Tests that None is returned if the SSH port is closed."""
        details = PiScanner.get_device_details("192.168.1.50", "pi", "raspberry")
        mock_is_port_open.assert_called_once_with("192.168.1.50", 22)
        assert details is None
