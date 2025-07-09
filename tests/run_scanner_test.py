import getpass
import sys
import os
import yaml
from dotenv import load_dotenv, set_key

# --- Path Setup ---
project_root = os.path.dirname(os.path.abspath(__file__))
src_path = os.path.join(project_root, 'src')
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from pi_scanner import PiScanner


def main():
    """Main function to run the network scanner test."""
    # Check for command-line arguments
    debug_mode = '--debug' in sys.argv
    yaml_output = '--output=yaml' in sys.argv

    if not yaml_output:
        print("--- PiSelfhosting Network Scanner ---")

    # --- Load .env and Get User Input ---
    env_path = os.path.join(project_root, '.env')
    load_dotenv(dotenv_path=env_path)

    try:
        # Subnet Selection
        stored_subnet = os.getenv("PISELFHOSTING_NETWORK_RANGE", "192.168.1.0/24")
        if not yaml_output:
            prompt = f"Enter the subnet to scan or press Enter to use default [{stored_subnet}]: "
            target_subnet = input(prompt).strip() or stored_subnet
        else:
            target_subnet = stored_subnet
        if target_subnet != stored_subnet:
            set_key(env_path, "PISELFHOSTING_NETWORK_RANGE", target_subnet)

        # Primary Credential Prompt
        stored_username = os.getenv("PISELFHOSTING_SSH_USER", "pi")
        if not yaml_output:
            print("\nEnter the primary SSH credentials for your network.")
            prompt = f"Primary SSH Username [{stored_username}]: "
            primary_username = input(prompt).strip() or stored_username
        else:
            primary_username = stored_username
        if primary_username != stored_username:
            set_key(env_path, "PISELFHOSTING_SSH_USER", primary_username)

        primary_password = getpass.getpass("Primary SSH Password: ")

    except KeyboardInterrupt:
        print("\nScan cancelled by user.", file=sys.stderr)
        return

    # --- Scanning and Verification ---
    if not yaml_output:
        print(f"\nScanning {target_subnet} for potential Raspberry Pi devices...")

    potential_pis = PiScanner.scan(target_subnet, debug=debug_mode)

    if not potential_pis:
        if not yaml_output:
            print("\nScan finished. No potential Raspberry Pi devices were found.")
        return

    if not yaml_output:
        print(f"\n--> Found {len(potential_pis)} potential device(s). Verifying via SSH...")

    verified_pis_by_serial = {}
    for pi in potential_pis:
        ip = pi['ip']
        if not yaml_output:
            print(f"\n--> Checking device at {ip}...")

        details = PiScanner.get_device_details(ip, primary_username, primary_password)

        if not details and not yaml_output:
            print(f"    Primary credentials failed for {ip}.")
            retry_choice = input("    Try again with different credentials for this device? (y/n): ").strip().lower()
            if retry_choice == 'y':
                try:
                    retry_username = input("    New Username: ").strip()
                    retry_password = getpass.getpass("    New Password: ")
                    details = PiScanner.get_device_details(ip, retry_username, retry_password)
                except KeyboardInterrupt:
                    print("\nRetry cancelled.")
                    continue

        if details and details.get('serial'):
            serial = details['serial']
            if not yaml_output:
                print(f"    ✅ Success! Found Pi with Serial: {serial}")
            if serial not in verified_pis_by_serial:
                verified_pis_by_serial[serial] = {
                    'ips': [ip],
                    'macs': [pi['mac']],
                    'model': details.get('model'),
                    'ram': details.get('ram'),
                    'disks': details.get('disks')
                }
            else:
                verified_pis_by_serial[serial]['ips'].append(ip)
                verified_pis_by_serial[serial]['macs'].append(pi['mac'])
        elif not yaml_output:
            print(f"    ❌ Could not verify device at {ip}. Skipping.")

    # --- Final Output ---
    if yaml_output:
        # In YAML mode, we can still filter for cleaner output if desired
        for serial, data in verified_pis_by_serial.items():
            if 'disks' in data and data['disks'] is not None:
                data['disks'] = [d for d in data['disks'] if d.get('type') != 'loop']
        print(yaml.dump(verified_pis_by_serial, default_flow_style=False, sort_keys=False))
    else:
        # Print the human-readable report
        print("\n" + "=" * 25)
        print("   Scan Report")
        print("=" * 25)
        if not verified_pis_by_serial:
            print("No verifiable Raspberry Pi devices were found on your network.")
        else:
            print(f"Found {len(verified_pis_by_serial)} unique Raspberry Pi device(s):")
            for i, (serial, data) in enumerate(verified_pis_by_serial.items()):
                print(f"\n--- Device #{i + 1} ---")
                print(f"  Serial Number: {serial}")
                print(f"  Model:         {data.get('model', 'N/A')}")
                print(f"  RAM:           {data.get('ram', 'N/A')}")
                print(f"  Detected IP(s):  {', '.join(data['ips'])}")
                print(f"  Detected MAC(s): {', '.join(data['macs'])}")

                physical_disks = [d for d in data.get('disks', []) if d.get('type') != 'loop']
                if physical_disks:
                    print("  Disks:")
                    for disk in physical_disks:
                        print(f"    - {disk.get('name')} ({disk.get('size')})")
        print("=" * 25)


if __name__ == "__main__":
    main()