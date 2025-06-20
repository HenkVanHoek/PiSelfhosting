#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e

echo "🚀 Starting PiSelfhosting Configuration Web Interface Bootstrap"
echo "------------------------------------------------------------"

# --- 1. Check for Docker installation ---
if ! command -v docker &> /dev/null
then
    echo "🐳 Docker is not installed. Installing Docker..."
    curl -sSL https://get.docker.com | sh

    # Add current user to the 'docker' group to run Docker commands without 'sudo'
    sudo usermod -aG docker "$USER"

    echo ""
    echo "=================================================================================="
    echo "  IMPORTANT: Docker group changes require a logout/login or system reboot."
    echo "  Please log out of your SSH session and log back in (or reboot your Raspberry Pi)."
    echo "  After that, run this 'bootstrap.sh' script again to continue the setup."
    echo "=================================================================================="
    echo ""
    exit 0 # Exit so the user can re-login
else
    echo "🐳 Docker is already installed."
fi

# --- 2. Define and Get DOMAIN environment variable ---
# Use the remembered domain if available, otherwise prompt the user.
# Your remembered domain is "henkenyvonne.nl"
DEFAULT_DOMAIN="henkenyvonne.nl" # Using your preferred domain

# Check if DOMAIN is already set in the environment or .env file, otherwise prompt
if [ -z "$DOMAIN" ]; then
    if [ -f ".env" ]; then
        # Load .env file if it exists, to check for DOMAIN
        set -a
        source .env
        set +a
    fi

    if [ -z "$DOMAIN" ]; then
        read -p "Enter your main domain (e.g., $DEFAULT_DOMAIN): " USER_INPUT_DOMAIN
        DOMAIN="${USER_INPUT_DOMAIN:-$DEFAULT_DOMAIN}" # Use user input or default
    fi
fi

# Ensure DOMAIN is written to .env if it was just entered or not present
if ! grep -q "DOMAIN=" ".env" 2>/dev/null; then
    echo "DOMAIN=$DOMAIN" >> .env
elif ! grep -q "DOMAIN=$DOMAIN" ".env"; then
    # Update DOMAIN if it exists but has a different value
    sed -i "/^DOMAIN=/c\DOMAIN=$DOMAIN" .env
fi

echo "Using domain: $DOMAIN"

# --- 3. Build the web interface Docker image ---
echo "📦 Building the PiSelfhosting config web image..."
# Assume your web interface code is in a directory named 'web-config'
# Adjust 'web-config' if your actual web interface directory name is different.
WEB_CONFIG_DIR="./web-config"
if [ ! -d "$WEB_CONFIG_DIR" ]; then
    echo "❌ Error: Web configuration directory '$WEB_CONFIG_DIR' not found."
    echo "Please ensure your web interface code is in this directory."
    exit 1
fi

docker build -t piselfhosting-config-web "$WEB_CONFIG_DIR"

# Check if the build was successful
if [ $? -ne 0 ]; then
    echo "❌ Failed to build Docker image. Please check the build logs above for errors."
    exit 1
fi

# --- 4. Run the web interface container ---
echo "▶️ Starting the PiSelfhosting config web container..."

# Stop and remove existing container if it's already running or exists
if docker ps -a --format '{{.Names}}' | grep -q "piselfhosting-config-web"; then
    echo "Stopping existing 'piselfhosting-config-web' container..."
    docker stop piselfhosting-config-web || true
    echo "Removing existing 'piselfhosting-config-web' container..."
    docker rm piselfhosting-config-web || true
fi

# Run the container, mapping port 80 to the host and passing the DOMAIN variable
docker run -d \
    --name piselfhosting-config-web \
    -p 80:80 \
    -e DOMAIN="$DOMAIN" \
    piselfhosting-config-web

# Check if the container started successfully
if [ $? -ne 0 ]; then
    echo "❌ Failed to start Docker container. Please check Docker logs."
    exit 1
fi

echo "✅ PiSelfhosting Configuration Web Interface is now running!"
echo "------------------------------------------------------------"
echo "You can access it in your web browser:"
echo "  - Via the IP address of your Raspberry Pi (e.g., http://<YOUR_PI_IP_ADDRESS>)"
echo "  - If you've configured DNS for your Pi, you might try http://config.$DOMAIN or http://setup.$DOMAIN"
echo ""
echo "Note: If you plan to use this on a subdomain (like config.$DOMAIN), you'll likely need to configure Nginx Proxy Manager or Traefik later through the web interface itself."