#!/bin/sh
# Runs on the Nextcloud server after every successful renewal.
# Install as /etc/letsencrypt/renewal-hooks/deploy/thermostat.sh (chmod 755).
#
# One-time setup:
#   1. On the Nextcloud server:  ssh-keygen -t ed25519 -N '' -f /root/.ssh/thermostat_deploy
#   2. On the Pi, in ~thermostat/.ssh/authorized_keys, one line (restricts the key
#      to writing into the certs directory only; it cannot open a shell):
#        command="rrsync -wo /opt/pi.thermostat/certs",restrict,from="NEXTCLOUD_LAN_IP" ssh-ed25519 AAAA... deploy
#      (rrsync ships with the rsync package: sudo apt install rsync)
#   3. Edit the three variables below.
set -eu

CERT_NAME="your-cert-name"          # directory name under /etc/letsencrypt/live/
PI_HOST="thermostat@192.168.1.50"   # service user @ Pi LAN address
KEY="/root/.ssh/thermostat_deploy"

# Only act for our certificate (hooks run for every renewed lineage).
[ "$(basename "${RENEWED_LINEAGE:-}")" = "$CERT_NAME" ] || exit 0

# -L: follow the "live" symlinks.  600: private key readable only by its owner.
rsync -L --chmod=F600 \
  -e "ssh -i $KEY -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=15" \
  "$RENEWED_LINEAGE/fullchain.pem" "$RENEWED_LINEAGE/privkey.pem" \
  "$PI_HOST:/"
# The thermostat server notices the new files and reloads them; no restart needed.
