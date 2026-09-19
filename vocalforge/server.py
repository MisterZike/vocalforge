"""Local web UI.

Uses only the standard library's HTTP server, so the whole app still needs
nothing beyond numpy and scipy.  Binds to localhost by default.
"""
from __future__ import annotations

import io
import json
import threading
import time
import traceback
import uuid
import webbrowser
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import numpy as np

from . import audio, g2p, macros, params, presets, render

WEB = Path(__file__).resolve().parent.parent / "web"
MAX_CACHED = 24
_cache: OrderedDict[str, tuple[bytes, float]] = OrderedDict()
_lock = threading.Lock()

MIME = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
        ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml",
        ".ico": "image/x-icon", ".json": "application/json"}


def _store(wav: bytes) -> str:
    key = uuid.uuid4().hex[:16]
    with _lock:
        _cache[key] = (wav, time.time())
        while len(_cache) > MAX_CACHED:
            _cache.popitem(last=False)
    return key


class Handler(BaseHTTPRequestHandler):
    server_version = "VocalForge"

    def log_message(self, fmt, *args):       # quieter console
        if "/api/render" in str(args):
            return

    # ---------------------------------------------------------------- utils
    def _send(self, code: int, body: bytes, ctype: str, extra: dict | None = None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json(self, obj, code: int = 200):
        self._send(code, json.dumps(obj).encode(), "application/json")

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode() or "{}")
        except json.JSONDecodeError:
            return {}

    # ------------------------------------------------------------------ GET
    def do_GET(self):
        u = urlparse(self.path)
        path, q = u.path, parse_qs(u.query)
        try:
            if path in ("/", "/index.html"):
                return self._file("index.html")
            if path.startswith("/api/"):
                return self._api_get(path, q)
            if path.startswith("/audio/"):
                key = path[len("/audio/"):].split(".")[0]
                with _lock:
                    hit = _cache.get(key)
                if not hit:
                    return self._json({"error": "expired"}, 404)
                return self._send(200, hit[0], "audio/wav",
                                  {"Content-Disposition":
                                   f'inline; filename="vocalforge-{key}.wav"'})
            name = path.lstrip("/")
            if "/" in name or ".." in name:
                return self._json({"error": "not found"}, 404)
            return self._file(name)
        except Exception:
            traceback.print_exc()
            self._json({"error": "internal error"}, 500)

    def _file(self, name: str):
        f = WEB / name
        if not f.is_file():
            return self._json({"error": "not found"}, 404)
        return self._send(200, f.read_bytes(),
                          MIME.get(f.suffix, "application/octet-stream"))

    def _api_get(self, path: str, q: dict):
        if path == "/api/schema":
            return self._json({"schema": params.describe(),
                               "groups": params.GROUPS,
                               "defaults": params.defaults()})
        if path == "/api/macros":
            return self._json({"macros": macros.describe()})
        if path == "/api/presets":
            return self._json({"presets": presets.list_presets()})
        if path == "/api/phonemes":
            text = (q.get("text") or [""])[0]
            words = g2p.text_to_phones(text, (q.get("espeak") or ["0"])[0] == "1")
            return self._json({"words": words,
                               "flat": " ".join(" ".join(w) for w in words)})
        return self._json({"error": "unknown endpoint"}, 404)

    # ----------------------------------------------------------------- POST
    def do_POST(self):
        u = urlparse(self.path)
        try:
            body = self._body()
            if u.path == "/api/render":
                return self._render(body)
            if u.path == "/api/align":
                # no audio -- runs on every edit in the melody editor
                return self._json(render.align(
                    str(body.get("text") or "hello world"),
                    body.get("params") or {}))
            if u.path == "/api/preset":
                name = str(body.get("name", "")).strip()
                if not name:
                    return self._json({"error": "a name is required"}, 400)
                path = presets.save(name, body.get("params") or {},
                                    str(body.get("description", "")),
                                    str(body.get("text", "")),
                                    macro_values=body.get("macros") or None)
                return self._json({"ok": True, "path": str(path),
                                   "id": presets.slugify(name),
                                   "presets": presets.list_presets()})
            if u.path == "/api/preset/delete":
                ok = presets.delete(str(body.get("name", "")))
                return self._json({"ok": ok, "presets": presets.list_presets()})
            return self._json({"error": "unknown endpoint"}, 404)
        except Exception as exc:
            traceback.print_exc()
            self._json({"error": f"{type(exc).__name__}: {exc}"}, 500)

    def _render(self, body: dict):
        text = str(body.get("text") or "hello world")
        p = params.normalize_params(body.get("params") or {})
        t0 = time.time()
        x, sr, info = render.render(text, p)
        buf = io.BytesIO()
        tmp = Path(f"/tmp/.vf-{uuid.uuid4().hex[:8]}.wav")
        try:
            audio.write_wav(tmp, x, sr, int(p["render.bits"]))
            wav = tmp.read_bytes()
        finally:
            tmp.unlink(missing_ok=True)
        key = _store(wav)
        info["waveform"] = render.waveform_preview(x)
        info["bytes"] = len(wav)
        info["total_time"] = round(time.time() - t0, 3)
        info["url"] = f"/audio/{key}.wav"
        return self._json(info)


def serve(host: str = "127.0.0.1", port: int = 8765, open_browser: bool = True):
    srv = ThreadingHTTPServer((host, port), Handler)
    url = f"http://{host}:{port}/"
    print(f"\n  VocalForge UI  ->  {url}")
    print("  Ctrl-C to stop\n")
    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n  stopped")
    finally:
        srv.server_close()
