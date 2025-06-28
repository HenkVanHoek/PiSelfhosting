#!/bin/bash

# PiSelfhosting Deployment Script
# Location: /home/PiSelfhosting/scripts/deploy.sh
# This script deploys and configures selected Docker services based on templates.

# Stop the script if any command fails (use set -x for debugging, set -e for production)
set -x # Keep set -x for final confirmation of successful run. Change back to set -e after.

# Define base directories and important file paths
export BASE_DIR="/home/PiSelfhosting"
export SCRIPTS_DIR="$BASE_DIR/scripts"
export DOCKER_COMPOSE_DIR="$BASE_DIR/docker"
export TEMPLATES_DIR="$SCRIPTS_DIR/templates"
export ENV_FILE="$BASE_DIR/.env"
export COMPONENTS_LIST_FILE="$SCRIPTS_DIR/components_list.txt"
export SELECTED_COMPONENTS_FILE="$SCRIPTS_DIR/selected_components.txt"
export NETWORK_NAME="piselfhosting_net" # Define network name here for consistency

# --- Function to ensure whiptail is installed ---
ensure_whiptail() {
    echo "--- Checking if 'whiptail' is installed ---"
    if ! command -v whiptail &> /dev/null; then
        echo "Info: 'whiptail' not found. Installing..."
        sudo apt-get update && sudo apt-get install -y whiptail
    else
        echo "Info: 'whiptail' is already installed."
    fi
    echo "--- 'whiptail' check complete ---"
}


# --- Helper to get the correct docker compose command (internal function for deploy.sh) ---
get_docker_compose_cmd() {
    if command -v docker &>/dev/null && docker compose version &>/dev/null; then
        echo "docker compose" # Docker Compose V2 plugin
    else
        echo "" # Not found or not V2
    fi
}

# --- Load environment variables ---
load_env_vars() {
    if [ -f "$ENV_FILE" ]; then
        echo "Info: Loading environment variables from $ENV_FILE..."
        set -a # Automatically export all subsequent variable assignments
        source "$ENV_FILE"
        set +a # Turn off auto-export

        # Ensure PUID and PGID are set, default to 1000 if not
        if [ -z "${PUID}" ]; then
            export PUID=1000
            echo "Warning: PUID not found in .env, defaulting to $PUID."
        fi
        if [ -z "${PGID}" ]; then
            export PGID=1000
            echo "Warning: PGID not found in .env, defaulting to $PGID."
        fi
    else
        echo "❌ Error: .env file not found at $ENV_FILE. Please run setup.sh first."
        exit 1
    fi
}

