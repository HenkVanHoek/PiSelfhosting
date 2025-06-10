#!/bin/bash

# PiSelfhosting Deploy Script
# Location: /home/PiSelfhosting/scripts/deploy.sh
# This script is responsible for deploying and managing Docker containers
# for the selected PiSelfhosting components.
# It handles cleanup, network setup, configuration file generation, and service startup.

# Stop the script if a command fails
set -e

# Define the base directory and important file paths
BASE_DIR="/home/PiSelfhosting"
SCRIPTS_DIR="$BASE_DIR/scripts"
ENV_FILE="$BASE_DIR/.env"
COMPONENTS_FILE="$BASE_DIR/scripts/selected_components.txt"
COMPONENTS_LIST_FILE="$SCRIPTS_DIR/components_list.txt" # Path to the file with component definitions
DOCKER_COMPOSE_DIR="${BASE_DIR}/docker" # Directory where individual docker-compose.yml files reside

# Ensure the scripts directory exists
mkdir -p "$SCRIPTS_DIR"
mkdir -p "$DOCKER_COMPOSE_DIR"


# --- Function to check if whiptail is installed and install it if necessary ---
ensure_whiptail() {
    echo "--- Checking if 'whiptail' is installed ---"
    if ! command -v whiptail &> /dev/null; then
        echo "Info: 'whiptail' not found. Installing..."
        sudo apt-get update && sudo apt-get install -y whiptail
        if [ $? -eq 0 ]; then
            echo "✅ 'whiptail' successfully installed."
        else
            echo "❌ Error: Could not install 'whiptail'. Ensure APT repositories are correctly configured."
            exit 1
        fi
    else
        echo "Info: 'whiptail' is already installed."
    fi
    echo "--- 'whiptail' check complete ---"
}

# Call the function to ensure whiptail
ensure_whiptail

# --- Collecting essential environment variables ---
echo "--- Setting essential environment variables ---"

# Try to load existing values, otherwise use defaults or ask the user
load_env_if_exists() {
    if [ -f "$ENV_FILE" ]; then
        set -a # Automatically export all subsequent assignments for the current shell
        source "$ENV_FILE"
        set +a # Disable auto-export
        echo "Existing variables loaded from .env file."
    fi
}
load_env_if_exists

# Ask for DOMAIN
if [ -z "${DOMAIN}" ]; then
    DOMAIN=$(whiptail --inputbox "Enter the main domain name you want to use for your services (e.g., 'myserver.com' or 'home.arpa'). This will be used for Nginx Proxy Manager and Dashy." 10 60 "myserver.com" 3>&1 1>&2 2>&3)
    if [ $? -ne 0 ]; then echo "❌ Canceled. Exiting."; exit 1; fi
fi

# Ask for MySQL/MariaDB database username and password
if [ -z "${DB_USER}" ]; then
    DB_USER=$(whiptail --inputbox "Enter the username for the MariaDB database (e.g., 'piselfhosting_user')." 10 60 "piselfhosting_user" 3>&1 1>&2 2>&3)
    if [ $? -ne 0 ]; then echo "❌ Canceled. Exiting."; exit 1; fi
fi

if [ -z "${DB_PASS}" ]; then
    DB_PASS=$(whiptail --passwordbox "Enter a STRONG password for the MariaDB user. Remember this well!" 10 60 3>&1 1>&2 2>&3)
    if [ $? -ne 0 ]; then echo "❌ Canceled. Exiting."; exit 1; fi
fi

# Ask for Nextcloud admin credentials
if [ -z "${NC_ADMIN_USER}" ]; then
    NC_ADMIN_USER=$(whiptail --inputbox "Enter the admin username for Nextcloud." 10 60 "nextcloud_admin" 3>&1 1>&2 2>&3)
    if [ $? -ne 0 ]; then echo "❌ Canceled. Exiting."; exit 1; fi
fi

if [ -z "${NC_ADMIN_PASS}" ]; then
    NC_ADMIN_PASS=$(whiptail --passwordbox "Enter a STRONG password for the Nextcloud admin user. Remember this well!" 10 60 3>&1 1>&2 2>&3)
    if [ $? -ne 0 ]; then echo "❌ Canceled. Exiting."; exit 1; fi
fi

# Ask for Pi-hole admin password
if [ -z "${PIHOLE_PASSWORD}" ]; then
    PIHOLE_PASSWORD=$(whiptail --passwordbox "Enter a STRONG password for the Pi-hole admin interface. Remember this well!" 10 60 3>&1 1>&2 2>&3)
    if [ $? -ne 0 ]; then echo "❌ Canceled. Exiting."; exit 1; fi
fi

# Ask for Frigate RTSP username and password (used as fallback for ONVIF and general cameras)
if [ -z "${FRIGATE_RTSP_USERNAME}" ]; then
    FRIGATE_RTSP_USERNAME=$(whiptail --inputbox "Enter a default username for RTSP cameras (e.g., 'frigate_user')." 10 60 "frigate_user" 3>&1 1>&2 2>&3)
    if [ $? -ne 0 ]; then echo "❌ Canceled. Exiting."; exit 1; fi
fi

if [ -z "${FRIGATE_RTSP_PASSWORD}" ]; then
    FRIGATE_RTSP_PASSWORD=$(whiptail --passwordbox "Enter a STRONG password for the default RTSP camera user. Remember this well!" 10 60 3>&1 1>&2 2>&3)
    if [ $? -ne 0 ]; then echo "❌ Canceled. Exiting."; exit 1; fi
fi

# Ask for MQTT username and password (for Mosquitto, used by Frigate and Home Assistant)
if [ -z "${MQTT_USER}" ]; then
    MQTT_USER=$(whiptail --inputbox "Enter a username for the MQTT broker (e.g., 'mqtt_user')." 10 60 "mqtt_user" 3>&1 1>&2 2>&3)
    if [ $? -ne 0 ]; then echo "❌ Canceled. Exiting."; exit 1; fi
fi

if [ -z "${MQTT_PASS}" ]; then
    MQTT_PASS=$(whiptail --passwordbox "Enter a STRONG password for the MQTT user. Remember this well!" 10 60 3>&1 1>&2 2>&3)
    if [ $? -ne 0 ]; then echo "❌ Canceled. Exiting."; exit 1; fi
fi

echo "✅ Essential variables collected."

# --- Save environment variables to .env file ---
echo "Writing environment variables to $ENV_FILE..."
cat > "$ENV_FILE" <<EOF
# PiSelfhosting Environment Variables
# This file is automatically loaded by Docker Compose and other scripts.
# DO NOT modify this manually unless you know what you are doing.
# Use the setup.sh script to update these values.

DOMAIN="${DOMAIN}"

# MariaDB/MySQL Database Credentials
DB_USER="${DB_USER}"
DB_PASS="${DB_PASS}"

# Nextcloud Admin Credentials
NC_ADMIN_USER="${NC_ADMIN_USER}"
NC_ADMIN_PASS="${NC_ADMIN_PASS}"

