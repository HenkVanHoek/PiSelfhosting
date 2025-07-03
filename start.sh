#!/bin/bash
# start.sh

echo "Starting PiSelfhosting Configurator..."
echo "This will open a new tab in your web browser."

# Get the directory where the script is located to reliably find the app
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

# Run the Flask application from the 'configurator_app' directory
python3 "$SCRIPT_DIR/configurator_app/app.py"

echo ""
echo "The server has been stopped. You can now close this window."