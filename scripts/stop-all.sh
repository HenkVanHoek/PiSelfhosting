#!/bin/bash

# PiSelfhosting Stop All Services Script
# Location: /home/PiSelfhosting/scripts/stop-all.sh

set -e

BASE_DIR="/home/PiSelfhosting"
ENV_FILE="/home/PiSelfhosting/.env"
DOCKER_COMPOSE_DIR="/home/PiSelfhosting/docker"
COMPONENTS_FILE="/home/PiSelfhosting/scripts/selected_components.txt" # For components_list_txt to know what to stop

if [ -f "$ENV_FILE" ]; then
    echo "Loading existing .env file..."
    source "$ENV_FILE"
else
    echo "Error: .env file not found at $ENV_FILE. Cannot proceed with stopping services."
    exit 1
fi

DOCKER_COMPOSE_COMMAND="docker compose"

echo "Stopping PiSelfhosting containers..."

declare -a COMPONENTS_FOR_DOWN=()
if [ -f "$COMPONENTS_FILE" ]; then
    for comp in $(cat "$COMPONENTS_FILE" | tr -d '"'); do
        # IMPORTANT: Skip 'docker' itself from the down command as it's not a service
        if [ "$comp" == "docker" ]; then
            continue
        fi
        if [ -f "$DOCKER_COMPOSE_DIR/$comp/docker-compose.yml" ]; then
            COMPONENTS_FOR_DOWN+=("-f" "$DOCKER_COMPOSE_DIR/$comp/docker-compose.yml")
        fi
    done
fi

if [ ${#COMPONENTS_FOR_DOWN[@]} -gt 0 ]; then
    (cd "$BASE_DIR" && $DOCKER_COMPOSE_COMMAND "${COMPONENTS_FOR_DOWN[@]}" down --volumes --remove-orphans) || {
        echo "⚠️ Failed to stop or remove some services. Check 'docker ps -a' and 'docker volume ls'."
    }
else
    echo "No Docker Compose files found from selected components. Nothing to stop."
fi

echo "✅ All PiSelfhosting containers stopped."
echo "You can check their status with: docker ps -a"
