# Contributing to PiSelfhosting

We highly appreciate your interest in contributing to PiSelfhosting! Every contribution, no matter how small, helps to improve the project.

## How Can You Contribute?

There are several ways you can contribute:

*   **Reporting Bugs:** If you find a bug, please create an issue in our issue tracker. Include a clear description of the bug, the steps to reproduce it, and any error messages.
*   **Suggesting Features:** Have an idea for a new feature or an improvement? Create an issue to discuss your idea.
*   **Contributing Code:** You can contribute by fixing bugs, implementing new features, or improving the documentation.

## Code Contribution Guidelines

*   **Fork the Repository:** Create a fork of the repository to your own GitHub account.
*   **Create a Feature Branch:** Make a new branch for your changes. Use a clear branch name, for example, `feature/new-application` or `bugfix/login-issue`.
*   **Write Clear Code:** Ensure your code is well-readable and documented. All code, comments, and documentation must be in English.
*   **Add Tests:** If you add new functionality, please also add tests to verify its correct operation.
*   **Submit a Pull Request:** When you are finished with your changes, submit a pull request to the `main` branch of the original repository. Provide a clear description of the changes you have made.

## Setting Up Your Development Environment

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
    source .venv/bin/activate  # On Windows use `.venv\Scripts\activate`
    ```
4.  Install the required dependencies:
    ```bash
    pip install -r requirements.txt
    ```
5.  Run the application:
    ```bash
    python configurator_app/app.py
    ```

We look forward to your contributions!