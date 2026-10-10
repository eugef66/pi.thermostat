"""One locked control pass: used by cron (`proc`) and, later, by the server.

Lock -> load state -> (apply request) -> read real relay state -> decide ->
drive pins -> save. If anything unexpected fails after the request step,
every relay is driven off (fail-safe) and the exception propagates.
"""
from __future__ import annotations

import copy
import time

from . import control
from .config import Config
from .hardware import Hardware
from .logsetup import level_for
from .state import StateStore


def run_cycle(cfg: Config, store: StateStore, hw: Hardware, log, *,
              samples=None, humidity=None, mutate=None, now=None):
    now = time.time() if now is None else now
    with store.locked() as st:
        events = list(mutate(st, now)) if mutate else []   # may raise ValidationError
        try:
            actual = hw.read_relays()
            res = control.cycle(cfg, st, samples, humidity, actual, now)
            hw.set_relays(res.relays)
        except Exception:
            hw.all_off()
            log.exception("control cycle failed; all relays driven off")
            raise
        for e in events + res.events:
            log.log(level_for(e), e)
        return res, copy.deepcopy(st)


def read_sensor_safely(hw: Hardware, log):
    """A sensor driver crash is just a failed read, never a control crash."""
    try:
        return hw.read_sensor()
    except Exception as e:
        log.warning("sensor driver error: %s: %s", type(e).__name__, e)
        return [None] * 3, [None] * 3


def watchdog_tick(cfg: Config, store: StateStore, hw: Hardware, log, now=None) -> bool:
    """Dead-man switch: if a relay is on but cron has been silent too long,
    drive everything off. Returns True if it tripped."""
    now = time.time() if now is None else now
    with store.locked() as st:
        if not control.deadman_expired(cfg, st, now):
            return False
        hw.all_off()
        events = control.force_off(st, now, "dead-man")
        st["fault"] = {"code": "cron_stalled", "since": now,
                       "message": "Control loop stopped; heating and cooling shut off"}
        for e in events:
            log.error(e)
        log.error("FAULT dead-man: control loop silent for more than %ss; all relays off",
                  cfg.control.deadman_s)
        return True
