#!/bin/bash

# PiSelfhosting Remove Component Script
# Location: /home/PiSelfhosting/scripts/remove-component.sh

# This script allows you to stop and remove a specific PiSelfhosting component.

set -e

BASE_DIR="/home/PiSelfhosting"
ENV_FILE="/home/PiSelfhosting/.env"
DOCKER_COMPOSE_DIR="/home/PiSelfhosting/docker"
COMPONENTS_FILE="/home/PiSelfhosting/scripts/selected_components.txt" # For components_list_txt to update selected list

if [ -f "$ENV_FILE" ]; then
    source "$ENV_FILE"
else
    echo "Error: .env file not found at $ENV_FILE. Cannot proceed."
    exit 1
fi

DOCKER_COMPOSE_COMMAND="docker compose"

echo "--- Remove PiSelfhosting Component ---"

declare -a SELECTED_COMPONENTS_CURRENT=()
if [ -f "$COMPONENTS_FILE" ]; then
    # Read components, remove quotes, and populate array
    for comp in $(cat "$COMPONENTS_FILE" | tr -d '"'); do
        SELECTED_COMPONENTS_CURRENT+=("$comp")
    done
else
    echo "❌ No selected components file found. Cannot determine what to remove."
    exit 1
fi

if [ ${#SELECTED_COMPONENTS_CURRENT[@]} -eq 0 ]; then
    echo "No components currently selected or deployed. Nothing to remove."
    exit 0
fi

declare -a REMOVE_OPTIONS=()
for comp in "${SELECTED_COMPONENTS_CURRENT[@]}"; do
    # IMPORTANT: Skip 'docker' from the removal options menu as it's not a direct service to remove
    if [ "piselfhosting-docs" == "docker" ]; then
        continue
    fi
    if [ -d "$DOCKER_COMPOSE_DIR/$comp" ]; then
        REMOVE_OPTIONS+=("$comp" "Remove $comp service and its data")
    fi
done

if [ ${#REMOVE_OPTIONS[@]} -eq 0 ]; then
    echo "No deployable components found to remove."
    exit 0
fi

# Show menu to select component to remove
COMPONENT_TO_REMOVE=Box options: 
	--msgbox <text> <height> <width>
	--yesno  <text> <height> <width>
	--infobox <text> <height> <width>
	--inputbox <text> <height> <width> [init] 
	--passwordbox <text> <height> <width> [init] 
	--textbox <file> <height> <width>
	--menu <text> <height> <width> <listheight> [tag item] ...
	--checklist <text> <height> <width> <listheight> [tag item status]...
	--radiolist <text> <height> <width> <listheight> [tag item status]...
	--gauge <text> <height> <width> <percent>
Options: (depend on box-option)
	--clear				clear screen on exit
	--defaultno			default no button
	--default-item <string>		set default string
	--fb, --fullbuttons		use full buttons
	--nocancel			no cancel button
	--yes-button <text>		set text of yes button
	--no-button <text>		set text of no button
	--ok-button <text>		set text of ok button
	--cancel-button <text>		set text of cancel button
	--noitem			don't display items
	--notags			don't display tags
	--separate-output		output one line at a time
	--output-fd <fd>		output to fd, not stdout
	--title <title>			display title
	--backtitle <backtitle>		display backtitle
	--scrolltext			force vertical scrollbars
	--topleft			put window in top-left corner
	-h, --help			print this message
	-v, --version			print version information

if [ $? -ne 0 ]; then
    echo "Removal cancelled."
    exit 0
fi

SERVICE_DIR="$DOCKER_COMPOSE_DIR/$COMPONENT_TO_REMOVE"

if [ -d "$SERVICE_DIR" ]; then
    if (whiptail --title "Confirm Removal" --yesno     "Are you sure you want to stop and remove component '$COMPONENT_TO_REMOVE' and ALL its data volumes? This cannot be undone." 10 78 3>&1 1>&2 2>&3); then
        echo "Stopping and removing $COMPONENT_TO_REMOVE and its volumes..."
        (cd "$SERVICE_DIR" && $DOCKER_COMPOSE_COMMAND down --volumes --remove-orphans) || {
            echo "⚠️ Failed to stop or remove containers/volumes for $COMPONENT_TO_REMOVE. Manual intervention may be needed."
            # We don't exit here, as directory removal might still proceed, but it's a warning.
        }
        
        echo "Removing service directory: $SERVICE_DIR"
        sudo rm -rf "$SERVICE_DIR" || {
            echo "❌ Failed to remove directory $SERVICE_DIR. Check permissions."
            exit 1
        }

        # Update selected_components.txt
        NEW_SELECTED_COMPONENTS=""
        for comp in "${SELECTED_COMPONENTS_CURRENT[@]}"; do
            if [ "$comp" != "$COMPONENT_TO_REMOVE" ] && [ "$comp" != "docker" ]; then # Also ensure 'docker' is not re-added
                NEW_SELECTED_COMPONENTS+="\"$comp\" "
            fi
        done
        echo "$NEW_SELECTED_COMPONENTS" > "$COMPONENTS_FILE"
        echo "✅ '$COMPONENT_TO_REMOVE' successfully removed and selected_components.txt updated."
    else
        echo "Removal cancelled for '$COMPONENT_TO_REMOVE'."
    fi
else
    echo "Component directory '$SERVICE_DIR' not found. Nothing to remove."
fi

echo "Check status with: docker ps -a"
