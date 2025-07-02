# /home/PiSelfhosting/src/frigate_camera_config_tool.py

import os
import sys
import json
import yaml
import subprocess
import time
from urllib.parse import quote
import ipaddress # For IP address parsing
import re # For regular expressions

# ONVIF imports
from onvif import ONVIFCamera
# Attempting to import discover from onvif.discovery, with robust error handling in discover_onvif_cameras
try:
    from onvif.discovery import discover
    ONVIF_DISCOVERY_AVAILABLE = True
except ImportError:
    # print("Warning: 'onvif.discovery' module not found. ONVIF camera discovery will be unavailable.") # Removed for cleaner output on startup
    ONVIF_DISCOVERY_AVAILABLE = False

from onvif.exceptions import ONVIFError
from zeep.exceptions import Fault
import asyncio
import platform

# Define base directory (consistent with your existing setup)
BASE_DIR = "/app/piselfhosting" # Changed for Docker container context
FRIGATE_CONFIG_PATH = os.path.join(BASE_DIR, "docker", "frigate", "config", "config.yml")
COMMUNITY_CAMERAS_FILE = os.path.join(BASE_DIR, "scripts", "community_cameras.json") # New file for community camera presets

# Common default camera credentials to try (for basic access, not ONVIF discovery itself)
COMMON_DEFAULT_CREDENTIALS = [
    {"user": "admin", "pass": "admin"},
    {"user": "admin", "pass": "123456"},
    {"user": "user", "pass": "user"},
    {"user": "root", "pass": "admin"},
    {"user": "admin", "pass": ""}, # Empty password
    {"user": "", "pass": ""},     # No credentials
]

def get_env_variable(key):
    """Loads a variable from the .env file. Prefer os.getenv for variables loaded by sourcing the .env."""
    # When the run-frigate-config-tool.sh script sources the .env, these are already
    # in the environment. So os.getenv is the correct way to retrieve them within python.
    return os.getenv(key, "")

def url_encode_password(password):
    """Encodes a password for use in a URL, including special characters."""
    # quote() encodes most special characters, safe for URL components
    return quote(password, safe='') # safe='' encodes ALL special characters

def get_local_subnet_suggestion():
    """
    Attempts to get the host's primary IP address and suggest a /24 subnet range.
    Returns a string like "192.168.1.1-254" or an empty string if unable to determine.
    """
    try:
        # Use 'hostname -I' to get local IPs, which should work in host network mode
        result = subprocess.run(['hostname', '-I'], capture_output=True, text=True, check=True, timeout=5)
        output_ips = result.stdout.strip().split()

        for ip_str in output_ips:
            try:
                # Try to parse as IPv4 and suggest the /24 range
                ip_obj = ipaddress.ip_address(ip_str)
                if ip_obj.version == 4:
                    network = ipaddress.ip_network(f"{ip_obj}/24", strict=False)
                    # Get the network address (e.g., 192.168.1.0) and suggest 1-254
                    network_prefix = str(network.network_address).rsplit('.', 1)[0]
                    return f"{network_prefix}.1-254"
            except ipaddress.AddressValueError:
                continue # Not a valid IP, try next one
        return "" # No valid IPv4 found
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as e:
        # print(f"Warning: Could not determine local IP for subnet suggestion: {e}") # Debugging
        return ""
    except Exception as e:
        # print(f"Unexpected error getting subnet suggestion: {e}") # Debugging
        return ""


def test_rtsp_stream(rtsp_url, timeout=10):
    """
    Tests an RTSP stream using ffprobe to check if it's reachable and contains valid video.
    Requires ffmpeg/ffprobe to be installed on the system.
    """
    print(f"Testing RTSP stream: {rtsp_url} (max. {timeout} seconds)...")
    try:
        # Use ffprobe to get stream information
        command = [
            'ffprobe',
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_streams',
            '-i', rtsp_url
        ]
        
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        stdout, stderr = process.communicate(timeout=timeout)
        
        if process.returncode == 0:
            try:
                data = json.loads(stdout)
                if 'streams' in data and len(data['streams']) > 0:
                    for stream in data['streams']:
                        if stream.get('codec_type') == 'video':
                            print(f"✅ RTSP stream is valid and contains video: {rtsp_url}")
                            return True
                print(f"❌ RTSP stream is reachable but does not contain video streams or is incomplete: {rtsp_url}")
                print(f"  FFprobe output: {stdout}")
                print(f"  FFprobe errors: {stderr}")
                return False
            except json.JSONDecodeError:
                print(f"❌ Error parsing FFprobe JSON output for {rtsp_url}: {stdout}")
                print(f"  FFprobe errors: {stderr}")
                return False
        else:
            print(f"❌ FFprobe could not open the stream or returned an error (exit code {process.returncode}) for {rtsp_url}.")
            print(f"  FFprobe errors: {stderr}")
            if "Connection refused" in stderr or "No route to host" in stderr:
                print("  Possible network issue or stream is not active.")
            elif "Unauthorized" in stderr or "401" in stderr:
                print("  Authentication error. Check username and password.")
            return False
    except FileNotFoundError:
        print("❌ Error: 'ffprobe' not found. Please install FFmpeg: sudo apt install ffmpeg")
        return False
    except subprocess.TimeoutExpired:
        process.kill()
        stdout, stderr = process.communicate()
        print(f"❌ Timeout ({timeout}s) while testing RTSP stream: {rtsp_url}")
        print(f"  FFprobe errors (if any): {stderr.strip()}")
        return False
    except Exception as e:
        print(f"❌ An unexpected error occurred while testing the stream: {e}")
        return False

def validate_url_template(template_string):
    """
    Validates if a URL template string contains the required placeholders.
    """
    required_placeholders = ["{user}", "{password}", "{ip}", "{port}"]
    for placeholder in required_placeholders:
        if placeholder not in template_string:
            return False
    return True