# --- Docker and Docker Compose Check/Installation ---
# NOTE: This function is also called in setup.sh, but kept here for robustness
# if deploy.sh is run independently.
ensure_docker_and_compose() {
    echo "--- Ensuring Docker CE and Docker Compose V2 are installed ---"
    if ! command -v docker &> /dev/null; then
        echo "Info: Docker not found. Installing..."
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
        echo "Info: Docker is already installed."
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

# --- Pre-deployment Cleanup ---
perform_full_cleanup() {
    echo -e "\n--- Starting pre-deployment cleanup ---"

    local current_docker_compose_cmd=$(get_docker_compose_cmd)
    if [ -z "$current_docker_compose_cmd" ]; then
        echo "❌ Docker Compose (v1 or v2) not found. Skipping container cleanup."
        return 1
    fi

    echo "Stopping and removing ALL existing PiSelfhosting containers, volumes, and networks..."

    # Export the project name for consistent cleanup
    export COMPOSE_PROJECT_NAME="piselfhosting"

    # Use the unified docker-compose.yml for cleanup
    local main_compose_file="$BASE_DIR/docker-compose.yml"
    if [ -f "$main_compose_file" ]; then
        echo "Info: Running 'docker compose down --volumes --remove-orphans' on the unified docker-compose.yml..."
        (cd "$BASE_DIR" && ${current_docker_compose_cmd} -f "$main_compose_file" down --volumes --remove-orphans) || {
            echo "⚠️ Could not cleanly bring down the unified project. Some containers/volumes might remain."
        }
    else
        echo "Info: Unified docker-compose.yml not found. Checking individual component compose files for cleanup."
        # This block is now largely vestigial as we move to a single compose file,
        # but kept for backward compatibility during transitions.
        local individual_compose_files=()
        if [ -f "$SELECTED_COMPONENTS_FILE" ]; then # Ensure selected_components.txt exists before reading
            for comp in $(cat "$SELECTED_COMPONENTS_FILE" | tr -d '"'); do
                if [ -f "$DOCKER_COMPOSE_DIR/$comp/docker-compose.yml" ]; then
                    individual_compose_files+=("-f" "$DOCKER_COMPOSE_DIR/$comp/docker-compose.yml")
                fi
            done
        fi

        if [ ${#individual_compose_files[@]} -gt 0 ]; then
            echo "Info: Running 'docker compose down --volumes --remove-orphans' on individual component compose files..."
            (cd "$BASE_DIR" && ${current_docker_compose_cmd} "${individual_compose_files[@]}" down --volumes --remove-orphans) || {
                echo "⚠️ Could not cleanly bring down individual component projects. Some containers/volumes might remain."
            }
        else
            echo "Info: No Docker Compose files found to clean up from individual component directories."

        fi
    fi

    echo "Removing old symlinks to .env files..."
    find "$DOCKER_COMPOSE_DIR" -maxdepth 2 -type l -name ".env" -delete || true
    echo "✅ Pre-deployment cleanup complete."
}

# --- Helper Function to initialize config files ---
init_config_file() {
    local app_name="$1"
    local relative_config_path="$2"
    local source_template="$TEMPLATES_DIR/$app_name/$relative_config_path"
    local dest_path="$DOCKER_COMPOSE_DIR/$app_name/$relative_config_path"

    # Check if the source template file exists
    if [ ! -f "$source_template" ]; then
        echo "❌ Template source not found for $app_name at $source_template. Skipping file creation."
        return 1
    fi

    echo "  Generating config/file for $app_name: $dest_path from template..."
    sudo mkdir -p "$(dirname "$dest_path")"

    # Use envsubst for templates to insert environment variables
    if ! command -v envsubst &> /dev/null; then
        echo "❌ Error: 'envsubst' not found. Please install 'gettext-base': sudo apt-get install gettext-base"
        exit 1
    fi

    # Export HOST_IP for Dashy's extra_hosts.
    export HOST_IP=$(hostname -I | awk '{print $1}' | tr -d '[:space:]')

    # Use sudo with tee to write the file, preserving permissions
    if envsubst < "$source_template" | sudo tee "$dest_path" > /dev/null; then
        echo "  ✅ Config file created/updated: $dest_path"
    else
        echo "  ❌ Failed to create/update config file: $dest_path"
        return 1
    fi
}
# --- Handle component-specific permissions or actions ---
perform_component_specific_actions() {
    local app_name="$1"
    local component_dir="$DOCKER_COMPOSE_DIR/$app_name"

    case "$app_name" in
        "frigate")
            sudo mkdir -p "$component_dir/media"
            echo "Info: Frigate media storage directory checked/created."
            ;;
        "mosquitto")
            sudo mkdir -p "$component_dir/data" "$component_dir/log"
            echo "Setting correct permissions for Mosquitto directories (UID/GID 1883)..."
            sudo chown -R 1883:1883 "$component_dir/config" # Assuming config is generated here
            sudo chown -R 1883:1883 "$component_dir/data"
            sudo chown -R 1883:1883 "$component_dir/log"
            echo "✅ Mosquitto permissions applied."
            ;;
        "docker-monitor") # Specific actions for docker-monitor, like creating its HTML directory
            sudo mkdir -p "$component_dir/html"
            echo "Info: Docker Monitor HTML directory checked/created for updates."
            # No specific permissions needed beyond ownership by 'pi' typically, handled by mkdir.
            ;;
    esac
}
# --- Generate Helper Scripts ---
generate_helper_scripts() {
    echo -e "\n--- Generating Helper Scripts ---"

    # Ensure DEPLOY_DOCKER_COMPOSE_CMD is set from the main script execution
    if [ -z "${DEPLOY_DOCKER_COMPOSE_CMD}" ]; then
        echo "❌ Error: DEPLOY_DOCKER_COMPOSE_CMD not set. Cannot generate helper scripts dependent on it."
        return 1
    fi

# --- Generate start-all.sh ---
cat <<EOF_START_ALL | sudo tee "$SCRIPTS_DIR/start-all.sh" > /dev/null
#!/bin/bash
# PiSelfhosting Start All Script (Generated by deploy.sh)
# Location: \${SCRIPTS_DIR}/start-all.sh # Escaped for later interpretation

# Stop the script if a command fails
set -e

BASE_DIR="${BASE_DIR}"
ENV_FILE="${ENV_FILE}"
NETWORK_NAME="${NETWORK_NAME}"

# --- Load environment variables ---
echo "Info: Loading environment variables from \$ENV_FILE and exporting them..."
if [ -f "\$ENV_FILE" ]; then
    set -a # Automatically export all subsequent assignments
    source "\$ENV_FILE"
    set +a # Disable auto-export
    echo "✅ Environment variables loaded."
else
    echo "❌ Error: .env file not found at \$ENV_FILE. Please run setup.sh first."
    exit 1
fi

# --- Create Docker network if it doesn't exist ---
if ! docker network inspect "\$NETWORK_NAME" &>/dev/null; then
    echo "Info: Docker network '\$NETWORK_NAME' not found. Creating..."
    docker network create "\$NETWORK_NAME"
    echo "✅ Docker network '\$NETWORK_NAME' created."
else
    echo "Info: Docker network '\$NETWORK_NAME' already exists."
fi

echo "🚀 Starting PiSelfhosting containers in dependency order..."

# --- Ensure a clean start by stopping and removing existing containers ---
echo "Attempting to stop and remove any existing PiSelfhosting containers for a clean start..."

# Explicitly stop and remove the mosquitto container first, in case it's lingering
# from a manual run or a different project context.
MOSQUITTO_CONTAINER_NAME="piselfhosting-mosquitto"
if docker ps -a --format '{{.Names}}' | grep -q "^\${MOSQUITTO_CONTAINER_NAME}$"; then
    echo "Info: Found existing '\$MOSQUITTO_CONTAINER_NAME'. Stopping and removing..."
    docker stop "\$MOSQUITTO_CONTAINER_NAME" &>/dev/null || true
    docker rm "\$MOSQUITTO_CONTAINER_NAME" &>/dev/null || true
    echo "✅ '\$MOSQUITTO_CONTAINER_NAME' removed."
fi

# Set the COMPOSE_PROJECT_NAME for consistent Docker Compose operations
export COMPOSE_PROJECT_NAME="piselfhosting"

DOCKER_COMPOSE_EXEC_CMD="${DEPLOY_DOCKER_COMPOSE_CMD}"

# Use docker compose down to stop and remove services managed by this project
# --remove-orphans ensures any containers that are no longer defined in the compose file
# but were part of the project are also removed.
MAIN_COMPOSE_FILE="${BASE_DIR}/docker-compose.yml"
if [ -f "\$MAIN_COMPOSE_FILE" ]; then
    echo "Info: Running 'docker compose down --volumes --remove-orphans' on the unified docker-compose.yml..."
    (cd "\$BASE_DIR" && \${DOCKER_COMPOSE_EXEC_CMD} -f "\$MAIN_COMPOSE_FILE" down --volumes --remove-orphans) || {
        echo "⚠️ Could not cleanly bring down the unified project. Some containers/volumes might remain."
    }
else
    echo "Warning: docker-compose.yml not found at \$MAIN_COMPOSE_FILE. Cannot perform clean shutdown of compose services."
fi

# --- Read selected components for starting ---
COMPONENTS_FILE="${SELECTED_COMPONENTS_FILE}" # This variable is already outside the problem section
if [ ! -f "\${COMPONENTS_FILE}" ]; then # ESCAPE
    echo "❌ Error: selected_components.txt not found at \${COMPONENTS_FILE}. Please run setup.sh first." # ESCAPE
    exit 1
fi

read -r -a SELECTED_COMPONENTS_ARRAY <<< "\$(cat "\${COMPONENTS_FILE}" | tr -d '"')" # ESCAPE
if [ \${#SELECTED_COMPONENTS_ARRAY[@]} -eq 0 ]; then
    echo "Info: No components selected in \${COMPONENTS_FILE}. Nothing to start." # ESCAPE
    exit 0
fi

# Translate selected component names to service names (e.g., component_name -> docker-compose_service_name)
declare -a SERVICES_TO_START_ARGS=()
for comp_name in "\${SELECTED_COMPONENTS_ARRAY[@]}"; do
    SERVICES_TO_START_ARGS+=("\$comp_name")
done

echo "Starting all selected services as a single Docker Compose project..."
if \${DOCKER_COMPOSE_EXEC_CMD} -f "\$MAIN_COMPOSE_FILE" up -d --build --remove-orphans \${SERVICES_TO_START_ARGS[*]}; then
    echo "✅ All selected PiSelfhosting containers started successfully."
    echo -e "\n--- PiSelfhosting Services Started ---"
    echo "You can check the status of your containers with: docker ps"
    echo "Or view logs with: \${DOCKER_COMPOSE_EXEC_CMD} logs -f"
    echo "If you selected Portainer, you can access its UI (usually on port 9000 or a subdomain)."
    echo "Access your services via the domain you set during setup (e.g., Dashy at dashboard.\$DOMAIN)."
else
    echo "❌ Failed to start one or more services. Check Docker logs for details."
    exit 1
fi
EOF_START_ALL

# --- Generate stop-all.sh ---
cat <<EOF_STOP_ALL | sudo tee "$SCRIPTS_DIR/stop-all.sh" > /dev/null
#!/bin/bash
# PiSelfhosting Stop All Script (Generated by deploy.sh)
# Location: \${SCRIPTS_DIR}/stop-all.sh # Escaped

# Stop the script if a command fails
set -e

BASE_DIR="${BASE_DIR}"
ENV_FILE="${ENV_FILE}"

# Load environment variables
echo "Info: Loading environment variables from \$ENV_FILE and exporting them..."
if [ -f "\$ENV_FILE" ]; then
    set -a
    source "\$ENV_FILE"
    set +a
    echo "✅ Environment variables loaded."
else
    echo "❌ Error: .env file not found at \$ENV_FILE. Cannot stop services."
    exit 1
fi

# Set the COMPOSE_PROJECT_NAME for consistent Docker Compose operations
export COMPOSE_PROJECT_NAME="piselfhosting"

DOCKER_COMPOSE_EXEC_CMD="${DEPLOY_DOCKER_COMPOSE_CMD}"

echo "🛑 Stopping all PiSelfhosting containers..."
MAIN_COMPOSE_FILE="${BASE_DIR}/docker-compose.yml"
if [ -f "\$MAIN_COMPOSE_FILE" ]; then
    echo "Info: Running 'docker compose down --volumes --remove-orphans' on the unified docker-compose.yml..."
    (cd "\$BASE_DIR" && \${DOCKER_COMPOSE_EXEC_CMD} -f "\$MAIN_COMPOSE_FILE" down) || {
        echo "⚠️ Failed to stop some services. Check logs."
    }
else
    echo "Warning: docker-compose.yml not found at \$MAIN_COMPOSE_FILE. Cannot stop services."
fi
echo "✅ All selected containers stopped."
EOF_STOP_ALL

# --- Generate restart-all.sh ---
cat <<EOF_RESTART_ALL | sudo tee "$SCRIPTS_DIR/restart-all.sh" > /dev/null
#!/bin/bash
# PiSelfhosting Restart All Script (Generated by deploy.sh)
# Location: \${SCRIPTS_DIR}/restart-all.sh # Escaped

BASE_DIR="${BASE_DIR}"
SCRIPTS_DIR="${SCRIPTS_DIR}"

echo "🔄 Restarting all PiSelfhosting services..."
"\$SCRIPTS_DIR/stop-all.sh" "\$@"
"\$SCRIPTS_DIR/start-all.sh" "\$@"
echo "✅ Restart complete."
EOF_RESTART_ALL

# --- Generate remove-component.sh ---
cat <<EOF_REMOVE_COMPONENT | sudo tee "$SCRIPTS_DIR/remove-component.sh" > /dev/null
#!/bin/bash
# PiSelfhosting Remove Component Script (Generated by deploy.sh)
# Location: \${SCRIPTS_DIR}/remove-component.sh # Escaped

# This script allows you to remove specific PiSelfhosting components.

# Stop the script if any command fails
set -e

BASE_DIR="${BASE_DIR}"
SCRIPTS_DIR="${SCRIPTS_DIR}"
ENV_FILE="${ENV_FILE}"
COMPONENTS_FILE="${SELECTED_COMPONENTS_FILE}"
DOCKER_COMPOSE_DIR="${DOCKER_COMPOSE_DIR}"
MAIN_COMPOSE_FILE="${BASE_DIR}/docker-compose.yml"

# Load environment variables
echo "Info: Loading environment variables from \$ENV_FILE and exporting them..."
if [ -f "\$ENV_FILE" ]; then
    set -a
    source "\$ENV_FILE"
    set +a
    echo "✅ Environment variables loaded."
fi

# Set the COMPOSE_PROJECT_NAME for consistent Docker Compose operations
export COMPOSE_PROJECT_NAME="piselfhosting"

DOCKER_COMPOSE_EXEC_CMD="${DEPLOY_DOCKER_COMPOSE_CMD}"

if [ -z "\$DOCKER_COMPOSE_EXEC_CMD" ]; then
    echo "❌ Docker Compose not found. Cannot remove components."
    exit 1
fi

echo "--- Remove PiSelfhosting Component ---"

if [ ! -f "\${COMPONENTS_FILE}" ]; then # ESCAPE
    echo "❌ Error: selected_components.txt not found at \${COMPONENTS_FILE}. No components to remove." # ESCAPE
    exit 1
fi

read -r -a SELECTED_COMPONENTS <<< "\$(cat "\${COMPONENTS_FILE}" | tr -d '"')" # ESCAPE
if [ \${#SELECTED_COMPONENTS[@]} -eq 0 ]; then
    echo "Info: No components are currently selected/installed. Nothing to remove."
    exit 0
fi

# whiptail requires local scope for options to prevent issues with variable expansion inside loops
declare -a remove_options=()
for comp in "\${SELECTED_COMPONENTS[@]}"; do
    remove_options+=("\$comp" "" "OFF")
done

if [ \${#remove_options[@]} -gt 0 ]; then
    REMOVE_CHOICES=\$(whiptail --title "Remove PiSelfhosting Component" --checklist \
    "Choose components to remove (use space to select/deselect, Enter to confirm):" 20 78 10 \
    "\${remove_options[@]}" 3>&1 1>&2 2>&3)

    if [ \$? -ne 0 ]; then
        echo "Component removal canceled."
        exit 0
    fi
else
    echo "Info: No removable components found."
    exit 0
fi

# Convert chosen components to an array
declare -a COMPONENTS_TO_REMOVE=()
if [ -n "\$REMOVE_CHOICES" ]; then
    # Remove quotes and split by spaces
    COMPONENTS_TO_REMOVE=(\$(echo "\$REMOVE_CHOICES" | tr -d '"'))
fi

if [ \${#COMPONENTS_TO_REMOVE[@]} -eq 0 ]; then
    echo "No components selected for removal."
    exit 0
fi

echo "--- Removing selected components ---"

declare -a new_selected_components=()
for comp in "\${SELECTED_COMPONENTS[@]}"; do
    local found_to_remove=false # Keep local for this inner loop var
    for to_remove in "\${COMPONENTS_TO_REMOVE[@]}"; do
        if [ "\$comp" == "\$to_remove" ]; then
            found_to_remove=true
            echo "Stopping and removing container for '\$comp'..."
            if \${DOCKER_COMPOSE_EXEC_CMD} -f "\$MAIN_COMPOSE_FILE" rm -s -v -f "\$comp"; then # -s for stop, -v for volumes, -f for force
                echo "✅ Container and associated volumes for '\$comp' removed."
            else
                echo "⚠️ Failed to remove container/volumes for '\$comp'. Manual cleanup might be needed."
            fi
            # Remove its docker-compose.yml and config directory
            if [ -d "${DOCKER_COMPOSE_DIR}/\$comp" ]; then
                echo "Removing component directory: ${DOCKER_COMPOSE_DIR}/\$comp"
                sudo rm -rf "${DOCKER_COMPOSE_DIR}/\$comp"
            fi
            break
        fi
    done
    if [ "\$found_to_remove" = false ]; then
        new_selected_components+=("\$comp")
    fi
done

# Update selected_components.txt
printf '%s ' "\${new_selected_components[@]}" > "\${COMPONENTS_FILE}" # ESCAPE
echo "✅ selected_components.txt updated."

echo -e "\n--- Component removal complete ---"
echo "You may need to run 'docker system prune' to clean up unused Docker resources."
EOF_REMOVE_COMPONENT

# --- Generate get_docker_compose_cmd.sh ---
cat <<EOF_GET_DOCKER_COMPOSE_CMD | sudo tee "$SCRIPTS_DIR/get-docker-compose-cmd.sh" > /dev/null
#!/bin/bash
# PiSelfhosting Docker Compose Command Helper
# Location: \${SCRIPTS_DIR}/get-docker-compose-cmd.sh # Escaped

if command -v docker &>/dev/null && docker compose version &>/dev/null; then
    echo "docker compose" # Docker Compose V2 plugin
else # Geen fallback naar docker-compose (V1)
    echo "" # Not found or not V2
fi
EOF_GET_DOCKER_COMPOSE_CMD

sudo chmod +x "$SCRIPTS_DIR/start-all.sh" "$SCRIPTS_DIR/stop-all.sh" "$SCRIPTS_DIR/restart-all.sh" "$SCRIPTS_DIR/remove-component.sh" "$SCRIPTS_DIR/get-docker-compose-cmd.sh"
echo "✅ Helper scripts (start-all, stop-all, restart-all, remove-component, get-docker-compose-cmd) generated."
}
# ================================================
#               MAIN SCRIPT LOGIC
# ================================================

# --- Load and export environment variables ---
load_env_vars

# --- Parse components_list.txt ---
COMPONENTS_ORDER=()
declare -A COMPONENT_DATA # Associative array needs explicit declare -A even outside functions
if [ -f "$COMPONENTS_LIST_FILE" ]; then
    COMPONENTS_ORDER_LINE=$(grep "^COMPONENTS_ORDER=" "$COMPONENTS_LIST_FILE")
    if [[ "$COMPONENTS_ORDER_LINE" =~ ^COMPONENTS_ORDER=(.*)$ ]]; then
        IFS=',' read -r -a COMPONENTS_ORDER <<< "${BASH_REMATCH[1]}"
    fi

    current_component=""
    while IFS='=' read -r key value || [ -n "$key" ]; do
        key=$(echo "$key" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')
        # Corrected sed expression for value trimming
        value=$(echo "$value" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')

        if [[ "$key" =~ ^\[(.+)\]$ ]]; then
            current_component="${BASH_REMATCH[1]}"
        elif [[ -n "$current_component" ]]; then
            COMPONENT_DATA["${current_component}_${key}"]="$value"
        fi
    done < "$COMPONENTS_LIST_FILE"
else
    echo "❌ components_list.txt not found. Cannot proceed."
    exit 1
fi


# --- Read selected components from previous run (if any) for accurate deploy ---
declare -a SELECTED_COMPONENTS_ARRAY=()
if [ -f "$SELECTED_COMPONENTS_FILE" ]; then
    read -r -a SELECTED_COMPONENTS_ARRAY <<< "$(cat "$SELECTED_COMPONENTS_FILE" | tr -d '"')"
fi

# --- Perform Cleanup ---
perform_full_cleanup

# Bepaal het Docker Compose commando string eenmalig HIER in deploy.sh
# Deze variabele zal later direct in de helper scripts worden ingevuld.
export DEPLOY_DOCKER_COMPOSE_CMD=$(get_docker_compose_cmd)
if [ -z "$DEPLOY_DOCKER_COMPOSE_CMD" ]; then
    echo "❌ Error: Docker Compose V2 not found even after trying to install. Cannot proceed with deployment."
    exit 1
fi

# --- Temporary files for collecting data ---
TEMP_SERVICES_FILE=$(mktemp)
TEMP_VOLUMES_OUT_FILE=$(mktemp)
declare -A UNIQUE_VOLUMES # To store unique volume definitions

# --- Generate Unified Docker Compose File Structure ---
echo -e "\n--- Generating unified docker-compose.yml ---"
{
    echo "networks:"
    echo "  ${NETWORK_NAME}:"
    echo "    external: true"
    echo "services:"
} | sudo tee "$BASE_DIR/docker-compose.yml" > /dev/null

# --- Process each selected component to extract services and volumes ---
for comp in "${COMPONENTS_ORDER[@]}"; do
    is_selected=false
    for selected in "${SELECTED_COMPONENTS_ARRAY[@]}"; do
        if [ "$selected" == "$comp" ]; then
            is_selected=true
            break
        fi
    done

    if [ "$is_selected" = true ]; then
        echo "Info: Processing service definition for '$comp'..."
        component_dir="$DOCKER_COMPOSE_DIR/$comp"
        sudo mkdir -p "$component_dir" # Ensure component directory exists
        sudo ln -sf "$ENV_FILE" "$component_dir/.env" # Symlink .env

        # Handle component-specific actions (e.g., creating specific directories)
        perform_component_specific_actions "$comp"

        # Start service block for this component
        echo "  $comp:" >> "$TEMP_SERVICES_FILE" # Print service name with correct indent

        # Special handling for Docker Monitor. It doesn't use a docker-compose.template.yml
        # but its service block is hardcoded here and its HTML is generated by a separate script.
        if [ "$comp" == "docker-monitor" ]; then
            echo "    Generating Docker Compose service block for docker-monitor content..."
            {
                echo "    container_name: piselfhosting-docker-monitor"
                echo "    image: nginx:alpine"
                echo "    restart: unless-stopped"
                echo "    volumes:"
                echo "      - $DOCKER_COMPOSE_DIR/docker-monitor/html:/usr/share/nginx/html:ro"
                echo "    ports:"
                echo "      - \"8088:80\""
                echo "    networks:"
                echo "      - piselfhosting_net"
            } >> "$TEMP_SERVICES_FILE"
            echo "✅ 'docker-monitor' service definition content prepared."
            continue # Skip general template processing for this special case
        fi

        # Process other components that use standard docker-compose.template.yml files
        # Check if the component has config_paths (these will be processed by init_config_file)
        # Note: piselfhosting-docs now has config_paths and will be handled here.
        config_paths_str=${COMPONENT_DATA["${comp}_config_paths"]}
        if [ -n "$config_paths_str" ]; then
            IFS=',' read -ra config_paths_array <<< "$config_paths_str"
            for path in "${config_paths_array[@]}"; do
                init_config_file "$comp" "$path"
            done
        fi


        compose_template="$TEMPLATES_DIR/$comp/docker-compose.template.yml"
        if [ -f "$compose_template" ]; then
            export HOST_IP=$(hostname -I | awk '{print $1}' | tr -d '[:space:]')

            # Temporary file for envsubst output, only the really required variables, leave the for docker compose to evaluate.
            temp_processed_compose=$(mktemp)
            envsubst '${PUID}:${PGID}:${HOST_IP}:${TZ}' < "$compose_template" > "$temp_processed_compose"

            # AWK for services
            awk -v section_type="service" -f "$SCRIPTS_DIR/utils/service_formatter.awk" "$temp_processed_compose" >> "$TEMP_SERVICES_FILE"

            # AWK for volumes
            awk -v section_type="volume" -f "$SCRIPTS_DIR/utils/service_formatter.awk" "$temp_processed_compose" >> "$TEMP_VOLUMES_OUT_FILE"

            rm "$temp_processed_compose"
            echo "✅ '$comp' service definition content prepared."
        else
            echo "❌ Docker Compose template for $comp not found at $compose_template. Cannot deploy."
            exit 1 # This should now only happen for truly missing templates (e.g., if selected but no template exists)
        fi
    else
        echo "Info: Skipping service definition for '$comp' (not selected)."
    fi
done

# Append all collected services to the main docker-compose.yml
sudo cat "$TEMP_SERVICES_FILE" | sudo tee -a "$BASE_DIR/docker-compose.yml" > /dev/null
rm "$TEMP_SERVICES_FILE" # Clean up temporary file

# Append unique top-level volumes to the main docker-compose.yml
if [ -s "$TEMP_VOLUMES_OUT_FILE" ]; then
    echo "" | sudo tee -a "$BASE_DIR/docker-compose.yml" > /dev/null # Add a newline for separation
    echo "volumes:" | sudo tee -a "$BASE_DIR/docker-compose.yml" > /dev/null

    declare -A UNIQUE_VOLUME_BLOCKS # Stores full YAML blocks for unique volumes
    current_volume_key="" # To store the YAML key like "  volume_name:"
    current_block_content=""

    # Read the raw output from awk for volumes
    while IFS= read -r line; do
        # If it's a new top-level volume definition (e.g., "  volume_name:")
        if [[ "$line" =~ ^[[:space:]]{2}([a-zA-Z0-9_-]+):[[:space:]]*$ ]]; then
            # If we were collecting a block, store it
            if [ -n "$current_volume_key" ]; then
                # Trim leading/trailing whitespace from the entire block content
                # And remove duplicate 'name:' fields if they somehow got in
                UNIQUE_VOLUME_BLOCKS["$current_volume_key"]="$(echo -e "$current_block_content" | awk '!/^[[:space:]]*name:/ || ++seen_name[$1]==1')"
            fi
            current_volume_key="$line" # Store the full line as the key
            current_block_content="" # Reset content for the new block
        elif [ -n "$current_volume_key" ]; then
            # Append lines to the current block content
            current_block_content+="$line\n"
        fi
    done < "$TEMP_VOLUMES_OUT_FILE"

    # Add the last collected block
    if [ -n "$current_volume_key" ]; then
        UNIQUE_VOLUME_BLOCKS["$current_volume_key"]="$(echo -e "$current_block_content" | awk '!/^[[:space:]]*name:/ || ++seen_name[$1]==1')"
    fi

    # Now, print all unique volume blocks in a consistent order
    for vol_key in "${!UNIQUE_VOLUME_BLOCKS[@]}"; do
        echo "$vol_key" | sudo tee -a "$BASE_DIR/docker-compose.yml" > /dev/null
        if [ -n "${UNIQUE_VOLUME_BLOCKS[$vol_key]}" ]; then
            echo -e "${UNIQUE_VOLUME_BLOCKS[$vol_key]}" | sudo tee -a "$BASE_DIR/docker-compose.yml" > /dev/null
        fi
    done
fi
rm "$TEMP_VOLUMES_OUT_FILE" # Clean up temporary file

echo "✅ Unified docker-compose.yml generated at $BASE_DIR/docker-compose.yml."

# --- Generate Helper Scripts ---
generate_helper_scripts

# --- Final Message ---
echo -e "\n--- Deployment complete ---\n"
echo "Your PiSelfhosting environment has been configured and is ready for use."
echo "Next steps:"
echo "1. Start your services: bash $SCRIPTS_DIR/start-all.sh"
echo "2. Configure Frigate (if selected): bash $SCRIPTS_DIR/run-frigate-camera-config-tool.sh"
echo "3. Update Dashy (if selected): bash $SCRIPTS_DIR/run-dashy-tile-config-tool.sh"
echo "4. Manage SSL Certificates (if needed): bash $SCRIPTS_DIR/run-ssl-cert-manager.sh"
echo "5. Configure Mailserver (if selected): bash $SCRIPTS_DIR/run-mailserver-config-tool.sh"