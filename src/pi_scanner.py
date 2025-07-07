import subprocess
import re
import os
import sys
import json
import socket
import ipaddress


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
    def scan(target_subnet, debug=False):
        """
        Actively scans a given subnet. From WSL, it calls the Windows nmap executable.
        Otherwise, it uses the native nmap command.
        """
        pi_oui_prefixes = PiScanner._load_prefixes()
        if not pi_oui_prefixes:
            print("Warning: No Raspberry Pi MAC prefixes were loaded. Scan may not find any devices.", file=sys.stderr)

        if not target_subnet:
            print("Error: A target subnet must be provided.", file=sys.stderr)
            return []

        # --- Command selection logic ---
        is_wsl = 'WSL_DISTRO_NAME' in os.environ
        nmap_path_windows = '/mnt/c/Program Files (x86)/Nmap/nmap.exe'

        if is_wsl and os.path.exists(nmap_path_windows):
            # If in WSL and Windows Nmap exists, use it. No sudo needed.
            print("--> In WSL, using native Windows Nmap for scan...")
            command = [nmap_path_windows, '-sn', '-n', '-oX', '-', target_subnet]
        else:
            # Otherwise, use the original logic for native Linux, macOS, or Windows
            print(f"--> Performing a privileged scan on {target_subnet} with nmap...")
            command = ['nmap', '-sn', '-n', '-PR', '-oX', '-', target_subnet]
            if sys.platform != "win32" and not is_wsl:
                command.insert(0, 'sudo')
        # --- End of command selection ---

        try:
            nmap_result = subprocess.run(
                command, capture_output=True, text=True, check=True, timeout=120
            )
            print("    Scan complete.")

            if debug:
                print("\n--- Raw Nmap XML Output (Debug Mode) ---")
                print(nmap_result.stdout)
                print("----------------------------------------\n")

            print("--> Parsing results to identify Raspberry Pis...")
            found_devices = PiScanner._parse_nmap_output(nmap_result.stdout, pi_oui_prefixes)
            print(f"    Found {len(found_devices)} Pi(s) after parsing scan results.")
            return found_devices
        except FileNotFoundError:
            if is_wsl:
                print(
                    f"Error: Nmap for Windows not found at '{nmap_path_windows}'. Please install it to the default location.",
                    file=sys.stderr)
            else:
                print("Error: 'nmap' command not found. Please ensure Nmap is installed and in your system's PATH.",
                      file=sys.stderr)
        except subprocess.CalledProcessError as e:
            print(f"An error occurred running nmap. Do you have sudo/administrator permissions? Error: {e.stderr}",
                  file=sys.stderr)
        except subprocess.TimeoutExpired:
            print("Error: The network scan timed out. Your network may be blocking ping scans.", file=sys.stderr)
        except Exception as e:
            print(f"An unexpected error occurred during scanning: {e}", file=sys.stderr)
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