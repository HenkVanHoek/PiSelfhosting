import json
import re
import socket
import subprocess
from typing import Dict, List, Optional

import paramiko


def is_port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    """
    Checks if a specific TCP port is open on a host.
    Returns True if open, False otherwise.
    This is a module-level helper function.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            # s.connect_ex returns 0 if the connection is successful
            return s.connect_ex((host, port)) == 0
    except (socket.gaierror, socket.error):
        # Handles cases where the host is not found or other socket errors
        return False


class PiScanner:
    """
    A utility class to scan the network for Raspberry Pi devices
    and retrieve their hardware details via SSH.
    """

    # List of official MAC address prefixes for Raspberry Pi devices
    PI_MAC_PREFIXES: List[str] = [
        "b8:27:eb",  # Raspberry Pi Foundation
        "dc:a6:32",  # Raspberry Pi Foundation
        "e4:5f:01",  # Raspberry Pi Foundation
        "28:cd:c1",  # Raspberry Pi (Trading) Ltd
        "d8:3a:dd",  # Raspberry Pi (Trading) Ltd
    ]

    SSH_COMMAND: str = (
        "cat /proc/device-tree/model; echo -e '\\x00---'; "
        "free -h | awk '/^Mem:/ {print $2}'; echo -e '\\x00---'; "
        "cat /proc/cpuinfo | grep Serial | awk '{print $3}'; echo -e '\\x00---'; "
        "lsblk -J -o NAME,SIZE,TYPE,MOUNTPOINT"
    )

    @staticmethod
    def detect_subnet() -> str:
        """
        Detects the most likely local subnet of the machine running the script.
        """
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                local_ip = s.getsockname()[0]
            return ".".join(local_ip.split(".")[:-1]) + ".0/24"
        except socket.error:
            return ""

    @classmethod
    def scan(cls, subnet: str):
        """
        Scans the given subnet for Raspberry Pi devices using nmap.
        Returns a tuple: (found_pis, nmap_stdout, nmap_stderr)
        """
        if not subnet:
            print("Error: A valid subnet (e.g., '192.168.1.0/24') must be provided.")
            return [], "", "No subnet provided."

        print(f"Scanning subnet {subnet} for Raspberry Pi devices...")
        found_pis = []
        nmap_stdout = ""
        nmap_stderr = ""
        try:
            # Use check=False to be able to capture stderr even on failure
            nmap_args = ["nmap", "-sn", subnet]
            result = subprocess.run(
                nmap_args,
                capture_output=True,
                text=True,
                check=False,
                timeout=180,
                encoding="utf-8",
                errors="replace",
            )
            nmap_stdout = result.stdout
            nmap_stderr = result.stderr

            if result.returncode != 0:
                print(f"Nmap exited with code {result.returncode}")

            pattern = re.compile(
                r"Nmap scan report for "
                r"([\d.]+)\s+Host is up.*?\s+MAC Address: ([0-9A-F:]+)",
                re.DOTALL | re.IGNORECASE,
            )
            matches = pattern.findall(nmap_stdout)

            for ip, mac in matches:
                mac_lower = mac.lower()
                if any(mac_lower.startswith(p) for p in cls.PI_MAC_PREFIXES):
                    found_pis.append({"ip": ip, "mac": mac_lower})

        except FileNotFoundError:
            nmap_stderr = (
                "Error: 'nmap' command not found. Is nmap installed and in your PATH?"
            )
        except subprocess.TimeoutExpired:
            nmap_stderr = "Error: nmap scan timed out after 3 minutes."

        print(f"Scan complete. Found {len(found_pis)} potential Raspberry Pi(s).")
        return found_pis, nmap_stdout, nmap_stderr

    @staticmethod
    def get_device_details(
        ip: str, username: str, password: Optional[str] = None
    ) -> Optional[Dict]:
        """
        Connects to a device via SSH and retrieves hardware details.
        """
        # MODIFICATION: Use the public module-level helper function
        if not is_port_open(ip, 22):
            print(f"SSH port 22 is not open on {ip}. Skipping.")
            return None

        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        try:
            try:
                ssh.connect(hostname=ip, username=username, password=None, timeout=10)
            except (paramiko.AuthenticationException, paramiko.SSHException):
                if password is not None:
                    ssh.connect(
                        hostname=ip, username=username, password=password, timeout=10
                    )
                else:
                    raise paramiko.AuthenticationException(
                        "Key-based authentication failed and no password was provided."
                    )

            _stdin, stdout, stderr = ssh.exec_command(PiScanner.SSH_COMMAND, timeout=15)
            output = stdout.read().decode("utf-8", errors="ignore")
            error_output = stderr.read().decode("utf-8", errors="ignore")

            if error_output:
                print(f"Error retrieving details from {ip}: {error_output}")
                return None

            parts = output.split("\x00---\n")
            if len(parts) < 4:
                print(f"Could not parse all details from {ip}. Raw output: {output}")
                return None

            model = parts[0].strip().replace("\x00", "")
            ram = parts[1].strip()
            serial = parts[2].strip()
            disks_json_str = parts[3].strip()

            try:
                disks_data = json.loads(disks_json_str)
                disks = disks_data.get("blockdevices", [])
            except json.JSONDecodeError:
                print(f"Could not parse disk JSON from {ip}: {disks_json_str}")
                disks = []

            return {"model": model, "ram": ram, "serial": serial, "disks": disks}

        except (
            paramiko.AuthenticationException,
            paramiko.SSHException,
            socket.timeout,
        ) as e:
            if isinstance(e, paramiko.AuthenticationException):
                print(f"Authentication failed for {ip} with user '{username}'.")
            else:
                print(f"SSH connection to {ip} failed: {e}")
            return None
        finally:
            ssh.close()
