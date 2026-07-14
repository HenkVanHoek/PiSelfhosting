---
name: docker-deploy
description: Workflows voor het valideren en deployen van Docker-services via SSH op de Raspberry Pi (192.168.178.118) voor PiSelfhosting.
---

# Docker Deploy Workflow (PiSelfhosting)

Gebruik deze skill wanneer de gebruiker vraagt om Docker-containers of configuraties te deployen, verifiëren of te beheren op de Raspberry Pi.

## Locatie op Remote Server:
* Gebruiker/Host: `hvhoek@192.168.178.118`
* Doelmap: `/home/hvhoek/docker/`

## Deployment Stappenplan:
1. **Kopieer Bestanden**: Kopieer de benodigde configuratiebestanden (zoals `docker-compose.yaml` of `verify_env.sh`) naar de server:
   ```bash
   scp verify_env.sh docker-compose.yaml hvhoek@192.168.178.118:/home/hvhoek/docker/
   ```
2. **Valideer de Omgeving**: Voer het verificatiescript uit via SSH om te controleren of alle omgevingsvariabelen correct zijn ingesteld:
   ```bash
   ssh hvhoek@192.168.178.118 "cd /home/hvhoek/docker && ./verify_env.sh"
   ```
3. **Start/Update Containers**: Start of herstart de containers:
   ```bash
   ssh hvhoek@192.168.178.118 "cd /home/hvhoek/docker && docker compose up -d"
   ```
4. **Verifieer Status**: Controleer of de containers correct draaien:
   ```bash
   ssh hvhoek@192.168.178.118 "docker ps -a"
   ```
