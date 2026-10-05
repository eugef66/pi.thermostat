import json, os, re, shutil, subprocess, tempfile, unittest

from thermostat import engine, hardware, state as S, static as static_mod
from tests.test_api import Client
from tests.test_server import Running, PIN
from tests.test_hardware_cli import set_temp

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC = os.path.join(ROOT, "static")
HAVE_NODE = shutil.which("node") is not None


class StaticServing(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.d, "data"))
        self.srv = Running(self.d, tls=False, extra=f'static_dir = "{STATIC}"\n')
        self.addCleanup(self.srv.close)
        # call the app in-process for header-level assertions
        from thermostat import api, auth, logsetup
        cfg, log = self.srv.cfg, self.srv.log
        self.app = api.create_app(cfg, S.StateStore(cfg.paths.state_file, cfg.paths.lock_file),
                                  hardware.open_hardware(cfg), log, auth.Auth(cfg, log))
        self.c = Client(self.app, secure=False)

    def get(self, path, **kw):
        st, j, h, full = self.c.call("GET", path, **kw)
        return st, h

    def raw(self, path, method="GET", headers=None):
        import io
        env = {"REQUEST_METHOD": method, "PATH_INFO": path, "REMOTE_ADDR": "1.1.1.1",
               "wsgi.input": io.BytesIO(), "CONTENT_LENGTH": "0", "HTTP_HOST": "x"}
        for k, v in (headers or {}).items():
            env["HTTP_" + k.upper().replace("-", "_")] = v
        out = {}
        body = b"".join(self.app(env, lambda s, h, e=None: out.update(status=int(s.split()[0]), h=dict(h))))
        return out["status"], out["h"], body

    def test_index_needs_no_login_and_has_strict_csp(self):
        st, h, body = self.raw("/")
        self.assertEqual(st, 200)
        self.assertTrue(h["Content-Type"].startswith("text/html"))
        csp = h["Content-Security-Policy"]
        for part in ("default-src 'none'", "script-src 'self'", "frame-ancestors 'none'"):
            self.assertIn(part, csp)
        self.assertNotIn("unsafe", csp)
        self.assertEqual(h["X-Frame-Options"], "DENY")

    def test_page_has_no_inline_script_style_or_handlers(self):
        html = open(os.path.join(STATIC, "index.html")).read()
        for m in re.finditer(r"<script\b[^>]*>", html):
            self.assertIn("src=", m.group(0))
        self.assertNotRegex(html, r"<script[^>]*>\s*[^<\s]")     # a src script has an empty body
        self.assertNotRegex(html, r"\sstyle=")
        self.assertNotRegex(html, r"\son[a-z]+=")
        self.assertNotIn("<style", html)
        js = open(os.path.join(STATIC, "app.js")).read()
        self.assertNotIn("innerHTML", js)                        # all text via textContent
        self.assertNotIn("eval(", js)

    def test_login_box_asks_for_number_pad(self):
        html = open(os.path.join(STATIC, "index.html")).read()
        self.assertRegex(html, r'id="pin"[^>]*inputmode="numeric"')
        self.assertRegex(html, r'id="pin"[^>]*type="password"')

    def test_every_referenced_asset_is_served(self):
        html = open(os.path.join(STATIC, "index.html")).read()
        refs = re.findall(r'(?:href|src)="(/[^"]+)"', html)
        self.assertGreaterEqual(len(refs), 5)
        for r in refs:
            self.assertEqual(self.raw(r)[0], 200, r)

    def test_manifest(self):
        st, h, body = self.raw("/manifest.webmanifest")
        self.assertEqual((st, h["Content-Type"]), (200, "application/manifest+json"))
        m = json.loads(body)
        self.assertEqual((m["display"], m["start_url"], m["scope"]), ("standalone", "/", "/"))
        purposes = {i["purpose"] for i in m["icons"]}
        self.assertEqual(purposes, {"any", "maskable"})
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow not installed")
        for i in m["icons"]:
            s, h2, data = self.raw(i["src"])
            self.assertEqual(s, 200, i["src"])
            self.assertEqual(h2["Content-Type"], "image/png")
            import io
            self.assertEqual("%dx%d" % Image.open(io.BytesIO(data)).size, i["sizes"])

    def test_cannot_escape_or_list_or_read_other_types(self):
        for p in ("/static/../config.example.toml", "/static/..%2fconfig.toml",
                  "/static/icons/../../thermostat/config.py", "/static/icons/",
                  "/static/icons", "/static/", "/static/app.py", "/static/.hidden",
                  "/static/nonexistent.js", "/static/%00.js", "/static/..\\x.js"):
            self.assertEqual(self.raw(p)[0], 404, p)

    def test_etag_and_head(self):
        st, h, _ = self.raw("/static/app.js")
        self.assertEqual(h["Cache-Control"], "no-cache")
        st2, h2, b2 = self.raw("/static/app.js", headers={"If-None-Match": h["ETag"]})
        self.assertEqual((st2, b2), (304, b""))
        st3, h3, b3 = self.raw("/static/app.js", method="HEAD")
        self.assertEqual((st3, b3), (200, b""))
        self.assertIn("max-age", self.raw("/static/icons/icon-192.png")[1]["Cache-Control"])

    def test_post_to_static_is_405(self):
        self.assertEqual(self.raw("/", method="POST")[0], 405)


@unittest.skipUnless(HAVE_NODE, "node not installed")
class BrowserCode(unittest.TestCase):
    def test_pure_helpers(self):
        r = subprocess.run(["node", os.path.join(ROOT, "tests", "ui_logic.js")],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_app_js_end_to_end(self):
        d = tempfile.mkdtemp()
        os.makedirs(os.path.join(d, "data"))
        srv = Running(d, tls=False, extra=f'static_dir = "{STATIC}"\n', deadman=300)
        try:
            set_temp(d, 66)
            hw = hardware.open_hardware(srv.cfg)
            store = S.StateStore(srv.cfg.paths.state_file, srv.cfg.paths.lock_file)
            engine.run_cycle(srv.cfg, store, hw, srv.log, samples=[66] * 3, humidity=[45] * 3)
            env = dict(os.environ, BASE=f"http://127.0.0.1:{srv.port}", PIN=PIN)
            r = subprocess.run(["node", os.path.join(ROOT, "tests", "ui_e2e.js")],
                               capture_output=True, text=True, env=env, timeout=60)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("UI E2E OK", r.stdout)
        finally:
            srv.close()


if __name__ == "__main__":
    unittest.main()
