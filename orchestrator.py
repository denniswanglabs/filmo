#!/usr/bin/env python3
"""Producer-brain orchestrator — brief/plan -> priced, budget-governed video -> P&L.

This is the deterministic Python harness for the producer-brain SKILL flow. It is
the reference implementation of "the right thing to do": the test suite asserts
against it, and a live Hermes/Nemotron run should reproduce its gate verdicts.

It runs the whole loop and writes a run LEDGER (runs/<run_id>/ledger.json) that the
dashboard reads:

  PLAN      validate the scene plan (plan_schema)
  PRICE     producer.py estimate  -> COGS, suggested price, LOCKED production budget
  EARN      stripe_money.earn     -> test Payment Link, or DEV MODE
  PROVISION stripe_money card     -> Issuing spending_limit = budget (or simulated)
  PRODUCE   each scene IN ORDER under the budget gate:
              free  (title/motion_graphic/walkthrough) -> produce, $0, no gate
              paid  (cinematic) -> producer.py gate -> approve / downgrade / decline
                                   + a Stripe authorization (the physical decline)
  VOICEOVER gate the VO spend too; synthesize via edge-tts (mock) / ElevenLabs (real)
  STITCH    ffmpeg concat + VO mux -> final MP4 (REAL in both modes)
  DELIVER   P&L: price vs actual COGS, the auto-declined line, net margin

Modes:
  --mode mock  (default) ZERO money: real free Higgsfield cost preview for pricing
               (or PRODUCER_COST_STUB for offline determinism), mock generation,
               edge-tts VO, real ffmpeg stitch.
  --mode real  the genuine paid pipeline.

Stdlib only.
"""

import argparse
import json
import os
import subprocess
import sys
import threading
import time

import adapters
import ledger as ledger_mod
import pricing as pricing_mod
import remotion_codegen
import stripe_money
from plan_schema import validate_plan, resolve_vo_beats, vo_script_from_beats

HERE = os.path.dirname(os.path.abspath(__file__))
PRODUCER = os.path.join(HERE, "producer.py")

FREE_TYPES = {"title", "motion_graphic", "walkthrough", "screenshot"}

# Premium pricing MENU flag (mirrors producer._premium_menu_enabled + the
# pricing-foundation handoff). Default OFF -> the produce loop + ledger are
# byte-identical to the pre-premium behavior: no watermark toggle, no format
# pack, no VO-engine override, no premium ledger block. ALL new produce-side
# behavior in this module is gated on premium_menu_enabled().
PREMIUM_MENU_ENV = "WS_PREMIUM_MENU"


def premium_menu_enabled():
    """True iff env WS_PREMIUM_MENU is a truthy flag ('1'/'true'/'yes'/'on')."""
    return os.environ.get(PREMIUM_MENU_ENV, "").strip().lower() in ("1", "true", "yes", "on")

# Parallelism (default ON; opt out with HERMES_PARALLEL=0). The walkthrough scene's
# generation — the slowest + flakiest segment, and FREE + independent of the budget
# gate — is kicked off in a background thread at the TOP of the produce loop and
# joined when the loop reaches its slot, removing it from the critical path. The
# budget gate, money.authorize(), active_budget.json writes, ledger `spent`
# accounting, and per-scene decision order ALWAYS stay serial and in scene order;
# only the off-budget walkthrough GENERATION runs off-thread. See orchestrate().
PARALLEL_ENV = "HERMES_PARALLEL"


def parallel_enabled():
    # Default ON (validated in real mode: ~2x speedup, threaded walk-agent confirmed
    # end-to-end, with failure-isolation + stitch normalization as safety nets).
    # Opt out with HERMES_PARALLEL=0 (also: false/no/off).
    return (os.environ.get(PARALLEL_ENV) or "").strip().lower() not in ("0", "false", "no", "off")


class _BgGen(threading.Thread):
    """Run one generation callable off-thread, capturing its result OR exception.

    Used only for FREE, budget-independent generation (the walkthrough), so nothing
    money-related ever runs here. join() then result_or_raise() reproduces the exact
    same return value / exception the inline call would have produced — the produce
    loop consumes it at the scene's slot, so the visible failure-isolation behavior
    is identical whether the flag is on or off.
    """

    def __init__(self, fn):
        super().__init__(daemon=True)
        self._fn = fn
        self.result = None
        self.exc = None

    def run(self):
        try:
            self.result = self._fn()
        except BaseException as e:  # noqa: BLE001 — re-raised on the main thread
            self.exc = e

    def result_or_raise(self):
        if self.exc is not None:
            raise self.exc
        return self.result

# The orchestrator↔webhook budget bridge. stripe_webhook.py reads the LIVE budget
# from runs/active_budget.json -> {"budget_cents": N, "spent_cents": M} and decides
# approve/decline against (budget - spent) for each incoming issuing_authorization.
# The orchestrator MUST externalize its locked budget + running spend here, or the
# listener would decide against {0,0}. We write it at budget-lock and refresh it
# right before every money.authorize() so the webhook (when live) evaluates each
# charge against the SAME numbers the in-process brain just used — making an
# over-budget cinematic charge produce a REAL declined issuing_authorization whose
# reason is the brain's own verdict (webhook_declined), no human in the loop.
ACTIVE_BUDGET_FILENAME = "active_budget.json"


def write_active_budget(runs_dir, budget_cents, spent_cents):
    """Externalize the live budget state for stripe_webhook.py.

    Path is <runs_dir>/active_budget.json. In a normal run runs_dir is HERE/runs,
    which is exactly stripe_webhook.STATE_DEFAULT, so the listener picks it up with
    no flag. Tests point the webhook at the temp path via --state / state_path.
    Written atomically (tmp + os.replace) so the 2-second webhook read never sees a
    half-written file.
    """
    os.makedirs(runs_dir, exist_ok=True)
    path = os.path.join(runs_dir, ACTIVE_BUDGET_FILENAME)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump({"budget_cents": int(budget_cents), "spent_cents": int(spent_cents)}, f)
    os.replace(tmp, path)
    return path


def run_producer(subcmd_args):
    """Call producer.py and return parsed JSON (inherits PRODUCER_COST_STUB env)."""
    proc = subprocess.run([sys.executable, PRODUCER, *subcmd_args],
                          capture_output=True, text=True, timeout=300, check=False)
    if proc.returncode != 0:
        raise RuntimeError("producer.py %s failed: %s" % (subcmd_args[:2], proc.stderr.strip()))
    return json.loads(proc.stdout)


