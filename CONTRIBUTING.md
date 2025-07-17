# Contributing to PiSelfhosting

First off, thank you for considering contributing! We welcome contributions from everyone. Whether you're reporting a bug, discussing features, or writing code, your help is valued.

This document provides guidelines for setting up your development environment and contributing to the project to ensure a smooth and effective process for everyone.

* [Code of Conduct](#-code-of-conduct)
* [Submitting an Issue](#-submitting-an-issue)
* [Feature Requests](#-feature-requests)
* [Development Quick Start](#-development-quick-start)
* [Package and Dependency Management](#-package-and-dependency-management)
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

* **Check the [Project Roadmap](ROADMAP.md)** to see if your idea is already planned.
* **Search for existing requests** to avoid duplicates. If you find a similar request, add your thoughts to that conversation.
* Be precise about the proposed outcome and how it relates to existing features.
* Fully complete the feature request template to start a productive conversation.

## 👨‍💻 Development Quick Start

To run the application from source for development or testing, follow these steps.

## Prerequisites

Ensure you have the following software installed on your workstation:

*   `Git`
*   `Python 3.10+`
*   `pip` (Python's package installer)
*   `Ansible`: The automation engine that performs the installation on the Raspberry Pi. The `ansible-runner` library requires a full Ansible installation.
    *   **On macOS:** `brew install ansible`
    *   **On Debian/Ubuntu:** `sudo apt-get update && sudo apt-get install ansible`
    *   **On Windows (via WSL or pip):** It's recommended to use WSL (Windows Subsystem for Linux). Alternatively, you can install it via pip: `pip install ansible`
*   `Nmap`: A network scanning tool used by the `PiScanner`.
    *   **On Windows:** Download the latest stable release installer (`nmap-*-setup.exe`) from the Nmap website. Run the installer and **ensure you do not change the default installation path**. The application logic expects `nmap.exe` to be in its standard location.
    *   **On macOS:** `brew install nmap`
    *   **On Debian/Ubuntu:** `sudo apt-get update && sudo apt-get install nmap`


### Setting Up Your Development Environment

1.  Clone your fork of the repository locally.

    ```bash
    git clone https://github.com/YOUR-USERNAME/PiSelfhosting.git
    ```

2.  Navigate to the project directory.

    ```bash
    cd PiSelfhosting
    ```

3.  It is recommended to create a virtual environment.

    ```bash
    python -m venv .venv
    source .venv/bin/activate  # On Windows use .venv\Scripts\activate
    ```

4.  Install the required dependencies.

    ```bash
    pip install -r requirements.txt
    ```
5.  Run the application:

    ```bash
    python src/app.py
    ```

## 📦 Package and Dependency Management

This project uses `pip` and `requirements.txt` files to manage dependencies.

*   `requirements.txt`: Contains the core packages required for the application to run.
*   `requirements-dev.txt`: Contains all packages needed for development, including testing (`pytest`), building (`pyinstaller`), and any other development tools. This file also includes everything from `requirements.txt`.

### Adding or Updating a Package

1.  **Determine the correct file.** If the package is essential for the application to run, add it to `requirements.txt`. If it's only for development or testing, add it to `requirements-dev.txt`.
2.  **Pin the version.** Always specify an exact version number using `==` (e.g., `requests==2.31.0`). This ensures that everyone uses the same package version, leading to consistent and reproducible builds.
3.  **Update your environment.** After modifying a requirements file, run the following command to install the new packages into your virtual environment:
    ```bash
    pip install -r requirements-dev.txt
    ```

## ✍️ Development Philosophy

*   **User-Centric**: The primary goal is to create a simple, intuitive, and reliable experience for the end-user.
*   **Clean Code**: Write clear, readable, and maintainable code. Follow PEP 8 guidelines.
*   **Language Consistency**: To keep the project accessible and maintainable for an international audience, all code, comments, documentation, and commit messages must be written in **English**.
*   **Robustness**: Add error handling and logging to make the application resilient and easy to debug.
*   **Security**: Handle user credentials and sensitive data with care. Avoid storing secrets in version control.

## 🧪 Testing

We use `pytest` for testing. A wrapper script is provided to ensure tests are run from the project root with the correct paths.

To run the test suite, execute the following command from the project's root directory:

python src/utils/run_pytest_wrapper.py

Please ensure all existing tests pass and add new tests for any new features or bug fixes you introduce.

## 🚀 Pull Request Process

1.  Ensure your code lints and all tests are passing.
2.  Update the `README.md` and other relevant documentation with details of changes to the interface. This includes new environment variables, exposed ports, useful file locations, and container parameters.
3.  Increase the version numbers in any examples and the `.bumpversion.cfg` file to the new version that this Pull Request would represent. The versioning scheme we use is SemVer.
4.  You may merge the Pull Request in once you have the sign-off of at least one other developer, or if you do not have permission to do that, you may request the second reviewer to merge it for you.

We look forward to your contributions!
