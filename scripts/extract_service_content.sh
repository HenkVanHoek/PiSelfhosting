# Maak een tijdelijke template file aan
cat <<EOF > /tmp/dashy_compose_template.tmp
services:
  dashy:
    container_name: piselfhosting-dashy
    image: lissy93/dashy:2.1.1
    restart: unless-stopped
    ports:
      - "8080:80" # Dashy HTTP port
      - "4443:443" # Dashy HTTPS port
    volumes:
      - ./config:/app/public/conf # Mount the config directory
    environment:
      - PUID=1000 # Host user ID, for file permissions
      - PGID=1000 # Host group ID
      - TZ=Europe/Amsterdam # Timezone
      - NODE_ENV=production
    extra_hosts:
      - "example.com:192.168.1.118" # Example DOMAIN:HOST_IP
    networks:
      - piselfhosting_net

networks:
  piselfhosting_net:
    external: true
EOF

# Gebruik envsubst om variabelen (indien aanwezig) in te vullen, net als deploy.sh
# Voor deze test vullen we ze handmatig in of zorgen dat ze al in de omgeving zijn
export DOMAIN="henkenyvonne.nl"
export HOST_IP="192.168.1.118"

envsubst < /tmp/dashy_compose_template.tmp > /tmp/dashy_compose_processed.tmp

echo "Processed template content for AWK test:"
cat -A /tmp/dashy_compose_processed.tmp
echo "--- End Processed template content ---"