# Contributing to PiSelfhosting

First off, thank you for considering contributing! We welcome contributions from everyone. Whether you're reporting a bug, discussing features, or writing code, your help is valued.

This document provides guidelines for setting up your development environment and contributing to the project to ensure a smooth and effective process for everyone.

* [Code of Conduct](#-code-of-conduct)
* [Submitting an Issue](#-submitting-an-issue)
* [Feature Requests](#-feature-requests)
* [Development Quick Start](#-development-quick-start)
* [Development Philosophy](#️-development-philosophy)
* [Testing](#-testing)
* [Pull Request Process](#-pull-request-process)

## ✅ Code of Conduct

Help us keep this project open and inclusive. Please read and follow our [Code of Conduct](https://github.com/HenkVanHoek/PiSelfhosting/blob/main/CODE_OF_CONDUCT.md).

## 🐛 Submitting an Issue

A great way to contribute is to send a detailed issue when you encounter a problem. We always appreciate a well-written, thorough bug report.

* **Do not open a duplicate issue!** Search through existing issues to see if your problem has already been reported. If it has, you can add a "👍" reaction to show your support or comment with any additional information.
* Review the documentation before opening a new issue.
* Fully complete the provided issue template with as much detail as possible.

## ✨ Feature Requests

We are always open to new ideas! However, before submitting a feature request:

* **Search for existing requests** to avoid duplicates. If you find a similar request, add your thoughts to that conversation.
* Be precise about the proposed outcome and how it relates to existing features.
* Fully complete the feature request template to start a productive conversation.

## 👨‍💻 Development Quick Start

To run the application from source for development or testing, follow these steps.

### 1. Prerequisites

Ensure you have the following software installed on your workstation:

* `Git`
* `Python 3.10+`
* `pip` (Python's package installer)
* `Nmap`: A network scanning tool used by the `PiScanner`.
    * **On Windows:** Download the latest stable release installer (`nmap-*-setup.exe`) from the [Nmap website](https://nmap.org/download.html). Run the installer and **ensure you do not change the default installation path**. The application logic expects `nmap.exe` to be in its standard location.
    * **On macOS:** `brew install nmap`
    * **On Debian/Ubuntu:** `sudo apt-get update && sudo apt-get install nmap`

# Setting Up Your Development Environment

1.  Clone your fork of the repository locally.
    ```bash
    git clone [https://github.com/YOUR-USERNAME/PiSelfhosting.git](https://github.com/YOUR-USERNAME/PiSelfhosting.git)
    ```
2.  Navigate to the project directory.
    ```bash
    cd PiSelfhosting
    ```
3.  It is recommended to create a virtual environment.
    ```bash
    python -m venv .venv
    source .venv/bin/activate  # On Windows use `.venv\Scripts\activate`
    ```
4.  Install the required dependencies. The project uses three different files for managing Python packages:
    * **`requirements.txt`**: Contains packages needed for the normal execution of the application on your workstation.
    * **`requirements-dev.txt`**: Contains extra packages for development, such as testing tools.
    * **`requirements-pi.txt`**: Contains packages that are required on the target Raspberry Pi. This file is handled automatically by the installer and does not need to be installed on your development machine.

    To set up your development environment, install both the standard and development requirements:
    ```bash
    pip install -r requirements.txt -r requirements-dev.txt
    ```
5.  Run the application:
    ```bash
    python configurator_app/app.py
    ```

We look forward to your contributions!