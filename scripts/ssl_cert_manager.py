# /home/PiSelfhosting/scripts/ssl_cert_manager.py

import os
import sys
import subprocess
import getpass
import platform # For platform.system()

# Define base directory as expected inside the Docker container
# The host's /home/PiSelfhosting will be mounted to /app/piselfhosting in the container.
BASE_DIR = "/app/piselfhosting"
# Centralized location for certificates on the host, mounted into the container.
# This assumes ~/PiSelfhosting/certs exists on the host.
CERT_STORAGE_HOST_PATH = os.path.join(os.getenv("BASE_DIR_HOST"), "certs")
CERT_STORAGE_CONTAINER_PATH = os.path.join(BASE_DIR, "certs")

def get_env_variable(key, default=""):
    """Loads a variable from the container's environment."""
    return os.getenv(key, default)

def get_user_input(prompt, default_value=None, secret=False):
    """Helper function to get user input with a default and optional secrecy."""
    if default_value is not None:
        prompt_text = f"{prompt} [{default_value}]: "
    else:
        prompt_text = f"{prompt}: "

    if secret:
        user_input = getpass.getpass(prompt_text)
    else:
        user_input = input(prompt_text)

    return user_input.strip() if user_input.strip() else (default_value if default_value is not None else "")

def ensure_cert_storage_exists():
    """Ensures the centralized certificate storage directory exists."""
    # This directory is on the host, but we create it via the mounted path
    os.makedirs(CERT_STORAGE_CONTAINER_PATH, exist_ok=True)
    print(f"✅ Certificate storage directory ensured: {CERT_STORAGE_HOST_PATH}")

def generate_self_signed_cert(domain_name, cert_path, key_path):
    """Generates a self-signed SSL certificate using OpenSSL."""
    print(f"\n--- Generating Self-Signed Certificate for {domain_name} ---")
    print("This certificate will NOT be trusted by browsers/clients without manual import.")

    # Generate a new RSA private key (2048-bit)
    print("Generating private key...")
    try:
        subprocess.run([
            "openssl", "genrsa", "-out", key_path, "2048"
        ], check=True, capture_output=True, text=True)
        print("✅ Private key generated.")
    except subprocess.CalledProcessError as e:
        print(f"❌ Error generating private key: {e.stderr}")
        return False

    # Generate a self-signed certificate
    print("Generating self-signed certificate (valid for 365 days)...")
    try:
        subprocess.run([
            "openssl", "req", "-new", "-x509", "-days", "365",
            "-key", key_path,
            "-out", cert_path,
            "-subj", f"/CN={domain_name}" # Common Name
        ], check=True, capture_output=True, text=True)
        print(f"✅ Self-signed certificate generated for {domain_name}.")
        print(f"Certificate: {cert_path}")
        print(f"Private Key: {key_path}")
        print("\n⚠️  Remember to import this certificate into your client's trust store to avoid warnings.")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Error generating self-signed certificate: {e.stderr}")
        return False

def manage_existing_certs(domain_name, cert_path, key_path):
    """Copies existing certificates to the centralized storage location."""
    print("\n--- Using Existing SSL Certificates ---")
    print("You will need to provide the full paths to your existing certificate and private key files.")
    
    existing_fullchain_path = get_user_input("Enter the full path to your existing fullchain.pem or .crt file: ")
    existing_privkey_path = get_user_input("Enter the full path to your existing privkey.pem or .key file: ")

    if not os.path.exists(existing_fullchain_path) or not os.path.exists(existing_privkey_path):
        print("❌ One or both provided paths do not exist. Please ensure the files are accessible.")
        return False

    try:
        # Use sudo to copy the files, as the destination might require root privileges
        # This will be executed by the run-ssl-cert-manager.sh script which may have sudo.
        subprocess.run(["sudo", "cp", existing_fullchain_path, cert_path], check=True)
        subprocess.run(["sudo", "cp", existing_privkey_path, key_path], check=True)
        print(f"✅ Existing certificates copied to:")
        print(f"Certificate: {cert_path}")
        print(f"Private Key: {key_path}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Error copying existing certificates: {e.stderr}")
        print("Please ensure the script has appropriate permissions to copy files.")
        return False
    except Exception as e:
        print(f"❌ An unexpected error occurred: {e}")
        return False

