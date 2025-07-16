# file: tests/test_pi_scanner.py
import socket
from unittest.mock import MagicMock, patch

import nmap

from src.pi_scanner import PiScanner


class TestPiScanner:
    """Test suite for the PiScanner class."""

    def test_detect_subnet_success(self, monkeypatch):
        """
        Tests that the subnet is correctly detected based on the local IP.
        """
        # Mock socket functions to avoid actual network calls
        monkeypatch.setattr(socket, "gethostname", lambda: "raspberrypi")
        monkeypatch.setattr(socket, "gethostbyname", lambda hn: "192.168.1.123")
        assert PiScanner.detect_subnet() == "192.168.1.0/24"

    def test_detect_subnet_failure(self, monkeypatch):
        """
        Tests that a default subnet is returned if IP detection fails.
        """
        # Simulate a scenario where the hostname cannot be resolved
        monkeypatch.setattr(
            socket, "gethostbyname", lambda hn: (_ for _ in ()).throw(socket.gaierror)
        )
        assert PiScanner.detect_subnet() == "192.168.1.0/24"

    @patch("src.pi_scanner.nmap.PortScanner")
    def test_scan_finds_pi(self, mock_nmap_scanner_class):
        """
        Tests that the scan method correctly and
        identifies a Raspberry Pi by its MAC address.
        """
        # Mock the nmap PortScanner's result
        mock_nm = MagicMock()
        mock_nm.all_hosts.return_value = ["192.168.1.101"]
        # FIX: Ensure the mocked item is a dictionary with a 'state' and 'ipv4' key
        mock_nm.__getitem__.return_value = {
            "addresses": {"mac": "b8:27:eb:aa:bb:cc", "ipv4": "192.168.1.101"},
            "state": "up",
        }
        mock_nmap_scanner_class.return_value = mock_nm

        # Run the scan and check results
        hosts, msg, err = PiScanner.scan("192.168.1.0/24")
        assert len(hosts) == 1
        assert hosts[0]["ip"] == "192.168.1.101"
        assert hosts[0]["mac"] == "b8:27:eb:aa:bb:cc"
        assert hosts[0]["status"] == "up"

    @patch("src.pi_scanner.nmap.PortScanner")
    def test_scan_ignores_other_devices(self, mock_nmap_scanner_class):
        """
        Tests that devices with non-Pi MAC addresses are ignored.
        """
        mock_nm = MagicMock()
        mock_nm.all_hosts.return_value = ["192.168.1.102"]
        mock_nm.__getitem__.return_value = {
            "addresses": {"mac": "00:11:22:33:44:55", "ipv4": "192.168.1.102"},
            "state": "up",
        }
        mock_nmap_scanner_class.return_value = mock_nm

        hosts, msg, err = PiScanner.scan("192.168.1.0/24")
        assert len(hosts) == 0

    @patch("src.pi_scanner.nmap.PortScanner")
    def test_scan_nmap_error(self, mock_nmap_scanner_class):
        """
        Tests that the scan method handles nmap errors gracefully.
        """
        # Configure the mock's scan method to raise a PortScannerError
        mock_nm = MagicMock()
        mock_nm.scan.side_effect = nmap.nmap.PortScannerError("Nmap failed")
        mock_nmap_scanner_class.return_value = mock_nm

        hosts, msg, err = PiScanner.scan("192.168.1.0/24")
        assert len(hosts) == 0
        assert msg == ""
        # FIX: Check for the actual error message content, which may include quotes
        assert "Nmap failed" in err

    @patch("src.pi_scanner.is_port_open", return_value=True)
    @patch("src.pi_scanner.subprocess.run")
    def test_get_device_details_success(self, mock_run, mock_is_port_open):
        """
        Tests that device details are retrieved successfully via SSH.
        """
        # Mock the subprocess result
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "PRETTY_NAME=Raspbian GNU/Linux 10 (buster)"
        mock_run.return_value = mock_result

        # Run get_device_details
        scanner = PiScanner("test_user", "test_pass")
        details, err = scanner.get_device_details("192.168.1.101")
        assert err is None
        assert details["os_version"] == "Raspbian GNU/Linux 10 (buster)"

    @patch("src.pi_scanner.is_port_open", return_value=False)
    def test_get_device_details_ssh_port_closed(self, mock_is_port_open):
        """
        Tests the behavior when the SSH port is closed.
        """
        scanner = PiScanner("user", "pass")
        details, err = scanner.get_device_details("192.168.1.101")
        assert details is None
        assert "SSH port 22 is not open" in err

    @patch("src.pi_scanner.is_port_open", return_value=True)
    @patch("src.pi_scanner.subprocess.run")
    def test_get_device_details_ssh_failure(self, mock_run, mock_is_port_open):
        """
        Tests the handling of an SSH command failure.
        """
        # Mock a failed subprocess execution
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "Permission denied"
        mock_run.return_value = mock_result

        scanner = PiScanner("user", "pass")
        details, err = scanner.get_device_details("192.168.1.101")
        assert details is None
        assert "Permission denied" in err

    @patch("src.pi_scanner.is_port_open", return_value=True)
    @patch("src.pi_scanner.subprocess.run")
    def test_get_device_details_incomplete_output(self, mock_run, mock_is_port_open):
        """
        Tests the handling of incomplete SSH command output.
        """
        # Mock subprocess result with missing info
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "SOME_OTHER_INFO=some_value"
        mock_run.return_value = mock_result

        scanner = PiScanner("user", "pass")
        details, err = scanner.get_device_details("192.168.1.101")
        assert details is None
        assert "Could not determine OS version" in err
