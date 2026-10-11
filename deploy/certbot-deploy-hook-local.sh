#!/bin/sh
# Use this when certbot runs on the Pi itself. certbot keeps its files readable by
# root only, so after each issue/renewal this copies the certificate and key into the
# thermostat's certs/ folder with the right owner and permissions.
#
# Install on the Pi:
#   sudo install -m 755 /opt/pi.thermostat/deploy/certbot-deploy-hook-local.sh \
#        /etc/letsencrypt/renewal-hooks/deploy/thermostat.sh
#   sudo nano /etc/letsencrypt/renewal-hooks/deploy/thermostat.sh     # set CERT_NAME
#   sudo /etc/letsencrypt/renewal-hooks/deploy/thermostat.sh          # first copy, by hand
#
# The thermostat server notices the new files and reloads them; no restart is needed
# after the first time. For a certificate obtained on another machine, use
# certbot-deploy-hook-remote.sh instead.
set -eu

CERT_NAME="${CERT_NAME:-your-cert-name}"      # folder name under /etc/letsencrypt/live/
DEST_DIR="${DEST_DIR:-/opt/pi.thermostat/certs}"
OWNER="${OWNER:-thermostat}"
GROUP="${GROUP:-$OWNER}"

# certbot runs every hook for every certificate; only act for ours.
# (Run by hand, RENEWED_LINEAGE is not set and CERT_NAME is used.)
if [ -n "${RENEWED_LINEAGE:-}" ] && [ "$(basename "$RENEWED_LINEAGE")" != "$CERT_NAME" ]; then
  exit 0
fi
LINEAGE="${RENEWED_LINEAGE:-/etc/letsencrypt/live/$CERT_NAME}"

# install follows certbot's "live" symlinks. 644: certificate is public. 600: key private.
install -o "$OWNER" -g "$GROUP" -m 644 "$LINEAGE/fullchain.pem" "$DEST_DIR/fullchain.pem"
install -o "$OWNER" -g "$GROUP" -m 600 "$LINEAGE/privkey.pem"  "$DEST_DIR/privkey.pem"
