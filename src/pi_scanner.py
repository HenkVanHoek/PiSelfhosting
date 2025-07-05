import subprocess
import re
import paramiko
import os
import sys
import xml.etree.ElementTree as ET


class PiScanner:
    """
    A tool to scan the local network and identify Raspberry Pi devices by calling
    the native nmap executable and parsing its XML output.
    """
    RASPBERRY_PI_OUI_PREFIXES = [
        'b8:27:eb',
        'dc:a6:32',
        'e4:5f:01',
        '2c:cf:67',
    ]

    @staticmethod
    def scan(target_subnet, debug=False):
        """
        Actively scans a given subnet using the nmap executable and parses XML output.
        """
        if not target_subnet:
            print("Error: A target subnet must be provided.", file=sys.stderr)
            return []

        found_devices = []
        try:
            print(f"--> Performing a privileged scan on {target_subnet} with nmap...")

            # Use -oX - to output XML to stdout. -sn is a ping scan.
            command = ['nmap', '-sn', '-oX', '-', target_subnet]
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

            # Parse the XML output from nmap
            root = ET.fromstring(nmap_result.stdout)
            for host in root.findall('host'):
                status = host.find('status')
                # Ensure the host is reported as 'up'
                if status is not None and status.get('state') == 'up':
                    ip_address_element = host.find('address[@addrtype="ipv4"]')
                    mac_address_element = host.find('address[@addrtype="mac"]')

                    # Both IP and MAC must be present to be useful
                    if ip_address_element is not None and mac_address_element is not None:
                        ip = ip_address_element.get('addr')
                        mac = mac_address_element.get('addr').lower()

                        for prefix in PiScanner.RASPBERRY_PI_OUI_PREFIXES:
                            if mac.startswith(prefix):
                                print(f"    ✅ Found Raspberry Pi: {ip} ({mac})")
                                if not any(d['mac'] == mac for d in found_devices):
                                    found_devices.append({'ip': ip, 'mac': mac})
                                break  # No need to check other prefixes for this MAC

            print(f"    Found {len(found_devices)} Pi(s) after parsing scan results.")

        except FileNotFoundError:
            print("Error: 'nmap' command not found. Please ensure Nmap is installed and in your system's PATH.",
                  file=sys.stderr)
        except subprocess.CalledProcessError as e:
            print(f"An error occurred running nmap. Do you have sudo/administrator permissions? Error: {e.stderr}",
                  file=sys.stderr)
        except subprocess.TimeoutExpired:
            print("Error: The network scan timed out.", file=sys.stderr)
        except Exception as e:
            print(f"An unexpected error occurred during scanning: {e}", file=sys.stderr)

        return found_devices

    @staticmethod
    def get_device_details(ip, username, password):
        """Connects to a device via SSH to get its unique serial number."""
        client = None
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(hostname=ip, username=username, password=password, timeout=5)

            stdin, stdout, stderr = client.exec_command("cat /proc/cpuinfo")
            output = stdout.read().decode().strip()

            match = re.search(r"Serial\s*:\s*(\w+)", output)
            if match:
                return {'serial': match.group(1), 'ip': ip}

        except (paramiko.AuthenticationException, paramiko.SSHException, TimeoutError):
            # Suppress noisy error messages for non-accessible devices
            pass
        except Exception as e:
            print(f"    An unexpected error occurred for {ip}: {e}", file=sys.stderr)
        finally:
            if client:
                client.close()

        return None

    @staticmethod
    def detect_subnet():
        """Attempts to detect the primary local subnet."""
        try:
            command = ['ip', '-o', '-4', 'addr', 'show']
            if sys.platform == "win32":
                # A different command would be needed for Windows, but 'ip' is fine for Linux/macOS
                # For simplicity in this tool, we only support the Linux/macOS auto-detect for now.
                return None

            ip_result = subprocess.run(
                command,
                capture_output=True, text=True, check=True, timeout=5
            )
            for line in ip_result.stdout.strip().splitlines():
                if ' lo ' not in line and ' docker' not in line:
                    parts = line.split()
                    if len(parts) >= 4:
                        return parts[3]
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            return None
        return None