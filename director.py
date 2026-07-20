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

THE FILM'S CURRENT BEATS (the ONLY editable beats; recordings of the site
itself are not editable and are not listed):
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
               "beat_title": "<the beat's title EXACTLY as listed above>",
               "to": "<treatment or empty>"}}]}}

TARGETING RULE: beat_title must be copied VERBATIM from the beat list above.
If the user references a beat by treatment ("the globe beat"), map it to the
title carrying that treatment in the list; if no listed beat carries it, or
two could match, ask instead (actions=[]).

VOICE (match this exactly):
- Open a reply with a 1-3 word acknowledgment token, an em-dash, then the move: "Perfect — …", "No problem — …", "Good catch — …". Never spend a sentence acknowledging, and never apologise.
- First person, present tense, saying what you are doing and WHY: "I'm swapping that beat so the title and what's under it agree."
- One to three sentences. No bullet lists, no headers, no emoji, no jargon, no internal names (treatments are "how a beat is treated", not "motifs").
- When you decline, frame it as care for the film, not a limitation, and offer the nearest move that IS in contract.

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


def _vignettes(stops):
    return [s for s in stops if not s.get("seg")]


def _beats_summary(stops):
    lines = []
    for n, s in enumerate(_vignettes(stops), start=1):
        lines.append(f"Beat {n}: “{s['title']}” -> "
                     f"{s.get('motif', '?')}")
    return "\n".join(lines)


def _norm_title(t: str) -> str:
    return " ".join(str(t or "").split()).lower()


def _resolve_actions(stops, actions):
    """Resolve model actions to CURRENT stops by verbatim title — one source
    of truth for targeting (F7: index-based targeting dropped the wrong beat
    after treatments shifted between rounds). Mutates stops for applied
    drops/swaps; returns (applied, rejected, rerun) where applied/rejected
    are outcome facts for the reply."""
    import proto_walkrec as pw
    vign = _vignettes(stops)
    by_title = {_norm_title(s["title"]): s for s in vign}
    applied, rejected = [], []
    rerun = False
    for a in actions:
        if a.get("action") == "rerun":
            rerun = True
            continue
        title = a.get("beat_title") or ""
        s = by_title.get(_norm_title(title))
        if s is None and isinstance(a.get("beat"), int):
            bi = a["beat"]
            if 0 <= bi < len(vign):
                s = vign[bi]
        if s is None:
            rejected.append((title or "(unnamed beat)",
                             "no beat with that title in the current cut"))
            continue
        if a.get("action") == "drop":
            s["_drop"] = True
            applied.append(("drop", s["title"]))
        elif a.get("action") == "swap_treatment":
            to = a.get("to", "")
            # Same tie-break the reviewer uses: the floor, plus what the rest
            # of the cut has already spent. `stops` is the current cut, so the
            # index has to be resolved from it rather than from `vign`.
            bi = stops.index(s)
            picked = pw._pick_repair(stops, bi, to)
            if picked == pw._CUT:
                rejected.append(
                    (s["title"],
                     f"“{to}” fails its material floor on this beat"))
                continue
            to = picked
            s["motif"] = to
            s["motif_locked"] = True
            applied.append(("swap", s["title"], to))
    stops[:] = [s for s in stops if not s.get("_drop")]
    return applied, rejected, rerun


def _outcome_reply(stops, applied, rejected) -> str:
    """The chat.director text for an action turn, authored FROM the resolved
    outcome — never from intent (F7: the pre-gate reply narrated a swap the
    gates then rejected, and a drop the film never made)."""
    parts = []
    # Lead with a short acknowledgment token, then the move — never spend a
    # whole sentence acknowledging, and never apologise.
    if applied:
        head = [(f"dropped “{a[1]}”" if a[0] == "drop"
                 else f"swapped “{a[1]}” to {a[2]}") for a in applied]
        parts.append("Done — " + ", ".join(head) + ".")
    for title, why in rejected:
        parts.append(f"I left “{title}” alone — {why}.")
    if applied:
        vign = _vignettes(stops)
        if vign:
            parts.append(f"The film closes on “{vign[-1]['title']}” now. "
                         "Re-cutting it — watch the film panel.")
        else:
            parts.append("Re-cutting it — watch the film panel.")
    elif not rejected:
        parts.append("Nothing to change there.")
    return " ".join(parts)


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


def _render_async(run_id: str, run_dir: str, state: dict, applied):
    """Render an already-resolved change set on a background thread (local
    path). Resolution/gating happened synchronously in handle() so the reply
    the user already saw is outcome-truth; this thread only prints."""
    def work():
        try:
            import proto_walkrec as pw
            stops = state["stops"]
            emit(run_dir, "review.apply",
                 "Director: " + "; ".join(
                     (f"dropped “{a[1][:40]}”" if a[0] == "drop"
                      else f"“{a[1][:40]}” → {a[2]}") for a in applied),
                 "Re-assembling and re-rendering.")
            pub = os.path.join(HERE, "studio", "public")
            out, _beats, _film_s = pw._assemble_and_render(
                run_id, run_dir, pub, stops, state["ctx"])
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


