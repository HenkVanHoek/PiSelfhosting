# PiSelfhosting: Core Architectural Doctrine

**Version:** 2.2
**Status:** Active

This document records the foundational patterns and "lessons learned" that ensure the project's backend and frontend are robust, testable, and maintainable. All development must adhere to this doctrine.

## 1. Core Architectural Principles

### 1.1 The Application Factory Pattern

- **Principle**: The Flask application instance shall only be created inside a **create_app()** factory function. No global application object shall be instantiated at the module level.
- **Rationale**: This prevents critical circular import dependencies and is the definitive solution to test suite initialization failures, allowing for the creation of test-specific app instances with mocked dependencies.

### 1.2 The "Single Source of Truth" (SST) Principle

- **Principle**: For any given piece of configuration, there must be exactly one, unambiguous source. Data duplication is strictly forbidden.
- **Rationale**: This is the most critical principle for system stability. The definitive architecture is:
    - **config/components_metadata.json**: The SST for the *identity* and *structure* of a component.
    - **component_templates/.../variables.json**: The SST for the configurable *parameters* for a component, including their default values.

For a detailed schema of these and other core data files, please refer to the **[DATA_CONTRACTS.md](DATA_CONTRACTS.md)** file.

### 1.3 The "Tarball" Deployment Pattern

- **Principle**: The preferred method for deploying multiple configuration files is to create a single, compressed archive, upload it, and then execute a remote command to extract it.
- **Rationale**: This pattern is an atomic, efficient, and robust operation that bypasses potential SFTP server quirks and permission issues.

### 1.4 The "Read-Merge-Write" Pattern for Data Integrity

- **Principle**: Any UI-driven operation that modifies a configuration file (like `variables.json`) must perform a non-destructive update.
- **Rationale**: UIs may not be aware of all keys present in a data file. To prevent data loss, the backend must follow a "Read-Merge-Write" pattern:
    1.  **Read:** Load the entire original file content into memory.
    2.  **Merge:** Update only the specific keys provided by the UI payload.
    3.  **Write:** Save the entire, merged data structure back to the file.
-   This ensures that complex, backend-only fields (e.g., `other_files`, `depends_on`, `options`) are preserved even when the UI does not manage them.

## 2. Manager and Application Architecture

### 2.1 The Monorepo for Atomic Commits

- **Principle**: The **configurator_app** and **editor_app** shall coexist in the same repository.
- **Rationale**: This ensures that a change to a core data contract and the corresponding changes in both UIs can be made in a single, atomic commit, preventing architectural drift.

### 2.2 The "Smart Renderer" and Orchestrator Pattern

- **Principle**: Business logic for a specific domain should be encapsulated in its expert manager, while the overall process is handled by an orchestrator.
- **Rationale**: This creates a clean separation of concerns.
    - **The Expert (`ComponentManager`):** Acts as the "smart renderer." It is responsible for the complex logic of rendering a *single* component, including injecting component-specific context like Traefik labels, hostnames (`VIRTUAL_HOST`), and `component_id`.
    - **The Orchestrator (`SetupManager`):** Manages the overall file generation process. It orchestrates calls to the expert managers but does not contain component-specific rendering logic itself. It is also responsible for system-wide logic, such as automatically injecting `depends_on` directives.

### 2.3 The API as an Adapter

- **Principle**: If a refactored backend produces data in a new, cleaner format that a legacy frontend does not understand, the API endpoint itself must act as an "adapter."
- **Rationale**: The API must reshape the new data into the old format that the frontend expects. This places the responsibility for the API contract on the backend.

### 2.4 The Template Validator as a Gatekeeper

- **Principle**: The **ComponentManager** must provide a validation method that is used as both an interactive tool for the user and as an automatic "gatekeeper" during the save process.
- **Rationale**: This "shift left" strategy catches configuration errors at the earliest possible moment, preventing inconsistent data from being saved.

## 3. Networking and Service Architecture

### 3.1 Docker's Built-in DNS for Service Discovery

- **Principle**: All container-to-container communication **must** rely on Docker's built-in DNS service. The `extra_hosts` directive is forbidden for this purpose.
- **Rationale**: When containers are on the same user-defined network (e.g., `piselfhosting_net`), Docker provides a DNS server that automatically resolves a service's name (e.g., `pi-hole`) to its internal container IP. This is the simplest, most robust, and architecturally correct pattern for service discovery. It requires zero configuration and is dynamic. Full hostnames (e.g., `pi-hole.piselfhosting.com`) are for external access only and are managed exclusively by Traefik.

### 3.2 Automatic Dependency Injection for Traefik

- **Principle**: The dependency of a service on Traefik must be derived automatically from its metadata, not hardcoded in its template.
- **Rationale**: To prevent race conditions where a service starts before Traefik is ready to route its traffic, a dependency is required. The **SetupManager** (the orchestrator) is responsible for automatically injecting a `depends_on: [traefik]` directive into any service whose component metadata includes the `"has_traefik_support": true` flag. This centralizes the logic and keeps the component templates clean and generic.

### 3.3 The Init Container Pattern for Environment Preparation

- **Principle**: When a service requires specific file permissions or pre-start configuration, an "init container" shall be used.
- **Rationale**: This is the standard, robust pattern for preparing a complex environment. A small, temporary container (e.g., `busybox`) runs a command and then exits. The main service is configured with a `depends_on` condition to only start after the init container has completed successfully.
- **Example**: This is used by the **Traefik** component to create and permission `acme.json`.

## 4. ATC-Grade Testing Doctrine

- **Principle**: Unit tests must be hermetically sealed. They shall never perform real network I/O or touch the real file system (outside of a controlled, temporary directory).
- **Rationale**: Full isolation is the only way to guarantee fast, reliable, and platform-independent test execution. All external interactions (SSH, file system) must be mocked.

## 5. Git Workflow and Commit Hygiene

- **Principle**: A single commit must represent a single, complete, logical unit of work that leaves the application in a fully-tested, stable state.
- **Principle**: The **git commit --amend** command is the standard procedure for adding corrections to a logical change that has not yet been pushed.
- **Rationale**: This ensures the final commit is atomic and avoids cluttering the history with "fix-up" commits. This is only safe for local commits.
