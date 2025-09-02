import socket
import subprocess
from unittest.mock import MagicMock, patch

import pytest

# Assuming your file is named pi_scanner.py
from pi_scanner import PiScanner, is_port_open, is_raspberry_pi


# Fixture for a reusable PiScanner instance
@pytest.fixture
def scanner():
    """Provides a default PiScanner instance for tests."""
    return PiScanner("testuser", "testpass")


class TestIsPortOpen:
    """Tests for the is_port_open utility function."""

    @patch("socket.socket")
    def test_port_is_open(self, mock_socket):
        """Verify it returns True when a connection is successful."""
        # The mock socket's connect method will not raise an error
        mock_instance = mock_socket.return_value
        mock_instance.connect.return_value = None

        assert is_port_open("192.168.1.1", 22) is True
        mock_instance.connect.assert_called_once_with(("192.168.1.1", 22))

    @patch("socket.socket")
    def test_port_is_closed(self, mock_socket):
        """Verify it returns False when a connection is refused."""
        mock_instance = mock_socket.return_value
        # Simulate a ConnectionRefusedError
        mock_instance.connect.side_effect = ConnectionRefusedError

        assert is_port_open("192.168.1.1", 22) is False

    @patch("socket.socket")
    def test_host_is_unreachable(self, mock_socket):
        """Verify it returns False on a socket timeout."""
        mock_instance = mock_socket.return_value
        # Simulate a timeout
        mock_instance.connect.side_effect = socket.timeout

        assert is_port_open("192.168.1.100", 22) is False


class TestPiScannerStaticMethods:
    """Tests for the static methods in the PiScanner class."""

    def test_is_raspberry_pi(self):
        """Test the MAC address checker."""
        assert is_raspberry_pi("B8:27:EB:XX:XX:XX") is True
        assert is_raspberry_pi("dc:a6:32:yy:yy:yy") is True
        assert is_raspberry_pi("00:1A:2B:3C:4D:5E") is False
        assert is_raspberry_pi("invalid-mac") is False

    @patch("socket.socket")
    def test_get_primary_ip_success(self, mock_socket):
        """Test successful IP detection."""
        mock_sock_instance = MagicMock()
        mock_sock_instance.getsockname.return_value = ["192.168.1.10"]
        mock_socket.return_value = mock_sock_instance

        assert PiScanner.get_primary_ip() == "192.168.1.10"

    @patch("socket.socket")
    def test_get_primary_ip_os_error(self, mock_socket):
        """Test fallback to 127.0.0.1 on OSError."""
        mock_sock_instance = MagicMock()
        mock_sock_instance.connect.side_effect = OSError
        mock_socket.return_value = mock_sock_instance

        assert PiScanner.get_primary_ip() == "127.0.0.1"

    @patch("psutil.net_if_addrs")
    @patch("pi_scanner.PiScanner.get_primary_ip")
    def test_detect_subnet_success(self, mock_get_ip, mock_psutil):
        """Test successful subnet detection."""
        mock_get_ip.return_value = "192.168.1.10"

        # Mock psutil return value
        mock_addr = MagicMock()
        mock_addr.family = socket.AF_INET
        mock_addr.address = "192.168.1.10"
        mock_addr.netmask = "255.255.255.0"
        mock_psutil.return_value = {"eth0": [mock_addr]}

        assert PiScanner.detect_subnet() == "192.168.1.0/24"

    @patch("pi_scanner.PiScanner.get_primary_ip")
    def test_detect_subnet_no_ip(self, mock_get_ip):
        """Test subnet detection failure when no primary IP is found."""
        mock_get_ip.return_value = "127.0.0.1"
        assert PiScanner.detect_subnet() is None


@patch("nmap.PortScanner")
class TestPiScannerScan:
    """Tests for the main network scan functionality."""

    def test_scan_finds_pi(self, mock_nmap, scanner):
        """Test a scan where a Raspberry Pi is found."""
        mock_nmap_instance = mock_nmap.return_value
        mock_nmap_instance.scan.return_value = {
            "scan": {
                "192.168.1.5": {
                    "hostnames": [{"name": "pi.local"}],
                    "addresses": {"mac": "B8:27:EB:01:02:03"},
                    "vendor": {"B8:27:EB:01:02:03": "Raspberry Pi Foundation"},
                },
                "192.168.1.2": {
                    "hostnames": [{"name": "other-device"}],
                    "addresses": {"mac": "00:1A:2B:AA:BB:CC"},
                    "vendor": {"00:1A:2B:AA:BB:CC": "Some Other Vendor"},
                },
            }
        }

        hosts, messages, err, _ = scanner.scan(subnet="192.168.1.0/24")

        assert not err
        assert len(hosts) == 1
        assert hosts[0]["ip"] == "192.168.1.5"
        assert hosts[0]["mac"] == "B8:27:EB:01:02:03"
        assert "🍓 Raspberry Pi found" in "".join(messages)

    def test_scan_finds_no_pi(self, mock_nmap, scanner):
        """Test a scan where no Raspberry Pi devices are found."""
        mock_nmap_instance = mock_nmap.return_value
        mock_nmap_instance.scan.return_value = {
            "scan": {
                "192.168.1.2": {
                    "hostnames": [{"name": "other-device"}],
                    "addresses": {"mac": "00:1A:2B:AA:BB:CC"},
                    "vendor": {"00:1A:2B:AA:BB:CC": "Some Other Vendor"},
                }
            }
        }

        hosts, messages, err, _ = scanner.scan(subnet="192.168.1.0/24")

        assert not err
        assert len(hosts) == 0
        assert "⚠️ No Raspberry Pi devices found" in "".join(messages)

    def test_scan_nmap_error(self, mock_nmap, scanner):
        """Test handling of an exception from nmap."""
        mock_nmap_instance = mock_nmap.return_value
        mock_nmap_instance.scan.side_effect = Exception("nmap failed")

        hosts, messages, err, _ = scanner.scan(subnet="192.168.1.0/24")

        assert len(hosts) == 0
        assert "❌ Scan failed: nmap failed" in err


