# piselfhosting_installer.py
import paramiko
import os
import sys
import getpass
import time

# --- Configuration ---
DEFAULT_PI_USER = "pi"
DEFAULT_PI_PORT = 22
# REMOTE_PROJECT_BASE_PATH = "/home/pi/PiSelfhosting" # This a dynamic variable from now on.
LOCAL_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))  # Assumes installer.py is in project root


# --- Helper Functions ---

def get_user_input(prompt, default_value=None, sensitive=False):
    """
    Prompts the user for input.
    If sensitive is True, uses getpass for secure password input.
    """
    if sensitive:
        return getpass.getpass(prompt).strip()
    else:
        if default_value:
            return input(f"{prompt} (default: {default_value}): ").strip() or default_value
        return input(f"{prompt}: ").strip()


def setup_ssh_client(hostname, username, password, port=DEFAULT_PI_PORT):
    """
    Sets up and returns a configured Paramiko SSH client.
    """
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    print(f"Attempting to connect to {username}@{hostname}:{port}...")
    try:
        client.connect(hostname=hostname, port=port, username=username, password=password, timeout=10)
        print("Successfully connected to Raspberry Pi via SSH.")
        return client
    except paramiko.AuthenticationException:
        print("Authentication failed. Please check your username and password.")
        return None
    except paramiko.SSHException as e:
        print(f"SSH connection error: {e}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred during SSH connection: {e}")
        return None


def execute_remote_command(ssh_client, command):
    """
    Executes a command on the remote Pi and returns stdout, stderr, and exit code.
    """
    print(f"\nExecuting remote command: '{command}'")

    stdin, stdout, stderr = ssh_client.exec_command(command, get_pty=True)

    stdout_lines = stdout.readlines()
    stderr_lines = stderr.readlines()

    exit_status = stdout.channel.recv_exit_status()

    stdout_output = "".join(stdout_lines).strip()
    stderr_output = "".join(stderr_lines).strip()

    if exit_status != 0:
        print(f"Command failed with exit code {exit_status}.")
        if stdout_output:
            print(f"STDOUT:\n{stdout_output}")
        if stderr_output:
            print(f"STDERR:\n{stderr_output}")
    else:
        if stdout_output:
            print(f"STDOUT:\n{stdout_output}")
        if stderr_output:
            print(f"STDERR (Warning/Info):\n{stderr_output}")
        print("Command executed successfully.")

    return exit_status, stdout_output, stderr_output


def check_and_install_docker(ssh_client, username):
    """
    Checks if Docker is installed on the remote Pi. If not, installs it.
    Also ensures the user is in the 'docker' group.
    """
    print("\n--- Checking Docker Installation ---")

    exit_code, stdout, stderr = execute_remote_command(ssh_client, "which docker")
    if exit_code == 0 and "docker" in stdout:
        print("Docker command found. Checking Docker service status...")
        exit_code, stdout, stderr = execute_remote_command(ssh_client, "sudo systemctl is-active docker")
        if exit_code == 0 and "active" in stdout:
            print("Docker is installed and running.")
        else:
            print("Docker command found, but service is not active. Attempting to start Docker service...")
            exit_code, stdout, stderr = execute_remote_command(ssh_client, "sudo systemctl start docker")
            if exit_code == 0:
                print("Docker service started successfully.")
            else:
                print("Failed to start Docker service. Please check manually.")
                return False

    else:
        print("Docker not found. Initiating Docker installation...")
        install_cmd = "curl -fsSL https://get.docker.com -o get-docker.sh && sudo sh get-docker.sh"
        exit_code, stdout, stderr = execute_remote_command(ssh_client, install_cmd)

        if exit_code != 0:
            print("Docker installation failed. Please check the output above for errors.")
            return False
        print("Docker installed successfully.")

        execute_remote_command(ssh_client, "rm get-docker.sh")

    print("\n--- Checking and Adding User to Docker Group ---")
    exit_code, stdout, stderr = execute_remote_command(ssh_client, f"groups {username}")
    if "docker" not in stdout:
        print(f"User '{username}' is not in the 'docker' group. Adding now...")
        add_group_cmd = f"sudo usermod -aG docker {username}"
        exit_code, stdout, stderr = execute_remote_command(ssh_client, add_group_cmd)
        if exit_code == 0:
            print(
                f"User '{username}' added to 'docker' group. A reboot or re-login is required for changes to take effect.")
            print("It is highly recommended to reboot the Raspberry Pi now for Docker permissions to apply.")
            reboot_choice = get_user_input("Reboot Raspberry Pi now? (y/N)", default_value="N").lower()
            if reboot_choice == 'y':
                print("Rebooting Raspberry Pi...")
                execute_remote_command(ssh_client, "sudo reboot")
                print("Waiting for Pi to reboot (approx. 60 seconds)...")
                time.sleep(60)
                return False
            else:
                print("Please remember to reboot your Raspberry Pi manually before proceeding with Docker commands.")
                return False
        else:
            print(f"Failed to add user '{username}' to 'docker' group.")
            return False
    else:
        print(f"User '{username}' is already in the 'docker' group.")

    print("Docker setup complete.")
    return True


