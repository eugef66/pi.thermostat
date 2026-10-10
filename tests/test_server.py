import json, os, ssl, subprocess, tempfile, threading, time, unittest, urllib.request, urllib.error

from thermostat import cli, engine, logsetup, server, state as S, auth as A
from tests.test_hardware_cli import set_temp

PIN = "482916"


def make_cert(d, name, cn="thermostat.test"):
    cert, key = os.path.join(d, f"{name}.pem"), os.path.join(d, f"{name}.key")
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "2",
                    "-keyout", key, "-out", cert, "-subj", f"/CN={cn}",
                    "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1"],
                   check=True, capture_output=True)
    os.chmod(key, 0o600)
    return cert, key


def write_cfg(d, extra_server="", tls=True, deadman=1):
    hw = "[hardware]\nemulate = true\nheat1_pin = 2\ncool_pin = 3\nheat2_pin = 5\nfan_pin = 6\n"
    ctl = f'[control]\ntimezone = "UTC"\ndeadman_s = {deadman}\n'
    au = f"[auth]\ncookie_secure = {str(tls).lower()}\n"
    sv = (f"[server]\nengine = \"wsgiref\"\nhost = \"127.0.0.1\"\nport = 0\ntls = {str(tls).lower()}\n"
          "cert_file = \"live/cert.pem\"\nkey_file = \"live/cert.key\"\n"
          "cert_check_s = 0.2\nwatchdog_interval_s = 0.2\n" + extra_server)
    p = os.path.join(d, "config.toml")
    with open(p, "w") as f:
        f.write("\n".join([hw, ctl, au, sv]))
    return p


def peer_der(port):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    import socket
    with socket.create_connection(("127.0.0.1", port), timeout=5) as s:
        with ctx.wrap_socket(s) as t:
            return t.getpeercert(binary_form=True)


class Http:
    def __init__(self, port, tls=True):
        self.base = f"{'https' if tls else 'http'}://127.0.0.1:{port}"
        self.ctx = ssl.create_default_context()
        self.ctx.check_hostname = False
        self.ctx.verify_mode = ssl.CERT_NONE
        self.cookie = None
        self.csrf = None

    def call(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        if self.cookie: req.add_header("Cookie", self.cookie)
        if self.csrf: req.add_header("X-CSRF-Token", self.csrf)
        try:
            with urllib.request.urlopen(req, context=self.ctx, timeout=10) as r:
                raw, code, hdrs = r.read(), r.status, r.headers
        except urllib.error.HTTPError as e:
            raw, code, hdrs = e.read(), e.code, e.headers
        if hdrs.get("Set-Cookie"):
            self.cookie = hdrs["Set-Cookie"].split(";")[0]
        return code, (json.loads(raw) if raw else None)


class Running:
    """Starts server.serve() in a thread against a temp dir."""

    def __init__(self, d, tls=True, extra="", deadman=1):
        self.cfg = cli.load(write_cfg(d, extra, tls=tls, deadman=deadman))
        self.log = logsetup.setup(self.cfg.paths.log_file)
        A.Auth(self.cfg, self.log).set_pin(PIN)
        self.stop, self.port, ready = threading.Event(), None, threading.Event()

        def on_ready(p):
            self.port = p; ready.set()
        self.rc = []
        self.t = threading.Thread(target=lambda: self.rc.append(
            server.serve(self.cfg, self.log, self.stop, on_ready)))
        self.t.start()
        assert ready.wait(10), "server did not start"

    def close(self):
        self.stop.set(); self.t.join(10)


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.d, "live"))
        os.makedirs(os.path.join(self.d, "data"))
        self.cert, self.key = make_cert(os.path.join(self.d, "live"), "cert")
        os.replace(self.cert, os.path.join(self.d, "live", "cert.pem"))
        os.replace(self.key, os.path.join(self.d, "live", "cert.key"))
        self.cert = os.path.join(self.d, "live", "cert.pem")
        self.key = os.path.join(self.d, "live", "cert.key")
        self.srv = Running(self.d)
        self.addCleanup(self.srv.close)

    def test_https_login_and_status(self):
        h = Http(self.srv.port)
        self.assertEqual(h.call("GET", "/api/v1/status")[0], 401)
        code, j = h.call("POST", "/api/v1/login", {"pin": PIN})
        self.assertEqual(code, 200)
        h.csrf = j["csrf_token"]
        code, j = h.call("GET", "/api/v1/status")
        self.assertEqual((code, j["mode"]), (200, "OFF"))
        code, j = h.call("POST", "/api/v1/set", {"mode": "FAN"})
        self.assertEqual((code, j["activity"]), (200, "fan"))

    def test_plain_http_to_tls_port_is_refused(self):
        with self.assertRaises(Exception):
            urllib.request.urlopen(f"http://127.0.0.1:{self.srv.port}/api/v1/status", timeout=5)

    def test_old_tls_versions_refused(self):
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
        ctx.maximum_version = ssl.TLSVersion.TLSv1_1
        import socket
        try:
            ctx.minimum_version = ssl.TLSVersion.TLSv1
        except ValueError:
            self.skipTest("OpenSSL build cannot offer TLS 1.1")
        with self.assertRaises((ssl.SSLError, OSError)):
            with socket.create_connection(("127.0.0.1", self.srv.port), timeout=5) as s:
                ctx.wrap_socket(s)

    def test_certificate_hot_reload(self):
        before = peer_der(self.srv.port)
        new_cert, new_key = make_cert(self.d, "new", cn="renewed.test")
        time.sleep(2.2)                      # let the old files age past the settle window
        os.replace(new_key, self.key)
        os.replace(new_cert, self.cert)
        deadline = time.time() + 8
        while time.time() < deadline and peer_der(self.srv.port) == before:
            time.sleep(0.3)
        self.assertNotEqual(peer_der(self.srv.port), before)
        self.assertIn("TLS certificate reloaded", open(self.srv.cfg.paths.log_file).read())
        h = Http(self.srv.port)                       # server still works
        self.assertEqual(h.call("POST", "/api/v1/login", {"pin": PIN})[0], 200)

    def test_bad_new_certificate_keeps_old_one(self):
        before = peer_der(self.srv.port)
        time.sleep(2.2)
        with open(self.cert, "w") as f:
            f.write("garbage")
        deadline = time.time() + 8
        while time.time() < deadline and "rejected" not in open(self.srv.cfg.paths.log_file).read():
            time.sleep(0.3)
        self.assertEqual(peer_der(self.srv.port), before)
        self.assertIn("rejected", open(self.srv.cfg.paths.log_file).read())

    def test_watchdog_thread_trips_when_cron_is_silent(self):
        set_temp(self.d, 60)
        from thermostat import hardware
        cfg, log = self.srv.cfg, self.srv.log
        store = S.StateStore(cfg.paths.state_file, cfg.paths.lock_file)
        hw = hardware.open_hardware(cfg)
        with store.locked() as st:
            st["mode"], st["target"] = "HEAT", 70.0
        engine.run_cycle(cfg, store, hw, log, samples=[60] * 3, humidity=[40] * 3,
                         now=time.time() - 120)          # cron "ran" 2 min ago
        self.assertTrue(hw.read_relays()["heat1"])
        deadline = time.time() + 5
        while time.time() < deadline and any(hw.read_relays().values()):
            time.sleep(0.2)
        self.assertFalse(any(hw.read_relays().values()))
        with store.snapshot() as st:
            self.assertEqual(st["fault"]["code"], "cron_stalled")

    def test_stopping_server_leaves_relays_alone(self):
        from thermostat import hardware
        hw = hardware.open_hardware(self.srv.cfg)
        hw.set_relays({"fan": True})
        self.srv.close()
        self.assertEqual(self.srv.rc, [0])
        self.assertTrue(hw.read_relays()["fan"])


