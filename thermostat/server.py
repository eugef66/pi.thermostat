"""HTTPS server: Cheroot (production) or a threaded stdlib server (dev/test).

Besides serving the API it runs two small background loops:
  * the dead-man watchdog (relays off if cron has stopped), and
  * the certificate watcher, which loads a renewed Let's Encrypt certificate
    into the live TLS context without a restart.

Stopping the server does NOT touch the relays: cron keeps controlling them.
"""
from __future__ import annotations

import os
import signal
import ssl
import threading
import time
from socketserver import ThreadingMixIn
from wsgiref.simple_server import WSGIRequestHandler, WSGIServer, make_server

from . import api, engine
from .auth import Auth
from .config import Config
from .hardware import open_hardware
from .state import StateStore

CERT_SETTLE_S = 2.0   # ignore files modified this recently (still being copied)


class CertReloader:
    """Reloads cert + key into an existing SSLContext when the files change."""

    def __init__(self, context: ssl.SSLContext, cert: str, key: str, log):
        self.ctx, self.cert, self.key, self.log = context, cert, key, log
        self.sig = self._sig()

    def _sig(self):
        try:
            return tuple((os.stat(p).st_mtime_ns, os.stat(p).st_size)
                         for p in (self.cert, self.key))
        except OSError:
            return None

    def check(self, now=None) -> bool:
        """True if a new certificate was loaded."""
        now = time.time() if now is None else now
        sig = self._sig()
        if sig is None or sig == self.sig:
            return False
        newest = max(os.stat(p).st_mtime for p in (self.cert, self.key))
        if now - newest < CERT_SETTLE_S:
            return False                      # wait until the copy is finished
        self.sig = sig                        # don't retry the same bad files forever
        try:
            self.ctx.load_cert_chain(self.cert, self.key)
        except (ssl.SSLError, OSError) as e:
            self.log.error("new certificate rejected, keeping the old one: %s", e)
            return False
        self.log.info("TLS certificate reloaded")
        return True


def make_context(cert: str, key: str) -> ssl.SSLContext:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(cert, key)
    return ctx


# ---------------------------------------------------------------- runners

class _QuietHandler(WSGIRequestHandler):
    def log_message(self, *a):
        pass


class _Threaded(ThreadingMixIn, WSGIServer):
    daemon_threads = True


class WsgirefRunner:
    """Dev/test only: no connection limits or slow-client protection."""

    def __init__(self, app, host, port, timeout, cert, key, log):
        self.app, self.host, self.req_port, self.timeout = app, host, port, timeout
        self.cert, self.key, self.log = cert, key, log
        self.context = None
        self.httpd = None

    def start(self):
        self.httpd = make_server(self.host, self.req_port, self.app,
                                 server_class=_Threaded, handler_class=_QuietHandler)
        self.httpd.timeout = self.timeout
        if self.cert:
            self.context = make_context(self.cert, self.key)
            self.httpd.socket = self.context.wrap_socket(self.httpd.socket, server_side=True)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    @property
    def port(self):
        return self.httpd.server_address[1]

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()


class CherootRunner:
    def __init__(self, app, host, port, threads, timeout, cert, key, log):
        from cheroot.wsgi import Server
        self.srv = Server((host, port), app, numthreads=threads, timeout=timeout,
                          server_name="thermostat")
        self.context = None
        if cert:
            from cheroot.ssl.builtin import BuiltinSSLAdapter
            adapter = BuiltinSSLAdapter(cert, key)
            ctx = getattr(adapter, "context", None)
            if ctx is None:
                raise RuntimeError("this Cheroot version has no adapter.context; "
                                   "certificate reload is not possible")
            ctx.minimum_version = ssl.TLSVersion.TLSv1_2
            self.srv.ssl_adapter = adapter
            self.context = ctx

    def start(self):
        self.srv.prepare()
        threading.Thread(target=self.srv.serve, daemon=True).start()

    @property
    def port(self):
        return self.srv.bind_addr[1]

    def stop(self):
        self.srv.stop()


# -------------------------------------------------------------------- run

def _loop(stop: threading.Event, interval: float, fn, log, what: str):
    while not stop.wait(interval):
        try:
            fn()
        except Exception:
            log.exception("%s failed", what)


def serve(cfg: Config, log, stop: threading.Event = None, on_ready=None) -> int:
    sv = cfg.server
    own_stop = stop is None
    stop = stop or threading.Event()

    cert = key = None
    if sv.tls:
        cert, key = sv.cert_file, sv.key_file
        for p in (cert, key):
            if not os.path.isfile(p):
                log.error("TLS file not found: %s", p)
                return 5
        if os.stat(key).st_mode & 0o077:
            log.warning("private key %s is readable by other users; chmod 600 it", key)

    store = StateStore(cfg.paths.state_file, cfg.paths.lock_file, cfg.control.default_target)
    hw = open_hardware(cfg)
    auth = Auth(cfg, log)
    if not auth.configured:
        log.warning("no PIN configured; run `set-pin` before logging in")
    app = api.create_app(cfg, store, hw, log, auth)

    if sv.engine == "cheroot":
        runner = CherootRunner(app, sv.host, sv.port, sv.threads, sv.timeout, cert, key, log)
    else:
        runner = WsgirefRunner(app, sv.host, sv.port, sv.timeout, cert, key, log)
    runner.start()
    log.info("server started on %s:%s (%s, %s)", sv.host, runner.port,
             "https" if sv.tls else "http", sv.engine)

    threads = [threading.Thread(target=_loop, daemon=True, args=(
        stop, sv.watchdog_interval_s,
        lambda: engine.watchdog_tick(cfg, store, hw, log), log, "watchdog"))]
    if sv.tls:
        reloader = CertReloader(runner.context, cert, key, log)
        threads.append(threading.Thread(target=_loop, daemon=True, args=(
            stop, sv.cert_check_s, reloader.check, log, "certificate check")))
    for t in threads:
        t.start()

    if own_stop and threading.current_thread() is threading.main_thread():
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, lambda *_: stop.set())
    if on_ready:
        on_ready(runner.port)
    stop.wait()
    log.info("server stopping")
    runner.stop()
    return 0
