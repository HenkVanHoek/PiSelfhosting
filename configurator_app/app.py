import json
import os
import sys
import webbrowser
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


def create_app(test_config=None):
    """Application Factory Function"""
    app = Flask(__name__)
    # A secret key is required for session management
    app.secret_key = os.urandom(24)

    # --- Configuration ---
    app.config.from_mapping(
        METADATA_FILE=os.path.join(project_root, 'config', 'components_metadata.json'),
        SELECTED_COMPONENTS_OUTPUT_FILE=os.path.join(project_root, 'selected_components.txt'),
        ENV_PATH=os.path.join(project_root, '.env')
    )
    if test_config:
        app.config.from_mapping(test_config)

    manager = ComponentManager(app.config['METADATA_FILE'])

    @app.route('/')
    def index():
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
            return render_template('select_pi.html')

    @app.route('/scan', methods=['POST'])
    def scan_network():
        """API endpoint to run the PiScanner."""
        data = request.json
        subnet = data.get('subnet')
        if not subnet:
            return jsonify({'error': 'Subnet is required.'}), 400

        # Note: This requires the start script to be run with sudo/admin rights
        found_pis = PiScanner.scan(target_subnet=subnet)
        return jsonify(found_pis)

    @app.route('/select-pi', methods=['POST'])
    def select_pi():
        """Saves the selected Pi's IP address to the user's session."""
        session['target_pi_ip'] = request.form.get('pi_ip')
        # Redirect back to the main page, which will now show the component selection
        return redirect(url_for('index'))

    @app.route('/save-and-install', methods=['POST'])
    def save_and_install():
        """Saves component selection and user credentials, then shows success page."""
        selected_ids = request.form.getlist('components')
        with open(app.config['SELECTED_COMPONENTS_OUTPUT_FILE'], 'w') as f:
            f.write(' '.join(selected_ids))

        # Save IP and credentials to the .env file for the executor to use
        env_path = app.config['ENV_PATH']
        set_key(env_path, "PI_IP", session.get('target_pi_ip', ''))
        set_key(env_path, "SSH_USER", request.form.get('ssh_user', ''))
        set_key(env_path, "SSH_PASSWORD", request.form.get('ssh_pass', ''))

        # This version no longer launches a subprocess.
        # It now renders a success page with the next steps for the user.
        return render_template('install_success.html')

    return app


if __name__ == '__main__':
    def open_browser():
        webbrowser.open_new("http://127.0.0.1:5000/")


    app = create_app()
    # Open the browser automatically after a short delay
    Timer(1, open_browser).start()
    # Run the Flask app
    app.run(host='127.0.0.1', port=5000, debug=False)