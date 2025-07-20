import logging
import socket
import subprocess

import nmap

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
    def detect_subnet():
        """
        Detects the local subnet with detailed user feedback.
        Returns tuple: (subnet, detection_info)
        """
        detection_info = {
            "success": False,
            "method_used": None,
            "detected_ip": None,
            "subnet": None,
            "messages": [],
        }

        try:
            # Method 1: Socket connection method
            detection_info["messages"].append(
                "🔍 Detecting your network configuration..."
            )

            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                local_ip = s.getsockname()[0]

            detection_info["detected_ip"] = local_ip
            detection_info["method_used"] = "socket_connection"
            detection_info["messages"].append(f"✅ Found your IP address: {local_ip}")

            # Construct the subnet
            ip_parts = local_ip.split(".")
            subnet = f"{ip_parts[0]}.{ip_parts[1]}.{ip_parts[2]}.0/24"

            detection_info["subnet"] = subnet
            detection_info["success"] = True
            detection_info["messages"].append(f"🌐 Will scan network: {subnet}")

            logger.info(f"Network detected via socket method: {local_ip} -> {subnet}")
            return subnet, detection_info

        except Exception as e:
            detection_info["messages"].append(f"⚠️ Primary detection failed: {str(e)}")
            logger.warning(f"Socket method failed: {e}")

            try:
                # Method 2: Hostname fallback
                detection_info["messages"].append(
                    "🔄 Trying alternative detection method..."
                )

                hostname = socket.gethostname()
                local_ip = socket.gethostbyname(hostname)

                detection_info["detected_ip"] = local_ip
                detection_info["method_used"] = "hostname_resolution"

                if local_ip.startswith("127."):
                    detection_info["messages"].append(
                        f"⚠️ Hostname resolved to localhost ({local_ip})"
                    )
                    detection_info["messages"].append(
                        "🔧 Using default network range: 192.168.1.0/24"
                    )
                    detection_info["subnet"] = "192.168.1.0/24"
                    logger.warning(
                        "Hostname resolved to localhost, using default "
                        "192.168.1.0/24 network range."
                    )
                    return "192.168.1.0/24", detection_info

                detection_info["messages"].append(
                    f"✅ Found IP via hostname: {local_ip}"
                )

                ip_parts = local_ip.split(".")
                subnet = f"{ip_parts[0]}.{ip_parts[1]}.{ip_parts[2]}.0/24"

                detection_info["subnet"] = subnet
                detection_info["success"] = True
                detection_info["messages"].append(f"🌐 Will scan network: {subnet}")

                logger.info(f"Network detected via hostname: {local_ip} -> {subnet}")
                return subnet, detection_info

            except socket.gaierror as e:
                detection_info["messages"].append(
                    f"❌ All detection methods failed: {str(e)}"
                )
                detection_info["messages"].append(
                    "🔧 Using default network: 192.168.1.0/24"
                )
                detection_info["subnet"] = "192.168.1.0/24"
                logger.warning(f"All detection failed: {e}")
                return "192.168.1.0/24", detection_info

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
            result = nm.scan(subnet, arguments="-sn")  # Ping scan

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

    def scan_and_get_details(self, subnet):
        """
        Scans for Pis and then tries to get details for each one found.
        """
        hosts, msg, err = self.scan(subnet)
        if err:
            return [], msg, err

        detailed_hosts = []
        for host in hosts:
            details, detail_err = self.get_device_details(host["ip"])
            if detail_err:
                logger.warning(f"Could not get details for {host['ip']}: {detail_err}")
                # Add basic info even if details fail
                host["os_version"] = f"Error: {detail_err}"
            else:
                host.update(details)
            detailed_hosts.append(host)

        return detailed_hosts, msg, None
