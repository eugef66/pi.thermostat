# Running the thermostat on a laptop (emulator)

You can run the whole application, including the web app, the REST API, the control
logic and the log, on a laptop with **no Raspberry Pi, relays or sensor**. The
emulator replaces the two pieces of hardware:

| Real hardware | Emulator |
|---|---|
| Relay pins (GPIO) | `data/emulated_pins.json`: one entry per pin, 0 = relay energized (active-low, like the real board) |
| DHT22 sensor | `data/emulated_sensor.json`: the temperature you set with `emu-temp` |
| cron every minute | `dev-loop`, which runs the same control pass every few seconds |

Everything else is the real code: control rules, lockouts, state file, login, API,
web app, watchdog, certificate reload. It is the quickest way to try changes and to
see the thermostat's behavior before you connect anything to a furnace.

**Needs:** Linux, macOS, or Windows with WSL2 (the state file lock uses `fcntl`, so
native Windows is not supported), Python 3.9 or newer. Node.js is optional (only for
the browser-code tests).

## 1. Set up (once)

```bash
cd pi.thermostat
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp config.emulator.example.toml config.toml
python -m thermostat check-config     # prints capabilities; "PIN: NOT SET" is expected
python -m thermostat set-pin          # choose any PIN, 6+ characters
```

`config.emulator.example.toml` already sets `emulate = true`, plain HTTP on
`127.0.0.1:8080`, and `cookie_secure = false` (required without HTTPS). **Never use
those settings on a real installation.**

## 2. Start it (three terminals, all in the project folder with the venv active)

**Terminal 1: the web server**
```bash
python -m thermostat serve
```

**Terminal 2: the control loop** (your stand-in for cron)
```bash
python -m thermostat dev-loop --interval 5
```
It prints one line per pass:
```
09:00:51    66.0F  HEAT 70F  relays: heat1, heat2
```

**Terminal 3: you, playing the weather**
```bash
python -m thermostat emu-temp 66      # the room is 66 F
```

Open **http://localhost:8080**, sign in with the PIN, and use the app normally. It
reads the same state the loop writes.

## 3. Things to try

Run the commands in Terminal 3 and watch Terminals 1-2 and the browser.

**A heat call with the second stage**
```bash
python -m thermostat emu-temp 66
python -m thermostat set --mode heat --temp 70      # or press Heat, +, Apply in the app
python -m thermostat emu-pins
```
```
W1 heat stage 1    GPIO 2  level 0  ON
W2 heat stage 2    GPIO 5  level 0  ON
Y cooling          GPIO 3  level 1  off
G fan              GPIO 6  level 1  off
```
66 °F is 4 °F below the target, which is more than 3, so both stages call.

**The second stage drops out first**
```bash
python -m thermostat emu-temp 68.5      # within 2 F of target
```
`relays: heat1` only: W2 turned off but W1 keeps running.

**Minimum run time**
```bash
python -m thermostat emu-temp 70.5      # warmer than the target
```
The furnace has not run its 2 minutes yet, so it keeps running; the log says
`deferred: heat1 minimum run time`. After 2 minutes it turns off.

**Sensor failure (fail-safe)**
```bash
python -m thermostat emu-temp --fail
```
After 5 failed passes, all relays go off, the app shows a red banner, and the log
records `FAULT sensor: all relays off`. Restore the sensor with
`python -m thermostat emu-temp 66`; the fault clears at once, and heat restarts when
its minimum off time (2 minutes) has passed.

**Cooling and compressor protection**
```bash
python -m thermostat emu-temp 76
python -m thermostat set --mode cool --temp 72
```
Y and G (fan) come on. Turn it off and straight back on: the compressor will not
restart for 5 minutes (`deferred: cool minimum off time`).

**A scheduled change**
In the app tick **Start later**, pick a time two minutes from now, Apply. The
"Scheduled" card appears; at that time the loop applies it. Or:
```bash
python -m thermostat set --mode heat --temp 72 --start 2030-01-01T06:30
python -m thermostat cancel-pending
```

