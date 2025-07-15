import json
import logging
import re
import socket
import subprocess

import paramiko

# Set up logging for the module
logger = logging.getLogger(__name__)


def is_port_open(ip, port, timeout=1):
    """
    Checks if a specific TCP port is open on a given IP address.

    Args:
        ip (str): The IP address to check.
        port (int): The port number to check.
        timeout (int, optional): Connection timeout in seconds. Defaults to 1.

    Returns:
        bool: True if the port is open, False otherwise.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        # connect_ex returns 0 if the connection is successful
        result = sock.connect_ex((ip, port))
        return result == 0
    except (socket.gaierror, socket.error):
        # Handle cases where the hostname is invalid or other socket errors occur
        return False
    finally:
        sock.close()


class PiScanner:
    """
    A class to scan the network for Raspberry Pi devices and retrieve their details.

    This scanner uses nmap to find devices with Raspberry Pi MAC addresses and then
    uses SSH to fetch hardware details from the devices.
    """

    # Class-level constants for MAC prefixes and SSH command
    PI_MAC_PREFIXES = {
        "b8:27:eb",  # Raspberry Pi Foundation
        "dc:a6:32",  # Raspberry Pi Foundation
        "e4:5f:01",  # Raspberry Pi Trading Ltd
    }

    SSH_COMMAND = """
    cat /proc/device-tree/model; echo '---';
    grep MemTotal /proc/meminfo | awk '{print $2, $3}'; echo '---';
    grep Serial /proc/cpuinfo | awk '{print $3}'; echo '---';
    lsblk -J -b -o NAME,SIZE,TYPE,MOUNTPOINT;
    """

    def __init__(self, username, password):
        """
        Initializes the scanner with credentials for SSH access.

        Args:
            username (str): The SSH username.
            password (str): The SSH password.
        """
        self.username = username
        self.password = password

    @staticmethod
    def detect_subnet():
        """
        Detects the most likely local subnet (e.g., '192.168.1.0/24').

        This method attempts to find the local IP address of the machine it's
        running on and assumes a /24 subnet, which is common for home networks.

        Returns:
            str: The detected subnet in CIDR notation, or a default value.
        """
        # noinspection PyBroadException
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                # Doesn't have to be reachable; used to get the local IP
                s.connect(("8.8.8.8", 80))
                ip_address = s.getsockname()[0]
                # Assume a /24 subnet, which is a common default
                subnet = ".".join(ip_address.split(".")[:-1]) + ".0/24"
                return subnet
        except Exception:
            logger.exception("Could not auto-detect subnet.")
            return "192.168.1.0/24"  # Fallback to a common default

    @staticmethod
    def scan(subnet):
        """
        Scans the given subnet for devices that appear to be Raspberry Pis.

        Args:
            subnet (str): The subnet to scan in CIDR notation (e.g., '192.168.1.0/24').

        Returns:
            tuple: A tuple containing:
                - list: A list of dictionaries, each representing a found Pi.
                - str: The stdout from the nmap command.
                - str: The stderr from the nmap command.
        """
        if not subnet:
            return [], "", "Subnet must be provided."

        # -sn: Ping scan (no ports)
        # -PR: ARP request to discover hosts
        command = ["nmap", "-sn", "-PR", subnet]
        try:
            result = subprocess.run(
                command, capture_output=True, text=True, check=True, timeout=120
            )
            stdout = result.stdout
            stderr = result.stderr
            logger.info("nmap scan successful.")

            found_pis = []
            # Regex to find MAC addresses and their preceding IP
            ip_mac_pattern = re.compile(
                r"Nmap scan report for (.*?)\n.*?MAC Address: ([\w:]+)"
            )

            for match in ip_mac_pattern.finditer(stdout):
                ip = match.group(1)
                mac = match.group(2).lower()
                # Check if the MAC address belongs to a Raspberry Pi
                if any(mac.startswith(prefix) for prefix in PiScanner.PI_MAC_PREFIXES):
                    found_pis.append({"ip": ip, "mac": mac})

            return found_pis, stdout, stderr

        except FileNotFoundError:
            logger.error(
                "nmap command not found. Is nmap installed and in the system's PATH?"
            )
            return [], "", "nmap is not installed."
        except subprocess.CalledProcessError as e:
            logger.error(
                f"nmap scan failed with return code {e.returncode}: {e.stderr}"
            )
            return [], e.stdout, e.stderr
        except subprocess.TimeoutExpired:
            logger.error("nmap scan timed out.")
            return [], "", "Scan timed out."

    def get_device_details(self, ip):
        """
        Connects to a device via SSH and retrieves hardware details.

        Args:
            ip (str): The IP address of the target device.

        Returns:
            dict or None: A dictionary with device details or None on failure.
        """
        if not is_port_open(ip, 22):
            logger.warning(f"SSH port 22 not open on {ip}. Skipping detail retrieval.")
            return None

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        try:
            # First, try connecting with key-based authentication
            logger.info(f"Attempting key-based SSH connection to {ip}...")
            client.connect(
                hostname=ip, username=self.username, password=None, timeout=10
            )
        except (paramiko.AuthenticationException, paramiko.SSHException):
            logger.info(f"Key-based auth failed. Trying password for {ip}...")
            try:
                # If key auth fails, fall back to password authentication
                client.connect(
                    hostname=ip,
                    username=self.username,
                    password=self.password,
                    timeout=10,
                )
            except (paramiko.AuthenticationException, paramiko.SSHException) as e:
                logger.error(f"SSH authentication failed for {ip}: {e}")
                return None

        try:
            stdin, stdout, stderr = client.exec_command(self.SSH_COMMAND)
            output = stdout.read().decode("utf-8").strip()
            err = stderr.read().decode("utf-8").strip()
            if err:
                logger.error(f"Error executing command on {ip}: {err}")

            parts = output.split("---\n")
            if len(parts) != 4:
                print(f"Could not parse all details from output: {output}")
                return None

            model, ram, serial, disk_json = parts
            return {
                "model": model.strip().replace("\x00", ""),
                "ram": ram.strip(),
                "serial": serial.strip(),
                "disks": json.loads(disk_json).get("blockdevices", []),
            }
        except Exception as my_err:
            logger.error(f"Failed to process SSH command output from {ip}: {my_err}")
            return None
        finally:
            client.close()
