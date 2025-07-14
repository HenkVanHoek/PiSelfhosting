#!/bin/bash

# ==============================================================================
#  Installation Script for PiSelfhosting Installer
# ==============================================================================

# Step 1: Check if the script is run as root (with sudo)
if [ "$(id -u)" -ne 0 ]; then
  echo "Please run this script with sudo: sudo ./install.sh" >&2
  exit 1
fi

echo "Installing PiSelfhosting Installer..."

# Step 2: Define source and destination paths
# Assumes the script is run from the directory containing the files
SOURCE_BINARY="PiSelfhosting-Installer-Linux"
SOURCE_ICON="images/piselfhosting-icon.png" # Assuming the icon is in the images folder
SOURCE_DESKTOP_FILE="piselfhosting-installer.desktop"

DEST_BIN="/usr/local/bin"
DEST_ICON="/usr/share/icons/hicolor/256x256/apps"
DEST_DESKTOP="/usr/share/applications"

# Step 3: Create destination directories if they don't exist
mkdir -p "$DEST_BIN"
mkdir -p "$DEST_ICON"
mkdir -p "$DEST_DESKTOP"

# Step 4: Copy files to their final locations
echo "Copying application..."
cp "$SOURCE_BINARY" "$DEST_BIN/"

echo "Copying icon..."
cp "$SOURCE_ICON" "$DEST_ICON/piselfhosting-installer.png"

echo "Creating application shortcut..."
# Update the .desktop file with the correct paths before copying
sed -i "s|Exec=.*|Exec=$DEST_BIN/$SOURCE_BINARY|" "$SOURCE_DESKTOP_FILE"
sed -i "s|Icon=.*|Icon=$DEST_ICON/piselfhosting-installer.png|" "$SOURCE_DESKTOP_FILE"
cp "$SOURCE_DESKTOP_FILE" "$DEST_DESKTOP/"

# Step 5: Make the application executable for all users
chmod +x "$DEST_BIN/$SOURCE_BINARY"

echo ""
echo "✅ Installation complete!"
echo "You can now find 'PiSelfhosting Installer' in your applications menu."

exit 0