def load_community_cameras():
    """
    Loads a list of community-contributed camera presets.
    If the file doesn't exist or is invalid, it initializes it with common presets.
    This function now relies on the host script to ensure the path is a file or non-existent.
    It now also validates templates upon loading.
    """
    valid_presets = []
    if os.path.exists(COMMUNITY_CAMERAS_FILE):
        try:
            with open(COMMUNITY_CAMERAS_FILE, 'r') as f:
                loaded_presets = json.load(f)
                if not isinstance(loaded_presets, list):
                    print(f"Warning: {COMMUNITY_CAMERAS_FILE} contains invalid format (not a list). Will recreate.")
                    os.remove(COMMUNITY_CAMERAS_FILE) # Remove invalid file
                else:
                    for preset in loaded_presets:
                        if isinstance(preset, dict) and "name" in preset and "url_template" in preset:
                            if validate_url_template(preset["url_template"]):
                                valid_presets.append(preset)
                            else:
                                print(f"Warning: Preset '{preset.get('name', 'Unknown')}' in {COMMUNITY_CAMERAS_FILE} has an invalid URL template: '{preset['url_template']}'. Skipping this preset.")
                        else:
                            print(f"Warning: Malformed preset found in {COMMUNITY_CAMERAS_FILE}: {preset}. Skipping.")
        except (json.JSONDecodeError, Exception) as e: # Catch JSON errors or general file reading errors
            print(f"Warning: Error parsing {COMMUNITY_CAMERAS_FILE} ({e}). File is corrupted and will be recreated.")
            os.remove(COMMUNITY_CAMERAS_FILE) # Remove corrupted file
    
    # If no valid presets were loaded (either file didn't exist, was corrupted, or all were invalid),
    # or if the file was removed due to corruption, initialize with popular cameras.
    if not valid_presets:
        initial_presets = [
            {
                "name": "Tapo C200/C310",
                "url_template": "rtsp://{user}:{password}@{ip}:{port}/stream0",
                "notes": "Common for TP-Link Tapo C100, C200, C310, etc."
            },
            {
                "name": "Reolink (main stream)",
                "url_template": "rtsp://{user}:{password}@{ip}:{port}/h264Preview_01_main",
                "notes": "Common for Reolink NVR/cameras main stream (varies by model)"
            },
            {
                "name": "Reolink (sub stream)",
                "url_template": "rtsp://{user}:{password}@{ip}:{port}/h264Preview_01_sub",
                "notes": "Common for Reolink NVR/cameras sub stream (varies by model)"
            },
            {
                "name": "Hikvision (main stream)",
                "url_template": "rtsp://{user}:{password}@{ip}:{port}/Streaming/Channels/101",
                "notes": "Hikvision main stream (channel=1, stream=0)"
            },
            {
                "name": "Hikvision (sub stream)",
                "url_template": "rtsp://{user}:{password}@{ip}:{port}/Streaming/Channels/102",
                "notes": "Hikvision sub stream (channel=1, stream=1)"
            },
            {
                "name": "Dahua (main stream)",
                "url_template": "rtsp://{user}:{password}@{ip}:{port}/cam/realmonitor?channel=1&subtype=0",
                "notes": "Dahua main stream"
            },
            {
                "name": "Dahua (sub stream)",
                "url_template": "rtsp://{user}:{password}@{ip}:{port}/cam/realmonitor?channel=1&subtype=1",
                "notes": "Dahua sub stream"
            },
            {
                "name": "Generic ONVIF Profile 1",
                "url_template": "rtsp://{user}:{password}@{ip}:{port}/onvif/profile1",
                "notes": "Common for ONVIF compliant cameras, profile 1"
            },
            {
                "name": "Generic ONVIF Profile S",
                "url_template": "rtsp://{user}:{password}@{ip}:{port}/onvif/profile.rtsp",
                "notes": "Another common ONVIF path"
            },
            {
                "name": "Generic IP Camera (Live)",
                "url_template": "rtsp://{user}:{password}@{ip}:{port}/live",
                "notes": "Some cameras simply use '/live'"
            }
        ]
        save_community_cameras(initial_presets)
        print(f"Info: {COMMUNITY_CAMERAS_FILE} has been created/recreated with a base list of camera presets.")
        return initial_presets
    
    return valid_presets

def save_community_cameras(cameras):
    """Saves the current list of community cameras."""
    # Ensure the directory exists before saving
    os.makedirs(os.path.dirname(COMMUNITY_CAMERAS_FILE), exist_ok=True)
    with open(COMMUNITY_CAMERAS_FILE, 'w') as f:
        json.dump(cameras, f, indent=2)

def add_new_camera_preset(camera_presets):
    """Interactively adds a new camera preset to the community list."""
    print("\n--- Add New Camera Preset ---")
    preset_name = input("Enter a unique name for this preset (e.g., 'My Custom Camera Model'): ").strip()
    if not preset_name:
        print("Name cannot be empty. Cancelling.")
        return camera_presets

    # Instruct user how to use placeholders
    print("Enter the base RTSP URL template.")
    print("Use placeholders: {user} for username, {password} for password, {ip} for IP address/hostname, {port} for port.")
    print("Example: rtsp://{user}:{password}@{ip}:{port}/stream0")
    model_url_template = input("RTSP URL template: ").strip()
    if not model_url_template:
        print("URL template cannot be empty. Cancelling.")
        return camera_presets
    
    # Validate the new URL template
    if not validate_url_template(model_url_template):
        print("Error: The URL template must contain all placeholders: {user}, {password}, {ip}, {port}. Please try again.")
        return camera_presets

    # Check for duplicates
    for preset in camera_presets:
        if preset['name'].lower() == preset_name.lower():
            print(f"Error: Preset with name '{preset_name}' already exists.")
            return camera_presets

    camera_presets.append({"name": preset_name, "url_template": model_url_template})
    save_community_cameras(camera_presets)
    print(f"Preset '{preset_name}' added.")
    return camera_presets


