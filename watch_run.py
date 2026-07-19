#!/usr/bin/env python3
"""Local viewer server for the agent activity stream (walkrec prototype).

    python3 watch_run.py <run-id> [--port 3040]

Serves:
  /                      -> viewer.html?run=<run-id> (redirect)
  /viewer.html           -> the feed UI
  /events/<run-id>?after=N -> JSON events with seq > N (long-poll-free; the
                             page polls at 1Hz)
  /runs/...              -> run artifacts (page shots, clips, the film)

Read-only, binds 127.0.0.1 only. Part of the "agent always gives updates"
contract: this is the render surface for runs/<id>/events.jsonl.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import run_events  # noqa: E402
import director  # noqa: E402


class Handler(BaseHTTPRequestHandler):
    run_id = ""

    def log_message(self, *a):  # quiet
        pass

    def _send(self, code, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path.startswith("/chat/"):
            rid = os.path.basename(parsed.path)
            try:
                n = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(n) or b"{}")
                res = director.handle(rid, str(body.get("message", ""))[:2000])
            except Exception as e:
                res = {"reply": f"Director error: {type(e).__name__}",
                       "working": False}
            self._send(200, json.dumps(res).encode(), "application/json")
            return
        self._send(404, b"not found", "text/plain")

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if path == "/":
            self.send_response(302)
            self.send_header("Location", f"/viewer.html?run={self.run_id}")
            self.end_headers()
            return
        if path == "/viewer.html":
            with open(os.path.join(HERE, "viewer.html"), "rb") as f:
                self._send(200, f.read(), "text/html; charset=utf-8")
            return
        if path.startswith("/events/"):
            rid = os.path.basename(path)
            after = int(urllib.parse.parse_qs(parsed.query)
                        .get("after", ["-1"])[0])
            evts = run_events.read_events(os.path.join(HERE, "runs", rid),
                                          after=after)
            self._send(200, json.dumps(evts).encode(), "application/json")
            return
        if path.startswith("/chat/"):
            rid = os.path.basename(path)
            out = []
            try:
                with open(os.path.join(HERE, "runs", rid, "chat.jsonl")) as f:
                    out = [json.loads(l) for l in f]
            except Exception:
                pass
            self._send(200, json.dumps(out).encode(), "application/json")
            return
        if path.startswith("/live/"):
            rid = os.path.basename(path)
            frame = os.path.join(HERE, "runs", rid, "live", "current.jpg")
            try:
                import time as _t
                if os.path.exists(frame) and _t.time() - os.path.getmtime(frame) < 3.0:
                    with open(frame, "rb") as f:
                        self._send(200, f.read(), "image/jpeg")
                    return
            except Exception:
                pass
            self._send(404, b"stale", "text/plain")
            return
        # Artifacts: repo-relative under runs/ only.
        rel = urllib.parse.unquote(path.lstrip("/"))
        full = os.path.realpath(os.path.join(HERE, rel))
        if (full.startswith(os.path.realpath(os.path.join(HERE, "runs")))
                and os.path.isfile(full)):
            ctype = ("video/mp4" if full.endswith(".mp4")
                     else "image/png" if full.endswith(".png")
                     else "image/jpeg" if full.endswith((".jpg", ".jpeg"))
                     else "application/octet-stream")
            with open(full, "rb") as f:
                self._send(200, f.read(), ctype)
            return
        self._send(404, b"not found", "text/plain")


def main(argv):
    rid = argv[1] if len(argv) > 1 else ""
    port = int(argv[argv.index("--port") + 1]) if "--port" in argv else 3040
    Handler.run_id = rid
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"[watch] http://localhost:{port}/viewer.html?run={rid}")
    srv.serve_forever()


if __name__ == "__main__":
    main(sys.argv)
