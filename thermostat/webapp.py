"""Tiny WSGI toolkit (no dependencies): routing, JSON in/out, error bodies.
Any WSGI server can host the resulting app (Cheroot in Stage 4)."""
from __future__ import annotations

import json
import re
from http import HTTPStatus
from http.cookies import SimpleCookie

SECURITY_HEADERS = [
    ("X-Content-Type-Options", "nosniff"),
    ("X-Frame-Options", "DENY"),
    ("Referrer-Policy", "no-referrer"),
]


class HTTPError(Exception):
    def __init__(self, status: int, code: str, message: str, headers=None):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message
        self.headers = headers or []


class Request:
    def __init__(self, environ, max_body: int):
        self.environ, self.max_body = environ, max_body
        self.method = environ["REQUEST_METHOD"].upper()
        self.path = environ.get("PATH_INFO", "/")
        self.ip = environ.get("REMOTE_ADDR", "?")
        self._cookies = None

    def header(self, name: str):
        return self.environ.get("HTTP_" + name.upper().replace("-", "_"))

    @property
    def cookies(self) -> dict:
        if self._cookies is None:
            jar = SimpleCookie()
            try:
                jar.load(self.environ.get("HTTP_COOKIE", ""))
            except Exception:
                pass
            self._cookies = {k: m.value for k, m in jar.items()}
        return self._cookies

    def json(self) -> dict:
        ctype = (self.environ.get("CONTENT_TYPE") or "").split(";")[0].strip().lower()
        if ctype != "application/json":
            raise HTTPError(415, "unsupported_media_type", "Content-Type must be application/json")
        try:
            length = int(self.environ.get("CONTENT_LENGTH") or 0)
        except ValueError:
            raise HTTPError(400, "bad_request", "invalid Content-Length")
        if length > self.max_body:
            raise HTTPError(413, "body_too_large", "request body too large")
        raw = self.environ["wsgi.input"].read(length) if length else b""
        try:
            data = json.loads(raw.decode() or "{}")
        except (ValueError, UnicodeDecodeError):
            raise HTTPError(400, "bad_json", "body is not valid JSON")
        if not isinstance(data, dict):
            raise HTTPError(400, "bad_json", "body must be a JSON object")
        return data


class Response:
    def __init__(self, status=200, body=None, headers=None):
        self.status, self.body, self.headers = status, body, list(headers or [])


def error_body(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message}}


class App:
    def __init__(self, max_body: int = 4096, secure: bool = True, log=None):
        self.routes, self.max_body, self.secure, self.log = [], max_body, secure, log

    def route(self, method: str, pattern: str):
        rx = re.compile("^" + pattern + "$")

        def deco(fn):
            self.routes.append((method, rx, fn))
            return fn
        return deco

    def _dispatch(self, req: Request) -> Response:
        allowed = []
        for method, rx, fn in self.routes:
            m = rx.match(req.path)
            if not m:
                continue
            if method != req.method and not (req.method == "HEAD" and method == "GET"):
                allowed.append(method)
                continue
            out = fn(req, **m.groupdict())
            if isinstance(out, Response):
                return out
            return Response(200, out)
        if allowed:
            raise HTTPError(405, "method_not_allowed", "method not allowed",
                            [("Allow", ", ".join(sorted(set(allowed))))])
        raise HTTPError(404, "not_found", "not found")

    def __call__(self, environ, start_response):
        req = Request(environ, self.max_body)
        try:
            resp = self._dispatch(req)
        except HTTPError as e:
            resp = Response(e.status, error_body(e.code, e.message), e.headers)
        except Exception:
            if self.log:
                self.log.exception("unhandled error on %s %s", req.method, req.path)
            resp = Response(500, error_body("internal_error", "internal error"))

        headers = list(SECURITY_HEADERS) + resp.headers
        if self.secure:
            headers.append(("Strict-Transport-Security", "max-age=31536000"))
        if resp.body is None:
            payload = b""
        elif isinstance(resp.body, (bytes, bytearray)):
            payload = bytes(resp.body)
        else:
            payload = json.dumps(resp.body).encode()
            headers.append(("Content-Type", "application/json"))
        if req.path.startswith("/api/"):
            headers.append(("Cache-Control", "no-store"))
        headers.append(("Content-Length", str(len(payload))))
        phrase = HTTPStatus(resp.status).phrase
        start_response(f"{resp.status} {phrase}", headers)
        return [payload] if req.method != "HEAD" else [b""]
