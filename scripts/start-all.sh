#!/bin/bash

# PiSelfhosting Start All Services Script
# Location: /home/PiSelfhosting/scripts/start-all.sh

# Stop the script if any command fails
set -e

# Define base directory
BASE_DIR="/home/PiSelfhosting"
ENV_FILE="/home/PiSelfhosting/.env"
COMPONENTS_FILE="/home/PiSelfhosting/scripts/selected_components.txt"
DOCKER_COMPOSE_DIR="/home/PiSelfhosting/docker"

# Source the .env file to load and export environment variables
if [ -f "$ENV_FILE" ]; then
    echo "Info: Loading environment variables from $ENV_FILE and exporting them..."
    set -a # Automatically export all subsequent assignments
    source "$ENV_FILE"
    set +a # Turn off auto-export
else
    echo "Error: .env file not found at $ENV_FILE. Cannot start containers."
    exit 1
fi

# Define the common Docker Compose command
DOCKER_COMPOSE_COMMAND="docker compose"

# Read selected components from file for unified Docker Compose command
declare -a DOCKER_COMPOSE_FILE_ARGS=()
if [ -f "$COMPONENTS_FILE" ]; then
    # Ensure correct parsing from the file. Assuming space-separated, quoted entries like "comp1" "comp2"
    for comp in $(cat "$COMPONENTS_FILE" | tr -d '"'); do
        # IMPORTANT: Skip 'docker' itself from the Docker Compose arguments as it's not a service
        if [ "$comp" == "docker" ]; then
            continue
        fi
        if [ -f "$DOCKER_COMPOSE_DIR/$comp/docker-compose.yml" ]; then
            DOCKER_COMPOSE_FILE_ARGS+=("-f" "$DOCKER_COMPOSE_DIR/$comp/docker-compose.yml")
        fi
    done
fi

