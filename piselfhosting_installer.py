import os
import sys

# NEW: Import the standard library for parsing TOML files
import tomllib

from dotenv import load_dotenv


def get_project_root():
    """
    Returns the correct root path whether running from source or as a
    PyInstaller bundle. In a bundle, this points to the temporary directory
    where all assets are unpacked.
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        # Running in a PyInstaller bundle (frozen).
        # noinspection PyProtectedMember
        return sys._MEIPASS
    else:
        # Running in a normal Python environment (from source)
        # This is complex to get the project root, not the file location in src
        return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


# NEW: A function to read the version from pyproject.toml
def get_project_version(project_root):
    """
    Reads the project version from the pyproject.toml file.
    """
    try:
        pyproject_path = os.path.join(project_root, "pyproject.toml")
        with open(pyproject_path, "rb") as f:
            data = tomllib.load(f)
            return data["project"]["version"]
    except (FileNotFoundError, KeyError):
        # Fallback if the file is missing or the version key is not found
        return "latest"


def run_installation():
    """
    A generator function that runs the Ansible playbook and yields its
    output line by line.
    """
    # --- Path and Module Setup ---
    project_root = get_project_root()
    src_path = os.path.join(project_root, "src")
    if src_path not in sys.path:
        sys.path.insert(0, src_path)

    import ansible_runner

    # The correct import path assumes piselfhosting_installer is outside src
    from managers.component_manager import ComponentManager

    # --- Environment and Configuration ---
    env_path = os.path.join(project_root, ".env")
    load_dotenv(dotenv_path=env_path)

    yield "--- PiSelfHosting Installer ---"
    yield "Starting the installation process..."

    # NEW: Get the project version
    project_version = get_project_version(project_root)
    yield f"Using Project Version: {project_version}"

    # --- Load Selected Components ---
    selected_components_file = os.path.join(project_root, "selected_components.txt")
    if not os.path.exists(selected_components_file):
        yield f"ERROR: Could not find '{selected_components_file}'."
        yield "Please make your selections in the web UI first."
        return

    with open(selected_components_file, "r") as f:
        selected_ids = f.read().strip().split()

    if not selected_ids:
        yield "ERROR: No components were selected for installation."
        return

    # --- Initialize Component Manager ---
    metadata_file = os.path.join(project_root, "config", "components_metadata.json")
    manager = ComponentManager(metadata_file)
    components_to_install = manager.get_components_by_id(selected_ids)

    yield f"Found {len(components_to_install)} components to install:"
    for comp in components_to_install:
        yield f"- {comp['name']} ({comp['id']})"
    yield "---------------------------------"

    # --- Prepare Ansible Runner ---
    pi_ip = os.getenv("PI_IP")
    ssh_user = os.getenv("SSH_USER")
    ssh_pass = os.getenv("SSH_PASSWORD")

    if not all([pi_ip, ssh_user]):
        yield "ERROR: Missing PI_IP or SSH_USER in the .env file."
        return

    extravars = {
        "selected_components": components_to_install,
        "ansible_user": ssh_user,
        # NEW: Add the project version so Ansible can use it in templates
        "project_version": project_version,
    }
    if ssh_pass:
        extravars["ansible_password"] = ssh_pass
        extravars["ansible_become_password"] = ssh_pass

    inventory = {"hosts": {pi_ip: None}}
    playbook_path = os.path.join(project_root, "ansible", "playbook.yml")

    yield "Preparing to run Ansible..."
    yield f"Target: {ssh_user}@{pi_ip}"
    yield "This process can take a long time. Please be patient."
    yield "---------------------------------"

    # --- Run Ansible and Stream Output ---
    try:
        runner_thread, runner = ansible_runner.run_async(
            private_data_dir=project_root,
            playbook=playbook_path,
            inventory=inventory,
            extravars=extravars,
            quiet=True,
        )

        for event in runner.events:
            if event["event"] == "runner_on_ok":
                if "stdout" in event["event_data"]["res"]:
                    for line in event["event_data"]["res"]["stdout_lines"]:
                        yield line
            elif event["event"] in ["runner_on_failed", "runner_on_unreachable"]:
                yield f"ERROR on task '{event['event_data']['task']}':"
                if "res" in event["event_data"] and "msg" in event["event_data"]["res"]:
                    yield event["event_data"]["res"]["msg"]
                else:
                    yield str(event)

        runner_thread.join()
        status = runner.status
        rc = runner.rc
        yield "---------------------------------"
        yield f"Ansible playbook finished with status: {status} (RC: {rc})"
        if rc != 0:
            yield "There were errors during the installation. Please review the log."
        else:
            yield "Installation completed successfully!"

    except Exception as e:
        yield f"FATAL: An unexpected error occurred while running Ansible: {e}"
