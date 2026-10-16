import datetime, os, shutil, socket, ssl, subprocess, tempfile, unittest

from tests.test_server import Running

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "deploy", "make-private-cert.sh")
HAVE = shutil.which("openssl") and shutil.which("sh")
HOST = "thermostat.example.com"


def make(out, *names, **env):
    return subprocess.run(["sh", SCRIPT, *names], capture_output=True, text=True,
                          env=dict(os.environ, OUT_DIR=out, **env))


def openssl_x509(path, *args):
    return subprocess.run(["openssl", "x509", "-in", path, "-noout", *args],
                          capture_output=True, text=True).stdout


@unittest.skipUnless(HAVE, "openssl/sh not available")
class PrivateCA(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.pca = os.path.join(self.d, "pca")
        r = make(self.pca, HOST, "thermostat.local", "192.168.1.50")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.ca = os.path.join(self.pca, "ca.crt")
        self.cert = os.path.join(self.pca, "fullchain.pem")

    def test_permissions_and_lifetime(self):
        mode = lambda n: oct(os.stat(os.path.join(self.pca, n)).st_mode & 0o777)
        self.assertEqual((mode("ca.key"), mode("privkey.pem")), ("0o600", "0o600"))
        self.assertEqual((mode("ca.crt"), mode("fullchain.pem")), ("0o644", "0o644"))
        fmt = "%b %d %H:%M:%S %Y %Z"
        start = datetime.datetime.strptime(openssl_x509(self.cert, "-startdate").split("=")[1].strip(), fmt)
        end = datetime.datetime.strptime(openssl_x509(self.cert, "-enddate").split("=")[1].strip(), fmt)
        self.assertLessEqual((end - start).days, 825)            # iPhones/Macs reject longer
        self.assertGreaterEqual((end - start).days, 700)

    def test_certificate_is_a_server_leaf_signed_by_the_ca(self):
        text = openssl_x509(self.cert, "-text")
        for needed in ("CA:FALSE", "TLS Web Server Authentication", "Digital Signature",
                       f"DNS:{HOST}", "DNS:thermostat.local", "IP Address:192.168.1.50"):
            self.assertIn(needed, text)
        self.assertIn("CA:TRUE", openssl_x509(self.ca, "-text"))
        v = subprocess.run(["openssl", "verify", "-CAfile", self.ca, self.cert], capture_output=True, text=True)
        self.assertIn("OK", v.stdout)

    def test_rerun_keeps_the_ca_and_issues_a_new_certificate(self):
        ca_before = openssl_x509(self.ca, "-fingerprint")
        serial_before = openssl_x509(self.cert, "-serial")
        self.assertEqual(make(self.pca, HOST).returncode, 0)
        self.assertEqual(openssl_x509(self.ca, "-fingerprint"), ca_before)      # phones need nothing
        self.assertNotEqual(openssl_x509(self.cert, "-serial"), serial_before)

    def test_refuses_lifetimes_phones_reject_and_missing_name(self):
        self.assertEqual(make(os.path.join(self.d, "x"), HOST, CERT_DAYS="900").returncode, 2)
        self.assertEqual(subprocess.run(["sh", SCRIPT], capture_output=True).returncode, 2)

    def test_thermostat_serves_it_and_a_client_trusting_only_the_ca_accepts_it(self):
        live = os.path.join(self.d, "live")
        os.makedirs(live); os.makedirs(os.path.join(self.d, "data"))
        shutil.copy(self.cert, os.path.join(live, "cert.pem"))
        shutil.copy(os.path.join(self.pca, "privkey.pem"), os.path.join(live, "cert.key"))
        srv = Running(self.d, tls=True)
        self.addCleanup(srv.close)

        def connect(ctx, name):
            with socket.create_connection(("127.0.0.1", srv.port), timeout=5) as s:
                with ctx.wrap_socket(s, server_hostname=name) as t:
                    t.sendall(f"GET /api/v1/session HTTP/1.0\r\nHost: {name}\r\n\r\n".encode())
                    return t.recv(4096)

        trusting = ssl.create_default_context(cafile=self.ca)
        self.assertIn(b"200 OK", connect(trusting, HOST))                         # full verification, no warnings
        self.assertIn(b"200 OK", connect(trusting, "thermostat.local"))
        self.assertIn(b"200 OK", connect(trusting, "192.168.1.50"))               # IP in the certificate too
        with self.assertRaises(ssl.SSLCertVerificationError):                     # a different name is refused
            connect(trusting, "other.example.com")
        with self.assertRaises(ssl.SSLCertVerificationError):                     # devices without the CA warn
            connect(ssl.create_default_context(), HOST)


if __name__ == "__main__":
    unittest.main()
