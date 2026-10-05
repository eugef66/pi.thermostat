"""Serves the web UI from a directory. Read-only, allow-listed file types,
no directory listings, no path escapes, ETag revalidation, strict CSP."""
from __future__ import annotations

import os

from .webapp import App, HTTPError, Response

MIME = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".webmanifest": "application/manifest+json",
    ".json": "application/json",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
}

# No inline script or style anywhere, and nothing loads from another origin.
CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; "
       "connect-src 'self'; manifest-src 'self'; base-uri 'none'; "
       "form-action 'none'; frame-ancestors 'none'")


def register(app: App, root: str, log=None) -> None:
    root = os.path.realpath(root)
    if not os.path.isdir(root):
        if log:
            log.warning("web UI directory not found: %s (API only)", root)
        return

    def serve(req, rel: str) -> Response:
        if "\0" in rel or "\\" in rel:
            raise HTTPError(404, "not_found", "not found")
        full = os.path.realpath(os.path.join(root, rel))
        ext = os.path.splitext(full)[1].lower()
        if os.path.commonpath([root, full]) != root or ext not in MIME \
                or not os.path.isfile(full):
            raise HTTPError(404, "not_found", "not found")
        st = os.stat(full)
        etag = f'"{st.st_mtime_ns:x}-{st.st_size:x}"'
        cache = "public, max-age=86400" if rel.startswith("icons/") else "no-cache"
        headers = [("ETag", etag), ("Cache-Control", cache)]
        if req.header("If-None-Match") == etag:
            return Response(304, None, headers)
        with open(full, "rb") as f:
            data = f.read()
        headers += [("Content-Type", MIME[ext]), ("Content-Security-Policy", CSP)]
        return Response(200, data, headers)

    app.route("GET", "/")(lambda req: serve(req, "index.html"))
    app.route("GET", "/manifest.webmanifest")(lambda req: serve(req, "manifest.webmanifest"))
    app.route("GET", "/static/(?P<rel>.+)")(lambda req, rel: serve(req, rel))
