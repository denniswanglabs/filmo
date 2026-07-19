#!/usr/bin/env python3
"""The Filmo DIRECTOR — conversational control of the walkrec pipeline.

NOT a normal chatbot (Dennis 2026-07-19, after the Palmier aesthetic-problem
piece): taste lives in the SYSTEM, the chat only steers within it.

Structural rules:
- CLOSED ACTION SPACE — the model returns actions from a fixed menu
  (drop / swap_treatment / retitle / rerun / answer); it can never write copy
  or free-edit the film. Retitles pick from VERBATIM site lines only.
- SYSTEM ALWAYS WINS on taste — off-brand aesthetic requests (new colors,
  foreign styles) are DECLINED with the honest reason (brand truth comes from
  the customer's site) and, where one exists, the nearest in-contract move.
- ZERO intake — the first cut is autonomous; conversation is for editing and
  for "why" questions, answered from the run's own event provenance.
- Every applied change re-renders through the SAME contracts (material
  floors revalidated, motif_locked, content-once) as the reviewer.

State: runs/<id>/stops.json ({stops, ctx}) written at assemble time;
chat transcript appended to runs/<id>/chat.jsonl; work runs on a background
thread emitting the usual events so the stage narrates the change.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from run_events import emit  # noqa: E402

# The watch server starts without the shell env — load the brain key here.
if not os.environ.get("OPENROUTER_API_KEY"):
    try:
        with open(os.path.expanduser("~/.hermes/.env")) as _f:
            for _line in _f:
                _line = _line.strip()
                if _line.startswith("OPENROUTER_API_KEY="):
                    os.environ["OPENROUTER_API_KEY"] =                         _line.split("=", 1)[1].strip().strip('"')
                    break
    except Exception:
        pass

_BUSY: dict = {}

_SYSTEM = """You are the Filmo Director — the conversational surface of an \
autonomous launch-film pipeline. You steer the film ONLY through the action \
menu below. Taste is owned by the system: every color, font, and visual \
style comes from the customer's own website, and every word shown comes \
verbatim from that site. You never invent copy, colors, or styles.

THE FILM'S CURRENT BEATS (index: title -> treatment):
{beats}

TREATMENTS AVAILABLE FOR SWAPS: check-list, chip-sweep, kinetic-line, \
quote-card, people-wall, stat-pop, logo-wall, request-table, context-cards, \
house, chat, globe, card, tag (the system revalidates material floors; an \
invalid swap is rejected).

RUN PROVENANCE (recent events you may cite when answering questions):
{events}

Respond with STRICT JSON only:
{{"reply": "<your short, warm, concrete reply to the user>",
  "actions": [{{"action": "drop"|"swap_treatment"|"rerun"|"none",
               "beat": <index or -1>, "to": "<treatment or empty>"}}]}}