def estimate(plan_path):
    return run_producer(["estimate", "--plan", plan_path])


def gate(plan_path, scene_id, proposed_cents, spent_cents, budget_cents):
    return run_producer(["gate", "--plan", plan_path, "--scene", scene_id,
                         "--proposed_cost_cents", str(proposed_cents),
                         "--spent_cents", str(spent_cents),
                         "--budget_cents", str(budget_cents)])


def preview_cost_for_model(plan, scene_id, model, work_dir):
    """Re-price one scene under a different model via a patched temp plan."""
    patched = json.loads(json.dumps(plan))
    for s in patched["scenes"]:
        if s["id"] == scene_id:
            s["model"] = model
    p = os.path.join(work_dir, "_patched_%s.json" % scene_id)
    with open(p, "w") as f:
        json.dump(patched, f)
    est = estimate(p)
    for s in est["scenes"]:
        if s["id"] == scene_id:
            return s["est_cost_cents"], p
    return 0, p


def orchestrate(plan, run_id, mode="mock", runs_dir=None, vo_provider="edge",
                stripe_live=False, now=None, do_stitch=True, overlays="mock",
                earn=None):
    runs_dir = runs_dir or os.path.join(HERE, "runs")
    run_dir = os.path.join(runs_dir, run_id)
    clips_dir = os.path.join(run_dir, "clips")
    os.makedirs(clips_dir, exist_ok=True)

    job = plan["job"]
    led = ledger_mod.Ledger(run_id, job, mode, now=now)
    # studio overlays = the agent renders real Remotion (and writes the title/MG
    # code on camera). DECOUPLED from mode: the white, brand-authored CARD scenes
    # (title / motion_graphic) render in EVERY mode now, so real-mode builds no
    # longer fall back to the flat orange synth placeholder. Real MEDIA scenes
    # (walkthrough / cinematic) still branch on `mode` below — in real mode they
    # run the genuine walk-agent / Higgsfield generators, NOT the studio
    # placeholder — so this flag never suppresses real-asset generation.
    # The palette comes from the CLIENT brand (style = genre).
    studio_active = (overlays == "studio")
    palette = remotion_codegen.palette_for(job.get("company_url"))
    if studio_active:
        led.data["overlays"] = "studio"
        led.data["brand_palette"] = palette

    # Live console plumbing: the ledger is written after every step so a polling
    # UI can watch the build progress. PRODUCER_PACE adds a watchable beat between
    # state changes (0 in tests; ~1s for the live console so scenes don't blink by).
    led_path = os.path.join(run_dir, "ledger.json")
    pace = float(os.environ.get("PRODUCER_PACE") or 0)

    def flush():
        led.write(led_path)

    def beat():
        if pace > 0:
            time.sleep(pace)

    # Persist the full storyboard the agent decided on, so the polling console can
    # show the SCRIPT (VO narration + ordered scene breakdown) the moment planning
    # completes — "watch the agent write the script before it shoots it." A trimmed
    # projection (not the raw plan) keeps the ledger lean; it stays through the build.
    vo_plan = plan.get("voiceover") or {}
    # Resolve narration into per-scene beats (new schema) or fall back to splitting
    # a legacy single script. The console still shows a flat `script` (derived from
    # the beats), plus the beats themselves so the storyboard can show line-per-scene.
    plan_beats = resolve_vo_beats(plan)
    vo_script_proj = vo_plan.get("script") or vo_script_from_beats(plan_beats)
    led.data["plan"] = {
        "voiceover": {"script": vo_script_proj, "voice": vo_plan.get("voice"),
                      "beats": plan_beats},
        "scenes": [{"id": s.get("id"), "type": s.get("type"), "model": s.get("model"),
                    "duration_s": s.get("duration_s"), "brief": s.get("brief", "")}
                   for s in plan.get("scenes", [])],
    }

    led.set_phase("planning")
    led.event("info", "storyboard decided: %d scenes, %d narration beats (%d chars)"
              % (len(plan.get("scenes", [])), len(plan_beats), len(vo_script_proj)))
    flush()

    # -- PLAN: validate -----------------------------------------------------
    problems = validate_plan(plan)
    if problems:
        led.set_status("failed")
        led.event("error", "plan failed validation", problems=problems)
        led.write(os.path.join(run_dir, "ledger.json"))
        raise ValueError("invalid plan: " + "; ".join(problems))
    led.event("info", "plan validated: %d scenes" % len(plan["scenes"]))

    # Ensure the on-disk plan carries a flat `script` derived from the beats, so
    # the cost estimator (producer.py) and any legacy reader still see the full
    # narration. The beats stay authoritative for placement; this is a mirror.
    if plan_beats and not (plan.get("voiceover") or {}).get("script"):
        plan.setdefault("voiceover", {})["script"] = vo_script_from_beats(plan_beats)

    plan_path = os.path.join(run_dir, "plan.json")
    with open(plan_path, "w") as f:
        json.dump(plan, f, indent=2)

    # -- PRICE: lock the budget --------------------------------------------
    est = estimate(plan_path)
    budget = est["production_budget_cents"]
    price = est["suggested_price_cents"]
    led.set_pricing(est)
    led.event("info", "priced: COGS %dc, price %sc, budget LOCKED at %dc"
              % (est["total_cogs_cents"], price, budget))
    per_scene_est = {s["id"]: s["est_cost_cents"] for s in est["scenes"]}

    # -- COST-PLUS PRICING (flag-gated): resolve the customer SELECTION + the
    # cost-plus quote producer.cmd_estimate already attached to `est`, then drive
    # the ONE customer choice — QUALITY (standard | premium) — below. OFF path =
    # everything stays None/default so the loop is byte-identical to pre-premium.
    # The SACRED budget gate + Stripe authorize sequence is UNTOUCHED — `budget`/
    # `price` already came out of the cost-plus quote via producer; here we only
    # gate the produce STACK (premium = Higgsfield cinematic + ElevenLabs VO;
    # standard = Remotion designed scene + edge-tts) and itemize the ledger.
    #
    # QUALITY changes WHAT the agent produces:
    #   * standard -> NO Higgsfield: cinematic scenes fall back to a free Remotion/
    #     designed scene (or are skipped); VO = free edge-tts. Cheapest, $5 floor.
    #   * premium  -> cinematic scenes use real Higgsfield (--mode real) + the VO
    #     uses a natural ElevenLabs STOCK voice (--mode real). Richer, ~$6-9.
    # In MOCK ($0 default) BOTH stay $0 — premium just records the upgrade and falls
    # back to free engines (no real spend) so the demo never costs money.
    #
    # The retired tier/booster behaviors (watermark, multi_format, founder_voice
    # clone, rush) are NO LONGER selected — their produce-side code remains in this
    # module + adapters.py as DORMANT helpers, but the active cost-plus path never
    # turns them on. `watermark`/`boosters` are kept as empty/false markers so the
    # rest of the loop reads byte-identical defaults.
    premium = premium_menu_enabled()
    selection = None
    menu = None
    boosters = set()       # retired; always empty in the active cost-plus flow
    quality = "standard"   # the ONE customer choice; default standard
    quality_premium = False  # convenience: True iff quality == "premium"
    if premium:
        # `selection`/`menu`/`quality` come from cmd_estimate (WS_PREMIUM_MENU is on
        # for the subprocess too, inherited via env). Fall back to the plan's
        # selection / the default so the produce side never crashes if a reader omits.
        selection = est.get("selection") or plan.get("selection") or pricing_mod.default_selection()
        menu = est.get("menu")
        quality = est.get("quality") or pricing_mod.quality_from_selection(selection)
        quality_premium = (quality == "premium")
        # No tiers, no watermark, no booster pack in the cost-plus model.
        watermark_on = False
        led.data["premium"] = {
            "enabled": True,
            "model": "cost_plus",
            "quality": quality,
            "selection": selection,
            "watermark": watermark_on,
            "menu": menu,
            "line_items": (menu or {}).get("line_items"),
        }
        led.event("info", "COST-PLUS: quality=%s (price %sc, COGS %sc)"
                  % (quality, (menu or {}).get("total_price_cents"),
                     (menu or {}).get("total_cogs_cents")))
    led.set_phase("pricing")
    # Bridge: externalize the just-locked budget (spent=0) so a live
    # stripe_webhook.py decides against the real ceiling, not {0,0}.
    write_active_budget(runs_dir, budget, 0)
    flush()

    # Production-time cost overrides (a test lever; models a real Higgsfield cost
    # coming in higher than the planning estimate, which is what triggers a
    # downgrade/decline since budget == planned COGS by construction). JSON map
    # {scene_id: cents, "__voiceover__": cents}. Empty/unset = costs match the plan.
    try:
        prod_override = json.loads(os.environ.get("PRODUCER_PRODUCTION_COST_STUB") or "{}")
    except (ValueError, json.JSONDecodeError):
        prod_override = {}

    # -- EARN ---------------------------------------------------------------
    led.set_phase("earning")
    flush()
    money = stripe_money.StripeMoney(live=stripe_live)
    if earn is not None:
        # Pre-production payment gate already cleared upstream (build_runner): the
        # customer paid a real test-mode Checkout Session before production began.
        # Preserve that earn block (session id + payment_status:"paid") rather than
        # minting a fresh Payment Link, so the final ledger reflects the real charge.
        led.set_earn(earn)
        if earn.get("payment_status") == "paid":
            led.event("money", "EARN: payment received via Stripe Checkout",
                      session_id=earn.get("session_id"))
        else:
            led.event("info", "EARN: pre-paid earn block carried in (status %s)"
                      % earn.get("payment_status"))
    else:
        earn = money.earn(price, job.get("currency", "usd"), job.get("goal", ""))
        led.set_earn(earn)
        if earn.get("status") == "dev_mode":
            led.event("info", "EARN: DEV MODE — no Stripe key, payment gate skipped")
        elif earn.get("status") == "awaiting_payment":
            led.event("money", "EARN: Stripe Payment Link created", payment_link=earn.get("payment_link"))

    card = money.provision_card(budget, job.get("currency", "usd"))
    led.set_card(card)

    # Pre-list every scene as 'queued' so the live storyboard pops them up before
    # the agent starts working each one.
    for i, s in enumerate(plan["scenes"]):
        led.upsert_scene({"id": s["id"], "type": s["type"], "order": i,
                          "brief": s.get("brief", ""), "model": s.get("model"),
                          "duration_s": s.get("duration_s"), "status": "queued",
                          "decision": None, "output_path": None})
    led.set_phase("producing")
    flush()

    # -- PRODUCE ------------------------------------------------------------
    spent = 0
    clips = []  # (order, path) for scenes that produced a clip
    warnings = []  # scenes that FAILED but were isolated so the run still ships
    shot_counter = 0  # 0-based index among screenshot scenes -> shot-NN.png mapping

    def _walkthrough_gen(scene, out):
        """The walkthrough's generation call, as a closure (so it can run inline OR
        off-thread). Walkthrough generation is MODE-INDEPENDENT: it always calls
        generate_walkthrough, which honors WS_WALKTHROUGH_CACHE (a cached mp4 clip,
        the $0/no-NIM verify path), else runs the GENUINE walk_native capture in BOTH
        mock and real mode. A $0 mock build now produces the SAME real per-brand
        walkthrough a paying Standard customer gets — mock and real differ only in
        payment (mock keeps PRODUCER_SIMULATE_PAID) and brain ($0 super-free), not in
        the walkthrough asset. The synth color card is a last-resort fallback (mock
        only) reached inside generate_walkthrough when the native capture fails.
        FREE + budget-independent — safe to background."""
        # Thread run_dir so the native capture (walk_native.py) streams its live
        # screencast into <run_dir>/walk/. Returns None (graceful skip) if the native
        # capture fails in real mode, or a brand-tinted placeholder (placeholder:True)
        # on a mock-mode native failure — both handled at the walkthrough slot below
        # (non-fatal): the None/placeholder gate drops the scene + its VO beat.
        # Thread the run's BRAND ACCENT so any last-resort synthesized placeholder card
        # is colored with the brand instead of the fixed generic teal (no-op for real
        # captures — generate_walkthrough only uses accent_hex on its synth fallback).
        return adapters.generate_walkthrough(scene, out, mode,
                                             job_url=job.get("company_url"),
                                             run_dir=run_dir,
                                             accent_hex=palette.get("accent"))

    # PARALLEL (opt-in): kick off the slow/flaky walkthrough generation NOW so it
    # overlaps the other scenes. Only GENERATION is off-thread — the walkthrough is
    # FREE and never touches the budget gate, so no money path moves off the main
    # thread. Result/exception is consumed at the walkthrough's own loop slot, where
    # the SAME failure-isolation as the serial path applies.
    bg_walk = {}  # idx -> (_BgGen, out_path)
    if parallel_enabled():
        for w_idx, w_scene in enumerate(plan["scenes"]):
            if w_scene["type"] == "walkthrough":
                w_out = os.path.join(clips_dir, "%02d_%s.mp4" % (w_idx, w_scene["id"]))
                t = _BgGen(lambda s=w_scene, o=w_out: _walkthrough_gen(s, o))
                t.start()
                bg_walk[w_idx] = (t, w_out)
        if bg_walk:
            led.event("info", "PARALLEL: walkthrough generation kicked off off-thread "
                      "(%d scene(s)) — overlapping the remaining scenes"
                      % len(bg_walk))
            flush()

    for idx, scene in enumerate(plan["scenes"]):
        sid = scene["id"]
        stype = scene["type"]
        rec = {"id": sid, "type": stype, "order": idx, "brief": scene.get("brief", ""),
               "model": scene.get("model"), "duration_s": scene.get("duration_s"),
               "spent_before_cents": spent}

        # mark this scene 'working' so the live console shows the agent on it
        led.upsert_scene({"id": sid, "type": stype, "order": idx, "brief": scene.get("brief", ""),
                          "model": scene.get("model"), "duration_s": scene.get("duration_s"),
                          "status": "working", "decision": None, "output_path": None})
        flush()
        beat()

        if stype in FREE_TYPES:
            out = os.path.join(clips_dir, "%02d_%s.mp4" % (idx, sid))
            studio_block = None
            try:
                if studio_active and stype in ("title", "motion_graphic"):
                    info = adapters.studio_overlay(scene, out, palette)   # the agent CODES it
                    studio_block = info
                    led.event("info", "STUDIO scene %r (%s): agent wrote %d lines of Remotion, "
                              "rendered in %dms" % (sid, info["archetype"], info["code_lines"], info["render_ms"]))
                elif stype == "walkthrough":
                    # Join the off-thread generation if we backgrounded it; else run
                    # it inline. result_or_raise() reproduces the exact inline result
                    # or exception, so isolation below is identical either way.
                    if idx in bg_walk:
                        t, out = bg_walk[idx]
                        t.join()
                        info = t.result_or_raise()
                    else:
                        info = _walkthrough_gen(scene, out)
                    # NON-FATAL skip: native real-mode capture returns None when it
                    # could not produce a clip (deadlock-proof: it never raises/hangs).
                    # Drop just this scene — append NO clip — and continue so the build
                    # still stitches the survivors. A paid build always ships SOMETHING.
                    if info is None:
                        rec.update({"decision": "skip", "status": "skipped",
                                    "tool": adapters_tool(stype),
                                    "preview_cost_cents": 0, "spent_cents": 0,
                                    "remaining_after_cents": budget - spent,
                                    "final_model": None, "output_path": None,
                                    "stripe_authorization": None, "studio": None,
                                    "note": "walkthrough capture unavailable — scene dropped"})
                        warnings.append({"id": sid, "type": stype,
                                         "error": "walkthrough capture skipped (non-fatal)"})
                        led.event("info", "WALKTHROUGH scene %r skipped — native "
                                  "capture unavailable; run continues without it" % sid)
                        led.upsert_scene(rec)
                        flush()
                        continue
                    # PLACEHOLDER GUARD ($0 fallback): when a build INTENDED a genuine
                    # per-brand walkthrough, a walkthrough that came back as a synthetic
                    # placeholder (the last-resort synth card or a studio storyboard
                    # frame) is NOT a real capture — so shipping it would play the
                    # brand's real-walkthrough VO over generic footage (the
                    # audio<->visual mismatch). Drop the scene the same way a failed
                    # native capture is dropped; the narrated VO beat then drops
                    # automatically (it is keyed off produced clips, so a scene with no
                    # clip never gets its beat). This is a CLEAN skip, not a warning —
                    # the real-capture path simply fell back.
                    #
                    # A build INTENDED a real walkthrough whenever the native capture
                    # ran: ALWAYS in real mode, and in MOCK for every real product build
                    # (build_runner sets WS_WALKTHROUGH_NATIVE=1). So mock now behaves
                    # like standard — a placeholder/failed walkthrough drops its scene +
                    # VO in mock too.
                    #   * offline test mock (no flag): the synth card is by-design (the
                    #     $0 orchestrator-judgment build never shipped to a customer) —
                    #     KEEP it, so those tests still ship the mock walkthrough.
                    #   * real native capture  -> info["placeholder"] is False -> KEEP.
                    #   * cached proven capture -> info["placeholder"] is False -> KEEP.
                    intended_real_walkthrough = (
                        mode == "real"
                        or bool((os.environ.get("WS_WALKTHROUGH_NATIVE") or "").strip()))
                    if (intended_real_walkthrough and isinstance(info, dict)
                            and info.get("placeholder")):
                        rec.update({"decision": "skip", "status": "skipped",
                                    "tool": adapters_tool(stype),
                                    "preview_cost_cents": 0, "spent_cents": 0,
                                    "remaining_after_cents": budget - spent,
                                    "final_model": None, "output_path": None,
                                    "stripe_authorization": None, "studio": None,
                                    "note": "walkthrough was a placeholder (no real "
                                            "capture) — scene + its VO beat dropped so "
                                            "the brand narration never plays over "
                                            "generic footage"})
                        led.event("info", "WALKTHROUGH scene %r dropped — only a "
                                  "placeholder was produced (no genuine capture); its "
                                  "narrated VO beat is dropped with it so the brand VO "
                                  "never narrates generic footage" % sid)
                        led.upsert_scene(rec)
                        flush()
                        continue
                    if studio_active:
                        studio_block = info
                elif stype == "screenshot":
                    # FREE + mode-independent: build a clip from the real captured
                    # shot-NN.png (the apple-screenshot proof beat). The customer-facing
                    # picture is the VO-engine Timeline render (same PNG in a branded
                    # browser card); this orchestrator clip is bookkeeping. Pass the
                    # 0-based screenshot index so the Nth screenshot scene maps to
                    # shot-NN. Never-blank: synth card if no capture.
                    sc = dict(scene, _shot_index=shot_counter)
                    info = adapters.generate_screenshot_clip(sc, out, mode)
                    shot_counter += 1
                    if studio_active:
                        studio_block = info
                else:
                    info = adapters.generate_overlay(scene, out, mode,
                                                     company_url=job.get("company_url"))
            except Exception as e:  # noqa: BLE001 — isolate one scene's failure
                _isolate_failed_scene(led, rec, sid, stype, e, budget, spent,
                                      warnings, flush)
                continue
            rec.update({"decision": "free", "tool": adapters_tool(stype),
                        "preview_cost_cents": 0, "spent_cents": 0,
                        "remaining_after_cents": budget - spent,
                        "final_model": None, "status": "produced",
                        "output_path": rel(out, run_dir), "stripe_authorization": None,
                        "studio": studio_block})
            clips.append((idx, out))
            led.event("info", "FREE scene %r (%s) produced — $0" % (sid, stype))
            led.upsert_scene(rec)
            flush()
            continue

        if stype != "cinematic":
            rec.update({"decision": "skip", "status": "skipped",
                        "spent_cents": 0, "remaining_after_cents": budget - spent})
            led.upsert_scene(rec)
            continue

        # -- STANDARD quality: NO Higgsfield. A cinematic scene falls back to a
        # free designed Remotion scene (studio-authored motion-graphics in studio
        # mode, else a designed overlay card) — never the paid Higgsfield path and
        # never the budget gate. This keeps standard at $0/floor and deterministic.
        # (Gated on `premium` so the flag-OFF path is byte-identical: when the menu
        # is OFF, `quality_premium` stays False but `premium` is False too, so this
        # branch is skipped and the original paid path runs unchanged.)
        if premium and not quality_premium:
            out = os.path.join(clips_dir, "%02d_%s.mp4" % (idx, sid))
            studio_block = None
            try:
                if studio_active:
                    studio_block = adapters.studio_overlay(scene, out, palette)
                else:
                    adapters.generate_overlay(dict(scene, type="motion_graphic"), out,
                                              mode, company_url=job.get("company_url"))
            except Exception as e:  # noqa: BLE001 — isolate one scene's failure
                _isolate_failed_scene(led, rec, sid, stype, e, budget, spent,
                                      warnings, flush)
                continue
            rec.update({"decision": "standard", "tool": "motion-graphics",
                        "preview_cost_cents": 0, "spent_cents": 0,
                        "remaining_after_cents": budget - spent,
                        "final_model": None, "status": "produced",
                        "output_path": rel(out, run_dir), "stripe_authorization": None,
                        "studio": studio_block})
            clips.append((idx, out))
            led.event("info", "STANDARD scene %r (cinematic -> designed Remotion, no "
                      "Higgsfield) produced — $0" % sid)
            led.upsert_scene(rec)
            flush()
            continue

        # -- PAID cinematic scene: gate before spending --------------------
        planned = per_scene_est.get(sid, 0)
        preview = int(prod_override.get(sid, planned))
        if preview != planned:
            rec["cost_overrun_cents"] = preview - planned
            led.event("info", "scene %r production cost %dc vs planned %dc (overrun %+dc)"
                      % (sid, preview, planned, preview - planned))
        verdict = gate(plan_path, sid, preview, spent, budget)
        decision = verdict["decision"]
        remaining = verdict["remaining_budget_cents"]
        led.event("gate", "GATE %r: %s — %s" % (sid, decision.upper(), verdict["reason"]),
                  scene=sid, proposed_cents=preview, remaining_cents=remaining)

        if decision == "approve":
            # Bridge: refresh live budget (committed `spent` so far) so a live
            # webhook decides this charge against the same remaining the brain saw.
            write_active_budget(runs_dir, budget, spent)
            auth = money.authorize(preview, remaining, "approve", card.get("card_id"))
            out = os.path.join(clips_dir, "%02d_%s.mp4" % (idx, sid))
            studio_block = None
            # The charge is already authorized; the spend is committed regardless of
            # whether generation then succeeds. Isolate a generation failure so it
            # marks THIS scene failed (with the auth + spend recorded) and the run
            # still ships the rest — never aborting the loop.
            spent += preview
            try:
                if studio_active and mode == "mock":
                    studio_block = adapters.studio_placeholder(scene, out, palette)
                else:
                    # Real mode: the gate already paid — generate the genuine
                    # Higgsfield clip (studio overlays decoupling never replaces
                    # a budgeted real cinematic asset with a placeholder).
                    adapters.generate_cinematic(scene, out, mode, company_url=job.get("company_url"))
            except Exception as e:  # noqa: BLE001 — isolate one scene's failure
                _isolate_failed_scene(led, rec, sid, stype, e, budget, spent,
                                      warnings, flush,
                                      extra={"decision": "approve", "spent_cents": preview,
                                             "preview_cost_cents": preview,
                                             "stripe_authorization": auth})
                continue
            rec.update({"decision": "approve", "tool": "higgsfield-scene",
                        "preview_cost_cents": preview, "spent_cents": preview,
                        "final_model": scene.get("model"),
                        "remaining_after_cents": budget - spent,
                        "status": "produced", "output_path": rel(out, run_dir),
                        "stripe_authorization": auth, "studio": studio_block})
            clips.append((idx, out))
            led.event("spend", "SPENT %dc on %r (%s) — remaining %dc"
                      % (preview, sid, scene.get("model"), budget - spent))

        elif decision == "downgrade":
            cheaper = verdict["suggested_cheaper_model"]
            new_cost, patched_path = preview_cost_for_model(plan, sid, cheaper, run_dir)
            verdict2 = gate(patched_path, sid, new_cost, spent, budget)
            led.event("gate", "RE-GATE %r after downgrade to %s: %s"
                      % (sid, cheaper, verdict2["decision"].upper()),
                      scene=sid, proposed_cents=new_cost,
                      remaining_cents=verdict2["remaining_budget_cents"])
            if verdict2["decision"] == "approve":
                write_active_budget(runs_dir, budget, spent)
                auth = money.authorize(new_cost, verdict2["remaining_budget_cents"],
                                       "approve", card.get("card_id"))
                out = os.path.join(clips_dir, "%02d_%s.mp4" % (idx, sid))
                studio_block = None
                # Charge authorized -> commit spend, then isolate any generation
                # failure so the run still ships the rest.
                spent += new_cost
                try:
                    if studio_active and mode == "mock":
                        studio_block = adapters.studio_placeholder(
                            dict(scene, model=cheaper), out, palette)
                    else:
                        # Real mode: paid downgrade -> generate the genuine
                        # (cheaper) Higgsfield clip, not a studio placeholder.
                        adapters.generate_cinematic(scene, out, mode, final_model=cheaper,
                                                    company_url=job.get("company_url"))
                except Exception as e:  # noqa: BLE001 — isolate one scene's failure
                    _isolate_failed_scene(led, rec, sid, stype, e, budget, spent,
                                          warnings, flush,
                                          extra={"decision": "downgrade", "spent_cents": new_cost,
                                                 "preview_cost_cents": preview,
                                                 "downgraded_from": scene.get("model"),
                                                 "final_model": cheaper,
                                                 "stripe_authorization": auth})
                    continue
                rec.update({"decision": "downgrade", "tool": "higgsfield-scene",
                            "preview_cost_cents": preview, "spent_cents": new_cost,
                            "downgraded_from": scene.get("model"), "final_model": cheaper,
                            "remaining_after_cents": budget - spent,
                            "status": "produced", "output_path": rel(out, run_dir),
                            "stripe_authorization": auth, "studio": studio_block})
                clips.append((idx, out))
                led.event("spend", "DOWNGRADED %r %s->%s, spent %dc — remaining %dc"
                          % (sid, scene.get("model"), cheaper, new_cost, budget - spent))
            else:
                # Bridge: refresh live budget so the webhook's decide() sees this
                # over-budget charge (new_cost > budget - spent) and returns a REAL
                # DECLINE — the autonomous money-shot.
                write_active_budget(runs_dir, budget, spent)
                auth = money.authorize(new_cost, verdict2["remaining_budget_cents"],
                                       "decline", card.get("card_id"))
                rec.update({"decision": "decline", "tool": "higgsfield-scene",
                            "preview_cost_cents": preview, "spent_cents": 0,
                            "would_have_cost_cents": new_cost,
                            "downgraded_from": scene.get("model"), "final_model": cheaper,
                            "remaining_after_cents": budget - spent,
                            "status": "declined", "output_path": None,
                            "stripe_authorization": auth})
                led.event("decline", "DECLINED %r even after downgrade — scene cut, $0 spent" % sid)

        else:  # decline
            # Bridge: refresh live budget so the webhook's decide() sees this
            # over-budget charge (preview > budget - spent = remaining) and returns
            # a REAL DECLINE — the autonomous money-shot, no human in the loop.
            write_active_budget(runs_dir, budget, spent)
            auth = money.authorize(preview, remaining, "decline", card.get("card_id"))
            rec.update({"decision": "decline", "tool": "higgsfield-scene",
                        "preview_cost_cents": preview, "spent_cents": 0,
                        "would_have_cost_cents": preview, "final_model": scene.get("model"),
                        "remaining_after_cents": budget - spent,
                        "status": "declined", "output_path": None,
                        "stripe_authorization": auth})
            led.event("money", "MONEY-SHOT: Stripe %s authorization for %r — $%0.2f cut, no human"
                      % ("declined" if not auth.get("approved") else "approved",
                         sid, preview / 100.0))
            led.event("decline", "DECLINED %r — %dc exceeds remaining %dc, scene cut"
                      % (sid, preview, remaining))

        led.upsert_scene(rec)
        flush()

    # Bridge: final refresh so active_budget.json reflects the total committed
    # scene spend after the produce loop (any post-loop manual authorization
    # capture decides against the true remaining).
    write_active_budget(runs_dir, budget, spent)

    # -- VOICEOVER (gated spend, scene-aligned) ----------------------------
    led.set_phase("voiceover")
    flush()
    beat()
    vo = plan.get("voiceover") or {}
    # Compute each PRODUCED clip's start offset (cumulative clip durations, the
    # hard-concat timeline the stitch uses). Beats whose scene never produced a
    # clip (cut/declined at the gate, or skipped) are dropped here, so a cut
    # scene's narration never plays.
    clips.sort(key=lambda c: c[0])
    produced_offsets = {}
    cursor = 0.0
    total_video_s = 0.0
    for order, path in clips:
        sid_at = plan["scenes"][order]["id"]
        produced_offsets[sid_at] = round(cursor, 3)
        cursor += adapters.ffprobe_duration(path)
    total_video_s = round(cursor, 3)

    # Map resolved beats onto produced scenes; drop beats for cut scenes.
    aligned_beats = []
    dropped_beats = []
    for b in plan_beats:
        sid_b = b.get("scene_id")
        if sid_b in produced_offsets:
            aligned_beats.append({"scene_id": sid_b, "text": b.get("text", ""),
                                  "start_s": produced_offsets[sid_b]})
        else:
            dropped_beats.append(sid_b)
    if dropped_beats:
        led.event("info", "VOICEOVER: dropped %d beat(s) for cut/absent scenes: %s"
                  % (len(dropped_beats), ", ".join(str(x) for x in dropped_beats)))

    vo_planned = est["voiceover"]["est_cost_cents"]
    vo_est = int(prod_override.get("__voiceover__", vo_planned))
    # STANDARD quality voices with FREE edge-tts (not ElevenLabs), so the VO incurs
    # no marginal spend — gate it at $0 so it always clears the (now ~$0) budget.
    # premium keeps the ElevenLabs estimate. OFF path (premium False) is unchanged.
    if premium and not quality_premium:
        vo_est = 0
    vo_rec = {"id": "__voiceover__", "type": "voiceover", "chars": len(vo.get("script", "")),
              "preview_cost_cents": vo_est, "spent_before_cents": spent,
              "beats_total": len(plan_beats), "beats_aligned": len(aligned_beats),
              "beats_dropped": dropped_beats}
    if vo_est != vo_planned:
        vo_rec["cost_overrun_cents"] = vo_est - vo_planned
    vo_remaining = budget - spent
    vo_decision = "approve" if vo_est <= vo_remaining else "decline"
    led.event("gate", "GATE voiceover: %s — %dc vs remaining %dc"
              % (vo_decision.upper(), vo_est, vo_remaining))
    vo_path = None
    vo_synth_provider = (vo_provider if mode == "mock"
                         else ("elevenlabs" if vo_provider == "elevenlabs" else "edge"))

    # -- QUALITY gates the VO engine (flag-gated):
    #   * premium -> a natural ElevenLabs STOCK voice. NOT a voice clone, so NO
    #     consent gate. The real ElevenLabs call fires ONLY on --mode real; in mock
    #     (the $0 default) it logs the upgrade and falls back to free edge-tts ($0).
    #   * standard -> always free edge-tts (the synthetic voice), $0.
    # (The retired founder_voice/validate_consent clone path is dormant — pricing.py
    # still ships validate_consent for back-compat, but the active flow never clones.)
    if premium and quality_premium:
        if mode == "real":
            led.event("info", "PREMIUM VO: natural voiceover via ElevenLabs STOCK "
                      "voice (no clone, no consent required)")
            vo_synth_provider = "elevenlabs"
            vo_rec["premium_vo"] = {"requested": True, "engine": "elevenlabs",
                                    "voice_type": "stock", "consent_required": False}
        else:
            led.event("info", "PREMIUM VO: ElevenLabs voice requested but mode=mock "
                      "— using free edge-tts ($0, no real synth)")
            vo_synth_provider = "edge"
            vo_rec["premium_vo"] = {"requested": True, "engine": "edge",
                                    "voice_type": "stock", "consent_required": False,
                                    "reason": "mode=mock (no real synth)"}
    elif premium:
        # standard: the clean synthetic voice (edge-tts), always free.
        vo_synth_provider = "edge"
        led.event("info", "STANDARD VO: clean synthetic voice via edge-tts ($0)")

    have_vo_audio = vo_decision == "approve" and (aligned_beats or vo.get("script"))
    if have_vo_audio:
        vo_path = os.path.join(run_dir, "voiceover.mp3")
        if aligned_beats:
            # Per-beat synth, each placed at its scene's start offset.
            info = adapters.synthesize_voiceover_aligned(
                aligned_beats, vo.get("voice", "Adam"), vo_path,
                vo_synth_provider, total_s=total_video_s)
            vo_rec["segments"] = info.get("segments")
            led.event("spend", "VOICEOVER: %d scene-aligned beat(s) synthesized via %s "
                      "(%dc) — remaining %dc"
                      % (len(aligned_beats), info["provider"], vo_est, budget - vo_est - spent))
        else:
            # Hedge: no beats available — anchor the single track to the FIRST
            # PRODUCED content (non-title) scene's offset, not t=0, so the
            # narration at least starts on real content instead of drifting.
            first_content = next((plan["scenes"][o]["id"] for o, _ in clips
                                  if plan["scenes"][o]["type"] != "title"), None)
            anchor = produced_offsets.get(first_content, 0.0)
            info = adapters.synthesize_voiceover_aligned(
                [{"scene_id": first_content, "text": vo["script"], "start_s": anchor}],
                vo.get("voice", "Adam"), vo_path, vo_synth_provider, total_s=total_video_s)
            led.event("spend", "VOICEOVER: single track anchored to %r at %.2fs (no beats) "
                      "via %s (%dc)" % (first_content, anchor, info["provider"], vo_est))
        spent += vo_est
        vo_rec.update({"decision": "approve", "spent_cents": vo_est,
                       "remaining_after_cents": budget - spent, "status": "produced",
                       "provider": info["provider"], "voice": info["voice"],
                       "output_path": rel(vo_path, run_dir)})
    else:
        vo_rec.update({"decision": "decline", "spent_cents": 0,
                       "would_have_cost_cents": vo_est,
                       "remaining_after_cents": budget - spent, "status": "declined",
                       "output_path": None})
        led.event("decline", "VOICEOVER declined — %dc exceeds remaining %dc" % (vo_est, vo_remaining))
    led.set_voiceover(vo_rec)
    led.set_phase("stitching")
    flush()
    beat()

    # -- STITCH -------------------------------------------------------------
    # Sort by scene idx so out-of-order parallel completion (HERMES_PARALLEL) still
    # stitches in scene order. Stitch whatever SUCCEEDED — failed/isolated scenes
    # simply never appended a clip, so the run still delivers a final video.
    stitched = False
    if do_stitch and clips:
        clips.sort(key=lambda c: c[0])
        final = os.path.join(run_dir, "final.mp4")
        # Watermark: DORMANT in the cost-plus model. There is no watermark tier and
        # no no_watermark booster anymore, so premium["watermark"] is always False
        # and this evaluates to False -> the OFF stitch is byte-identical. The
        # adapters.stitch watermark code remains for back-compat but is never armed.
        stitch_rec = adapters.stitch([c[1] for c in clips], vo_path, final,
                                     watermark=(premium and led.data["premium"]["watermark"]))
        stitch_rec["output_path"] = rel(final, run_dir)
        stitch_rec["scenes_included"] = [plan["scenes"][c[0]]["id"] for c in clips]
        stitch_rec["scenes_cut"] = [s["id"] for s in plan["scenes"]
                                    if s["id"] not in stitch_rec["scenes_included"]
                                    and s["type"] == "cinematic"]
        led.set_stitch(stitch_rec)
        if premium:
            led.event("info", "STITCHED final.mp4 — %ss, %d clips, audio=%s, watermark=%s"
                      % (stitch_rec["duration_s"], stitch_rec["clip_count"],
                         stitch_rec["has_audio"], stitch_rec.get("watermark")))
        else:
            # OFF path: emit the exact pre-premium message (byte-identical ledger).
            led.event("info", "STITCHED final.mp4 — %ss, %d clips, audio=%s"
                      % (stitch_rec["duration_s"], stitch_rec["clip_count"],
                         stitch_rec["has_audio"]))
        stitched = True

        # multi_format: DORMANT in the cost-plus model. `boosters` is always empty
        # now, so this never executes. adapters.make_format_pack is kept for
        # back-compat but is no longer surfaced or selected.
        if premium and "multi_format" in boosters:
            n_formats = int((selection.get("options") or {}).get("formats") or 0)
            if n_formats > 0:
                pack = adapters.make_format_pack(final, run_dir, n_formats,
                                                 vo_path=vo_path)
                for item in pack:
                    item["output_path"] = rel(item["output_path"], run_dir)
                led.data["premium"]["format_pack"] = pack
                led.event("info", "MULTI-FORMAT: produced %d extra cut(s): %s"
                          % (len(pack), ", ".join(p["label"] for p in pack)))

    # -- PREMIUM ledger itemization (flag-gated) ----------------------------
    # Itemize the tier + each booster as separate line items MATCHING
    # price_selection()'s line_items, so the on-screen P&L (which reads the same
    # menu) and the produced ledger never drift. Each line carries the STABLE
    # label, its price_cents, cogs_cents and a per-line margin. The totals are the
    # menu totals == the locked budget (COGS) + the customer price.
    if premium and menu:
        items = []
        for li in menu.get("line_items", []):
            lp = int(li.get("price_cents") or 0)
            lc = int(li.get("cogs_cents") or 0)
            items.append({
                "key": li.get("key"),
                "label": li.get("label"),
                "qty": li.get("qty", 1),
                "price_cents": lp,
                "cogs_cents": lc,
                "margin": (0.0 if lp == 0 else round((lp - lc) / lp, 4)),
            })
        led.data["premium"]["ledger"] = {
            "line_items": items,
            "total_price_cents": menu.get("total_price_cents"),
            "total_cogs_cents": menu.get("total_cogs_cents"),
            "margin": round(menu.get("margin", 0.0), 6),
        }
        led.event("info", "PREMIUM LEDGER: %d line item(s), price %sc, COGS %sc"
                  % (len(items), menu.get("total_price_cents"),
                     menu.get("total_cogs_cents")))

    # -- P&L ----------------------------------------------------------------
    pnl = ledger_mod.compute_pnl(price, led.data["scenes"], led.data["voiceover"])
    led.set_pnl(pnl)

    # Status visibility: a clean run is "delivered"; a run that isolated one or more
    # scene failures but still shipped a video is "completed_with_warnings" (the
    # degradation is VISIBLE in the ledger/dashboard, never masked as a clean
    # "delivered"); a run where NOTHING produced a clip (do_stitch on but no
    # survivors) is a true whole-run abort -> "failed".
    if do_stitch and not stitched:
        led.set_status("failed")
        led.set_phase("failed")
        led.data["warnings"] = warnings
        led.event("error", "RUN FAILED — no scene produced a usable clip; nothing to stitch")
        led_path = led.write(os.path.join(run_dir, "ledger.json"))
        _update_index(runs_dir)
        return led.to_dict(), led_path

    if warnings:
        led.set_status("completed_with_warnings")
        led.data["warnings"] = warnings
        led.event("info", "COMPLETED WITH WARNINGS — %d scene(s) failed but the run "
                  "shipped: %s" % (len(warnings),
                                   ", ".join(w["id"] for w in warnings)))
    else:
        led.set_status("delivered")
    led.set_phase("delivered")
    led.event("info", "DELIVERED — price %sc, spent %dc, margin %s, overage avoided %dc"
              % (price, pnl["cogs_spent_cents"],
                 ("%.1f%%" % (pnl["margin"] * 100) if pnl["margin"] is not None else "n/a"),
                 pnl["overage_avoided_cents"]))

    led_path = led.write(os.path.join(run_dir, "ledger.json"))
    _update_index(runs_dir)
    return led.to_dict(), led_path


