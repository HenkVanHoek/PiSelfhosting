import json
import os
import sys
import webbrowser
import logging
from threading import Timer
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from dotenv import set_key

# --- Path and Module Setup ---
# This ensures the app can find your other source files
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
src_path = os.path.join(project_root, 'src')
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from component_manager import ComponentManager
from pi_scanner import PiScanner

logging.basicConfig(
    filename='configurator.log',
    filemode='w',  # 'w' overwrites the log on each start, use 'a' to append
    level=logging.DEBUG,  # Log everything from DEBUG level and higher
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s'
)

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
                components_to_display = {k: v for k, v in all_components.items() if not k.startswith('_')}
                return render_template('select_components.html', components=components_to_display,
                                       pi_ip=session['target_pi_ip'])
            else:
                detected_subnet = PiScanner.detect_subnet()
                return render_template('select_pi.html', detected_subnet=detected_subnet)
        except Exception as e:
            # 4. Log the full error if something goes wrong
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
        password = data.get('password')

        if not all([subnet, username, password]):
            return jsonify({'error': 'Subnet, username, and password are required.'}), 400

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
        password = data.get('password')

        if not all([ip, mac, username, password]):
            return jsonify({'error': 'IP, MAC, username, and password are required.'}), 400

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

    return app


if __name__ == '__main__':
    def open_browser():
        webbrowser.open_new("http://127.0.0.1:5000/")


    app = create_app()
    Timer(1, open_browser).start()
    app.run(host='127.0.0.1', port=5000, debug=False)