def handle_lets_encrypt(domain_name):
    """Provides instructions for obtaining Let's Encrypt certs via Nginx Proxy Manager."""
    print("\n--- Obtaining Let's Encrypt Certificates via Nginx Proxy Manager ---")
    print("\nThis tool does NOT directly request Let's Encrypt certificates.")
    print("Instead, it guides you on how to use Nginx Proxy Manager (NPM), which has built-in Let's Encrypt support, to acquire them.")
    print("\n**Crucial Prerequisites:**")
    print("1.  **Nginx Proxy Manager must be installed and running.** (Ensure it's selected in 'setup.sh' and deployed).")
    print("2.  **Ports 80 (HTTP) and 443 (HTTPS) MUST be forwarded from your router to your host machine's Nginx Proxy Manager container.**")
    print("    This is essential for the Let's Encrypt ACME challenge to work.")
    print("3.  **Your domain's A Record MUST point to your public IP address.** (e.g., your router's external IP if on a home network).")

    print("\n**Step-by-Step Guide to get Let's Encrypt Certificate via Nginx Proxy Manager:**")
    print(f"1.  **Access Nginx Proxy Manager UI:** Open your web browser and navigate to: http://{domain_name}:81")
    print("    (Use the admin credentials you set during NPM's first-run setup).")
    print("2.  **Go to 'SSL Certificates':** In the NPM dashboard, click on 'SSL Certificates' in the left sidebar.")
    print("3.  **Add New Certificate:** Click the 'Add SSL Certificate' button and select 'Let's Encrypt'.")
    print("4.  **Enter Domain Details:**")
    print(f"    - For 'Domain Names', enter your primary domain (e.g., '{domain_name}'). If you have subdomains you want to secure (e.g., mail.{domain_name}, frigate.{domain_name}), add them here as well, separated by commas.")
    print("    - Enable 'Use DNS Challenge' if you prefer, but the HTTP challenge is usually simpler if ports 80/443 are forwarded.")
    print("    - Agree to the Terms of Service and provide an email for notifications.")
    print("5.  **Save/Issue:** Click 'Save' or 'Issue'. NPM will attempt to obtain the certificate.")
    print("    - **Troubleshooting:** If it fails, double-check your port forwarding (80 and 443) and DNS A records. The error message in NPM will usually provide clues.")
    print("\n**Once the certificate is issued by NPM:**")
    print("  - NPM will automatically use it for any Proxy Hosts you configure that point to HTTPS backends.")
    print("  - **For Services needing direct certificate access (like Mailserver):**")
    print("    You will need to manually copy the generated certificate files from NPM's internal volume to your centralized certificate storage.")
    print(f"    1. Find NPM's internal volume for Let's Encrypt: `docker volume inspect piselfhosting-npm-letsencrypt`")
    print("    2. Locate the certificate files within that volume (usually in `_data/live/your.domain.com/`).")
    print(f"    3. Copy `fullchain.pem` and `privkey.pem` to your centralized host path: `{CERT_STORAGE_HOST_PATH}`")
    print(f"       Example (replace with your actual paths): `sudo cp /var/lib/docker/volumes/piselfhosting-npm-letsencrypt/_data/live/{domain_name}/fullchain.pem {CERT_STORAGE_HOST_PATH}/fullchain.pem`")
    print(f"       `sudo cp /var/lib/docker/volumes/piselfhosting-npm-letsencrypt/_data/live/{domain_name}/privkey.pem {CERT_STORAGE_HOST_PATH}/privkey.pem`")
    print("\nAfter placing the certificate files, remember to configure your Mailserver's Dockerfile/config to mount and use them.")
    return True

