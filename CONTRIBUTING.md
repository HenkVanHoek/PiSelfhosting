# Contributing to PiSelfhosting

Thank you for considering contributing to PiSelfhosting! We welcome contributions from everyone, whether you are reporting bugs, suggesting features, or writing code. Your help is greatly appreciated.

This document provides guidelines for setting up your development environment and contributing effectively to the project.

## ✅ Code of Conduct

Help us keep this project open and inclusive. Please read and follow our [Code of Conduct](https://github.com/HenkVanHoek/PiSelfhosting/blob/main/CODE_OF_CONDUCT.md).

## 🚀 New to GitHub and Open Source? Welcome!

If this is your first time contributing to an open source project, do not worry - we are here to help! Here is a quick overview of the process:

### The GitHub Fork-and-Pull Workflow

1. **Fork the repository**: Click the "Fork" button on our [main repository page](https://github.com/HenkVanHoek/PiSelfhosting). This creates your own copy of the project under your GitHub account.

2. **Clone your fork**: Clone your forked repository (not the original) to your computer:
   ```bash
   git clone https://github.com/YOUR-USERNAME/PiSelfhosting.git
   ```
   Replace **YOUR-USERNAME** with your actual GitHub username.

3. **Make your changes**: Work on your improvements in your local copy.

4. **Push to your fork**: Upload your changes back to your forked repository on GitHub:
   ```bash
   git add .
   git commit -m "Description of your changes"
   git push origin main
   ```

5. **Create a Pull Request**: Go to your fork on GitHub and click "Pull Request" to propose your changes be merged into the main project.

### Helpful Resources for Git/GitHub Beginners

- [The GitHub "Hello World" Guide](https://guides.github.com/activities/hello-world/)
- [Git Handbook](https://guides.github.com/introduction/git-handbook/)
- [First Contributions Guide](https://github.com/firstcontributions/first-contributions)

Remember: Every expert was once a beginner. Your fresh perspective as a newcomer can actually be valuable!

## 🐛 Submitting an Issue

One of the best ways to contribute is by submitting detailed bug reports when you encounter problems. Use the issue template and provide as much detail as possible.

## ✨ Feature Requests

We are always open to new ideas! Please check the [Project Roadmap](ROADMAP.md) and search existing requests before opening a new one.

## 👨‍💻 Development Setup

This section details how to get a fully functional development environment.

### 1. Development Environment Recommendations

- **Operating System:** An Ubuntu environment is strongly recommended, as it is the primary development and testing platform.
- **Virtualization Setup:** For users on other operating systems, we recommend running Ubuntu in a virtual machine using VirtualBox. To ensure proper network functionality for tests, please configure the **virtual machine network adapter** to **Bridged Mode**.

### 2. System-Level Dependencies

Ensure you have the following installed on your development workstation using the appropriate package manager for your OS (e.g., **apt**, **brew**, **choco**):

- **Git**: Version control system.
- **Python 3.11+**: The core runtime.
- **Ansible**: Required for deployment automation.
- **Nmap**: Network scanning tool used for Pi discovery.
- **sshpass**: Required for non-interactive SSH (primarily for Linux/macOS).

### 3. Python Project Setup

1.  **Fork and clone** the repository.
2.  **Create and activate a virtual environment**.
3.  **Install all dependencies from pyproject.toml**:

    pip install -e .[dev,test]

### 4. Critical: Platform-Specific Scanner Configuration

The Pi Scanner uses **nmap** to discover devices by their MAC address. This requires elevated permissions, and the setup is **different for each operating system**.

#### For Linux (Recommended)

On Linux, we use **setcap** to grant the **nmap** executable the specific network permissions it needs without requiring the entire application to run as root.

**Run this command one time after installing nmap:**

    sudo setcap cap_net_raw,cap_net_admin,cap_net_bind_service+eip $(which nmap)

This is a secure, permanent fix. The application can now be run as a normal user.

#### For Windows

On Windows, permissions are handled by the **Npcap driver** and the **Windows Firewall**.

1.  **Install Nmap:** Use the **official Nmap installer** from nmap.org. During the installation, you **must agree** to install the Npcap driver when prompted by the User Account Control (UAC).
2.  **Configure Firewall:** The Windows Defender Firewall will likely block scans. You must create an **inbound and outbound firewall rule** to allow traffic for the **nmap.exe** program, which is typically located in `C:\Program Files (x86)\Nmap`.

#### For macOS

macOS does not have a **setcap** equivalent. To perform a privileged scan, the script that calls **nmap** must be run with **sudo**.

When testing the scanner or running the Flask application, you will need to prepend the command with **sudo**. You will also need to use the full path to the Python interpreter within your virtual environment, for example:

    sudo .venv/bin/python -m flask run --host=0.0.0.0

## 🧪 Running the Application and Tests

### Running the Configurator Web App

To start the Flask development server for the configurator:

    flask run --host=0.0.0.0

### Running Tests

We use **pytest** for testing. Run tests from the project root:

    pytest

## ✍️ Development Philosophy

- **User-Centric:** Prioritize simple, intuitive, and reliable user experiences
- **Clean Code:** Follow PEP 8, write clear and maintainable code
- **English Only:** All code, comments, documentation, and commit messages must be in English for international accessibility
- **Robust Error Handling:** Include comprehensive logging and error handling
- **Security-First:** Handle credentials securely, never commit secrets

## 릴 Creating a New Release

This project has a standardized release workflow.

### 1. Pre-Commit Checks

Before committing your code, run the pre-commit hooks to automatically fix formatting and linting issues.

    pre-commit run --all-files

You may need to run this command twice if it makes changes the first time.

### 2. Bumping the Version

This project uses **bump-my-version** to update the version number across all necessary files (**pyproject.toml**, **README.md**, etc.), create a git commit, and tag the release.

To create a new patch release (e.g., 0.1.0 -> 0.1.1):

    bump-my-version patch

Use **minor** or **major** for larger version bumps.

### 3. Pushing to GitHub

After bumping the version, push your commit and the new tag to the repository.

    git push && git push --tags