async def discover_onvif_cameras(ip_range_str=None):
    """
    Discovers ONVIF cameras. Can either use built-in discovery (if available)
    or scan a provided IP range.
    Returns a list of dictionaries with camera details.
    """
    found_cameras = []
    
    # Retrieve default RTSP username and password from environment (set by setup.sh)
    # These are the credentials the user set globally in their .env
    default_env_rtsp_username = get_env_variable("FRIGATE_RTSP_USERNAME")
    default_env_rtsp_password = get_env_variable("FRIGATE_RTSP_PASSWORD")

    # Create a dynamic list of credentials to try during ONVIF access
    # Prioritize the user's specified .env credentials, then common defaults
    dynamic_creds_to_try = []

    # Add the user's .env credentials first, if they are not empty
    if default_env_rtsp_username or default_env_rtsp_password:
        dynamic_creds_to_try.append({"user": default_env_rtsp_username, "pass": default_env_rtsp_password})
        print(f"Info: Adding .env RTSP credentials ({default_env_rtsp_username}:***) to ONVIF scan attempts.")
    
    # Add common default credentials (ensure no exact duplicates if they happen to match .env ones)
    for cred in COMMON_DEFAULT_CREDENTIALS:
        # Avoid adding exact duplicates if already added from .env (basic check)
        if not any(d['user'] == cred['user'] and d['pass'] == cred['pass'] for d in dynamic_creds_to_try):
            dynamic_creds_to_try.append(cred)

    if ip_range_str:
        print(f"\nScanning IP range {ip_range_str} for ONVIF cameras...")
        ip_addresses_to_scan = []
        if '-' in ip_range_str:
            # Handle IP range like 192.168.1.1-254
            parts = ip_range_str.split('.')
            if len(parts) != 4:
                print(f"Invalid IP range format: {ip_range_str}. Expected format like 192.168.1.1-254.")
                return []
            
            base_ip = ".".join(parts[:3]) + "."
            last_octet_range = parts[3].split('-')
            try:
                start_octet = int(last_octet_range[0])
                end_octet = int(last_octet_range[1])
                for i in range(start_octet, end_octet + 1):
                    ip_addresses_to_scan.append(f"{base_ip}{i}")
            except ValueError:
                print(f"Invalid IP range format: {ip_range_str}. Octets must be integers.")
                return []
        else:
            # Assume a single IP address
            ip_addresses_to_scan.append(ip_range_str)

        # Added port 2020 for Tapo C310 ONVIF
        onvif_ports_to_try = [80, 8000, 8080, 2020] # Common ONVIF ports (HTTP)

        for ip in ip_addresses_to_scan:
            print(f"  Attempting ONVIF connection to {ip}...")
            camera_accessed = False

            for port in onvif_ports_to_try:
                print(f"    Trying port {port}...")
                xaddr_base = f"http://{ip}:{port}/onvif/device_service"
                
                onvif_service_detected = False
                try:
                    # First, try to connect with empty credentials to simply detect if an ONVIF service exists
                    mycam_probe = ONVIFCamera(ip, port, '', '', xaddr_base)
                    await mycam_probe.create_device_service() # Only attempt to create device service
                    onvif_service_detected = True
                    print(f"    ONVIF service detected on {ip}:{port}.")
                except (ONVIFError, Fault, asyncio.TimeoutError):
                    # No ONVIF service found or accessible without any credentials on this port
                    continue # Try next port

                # If an ONVIF service was detected, proceed to try credentials
                if onvif_service_detected:
                    # Try the combined list of dynamic credentials first
                    for cred in dynamic_creds_to_try: # MODIFIED: Using dynamic_creds_to_try
                        try:
                            mycam = ONVIFCamera(ip, port, cred['user'], cred['pass'], xaddr_base)
                            await mycam.create_media_service() # Test if media service can be created
                            
                            device_info = await mycam.devicemgmt.GetDeviceInformation()
                            camera_name = getattr(device_info, 'Model', f"ONVIF Device at {ip}")
                            print(f"    ✅ ONVIF device found at {ip}:{port} with credentials ({cred['user']}:***).") # Hide password
                            
                            # Proceed to get stream URIs
                            rtsp_uris = []
                            profiles = await mycam.media.GetProfiles()
                            for profile in profiles:
                                try:
                                    uri_response = await mycam.media.GetStreamUri({'StreamSetup': {'Stream': 'RTP_UNICAST', 'Transport': {'Protocol': 'RTSP'}}, 'ProfileToken': profile.token})
                                    rtsp_uri = uri_response.Uri
                                    if rtsp_uri:
                                        encoded_user = quote(cred['user'])
                                        encoded_pass = quote(cred['pass'])
                                        # Inject credentials into RTSP URL if they exist and are not already present
                                        if (encoded_user or encoded_pass) and "@" not in rtsp_uri:
                                            rtsp_uri_parts = rtsp_uri.split('//')
                                            auth_string = f"{encoded_user}"
                                            if encoded_pass:
                                                auth_string += f":{encoded_pass}"
                                            rtsp_uri = f"{rtsp_uri_parts[0]}//{auth_string}@{rtsp_uri_parts[1]}"
                                        rtsp_uris.append(rtsp_uri)
                                except Exception: # Catch any error during URI retrieval for this profile
                                    pass

                            if rtsp_uris:
                                found_cameras.append({
                                    'name': camera_name,
                                    'ip_address': ip,
                                    'port': port,
                                    'username': cred['user'],
                                    'password': cred['pass'],
                                    'rtsp_urls': rtsp_uris,
                                    'access_method': 'ONVIF (IP Scan - Auto Creds)', # Changed access method label
                                    'security_warning': "Credentials used from .env or common list.",
                                    'model': getattr(device_info, 'Model', 'Unknown'),
                                    'manufacturer': getattr(device_info, 'Manufacturer', 'Unknown')
                                })
                                camera_accessed = True
                                break # Break from credential loop once found with default creds
                        except (ONVIFError, Fault, asyncio.TimeoutError) as e:
                            pass # Keep trying other credentials in dynamic_creds_to_try
                        except Exception as e:
                            pass # Catch other unexpected errors during creds check

                    # If no default credentials worked, prompt user for custom credentials
                    if not camera_accessed:
                        print(f"    All auto-attempted credentials failed for {ip}:{port}. Attempting custom credentials...")
                        print("    Tip: If the camera is unresponsive, it might have a limited number of active streams. Check other applications using the camera.")
                        custom_user_input = input(f"      Enter custom username for {ip}:{port} (leave blank to skip): ").strip()
                        if custom_user_input:
                            custom_pass_input = input(f"      Enter custom password for {ip}:{port}: ").strip()
                            try:
                                mycam = ONVIFCamera(ip, port, custom_user_input, custom_pass_input, xaddr_base)
                                await mycam.create_media_service()
                                device_info = await mycam.devicemgmt.GetDeviceInformation()
                                camera_name = getattr(device_info, 'Model', f"ONVIF Device at {ip}")
                                print(f"    ✅ ONVIF device found at {ip}:{port} with custom credentials.")
                                
                                rtsp_uris = []
                                profiles = await mycam.media.GetProfiles()
                                for profile in profiles:
                                    try:
                                        uri_response = await mycam.media.GetStreamUri({'StreamSetup': {'Stream': 'RTP_UNICAST', 'Transport': {'Protocol': 'RTSP'}}, 'ProfileToken': profile.token})
                                        rtsp_uri = uri_response.Uri
                                        if rtsp_uri:
                                            encoded_user = quote(custom_user_input)
                                            encoded_pass = quote(custom_pass_input)
                                            if (encoded_user or encoded_pass) and "@" not in rtsp_uri:
                                                rtsp_uri_parts = rtsp_uri.split('//')
                                                auth_string = f"{encoded_user}"
                                                if encoded_pass:
                                                    auth_string += f":{encoded_pass}"
                                                rtsp_uri = f"{rtsp_uri_parts[0]}//{auth_string}@{rtsp_uri_parts[1]}"
                                            rtsp_uris.append(rtsp_uri)
                                    except Exception:
                                        pass

                                found_cameras.append({
                                    'name': camera_name,
                                    'ip_address': ip,
                                    'port': port,
                                    'username': custom_user_input,
                                    'password': custom_pass_input,
                                    'rtsp_urls': rtsp_uris,
                                    'access_method': 'ONVIF (IP Scan - Custom Creds)',
                                    'security_warning': "Custom credentials used.",
                                    'model': getattr(device_info, 'Model', 'Unknown'),
                                    'manufacturer': getattr(device_info, 'Manufacturer', 'Unknown')
                                })
                                camera_accessed = True
                            except (ONVIFError, Fault, asyncio.TimeoutError) as e:
                                print(f"      ❌ Failed to connect with provided custom credentials: {e}. Trying next port/IP.")
                                print("      Tip: If the camera is unresponsive, it might have a limited number of active streams. Check other applications using the camera.")
                            except Exception as e:
                                print(f"      ❌ Unexpected error with custom credentials: {e}. Trying next port/IP.")
                                print("      Tip: If the camera is unresponsive, it might have a limited number of active streams. Check other applications using the camera.")
                        else:
                            print(f"      Skipping custom credentials for {ip}:{port}.")
                
                if camera_accessed: # If camera was accessed (default or custom), break from port loop
                    break 
            
            if not camera_accessed: # This means no ONVIF service was found, or none could be accessed
                print(f"  ❌ Could not gain ONVIF access to {ip} on any common ports with provided credentials (or no service found).")
                print("  Tip: If the camera is unresponsive, it might have a limited number of active streams. Check other applications using the camera.")
                # Add a placeholder for the failed camera if no access was gained
                # Only add if it wasn't already added (e.g. if mycam_probe failed initially)
                if not any(c['ip_address'] == ip and c['access_method'] == 'ONVIF (IP Scan - No Access)' for c in found_cameras):
                    found_cameras.append({
                        'name': f"ONVIF Device at {ip} (No Access)",
                        'ip_address': ip,
                        'port': 'N/A',
                        'username': '', 'password': '', 'rtsp_urls': [],
                        'access_method': 'ONVIF (IP Scan - No Access)',
                        'security_warning': 'Could not establish ONVIF connection. Manual configuration required.',
                        'model': 'Unknown', 'manufacturer': 'Unknown'
                    })
            print("-" * 20) # Separator for IPs
        
        return found_cameras

    else: # Fallback to original discover if no IP range is provided and discover is available
        print("\nSearching for ONVIF cameras on the network using built-in discovery... This may take a moment (max 10 sec).")
        if not ONVIF_DISCOVERY_AVAILABLE:
            print("ONVIF camera discovery is currently unavailable due to missing library components.")
            print("Please ensure 'onvif-zeep' is correctly installed with discovery capabilities, or proceed with manual configuration or IP range scan.")
            return []

        try:
            devices = await discover(timeout=5, no_cache=True, strict=False)
            if not devices:
                print("No ONVIF cameras found via built-in discovery.")
                return []
            
            print(f"Built-in ONVIF discovery found {len(devices)} potential devices.")
            
            for xaddr in devices:
                print(f"  Attempting to retrieve details from: {xaddr} (from built-in discovery)")
                camera_accessed = False
                try:
                    parts = xaddr.split('//')
                    host_port_path = parts[1]
                    host_port_parts = host_port_path.split('/')[0].split(':')
                    ip = host_port_parts[0]
                    port = int(host_port_parts[1]) if len(host_port_parts) > 1 else 80

                    # Try the combined list of dynamic credentials first
                    for cred in dynamic_creds_to_try: # MODIFIED: Using dynamic_creds_to_try
                        try:
                            mycam = ONVIFCamera(ip, port, cred['user'], cred['pass'], xaddr)
                            await mycam.create_media_service()
                            device_info = await mycam.devicemgmt.GetDeviceInformation()
                            camera_name = getattr(device_info, 'Model', f"ONVIF Camera at {ip}")
                            
                            profiles = await mycam.media.GetProfiles()
                            rtsp_uris = []
                            for profile in profiles:
                                try:
                                    uri_response = await mycam.media.GetStreamUri({'StreamSetup': {'Stream': 'RTP_UNICAST', 'Transport': {'Protocol': 'RTSP'}}, 'ProfileToken': profile.token})
                                    rtsp_uri = uri_response.Uri
                                    if rtsp_uri:
                                        encoded_user = quote(cred['user'])
                                        encoded_pass = quote(cred['pass'])
                                        if (encoded_user or encoded_pass) and "@" not in rtsp_uri:
                                            rtsp_uri_parts = rtsp_uri.split('//')
                                            auth_string = f"{encoded_user}"
                                            if encoded_pass:
                                                auth_string += f":{encoded_pass}"
                                            rtsp_uri = f"{rtsp_uri_parts[0]}//{auth_string}@{rtsp_uri_parts[1]}"
                                        rtsp_uris.append(rtsp_uri)
                                except Exception:
                                    pass
                            
                            if rtsp_uris:
                                found_cameras.append({
                                    'name': camera_name,
                                    'ip_address': ip,
                                    'port': port,
                                    'username': cred['user'],
                                    'password': cred['pass'],
                                    'rtsp_urls': rtsp_uris,
                                    'access_method': 'ONVIF (Built-in Discovery - Auto Creds)', # Changed access method label
                                    'security_warning': "Credentials used from .env or common list.",
                                    'model': getattr(device_info, 'Model', 'Unknown'),
                                    'manufacturer': getattr(device_info, 'Manufacturer', 'Unknown')
                                })
                                camera_accessed = True
                                print(f"  ✅ Camera '{camera_name}' ({ip}) detected with credentials.")
                                break # Break from credential loop
                        except (ONVIFError, Fault, asyncio.TimeoutError):
                            pass
                        except Exception:
                            pass

                    # If no default credentials worked, prompt user for custom credentials for this discovered XAddr
                    if not camera_accessed:
                        print(f"  All auto-attempted credentials failed for discovered device {xaddr}. Do you want to try custom ones?")
                        print("  Tip: If the camera is unresponsive, it might have a limited number of active streams. Check other applications using the camera.")
                        custom_user_input = input(f"    Enter custom username for {ip}:{port} (leave blank to skip): ").strip()
                        if custom_user_input:
                            custom_pass_input = input(f"    Enter custom password for {ip}:{port}: ").strip()
                            try:
                                mycam = ONVIFCamera(ip, port, custom_user_input, custom_pass_input, xaddr)
                                await mycam.create_media_service()
                                device_info = await mycam.devicemgmt.GetDeviceInformation()
                                camera_name = getattr(device_info, 'Model', f"ONVIF Device at {ip}")
                                print(f"  ✅ ONVIF device found at {ip}:{port} with custom credentials.")
                                
                                rtsp_uris = []
                                profiles = await mycam.media.GetProfiles()
                                for profile in profiles:
                                    try:
                                        uri_response = await mycam.media.GetStreamUri({'StreamSetup': {'Stream': 'RTP_UNICAST', 'Transport': {'Protocol': 'RTSP'}}, 'ProfileToken': profile.token})
                                        rtsp_uri = uri_response.Uri
                                        if rtsp_uri:
                                            encoded_user = quote(custom_user_input)
                                            encoded_pass = quote(custom_pass_input)
                                            if (encoded_user or encoded_pass) and "@" not in rtsp_uri:
                                                rtsp_uri_parts = rtsp_uri.split('//')
                                                auth_string = f"{encoded_user}"
                                                if encoded_pass:
                                                    auth_string += f":{encoded_pass}"
                                                rtsp_uri = f"{rtsp_uri_parts[0]}//{auth_string}@{rtsp_uri_parts[1]}"
                                            rtsp_uris.append(rtsp_uri)
                                    except Exception:
                                        pass

                                found_cameras.append({
                                    'name': camera_name,
                                    'ip_address': ip,
                                    'port': port,
                                    'username': custom_user_input,
                                    'password': custom_pass_input,
                                    'rtsp_urls': rtsp_uris,
                                    'access_method': 'ONVIF (Built-in Discovery - Custom Creds)',
                                    'security_warning': "Custom credentials used.",
                                    'model': getattr(device_info, 'Model', 'Unknown'),
                                    'manufacturer': getattr(device_info, 'Manufacturer', 'Unknown')
                                })
                                camera_accessed = True
                            except (ONVIFError, Fault, asyncio.TimeoutError) as e:
                                print(f"    ❌ Failed to connect with provided custom credentials for {xaddr}: {e}.")
                                print("    Tip: If the camera is unresponsive, it might have a limited number of active streams. Check other applications using the camera.")
                            except Exception as e:
                                print(f"    ❌ Unexpected error with custom credentials for {xaddr}: {e}.")
                                print("    Tip: If the camera is unresponsive, it might have a limited number of active streams. Check other applications using the camera.")
                        else:
                            print(f"    Skipping custom credentials for {xaddr}.")
                except Exception as e:
                    print(f"  Error processing ONVIF device {xaddr} from built-in discovery: {e}")
                    found_cameras.append({
                        'name': f"ONVIF Device (Error) at {xaddr.split('//')[1].split('/')[0]}",
                        'ip_address': xaddr.split('//')[1].split('/')[0].split(':')[0],
                        'port': int(xaddr.split('//')[1].split('/')[0].split(':')[1]) if ':' in xaddr.split('//')[1].split('/')[0] else 80,
                        'username': '', 'password': '', 'rtsp_urls': [],
                        'access_method': 'ONVIF (Built-in Discovery - Error)',
                        'security_warning': 'Details could not be retrieved via ONVIF.',
                        'model': 'Unknown', 'manufacturer': 'Unknown'
                    })
        except Exception as e: # Catch any error during the built-in discover call itself
            print(f"Error during built-in ONVIF discovery: {e}")
            print("Tip: If running this script in a Docker container, ensure it's in 'host' network mode for ONVIF discovery.")

    return found_cameras


