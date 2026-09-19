"""Vercel serverless entry point.

Vercel's Python runtime wants a BaseHTTPRequestHandler subclass named
``handler``.  VocalForge's local server is already built on one, so this
re-uses it and only changes what has to change for a stateless function:

* audio is returned inline in the render response rather than cached and
  fetched on a second request, which would land on a different instance
* preset writes are refused; the browser keeps user presets in localStorage
* the route arrives via a ``route`` query parameter, because vercel.json
  rewrites every /api/* path onto this one file
"""
from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from vocalforge import server as vf  # noqa: E402

vf.STATELESS = True


class handler(vf.Handler):
    def _route(self) -> str:
        u = urlparse(self.path)
        q = parse_qs(u.query)
        r = (q.get("route") or [None])[0]
        if r:
            rest = {k: v[0] for k, v in q.items() if k != "route"}
            query = urlencode(rest)
            return "/api/" + r.lstrip("/") + (f"?{query}" if query else "")
        return self.path

    def do_GET(self):
        self.path = self._route()
        return super().do_GET()

    def do_POST(self):
        self.path = self._route()
        return super().do_POST()

    def log_message(self, fmt, *args):
        pass
