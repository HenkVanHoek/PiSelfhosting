# app.py
import json
import os
import subprocess
import sys
import webbrowser
from threading import Timer
from flask import Flask, render_template, request, redirect, url_for

# Assume component_manager.py is in the same directory or a reachable path
from component_manager import ComponentManager

# --- Configuration ---
METADATA_FILE = os.path.join('config', 'components_metadata.json')
SELECTED_COMPONENTS_OUTPUT_FILE = 'selected_components.txt'
EXECUTOR_SCRIPT = 'piselfhosting_installer.py' # The main installer script

# --- Flask App Initialization ---
app = Flask(__name__)
# Load the metadata using the manager you created
manager = ComponentManager(METADATA_FILE)

@app.route('/', methods=['GET'])
def index():
    """
    Main page that displays all available components in a checklist.
    """
    all_components = manager.get_all_components()
    # Filter out the internal _piselfhosting key before sending to template
    components_to_display = {k: v for k, v in all_components.items() if not k.startswith('_')}
    return render_template('index.html', components=components_to_display)

@app.route('/install', methods=['POST'])
def install():
    """
    Handles the form submission, generates selected_components.txt,
    and launches the main installer script in a new terminal.
    """
    # Get the list of selected component IDs from the form's checkboxes
    selected_ids = request.form.getlist('components')

    # Write the selected components to the output file, separated by spaces
    with open(SELECTED_COMPONENTS_OUTPUT_FILE, 'w') as f:
        f.write(' '.join(selected_ids))

    print(f"'{SELECTED_COMPONENTS_OUTPUT_FILE}' generated with the following components: {selected_ids}")
    print("Launching the installer in a new terminal window...")

    # --- Launch the Executor script in a new terminal ---
    # This logic detects the OS and uses the appropriate command.
    command = []
    if sys.platform == "win32":
        # For Windows
        command = ['cmd.exe', '/c', 'start', 'python', EXECUTOR_SCRIPT]
    elif sys.platform == "darwin":
        # For macOS
        command = ['open', '-a', 'Terminal', f'python3 "{os.path.abspath(EXECUTOR_SCRIPT)}"']
    else:
        # For Linux (assumes gnome-terminal, user might need to change)
        # xterm is a more universal fallback
        try:
            command = ['xterm', '-e', f'python3 "{os.path.abspath(EXECUTOR_SCRIPT)}"; read -p "Press Enter to close terminal..."']
        except FileNotFoundError:
            print("Warning: xterm not found. Please run the installer manually.")
            print(f"python3 {EXECUTOR_SCRIPT}")


    if command:
        subprocess.Popen(command)

    return "<h2>Configuration saved!</h2><p>The installer has been launched in a new terminal window. You can now close this browser tab.</p>"

def open_browser():
    """Opens the default web browser to the Flask app's URL."""
    webbrowser.open_new("http://127.0.0.1:5000/")

if __name__ == '__main__':
    # Open the browser automatically after a short delay
    Timer(1, open_browser).start()
    # Run the Flask app
    app.run(host='127.0.0.1', port=5000, debug=False)