def _isolate_failed_scene(led, rec, sid, stype, exc, budget, spent, warnings, flush,
                          extra=None):
    """One scene's production failed — isolate it so the run still ships.

    Records the scene as status='failed' with the error (and any money already
    committed, via `extra`), logs a ledger event, appends to `warnings`, and
    flushes. The caller then `continue`s the produce loop. NO clip is appended for
    a failed scene, so stitch simply assembles the survivors. This is the bug fix:
    before, a single scene's exception aborted the whole produce loop and the run
    lost every later scene plus the final stitch.
    """
    err = "%s: %s" % (type(exc).__name__, exc)
    rec.update({"status": "failed", "decision": (extra or {}).get("decision", "failed"),
                "error": err, "output_path": None,
                "remaining_after_cents": budget - spent})
    if extra:
        rec.update(extra)
    rec.setdefault("spent_cents", 0)
    warnings.append({"id": sid, "type": stype, "error": err})
    led.event("error", "SCENE FAILED %r (%s) — isolated; run continues. %s"
              % (sid, stype, err), scene=sid)
    led.upsert_scene(rec)
    flush()


def adapters_tool(stype):
    return {"title": "motion-graphics", "motion_graphic": "motion-graphics",
            "walkthrough": "walk-agent", "screenshot": "site-capture"}.get(stype, "unknown")


