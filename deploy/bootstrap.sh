#!/usr/bin/env bash
# One-time server setup (Ubuntu 24.04), run as root on the server:
#   ssh root@<ip> 'bash -s' < deploy/bootstrap.sh
# Installs Docker, opens only 22/80/443, turns on automatic security updates.
set -euo pipefail

apt-get update -q
apt-get install -yq ca-certificates curl ufw unattended-upgrades cron rsync
command -v docker >/dev/null || curl -fsSL https://get.docker.com | sh
systemctl enable --now docker cron

ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443
ufw --force enable

dpkg-reconfigure -f noninteractive unattended-upgrades
mkdir -p /opt/ledgerwise/deploy /var/backups
echo "bootstrap done: now copy deploy/.env to /opt/ledgerwise/deploy/.env (chmod 600) and run scripts/deploy.sh"
