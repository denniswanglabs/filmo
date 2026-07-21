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
import workspace_store  # noqa: E402

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
itself — the real screen footage — are NOT editable and are NOT listed):
{beats}

THE CONVERSATION SO FAR — this is your MEMORY. Every turn is a fresh start, so
resolve every reference ("that scene", "the checklist one", "the second one",
"yes", "do it", "that treatment") against these turns, not against this last
message alone:
{chat}

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

ACT, DON'T RE-ASK: when the ACTION and the TARGET beat are BOTH determined
across the conversation — even if they arrived in different turns — emit the
action THIS turn. Ask at most ONE clarifying question per ambiguity; once the
user answers it, it is settled and the next turn ACTS on the answer. Never
re-offer a choice the user already made, and never ask what the conversation
above already answers.

THE TREATMENT IS THE USER'S WORD: a swap's target treatment must be one the
USER named (in this message or earlier in the conversation). NEVER choose the
treatment yourself. If the user wants a swap but has not named a treatment, ask
exactly once — "Swap it to what — a logo wall, a stat pop, a quote card?" — with
actions=[]. Emitting a swap to a treatment the user never said is the one thing
you must never do.

RECORDINGS ARE REAL FOOTAGE: the opening and any screen recording of the site
are NOT in the beat list and CANNOT be dropped, cut, restyled, or edited. If the
user asks to delete or change "the first scene", "the opening", "the intro", or
any real footage, tell the plain truth — the recordings are real footage of
their site, so you can't cut or restyle them; you can only drop or re-treat the
graphic beats — and then LIST those beats. Never steer them into a forced choice
among unrelated beats to satisfy a request aimed at a recording.

ACT WITH THE NOTE, don't flag-and-wait: when the instruction is explicit and the
beat resolves, APPLY it; if you have a concern, VOICE it in the SAME reply while
doing it, never instead of doing it.

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
- Ambiguous beat references: ask which beat ONCE; actions=[]. A reference the
  conversation already resolves is NOT ambiguous — act on it.
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


# The closed treatment vocabulary the user may name (mirrors the SWAP menu in
# _SYSTEM). A swap the director APPLIES must land on one of these AND on one the
# USER actually said — see _said_treatments and _resolve_actions.
_TREATMENTS = ("check-list", "chip-sweep", "kinetic-line", "quote-card",
               "people-wall", "stat-pop", "logo-wall", "request-table",
               "context-cards", "house", "chat", "globe", "card", "tag")


def _canon_treatment(t: str) -> str:
    """Canonical hyphenated menu form so "logo wall", "Logo-Wall" and
    "logo-wall" all compare equal."""
    return "-".join(str(t or "").lower().replace("-", " ").split())


def _chat_user_texts(run_dir: str):
    """Every USER line from chat.jsonl, oldest-first — the corpus the treatment
    guard checks a swap's target against."""
    out = []
    try:
        with open(os.path.join(run_dir, "chat.jsonl")) as f:
            for line in f:
                try:
                    o = json.loads(line)
                except Exception:
                    continue
                if o.get("role") == "user" and o.get("text"):
                    out.append(str(o["text"]))
    except Exception:
        pass
    return out


def _said_treatments(run_dir: str, message: str) -> set:
    """The treatments the USER has named — in this message or any earlier turn —
    canonicalized. Enforces fix #3 in code, not just prompt: the director may
    PROPOSE a swap, but the treatment it lands on must be a word the user
    actually said (a swap to "context-cards" nobody asked for shipped
    2026-07-20 because nothing checked this). Ambient words are permissive by
    design — the guard only has to stop a treatment the user NEVER mentioned."""
    said = set()
    for text in _chat_user_texts(run_dir) + [message or ""]:
        low = " " + " ".join(str(text).lower().replace("-", " ").split()) + " "
        for m in _TREATMENTS:
            if " " + m.replace("-", " ") + " " in low:
                said.add(m)
    return said


