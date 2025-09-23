# Contributing to PiSelfhosting

Thank you for considering contributing to PiSelfhosting! We welcome contributions from everyone.

This document provides guidelines for setting up your development environment and contributing effectively to the project.

## ✅ Code of Conduct

Please read and follow our [Code of Conduct](https://github.com/HenkVanHoek/PiSelfhosting/blob/main/CODE_OF_CONDUCT.md).

## 🏛️ Architectural Doctrine

Before making changes, it is essential to understand the core principles that guide our development. All contributions must adhere to the architectural standards for the project to ensure the system remains stable, maintainable, and testable.

**Please read the [ARCHITECTURE.md](https://github.com/HenkVanHoek/PiSelfhosting/blob/main/ARCHITECTURE.md) file to review these principles.**

## 🚀 Getting Started: The GitHub Workflow

1.  **Fork the repository**.
2.  **Clone your fork** to your local machine.
3.  Make your changes.
4.  **Push** your changes to your fork.
5.  Open a **Pull Request** to the main project repository.

## 👨‍💻 Development Setup

### 1. Environment

- **OS:** An Ubuntu environment is strongly recommended.
- **Virtualization:** For other OSes, use VirtualBox with the network adapter in **Bridged Mode**.

### 2. System Dependencies

Ensure **git**, **python3.11+**, **ansible**, **nmap**, and **sshpass** are installed on your system.

### 3. Project Installation

1.  Clone your forked repository.
2.  Navigate to the project root directory.
3.  Create and activate a Python virtual environment.
4.  Install all dependencies:

    pip install -e .[dev,test]

### 4. Nmap Permissions (Critical)

The Pi Scanner requires elevated permissions. This setup is OS-specific.

#### For Linux (Recommended)

You must add a **sudoers** rule to allow **nmap** to run without a password. Replace **your_username** with your actual Linux username.

    echo "your_username ALL=(ALL) NOPASSWD: /usr/bin/nmap" | sudo tee /etc/sudoers.d/99-piselfhosting
    sudo chmod 0440 /etc/sudoers.d/99-piselfhosting

#### For Windows & macOS

Please refer to the project's main **README.md** for detailed instructions on configuring Nmap and the firewall on these systems.

## 🧪 Running the Apps and Tests

### Run the Configurator App

    flask --app src.configurator_app.app:create_app run

### Run the Editor App

    flask --app src.editor_app.app:create_app run

### Run the Test Suite

From the project root directory:

    pytest

## 릴 Creating a New Release

1.  **Run Pre-Commit Checks**: `pre-commit run --all-files`
2.  **Bump the Version**: `bump-my-version patch` (or `minor`/`major`)
3.  **Push to GitHub**: `git push && git push --tags`
