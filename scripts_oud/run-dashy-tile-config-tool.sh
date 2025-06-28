#!/bin/bash

# /home/PiSelfhosting/scripts/run-dashy-tile-config-tool.sh
# This script runs the dashy_tile_config_tool.py inside a Docker container.

# Define base directory (on the host)
BASE_DIR="/home/PiSelfhosting"
SCRIPTS_DIR="$BASE_DIR/scripts"
DOCKER_COMPOSE_DIR="$BASE_DIR/docker" # Needed for mounting config paths
DOCKERFILE="$SCRIPTS_DIR/config_tool_base_dockerfile"
TOOL_SCRIPT="$SCRIPTS_DIR/dashy_tile_config_tool.py"
IMAGE_NAME="piselfhosting-config-tool-base"

echo "Building Docker image for config tools if not already built..."
# Build the Docker image. Use --pull to ensure we get the latest base image.
docker build -t "$IMAGE_NAME" -f "$DOCKERFILE" "$SCRIPTS_DIR" || {
    echo "❌ Failed to build Docker image '$IMAGE_NAME'. Exiting."
    exit 1
}
echo "✅ Docker image '$IMAGE_NAME' built/updated."

echo "Running Dashy tile configuration tool in Docker container..."

# Run the Python script in a temporary Docker container
# -it: Interactive (for user input if needed)
# --rm: Remove container after exit
# -v: Mount volumes:
#     - Host BASE_DIR to /app/piselfhosting in container (for consistent paths for config files)
#     - The specific Python script itself so it can be executed
# -e BASE_DIR_HOST: Pass the host's BASE_DIR into the container for correct path resolution if needed by Python scripts
# -e ENV_FILE: Pass the .env file path
# -e DB_PASS, FRIGATE_RTSP_PASSWORD, etc.: Pass environment variables from host's .env to the container
#       (The wrapper script will try to load them if not already in current shell env)

# Load .env variables if not already loaded (e.g., if script is run directly)
if [ -f "$BASE_DIR/.env" ]; then
    set -a # Automatically export all subsequent assignments
    source "$BASE_DIR/.env"
    set +a # Turn off auto-export
fi

# Define environment variables to pass through to the container
# This is crucial so the Python script can access them via os.getenv()
ENV_VARS_TO_PASS=""
ENV_VARS=(DOMAIN PORT_WEB PORT_SSL DB_USER DB_PASS FRIGATE_RTSP_USERNAME FRIGATE_RTSP_PASSWORD NC_ADMIN_USER NC_ADMIN_PASS PIHOLE_PASSWORD)
for var in "${ENV_VARS[@]}"; do
    if [ -n "${!var}" ]; then # Check if the variable is set and not empty
        ENV_VARS_TO_PASS+=" -e $var=\"${!var}\""
    fi
done

# Pass the BASE_DIR_HOST so Python scripts can resolve paths relative to the original host structure
ENV_VARS_TO_PASS+=" -e BASE_DIR_HOST=\"$BASE_DIR\""

docker run --rm \
    -v "$BASE_DIR:/app/piselfhosting" \
    --network piselfhosting_net \
    $ENV_VARS_TO_PASS \
    "$IMAGE_NAME" python3 /app/piselfhosting/scripts/dashy_tile_config_tool.py || {
    echo "❌ Failed to run Dashy tile configuration tool in Docker."
    exit 1
}

echo "✅ Dashy tile configuration tool execution complete."
echo "Remember to restart Dashy if changes were made: $BASE_DIR/scripts/restart-all.sh dashy"

