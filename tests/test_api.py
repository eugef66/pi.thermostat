import io, json, os, tempfile, unittest
from datetime import datetime, timedelta, timezone

from thermostat import api, auth as A, cli, engine, hardware, logsetup, state as S
from thermostat.config import from_dict
from tests.test_hardware_cli import write_cfg, set_temp

PIN = "482916"


class Client:
    """Minimal WSGI test client."""

    def __init__(self, app, ip="10.0.0.5", secure=True):
        self.app, self.ip, self.cookies = app, ip, {}
        self.csrf = None
        self.cookie_name = "__Host-sid" if secure else "sid"

    def call(self, method, path, body=None, headers=None, ctype="application/json", raw=None):
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else b"")
        env = {"REQUEST_METHOD": method, "PATH_INFO": path, "REMOTE_ADDR": self.ip,
               "CONTENT_TYPE": ctype, "CONTENT_LENGTH": str(len(data)),
               "wsgi.input": io.BytesIO(data), "HTTP_HOST": "t.example.com"}
        if self.cookies:
            env["HTTP_COOKIE"] = "; ".join(f"{k}={v}" for k, v in self.cookies.items())
        for k, v in (headers or {}).items():
            env["HTTP_" + k.upper().replace("-", "_")] = v
        out = {}

        def sr(status, hdrs, exc=None):
            out["status"], out["headers"] = int(status.split()[0]), hdrs
        payload = b"".join(self.app(env, sr))
        for k, v in out["headers"]:
            if k == "Set-Cookie":
                name, _, rest = v.partition("=")
                val = rest.split(";")[0]
                if val: self.cookies[name] = val
                else: self.cookies.pop(name, None)
        try:
            j = json.loads(payload) if payload else None
        except ValueError:
            j = None
        return out["status"], j, dict(out["headers"]), dict(out)

    def login(self, pin=PIN):
        st, j, _, _ = self.call("POST", "/api/v1/login", {"pin": pin})
        if st == 200: self.csrf = j["csrf_token"]
        return st, j

    def post(self, path, body=None, csrf=True, **kw):
        h = {"X-CSRF-Token": self.csrf} if csrf and self.csrf else {}
        return self.call("POST", path, body, headers=h, **kw)[:3]


class ApiBase(unittest.TestCase):
    secure = True

    def setUp(self):
        self.d = tempfile.mkdtemp()
        path = write_cfg(self.d)
        with open(path, "a") as f:
            f.write(f"\n[auth]\ncookie_secure = {str(self.secure).lower()}\n")
        os.makedirs(os.path.join(self.d, "data"), exist_ok=True)
        self.cfg = cli.load(path)
        self.log = logsetup.setup(self.cfg.paths.log_file)
        self.now = datetime(2030, 1, 1, 12, 0, tzinfo=timezone.utc).timestamp()
        self.clock = lambda: self.now
        self.auth = A.Auth(self.cfg, self.log, self.clock)
        self.auth.set_pin(PIN)
        self.store = S.StateStore(self.cfg.paths.state_file, self.cfg.paths.lock_file)
        self.hw = hardware.open_hardware(self.cfg)
        self.app = api.create_app(self.cfg, self.store, self.hw, self.log, self.auth, self.clock)
        self.c = Client(self.app, secure=self.secure)

    def tick_cron(self, temp):
        samples = [temp] * 3
        engine.run_cycle(self.cfg, self.store, self.hw, self.log, samples=samples,
                         humidity=[45] * 3, now=self.now)


