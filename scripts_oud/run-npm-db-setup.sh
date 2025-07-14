#!/bin/bash
# PiSelfhosting Nginx Proxy Manager Database Setup Script
# Location: /home/PiSelfhosting/scripts/run-npm-db-setup.sh
# This script ensures the Nginx Proxy Manager database and user permissions are correctly set up.

# Stop the script if any command fails
set -e

# Define base directories and important file paths (should be consistent with deploy.sh)
export BASE_DIR="/home/PiSelfhosting"
export SCRIPTS_DIR="$BASE_DIR/scripts"
export ENV_FILE="$BASE_DIR/.env" # Path to your .env file

# --- Load environment variables ---
load_env_vars() {
    if [ -f "$ENV_FILE" ]; then
        echo "Info: Loading environment variables from $ENV_FILE..."
        set -a # Automatically export all subsequent variable assignments
        source "$ENV_FILE"
        set +a # Turn off auto-export
        echo "✅ Environment variables loaded."
    else
        echo "❌ Error: .env file not found at $ENV_FILE. Please ensure it exists."
        exit 1
    fi
}

# --- Main logic ---
echo -e "\n--- Starting Nginx Proxy Manager Database Setup ---"

# Load environment variables to get DB credentials
load_env_vars

# Check if required variables are set
if [ -z "${DB_USER}" ] || [ -z "${DB_PASS}" ] || [ -z "${DOMAIN}" ]; then
    echo "❌ Error: Missing required environment variables (DB_USER, DB_PASS, DOMAIN). Please check your .env file."
    exit 1
fi

# Determine MariaDB container name (assuming consistent naming from deploy.sh)
MARIADB_CONTAINER_NAME="piselfhosting-mariadb"
NPM_CONTAINER_NAME="piselfhosting-nginxproxymanager"
NPM_DB_NAME="npm_database" # As defined in your docker-compose.yml for NPM

echo "Info: Checking if MariaDB container '$MARIADB_CONTAINER_NAME' is running..."
if ! docker ps --format '{{.Names}}' | grep -q "^${MARIADB_CONTAINER_NAME}$"; then
    echo "❌ Error: MariaDB container '$MARIADB_CONTAINER_NAME' is not running. Please start it first."
    exit 1
fi

echo "Info: Checking if Nginx Proxy Manager container '$NPM_CONTAINER_NAME' is running..."
if ! docker ps --format '{{.Names}}' | grep -q "^${NPM_CONTAINER_NAME}$"; then
    echo "Info: Nginx Proxy Manager container '$NPM_CONTAINER_NAME' is not running. Attempting to start it for setup."
    docker start "$NPM_CONTAINER_NAME" || { echo "❌ Error: Failed to start Nginx Proxy Manager. Exiting."; exit 1; }
    echo "Info: Started Nginx Proxy Manager for setup. Will stop it temporarily if needed."
    # Give it a moment to stabilize
    sleep 5
fi

echo "Info: Temporarily stopping Nginx Proxy Manager container for database operations..."
docker stop "$NPM_CONTAINER_NAME" || true # Use || true to prevent script from exiting if already stopped

echo "Info: Setting up database '$NPM_DB_NAME' and granting permissions to user '$DB_USER'..."

# IMPORTANT: Ensure DB_ROOT_PASS is set in your .env file for root access to MariaDB.
# If not set, this script will attempt to use DB_USER credentials, which might lack sufficient privileges.
if [ -z "${DB_ROOT_PASS}" ]; then
    echo "Warning: DB_ROOT_PASS not found in .env. Attempting to use DB_USER credentials for database creation and grants."
    MARIADB_USER_FOR_GRANTS="${DB_USER}"
    MARIADB_PASS_FOR_GRANTS="${DB_PASS}"
else
    echo "Info: Using MariaDB root credentials for database creation and grants."
    MARIADB_USER_FOR_GRANTS="root"
    MARIADB_PASS_FOR_GRANTS="${DB_ROOT_PASS}"
fi

# Create database if not exists
docker exec "$MARIADB_CONTAINER_NAME" mariadb -u "${MARIADB_USER_FOR_GRANTS}" -p"${MARIADB_PASS_FOR_GRANTS}" -e "CREATE DATABASE IF NOT EXISTS ${NPM_DB_NAME};"

# Grant privileges to the NPM database user (pihost)
docker exec "$MARIADB_CONTAINER_NAME" mariadb -u "${MARIADB_USER_FOR_GRANTS}" -p"${MARIADB_PASS_FOR_GRANTS}" -e "GRANT ALL PRIVILEGES ON ${NPM_DB_NAME}.* TO '${DB_USER}'@'%';"

# Flush privileges
docker exec "$MARIADB_CONTAINER_NAME" mariadb -u "${MARIADB_USER_FOR_GRANTS}" -p"${MARIADB_PASS_FOR_GRANTS}" -e "FLUSH PRIVILEGES;"

echo "✅ Database '$NPM_DB_NAME' created and permissions granted."

echo "Info: Starting Nginx Proxy Manager container..."
docker start "$NPM_CONTAINER_NAME"

echo -e "\n--- Nginx Proxy Manager Database Setup Complete ---\n"

# Manual steps instructions
echo "---------------------------------------------------------"
echo "           Nginx Proxy Manager Post-Setup Steps          "
echo "---------------------------------------------------------"
echo "Your Nginx Proxy Manager database and permissions are configured."
echo "Now, you need to perform the initial login and configure your proxy hosts."
echo ""
echo "1. Initial Login to Nginx Proxy Manager UI:"
echo "   Open your web browser and go to: http://<YOUR_PI_IP_ADDRESS>:81"
echo "   Use the default credentials for the first login:"
echo "   - Email:    admin@example.com"
echo "   - Password: changeme"
echo ""
echo "2. Change Default Credentials (CRITICAL!):"
echo "   Upon successful login, you will be prompted to change the default"
echo "   email and password. This is essential for your security. Choose"
echo "   a strong, unique password and use a valid email address for the"
echo "   admin account."
echo ""
echo "3. Configure Your Proxy Hosts:"
echo "   After securing your account, proceed to configure your proxy hosts."
echo "   This involves:"
echo "   - Adding new Proxy Hosts for services like Dashy, Nextcloud, etc."
echo "   - Forwarding traffic to the correct internal Docker service names/ports."
echo "   - Requesting SSL Certificates (e.g., using Let's Encrypt) for your domains."
echo ""
echo "For detailed instructions on configuring Proxy Hosts, please refer to the"
echo "official Nginx Proxy Manager documentation or your PiSelfhosting guides."
echo "---------------------------------------------------------"