# Pi-hole Admin Password
PIHOLE_PASSWORD="${PIHOLE_PASSWORD}"

# Frigate RTSP Default Credentials
FRIGATE_RTSP_USERNAME="${FRIGATE_RTSP_USERNAME}"
FRIGATE_RTSP_PASSWORD="${FRIGATE_RTSP_PASSWORD}"

# MQTT Broker Credentials (Mosquitto)
MQTT_USER="${MQTT_USER}"
MQTT_PASS="${MQTT_PASS}"

EOF
echo "✅ Environment variables saved to $ENV_FILE."


# --- Dynamically load components from components_list.txt ---
declare -a ALL_COMPONENT_NAMES_ORDERED_SETUP_SCRIPT
declare -A COMPONENT_DATA_SETUP_SCRIPT

if [ ! -f "$COMPONENTS_LIST_FILE" ]; then
    echo "❌ Component list file not found at $COMPONENTS_LIST_FILE. Setup aborted."
    exit 1
fi

# First, read COMPONENTS_ORDER
COMPONENTS_ORDER_LINE=$(grep "^COMPONENTS_ORDER=" "$COMPONENTS_LIST_FILE")
if [[ "$COMPONENTS_ORDER_LINE" =~ ^COMPONENTS_ORDER=(.*)$ ]]; then
    IFS=',' read -r -a ALL_COMPONENT_NAMES_ORDERED_SETUP_SCRIPT <<< "${BASH_REMATCH[1]}"
else
    echo "❌ COMPONENTS_ORDER not found or invalid in $COMPONENTS_LIST_FILE. Setup aborted."
    exit 1
fi

current_component_name_setup_script=""
while IFS='=' read -r key value || [ -n "$key" ]; do
    key=$(echo "$key" | xargs)
    value=$(echo "$value" | xargs)

    if [[ "$key" =~ ^\[(.+)\]$ ]]; then # New component section
        current_component_name_setup_script="${BASH_REMATCH[1]}"
    elif [[ -n "$current_component_name_setup_script" ]]; then
        COMPONENT_DATA_SETUP_SCRIPT["${current_component_name_setup_script}_${key}"]="$value"
    fi
done < "$COMPONENTS_LIST_FILE"


# --- Component selection via whiptail checklist ---
echo "--- Select components to install ---"
declare -a menu_options=()

# Always add 'docker' as an option and mark it as ON
menu_options+=("docker" "Docker CE and Docker Compose V2 (essential)" ON)

# Add other components based on components_list.txt
for comp_name in "${ALL_COMPONENT_NAMES_ORDERED_SETUP_SCRIPT[@]}"; do
    if [ "$comp_name" != "docker" ]; then # Skip 'docker', it's already added
        local display_name="${COMPONENT_DATA_SETUP_SCRIPT["${comp_name}_display_name"]}"
        local description="${COMPONENT_DATA_SETUP_SCRIPT["${comp_name}_description"]}"
        if [ -n "$display_name" ] && [ -n "$description" ]; then
            menu_options+=("$comp_name" "$display_name - $description" OFF) # Default to OFF
        fi
    fi
done

# Let the user choose components
CHOICES=$(whiptail --title "PiSelfhosting Component Selection" --checklist \
"Choose which self-hosting components you want to install (use space to select/deselect, Enter to confirm):" 25 78 15 \
"${menu_options[@]}" 3>&1 1>&2 2>&3)

if [ $? -ne 0 ]; then
    echo "❌ Component selection canceled. Exiting setup."
    exit 1
fi

# Save the selected components to a file
echo "$CHOICES" > "$COMPONENTS_FILE"
echo "✅ Selected components saved to $COMPONENTS_FILE."

echo -e "\n--- Setup complete ---"
echo "You have configured your essential variables and selected your components."
echo "The next step is to run the deployment script:"
echo "  bash $SCRIPTS_DIR/deploy.sh"
echo "This will set up the Docker environment and deploy the selected services."

# --- Helper Function: Get Docker Compose Command ---
get_docker_compose_cmd() {
    if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
        echo "docker compose"
    elif command -v docker-compose >/dev/null 2>&1; then
        echo "docker-compose"
    else
        echo ""
    fi
}

