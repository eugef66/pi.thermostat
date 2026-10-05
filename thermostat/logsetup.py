"""Event log shared by cron and server.

One line per event, ISO timestamp with offset. Rotation is done under a file
lock so two processes writing at once cannot corrupt or double-rotate it.
"""
from __future__ import annotations

import fcntl
import logging
import os
from datetime import datetime

LOGGER_NAME = "thermostat"


class SharedRotatingHandler(logging.Handler):
    def __init__(self, path: str, max_bytes: int = 1_000_000, backups: int = 5):
        super().__init__()
        self.path, self.max_bytes, self.backups = path, max_bytes, backups
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)

    def _rotate(self):
        for i in range(self.backups - 1, 0, -1):
            src = f"{self.path}.{i}"
            if os.path.exists(src):
                os.replace(src, f"{self.path}.{i + 1}")
        os.replace(self.path, f"{self.path}.1")

    def emit(self, record):
        try:
            line = self.format(record) + "\n"
            with open(self.path + ".lock", "a+") as lk:
                fcntl.flock(lk, fcntl.LOCK_EX)
                try:
                    if os.path.exists(self.path) and \
                            os.path.getsize(self.path) + len(line) > self.max_bytes:
                        self._rotate()
                    with open(self.path, "a") as f:
                        f.write(line)
                finally:
                    fcntl.flock(lk, fcntl.LOCK_UN)
        except Exception:
            self.handleError(record)


class _Fmt(logging.Formatter):
    def format(self, record):
        ts = datetime.fromtimestamp(record.created).astimezone().isoformat(timespec="seconds")
        return f"{ts} {record.levelname:<7} {record.getMessage()}"


def setup(path: str, verbose: bool = False, max_bytes=1_000_000, backups=5) -> logging.Logger:
    log = logging.getLogger(LOGGER_NAME)
    log.setLevel(logging.INFO)
    log.handlers.clear()
    h = SharedRotatingHandler(path, max_bytes, backups)
    h.setFormatter(_Fmt())
    log.addHandler(h)
    if verbose:
        sh = logging.StreamHandler()
        sh.setFormatter(_Fmt())
        log.addHandler(sh)
    return log


def level_for(event: str) -> int:
    if event.startswith(("FAULT", "INTERLOCK")):
        return logging.ERROR
    if any(w in event for w in ("failed", "rejected", "dropped", "corrupt", "found")):
        return logging.WARNING
    return logging.INFO
