#!/bin/sh
# Creates a private certificate authority (once) and a certificate for the thermostat's
# host name, signed by it. Use this when Let's Encrypt is not an option (for example your
# provider blocks inbound port 80). Install ca.crt on each phone/computer that will open the
# thermostat and they will trust it with no warnings; see docs/INSTALL.md, Option E.
#
# Run it on your laptop, NOT on the Pi: ca.key can mint certificates your devices trust,
# so keep it off the thermostat. Needs only openssl (Linux, macOS, WSL, Git Bash).
#
#   sh make-private-cert.sh thermostat.example.com [more names or IP addresses ...]
#
# Output, in ./private-ca (or $OUT_DIR):
#   fullchain.pem  privkey.pem   copy these two to the Pi's certs/ folder
#   ca.crt                       install this on your phone/computer (public, safe to share)
#   ca.key                       KEEP SECRET; needed to renew; never copy it to the Pi
#
# Run it again later with the same folder to issue a fresh certificate from the same CA
# (devices that already trust the CA need nothing).
set -eu

if [ $# -lt 1 ]; then
  echo "usage: sh $0 HOSTNAME [more names or IP addresses ...]" >&2
  exit 2
fi
NAME=$1
OUT="${OUT_DIR:-private-ca}"
CERT_DAYS="${CERT_DAYS:-730}"     # iPhones and Macs reject server certificates longer than 825 days
CA_DAYS="${CA_DAYS:-3650}"

command -v openssl >/dev/null 2>&1 || { echo "openssl is required" >&2; exit 1; }
if [ "$CERT_DAYS" -gt 825 ] 2>/dev/null; then
  echo "CERT_DAYS must be 825 or less" >&2
  exit 2
fi

umask 077
mkdir -p "$OUT"

if [ ! -f "$OUT/ca.key" ]; then
  echo "Creating the private CA in $OUT ..."
  openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -nodes \
      -keyout "$OUT/ca.key" -out "$OUT/ca.crt" -days "$CA_DAYS" -sha256 \
      -subj "/CN=Thermostat Private CA" \
      -addext "basicConstraints=critical,CA:TRUE,pathlen:0" \
      -addext "keyUsage=critical,keyCertSign,cRLSign" 2>/dev/null
else
  echo "Using the existing CA in $OUT"
fi

# Every name the thermostat will be opened by must be listed (the browser checks the exact name).
SAN=""
for n in "$@"; do
  case "$n" in
    *:*)            kind=IP  ;;    # IPv6 address
    *[!0-9.]*)      kind=DNS ;;    # contains something other than digits and dots: a name
    *)              kind=IP  ;;    # IPv4 address
  esac
  SAN="${SAN:+$SAN,}$kind:$n"
done

cat > "$OUT/server.ext" <<EXT
subjectAltName=$SAN
basicConstraints=critical,CA:FALSE
keyUsage=critical,digitalSignature
extendedKeyUsage=serverAuth
EXT

openssl req -new -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -nodes \
    -keyout "$OUT/privkey.pem" -out "$OUT/server.csr" -subj "/CN=$NAME" 2>/dev/null
openssl x509 -req -in "$OUT/server.csr" -CA "$OUT/ca.crt" -CAkey "$OUT/ca.key" \
    -CAcreateserial -out "$OUT/fullchain.pem" -days "$CERT_DAYS" -sha256 \
    -extfile "$OUT/server.ext" 2>/dev/null
rm -f "$OUT/server.csr" "$OUT/server.ext"

chmod 600 "$OUT/ca.key" "$OUT/privkey.pem"
chmod 644 "$OUT/ca.crt" "$OUT/fullchain.pem"

echo
echo "Certificate for: $SAN"
openssl x509 -in "$OUT/fullchain.pem" -noout -enddate | sed 's/^notAfter=/Valid until:    /'
echo
echo "Next:"
echo "  1. Copy $OUT/fullchain.pem and $OUT/privkey.pem to the Pi (INSTALL.md, Option E)."
echo "  2. Install $OUT/ca.crt on every phone/computer you will use."
echo "  3. Keep $OUT/ca.key private and off the Pi. Renew before the date above."
