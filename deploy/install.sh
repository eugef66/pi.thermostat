#!/usr/bin/env bash
# pi.thermostat installer for Raspberry Pi OS (the Lite image is fine).
#
# On a fresh Pi, over SSH:
#   curl -fsSL https://raw.githubusercontent.com/eugef66/pi.thermostat/HEAD/install.sh | sudo bash
#
# Or, from an unpacked copy of the project (a zip, or a clone):
#   sudo bash install.sh
#
# What it does:
#   1. installs the system packages it needs, including git (a fresh Lite image has none)
#   2. creates the "thermostat" service user and adds it to the gpio group
#   3. fetches the code into /opt/pi.thermostat (git clone, or copies the folder it runs from)
#   4. builds a Python virtual environment and installs the dependencies
#   5. creates data/ and certs/ and a config.toml you can edit
#   6. installs the short "th" command
#
# It never touches your settings or data. Running it again updates the code and leaves
# config.toml, data/ and certs/ alone, so it is also the way to update.
#
# Settings (environment variables, all optional):
#   REPO_URL      where to clone from      (default https://github.com/eugef66/pi.thermostat.git)
#   BRANCH        branch to clone          (default: the repository's default branch)
#   INSTALL_DIR   where to install         (default /opt/pi.thermostat)
#   SERVICE_USER  account that runs it     (default thermostat)
#   BIN_DIR       where "th" is installed  (default /usr/local/bin)
#   SKIP_APT=1    don't run apt (packages already installed)
#   SKIP_PIP=1    don't run pip (for testing)
# With "curl ... | sudo bash" pass them like:  curl ... | sudo REPO_URL=... BRANCH=... bash
set -Eeuo pipefail

REPO_URL="${REPO_URL:-https://github.com/eugef66/pi.thermostat.git}"
BRANCH="${BRANCH:-}"
INSTALL_DIR="${INSTALL_DIR:-/opt/pi.thermostat}"
SERVICE_USER="${SERVICE_USER:-thermostat}"
BIN_DIR="${BIN_DIR:-/usr/local/bin}"
SKIP_APT="${SKIP_APT:-0}"
SKIP_PIP="${SKIP_PIP:-0}"

STEP="starting"
say()  { printf '\n==> %s\n' "$*"; }
note() { printf '    %s\n' "$*"; }
warn() { printf '    WARNING: %s\n' "$*" >&2; }
die()  { printf '\nERROR: %s\n' "$*" >&2; exit 1; }

on_exit() {
  local rc=$?
  if [ "$rc" -ne 0 ]; then
    printf '\nThe install stopped during: %s (exit %s).\n' "$STEP" "$rc" >&2
    printf 'Fix the problem shown above and run the installer again; it is safe to repeat.\n' >&2
  fi
}
trap on_exit EXIT

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  sed -n '2,/^set -Eeuo/p' "${BASH_SOURCE[0]:-/dev/null}" 2>/dev/null | sed '$d; s/^# \{0,1\}//'
  exit 0
fi

[ "$(id -u)" -eq 0 ] || die "run this as root:  sudo bash install.sh   (or  curl ... | sudo bash)"

is_pi() {
  [ "${FORCE_PI:-0}" = 1 ] && return 0
  [ -r /proc/device-tree/model ] && tr -d '\0' < /proc/device-tree/model | grep -qi 'raspberry pi'
}

# --- where does the code come from? A folder next to this script, or git -------------
LOCAL_SRC=""
if [ -n "${BASH_SOURCE[0]:-}" ] && [ -f "${BASH_SOURCE[0]}" ]; then
  here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
  if [ -f "$here/thermostat/__main__.py" ] && [ -f "$here/requirements.txt" ]; then
    LOCAL_SRC="$here"
  fi
fi

echo "pi.thermostat installer"
note "install folder : $INSTALL_DIR"
note "service user   : $SERVICE_USER"
if [ -n "$LOCAL_SRC" ]; then note "code from      : $LOCAL_SRC"; else note "code from      : $REPO_URL${BRANCH:+ (branch $BRANCH)}"; fi
is_pi || note "this does not look like a Raspberry Pi: the GPIO/sensor libraries will be skipped"