Rules:
- Aesthetic requests outside the brand's own palette/style (e.g. 'make it \
neon cyberpunk', 'use red', 'add emojis'): actions=[], and the reply \
honestly declines: brand truth comes from their site; offer the nearest \
in-system move if one exists (e.g. a darker treatment mix, a kinetic beat).
- 'Why' questions: answer from the provenance events; actions=[].
- Ambiguous beat references: ask which beat; actions=[].
- 'Redo/regenerate the whole film': one action {{"action": "rerun"}}.
- Keep replies under 80 words. No emojis."""


def _load_state(run_dir: str):
    with open(os.path.join(run_dir, "stops.json")) as f:
        return json.load(f)


def _beats_summary(stops):
    lines = []
    for i, s in enumerate(stops):
        tr = "recording" if s.get("seg") else s.get("motif", "?")
        lines.append(f"{i}: “{s['title'][:60]}” -> {tr}")
    return "\n".join(lines)


def _events_tail(run_dir: str, n: int = 18):
    try:
        with open(os.path.join(run_dir, "events.jsonl")) as f:
            evts = [json.loads(l) for l in f][-n:]
        return "\n".join(f"[{e['kind']}] {e['title']}"
                         + (f" — {e['detail'][:90]}" if e.get("detail") else "")
                         for e in evts)
    except Exception:
        return "(no events)"


def _log_chat(run_dir: str, role: str, text: str):
    try:
        with open(os.path.join(run_dir, "chat.jsonl"), "a") as f:
            f.write(json.dumps({"ts": round(time.time(), 3), "role": role,
                                "text": text}) + "\n")
    except Exception:
        pass


def _apply_async(run_id: str, run_dir: str, state: dict, actions):
    """Apply gated actions and re-render on a background thread; the stage
    narrates via the normal event stream."""
    def work():
        try:
            import proto_walkrec as pw
            stops, ctx = state["stops"], state["ctx"]
            applied = []
            for a in actions:
                if a["action"] == "rerun":
                    emit(run_dir, "run.start",
                         "Director: full re-run requested",
                         "Re-reading the site and re-filming from scratch.")
                    url = ctx.get("host", "")
                    subprocess.Popen(
                        [sys.executable, os.path.join(HERE, "proto_walkrec.py"),
                         "--url", url, "--run-id", run_id, "--tour"],
                        cwd=HERE)
                    return
                bi = a.get("beat", -1)
                if not (0 <= bi < len(stops)) or stops[bi].get("seg"):
                    continue
                if a["action"] == "drop":
                    applied.append(f"dropped “{stops[bi]['title'][:40]}”")
                    stops[bi]["_drop"] = True
                elif a["action"] == "swap_treatment":
                    to = a.get("to", "")
                    if pw._refine_motif(to, stops[bi], set()) != to:
                        emit(run_dir, "review.finding",
                             f"Swap rejected for beat {bi + 1}",
                             f"“{to}” fails its material floor on this beat.")
                        continue
                    stops[bi]["motif"] = to
                    stops[bi]["motif_locked"] = True
                    applied.append(f"beat {bi + 1} → {to}")
            stops[:] = [s for s in stops if not s.get("_drop")]
            if not applied:
                emit(run_dir, "review.pass", "No changes applied",
                     "The requested edits did not survive the gates.")
                return
            emit(run_dir, "review.apply",
                 "Director: " + "; ".join(applied),
                 "Re-assembling and re-rendering.")
            pub = os.path.join(HERE, "studio", "public")
            out, _ = pw._assemble_and_render(run_id, run_dir, pub, stops, ctx)
            emit(run_dir, "review.done", "Change applied — film updated",
                 artifact=out)
            emit(run_dir, "run.done", "Run finished",
                 "The updated film is ready.")
        except BaseException as e:
            emit(run_dir, "run.error", "Director change failed",
                 f"{type(e).__name__}: {e}")
    t = threading.Thread(target=work, daemon=True)
    _BUSY[run_id] = t
    t.start()


def _parse(run_dir: str, state: dict, message: str):
    """One director parse: (reply, gated_actions). Raises on brain failure."""
    import validate_planner as vp
    sys_prompt = _SYSTEM.format(
        beats=_beats_summary(state["stops"]),
        events=_events_tail(run_dir))
    raw = vp.call_model([{"role": "system", "content": sys_prompt},
                         {"role": "user", "content": message}],
                        brain="sonnet5") or ""
    obj = None
    dec = json.JSONDecoder()
    for i, ch in enumerate(raw):
        if ch == "{":
            try:
                obj, _ = dec.raw_decode(raw[i:])
                break
            except Exception:
                continue
    if not isinstance(obj, dict):
        raise ValueError("unparseable director reply")
    reply = str(obj.get("reply") or "")[:600]
    actions = [a for a in (obj.get("actions") or [])
               if isinstance(a, dict)
               and a.get("action") in ("drop", "swap_treatment", "rerun")]
    return reply, actions


def _apply_work(run_id: str, run_dir: str, state: dict, actions) -> None:
    """Apply gated actions + re-render, synchronously. Emits the outcome."""
    import proto_walkrec as pw
    stops, ctx = state["stops"], state["ctx"]
    applied = []
    for a in actions:
        if a["action"] == "rerun":
            emit(run_dir, "run.start",
                 "Director: full re-run requested",
                 "Re-reading the site and re-filming from scratch.")
            pw.build_tour_film(ctx.get("host", ""), run_id)
            return
        bi = a.get("beat", -1)
        if not (0 <= bi < len(stops)) or stops[bi].get("seg"):
            continue
        if a["action"] == "drop":
            applied.append(f"dropped \u201c{stops[bi]['title'][:40]}\u201d")
            stops[bi]["_drop"] = True
        elif a["action"] == "swap_treatment":
            to = a.get("to", "")
            if pw._refine_motif(to, stops[bi], set()) != to:
                emit(run_dir, "review.finding",
                     f"Swap rejected for beat {bi + 1}",
                     f"\u201c{to}\u201d fails its material floor on this beat.")
                continue
            stops[bi]["motif"] = to
            stops[bi]["motif_locked"] = True
            applied.append(f"beat {bi + 1} \u2192 {to}")
    stops[:] = [s for s in stops if not s.get("_drop")]
    if not applied:
        emit(run_dir, "review.pass", "No changes applied",
             "The requested edits did not survive the gates.")
        return
    emit(run_dir, "review.apply", "Director: " + "; ".join(applied),
         "Re-assembling and re-rendering.")
    pub = os.path.join(HERE, "studio", "public")
    out, _beats = pw._assemble_and_render(run_id, run_dir, pub,
                                          stops, state["ctx"])
    import run_events as _re
    _re.ship_final(run_dir, run_id, out)
    emit(run_dir, "review.done", "Change applied — film updated",
         artifact=out)
    emit(run_dir, "run.done", "Run finished", "The updated film is ready.")
    _re.flush_sinks()


def handle_job(run_key: str, insforge_run_id: str, message: str) -> int:
    """Hosted director turn (claimer job): reply + apply, all through the
    event bus so the workspace narrates it. Returns a process exit code."""
    run_dir = os.path.join(HERE, "runs", run_key)
    os.makedirs(run_dir, exist_ok=True)
    if insforge_run_id:
        try:
            with open(os.path.join(run_dir, "insforge-run-id"), "w") as f:
                f.write(insforge_run_id)
        except Exception:
            pass
    try:
        state = _load_state(run_dir)
    except Exception:
        emit(run_dir, "chat.director",
             "This run's working files were recycled by a redeploy — say "
             "\u201credo the film\u201d and I'll make a fresh cut.", "")
        return 0
    try:
        reply, actions = _parse(run_dir, state, message)
    except (Exception, SystemExit) as e:
        emit(run_dir, "chat.director",
             f"I hit a snag reading that ({type(e).__name__}) — try again?", "")
        return 0
    emit(run_dir, "chat.director", reply, "")
    if actions:
        try:
            _apply_work(run_key, run_dir, state, actions)
        except BaseException as e:
            emit(run_dir, "run.error", "Director change failed",
                 f"{type(e).__name__}: {e}")
            return 1
    return 0


def handle(run_id: str, message: str) -> dict:
    """One chat turn. Returns {reply, working}. Never raises."""
    run_dir = os.path.join(HERE, "runs", run_id)
    _log_chat(run_dir, "user", message)
    if _BUSY.get(run_id) and _BUSY[run_id].is_alive():
        reply = ("Still working on the previous change — watch the stage; "
                 "I'll take the next note when it lands.")
        _log_chat(run_dir, "director", reply)
        return {"reply": reply, "working": True}
    try:
        state = _load_state(run_dir)
    except Exception:
        reply = ("This run has no editable state yet — let it finish its "
                 "first cut, then I can take changes.")
        _log_chat(run_dir, "director", reply)
        return {"reply": reply, "working": False}
    try:
        reply, actions = _parse(run_dir, state, message)
        working = bool(actions)
        if actions:
            _apply_async(run_id, run_dir, state, actions)
        _log_chat(run_dir, "director", reply)
        return {"reply": reply, "working": working}
    except (Exception, SystemExit) as e:
        reply = f"I hit a snag reading that ({type(e).__name__}) — try again?"
        _log_chat(run_dir, "director", reply)
        return {"reply": reply, "working": False}