class StartupTests(unittest.TestCase):
    def test_missing_certificate_refuses_to_start(self):
        d = tempfile.mkdtemp()
        cfg = cli.load(write_cfg(d))
        log = logsetup.setup(cfg.paths.log_file)
        self.assertEqual(server.serve(cfg, log, threading.Event()), 5)

    def test_plain_http_dev_mode(self):
        d = tempfile.mkdtemp()
        os.makedirs(os.path.join(d, "data"))
        s = Running(d, tls=False)
        try:
            h = Http(s.port, tls=False)
            self.assertEqual(h.call("POST", "/api/v1/login", {"pin": PIN})[0], 200)
        finally:
            s.close()

    def test_tls_off_with_secure_cookies_is_rejected(self):
        from thermostat.config import from_dict, ConfigError
        with self.assertRaises(ConfigError):
            from_dict({"server": {"tls": False}})

    def test_cli_check_config(self):
        d = tempfile.mkdtemp()
        os.makedirs(os.path.join(d, "data"))
        p = write_cfg(d, tls=False)
        import io
        from contextlib import redirect_stdout
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(cli.main(["-c", p, "check-config"]), 0)
        self.assertIn("PIN: NOT SET", out.getvalue())


class ReloaderUnit(unittest.TestCase):
    def test_waits_for_files_to_settle(self):
        d = tempfile.mkdtemp()
        cert, key = make_cert(d, "a")
        log = logsetup.setup(os.path.join(d, "l.log"))
        ctx = server.make_context(cert, key)
        r = server.CertReloader(ctx, cert, key, log)
        self.assertFalse(r.check())                         # unchanged
        c2, k2 = make_cert(d, "b")
        os.replace(c2, cert); os.replace(k2, key)
        self.assertFalse(r.check(now=time.time()))          # just written: wait
        self.assertTrue(r.check(now=time.time() + 5))       # settled: load


if __name__ == "__main__":
    unittest.main()