def upload_project_files(ssh_client, local_path, remote_base_path):
    """
    Uploads files/directories recursively from local_path to remote_base_path on the Pi.
    """
    sftp_client = ssh_client.open_sftp()

    # List of items to exclude from upload (relative to local_path)
    # Common exclusions: virtual environments, git metadata, PyCharm project files, pytest cache.
    exclude_list = [
        '.git',
        '.idea',
        'venv',  # <-- EXCLUDE VIRTUAL ENVIRONMENT
        '__pycache__',
        '.pytest_cache',
        'scripts',
        'docker',
        '.DS_Store' # macOS specific
    ]

    # Ensure the remote base path exists (use remote_base_path directly)
    try:
        # This will create /home/<user>/PiSelfhosting if it doesn't exist
        exit_code, stdout, stderr = execute_remote_command(ssh_client, f"mkdir -p {remote_base_path}")
        if exit_code != 0:
            print(f"Error creating remote base directory {remote_base_path}: {stderr}")
            sftp_client.close()
            return False
    except Exception as e:
        print(f"Unexpected error creating remote base directory {remote_base_path}: {e}")
        sftp_client.close()
        return False

    print(f"\n--- Uploading files from {local_path} to {remote_base_path} ---")

    try:
        for item in os.listdir(local_path):
            if item in exclude_list:  # <-- CHECK EXCLUDE LIST
                print(f"Skipping excluded item: {item}/")
                continue

            local_item_path = os.path.join(local_path, item)

            # For non-excluded items, handle as before
            if os.path.isfile(local_item_path):
                remote_file_path = os.path.join(remote_base_path, item).replace('\\', '/')
                print(f"Uploading file: {item}")
                sftp_client.put(local_item_path, remote_file_path)
            elif os.path.isdir(local_item_path):
                print(f"Uploading directory: {item}/")
                # Need to walk recursively, but check sub-items against exclude list too if desired
                # For simplicity, we apply exclude at the top-level of os.walk.
                # If a directory is excluded, its contents are not walked.

                # Construct remote_current_dir relative to remote_base_path
                remote_dir_base = os.path.join(remote_base_path, item).replace('\\', '/')
                execute_remote_command(ssh_client,
                                       f"mkdir -p {remote_dir_base}")  # Create the top-level excluded folder if it has content (e.g., .git/config)

                for root, dirs, files in os.walk(local_item_path):
                    # Filter out excluded subdirectories before descending into them
                    dirs[:] = [d for d in dirs if d not in exclude_list]  # Modify dirs in-place for os.walk

                    remote_current_dir = os.path.join(remote_base_path, os.path.relpath(root, local_path)).replace('\\',
                                                                                                                   '/')
                    execute_remote_command(ssh_client,
                                           f"mkdir -p {remote_current_dir}")  # Ensure current subdirectory exists

                    for file_name in files:
                        # Check if parent directory is excluded. If we are here, it's not a top-level excluded item.
                        # We also check if the file itself needs to be excluded if specific files are in exclude_list
                        if file_name in exclude_list:  # For specific file exclusions
                            print(
                                f"Skipping excluded file: {os.path.relpath(os.path.join(root, file_name), local_path)}")
                            continue

                        local_file_path = os.path.join(root, file_name)
                        remote_file_path = os.path.join(remote_current_dir, file_name).replace('\\', '/')

                        print(f"  Uploading: {os.path.relpath(local_file_path, local_path)}")
                        sftp_client.put(local_file_path, remote_file_path)
            else:
                print(f"Skipping unsupported item type: {item}")

        print("File upload complete.")
        return True
    except FileNotFoundError as e:
        print(f"Error: Local file or directory not found: {e}")
        return False
    except paramiko.SSHException as e:
        print(f"SSH/SFTP error during file upload: {e}")
        return False
    except Exception as e:
        print(f"An unexpected error occurred during file upload: {e}")
        return False
    finally:
        sftp_client.close()


