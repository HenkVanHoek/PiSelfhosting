# piselfhosting_installer.py
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

# --- Constants and Configuration ---

# Attempt to import constants from the 'src' directory.
# This ensures the script works when run from the project root.
try:
    from src.setup import DOCKER_COMPOSE_OUTPUT_DIR, UNIFIED_DOCKER_COMPOSE_FILENAME, GLOBAL_DATA_ROOT
except ImportError:
    print("Error: Could not import from 'src.setup'. Make sure you are running this script from the project root.")
    print("And that 'src/__init__.py' and 'src/setup.py' exist.")
    sys.exit(1)

# Items to exclude from synchronization to the Raspberry Pi.
# Paths are relative to the project root. Directories should end with a '/'.
EXCLUDED_ITEMS = [
    '.git/',
    '.idea/',
    'venv/',
    '__pycache__/',
    '.pytest_cache/',
    'tests/',
    'README.md',
    # Exclude the local .env file used by the installer itself.
    '.env',
    # Exclude old or generated files that shouldn't be synced.
    'docker-compose.yml',
    'requirements.txt'
]

# --- Load Environment for Installer ---

# Load environment variables from a local .env file for installer convenience.
load_dotenv()

# --- Default Configuration Values ---

# SSH Defaults
DEFAULT_PI_IP = os.getenv('PI_IP', 'raspberrypi.local')
DEFAULT_SSH_USERNAME = os.getenv('SSH_USERNAME', 'pi')
DEFAULT_SSH_PASSWORD = os.getenv('SSH_PASSWORD', '')

# Service Configuration Defaults
DEFAULT_DOMAIN = os.getenv('DOMAIN', 'yourdomain.com')
DEFAULT_PUID = os.getenv('PUID', '1000')
DEFAULT_PGID = os.getenv('PGID', '1000')
DEFAULT_HOST_IP = os.getenv('HOST_IP', '')  # Let's try to auto-detect this first.
DEFAULT_DB_USER = os.getenv('DB_USER', 'piselfhosting_user')
DEFAULT_DB_PASS = os.getenv('DB_PASS', 'change_this_secure_password')
DEFAULT_TZ = os.getenv('TZ', 'Europe/Amsterdam')
DEFAULT_ADMIN_EMAIL = os.getenv('ADMIN_EMAIL', 'admin@yourdomain.com')
DEFAULT_FRIGATE_RTSP_PASSWORD = os.getenv('FRIGATE_RTSP_PASSWORD', 'change_this_frigate_password')
DEFAULT_PHPMYADMIN_BLOWFISH_SECRET = os.getenv('PHPMYADMIN_BLOWFISH_SECRET', '')
DEFAULT_PMA_HOST = os.getenv('PMA_HOST', 'mariadb')

# Installer Behavior Flag
DEFAULT_REUSE_VARIABLES_FLAG = os.getenv('PISELFHOSTING_REUSE_VARIABLES', 'false').lower()
ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')


# --- Helper Functions ---

def get_user_input(prompt, default_value, use_previous=False, stored_value=None):
    """Asks for user input with a default, reusing stored value if specified."""
    if use_previous and stored_value:
        print(f"- {prompt} (using previous: {stored_value})")
        return stored_value

    user_input = input(f"- {prompt} (default: {default_value}): ").strip()
    return user_input or default_value


def get_password(prompt, use_previous=False, stored_value=None):
    """Safely asks for a password, reusing stored value if specified."""
    if use_previous and stored_value:
        print(f"- {prompt} (using previous: {'*' * 10})")
        return stored_value

    pwd = getpass.getpass(f"- {prompt}: ")
    return pwd or stored_value