class AuthTests(ApiBase):
    def test_everything_requires_login(self):
        for m, p in (("GET", "/api/v1/status"), ("GET", "/api/v1/capabilities"),
                     ("POST", "/api/v1/set"), ("DELETE", "/api/v1/pending"),
                     ("POST", "/api/v1/logout")):
            st, j, _, _ = self.c.call(m, p, {})
            self.assertEqual(st, 401, p)
            self.assertEqual(j["error"]["code"], "unauthenticated")

    def test_login_cookie_attributes(self):
        st, j, h, full = self.c.call("POST", "/api/v1/login", {"pin": PIN})
        self.assertEqual(st, 200)
        cookie = [v for k, v in full["headers"] if k == "Set-Cookie"][0]
        for part in ("__Host-sid=", "HttpOnly", "Secure", "SameSite=Strict", "Path=/"):
            self.assertIn(part, cookie)
        self.assertNotIn("Domain", cookie)
        self.assertIn("csrf_token", j)
        self.assertIn("Strict-Transport-Security", h)
        self.assertEqual(h["Cache-Control"], "no-store")
        self.assertEqual(h["X-Frame-Options"], "DENY")

    def test_wrong_pin_and_bad_input(self):
        self.assertEqual(self.c.login("000111")[0], 401)
        st, j, _, _ = self.c.call("POST", "/api/v1/login", {"pin": 123456})
        self.assertEqual(st, 422)
        self.assertEqual(self.c.call("POST", "/api/v1/login", raw=b"{bad")[0], 400)
        self.assertEqual(self.c.call("POST", "/api/v1/login", {"pin": PIN},
                                     ctype="text/plain")[0], 415)
        self.assertEqual(self.c.call("POST", "/api/v1/login", raw=b"x" * 5000)[0], 413)

    def test_session_endpoint(self):
        self.assertFalse(self.c.call("GET", "/api/v1/session")[1]["authenticated"])
        self.c.login()
        j = self.c.call("GET", "/api/v1/session")[1]
        self.assertTrue(j["authenticated"])
        self.assertEqual(j["csrf_token"], self.c.csrf)   # lets a reloaded page recover

    def test_csrf_and_origin_enforced(self):
        self.c.login()
        body = {"mode": "HEAT", "target": 70}
        self.assertEqual(self.c.post("/api/v1/set", body, csrf=False)[0], 403)
        self.assertEqual(self.c.call("POST", "/api/v1/set", body,
                                     headers={"X-CSRF-Token": "wrong"})[0], 403)
        self.assertEqual(self.c.call("POST", "/api/v1/set", body, headers={
            "X-CSRF-Token": self.c.csrf, "Origin": "https://evil.example"})[0], 403)
        self.assertEqual(self.c.call("POST", "/api/v1/set", body, headers={
            "X-CSRF-Token": self.c.csrf, "Origin": "https://t.example.com"})[0], 200)

    def test_logout_invalidates(self):
        self.c.login()
        self.assertEqual(self.c.post("/api/v1/logout")[0], 204)
        self.assertEqual(self.c.call("GET", "/api/v1/status")[0], 401)

    def test_session_expires(self):
        self.c.login()
        self.now += self.cfg.auth.session_hours * 3600 + 1
        self.assertEqual(self.c.call("GET", "/api/v1/status")[0], 401)

    def test_sessions_survive_restart_and_store_only_hashes(self):
        self.c.login()
        raw = open(self.cfg.paths.sessions_file).read()
        token = self.c.cookies["__Host-sid"]
        self.assertNotIn(token, raw)
        auth2 = A.Auth(self.cfg, self.log, self.clock)
        app2 = api.create_app(self.cfg, self.store, self.hw, self.log, auth2, self.clock)
        c2 = Client(app2); c2.cookies = dict(self.c.cookies)
        self.assertEqual(c2.call("GET", "/api/v1/status")[0], 200)

    def test_bearer_token_flow_needs_no_csrf(self):
        st, j, _, _ = self.c.call("POST", "/api/v1/login", {"pin": PIN, "token": True})
        self.assertEqual(st, 200)
        self.assertNotIn("csrf_token", j)
        fresh = Client(self.app)
        h = {"Authorization": "Bearer " + j["token"]}
        self.assertEqual(fresh.call("GET", "/api/v1/status", headers=h)[0], 200)
        self.assertEqual(fresh.call("POST", "/api/v1/set", {"mode": "OFF"}, headers=h)[0], 200)
        # a bearer token is not accepted as a cookie, nor vice versa
        fresh.cookies = {"__Host-sid": j["token"]}
        self.assertEqual(fresh.call("GET", "/api/v1/status")[0], 401)

    def test_pin_not_configured(self):
        os.remove(self.cfg.paths.auth_file)
        self.assertEqual(self.c.login()[0], 503)

    def test_pin_policy_and_file_mode(self):
        for bad in ("12345", "111111", "x" * 129):
            with self.assertRaises(A.AuthError):
                self.auth.set_pin(bad)
        self.auth.set_pin("correct horse battery")
        self.assertEqual(os.stat(self.cfg.paths.auth_file).st_mode & 0o777, 0o600)
        self.assertNotIn("correct", open(self.cfg.paths.auth_file).read())
        self.assertTrue(self.auth.check_pin("correct horse battery"))
        self.assertFalse(self.auth.check_pin(PIN))

    def test_throttle_per_ip_with_backoff(self):
        for _ in range(5):
            self.assertEqual(self.c.login("999999")[0], 401)
        st, j = self.c.login(PIN)                      # right PIN, still locked
        self.assertEqual(st, 429)
        _, _, h, _ = self.c.call("POST", "/api/v1/login", {"pin": PIN})
        self.assertIn("Retry-After", h)
        other = Client(self.app, ip="10.0.0.9")
        self.assertEqual(other.login()[0], 200)        # other clients unaffected
        self.now += 31
        self.assertEqual(self.c.login("999999")[0], 401)   # 6th failure -> 60 s lock
        self.now += 31
        self.assertEqual(self.c.login(PIN)[0], 429)
        self.now += 31
        self.assertEqual(self.c.login(PIN)[0], 200)

    def test_global_throttle(self):
        for i in range(30):
            Client(self.app, ip=f"10.1.0.{i}").login("999999")
        self.assertEqual(Client(self.app, ip="10.2.0.1").login(PIN)[0], 429)
        self.now += 301
        self.assertEqual(Client(self.app, ip="10.2.0.1").login(PIN)[0], 200)

    def test_auth_events_logged(self):
        self.c.login("999999"); self.c.login()
        text = open(self.cfg.paths.log_file).read()
        self.assertIn("login FAILED from 10.0.0.5", text)
        self.assertIn("login ok from 10.0.0.5", text)
        self.assertNotIn(PIN, text)

    def test_routing_errors(self):
        self.assertEqual(self.c.call("GET", "/api/v1/nope")[0], 404)
        st, _, h, _ = self.c.call("PUT", "/api/v1/login", {})
        self.assertEqual((st, h["Allow"]), (405, "POST"))


