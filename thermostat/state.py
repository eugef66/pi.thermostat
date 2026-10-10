"""Persistent state shared by the cron job and the server.

Every process takes an exclusive file lock, loads the JSON state, mutates it,
and saves it atomically. Timers (when each relay last changed) live here
because each cron run is a fresh process.
"""
from __future__ import annotations

import fcntl
import json
import os
import time
from contextlib import contextmanager

RELAY_NAMES = ("heat1", "heat2", "cool", "fan")
VALID_MODES = ("OFF", "HEAT", "COOL", "AUTO", "FAN")
VERSION = 1


class StateError(Exception):
    pass


class LockTimeout(StateError):
    pass


def new_state(default_target: float = 70.0) -> dict:
    return {
        "version": VERSION,
        "mode": "OFF",
        "target": default_target,
        "pending": None,        # {"mode", "target", "start_at"(ISO 8601 with offset)}
        "relays": {n: {"on": False, "changed_at": None} for n in RELAY_NAMES},
        "sensor": {"failures": 0, "last_good": None, "last_good_at": None,
                   "candidate": None},
        "reading": None,        # {"temp", "humidity", "at"}
        "fault": None,          # {"code", "message", "since"}
        "defer_note": None,
        "last_proc_at": None,
    }


def _normalize(st: dict, default_target: float) -> dict:
    base = new_state(default_target)
    for k, v in base.items():
        st.setdefault(k, v)
    for n in RELAY_NAMES:
        st["relays"].setdefault(n, {"on": False, "changed_at": None})
    for k, v in base["sensor"].items():
        st["sensor"].setdefault(k, v)
    if st["mode"] not in VALID_MODES:
        st["mode"] = "OFF"
    return st


def migrate_legacy(data: dict, default_target: float) -> dict:
    """Import the old db.json (mode / target_temperature / schedule)."""
    st = new_state(default_target)
    mode = data.get("mode")
    st["mode"] = mode if mode in VALID_MODES else "OFF"
    try:
        st["target"] = float(data["target_temperature"])
    except (KeyError, TypeError, ValueError):
        pass
    # the old naive one-shot schedule is dropped on purpose
    return st


class StateStore:
    def __init__(self, path: str, lock_path: str, default_target: float = 70.0,
                 lock_timeout: float = 10.0):
        self.path, self.lock_path = path, lock_path
        self.default_target = default_target
        self.lock_timeout = lock_timeout

    def _load(self) -> dict:
        try:
            with open(self.path) as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("not an object")
        except FileNotFoundError:
            return new_state(self.default_target)
        except (ValueError, OSError):
            # corrupt: keep the evidence, start safe (mode OFF)
            os.replace(self.path, f"{self.path}.corrupt-{int(time.time())}")
            st = new_state(self.default_target)
            st["recovered_from_corruption"] = True
            return st
        if "target_temperature" in data:
            return migrate_legacy(data, self.default_target)
        return _normalize(data, self.default_target)

    def _save(self, st: dict) -> None:
        tmp = f"{self.path}.tmp"
        with open(tmp, "w") as f:
            json.dump(st, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.path)

    @contextmanager
    def locked(self):
        """Exclusive lock + load; saves on clean exit, discards on exception."""
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        fd = open(self.lock_path, "a+")
        try:
            deadline = time.monotonic() + self.lock_timeout
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() > deadline:
                        raise LockTimeout("could not lock state file")
                    time.sleep(0.05)
            st = self._load()
            yield st
            self._save(st)
        finally:
            fd.close()  # closing releases the flock

    @contextmanager
    def snapshot(self):
        """Locked read-only view; nothing is written back."""
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        fd = open(self.lock_path, "a+")
        try:
            deadline = time.monotonic() + self.lock_timeout
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() > deadline:
                        raise LockTimeout("could not lock state file")
                    time.sleep(0.05)
            yield self._load()
        finally:
            fd.close()
