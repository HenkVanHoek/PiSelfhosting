#!/bin/bash
# PiSelfhosting Docker Compose Command Helper
# Location: /home/PiSelfhosting/scripts/get_docker_compose_cmd.sh

if command -v docker &>/dev/null && docker compose version &>/dev/null; then
    echo "docker compose" # Docker Compose V2 plugin
elif command -v docker-compose &>/dev/null; then
    echo "docker-compose" # Docker Compose V1 standalone
else
    echo "" # Not found
fi