**The dead-man switch**
Make a relay call, then stop the control loop (Ctrl-C in Terminal 2). After
`deadman_s` (300 s by default) the server turns everything off and the app shows
"Control loop stopped". Set `deadman_s = 30` in `config.toml` to see it faster.
Start `dev-loop` again and the banner clears.

**Other installs**
Delete `cool_pin` from `config.toml` (heat-only house) or `fan_pin` (no fan wire) and
restart the server: the app's mode buttons change to match. Delete `heat2_pin` for
single-stage heat.

## 4. Seeing what is going on

```bash
python -m thermostat get                  # temperature, mode, relays, fault, last run
python -m thermostat get --json           # the complete saved state
python -m thermostat emu-pins             # relay and pin levels
tail -f data/thermostat.log               # every relay change, login, deferral and fault
watch -n 1 python -m thermostat emu-pins  # live view (Linux; on macOS: brew install watch)
```

## 5. Speeding things up

The real timers are minutes long, on purpose. For experiments, uncomment the short
timers at the top of `config.toml`'s `[control]` section (10-20 seconds for the
minimum run/off times and the heat/cool changeover) and restart the server. Put the
real values back before judging how it will behave in the house.

## 6. HTTPS on the laptop (optional)

This exercises the TLS code and the live certificate reload with a throwaway
certificate:

```bash
mkdir -p certs
openssl req -x509 -newkey rsa:2048 -nodes -days 30 \
  -keyout certs/privkey.pem -out certs/fullchain.pem -subj "/CN=localhost" \
  -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"
```

In `config.toml` set `[auth] cookie_secure = true` and, under `[server]`,
`port = 8443`, `tls = true`, `cert_file = "certs/fullchain.pem"`,
`key_file = "certs/privkey.pem"`, and `cert_check_s = 5`. Restart `serve` and open
**https://localhost:8443** (your browser will warn about the self-signed certificate;
that is expected here).

To watch a renewal arrive, run the `openssl req ...` command again while the server
is running. After a few seconds `data/thermostat.log` shows `TLS certificate reloaded`
and new connections get the new certificate, with no restart.

## 7. Trying it from your phone

In `config.toml` set `host = "0.0.0.0"`, restart `serve`, and open
`http://<your-laptop's-LAN-address>:8080` on a phone on the same Wi-Fi. This is for
development only: it is plain HTTP on your local network. (Some phone features, such
as Android's "Install app" prompt, need HTTPS; "Add to Home Screen" on iPhone works.)
Set `host` back to `127.0.0.1` afterwards.

## 8. Tests

```bash
pip install pillow          # only for the icon tests
python -m unittest discover -s tests -t .
```

The tests use the emulator too: they start real servers (including a real TLS
handshake and a certificate swap), run the browser code in Node if it is installed,
and drive the control logic through hundreds of simulated minutes. They take about 30
seconds.

## 9. Starting over

Stop the server and loop, then:
```bash
rm -f data/state.json data/emulated_pins.json data/emulated_sensor.json
```
(`data/auth.json` holds the PIN hash and `data/sessions.json` the logins; delete
`sessions.json` to log everyone out.)

## What the emulator does *not* tell you

* How a real DHT22 behaves. It fails and glitches far more than the perfect emulated
  one. Use `emu-temp --fail` for the worst case and `th test-sensor` on the Pi.
* Relay board wiring: logic levels, the yellow jumper, a swapped channel. Use
  `th test-relays` on the Pi.
* GPIO permissions (`gpio` group) and the Pi's boot behavior.
* The production web server. The laptop uses Python's built-in server
  (`engine = "wsgiref"`); the Pi uses Cheroot.
* Cron timing: `dev-loop` runs every few seconds, cron once a minute, so real timers
  are checked at minute resolution.
