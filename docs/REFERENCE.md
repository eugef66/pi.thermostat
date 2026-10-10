# Reference: command line and REST API

Everything below was run against a real instance (the emulator), so the example output
is what you will see. Dates and times in examples are illustrative.

**Contents**
1. [Conventions](#1-conventions)
2. [Command line](#2-command-line)
3. [REST API](#3-rest-api)
4. [Behavior you need to know](#4-behavior-you-need-to-know)
5. [Log messages](#5-log-messages)
6. [Saved state](#6-saved-state-get---json)

---

## 1. Conventions

* **Units:** temperatures are °F. Durations are seconds.
* **Times in the API** are ISO 8601 with a UTC offset (`2026-10-07T19:28:09-04:00`),
  shown in the time zone from `config.toml`. Times in the saved state file are Unix
  seconds.
* **Modes:** `OFF`, `HEAT`, `COOL`, `AUTO`, `FAN`. Which exist depends on your wiring:
  no `cool_pin` removes `COOL` and `AUTO`, no `fan_pin` removes `FAN`. Mode names are
  accepted in any letter case; they are always returned in capitals.
* **On a Pi** the examples use the `th` helper (`deploy/th`), which means
  `sudo -u thermostat .venv/bin/python -m thermostat -c /opt/pi.thermostat/config.toml`.
  Elsewhere, write `python -m thermostat` in its place.

### What each mode does

With target **T**, deadband **1**, auto gap **4** (all configurable):

| Mode | Heat (W1) | Cool (Y) | Fan (G) |
|---|---|---|---|
| `OFF` | never | never | never |
| `HEAT` | on at T−1 or colder, off at T | never | only if `fan_with_heat` |
| `COOL` | never | on at T+1 or warmer, off at T | with cooling (`fan_with_cool`) |
| `AUTO` | on at T−2 or colder, off at T−1 | on at T+2 or warmer, off at T+1 | with cooling |
| `FAN` | never | never | always on |

Heat stage 2 (W2) joins W1 when the room is more than 3 °F below T and drops out again
within 2 °F of T; W1 stays on whenever W2 is on. Minimum run and off times and the
heat/cool changeover delay apply to everything except `OFF`; see
[section 4](#4-behavior-you-need-to-know).

---

## 2. Command line

```
python -m thermostat [-c CONFIG] [-v] <command> [options]
```

| Global option | Meaning |
|---|---|
| `-c`, `--config PATH` | Config file. Default: `$THERMOSTAT_CONFIG`, else `./config.toml`. |
| `-v`, `--verbose` | Also print log lines to the terminal. |

Global options go **before** the command: `th -v proc`, not `th proc -v`.

### Exit codes

| Code | Meaning |
|---|---|
| 0 | Success. |
| 1 | The command failed (details in the log), `test-relays` refused to run, or `test-sensor` found the sensor mostly failing. |
| 2 | Bad request or usage: invalid value, wrong arguments, weak PIN, or an emulator command on a real-hardware config. |
| 3 | Config file error. |
| 4 | The state is locked by another process for more than 10 seconds; this run was skipped. |
| 5 | `serve` could not start because a TLS file is missing. |

### Commands at a glance

| Command | Purpose | Needs hardware |
|---|---|---|
| [`proc`](#proc) | One control pass (cron runs this every minute) | yes |
| [`get`](#get) | Show status | no |
| [`set`](#set) | Change mode, target, or schedule a change | yes |
| [`cancel-pending`](#cancel-pending) | Drop the scheduled change | yes |
| [`init`](#init) | Turn every relay off (run at boot) | yes |
| [`serve`](#serve) | Run the HTTPS API and web app | yes |
| [`set-pin`](#set-pin) | Set the login PIN or passphrase | no |
| [`check-config`](#check-config) | Validate the config and show what is installed | no |
| [`test-sensor`](#test-sensor) | Read the sensor repeatedly and report | yes |
| [`test-relays`](#test-relays) | Click each relay in turn | yes |
| [`emu-temp`](#emu-temp), [`emu-pins`](#emu-pins), [`dev-loop`](#dev-loop) | Emulator only | emulator |

### proc

```
th proc
```

One control pass; this is what cron runs every minute. It reads the sensor (three
samples about 2.5 s apart, so roughly 5 s on a real DHT22) **before** taking the lock,
then, under the lock: checks the relays' real state, applies a scheduled change if its
time has come, filters the reading, decides, and drives the relays. It prints nothing on
success; see the log (`data/thermostat.log`).

If anything unexpected goes wrong during the pass, every relay is driven **off**, the
error is logged with a traceback, and the exit code is 1. If another process holds the
lock for more than 10 s the run is skipped (exit 4); the next minute's run catches up.

### get

```
th get [--json]
```

```
$ th get
Temperature : 66.0 F, humidity 45.0% (at 2026-10-07T19:27:50-04:00)
Mode        : HEAT  target 70 F
Relays on   : heat1, heat2
Fault       : none
Last run    : 2026-10-07T19:27:50-04:00
```

With a scheduled change there is an extra line:
`Pending     : COOL 74 F at 2026-10-07T22:28-04:00`.

"Last run" is the last `proc` pass. If it is more than about 3 minutes old, cron is not
running. `--json` prints the complete saved state (see [section 6](#6-saved-state-get---json)).

### set

```
th set --mode MODE [--temp F] [--start WHEN]
```

| Option | Meaning |
|---|---|
| `--mode` | Required. `off`, `heat`, `cool`, `auto` or `fan`, as installed. |
| `--temp` | Target in °F, within the configured range (default 50 to 85). Optional: leave it out to keep the current target. It is ignored (but still range-checked) for `off` and `fan`. |
| `--start` | Apply the change later instead of now. ISO 8601: `2026-10-08T06:30` (interpreted in the time zone from `config.toml`), or with an offset or `Z`: `2026-10-08T10:30:00Z`. Must be in the future and at most 30 days away. |

```
$ th set --mode heat --temp 70
Temperature : 66.0 F, humidity 45.0% (at 2026-10-07T19:27:50-04:00)
Mode        : HEAT  target 70 F
Relays on   : heat1, heat2
Fault       : none
Last run    : 2026-10-07T19:27:50-04:00

$ th set --mode cool --temp 74 --start 2026-10-08T06:30
...
Pending     : COOL 74 F at 2026-10-08T06:30-04:00
```

Errors print one line to stderr and exit 2:
```
$ th set --mode heat --temp 99
error: target must be between 50 and 85
$ th set --mode banana
error: mode must be one of OFF, HEAT, COOL, AUTO, FAN
$ th set --mode heat --start 2031-01-01T00:00
error: start_at is more than 30 days away
```

Notes:

* `set` applies at once but **does not read the sensor**: it reuses the last reading if
  it is under 3 minutes old. If there is none, the relays stay as they are until the
  next `proc` (under a minute). `OFF` and `FAN` always apply immediately.
* A `set` is a request, not a promise: the relays still obey the minimum off times and
  the changeover delay (see [section 4](#4-behavior-you-need-to-know)).
* There is **one** scheduled change. A new `--start` replaces it. A later immediate
  `set` does *not* cancel it; use `cancel-pending`.

### cancel-pending

```
th cancel-pending
```
Removes the scheduled change, if any. Nothing is printed. It is not an error if there
is none.

### init

```
th init
```
Drives every relay off and records that they are off. Run at boot (the supplied
crontab does). Because it records "just turned off", the minimum off times (2 minutes
for heat, 5 for cooling) start counting from the moment it runs. That is deliberate
compressor protection after a power cut.

### serve

```
th serve
```
Runs the web server (API and web app) on the host and port from `[server]`, plus two
background checks: the dead-man watchdog and the certificate watcher. It runs until you
press Ctrl-C or the process receives SIGTERM, then exits 0.

* Exit 5 if `tls = true` and the certificate or key file is missing (the path is logged).
* Warns in the log if no PIN is set, or if the private key file is readable by other users.
* Stopping it does **not** change any relay; cron keeps controlling them.

### set-pin

```
th set-pin
```
Prompts twice, without echo:
```
New PIN or passphrase:
Repeat:
PIN saved. Existing sessions stay valid until they expire or are logged out.
```
Rules: at least `auth.pin_min_length` characters (default 6), at most 128, and not one
repeated character. Violations print `error: ...` and exit 2. The PIN is stored as a
salted scrypt hash in `data/auth.json` (mode 600). The PIN itself is never logged.
To log everyone out, delete `data/sessions.json` and restart `serve`.

### check-config

```
th check-config
```
Validates `config.toml` (a bad file prints `config error: ...` and exits 3) and shows
what the app will offer:
```
{
  "modes": ["OFF", "HEAT", "COOL", "AUTO", "FAN"],
  "heat": true, "cool": true, "fan": true, "heat_stage_2": true,
  "unit": "F", "setpoint_min": 50.0, "setpoint_max": 85.0,
  "timezone": "America/New_York"
}

server: https://0.0.0.0:8443 (cheroot)
certificate: /opt/pi.thermostat/certs/fullchain.pem (found)
private key: /opt/pi.thermostat/certs/privkey.pem (found)
PIN: set
```
(The JSON is printed indented; shortened here.) `MISSING` next to a TLS file or
`PIN: NOT SET` means `serve` will not be usable yet.

### test-sensor

```
th test-sensor
```
Ten rounds of three reads each (about a minute on a real sensor). A few `fail` entries
are normal for a DHT22.
```
read  1: 70.0F/45%, 70.0F/45%, 70.0F/45%
...
read 10: 70.0F/45%, 70.0F/45%, 70.0F/45%

30/30 reads succeeded
Sensor looks healthy.
```
If fewer than 70% succeed it prints wiring advice and exits 1:
```
0/30 reads succeeded
Mostly failing: check wiring (+ 3.3V, out GPIO 4, - GND) and try a 4.7k pull-up from data to 3.3V. Last error: emulated failure
```

### test-relays

```
th test-relays
```
Clicks each installed relay for 3 seconds, one at a time, after you press Enter. Type
`q` and Enter to stop; all relays are switched off however it ends.
```
Disconnect nothing; this only clicks the relays. Make sure the equipment is safe to
receive calls or the thermostat wires are disconnected from it.

Enter to energize W1 heat stage 1 (GPIO 2) for 3 s, 'q' to quit:   off
Enter to energize W2 heat stage 2 (GPIO 5) for 3 s, 'q' to quit:   off
Enter to energize Y cooling (GPIO 3) for 3 s, 'q' to quit:   off
Enter to energize G fan (GPIO 6) for 3 s, 'q' to quit:   off
```
* The **order** is W1, W2, Y, G, which on the usual wiring is relays **K1, K3, K2, K4**.
* It holds the state lock for the whole test, so cron passes during that time are
  skipped. That is harmless while everything is off.
* It refuses (exit 1) unless the mode is `OFF` and nothing is running:
  `Refusing: set mode OFF and wait for all calls to end first (set --mode OFF).`
* Disconnect the relay board from the furnace, or switch the furnace off, first.

### emu-temp

Emulator only (`hardware.emulate = true`; otherwise exit 2).
```
th emu-temp 66                 # the room is 66 F
th emu-temp 66 --humidity 52
th emu-temp --fail             # the sensor stops answering
```
```
emulated sensor: 66 F, 45% humidity
```
A jump of more than 5 °F is held back for one pass, exactly as with the real sensor
(see [section 4](#4-behavior-you-need-to-know)).

### emu-pins

Emulator only. Shows each installed relay's pin level (0 = energized):
```
W1 heat stage 1    GPIO 2  level 0  ON
W2 heat stage 2    GPIO 5  level 0  ON
Y cooling          GPIO 3  level 1  off
G fan              GPIO 6  level 1  off
```

### dev-loop

Emulator only. A stand-in for cron.
```
th dev-loop [--interval SECONDS] [--count N]       # default: every 10 s, forever
```
```
running a control pass every 5s; Ctrl-C to stop
19:27:51    66.0F  HEAT 70F  relays: heat1, heat2
19:27:56    66.0F  HEAT 70F  relays: heat1, heat2
```
`FAULT: <code>` is appended to the line while a fault is active.

---

## 3. REST API

Base path: `/api/v1`, for example `https://thermostat.example.com:8443/api/v1/status`.

### 3.1 Rules for every request

* Bodies are JSON objects and need `Content-Type: application/json` (otherwise **415**).
  The size limit is 4096 bytes (**413**); invalid JSON is **400**.
* Responses are JSON, except `204 No Content` for logout. They carry
  `Cache-Control: no-store`, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
  and, over HTTPS, `Strict-Transport-Security`.
* Errors always look like this:
  ```json
  {"error": {"code": "target_out_of_range", "message": "target must be between 50 and 85"}}
  ```
  Use `code` in programs; `message` is for people.

### 3.2 Authentication

There are two ways to sign in, both through `POST /login`:

| | Browser session (default) | Bearer token (scripts) |
|---|---|---|
| Ask for it | `{"pin": "..."}` | `{"pin": "...", "token": true}` |
| You receive | A cookie (`__Host-sid` over HTTPS, `sid` in plain-HTTP development) and a `csrf_token` | A `token` |
| Send it as | The cookie, automatically | `Authorization: Bearer <token>` |
| Changing things | Also send `X-CSRF-Token: <csrf_token>` | Nothing extra |

Both last `auth.session_hours` (default 168 = 7 days) and survive a server restart. A
token cannot be used as a cookie, nor a cookie as a token.

For browser sessions, `POST` and `DELETE` requests need the CSRF header, and if the
request carries an `Origin` header its host must match the `Host` header; otherwise
**403 `csrf_failed`**. `GET /session` returns the CSRF token again after a page reload.

**Login throttling** is per client IP: after 5 wrong PINs that IP is locked out for 30 s,
doubling with each further failure up to an hour. A correct login clears the count. If
30 wrong PINs arrive from anywhere within 10 minutes, all logins pause for 5 minutes.
While locked out, even the correct PIN returns **429** with a `Retry-After` header.

### 3.3 Endpoints

| Method and path | Auth | Purpose |
|---|---|---|
| [`POST /login`](#post-login) | none | Sign in |
| [`POST /logout`](#post-logout) | yes | Sign out |
| [`GET /session`](#get-session) | none | Am I signed in? Get the CSRF token |
| [`GET /capabilities`](#get-capabilities) | yes | What this installation supports |
| [`GET /status`](#get-status) | yes | Current state |
| [`POST /set`](#post-set) | yes | Change mode/target now or later |
| [`DELETE /pending`](#delete-pending) | yes | Cancel the scheduled change |

The web app itself is served at `/` and `/static/...` with no login; it contains no
data, only the login screen and code.

#### POST /login

Body: `pin` (string, required); `token` (boolean, optional, `true` for a bearer token).

```
$ curl -i -c jar.txt -X POST -H 'Content-Type: application/json' \
       -d '{"pin":"482916"}' https://thermostat.example.com:8443/api/v1/login
HTTP/1.1 200 OK
Set-Cookie: __Host-sid=u_ojtGIjKCks...; Path=/; Max-Age=604800; HttpOnly; Secure; SameSite=Strict

{"expires_at": "2026-10-14T19:28:09-04:00", "csrf_token": "KeGNCvlNzii27DmQZZfOgUhrIRiUF0f1"}
```
Token form:
```
$ curl -X POST -H 'Content-Type: application/json' -d '{"pin":"482916","token":true}' .../login
{"expires_at": "2026-10-14T19:28:09-04:00", "token": "Y3b0...."}
```
Errors: `401 invalid_credentials`; `422 invalid_pin` (pin is not a string);
`429 throttled`; `503 not_configured` (no PIN set yet; run `set-pin`).

#### POST /logout

Ends the session and clears the cookie. Returns `204` with no body. Browser sessions
need the CSRF header.

#### GET /session

No sign-in needed. Tells a page whether to show the login screen.
```
{"authenticated": false, "configured": true}
```
When signed in with a cookie:
```
{"authenticated": true, "configured": true, "expires_at": "2026-10-14T19:28:09-04:00",
 "csrf_token": "KeGNCvlNzii27DmQZZfOgUhrIRiUF0f1"}
```
(A bearer token session has no `csrf_token`.) `configured: false` means no PIN is set.

#### GET /capabilities

```
{
  "modes": ["OFF", "HEAT", "COOL", "AUTO", "FAN"],
  "heat": true, "cool": true, "fan": true, "heat_stage_2": true,
  "unit": "F", "setpoint_min": 50.0, "setpoint_max": 85.0,
  "timezone": "America/New_York"
}
```
Build your interface from this rather than assuming; a heat-only install returns
`"modes": ["OFF", "HEAT"]` and `"cool": false`.

#### GET /status

```
{
  "server_time": "2026-10-07T19:28:09-04:00",
  "unit": "F",
  "temperature": 66.0,
  "humidity": 45.0,
  "reading_at": "2026-10-07T19:28:09-04:00",
  "reading_age_s": 0,
  "stale": false,
  "mode": "HEAT",
  "target": 70.0,
  "activity": "heating",
  "relays": {"heat1": true, "heat2": true, "cool": false, "fan": false},
  "pending": null,
  "fault": null
}
```

| Field | Meaning |
|---|---|
| `temperature`, `humidity` | Latest accepted reading; `null` before the first one. |
| `reading_at`, `reading_age_s` | When it was taken, and how many seconds ago. |
| `stale` | `true` if there is no reading, it is over 180 s old, or the control loop has not run for over 180 s. Treat the numbers as unreliable. |
| `mode`, `target` | The active mode and target. |
| `activity` | What the equipment is doing right now: `heating` (W1 or W2 on), `cooling`, `fan`, or `idle`. |
| `relays` | Actual on/off state of each relay. |
| `pending` | The scheduled change: `{"mode": "COOL", "target": 74, "start_at": "2026-10-07T22:28-04:00"}`, or `null`. |
| `fault` | `null`, or `{"code", "message", "since"}`. Codes: `sensor` (sensor failing, everything is off) and `cron_stalled` (the control loop stopped, everything was shut off). Both clear themselves when the cause is fixed. |

Error `503 busy` if the controller could not be read within 10 s; retry.

#### POST /set

Body:

| Field | Type | Meaning |
|---|---|---|
| `mode` | string, required | One of `capabilities.modes`, any letter case. |
| `target` | number, optional | °F within `setpoint_min` to `setpoint_max`. Omit to keep the current target. Ignored for `OFF` and `FAN`. |
| `start_at` | string, optional | ISO 8601 time to apply the change instead of now (future, within 30 days). Without an offset it is read in the configured time zone; `Z` or `+hh:mm` are fine. |

Unknown fields are rejected (`unknown_field`). The reply is the new [status](#get-status).

Apply now:
```
$ curl -b jar.txt -X POST -H 'Content-Type: application/json' -H "X-CSRF-Token: $CSRF" \
       -d '{"mode":"heat","target":70}' .../set
{ "mode": "HEAT", "target": 70, "activity": "heating", ... }
```
Apply later (the active mode and target stay as they are until then):
```
$ curl ... -d '{"mode":"cool","target":74,"start_at":"2026-10-08T06:30:00-04:00"}' .../set
{ "mode": "HEAT", "target": 70,
  "pending": {"mode": "COOL", "target": 74, "start_at": "2026-10-08T06:30-04:00"}, ... }
```
Errors (all **422** except the common ones):

| `code` | Cause |
|---|---|
| `invalid_mode` | Missing, not a string, or not installed on this system. |
| `invalid_target` | Not a number. |
| `target_out_of_range` | Outside the setpoint limits. |
| `invalid_start_at` | Not a string, or not valid ISO 8601. |
| `start_at_in_past` | Not in the future. |
| `start_at_too_far` | More than 30 days ahead. |
| `unknown_field` | A field other than `mode`, `target`, `start_at`. |

**The reply shows what actually happened.** A fresh `HEAT` request may come back with
`"activity": "idle"` and all relays `false`: the mode changed, but the furnace is still
inside its minimum off time. It will start by itself when the lockout ends (see below).

#### DELETE /pending

No body. Cancels the scheduled change and returns the new status. It succeeds even if
nothing was scheduled.
```
$ curl -b jar.txt -X DELETE -H "X-CSRF-Token: $CSRF" .../pending
```

### 3.4 Error reference

| HTTP | `code` | When |
|---|---|---|
| 400 | `bad_json`, `bad_request` | Body is not valid JSON, is not an object, or has a bad `Content-Length`. |
| 401 | `unauthenticated` | No valid session. Show the login screen. |
| 401 | `invalid_credentials` | Wrong PIN. |
| 403 | `csrf_failed` | Missing or wrong `X-CSRF-Token`, or a cross-origin request. |
| 404 | `not_found` | No such path. |
| 405 | `method_not_allowed` | Wrong method; the `Allow` header lists the right one. |
| 413 | `body_too_large` | Body over 4096 bytes. |
| 415 | `unsupported_media_type` | `Content-Type` is not `application/json`. |
| 422 | see `POST /set`, `invalid_pin` | A value was rejected. |
| 429 | `throttled` | Too many wrong PINs; wait `Retry-After` seconds. |
| 500 | `internal_error` | A bug; details are in the log. |
| 503 | `busy` | The controller state was locked; retry shortly. |
| 503 | `not_configured` | No PIN has been set. |

### 3.5 Scripting examples

**Shell:** warm the house up, using a bearer token.
```bash
HOST=https://thermostat.example.com:8443/api/v1
TOKEN=$(curl -s -X POST -H 'Content-Type: application/json' \
        -d '{"pin":"482916","token":true}' $HOST/login | python3 -c 'import sys,json;print(json.load(sys.stdin)["token"])')

curl -s -X POST -H 'Content-Type: application/json' -H "Authorization: Bearer $TOKEN" \
     -d '{"mode":"heat","target":72}' $HOST/set
curl -s -H "Authorization: Bearer $TOKEN" $HOST/status
```
Keep the PIN out of scripts you share; log in once and reuse the token until it
expires (a `401` means log in again).

**Python (standard library only):**
```python
import json, urllib.request, urllib.error

HOST = "https://thermostat.example.com:8443/api/v1"

def call(method, path, body=None, token=None):
    req = urllib.request.Request(HOST + path, method=method,
                                 data=None if body is None else json.dumps(body).encode())
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.load(r) if r.status != 204 else None
    except urllib.error.HTTPError as e:
        raise RuntimeError(json.load(e)["error"]["message"]) from None

token = call("POST", "/login", {"pin": "482916", "token": True})["token"]
status = call("GET", "/status", token=token)
print(status["temperature"], status["mode"], status["activity"])
call("POST", "/set", {"mode": "heat", "target": 71}, token=token)
```

---

## 4. Behavior you need to know

**Protection timers.** The control pass obeys these even when you ask for something else
(defaults; all in `config.toml`):

| Rule | Default | Effect |
|---|---|---|
| Heat minimum on / off | 2 min / 2 min | A call is not dropped, or restarted, sooner. |
| Cool minimum on / off | 3 min / 5 min | Compressor protection. |
| Heat↔cool changeover | 5 min | Cooling will not start within 5 min of heat stopping, or the reverse. |
| After a reboot, `init`, or a fault | | All timers restart; nothing starts until its minimum off time has passed. |

`OFF` is always immediate. Timers are checked once a minute, so "2 minutes" means 2 to 3.
When a request is held back, the log says why (`deferred: heat1 minimum off time`).

**Sensor handling.** Each pass takes three samples and uses the median. Readings outside
−20 to 140 °F are discarded. A change of more than 5 °F from the last good reading is
held for one pass and accepted only if the next pass confirms it, so one wild reading
cannot swing the furnace. After 5 consecutive failed passes everything turns off and the
`sensor` fault appears; a good reading clears it.

**Staleness and the dead-man switch.** `stale` in the status goes `true` after 3 minutes
without a fresh reading or control pass. If a relay is on and the control loop has been
silent for `deadman_s` (default 5 minutes), the server turns everything off and reports
the `cron_stalled` fault until the loop runs again.

**Scheduled change.** There is one. It replaces any earlier one, survives restarts, and
is applied by the first control pass after its time. An immediate change does not cancel
it.

**Setpoint limits** apply to every route, including scheduled changes; if you tighten
the limits later, an out-of-range saved target is clamped on the next pass.

---

## 5. Log messages

`data/thermostat.log`, one line per event, rotated at 1 MB (5 files kept).
`ERROR` is used for faults, `WARNING` for things that merit a look, `INFO` otherwise.

| Message | Meaning |
|---|---|
| `relay heat1 ON at 66.0F` / `relay heat1 OFF at 70.0F` | A relay changed (`heat1` W1, `heat2` W2, `cool` Y, `fan` G). |
| `set[cli]: HEAT 70` / `set[api 10.0.0.5]: HEAT 70` | A change, and where it came from. |
| `deferred: heat1 minimum run time` | A request is being held back. Also: `heat1 minimum off time`, `cool minimum run time`, `cool minimum off time`, `cool changeover lockout`, `heat1 changeover lockout`, `cool waiting for heat1 to stop`, `heat1 waiting for cool to stop`. |
| `pending applied: COOL 74` / `pending change cancelled` | Schedule events. |
| `sensor read failed (2/5)` | A failed pass; at 5 the fail-safe trips. |
| `sensor jump to 76.0F rejected, awaiting confirmation` / `... confirmed` | The 5 °F plausibility check. |
| `FAULT sensor: all relays off` / `sensor recovered` | Fail-safe tripped / cleared. |
| `FAULT dead-man: control loop silent for more than 300s; all relays off` | Cron stopped. |
| `control loop running again` | Cron resumed after a dead-man trip. |
| `relay heat1 found OFF; timer restarted` | The pin did not match the record (reboot, power cut). |
| `INTERLOCK: heat and cool both requested; all off` | Should never appear; report it if it does. |
| `mode COOL unavailable; switched to OFF` | The config no longer has the equipment for the saved mode. |
| `target 90 outside limits; set to 85` | The saved target was out of range after a config change. |
| `state file was corrupt; reset to OFF` | The old file is kept as `state.json.corrupt-<time>`. |
| `login ok from 1.2.3.4 (cookie)` / `(token)`, `login FAILED from 1.2.3.4`, `login throttled for 1.2.3.4 (30s)`, `logout from 1.2.3.4` | Authentication events. |
| `TLS certificate reloaded` / `new certificate rejected, keeping the old one: ...` | A renewal arrived. |
| `server started on 0.0.0.0:8443 (https, cheroot)` / `server stopping` | Server lifecycle. |
| `PIN changed` | `set-pin` was run. |

---

## 6. Saved state (`get --json`)

`data/state.json`, shown by `th get --json`. All times are Unix seconds.

| Key | Meaning |
|---|---|
| `mode`, `target` | Active mode and target. |
| `pending` | `null`, or `{"mode", "target", "start_at"}` (`start_at` is ISO 8601). |
| `relays` | For each of `heat1`, `heat2`, `cool`, `fan`: `{"on": bool, "changed_at": time or null}`. The timers read this. |
| `reading` | `{"temp", "humidity", "at"}`: the last accepted reading. |
| `sensor` | `failures` (consecutive failed passes), `last_good`, `last_good_at`, and `candidate` (a jump awaiting confirmation). |
| `fault` | `null`, or `{"code", "message", "since"}`. |
| `defer_note` | The reason a request is currently being held back, or `null`. |
| `last_proc_at` | When the last control pass ran. |
| `version` | State format version (1). |

Do not edit this file while `proc` or `serve` is running; use the commands above.
