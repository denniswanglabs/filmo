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
import time

HERE = os.path.dirname(os.path.abspath(__file__))


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