def _chat_tail(run_dir: str, message: str = "", turns: int = 12,
               max_chars: int = 2400) -> str:
    """The last few conversation turns from chat.jsonl for the prompt's memory
    section — oldest-first, most-recent kept within the char budget; "" for a
    fresh thread. THIS is what turns a pile of fresh processes into a director
    with memory: "the checklist scene", "yes", "do that" resolve only when the
    turns before them are in the prompt. A trailing user row equal to `message`
    is dropped so the current turn is not double-counted (it is passed
    separately as the user content)."""
    rows = []
    try:
        with open(os.path.join(run_dir, "chat.jsonl")) as f:
            for line in f:
                try:
                    o = json.loads(line)
                except Exception:
                    continue
                role, text = o.get("role"), str(o.get("text") or "").strip()
                if role in ("user", "director") and text:
                    rows.append((role, text))
    except Exception:
        return ""
    if rows and rows[-1] == ("user", (message or "").strip()):
        rows = rows[:-1]
    rows = rows[-turns:]
    kept, used = [], 0
    for role, text in reversed(rows):
        line = ("User: " if role == "user" else "You (the director): ") + text
        if kept and used + len(line) + 1 > max_chars:
            break
        kept.append(line)
        used += len(line) + 1
    kept.reverse()
    return "\n".join(kept)


def _resolve_actions(stops, actions, said):
    """Resolve model actions to CURRENT stops by verbatim title — one source
    of truth for targeting (F7: index-based targeting dropped the wrong beat
    after treatments shifted between rounds). `said` is the set of treatments
    the USER named (see _said_treatments): an applied swap must land on one of
    them, so the director can never invent a treatment. Mutates stops for
    applied drops/swaps; returns (applied, rejected, rerun) where each rejected
    entry is (title, why, kind) — kind in {recording, unnamed_treatment, floor,
    no_beat} steers the honest reply."""
    import proto_walkrec as pw
    vign = _vignettes(stops)
    by_title = {_norm_title(s["title"]): s for s in vign}
    # The recordings — real screen footage — carry titles too but are NOT
    # editable; keep them separate so a request aimed at one gets the honest
    # limit, not a generic "no such beat" (fix #4).
    rec_titles = {_norm_title(s.get("title") or "") for s in stops
                  if s.get("seg")}
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
            if _norm_title(title) in rec_titles:
                rejected.append((title or "(the opening)",
                                 "that's real footage of the site, which I "
                                 "can't cut or restyle", "recording"))
            else:
                rejected.append((title or "(unnamed beat)",
                                 "no beat with that title in the current cut",
                                 "no_beat"))
            continue
        if a.get("action") == "drop":
            s["_drop"] = True
            applied.append(("drop", s["title"]))
        elif a.get("action") == "swap_treatment":
            # THE TREATMENT IS THE USER'S WORD (fix #3, in code): the model may
            # target a beat, but the treatment it swaps to must be one the user
            # actually named — otherwise ASK, never invent.
            req = _canon_treatment(a.get("to", ""))
            if not req or req not in said:
                rejected.append((s["title"],
                                 "no treatment was named for that swap",
                                 "unnamed_treatment"))
                continue
            # Same tie-break the reviewer uses: the floor, plus what the rest
            # of the cut has already spent. `stops` is the current cut, so the
            # index has to be resolved from it rather than from `vign`.
            bi = stops.index(s)
            picked = pw._pick_repair(stops, bi, req)
            # The floor may refuse the treatment outright (_CUT) or only be able
            # to land it on a DIFFERENT treatment (a content-wins downgrade).
            # Either way we do NOT silently apply a treatment the user did not
            # name — decline honestly and let them pick again.
            if picked == pw._CUT or _canon_treatment(picked) not in said:
                rejected.append(
                    (s["title"],
                     f"“{req}” doesn't hold its material floor on this beat",
                     "floor"))
                continue
            s["motif"] = picked
            s["motif_locked"] = True
            applied.append(("swap", s["title"], picked))
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
    for title, why, kind in rejected:
        if kind == "recording":
            vign = _vignettes(stops)
            names = ", ".join(f"“{s['title']}”" for s in vign) or "(none)"
            parts.append(
                f"“{title}” is real footage of your site — I can't cut or "
                f"restyle the recordings, only the graphic beats: {names}.")
        elif kind == "unnamed_treatment":
            parts.append(f"Swap “{title}” to what — a logo wall, a stat pop, "
                         "or a quote card?")
        else:
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