def build_and_run_setup_tool_container(ssh_client, remote_project_path):
    """
    Builds the piselfhosting-setup-tool Docker image on the remote Pi
    and then runs src/setup.py inside a container using that image.
    """
    SETUP_TOOL_IMAGE_NAME = "piselfhosting-setup-tool"
    DOCKERFILE_NAME = "Dockerfile.setup-tool"

    remote_dockerfile_path = os.path.join(remote_project_path, DOCKERFILE_NAME).replace('\\', '/')
    remote_src_path_in_container = "/app"  # Path where project root is mounted inside container

    print(f"\n--- Building Docker image for setup tool ({SETUP_TOOL_IMAGE_NAME}) ---")
    # Build the Docker image. The context for the build is the remote_project_path.
    # --no-cache is good for development to ensure latest changes are picked up.
    # -f specifies the Dockerfile name within the build context.
    build_cmd = f"docker build -t {SETUP_TOOL_IMAGE_NAME} -f {remote_dockerfile_path} {remote_project_path}"
    exit_code, stdout, stderr = execute_remote_command(ssh_client, build_cmd)

    if exit_code != 0:
        print(f"Failed to build Docker image '{SETUP_TOOL_IMAGE_NAME}'.")
        return False
    print(f"Docker image '{SETUP_TOOL_IMAGE_NAME}' built successfully.")

    print(f"\n--- Running src/setup.py inside Docker container ---")
    # Run the setup tool container.
    # --rm: Automatically remove the container when it exits.
    # -v {remote_project_path}:{remote_src_path_in_container}: Mount the entire project folder from the Pi host into the container.
    # This allows src/setup.py inside the container to access all templates, configs etc.
    # python {remote_src_path_in_container}/src/setup.py: Command to execute inside the container.
    run_setup_cmd = f"docker run --rm -v {remote_project_path}:{remote_src_path_in_container} {SETUP_TOOL_IMAGE_NAME} python {remote_src_path_in_container}/src/setup.py"

    # Execute the command. The output of src/setup.py will be streamed here.
    # This will trigger interactive selection, compose generation, etc.
    exit_code, stdout, stderr = execute_remote_command(ssh_client, run_setup_cmd)

    if exit_code != 0:
        print(f"Execution of src/setup.py in container failed with exit code {exit_code}.")
        return False
    print("src/setup.py executed successfully inside the Docker container.")

    return True


def main():
    print("--- PiSelfhosting Installer & Orchestrator ---")
    print("This script helps you manage your PiSelfhosting project on your Raspberry Pi.")

    pi_hostname = get_user_input("Enter Raspberry Pi IP address or hostname", default_value="raspberrypi.local")
    pi_username = get_user_input("Enter Raspberry Pi SSH username", default_value=DEFAULT_PI_USER)
    pi_password = get_user_input(f"Enter password for {pi_username}@{pi_hostname}", sensitive=True)

    ssh_client = None
    try:
        ssh_client = setup_ssh_client(pi_hostname, pi_username, pi_password)
        if ssh_client is None:
            print("Failed to establish SSH connection. Exiting.")
            sys.exit(1)

        # --- Dynamically determine remote project path ---
        print("\n--- Determining remote project path ---")
        exit_code, home_dir_output, stderr_output = execute_remote_command(ssh_client, "echo $HOME")

        dynamic_remote_project_path = ""
        if exit_code == 0 and home_dir_output:
            remote_user_home_dir = home_dir_output.strip()
            dynamic_remote_project_path = os.path.join(remote_user_home_dir, "PiSelfhosting").replace('\\', '/')
            print(f"Determined remote home directory: {remote_user_home_dir}")
            print(f"Project will be installed/synced in: {dynamic_remote_project_path}")
        else:
            print("Could not determine remote home directory. Defaulting to /home/pi/PiSelfhosting.")
            dynamic_remote_project_path = "/home/pi/PiSelfhosting"
            print(f"Project will be installed/synced in: {dynamic_remote_project_path}")

        # --- Test basic remote command execution ---
        print("\n--- Testing basic remote command execution ---")
        exit_code, stdout, stderr = execute_remote_command(ssh_client, "uname -a")
        if exit_code == 0:
            print("Basic command 'uname -a' succeeded.")
        else:
            print("Basic command 'uname -a' failed. Please check connection and permissions.")

        # --- Check and Install Docker ---
        docker_ready = check_and_install_docker(ssh_client, pi_username)
        if not docker_ready:
            print("Docker is not ready. Please resolve issues or reboot the Pi if prompted, then re-run the installer.")
            sys.exit(1)

        # --- Upload Project Files ---
        print("\n--- Starting project file synchronization ---")
        if not upload_project_files(ssh_client, LOCAL_PROJECT_ROOT, dynamic_remote_project_path):
            print("Failed to upload project files. Exiting.")
            sys.exit(1)

        # --- Build and Run Setup Tool Container ---
        print("\n--- Starting setup tool execution via Docker container ---")
        if not build_and_run_setup_tool_container(ssh_client, dynamic_remote_project_path):
            print("Setup tool execution failed. Exiting.")
            sys.exit(1)

        print("\n--- PiSelfhosting Deployment Process Complete ---")
        print("Your PiSelfhosting services should now be configured and deployed on your Raspberry Pi.")
        print("Remember to check the web interfaces of your services!")

    finally:  # Re-enabled the finally block to ensure SSH connection is closed.
        if ssh_client:
            ssh_client.close()
            print("\nSSH connection closed.")


if __name__ == "__main__":
    main()