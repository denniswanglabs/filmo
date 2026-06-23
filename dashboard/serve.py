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
import signal
import socketserver
import subprocess
import sys
import time
import uuid
from urllib.parse import parse_qs, urlparse

PORT = 3030
PROJECT_ROOT = os.path.dirname(os.path.abspath(os.path.dirname(__file__)))
RUNS_DIR = os.path.join(PROJECT_ROOT, "runs")
STUDIO_DIR = os.path.join(PROJECT_ROOT, "studio")
# The folded in-browser video editor. Built by `cd studio/editor && npm run build`
# (Vite, base "/editor/") into this dist dir. The dashboard serves it at /editor/
# so the whole product is ONE app on :3030 — no separate :3040 process.
EDITOR_DIST = os.path.join(STUDIO_DIR, "editor", "dist")

# User-facing output styles accepted from the dashboard pill (carried in the POST
# body's `pace` field). Anything else falls back to "standard" (today's default).
_STYLES = ("snappy", "standard", "cinematic")

# OPERATOR planner-BRAIN keys accepted from the dashboard's operator control
# (carried in the POST body's `brain` field). All three route through OpenRouter;
# anything else falls back to the free Super default ($0). Sourced from brain.py so
# the slug registry stays the single source of truth.
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
try:
    import brain as _brain
    _BRAINS = _brain.VALID_BRAINS
    _DEFAULT_BRAIN = _brain.DEFAULT_BRAIN
except Exception:  # never let a brain import problem stop the server from booting
    _BRAINS = ("ultra-paid", "super-free", "super-paid")
    _DEFAULT_BRAIN = "super-free"

# A run only counts as "active" if its ledger says status=="running" AND it shows
# recent liveness. A live build_runner.py rewrites build.log (and ledger.json) every
# few seconds; a dead one leaves them frozen. If the newest of build.log/ledger.json
# is older than this window, the run is an orphaned corpse (its process died without
# finalizing the ledger) and is NOT reported as active — so a reload lands on the home
# composer, not a forever-spinning "BUILDING…" view for a build that will never finish.
# 180s is generous: it survives a slow render/stitch phase (which still touches files
# well inside the window) while excluding anything minutes-to-days old.
_ACTIVE_FRESHNESS_SECS = 180

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


