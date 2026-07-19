"""Run event bus (walkrec prototype) — the agent's visible activity stream.

ARCHITECTURAL CONTRACT (Dennis 2026-07-18: "the agent always gives updates"):
1. ONE BUS — every user-visible progress line flows through emit(). emit()
   both appends a structured JSON event to runs/<id>/events.jsonl AND prints
   the human log line, so narration and telemetry are the same act and can
   never drift apart.
2. NO SILENT ENDINGS — the run wrapper emits a terminal event ("run.done" /
   "run.error") from a finally block; a watcher always learns how a run ended.
3. ARTIFACTS BY REFERENCE — events carry repo-relative paths to the real
   files the agent produced (page shots, recordings, the film). The viewer
   shows what the agent actually saw, never a reconstruction.

Events are append-only JSONL: {"seq", "ts", "kind", "title", "detail",
"artifact"}. kind is dot-namespaced: run.*, read.*, decide.*, film.*,
assemble.*. Never raises — a broken event stream must not break a build.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))

# HOSTED SINK (walkrec beta): when the worker env carries InsForge access,
# every event ALSO lands in public.agent_events and artifacts upload to
# storage — same bus, second sink, best-effort and non-blocking so a network
# blip can never break a build.
_IF_BASE = os.environ.get("INSFORGE_BASE_URL", "").rstrip("/")
_IF_KEY = os.environ.get("INSFORGE_API_KEY", "")
_IF_BUCKET = os.environ.get("INSFORGE_BUCKET", "walk-videos")


def _hosted_run_id(run_dir: str) -> str:
    """The InsForge runs.id for this run dir ('' when not a hosted run).
    The worker writes runs/<dir>/insforge-run-id at claim time."""
    try:
        with open(os.path.join(run_dir, "insforge-run-id")) as f:
            return f.read().strip()
    except Exception:
        return ""


def _if_req(method: str, path: str, body: bytes, ctype: str):
    req = urllib.request.Request(
        _IF_BASE + path, data=body, method=method,
        headers={"Authorization": f"Bearer {_IF_KEY}", "Content-Type": ctype})
    return urllib.request.urlopen(req, timeout=15)


def _upload_artifact(run_id: str, seq: int, path: str) -> str:
    ext = os.path.splitext(path)[1] or ".bin"
    key = f"agent/{run_id}/{seq}{ext}"
    ctype = ("video/mp4" if ext == ".mp4" else
             "image/jpeg" if ext in (".jpg", ".jpeg") else "image/png")
    with open(path, "rb") as f:
        _if_req("PUT", f"/api/storage/buckets/{_IF_BUCKET}/objects/{key}",
                f.read(), ctype)
    return f"{_IF_BASE}/api/storage/buckets/{_IF_BUCKET}/objects/{key}"


def _hosted_sink(run_dir: str, evt: dict, artifact_path: str) -> None:
    rid = _hosted_run_id(run_dir)
    if not (rid and _IF_BASE and _IF_KEY):
        return

    def work():
        try:
            url = ""
            if artifact_path and os.path.exists(artifact_path):
                try:
                    url = _upload_artifact(rid, evt["seq"], artifact_path)
                except Exception:
                    url = ""
            row = {"run_id": rid, "seq": evt["seq"], "ts": evt["ts"],
                   "kind": evt["kind"], "title": evt["title"],
                   "detail": evt["detail"], "artifact_url": url}
            _if_req("POST", "/api/database/records/agent_events",
                    json.dumps([row]).encode(), "application/json")
        except Exception:
            pass
    threading.Thread(target=work, daemon=True).start()


def _events_path(run_dir: str) -> str:
    return os.path.join(run_dir, "events.jsonl")


def emit(run_dir: str, kind: str, title: str, detail: str = "",
         artifact: str = "") -> None:
    """Append one event and mirror it to stderr. Best-effort, never raises."""
    try:
        os.makedirs(run_dir, exist_ok=True)
        path = _events_path(run_dir)
        seq = 0
        if os.path.exists(path):
            with open(path, "rb") as f:
                seq = sum(1 for _ in f)
        if artifact:
            # Store repo-relative so the viewer server can serve it.
            ap = os.path.abspath(artifact)
            if ap.startswith(HERE):
                artifact = os.path.relpath(ap, HERE)
        evt = {"seq": seq, "ts": round(time.time(), 3), "kind": kind,
               "title": title, "detail": detail, "artifact": artifact}
        with open(path, "a") as f:
            f.write(json.dumps(evt, ensure_ascii=False) + "\n")
        print(f"[{kind}] {title}" + (f" — {detail}" if detail else ""),
              file=sys.stderr)
        _hosted_sink(run_dir, evt,
                     os.path.join(HERE, artifact) if artifact else "")
    except Exception:
        pass


def read_events(run_dir: str, after: int = -1):
    """Events with seq > after. Never raises."""
    try:
        out = []
        with open(_events_path(run_dir)) as f:
            for line in f:
                try:
                    e = json.loads(line)
                    if e.get("seq", -1) > after:
                        out.append(e)
                except Exception:
                    continue
        return out
    except Exception:
        return []
