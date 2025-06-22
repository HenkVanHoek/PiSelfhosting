import paramiko
import os
import sys
from stat import S_ISDIR
from dotenv import load_dotenv, set_key
import getpass

# --- Configuration ---
# Excluded items from synchronization (relative to project root)
# Ensure these patterns are relative to the local_path passed to sync_files_to_pi
# and should end with '/' for directories, or be exact filenames for files.
EXCLUDED_ITEMS = [
    '.git/',
    '.idea/',
    'venv/',
    '.pytest_cache/',
    '__pycache__/',  # Exclude Python cache directories like __pycache__/
    'docker/',  # Specific docker-compose files will be generated on Pi, so exclude the local 'docker' output directory
    'scripts/',  # Old scripts, will be replaced by src
    '.env',  # Exclude .env file itself from being synced to Pi (it's local config)
    'docker-compose.yml'  # The old global docker-compose.yml in the root
]

# Load environment variables from .env file
# This will load variables from .env into os.environ, allowing them to serve as defaults.
load_dotenv()

# --- Global variables (now potentially read from .env) ---
# These will be passed as environment variables to the setup.py script running on the Pi.
DEFAULT_PI_IP = os.getenv('PI_IP', 'raspberrypi.local')
DEFAULT_SSH_USERNAME = os.getenv('SSH_USERNAME', 'pi')
DEFAULT_DOMAIN = os.getenv('DOMAIN', 'yourdomain.com')
DEFAULT_PUID = os.getenv('PUID', '1000')  # Example User ID (typically 1000 for 'pi' user)
DEFAULT_PGID = os.getenv('PGID', '1000')  # Example Group ID (typically 1000 for 'pi' user)
DEFAULT_HOST_IP = os.getenv('HOST_IP',
                            '192.168.178.118')  # Default internal IP for container's extra_hosts (e.g., Dashy)
DEFAULT_DB_USER = os.getenv('DB_USER', 'piselfhosting_user')
DEFAULT_DB_PASS = os.getenv('DB_PASS', 'secure_password_please_change')
DEFAULT_TZ = os.getenv('TZ', 'Europe/Amsterdam')
DEFAULT_ADMIN_EMAIL = os.getenv('ADMIN_EMAIL',
                                'admin@yourdomain.com')  # Admin email for SSL certificates (e.g., Traefik)

# Path to the .env file (local to the installer script)
ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')


def run_remote_command(ssh_client, command):
    """Executes a command on the remote Raspberry Pi and prints output."""
    print(f"\nExecuting remote command: '{command}'")
    stdin, stdout, stderr = ssh_client.exec_command(command)
    exit_status = stdout.channel.recv_exit_status()  # Wait for command to complete

    stdout_output = stdout.read().decode('utf-8').strip()
    stderr_output = stderr.read().decode('utf-8').strip()

    if exit_status == 0:
        print("Command executed successfully.")
        if stdout_output:
            print(stdout_output)
        return True, stdout_output, stderr_output
    else:
        print(f"Command failed with exit status {exit_status}.")
        if stdout_output:
            print("STDOUT:")
            print(stdout_output)
        if stderr_output:
            print("STDERR:")
            print(stderr_output)
        return False, stdout_output, stderr_output


def _is_excluded(local_item_path, base_local_path, exclude_list):
    """Checks if a given local item path should be excluded from synchronization.
    Patterns in exclude_list are relative to base_local_path (project root)."""
    normalized_local_item_path = os.path.normpath(local_item_path).replace(os.sep, '/')

    # Calculate path relative to base_local_path (project root) for matching exclude_list patterns
    relative_path = os.path.relpath(local_item_path, base_local_path).replace(os.sep, '/')

    # Special handling for the base_local_path itself if it's the current directory ('.')
    if relative_path == ".":
        return False  # The root itself is never excluded, only its contents or specific files within it.

    for exclude_pattern in exclude_list:
        # Normalize the exclude pattern for comparison
        normalized_exclude_pattern = os.path.normpath(exclude_pattern).replace(os.sep, '/')

        if normalized_exclude_pattern.endswith('/'):  # Directory exclusion (e.g., 'venv/')
            # Check if the relative path starts with the excluded directory pattern
            # and ensure it's a full directory match (e.g., 'venv' not 'venom')
            if relative_path.startswith(normalized_exclude_pattern):
                return True
            # Also check exact match for the directory itself at the top level
            if relative_path == normalized_exclude_pattern.strip('/'):
                return True
        else:  # File exclusion (e.g., '.env', 'docker-compose.yml')
            # Check for exact file name match in the current directory, or a specific file path
            if relative_path == normalized_exclude_pattern:
                return True
            # Check if it's just the basename matching (for files anywhere)
            if os.path.basename(normalized_local_item_path) == normalized_exclude_pattern:
                return True
    return False