if [ ${#DOCKER_COMPOSE_FILE_ARGS[@]} -eq 0 ]; then
    echo "No Docker Compose files found for selected components. Nothing to start."
    exit 0
fi

# --- Function to wait for a specific port to be open ---
wait_for_port() {
    local host="$1"
    local port="$2"
    local timeout="$3"
    local service_name="$4"
    local count=0

    echo "⏳ Waiting for $service_name ($host:$port) to be ready..."

    if ! command -v nc &> /dev/null; then
        echo "❌ 'netcat' (nc) not found. Please install it (e.g., sudo apt install netcat-traditional or netcat-openbsd) for robust port checking."
        echo "   Falling back to sleep for $timeout seconds for $service_name."
        sleep "$timeout"
        return 0
    fi

    while ! nc -z "$host" "$port" &> /dev/null; do
        if [ "$count" -ge "$timeout" ]; then
            echo "❌ Timeout waiting for $service_name ($host:$port). It might not have started correctly."
            return 1
        fi
        echo "   Still waiting for $service_name ($host:$port)... ($((timeout - count))s remaining)"
        sleep 1
        count=$((count + 1))
    done

    echo "✅ $service_name ($host:$port) is ready."
    return 0
}

# --- Function to wait for MariaDB to be fully ready (checking logs) ---
wait_for_mariadb_ready() {
    local container_name="$1"
    local timeout="$2"
    local count=0
    local log_ready_string="ready for connections"

    echo "⏳ Waiting for MariaDB container '$container_name' to be fully ready (checking logs for '$log_ready_string')..."

    while true; do
        if [ "$count" -ge "$timeout" ]; then
            echo "❌ Timeout waiting for MariaDB container '$container_name' to be ready."
            echo "--- Debugging MariaDB container ($container_name) ---"
            echo "Container Status:"
            docker ps -a --filter name="$container_name" --format "ID: {{.ID}}\nName: {{.Names}}\nStatus: {{.Status}}\nPorts: {{.Ports}}"
            echo "Last 50 log lines from MariaDB:"
            docker logs "$container_name" --tail 50 2>&1
            echo "--- End Debugging ---"
            return 1
        fi

        if ! docker ps -f name="$container_name" --format "{{.Names}}" | grep -q "$container_name"; then
            echo "❌ MariaDB container '$container_name' is not running or has stopped. It might have failed to start."
            echo "--- Debugging MariaDB container ($container_name) ---"
            echo "Container Status:"
            docker ps -a --filter name="$container_name" --format "ID: {{.ID}}\nName: {{.Names}}\nStatus: {{.Status}}\nPorts: {{.Ports}}"
            echo "Last 50 log lines from MariaDB:"
            docker logs "$container_name" --tail 50 2>&1
            echo "--- End Debugging ---"
            return 1
        fi

        if docker logs "$container_name" 2>&1 | grep -q "$log_ready_string"; then
            echo "✅ MariaDB container '$container_name' is fully ready."
            return 0
        fi

        echo "   Still waiting for MariaDB container '$container_name' to be fully ready... ($((timeout - count))s remaining)"
        sleep 1
        count=$((count + 1))
    done
}

# --- Function to wait for Mosquitto to be fully ready (checking logs) ---
wait_for_mosquitto_ready() {
    local container_name="$1"
    local timeout="$2"
    local count=0
    local log_ready_string="mosquitto version"

    echo "⏳ Waiting for Mosquitto container '$container_name' to be fully ready (checking logs for '$log_ready_string')..."

    while true; do
        if [ "$count" -ge "$timeout" ]; then
            echo "❌ Timeout waiting for Mosquitto container '$container_name' to be ready."
            echo "--- Debugging Mosquitto container ($container_name) ---"
            echo "Container Status:"
            docker ps -a --filter name="$container_name" --format "ID: {{.ID}}\nName: {{.Names}}\nStatus: {{.Status}}\nPorts: {{.Ports}}"
            echo "Last 50 log lines from Mosquitto:"
            docker logs "$container_name" --tail 50 2>&1
            echo "--- End Debugging ---"
            return 1
        fi

        if ! docker ps -f name="$container_name" --format "{{.Names}}" | grep -q "$container_name"; then
            echo "❌ Mosquitto container '$container_name' is not running or has stopped. It might have failed to start."
            echo "--- Debugging Mosquitto container ($container_name) ---"
            echo "Container Status:"
            docker ps -a --filter name="$container_name" --format "ID: {{.ID}}\nName: {{.Names}}\nStatus: {{.Status}}\nPorts: {{.Ports}}"
            echo "Last 50 log lines from Mosquitto:"
            docker logs "$container_name" --tail 50 2>&1
            echo "--- End Debugging ---"
            return 1
        fi

        if docker logs "$container_name" 2>&1 | grep -q "$log_ready_string"; then
            echo "✅ Mosquitto container '$container_name' is fully ready."
            return 0
        fi

        echo "   Still waiting for Mosquitto container '$container_name' to be fully ready... ($((timeout - count))s remaining)"
        sleep 1
        count=$((count + 1))
    done
}


echo "🚀 Starting PiSelfhosting containers in dependency order..."

# --- Check and create the Docker network if it doesn't exist ---
NETWORK_NAME="piselfhosting_net"
if ! docker network inspect "$NETWORK_NAME" &>/dev/null; then
    echo "Info: Docker network '$NETWORK_NAME' not found. Creating it..."
    sudo docker network create "$NETWORK_NAME" || {
        echo "❌ Error: Failed to create Docker network '$NETWORK_NAME'. Exiting."
        exit 1
    }
    echo "✅ Docker network '$NETWORK_NAME' created."
else
    echo "Info: Docker network '$NETWORK_NAME' already exists."
fi


# --- Explicitly stop and remove containers for a clean start ---
echo "Attempting to stop and remove any existing PiSelfhosting containers for a clean start..."
(cd "$BASE_DIR" && $DOCKER_COMPOSE_COMMAND "${DOCKER_COMPOSE_FILE_ARGS[@]}" down --remove-orphans) || {
    echo "⚠️ Failed to stop or remove some existing services. Continuing with startup, but conflicts might persist."
}

echo "Starting all selected services as a single Docker Compose project..."
(cd "$BASE_DIR" && $DOCKER_COMPOSE_COMMAND "${DOCKER_COMPOSE_FILE_ARGS[@]}" up -d --force-recreate --pull always) || {
    echo "❌ Failed to start one or more services. Check Docker logs for details."
    exit 1
}

# Define the ordered list of all possible components to maintain dependency order for health checks
declare -a ALL_POSSIBLE_COMPONENTS=(
    "mariadb"
    "mosquitto"
    "phpmyadmin"
    "nextcloud"
    "mailserver" # Note: Mailserver readiness might be more complex than a single port check
    "homeassistant"
    "frigate"
    "pihole"
    "docker-monitor"
    "portainer"
    "dashy"
    "nginxproxymanager"
    "piselfhosting-docs"
)

# Loop through the ordered list of all possible components for individual port/readiness checks
for component_name_to_start in "${ALL_POSSIBLE_COMPONENTS[@]}"; do
    # Only check if the component was actually selected
    if [[ " $(cat "$COMPONENTS_FILE" | tr -d '"') " =~ " ${component_name_to_start} " ]]; then
        case "$component_name_to_start" in
            "mariadb")
                wait_for_port "127.0.0.1" 3306 60 "MariaDB (port check)" || exit 1
                wait_for_mariadb_ready "piselfhosting-mariadb" 120 || exit 1
                ;;
            "mosquitto")
                wait_for_port "127.0.0.1" 1883 30 "Mosquitto (port check)" || exit 1
                wait_for_mosquitto_ready "piselfhosting-mosquitto" 60 || exit 1
                ;;
            "phpmyadmin")
                wait_for_port "127.0.0.1" 8083 60 "phpMyAdmin" || exit 1
                ;;
            "nextcloud")
                wait_for_port "127.0.0.1" 8081 90 "Nextcloud" || exit 1
                ;;
            "mailserver")
                wait_for_port "127.0.0.1" 25 60 "Mailserver (SMTP Exim4)" || true # Non-blocking for now
                wait_for_port "127.0.0.1" 143 60 "Mailserver (IMAP Dovecot)" || true # Non-blocking for now
                echo "Info: Mailserver services are complex and may take longer to fully initialize. Please check logs for details."
                sleep 10 # Give it a bit more time
                ;;
            "homeassistant")
                wait_for_port "127.0.0.1" 8123 90 "Home Assistant" || exit 1
                ;;
            "frigate")
                wait_for_port "127.0.0.1" 5000 30 "Frigate" || exit 1
                ;;
            "pihole")
                wait_for_port "127.0.0.1" 8082 30 "Pi-hole Admin" || exit 1
                ;;
            "docker-monitor")
                wait_for_port "127.0.0.1" 8088 20 "Docker Monitor" || exit 1
                ;;
            "portainer")
                wait_for_port "127.0.0.1" 9000 30 "Portainer" || exit 1
                ;;
            "dashy")
                wait_for_port "127.0.0.1" 8080 45 "Dashy" || exit 1
                ;;
            "nginxproxymanager")
                wait_for_port "127.0.0.1" 81 60 "Nginx Proxy Manager Admin" || exit 1
                ;;
            "piselfhosting-docs")
                wait_for_port "127.0.0.1" 8089 30 "PiSelfhosting Docs (Nginx)" || exit 1 # Assuming default doc port is 8089. If npm fronts it, this port isn't exposed.
                ;;
            *)
                echo "No specific port wait defined for ${component_name_to_start}. Waiting for 5 seconds."
                sleep 5 ;;
        esac
    fi
done

echo "\n✅ All selected containers have been started."
echo "Check their status with: docker ps"
echo "You can now access services via Nginx Proxy Manager (if configured), or their direct ports."

