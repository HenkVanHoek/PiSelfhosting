# Still in test phase, beware!

# PiSelfhosting

## Self-Hosted Services for Raspberry Pi with Docker

Welcome to PiSelfhosting! This project provides a set of automated scripts and configurations to easily deploy and manage various self-hosted services on a Raspberry Pi (or any compatible Linux system) using Docker and Docker Compose. Our goal is to make self-hosting accessible, maintainable, and robust.

## 🌟 Features

* **Modular Deployment:** Select only the services you need during setup.
* **Dockerized Services:** Each service runs in its own isolated Docker container for easy management and updates.
* **Automated Configuration:** Scripts handle the generation of `docker-compose.yml` files and initial configuration.
* **User-Friendly Tools:** Interactive Python scripts for common tasks like camera configuration, dashboard tile management, and SSL certificate setup.
* **Centralized `.env`:** Manage all your environment variables from a single `.env` file.
* **Dependency Management:** Services are started and managed in the correct order to ensure dependencies are met.
* **Nginx Proxy Manager Integration:** Easily configure reverse proxies and obtain free SSL certificates with Let's Encrypt. Includes automated database setup for NPM.

## 🛠️ Prerequisites

Before you begin, ensure you have the following on your Raspberry Pi (or Linux machine):

* **Operating System:** Raspberry Pi OS Lite (recommended) or any Debian-based Linux distribution.
* **SSH Access:** Enabled and configured for remote management.
* **Git:** Installed to clone this repository (`sudo apt install git`).
* **`whiptail`:** For interactive menus in shell scripts (`sudo apt install whiptail`).
* **`envsubst`:** From `gettext-base` package (`sudo apt install gettext-base`).
* **Python 3 & Pip:** Required for configuration tools (`sudo apt install python3 python3-pip`).
* **Docker & Docker Compose (v2 recommended):** The `deploy.sh` script will attempt to install these for you if not found.

## 🚀 Quick Start

Follow these steps to get your PiSelfhosting environment up and running:

1.  **Clone the Repository:**
    ```
    git clone [https://github.com/HenkVanHoek/PiSelfhosting.git](https://github.com/HenkVanHoek/PiSelfhosting.git) /home/PiSelfhosting
    cd /home/PiSelfhosting
    ```
    *Replace `HenkVanHoek` with your actual GitHub username.*

2.  **Run the Initial Setup Script:**
    This script will guide you through setting up your `.env` file and selecting which services to install.
    ```
    bash scripts/setup.sh
    ```

3.  **Deploy Your Selected Components:**
    This script generates the necessary Docker Compose files and initial configurations based on your `.env` and component selections.
    ```
    bash scripts/deploy.sh
    ```
    *You will be prompted to choose an overwrite mode for configuration files. `all` is recommended for first-time deployments.*

4.  **Start All Services:**
    This script brings up all your selected Docker containers in the correct order, ensuring dependencies like databases are ready first.
    ```
    bash scripts/start-all.sh
    ```

5.  **Verify Services:**
    Check if your containers are running:
    ```
    docker ps
    ```
    If any container fails to start, check its logs for errors: `docker logs -f <container_name>`

## 🔧 Configuration Tools

The `scripts/` directory contains various Python-based tools to help you configure specific services:

* **Frigate Camera Configuration:**
    ```
    bash scripts/run-frigate-config-tool.sh
    ```
    *Use this to add and manage your IP cameras in Frigate, including ONVIF discovery and RTSP URL testing.*

* **Dashy Tile Configuration:**
    ```
    bash scripts/run-dashy-tile-config-tool.sh
    ```
    *Automatically populate your Dashy dashboard with tiles for your installed services.*

* **Nginx Proxy Manager Database Setup:**
    ```bash
    bash scripts/run-npm-db-setup.sh
    ```
    *This script automates the creation of the `npm_database` in MariaDB and grants necessary permissions to your `pihost` user. It requires `DB_ROOT_PASS` to be set in your `.env` file for MariaDB root access. After running this script, you will need to perform the initial login to the Nginx Proxy Manager web interface and secure your administrator account.*

    **Manual Post-Setup Steps for Nginx Proxy Manager:**
    1.  **Initial Login to Nginx Proxy Manager UI:**
        Open your web browser and go to: `http://<YOUR_PI_IP_ADDRESS>:81`
        Use the default credentials for the first login:
        * **Email:** `admin@example.com`
        * **Password:** `changeme`
    2.  **Change Default Credentials (CRITICAL!):**
        Upon successful login, you will be prompted to change the default email and password. This is essential for your security. Choose a strong, unique password and use a valid email address for the admin account.
    3.  **Configure Your Proxy Hosts:**
        After securing your account, proceed to configure your proxy hosts. This involves adding new Proxy Hosts for services like Dashy, Nextcloud, etc., forwarding traffic to the correct internal Docker service names/ports, and requesting SSL Certificates (e.g., using Let's Encrypt) for your domains.

* **Mailserver Configuration:**
    ```
    bash scripts/run-mailserver-config-tool.sh
    ```
    *Helps configure Exim4 and Dovecot for your self-hosted mail server, including virtual user management and DNS record suggestions.*

* **SSL Certificate Manager:**
    ```
    bash scripts/run-ssl-cert-manager.sh
    ```
    *Provides guidance on obtaining and managing SSL certificates (via Nginx Proxy Manager or self-signed) for your services.*

## 🔄 Updating Services

To update all your installed Docker containers to their latest images:

*This script will stop all services, pull the latest images, recreate containers, and then start them in the correct order. You can also specify individual services, e.g., `bash scripts/restart-all.sh frigate`.*


## ➕ Adding/Removing Components

* **Adding a New Component:**
    1.  Run `bash scripts/setup.sh` again and select the new component(s) you wish to add.
    2.  Run `bash scripts/deploy.sh` (choose `create_if_missing` or `select` to avoid overwriting existing configs).
    3.  Run `bash scripts/start-all.sh` to start the new service(s).
    4.  Run `bash scripts/run-dashy-tile-config-tool.sh` to add the new service to your Dashy dashboard.

* **Removing a Component:**
    ```
    bash scripts/remove-component.sh
    ```
    *This interactive script allows you to select and completely remove a service, its Docker container, and associated data volumes.*

## Troubleshooting

* **`Permission Denied` Errors:** Ensure your user is part of the `docker` group (`sudo usermod -aG docker $USER`) and log out/in (or reboot) for changes to take effect. The `deploy.sh` script uses `sudo` for sensitive file operations, but overall ownership of the `/home/PiSelfhosting` directory by your user is recommended.

* **Services Not Starting:**
    * Check Docker logs: `docker logs -f <container_name>`
    * Ensure all required `.env` variables are set and correct.
    * Verify port availability.
    * If `mariadb` is not starting, try `bash scripts/restart-all.sh mariadb` to ensure a clean start with `initdb.d` scripts.

* **Pi-hole Admin Password Issue:** If you can't log into Pi-hole, use the `reset_pihole_password` instructions (see dedicated documentation for details).

* **`ffprobe` not found (in Frigate tool):** Install FFmpeg on your host: `sudo apt install ffmpeg`.

## 🤝 Contributing

Contributions are welcome! If you have suggestions, bug reports, or want to contribute code, please open an issue or submit a pull request on the GitHub repository.

## 📄 License

This project is open-source and available under the [MIT License](LICENSE)