class TestPiScannerGetDetails:
    """Tests for retrieving device details via SSH."""

    @patch("pi_scanner.is_port_open", return_value=False)
    def test_get_details_port_closed(self, mock_port_open, scanner):
        """Test that details are not fetched if SSH port is closed."""
        details, err = scanner.get_device_details("192.168.1.5")
        assert details is None
        assert "SSH port 22 is not open" in err
        mock_port_open.assert_called_once_with("192.168.1.5", 22)

    @patch("subprocess.run")
    @patch("pi_scanner.is_port_open", return_value=True)
    def test_get_details_success(self, _mock_port_open, mock_subprocess, scanner):
        """Test successful retrieval of device details."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = (
            'PRETTY_NAME="Raspbian GNU/Linux 11 (bullseye)"\n'
            "---\n"
            "1000000012345678\n"
            "---\n"
            "Raspberry Pi 4 Model B Rev 1.4\n"
            "---\n"
            "4096 MB\n"
            "---\n"
            "Filesystem Size Used Avail Use% Mounted on\n"
            "/dev/root 30G 5.0G 23G 18% /"
        )
        mock_subprocess.return_value = mock_result

        details, err = scanner.get_device_details("192.168.1.5")

        assert err is None
        assert details["os_version"] == "Raspbian GNU/Linux 11 (bullseye)"

    @patch("subprocess.run")
    @patch("pi_scanner.is_port_open", return_value=True)
    def test_get_details_ssh_command_fails(
        self, _mock_port_open, mock_subprocess, scanner
    ):
        """Test handling of a failed SSH command execution."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "Permission denied"
        mock_subprocess.return_value = mock_result

        details, err = scanner.get_device_details("192.168.1.5")
        assert details is None
        assert "SSH command failed: Permission denied" in err

    @patch("subprocess.run")
    @patch("pi_scanner.is_port_open", return_value=True)
    def test_get_details_ssh_timeout(self, _mock_port_open, mock_subprocess, scanner):
        """Test handling of an SSH timeout."""
        mock_subprocess.side_effect = subprocess.TimeoutExpired(cmd="ssh", timeout=10)

        details, err = scanner.get_device_details("192.168.1.5")
        assert details is None
        assert "SSH command timed out" in err

    @patch("subprocess.run")
    @patch("pi_scanner.is_port_open", return_value=True)
    def test_get_details_sshpass_not_found(
        self, _mock_port_open, mock_subprocess, scanner
    ):
        """Test handling of FileNotFoundError for sshpass."""
        mock_subprocess.side_effect = FileNotFoundError

        details, err = scanner.get_device_details("192.168.1.5")
        assert details is None
        assert "sshpass is not installed" in err


class TestPiScannerEndToEnd:
    """Integration tests for the PiScanner's combined methods."""

    @patch("pi_scanner.PiScanner.get_device_details")
    @patch("pi_scanner.PiScanner.scan")
    def test_scan_and_get_details_success(self, mock_scan, mock_get_details, scanner):
        """Test the combined scan-and-get-details workflow."""
        # Mock scan returns one Pi
        mock_scan.return_value = (
            [{"ip": "192.168.1.5", "mac": "B8:27:EB:01:02:03"}],
            ["Scan message"],
            None,
            {},
        )
        # Mock get_details returns OS version
        mock_get_details.return_value = ({"os_version": "Raspbian"}, None)

        hosts, messages, err = scanner.scan_and_get_details("192.168.1.0/24")

        assert err is None
        assert len(hosts) == 1
        assert hosts[0]["ip"] == "192.168.1.5"
        assert hosts[0]["os_version"] == "Raspbian"
        assert hosts[0]["details_available"] is True
        mock_get_details.assert_called_once_with("192.168.1.5")

    @patch("pi_scanner.PiScanner.get_device_details")
    @patch("pi_scanner.PiScanner.scan")
    def test_scan_and_get_details_fails(self, mock_scan, mock_get_details, scanner):
        """Test workflow when getting details fails for a device."""
        mock_scan.return_value = (
            [{"ip": "192.168.1.5", "mac": "B8:27:EB:01:02:03"}],
            ["Scan message"],
            None,
            {},
        )
        # Mock get_details returns an error
        mock_get_details.return_value = (None, "Auth failed")

        hosts, messages, err = scanner.scan_and_get_details("192.168.1.0/24")

        assert err is None
        assert len(hosts) == 1
        assert "Error: Auth failed" in hosts[0]["os_version"]
        assert hosts[0]["details_available"] is False