def _local_events(run_dir: str, n: int):
    """The last n events from the local events.jsonl, oldest-first; [] when
    absent/unreadable. The FAST PATH — a warm builder replica holds the run's
    whole event history on disk."""
    try:
        with open(os.path.join(run_dir, "events.jsonl")) as f:
            return [json.loads(l) for l in f][-n:]
    except Exception:
        return []


def _db_events(run_dir: str, n: int):
    """The run's last n agent_events from InsForge, oldest-first; [] when
    off-hosted, empty, or unreachable. Provenance's SURVIVAL PATH across a
    redeploy: events.jsonl is deliberately NOT persisted (workspace_store), so a
    replica that rehydrated a film has none of the build's decide.*/read.*/film.*
    events on disk — but every event was ALSO sinked to public.agent_events
    (run_events._hosted_sink), which outlives the ephemeral container disk.
    Mirrors the sink's own auth/query shape by reusing run_events._if_req, so the
    key never leaves that module and is never echoed here. Single-shot (not the
    retrying variant): a provenance read must degrade fast, never retry into the
    hot path."""
    import run_events as _re
    rid = _re._hosted_run_id(run_dir)
    if not (rid and _re._IF_BASE and _re._IF_KEY):
        return []
    try:
        resp = _re._if_req(
            "GET",
            f"/api/database/records/agent_events?run_id=eq.{rid}"
            f"&select=kind,title,detail&order=seq.desc&limit={int(n)}",
            None, "application/json")
        rows = json.loads(resp.read())
    except Exception:
        return []
    if not isinstance(rows, list):
        return []
    rows.reverse()   # DB returns newest-first; the prompt reads oldest-first
    return rows


def _fmt_events(evts) -> str:
    return "\n".join(
        f"[{e.get('kind')}] {e.get('title')}"
        + (f" — {e['detail'][:90]}" if e.get("detail") else "")
        for e in evts)


def _events_tail(run_dir: str, n: int = 18) -> str:
    """The recent run events for the prompt's provenance section. Local
    events.jsonl is the FAST PATH; when it is absent or thinner than the tail —
    the common case on a replica that rehydrated a film after a redeploy, since
    events.jsonl is not persisted — fall back to the run's agent_events in
    InsForge so a "why did you…" question still has provenance to cite. Same
    tail size either way; "(no events)" only when neither source has any."""
    local = _local_events(run_dir, n)
    if len(local) >= n:
        return _fmt_events(local)
    db = _db_events(run_dir, n)
    if db:
        return _fmt_events(db)
    return _fmt_events(local) if local else "(no events)"


def _log_chat(run_dir: str, role: str, text: str):
    try:
        with open(os.path.join(run_dir, "chat.jsonl"), "a") as f:
            f.write(json.dumps({"ts": round(time.time(), 3), "role": role,
                                "text": text}) + "\n")
    except Exception:
        pass


def _say(run_dir: str, text: str):
    """Speak one director line: narrate it on the bus AND record it in
    chat.jsonl, so the NEXT turn — a fresh process — remembers what was said.
    The hosted path never wrote chat.jsonl before (2026-07-20): the reply was
    emitted to the DB for the UI but never fed back to the model, so every turn
    started amnesiac. This is the write half of that memory; _chat_tail is the
    read half."""
    emit(run_dir, "chat.director", text, "")
    _log_chat(run_dir, "director", text)


