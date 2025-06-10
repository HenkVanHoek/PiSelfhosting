# /home/PiSelfhosting/scripts/mailserver_config_tool.py

import os
import sys
import yaml
import hashlib # For password hashing
import crypt # For system-like password hashing (optional, often better to use standard hashes)
import platform # Import the platform module

# Define base directory as expected inside the Docker container
# The host's /home/PiSelfhosting will be mounted to /app/piselfhosting in the container.
BASE_DIR = "/app/piselfhosting"
EXIM4_CONFIG_DIR = os.path.join(BASE_DIR, "docker", "mailserver", "exim4", "config")
DOVECOT_CONFIG_DIR = os.path.join(BASE_DIR, "docker", "mailserver", "dovecot", "config")

# Paths for files managed by this script
EXIM4_UPDATE_CONF = os.path.join(EXIM4_CONFIG_DIR, "update-exim4.conf.conf")
EXIM4_PASSWD_BYNAME = os.path.join(EXIM4_CONFIG_DIR, "passwd.byname")
DOVECOT_USERS_CONF = os.path.join(DOVECOT_CONFIG_DIR, "users.conf") # For virtual users
DOVECOT_10_AUTH_CONF = os.path.join(DOVECOT_CONFIG_DIR, "conf.d", "10-auth.conf")
DOVECOT_10_MAIL_CONF = os.path.join(DOVECOT_CONFIG_DIR, "conf.d", "10-mail.conf")

# Default values and expert notes
DEFAULT_MAIL_DOMAIN = os.getenv("DOMAIN", "mail.example.com") # Get from .env or default
DEFAULT_POSTMASTER_EMAIL = f"postmaster@{DEFAULT_MAIL_DOMAIN}"
DEFAULT_RELAY_HOST = "" # Empty means direct sending

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
        # For sensitive input, read from getpass if available, otherwise fallback to input
        try:
            import getpass
            user_input = getpass.getpass(prompt_text)
        except ImportError:
            user_input = input(prompt_text)
    else:
        user_input = input(prompt_text)

    return user_input.strip() if user_input.strip() else (default_value if default_value is not None else "")

def ensure_directories_exist():
    """Ensures that the necessary configuration directories exist on the host."""
    os.makedirs(EXIM4_CONFIG_DIR, exist_ok=True)
    os.makedirs(os.path.dirname(DOVECOT_10_AUTH_CONF), exist_ok=True) # Ensures conf.d exists
    os.makedirs(os.path.dirname(DOVECOT_10_MAIL_CONF), exist_ok=True)
    print("✅ Mailserver configuration directories ensured.")

def hash_password(password):
    """Hashes a password using SHA512CRYPT (similar to system passwords)."""
    # Using crypt.crypt is standard for system-like password hashing, but requires salt.
    # For simplicity for virtual users, we might use SHA512 (SHA-512) directly or salted SHA512.
    # Dovecot can use SHA512-CRYPT, SHA256-CRYPT, plain SHA512, MD5, etc.
    # For basic file-based virtual users, a simple SHA512 might suffice for Dovecot.
    # Exim4's passwd.byname typically expects plaintext or specific obscure hashes, simpler to use plaintext with strong file permissions.
    # For a robust setup, integrate with a database or a secure password hashing library.
    
    # For Dovecot's 'passwd-file' with {SHA512-CRYPT}
    # This generates a hash compatible with Dovecot's {SHA512-CRYPT} scheme.
    # The 'salt' should be a random string.
    try:
        import secrets
        salt = secrets.token_urlsafe(16) # Generate a random salt
        # Use crypt.crypt with a SHA512 method prefix
        return crypt.crypt(password, f"$6${salt}") # $6$ is the prefix for SHA512-CRYPT
    except Exception as e:
        print(f"Warning: Failed to generate SHA512-CRYPT hash ({e}). Falling back to plain SHA512.")
        return "{SHA512}" + hashlib.sha512(password.encode()).hexdigest()

