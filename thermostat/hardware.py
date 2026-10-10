"""Hardware layer: relays and the DHT22/AM2302 sensor.

`open_hardware(cfg)` returns the real GPIO implementation, or an emulator
(config `hardware.emulate = true`) whose pin levels live in a JSON file so
separate processes (cron and server) see each other, like real pins would.

Safety notes:
 * Pins are never released with GPIO.cleanup(); an output keeps its last
   level when the process exits, so a finished cron run leaves relays as set.
 * A pin that is not yet an output is first read with the board's pull,
   then made an output already at the OFF level: no glitch to ON.
"""
from __future__ import annotations

import json
import os
import time

from .config import Config
from .state import RELAY_NAMES

PIN_ATTR = {"heat1": "heat1_pin", "heat2": "heat2_pin", "cool": "cool_pin", "fan": "fan_pin"}


def c_to_f(c):
    return None if c is None else c * 9.0 / 5.0 + 32.0


# ------------------------------------------------------------------ pins

class EmulatedPins:
    def __init__(self, path: str):
        self.path = path

    def _load(self) -> dict:
        try:
            with open(self.path) as f:
                return json.load(f)
        except (FileNotFoundError, ValueError):
            return {}

    def prepare(self, pins, off_level):
        d = self._load()
        for p in pins:
            d.setdefault(str(p), off_level)   # unconfigured pins boot at the OFF level
        self._save(d)

    def level(self, pin) -> int:
        return self._load().get(str(pin), 1)

    def write(self, pin, level):
        d = self._load()
        d[str(pin)] = level
        self._save(d)

    def _save(self, d):
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(d, f)
        os.replace(tmp, self.path)


class GpioPins:
    def __init__(self, active_low: bool):
        import RPi.GPIO as GPIO   # imported lazily so laptops/tests don't need it
        self.GPIO = GPIO
        self.active_low = active_low
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)

    def prepare(self, pins, off_level):
        G = self.GPIO
        pull = G.PUD_UP if off_level else G.PUD_DOWN
        for p in pins:
            if G.gpio_function(p) == G.OUT:
                G.setup(p, G.OUT)                    # keep the current level
            else:
                G.setup(p, G.IN, pull_up_down=pull)  # let the pull settle
                G.setup(p, G.OUT, initial=off_level)

    def level(self, pin) -> int:
        return int(self.GPIO.input(pin))

    def write(self, pin, level):
        self.GPIO.output(pin, level)


# -------------------------------------------------------------- sensors

class EmulatedSensor:
    """Reads data/emulated_sensor.json {"temp": 70, "humidity": 40} (deg F).
    {"fail": true} makes every read fail, like a disconnected sensor."""

    def __init__(self, path: str):
        self.path = path
        self.last_error = None

    def read(self):
        try:
            with open(self.path) as f:
                d = json.load(f)
            if d.get("fail"):
                self.last_error = "emulated failure"
                return [None] * 3, [None] * 3
            t, h = float(d["temp"]), float(d.get("humidity", 40))
        except (FileNotFoundError, ValueError, KeyError):
            t, h = 70.0, 40.0
        return [t, t, t], [h, h, h]


class DhtSensor:
    """DHT22 / AM2302 via adafruit-circuitpython-dht. Takes several samples
    (the chip needs >= 2 s between reads); failed reads come back as None."""

    def __init__(self, pin: int, samples: int = 3, spacing: float = 2.5):
        self.pin, self.samples, self.spacing = pin, samples, spacing
        self.last_error = None

    def read(self):
        import adafruit_dht
        import board
        dht = adafruit_dht.DHT22(getattr(board, f"D{self.pin}"))
        temps, hums = [], []
        try:
            for i in range(self.samples):
                if i:
                    time.sleep(self.spacing)
                try:
                    t, h = dht.temperature, dht.humidity
                    if t is None or h is None:
                        raise RuntimeError("empty reading")
                    temps.append(c_to_f(t)); hums.append(h)
                except Exception as e:      # RuntimeError is routine for DHT22
                    self.last_error = f"{type(e).__name__}: {e}"
                    temps.append(None); hums.append(None)
        finally:
            try:
                dht.exit()
            except Exception:
                pass
        return temps, hums


# --------------------------------------------------------------- facade

class Hardware:
    def __init__(self, cfg: Config, pins, sensor):
        self.cfg, self.pins, self.sensor = cfg, pins, sensor
        hw = cfg.hardware
        self.pin_of = {n: getattr(hw, a) for n, a in PIN_ATTR.items()
                       if getattr(hw, a) is not None}
        self.on_level = 0 if hw.relay_active_low else 1
        self.off_level = 1 - self.on_level
        pins.prepare(list(self.pin_of.values()), self.off_level)

    def read_sensor(self):
        return self.sensor.read()

    def read_relays(self) -> dict:
        return {n: (self.pins.level(self.pin_of[n]) == self.on_level)
                if n in self.pin_of else False for n in RELAY_NAMES}

    def set_relays(self, want: dict) -> None:
        """Offs first, then ons, so two calls never overlap by accident."""
        for n in RELAY_NAMES:
            if n in self.pin_of and not want.get(n):
                self.pins.write(self.pin_of[n], self.off_level)
        for n in RELAY_NAMES:
            if want.get(n):
                if n not in self.pin_of:
                    raise ValueError(f"relay {n} requested but not configured")
                self.pins.write(self.pin_of[n], self.on_level)

    def all_off(self) -> None:
        for p in self.pin_of.values():
            self.pins.write(p, self.off_level)


def open_hardware(cfg: Config) -> Hardware:
    hw = cfg.hardware
    if hw.emulate:
        d = os.path.dirname(cfg.paths.state_file)
        return Hardware(cfg, EmulatedPins(os.path.join(d, "emulated_pins.json")),
                        EmulatedSensor(os.path.join(d, "emulated_sensor.json")))
    return Hardware(cfg, GpioPins(hw.relay_active_low), DhtSensor(hw.sensor_pin))