def _persist_chat(run_dir: str, run_key: str) -> None:
    """Persist the CONVERSATION DELTA after a turn that wrote only to chat.jsonl
    (a clarification / decline / answer — no re-render). Without this, only
    APPLIED edits persisted (2026-07-20): a worker deploy mid-conversation, then
    a rehydrate on another replica, silently dropped every turn since the last
    edit — so "yes, the checklist one" resolved against a stale thread. The
    edit/build paths persist their own heavier workspace; this covers the turns
    that never reach them. reason="chat" makes workspace_store skip the
    unchanged stops.json + clips, so the delta is chat.jsonl + the manifest (a
    few KB). Best-effort and OFF the reply's critical path — the line is already
    spoken and flushed before this runs, so it only extends the job-hold by the
    upload of those few KB, never the user's perceived latency."""
    try:
        workspace_store.persist(run_dir, run_key, reason="chat")
    except Exception as e:
        print(f"[workspace!] chat persist skipped: {type(e).__name__}: {e}",
              file=sys.stderr)


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
        chat=(_chat_tail(run_dir, message)
              or "(no earlier turns — this is the first message in the thread)"),
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


def _apply_work(run_id: str, run_dir: str, state: dict, actions, said,
                job_id: str = "") -> None:
    """Resolve + gate + apply + re-render, synchronously. The chat reply is
    authored from the OUTCOME (never from intent) and emitted before the
    slow render so the user sees truth immediately. `said` = the treatments the
    user named — the swap guard in _resolve_actions enforces it."""
    import proto_walkrec as pw
    stops, ctx = state["stops"], state["ctx"]
    applied, rejected, rerun = _resolve_actions(stops, actions, said)
    if rerun:
        _say(run_dir,
             "Redoing the whole film — re-reading the site and re-filming "
             "from scratch.")
        emit(run_dir, "run.start", "Director: full re-run requested",
             "Re-reading the site and re-filming from scratch.")
        # FINISH LIKE THE BUILD PATH (build_runner.py): build_tour_film
        # re-reads the site, re-films, and writes a NEW stops.json + clips, then
        # RETURNS the film path WITHOUT delivering it — main()/build_runner own
        # the ship. The director is this rerun's ONLY wrapper, so a bare return
        # (the pre-2026-07-20 bug) renders a film nobody receives. Ship the new
        # cut through the same shipper, announce completion in the same event
        # grammar, flush, then re-persist so the NEXT edit rehydrates THIS
        # re-run, not the pre-rerun cut. A failure inside build_tour_film
        # propagates to _handle_job, which emits run.error and flushes.
        import run_events as _re
        out = pw.build_tour_film(ctx.get("host", ""), run_id)
        _re.ship_final(run_dir, run_id, out)
        emit(run_dir, "run.done", "Film delivered",
             "The re-filmed tour is rendered and shipped.")
        _re.flush_sinks()
        # RERUN CHARGE — DELIBERATELY ABSENT, FLAGGED FOR DENNIS. An applied
        # edit charges EDIT_CREDIT_COST (70); a from-scratch production charges
        # VIDEO_CREDIT_COST (640) at creation (web/app/actions.ts). The web
        # gates a director turn on the EDIT allowance (70), so charging 640 here
        # would admit-at-70 / debit-at-640 — the exact mismatch the
        # EDIT_CREDIT_COST note warns against — and charging 70 would price a
        # full re-production as an edit. No spec defines a rerun price, so NONE
        # is written here (today's free behavior, unchanged) pending Dennis's
        # pricing call: inventing one is worse than leaving the seam visible.
        try:
            workspace_store.persist(run_dir, run_id, reason="edit")
        except Exception as e:
            print(f"[workspace!] rerun persist skipped: "
                  f"{type(e).__name__}: {e}", file=sys.stderr)
        return
    _say(run_dir, _outcome_reply(stops, applied, rejected))
    for title, why, kind in rejected:
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
    # RE-PERSIST (revision++) — the NEXT edit, possibly on another replica after
    # another deploy, must rehydrate THIS cut, not the pre-edit one. AFTER
    # delivery + flush, so it only keeps the job claimed a few seconds longer;
    # only stops.json + the manifest change on a drop/swap (clips are immutable).
    try:
        workspace_store.persist(run_dir, run_id, reason="edit")
    except Exception as e:
        print(f"[workspace!] edit persist skipped: {type(e).__name__}: {e}",
              file=sys.stderr)


