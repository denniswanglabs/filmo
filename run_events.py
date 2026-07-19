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
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))

# HOSTED SINK (walkrec beta): when the worker env carries InsForge access,
# every event ALSO lands in public.agent_events and artifacts upload to
# storage — same bus, second sink, best-effort and non-blocking so a network
# blip can never break a build.
_IF_BASE = (os.environ.get("INSFORGE_BASE_URL")
            or os.environ.get("INSFORGE_URL", "")).rstrip("/")
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


def _multipart(fields: dict, file_field: str, filename: str,
               ctype: str, data: bytes):
    """Encode a multipart/form-data body (stdlib only)."""
    boundary = "----filmo%d" % int(time.time() * 1000)
    out = []
    for k, v in fields.items():
        out.append(f"--{boundary}\r\nContent-Disposition: form-data; "
                   f"name=\"{k}\"\r\n\r\n{v}\r\n".encode())
    out.append(f"--{boundary}\r\nContent-Disposition: form-data; "
               f"name=\"{file_field}\"; filename=\"{filename}\"\r\n"
               f"Content-Type: {ctype}\r\n\r\n".encode())
    out.append(data)
    out.append(f"\r\n--{boundary}--\r\n".encode())
    return b"".join(out), f"multipart/form-data; boundary={boundary}"


def upload_object(key: str, path: str, overwrite: bool = False) -> str:
    """Upload a file via the documented strategy flow (S3 presigned POST or
    local direct PUT). Returns the object URL, '' on failure. Never raises."""
    try:
        ext = os.path.splitext(path)[1].lower()
        ctype = ("video/mp4" if ext == ".mp4" else
                 "image/jpeg" if ext in (".jpg", ".jpeg") else "image/png")
        with open(path, "rb") as f:
            data = f.read()
        if overwrite:
            try:
                req = urllib.request.Request(
                    f"{_IF_BASE}/api/storage/buckets/{_IF_BUCKET}/objects/{key}",
                    method="DELETE",
                    headers={"Authorization": f"Bearer {_IF_KEY}"})
                urllib.request.urlopen(req, timeout=10)
            except Exception:
                pass
        strat = json.loads(_if_req(
            "POST", f"/api/storage/buckets/{_IF_BUCKET}/upload-strategy",
            json.dumps({"filename": key, "contentType": ctype,
                        "size": len(data)}).encode(),
            "application/json").read())
        if strat.get("method") == "presigned":
            fields = dict(strat.get("fields") or {})
            body, mp_ctype = _multipart(fields, "file", key, ctype, data)
            req = urllib.request.Request(strat["uploadUrl"], data=body,
                                         method="POST",
                                         headers={"Content-Type": mp_ctype})
            urllib.request.urlopen(req, timeout=60)
            _if_req("POST",
                    f"/api/storage/buckets/{_IF_BUCKET}/objects/"
                    f"{urllib.parse.quote(key, safe='')}/confirm-upload",
                    json.dumps({"size": len(data)}).encode(),
                    "application/json")
        else:
            body, mp_ctype = _multipart({}, "file", key, ctype, data)
            req = urllib.request.Request(strat.get("uploadUrl", ""), data=body,
                                         method="PUT",
                                         headers={
                                             "Authorization": f"Bearer {_IF_KEY}",
                                             "Content-Type": mp_ctype})
            urllib.request.urlopen(req, timeout=60)
        return (f"{_IF_BASE}/api/storage/buckets/{_IF_BUCKET}/objects/"
                f"{urllib.parse.quote(key, safe='')}")
    except Exception:
        return ""


def _upload_artifact(run_id: str, seq: int, path: str) -> str:
    ext = os.path.splitext(path)[1] or ".bin"
    return upload_object(f"agent/{run_id}/{seq}{ext}", path)


_SINK_THREADS: list = []


def flush_sinks(timeout: float = 120.0) -> None:
    """Join pending sink threads. The bus contract's exit clause: daemon
    threads die with the process, so a run's TAIL events (terminal events,
    the film artifact) were lost when the pipeline exited right after its
    last emit. Callers that end a run MUST flush."""
    deadline = time.time() + timeout
    for t in list(_SINK_THREADS):
        t.join(max(0.0, deadline - time.time()))
    _SINK_THREADS.clear()


def _hosted_sink(run_dir: str, evt: dict, artifact_path: str) -> None:
    rid = _hosted_run_id(run_dir)
    if not (rid and _IF_BASE and _IF_KEY):
        return

    def work():
        # ROW FIRST, PIXELS AFTER: the text event must reach the UI in
        # seconds; artifact uploads (cross-region, uplink shared with the
        # live-frame stream) can take a minute — serializing insert behind
        # upload made the whole thread lag minutes behind the live canvas.
        # The artifact attaches to the already-visible row via PATCH.
        try:
            row = {"run_id": rid, "seq": evt["seq"], "ts": evt["ts"],
                   "kind": evt["kind"], "title": evt["title"],
                   "detail": evt["detail"], "artifact_url": ""}
            _if_req("POST", "/api/database/records/agent_events",
                    json.dumps([row]).encode(), "application/json")
        except Exception as e:
            print(f"[sink!] insert {evt['kind']} seq {evt['seq']}: {e}",
                  file=sys.stderr)
            return
        if not (artifact_path and os.path.exists(artifact_path)):
            return
        try:
            url = _upload_artifact(rid, evt["seq"], artifact_path)
            if url:
                _if_req("PATCH",
                        "/api/database/records/agent_events"
                        f"?run_id=eq.{rid}&seq=eq.{evt['seq']}",
                        json.dumps({"artifact_url": url}).encode(),
                        "application/json")
        except Exception as e:
            print(f"[sink!] artifact {evt['kind']} seq {evt['seq']}: {e}",
                  file=sys.stderr)
    t = threading.Thread(target=work, daemon=True)
    _SINK_THREADS.append(t)
    t.start()


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
