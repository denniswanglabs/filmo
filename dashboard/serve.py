#!/usr/bin/env python3
"""Tiny stdlib-only static server for the Hermes producer-brain dashboard.

Serves the PROJECT ROOT so the browser can fetch both /dashboard/* and
/runs/* (ledgers + final.mp4).

NOTE: Python's SimpleHTTPRequestHandler does NOT implement HTTP Range
requests (verified against the installed interpreter), and Safari refuses
to seek — or sometimes to play at all — a video served without them. So
this handler implements Range itself: byte-range GET/HEAD return 206
Partial Content with Content-Range, and every response advertises
Accept-Ranges: bytes. Still stdlib-only, no build step, no dependencies.

Usage (from anywhere):
    python3 dashboard/serve.py

Then open http://localhost:3030 in Safari.
"""

import http.server
import json
import os
import re
import shlex
import shutil
import socketserver
import subprocess
import sys
import uuid

PORT = 3030
PROJECT_ROOT = os.path.dirname(os.path.abspath(os.path.dirname(__file__)))
RUNS_DIR = os.path.join(PROJECT_ROOT, "runs")

# User-facing output styles accepted from the dashboard pill (carried in the POST
# body's `pace` field). Anything else falls back to "standard" (today's default).
_STYLES = ("snappy", "standard", "cinematic")

_RANGE_RE = re.compile(r"^bytes=(\d*)-(\d*)$")
# A run id is the folder name. Allow ONLY these chars — no path separators, no
# dots-runs, no spaces. Matched against the WHOLE string (fullmatch).
_RUN_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def _slug(url):
    u = (url or "").lower().replace("https://", "").replace("http://", "").replace("www.", "")
    host = u.split("/")[0].split(".")
    name = host[-2] if len(host) >= 2 else (host[0] if host else "site")
    return re.sub(r"[^a-z0-9]", "", name)[:16] or "site"


def safe_run_dir(run_id):
    """Resolve `runs/<run_id>` ONLY if `run_id` is a safe, contained folder name.

    Returns the absolute run directory path, or raises ValueError. Defends
    against path traversal flagged in the production-readiness review:
      * reject empty / non-string ids
      * reject anything outside the [A-Za-z0-9._-] character class (so '/',
        '\\', spaces, null bytes, etc. are all out)
      * reject '.', '..', and any id containing a '..' segment explicitly
      * after resolving symlinks, REQUIRE the path to live directly inside the
        runs dir (its parent must BE the runs dir) — a final belt-and-braces
        check that the resolved target can't escape.
    """
    if not isinstance(run_id, str):
        raise ValueError("run id must be a string")
    run_id = run_id.strip()
    if not run_id or run_id in (".", ".."):
        raise ValueError("empty or relative run id")
    if ".." in run_id:
        raise ValueError("'..' not allowed in run id")
    if not _RUN_ID_RE.fullmatch(run_id):
        raise ValueError("run id has illegal characters")
    runs_real = os.path.realpath(RUNS_DIR)
    candidate = os.path.realpath(os.path.join(runs_real, run_id))
    # The resolved candidate must sit DIRECTLY inside the runs dir.
    if os.path.dirname(candidate) != runs_real:
        raise ValueError("resolved path escapes the runs dir")
    if candidate == runs_real:
        raise ValueError("refusing to target the runs dir itself")
    return candidate


def rebuild_runs_index():
    """Regenerate runs/index.json from the surviving ledgers (used after a delete).

    Mirrors the index shape in LEDGER.md. Skips dirs without a ledger and any
    ledger that won't parse. Sort newest-first by created_at when present, else
    by folder name, so the rail order stays stable.
    """
    rows = []
    try:
        names = os.listdir(RUNS_DIR)
    except OSError:
        names = []
    for name in sorted(names):
        p = os.path.join(RUNS_DIR, name, "ledger.json")
        if not os.path.exists(p):
            continue
        try:
            with open(p) as fh:
                d = json.load(fh)
        except (OSError, ValueError):
            continue
        pnl = d.get("pnl") or {}
        rows.append({
            "run_id": d.get("run_id", name),
            "mode": d.get("mode"),
            "status": d.get("status"),
            "created_at": d.get("created_at"),
            "goal": (d.get("job") or {}).get("goal"),
            "company_url": (d.get("job") or {}).get("company_url"),
            "price_cents": pnl.get("price_cents"),
            "cogs_spent_cents": pnl.get("cogs_spent_cents"),
            "margin": pnl.get("margin"),
            "overage_avoided_cents": pnl.get("overage_avoided_cents"),
            "declines": len(pnl.get("declines") or []),
        })
    rows.sort(key=lambda r: (r.get("created_at") or "", r.get("run_id") or ""), reverse=True)
    with open(os.path.join(RUNS_DIR, "index.json"), "w") as fh:
        json.dump({"runs": rows}, fh, indent=2)
    return rows


