# Contributing to PiSelfhosting

Thank you for considering contributing to PiSelfhosting! We welcome contributions from everyone, whether you're reporting bugs, suggesting features, or writing code. Your help is greatly appreciated.

This document provides guidelines for setting up your development environment and contributing effectively to the project.

## ✅ Code of Conduct

Help us keep this project open and inclusive. Please read and follow our [Code of Conduct](https://github.com/HenkVanHoek/PiSelfhosting/blob/main/CODE_OF_CONDUCT.md).

## 🚀 New to GitHub and Open Source? Welcome!

If this is your first time contributing to an open source project, don't worry - we're here to help! Here's a quick overview of the process:

### The GitHub Fork-and-Pull Workflow

1. **Fork the repository**: Click the "Fork" button on our [main repository page](https://github.com/HenkVanHoek/PiSelfhosting). This creates your own copy of the project under your GitHub account.

2. **Clone your fork**: Clone your forked repository (not the original) to your computer:
   ```bash
   git clone https://github.com/YOUR-USERNAME/PiSelfhosting.git
   ```
   Replace `YOUR-USERNAME` with your actual GitHub username.

3. **Make your changes**: Work on your improvements in your local copy.

4. **Push to your fork**: Upload your changes back to your forked repository on GitHub:
   ```bash
   git add .
   git commit -m "Description of your changes"
   git push origin main
   ```

5. **Create a Pull Request**: Go to your fork on GitHub and click "Pull Request" to propose your changes be merged into the main project.

### Why This Process?

This workflow protects the main project while giving you freedom to experiment. You can't accidentally break anything in the main repository - you're working in your own safe space! When you're ready, you submit a pull request for review.

### Don't Be Shy!

- **Small contributions matter**: Even fixing a typo or improving documentation helps!
- **Questions are welcome**: Open an issue if you're unsure about anything
- **Learning is expected**: We've all been beginners - ask questions and learn as you go
- **Community support**: The open source community is generally very supportive of newcomers

### Helpful Resources for Git/GitHub Beginners

- [GitHub's "Hello World" Guide](https://guides.github.com/activities/hello-world/)
- [Git Handbook](https://guides.github.com/introduction/git-handbook/)
- [First Contributions Guide](https://github.com/firstcontributions/first-contributions)

Remember: Every expert was once a beginner. Your fresh perspective as a newcomer can actually be very valuable!

## 🐛 Submitting an Issue

One of the best ways to contribute is by submitting detailed bug reports when you encounter problems.

**Before submitting a new issue:**
* **Search existing issues** to avoid duplicates. If you find a similar issue, add a "👍" reaction or comment with additional information
* **Review the documentation** to ensure the issue isn't covered there
* **Use the issue template** and provide as much detail as possible

## ✨ Feature Requests

We're always open to new ideas! Before submitting a feature request:

* **Check the [Project Roadmap](ROADMAP.md)** to see if your idea is already planned
* **Search existing requests** to avoid duplicates - if you find something similar, join that conversation instead
* **Be specific** about the proposed outcome and how it relates to existing features
* **Complete the feature request template** to start a productive discussion

## 👨‍💻 Development Quick Start

### Prerequisites

Ensure you have the following installed on your development workstation:

* **Git** - Version control system
* **Python 3.10+** - Core runtime
* **pip** - Python package installer (usually included with Python)
* **Ansible** - Required for the deployment automation. Install the full version (not just ansible-core):
  * **macOS:** `brew install ansible`
  * **Ubuntu/Debian:** `sudo apt-get update && sudo apt-get install ansible`
  * **Windows:** Use WSL (recommended) or install via pip: `pip install ansible`
* **Nmap** - Network scanning tool used for Pi discovery:
  * **Windows:** Download from the [official Nmap website](https://nmap.org/download.html). Use the default installation path
  * **macOS:** `brew install nmap`
  * **Ubuntu/Debian:** `sudo apt-get update && sudo apt-get install nmap`

### Setting Up Your Development Environment

1. **Fork and clone** the repository:
   ```bash
   git clone https://github.com/YOUR-USERNAME/PiSelfhosting.git
   cd PiSelfhosting
   ```

2. **Create a virtual environment** (recommended):
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements-dev.txt
   ```

4. **Run the application**:
   ```bash
   python main.py
   ```
   This will start the configurator web interface in your browser.

### Development Workflow

The application consists of:
- **Configurator** (Flask web app) - runs on your development machine
- **Pi Scanner** - discovers Raspberry Pis on your network
- **Deployment Engine** - uses Ansible to install services remotely on selected Pis
- **Docker Templates** - service definitions deployed as containers

## 📦 Package and Dependency Management

This project uses standard Python package management:

* **`requirements.txt`** - Core packages needed to run the application
* **`requirements-dev.txt`** - Development tools (testing, building, etc.) plus all core requirements

### Adding Dependencies

1. **Choose the right file:**
   - Core functionality → `requirements.txt`
   - Development/testing tools → `requirements-dev.txt`

2. **Pin exact versions** using `==` (e.g., `requests==2.31.0`) for reproducible builds

3. **Update your environment:**
   ```bash
   pip install -r requirements-dev.txt
   ```

## ✍️ Development Philosophy

* **User-Centric:** Prioritize simple, intuitive, and reliable user experiences
* **Clean Code:** Follow PEP 8, write clear and maintainable code
* **English Only:** All code, comments, documentation, and commit messages must be in English for international accessibility
* **Robust Error Handling:** Include comprehensive logging and error handling
* **Security-First:** Handle credentials securely, never commit secrets

## 🧪 Testing

We use `pytest` for testing. Run tests from the project root:

```bash
python src/utils/run_pytest_wrapper.py
```
