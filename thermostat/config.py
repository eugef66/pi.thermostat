"""Configuration loading and validation (config.toml).

Pins left out of the file mean "not installed": no cool_pin = heat-only
install, no fan_pin = no Fan mode, no heat2_pin = single-stage heat.
Temperatures are degrees Fahrenheit, durations are seconds.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, fields
from typing import Optional

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    import tomli as tomllib  # type: ignore


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Hardware:
    emulate: bool = False          # use laptop emulators instead of real GPIO/DHT
    relay_active_low: bool = True  # LOW input energizes the relay
    sensor_pin: int = 4            # DHT22 / AM2302 data (BCM numbering)
    heat1_pin: int = 2             # W1
    heat2_pin: Optional[int] = None  # W2 (optional)
    cool_pin: Optional[int] = None   # Y  (optional; absent = heat-only)
    fan_pin: Optional[int] = None    # G  (optional; absent = no Fan mode)


@dataclass(frozen=True)
class Control:
    setpoint_min: float = 50.0
    setpoint_max: float = 85.0
    default_target: float = 70.0
    deadband: float = 1.0
    auto_gap: float = 4.0            # total gap between heat-on and cool-on points
    stage2_on_deficit: float = 3.0   # W2 on when this far below target
    stage2_off_deficit: float = 2.0  # W2 off when back within this
    heat_min_on_s: int = 120
    heat_min_off_s: int = 120
    cool_min_on_s: int = 180
    cool_min_off_s: int = 300
    changeover_s: int = 300          # gap between heat and cool calls
    fan_with_cool: bool = True       # raise G whenever Y is on (needs fan_pin)
    fan_with_heat: bool = False      # most furnaces run their own blower
    sensor_fail_limit: int = 5       # consecutive failed runs before fail-safe off
    sensor_min: float = -20.0
    sensor_max: float = 140.0
    sensor_max_jump: float = 5.0     # unconfirmed jumps larger than this are rejected
    sensor_jump_expiry_s: int = 1800
    calibration: float = 0.0
    deadman_s: int = 300             # server forces relays off if cron is silent
    pending_max_days: int = 30
    timezone: str = "UTC"            # for naive start times and display


@dataclass(frozen=True)
class Paths:
    state_file: str = "data/state.json"
    lock_file: str = "data/state.lock"
    log_file: str = "data/thermostat.log"
    auth_file: str = "data/auth.json"          # PIN hash (keep out of git)
    sessions_file: str = "data/sessions.json"  # hashed session tokens


@dataclass(frozen=True)
class Auth:
    pin_min_length: int = 6
    session_hours: int = 168
    cookie_secure: bool = True       # set false only for plain-HTTP development
    max_body_bytes: int = 4096
    ip_free_failures: int = 5        # failures before a per-IP lockout starts
    ip_lockout_base_s: int = 30      # doubles with every further failure
    ip_lockout_max_s: int = 3600
    global_failures: int = 30        # failures from anyone within the window...
    global_window_s: int = 600
    global_lockout_s: int = 300      # ...pause all logins for this long

@dataclass(frozen=True)
class Server:
    host: str = "0.0.0.0"
    port: int = 8443
    tls: bool = True
    cert_file: str = "certs/fullchain.pem"
    key_file: str = "certs/privkey.pem"
    static_dir: str = "static"       # the web UI files
    engine: str = "cheroot"          # "wsgiref" = threaded stdlib server, dev/test only
    threads: int = 8
    timeout: int = 10                # socket timeout, seconds
    cert_check_s: float = 60.0       # how often to look for a renewed certificate
    watchdog_interval_s: float = 30.0


@dataclass(frozen=True)
class Config:
    hardware: Hardware
    control: Control
    paths: Paths
    auth: "Auth" = None  # type: ignore  (filled in by from_dict)
    server: "Server" = None  # type: ignore

    @property
    def has_cool(self) -> bool:
        return self.hardware.cool_pin is not None

    @property
    def has_fan(self) -> bool:
        return self.hardware.fan_pin is not None

    @property
    def has_heat2(self) -> bool:
        return self.hardware.heat2_pin is not None

    @property
    def modes(self) -> tuple:
        m = ["OFF", "HEAT"]
        if self.has_cool:
            m += ["COOL", "AUTO"]
        if self.has_fan:
            m.append("FAN")
        return tuple(m)

    def capabilities(self) -> dict:
        c = self.control
        return {
            "modes": list(self.modes),
            "heat": True,
            "cool": self.has_cool,
            "fan": self.has_fan,
            "heat_stage_2": self.has_heat2,
            "unit": "F",
            "setpoint_min": c.setpoint_min,
            "setpoint_max": c.setpoint_max,
            "timezone": c.timezone,
        }


def _build(cls, section: str, data: dict):
    names = {f.name for f in fields(cls)}
    unknown = set(data) - names
    if unknown:
        raise ConfigError(f"[{section}] unknown keys: {', '.join(sorted(unknown))}")
    return cls(**data)


def validate(cfg: Config) -> Config:
    from zoneinfo import ZoneInfo

    h, c = cfg.hardware, cfg.control
    pins = [h.sensor_pin, h.heat1_pin, h.heat2_pin, h.cool_pin, h.fan_pin]
    used = [p for p in pins if p is not None]
    for p in used:
        if isinstance(p, bool) or not isinstance(p, int) or not 0 <= p <= 27:
            raise ConfigError(f"invalid BCM pin: {p!r}")
    if len(set(used)) != len(used):
        raise ConfigError("the same pin is used for more than one function")
    if not c.setpoint_min < c.setpoint_max:
        raise ConfigError("setpoint_min must be below setpoint_max")
    if not c.setpoint_min <= c.default_target <= c.setpoint_max:
        raise ConfigError("default_target outside setpoint range")
    if c.deadband <= 0:
        raise ConfigError("deadband must be > 0")
    if cfg.has_cool and not c.auto_gap / 2 > c.deadband:
        raise ConfigError("auto_gap/2 must be greater than deadband")
    if not c.stage2_off_deficit < c.stage2_on_deficit:
        raise ConfigError("stage2_off_deficit must be below stage2_on_deficit")
    for name in ("heat_min_on_s", "heat_min_off_s", "cool_min_on_s",
                 "cool_min_off_s", "changeover_s", "deadman_s",
                 "sensor_jump_expiry_s", "pending_max_days"):
        if getattr(c, name) < 0:
            raise ConfigError(f"{name} must be >= 0")
    a = cfg.auth
    if a.pin_min_length < 4 or a.session_hours < 1 or a.max_body_bytes < 256:
        raise ConfigError("auth limits are too small")
    sv = cfg.server
    if not 0 <= sv.port <= 65535:
        raise ConfigError("server.port out of range")
    if sv.engine not in ("cheroot", "wsgiref"):
        raise ConfigError("server.engine must be 'cheroot' or 'wsgiref'")
    if sv.tls is False and a.cookie_secure:
        raise ConfigError("server.tls = false needs auth.cookie_secure = false "
                          "(development only; never expose this to the internet)")
    if sv.threads < 2 or sv.timeout < 1 or sv.cert_check_s <= 0 or sv.watchdog_interval_s <= 0:
        raise ConfigError("server limits out of range")
    if c.sensor_fail_limit < 1:
        raise ConfigError("sensor_fail_limit must be >= 1")
    try:
        ZoneInfo(c.timezone)
    except Exception as e:
        raise ConfigError(f"invalid timezone {c.timezone!r}: {e}")
    return cfg


def from_dict(raw: dict, base_dir: str = ".") -> Config:
    raw = dict(raw)
    hw = _build(Hardware, "hardware", dict(raw.pop("hardware", {})))
    ct = _build(Control, "control", dict(raw.pop("control", {})))
    pa = _build(Paths, "paths", dict(raw.pop("paths", {})))
    # relative paths are relative to the config file
    pa = Paths(**{f.name: (v if os.path.isabs(v) else os.path.join(base_dir, v))
                  for f in fields(Paths) for v in [getattr(pa, f.name)]})
    au = _build(Auth, "auth", dict(raw.pop("auth", {})))
    sv = _build(Server, "server", dict(raw.pop("server", {})))
    sv = Server(**{f.name: (os.path.join(base_dir, v) if f.name in ("cert_file", "key_file", "static_dir")
                            and not os.path.isabs(v) else v)
                   for f in fields(Server) for v in [getattr(sv, f.name)]})
    return validate(Config(hw, ct, pa, au, sv))


def load(path: str) -> Config:
    try:
        with open(path, "rb") as f:
            raw = tomllib.load(f)
    except FileNotFoundError:
        raise ConfigError(f"config file not found: {path}")
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{path}: {e}")
    return from_dict(raw, os.path.dirname(os.path.abspath(path)))