def _sftp_put_recursive(sftp_client, ssh_connection_client, local_src_path, remote_dest_path, exclude_list,
                        base_local_path):
    """
    Recursively uploads files and directories to the remote host via SFTP.
    Handles exclusions and creates remote directories as needed.
    """
    # Ensure remote_dest_path exists as a directory
    try:
        sftp_stat = sftp_client.stat(remote_dest_path)
        if not S_ISDIR(sftp_stat.st_mode):
            print(f"Warning: Remote path {remote_dest_path} exists but is not a directory. Skipping upload.")
            return
    except FileNotFoundError:
        success, _, _ = run_remote_command(ssh_connection_client, f"mkdir -p {remote_dest_path}")
        if not success:
            print(f"Error: Failed to create remote directory {remote_dest_path}. Skipping content upload.")
            return

    if os.path.isdir(local_src_path):
        for item in os.listdir(local_src_path):
            local_item_child_path = os.path.join(local_src_path, item)
            remote_item_child_path = os.path.join(remote_dest_path, item).replace('\\',
                                                                                  '/')  # Ensure forward slashes for Linux paths

            # Determine display path for logging (relative to project root)
            display_path = os.path.relpath(local_item_child_path, base_local_path).replace(os.sep, '/')

            if _is_excluded(local_item_child_path, base_local_path, exclude_list):
                print(f"Skipping excluded item: {display_path}/" if os.path.isdir(
                    local_item_child_path) else f"Skipping excluded item: {display_path}")
                continue

            if os.path.isdir(local_item_child_path):
                print(f"Uploading directory: {display_path}/")
                _sftp_put_recursive(sftp_client, ssh_connection_client, local_item_child_path, remote_item_child_path,
                                    exclude_list, base_local_path)
            else:  # It's a file
                print(f"  Uploading: {display_path}")
                sftp_client.put(local_item_child_path, remote_item_child_path)
    # If local_src_path is a file, it should have been handled by the calling sync_files_to_pi or recursive call.
    # This function is primarily designed to recurse into directories.


def sync_files_to_pi(ssh_client, local_path, remote_path, exclude_list):
    """
    Synchronizes files and directories from local_path to remote_path on the Pi.
    This function first clears the remote project directory for a clean sync.
    """
    print(f"\n--- Uploading files from {local_path} to {remote_path} ---")

    # Clear and recreate the entire remote project directory (using sudo for permissions)
    print(f"Clearing and recreating remote directory {remote_path} to ensure clean synchronization...")
    success, _, stderr = run_remote_command(ssh_client, f"sudo rm -rf {remote_path} && mkdir -p {remote_path}")
    if not success:
        print(f"Error: Failed to clear and recreate remote directory. Exiting. Error: {stderr}")
        ssh_client.close()
        sys.exit(1)
    else:
        print("Remote directory cleared and recreated successfully.")

    sftp = ssh_client.open_sftp()

    # Iterate over top-level items in local_path and upload them recursively
    for item_name in os.listdir(local_path):
        local_item_full_path = os.path.join(local_path, item_name)
        remote_item_full_path = os.path.join(remote_path, item_name).replace('\\', '/')  # Ensure forward slashes

        if _is_excluded(local_item_full_path, local_path, exclude_list):
            print(f"Skipping excluded item: {item_name}/" if os.path.isdir(
                local_item_full_path) else f"Skipping excluded item: {item_name}")
            continue

        if os.path.isdir(local_item_full_path):
            print(f"Uploading directory: {item_name}/")
            _sftp_put_recursive(sftp, ssh_client, local_item_full_path, remote_item_full_path, exclude_list, local_path)
        else:  # Top-level file
            print(f"  Uploading: {item_name}")
            sftp.put(local_item_full_path, remote_item_full_path)

    sftp.close()
    print("File upload complete.")


