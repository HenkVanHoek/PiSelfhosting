import ipaddress
import json
import logging
import os
import socket
import subprocess

import nmap
import psutil

from utils.resource_utils import resource_path

logger = logging.getLogger(__name__)


def _load_pi_mac_prefixes():
    try:
        config_path = resource_path(
            os.path.join("config", "raspberry_pi_oui.json"))
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return set(data.get("prefixes", []))
    except (FileNotFoundError, json.JSONDecodeError):
        logger.error("Could not load Raspberry Pi MAC prefixes")
        return set()


PI_MAC_PREFIXES = _load_pi_mac_prefixes()


def is_raspberry_pi(mac_address):
    if not mac_address:
        return False
    mac_prefix = mac_address[:8].lower()
    return mac_prefix in PI_MAC_PREFIXES


def is_port_open(host, port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(1)
    try:
        s.connect((host, port))
        s.close()
        return True
    except (socket.timeout, ConnectionRefusedError):
        return False


class PiScanner:
    SSH_COMMAND = (
        "cat /etc/os-release && "
        "echo '---' && "
        "cat /proc/cpuinfo | grep Serial | cut -d ' ' -f 2 && "
        "echo '---' && "
        "cat /proc/device-tree/model && "
        "echo '---' && "
        "free -m | grep Mem | awk '{print $2 \" MB\"}' && "
        "echo '---' && "
        "df -h --output=source,size,used,avail,pcent,target"
    )

    def __init__(self, username, password):
        self.username = username
        self.password = password

    @staticmethod
    def get_primary_ip():
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0)
        try:
            s.connect(("8.8.8.8", 1))
            # Use an intermediate variable for clarity and to ensure correctness
            sock_info_tuple = s.getsockname()
            ip_address = sock_info_tuple
        except OSError:
            return "127.0.0.1"
        except Exception:
            logging.exception("Unexpected error in get_local_ip")
            return "127.0.0.1"
        finally:
            s.close()
        return ip_address

    @staticmethod
    def detect_subnet():
        primary_ip = PiScanner.get_primary_ip()
        if primary_ip == "127.0.0.1":
            logger.warning("Could not determine a non-loopback IP address.")
            return None

        logger.info(f"🔍 Primary IP detected: {primary_ip}")
        all_addrs = psutil.net_if_addrs()
        for interface_addresses in all_addrs.values():
            for addr in interface_addresses:
                if addr.family == socket.AF_INET and addr.address == primary_ip:
                    netmask = addr.netmask
                    logger.info(f"   - IP Address: {addr.address}")
                    logger.info(f"   - Netmask:    {netmask}")
                    network = ipaddress.IPv4Network(
                        f"{addr.address}/{netmask}", strict=False
                    )
                    logger.info(
                        f"🌐 Calculated Subnet: {network.with_prefixlen}")
                    return str(network.with_prefixlen)

        logger.warning(
            "❌ Could not find interface details for the primary IP using psutil.")
        return None

    def scan(self, subnet=None):
        detection_info = {}
        messages = []

        if subnet is None:
            detected_subnet = self.detect_subnet()
            if detected_subnet:
                subnet = detected_subnet
                detection_info = {
                    "success": True,
                    "method_used": "auto_detect",
                    "detected_ip": self.get_primary_ip(),
                    "subnet": subnet,
                }
                messages.append(f"✅ Subnet auto-detected: {subnet}")
            else:
                error_msg = "Could not auto-detect subnet. Please provide one manually."
                messages.append(error_msg)
                detection_info["success"] = False
                return [], messages, error_msg, detection_info
        else:
            detection_info = {"success": True, "method_used": "user_provided",
                              "subnet": subnet}
            messages.append(f"🎯 Using provided network: {subnet}")

        messages.append(f"🔍 Scanning {subnet} for Raspberry Pi devices...")

        try:
            nm = nmap.PortScanner()
            result = nm.scan(hosts=subnet, arguments="-sn -PR", sudo=True)

            hosts = []
            scanned_hosts = list(result["scan"].keys())
            messages.append(f"📡 Found {len(scanned_hosts)} active devices")
            detection_info['total_hosts_scanned'] = len(scanned_hosts)

            pi_count = 0
            mac_address_count = 0
            for host in scanned_hosts:
                host_info = result["scan"][host]
                if "addresses" in host_info and "mac" in host_info["addresses"]:
                    mac_address_count += 1
                    mac_address = host_info["addresses"]["mac"].upper()
                    vendor = host_info["vendor"].get(mac_address, "Unknown")
                    if is_raspberry_pi(mac_address):
                        pi_count += 1
                        hosts.append({
                            "ip": host, "mac": mac_address, "vendor": vendor,
                            "hostname": host_info.get("hostnames", [{}]).get(
                                "name", "Unknown"),
                        })
                        messages.append(
                            f"🍓 Raspberry Pi found: {host} ({vendor})")

            detection_info['mac_addresses_found'] = mac_address_count

            if pi_count == 0:
                messages.append(
                    "⚠️ No Raspberry Pi devices found in this network")
            else:
                messages.append(
                    f"✅ Scan complete: {pi_count} Raspberry Pi(s) discovered")

            logger.info(
                f"Scan completed. Found {len(hosts)} Raspberry Pi devices.")
            return hosts, messages, "", detection_info
        except Exception as e:
            error_msg = f"❌ Scan failed: {str(e)}"
            logger.error(f"Scan failed: {e}")
            detection_info["success"] = False
            return [], messages, error_msg, detection_info

    def get_device_details(self, ip_address):
        if not is_port_open(ip_address, 22):
            return None, f"SSH port 22 is not open on {ip_address}."

        try:
            command = [
                "sshpass", "-p", self.password, "ssh",
                "-o", "StrictHostKeyChecking=no",
                "-o", "ConnectTimeout=10",
                f"{self.username}@{ip_address}", self.SSH_COMMAND,
            ]
            result = subprocess.run(command, capture_output=True, text=True,
                                    timeout=20)

            if result.returncode != 0:
                return None, f"SSH command failed: {result.stderr.strip()}"

            parts = result.stdout.strip().split("\n---\n")
            if len(parts) < 5:
                return None, "Failed to parse all details from SSH output."

            os_info_raw, serial_raw, model_raw, ram_raw, disk_raw = parts
            os_info = dict(
                line.split("=", 1)
                for line in os_info_raw.strip().split("\n")
                if "=" in line
            )

            disk_lines = disk_raw.strip().split("\n")[1:]
            disks = []
            for line in disk_lines:
                line_parts = line.split()
                if len(line_parts) == 6:
                    disks.append(dict(
                        zip(["filesystem", "size", "used", "avail", "pcent",
                             "mounted_on"], line_parts)))

            details = {
                "os_version": os_info.get("PRETTY_NAME", "N/A").strip('"'),
                "serial": serial_raw.strip(),
                "model": model_raw.strip().replace("\x00", ""),
                "ram": ram_raw.strip(),
                "disks": disks,
            }
            return details, None
        except FileNotFoundError:
            msg = "sshpass is not installed. This tool is required for SSH."
            logger.error(msg)
            return None, msg
        except subprocess.TimeoutExpired:
            msg = f"SSH command timed out for {ip_address}."
            logger.error(msg)
            return None, msg
        except Exception as e:
            msg = f"An unexpected SSH error occurred: {e}"
            logger.error(msg, exc_info=True)
            return None, msg

    def scan_and_get_details(self, subnet, per_device_callback=None):
        """
        Scans for Pis and then tries to get details for each one found.
        """
        hosts, messages, err, _ = self.scan(subnet)
        if err:
            return [], messages, err

        detailed_hosts = []
        for host in hosts:
            details, detail_err = self.get_device_details(host["ip"])

            if detail_err and per_device_callback:
                custom_creds = per_device_callback(host["ip"], detail_err)
                if custom_creds:
                    username, password = custom_creds
                    temp_scanner = PiScanner(username, password)
                    details, detail_err = temp_scanner.get_device_details(
                        host["ip"])

            if detail_err:
                logger.warning(
                    f"Could not get details for {host['ip']}: {detail_err}"
                )
                host["os_version"] = f"Error: {detail_err}"
                host["details_available"] = False
            else:
                host.update(details)
                host["details_available"] = True

            detailed_hosts.append(host)

        return detailed_hosts, messages, None