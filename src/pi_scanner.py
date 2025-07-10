import logging
import subprocess
import re
import os
import sys
import json
import socket
import ipaddress

logger = logging.getLogger(__name__)

class PiScanner:
    """
    A tool to scan the local network and identify Raspberry Pi devices by calling
    the native nmap executable and parsing its XML output.
    """

    @staticmethod
    def _load_prefixes():
        """Loads the list of Raspberry Pi MAC prefixes from a JSON file."""
        # This path is relative to the project root where the runner script is executed.
        prefixes_path = os.path.join('config', 'raspberry_pi_oui.json')
        try:
            with open(prefixes_path, 'r') as f:
                data = json.load(f)
                return data.get('prefixes', [])
        except (FileNotFoundError, json.JSONDecodeError):
            print(f"Warning: Could not load or parse {prefixes_path}. Scanning may be incomplete.", file=sys.stderr)
            return []

    @staticmethod
    def _parse_nmap_output(nmap_xml_output, pi_oui_prefixes):
        """Parses the XML output from nmap to find Raspberry Pi devices."""
        # Local import for fast startup
        import xml.etree.ElementTree as etree

        found_devices = []
        found_macs = set()
        try:
            root = etree.fromstring(nmap_xml_output)
            for host in root.findall('host'):
                status = host.find('status')
                if status is None or status.get('state') != 'up':
                    continue

                ip_address_element = host.find('address[@addrtype="ipv4"]')
                mac_address_element = host.find('address[@addrtype="mac"]')

                if ip_address_element is not None and mac_address_element is not None:
                    ip = ip_address_element.get('addr')
                    mac = mac_address_element.get('addr').lower()

                    is_pi = any(mac.startswith(prefix) for prefix in pi_oui_prefixes)

                    if is_pi and mac not in found_macs:
                        found_devices.append({'ip': ip, 'mac': mac})
                        found_macs.add(mac)
        except etree.ParseError as e:
            print(f"Error parsing nmap XML output: {e}", file=sys.stderr)

        return found_devices

    @staticmethod
    def scan(target_subnet):
        """
        Scans the given subnet for potential Raspberry Pi devices using nmap.

        Args:
            target_subnet (str): The network subnet to scan (e.g., '192.168.1.0/24').

        Returns:
            list: A list of dictionaries, where each dictionary represents a
                  potential Pi with its 'ip' and 'mac' address.
        """
        logger.info(f"Starting nmap scan on subnet: {target_subnet}")
        try:
            # Use nmap to find hosts that are up and have the SSH port (22) open.
            # -p 22: Only scan for port 22
            # --open: Only show hosts where the port is open
            # -sn: Ping scan to discover hosts (can be redundant with -p but good practice)
            command = ['nmap', '-sn', '-p', '22', '--open', target_subnet]
            logger.debug(f"Executing nmap command: {' '.join(command)}")

            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False  # Do not raise an exception on non-zero exit code
            )

            # --- Diagnostic Logging ---
            # Log the raw output from nmap to help debug discovery issues.
            logger.debug(f"nmap scan completed with exit code: {result.returncode}")
            if result.stdout:
                logger.debug(f"--- nmap stdout ---\n{result.stdout}\n--- end nmap stdout ---")
            if result.stderr:
                # nmap often prints warnings to stderr, so we log it as a warning.
                logger.warning(f"--- nmap stderr ---\n{result.stderr}\n--- end nmap stderr ---")
            # --- End Diagnostic Logging ---

            if result.returncode != 0 and "command not found" in result.stderr.lower():
                logger.critical(
                    "The 'nmap' command was not found. Please ensure nmap is installed and accessible in the system's PATH.")
                return []

            # Parse the nmap output to find devices with a Raspberry Pi MAC address.
            # Regex to find blocks of text for each host.
            host_blocks = re.findall(r"Nmap scan report for ([\s\S]*?)(?=\nNmap scan report for|\Z)", result.stdout)
            potential_pis = []

            for block in host_blocks:
                ip_match = re.search(r"(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})", block)
                mac_match = re.search(r"MAC Address: ([0-9A-F:]+) \((Raspberry Pi.*?)\)", block, re.IGNORECASE)

                if ip_match and mac_match:
                    ip = ip_match.group(1)
                    mac = mac_match.group(1).lower
                    logger.info(f"Found potential Pi at {ip} with MAC {mac}")
                    potential_pis.append({'ip': ip, 'mac': mac})

            logger.info(f"Scan finished. Found {len(potential_pis)} potential Raspberry Pi devices.")
            return potential_pis

        except FileNotFoundError:
            logger.critical(
                "The 'nmap' command was not found. Please ensure nmap is installed and accessible in the system's PATH.")
            return []
        except Exception as e:
            logger.error(f"An unexpected error occurred during the nmap scan: {e}", exc_info=True)
            return []

    @staticmethod
    def _is_port_open(ip, port, timeout=1.0):
        """Checks if a TCP port is open on a given IP address."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        try:
            return sock.connect_ex((ip, port)) == 0
        except socket.gaierror:
            return False
        finally:
            sock.close()

    @staticmethod
    def get_device_details(ip, username, password):
        """
        Connects to a device via SSH to get detailed hardware information,
        but only after checking if the SSH port is open.
        """
        # Local import for fast startup
        import paramiko

        if not PiScanner._is_port_open(ip, 22):
            print(f"    Skipping SSH attempt for {ip}: Port 22 is not open.")
            return None

        client = None
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(hostname=ip, username=username, password=password, timeout=5)

            command = (
                "cat /sys/firmware/devicetree/base/model; echo '---'; "
                "free -h | grep Mem | awk '{print $2}'; echo '---'; "
                "cat /proc/cpuinfo | grep Serial | awk '{print $3}'; echo '---'; "
                "lsblk -o NAME,SIZE,TYPE,MOUNTPOINT --json"
            )
            _, stdout, _ = client.exec_command(command)
            output = stdout.read().decode().strip()

            details = {'ip': ip}
            parts = output.split('---')
            if len(parts) >= 4:
                details['model'] = parts[0].strip().replace('\x00', '')
                details['ram'] = parts[1].strip()
                details['serial'] = parts[2].strip()
                try:
                    disk_info = json.loads(parts[3].strip())
                    details['disks'] = disk_info.get('blockdevices', [])
                except json.JSONDecodeError:
                    details['disks'] = []
            return details
        except (paramiko.AuthenticationException, paramiko.SSHException, TimeoutError) as e:
            print(f"    Could not connect or get details for {ip}: {type(e).__name__}")
        except Exception as e:
            print(f"    An unexpected error occurred for {ip}: {e}", file=sys.stderr)
        finally:
            if client:
                client.close()
        return None

    @staticmethod
    def detect_subnet():
        """
        Attempts to detect the primary local subnet. Handles native Windows,
        Linux, macOS, and the WSL-on-Windows case.
        """
        try:
            # --- For WSL on Windows ---
            is_wsl = 'WSL_DISTRO_NAME' in os.environ
            if is_wsl:
                # In WSL, call the Windows 'ipconfig' command
                command = ['/mnt/c/Windows/System32/ipconfig.exe']
                result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=5)

                # Parse ipconfig output for the active adapter's IP and Subnet Mask
                # We look for an adapter that has a Default Gateway, which is usually the active one
                active_adapter_blocks = re.split(r'\r\n\r\n', result.stdout)
                for block in active_adapter_blocks:
                    if 'Default Gateway' in block and '192.168' in block:  # Filter for common private gateways
                        ip_match = re.search(r"IPv4 Address[ .]*: ([\d.]+)", block)
                        mask_match = re.search(r"Subnet Mask[ .]*: ([\d.]+)", block)
                        if ip_match and mask_match:
                            ip = ip_match.group(1)
                            mask = mask_match.group(1)
                            # Use the ipaddress module to correctly calculate the network address/CIDR
                            network = ipaddress.ip_network(f"{ip}/{mask}", strict=False)
                            return str(network)

            # --- For native Linux ---
            elif sys.platform.startswith('linux'):
                command = ['ip', '-o', '-4', 'addr', 'show']
                result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=5)
                # Parse 'ip addr' output
                for line in result.stdout.strip().splitlines():
                    if ' lo ' not in line and ' docker' not in line:  # Ignore loopback and docker interfaces
                        parts = line.split()
                        if len(parts) >= 4 and '/' in parts[3]:
                            return parts[3]

            # --- For native macOS ---
            elif sys.platform == "darwin":
                command = ['ifconfig']
                result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=5)
                # Parse 'ifconfig' output
                match = re.search(r"en\d:.*?inet (\d+\.\d+\.\d+\.\d+).*?netmask (0x[0-9a-fA-F]+)", result.stdout,
                                  re.DOTALL)
                if match:
                    ip = match.group(1)
                    netmask_hex = match.group(2)
                    # Convert hex netmask to CIDR
                    cidr = sum(bit == '1' for bit in bin(int(netmask_hex, 16)))
                    network = ipaddress.ip_network(f"{ip}/{cidr}", strict=False)
                    return str(network)

        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired, ValueError):
            # If any command fails or parsing goes wrong, return None
            return None

        return None