def get_local_ip_address():
    """Attempts to determine the local IP address of the machine running the script."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return None


# --- Remote Execution and File Sync ---

def run_remote_command(ssh_client, command, check_exit_status=True):
    """
    Executes a command on the remote host with a loading spinner.

    Returns a tuple (success, stdout, stderr).
    Raises an exception on failure if check_exit_status is True.
    """
    print(f"\n> Executing on Pi: '{command}'")

    done_event = threading.Event()
    result = {}

    def _execute():
        try:
            stdin, stdout, stderr = ssh_client.exec_command(command)
            result['stdout'] = stdout.read().decode('utf-8', errors='ignore').strip()
            result['stderr'] = stderr.read().decode('utf-8', errors='ignore').strip()
            result['exit_status'] = stdout.channel.recv_exit_status()
        except Exception as e:
            result['stderr'] = f"SSH execution error: {e}"
            result['exit_status'] = -1
        finally:
            done_event.set()

    thread = threading.Thread(target=_execute)
    thread.start()

    spinner = ['-', '\\', '|', '/']
    idx = 0
    while not done_event.is_set():
        print(f"\rWorking... {spinner[idx % len(spinner)]}", end="")
        idx += 1
        time.sleep(0.1)

    thread.join()
    print("\rWorking... Done.      ")

    exit_status = result.get('exit_status', -1)
    stdout_output = result.get('stdout', '')
    stderr_output = result.get('stderr', '')

    if exit_status != 0:
        print(f"  Error: Command failed with exit status {exit_status}.")
        if stdout_output: print(f"  STDOUT:\n{stdout_output}")
        if stderr_output: print(f"  STDERR:\n{stderr_output}")
        if check_exit_status:
            raise Exception(f"Remote command failed: {command}")
        return False, stdout_output, stderr_output

    if stdout_output:
        print(stdout_output)
    return True, stdout_output, stderr_output


def _is_excluded(local_path, project_root, exclude_list):
    """Checks if a file or directory should be excluded from synchronization."""
    relative_path = os.path.relpath(local_path, project_root).replace(os.sep, '/')
    if relative_path == ".":
        return False

    for pattern in exclude_list:
        norm_pattern = pattern.replace(os.sep, '/')
        if norm_pattern.endswith('/'):  # Directory pattern
            if relative_path.startswith(norm_pattern.rstrip('/')):
                return True
        else:  # File pattern
            if relative_path == norm_pattern:
                return True
            if '/' not in norm_pattern and os.path.basename(relative_path) == norm_pattern:
                return True
    return False


def sync_files_to_pi(ssh_client, local_project_root, remote_project_root):
    """Synchronizes the project directory to the Raspberry Pi via SFTP."""
    print(f"\n--- Synchronizing project files to {remote_project_root} ---")

    try:
        run_remote_command(ssh_client, f"sudo rm -rf {remote_project_root} && mkdir -p {remote_project_root}")
    except Exception as e:
        print(f"Error: Could not clean remote directory. Aborting. {e}")
        sys.exit(1)

    sftp = ssh_client.open_sftp()

    for root, dirs, files in os.walk(local_project_root, topdown=True):
        # Filter directories and files using the exclusion list
        dirs[:] = [d for d in dirs if not _is_excluded(os.path.join(root, d), local_project_root, EXCLUDED_ITEMS)]
        files[:] = [f for f in files if not _is_excluded(os.path.join(root, f), local_project_root, EXCLUDED_ITEMS)]

        remote_root = os.path.join(remote_project_root, os.path.relpath(root, local_project_root)).replace(os.sep, '/')

        for dirname in dirs:
            remote_dir_path = os.path.join(remote_root, dirname).replace(os.sep, '/')
            print(f"  Creating directory: {remote_dir_path}")
            try:
                sftp.mkdir(remote_dir_path)
            except paramiko.SFTPError as e:
                if e.errno != 4:  # Allow "failure" which means it already exists
                    raise

        for filename in files:
            local_file_path = os.path.join(root, filename)
            remote_file_path = os.path.join(remote_root, filename).replace(os.sep, '/')
            print(f"  Uploading file: {remote_file_path}")
            sftp.put(local_file_path, remote_file_path)

    sftp.close()
    print("--- File synchronization complete. ---")


# --- Main Orchestration Function ---

def main():
    """Main function to drive the installer."""
    print("--- PiSelfhosting Installer ---")

    # 1. Gather SSH Credentials
    print("\n--- Step 1: SSH Connection ---")
    pi_hostname = get_user_input("Enter Pi hostname or IP", DEFAULT_PI_IP)
    ssh_username = get_user_input("Enter SSH username", DEFAULT_SSH_USERNAME)
    ssh_password = get_password("Enter SSH password")

    # 2. Establish SSH Connection
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(hostname=pi_hostname, username=ssh_username, password=ssh_password, port=22, timeout=10)
        print("Successfully connected to Raspberry Pi.")
    except Exception as e:
        print(f"Fatal: Could not establish SSH connection: {e}")
        sys.exit(1)

    # 3. Prerequisite Checks on the Pi
    print("\n--- Step 2: System Pre-flight Checks ---")
    try:
        # Check for Docker
        _, _, _ = run_remote_command(ssh, "which docker")
        _, status, _ = run_remote_command(ssh, "sudo systemctl is-active docker", check_exit_status=False)
        if status != 'active':
            print("Error: Docker is not installed or not running on the Pi.")
            ssh.close()
            sys.exit(1)

        # Check if user is in the docker group
        _, groups, _ = run_remote_command(ssh, f"groups {ssh_username}")
        if 'docker' not in groups:
            print(f"User '{ssh_username}' is not in the 'docker' group. Adding now...")
            run_remote_command(ssh, f"sudo usermod -aG docker {ssh_username}")
            print("User added. A reboot or new login session on the Pi might be required.")
        print("Docker checks passed.")
    except Exception as e:
        print(f"Fatal: Prerequisite check failed: {e}")
        ssh.close()
        sys.exit(1)

    # 4. Gather Configuration Variables
    print("\n--- Step 3: Configure Your Services ---")
    # Determine remote project path
    _, home_dir, _ = run_remote_command(ssh, 'echo $HOME')
    remote_project_path = os.path.join(home_dir, "piselfhosting").replace("\\", "/")

    # Gather other variables
    domain = get_user_input("Enter your primary domain name", DEFAULT_DOMAIN)
    puid = get_user_input("Enter PUID for user permissions", DEFAULT_PUID)
    pgid = get_user_input("Enter PGID for group permissions", DEFAULT_PGID)
    tz = get_user_input("Enter timezone", DEFAULT_TZ)
    admin_email = get_user_input("Enter admin email for SSL certs", DEFAULT_ADMIN_EMAIL)

    # Auto-detect IP if possible, else ask
    detected_ip = get_local_ip_address()
    host_ip_prompt = "Enter the Pi's local IP address"
    host_ip = get_user_input(host_ip_prompt, detected_ip or DEFAULT_HOST_IP)

    db_user = get_user_input("Enter database username", DEFAULT_DB_USER)
    db_pass = get_password("Enter database password", stored_value=DEFAULT_DB_PASS)
    frigate_pass = get_password("Enter Frigate RTSP password", stored_value=DEFAULT_FRIGATE_RTSP_PASSWORD)

    blowfish = DEFAULT_PHPMYADMIN_BLOWFISH_SECRET or os.urandom(32).hex()

    # 5. Synchronize Project Files
    local_project_path = os.path.dirname(os.path.abspath(__file__))
    sync_files_to_pi(ssh, local_project_path, remote_project_path)

    # 6. Prepare and Run Setup on the Pi
    print("\n--- Step 4: Generating Configuration on the Pi ---")

    # Collect all variables for the setup script
    env_vars_for_setup = {
        "DOMAIN": domain, "PUID": puid, "PGID": pgid, "HOST_IP": host_ip,
        "DB_USER": db_user, "DB_PASS": db_pass, "TZ": tz, "ADMIN_EMAIL": admin_email,
        "REMOTE_PROJECT_PATH": remote_project_path,
        "FRIGATE_RTSP_PASSWORD": frigate_pass,
        "PHPMYADMIN_BLOWFISH_SECRET": blowfish,
        "PMA_HOST": DEFAULT_PMA_HOST
    }

    # Create the remote .env file for Docker Compose
    remote_docker_env_path = os.path.join(remote_project_path, DOCKER_COMPOSE_OUTPUT_DIR, ".env").replace(os.sep, '/')
    env_file_content = "\\n".join([f"{k}={v}" for k, v in env_vars_for_setup.items()])
    run_remote_command(ssh, f"mkdir -p {os.path.dirname(remote_docker_env_path)}")
    run_remote_command(ssh, f"echo -e \"{env_file_content}\" > {remote_docker_env_path}")
    print("Remote '.env' file for Docker Compose created successfully.")

    # Build the setup tool Docker image
    docker_build_cmd = (
        f"docker build -t piselfhosting-setup-tool "
        f"-f {remote_project_path}/Dockerfile.setup-tool {remote_project_path}"
    )
    run_remote_command(ssh, docker_build_cmd)

    # Run the setup tool container
    docker_run_cmd = (
        f"docker run --rm -v {remote_project_path}:/app "
        f"--env-file {remote_docker_env_path} "
        f"piselfhosting-setup-tool python /app/src/setup.py"
    )
    _, setup_stdout, _ = run_remote_command(ssh, docker_run_cmd)

    # 7. Move Generated Configs
    print("\n--- Step 5: Finalizing Configuration ---")
    generated_configs_map = {}
    for line in reversed(setup_stdout.splitlines()):
        if line.strip().startswith('{') and line.strip().endswith('}'):
            try:
                generated_configs_map = json.loads(line.strip())
                print(f"Parsed config map from setup script: {generated_configs_map}")
                break
            except json.JSONDecodeError:
                print("Warning: Could not parse JSON map from setup script output.")

    if generated_configs_map:
        for temp_path, final_path in generated_configs_map.items():
            final_dir = os.path.dirname(final_path)
            # temp_path is from container's perspective (/app/...), convert to host path
            host_temp_path = os.path.join(remote_project_path, temp_path[len('/app/'):]).replace(os.sep, '/')

            run_remote_command(ssh, f"sudo mkdir -p {final_dir}")
            run_remote_command(ssh, f"sudo mv {host_temp_path} {final_path}")
            print(f"Moved '{os.path.basename(final_path)}' to its final destination.")
    else:
        print("No configuration files to move.")

    # 8. Final Action Menu
    print("\n--- Installation Complete! ---")
    while True:
        print("\nWhat would you like to do next?")
        print("  1. Start all services (docker compose up)")
        print("  2. Stop all services (docker compose down)")
        print("  3. Exit")
        choice = input("Enter your choice [1, 2, 3]: ").strip()

        compose_file_path = os.path.join(remote_project_path, DOCKER_COMPOSE_OUTPUT_DIR,
                                         UNIFIED_DOCKER_COMPOSE_FILENAME).replace(os.sep, '/')

        if choice == '1':
            run_remote_command(ssh, "docker network create piselfhosting_net || true")
            run_remote_command(ssh, f"docker compose -f {compose_file_path} up -d")
            print("All services are starting.")
            break
        elif choice == '2':
            run_remote_command(ssh, f"docker compose -f {compose_file_path} down")
            print("All services have been stopped.")
            break
        elif choice == '3':
            break
        else:
            print("Invalid choice. Please try again.")

    ssh.close()
    print("\nConnection closed. Goodbye!")


if __name__ == "__main__":
    main()