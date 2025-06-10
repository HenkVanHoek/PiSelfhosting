#!/bin/bash

# PiSelfhosting Restart All/Specific Service Script
# Location: /home/PiSelfhosting/scripts/restart-all.sh

# This script restarts all selected PiSelfhosting containers, or a specific service.
# It pulls the latest image before restarting if no specific service is given.

set -e

BASE_DIR="/home/PiSelfhosting"
ENV_FILE="/home/PiSelfhosting/.env"
COMPONENTS_FILE="/home/PiSelfhosting/scripts/selected_components.txt"
DOCKER_COMPOSE_DIR="/home/PiSelfhosting/docker"

if [ -f "$ENV_FILE" ]; then
    source "$ENV_FILE"
else
    echo "Error: .env file not found at $ENV_FILE. Cannot proceed."
    exit 1
fi

DOCKER_COMPOSE_COMMAND="docker compose"

SERVICE_TO_RESTART="$1" # Check for an argument (specific service name)

if [ -z "$SERVICE_TO_RESTART" ]; then
    echo "Restarting all selected PiSelfhosting containers (pulling latest images)..."
    
    declare -a COMPONENTS_FOR_RESTART=()
    if [ -f "$COMPONENTS_FILE" ]; then
        for comp in $(cat "$COMPONENTS_FILE" | tr -d '"'); do
            # IMPORTANT: Skip 'docker' itself from the restart command as it's not a service
            if [ "$comp" == "docker" ]; then
                continue
            fi
            if [ -f "$DOCKER_COMPOSE_DIR/$comp/docker-compose.yml" ]; then
                COMPONENTS_FOR_RESTART+=("-f" "$DOCKER_COMPOSE_DIR/$comp/docker-compose.yml")
            fi
        done
    fi

    if [ ${#COMPONENTS_FOR_RESTART[@]} -eq 0 ]; then
        echo "No Docker Compose files found for selected components. Nothing to restart."
        exit 0
    fi

    echo "Stopping and removing existing containers..."
    (cd "$BASE_DIR" && $DOCKER_COMPOSE_COMMAND "${COMPONENTS_FOR_RESTART[@]}" down --remove-orphans) || echo "⚠️ Some containers could not be stopped/removed. Continuing."
    
    echo "Pulling latest images and starting all selected services..."
    (cd "$BASE_DIR" && $DOCKER_COMPOSE_COMMAND "${COMPONENTS_FOR_RESTART[@]}" up -d --force-recreate --pull always) || {
        echo "❌ Failed to start one or more services. Check Docker logs."
        exit 1
    }
    echo "✅ All selected containers restarted successfully."
else
    echo "Restarting specific service: $SERVICE_TO_RESTART (pulling latest image)..."
    SERVICE_DIR="$DOCKER_COMPOSE_DIR/$SERVICE_TO_RESTART"
    if [ -d "$SERVICE_DIR" ] && [ -f "$SERVICE_DIR/docker-compose.yml" ]; then
        echo "Attempting to stop and remove existing container for $SERVICE_TO_RESTART..."
        (cd "$SERVICE_DIR" && $DOCKER_COMPOSE_COMMAND stop &>/dev/null) || true
        (cd "$SERVICE_DIR" && $DOCKER_COMPOSE_COMMAND rm -f &>/dev/null) || true
        
        echo "Pulling latest image and starting $SERVICE_TO_RESTART..."
        (cd "$SERVICE_DIR" && $DOCKER_COMPOSE_COMMAND up -d --force-recreate --pull always) || {
            echo "❌ Failed to restart $SERVICE_TO_RESTART. Check Docker logs."
            exit 1
        }
        echo "✅ Service $SERVICE_TO_RESTART restarted successfully."
    else
        echo "❌ Service directory or docker-compose.yml for '$SERVICE_TO_RESTART' not found: $SERVICE_DIR."
        echo "Please ensure the service name is correct and it was deployed."
        exit 1
    fi
fi

echo "Check status with: docker ps"