def main():
    """Main function for the SSL Certificate Manager tool."""
    print("\n--- PiSelfhosting SSL Certificate Manager ---")
    domain = get_env_variable("DOMAIN")
    if not domain:
        print("Error: DOMAIN variable not found in .env. Ensure setup.sh has been run.")
        sys.exit(1)

    ensure_cert_storage_exists()

    default_cert_file = os.path.join(CERT_STORAGE_CONTAINER_PATH, "fullchain.pem")
    default_key_file = os.path.join(CERT_STORAGE_CONTAINER_PATH, "privkey.pem")

    while True:
        print("\nChoose your SSL Certificate method:")
        print("1. Let's Encrypt (Recommended - via Nginx Proxy Manager)")
        print("2. Self-Signed Certificate (for internal use, not publicly trusted)")
        print("3. Use Existing Certificates (copy your own .pem/.crt/.key files)")
        print("0. Exit")

        choice = get_user_input("Enter your choice (1/2/3/0): ").strip()

        success = False
        if choice == '1':
            success = handle_lets_encrypt(domain)
        elif choice == '2':
            success = generate_self_signed_cert(domain, default_cert_file, default_key_file)
        elif choice == '3':
            success = manage_existing_certs(domain, default_cert_file, default_key_file)
        elif choice == '0':
            print("Exiting SSL Certificate Manager.")
            break
        else:
            print("Invalid choice. Please try again.")
            continue
        
        if success:
            print("\n--- Configuration for Services Using Certificates ---")
            print(f"Your certificates should now be available on the host at: `{CERT_STORAGE_HOST_PATH}/`")
            print("\n**For your Mailserver (Exim4 and Dovecot):**")
            print("  You will need to update their configuration files (e.g., Exim4's `update-exim4.conf.conf` or a dedicated TLS config, Dovecot's `10-ssl.conf`) to point to these certificate files.")
            print("  Example paths to use *inside* the Mailserver containers (due to volume mapping):")
            print(f"  - Certificate Path: `/etc/exim4/fullchain.pem` or `/etc/dovecot/fullchain.pem`") # Example assuming config volume is mapped
            print(f"  - Private Key Path: `/etc/exim4/privkey.pem` or `/etc/dovecot/privkey.pem`") # Example assuming config volume is mapped
            print(f"\n  To make these available, ensure your `docker/mailserver/docker-compose.yml` mounts the certificates into the container's config directories, for example:")
            print(f"    volumes:")
            print(f"      - {CERT_STORAGE_HOST_PATH}/fullchain.pem:/etc/exim4/fullchain.pem:ro")
            print(f"      - {CERT_STORAGE_HOST_PATH}/privkey.pem:/etc/exim4/privkey.pem:ro")
            print(f"      - {CERT_STORAGE_HOST_PATH}/fullchain.pem:/etc/dovecot/fullchain.pem:ro")
            print(f"      - {CERT_STORAGE_HOST_PATH}/privkey.pem:/etc/dovecot/privkey.pem:ro")
            print("\n  After updating configs and Docker Compose, rebuild and restart your Mailserver:")
            print(f"  `bash {os.path.join(os.getenv('BASE_DIR_HOST'), 'scripts', 'restart-all.sh')} mailserver`")
            
            print("\n**For Nginx Proxy Manager (if you used Self-Signed or Existing Certs):**")
            print("  You will need to import these certificates into NPM's UI or ensure NPM is configured to use them for your proxy hosts.")
            print("\n--- SSL Certificate Management Complete ---")
            break # Exit after successful operation

if __name__ == "__main__":
    if platform.system() == "Windows":
        # Only import asyncio if it's actually needed for specific async operations.
        # This script does not use async functions for now.
        pass
    main()

