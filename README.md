<div align="center" dir="auto"><img width="150" height="150" style="max-width: 100%; height: auto; max-height: 150px;" alt="piselfhosting-icon512x512" src="https://github.com/HenkVanHoek/assets/63ed723a-578f-47f9-b40b-e241c4c5935b" /></div>

# PiSelfhosting

Welcome to PiSelfhosting! This project provides a user-friendly system to deploy and manage a suite of self-hosted services on a Raspberry Pi (or any Linux-based system) using Docker. Our goal is to make self-hosting powerful, accessible, and easy to maintain.

## 🌟 Key Features

- **Fully Browser-Based Installer**: A simple, local web application guides you through every step, from device discovery to watching the live installation log.
- **Modular & Flexible**: Choose only the services you want from a curated list of popular applications.
- **Dockerized & Isolated**: Every service runs in its own Docker container, making the system clean, secure, and easy to manage.
- **Component Editor**: A powerful web-based tool for developers to add, manage, and configure all components in the PiSelfhosting ecosystem.

## 🏛️ How It Works

A user downloads a single installer package from GitHub Releases. The installer runs a local web-based "Configurator" for device discovery and component selection, which then generates the necessary Docker Compose files and streams the installation process directly into the browser for the user.

## 📋 System Requirements

**On Your Main Computer (where you run the installer):**
- Windows, macOS, or Linux.
- **Linux Users**: The **nmap** utility must be installed (`sudo apt install nmap`).

**On Your Target Server (e.g., Raspberry Pi):**
- A Raspberry Pi 4 or newer is recommended.
- Or, use a Debian-based server, such as the one provided by [pi-server-vm](https://github.com/HenkVanHoek/pi-server-vm).
- Docker and Docker Compose must be installed.
- SSH access must be enabled.

## 🚀 Quick Start Guide

1.  **Download the Installer**: Go to the [GitHub Releases page](https://github.com/HenkVanHoek/PiSelfhosting/releases) and download the latest installer for your operating system.
2.  **Run the Installer**: Unzip the file and run the `PiSelfhosting-Configurator` executable.
3.  **Configure**: Your web browser will open to the configurator UI. Follow the on-screen steps to discover your device, select software, and provide any required configuration.
4.  **Deploy**: After confirming your selections, the system will generate the necessary files and allow you to deploy them to your target device, with a live log of the entire process.

### One-Time Setup for Linux Users

If you are running the installer on a `Linux desktop`, you must perform a one-time setup to grant the scanner the necessary network permissions. Replace `your_username` with your actual Linux username.

    echo "your_username ALL=(ALL) NOPASSWD: /usr/bin/nmap" | sudo tee /etc/sudoers.d/99-piselfhosting
    sudo chmod 0440 /etc/sudoers.d/99-piselfhosting

## 🤝 Contributing
We welcome contributions! For guidelines on how to get started with development, please see our `CONTRIBUTING.md` file. To understand the core design principles and data contracts of the project, please review the `ARCHITECTURE.md` file.

## 📄 License

This project is open-source and available under the MIT License.

You can also find more information about this project on my GitHub page: [HenkVanHoek/PiSelfhosting](https://github.com/HenkVanHoek/PiSelfhosting).
