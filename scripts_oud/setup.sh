#!/bin/bash

# PiSelfhosting Setup Script
# Location: /home/PiSelfhosting/scripts/setup.sh
# This script is responsible for the initial setup of your PiSelfhosting environment.
# It installs necessary tools (whiptail, Docker, Docker Compose),
# collects essential environment variables, and allows you to select
# which PiSelfhosting components you want to deploy.

# Stop the script if a command fails
set -e

# Define the base directory and important file paths
BASE_DIR="/home/PiSelfhosting"
SCRIPTS_DIR="$BASE_DIR/scripts"
ENV_FILE="$BASE_DIR/.env"
COMPONENTS_FILE="$BASE_DIR/scripts/selected_components.txt"
COMPONENTS_LIST_FILE="$SCRIPTS_DIR/components_list.txt" # Path to the file with component definitions

# Ensure the scripts directory exists
mkdir -p "$SCRIPTS_DIR"

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
    DOMAIN=$(whiptail --inputbox "Enter the main domain name you want to use for your services (e.g., 'myserver.com' or 'home.arpa'). This will be used for Nginx Proxy Manager and Dashy." 10 60 "${DOMAIN:-henkenyvonne.nl}" 3>&1 1>&2 2>&3)
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
    # Use sed for robust whitespace trimming
    key=$(echo "$key" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')
    value=$(echo "$value" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')

    if [[ "$key" =~ ^\[(.+)\]$ ]]; then # New component section
        current_component_name_setup_script="${BASH_REMATCH[1]}"
    elif [[ -n "$current_component_name_setup_script" ]]; then
        COMPONENT_DATA_SETUP_SCRIPT["${current_component_name_setup_script}_${key}"]="$value"
    fi
done < "$COMPONENTS_LIST_FILE"


# --- Docker and Docker Compose Check/Installation ---
ensure_docker_and_compose() {
    echo "--- Ensuring Docker CE and Docker Compose V2 are installed ---"
    if ! command -v docker &> /dev/null; then
        echo "Info: 'docker' not found. Installing Docker CE..."
        sudo apt-get update
        sudo apt-get install -y ca-certificates curl gnupg
        sudo install -m 0755 -d /etc/apt/keyrings
        curl -fsSL https://download.docker.com/linux/raspbian/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
        sudo chmod a+r /etc/apt/keyrings/docker.gpg
        echo \
            "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/raspbian \
            $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
            sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
        sudo apt-get update
        sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
        echo "✅ Docker CE installed."
    else
        echo "Info: 'docker' is already installed."
    fi

    if ! docker compose version &>/dev/null; then
        echo "Info: Docker Compose V2 plugin not found. Installing..."
        sudo apt-get install -y docker-compose-plugin
        echo "✅ Docker Compose V2 plugin installed."
    else
        echo "Info: Docker Compose V2 plugin is already installed."
    fi

    if ! id -nG "$(whoami)" | grep -qw "docker"; then
        echo "Adding current user '$(whoami)' to the 'docker' group..."
        sudo usermod -aG docker "$(whoami)"
        echo "Please log out and log back in (or reboot) for the changes to take effect."
    fi
    echo "--- Docker CE and Docker Compose V2 check/install complete ---"
}
ensure_docker_and_compose # Call the function to ensure Docker is installed here

# --- Component selection via whiptail checklist ---
echo "--- Select components to install ---"
declare -a menu_options=()

# Read previously selected components for default checking
declare -A PREVIOUSLY_SELECTED_COMPONENTS
if [ -f "$COMPONENTS_FILE" ]; then
    # Read components, remove quotes, and split into array
    read -r -a PREV_CHOICES <<< "$(cat "$COMPONENTS_FILE" | tr -d '"')"
    for comp in "${PREV_CHOICES[@]}"; do
        PREVIOUSLY_SELECTED_COMPONENTS["$comp"]="true"
    done
    echo "Info: Loaded previously selected components from $COMPONENTS_FILE."
else
    echo "Info: No previous component selections found. All components will be OFF by default."
fi

# Add components based on components_list.txt and set default state
for comp_name in "${ALL_COMPONENT_NAMES_ORDERED_SETUP_SCRIPT[@]}"; do
    description="${COMPONENT_DATA_SETUP_SCRIPT["${comp_name}_description"]}" # Use description
    default_state="OFF"

    # Check if this component was previously selected
    if [ "${PREVIOUSLY_SELECTED_COMPONENTS["$comp_name"]}" = "true" ]; then
        default_state="ON"
    fi

    if [ -n "$description" ]; then # Check only for description
        menu_options+=("$comp_name" "$description" "$default_state") # Use description as the item text
    fi
done

# Check if there are any options to display
if [ ${#menu_options[@]} -eq 0 ]; then
    echo "❌ No components defined in components_list.txt or all are filtered out. Setup aborted."
    exit 1
fi

# Let the user choose components
CHOICES=$(whiptail --title "PiSelfhosting Component Selection" --checklist \
"Choose which self-hosting components you want to install (use space to select/deselect, Enter to confirm):" 25 78 15 \
"${menu_options[@]}" 3>&1 1>&2 2>&3)

if [ $? -ne 0 ]; then
    echo "❌ Component selection canceled. Exiting setup."
    exit 1
fi

# Remove double quotes and save the selected components to a file, separated by spaces
# The tr -d '"' command ensures no double quotes remain.
echo "$CHOICES" | tr -d '"' > "$COMPONENTS_FILE"
echo "✅ Selected components saved to $COMPONENTS_FILE."


echo -e "\n--- PiSelfhosting Setup Complete ---"
echo "You have configured your essential variables and selected your components."
echo "The next step is to run the deployment script:"
echo "    bash $SCRIPTS_DIR/deploy.sh"
echo "This will set up the Docker environment and deploy the selected services."
