# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog, and this project adheres to Semantic Versioning.

## [0.5.0] - 2025-10-06

### Added
- Traefik configuration validation in DeploymentManager to prevent duplicate internal ports and conflicting derived hostnames. ([296f1cf](https://github.com/HenkVanHoek/PiSelfhosting/commit/296f1cf))
- New `port_exclude_traefik` variable type in ComponentManager to allow excluding specific ports from Traefik label generation. ([ef0ddaa](https://github.com/HenkVanHoek/PiSelfhosting/commit/ef0ddaa), [7632f1d](https://github.com/HenkVanHoek/PiSelfhosting/commit/7632f1d))

### Changed
- Configurator UX/Security hardening: disable SSH credential fields when the "Manage" switch is off and auto-toggle on user input. ([ef0ddaa](https://github.com/HenkVanHoek/PiSelfhosting/commit/ef0ddaa), [7632f1d](https://github.com/HenkVanHoek/PiSelfhosting/commit/7632f1d))
- README: add reference to the pi-server-vm repository for Virtual Pi OS test server. ([faf21c4](https://github.com/HenkVanHoek/PiSelfhosting/commit/faf21c4))

### Fixed
- Editor: resolve "Save All Changes" failure and initialization stability issues in editor UI, adding defensive checks in `editor.v2.js`. ([faf21c4](https://github.com/HenkVanHoek/PiSelfhosting/commit/faf21c4))
- Deployment: finalize stability fixes and validation before any file transfer or remote execution (including conflict checks and better test harness). ([296f1cf](https://github.com/HenkVanHoek/PiSelfhosting/commit/296f1cf))
- Testing: explicit mock management in Configurator tests; temporary skip of unstable tests in terminal environment; various test cleanups. ([ef0ddaa](https://github.com/HenkVanHoek/PiSelfhosting/commit/ef0ddaa), [7632f1d](https://github.com/HenkVanHoek/PiSelfhosting/commit/7632f1d))

### Chore / Dependencies
- Fix dependency typo: use `argon2-cffi` instead of `argon-cffi`. ([9aaab1c](https://github.com/HenkVanHoek/PiSelfhosting/commit/9aaab1c))

---

Previous releases are not yet captured in this CHANGELOG. Future entries will continue following Keep a Changelog and SemVer.
