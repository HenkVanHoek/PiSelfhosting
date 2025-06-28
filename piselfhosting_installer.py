import paramiko
import os
import sys
from stat import S_ISDIR
from dotenv import load_dotenv, set_key
import getpass
import socket
import threading
import time
import json
import re

# Import constants from src.setup (needed for paths)
from src.setup import DOCKER_COMPOSE_OUTPUT_DIR, UNIFIED_DOCKER_COMPOSE_FILENAME, \
    GLOBAL_DATA_ROOT  # Also import GLOBAL_DATA_ROOT

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
#    'scripts/',  # Old scripts, will be replaced by src
    '.env',  # This excludes the .env file in the project ROOT, as it's for local installer config only.
    'docker-compose.yml'  # The old global docker-compose.yml in the root
]

# Load environment variables from .env file
load_dotenv()

# --- Global variables ---
DEFAULT_PI_IP = os.getenv('PI_IP', 'raspberrypi.local')
DEFAULT_SSH_USERNAME = os.getenv('SSH_USERNAME', 'pi')
DEFAULT_SSH_PASSWORD = os.getenv('SSH_PASSWORD', '')

DEFAULT_DOMAIN = os.getenv('DOMAIN', 'yourdomain.com')
DEFAULT_PUID = os.getenv('PUID', '1000')
DEFAULT_PGID = os.getenv('PGID', '1000')
DEFAULT_HOST_IP = os.getenv('HOST_IP', '192.168.178.118')
DEFAULT_DB_USER = os.getenv('DB_USER', 'piselfhosting_user')
DEFAULT_DB_PASS = os.getenv('DB_PASS', 'secure_password_please_change')
DEFAULT_TZ = os.getenv('TZ', 'Europe/Amsterdam')
DEFAULT_ADMIN_EMAIL = os.getenv('ADMIN_EMAIL', 'admin@yourdomain.com')
DEFAULT_FRIGATE_RTSP_PASSWORD = os.getenv('FRIGATE_RTSP_PASSWORD', 'change_me_frigate_rtsp_pass')
DEFAULT_PHPMYADMIN_BLOWFISH_SECRET = os.getenv('PHPMYADMIN_BLOWFISH_SECRET', os.urandom(32).hex())
DEFAULT_PMA_HOST = os.getenv('PMA_HOST', 'mariadb')

DEFAULT_REUSE_VARIABLES_FLAG = os.getenv('PISELFHOSTING_REUSE_VARIABLES', 'false').lower()

# Path to the .env file (local to the installer script)
ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')


# --- Helper Functions ---

def get_user_input(prompt, default_value, use_previous=False, stored_value=None):
    """Asks for user input with a default value."""
    if use_previous:
        print(f"{prompt} (using previous: {stored_value})")
        return stored_value
    user_input = input(f"{prompt} (default: {default_value}): ").strip()
    return user_input if user_input else default_value


def get_password(prompt, use_previous=False, stored_value=None):
    """Safely asks for a password."""
    if use_previous and stored_value:
        print(f"{prompt} (using previous: {'*' * len(str(stored_value))})")
        return stored_value
    pwd = getpass.getpass(prompt)
    return pwd if pwd else stored_value


