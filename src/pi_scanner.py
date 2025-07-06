import subprocess
import re
import os
import sys
import json
import socket


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
        Actively scans a given subnet using the nmap executable and parses XML output.
        """
        pi_oui_prefixes = PiScanner._load_prefixes()
        if not pi_oui_prefixes:
            print("Warning: No Raspberry Pi MAC prefixes were loaded. Scan may not find any devices.", file=sys.stderr)

        if not target_subnet:
            print("Error: A target subnet must be provided.", file=sys.stderr)
            return []
        try:
            print(f"--> Performing a privileged scan on {target_subnet} with nmap...")
            command = ['nmap', '-sn', '-n', '-oX', '-', target_subnet]
            if sys.platform != "win32":
                command.insert(0, 'sudo')

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
    def _detect_subnet_linux():
        """Detects subnet on Linux."""
        command = ['ip', '-o', '-4', 'addr', 'show']
        result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=5)
        for line in result.stdout.strip().splitlines():
            if ' lo ' not in line and ' docker' not in line:
                parts = line.split()
                if len(parts) >= 4:
                    return parts[3]
        return None

    @staticmethod
    def _detect_subnet_macos():
        """Detects subnet on macOS."""
        command = ['ifconfig']
        result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=5)
        match = re.search(r"en\d:.*?inet (\d+\.\d+\.\d+\.\d+).*?netmask (0x[0-9a-fA-F]+)", result.stdout, re.DOTALL)
        if match:
            ip_address = match.group(1)
            netmask_hex = match.group(2)
            netmask_bin = bin(int(netmask_hex, 16))
            cidr = sum(bit == '1' for bit in netmask_bin)
            return f"{ip_address}/{cidr}"
        return None

    @staticmethod
    def detect_subnet():
        """Attempts to detect the primary local subnet."""
        try:
            if sys.platform.startswith('linux'):
                return PiScanner._detect_subnet_linux()
            elif sys.platform == "darwin":  # macOS
                return PiScanner._detect_subnet_macos()
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            return None
        return None