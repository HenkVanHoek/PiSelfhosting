import json
import os
import sys
import webbrowser
import logging
import subprocess
from collections import defaultdict
from logging.handlers import RotatingFileHandler
from threading import Timer
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, Response
from dotenv import set_key


def get_project_root():
    """
    Returns the correct root path whether running from source or as a
    PyInstaller bundle. In a bundle, this points to the temporary directory
    where all assets (like the 'config' folder) are unpacked.
    """
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        # Running in a PyInstaller bundle (frozen).
        # This is the correct, documented way to get the path.
        # noinspection PyProtectedMember
        return sys._MEIPASS
    else:
        # Running in a normal Python environment (from source)
        return os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))


# --- Path and Module Setup ---
# This ensures the app can find your other source files
project_root = get_project_root()
src_path = os.path.join(project_root, 'src')
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from component_manager import ComponentManager
from pi_scanner import PiScanner

# --- Professional, Rotating Logging Setup ---
log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(name)s - %(message)s')
log_handler = RotatingFileHandler(
    'configurator.log',
    maxBytes=1024 * 1024,  # 1 Megabyte
    backupCount=3,  # Keep up to 3 old log files
    encoding='utf-8'
)
log_handler.setFormatter(log_formatter)
log_handler.setLevel(logging.DEBUG)

# Get the root logger and add our handler.
root_logger = logging.getLogger()
root_logger.setLevel(logging.DEBUG)
if not root_logger.handlers:
    root_logger.addHandler(log_handler)