class Handler(http.server.SimpleHTTPRequestHandler):
    """Serves the project root with Range support so the MP4 <video> seeks.

    GET / redirects to the dashboard index. HTTP/1.1 is used so responses
    carry a Content-Length and the browser can keep the connection alive
    while streaming the video.
    """

    protocol_version = "HTTP/1.1"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=PROJECT_ROOT, **kwargs)

    def do_GET(self):
        if self.path.startswith("/api/"):
            return self._api_get()
        if self._redirect_root():
            return
        f = self.send_head()
        if f:
            try:
                self.copyfile(f, self.wfile)
            finally:
                f.close()

    def do_HEAD(self):
        if self._redirect_root():
            return
        f = self.send_head()
        if f:
            f.close()

    def do_POST(self):
        if self.path == "/api/build":
            return self._api_build()
        if self.path == "/api/delete":
            return self._api_delete()
        self._json(404, {"error": "unknown endpoint"})

    # ---- live-build API ---------------------------------------------------
    def _api_get(self):
        if self.path.startswith("/api/active"):
            return self._api_active()
        if self.path.startswith("/api/analytics"):
            return self._api_analytics()
        self._json(404, {"error": "unknown api"})

    def _api_analytics(self):
        """READ-ONLY operator analytics: aggregate every runs/*/ledger.json into
        the P&L rollup the Analytics tab consumes. Delegates to analytics.summarize()
        (PROJECT_ROOT is on sys.path). Import is lazy so a problem in analytics.py
        can never stop the server from booting; any failure becomes a 500, not a crash.
        """
        try:
            if PROJECT_ROOT not in sys.path:
                sys.path.insert(0, PROJECT_ROOT)
            import analytics
            self._json(200, analytics.summarize())
        except Exception as e:  # noqa: BLE001 - never let one bad ledger 500 the rest
            self._json(500, {"error": "analytics failed: %s" % e})

    def _api_active(self):
        runs_dir = os.path.join(PROJECT_ROOT, "runs")
        active = []
        try:
            names = sorted(os.listdir(runs_dir))
        except OSError:
            names = []
        for name in names:
            p = os.path.join(runs_dir, name, "ledger.json")
            if not os.path.exists(p):
                continue
            try:
                with open(p) as fh:
                    d = json.load(fh)
            except (OSError, ValueError):
                continue
            if d.get("status") == "running":
                active.append({"run_id": d.get("run_id"), "phase": d.get("phase")})
        self._json(200, {"active": active})

    def _api_build(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            return self._json(400, {"error": "bad JSON body"})
        url = (body.get("url") or "").strip()
        if not url:
            return self._json(400, {"error": "url required"})
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        goal = (body.get("goal") or "").strip() or "30-second brand promo"
        mode = "real" if body.get("mode") == "real" else "mock"
        duration = int(body.get("duration") or 30)
        # The dashboard's Snappy/Standard/Cinematic pill arrives in the `pace` field
        # (see app.js). Read it as the user-facing STYLE and thread it to the build
        # runner as --style so the three pills produce genuinely different videos.
        # Anything unrecognized falls back to the historical default ("standard").
        style = str(body.get("pace") or "standard").strip().lower()
        if style not in _STYLES:
            style = "standard"
        # QUALITY — the upfront customer choice (standard | premium). Read either
        # from a top-level `quality` field or from selection.quality (app.js sends
        # both). Standard = Remotion + edge-tts (no Higgsfield/ElevenLabs); premium
        # = cinematic Higgsfield + ElevenLabs VO. Threaded to the build runner as
        # --quality so the plan is priced AND produced for the chosen tier.
        selection = body.get("selection") or {}
        quality = str(body.get("quality") or selection.get("quality") or "standard").strip().lower()
        if quality not in ("standard", "premium"):
            quality = "standard"
        run_id = "build-%s-%s" % (_slug(url), uuid.uuid4().hex[:6])
        run_dir = os.path.join(PROJECT_ROOT, "runs", run_id)
        os.makedirs(run_dir, exist_ok=True)
        logf = open(os.path.join(run_dir, "build.log"), "w")
        # zsh -lc sources ~/.zshrc so the Nemotron planner sees NVIDIA_API_KEY.
        inner = ("cd %s && python3 build_runner.py --url %s --goal %s --run-id %s "
                 "--mode %s --duration %d --style %s --quality %s"
                 % (shlex.quote(PROJECT_ROOT), shlex.quote(url), shlex.quote(goal),
                    shlex.quote(run_id), mode, duration, shlex.quote(style),
                    shlex.quote(quality)))
        subprocess.Popen(["zsh", "-lc", inner], stdout=logf, stderr=subprocess.STDOUT,
                         cwd=PROJECT_ROOT, start_new_session=True)
        self._json(200, {"run_id": run_id, "mode": mode, "quality": quality})

    def _api_delete(self):
        """Delete one run folder, then regenerate runs/index.json.

        Body: {"id": "<run_id>"}. The id is sanitized HARD via safe_run_dir()
        before ANY filesystem touch — deletion is strictly confined to a single
        folder directly inside runs/. Path-traversal attempts (../, /etc, absolute
        paths, separators) are rejected with 400 and never reach shutil.rmtree.
        """
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            return self._json(400, {"error": "bad JSON body"})
        run_id = body.get("id")
        try:
            target = safe_run_dir(run_id)
        except ValueError as e:
            return self._json(400, {"error": "invalid run id: %s" % e})
        if not os.path.isdir(target):
            return self._json(404, {"error": "run not found"})
        try:
            shutil.rmtree(target)
        except OSError as e:
            return self._json(500, {"error": "delete failed: %s" % e})
        runs = rebuild_runs_index()
        self._json(200, {"deleted": run_id, "runs": runs})

    def _json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _redirect_root(self):
        # Match the root path IGNORING any query string. The Stripe Checkout
        # return lands on "/?paid=<id>" (or "/?cancelled=<id>"); without splitting
        # off the query first this fell through to a bare directory listing. Carry
        # the query through to the dashboard so app.js can act on ?paid / ?cancelled.
        path, sep, query = self.path.partition("?")
        if path in ("/", "/index.html", ""):
            location = "/dashboard/index.html" + (sep + query if query else "")
            self.send_response(302)
            self.send_header("Location", location)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return True
        return False

    # ---- Range-aware send_head -------------------------------------------
    def send_head(self):
        path = self.translate_path(self.path)

        # Let the parent handle directories (listings / index redirects).
        if os.path.isdir(path):
            return super().send_head()

        try:
            f = open(path, "rb")
        except OSError:
            self.send_error(404, "File not found")
            return None

        try:
            fs = os.fstat(f.fileno())
            file_len = fs[6]
            ctype = self.guess_type(path)

            range_header = self.headers.get("Range")
            rng = self._parse_range(range_header, file_len) if range_header else None

            if rng is None:
                # Full content.
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(file_len))
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Last-Modified", self.date_time_string(fs.st_mtime))
                self.end_headers()
                return f

            # Partial content.
            start, end = rng
            length = end - start + 1
            f.seek(start)
            self.send_response(206)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(length))
            self.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, file_len))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Last-Modified", self.date_time_string(fs.st_mtime))
            self.end_headers()
            return _RangeReader(f, length)
        except Exception:
            f.close()
            raise

    def _parse_range(self, header, file_len):
        """Return (start, end) inclusive, or None for full content.

        Sends a 416 and returns None for an unsatisfiable range.
        """
        m = _RANGE_RE.match((header or "").strip())
        if not m or file_len == 0:
            return None
        g1, g2 = m.group(1), m.group(2)
        if g1 == "" and g2 == "":
            return None
        if g1 == "":
            # suffix: last N bytes
            n = int(g2)
            if n == 0:
                self._send_416(file_len)
                return None
            start = max(0, file_len - n)
            end = file_len - 1
        else:
            start = int(g1)
            end = int(g2) if g2 != "" else file_len - 1
            if end >= file_len:
                end = file_len - 1
            if start > end or start >= file_len:
                self._send_416(file_len)
                return None
        return (start, end)

    def _send_416(self, file_len):
        self.send_response(416, "Requested Range Not Satisfiable")
        self.send_header("Content-Range", "bytes */%d" % file_len)
        self.send_header("Content-Length", "0")
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()

    def end_headers(self):
        # No-cache so a Refresh always pulls fresh ledgers during live runs.
        self.send_header("Cache-Control", "no-store, must-revalidate")
        super().end_headers()

    def log_message(self, fmt, *args):
        sys.stderr.write("  %s\n" % (fmt % args))


class _RangeReader:
    """Wraps an open file so copyfile() reads at most `length` bytes."""

    def __init__(self, fileobj, length):
        self._f = fileobj
        self._remaining = length

    def read(self, n=-1):
        if self._remaining <= 0:
            return b""
        if n is None or n < 0 or n > self._remaining:
            n = self._remaining
        data = self._f.read(n)
        self._remaining -= len(data)
        return data

    def close(self):
        self._f.close()


class ThreadingServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    """Threaded so streaming the video doesn't block dashboard JSON fetches."""

    daemon_threads = True
    allow_reuse_address = True


def main():
    os.chdir(PROJECT_ROOT)
    with ThreadingServer(("127.0.0.1", PORT), Handler) as httpd:
        url = "http://localhost:%d/" % PORT
        print("Hermes dashboard serving %s" % PROJECT_ROOT)
        print("  Open  ->  %s" % url)
        print("  (Ctrl-C to stop)")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nStopped.")


if __name__ == "__main__":
    main()