# An applied edit re-renders the film — real compute, so it costs credits.
# Conversation (answers, and anything the taste gates decline) is free: the
# user must never pay for the system saying no.
#
# ── SECOND COPY OF A PRICE ───────────────────────────────────────────────
# AUTHORITY: `EDIT_CREDIT_COST` in `web/app/actions.ts` (~line 107), which
# sits under the derivation comment that explains where 70 comes from (an
# edit ≈ 2,500 tokens) and beside VIDEO_CREDIT_COST / the daily cap it was
# derived against. This is a duplicate, not the source: the TS constant
# gates the user's balance BEFORE the job is queued, and this one writes the
# ledger row AFTER the render. A change to one alone silently quotes one
# price and charges another — the user is admitted at 70 and debited
# whatever the worker still believes. There is no shared config the two
# runtimes both read, so this cross-reference is the seam: change the
# authority first, then this line in the same commit.
EDIT_CREDIT_COST = 70


def _apply_work(run_id: str, run_dir: str, state: dict, actions,
                job_id: str = "") -> None:
    """Resolve + gate + apply + re-render, synchronously. The chat reply is
    authored from the OUTCOME (never from intent) and emitted before the
    slow render so the user sees truth immediately."""
    import proto_walkrec as pw
    stops, ctx = state["stops"], state["ctx"]
    applied, rejected, rerun = _resolve_actions(stops, actions)
    if rerun:
        emit(run_dir, "chat.director",
             "Redoing the whole film — re-reading the site and re-filming "
             "from scratch.", "")
        emit(run_dir, "run.start", "Director: full re-run requested",
             "Re-reading the site and re-filming from scratch.")
        pw.build_tour_film(ctx.get("host", ""), run_id)
        return
    emit(run_dir, "chat.director", _outcome_reply(stops, applied, rejected),
         "")
    for title, why in rejected:
        emit(run_dir, "review.finding", f"Rejected: “{title[:60]}”", why + ".")
    if not applied:
        emit(run_dir, "review.pass", "No changes applied",
             "The requested edits did not survive the gates.")
        return
    emit(run_dir, "review.apply",
         "Director: " + "; ".join(
             (f"dropped “{a[1][:40]}”" if a[0] == "drop"
              else f"“{a[1][:40]}” → {a[2]}") for a in applied),
         "Re-assembling and re-rendering.")
    import run_events as _rev
    _rev.charge_credits(run_dir, EDIT_CREDIT_COST,
                        f"edit:{job_id or int(time.time())}")
    pub = os.path.join(HERE, "studio", "public")
    out, _beats, _film_s = pw._assemble_and_render(run_id, run_dir, pub,
                                                   stops, state["ctx"])
    import run_events as _re
    _re.ship_final(run_dir, run_id, out)
    emit(run_dir, "review.done", "Change applied — film updated",
         artifact=out)
    emit(run_dir, "run.done", "Run finished", "The updated film is ready.")
    _re.flush_sinks()


def handle_job(run_key: str, insforge_run_id: str, message: str,
               job_id: str = "") -> int:
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
    if not actions:
        # Answers and declines: the model's own voice IS the outcome.
        emit(run_dir, "chat.director", reply, "")
        return 0
    try:
        _apply_work(run_key, run_dir, state, actions, job_id)
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
        if actions:
            applied, rejected, rerun = _resolve_actions(state["stops"],
                                                        actions)
            if rerun:
                emit(run_dir, "run.start", "Director: full re-run requested",
                     "Re-reading the site and re-filming from scratch.")
                subprocess.Popen(
                    [sys.executable, os.path.join(HERE, "proto_walkrec.py"),
                     "--url", state["ctx"].get("host", ""),
                     "--run-id", run_id, "--tour"], cwd=HERE)
                reply = "Redoing the whole film from scratch — watch the stage."
                _log_chat(run_dir, "director", reply)
                return {"reply": reply, "working": True}
            reply = _outcome_reply(state["stops"], applied, rejected)
            for title, why in rejected:
                emit(run_dir, "review.finding",
                     f"Rejected: “{title[:60]}”", why + ".")
            if applied:
                _render_async(run_id, run_dir, state, applied)
            else:
                emit(run_dir, "review.pass", "No changes applied",
                     "The requested edits did not survive the gates.")
        working = bool(actions)
        _log_chat(run_dir, "director", reply)
        return {"reply": reply, "working": working}
    except (Exception, SystemExit) as e:
        reply = f"I hit a snag reading that ({type(e).__name__}) — try again?"
        _log_chat(run_dir, "director", reply)
        return {"reply": reply, "working": False}