# noinspection PyShadowingNames
def create_app(test_config=None):
    """Application Factory Function"""
    app = Flask(__name__)
    # A secret key is required for session management
    app.secret_key = os.urandom(24)

    app.logger.info("Flask application starting up...")

    # --- Configuration ---
    app.config.from_mapping(
        METADATA_FILE=os.path.join(project_root, 'config', 'components_metadata.json'),
        DEFAULT_COMPONENTS_FILE=os.path.join(project_root, 'config', 'default_selected_components.txt'),
        SELECTED_COMPONENTS_OUTPUT_FILE=os.path.join(project_root, 'selected_components.txt'),
        DOCS_OUTPUT_FILE=os.path.join(project_root, 'SUPPORTED_COMPONENTS.md'),
        ENV_PATH=os.path.join(project_root, '.env')
    )
    if test_config:
        app.config.from_mapping(test_config)

    manager = ComponentManager(
        app.config['METADATA_FILE'],
        docs_output_path=app.config['DOCS_OUTPUT_FILE']
    )

    @app.route('/')
    def index():
        try:
            """
            Main page: shows the Pi discovery/selection page if no Pi is selected,
            otherwise shows the component selection page.
            """
            if 'target_pi_ip' in session:
                all_components = manager.get_all_components()
                uniqueness_groups = manager.get_uniqueness_groups()

                # --- Grouping Logic ---
                # Use a defaultdict to easily group components by their section.
                grouped_components = defaultdict(list)
                order = all_components.get('_piselfhosting', {}).get('components_order', [])

                # Iterate through the defined order to maintain consistency
                for component_id in order:
                    component_data = all_components.get(component_id)
                    if component_data:
                        # Use 'Uncategorized' as a fallback group
                        section_name = component_data.get('dashy_section', 'Uncategorized')
                        # Append the full component info, including its ID
                        grouped_components[section_name].append({
                            'id': component_id,
                            'data': component_data
                        })
                # --- End of Grouping Logic ---

                # --- Load Default Selections ---
                default_components = []
                try:
                    with open(app.config['DEFAULT_COMPONENTS_FILE'], 'r') as f:
                        # Read the file, strip whitespace, and split by spaces/newlines
                        default_components = f.read().strip().split()
                except FileNotFoundError:
                    app.logger.warning(
                        f"Default components file not found at {app.config['DEFAULT_COMPONENTS_FILE']}. "
                        f"No components will be pre-selected."
                    )
                # --- End of Default Selections ---

                return render_template('select_components.html',
                                       # Pass the new grouped data structure to the template
                                       grouped_components=grouped_components,
                                       pi_ip=session['target_pi_ip'],
                                       uniqueness_groups=json.dumps(uniqueness_groups),
                                       default_components=default_components)
            else:
                detected_subnet = PiScanner.detect_subnet()
                return render_template('select_pi.html', detected_subnet=detected_subnet)
        except Exception:
            # Log the full error if something goes wrong
            app.logger.error("An unhandled exception occurred in the index route!", exc_info=True)
            # You can still let Flask show the generic 500 error page to the user
            raise

    @app.route('/scan', methods=['POST'])
    def scan_network():
        """
        API endpoint to run PiScanner and return both successfully identified
        devices and devices that failed authentication.
        """
        data = request.json
        subnet = data.get('subnet')
        username = data.get('username')
        password = data.get('password')  # Can be None for key-based auth

        if not all([subnet, username]):
            return jsonify({'error': 'Subnet and username are required.'}), 400

        potential_pis = PiScanner.scan(target_subnet=subnet)
        if not potential_pis:
            return jsonify({'success': {}, 'failed': []})

        results = {
            'success': {},
            'failed': []
        }

        for pi in potential_pis:
            ip = pi['ip']
            details = PiScanner.get_device_details(ip, username, password)
            if details and details.get('serial'):
                serial = details['serial']
                if serial not in results['success']:
                    results['success'][serial] = {
                        'model': details.get('model', 'N/A'),
                        'ram': details.get('ram', 'N/A'),
                        'serial': serial,
                        'disks': details.get('disks', []),
                        'connections': [{'ip': ip, 'mac': pi['mac']}]
                    }
                else:
                    results['success'][serial]['connections'].append({'ip': ip, 'mac': pi['mac']})
            else:
                # If details could not be fetched, add to the failed list
                results['failed'].append(pi)

        return jsonify(results)

    @app.route('/get-details', methods=['POST'])
    def get_device_details_for_ip():
        """
        API endpoint to get details for a single IP address with specific credentials.
        Used for the "retry" functionality.
        """
        data = request.json
        ip = data.get('ip')
        mac = data.get('mac')
        username = data.get('username')
        password = data.get('password')  # Can be None

        if not all([ip, mac, username]):
            return jsonify({'error': 'IP, MAC, and username are required.'}), 400

        details = PiScanner.get_device_details(ip, username, password)
        if details and details.get('serial'):
            # If successful, return the device details in the same format as the scan
            serial = details['serial']
            device_data = {
                serial: {
                    'model': details.get('model', 'N/A'),
                    'ram': details.get('ram', 'N/A'),
                    'serial': serial,
                    'disks': details.get('disks', []),
                    'connections': [{'ip': ip, 'mac': mac}]
                }
            }
            return jsonify({'success': device_data})
        else:
            return jsonify({'error': 'Authentication failed or could not retrieve details.'}), 400

    @app.route('/select-pi', methods=['POST'])
    def select_pi():
        """Saves the selected Pi's IP address to the user's session."""
        session['target_pi_ip'] = request.form.get('pi_ip')
        return redirect(url_for('index'))

    @app.route('/save-and-install', methods=['POST'])
    def save_and_install():
        """Saves component selection and user credentials, then shows success page."""
        selected_ids = request.form.getlist('components')
        with open(app.config['SELECTED_COMPONENTS_OUTPUT_FILE'], 'w') as f:
            f.write(' '.join(selected_ids))

        env_path = app.config['ENV_PATH']
        set_key(env_path, "PI_IP", session.get('target_pi_ip', ''))
        set_key(env_path, "SSH_USER", request.form.get('ssh_user', ''))
        set_key(env_path, "SSH_PASSWORD", request.form.get('ssh_pass', ''))

        return render_template('install_success.html')

    @app.route('/live-log')
    def live_log():
        """Renders the page that will display the live installation log."""
        return render_template('live_log.html')

    @app.route('/install-stream')
    def install_stream():
        """
        Runs the installer script as a subprocess and streams its
        stdout and stderr to the client using Server-Sent Events.
        """
        def generate_log():
            # Path to the installer script, relative to the project root
            installer_script_path = os.path.join(project_root, 'piselfhosting_installer.py')

            if not os.path.exists(installer_script_path):
                yield f"data: FATAL ERROR: Installer script not found at {installer_script_path}\n\n"
                yield "data: --- SCRIPT FINISHED ---\n\n"
                return

            # Use Popen to run the script as a non-blocking subprocess
            # We merge stdout and stderr to capture all output in one stream
            process = subprocess.Popen(
                [sys.executable, installer_script_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8',
                errors='replace',
                bufsize=1  # Line-buffered
            )

            # Read output line by line as it's generated
            for line in iter(process.stdout.readline, ''):
                # Format the line for SSE and yield it to the client
                yield f"data: {line.strip()}\n\n"

            process.stdout.close()
            return_code = process.wait()
            yield f"data: \n--- SCRIPT FINISHED (Exit Code: {return_code}) ---\n\n"

        # Return a streaming response
        return Response(generate_log(), mimetype='text/event-stream')

    return app


if __name__ == '__main__':
    def open_browser():
        webbrowser.open_new("http://127.0.0.1:5000/")


    app = create_app()
    Timer(1, open_browser).start()
    app.run(host='127.0.0.1', port=5000, debug=False)