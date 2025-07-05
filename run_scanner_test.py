import getpass
import sys
import os
from dotenv import load_dotenv, set_key

# --- Path Setup ---
# Ensure the 'src' directory is on the path to find the PiScanner module
project_root = os.path.dirname(os.path.abspath(__file__))
src_path = os.path.join(project_root, 'src')
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from pi_scanner import PiScanner


def main():
    """Main function to run the network scanner test."""
    # Check for the --debug flag from the command line
    debug_mode = '--debug' in sys.argv
    if debug_mode:
        print("[DEBUG] Debug mode is ON.")

    print("--- PiSelfhosting Network Scanner ---")

    # --- Load .env and Get User Input ---
    env_path = os.path.join(project_root, '.env')
    load_dotenv(dotenv_path=env_path)

    try:
        # Subnet Selection
        stored_subnet = os.getenv("PISELFHOSTING_NETWORK_RANGE", "192.168.1.0/24")
        detected_subnet = PiScanner.detect_subnet()
        if detected_subnet:
            print(f"\nInfo: Auto-detected a local subnet: {detected_subnet}")
            # If no subnet is stored, suggest the detected one
            if not os.getenv("PISELFHOSTING_NETWORK_RANGE"):
                stored_subnet = detected_subnet

        prompt = f"Enter the subnet to scan or press Enter to use default [{stored_subnet}]: "
        target_subnet = input(prompt).strip() or stored_subnet

        # Save the chosen value for next time if it's different
        if target_subnet != os.getenv("PISELFHOSTING_NETWORK_RANGE"):
            print(f"Saving new subnet '{target_subnet}' to .env file...")
            set_key(env_path, "PISELFHOSTING_NETWORK_RANGE", target_subnet)

        # Username Selection
        stored_username = os.getenv("PISELFHOSTING_SSH_USER", "pi")
        prompt = f"Enter the SSH username for your Pi(s) [{stored_username}]: "
        username = input(prompt).strip() or stored_username

        if username != os.getenv("PISELFHOSTING_SSH_USER"):
            print(f"Saving new username '{username}' to .env file...")
            set_key(env_path, "PISELFHOSTING_SSH_USER", username)

        # Password Prompt
        password = getpass.getpass("Enter the SSH password: ")

    except KeyboardInterrupt:
        print("\nScan cancelled by user.")
        return

    # --- Scanning ---
    print(f"\nScanning {target_subnet} for potential Raspberry Pi devices...")
    potential_pis = PiScanner.scan(target_subnet, debug=debug_mode)

    if not potential_pis:
        print("\nScan finished. No potential Raspberry Pi devices were found.")
        return

    print(f"\n--> Found {len(potential_pis)} potential device(s). Verifying via SSH...")

    verified_pis_by_serial = {}
    for pi in potential_pis:
        ip = pi['ip']
        print(f"    - Checking device at {ip}...")
        details = PiScanner.get_device_details(ip, username, password)
        if details and details.get('serial'):
            serial = details['serial']
            print(f"      ✅ Success! Found Pi with Serial: {serial}")
            if serial not in verified_pis_by_serial:
                verified_pis_by_serial[serial] = {'ips': [ip], 'macs': [pi['mac']]}
            else:
                # This is the same physical Pi with another network interface
                verified_pis_by_serial[serial]['ips'].append(ip)
                verified_pis_by_serial[serial]['macs'].append(pi['mac'])

    # --- Final Report ---
    print("\n" + "=" * 25)
    print("   Scan Report")
    print("=" * 25)
    if not verified_pis_by_serial:
        print("No verifiable Raspberry Pi devices were found.")
    else:
        print(f"Found {len(verified_pis_by_serial)} unique Raspberry Pi device(s):")
        for i, (serial, data) in enumerate(verified_pis_by_serial.items()):
            print(f"\n--- Device #{i + 1} ---")
            print(f"  Serial Number: {serial}")
            print(f"  Detected IP(s): {', '.join(data['ips'])}")
            print(f"  Detected MAC(s): {', '.join(data['macs'])}")
    print("=" * 25)


if __name__ == "__main__":
    main()