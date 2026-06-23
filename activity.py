#!/usr/bin/env python3
"""Agent activity feed — the CONVERSATION between HERMES (the producer agent) and
NEMOTRON (the planning brain), reconstructed from runs/*/ledger.json.

This is the proof-of-execution view: judges (and Dennis) can watch Hermes hand a
brief to Nemotron, see Nemotron's real plan come back (with the real model, token
counts, and finish_reason), then watch Hermes execute it step by step (pricing,
budget gate, scene production, Stripe payment, stitch, delivery). Every value here
is read from what a build actually wrote — nothing is invented.

Each run becomes an ordered list of `turns`:
  hermes/request   Hermes asks Nemotron to plan THIS brief (url, goal, emphasis)
  nemotron/plan    Nemotron's real response: the scene plan + voiceover + tokens
                   (or nemotron/unavailable when it fell back to a template)
  hermes|stripe/event   Hermes executing the plan, narrated from the ledger events

The dashboard renders these as a chat thread inside the (widened) sidebar. Stdlib
only, plus the sibling brain.py / validate_planner for the human-readable brain
label and the real system prompt. One bad ledger can never break the feed.
"""
import json
import os

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
RUNS_DIR = os.path.join(PROJECT_ROOT, "runs")

# Newest-N runs included (bounded payload; the response flags truncation).
MAX_RUNS = 30
# How much of the 12K-char planner system prompt to ship as a preview.
SYSTEM_PROMPT_PREVIEW_CHARS = 900

try:
    import brain as _brain_mod
    _BRAINS = _brain_mod.BRAINS
except Exception:  # noqa: BLE001
    _BRAINS = {}


def _system_prompt():
    """The REAL standing instructions Hermes gives Nemotron (a preview + length).
    Shown once at the top of the feed so judges see the actual agent contract."""
    try:
        import validate_planner as vp
        sp = getattr(vp, "SYSTEM_PROMPT", "") or ""
    except Exception:  # noqa: BLE001
        sp = ""
    return {
        "preview": sp[:SYSTEM_PROMPT_PREVIEW_CHARS],
        "chars": len(sp),
        "truncated": len(sp) > SYSTEM_PROMPT_PREVIEW_CHARS,
    }


# Keyword -> actor for the execution events. Nemotron cues are checked so the
# plan-decision events can be DROPPED from the execution narration (they're already
# represented by the dedicated nemotron/plan turn); Stripe cues tag the money rail.
_NEMOTRON_CUES = (
    "storyboard decided", "planner", "brain=", "llm plan", "nemotron",
    "plan unavailable", "falling back to deterministic", "re-planned",
)
_STRIPE_CUES = (
    "stripe", "payment link", "issuing", "spending_limit", "spending limit",
    "authorization", "authoriz", "provision", "earn", "cardholder",
    "virtual card", " card ", "charge", "payout", "checkout",
)


def _classify(msg):
    m = (msg or "").lower()
    for cue in _NEMOTRON_CUES:
        if cue in m:
            return "nemotron"
    for cue in _STRIPE_CUES:
        if cue in m:
            return "stripe"
    return "hermes"


def _brand_of(ledger):
    url = ((ledger.get("job") or {}).get("company_url") or "").strip()
    if not url:
        return ledger.get("run_id") or "unknown"
    for pre in ("https://", "http://"):
        if url.startswith(pre):
            url = url[len(pre):]
    return url.rstrip("/").split("/")[0] or url


def _brain_label(brain_key):
    rec = _BRAINS.get(brain_key or "")
    return (rec.get("label") if rec else None) or brain_key or "—"


def _read_ledger(run_dir):
    p = os.path.join(run_dir, "ledger.json")
    if not os.path.exists(p):
        return None
    try:
        with open(p) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _request_text(job, quality):
    """What Hermes asks Nemotron — built from the real brief."""
    dur = job.get("target_duration_s")
    goal = (job.get("goal") or "a brand video").strip()
    emph = (job.get("emphasis") or "").strip()
    q = (quality or "standard").strip()
    head = "Plan a %s%s video for %s." % (
        (str(int(dur)) + "s ") if dur else "", q, _brand_of({"job": job}))
    parts = [head, "Goal: %s." % goal]
    if emph:
        parts.append("Emphasize: %s." % emph)
    parts.append("Return a strict JSON scene plan with a scene-aligned voiceover.")
    return " ".join(parts)


