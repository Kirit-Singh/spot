#!/usr/bin/env python3
"""Hardened static server for the spot public distribution.

Serves ONLY the allowlisted distribution directory (``SPOT_DIST``) over GET/HEAD.
There are NO mutation endpoints, NO shell/SSH execution, and NO filesystem writes.
Source files, scripts, dotfiles, logs and any non-allowlisted extension are refused
with 404 as defense in depth — the distribution should contain none of them.

This replaces the previous serve.py, which exposed repository source and an
unauthenticated POST /rerun mutation endpoint.
"""
import os, re, sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

DIST = os.environ.get("SPOT_DIST", "/home/tcelab/spot-dist")
PORT = int(os.environ.get("SPOT_PORT", "8347"))
# Only these content extensions may be served; everything else 404s.
ALLOW_EXT = {".html", ".css", ".js", ".json", ".svg", ".png", ".ico", ".woff2", ".webp", ".map", ".txt"}
# Explicit denylist (belt-and-suspenders): dotfiles, pycache, source/scripts/logs/configs.
DENY = re.compile(r"(^|/)\.|/__pycache__/|\.(py|sh|log|md|env|ini|cfg|pem|key|lock|toml|ya?ml|sql)$", re.I)


class H(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=DIST, **k)

    def _forbidden(self):
        p = self.path.split("?", 1)[0]
        if DENY.search(p):
            return True
        base = os.path.basename(p)
        if base and "." in base and os.path.splitext(base)[1].lower() not in ALLOW_EXT:
            return True
        return False

    def do_GET(self):
        if self._forbidden():
            return self.send_error(404)
        super().do_GET()

    def do_HEAD(self):
        if self._forbidden():
            return self.send_error(404)
        super().do_HEAD()

    def do_POST(self):
        self.send_error(405)

    def do_PUT(self):
        self.send_error(405)

    def do_DELETE(self):
        self.send_error(405)

    def do_PATCH(self):
        self.send_error(405)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    if not os.path.isdir(DIST):
        sys.exit("dist dir not found: " + DIST)
    ThreadingHTTPServer.allow_reuse_address = True
    print("spot static server on :%d (GET/HEAD only, dist=%s)" % (PORT, DIST))
    ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