# --- 1. system packages --------------------------------------------------------------
STEP="installing system packages"
if [ "$SKIP_APT" != 1 ]; then
  say "1/6  System packages (python, git, build tools, ...)"
  command -v apt-get >/dev/null 2>&1 || die "apt-get not found: this installer is for Raspberry Pi OS / Debian"
  export DEBIAN_FRONTEND=noninteractive
  apt-get update
  apt-get install -y --no-install-recommends \
      python3 python3-venv python3-dev build-essential git curl rsync ca-certificates
  # The sensor library needs libgpiod; its package name differs between OS releases.
  gpiod=""
  for p in libgpiod3 libgpiod2t64 libgpiod2; do
    if apt-cache show "$p" >/dev/null 2>&1; then gpiod="$p"; break; fi
  done
  if [ -n "$gpiod" ]; then
    apt-get install -y --no-install-recommends "$gpiod" || warn "could not install $gpiod"
  else
    warn "no libgpiod package found; the DHT22 sensor library may not work (see INSTALL.md, troubleshooting)"
  fi
else
  say "1/6  System packages: skipped (SKIP_APT=1)"
fi
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' \
  || die "Python 3.9 or newer is required (found $(python3 --version 2>&1))"
if [ -z "$LOCAL_SRC" ]; then
  command -v git >/dev/null 2>&1 || die "git is not installed (re-run without SKIP_APT=1)"
fi

# --- 2. service user -----------------------------------------------------------------
STEP="creating the service user"
say "2/6  Service user '$SERVICE_USER'"
if id "$SERVICE_USER" >/dev/null 2>&1; then
  note "already exists"
else
  useradd --system --create-home --shell /bin/sh "$SERVICE_USER"
  note "created (no password; it cannot log in)"
fi
if getent group gpio >/dev/null 2>&1; then
  usermod -aG gpio "$SERVICE_USER"
  note "added to the gpio group"
else
  warn "no 'gpio' group on this system: relay access will not work here (fine for the emulator)"
fi
SERVICE_HOME="$(getent passwd "$SERVICE_USER" | cut -d: -f6)"
as_user() {   # run a command as the service user with a sane environment
  runuser -u "$SERVICE_USER" -- env HOME="$SERVICE_HOME" PIP_DISABLE_PIP_VERSION_CHECK=1 "$@"
}

# --- 3. the code ---------------------------------------------------------------------
STEP="fetching the code"
say "3/6  Code in $INSTALL_DIR"
mkdir -p "$INSTALL_DIR"
if [ -n "$LOCAL_SRC" ]; then
  if [ "$(cd "$INSTALL_DIR" && pwd -P)" = "$LOCAL_SRC" ]; then
    note "running from the install folder already"
  else
    # replace the code folders, keep config.toml, data/, certs/, .venv
    for d in thermostat static deploy docs tests tools; do rm -rf "${INSTALL_DIR:?}/$d"; done
    tar -C "$LOCAL_SRC" --exclude=./.git --exclude=./.venv --exclude=./data --exclude=./certs \
        --exclude=./config.toml --exclude='__pycache__' --exclude='*.pyc' -cf - . \
      | tar -C "$INSTALL_DIR" -xf -
    note "copied from $LOCAL_SRC"
  fi
  chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"
elif [ -d "$INSTALL_DIR/.git" ]; then
  chown "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"
  if [ -n "$BRANCH" ]; then
    as_user git -C "$INSTALL_DIR" fetch --quiet origin "$BRANCH"
    as_user git -C "$INSTALL_DIR" checkout --quiet "$BRANCH"
  fi
  as_user git -C "$INSTALL_DIR" pull --ff-only
  note "updated"
elif [ -z "$(ls -A "$INSTALL_DIR")" ]; then
  chown "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"
  if [ -n "$BRANCH" ]; then
    as_user git clone --branch "$BRANCH" "$REPO_URL" "$INSTALL_DIR"
  else
    as_user git clone "$REPO_URL" "$INSTALL_DIR"
  fi
else
  die "$INSTALL_DIR exists, is not empty, and is not a git checkout. Move it away, or choose another folder with INSTALL_DIR=..."
fi
[ -f "$INSTALL_DIR/thermostat/__main__.py" ] || die "the code in $INSTALL_DIR does not look right (thermostat/__main__.py is missing)"

# --- 4. python environment -----------------------------------------------------------
STEP="building the Python environment"
say "4/6  Python environment (.venv)"
if [ ! -x "$INSTALL_DIR/.venv/bin/python" ]; then
  as_user python3 -m venv "$INSTALL_DIR/.venv"
  note "created"
