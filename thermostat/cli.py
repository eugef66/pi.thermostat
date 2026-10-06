"""Command line: `python -m thermostat <command>`.

  proc            one control pass (run from cron every minute)
  get             show current status
  set             change mode/target now or at a start time
  cancel-pending  drop the pending change
  init            drive every relay off (run at boot)
  test-sensor     read the sensor 10 times and report
  test-relays     click each relay in turn, with prompts
  set-pin         set the login PIN/passphrase
  serve           run the HTTPS API server
  check-config    validate the config and show what is installed
  emu-temp        (emulator) set the pretend room temperature, or --fail
  emu-pins        (emulator) show relay states
  dev-loop        (emulator) run `proc` every few seconds instead of cron
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime

from . import control, engine, logsetup
from .config import ConfigError, load
from .hardware import open_hardware
from .state import LockTimeout, RELAY_NAMES, StateStore

LABELS = {"heat1": "W1 heat stage 1", "heat2": "W2 heat stage 2",
          "cool": "Y cooling", "fan": "G fan"}


def _config_path(arg):
    return arg or os.environ.get("THERMOSTAT_CONFIG") or "config.toml"


def _fmt_time(ts):
    return "never" if ts is None else \
        datetime.fromtimestamp(ts).astimezone().isoformat(timespec="seconds")


def print_status(cfg, st, out=None):
    out = out or sys.stdout
    r = st.get("reading")
    print(f"Temperature : {r['temp']:.1f} F, humidity {r['humidity']}% "
          f"(at {_fmt_time(r['at'])})" if r else "Temperature : no reading yet", file=out)
    print(f"Mode        : {st['mode']}  target {st['target']:g} F", file=out)
    if st["pending"]:
        p = st["pending"]
        print(f"Pending     : {p['mode']} {p['target']:g} F at {p['start_at']}", file=out)
    on = [n for n in RELAY_NAMES if st["relays"][n]["on"]]
    print(f"Relays on   : {', '.join(on) or 'none'}", file=out)
    print(f"Fault       : {st['fault']['message'] if st['fault'] else 'none'}", file=out)
    print(f"Last run    : {_fmt_time(st['last_proc_at'])}", file=out)


def cmd_proc(cfg, store, hw, log, args):
    samples, hum = engine.read_sensor_safely(hw, log)      # slow; outside the lock
    engine.run_cycle(cfg, store, hw, log, samples=samples, humidity=hum)
    return 0


def cmd_get(cfg, store, hw, log, args):
    with store.locked() as st:
        if args.json:
            print(json.dumps(st, indent=2))
        else:
            print_status(cfg, st)
    return 0


def cmd_set(cfg, store, hw, log, args):
    def mutate(st, now):
        req = control.validate_set(cfg, st, args.mode.upper(), args.temp, args.start, now)
        return control.apply_set(st, req, "cli")
    try:
        _, st = engine.run_cycle(cfg, store, hw, log, mutate=mutate)
    except control.ValidationError as e:
        print(f"error: {e.message}", file=sys.stderr)
        return 2
    print_status(cfg, st)
    return 0


def cmd_cancel(cfg, store, hw, log, args):
    engine.run_cycle(cfg, store, hw, log,
                     mutate=lambda st, now: control.cancel_pending(st))
    return 0


def cmd_init(cfg, store, hw, log, args):
    with store.locked() as st:
        hw.all_off()
        for e in control.force_off(st, time.time(), "init"):
            log.info(e)
        log.info("init: all relays off")
    return 0


def cmd_test_sensor(cfg, store, hw, log, args):
    ok = 0
    for i in range(10):
        if i:
            time.sleep(2.5)
        temps, hums = hw.read_sensor()
        good = [t for t in temps if t is not None]
        ok += len(good)
        shown = ", ".join("fail" if t is None else f"{t:.1f}F/{h:.0f}%"
                          for t, h in zip(temps, hums))
        print(f"read {i + 1:2d}: {shown}")
    total = 10 * len(temps)
    print(f"\n{ok}/{total} reads succeeded")
    err = getattr(hw.sensor, "last_error", None)
    if ok < total * 0.7:
        print("Mostly failing: check wiring (+ 3.3V, out GPIO "
              f"{cfg.hardware.sensor_pin}, - GND) and try a 4.7k pull-up "
              "from data to 3.3V." + (f" Last error: {err}" if err else ""))
        return 1
    print("Sensor looks healthy.")
    return 0


def cmd_test_relays(cfg, store, hw, log, args):
    with store.locked() as st:     # hold the lock: cron/server can't touch relays meanwhile
        if st["mode"] != "OFF" or any(st["relays"][n]["on"] for n in RELAY_NAMES) \
                or any(hw.read_relays().values()):
            print("Refusing: set mode OFF and wait for all calls to end first "
                  "(`set --mode OFF`).", file=sys.stderr)
            return 1
        print("Disconnect nothing; this only clicks the relays. Make sure the "
              "equipment is safe to receive calls or the thermostat wires are "
              "disconnected from it.\n")
        try:
            for n in RELAY_NAMES:
                if n not in hw.pin_of:
                    continue
                pin = hw.pin_of[n]
                if input(f"Enter to energize {LABELS[n]} (GPIO {pin}) for 3 s, 'q' to quit: "
                         ).strip().lower() == "q":
                    break
                hw.pins.write(pin, hw.on_level)
                time.sleep(3)
                hw.pins.write(pin, hw.off_level)
                print("  off")
        finally:
            hw.all_off()
    return 0


def cmd_set_pin(cfg, store, hw, log, args):
    import getpass
    from .auth import Auth, AuthError
    pin = getpass.getpass("New PIN or passphrase: ")
    if pin != getpass.getpass("Repeat: "):
        print("error: entries do not match", file=sys.stderr)
        return 2
    try:
        Auth(cfg, log).set_pin(pin)
    except AuthError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    log.info("PIN changed")
    print("PIN saved. Existing sessions stay valid until they expire or are logged out.")
    return 0


def cmd_serve(cfg, store, hw, log, args):
    from .server import serve
    return serve(cfg, log)


def cmd_check_config(cfg, store, hw, log, args):
    print(json.dumps(cfg.capabilities(), indent=2))
    sv = cfg.server
    print(f"\nserver: {'https' if sv.tls else 'http'}://{sv.host}:{sv.port} ({sv.engine})")
    for label, path in (("certificate", sv.cert_file), ("private key", sv.key_file)):
        if sv.tls:
            print(f"{label}: {path} ({'found' if os.path.isfile(path) else 'MISSING'})")
    from .auth import Auth
    print("PIN:", "set" if Auth(cfg, log).configured else "NOT SET (run set-pin)")
    return 0


def _require_emulator(cfg):
    if not cfg.hardware.emulate:
        print("error: this command only works with hardware.emulate = true", file=sys.stderr)
        return False
    return True


def cmd_emu_temp(cfg, store, hw, log, args):
    """Set the pretend room temperature (or make the sensor fail)."""
    if not _require_emulator(cfg):
        return 2
    path = os.path.join(os.path.dirname(cfg.paths.state_file), "emulated_sensor.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if args.fail:
        data = {"fail": True}
    elif args.temp is None:
        print("error: give a temperature, or --fail", file=sys.stderr)
        return 2
    else:
        data = {"temp": args.temp, "humidity": args.humidity}
    with open(path, "w") as f:
        json.dump(data, f)
    print("emulated sensor:", "FAILING" if args.fail else f"{args.temp:g} F, {args.humidity:g}% humidity")
    return 0


def cmd_emu_pins(cfg, store, hw, log, args):
    """Show what the relays are doing right now."""
    if not _require_emulator(cfg):
        return 2
    on = hw.read_relays()
    for n in RELAY_NAMES:
        if n in hw.pin_of:
            pin = hw.pin_of[n]
            print(f"{LABELS[n]:<18} GPIO {pin:<2} level {hw.pins.level(pin)}  "
                  f"{'ON ' if on[n] else 'off'}")
    return 0


def cmd_dev_loop(cfg, store, hw, log, args):
    """Stand-in for cron on a laptop: one control pass every few seconds."""
    if not _require_emulator(cfg):
        return 2
    print(f"running a control pass every {args.interval:g}s; Ctrl-C to stop")
    n = 0
    try:
        while True:
            samples, hum = engine.read_sensor_safely(hw, log)
            _, st = engine.run_cycle(cfg, store, hw, log, samples=samples, humidity=hum)
            r = st.get("reading")
            temp_txt = "%.1fF" % r["temp"] if r else "--"
            on = [x for x in RELAY_NAMES if st["relays"][x]["on"]] or ["none"]
            fault = "  FAULT: " + st["fault"]["code"] if st["fault"] else ""
            print("%s  %7s  %-4s %gF  relays: %s%s" % (
                datetime.now().strftime("%H:%M:%S"), temp_txt, st["mode"], st["target"],
                ", ".join(on), fault), flush=True)
            n += 1
            if args.count and n >= args.count:
                return 0
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print()
        return 0


NEEDS_HARDWARE = {"proc", "set", "cancel-pending", "init", "test-sensor", "test-relays", "serve", "emu-pins", "dev-loop"}

EMULATOR_ONLY = {"emu-pins", "dev-loop"}

COMMANDS = {"proc": cmd_proc, "get": cmd_get, "set": cmd_set,
            "cancel-pending": cmd_cancel, "init": cmd_init,
            "test-sensor": cmd_test_sensor, "set-pin": cmd_set_pin,
            "serve": cmd_serve, "emu-temp": cmd_emu_temp,
            "emu-pins": cmd_emu_pins, "dev-loop": cmd_dev_loop, "check-config": cmd_check_config, "test-relays": cmd_test_relays}


def build_parser():
    p = argparse.ArgumentParser(prog="thermostat", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("-c", "--config", help="config.toml (or $THERMOSTAT_CONFIG)")
    p.add_argument("-v", "--verbose", action="store_true", help="also log to stderr")
    sub = p.add_subparsers(dest="command", required=True)
    for name in COMMANDS:
        sp = sub.add_parser(name)
        if name == "get":
            sp.add_argument("--json", action="store_true")
        if name == "emu-temp":
            sp.add_argument("temp", nargs="?", type=float, help="room temperature in F")
            sp.add_argument("--humidity", type=float, default=45.0)
            sp.add_argument("--fail", action="store_true", help="make the sensor fail")
        if name == "dev-loop":
            sp.add_argument("--interval", type=float, default=10.0, help="seconds between passes")
            sp.add_argument("--count", type=int, default=0, help="stop after N passes (0 = forever)")
        if name == "set":
            sp.add_argument("--mode", required=True)
            sp.add_argument("--temp", type=float)
            sp.add_argument("--start", help="ISO 8601; naive times use the configured zone")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        cfg = load(_config_path(args.config))
    except ConfigError as e:
        print(f"config error: {e}", file=sys.stderr)
        return 3
    log = logsetup.setup(cfg.paths.log_file, verbose=args.verbose)
    store = StateStore(cfg.paths.state_file, cfg.paths.lock_file, cfg.control.default_target)
    hw = None
    if args.command in NEEDS_HARDWARE and (cfg.hardware.emulate or args.command not in EMULATOR_ONLY):
        hw = open_hardware(cfg)      # emulator-only commands never touch real pins
    try:
        return COMMANDS[args.command](cfg, store, hw, log, args)
    except BrokenPipeError:      # e.g. `th get | head`: the work is done, ignore
        return 0
    except LockTimeout:
        log.error("state is locked by another process; skipped this run")
        return 4
    except Exception:
        log.exception("%s failed", args.command)
        return 1
