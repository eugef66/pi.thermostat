# pi.thermostat

A web-controlled thermostat for a Raspberry Pi: it switches a gas furnace (one or
two stages), an air conditioner and a blower fan through a relay board, reads a
DHT22/AM2302 temperature and humidity sensor, and serves a phone-friendly app over
HTTPS with a Let's Encrypt certificate.

* **Install and wire it:** [docs/INSTALL.md](docs/INSTALL.md), with the
  [wiring diagram](docs/wiring.png) and the [Pi 3B GPIO pin map](docs/gpio-pinmap.png)
* **Try it on a laptop, no hardware:** [docs/EMULATOR.md](docs/EMULATOR.md)
* **Every command and API call, with examples:** [docs/REFERENCE.md](docs/REFERENCE.md)
* Rewritten from scratch; the earlier Bottle/Apache version is gone.

## Features

* Modes: Off, Heat, Cool, Auto, Fan. The app shows only what your hardware supports:
  leave `cool_pin` out of the config for a heat-only house, `fan_pin` out for a
  four-wire install, `heat2_pin` out for single-stage heat.
* Protection built in: deadband, minimum run and off times, heat/cool changeover
  lockout, compressor restart delay (also after a power cut), and fail-safe-off when
  the sensor stops working.
* One scheduled change ("start Heat 70° at 6:30 PM"), which you can cancel or replace.
* A dead-man switch: if the control loop stops while something is running, the server
  shuts everything off and shows a red banner.
* A single PIN or passphrase, scrypt-hashed. Failed logins are throttled and logged.
* A dependency-free web app that works as a home-screen shortcut.

## How it fits together

```
 phone ──HTTPS──▶ server.py (Cheroot, TLS, cert reload)     cron, every minute
                      │  api.py  /api/v1/*   auth.py              │
                      │  static.py  (the web app in static/)      │
                      ▼                                           ▼
                  engine.run_cycle  ◀── file lock + state.json ──▶ engine.run_cycle
                      │                                           │
                      └────────────── control.py (pure logic) ────┘
                                      hardware.py  → relays (GPIO) + DHT22
```

* `control.py` is pure logic with no I/O, which is why it has the most tests.
* Cron owns the sensor and the regular control pass. The server applies your changes
  immediately using the last reading, and runs the watchdog.
* Both take the same file lock, and relay timers live in `data/state.json`.
* Stopping the server never touches the relays; cron keeps controlling them.

## REST API (`/api/v1`)

JSON in and out. Errors: `{"error": {"code": "...", "message": "..."}}`.

| Request | Purpose |
|---|---|
| `POST /login` `{pin}` | Sets the session cookie, returns `csrf_token`. With `"token": true` returns a bearer `token` instead. |
| `POST /logout` | Ends the session. |
| `GET /session` | `{authenticated, csrf_token?}` |
| `GET /capabilities` | Modes, stage 2/fan/cool availability, setpoint limits, time zone. |
| `GET /status` | Temperature, humidity, mode, target, activity, relays, pending change, fault, staleness. |
| `POST /set` `{mode, target?, start_at?}` | Apply now, or store as the pending change if `start_at` (ISO 8601) is given. |
| `DELETE /pending` | Cancel the pending change. |

State-changing calls from a browser session need the `X-CSRF-Token` header; bearer
clients don't. Status codes: 401 not signed in, 403 CSRF/origin, 413 and 415 bad
body, 422 invalid value, 429 throttled (with `Retry-After`), 503 controller busy.

## CLI

`python -m thermostat [-c config.toml] [-v] <command>`:
`proc`, `get [--json]`, `set --mode M [--temp T] [--start ISO]`, `cancel-pending`,
`init`, `serve`, `set-pin`, `check-config`, `test-sensor`, `test-relays`; and for the
emulator only: `emu-temp`, `emu-pins`, `dev-loop`.

## Security model

* Exposed directly to the internet on a non-standard port, over TLS 1.2+, with
  HSTS, a strict Content-Security-Policy and `__Host-` cookies (`HttpOnly`,
  `Secure`, `SameSite=Strict`).
* Session tokens are random and stored only as hashes. Login throttling is per IP
  with backoff, plus a global limit. Setpoints are range-checked on the server.
* No secrets in git: the PIN hash, sessions, certificates and `config.toml` live
  outside version control (`data/`, `certs/`).
* Login throttling uses the connecting IP. If you ever put a reverse proxy in front,
  revisit that.
* The furnace's own limit switches remain the final safety. Do not rely on this
  software alone for life-safety functions.

## Development (no Raspberry Pi needed)

The emulator runs the whole application on a laptop: fake relays, a fake sensor you
control with `emu-temp`, and `dev-loop` in place of cron. The full walkthrough is in
[docs/EMULATOR.md](docs/EMULATOR.md). The short version:

```bash
python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
cp config.emulator.example.toml config.toml
python -m thermostat set-pin
python -m thermostat serve                       # terminal 1: http://localhost:8080
python -m thermostat dev-loop --interval 5       # terminal 2: stand-in for cron
python -m thermostat emu-temp 66                 # terminal 3: set the room temperature
python -m unittest discover -s tests -t .        # tests (Pillow and Node optional)
```

Regenerate artwork: `python3 tools/make_icons.py [--design 1|2|3]`,
`python3 tools/make_wiring_diagram.py`, `python3 tools/make_pinmap.py`,
`python3 tools/preview_icons.py` (icon options sheet).

## Layout

```
thermostat/   config, state, control, hardware, engine, auth, webapp, api, static, server, cli
static/       the web app (index.html, style.css, app.js, manifest, icons)
deploy/       systemd unit, crontab, certbot deploy hooks (local and remote), `th` helper
docs/         INSTALL.md, EMULATOR.md, REFERENCE.md, wiring diagram, GPIO pin map, icon options
tests/        unit, API, server (real TLS), UI (runs app.js in Node)
tools/        icon and diagram generators
```

Licensed under the GNU GPL v3 (see `LICENSE`).
