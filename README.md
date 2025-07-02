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

![Development & Build Workflow Diagram](docs/images/development-cycle.jpg)
![User Deployment Workflow Diagram](docs/images/user-experience.jpg)
In short, a user downloads a single installer package. This package runs a local web-based "Configurator" for component selection, which then launches a command-line "Executor" to perform the actual installation on the Raspberry Pi.

## 🚀 Quick Start Guide

Getting your self-hosted environment running is simple:

1.  **Visit our Website**: Go to `piselfhosting.com` to see the available components and learn more.
2.  **Download the Installer**: Use the download link on the website to get the latest installer package (`PiSelfhosting-Installer.zip`) from our GitHub Releases.
3.  **Unzip & Run**: Unzip the file on your main computer (Windows, Mac, or Linux) and run the `start` script (`start.bat` or `start.sh`).
4.  **Configure**: The `start` script will launch the **Configurator** in your web browser. Use this graphical interface to select the components you want to install and enter your server details (Pi's IP address, etc.).
5.  **Deploy**: After you confirm your selection, the **Executor** will launch in a new terminal window. It will connect to your Raspberry Pi and handle the entire installation automatically. You can follow the progress live in this terminal.

## 🔧 Using the Helper Tools

After installation, you can manage your services using the included helper tools. These are located in the `scripts/` directory and are designed to be run via their wrapper scripts.

For example, to configure cameras for Frigate, you would run:
```bash
bash scripts/run-frigate-config-tool.sh