def _editor_render_cmd(abs_props, abs_out):
    """The editor's re-render command, mirroring build_runner.py exactly (cwd=studio,
    `remotion` resolved off studio/node_modules/.bin). Kept byte-identical to the
    production render so an edited.mp4 matches what the pipeline would have produced.
    """
    return ["remotion", "render", "src/index.ts", "Timeline", abs_out,
            "--codec=h264", "--concurrency=8", "--props=%s" % abs_props]


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
        if self._route_editor():
            return
        if self._redirect_root():
            return
        f = self.send_head()
        if f:
            try:
                self.copyfile(f, self.wfile)
            finally:
                f.close()

    def do_HEAD(self):
        if self._route_editor():
            return
        if self._redirect_root():
            return
        f = self.send_head()
        if f:
            f.close()

    def do_POST(self):
        if self.path == "/api/build":
            return self._api_build()
        if self.path == "/api/abort":
            return self._api_abort()
        if self.path == "/api/delete":
            return self._api_delete()
        if self.path == "/api/editor/save":
            return self._api_editor_save()
        if self.path == "/api/editor/render":
            return self._api_editor_render()
        self._json(404, {"error": "unknown endpoint"})

    def _route_editor(self):
        """Map the folded editor's public URL space onto studio/editor/dist/.

        The built Vite app uses base "/editor/", so the browser asks for /editor/
        (the SPA shell) and /editor/assets/*.{js,css}. We rewrite those onto
        /studio/editor/dist/* and let the normal Range-aware static handler serve
        them. Anything under /editor/ that isn't a real built file falls back to the
        SPA shell (dist/index.html) so a deep link like /editor/?run=x still loads —
        ?run is read client-side from window.location.search, which keeps the
        original browser URL (we only rewrite the path used to pick the file).

        Returns True only when a response was already sent (the no-trailing-slash
        redirect); otherwise rewrites self.path in place and returns False so the
        caller continues into the static handler.
        """
        path, sep, query = self.path.partition("?")
        if path != "/editor" and not path.startswith("/editor/"):
            return False  # not an editor request — leave self.path untouched
        if path == "/editor":
            # Normalize to the trailing-slash form so the SPA shell is served.
            self.send_response(301)
            self.send_header("Location", "/editor/" + (sep + query if query else ""))
            self.send_header("Content-Length", "0")
            self.end_headers()
            return True
        rel = path[len("/editor/"):]  # "" | "assets/index-xxxx.js" | favicon etc.
        if ".." in rel or not os.path.isfile(os.path.join(EDITOR_DIST, rel)):
            rel = "index.html"  # SPA shell fallback (covers "/editor/" and unknowns)
        self.path = "/studio/editor/dist/" + rel
        return False

    # ---- live-build API ---------------------------------------------------
    def _api_get(self):
        if self.path.startswith("/api/active"):
            return self._api_active()
        if self.path.startswith("/api/analytics"):
            return self._api_analytics()
        if self.path.startswith("/api/activity"):
            return self._api_activity()
        if self.path.startswith("/api/editor/runs"):
            return self._api_editor_runs()
        if self.path.startswith("/api/editor/props"):
            return self._api_editor_props()
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

    def _api_activity(self):
        """READ-ONLY activity feed: aggregate every runs/*/ledger.json into the
        actor-tagged Hermes/Nemotron event stream the Activity tab consumes.
        Delegates to activity.feed(); lazy import + error-trapped so one bad ledger
        (or a problem in activity.py) becomes a 500, never a server crash.
        """
        try:
            if PROJECT_ROOT not in sys.path:
                sys.path.insert(0, PROJECT_ROOT)
            import activity
            self._json(200, activity.feed())
        except Exception as e:  # noqa: BLE001 - never let one bad ledger 500 the rest
            self._json(500, {"error": "activity failed: %s" % e})

    def _api_active(self):
        """Report ONLY genuinely-live builds.

        A run is active iff its ledger says status=="running" AND it shows recent
        liveness: the newest mtime of runs/<id>/build.log and runs/<id>/ledger.json
        is within _ACTIVE_FRESHNESS_SECS. A "running" ledger whose files are stale is
        an orphaned corpse (the build process died before finalizing) and is excluded,
        so a dashboard reload doesn't get stuck polling a build that will never finish.
        Response shape is unchanged: {"active": [{"run_id", "phase"}]}.
        """
        import time
        runs_dir = os.path.join(PROJECT_ROOT, "runs")
        active = []
        now = time.time()
        try:
            names = sorted(os.listdir(runs_dir))
        except OSError:
            names = []
        for name in names:
            run_dir = os.path.join(runs_dir, name)
            p = os.path.join(run_dir, "ledger.json")
            if not os.path.exists(p):
                continue
            try:
                with open(p) as fh:
                    d = json.load(fh)
            except (OSError, ValueError):
                continue
            if d.get("status") != "running":
                continue
            # Liveness = freshest of build.log / ledger.json. A live build_runner.py
            # writes both continuously; a dead one's files are frozen in the past.
            newest = 0.0
            for fname in ("build.log", "ledger.json"):
                fp = os.path.join(run_dir, fname)
                try:
                    newest = max(newest, os.path.getmtime(fp))
                except OSError:
                    continue
            if now - newest > _ACTIVE_FRESHNESS_SECS:
                continue  # stale "running" run — an orphaned corpse, not active
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
        # EMPHASIS — the walkthrough target (free user text from the composer's
        # emphasis input). Becomes the STANDARD walkthrough's specific multi-step
        # goal (avoids the one-nav-link loop). Threaded to build_runner as
        # --emphasis; empty is fine — build_runner's argparse defaults emphasis="",
        # so we only append the flag when the user supplied a value.
        emphasis = (body.get("emphasis") or "").strip()
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
        # BRAIN — the OPERATOR choice (ultra-paid | super-free | super-paid), all via
        # OpenRouter. Picks which LLM PLANS the storyboard (not scene["model"]). Read
        # from a top-level `brain` field or selection.brain (app.js sends both);
        # absent/unknown defaults to super-free ($0) so nothing bills by accident.
        # Threaded to the build runner as --brain (mirrors --quality).
        brain = str(body.get("brain") or selection.get("brain") or _DEFAULT_BRAIN).strip().lower()
        if brain not in _BRAINS:
            brain = _DEFAULT_BRAIN
        run_id = "build-%s-%s" % (_slug(url), uuid.uuid4().hex[:6])
        run_dir = os.path.join(PROJECT_ROOT, "runs", run_id)
        os.makedirs(run_dir, exist_ok=True)
        logf = open(os.path.join(run_dir, "build.log"), "w")
        # zsh -lc sources ~/.zshrc so the planner sees OPENROUTER_API_KEY (the brain
        # endpoint) — same mechanism that exposed NVIDIA_API_KEY before.
        inner = ("cd %s && python3 build_runner.py --url %s --goal %s --run-id %s "
                 "--mode %s --duration %d --style %s --quality %s --brain %s"
                 % (shlex.quote(PROJECT_ROOT), shlex.quote(url), shlex.quote(goal),
                    shlex.quote(run_id), mode, duration, shlex.quote(style),
                    shlex.quote(quality), shlex.quote(brain)))
        # Append the walkthrough emphasis as --emphasis ONLY when the user supplied
        # one (build_runner defaults emphasis=""). shlex.quote keeps the free user
        # text shell-safe — it's the same hardening applied to --url/--goal above.
        if emphasis:
            inner += " --emphasis %s" % shlex.quote(emphasis)
        # MOCK builds auto-simulate the test payment ($0, no card) so automated /
        # visual testing isn't blocked on the Stripe gate. build_runner's
        # _payment_gate honors PRODUCER_SIMULATE_PAID=1 by resolving the poll to
        # "paid" immediately (it still CREATES a real test-mode session, just never
        # waits for a card). REAL mode deliberately omits this so it opens a genuine
        # test-mode Stripe gate that requires the test card. Inherit the current env
        # (zsh -lc still sources ~/.zshrc for the API keys) and add the flag only for
        # mock.
        child_env = os.environ.copy()
        if mode == "mock":
            child_env["PRODUCER_SIMULATE_PAID"] = "1"
        proc = subprocess.Popen(["zsh", "-lc", inner], stdout=logf, stderr=subprocess.STDOUT,
                                cwd=PROJECT_ROOT, start_new_session=True, env=child_env)
        # Record the spawned PID so POST /api/abort can stop this build. Because
        # start_new_session=True, the child's PID == its process-GROUP id, so
        # os.killpg(pid, ...) takes down build_runner.py AND every descendant it
        # spawned (remotion render, walk_native/Playwright). Best-effort: a failure
        # to write the pid file must never break the build that just started.
        try:
            with open(os.path.join(run_dir, "build.pid"), "w") as pidf:
                pidf.write(str(proc.pid))
        except OSError:
            pass
        self._json(200, {"run_id": run_id, "mode": mode, "quality": quality, "brain": brain, "emphasis": emphasis})

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

    def _api_abort(self):
        """Stop an in-progress build: kill its process GROUP, then mark the ledger
        aborted so the run leaves /api/active and the UI shows it stopped.

        Body: {"id": "<run_id>"}. The id is sanitized HARD via safe_run_dir()
        before any filesystem touch. We read runs/<id>/build.pid (written by
        _api_build right after Popen). Because the build was spawned with
        start_new_session=True, that PID is also the process-GROUP id, so
        os.killpg(pgid, SIGTERM) takes down build_runner.py AND its children
        (remotion render, walk_native/Playwright). We send SIGTERM, wait briefly,
        then SIGKILL anything still alive (os.killpg(pgid, 0) probes liveness).

        Idempotent + safe by design:
          * missing build.pid, an unparseable pid, or an already-dead group are all
            fine — we still mark the ledger aborted and return {ok: true}.
          * a bad/illegal run id is a 400 (never touches the filesystem).
        """
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            return self._json(400, {"error": "bad JSON body"})
        run_id = body.get("id")
        try:
            run_dir = safe_run_dir(run_id)
        except ValueError as e:
            return self._json(400, {"error": "invalid run id: %s" % e})
        if not os.path.isdir(run_dir):
            return self._json(404, {"error": "run not found"})

        killed = False
        pgid = None
        pid_path = os.path.join(run_dir, "build.pid")
        try:
            with open(pid_path) as fh:
                pgid = int((fh.read() or "").strip())
        except (OSError, ValueError):
            pgid = None  # no/garbage pid file — nothing to kill, still mark aborted

        if pgid and pgid > 1:
            # SIGTERM the whole group, give it a beat, then SIGKILL stragglers.
            try:
                os.killpg(pgid, signal.SIGTERM)
                killed = True
            except ProcessLookupError:
                pass  # group already gone — already dead, fine
            except OSError:
                pass
            if killed:
                # Brief escalation loop: poll up to ~2s for the group to die, then
                # SIGKILL whatever remains. os.killpg(pgid, 0) raises once the group
                # is gone (ProcessLookupError) — that's our "dead" signal.
                gone = False
                for _ in range(20):  # 20 * 0.1s = 2s
                    try:
                        os.killpg(pgid, 0)
                    except ProcessLookupError:
                        gone = True
                        break
                    except OSError:
                        gone = True  # e.g. ESRCH-equivalent — treat as gone
                        break
                    time.sleep(0.1)
                if not gone:
                    try:
                        os.killpg(pgid, signal.SIGKILL)
                    except OSError:
                        pass

        # Mark the ledger aborted (preserve every other field) so the run drops out
        # of /api/active and the UI reflects a stopped build. Best-effort: a missing
        # or unreadable ledger must not turn a successful kill into an error.
        ledger_path = os.path.join(run_dir, "ledger.json")
        try:
            with open(ledger_path) as fh:
                ledger = json.load(fh)
        except (OSError, ValueError):
            ledger = {}
        ledger["status"] = "aborted"
        ledger["aborted_by"] = "user"
        try:
            with open(ledger_path, "w") as fh:
                json.dump(ledger, fh, indent=2)
        except OSError as e:
            return self._json(500, {"error": "could not update ledger: %s" % e})

        self._json(200, {"ok": True, "id": run_id, "killed": killed, "pgid": pgid})

    # ---- folded video-editor API -----------------------------------------
    # These mirror studio/editor/server-api.js EXACTLY (same contract, now served
    # by the dashboard so the editor is one app on :3030). They only read/write
    # files under runs/<id>/ and spawn the same `remotion render` the pipeline uses.

    def _editor_list_runs(self):
        """Every runs/<id>/ that has a props.json, newest props first (so a freshly
        generated run sorts to the top of the editor's run picker)."""
        out = []
        if not os.path.isdir(RUNS_DIR):
            return out
        for name in os.listdir(RUNS_DIR):
            d = os.path.join(RUNS_DIR, name)
            if not os.path.isdir(d):
                continue
            if not os.path.isfile(os.path.join(d, "props.json")):
                continue
            try:
                mtime = os.path.getmtime(os.path.join(d, "props.json"))
            except OSError:
                mtime = 0
            out.append({
                "id": name,
                "hasProps": True,
                "hasEdited": os.path.isfile(os.path.join(d, "props.edited.json")),
                "hasFinal": os.path.isfile(os.path.join(d, "final.mp4")),
                "hasEditedMp4": os.path.isfile(os.path.join(d, "edited.mp4")),
                "mtime": mtime,
            })
        out.sort(key=lambda r: r["mtime"], reverse=True)
        return out

    def _api_editor_runs(self):
        self._json(200, {"runs": self._editor_list_runs()})

    def _api_editor_props(self):
        qs = parse_qs(urlparse(self.path).query)
        rid = (qs.get("id") or [""])[0]
        if not rid:
            return self._json(400, {"error": "missing id"})
        try:
            d = safe_run_dir(rid)
        except ValueError as e:
            return self._json(400, {"error": "invalid run id: %s" % e})
        base = os.path.join(d, "props.json")
        edited = os.path.join(d, "props.edited.json")
        has_edited = os.path.isfile(edited)
        # DEFAULT to the CLEAN canonical props.json; only serve props.edited.json
        # when the caller explicitly opts in (&edited=1) AND it exists, so a stale
        # edit never silently shadows the real generated props.
        want_edited = (qs.get("edited") or [""])[0].lower() in ("1", "true", "yes")
        which = edited if (want_edited and has_edited) else base
        if not os.path.isfile(which):
            return self._json(404, {"error": "no props for " + rid})
        try:
            with open(which, "r") as fh:
                props = json.load(fh)
        except Exception as e:  # noqa: BLE001
            return self._json(500, {"error": "could not read props: %s" % e})
        self._json(200, {
            "id": rid,
            "source": os.path.basename(which),
            "hasEdited": has_edited,
            "props": props,
        })

    def _api_editor_save(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            return self._json(400, {"error": "bad JSON body"})
        rid = body.get("id")
        props = body.get("props")
        if not rid or props is None:
            return self._json(400, {"error": "missing id or props"})
        try:
            d = safe_run_dir(rid)
        except ValueError as e:
            return self._json(400, {"error": "invalid run id: %s" % e})
        if not os.path.isdir(d):
            return self._json(404, {"error": "no run " + rid})
        edited_path = os.path.join(d, "props.edited.json")
        try:
            with open(edited_path, "w") as fh:
                json.dump(props, fh, indent=2)
        except OSError as e:
            return self._json(500, {"error": "save failed: %s" % e})
        abs_props = os.path.abspath(edited_path)
        abs_out = os.path.abspath(os.path.join(d, "edited.mp4"))
        self._json(200, {
            "ok": True,
            "wrote": edited_path,
            "renderCommand": "cd %s && %s" % (STUDIO_DIR, " ".join(_editor_render_cmd(abs_props, abs_out))),
        })

    def _api_editor_render(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            return self._json(400, {"error": "bad JSON body"})
        rid = body.get("id")
        if not rid:
            return self._json(400, {"error": "missing id"})
        try:
            d = safe_run_dir(rid)
        except ValueError as e:
            return self._json(400, {"error": "invalid run id: %s" % e})
        edited_path = os.path.join(d, "props.edited.json")
        if not os.path.isfile(edited_path):
            return self._json(400, {"error": "no props.edited.json — Save first"})
        abs_props = os.path.abspath(edited_path)
        abs_out = os.path.abspath(os.path.join(d, "edited.mp4"))
        cmd = _editor_render_cmd(abs_props, abs_out)

        # Stream plain-text status lines as the render runs (the editor's render()
        # reads this body incrementally and stops at the final __DONE__ <json> line).
        # HTTP/1.1 needs a body delimiter; we close the connection at the end so the
        # browser's stream reader gets a clean EOF. The server is threaded, so this
        # multi-minute render never blocks the dashboard's other requests.
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True

        def w(s):
            try:
                self.wfile.write(s.encode())
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass

        w("[editor] rendering %s -> %s\n" % (rid, abs_out))
        w("[editor] cmd: %s\n" % " ".join(cmd))
        env = os.environ.copy()
        env["PATH"] = os.path.join(STUDIO_DIR, "node_modules", ".bin") + os.pathsep + env.get("PATH", "")
        try:
            proc = subprocess.Popen(cmd, cwd=STUDIO_DIR, env=env,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        except Exception as e:  # noqa: BLE001
            w("\n[editor] spawn error: %s\n" % e)
            w("__DONE__ %s\n" % json.dumps({"ok": False, "error": str(e)}))
            return
        for line in proc.stdout:
            w(line)
        code = proc.wait()
        exists = os.path.isfile(abs_out)
        ok = code == 0 and exists
        w("\n[editor] exit=%s exists=%s\n" % (code, exists))
        w("__DONE__ %s\n" % json.dumps({"ok": ok, "out": abs_out if ok else None, "code": code}))

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
