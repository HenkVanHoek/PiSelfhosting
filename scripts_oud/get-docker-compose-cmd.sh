#!/bin/bash
# PiSelfhosting Docker Compose Command Helper
# Location: ${SCRIPTS_DIR}/get-docker-compose-cmd.sh # Escaped

if command -v docker &>/dev/null && docker compose version &>/dev/null; then
    echo "docker compose" # Docker Compose V2 plugin
else # Geen fallback naar docker-compose (V1)
    echo "" # Not found or not V2
fi