class ControlApiTests(ApiBase):
    def setUp(self):
        super().setUp()
        set_temp(self.d, 66)
        self.tick_cron(66)
        self.c.login()

    def test_capabilities(self):
        j = self.c.call("GET", "/api/v1/capabilities")[1]
        self.assertEqual(j["modes"], ["OFF", "HEAT", "COOL", "AUTO", "FAN"])
        self.assertTrue(j["heat_stage_2"] and j["fan"])

    def test_status_shape(self):
        j = self.c.call("GET", "/api/v1/status")[1]
        self.assertEqual(j["temperature"], 66)
        self.assertEqual(j["humidity"], 45)
        self.assertEqual((j["mode"], j["activity"], j["stale"]), ("OFF", "idle", False))
        self.assertIsNone(j["fault"])
        self.assertTrue(j["server_time"].startswith("2030-01-01"))
        self.now += 400
        self.assertTrue(self.c.call("GET", "/api/v1/status")[1]["stale"])

    def test_set_applies_immediately_and_cron_continues(self):
        st, j, _ = self.c.post("/api/v1/set", {"mode": "heat", "target": 70})
        self.assertEqual(st, 200)
        self.assertEqual((j["mode"], j["target"], j["activity"]), ("HEAT", 70, "heating"))
        self.assertTrue(j["relays"]["heat1"] and j["relays"]["heat2"])  # 4F below
        self.assertEqual(json.load(open(os.path.join(self.d, "data/emulated_pins.json")))["2"], 0)
        self.assertIn("set[api 10.0.0.5]", open(self.cfg.paths.log_file).read())

    def test_off_is_immediate(self):
        self.c.post("/api/v1/set", {"mode": "HEAT", "target": 70})
        j = self.c.post("/api/v1/set", {"mode": "OFF"})[1]
        self.assertEqual(j["activity"], "idle")
        self.assertFalse(any(self.hw.read_relays().values()))

    def test_validation_errors_are_422_and_touch_nothing(self):
        for body, code in (({"mode": "BOGUS"}, "invalid_mode"),
                           ({"mode": "HEAT", "target": 99}, "target_out_of_range"),
                           ({"mode": "HEAT", "target": "70"}, "invalid_target"),
                           ({"mode": "HEAT", "start_at": "garbage"}, "invalid_start_at"),
                           ({"mode": "HEAT", "start_at": "2001-01-01T00:00:00Z"}, "start_at_in_past"),
                           ({"mode": "HEAT", "bogus": 1}, "unknown_field"),
                           ({}, "invalid_mode")):
            st, j, _ = self.c.post("/api/v1/set", body)
            self.assertEqual((st, j["error"]["code"]), (422, code), body)
        self.assertEqual(self.c.call("GET", "/api/v1/status")[1]["mode"], "OFF")
        self.assertFalse(any(self.hw.read_relays().values()))

    def test_pending_lifecycle(self):
        start = (datetime.fromtimestamp(self.now, timezone.utc) + timedelta(hours=2)).isoformat()
        j = self.c.post("/api/v1/set", {"mode": "HEAT", "target": 72, "start_at": start})[1]
        self.assertEqual(j["mode"], "OFF")
        self.assertEqual(j["pending"]["mode"], "HEAT")
        self.assertIn("+00:00", j["pending"]["start_at"])
        st, j, _, _ = self.c.call("DELETE", "/api/v1/pending",
                                  headers={"X-CSRF-Token": self.c.csrf})
        self.assertEqual((st, j["pending"]), (200, None))
        # replace, then let it come due via the cron loop
        self.c.post("/api/v1/set", {"mode": "HEAT", "target": 72, "start_at": start})
        self.now += 3 * 3600
        self.tick_cron(66)
        j = self.c.call("GET", "/api/v1/status")[1]
        self.assertEqual((j["mode"], j["target"], j["pending"]), ("HEAT", 72, None))

    def test_heat_only_install_rejects_cool(self):
        write_cfg(self.d, cool_pin=None)       # rewrites config without a cool pin
        cfg = from_dict({"hardware": {"emulate": True, "heat1_pin": 2}}, self.d)
        app = api.create_app(cfg, self.store, self.hw, self.log, self.auth, self.clock)
        c = Client(app, secure=True); c.cookies = dict(self.c.cookies); c.csrf = self.c.csrf
        self.assertEqual(c.call("GET", "/api/v1/capabilities")[1]["modes"], ["OFF", "HEAT"])
        st, j, _ = c.post("/api/v1/set", {"mode": "COOL", "target": 70})
        self.assertEqual((st, j["error"]["code"]), (422, "invalid_mode"))

    def test_fault_visible_in_status(self):
        for _ in range(5):
            engine.run_cycle(self.cfg, self.store, self.hw, self.log,
                             samples=[None] * 3, humidity=[None] * 3, now=self.now)
        f = self.c.call("GET", "/api/v1/status")[1]["fault"]
        self.assertEqual(f["code"], "sensor")


