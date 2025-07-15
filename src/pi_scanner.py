import logging
import re
import socket
import subprocess
import time
from functools import lru_cache

import paramiko

# from unittest.mock import MagicMock, patch


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def is_port_open(host, port):
    """
    Check if a TCP port is open on a given host.

    This function attempts to connect to a specific port on a host.
    It returns True if the connection is successful, and False otherwise.

    :param host: The hostname or IP address to check.
    :param port: The port to check.
    :return: True if the port is open, False otherwise.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)  # Set a short timeout to avoid long waits
            if s.connect_ex((host, port)) == 0:
                return True
    except (socket.timeout, socket.gaierror):
        # socket.gaierror handles cases where the hostname is invalid
        return False
    return False


class PiScanner:
    """
    A class to scan the network for Raspberry Pi devices and retrieve their details.
    """

    # A list of known MAC address prefixes for Raspberry Pi devices.
    PI_MAC_PREFIXES = ("b8:27:eb", "dc:a6:32", "e4:5f:01")

    # The SSH command used to get the serial number from a Pi.
    # It reads from /proc/cpuinfo and filters for the line containing "Serial".
    SSH_COMMAND = "cat /proc/cpuinfo | grep 'Serial' | awk '{print $3}'"

    def __init__(self, username=None, password=None):
        """
        Initializes the PiScanner with optional SSH credentials.

        :param username: The SSH username for connecting to the Pi.
        :param password: The SSH password for connecting to the Pi.
        """
        self.username = username
        self.password = password

    def detect_subnet(self):
        """
        Automatically detect the local subnet (e.g., "192.168.1.0/24").

        This method works by creating a temporary connection to the internet
        to determine the local IP address of the machine running the scanner.
        It then constructs the subnet range based on that IP.

        :return: The detected subnet as a string, or None if detection fails.
        """
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                # Connect to a public DNS server to find the local IP
                s.connect(("8.8.8.8", 80))
                ip_address = s.getsockname()[0]
                # Construct the subnet by replacing the last octet with ".0/24"
                subnet = ".".join(ip_address.split(".")[:-1]) + ".0/24"
                return subnet
        except Exception as e:
            logger.error(f"Could not detect subnet: {e}")
            return None

    @staticmethod
    def scan(subnet):
        """
        Scan the given subnet for Raspberry Pi devices using nmap.

        This method uses nmap to perform a ping scan on the specified subnet.
        It then parses the output to find devices with MAC addresses that match
        known Raspberry Pi prefixes.

        :param subnet: The subnet to scan (e.g., "192.168.1.0/24").
        :return: A tuple containing:
                 - A list of dictionaries, where each dict represents a found Pi
                   and contains its 'ip' and 'mac' address.
                 - The raw stdout from the nmap command.
                 - The raw stderr from the nmap command.
        """
        if not subnet:
            logger.error("Subnet must be provided to scan.")
            return [], "", "Subnet not provided"

        found_pis = []
        try:
            # Use nmap to find all devices on the network and get their MACs
            command = ["nmap", "-sn", subnet, "-oG", "-"]
            logger.info(f"Running nmap command: {' '.join(command)}")
            proc = subprocess.run(
                command, capture_output=True, text=True, check=False, timeout=120
            )

            if proc.returncode != 0:
                logger.error(f"Nmap failed with error: {proc.stderr}")
                return [], proc.stdout, proc.stderr

            # Parse the output to find hosts with Raspberry Pi MAC addresses
            for line in proc.stdout.splitlines():
                if "Status: Up" not in line:
                    continue

                ip_match = re.search(
                    r"Host: (\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})", line
                )
                mac_match = re.search(r"MAC Address: ([0-9A-F:]+)", line)

                if ip_match and mac_match:
                    mac_address = mac_match.group(1).lower()
                    if any(
                        mac_address.startswith(prefix)
                        for prefix in PiScanner.PI_MAC_PREFIXES
                    ):
                        found_pis.append({"ip": ip_match.group(1), "mac": mac_address})

            return found_pis, proc.stdout, proc.stderr

        except FileNotFoundError:
            msg = "nmap is not installed or not in the system's PATH."
            logger.error(msg)
            return [], "", msg
        except subprocess.TimeoutExpired:
            msg = "Nmap scan timed out. The network may be too large or slow."
            logger.error(msg)
            return [], "", msg

    @lru_cache(maxsize=32)
    def get_device_details(self, ip, retries=3, delay=5):
        """
        Get detailed information from a Raspberry Pi using SSH.

        This method connects to a given IP address via SSH to fetch the device's
        serial number, model, RAM, and disk space. It uses paramiko for the
        SSH connection and has a retry mechanism for connection failures.

        :param ip: The IP address of the Raspberry Pi.
        :param retries: The number of times to retry the SSH connection.
        :param delay: The delay in seconds between retries.
        :return: A dictionary with device details, or None if connection fails.
        """
        if not all([self.username, self.password]):
            logger.warning("SSH credentials are not set; skipping detail retrieval.")
            return None

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        for attempt in range(retries):
            try:
                logger.info(f"Attempting to connect to {ip}, attempt {attempt + 1}")
                client.connect(
                    ip,
                    port=22,
                    username=self.username,
                    password=self.password,
                    timeout=10,
                )

                # Fetch hardware details
                _, stdout, _ = client.exec_command("cat /proc/cpuinfo")
                cpu_info = stdout.read().decode()
                serial = re.search(r"Serial\s*:\s*(\w+)", cpu_info).group(1)
                model_str = re.search(r"Model\s*:\s*(.*)", cpu_info).group(1)

                # Fetch RAM
                _, stdout, _ = client.exec_command("free -m | awk '/^Mem:/ {print $2}'")
                ram_mb = int(stdout.read().decode().strip())
                ram_gb = round(ram_mb / 1024, 1)

                # Fetch disk space
                _, stdout, _ = client.exec_command("df -h /")
                disk_info = stdout.read().decode().splitlines()[1].split()
                disk_size, disk_used, disk_avail = (
                    disk_info[1],
                    disk_info[2],
                    disk_info[3],
                )

                return {
                    "serial": serial,
                    "model": model_str,
                    "ram": f"{ram_gb} GB",
                    "disk": f"{disk_size} (Used: {disk_used}, Available: {disk_avail})",
                }

            except (
                paramiko.AuthenticationException,
                paramiko.SSHException,
                socket.error,
            ) as e:
                logger.error(f"SSH connection to {ip} failed: {e}")
                if attempt < retries - 1:
                    logger.info(f"Retrying in {delay} seconds...")
                    time.sleep(delay)
                else:
                    return None
            finally:
                client.close()

        return None
