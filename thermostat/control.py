"""Control logic. Pure functions over a state dict: no GPIO, no clock, no I/O.

`cycle()` is the one entry point used by both the cron job and the server:
it reconciles recorded relay state with the hardware, applies a due pending
change, filters the sensor reading, and decides which relays should be on,
honoring deadband, minimum run/off times, heat/cool changeover lockout and
fail-safe-off. The caller drives the pins and writes the log.
"""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from .config import Config
from .state import RELAY_NAMES

INF = float("inf")
HEAT_MODES = ("HEAT", "AUTO")
COOL_MODES = ("COOL", "AUTO")
READING_MAX_AGE_S = 180


class ValidationError(Exception):
    """Bad request value. The API maps this to HTTP 422."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


@dataclass
class CycleResult:
    relays: dict                      # desired on/off per relay
    events: list = field(default_factory=list)
    temp: Optional[float] = None


# ---------------------------------------------------------------- helpers

def _off_for(st: dict, name: str, now: float) -> float:
    r = st["relays"][name]
    if r["on"]:
        return 0.0
    return INF if r["changed_at"] is None else now - r["changed_at"]


def _on_for(st: dict, name: str, now: float) -> float:
    r = st["relays"][name]
    if not r["on"]:
        return 0.0
    return INF if r["changed_at"] is None else now - r["changed_at"]


def parse_time(value, tz_name: str) -> datetime:
    """ISO 8601 string -> aware datetime. Naive values use the configured zone."""
    if not isinstance(value, str):
        raise ValidationError("invalid_start_at", "start_at must be an ISO 8601 string")
    s = value.strip()
    if s.endswith(("Z", "z")):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        raise ValidationError("invalid_start_at", "start_at is not valid ISO 8601")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo(tz_name))
    return dt


# ------------------------------------------------------------ set requests

def validate_set(cfg: Config, st: dict, mode, target, start_at, now: float) -> dict:
    """Normalize and validate a set request. Raises ValidationError."""
    c = cfg.control
    if mode not in cfg.modes:
        raise ValidationError("invalid_mode",
                              f"mode must be one of {', '.join(cfg.modes)}")
    if target is None:
        target = st["target"]
    else:
        if isinstance(target, bool) or not isinstance(target, (int, float)) \
                or not math.isfinite(target):
            raise ValidationError("invalid_target", "target must be a number")
        if not c.setpoint_min <= target <= c.setpoint_max:
            raise ValidationError(
                "target_out_of_range",
                f"target must be between {c.setpoint_min:g} and {c.setpoint_max:g}")
    out = {"mode": mode, "target": target, "start_at": None}
    if start_at is not None:
        dt = parse_time(start_at, c.timezone)
        ts = dt.timestamp()
        if ts <= now:
            raise ValidationError("start_at_in_past", "start_at must be in the future")
        if ts > now + c.pending_max_days * 86400:
            raise ValidationError("start_at_too_far",
                                  f"start_at is more than {c.pending_max_days} days away")
        out["start_at"] = dt.astimezone(ZoneInfo(c.timezone)).isoformat(timespec="minutes")
    return out


def apply_set(st: dict, req: dict, source: str = "api") -> list:
    """Apply a validated request: immediately, or as the single pending change.
    An immediate change leaves any pending change alone (cancel it explicitly)."""
    if req["start_at"]:
        st["pending"] = {"mode": req["mode"], "target": req["target"],
                         "start_at": req["start_at"]}
        return [f"set[{source}]: pending {req['mode']} {req['target']:g} at {req['start_at']}"]
    st["mode"], st["target"] = req["mode"], req["target"]
    return [f"set[{source}]: {req['mode']} {req['target']:g}"]


def cancel_pending(st: dict) -> list:
    if st.get("pending"):
        st["pending"] = None
        return ["pending change cancelled"]
    return []


def _activate_pending(cfg: Config, st: dict, now: float, events: list) -> None:
    p = st.get("pending")
    if not p:
        return
    try:
        due = parse_time(p["start_at"], cfg.control.timezone).timestamp()
    except (ValidationError, KeyError, TypeError):
        st["pending"] = None
        events.append("pending change dropped: unreadable start time")
        return
    if now >= due:
        st["pending"] = None
        if p.get("mode") in cfg.modes:
            st["mode"], st["target"] = p["mode"], p["target"]
            events.append(f"pending applied: {p['mode']} {p['target']:g}")
        else:
            events.append("pending change dropped: mode no longer available")


# ------------------------------------------------------------ sensor input

def accept_reading(cfg: Config, st: dict, samples, now: float, events: list):
    """Median of valid samples + plausibility filter. Returns F or None."""
    c, s = cfg.control, st["sensor"]
    valid = [x for x in samples
             if isinstance(x, (int, float)) and c.sensor_min <= x <= c.sensor_max]
    if not valid:
        s["failures"] += 1
        events.append(f"sensor read failed ({s['failures']}/{c.sensor_fail_limit})")
        return None
    m = statistics.median(valid) + c.calibration
    last, last_at = s["last_good"], s["last_good_at"]
    stale = last_at is None or now - last_at > c.sensor_jump_expiry_s
    if last is not None and not stale and abs(m - last) > c.sensor_max_jump:
        cand = s["candidate"]
        if cand is not None and abs(m - cand) <= c.sensor_max_jump:
            events.append(f"sensor jump to {m:.1f}F confirmed")   # repeated: accept
        else:
            s["candidate"] = m
            s["failures"] += 1
            events.append(f"sensor jump to {m:.1f}F rejected, awaiting confirmation")
            return None
    s.update(failures=0, last_good=m, last_good_at=now, candidate=None)
    return m


def _median_humidity(samples):
    v = [x for x in samples if isinstance(x, (int, float)) and 0 <= x <= 100]
    return round(statistics.median(v), 1) if v else None


# ---------------------------------------------------------------- decision

def decide(cfg: Config, st: dict, temp: Optional[float], now: float):
    """Return (desired relays dict, events). Mutates st only for fault/defer_note."""
    c = cfg.control
    events: list = []
    cur = {n: st["relays"][n]["on"] for n in RELAY_NAMES}
    all_off = {n: False for n in RELAY_NAMES}

    # Fan-only needs no temperature: it must work before the first reading
    # and with a stale cache, as long as the sensor is not in fail-safe.
    if temp is None and st["mode"] == "FAN" and st["sensor"]["failures"] < c.sensor_fail_limit:
        temp = st["target"]

    if temp is None:
        if st["sensor"]["failures"] >= c.sensor_fail_limit:
            if not st["fault"] or st["fault"]["code"] != "sensor":
                st["fault"] = {"code": "sensor", "since": now,
                               "message": "Temperature sensor failing; heating and cooling stopped"}
                events.append("FAULT sensor: all relays off")
            return dict(all_off), events
        if st["mode"] == "OFF":
            return dict(all_off), events  # OFF never waits for a sensor
        return dict(cur), events          # tolerate a few misses: hold

    if st["fault"] and st["fault"]["code"] == "sensor":
        st["fault"] = None
        events.append("sensor recovered")

    mode, target = st["mode"], st["target"]
    if mode == "OFF":
        st["defer_note"] = None
        return dict(all_off), events      # OFF is always immediate

    db = c.deadband
    half = c.auto_gap / 2
    heat_on = heat_off = cool_on = cool_off = None
    if mode == "HEAT":
        heat_on, heat_off = target - db, target
    elif mode == "COOL":
        cool_on, cool_off = target + db, target
    elif mode == "AUTO":
        heat_on, heat_off = target - half, target - db
        cool_on, cool_off = target + half, target + db

    want_heat = want_cool = False
    if heat_on is not None:
        want_heat = temp < heat_off if cur["heat1"] else temp <= heat_on
    if cool_on is not None and cfg.has_cool:
        want_cool = temp > cool_off if cur["cool"] else temp >= cool_on

    final = dict(cur)
    just_off = set()
    notes = []
    cfgs = {"heat1": (c.heat_min_on_s, c.heat_min_off_s),
            "cool": (c.cool_min_on_s, c.cool_min_off_s)}

    # 1) turn-offs, respecting minimum run time
    for n, want in (("heat1", want_heat), ("cool", want_cool)):
        if cur[n] and not want:
            if _on_for(st, n, now) < cfgs[n][0]:
                notes.append(f"{n} minimum run time")
            else:
                final[n] = False
                just_off.add(n)
    # 2) turn-ons, respecting minimum off time and heat/cool changeover
    for n, other, want in (("heat1", "cool", want_heat), ("cool", "heat1", want_cool)):
        if want and not cur[n]:
            other_off = 0.0 if other in just_off else _off_for(st, other, now)
            if final[other]:
                notes.append(f"{n} waiting for {other} to stop")
            elif other_off < c.changeover_s:
                notes.append(f"{n} changeover lockout")
            elif _off_for(st, n, now) < cfgs[n][1]:
                notes.append(f"{n} minimum off time")
            else:
                final[n] = True

    # 3) stage 2: only while W1 is on, with a release point below the trigger
    final["heat2"] = False
    if cfg.has_heat2 and final["heat1"] and mode in HEAT_MODES:
        deficit = target - temp
        final["heat2"] = (deficit > c.stage2_off_deficit if cur["heat2"]
                          else deficit > c.stage2_on_deficit)

    # 4) fan
    final["fan"] = bool(cfg.has_fan and (
        mode == "FAN"
        or (c.fan_with_cool and final["cool"])
        or (c.fan_with_heat and final["heat1"])))

    # last-resort interlock
    if (final["heat1"] or final["heat2"]) and final["cool"]:
        final.update(heat1=False, heat2=False, cool=False)
        events.append("INTERLOCK: heat and cool both requested; all off")

    note = "; ".join(notes) or None
    if note != st["defer_note"]:
        if note:
            events.append(f"deferred: {note}")
        st["defer_note"] = note
    return final, events


# ------------------------------------------------------------------- cycle

def cycle(cfg: Config, st: dict, samples, humidity_samples, actual: dict,
          now: float) -> CycleResult:
    """One control pass. `samples` are raw F readings (None for failed reads);
    `actual` is the real on/off state of each relay from the hardware."""
    events: list = []
    c = cfg.control

    if st.pop("recovered_from_corruption", False):
        events.append("state file was corrupt; reset to OFF")

    # 1) hardware is the truth; after a reboot everything reads off and the
    #    timers restart from now, which keeps compressor protection intact
    for n in RELAY_NAMES:
        a = bool(actual.get(n, False))
        r = st["relays"][n]
        if r["on"] != a:
            events.append(f"relay {n} found {'ON' if a else 'OFF'}; timer restarted")
            r["on"], r["changed_at"] = a, now

    # 2) config may have changed since the state was saved
    if st["mode"] not in cfg.modes:
        events.append(f"mode {st['mode']} unavailable; switched to OFF")
        st["mode"] = "OFF"
    clamped = min(max(st["target"], c.setpoint_min), c.setpoint_max)
    if clamped != st["target"]:
        events.append(f"target {st['target']:g} outside limits; set to {clamped:g}")
        st["target"] = clamped

    if samples is not None and st["fault"] and st["fault"]["code"] == "cron_stalled":
        st["fault"] = None
        events.append("control loop running again")
    _activate_pending(cfg, st, now, events)
    if samples is None:
        # Immediate action from a Set request: no sensor read, reuse a fresh
        # cached one. A stale cache just holds; the next cron run decides.
        r = st.get("reading")
        temp = r["temp"] if r and now - r["at"] <= READING_MAX_AGE_S else None
    else:
        temp = accept_reading(cfg, st, samples, now, events)
        if temp is not None:
            st["reading"] = {"temp": round(temp, 1),
                             "humidity": _median_humidity(humidity_samples or []),
                             "at": now}
        st["last_proc_at"] = now        # only real sensor runs prove cron is alive

    want, ev = decide(cfg, st, temp, now)
    events += ev

    for n in RELAY_NAMES:
        if want[n] != st["relays"][n]["on"]:
            st["relays"][n] = {"on": want[n], "changed_at": now}
            shown = f" at {temp:.1f}F" if temp is not None else ""
            events.append(f"relay {n} {'ON' if want[n] else 'OFF'}{shown}")
    return CycleResult(want, events, temp)


def force_off(st: dict, now: float, reason: str) -> list:
    """Record all relays off (dead-man trip, shutdown). Caller drives the pins."""
    events = []
    for n in RELAY_NAMES:
        if st["relays"][n]["on"]:
            st["relays"][n] = {"on": False, "changed_at": now}
            events.append(f"relay {n} OFF ({reason})")
    return events


def deadman_expired(cfg: Config, st: dict, now: float) -> bool:
    """True if a relay is on but the cron loop has been silent too long."""
    last = st.get("last_proc_at")
    if last is None or not any(st["relays"][n]["on"] for n in RELAY_NAMES):
        return False
    return now - last > cfg.control.deadman_s
