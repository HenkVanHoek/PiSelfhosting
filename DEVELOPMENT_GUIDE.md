# PiSelfhosting: Core Development Principles & Architectural Doctrine

**Version:** 1.0
**Status:** Active

## 1. Core Architectural Principles

This section documents the foundational patterns that ensure the backend is robust, testable, and maintainable.

### 1.1 The Application Factory Pattern

- **Principle**: The Flask application instance shall only be created inside a `create_app()` factory function. No global application object shall be instantiated at the module level.
- **Rationale**: This prevents critical circular import dependencies between the application (`app.py`) and its managers. It is the definitive solution to test suite initialization failures and hangs, as it allows for the creation of test-specific app instances with mocked dependencies.

### 1.2 Dependency Injection for Testability

- **Principle**: Classes that interact with the file system or other external resources must be designed to have those resources injected into them. Hardcoded paths or resource locators are forbidden.
- **Rationale**: As demonstrated by the `SetupManager` refactoring, injecting the `template_base_path` was the only way to create a fully isolated and reliable unit test. This pattern allows us to substitute a real resource (like a template directory) with a temporary or mock version during testing.

### 1.3 Two-Pass Template Rendering

- **Principle**: The `SetupManager` must perform a "self-rendering" pass on its variable context before rendering the final component templates.
- **Rationale**: This correctly handles nested variables (e.g., `HOMARR_CONFIG_PATH` resolving to `{{ CONFIG_BASE_PATH }}/homarr`). This ensures that the final output files contain only fully-rendered values, preventing deployment failures on the target machine.

### 1.4 The "Single Source of Truth" Principle for Configuration

- **Principle**: For any given piece of configuration, there must be exactly one, unambiguous source of truth. Data duplication is strictly forbidden.
- **Rationale**: The entire series of bugs related to the "Access Your Services" summary was caused by a violation of this principle. We had default port numbers defined in template files, `variables.json`, and the `components_metadata.json` (SST). The definitive, ATC-grade solution was to establish a clear hierarchy: `variables.json` is the single source of truth for all defaults, which can be overridden by the user in the UI. This eliminates an entire class of bugs and makes the system predictable and maintainable.

### 1.5 The "Tarball" Deployment Pattern

- **Principle**: For deploying multiple configuration files to a remote system, the preferred method is to create a single, compressed archive (a "tarball"), upload it to a temporary location, and then execute a remote command to extract it.
- **Rationale**: This pattern is architecturally superior to uploading files one by one. Our debugging proved that individual SFTP file creation can fail due to subtle, hard-to-diagnose server-side permission or configuration issues (the `Failure` error). The single tarball upload is an atomic, more efficient, and far more robust operation that bypasses these potential SFTP server quirks.

## 2. ATC-Grade Remote Operations Doctrine

This new section is critical, as it captures the most difficult lessons we learned.

### 2.1 Never Assume the State of the Remote Environment

- **Principle**: All remote deployment scripts must be written with the assumption that they are operating on a minimal, hardened, and potentially non-standard base operating system.
- **Rationale**: Our entire debugging journey was a process of discovering and correcting false assumptions. We incorrectly assumed that `curl` would be installed, that Docker would be installed, that the user would have passwordless `sudo`, that the home directory would be in `/home/`, and that the filesystem would be writable by the user. An ATC-grade script must programmatically **check for** and, if necessary, **create** its required environment.

### 2.2 A TTY is Required for `sudo` Automation

- **Principle**: When automating commands that use `sudo` via a non-interactive SSH library like Paramiko, a pseudo-terminal (`pty`) must be allocated for the command channel.
- **Rationale**: We discovered that modern, secure Linux distributions will refuse to accept a piped password for `sudo` unless the session appears to be an interactive terminal. The `get_pty()` method is the definitive solution to the `sudo: a terminal is required to read the password` error.

### 2.3 All Long-Running Commands Must Be Streamed

- **Principle**: Any remote command whose execution time is non-deterministic or expected to exceed a few seconds (e.g., `apt-get update`, `docker pull`, `docker compose up`) **must** be executed via a streaming I/O method.
- **Rationale**: The use of a synchronous, blocking `execute_command` call for the Docker installation caused our client-side watchdog timer to consistently and correctly report a stall. An ATC-grade system must provide real-time feedback to the user and the monitoring system, which can only be achieved by reading the command's `stdout` and `stderr` as it is generated.

### 2.4 Always Reconnect After Changing Security Context

- **Principle**: After executing a remote command that fundamentally changes the user's security context (e.g., `systemctl stop apparmor` or `usermod -aG docker`), the current SSH session must be immediately closed and a new session must be established.
- **Rationale**: We proved that a user's new permissions (like the ability to run `docker` without `sudo`) are not applied to their existing, active SSH session. The "ghost of the old session" bug was one of the most subtle and difficult to diagnose. The only guaranteed way to operate in the new context is to reconnect.

## 3. ATC-Grade Testing Doctrine

This section defines the non-negotiable standards for all unit tests.

### 3.1 Full Isolation is Mandatory

- **Principle**: Unit tests must be hermetically sealed. They shall never perform real network I/O or touch the real file system (outside of a controlled, temporary directory).
- **Rationale**: The test suite hangs were caused by unmocked dependencies (Jinja2 s `FileSystemLoader`, the `Path` class) attempting real I/O. Full isolation is the only way to guarantee fast, reliable, and platform-independent test execution.

### 3.2 Use Explicit Manual Patching

- **Principle**: For complex test cases, especially those involving the Flask application, mocks shall be controlled by manually starting them in `setUp` and stopping them in `tearDown`.
- **Rationale**: The use of class-level decorators, while convenient, created subtle and difficult-to-diagnose bugs related to the mock lifecycle. The manual `patcher.start()` and `patcher.stop()` pattern is more verbose but provides unambiguous control and is the standard for robust test suites.

### 3.3 Test Data Must Match Application Contracts

- **Principle**: The data structures provided to a function in a test must be identical in type and shape to what the real application provides.
- **Rationale**: The `KeyError: 0` failure was caused by a test providing a dictionary where the application expected a list of dictionaries. The test suite must be the first line of defense for enforcing these internal API contracts.

## 4. Git Workflow and Commit Hygiene

### 4.1 Commits Must Be Atomic

- **Principle**: A single commit must represent a single, complete, logical unit of work that leaves the application in a fully-tested, stable state.
- **Rationale**: This creates a clean, professional, and easily auditable project history.

### 4.2 Use Amend for In-Flight Corrections

- **Principle**: The `git commit --amend` command shall be the standard procedure for adding corrections (e.g., test fixes) to a logical change that has not yet been pushed to a shared remote.
- **Rationale**: This ensures the final commit is atomic and avoids cluttering the history with "fix-up" commits. This is only safe for local commits.

## 5. Frontend and Backend Interaction

### 5.1 The API Contract is King

- **Principle**: The JSON keys sent by the frontend (`app.js`) must exactly match the keys expected by the backend (`app.py`).
- **Rationale**: The entire series of `400 Bad Request` errors was caused by a mismatch in a single key (`ip` vs. `ip_address`). This contract is absolute and is a primary focus for debugging.

### 5.2 Never Trust the Cache

- **Principle**: When debugging frontend issues, the first step is always a force refresh (**Ctrl+Shift+R**) to eliminate the browser cache as a variable. When debugging backend issues, the first step is always a full server restart to eliminate a stale process.
- **Rationale**: This establishes a clean, known state and prevents wasted time debugging issues that are environmental, not logical.