# --- Pre-deployment Cleanup ---
pre_deployment_cleanup() {
    echo "--- Initiating pre-deployment cleanup ---"
    DOCKER_COMPOSE_COMMAND=$(get_docker_compose_cmd)
    if [ -z "$DOCKER_COMPOSE_COMMAND" ]; then
        echo "❌ Error: Docker Compose (v1 or v2) not found. Please install Docker and Docker Compose."
        exit 1
    fi

    # Explicitly try to remove the problematic Mosquitto container first
    echo "Attempting to forcefully remove any existing piselfhosting-mosquitto container to prevent conflicts..."
    # START OF ADDED LINE
    sudo docker rm -f piselfhosting-mosquitto &>/dev/null || true
    # END OF ADDED LINE
    echo "Forceful removal attempt complete (may show no output if not found or already removed)."

    echo "Stopping and removing all existing PiSelfhosting containers and associated volumes..."
    # The --rmi all option is removed as it's not applicable here and causes issues.
    # We should only remove images explicitly created by the project.
    (cd "$BASE_DIR" && $DOCKER_COMPOSE_COMMAND down --volumes --remove-orphans) || {
        echo "⚠️ Warning: Some containers might not have stopped/removed cleanly. Proceeding..."
    }

    # Remove symlinks to .env files in service directories
    echo "Removing old .env symlinks in service directories..."
    for dir in "$DOCKER_COMPOSE_DIR"/*/; do
        if [ -L "${dir}.env" ]; then
            rm "${dir}.env"
        fi
    done
    echo "--- Pre-deployment cleanup complete ---"
}

# --- Docker Network Check/Creation ---
ensure_docker_network() {
    echo "Ensuring Docker network 'piselfhosting_net' exists..."
    docker network create piselfhosting_net || echo "Network 'piselfhosting_net' already exists or creation failed for another reason (continuing)."
    echo "✅ Docker network check complete."
}

# --- Helper Function: Initialize Configuration File ---
init_config_file() {
    local service_name=$1
    local template_path=$2
    local dest_path=$3
    local overwrite_mode=$4 # 'all', 'select', 'create_if_missing', 'skip_all'

    # Ensure parent directory exists for the destination file
    sudo mkdir -p "$(dirname "$dest_path")"

    if [ "$overwrite_mode" = "skip_all" ]; then
        echo "  Skipping config for ${service_name} at ${dest_path} (skip_all mode)."
        return
    }

    if [ -f "$dest_path" ]; then
        case "$overwrite_mode" in
            "all")
                echo "  Overwriting existing config for ${service_name} at ${dest_path} (all mode)."
                sudo envsubst < "$template_path" | sudo tee "$dest_path" > /dev/null
                ;;
            "select")
                local prompt="Overwrite ${service_name} config at ${dest_path}?"
                if (whiptail --yesno "$prompt" 10 60 --defaultno 3>&1 1>&2 2>&3); then
                    echo "  Overwriting selected config for ${service_name} at ${dest_path}."
                    sudo envsubst < "$template_path" | sudo tee "$dest_path" > /dev/null
                else
                    echo "  Skipping overwrite for ${service_name} config at ${dest_path} (user skipped)."
                fi
                ;;
            "create_if_missing")
                echo "  Config for ${service_name} already exists at ${dest_path}. Skipping (create_if_missing mode)."
                ;;
            *)
                echo "  Unknown overwrite mode. Skipping config for ${service_name} at ${dest_path}."
                ;;
        esac
    else
        echo "  Creating new config for ${service_name} at ${dest_path}."
        sudo envsubst < "$template_path" | sudo tee "$dest_path" > /dev/null
    fi
    if [ $? -ne 0 ]; then
        echo "❌ Failed to create/update config file for ${service_name}. Check permissions at ${dest_path}."
        exit 1
    fi
}

# --- Function to Deploy a Component ---
deploy_component() {
    local service_name=$1
    local compose_template=$2
    local config_template_dir=$3 # Directory on host with config templates for this service
    local container_config_dir=$4 # Path inside container where config should go (e.g., /config, /etc/mosquitto)
    local overwrite_mode=$5

    local service_dir="${DOCKER_COMPOSE_DIR}/${service_name}"
    local docker_compose_file="${service_dir}/docker-compose.yml"

    echo "--- Deploying component: ${service_name} ---"

    # Create service directory
    sudo mkdir -p "$service_dir"
    echo "  Ensured directory: $service_dir"

    # Symlink .env file into service directory
    if [ ! -L "${service_dir}/.env" ]; then
        ln -s "$ENV_FILE" "${service_dir}/.env"
        echo "  Symlinked .env to $service_dir"
    else
        echo "  .env symlink already exists for $service_dir"
    fi

    # Generate docker-compose.yml for the service
    echo "  Generating docker-compose.yml for ${service_name}..."
    sudo envsubst < "$compose_template" | sudo tee "$docker_compose_file" > /dev/null
    if [ $? -ne 0 ]; then
        echo "❌ Failed to generate docker-compose.yml for ${service_name}. Check permissions."
        exit 1
    fi
    echo "  ✅ Generated docker-compose.yml at: $docker_compose_file"

    # Handle service-specific configurations
    case "$service_name" in
        "mariadb")
            init_config_file "${service_name}" "${config_template_dir}/initdb.d/init.sql.template" "${service_dir}/initdb.d/init.sql" "$overwrite_mode"
            ;;
        "mosquitto")
            init_config_file "${service_name}" "${config_template_dir}/config/mosquitto.conf.template" "${service_dir}/config/mosquitto.conf" "$overwrite_mode"
            # Set specific permissions for Mosquitto's data and config volumes on the host
            echo "  Setting permissions for Mosquitto volumes..."
            sudo chown -R 1883:1883 "${service_dir}/config" "${service_dir}/data" "${service_dir}/log" || true
            sudo chmod -R 775 "${service_dir}/data" "${service_dir}/log" || true
            # Ensure config file is readable by the Mosquitto user (UID 1883)
            sudo chmod 644 "${service_dir}/config/mosquitto.conf" || true
            sudo chmod 755 "${service_dir}/config" || true # Ensure directory is traversable
            echo "  ✅ Mosquitto permissions set."
            ;;
        "frigate")
            init_config_file "${service_name}" "${config_template_dir}/config/config.yml.template" "${service_dir}/config/config.yml" "$overwrite_mode"
            # Ensure /media/frigate exists on the host
            echo "  Ensuring /media/frigate directory exists for Frigate..."
            sudo mkdir -p /media/frigate
            sudo chown -R 1000:1000 /media/frigate || true # Often Frigate runs as UID 1000, adjust if needed
            echo "  ✅ /media/frigate directory ensured."
            ;;
        "pihole")
            # No specific config file to copy directly, it's managed via environment variables
            ;;
        "dashy")
            init_config_file "${service_name}" "${config_template_dir}/config/conf.yml.template" "${service_dir}/config/conf.yml" "$overwrite_mode"
            # PUID/PGID are handled by environment variables in docker-compose.yml
            ;;
        "docker-monitor")
            init_config_file "${service_name}" "${config_template_dir}/html/index.1.html.template" "${service_dir}/html/index.html" "$overwrite_mode"
            ;;
        "piselfhosting-docs")
            init_config_file "${service_name}" "${config_template_dir}/html/index.html.template" "${service_dir}/html/index.html" "$overwrite_mode"
            ;;
        "mailserver")
            # These are handled by the separate mailserver_config_tool.py script
            # Ensure the config directories exist on the host side for the tool to write into
            sudo mkdir -p "${service_dir}/exim4/config" "${service_dir}/dovecot/config/conf.d"
            ;;
        # Add other service-specific config initializations here if needed
    esac

    echo "--- Component ${service_name} deployed ---"
}

# --- Main Deployment Logic ---
echo -e "\n--- Starting PiSelfhosting Deployment ---"

# Prompt for overwrite mode
OVERWRITE_MODE=$(whiptail --radiolist "Select Configuration Overwrite Mode:" 15 78 4 \
"all" "Overwrite ALL existing configuration files" ON \
"select" "Select which existing files to overwrite (missing files are created)" OFF \
"create_if_missing" "Only create config files if they don't exist (preserve existing)" OFF \
"skip_all" "Do NOT create or overwrite any config files" OFF 3>&1 1>&2 2>&3)

if [ $? -ne 0 ]; then
    echo "❌ Configuration overwrite selection canceled. Exiting deployment."
    exit 1
fi
echo "Info: Selected overwrite mode: $OVERWRITE_MODE"

pre_deployment_cleanup # Run cleanup before attempting to deploy anything
ensure_docker_network  # Ensure the shared network exists

# Read selected components from the file
if [ ! -f "$COMPONENTS_FILE" ]; then
    echo "❌ Selected components file not found at $COMPONENTS_FILE. Please run setup.sh first."
    exit 1
fi

SELECTED_COMPONENTS=$(cat "$COMPONENTS_FILE" | tr -d '"')

# Define component deployment order to handle dependencies
# This list specifies the order in which services should be processed by this script.
# Dependencies (e.g., MariaDB before Nextcloud) are crucial for successful startup.
DEPLOYMENT_ORDER=(
    "mariadb"
    "mosquitto"
    "nginxproxymanager" # Depends on mariadb
    "nextcloud"         # Depends on mariadb
    "phpmyadmin"        # Depends on mariadb
    "homeassistant"
    "frigate"           # Depends on mosquitto
    "pihole"
    "portainer"
    "dashy"
    "docker-monitor"
    "piselfhosting-docs"
    "mailserver" # Requires Dockerfiles in its directory to be built separately
)

declare -A COMPONENTS_TO_DEPLOY # Associative array to easily check if a component is selected

for comp_name in $SELECTED_COMPONENTS; do
    COMPONENTS_TO_DEPLOY["$comp_name"]="true"
done

echo "--- Deploying selected components ---"

for service_name in "${DEPLOYMENT_ORDER[@]}"; do
    if [ "${COMPONENTS_TO_DEPLOY[$service_name]}" = "true" ]; then
        # Dynamically determine the template path based on service_name
        case "$service_name" in
            "mariadb")
                deploy_component "$service_name" "${SCRIPTS_DIR}/templates/mariadb/docker-compose.yml.template" "${SCRIPTS_DIR}/templates/mariadb" "/docker-entrypoint-initdb.d" "$OVERWRITE_MODE"
                ;;
            "mosquitto")
                deploy_component "$service_name" "${SCRIPTS_DIR}/templates/mosquitto/docker-compose.yml.template" "${SCRIPTS_DIR}/templates/mosquitto" "/mosquitto" "$OVERWRITE_MODE"
                ;;
            "nextcloud")
                deploy_component "$service_name" "${SCRIPTS_DIR}/templates/nextcloud/docker-compose.yml.template" "${SCRIPTS_DIR}/templates/nextcloud" "/var/www/html" "$OVERWRITE_MODE"
                ;;
            "homeassistant")
                deploy_component "$service_name" "${SCRIPTS_DIR}/templates/homeassistant/docker-compose.yml.template" "${SCRIPTS_DIR}/templates/homeassistant" "/config" "$OVERWRITE_MODE"
                ;;
            "frigate")
                deploy_component "$service_name" "${SCRIPTS_DIR}/templates/frigate/docker-compose.yml.template" "${SCRIPTS_DIR}/templates/frigate" "/config" "$OVERWRITE_MODE"
                ;;
            "pihole")
                deploy_component "$service_name" "${SCRIPTS_DIR}/templates/pihole/docker-compose.yml.template" "${SCRIPTS_DIR}/templates/pihole" "/etc/pihole" "$OVERWRITE_MODE"
                ;;
            "portainer")
                deploy_component "$service_name" "${SCRIPTS_DIR}/templates/portainer/docker-compose.yml.template" "${SCRIPTS_DIR}/templates/portainer" "/data" "$OVERWRITE_MODE"
                ;;
            "dashy")
                deploy_component "$service_name" "${SCRIPTS_DIR}/templates/dashy/docker-compose.yml.template" "${SCRIPTS_DIR}/templates/dashy" "/app/public/conf" "$OVERWRITE_MODE"
                ;;
            "phpmyadmin")
                deploy_component "$service_name" "${SCRIPTS_DIR}/templates/phpmyadmin/docker-compose.yml.template" "${SCRIPTS_DIR}/templates/phpmyadmin" "" "$OVERWRITE_MODE" # No specific config dir in container for phpMyAdmin
                ;;
            "nginxproxymanager")
                deploy_component "$service_name" "${SCRIPTS_DIR}/templates/nginxproxymanager/docker-compose.yml.template" "${SCRIPTS_DIR}/templates/nginxproxymanager" "/data" "$OVERWRITE_MODE"
                ;;
            "docker-monitor")
                deploy_component "$service_name" "${SCRIPTS_DIR}/templates/docker-monitor/docker-compose.yml.template" "${SCRIPTS_DIR}/templates/docker-monitor" "/usr/share/nginx/html" "$OVERWRITE_MODE"
                ;;
            "piselfhosting-docs")
                deploy_component "$service_name" "${SCRIPTS_DIR}/templates/piselfhosting-docs/docker-compose.yml.template" "${SCRIPTS_DIR}/templates/piselfhosting-docs" "/usr/share/nginx/html" "$OVERWRITE_MODE"
                ;;
            "mailserver")
                 deploy_component "$service_name" "${SCRIPTS_DIR}/templates/mailserver/docker-compose.yml.template" "${SCRIPTS_DIR}/templates/mailserver" "" "$OVERWRITE_MODE" # Config handled by separate tool
                 # Create Dockerfiles for Exim4 and Dovecot if they don't exist
                 sudo mkdir -p "${DOCKER_COMPOSE_DIR}/mailserver/exim4" "${DOCKER_COMPOSE_DIR}/mailserver/dovecot"
                 init_config_file "${service_name}/exim4" "${SCRIPTS_DIR}/templates/mailserver/exim4/Dockerfile.template" "${DOCKER_COMPOSE_DIR}/mailserver/exim4/Dockerfile" "$OVERWRITE_MODE"
                 init_config_file "${service_name}/dovecot" "${SCRIPTS_DIR}/templates/mailserver/dovecot/Dockerfile.template" "${DOCKER_COMPOSE_DIR}/mailserver/dovecot/Dockerfile" "$OVERWRITE_MODE"
                 echo "  Run 'bash ${SCRIPTS_DIR}/run-mailserver-config-tool.sh' to configure mailserver."
                 ;;
            *)
                echo "Warning: No deployment logic found for service: ${service_name}. Skipping."
                ;;
        esac
    fi
DOCKER_COMPOSE_COMMAND=$(get_docker_compose_cmd) # Re-get in case something changed
done

# --- Generate Helper Scripts ---
echo -e "\n--- Generating helper scripts ---"

# --- start-all.sh ---
cat > "$SCRIPTS_DIR/start-all.sh" << 'EOF'
#!/bin/bash

# This script is responsible for starting all selected PiSelfhosting Docker containers.

# Exit immediately if a command exits with a non-zero status.
set -e

BASE_DIR="/home/PiSelfhosting"
DOCKER_COMPOSE_DIR="${BASE_DIR}/docker"
SCRIPTS_DIR="${BASE_DIR}/scripts"
COMPONENTS_FILE="${SCRIPTS_DIR}/selected_components.txt"

# --- Helper Function: Get Docker Compose Command ---
get_docker_compose_cmd() {
    if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
        echo "docker compose"
    elif command -v docker-compose >/dev/null 2>&1; then
        echo "docker-compose"
    else
        echo ""
    fi
}

DOCKER_COMPOSE_COMMAND=$(get_docker_compose_cmd)
if [ -z "$DOCKER_COMPOSE_COMMAND" ]; then
    echo "❌ Error: Docker Compose (v1 or v2) not found. Please install Docker and Docker Compose."
    exit 1
fi

echo "--- Starting PiSelfhosting containers ---"

if [ ! -f "$COMPONENTS_FILE" ]; then
    echo "❌ Selected components file not found at $COMPONENTS_FILE. Please run setup.sh first."
    exit 1
fi

SELECTED_COMPONENTS=$(cat "$COMPONENTS_FILE" | tr -d '"')

# Define service startup order to handle dependencies
STARTUP_ORDER=(
    "mariadb"
    "mosquitto"
    "nginxproxymanager"
    "nextcloud"
    "phpmyadmin"
    "homeassistant"
    "frigate"
    "pihole"
    "portainer"
    "dashy"
    "docker-monitor"
    "piselfhosting-docs"
    "exim4" # Part of mailserver
    "dovecot" # Part of mailserver
)

# Use an associative array for quick lookup of selected components
declare -A IS_SELECTED

for comp in $SELECTED_COMPONENTS; do
    IS_SELECTED["$comp"]="true"
done

# Loop through services in the defined order and start them if selected
for service_name in "${STARTUP_ORDER[@]}"; do
    # For mailserver, check for exim4 or dovecot directly as they are sub-services
    if [[ "$service_name" == "exim4" || "$service_name" == "dovecot" ]]; then
        if [ "${IS_SELECTED["mailserver"]}" != "true" ]; then
            continue # Skip exim4/dovecot if mailserver wasn't selected
        fi
    fi

    if [ "${IS_SELECTED["$service_name"]}" = "true" ] || [[ "$service_name" == "exim4" && "${IS_SELECTED["mailserver"]}" == "true" ]] || [[ "$service_name" == "dovecot" && "${IS_SELECTED["mailserver"]}" == "true" ]]; then
        local service_dir="${DOCKER_COMPOSE_DIR}/${service_name}"
        if [ ! -d "$service_dir" ]; then
            # If the service directory doesn't exist, it means this component was not deployed
            # or is a sub-service (exim4/dovecot) whose parent (mailserver) was not deployed.
            # In either case, we skip.
            echo "  Skipping startup for ${service_name}: deployment directory not found."
            continue
        fi

        echo "  Starting ${service_name}..."
        (cd "$service_dir" && $DOCKER_COMPOSE_COMMAND up -d "$service_name") || {
            echo "❌ Failed to start ${service_name}. Check logs: docker logs piselfhosting-${service_name}"
        }

        # Add a delay for services that need time to initialize
        if [ "$service_name" == "mariadb" ]; then
            echo "  Waiting for MariaDB to be ready..."
            # Adjust the host and port for the check if MariaDB is not on host network (which it isn't here, it's on piselfhosting_net)
            # We can't directly check the container's port from the host easily without knowing its internal IP.
            # A simpler way is to wait for a specific log message in the container indicating readiness.
            # This is a basic waiting mechanism. For production, consider Docker's HEALTHCHECK.
            local max_attempts=30
            local attempt=0
            local ready=false
            while [ $attempt -lt $max_attempts ]; do
                if docker logs piselfhosting-mariadb 2>&1 | grep -q "ready for connections"; then
                    echo "  ✅ MariaDB is ready."
                    ready=true
                    break
                fi
                echo "  Still waiting for MariaDB to be ready... ($((max_attempts - attempt))s remaining)"
                sleep 1
                attempt=$((attempt + 1))
            done
            if [ "$ready" = false ]; then
                echo "❌ MariaDB did not become ready in time. Services depending on it may fail."
            fi
        elif [ "$service_name" == "mosquitto" ]; then
            echo "  Waiting for Mosquitto to be ready..."
            local max_attempts=20
            local attempt=0
            local ready=false
            while [ $attempt -lt $max_attempts ]; do
                if docker logs piselfhosting-mosquitto 2>&1 | grep -q "mosquitto version .* running"; then
                    echo "  ✅ Mosquitto is ready."
                    ready=true
                    break
                fi
                echo "  Still waiting for Mosquitto (log check) ($((max_attempts - attempt))s remaining)"
                sleep 1
                attempt=$((attempt + 1))
            done
            if [ "$ready" = false ]; then
                echo "❌ Mosquitto did not become ready in time. Services depending on it may fail."
            fi
        elif [ "$service_name" == "pihole" ]; then
            echo "  Waiting for Pi-hole to be healthy..."
            local max_attempts=30
            local attempt=0
            local healthy=false
            while [ $attempt -lt $max_attempts ]; do
                if docker inspect --format='{{.State.Health.Status}}' piselfhosting-pihole | grep -q "healthy"; then
                    echo "  ✅ Pi-hole is healthy."
                    healthy=true
                    break
                fi
                echo "  Still waiting for Pi-hole to be healthy... ($((max_attempts - attempt))s remaining)"
                sleep 1
                attempt=$((attempt + 1))
            done
            if [ "$healthy" = false ]; then
                echo "❌ Pi-hole did not become healthy in time."
            fi
        fi
    fi
done

echo "--- All selected PiSelfhosting containers started or attempted ---"
echo "You can check their status with: docker ps"
EOF
chmod +x "$SCRIPTS_DIR/start-all.sh"
echo "✅ Generated start-all.sh"

# --- stop-all.sh ---
cat > "$SCRIPTS_DIR/stop-all.sh" << 'EOF'
#!/bin/bash

# This script is responsible for stopping and removing all selected PiSelfhosting Docker containers.

# Exit immediately if a command exits with a non-zero status.
set -e

# Define base directory
BASE_DIR="$(dirname "$(dirname "$(readlink -f "$0")")")"
DOCKER_COMPOSE_DIR="${BASE_DIR}/docker"
ENV_FILE="${BASE_DIR}/.env" # Load .env

# --- Load environment variables ---
if [ -f "${ENV_FILE}" ]; then
    echo "Loading existing .env file..."
    source "${ENV_FILE}"
else
    echo "Error: .env file not found at ${ENV_FILE}. Cannot proceed with stopping services."
    exit 1
fi

echo "Stopping PiSelfhosting containers..."

# Define common Docker Compose command
DOCKER_COMPOSE_COMMAND="docker compose"

# Define a list of all potential service names that might be running
ALL_KNOWN_SERVICES=(
    "mariadb" "mosquitto" "nextcloud" "homeassistant" "frigate" "portainer"
    "dashy" "pihole" "docker-monitor" "phpmyadmin" "nginxproxymanager" "mailserver"
    "piselfhosting-docs" # Added piselfhosting-docs to the list of known services
    "exim4" # Added mailserver sub-services for explicit stop/rm
    "dovecot" # Added mailserver sub-services for explicit stop/rm
)

for service_name in "${ALL_KNOWN_SERVICES[@]}"; do
    # Determine the correct directory for docker compose, handling 'mailserver' as a parent
    local current_service_dir
    if [[ "$service_name" == "exim4" || "$service_name" == "dovecot" ]]; then
        current_service_dir="${DOCKER_COMPOSE_DIR}/mailserver"
    else
        current_service_dir="${DOCKER_COMPOSE_DIR}/${service_name}"
    fi

    if [ -d "${current_service_dir}" ]; then
        echo "  Stopping and removing container for ${service_name} in ${current_service_dir}..."
        # Stop and remove the container, suppress output for non-existent containers
        # Use || true to prevent script from exiting if container is already stopped/removed
        (cd "${current_service_dir}" && ${DOCKER_COMPOSE_COMMAND} stop "${service_name}" &>/dev/null) || true
        (cd "${current_service_dir}" && ${DOCKER_COMPOSE_COMMAND} rm -f "${service_name}" &>/dev/null) || true
    else
        echo "  Info: Directory for ${service_name} not found (${current_service_dir}), skipping removal."
    fi
done

echo "✅ All PiSelfhosting containers stopped and removed."
echo "You can check their status with: docker ps -a"
EOF
chmod +x "$SCRIPTS_DIR/stop-all.sh"
echo "✅ Generated stop-all.sh"

# --- restart-all.sh ---
cat > "$SCRIPTS_DIR/restart-all.sh" << 'EOF'
#!/bin/bash

# This script stops and then starts all (or specified) PiSelfhosting Docker containers.

# Exit immediately if a command exits with a non-zero status.
set -e

BASE_DIR="/home/PiSelfhosting"
DOCKER_COMPOSE_DIR="${BASE_DIR}/docker"
SCRIPTS_DIR="${BASE_DIR}/scripts"
COMPONENTS_FILE="${SCRIPTS_DIR}/selected_components.txt"

# --- Helper Function: Get Docker Compose Command ---
get_docker_compose_cmd() {
    if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
        echo "docker compose"
    elif command -v docker-compose >/dev/null 2>&1; then
        echo "docker-compose"
    else
        echo ""
    fi
}

DOCKER_COMPOSE_COMMAND=$(get_docker_compose_cmd)
if [ -z "$DOCKER_COMPOSE_COMMAND" ]; then
    echo "❌ Error: Docker Compose (v1 or v2) not found. Please install Docker and Docker Compose."
    exit 1
fi

TARGET_SERVICE="$1" # Optional: specify a single service to restart

echo "--- Restarting PiSelfhosting containers ---"

if [ ! -f "$COMPONENTS_FILE" ]; then
    echo "❌ Selected components file not found at $COMPONENTS_FILE. Please run setup.sh first."
    exit 1
fi

SELECTED_COMPONENTS=$(cat "$COMPONENTS_FILE" | tr -d '"')

# Define service startup order to handle dependencies
RESTART_ORDER=(
    "mariadb"
    "mosquitto"
    "nginxproxymanager"
    "nextcloud"
    "phpmyadmin"
    "homeassistant"
    "frigate"
    "pihole"
    "portainer"
    "dashy"
    "docker-monitor"
    "piselfhosting-docs"
    "exim4" # Part of mailserver
    "dovecot" # Part of mailserver
)

# Use an associative array for quick lookup of selected components
declare -A IS_SELECTED

for comp in $SELECTED_COMPONENTS; do
    IS_SELECTED["$comp"]="true"
done

for service_name in "${RESTART_ORDER[@]}"; do
    # Determine the correct directory for docker compose, handling 'mailserver' as a parent
    local current_service_dir
    local actual_service_name="$service_name" # The name for docker compose up/stop/rm

    if [[ "$service_name" == "exim4" || "$service_name" == "dovecot" ]]; then
        current_service_dir="${DOCKER_COMPOSE_DIR}/mailserver"
        if [ "${IS_SELECTED["mailserver"]}" != "true" ]; then
            continue # Skip exim4/dovecot if mailserver wasn't selected
        fi
    else
        current_service_dir="${DOCKER_COMPOSE_DIR}/${service_name}"
        if [ "${IS_SELECTED["$service_name"]}" != "true" ]; then
            continue # Skip if component not selected
        fi
    fi

    # If a specific service is targeted, and it's not this one, skip
    if [ -n "$TARGET_SERVICE" ] && [ "$TARGET_SERVICE" != "$actual_service_name" ] && [ "$TARGET_SERVICE" != "all" ]; then
        if [[ "$actual_service_name" != "exim4" && "$actual_service_name" != "dovecot" ]] || [[ "$TARGET_SERVICE" != "mailserver" ]]; then
            continue
        fi
    fi

    if [ ! -d "$current_service_dir" ]; then
        echo "  Skipping restart for ${service_name}: deployment directory not found."
        continue
    fi

    echo "  Restarting ${service_name}..."
    # Stop, remove, then start to ensure latest config/image (if image pull is configured)
    (cd "$current_service_dir" && ${DOCKER_COMPOSE_COMMAND} stop "$actual_service_name" &>/dev/null) || true
    (cd "$current_service_dir" && ${DOCKER_COMPOSE_COMMAND} rm -f "$actual_service_name" &>/dev/null) || true
    
    # For mailserver sub-services, we need to rebuild them if there are Dockerfile changes
    if [[ "$actual_service_name" == "exim4" || "$actual_service_name" == "dovecot" ]]; then
        echo "  Rebuilding mailserver component image for ${actual_service_name}..."
        (cd "$current_service_dir" && ${DOCKER_COMPOSE_COMMAND} build "$actual_service_name") || {
            echo "❌ Failed to rebuild image for ${actual_service_name}. Check Dockerfile or build logs."
            # Don't exit, try to continue starting
        }
    fi

    (cd "$current_service_dir" && ${DOCKER_COMPOSE_COMMAND} up -d "$actual_service_name") || {
        echo "❌ Failed to start ${service_name}. Check logs: docker logs piselfhosting-${actual_service_name}"
    }

    # Add a delay for services that need time to initialize
    if [ "$actual_service_name" == "mariadb" ]; then
        echo "  Waiting for MariaDB to be ready..."
        local max_attempts=30
        local attempt=0
        local ready=false
        while [ $attempt -lt $max_attempts ]; do
            if docker logs piselfhosting-mariadb 2>&1 | grep -q "ready for connections"; then
                echo "  ✅ MariaDB is ready."
                ready=true
                break
            fi
            echo "  Still waiting for MariaDB to be ready... ($((max_attempts - attempt))s remaining)"
            sleep 1
            attempt=$((attempt + 1))
        done
        if [ "$ready" = false ]; then
            echo "❌ MariaDB did not become ready in time. Services depending on it may fail."
        fi
    elif [ "$actual_service_name" == "mosquitto" ]; then
        echo "  Waiting for Mosquitto to be ready..."
        local max_attempts=20
        local attempt=0
        local ready=false
        while [ $attempt -lt $max_attempts ]; do
            if docker logs piselfhosting-mosquitto 2>&1 | grep -q "mosquitto version .* running"; then
                echo "  ✅ Mosquitto is ready."
                ready=true
                break
            fi
            echo "  Still waiting for Mosquitto (log check) ($((max_attempts - attempt))s remaining)"
            sleep 1
            attempt=$((attempt + 1))
        done
        if [ "$ready" = false ]; then
            echo "❌ Mosquitto did not become ready in time. Services depending on it may fail."
        fi
    elif [ "$actual_service_name" == "pihole" ]; then
        echo "  Waiting for Pi-hole to be healthy..."
        local max_attempts=30
        local attempt=0
        local healthy=false
        while [ $attempt -lt $max_attempts ]; do
            if docker inspect --format='{{.State.Health.Status}}' piselfhosting-pihole | grep -q "healthy"; then
                echo "  ✅ Pi-hole is healthy."
                healthy=true
                break
            fi
            echo "  Still waiting for Pi-hole to be healthy... ($((max_attempts - attempt))s remaining)"
            sleep 1
            attempt=$((attempt + 1))
        done
        if [ "$healthy" = false ]; then
            echo "❌ Pi-hole did not become healthy in time."
        fi
    fi
done

echo "--- All selected PiSelfhosting containers restarted or attempted ---"
echo "You can check their status with: docker ps"
EOF
chmod +x "$SCRIPTS_DIR/restart-all.sh"
echo "✅ Generated restart-all.sh"

# --- remove-component.sh ---
cat > "$SCRIPTS_DIR/remove-component.sh" << 'EOF'
#!/bin/bash

# This script allows you to remove specific PiSelfhosting Docker components.

# Exit immediately if a command exits with a non-zero status.
set -e

BASE_DIR="/home/PiSelfhosting"
DOCKER_COMPOSE_DIR="${BASE_DIR}/docker"
SCRIPTS_DIR="${BASE_DIR}/scripts"
COMPONENTS_FILE="${SCRIPTS_DIR}/selected_components.txt"

# --- Helper Function: Get Docker Compose Command ---
get_docker_compose_cmd() {
    if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
        echo "docker compose"
    elif command -v docker-compose >/dev/null 2>&1; then
        echo "docker-compose"
    else
        echo ""
    fi
}

DOCKER_COMPOSE_COMMAND=$(get_docker_compose_cmd)
if [ -z "$DOCKER_COMPOSE_COMMAND" ]; then
    echo "❌ Error: Docker Compose (v1 or v2) not found. Please install Docker and Docker Compose."
    exit 1
fi

echo "--- Remove PiSelfhosting Component ---"

if [ ! -f "$COMPONENTS_FILE" ]; then
    echo "❌ Selected components file not found at $COMPONENTS_FILE. Please run setup.sh first."
    exit 1
fi

SELECTED_COMPONENTS=$(cat "$COMPONENTS_FILE" | tr -d '"')

declare -a MENU_OPTIONS=()
declare -A CURRENTLY_SELECTED_MAP

# Prepare menu options based on currently selected components
for comp in $SELECTED_COMPONENTS; do
    MENU_OPTIONS+=("$comp" "Currently installed component" OFF)
    CURRENTLY_SELECTED_MAP["$comp"]="true"
done

if [ ${#MENU_OPTIONS[@]} -eq 0 ]; then
    echo "No components are currently selected or installed to remove."
    echo "Exiting."
    exit 0
fi

# Show a checklist of currently deployed components
COMPONENT_TO_REMOVE=$(whiptail --title "Remove PiSelfhosting Component" --radiolist \
"Select the component you wish to STOP and REMOVE COMPLETELY (including its data volumes):" 20 78 10 \
"${MENU_OPTIONS[@]}" 3>&1 1>&2 2>&3)

if [ $? -ne 0 ]; then
    echo "❌ Component removal canceled."
    exit 0
fi

echo "You selected to remove: $COMPONENT_TO_REMOVE"

# Confirmation
if (whiptail --yesno "Are you SURE you want to STOP and REMOVE ALL data for ${COMPONENT_TO_REMOVE}? This action is IRREVERSIBLE." 10 60 --defaultno 3>&1 1>&2 2>&3); then
    echo "Proceeding with removal of ${COMPONENT_TO_REMOVE}..."
else
    echo "Component removal canceled by user."
    exit 0
fi

# Handle removal based on component type (e.g., mailserver has sub-services)
case "$COMPONENT_TO_REMOVE" in
    "mailserver")
        # For mailserver, stop and remove its sub-services (exim4, dovecot)
        echo "  Stopping and removing Exim4 (part of Mailserver)..."
        (cd "${DOCKER_COMPOSE_DIR}/mailserver" && ${DOCKER_COMPOSE_COMMAND} down exim4 --volumes --remove-orphans &>/dev/null) || true
        echo "  Stopping and removing Dovecot (part of Mailserver)..."
        (cd "${DOCKER_COMPOSE_DIR}/mailserver" && ${DOCKER_COMPOSE_COMMAND} down dovecot --volumes --remove-orphans &>/dev/null) || true
        echo "  Removing Mailserver Docker Compose directory and its contents..."
        sudo rm -rf "${DOCKER_COMPOSE_DIR}/mailserver"
        ;;
    *)
        # For other single-service components
        local service_dir="${DOCKER_COMPOSE_DIR}/${COMPONENT_TO_REMOVE}"
        if [ -d "$service_dir" ]; then
            echo "  Stopping and removing ${COMPONENT_TO_REMOVE}..."
            (cd "$service_dir" && ${DOCKER_COMPOSE_COMMAND} down --volumes --remove-orphans &>/dev/null) || true
            echo "  Removing ${COMPONENT_TO_REMOVE} Docker Compose directory and its contents..."
            sudo rm -rf "$service_dir"
        else
            echo "  Directory for ${COMPONENT_TO_REMOVE} not found. Already removed or never deployed?"
        fi
        ;;
esac

# Update selected_components.txt to reflect the removal
UPDATED_SELECTED_COMPONENTS=""
for comp in $SELECTED_COMPONENTS; do
    if [ "$comp" != "$COMPONENT_TO_REMOVE" ]; then
        UPDATED_SELECTED_COMPONENTS+="\"$comp\" "
    fi
done
echo "$UPDATED_SELECTED_COMPONENTS" > "$COMPONENTS_FILE"
echo "✅ ${COMPONENT_TO_REMOVE} has been removed and unselected from future deployments."
echo "You can verify with: docker ps -a"
EOF
chmod +x "$SCRIPTS_DIR/remove-component.sh"
echo "✅ Generated remove-component.sh"

# --- update-docker-stats.sh ---
cat > "$SCRIPTS_DIR/update-docker-stats.sh" << 'EOF'
#!/bin/bash

# This script fetches Docker container statistics and generates an HTML file.
# It's intended to be run periodically, e.g., via a cron job.

# Exit immediately if a command exits with a non-zero status.
set -e

BASE_DIR="/home/PiSelfhosting"
DOCKER_MONITOR_HTML_DIR="${BASE_DIR}/docker/docker-monitor/html"
HTML_OUTPUT_FILE="${DOCKER_MONITOR_HTML_DIR}/index.html" # Overwrite the template

# Ensure the output directory exists
mkdir -p "$DOCKER_MONITOR_HTML_DIR"

# Get current timestamp
LAST_UPDATED_TIME=$(date '+%Y-%m-%d %H:%M:%S %Z')

# Generate the table rows dynamically
STATS_ROWS=""
# Get stats for all PiSelfhosting containers
while IFS= read -r line; do
    # Skip header line
    if [[ "$line" == CONTAINER* ]]; then
        continue
    fi

    CONTAINER_ID=$(echo "$line" | awk '{print $1}')
    NAME=$(echo "$line" | awk '{print $NF}') # Last column is NAME
    STATUS_FULL=$(echo "$line" | awk '{$1=$2=$3=$4=$5=$6=""; print $0}' | sed -E 's/  +/ /g' | xargs | cut -d' ' -f4- | sed 's/ (healthy)//;s/ (unhealthy)//;s/ (starting)//')
    IMAGE=$(echo "$line" | awk '{print $2}')
    CPU_USAGE=$(docker stats --no-stream --format "{{.CPUPerc}}" "$CONTAINER_ID" 2>/dev/null || echo "N/A")
    MEM_USAGE=$(docker stats --no-stream --format "{{.MemUsage}}" "$CONTAINER_ID" 2>/dev/null || echo "N/A")
    NET_IO=$(docker stats --no-stream --format "{{.NetIO}}" "$CONTAINER_ID" 2>/dev/null || echo "N/A")
    BLOCK_IO=$(docker stats --no-stream --format "{{.BlockIO}}" "$CONTAINER_ID" 2>/dev/null || echo "N/A")

    # Determine status class for styling
    STATUS_CLASS="text-gray-600"
    if [[ "$STATUS_FULL" == Up* ]]; then
        STATUS_CLASS="status-running"
    elif [[ "$STATUS_FULL" == Exited* ]]; then
        STATUS_CLASS="status-exited"
    elif [[ "$STATUS_FULL" == Paused* ]]; then
        STATUS_CLASS="status-paused"
    fi

    # Escape HTML special characters in values for display
    NAME_ESC=$(echo "$NAME" | sed 's/&/\&amp;/g; s/</\&lt;/g; s/>/\&gt;/g; s/"/\&quot;/g; s/'"'"'/\&#39;/g')
    IMAGE_ESC=$(echo "$IMAGE" | sed 's/&/\&amp;/g; s/</\&lt;/g; s/>/\&gt;/g; s/"/\&quot;/g; s/'"'"'/\&#39;/g')
    STATUS_FULL_ESC=$(echo "$STATUS_FULL" | sed 's/&/\&amp;/g; s/</\&lt;/g; s/>/\&gt;/g; s/"/\&quot;/g; s/'"'"'/\&#39;/g')

    STATS_ROWS+="
            <tr class='border-b border-gray-200'>
                <td data-label='Name' class='py-3 px-4'>${NAME_ESC}</td>
                <td data-label='Image' class='py-3 px-4 text-sm text-gray-500'>${IMAGE_ESC}</td>
                <td data-label='Status' class='py-3 px-4'><span class='${STATUS_CLASS} font-semibold'>${STATUS_FULL_ESC}</span></td>
                <td data-label='CPU' class='py-3 px-4 metric'>${CPU_USAGE}</td>
                <td data-label='Memory' class='py-3 px-4 metric'>${MEM_USAGE}</td>
                <td data-label='Net I/O' class='py-3 px-4 text-sm'>${NET_IO}</td>
                <td data-label='Block I/O' class='py-3 px-4 text-sm'>${BLOCK_IO}</td>
            </tr>"
done < <(docker ps -a --format "{{.ID}}\t{{.Image}}\t{{.Status}}\t{{.Names}}" --filter "name=piselfhosting")

# Full HTML template
HTML_TEMPLATE=$(cat <<_EOF_
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Docker Container Stats</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        body {
            font-family: 'Inter', sans-serif;
            background-color: #f0f4f8;
            color: #334155;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            justify-content: flex-start; /* Changed to flex-start */
            align-items: center;
            padding: 1rem;
        }
        .container {
            background-color: #ffffff;
            border-radius: 1rem;
            box-shadow: 0 10px 15px rgba(0, 0, 0, 0.1);
            padding: 2rem;
            width: 100%;
            max-width: 960px;
            margin-top: 2rem; /* Added margin-top */
        }
        table {
            width: 100%;
            border-collapse: separate;
            border-spacing: 0;
        }
        th, td {
            padding: 0.75rem 1rem;
            text-align: left;
            border-bottom: 1px solid #e2e8f0;
        }
        th {
            background-color: #edf2f7;
            font-weight: 600;
            color: #4a5568;
            text-transform: uppercase;
            font-size: 0.75rem;
            letter-spacing: 0.05em;
        }
        th:first-child { border-top-left-radius: 0.5rem; }
        th:last-child { border-top-right-radius: 0.5rem; }
        tr:last-child td:first-child { border-bottom-left-radius: 0.5rem; }
        tr:last-child td:last-child { border-bottom-right-radius: 0.5rem; }
        tbody tr:hover {
            background-color: #f7fafc;
        }
        .metric {
            font-weight: 700;
            color: #1a202c;
        }
        .status-running { color: #10b981; } /* Emerald Green */
        .status-exited { color: #ef4444; }  /* Red */
        .status-paused { color: #f59e0b; }  /* Amber */

        @media (max-width: 768px) {
            .container {
                padding: 1rem;
            }
            table, thead, tbody, th, td, tr {
                display: block;
            }
            thead tr {
                position: absolute;
                top: -9999px;
                left: -9999px;
            }
            tr {
                border: 1px solid #e2e8f0;
                margin-bottom: 0.75rem;
                border-radius: 0.5rem;
            }
            td {
                border: none;
                position: relative;
                padding-left: 50%;
                text-align: right;
            }
            td:before {
                content: attr(data-label);
                position: absolute;
                left: 1rem;
                width: calc(50% - 1rem);
                padding-right: 0.5rem;
                white-space: nowrap;
                text-align: left;
                font-weight: 600;
                color: #4a5568;
            }
        }
    </style>
</head>
<body class="bg-gray-100 p-4">
    <div class="container mx-auto mt-8 p-6 bg-white rounded-xl shadow-lg">
        <h1 class="text-3xl font-bold text-center text-gray-800 mb-6">Docker Container Stats</h1>
        <div id="statsContent" class="overflow-x-auto">
            <table class="min-w-full bg-white rounded-lg overflow-hidden">
                <thead>
                    <tr>
                        <th>Name</th>
                        <th>Image</th>
                        <th>Status</th>
                        <th>CPU %</th>
                        <th>Memory Usage</th>
                        <th>Net I/O</th>
                        <th>Block I/O</th>
                    </tr>
                </thead>
                <tbody>
                    ${STATS_ROWS}
                </tbody>
            </table>
        </div>
        <p class="text-sm text-center text-gray-500 mt-6">
            Last Updated: <span id="lastUpdated">${LAST_UPDATED_TIME}</span>
        </p>
    </div>
</body>
</html>
_EOF_
)

echo "$HTML_TEMPLATE" > "$HTML_OUTPUT_FILE"
echo "✅ Docker stats HTML updated at: $HTML_OUTPUT_FILE"
echo "You can view it via your Dashy dashboard or by navigating to http://YOUR_DOMAIN:8088"
EOF
chmod +x "$SCRIPTS_DIR/update-docker-stats.sh"
echo "✅ Generated update-docker-stats.sh"

echo -e "\n--- PiSelfhosting Deployment Complete ---"
echo "To start all your services, run: bash $SCRIPTS_DIR/start-all.sh"
echo "To update Dashy tiles, run: bash $SCRIPTS_DIR/run-dashy-tile-config-tool.sh"
echo "To configure Frigate cameras, run: bash $SCRIPTS_DIR/run-frigate-config-tool.sh"
echo "To configure Mailserver, run: bash $SCRIPTS_DIR/run-mailserver-config-tool.sh"
echo "To manage SSL certificates, run: bash $SCRIPTS_DIR/run-ssl-cert-manager.sh"

