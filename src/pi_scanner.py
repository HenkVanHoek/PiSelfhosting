# src/pi_scanner.py
import json
import re
import socket
import subprocess

import paramiko


class PiScanner:
    """
    A utility class to scan the network for Raspberry Pi devices
    and retrieve their hardware details via SSH.
    """

    # List of MAC address prefixes for Raspberry Pi devices
    PI_MAC_PREFIXES = [
        "b8:27:eb",  # Raspberry Pi Foundation
        "dc:a6:32",  # Raspberry Pi Foundation
        "e4:5f:01",  # Raspberry Pi Foundation
        "28:cd:c1",  # Raspberry Pi (Trading) Ltd
        "d8:3a:dd",  # Raspberry Pi (Trading) Ltd
    ]

    # Command to get multiple hardware details at once, separated by a delimiter
    # Uses null characters (\x00) and a unique string as delimiters
    # to handle multi-line outputs safely.
    SSH_COMMAND = (
        "cat /proc/device-tree/model; echo -e '\\x00---'; "
        "free -h | awk '/^Mem:/ {print $2}'; echo -e '\\x00---'; "
        "cat /proc/cpuinfo | grep Serial | awk '{print $3}'; echo -e '\\x00---'; "
        "lsblk -J -o NAME,SIZE,TYPE,MOUNTPOINT"
    )

    @staticmethod
    def detect_subnet():
        """
        Detects the most likely local subnet of the machine running the script.
        """
        try:
            # Create a temporary socket to find the local IP
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                # Doesn't have to be reachable
                s.connect(("8.8.8.8", 80))
                local_ip = s.getsockname()[0]
            # Assume a /24 subnet, which is common for home networks
            return ".".join(local_ip.split(".")[:-1]) + ".0/24"
        except socket.error:  # Catch specific network errors instead of all exceptions
            return ""

    @staticmethod
    def _is_port_open(host, port, timeout=0.5):
        """
        Checks if a specific TCP port is open on a host.
        Returns True if open, False otherwise.
        """
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(timeout)
                # Returns 0 if the connection is successful
                return s.connect_ex((host, port)) == 0
        except (socket.gaierror, socket.error):
            # Host not found or other socket error
            return False

    @staticmethod
    def scan(target_subnet):
        """
        Scans the given subnet for Raspberry Pi devices using nmap.
        """
        print(f"Scanning subnet {target_subnet} for Raspberry Pi devices...")
        try:
            # Use -sn for a ping scan (no port scan) and -oG - for grepable output
            # The command is split for readability
            command = [
                "nmap",
                "-sn",  # Ping scan - disables port scanning
                target_subnet,
            ]
            result = subprocess.run(
                command, capture_output=True, text=True, check=True, timeout=120
            )
        except FileNotFoundError:
            print("Error: 'nmap' command not found. Please install nmap.")
            return []
        except subprocess.CalledProcessError as e:
            print(f"Error running nmap: {e.stderr}")
            return []
        except subprocess.TimeoutExpired:
            print("Error: nmap scan timed out after 2 minutes.")
            return []

        found_pis = []
        # Regex to find IP and MAC addresses from nmap's standard output
        # This is more robust than parsing grepable output.
        ip_mac_pattern = re.compile(
            # Corrected: Removed redundant escape `\` before the dot in `[\d.]`
            r"Nmap scan report for ([\d.]+)\n.*?MAC Address: ([0-9A-F:]+)",
            re.DOTALL,
        )

        for match in ip_mac_pattern.finditer(result.stdout):
            ip, mac = match.groups()
            mac_lower = mac.lower()
            if any(
                mac_lower.startswith(prefix) for prefix in PiScanner.PI_MAC_PREFIXES
            ):
                found_pis.append({"ip": ip, "mac": mac})

        print(f"Scan complete. Found {len(found_pis)} potential Raspberry Pi(s).")
        return found_pis

    @staticmethod
    def get_device_details(ip, username, password=None):
        """
        Connects to a device via SSH and retrieves hardware details.
        Tries key-based auth first, then falls back to password auth.
        """
        if not PiScanner._is_port_open(ip, 22):
            print(f"SSH port 22 is not open on {ip}. Skipping.")
            return None

        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        try:
            # --- Attempt 1: Key-based authentication (password=None) ---
            try:
                ssh.connect(hostname=ip, username=username, password=None, timeout=5)
            except (paramiko.AuthenticationException, paramiko.SSHException):
                # --- Attempt 2: Password-based authentication (if provided) ---
                if password is not None:
                    ssh.connect(
                        hostname=ip, username=username, password=password, timeout=5
                    )
                else:
                    # If no password is provided and key auth fails, we can't connect.
                    raise paramiko.AuthenticationException(
                        "Key-based authentication failed and no password was provided."
                    )

            # If connection is successful, execute the command
            _stdin, stdout, stderr = ssh.exec_command(PiScanner.SSH_COMMAND)
            output = stdout.read().decode("utf-8", errors="ignore")
            error_output = stderr.read().decode("utf-8", errors="ignore")

            if error_output:
                print(f"Error retrieving details from {ip}: {error_output}")
                return None

            # Split the combined output by our unique delimiter
            parts = output.split("\x00---\n")
            if len(parts) < 4:
                print(f"Could not parse all details from {ip}. Output: {output}")
                return None

            model = parts[0].strip().replace("\x00", "")
            ram = parts[1].strip()
            serial = parts[2].strip()
            disks_json = parts[3].strip()

            try:
                disks_data = json.loads(disks_json)
                disks = disks_data.get("blockdevices", [])
            except json.JSONDecodeError:
                disks = []

            return {"model": model, "ram": ram, "serial": serial, "disks": disks}

        except (
            paramiko.AuthenticationException,
            paramiko.SSHException,
            socket.timeout,
            TimeoutError,
        ) as e:
            # This catches failures from both key and password attempts
            if isinstance(e, paramiko.AuthenticationException):
                print(f"Authentication failed for {ip} with user '{username}'.")
            else:
                print(f"SSH connection to {ip} failed: {e}")
            return None
        finally:
            ssh.close()
