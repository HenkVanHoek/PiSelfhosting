    cat <<'EOF_START_ALL' | sudo tee "$SCRIPTS_DIR/start-all.sh" > /dev/null
EOF_START_ALL
    cat <<'EOF_STOP_ALL' | sudo tee "$SCRIPTS_DIR/stop-all.sh" > /dev/null
EOF_STOP_ALL
    cat <<'EOF_RESTART_ALL' | sudo tee "$SCRIPTS_DIR/restart-all.sh" > /dev/null
EOF_RESTART_ALL
    cat <<'EOF_REMOVE_COMPONENT' | sudo tee "$SCRIPTS_DIR/remove-component.sh" > /dev/null
EOF_REMOVE_COMPONENT
    cat <<'EOF_GET_DOCKER_COMPOSE_CMD' | sudo tee "$SCRIPTS_DIR/get_docker_compose_cmd.sh" > /dev/null
EOF_GET_DOCKER_COMPOSE_CMD
