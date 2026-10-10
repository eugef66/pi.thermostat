"""PIN check, sessions and login throttling.

 * PIN is stored as a salted scrypt hash in a private file (never in git).
 * Session tokens are random; only their SHA-256 is stored on disk.
 * Failed logins are throttled per IP (exponential backoff) and globally.
"""
from __future__ import annotations

import base64
import collections
import hashlib
import hmac
import json
import os
import secrets
import threading
import time

from .config import Config

SCRYPT_N, SCRYPT_R, SCRYPT_P = 2 ** 14, 8, 1


class AuthError(Exception):
    pass


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode()


def hash_pin(pin: str) -> str:
    salt = secrets.token_bytes(16)
    h = hashlib.scrypt(pin.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P,
                       dklen=32, maxmem=64 * 1024 * 1024)
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${_b64(salt)}${_b64(h)}"


def verify_pin(pin: str, stored: str) -> bool:
    try:
        _, n, r, p, salt, want = stored.split("$")
        got = hashlib.scrypt(pin.encode(), salt=base64.b64decode(salt), n=int(n),
                             r=int(r), p=int(p), dklen=32, maxmem=64 * 1024 * 1024)
        return hmac.compare_digest(got, base64.b64decode(want))
    except (ValueError, TypeError):
        return False


def _write_private(path: str, data: dict) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(data, f)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


class Throttle:
    def __init__(self, a):
        self.a = a
        self.ip = {}                       # ip -> [failures, locked_until]
        self.recent = collections.deque()  # timestamps of all recent failures
        self.global_until = 0.0
        self.lock = threading.Lock()

    def retry_after(self, ip: str, now: float) -> int:
        with self.lock:
            until = max(self.global_until, self.ip.get(ip, [0, 0.0])[1])
        return max(0, int(until - now + 0.999))

    def failure(self, ip: str, now: float) -> None:
        a = self.a
        with self.lock:
            rec = self.ip.setdefault(ip, [0, 0.0])
            rec[0] += 1
            if rec[0] >= a.ip_free_failures:
                extra = rec[0] - a.ip_free_failures
                rec[1] = now + min(a.ip_lockout_max_s, a.ip_lockout_base_s * 2 ** min(extra, 20))
            self.recent.append(now)
            while self.recent and now - self.recent[0] > a.global_window_s:
                self.recent.popleft()
            if len(self.recent) >= a.global_failures:
                self.global_until = now + a.global_lockout_s
                self.recent.clear()
            if len(self.ip) > 5000:        # bound memory under a spray attack
                for k in [k for k, v in self.ip.items() if v[1] < now][:2500]:
                    del self.ip[k]

    def success(self, ip: str) -> None:
        with self.lock:
            self.ip.pop(ip, None)


class Auth:
    def __init__(self, cfg: Config, log, clock=time.time):
        self.cfg, self.log, self.clock = cfg, log, clock
        self.a = cfg.auth
        self.throttle = Throttle(self.a)
        self.lock = threading.Lock()
        self.sessions = self._load_sessions()

    # ---- PIN
    def _stored_pin(self):
        try:
            with open(self.cfg.paths.auth_file) as f:
                return json.load(f).get("pin")
        except (FileNotFoundError, ValueError):
            return None

    @property
    def configured(self) -> bool:
        return bool(self._stored_pin())

    def set_pin(self, pin: str) -> None:
        if len(pin) < self.a.pin_min_length:
            raise AuthError(f"PIN must be at least {self.a.pin_min_length} characters")
        if len(set(pin)) == 1:
            raise AuthError("PIN must not be a single repeated character")
        if len(pin) > 128:
            raise AuthError("PIN is too long")
        _write_private(self.cfg.paths.auth_file, {"pin": hash_pin(pin)})

    def check_pin(self, pin) -> bool:
        stored = self._stored_pin()
        return bool(stored) and isinstance(pin, str) and len(pin) <= 128 \
            and verify_pin(pin, stored)

    # ---- sessions
    def _load_sessions(self) -> dict:
        try:
            with open(self.cfg.paths.sessions_file) as f:
                data = json.load(f)
        except (FileNotFoundError, ValueError):
            return {}
        now = self.clock()
        return {k: v for k, v in data.items() if v.get("expires", 0) > now}

    def _save_sessions(self) -> None:
        _write_private(self.cfg.paths.sessions_file, self.sessions)

    @staticmethod
    def _key(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    def create_session(self, kind: str):
        now = self.clock()
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
        sess = {"kind": kind, "created": now, "csrf": csrf,
                "expires": now + self.a.session_hours * 3600}
        with self.lock:
            self.sessions = {k: v for k, v in self.sessions.items() if v["expires"] > now}
            self.sessions[self._key(token)] = sess
            self._save_sessions()
        return token, sess

    def lookup(self, token):
        if not token or len(token) > 200:
            return None
        with self.lock:
            s = self.sessions.get(self._key(token))
            if s and s["expires"] > self.clock():
                return s
        return None

    def end_session(self, token) -> None:
        with self.lock:
            if self.sessions.pop(self._key(token), None) is not None:
                self._save_sessions()
