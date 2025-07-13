# PiSelfhosting Project Roadmap

This document outlines the development roadmap for PiSelfhosting. It is a living document that details our current priorities, planned features for upcoming releases, and long-term goals. Our aim is to be transparent about our direction and to help contributors understand where they can best apply their efforts.

## Guiding Principles

Our development is guided by the following principles:
1.  **Stability First**: Core features must be robust, reliable, and well-tested before new, complex functionality is added.
2.  **User Experience**: The primary goal is to simplify the self-hosting journey for our users.
3.  **Maintainability**: The codebase and architecture should remain clean, modular, and easy for new contributors to understand.

---

## Phase 1: Foundation & Core Usability (Current Focus)

This phase is focused on creating a rock-solid, feature-rich, and user-friendly installer with a single, well-supported database backend.

*   **[✅] Solidify Core Installer**: Refactor to a full Python application with a seamless web-based UI.
*   **[✅] Robust Component System**: Implement a metadata-driven system (`components_metadata.json`) to easily add and manage new services.
*   **[In Progress] Component Configuration Tools**: Develop modular, post-installation tools for key services (e.g., Frigate camera management) accessible from the user's dashboard.
*   **[In Progress] Comprehensive Testing**: Expand the `pytest` suite to ensure the reliability of the installer and utility functions.
*   **[In Progress] Documentation**: Create clear documentation for both end-users and contributors.
*   **[Planned] Integrated Backup & Restore**: Develop a user-friendly, Flask-based tool to back up and restore all persistent service data. This is a critical feature for data security and user peace of mind.
    *   **Implementation**: This will be a new, optional management tool built with Flask. It will provide a simple web UI to automatically detect and back up all persistent Docker volumes. The tool will feature **smart, configurable defaults**, allowing users to easily exclude large data volumes (like Frigate video recordings) to ensure fast and efficient backups of critical configuration data.*   **MariaDB as the Primary Database**: Standardize on MariaDB as the sole database option to ensure stability and reduce testing complexity. This provides excellent compatibility for the vast majority of popular self-hosted applications.

---

## Phase 2: Expansion & Flexibility (Future)

Once the foundation is stable and well-documented, this phase will focus on expanding the ecosystem and providing more options for advanced users.

*   **Introduce PostgreSQL Support**:
    *   **Why?**: To support a new class of powerful applications that require or strongly prefer PostgreSQL (e.g., Mastodon).
    *   **Implementation**: This will be a significant architectural update. It will involve adding PostgreSQL and `pgAdmin` as components, and updating the installer and component templates to handle the choice between MariaDB and PostgreSQL. This is a complex task reserved for a future major version to avoid destabilizing the core product.
*   **Advanced Installer Options**: Introduce an "Advanced Mode" in the installer for power users to tweak more specific Docker settings.

---

## Future Ideas & Long-Term Vision

This is a collection of ideas that are being considered for the long-term future, beyond Phase 2.

*   **Plugin Marketplace**: An interface where the community can submit new component templates for easy inclusion.
*   **Multi-Node/Clustering Support**: The ability to deploy services across multiple Raspberry Pi devices.
*   **Enhanced Security Auditing**: Tools to scan configurations for common security misconfigurations.

We welcome discussion on this roadmap! Please open an issue to discuss any of the points above or to propose new features.