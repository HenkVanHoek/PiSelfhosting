#!/bin/bash

# /home/PiSelfhosting/scripts/run-ssl-cert-manager.sh
# This script runs the ssl_cert_manager.py inside a Docker container.

# Define base directory (host path)
BASE_DIR_HOST="/home/PiSelfhosting"
SCRIPTS_DIR="${BASE_DIR_HOST}/scripts"
DOCKERFILE="${SCRIPTS_DIR}/config_tool_base_dockerfile"
IMAGE_NAME="piselfhosting-config-tool-base"

echo "Building Docker image for config tools if not already built..."
# Build the Docker image. Use --pull to ensure we get the latest base image.
docker build -t "$IMAGE_NAME" -f "$DOCKERFILE" "$SCRIPTS_DIR" || {
    echo "❌ Failed to build Docker image '$IMAGE_NAME'. Exiting."
    exit 1
}
echo "✅ Docker image '$IMAGE_NAME' built/updated."

echo "Running SSL Certificate Manager in Docker container..."

# Load .env variables if not already loaded (e.g., if script is run directly)
if [ -f "$BASE_DIR_HOST/.env" ]; then
    set -a # Automatically export all subsequent assignments
    source "$BASE_DIR_HOST/.env"
    set +a # Turn off auto-export
fi

# Define environment variables to pass through to the container
ENV_VARS_TO_PASS=""
ENV_VARS=(DOMAIN) # Pass DOMAIN from .env to the Python script
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
    "$IMAGE_NAME" python3 /app/piselfhosting/scripts/ssl_cert_manager.py || {
    echo "❌ Failed to run SSL Certificate Manager in Docker."
    exit 1
}

echo "✅ SSL Certificate Manager execution complete."
echo "Remember to update your services' configurations to use the new certificates if needed."

