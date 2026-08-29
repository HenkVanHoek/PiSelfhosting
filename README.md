<div align="center" dir="auto">
  <img width="140" height="140" alt="NjordDeploy & PiSelfhosting Evolution" src="https://github.com/HenkVanHoek/assets/63ed723a-578f-47f9-b40b-e241c4c5935b" />
  <h1>PiSelfhosting ➡️ NjordDeploy</h1>
  <p><strong>This project has evolved into <a href="https://github.com/HenkVanHoek/njord-deploy">NjordDeploy</a> — The Sovereign Stack Deployment Engine.</strong></p>
</div>

---

> [!IMPORTANT]
> ### 🚀 Project Transition & Graduation Notice
> **PiSelfhosting** has outgrown its original single-board footprint and has officially graduated into **[NjordDeploy](https://github.com/HenkVanHoek/njord-deploy)** and **[njorddeploy.com](https://njorddeploy.com)**.
>
> All active development, component templates, deployment tools, and web configurators are now maintained under the **NjordDeploy** ecosystem.

---

## 📖 The Story & Evolution

### 1. 🍓 How It Started (The Genesis)
PiSelfhosting began with a clear, inspiring mission: **taking back digital sovereignty from Big Tech**. The idea was to empower individuals and small organizations to run essential, privacy-respecting cloud applications (Nextcloud, Vaultwarden, Matrix, AdGuard) on accessible, energy-efficient Raspberry Pi hardware at home.

### 2. ⚡ How It Matured (Beyond the Single Board)
As real-world usage grew, so did the infrastructure requirements:
* **Multi-Node & Virtualization:** Workloads expanded from standalone single-board computers to **Proxmox VE hypervisors (x86 KVM & LXC)**.
* **Resilient Distributed Storage:** Simple local mounts evolved into a high-availability **Garage Distributed S3 cluster** spanning multiple nodes.
* **Edge Security & Mesh Networking:** Integrations with **Caddy Coraza WAF**, **CrowdSec**, and **Headscale/Tailscale VPN mesh** networks provided enterprise-grade protection.
* **100+ Component Catalog:** The collection of supported services grew from a handful of basic tools to over **100+ curated, production-ready container templates**.

### 3. 🌊 The Birth of NjordDeploy
With enterprise-grade virtualization, automated Ansible provisioning, and complete hardware independence (supporting bare-metal, VPS, Proxmox, and Raspberry Pi alike), the name *"Pi"* no longer represented the true scope and power of the platform.

Named after **Njörðr** (the Norse god of navigation, the sea, and safe harbors), **NjordDeploy** was launched as the modern, hardware-agnostic deployment engine and web configurator for the **Sovereign Stack**.

---

## 🧭 The New Ecosystem & Repositories

Please refer to the following active repositories for current releases, documentation, and contributions:

| Repository / Resource | Purpose |
| :--- | :--- |
| 🚀 **[HenkVanHoek/njord-deploy](https://github.com/HenkVanHoek/njord-deploy)** | **The Core Engine & Web Configurator**: The browser-based UI, orchestration tools, and Proxmox VM deployment suite. |
| 📦 **[HenkVanHoek/njord-deploy-components](https://github.com/HenkVanHoek/njord-deploy-components)** | **The 100+ Component Catalog**: Production-tested Docker Compose templates, metadata, and pre-packaged service stacks. |
| 🎨 **[HenkVanHoek/njord-deploy-design-system](https://github.com/HenkVanHoek/njord-deploy-design-system)** | **Design System & UI Components**: The unified UI framework powering NjordDeploy interfaces. |
| 🌐 **[njorddeploy.com](https://njorddeploy.com)** | **Official Portal & Showcase**: Live platform showcase, documentation, and guides. |
| 🛠️ **[HenkVanHoek/sysops](https://github.com/HenkVanHoek/sysops)** | **Infrastructure as Code (IaC)**: Centralized Ansible playbooks, monitoring, and fleet automation. |

---

## 🏛️ Historical Archive

The code in this repository is preserved for historical reference and archival purposes.

We thank everyone who tested, supported, and used PiSelfhosting during its foundational years. See you at **[NjordDeploy](https://github.com/HenkVanHoek/njord-deploy)**!

---

*Licensed under the [MIT License](LICENSE).*
