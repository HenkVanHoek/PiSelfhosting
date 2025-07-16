# file: src/pi_scanner.py
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
        "dc:a6:32",  # Raspberry Pi (Trading) Ltd
        "e4:5f:01",  # Raspberry Pi (Trading) Ltd
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
        Detects the local subnet based on the host's IP address.
        Returns the subnet in CIDR notation (e.g., '192.168.1.0/24')
        or a default value if detection fails.
        """
        try:
            # Get the hostname and then the IP address
            hostname = socket.gethostname()
            local_ip = socket.gethostbyname(hostname)

            # Construct the subnet
            ip_parts = local_ip.split(".")
            subnet = f"{ip_parts[0]}.{ip_parts[1]}.{ip_parts[2]}.0/24"
            logger.info(f"Detected local subnet: {subnet}")
            return subnet
        except socket.gaierror:
            logger.warning("Could not detect local IP. Falling back to default subnet.")
            # Fallback to a common default if detection fails
            return "192.168.1.0/24"

    @staticmethod
    def scan(subnet):
        """
        Scans the given subnet for Raspberry Pi devices using nmap.
        :param subnet: The subnet to scan (e.g., '192.168.1.0/24').
        :return: A tuple containing a list of found hosts,
        :a message, and an error string.
        """
        found_hosts = []
        try:
            logger.info(f"Starting nmap scan on subnet: {subnet}...")
            nm = nmap.PortScanner()
            # -sn: Ping Scan - disables port scan
            # -T4: Aggressive timing template for faster scans
            nm.scan(hosts=subnet, arguments="-sn -T4")
            logger.info(f"Scan complete. Hosts found: {', '.join(nm.all_hosts())}")

            for host in nm.all_hosts():
                if "mac" in nm[host]["addresses"]:
                    mac_address = nm[host]["addresses"]["mac"].lower()

                    # Check if the MAC address matches any of the Pi prefixes
                    if any(
                        mac_address.startswith(prefix)
                        for prefix in PiScanner.PI_MAC_PREFIXES
                    ):
                        logger.info(f"Found Raspberry Pi at {host} ({mac_address})")
                        found_hosts.append(
                            {
                                "ip": nm[host]["addresses"]["ipv4"],
                                "mac": mac_address,
                                "status": nm[host]["state"],
                            }
                        )
                else:
                    logger.debug(
                        f"Host {host} has no MAC address information. Skipping."
                    )

            if not found_hosts:
                return [], "No Raspberry Pi devices found on the network.", None

            return found_hosts, f"Found {len(found_hosts)} Raspberry Pi(s).", None

        except nmap.nmap.PortScannerError as e:
            logger.error(f"Nmap scan failed: {e}")
            return (
                [],
                "",
                f"Nmap scan failed. Ensure nmap is installed and "
                f"you have sufficient privileges. Error: {e}",
            )
        except Exception as e:
            logger.error(f"An unexpected error occurred during scan: {e}")
            return [], "", f"An unexpected error occurred: {e}"

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