def handle_job(run_key: str, insforge_run_id: str, message: str,
               job_id: str = "") -> int:
    """Hosted director turn (claimer job): reply + apply, all through the
    event bus so the workspace narrates it. Returns a process exit code.

    EVERY exit flushes (2026-07-20, found live): the hosted sink posts on
    background threads, and run_events' own contract says callers that end a
    run MUST flush. The build path flushes; the QUICK-REPLY paths below
    returned within a second of their emit, the process died, and the
    customer's thread showed "Thinking..." forever while the director's
    answer sat in a dead thread's buffer. A reply that is not flushed was
    never spoken."""
    try:
        return _handle_job(run_key, insforge_run_id, message, job_id)
    finally:
        import run_events as _re_flush
        _re_flush.flush_sinks()


def _handle_job(run_key: str, insforge_run_id: str, message: str,
                job_id: str = "") -> int:
    run_dir = os.path.join(HERE, "runs", run_key)
    os.makedirs(run_dir, exist_ok=True)
    if insforge_run_id:
        try:
            with open(os.path.join(run_dir, "insforge-run-id"), "w") as f:
                f.write(insforge_run_id)
        except Exception:
            pass
    # REHYDRATE (survives a redeploy): if this replica doesn't already hold the
    # working files — the common case after a deploy, which wipes every
    # container disk — pull the persisted workspace so _load_state finds
    # stops.json and the clips it references. A warm local hit skips the pull.
    # Download lines go to the operator log; the thread narrates the edit
    # itself. Only a truly absent manifest (a film delivered before this
    # shipped) or a failed pull still reaches the honest fallback below.
    if not workspace_store.has_local_workspace(run_dir):
        workspace_store.rehydrate(run_dir, run_key)
    try:
        state = _load_state(run_dir)
    except Exception:
        _log_chat(run_dir, "user", message)
        _say(run_dir,
             "This film's working files were recycled by a redeploy, so I "
             "can't re-cut it in place. Start a new filmo of the same URL "
             "from New filmo — about ten minutes — and ask for this change "
             "while it's fresh.")
        return 0
    try:
        # _parse reads the PRIOR turns from chat.jsonl for its memory; the
        # current user turn is logged just below, AFTER it is read, so it is
        # not double-counted.
        reply, actions = _parse(run_dir, state, message)
    except (Exception, SystemExit) as e:
        _log_chat(run_dir, "user", message)
        _say(run_dir,
             f"I hit a snag reading that ({type(e).__name__}) — try again?")
        _persist_chat(run_dir, run_key)
        return 0
    _log_chat(run_dir, "user", message)
    said = _said_treatments(run_dir, message)
    if not actions:
        # Answers and declines: the model's own voice IS the outcome. _say also
        # records it so the next turn remembers the question it just asked. The
        # chat delta is persisted so a redeploy mid-conversation does not drop
        # this turn (only APPLIED edits persisted before 2026-07-20).
        _say(run_dir, reply)
        _persist_chat(run_dir, run_key)
        return 0
    try:
        _apply_work(run_key, run_dir, state, actions, said, job_id)
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
            said = _said_treatments(run_dir, message)
            applied, rejected, rerun = _resolve_actions(state["stops"],
                                                        actions, said)
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
            for title, why, kind in rejected:
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