class WatchdogTests(ApiBase):
    def test_deadman_trips_and_recovers(self):
        set_temp(self.d, 60)
        self.tick_cron(60)
        self.c.login()
        self.c.post("/api/v1/set", {"mode": "HEAT", "target": 70})
        self.assertTrue(any(self.hw.read_relays().values()))
        self.assertFalse(engine.watchdog_tick(self.cfg, self.store, self.hw, self.log, self.now + 200))
        self.assertTrue(engine.watchdog_tick(self.cfg, self.store, self.hw, self.log, self.now + 400))
        self.assertFalse(any(self.hw.read_relays().values()))
        with self.store.snapshot() as st:
            self.assertEqual(st["fault"]["code"], "cron_stalled")
        self.now += 400
        self.tick_cron(60)                      # cron comes back
        with self.store.snapshot() as st:
            self.assertIsNone(st["fault"])


class InsecureDevMode(ApiBase):
    secure = False

    def test_http_dev_cookie(self):
        _, _, h, full = self.c.call("POST", "/api/v1/login", {"pin": PIN})
        cookie = [v for k, v in full["headers"] if k == "Set-Cookie"][0]
        self.assertTrue(cookie.startswith("sid="))
        self.assertNotIn("Secure", cookie)
        self.assertNotIn("Strict-Transport-Security", h)


if __name__ == "__main__":
    unittest.main()
