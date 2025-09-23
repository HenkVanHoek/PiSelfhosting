# PiSelfhosting: Core Architectural Doctrine

**Version:** 2.0
**Status:** Active

This document records the foundational patterns and "lessons learned" that ensure the project's backend and frontend are robust, testable, and maintainable. All development must adhere to this doctrine.

## 1. Core Architectural Principles

### 1.1 The Application Factory Pattern

- **Principle**: The Flask application instance shall only be created inside a **create_app()** factory function. No global application object shall be instantiated at the module level.
- **Rationale**: This prevents critical circular import dependencies and is the definitive solution to test suite initialization failures, allowing for the creation of test-specific app instances with mocked dependencies.

### 1.2 The "Single Source of Truth" (SST) Principle

- **Principle**: For any given piece of configuration, there must be exactly one, unambiguous source. Data duplication is strictly forbidden.
- **Rationale**: This is the most critical principle for system stability. The definitive architecture is:
    - **config/components_metadata.json**: The SST for the *identity* of a component (name, description, group, etc.).
    - **component_templates/.../variables.json**: The SST for the configurable *parameters* for a component, including their default values.

### 1.3 The "Tarball" Deployment Pattern

- **Principle**: The preferred method for deploying multiple configuration files is to create a single, compressed archive, upload it, and then execute a remote command to extract it.
- **Rationale**: This pattern is an atomic, efficient, and robust operation that bypasses potential SFTP server quirks and permission issues that can occur when creating many small files individually.

## 2. Manager and Application Architecture

### 2.1 The Monorepo for Atomic Commits

- **Principle**: The **configurator_app** and **editor_app** shall coexist in the same repository.
- **Rationale**: This is a deliberate choice to ensure that a change to a core data contract (e.g., in **ComponentManager** or **components_metadata.json**) and the corresponding changes in both UIs can be made in a single, atomic commit, preventing architectural drift.

### 2.2 Managers as the Source of Truth

- **Principle**: Flask application routes (**app.py**) must be lightweight. All business logic, file I/O, and data manipulation must be encapsulated within dedicated manager classes (**ComponentManager**, **SetupManager**, etc.).
- **Rationale**: This creates a clean separation of concerns. The managers act as a stable, testable service layer, while the Flask routes are simply a thin API "veneer" that calls them.

### 2.3 The API as an Adapter

- **Principle**: If a refactored backend produces data in a new, cleaner format that a legacy frontend does not understand, the API endpoint itself must act as an "adapter."
- **Rationale**: The API must reshape the new data into the old format that the frontend expects. This prevents the need for complex, risky frontend changes and firmly places the responsibility for the API contract on the backend.

### 2.4 The Template Validator as a Gatekeeper

- **Principle**: The **ComponentManager** must provide a comprehensive validation method that is used as both an interactive tool for the user and as an automatic "gatekeeper" during the save process.
- **Rationale**: This "shift left" strategy catches configuration errors at the earliest possible moment (during editing). It prevents inconsistent or invalid data from ever being saved, which is critical for system reliability. The validator must enforce a two-way contract: all variables used in a template must be defined, and all variables defined must be used.

## 3. ATC-Grade Testing Doctrine

### 3.1 Full Isolation is Mandatory

- **Principle**: Unit tests must be hermetically sealed. They shall never perform real network I/O or touch the real file system (outside of a controlled, temporary directory provided by **pytest**).
- **Rationale**: Full isolation is the only way to guarantee fast, reliable, and platform-independent test execution.

### 3.2 Test-Driven Development (TDD) for New Features

- **Principle**: All new backend functionality must be developed using the "Red-Green-Refactor" cycle. A failing test ("Red") must be written first to define the feature, then the minimal code to make it pass ("Green"), followed by a cleanup ("Refactor").
- **Rationale**: TDD produces a comprehensive test suite as a natural byproduct of development and ensures all code is written to be testable from the start.

## 4. Git Workflow and Commit Hygiene

### 4.1 Commits Must Be Atomic

- **Principle**: A single commit must represent a single, complete, logical unit of work that leaves the application in a fully-tested, stable state.

### 4.2 Use Amend for In-Flight Corrections

- **Principle**: The **git commit --amend** command is the standard procedure for adding corrections to a logical change that has not yet been pushed.
- **Rationale**: This ensures the final commit is atomic and avoids cluttering the history with "fix-up" commits. This is only safe for local commits.
