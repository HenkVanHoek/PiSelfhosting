# PiSelfhosting

![GitHub license](https://img.shields.io/badge/license-MIT-blue.svg) ![GitHub stars](https://img.shields.io/github/stars/HenkVanHoek/PiSelfhosting.svg)

Welcome to PiSelfhosting! This project provides a user-friendly system to deploy and manage a suite of self-hosted services on a Raspberry Pi (or any Linux-based system) using Docker. Our goal is to make self-hosting powerful, accessible, and easy to maintain.

## 🌟 Key Features

* **User-Friendly GUI Installer**: A simple, local web application guides you through selecting and configuring components. No command-line expertise is needed to get started.
* **Modular & Flexible**: Choose only the services you want from a curated list of popular applications.
* **Dockerized & Isolated**: Every service runs in its own Docker container, making the system clean, secure, and easy to manage.
* **Secure by Design**: Your sensitive information (like passwords) is handled securely and is not stored in plain text in the main configuration files.
* **Automated Helper Tools**: Powerful command-line tools help with complex tasks like discovering cameras for Frigate or managing service configurations.

## 🏛️ How It Works

The project is split into two main workflows: the **Development & Build Cycle** (how the software is packaged) and the **User Deployment Cycle** (how you install it).

![Development & Build Workflow Diagram](https://raw.githubusercontent.com/HenkVanHoek/PiSelfhosting/main/docs/images/development-cycle.png)

![User Deployment Workflow Diagram](https://raw.githubusercontent.com/HenkVanHoek/PiSelfhosting/main/docs/images/user-experience.png)

In short, a user downloads a single installer package from GitHub. The first step for the installer is to find the target Raspberry Pi on the network. The package then runs a local web-based "Configurator" for component selection, which launches a command-line "Executor" to perform the actual installation on the chosen Pi.

## 🚀 Quick Start Guide (For End-Users)

Getting your self-hosted environment running is simple:

1.  **Visit our Website**: Go to `piselfhosting.com` to see the available components and learn more.
2.  **Download the Installer**: Use the download link on the website to get the latest installer package (`PiSelfhosting-Installer.zip`) from our GitHub Releases.
3.  **Unzip & Run**: Unzip the file on your main computer (Windows, Mac, or Linux) and run the single executable file (e.g., `PiSelfhosting-Configurator.exe`).
4.  **Configure**: The executable will launch the **Configurator** in your web browser. Use this graphical interface to select the components you want to install and enter your server details (Pi's IP address, etc.).
5.  **Deploy**: After you confirm your selection, the **Executor** will launch in a new terminal window. It will connect to your Raspberry Pi and handle the entire installation automatically. You can follow the progress live in this terminal.


## 🧩 Supported Components

PiSelfhosting supports a curated list of popular and powerful self-hosted services. The installer allows you to select any combination of the following components.

For an up-to-date list of all supported components and their details, please see the automatically generated table here:

➡️ [**Supported Components List**](./SUPPORTED_COMPONENTS.md)

## 🔧 Component Specific Notes

After installation, some components require additional setup or have important considerations. Find the notes for your installed services below.

### Matrix (Conduit)
* **❗️ Domain Name Required**: For your Matrix server to communicate with other servers (federation), it **must** be accessible on the internet via a domain name (e.g., `matrix.yourdomain.com`).
* **Reverse Proxy**: You must configure your reverse proxy (like Traefik or Nginx Proxy Manager) to correctly route traffic to the Conduit container. This involves setting up specific `.well-known` files for server discovery.
* **Client**: Conduit is a backend server. To use it, you need to connect with a Matrix client like [Element](https://element.io/).

### Reverse Proxies (Traefik / Nginx Proxy Manager)
* **Choose One**: You should only run **one** reverse proxy at a time. Both Traefik and Nginx Proxy Manager need to use the standard web ports (80 and 443) to function, and only one service can use a port at a time.

### DNS Ad-Blockers (Pi-hole / AdGuard Home)
* **Router Configuration**: After installation, you must log in to your router and change its **LAN/DHCP DNS server** setting to the IP address of your Raspberry Pi. This will route all network traffic from your devices through the ad-blocker.
* **No other action is needed** for devices on your network to be protected once the router setting is changed.

### Jellyfin
* **Hardware Acceleration**: For the best performance on a Raspberry Pi, it is highly recommended to enable hardware acceleration. The installer will automatically select the correct settings based on your Pi model.
* **Media Libraries**: After starting Jellyfin, you will need to configure your media libraries inside the Jellyfin web UI. Point them to the correct paths inside the container (e.g., `/data/movies` and `/data/tvshows`).

## 🛠️ Using the Helper Tools

After installation, you can manage your services using the included helper tools. These are located in the `scripts/` directory and are designed to be run via their wrapper scripts.

### Pi Network Scanner
For development and advanced troubleshooting, a network scanner tool is included.
* **`src/pi_scanner.py`**: This is the core Python module that contains the logic for finding Raspberry Pi devices on the network.
* **`run_scanner_test.py`**: This script provides a simple command-line interface to run the scanner, ask for credentials, and see a report of discovered devices. It is the primary way to test the scanning functionality.

### Frigate Camera Configuration
To configure cameras for Frigate, you would run:
```bash
bash scripts/run-frigate-config-tool.sh
```
## 🤝 Contributing

We welcome contributions! For guidelines on how to contribute, please see our [CONTRIBUTING.md](CONTRIBUTING.md) file.

## 📄 License

This project is open-source and available under the <a href="https://github.com/HenkVanHoek/PiSelfhosting/blob/main/LICENSE" target="_blank" rel="noopener noreferrer">MIT License</a>.