# Removed update_dashy_config function from this script.
# It is now handled by dashy_tile_config_tool.py

async def main():
    """Main function to run the Frigate Camera configuration tool."""
    print("\n--- Frigate Camera Configuration Tool ---")
    domain = get_env_variable("DOMAIN")
    if not domain:
        print("Error: DOMAIN variable not found in .env. Ensure setup.sh has been run.")
        return

    # Retrieve default RTSP username and password from environment (set by setup.sh)
    default_rtsp_username = get_env_variable("FRIGATE_RTSP_USERNAME")
    default_rtsp_password = get_env_variable("FRIGATE_RTSP_PASSWORD")

    community_cameras = load_community_cameras() 
    
    all_camera_configs_to_add = {} 
    
    # Initialize should_enter_manual early to prevent UnboundLocalError
    should_enter_manual = False 

    local_subnet_suggestion = get_local_subnet_suggestion()
    
    print("\nHow would you like to discover cameras?")
    print("1. Attempt built-in ONVIF discovery (may not work in this environment)")
    print(f"2. Scan a specific IP address or range for ONVIF cameras (e.g., {local_subnet_suggestion or '192.168.1.1-254'})")
    print("3. Manually enter camera details (RTSP URL, etc.)")
    print("0. Exit")

    discovery_choice = input("Enter your choice (1/2/3/0): ").strip()

    discovered_onvif_cameras = []

    if discovery_choice == '1':
        discovered_onvif_cameras = await discover_onvif_cameras()
    elif discovery_choice == '2':
        default_ip_range_prompt = local_subnet_suggestion if local_subnet_suggestion else '192.168.1.1-254'
        ip_range_input = input(f"Enter IP address or range (e.g., {default_ip_range_prompt}): ").strip()
        if not ip_range_input:
            ip_range_input = default_ip_range_prompt # Use default if user presses Enter
            print(f"Using default IP range: {ip_range_input}")

        if ip_range_input:
            discovered_onvif_cameras = await discover_onvif_cameras(ip_range_str=ip_range_input)
        else:
            print("No IP range provided. Skipping IP scan.")
    elif discovery_choice == '3':
        pass # Proceed to manual entry section
    elif discovery_choice == '0':
        print("Exiting tool.")
        return
    else:
        print("Invalid choice. Proceeding to manual entry.")


    # Define coral_enabled and coral_device_type for both discovery flows
    coral_enabled = False
    coral_device_type = None

    # Prompt for Coral TPU setup if we will proceed to add cameras (either discovered or manual)
    # This ensures the prompt only appears once and its state is used globally.
    should_prompt_coral = False 
    if discovered_onvif_cameras or discovery_choice == '3':
        should_prompt_coral = True
    elif discovery_choice in ['1', '2'] and not discovered_onvif_cameras: # If discovery failed, but user might still want to add manually
        should_prompt_coral = True

    if should_prompt_coral:
        coral_enabled_input = input("\nDo you want to enable Google Coral TPU detection? (yes/no) [no]: ").strip().lower()
        coral_enabled = (coral_enabled_input == 'yes')
        if coral_enabled:
            while True:
                coral_device_type_input = input("Enter Coral TPU device type (usb/pci) [usb]: ").strip().lower() or "usb"
                if coral_device_type_input in ['usb', 'pci']:
                    coral_device_type = coral_device_type_input
                    break
                else:
                    print("Invalid device type. Please enter 'usb' or 'pci'.")


    if discovered_onvif_cameras:
        print("\n--- Discovered ONVIF Cameras (via chosen method) ---")
        for i, cam_info in enumerate(discovered_onvif_cameras):
            status = "Ok" if cam_info['rtsp_urls'] else "Needs manual config"
            print(f"{i+1}. Name: {cam_info['name']} (IP: {cam_info['ip_address']})")
            print(f"   Manufacturer: {cam_info['manufacturer']}, Model: {cam_info['model']}")
            print(f"   Status: {status} ({cam_info['access_method']}) - {cam_info['security_warning']}")
            if cam_info['rtsp_urls']:
                for j, url in enumerate(cam_info['rtsp_urls']):
                    print(f"     Stream {j+1}: {url}")
            print("-" * 30)

        print("\nWhat would you like to do with the discovered cameras?")
        print("1. Add ALL discovered cameras to Frigate (automatic naming)")
        print("2. Add selected cameras manually or configure manually")
        print("0. Proceed without adding these cameras and go to manual input or exit")

        choice = input("Enter your choice (1/2/0): ").strip()

        if choice == '1':
            for i, cam_info in enumerate(discovered_onvif_cameras):
                if cam_info['rtsp_urls']: 
                    camera_name = f"{cam_info['manufacturer'].replace(' ', '')}{cam_info['model'].replace(' ', '')}-{cam_info['ip_address'].replace('.', '_')}"[:30].lower()
                    
                    counter = 1
                    original_name = camera_name
                    while camera_name in all_camera_configs_to_add:
                        camera_name = f"{original_name}-{counter}"
                        counter += 1

                    rtsp_url = cam_info['rtsp_urls'][0] 

                    if test_rtsp_stream(rtsp_url):
                        all_camera_configs_to_add[camera_name] = {
                            'ffmpeg': {
                                'inputs': [
                                    {
                                        'path': rtsp_url,
                                        'roles': ['detect', 'rtmp']
                                    }
                                ]
                            },
                            'detect': {
                                'width': 1280, 
                                'height': 720,
                                'fps': 5
                            }
                        }
                        # Frigate will automatically use the main detector if configured globally.
                        
                        print(f"  ✅ Camera '{camera_name}' added with URL: {rtsp_url}")
                        if cam_info['security_warning']:
                            print(f"  ⚠️ Security Warning: {cam_info['security_warning']}")
                    else:
                        print(f"  ❌ Camera '{cam_info['name']}' ({cam_info['ip_address']}) could not be verified. Skipping.")
            
            # If all cameras were added, check if user wants to exit or proceed
            if all_camera_configs_to_add:
                print("\nAll selected cameras added to Frigate config. Do you want to continue to manual entry or finish?")
                final_choice = input("Enter 'manual' to continue to manual entry or anything else to finish: ").strip().lower()
                if final_choice != 'manual':
                    # Skip manual entry section and proceed to config update
                    pass
                else:
                    # Fall through to manual entry
                    pass
            else:
                print("No cameras were successfully added from discovery. Proceeding to manual entry.")
                # Fall through to manual entry
                pass

        elif choice == '2':
            # This option will lead to the manual entry section
            pass 
        else: # choice == '0' or invalid
            print("Skipping discovered cameras. Proceeding to manual entry or exiting.")
            # Fall through to manual entry, user can type 'stop' to exit immediately
            pass
    else:
        print("No ONVIF cameras detected via discovery or IP scan, or you chose to skip them.")

    # Manual camera configuration section (only if not already handled by full discovery add)
    # The coral_enabled and coral_device_type variables are already defined above and reused.
    # should_enter_manual is now initialized at the very start of main()
    if not all_camera_configs_to_add and (discovery_choice == '3' or (discovery_choice in ['1', '2'] and not discovered_onvif_cameras) or (discovered_onvif_cameras and choice in ['2', '0'])):
        should_enter_manual = True # This assigns True if manual entry path is taken

    if should_enter_manual:
        # If Coral TPU setup hasn't been prompted yet, do it here.
        # This prevents duplicate prompts if user selected option 1/2 and no cameras were found.
        # The variables coral_enabled and coral_device_type are now initialized at the start of main.
        if not should_prompt_coral: # Only prompt if not already prompted earlier
            coral_enabled_input = input("\nDo you want to enable Google Coral TPU detection? (yes/no) [no]: ").strip().lower()
            coral_enabled = (coral_enabled_input == 'yes')
            coral_device_type = None
            if coral_enabled:
                while True:
                    coral_device_type_input = input("Enter Coral TPU device type (usb/pci) [usb]: ").strip().lower() or "usb"
                    if coral_device_type_input in ['usb', 'pci']:
                        coral_device_type = coral_device_type_input
                        break
                    else:
                        print("Invalid device type. Please enter 'usb' or 'pci'.")


        while True:
            camera_name = input("\nEnter a name for the camera (e.g., 'frontdoor', 'backyard', or 'stop' to finish): ").strip()
            if camera_name.lower() == 'stop':
                break
            if not camera_name:
                print("Name cannot be empty.")
                continue

            if community_cameras:
                print("\nAvailable camera presets:")
                for i, preset in enumerate(community_cameras):
                    print(f"{i+1}. {preset['name']} - {preset.get('notes', preset['url_template'])}")
                print(f"{len(community_cameras)+1}. Add a new preset to this list")
                print("0. Do not use a preset (manual entry of all components)")

                preset_choice = input("Choose a preset number, add a new one, or 0 for manual entry: ").strip()
                
                selected_preset = None
                if preset_choice.isdigit():
                    preset_choice_int = int(preset_choice)
                    if preset_choice_int == 0:
                        selected_preset = None 
                    elif preset_choice_int == len(community_cameras) + 1:
                        community_cameras = add_new_camera_preset(community_cameras)
                        continue # Go back to the top of the while loop to re-display presets or ask for new camera name
                    elif 1 <= preset_choice_int <= len(community_cameras):
                        selected_preset = community_cameras[preset_choice_int - 1]
                        print(f"Preset '{selected_preset['name']}' selected.")
                    else:
                        print("Invalid preset choice. Please try again.")
                        continue
                else:
                    print("Invalid input for preset choice. Please try again.")
                    continue

            ip_address = input(f"Enter the camera's IP address or hostname (e.g., '192.168.1.10' or 'mycamera.local'): ").strip()
            # Show default RTSP username and password from .env
            username = input(f"Enter the camera's username (leave empty for none) [{default_rtsp_username}]: ").strip() or default_rtsp_username
            password = input(f"Enter the camera's password (leave empty for none) [{default_rtsp_password}]: ").strip() or default_rtsp_password
            
            encoded_username = quote(username)
            encoded_password = quote(password)

            auth_part = ""
            if encoded_username:
                auth_part = f"{encoded_username}"
                if encoded_password:
                    auth_part += f":{encoded_password}"
                auth_part += "@"

            if selected_preset:
                port = input("Enter the RTSP port (usually 554, leave empty for default): ").strip() or "554"
                print(f"DEBUG: Using port value: '{port}'") 
                print(f"DEBUG: Selected preset URL template: '{selected_preset['url_template']}'") 
                try:
                    rtsp_url = selected_preset['url_template'].format(
                        user=encoded_username,
                        password=encoded_password,
                        ip=ip_address,
                        port=port
                    )
                except KeyError as e:
                    print(f"Error: The selected preset's template is incomplete or has missing placeholders ({e}).")
                    print("Please try again with manual entry or a different preset.")
                    continue
            else:
                port = input("Enter the RTSP port (usually 554, leave empty for default): ").strip() or "554"
                rtsp_path = input("Enter the camera path (e.g., '/stream0' or '/live/ch00_0', include leading slash): ").strip()
                if not rtsp_path.startswith('/'):
                    rtsp_path = '/' + rtsp_path 
                
                rtsp_url = f"rtsp://{auth_part}{ip_address}:{port}{rtsp_path}"
            
            print(f"Constructed RTSP URL: {rtsp_url}")
                
            if not test_rtsp_stream(rtsp_url):
                print("Stream test failed. Please try again or check the provided data.")
                continue 

            # New prompt for FFmpeg input arguments
            print("\nEnter optional FFmpeg input arguments. These can help with stream stability or authentication issues.")
            print("Common examples:")
            print("  - '-rtsp_transport tcp': Forces TCP for RTSP (often solves 401 Unauthorized errors).")
            print("  - '-rtsp_transport tcp -stimeout 5000000': Adds a 5-second timeout, useful for slow cameras.")
            print("  - '-rtsp_transport tcp -rtsp_flags prefer_tcp': Another variation for TCP preference.")
            ffmpeg_input_args_str = input("Enter arguments (e.g., '-rtsp_transport tcp' or leave empty): ").strip()
            ffmpeg_input_args = []
            if ffmpeg_input_args_str:
                # Simple split on spaces. For more complex args with spaces, user needs to be careful or we need a more advanced parser.
                # For example, '-rtsp_transport tcp -stimeout 5000000' would be split into two items.
                ffmpeg_input_args = [arg.strip() for arg in ffmpeg_input_args_str.split(' ') if arg.strip()]


            camera_config = {
                'ffmpeg': {
                    'inputs': [
                        {
                            'path': rtsp_url,
                            'roles': ['detect', 'rtmp']
                        }
                    ],
                    'input_args': ffmpeg_input_args # This will be an empty list if nothing entered
                },
                'detect': {
                    'width': 1280, 
                    'height': 720,
                    'fps': 5
                }
            }
            # Frigate will automatically use the main detector if configured globally.

            all_camera_configs_to_add[camera_name] = camera_config
            print(f"Camera '{camera_name}' added for Frigate configuration.")
            
            if username or password:
                print("\nTip: It is highly recommended to change your camera's default credentials for security!")


    if not all_camera_configs_to_add:
        print("No cameras configured in this session.")
        return

    frigate_data = {}
    if os.path.exists(FRIGATE_CONFIG_PATH):
        try:
            with open(FRIGATE_CONFIG_PATH, 'r') as f:
                frigate_data = yaml.safe_load(f)
                if frigate_data is None: 
                    frigate_data = {}
            print(f"Existing Frigate config loaded from {FRIGATE_CONFIG_PATH}")
        except yaml.YAMLError as e:
            print(f"Warning: Error parsing existing Frigate config ({e}). Please backup and start with an empty config.")
            frigate_data = {} 

    # --- Add Coral TPU detector configuration if enabled ---
    # This logic ensures it's added only once and only if Coral is enabled.
    if coral_enabled and coral_device_type:
        if 'detectors' not in frigate_data:
            frigate_data['detectors'] = {}
        if 'coral' not in frigate_data['detectors']: # Avoid overwriting if 'coral' already exists
            frigate_data['detectors']['coral'] = {
                'type': 'edgetpu',
                'device': coral_device_type
            }
            print(f"Info: Google Coral TPU detector '{coral_device_type}' added to Frigate configuration.")
        else:
            print(f"Info: Google Coral TPU detector 'coral' already exists in Frigate config. Skipping creation.")
    # --- End Coral TPU detector configuration ---


    if 'cameras' not in frigate_data:
        frigate_data['cameras'] = {}
    
    for cam_name, cam_details in all_camera_configs_to_add.items():
        if cam_name in frigate_data['cameras']:
            print(f"Warning: Camera '{cam_name}' already exists in Frigate config. Overwriting...")
        frigate_data['cameras'][cam_name] = cam_details

    try:
        with open(FRIGATE_CONFIG_PATH, 'w') as f:
            yaml.dump(frigate_data, f, indent=2, sort_keys=False) 
        print(f"\n✅ Frigate config.yml successfully updated at: {FRIGATE_CONFIG_PATH}")
        print("Please restart Frigate to apply changes:")
        print(f"  bash {os.path.join(os.getenv('BASE_DIR_HOST', '/home/PiSelfhosting'), 'scripts', 'restart-all.sh')}") # Reference to host path
    except Exception as e:
        print(f"❌ Error writing Frigate config.yml: {e}")

    # Moved Dashy updates to a separate script.
    print("\nℹ️  To update your Dashy dashboard with all service tiles, please run:")
    print(f"  bash {os.path.join(os.getenv('BASE_DIR_HOST', '/home/PiSelfhosting'), 'scripts', 'run-dashy-tile-config-tool.sh')}") # Reference to host path
    print("  (This script can be run at any time to synchronize Dashy tiles).")

if __name__ == "__main__":
    if platform.system() == "Windows":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    asyncio.run(main())

