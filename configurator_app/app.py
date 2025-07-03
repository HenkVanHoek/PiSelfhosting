# configurator_app/app.py
import json
import os
import webbrowser
from threading import Timer
from flask import Flask, render_template, request

# --- Corrected Import Logic ---
# Add parent directory to path to find 'src'
import sys

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
src_path = os.path.join(project_root, 'src')
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from component_manager import ComponentManager


def create_app(test_config=None):
    """Application Factory Function"""
    app = Flask(__name__, instance_relative_config=True)

    # --- Path and Test Configuration ---
    if test_config:
        app.config.from_mapping(test_config)
    else:
        # Default paths for normal execution
        app.config.from_mapping(
            METADATA_FILE=os.path.join(project_root, 'config', 'components_metadata.json'),
            SELECTED_COMPONENTS_OUTPUT_FILE=os.path.join(project_root, 'selected_components.txt')
        )

    # Initialize the component manager with the correct path
    manager = ComponentManager(app.config['METADATA_FILE'])

    @app.route('/')
    def index():
        all_components = manager.get_all_components()
        components_to_display = {k: v for k, v in all_components.items() if not k.startswith('_')}
        return render_template('index.html', components=components_to_display)

    @app.route('/install', methods=['POST'])
    def install():
        selected_ids = request.form.getlist('components')
        output_file = app.config['SELECTED_COMPONENTS_OUTPUT_FILE']

        with open(output_file, 'w') as f:
            f.write(' '.join(selected_ids))

        print(f"'{output_file}' generated with: {selected_ids}")

        return render_template('install_success.html')

    return app


def open_browser():
    """Opens the default web browser to the Flask app's URL."""
    webbrowser.open_new("http://127.0.0.1:5000/")


if __name__ == '__main__':
    app = create_app()
    Timer(1, open_browser).start()
    app.run(host='127.0.0.1', port=5000, debug=False)