def load_virtual_users():
    """Loads virtual users from DOVECOT_USERS_CONF."""
    users = {}
    if os.path.exists(DOVECOT_USERS_CONF):
        try:
            with open(DOVECOT_USERS_CONF, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        parts = line.split(':')
                        if len(parts) >= 2: # At least username:password_hash
                            username = parts[0]
                            # The hash will be the second part, but might contain more fields for mailbox
                            password_hash = parts[1]
                            users[username] = password_hash # Store the hash directly
            print(f"Loaded existing virtual users from {DOVECOT_USERS_CONF}")
        except Exception as e:
            print(f"Warning: Could not load virtual users from {DOVECOT_USERS_CONF} ({e}). Starting fresh.")
    return users

def save_virtual_users(users):
    """Saves virtual users to DOVECOT_USERS_CONF and EXIM4_PASSWD_BYNAME."""
    try:
        # Save for Dovecot (format: user:password_hash)
        with open(DOVECOT_USERS_CONF, 'w') as f:
            f.write("# Dovecot virtual users file\n")
            f.write("# Format: username:password_hash[:uid:gid:home:extra_fields]\n")
            f.write("# Use {SHA512-CRYPT} for SHA512 hashed passwords (recommended).\n")
            for user, pwd_hash in users.items():
                # For simplicity, we just save username:hash. uid/gid/home will be defaulted by Dovecot.
                f.write(f"{user}:{pwd_hash}\n")
        print(f"✅ Dovecot virtual users saved to {DOVECOT_USERS_CONF}")
        
        # Save for Exim4 (format: user:password)
        # Exim's passwd.byname for SMTP AUTH usually expects plaintext for basic file auth
        # or specific hashes. For simplicity, we will use plaintext here.
        # This is a security risk if the file is not properly secured!
        with open(EXIM4_PASSWD_BYNAME, 'w') as f:
            f.write("# Exim4 plaintext passwords for AUTH (less secure, ensure strong file permissions)\n")
            f.write("# Format: username:password\n")
            # We need to get the plaintext password from the user again for Exim4
            # OR refactor password handling to store plain during user input temporarily.
            # For this basic version, we will ask for plaintext again for Exim's file.
            # In a real scenario, use a secure password store and lookup for Exim.
            
            # Since the tool only stores hashes in `users` dict, for Exim we'll provide a warning
            # and instruct user to manually add the plaintext password.
            f.write("# Please manually add users and plaintext passwords here for Exim4 if needed for SMTP AUTH.\n")
            f.write("# Example: user1:plain_password_for_user1\n")
            # This is a significant limitation of a simple file-based approach for two different MTAs.
            # A common database for users is usually better.

        print(f"⚠️  Exim4 passwd.byname created/updated at {EXIM4_PASSWD_BYNAME}. You might need to manually add plaintext passwords for SMTP AUTH if needed.")
        print(f"   Ensure permissions are restrictive (e.g., chmod 600 {EXIM4_PASSWD_BYNAME}) as it may contain plain text passwords.")

    except Exception as e:
        print(f"❌ Error saving virtual users: {e}")
        sys.exit(1)

def configure_exim4():
    """Configures main Exim4 settings."""
    print("\n--- Configuring Exim4 (MTA) ---")
    mail_domain = get_user_input("Enter your primary mail domain", DEFAULT_MAIL_DOMAIN)
    postmaster_email = get_user_input("Enter Postmaster email address", DEFAULT_POSTMASTER_EMAIL)
    relay_choice = get_user_input("Do you want to send mail directly or use a relay host? (direct/relay) [direct]: ", "direct").lower()

    relay_host = ""
    if relay_choice == "relay":
        relay_host = get_user_input("Enter your relay host (e.g., smtp.gmail.com:587). Leave empty for none.", DEFAULT_RELAY_HOST)
        # Add a warning about needing relay authentication setup (which this tool won't fully cover)
        print("⚠️ Note: If using a relay, you will likely need to configure authentication for the relay host in Exim4's configuration (e.g., using `passwd.client`). This tool does not configure relay authentication.")

    # Generate update-exim4.conf.conf
    exim4_conf_content = f"""
# /etc/exim4/update-exim4.conf.conf
# This file is managed by mailserver_config_tool.py.
# DO NOT EDIT THIS FILE MANUALLY UNLESS YOU KNOW WHAT YOU ARE DOING.

# Primary mail domain (used by Exim to know for which domains it's authoritative)
dc_local_interfaces='0.0.0.0.25;0.0.0.0.587;0.0.0.0.465' # Listen on all interfaces on common SMTP ports
dc_readhost='{mail_domain}'
dc_local_interfaces_include_localhost='yes'
dc_minimaldns='no' # Full DNS lookups
dc_relay_nets=''
dc_qualify_domain='{mail_domain}'
dc_route_local_relay=''
dc_mailname_dot_domain='{mail_domain}'
dc_postmaster='{postmaster_email}'

# How to send mail: 'local_delivery' for direct, 'smarthost' for relay
dc_use_split_config='true'
dc_hide_mailname='false' # Ensure full email address is used
dc_use_experimental_interface='false'

# If using a relay host (smarthost)
# Uncomment these lines in a smarthost setup
# dc_smarthost='{relay_host}'
# dc_localdelivery='maildir_home' # For local user delivery

# Default settings (usually fine)
dc_local_delivery='maildir_home'
dc_other_hostnames='localhost'
dc_relay_domains=''
"""
    if relay_host:
        exim4_conf_content += f"dc_smarthost='{relay_host}'\n"
        exim4_conf_content += "dc_localdelivery='maildir_home'\n"
    else:
        exim4_conf_content += "dc_smarthost=''\n"
        exim4_conf_content += "dc_localdelivery='maildir_home'\n"

    try:
        with open(EXIM4_UPDATE_CONF, 'w') as f:
            f.write(exim4_conf_content.strip())
        print(f"✅ Exim4 main configuration saved to {EXIM4_UPDATE_CONF}")
    except Exception as e:
        print(f"❌ Error writing Exim4 config: {e}")
        sys.exit(1)

    print("ℹ️ Exim4's main configuration is now set.")
    print("   For advanced features (SMTP AUTH, TLS, spam filtering, custom routing),")
    print("   you will need to manually edit files in the Exim4 config directory mounted at:")
    print(f"   {EXIM4_CONFIG_DIR} (on the host: {os.path.join(os.getenv('BASE_DIR_HOST'), 'docker', 'mailserver', 'exim4', 'config')})")


def configure_dovecot():
    """Configures Dovecot for IMAP/POP3."""
    print("\n--- Configuring Dovecot (IMAP/POP3) ---")

    # Basic 10-mail.conf
    mail_conf_content = f"""
# /etc/dovecot/conf.d/10-mail.conf
# This file is managed by mailserver_config_tool.py.
# DO NOT EDIT THIS FILE MANUALLY UNLESS YOU KNOW WHAT YOU ARE DOING.

mail_location = maildir:/var/mail/%d/%n # Store mail in Maildir format under /var/mail/domain/user/
"""
    try:
        with open(DOVECOT_10_MAIL_CONF, 'w') as f:
            f.write(mail_conf_content.strip())
        print(f"✅ Dovecot mail location saved to {DOVECOT_10_MAIL_CONF}")
    except Exception as e:
        print(f"❌ Error writing Dovecot mail config: {e}")
        sys.exit(1)

    # Basic 10-auth.conf for plaintext authentication (for file-based users)
    auth_conf_content = f"""
# /etc/dovecot/conf.d/10-auth.conf
# This file is managed by mailserver_config_tool.py.
# DO NOT EDIT THIS FILE MANUALLY UNLESS YOU KNOW WHAT YOU ARE DOING.

disable_plaintext_auth = no # Allow plaintext auth (less secure, but easier for initial setup)
auth_mechanisms = plain login # Supported authentication mechanisms

!include auth-passwdfile.conf.ext # Include the password file configuration
"""
    try:
        with open(DOVECOT_10_AUTH_CONF, 'w') as f:
            f.write(auth_conf_content.strip())
        print(f"✅ Dovecot authentication config saved to {DOVECOT_10_AUTH_CONF}")
    except Exception as e:
        print(f"❌ Error writing Dovecot auth config: {e}")
        sys.exit(1)
        
    # Create required auth-passwdfile.conf.ext (used by 10-auth.conf)
    # This file tells Dovecot to use the 'users.conf' file for authentication
    auth_passwdfile_ext_content = f"""
# /etc/dovecot/conf.d/auth-passwdfile.conf.ext
# This file is managed by mailserver_config_tool.py.
# DO NOT EDIT THIS FILE MANUALLY UNLESS YOU KNOW WHAT YOU ARE DOING.

passdb {{
  driver = passwd-file
  args = scheme=SHA512-CRYPT username_format=%u /etc/dovecot/users.conf
}}

userdb {{
  driver = passwd-file
  args = username_format=%u /etc/dovecot/users.conf
  # default_fields = uid=vmail gid=vmail home=/var/mail/%d/%n # Example for specific UID/GID and home
}}
"""
    try:
        with open(os.path.join(DOVECOT_CONFIG_DIR, "conf.d", "auth-passwdfile.conf.ext"), 'w') as f:
            f.write(auth_passwdfile_ext_content.strip())
        print(f"✅ Dovecot auth-passwdfile.conf.ext created.")
    except Exception as e:
        print(f"❌ Error writing Dovecot auth-passwdfile.conf.ext: {e}")
        sys.exit(1)


    print("ℹ️ Dovecot's basic mail and authentication configuration is now set.")
    print("   For advanced features (SSL/TLS, LDAP/SQL user backends, Sieve filtering),")
    print("   you will need to manually edit files in the Dovecot config directory mounted at:")
    print(f"   {DOVECOT_CONFIG_DIR} (on the host: {os.path.join(os.getenv('BASE_DIR_HOST'), 'docker', 'mailserver', 'dovecot', 'config')})")

def manage_virtual_users():
    """Interactive management of virtual mail users."""
    users = load_virtual_users()
    while True:
        print("\n--- Manage Virtual Mail Users ---")
        print("1. List existing users")
        print("2. Add new user")
        print("3. Change user password")
        print("4. Delete user")
        print("0. Back to main menu")

        choice = get_user_input("Enter your choice: ")
        if choice == '1':
            if not users:
                print("No virtual users defined yet.")
            else:
                print("\nExisting Virtual Users:")
                for i, username in enumerate(users.keys()):
                    print(f"{i+1}. {username}")
        elif choice == '2':
            username = get_user_input("Enter new username (e.g., 'john.doe@example.com'): ").strip()
            if not username:
                print("Username cannot be empty.")
                continue
            if username in users:
                print(f"User '{username}' already exists. Use option 3 to change password.")
                continue
            password = get_user_input("Enter password for new user", secret=True)
            if not password:
                print("Password cannot be empty.")
                continue
            users[username] = hash_password(password)
            save_virtual_users(users)
            print(f"User '{username}' added.")
        elif choice == '3':
            username = get_user_input("Enter username to change password for: ").strip()
            if username not in users:
                print(f"User '{username}' not found.")
                continue
            password = get_user_input("Enter new password for user", secret=True)
            if not password:
                print("Password cannot be empty.")
                continue
            users[username] = hash_password(password)
            save_virtual_users(users)
            print(f"Password for user '{username}' updated.")
        elif choice == '4':
            username = get_user_input("Enter username to delete: ").strip()
            if username in users:
                del users[username]
                save_virtual_users(users)
                print(f"User '{username}' deleted.")
            else:
                print(f"User '{username}' not found.")
        elif choice == '0':
            break
        else:
            print("Invalid choice. Please try again.")

def main():
    ensure_directories_exist()

    while True:
        print("\n--- Mailserver Configuration Tool Main Menu ---")
        print("1. Configure Exim4 (MTA)")
        print("2. Configure Dovecot (IMAP/POP3)")
        print("3. Manage Virtual Mail Users")
        print("0. Exit")

        choice = get_user_input("Enter your choice: ")
        if choice == '1':
            configure_exim4()
        elif choice == '2':
            configure_dovecot()
        elif choice == '3':
            manage_virtual_users()
        elif choice == '0':
            print("Exiting Mailserver Configuration Tool.")
            break
        else:
            print("Invalid choice. Please try again.")

    print("\n--- Important Next Steps for Your Mailserver ---")
    print("1.  **Rebuild Mailserver Docker Images:** The Dockerfiles for Exim4 and Dovecot (if you customized them) need to be rebuilt, and then the containers restarted to pick up the new configuration files.")
    print(f"    Run: `bash {os.path.join(os.getenv('BASE_DIR_HOST', '/home/PiSelfhosting'), 'scripts', 'restart-all.sh')} mailserver`")
    print("2.  **SSL/TLS Certificates:** For secure mail (highly recommended!), you need to configure SSL/TLS certificates for both Exim4 and Dovecot.")
    print("    - Place your certificate files (e.g., fullchain.pem, privkey.pem) into the mailserver config directories on your host.")
    print(f"      Host paths: `{os.path.join(os.getenv('BASE_DIR_HOST'), 'docker', 'mailserver', 'exim4', 'config')}` and `{os.path.join(os.getenv('BASE_DIR_HOST'), 'docker', 'mailserver', 'dovecot', 'config')}`.")
    print("    - Then, edit the Exim4 and Dovecot configuration files (e.g., Exim's `update-exim4.conf.conf` or a separate TLS config, Dovecot's `10-ssl.conf`) to point to these certificate files.")
    print("3.  **DNS Records:** You must set up correct DNS records for your mail domain, including:")
    print("    - **A Record:** Your mail domain (e.g., `mail.example.com`) pointing to your server's public IP address.")
    print("    - **MX Record:** For `example.com` (your main domain), pointing to `mail.example.com` (your mail server's hostname).")
    print("    - **SPF Record:** A TXT record to specify allowed sending hosts (e.g., `v=spf1 mx a -all`).")
    print("    - **DKIM Record:** For email signing (requires Exim4 configuration and a key).")
    print("    - **DMARC Record:** For email policy enforcement (requires SPF and DKIM).")
    print("4.  **Firewall Rules:** Ensure ports 25 (SMTP), 143 (IMAP), 993 (IMAPS), 465 (SMTPS), 587 (Submission) are open on your router/firewall and forwarded to your mailserver container.")
    print("5.  **Anti-Spam/Anti-Virus:** Consider integrating solutions like SpamAssassin and ClamAV for a production environment (requires more complex configuration).")

if __name__ == "__main__":
    # asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy()) is removed for mailserver_config_tool.py as it does not use asyncio
    # For local testing compatibility on Windows, if it's needed for other parts that might get integrated,
    # it should be part of a proper async setup. The current main function is synchronous.
    
    # If the tool needed async functions (like ONVIF discovery), it would be structured like frigate_config_tool.py
    # For the mailserver tool, `asyncio` is not used, so setting event loop policy is unnecessary here.
    main() 

