# PiSelfhosting: Core Architectural Doctrine

**Version:** 2.1
**Status:** Active

This document records the foundational patterns and "lessons learned" that ensure the project's backend and frontend are robust, testable, and maintainable. All development must adhere to this doctrine.

## 1. Core Architectural Principles

### 1.1 The Application Factory Pattern

- **Principle**: The Flask application instance shall only be created inside a **create_app()** factory function. No global application object shall be instantiated at the module level.
- **Rationale**: This prevents critical circular import dependencies and is the definitive solution to test suite initialization failures, allowing for the creation of test-specific app instances with mocked dependencies.

### 1.2 The "Single Source of Truth" (SST) Principle

- **Principle**: For any given piece of configuration, there must be exactly one, unambiguous source. Data duplication is strictly forbidden.
- **Rationale**: This is the most critical principle for system stability. The definitive architecture is:
    - **config/components_metadata.json**: The SST for the *identity* and *structure* of a component. This includes its name, description, group, and pointers to other data contracts.
        - **"ui_port_variable"**: A pointer to the ID of the variable in `variables.json` that controls the component's main web port. This is the SST for which variable to use when generating a UI link. The static `ui_port` key is deprecated.
        - **"docker_service_name"**: For components with multiple services (e.g., an init container), this is a pointer to the name of the primary, user-facing service in the `docker-compose.template.yml`. This allows the system to generate links correctly.
    - **component_templates/.../variables.json**: The SST for the configurable *parameters* for a component, including their default values. The `required_variables` key is strictly forbidden in `components_metadata.json`.

For a detailed schema of these and other core data files, please refer to the **[DATA_CONTRACTS.md](DATA_CONTRACTS.md)** file.

### 1.3 The "Tarball" Deployment Pattern

- **Principle**: The preferred method for deploying multiple configuration files is to create a single, compressed archive, upload it, and then execute a remote command to extract it.
- **Rationale**: This pattern is an atomic, efficient, and robust operation that bypasses potential SFTP server quirks and permission issues that can occur when creating many small files individually.

## 2. Manager and Application Architecture

### 2.1 The Monorepo for Atomic Commits

- **Principle**: The **configurator_app** and **editor_app** shall coexist in the same repository.
- **Rationale**: This is a deliberate choice to ensure that a change to a core data contract (e.g., in **ComponentManager**) and the corresponding changes in both UIs can be made in a single, atomic commit, preventing architectural drift.

### 2.2 Managers as the Source of Truth

- **Principle**: Flask application routes (**app.py**) must be lightweight. All business logic, file I/O, and data manipulation must be encapsulated within dedicated manager classes (**ComponentManager**, **SetupManager**, etc.).
- **Rationale**: This creates a clean separation of concerns. The managers act as a stable, testable service layer, while the Flask routes are simply a thin API "veneer" that calls them.

### 2.3 The API as an Adapter

- **Principle**: If a refactored backend produces data in a new, cleaner format that a legacy frontend does not understand, the API endpoint itself must act as an "adapter."
- **Rationale**: The API must reshape the new data into the old format that the frontend expects. This prevents the need for complex, risky frontend changes and firmly places the responsibility for the API contract on the backend.

### 2.4 The Template Validator as a Gatekeeper

- **Principle**: The **ComponentManager** must provide a comprehensive validation method that is used as both an interactive tool for the user and as an automatic "gatekeeper" during the save process.
- **Rationale**: This "shift left" strategy catches configuration errors at the earliest possible moment. It prevents inconsistent data from being saved, which is critical for system reliability. The validator enforces a two-way contract: all variables used in a template must be defined, and all variables defined must be used.

### 2.5 The Variable and Macro System

- **Principle**: The system must provide a secure and robust way to manage both component-specific and global, system-provided configuration values.
- **Rationale**: This system separates sensitive, user-specific data (like domain names or API keys) from the version-controlled component templates. It is governed by two key macros that can be used in the **Default Value** field of a variable within the Component Editor.

- **The `{{ CONFIG_BASE_PATH }}` Macro**:
    - **Purpose**: To ensure that data paths for Docker volumes are portable and consistently located.
    - **Usage**: Use this macro as a prefix for any default value that represents a host-side data directory. For example: `{{ CONFIG_BASE_PATH }}/portainer/data`.
    - **Resolution**: The **SetupManager** will automatically replace this macro at deployment time with the final, absolute path for persistent data on the target device (e.g., `~/piselfhosting_data/config/portainer/data`).

- **The `{{ DOTENV.VARIABLE_NAME }}` Binding**:
    - **Purpose**: To securely link a component variable to a global, user-defined value stored in an **.env** file that is not committed to Git.
    - **Usage**: In the Component Editor, set the **Default Value** of a variable to `{{ DOTENV.YOUR_GLOBAL_VAR }}`, where `YOUR_GLOBAL_VAR` is a variable in the root **.env** file.
    - **Resolution**: The **SetupManager** will read the user **.env** file during deployment and substitute the value of `YOUR_GLOBAL_VAR` as the default for the component variable.

- **System-Provided Global Variables**:
    - **Principle**: A set of common, system-generated variables are automatically injected into the Jinja2 context during template rendering.
    - **SST**: The definitive list of these variable names is stored in `config/components_metadata.json` under the `_piselfhosting.global_variables` key. The editor's validator uses this list to allow these variables in templates without requiring them to be defined in `variables.json`.

### 2.6 The Init Container Pattern for Environment Preparation

- **Principle**: When a service requires specific file permissions or pre-start configuration that cannot be handled by Docker volumes alone, an "init container" shall be used.
- **Rationale**: This is the standard, robust pattern for preparing a complex environment. A small, temporary container (e.g., `busybox`) runs a specific command (like `chmod` or `touch`) and then exits. The main service is configured with a `depends_on` condition to only start after the init container has completed successfully, guaranteeing a correctly prepared environment.
- **Example**: This is used by the **Traefik** component to create the `acme.json` file and set its permissions to `600` before the main Traefik service starts.

## 3. ATC-Grade Testing Doctrine

- **Principle**: Unit tests must be hermetically sealed. They shall never perform real network I/O or touch the real file system (outside of a controlled, temporary directory provided by **pytest**).
- **Rationale**: Full isolation is the only way to guarantee fast, reliable, and platform-independent test execution.

## 4. Git Workflow and Commit Hygiene

- **Principle**: A single commit must represent a single, complete, logical unit of work that leaves the application in a fully-tested, stable state.
- **Principle**: The **git commit --amend** command is the standard procedure for adding corrections to a logical change that has not yet been pushed.
- **Rationale**: This ensures the final commit is atomic and avoids cluttering the history with "fix-up" commits. This is only safe for local commits.
