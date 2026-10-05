"""REST API under /api/v1. JSON only; errors are {"error": {"code", "message"}}."""
from __future__ import annotations

import hmac
import time
from datetime import datetime
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from . import control, engine, static
from .auth import Auth
from .state import LockTimeout
from .webapp import App, HTTPError, Request, Response

READING_STALE_S = 180
RUN_STALE_S = 180


def _iso(cfg, ts):
    return None if ts is None else \
        datetime.fromtimestamp(ts, ZoneInfo(cfg.control.timezone)).isoformat(timespec="seconds")


def status_payload(cfg, st: dict, now: float) -> dict:
    r = st.get("reading")
    relays = {n: st["relays"][n]["on"] for n in ("heat1", "heat2", "cool", "fan")}
    if relays["heat1"] or relays["heat2"]:
        activity = "heating"
    elif relays["cool"]:
        activity = "cooling"
    elif relays["fan"]:
        activity = "fan"
    else:
        activity = "idle"
    reading_age = None if not r else round(now - r["at"])
    run_age = None if st["last_proc_at"] is None else round(now - st["last_proc_at"])
    return {
        "server_time": _iso(cfg, now),
        "unit": "F",
        "temperature": r["temp"] if r else None,
        "humidity": r["humidity"] if r else None,
        "reading_at": _iso(cfg, r["at"]) if r else None,
        "reading_age_s": reading_age,
        "stale": reading_age is None or reading_age > READING_STALE_S
                 or run_age is None or run_age > RUN_STALE_S,
        "mode": st["mode"],
        "target": st["target"],
        "activity": activity,
        "relays": relays,
        "pending": st["pending"],
        "fault": None if not st["fault"] else {
            "code": st["fault"]["code"], "message": st["fault"]["message"],
            "since": _iso(cfg, st["fault"]["since"])},
    }


def create_app(cfg, store, hw, log, auth: Auth, clock=time.time) -> App:
    a = cfg.auth
    app = App(max_body=a.max_body_bytes, secure=a.cookie_secure, log=log)
    cookie_name = "__Host-sid" if a.cookie_secure else "sid"

    def set_cookie(token, max_age):
        v = f"{cookie_name}={token}; Path=/; Max-Age={max_age}; HttpOnly; SameSite=Strict"
        return ("Set-Cookie", v + ("; Secure" if a.cookie_secure else ""))

    def check_origin(req: Request):
        origin = req.header("Origin")
        if origin and urlparse(origin).netloc != req.header("Host"):
            raise HTTPError(403, "csrf_failed", "cross-origin request refused")

    def session_of(req: Request):
        """-> (token, session) or (None, None). Bearer tokens beat cookies."""
        h = req.header("Authorization") or ""
        if h.lower().startswith("bearer "):
            tok = h[7:].strip()
            s = auth.lookup(tok)
            return (tok, s) if s and s["kind"] == "token" else (None, None)
        tok = req.cookies.get(cookie_name)
        s = auth.lookup(tok)
        return (tok, s) if s and s["kind"] == "cookie" else (None, None)

    def require(req: Request, changes_state=False):
        tok, s = session_of(req)
        if not s:
            raise HTTPError(401, "unauthenticated", "login required")
        if changes_state and s["kind"] == "cookie":
            check_origin(req)
            sent = req.header("X-CSRF-Token") or ""
            if not hmac.compare_digest(sent, s["csrf"]):
                raise HTTPError(403, "csrf_failed", "missing or invalid CSRF token")
        return tok, s

    def read_status():
        try:
            with store.snapshot() as st:
                return status_payload(cfg, st, clock())
        except LockTimeout:
            raise HTTPError(503, "busy", "controller busy, try again")

    def run_mutation(mutate):
        try:
            _, st = engine.run_cycle(cfg, store, hw, log, mutate=mutate, now=clock())
        except control.ValidationError as e:
            raise HTTPError(422, e.code, e.message)
        except LockTimeout:
            raise HTTPError(503, "busy", "controller busy, try again")
        return status_payload(cfg, st, clock())

    # ------------------------------------------------------------- routes
    @app.route("POST", "/api/v1/login")
    def login(req):
        check_origin(req)
        body = req.json()
        now = clock()
        wait = auth.throttle.retry_after(req.ip, now)
        if wait:
            log.warning("login throttled for %s (%ss)", req.ip, wait)
            raise HTTPError(429, "throttled", "too many attempts; try again later",
                            [("Retry-After", str(wait))])
        if not auth.configured:
            raise HTTPError(503, "not_configured", "no PIN set; run `set-pin` on the device")
        pin = body.get("pin")
        if not isinstance(pin, str):
            raise HTTPError(422, "invalid_pin", "pin must be a string")
        kind = "token" if body.get("token") is True else "cookie"
        if not auth.check_pin(pin):
            auth.throttle.failure(req.ip, now)
            log.warning("login FAILED from %s", req.ip)
            raise HTTPError(401, "invalid_credentials", "incorrect PIN")
        auth.throttle.success(req.ip)
        token, sess = auth.create_session(kind)
        log.info("login ok from %s (%s)", req.ip, kind)
        out = {"expires_at": _iso(cfg, sess["expires"])}
        if kind == "token":
            out["token"] = token
            return out
        out["csrf_token"] = sess["csrf"]
        return Response(200, out, [set_cookie(token, a.session_hours * 3600)])

    @app.route("POST", "/api/v1/logout")
    def logout(req):
        tok, _ = require(req, changes_state=True)
        auth.end_session(tok)
        log.info("logout from %s", req.ip)
        return Response(204, None, [set_cookie("", 0)])

    @app.route("GET", "/api/v1/session")
    def session(req):
        _, s = session_of(req)
        if not s:
            return {"authenticated": False, "configured": auth.configured}
        out = {"authenticated": True, "configured": True,
               "expires_at": _iso(cfg, s["expires"])}
        if s["kind"] == "cookie":
            out["csrf_token"] = s["csrf"]
        return out

    @app.route("GET", "/api/v1/capabilities")
    def capabilities(req):
        require(req)
        return cfg.capabilities()

    @app.route("GET", "/api/v1/status")
    def status(req):
        require(req)
        return read_status()

    @app.route("POST", "/api/v1/set")
    def set_(req):
        require(req, changes_state=True)
        body = req.json()
        mode = body.get("mode")
        if not isinstance(mode, str):
            raise HTTPError(422, "invalid_mode", "mode is required")
        extra = set(body) - {"mode", "target", "start_at"}
        if extra:
            raise HTTPError(422, "unknown_field", f"unknown field: {sorted(extra)[0]}")

        def mutate(st, now):
            r = control.validate_set(cfg, st, mode.upper(), body.get("target"),
                                     body.get("start_at"), now)
            return control.apply_set(st, r, f"api {req.ip}")
        return run_mutation(mutate)

    @app.route("DELETE", "/api/v1/pending")
    def cancel(req):
        require(req, changes_state=True)
        return run_mutation(lambda st, now: [
            f"{e} [api {req.ip}]" for e in control.cancel_pending(st)])

    static.register(app, cfg.server.static_dir, log)
    return app