def _voiceover_script(ledger):
    vo = ledger.get("voiceover") or {}
    s = vo.get("script")
    if not s:
        s = ((ledger.get("plan") or {}).get("voiceover") or {}).get("script")
    return s or ""


def _plan_turn(ledger, sel, tokens):
    """Nemotron's real response turn (or the template-fallback turn)."""
    llm = sel.get("plan_source") == "llm"
    brain_label = _brain_label(sel.get("brain"))
    if not llm:
        return {
            "from": "nemotron", "kind": "unavailable", "brain": brain_label,
            "text": "No usable plan returned — Hermes fell back to a deterministic "
                    "template so the build still ships.",
        }
    scenes = ledger.get("scenes") or []
    types = [s.get("type") for s in scenes if isinstance(s, dict)]
    script = _voiceover_script(ledger)
    beats = len([b for b in script.split(".") if b.strip()]) if script else len(types)
    summary = "Returned a %d-scene plan (%s) with a %d-beat voiceover." % (
        len(types), ", ".join(types) if types else "—", beats)
    return {
        "from": "nemotron", "kind": "plan", "brain": brain_label,
        "finish_reason": sel.get("finish_reason"),
        "tokens": tokens,
        "scenes": types,
        "script": script,
        "text": summary,
    }


def _run_entry(ledger):
    sel = ledger.get("selection") or {}
    job = ledger.get("job") or {}
    usage = sel.get("planner_usage") or {}
    tokens = {
        "prompt": usage.get("prompt_tokens"),
        "completion": usage.get("completion_tokens"),
        "total": usage.get("total_tokens"),
    }
    turns = [
        {"from": "hermes", "kind": "request", "text": _request_text(job, sel.get("quality"))},
        _plan_turn(ledger, sel, tokens),
    ]
    # Execution narration: the ledger events, EXCLUDING the plan-decision events the
    # plan turn already represents. Tagged hermes (orchestration) or stripe (money).
    for e in (ledger.get("events") or []):
        msg = e.get("msg") or ""
        actor = _classify(msg)
        if actor == "nemotron":
            continue  # already shown as the nemotron/plan turn
        turns.append({"from": actor, "kind": "event",
                      "level": e.get("level") or "info", "text": msg})
    return {
        "run_id": ledger.get("run_id"),
        "brand": _brand_of(ledger),
        "created_at": ledger.get("created_at"),
        "status": ledger.get("status"),
        "mode": ledger.get("mode"),
        "brain_key": sel.get("brain"),
        "brain_label": _brain_label(sel.get("brain")),
        "plan_source": sel.get("plan_source"),
        "tokens": tokens,
        "turns": turns,
    }


def feed(max_runs=MAX_RUNS):
    """Newest-first agent conversations across all runs + token rollups.
    {generated_at, truncated, system_prompt, totals, runs:[{...,turns:[...]}]}."""
    try:
        names = os.listdir(RUNS_DIR)
    except OSError:
        names = []

    ledgers = []
    for name in names:
        run_dir = os.path.join(RUNS_DIR, name)
        if not os.path.isdir(run_dir):
            continue
        led = _read_ledger(run_dir)
        if led:
            ledgers.append(led)

    ledgers.sort(key=lambda d: d.get("created_at") or 0, reverse=True)
    truncated = len(ledgers) > max_runs
    runs = [_run_entry(l) for l in ledgers[:max_runs]]

    nemotron_calls = sum(1 for r in runs if r.get("plan_source") == "llm")
    nemotron_tokens = sum((r["tokens"].get("total") or 0) for r in runs)
    turn_count = sum(len(r["turns"]) for r in runs)

    return {
        "generated_at": _now(),
        "truncated": truncated,
        "system_prompt": _system_prompt(),
        "totals": {
            "builds": len(ledgers),
            "builds_shown": len(runs),
            "nemotron_calls": nemotron_calls,
            "nemotron_tokens": nemotron_tokens,
            "turns": turn_count,
        },
        "runs": runs,
    }


def _now():
    import time
    return time.time()


if __name__ == "__main__":
    print(json.dumps(feed(max_runs=2), indent=1)[:2600])