def main():
    print("--- PiSelfhosting Installer & Orchestrator ---")
    print("This script helps you manage your PiSelfhosting project on your Raspberry Pi.")

    # Use default values from .env if available
    pi_ip = input(f"Enter Raspberry Pi IP address or hostname (default: {DEFAULT_PI_IP}): ")
    if not pi_ip:
        pi_ip = DEFAULT_PI_IP
    set_key(ENV_PATH, "PI_IP", pi_ip)  # Save to .env
    print(f"Using Raspberry Pi IP/hostname: {pi_ip}")

    ssh_username = input(f"Enter Raspberry Pi SSH username (default: {DEFAULT_SSH_USERNAME}): ")
    if not ssh_username:
        ssh_username = DEFAULT_SSH_USERNAME
    set_key(ENV_PATH, "SSH_USERNAME", ssh_username)  # Save to .env
    print(f"Using SSH username: {ssh_username}")

    ssh_password = getpass.getpass(f"Enter password for {ssh_username}@{pi_ip}: ")

    ssh_client = paramiko.SSHClient()
    ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        print(f"Attempting to connect to {ssh_username}@{pi_ip}:22...")
        ssh_client.connect(hostname=pi_ip, username=ssh_username, password=ssh_password, port=22, timeout=10)
        print("Successfully connected to Raspberry Pi via SSH.")
    except Exception as e:
        print(f"Failed to connect to Raspberry Pi: {e}")
        sys.exit(1)

    # --- Determine remote project path ---
    print("\n--- Determining remote project path ---")
    success, stdout, _ = run_remote_command(ssh_client, 'echo $HOME')
    if not success:
        print("Could not determine remote home directory. Exiting.")
        ssh_client.close()
        sys.exit(1)
    remote_home_dir = stdout
    remote_project_path = os.path.join(remote_home_dir, "PiSelfhosting").replace('\\',
                                                                                 '/')  # Ensure forward slashes for Linux paths
    print(f"Determined remote home directory: {remote_home_dir}")
    print(f"Project will be installed/synced in: {remote_project_path}")

    # --- Test basic remote command execution ---
    print("\n--- Testing basic remote command execution ---")
    success, _, _ = run_remote_command(ssh_client, 'uname -a')
    if not success:
        print("Basic remote command failed. Exiting.")
        ssh_client.close()
        sys.exit(1)
    print("Basic command 'uname -a' succeeded.")

    # --- Check Docker Installation ---
    print("\n--- Checking Docker Installation ---")
    success, _, _ = run_remote_command(ssh_client, 'which docker')
    if not success:
        print("Docker command not found. Please install Docker on your Raspberry Pi. Exiting.")
        ssh_client.close()
        sys.exit(1)
    print("Docker command found. Checking Docker service status...")

    success, _, _ = run_remote_command(ssh_client, 'sudo systemctl is-active docker')
    if not success:
        print("Docker service is not running. Please start Docker. Exiting.")
        ssh_client.close()
        sys.exit(1)
    print("Docker is installed and running.")

    # --- Check and Add User to Docker Group ---
    print("\n--- Checking and Adding User to Docker Group ---")
    success, stdout, _ = run_remote_command(ssh_client, f'groups {ssh_username}')
    if not success or 'docker' not in stdout:
        print(f"User '{ssh_username}' is not in the 'docker' group. Attempting to add...")
        print("You may be prompted for your password on the Pi for 'sudo' command.")
        success, _, stderr_output = run_remote_command(ssh_client,
                                                       f'sudo usermod -aG docker {ssh_username} && newgrp docker')
        if not success:
            print(f"Failed to add user to docker group. Error: {stderr_output}")
            print("Please add the user to the 'docker' group manually: 'sudo usermod -aG docker YOUR_USERNAME'")
            ssh_client.close()
            sys.exit(1)
        print(f"User '{ssh_username}' added to 'docker' group. A reboot might be required for changes to take effect.")
    else:
        print(f"User '{ssh_username}' is already in the 'docker' group.")
    print("Docker setup complete.")

    # --- Gathering configuration parameters and saving to .env ---
    print("\n--- Gathering configuration parameters ---")

    domain = input(f"Enter your primary domain name (default: {DEFAULT_DOMAIN}): ")
    if not domain:
        domain = DEFAULT_DOMAIN
    set_key(ENV_PATH, "DOMAIN", domain)  # Save to .env
    print(f"Using domain: {domain}")

    puid = input(f"Enter PUID for user (default: {DEFAULT_PUID}): ")
    if not puid:
        puid = DEFAULT_PUID
    set_key(ENV_PATH, "PUID", puid)  # Save to .env
    print(f"Using PUID: {puid}")

    pgid = input(f"Enter PGID for user (default: {DEFAULT_PGID}): ")
    if not pgid:
        pgid = DEFAULT_PGID
    set_key(ENV_PATH, "PGID", pgid)  # Save to .env
    print(f"Using PGID: {pgid}")

    # Host IP for extra_hosts (needed by Dashy)
    host_ip = input(f"Enter Raspberry Pi's internal IP for container's extra_hosts (default: {DEFAULT_HOST_IP}): ")
    if not host_ip:
        host_ip = DEFAULT_HOST_IP
    set_key(ENV_PATH, "HOST_IP", host_ip)  # Save to .env
    print(f"Using host IP for containers: {host_ip}")

    # Database credentials for services like NPM, phpMyAdmin
    db_user = input(f"Enter database username (default: {DEFAULT_DB_USER}): ")
    if not db_user:
        db_user = DEFAULT_DB_USER
    set_key(ENV_PATH, "DB_USER", db_user)  # Save to .env
    print(f"Using DB user: {db_user}")

    db_pass = getpass.getpass(f"Enter database password (default: {DEFAULT_DB_PASS}): ")
    if not db_pass:
        db_pass = DEFAULT_DB_PASS
    set_key(ENV_PATH, "DB_PASS", db_pass)  # Save to .env
    print(f"Using DB password: {'*' * len(db_pass) if db_pass else 'None'}")  # Mask password output

    # Timezone
    tz = input(f"Enter timezone (default: {DEFAULT_TZ}, e.g., Europe/Amsterdam): ")
    if not tz:
        tz = DEFAULT_TZ
    set_key(ENV_PATH, "TZ", tz)  # Save to .env
    print(f"Using timezone: {tz}")

    admin_email = input(f"Enter admin email for SSL certificates (default: {DEFAULT_ADMIN_EMAIL}): ")
    if not admin_email:
        admin_email = DEFAULT_ADMIN_EMAIL
    set_key(ENV_PATH, "ADMIN_EMAIL", admin_email)  # Save to .env
    print(f"Using admin email: {admin_email}")

    # --- Start project file synchronization ---
    print("\n--- Starting project file synchronization ---")
    local_project_path = os.path.abspath(os.path.dirname(__file__))

    sync_files_to_pi(ssh_client, local_project_path, remote_project_path, EXCLUDED_ITEMS)

    # --- Build and Run Setup Tool via Docker container ---
    print("\n--- Starting setup tool execution via Docker container ---")

    # Build Docker image for the setup tool
    print("\n--- Building Docker image for setup tool (piselfhosting-setup-tool) ---")
    docker_build_command = (
        f"docker build -t piselfhosting-setup-tool "
        f"-f {remote_project_path}/Dockerfile.setup-tool "  # Path to Dockerfile
        f"{remote_project_path}"  # Build context
    )
    success, stdout_build, stderr_build = run_remote_command(ssh_client, docker_build_command)
    if not success:
        print(f"Failed to build Docker image for setup tool. Exiting. Error: {stderr_build}")
        ssh_client.close()
        sys.exit(1)
    print("Docker image 'piselfhosting-setup-tool' built successfully.")

    # Run setup.py inside the Docker container with environment variables
    print("\n--- Running src/setup.py inside Docker container ---")
    # Pass environment variables to the Docker container, including the remote project path
    env_vars_for_docker = (
        f"-e DOMAIN=\"{domain}\" "
        f"-e PUID=\"{puid}\" "
        f"-e PGID=\"{pgid}\" "
        f"-e HOST_IP=\"{host_ip}\" "
        f"-e DB_USER=\"{db_user}\" "
        f"-e DB_PASS=\"{db_pass}\" "
        f"-e TZ=\"{tz}\" "
        f"-e ADMIN_EMAIL=\"{admin_email}\" "
        f"-e REMOTE_PROJECT_PATH=\"{remote_project_path}\""  # Pass remote project path for setup.py's host path output
    )
    # The setup.py script expects to find project files under /app
    setup_tool_command = (
        f"docker run --rm "  # --rm removes the container after it exits
        f"-v {remote_project_path}:/app "  # Mount project directory
        f"{env_vars_for_docker} "  # Environment variables for the container
        f"piselfhosting-setup-tool "  # Image name
        f"python /app/src/setup.py"  # Command to execute inside the container
    )
    success, stdout_setup, stderr_setup = run_remote_command(ssh_client, setup_tool_command)

    if not success:
        print(f"Error during setup tool execution inside Docker container. Exiting. Error: {stderr_setup}")
        ssh_client.close()
        sys.exit(1)
    print("src/setup.py executed successfully inside the Docker container.")

    print("\n--- PiSelfhosting Deployment Process Complete ---")
    print("Your PiSelfhosting services should now be configured and deployed on your Raspberry Pi.")
    print("Remember to check the web interfaces of your services!")

    ssh_client.close()
    print("SSH connection closed.")


if __name__ == "__main__":
    main()