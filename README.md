# PiSelfhosting

![GitHub license](https://img.shields.io/badge/license-MIT-blue.svg) ![GitHub stars](https://img.shields.io/github/stars/HenkVanHoek/PiSelfhosting.svg)

Welcome to PiSelfhosting! This project provides a user-friendly system to deploy and manage a suite of self-hosted services on a Raspberry Pi (or any Linux-based system) using Docker. Our goal is to make self-hosting powerful, accessible, and easy to maintain.

## 🌟 Key Features

*   **Fully Browser-Based Installer**: A simple, local web application guides you through every step, from device discovery to watching the live installation log, all without leaving your browser.
*   **Modular & Flexible**: Choose only the services you want from a curated list of popular applications.
*   **Dockerized & Isolated**: Every service runs in its own Docker container, making the system clean, secure, and easy to manage.
*   **Secure by Design**: Your sensitive information (like passwords) is handled securely and is not stored in plain text in the main configuration files.
*   **Integrated Configuration Tools**: Component-specific configuration tools are planned to be accessible directly from your dashboard.

## 🏛️ How It Works

The project is split into two main workflows: the **Development & Build Cycle** (how the software is packaged) and the **User Deployment Cycle** (how you install it).

![Development & Build Workflow Diagram](https://raw.githubusercontent.com/HenkVanHoek/PiSelfhosting/main/docs/images/development-cycle.png)

![User Deployment Workflow Diagram](https://raw.githubusercontent.com/HenkVanHoek/PiSelfhosting/main/docs/images/user-experience.png)

In short, a user downloads a single installer package from GitHub. The installer runs a local web-based "Configurator" for device discovery and component selection, which then streams the installation process directly into the browser.

## 📋 System Requirements

Before you begin, please ensure your system meets the following requirements.

#### On Your Main Computer (where you run the installer):
*   Windows, macOS, or Linux.
*   **For Linux Users:** The `nmap` utility must be installed. You can install it with `sudo apt update && sudo apt install nmap`.

#### On Your Raspberry Pi (or other Linux Server):
*   A Raspberry Pi 4 or newer is recommended.
*   Raspberry Pi OS (or another Debian/Ubuntu-based distribution).
*   Docker and Docker Compose must be installed.
*   SSH access must be enabled.

## 🚀 Quick Start Guide

Getting your self-hosted environment running is simple:

1.  **Visit our Website**: Go to `piselfhosting.com` to learn more.
2.  **Download the Installer**: Use the download link on the website to get the latest installer package from our GitHub Releases page.
3.  **Linux Users - One-Time Setup**: If you are running the installer on Linux, you must perform a one-time setup step to grant the necessary network permissions. See the "One-Time Setup for Linux Users" section below for instructions.
4.  **Unzip & Run**: Unzip the file on your main computer and run the single executable file (e.g., **PiSelfhosting-Configurator.exe**).
5.  **Configure**: The executable will launch the **Configurator** in your web browser. Use this graphical interface to find your Pi, select the components you want to install, and enter your server details.
6.  **Deploy & Watch**: After you confirm your selection, you will be taken to a new page in your browser where you can follow the installation progress live.

### One-Time Setup for Linux Users

To allow the PiSelfhosting scanner to discover devices on your network, you need to grant it special permission. This is a standard security procedure on Linux.

Please run the following two commands in your terminal. You will be asked for your password. **Make sure to replace `your_username` with your actual Linux username.**

1.  **Grant Permission:**

    echo 'your_username ALL=(ALL) NOPASSWD: /usr/bin/nmap' | sudo tee /etc/sudoers.d/99-piselfhosting

2.  **Set File Permissions:**

    sudo chmod 0440 /etc/sudoers.d/99-piselfhosting

This setup is secure and only allows the **nmap** command used by PiSelfhosting to run with the necessary permissions.

## 🧩 Supported Components

PiSelfhosting supports a curated list of popular and powerful self-hosted services. The installer allows you to select any combination of the following components.

For an up-to-date list of all supported components and their details, please see the automatically generated table here:

➡️ **Supported Components List**

## 🔧 Component Specific Notes

After installation, some components require additional setup or have important considerations.

### Matrix (Conduit)
* **Domain Name Required**: For your Matrix server to communicate with other servers (federation), it **must** be accessible on the internet via a domain name.
* **Reverse Proxy**: You must configure your reverse proxy (like Traefik) to correctly route traffic to the Conduit container.

### Reverse Proxies (Traefik / Nginx Proxy Manager)
* **Choose One**: You should only run **one** reverse proxy at a time as they both need to use the standard web ports (80 and 443).

### DNS Ad-Blockers (Pi-hole / AdGuard Home)
* **Router Configuration**: After installation, you must log in to your router and change its **LAN/DHCP DNS server** setting to the IP address of your Raspberry Pi.

### Jellyfin
* **Hardware Acceleration**: The installer will attempt to select the correct hardware acceleration settings for your Pi model.
* **Media Libraries**: You will need to configure your media libraries inside the Jellyfin web UI after installation.

## 🤝 Contributing

We welcome contributions! For guidelines on how to contribute, please see our [CONTRIBUTING.md](CONTRIBUTING.md) file.

## 📄 License

This project is open-source and available under the [MIT License](LICENSE).