#!/bin/bash

# /home/PiSelfhosting/scripts/run-mailserver-config-tool.sh
# This script runs the mailserver_config_tool.py inside a Docker container.

# Define base directory (host path)
BASE_DIR_HOST="/home/PiSelfhosting"
SCRIPTS_DIR="${BASE_DIR_HOST}/scripts"
DOCKER_COMPOSE_DIR="${BASE_DIR_HOST}/docker" # Needed for mounting config paths
DOCKERFILE="${SCRIPTS_DIR}/config_tool_base_dockerfile"
IMAGE_NAME="piselfhosting-config-tool-base"

echo "Building Docker image for config tools if not already built..."
# Build the Docker image. Use --pull to ensure we get the latest base image.
docker build -t "$IMAGE_NAME" -f "$DOCKERFILE" "$SCRIPTS_DIR" || {
    echo "❌ Failed to build Docker image '$IMAGE_NAME'. Exiting."
    exit 1
}
echo "✅ Docker image '$IMAGE_NAME' built/updated."

echo "Running Mailserver configuration tool in Docker container..."

# Load .env variables if not already loaded (e.g., if script is run directly)
if [ -f "$BASE_DIR_HOST/.env" ]; then
    set -a # Automatically export all subsequent assignments
    source "$BASE_DIR_HOST/.env"
    set +a # Turn off auto-export
fi

# Define environment variables to pass through to the container
ENV_VARS_TO_PASS=""
ENV_VARS=(DOMAIN) # Only DOMAIN needed for mailserver config, add others if necessary
for var in "${ENV_VARS[@]}"; do
    if [ -n "${!var}" ]; then # Check if the variable is set and not empty
        ENV_VARS_TO_PASS+=" -e $var=\"${!var}\""
    fi
done

# Pass the BASE_DIR_HOST so Python scripts can resolve paths relative to the original host structure
ENV_VARS_TO_PASS+=" -e BASE_DIR_HOST=\"$BASE_DIR_HOST\""

docker run --rm -it \
    -v "$BASE_DIR_HOST:/app/piselfhosting" \
    --network piselfhosting_net \
    $ENV_VARS_TO_PASS \
    "$IMAGE_NAME" python3 /app/piselfhosting/scripts/mailserver_config_tool.py || {
    echo "❌ Failed to run Mailserver configuration tool in Docker."
    exit 1
}

echo "✅ Mailserver configuration tool execution complete."
echo "Remember to rebuild and restart your Mailserver if changes were made: $BASE_DIR_HOST/scripts/restart-all.sh mailserver"