# noinspection PyBroadException
def get_local_ip_address():
    """
    Attempts to determine the internal IP address of the host running the script.
    This is a basic implementation and may not work in all network configurations.
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip_address = s.getsockname()[0]
        s.close()
        return ip_address
    except Exception:
        return None


# Helper for threaded remote command execution
_remote_command_result = {}  # Use a dict to store results from the thread
_remote_command_done_event = threading.Event()  # Event to signal completion


def _run_command_in_thread(ssh_client, command, local_result_dict):
    """Helper to run command in a thread and store results."""
    stdin, stdout, stderr = ssh_client.exec_command(command)
    local_result_dict['stdout'] = stdout.read().decode('utf-8').strip()
    local_result_dict['stderr'] = stderr.read().decode('utf-8').strip()
    local_result_dict['exit_status'] = stdout.channel.recv_exit_status()
    _remote_command_done_event.set()  # Signal completion


# Modified run_remote_command with spinner
# noinspection PyArgumentList,PyTypeChecker
def run_remote_command(ssh_client, command, check_exit_status=True):
    """Executes a command on the remote Raspberry Pi and prints output with a spinner."""
    print(f"\nExecuting remote command: '{command}'")

    _remote_command_result.clear()  # Clear results from previous run
    _remote_command_done_event.clear()  # Reset event for new command

    # Start the command in a separate thread
    command_thread = threading.Thread(target=_run_command_in_thread, args=(ssh_client, command, _remote_command_result))
    command_thread.start()

    # Show a spinner while the command is running
    spinner_chars = ['-', '\\', '|', '/']  # Simple spinner animation
    spinner_idx = 0
    print("Working ", end="", flush=True)  # Print "Working " without newline

    while not _remote_command_done_event.is_set():  # Wait until the event is set by the thread
        print(f"\b{spinner_chars[spinner_idx]}", end="", flush=True)  # Overwrite previous char using backspace
        spinner_idx = (spinner_idx + 1) % len(spinner_chars)
        time.sleep(0.1)  # Update every 100ms

    command_thread.join()  # Ensure the thread has completely finished
    print("\b \n", end="", flush=True)  # Clear spinner and print a newline

    stdout_output = _remote_command_result.get('stdout', '')
    stderr_output = _remote_command_result.get('stderr', '')
    exit_status = _remote_command_result.get('exit_status', -1)  # Default to -1 if no status

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
        if check_exit_status:
            raise Exception(f"Remote command failed: {command}\nSTDERR:\n{stderr_output}")
        return False, stdout_output, stderr_output


def _is_excluded(local_item_path, base_local_path, exclude_list):
    """Checks if a given local item path should be excluded from synchronization.
    Patterns in exclude_list are relative to base_local_path (project root)."""
    normalized_local_item_path = os.path.normpath(local_item_path).replace(os.sep, '/')

    relative_path = os.path.relpath(local_item_path, base_local_path).replace(os.sep, '/')

    if relative_path == ".":
        return False

    for exclude_pattern in exclude_list:
        normalized_exclude_pattern = os.path.normpath(exclude_pattern).replace(os.sep, '/')

        if normalized_exclude_pattern.endswith('/'):
            if relative_path.startswith(normalized_exclude_pattern):
                return True
            if relative_path == normalized_exclude_pattern.strip('/'):
                return True
        else:
            # Corrected logic for file exclusion:
            # Match exact relative path (e.g., '.env' for root .env)
            if relative_path == normalized_exclude_pattern:
                return True
            # Also cover files by basename if the exclude_pattern is just a basename (no slashes in pattern)
            elif os.path.basename(
                    normalized_local_item_path) == normalized_exclude_pattern and '/' not in normalized_exclude_pattern:
                return True

    return False


def _sftp_put_recursive(sftp_client, ssh_connection_client, local_src_path, remote_dest_path, exclude_list,
                        base_local_path):
    """
    Recursively uploads files and directories to the remote host via SFTP.
    Handles exclusions and creates remote directories as needed.
    """
    try:
        sftp_stat = sftp_client.stat(remote_dest_path)
        if not S_ISDIR(sftp_stat.st_mode):
            print(f"Warning: Remote path {remote_dest_path} exists but is not a directory. Skipping upload.")
            return
    except FileNotFoundError:
        # noinspection PyBroadException
        try:
            success, _, _ = run_remote_command(ssh_connection_client, f"mkdir -p {remote_dest_path}")
            if not success:
                print(f"Error: Failed to create remote directory {remote_dest_path}. Skipping content upload.")
                return
        except Exception:
            print(
                f"Error: Failed to create remote directory {remote_dest_path} (exception caught). Skipping content upload.")
            return

    if os.path.isdir(local_src_path):
        for item in os.listdir(local_src_path):
            local_item_child_path = os.path.join(local_src_path, item)
            remote_item_child_path = os.path.join(remote_dest_path, item).replace('\\', '/')

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


def sync_files_to_pi(ssh_client, local_path, remote_path, exclude_list):
    """
    Synchronizes files and directories from local_path to remote_path on the Pi.
    This function first clears the remote project directory for a clean sync.
    """
    print(f"\n--- Uploading files from {local_path} to {remote_path} ---")

    print(f"Clearing and recreating remote directory {remote_path} to ensure clean synchronization...")
    # noinspection PyBroadException
    try:
        success, _, stderr = run_remote_command(ssh_client, f"sudo rm -rf {remote_path} && mkdir -p {remote_path}")
        if not success:
            print(f"Error: Failed to clear and recreate remote directory. Exiting. Error: {stderr}")
            ssh_client.close()
            sys.exit(1)
        else:
            print("Remote directory cleared and recreated successfully.")
    except Exception as e:
        print(f"Error: An unexpected error occurred during remote directory clear/recreate: {e}. Exiting.")
        ssh_client.close()
        sys.exit(1)

    sftp = ssh_client.open_sftp()

    for item_name in os.listdir(local_path):
        local_item_full_path = os.path.join(local_path, item_name)
        remote_item_full_path = os.path.join(remote_path, item_name).replace('\\', '/')

        if _is_excluded(local_item_full_path, local_path, exclude_list):
            print(f"Skipping excluded item: {item_name}/" if os.path.isdir(
                local_item_full_path) else f"Skipping excluded item: {item_name}")
            continue

        if os.path.isdir(local_item_full_path):
            print(f"Uploading directory: {item_name}/")
            _sftp_put_recursive(sftp, ssh_client, local_item_full_path, remote_item_full_path, exclude_list, local_path)
        else:
            print(f"  Uploading: {item_name}")
            sftp.put(local_item_full_path, remote_item_full_path)

    sftp.close()
    print("File upload complete.")


def run_remote_docker_compose(ssh_client, remote_project_path, action):
    """
    Executes a Docker Compose command (e.g., 'up -d', 'down') on the remote Raspberry Pi.
    Assumes docker-compose CLI is installed and user is in 'docker' group.
    """
    print(f"\n--- Executing 'docker compose {action}' on Raspberry Pi ---")

    remote_docker_compose_dir = os.path.join(remote_project_path, DOCKER_COMPOSE_OUTPUT_DIR).replace('\\', '/')
    unified_compose_file_on_host = os.path.join(remote_docker_compose_dir, UNIFIED_DOCKER_COMPOSE_FILENAME).replace(
        '\\', '/')

    command = f"docker compose -f {unified_compose_file_on_host} {action}"

    if action == "up -d":
        print(f"Attempting to start services with: {command}")
    elif action == "down":
        print(f"Attempting to stop and remove services with: {command}")
    else:
        print(f"Error: Unknown Docker Compose action '{action}'.")
        return False

    success, stdout, stderr = run_remote_command(ssh_client, command)

    if success:
        print(f"Docker Compose '{action}' command executed successfully on Raspberry Pi.")
        return True
    else:
        print(f"Docker Compose '{action}' command failed. Error: {stderr}")
        return False


def main():
    """Main function of the installer."""
    print("--- PiSelfhosting Installer & Orchestrator ---")
    print("This script helps you manage your PiSelfhosting project on your Raspberry Pi.")

    use_previous_values = False
    if DEFAULT_REUSE_VARIABLES_FLAG == 'true':
        while True:
            choice = input(
                f"Reuse previously stored values? (Y/n/q, current state: {DEFAULT_REUSE_VARIABLES_FLAG.upper()}): ").strip().lower()
            if choice == 'y' or choice == '':
                use_previous_values = True
                break
            elif choice == 'n':
                use_previous_values = False
                break
            elif choice == 'q':
                print("Exiting installer.")
                set_key(ENV_PATH, "PISELFHOSTING_REUSE_VARIABLES", "false")  # Explicitly set to false on quit
                sys.exit(0)
            else:
                print("Invalid choice. Please enter 'Y', 'n', or 'q'.")
    else:
        print("No previous values found or reuse is set to 'false'. Starting with fresh input.")

    # --- Request SSH details ---
    pi_hostname = get_user_input("Enter Raspberry Pi IP address or hostname", DEFAULT_PI_IP, use_previous_values,
                                 os.getenv('PI_IP'))
    ssh_username = get_user_input("Enter Raspberry Pi SSH username", DEFAULT_SSH_USERNAME, use_previous_values,
                                  os.getenv('SSH_USERNAME'))
    ssh_password = get_password(f"Enter password for {ssh_username}@{pi_hostname}", use_previous_values,
                                os.getenv('SSH_PASSWORD'))

    if DEFAULT_SSH_PASSWORD != ssh_password:
        set_key(ENV_PATH, "SSH_PASSWORD", ssh_password)
        print("WARNING: SSH password stored in .env file. Keep this file secure and out of version control!")
    elif use_previous_values and os.getenv('SSH_PASSWORD'):
        print("Using previous SSH password from .env.")

    # --- Establish SSH connection ---
    # noinspection PyBroadException
    try:
        print(f"Attempting to connect to {ssh_username}@{pi_hostname}:22...")
        ssh_client = paramiko.SSHClient()
        ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh_client.connect(hostname=pi_hostname, username=ssh_username, password=ssh_password, port=22, timeout=10)
        print("Successfully connected to Raspberry Pi via SSH.")
    except paramiko.AuthenticationException:
        print("Authentication failed. Please check your username and password.")
        sys.exit(1)
    except paramiko.SSHException as e:
        print(f"Could not establish SSH connection: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred during SSH connection: {e}")
        sys.exit(1)

    # --- Determine remote project path ---
    print("\n--- Determining remote project path ---")
    # noinspection PyBroadException
    try:
        success, home_dir, _ = run_remote_command(ssh_client, 'echo $HOME')
        if not success:
            raise Exception("Failed to get remote home directory.")
        print(f"Determined remote home directory: {home_dir}")
        remote_project_path = os.path.join(home_dir, "PiSelfhosting").replace("\\", "/")
        print(f"Project will be installed/synced in: {remote_project_path}")
    except Exception as e:
        print(f"Failed to determine remote home directory: {e}")
        ssh_client.close()
        sys.exit(1)

    # --- Test basic remote command execution ---
    print("\n--- Testing basic remote command execution ---")
    # noinspection PyBroadException
    try:
        success_basic_cmd, _, _ = run_remote_command(ssh_client, 'uname -a')
        if not success_basic_cmd:
            raise Exception("Basic command failed.")
        print("Basic command 'uname -a' succeeded.")
    except Exception as e:
        print(f"Basic command execution failed: {e}")
        ssh_client.close()
        sys.exit(1)

    # --- Check Docker Installation ---
    print("\n--- Checking Docker Installation ---")
    # noinspection PyBroadException
    try:
        success_which_docker, docker_path, _ = run_remote_command(ssh_client, 'which docker', check_exit_status=False)
        if success_which_docker:
            print("Docker command found. Checking Docker service status...")
            success_systemctl, docker_status, _ = run_remote_command(ssh_client, 'sudo systemctl is-active docker',
                                                                     check_exit_status=False)
            if success_systemctl and docker_status == 'active':
                print("Docker is installed and running.")
            else:
                print("Docker is installed but not running or not active. Please start Docker service.")
                sys.exit(1)
        else:
            print("Docker command not found. Please install Docker on your Raspberry Pi.")
            print(
                "Refer to the official Docker documentation for installation instructions: https://docs.docker.com/engine/install/debian/")
            ssh_client.close()
            sys.exit(1)
    except Exception as e:
        print(f"Error checking Docker installation: {e}")
        ssh_client.close()
        sys.exit(1)

    # --- Check and Add User to Docker Group ---
    print("\n--- Checking and Adding User to Docker Group ---")
    # noinspection PyBroadException
    try:
        success_groups, groups_output, _ = run_remote_command(ssh_client, f'groups {ssh_username}')
        if not success_groups:
            raise Exception(f"Failed to retrieve user groups for '{ssh_username}'.")

        if 'docker' in groups_output:
            print(f"User '{ssh_username}' is already in the 'docker' group.")
        else:
            print(f"User '{ssh_username}' is not in the 'docker' group. Adding user to 'docker' group...")
            run_remote_command(ssh_client, f'sudo usermod -aG docker {ssh_username}')
            print(
                f"User '{ssh_username}' added to 'docker' group. You may need to log out and log back in for changes to take effect.")
    except Exception as e:
        print(f"Error checking/adding user to docker group: {e}")
        ssh_client.close()
        sys.exit(1)
    print("Docker setup complete.")

    # --- Gather configuration parameters ---
    print("\n--- Gathering configuration parameters ---")
    domain = get_user_input("Enter your primary domain name", DEFAULT_DOMAIN, use_previous_values, os.getenv('DOMAIN'))
    puid = get_user_input("Enter PUID for user", str(DEFAULT_PUID), use_previous_values, os.getenv('PUID'))
    pgid = get_user_input("Enter PGID for user", str(DEFAULT_PGID), use_previous_values, os.getenv('PGID'))

    detected_ip = get_local_ip_address()
    if detected_ip:
        # noinspection PyTypeChecker
        host_ip = get_user_input(
            f"Enter Raspberry Pi's internal IP for container's extra_hosts (default: {detected_ip})", detected_ip,
            use_previous_values, os.getenv('HOST_IP'))
    else:
        # noinspection PyTypeChecker
        host_ip = get_user_input(f"Enter Raspberry Pi's internal IP for container's extra_hosts", DEFAULT_HOST_IP,
                                 use_previous_values, os.getenv('HOST_IP'))
    print(f"Using host IP for containers: {host_ip}")

    db_user = get_user_input("Enter database username", DEFAULT_DB_USER, use_previous_values, os.getenv('DB_USER'))
    db_pass = get_password(
        f"Enter database password (default: {'*' * len(DEFAULT_DB_PASS) if DEFAULT_DB_PASS else 'None'}):",
        use_previous_values, DEFAULT_DB_PASS)
    print("Using DB password: ************")

    tz = get_user_input("Enter timezone (e.g., Europe/Amsterdam)", DEFAULT_TZ, use_previous_values, os.getenv('TZ'))
    admin_email = get_user_input("Enter admin email for SSL certificates", DEFAULT_ADMIN_EMAIL, use_previous_values,
                                 os.getenv('ADMIN_EMAIL'))

    frigate_rtsp_password = get_password(
        f"Enter Frigate RTSP password (default: {'*' * len(DEFAULT_FRIGATE_RTSP_PASSWORD) if DEFAULT_FRIGATE_RTSP_PASSWORD else 'None'}):",
        use_previous_values, DEFAULT_FRIGATE_RTSP_PASSWORD)
    print("Using Frigate RTSP password: ************")

    # Generate a random blowfish secret for phpMyAdmin ONLY IF NOT REUSING OR NOT ALREADY SET
    phpmyadmin_blowfish_secret = os.getenv('PHPMYADMIN_BLOWFISH_SECRET')
    if not use_previous_values or not phpmyadmin_blowfish_secret:
        phpmyadmin_blowfish_secret = os.urandom(32).hex()
        set_key(ENV_PATH, "PHPMYADMIN_BLOWFISH_SECRET", phpmyadmin_blowfish_secret)
        print("Generated new phpMyAdmin Blowfish Secret.")
    else:
        print("Using previous phpMyAdmin Blowfish Secret.")
        os.environ['PHPMYADMIN_BLOWFISH_SECRET'] = phpmyadmin_blowfish_secret

    pma_host = get_user_input("Enter phpMyAdmin host (internal Docker network name)", DEFAULT_PMA_HOST,
                              use_previous_values, os.getenv('PMA_HOST'))

    # Collect all environment variables for the .env file to be written to Pi's docker folder
    collected_env_vars = {
        "DOMAIN": domain,
        "PUID": puid,
        "PGID": pgid,
        "HOST_IP": host_ip,
        "DB_USER": db_user,
        "DB_PASS": db_pass,
        "TZ": tz,
        "ADMIN_EMAIL": admin_email,
        "REMOTE_PROJECT_PATH": remote_project_path,
        "TRAEFIK_DASHBOARD_DOMAIN": f"traefik.{domain}",
        "FRIGATE_RTSP_PASSWORD": frigate_rtsp_password,
        "PHPMYADMIN_BLOWFISH_SECRET": phpmyadmin_blowfish_secret,
        "PMA_HOST": pma_host
    }
    # Persist all collected variables to the local .env file
    for key, value in collected_env_vars.items():
        if key == "REMOTE_PROJECT_PATH":
            continue
        if os.getenv(key) != value:
            set_key(ENV_PATH, key, value)

    # CRUCIAL: Set the reuse flag to 'true' here, after all variables are successfully collected and persisted.
    # This indicates that for the *next* run, the reuse prompt will appear and values can be used.
    set_key(ENV_PATH, "PISELFHOSTING_REUSE_VARIABLES", "true")
    print("Updated local .env file with current configuration.")
    print("Next run can reuse these values by default.")

    # --- Start project file synchronization ---
    print("\n--- Starting project file synchronization ---")
    local_project_path = os.path.abspath(os.path.dirname(__file__))

    # Generate the .env file to be synced to Pi's docker folder
    local_docker_output_path = os.path.join(local_project_path, DOCKER_COMPOSE_OUTPUT_DIR)
    os.makedirs(local_docker_output_path, exist_ok=True)

    local_docker_env_path = os.path.join(local_docker_output_path, ".env")
    with open(local_docker_env_path, "w") as f:
        for key, value in collected_env_vars.items():
            f.write(f"{key}={value}\n")
    print(f"Generated temp .env file for Docker Compose on Pi at {local_docker_env_path}")

    sync_files_to_pi(ssh_client, local_project_path, remote_project_path, EXCLUDED_ITEMS)

    # NEW: Explicitly upload the generated docker/.env file (critical for Docker Compose)
    print("\n--- Uploading Docker Compose .env file to Raspberry Pi ---")
    remote_docker_output_path = os.path.join(remote_project_path, DOCKER_COMPOSE_OUTPUT_DIR).replace('\\', '/')
    # noinspection PyBroadException
    try:
        success_mkdir_docker_env, _, stderr_mkdir_docker_env = run_remote_command(ssh_client,
                                                                                  f"mkdir -p {remote_docker_output_path}")
        if not success_mkdir_docker_env:
            print(
                f"Error: Failed to ensure remote Docker output directory exists at {remote_docker_output_path}: {stderr_mkdir_docker_env}")
            ssh_client.close()
            sys.exit(1)
        sftp_client = ssh_client.open_sftp()
        sftp_client.put(local_docker_env_path, os.path.join(remote_docker_output_path, ".env").replace('\\', '/'))
        sftp_client.close()
        print(
            f"Successfully uploaded {os.path.basename(local_docker_env_path)} to {os.path.join(remote_docker_output_path, '.env')}")
    except Exception as e:
        print(f"Error uploading Docker Compose .env file to Pi: {e}")
        ssh_client.close()
        sys.exit(1)

    # --- Start setup tool execution via Docker container ---
    print("\n--- Starting setup tool execution via Docker container ---")

    # Build Docker image for setup tool
    # noinspection PyBroadException
    try:
        docker_build_command = (
            f"docker build -t piselfhosting-setup-tool "
            f"-f {remote_project_path}/Dockerfile.setup-tool "
            f"{remote_project_path}"
        )
        run_remote_command(ssh_client, docker_build_command)
        print("Docker image 'piselfhosting-setup-tool' built successfully.")
    except Exception as e:
        print(f"Failed to build Docker image for setup tool: {e}")
        ssh_client.close()
        sys.exit(1)

    # Run src/setup.py within Docker container
    print("\n--- Running src/setup.py inside Docker container ---")
    env_vars_for_docker_run_list = []
    for key, value in collected_env_vars.items():
        if ' ' in str(value):
            env_vars_for_docker_run_list.append(f"-e {key}=\"{value}\"")
        else:
            env_vars_for_docker_run_list.append(f"-e {key}={value}")
    env_vars_for_docker_run = " ".join(env_vars_for_docker_run_list)

    docker_run_command = (
        f"docker run --rm "
        f"-v {remote_project_path}:/app "
        f"{env_vars_for_docker_run} "
        f"piselfhosting-setup-tool "
        f"python /app/src/setup.py"
    )
    # noinspection PyBroadException
    try:
        success_setup, stdout_setup, stderr_setup = run_remote_command(ssh_client, docker_run_command)

        generated_config_files_to_move_map = {}
        if success_setup:
            print("src/setup.py executed successfully inside the Docker container.")
            json_line = None
            for line in reversed(stdout_setup.splitlines()):
                if line.strip().startswith('{') and line.strip().endswith('}'):
                    json_line = line.strip()
                    break

            if json_line:
                # noinspection PyBroadException
                try:
                    generated_config_files_to_move_map = json.loads(json_line)
                    print(
                        f"Parsed generated config files map from setup.py output: {generated_config_files_to_move_map}")
                except json.JSONDecodeError as json_err:  # noinspection PyBroadException
                    print(
                        f"Warning: Failed to decode JSON from setup.py output: {json_err}. Output snippet: {json_line[:100]}...")
            else:
                print("Warning: No JSON map found in setup.py output for config files to move.")

        else:  # This else is for if success_setup is False
            print(f"Failed to execute src/setup.py inside Docker container: {stderr_setup}")
            ssh_client.close()
            sys.exit(1)
    except Exception as e:
        print(f"An error occurred during setup tool execution: {e}")
        ssh_client.close()
        sys.exit(1)

    # NEW: Move generated config files from remote docker/generated_configs/ to their FHS paths on Pi
    print("\n--- Moving generated config files to FHS paths on Raspberry Pi ---")

    if generated_config_files_to_move_map:
        for temp_container_path_src, final_fhs_path_dest in generated_config_files_to_move_map.items():
            if 'dashy/config/conf.yml' in final_fhs_path_dest:
                print("Skipping move for Dashy's conf.yml to preserve live changes made by updater utilities.")
                continue

            remote_temp_file_on_host_path_src = os.path.join(remote_project_path,
                                                             temp_container_path_src[len('/app/'):]).replace('\\', '/')

            final_fhs_dir_dest = os.path.dirname(final_fhs_path_dest)
            # noinspection PyBroadException
            try:
                success_mkdir_fhs, _, stderr_mkdir_fhs = run_remote_command(ssh_client,
                                                                            f"sudo mkdir -p {final_fhs_dir_dest}")
                if not success_mkdir_fhs:
                    print(
                        f"Error: Failed to create final FHS config directory {final_fhs_dir_dest}: {stderr_mkdir_fhs}. Skipping move for {os.path.basename(final_fhs_path_dest)}.")
                    continue
            except Exception as e:
                print(
                    f"Error creating final FHS config directory {final_fhs_dir_dest}: {e}. Skipping move for {os.path.basename(final_fhs_path_dest)}.")
                continue

            # noinspection PyBroadException
            try:
                run_remote_command(ssh_client, f"sudo mv {remote_temp_file_on_host_path_src} {final_fhs_path_dest}")
                print(f"Moved config file: {os.path.basename(final_fhs_path_dest)} to {final_fhs_path_dest}")
            except Exception as e:
                print(f"Error moving config file {os.path.basename(final_fhs_path_dest)} to {final_fhs_path_dest}: {e}")
    else:
        print("No specific config files generated by setup.py that need moving.")


    print("\n--- PiSelfhosting Deployment Process Complete ---")
    print("Your PiSelfhosting services configuration has been generated on your Raspberry Pi.")

    # --- Choice menu for next action ---
    while True:
        print("\nWhat would you like to do next?")
        print("1. Start all selected services (docker compose up -d)")
        print("2. Stop and remove all selected services (docker compose down)")
        print("3. Exit without further action")
        choice = input("Enter your choice (1, 2, or 3): ").strip()

        if choice == '1':
            print("\n--- Executing 'docker compose up -d' on Raspberry Pi ---")
            print("Ensuring Docker network 'piselfhosting_net' exists...")
            # noinspection PyBroadException
            try:
                run_remote_command(ssh_client, 'docker network create piselfhosting_net || true')
                print("Docker network 'piselfhosting_net' ensured to exist.")
            except Exception as e:
                print(f"Failed to ensure Docker network exists: {e}")
                break

            print(
                "Attempting to start services with: docker compose -f /home/hvhoek/PiSelfhosting/docker/docker-compose.yml up -d")
            # noinspection PyBroadException
            try:
                run_remote_command(ssh_client,
                                   f'docker compose -f {remote_project_path}/docker/{UNIFIED_DOCKER_COMPOSE_FILENAME} up -d')
                print("Docker Compose 'up -d' command executed successfully.")
            except Exception as e:
                print(f"Docker Compose 'up -d' command failed. Error: {e}")
            break
        elif choice == '2':
            print("\n--- Executing 'docker compose down' on Raspberry Pi ---")
            # noinspection PyBroadException
            try:
                run_remote_command(ssh_client,
                                   f'docker compose -f {remote_project_path}/docker/{UNIFIED_DOCKER_COMPOSE_FILENAME} down')
                print("Docker Compose 'down' command executed successfully.")
            except Exception as e:
                print(f"Docker Compose 'down' command failed. Error: {e}")
            break
        elif choice == '3':
            print("Exiting without further action.")
            break
        else:
            print("Invalid choice. Please enter 1, 2, or 3.")

    ssh_client.close()
    print("SSH connection closed.")


if __name__ == "__main__":
    main()