import logging
import socket
import subprocess

import nmap
import psutil
import ipaddress

# Configure logging
logger = logging.getLogger(__name__)


def is_port_open(host, port):
    """
    Check if a specific port is open on a given host.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(1)
    try:
        s.connect((host, port))
        s.close()
        return True
    except (socket.timeout, ConnectionRefusedError):
        return False


class PiScanner:
    """
    A class to scan the network for Raspberry Pi devices and retrieve their details.
    """

    # Official Raspberry Pi MAC address prefixes
    PI_MAC_PREFIXES = {
        "b8:27:eb",  # Raspberry Pi Foundation
        "dc:a6:32",  # Raspberry Pi Trading Ltd
        "e4:5f:01",  # Raspberry Pi Foundation
        "28:cd:c1",  # Raspberry Pi Foundation
        "d8:3a:dd",  # Raspberry Pi Foundation
        "2c:cf:67",  # Associated with Raspberry Pi
    }

    # Command to get OS details, executed via SSH
    SSH_COMMAND = "cat /etc/os-release"

    def __init__(self, username, password):
        """
        Initializes the PiScanner with SSH credentials.
        :param username: The SSH username for the Raspberry Pi.
        :param password: The SSH password for the Raspberry Pi.
        """
        self.username = username
        self.password = password

    @staticmethod
    def get_primary_ip():
        """
        Gets the primary outbound IP address of the machine.
        Uses the socket connect trick, which is fast and dependency-free.
        """
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0)
        # noinspection PyBroadException
        try:
            # This doesn't send a packet
            s.connect(('8.8.8.8', 1))
            ip = s.getsockname()[0]
        except OSError:
            return '127.0.0.1'
        # pylint: disable=broad-exception-caught
        except Exception:
            logging.exception("Unexpected error in get_local_ip")
            return '127.0.0.1'
        finally:
            s.close()
        return ip
        # pylint: enable=broad-exception-caught


    @staticmethod
    def detect_subnet():
        """
        Detects the local subnet using psutil, which is robust and maintained.
        Returns the subnet as a string (e.g., '192.168.178.0/24') or None on failure.
        """
        primary_ip = PiScanner.get_primary_ip()

        if primary_ip == '127.0.0.1':
            logger.warning("Could not determine a non-loopback IP address.")
            return None

        logger.info(f"🔍 Primary IP detected: {primary_ip}")

        # psutil.net_if_addrs() returns all addresses on the system
        # The key is the interface name (e.g., 'eth0', 'Wi-Fi')
        # The value is a list of addresses on that interface
        all_addrs = psutil.net_if_addrs()

        for interface_name, interface_addresses in all_addrs.items():
            for addr in interface_addresses:
                # We are looking for the IPv4 address that matches our primary IP
                if addr.family == socket.AF_INET and addr.address == primary_ip:
                    # print(f"✅ Found matching interface '{interface_name}'")
                    netmask = addr.netmask
                    logger.info(f"   - IP Address: {addr.address}")
                    logger.info(f"   - Netmask:    {netmask}")

                    # Use the excellent 'ipaddress' library to correctly calculate the network
                    # strict=False allows creating a network from an IP/netmask pair
                    network = ipaddress.IPv4Network(f'{addr.address}/{netmask}', strict=False)

                    logger.info(f"🌐 Calculated Subnet: {network.with_prefixlen}")
                    return str(network.with_prefixlen)

        logger.warning("❌ Could not find interface details for the primary IP using psutil.")
        return None

    @classmethod
    def scan(cls, subnet=None):
        """
        Enhanced scan with detection info returned.
        Returns: (hosts, messages, errors, detection_info)
        """
        if subnet is None:
            subnet, detection_info = cls.detect_subnet()
        else:
            detection_info = {
                "success": True,
                "method_used": "user_provided",
                "subnet": subnet,
                "messages": [f"🎯 Using provided network: {subnet}"],
            }

        detection_info["messages"].append(
            f"🔍 Scanning {subnet} for Raspberry Pi devices..."
        )

        # Rest of scanning logic...
        try:
            nm = nmap.PortScanner()
            result = nm.scan(subnet, ports="22", arguments="-sS")  # Ping scan

            hosts = []
            scan_messages = []

            scanned_hosts = list(result["scan"].keys())
            scan_messages.append(f"📡 Found {len(scanned_hosts)} active devices")

            pi_count = 0
            for host in scanned_hosts:
                host_info = result["scan"][host]

                if "addresses" in host_info and "mac" in host_info["addresses"]:
                    mac_address = host_info["addresses"]["mac"].upper()
                    vendor = host_info["vendor"].get(
                        host_info["addresses"]["mac"], "Unknown"
                    )

                    if cls.is_raspberry_pi(mac_address):
                        pi_count += 1
                        hosts.append(
                            {
                                "ip": host,
                                "mac": mac_address,
                                "vendor": vendor,
                                "hostname": host_info.get("hostnames", [{}])[0].get(
                                    "name", "Unknown"
                                ),
                            }
                        )
                        scan_messages.append(
                            f"🍓 Raspberry Pi found: {host} ({vendor})"
                        )

            if pi_count == 0:
                scan_messages.append("⚠️ No Raspberry Pi devices found in this network")
            else:
                scan_messages.append(
                    f"✅ Scan complete: {pi_count} Raspberry Pi(s) discovered"
                )

            # Combine detection and scan messages
            all_messages = detection_info["messages"] + scan_messages

            logger.info(f"Scan completed. Found {len(hosts)} Raspberry Pi devices.")
            return hosts, all_messages, "", detection_info

        except Exception as e:
            error_msg = f"❌ Scan failed: {str(e)}"
            logger.error(f"Scan failed: {e}")
            return [], detection_info["messages"], error_msg, detection_info

    def get_device_details(self, ip_address):
        """
        Retrieves OS and hardware details from a device using SSH.
        :param ip_address: The IP address of the device.
        :return: A tuple of (details_dict, error_string).
        """
        # First, check if the SSH port is open
        if not is_port_open(ip_address, 22):
            logger.warning(f"SSH port 22 not open on {ip_address}.")
            return None, f"SSH port 22 is not open on {ip_address}."

        try:
            # Construct the sshpass command
            command = [
                "sshpass",
                "-p",
                self.password,
                "ssh",
                "-o",
                "StrictHostKeyChecking=no",
                f"{self.username}@{ip_address}",
                self.SSH_COMMAND,
            ]
            logger.info(f"Executing SSH command: {' '.join(command)}")
            result = subprocess.run(command, capture_output=True, text=True, timeout=10)

            if result.returncode != 0:
                logger.error(
                    f"SSH command failed for {ip_address}: {result.stderr.strip()}"
                )
                return None, f"SSH command failed: {result.stderr.strip()}"

            # Parse the output of /etc/os-release
            os_info = dict(
                line.split("=", 1)
                for line in result.stdout.strip().split("\n")
                if "=" in line
            )
            pretty_name = os_info.get("PRETTY_NAME", "N/A").strip('"')

            if pretty_name == "N/A":
                logger.warning(
                    f"Could not determine OS version "
                    f"for {ip_address}. Output: {result.stdout}"
                )
                return None, "Could not determine OS version from SSH output."

            logger.info(f"Successfully retrieved details from {ip_address}")
            return {"os_version": pretty_name}, None

        except FileNotFoundError:
            logger.error(
                "sshpass is not installed. Please install it to use SSH functionality."
            )
            return (
                None,
                "sshpass is not installed. This tool is required for SSH.",
            )
        except subprocess.TimeoutExpired:
            logger.error(f"SSH command timed out for {ip_address}.")
            return None, "SSH connection timed out."
        except Exception as e:
            logger.error(
                f"An unexpected error occurred during SSH connection: {e}",
                exc_info=True,
            )
            return None, f"An unexpected SSH error occurred: {e}"

    def scan_and_get_details(self, subnet, per_device_callback=None):
        """
        Scans for Pis and then tries to get details for each one found.
        :param subnet: Network subnet to scan
        :param per_device_callback: Optional callback function to
        get credentials per device
        :return: Tuple of (detailed_hosts, messages, error)
        """
        hosts, messages, err, detection_info = self.scan(subnet)
        if err:
            return [], messages, err

        detailed_hosts = []
        for host in hosts:
            details, detail_err = self.get_device_details(host["ip"])

            if detail_err and per_device_callback:
                # Try with device-specific credentials
                custom_creds = per_device_callback(host["ip"], detail_err)
                if custom_creds:
                    username, password = custom_creds
                    temp_scanner = PiScanner(username, password)
                    details, detail_err = temp_scanner.get_device_details(host["ip"])

            if detail_err:
                logger.warning(f"Could not get details for {host['ip']}: {detail_err}")
                # Add basic info even if details fail
                host["os_version"] = f"Error: {detail_err}"
                host["details_available"] = False
            else:
                host.update(details)
                host["details_available"] = True

            detailed_hosts.append(host)

        return detailed_hosts, messages, None

    @staticmethod
    def get_device_details_with_credentials(ip_address, username, password):
        """
        Static method to get device details with specific credentials.
        Useful for per-device authentication.
        """
        scanner = PiScanner(username, password)
        return scanner.get_device_details(ip_address)

    @classmethod
    def is_raspberry_pi(cls, mac_address):
        """Check if a MAC address belongs to a Raspberry Pi."""
        mac_prefix = mac_address[:8].lower()
        return mac_prefix in cls.PI_MAC_PREFIXES
