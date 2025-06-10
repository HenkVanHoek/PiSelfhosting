#!/bin/bash

# This script is designed to be run from the host machine to configure Frigate cameras.
# It sources the .env file to get necessary environment variables and then runs
# the Python configuration tool within the Docker environment.

# Determine the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
BASE_DIR_HOST=$(dirname "$SCRIPT_DIR") # Assumes scripts directory is directly under BASE_DIR_HOST

# Load environment variables from .env
# This ensures variables like FRIGATE_RTSP_USERNAME and FRIGATE_RTSP_PASSWORD are available
# for the Python script running inside the container.
ENV_FILE="$BASE_DIR_HOST/.env"
if [ -f "$ENV_FILE" ]; then
    echo "Info: Loading environment variables from $ENV_FILE..."
    set -a # Automatically export all variables
    # Use 'source' or '.' to load the .env file into the current shell's environment
    source "$ENV_FILE"
    set +a
else
    echo "Error: .env file not found at $ENV_FILE. Please ensure you've run setup.sh."
    exit 1
fi

echo "--- Starting Frigate Camera Configuration Tool ---"

# Pass the BASE_DIR_HOST to the container so Python script can reference it for restart command suggestion
# Use docker compose exec to run the python script inside the 'frigate' service container
# This assumes the 'frigate' service is defined in your docker-compose.yml and is running.
docker compose -f "$BASE_DIR_HOST/docker-compose.yml" exec frigate \
    python3 /app/piselfhosting/scripts/frigate_camera_config_tool.py \
    -e FRIGATE_RTSP_USERNAME="$FRIGATE_RTSP_USERNAME" \
    -e FRIGATE_RTSP_PASSWORD="$FRIGATE_RTSP_PASSWORD" \
    -e DOMAIN="$DOMAIN" \
    -e BASE_DIR_HOST="$BASE_DIR_HOST"

echo "--- Frigate Camera Configuration Tool Finished ---"
echo "Remember to restart Frigate if changes were made: bash $BASE_DIR_HOST/scripts/restart-all.sh"