def rel(path, base):
    try:
        return os.path.relpath(path, base)
    except ValueError:
        return path


def _update_index(runs_dir):
    """Maintain runs/index.json — the list the dashboard loads first."""
    entries = []
    for name in sorted(os.listdir(runs_dir)):
        led_path = os.path.join(runs_dir, name, "ledger.json")
        if not os.path.exists(led_path):
            continue
        try:
            with open(led_path) as f:
                d = json.load(f)
        except (OSError, ValueError):
            continue
        pnl = d.get("pnl") or {}
        entries.append({
            "run_id": d.get("run_id"), "mode": d.get("mode"),
            "status": d.get("status"), "created_at": d.get("created_at"),
            "goal": (d.get("job") or {}).get("goal"),
            "company_url": (d.get("job") or {}).get("company_url"),
            "price_cents": pnl.get("price_cents"),
            "cogs_spent_cents": pnl.get("cogs_spent_cents"),
            "margin": pnl.get("margin"),
            "overage_avoided_cents": pnl.get("overage_avoided_cents"),
            "declines": len(pnl.get("declines") or []),
        })
    with open(os.path.join(runs_dir, "index.json"), "w") as f:
        json.dump({"runs": entries}, f, indent=2)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Producer-brain orchestrator")
    ap.add_argument("--plan", required=True)
    ap.add_argument("--run-id", default=None)
    ap.add_argument("--mode", choices=["mock", "real"], default="mock")
    ap.add_argument("--runs-dir", default=None)
    ap.add_argument("--vo", choices=["edge", "elevenlabs"], default="edge")
    ap.add_argument("--overlays", choices=["mock", "studio"], default="mock",
                    help="studio = the agent writes + renders real Remotion (title/MG) "
                         "and an animatic storyboard for cinematic/walkthrough")
    ap.add_argument("--stripe-live", action="store_true",
                    help="use the real Stripe test-mode API (needs a key present)")
    ap.add_argument("--now", default=None, help="ISO timestamp for the ledger (reproducible runs)")
    ap.add_argument("--no-stitch", action="store_true")
    args = ap.parse_args(argv)

    with open(args.plan) as f:
        plan = json.load(f)

    run_id = args.run_id or _derive_run_id(args.plan)
    data, led_path = orchestrate(
        plan, run_id, mode=args.mode, runs_dir=args.runs_dir, vo_provider=args.vo,
        stripe_live=args.stripe_live, now=args.now, do_stitch=not args.no_stitch,
        overlays=args.overlays)

    pnl = data["pnl"]
    print("RUN %s [%s] -> %s" % (run_id, data["mode"], led_path))
    print("  price=%sc spent=%dc margin=%s overage_avoided=%dc declines=%d"
          % (pnl["price_cents"], pnl["cogs_spent_cents"],
             ("%.1f%%" % (pnl["margin"] * 100) if pnl["margin"] is not None else "n/a"),
             pnl["overage_avoided_cents"], len(pnl["declines"])))
    if data.get("stitch"):
        print("  final: %s (%ss)" % (data["stitch"]["output_path"], data["stitch"]["duration_s"]))
    return 0


def _derive_run_id(plan_path):
    base = os.path.splitext(os.path.basename(plan_path))[0]
    return base.replace("/", "_")


if __name__ == "__main__":
    sys.exit(main())