else
  note "already exists"
fi
if [ "$SKIP_PIP" != 1 ]; then
  STEP="installing Python packages"
  as_user "$INSTALL_DIR/.venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt"
  if is_pi; then
    STEP="installing the Raspberry Pi GPIO and sensor libraries"
    if ! as_user "$INSTALL_DIR/.venv/bin/pip" install -r "$INSTALL_DIR/requirements-pi.txt"; then
      warn "the GPIO/sensor libraries did not install (details above)."
      warn "Everything else is installed. See INSTALL.md, Troubleshooting, then run:"
      warn "  sudo -u $SERVICE_USER $INSTALL_DIR/.venv/bin/pip install -r $INSTALL_DIR/requirements-pi.txt"
    fi
  else
    note "skipped the Raspberry Pi libraries (not a Pi); use hardware.emulate = true to try it"
  fi
else
  note "pip skipped (SKIP_PIP=1)"
fi

# --- 5. folders and config -----------------------------------------------------------
STEP="creating data, certs and config.toml"
say "5/6  data/, certs/ and config.toml"
as_user mkdir -p "$INSTALL_DIR/data" "$INSTALL_DIR/certs"
chmod 700 "$INSTALL_DIR/certs"
if [ -f "$INSTALL_DIR/config.toml" ]; then
  note "config.toml already exists: left as it is"
else
  as_user cp "$INSTALL_DIR/config.example.toml" "$INSTALL_DIR/config.toml"
  note "created config.toml from config.example.toml: edit it for your wiring"
fi

# --- 6. the th command ---------------------------------------------------------------
STEP="installing the th command"
say "6/6  The 'th' command"
mkdir -p "$BIN_DIR"
sed -e "s|/opt/pi.thermostat|$INSTALL_DIR|g" -e "s|sudo -u thermostat|sudo -u $SERVICE_USER|" \
    "$INSTALL_DIR/deploy/th" > "$BIN_DIR/th.new"
chmod 755 "$BIN_DIR/th.new"
mv -f "$BIN_DIR/th.new" "$BIN_DIR/th"
note "installed $BIN_DIR/th"

# --- check ---------------------------------------------------------------------------
STEP="checking the installation"
say "Checking"
cd "$INSTALL_DIR"      # python -m finds the package from the current folder
if out="$(as_user "$INSTALL_DIR/.venv/bin/python" -m thermostat check-config 2>&1)"; then
  printf '%s\n' "$out" | grep -E "^(server|certificate|private key|PIN)" | sed "s/^/    /"
else
  # The code is installed; only the settings file needs attention. Do not report the install as failed.
  warn "the installed program is fine, but check-config reports a problem with your settings:"
  printf '%s\n' "$out" | sed "s/^/        /" >&2
  warn "edit $INSTALL_DIR/config.toml (compare with config.example.toml), then run: th check-config"
fi
if is_pi && [ "$SKIP_PIP" != 1 ]; then
  as_user "$INSTALL_DIR/.venv/bin/python" -c "import RPi.GPIO" >/dev/null 2>&1 \
    && note "RPi.GPIO: ok" || warn "RPi.GPIO cannot be imported: relays will not work"
  as_user "$INSTALL_DIR/.venv/bin/python" -c "import adafruit_dht, board" >/dev/null 2>&1 \
    && note "DHT22 library: ok" || warn "the DHT22 library cannot be imported: see INSTALL.md, Troubleshooting"
fi

STEP="finished"
cat <<EOF

Installed.  Next (INSTALL.md has the details for each):

  1. Set your wiring:        sudo -u $SERVICE_USER nano $INSTALL_DIR/config.toml
  2. Check the hardware, with the relay board NOT connected to the furnace:
                             th test-sensor
                             th test-relays
  3. Choose a PIN:           th set-pin
  4. Start the control loop and the web server:
                             sudo cp $INSTALL_DIR/deploy/crontab.example /etc/cron.d/thermostat
                             sudo chmod 644 /etc/cron.d/thermostat
                             sudo cp $INSTALL_DIR/deploy/thermostat.service /etc/systemd/system/
                             sudo systemctl daemon-reload && sudo systemctl enable --now thermostat
     (the web server starts working once the certificate in step 5 is in place)
  5. HTTPS certificate:      INSTALL.md, section 7

To update later, run the same installer command again.
EOF
