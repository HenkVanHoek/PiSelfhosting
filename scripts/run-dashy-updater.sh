#!/bin/bash
# scripts/run-dashy-updater.sh

# This script runs the dashy_updater.py tool inside a Docker container
# to ensure a consistent environment and no host dependencies.

echo "--- Starting Dashy Tile Updater (in Docker) ---"

# Determine the project root
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
PROJECT_ROOT="$( dirname "$SCRIPT_DIR" )"

# Define paths and names
ENV_FILE="$PROJECT_ROOT/docker/.env"
PYTHON_SCRIPT_PATH_IN_CONTAINER="/app/scripts/dashy_updater.py"
DOCKER_IMAGE_NAME="piselfhosting-setup-tool" # Reuse the image from the main installer

# Check if the .env file exists
if [ ! -f "$ENV_FILE" ]; then
    echo "❌ Error: .env file not found at $ENV_FILE"
    echo "   Please run the main installer first to generate the .env and Docker image."
    exit 1
fi

# Load the HOST_IP from the .env file
# We use a specific grep/sed combo to avoid issues with special characters
HOST_IP=$(grep -E '^HOST_IP=' "$ENV_FILE" | sed -e 's/HOST_IP=//')

# Check if the HOST_IP variable is loaded
if [ -z "$HOST_IP" ]; then
    echo "❌ Error: HOST_IP is not set in the .env file at $ENV_FILE"
    exit 1
fi

# Check if the Docker image exists
if ! docker image inspect "$DOCKER_IMAGE_NAME" &> /dev/null; then
    echo "❌ Error: Docker image '$DOCKER_IMAGE_NAME' not found."
    echo "   Please run the main installer first to build the tool image."
    exit 1
fi

echo "Running updater with HOST_IP: $HOST_IP..."

# Execute the Python script inside the reusable Docker container
docker run --rm \
  --env HOST_IP="$HOST_IP" \
  -v "$PROJECT_ROOT:/app" \
  "$DOCKER_IMAGE_NAME" \
  python3 "$PYTHON_SCRIPT_PATH_IN_CONTAINER" "$HOST_IP"

echo "--- Dashy Tile Updater Finished ---"