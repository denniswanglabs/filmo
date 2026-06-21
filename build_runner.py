#!/usr/bin/env python3
"""Run ONE live build job: URL + goal -> storyboard -> PAYMENT GATE -> produced video.

Launched as a subprocess by the dashboard server. The flow, watchable live in the
console via the incrementally-written ledger:

  1. PLAN     write a 'planning' ledger at once (so the console shows the agent
              thinking), then plan the storyboard via the free Nemotron planner.
  2. PRICE    price the plan with producer.py BEFORE producing, so the customer
              price is known before any money is spent.
  3. EARN/GATE create a REAL Stripe TEST-mode Checkout Session, write an
              `awaiting_payment` ledger (phase + earn block) so the dashboard
              renders the pay-gate card, then POLL the session's payment_status
              until 'paid' (webhook is blocked on `stripe login`; poll is the
              working path) or a ~15-min wall-clock cap.
  4. PRODUCE  on 'paid', hand off to orchestrator.orchestrate (carrying the paid
              earn block) which produces each scene under the budget gate and
              writes the rest of the ledger -> delivered.

Mode:
  mock  ($0) — real Remotion titles + storyboard placeholders, edge-tts VO.
  real  (paid) — real Higgsfield + walk-agent. "Always real ($)": a real customer
        payment triggers real production with no mock fallback.

$0 DEV AFFORDANCE — env `PRODUCER_SIMULATE_PAID=1`: the poll resolves to 'paid'
immediately (a real test session is still created for realism). Combined with
`--mode mock` this runs plan -> gate -> (simulated paid) -> mock production ->
delivered entirely at $0, with no real human payment and no Higgsfield spend.
In production: no simulate flag + mode=real.

Watchable pacing: sets PRODUCER_PACE so scene state-changes don't blink past.
"""

import json
import os
import shutil
import sys
import time

import ledger as ledger_mod
import orchestrator
import plan_job
import producer
import stripe_earn

HERE = os.path.dirname(os.path.abspath(__file__))
RUNS = os.path.join(HERE, "runs")
BRANDING = os.path.join(HERE, "branding")

# VO-DRIVEN ENGINE flag (the blank-scenes fix). When ON (default for the dashboard
# build path), the PICTURE is produced by the VO-driven <Timeline> engine
# (align_vo -> build_timeline -> style_fill.build_props -> Remotion render) which
# NEVER emits a blank scene: a cinematic/walkthrough beat with no real footage
# falls to the designed ExplainerCard, not the old flat solid-color synth_clip.
# When OFF, the legacy per-scene-clip path is the only picture (still reachable for
# the original demo). The SACRED money path (orchestrator's budget gate + Stripe
# authorize + ledger/P&L) runs UNCHANGED either way — the engine only replaces the
# final.mp4 picture, never the money/ledger flow.
VO_ENGINE_ENV = "WS_VO_ENGINE"
# The curated style the engine fills. Only one style ships today; default to it.
VO_ENGINE_STYLE = "orinovate-kinetic-light"


def vo_engine_enabled():
    """True unless WS_VO_ENGINE is explicitly a falsy flag ('0'/'false'/'no'/'off').

    Default ON for the dashboard build path (run()) so the blank-scenes fix is the
    shipped behavior; set WS_VO_ENGINE=0 to fall back to the legacy picture.
    """
    return (os.environ.get(VO_ENGINE_ENV) or "").strip().lower() not in ("0", "false", "no", "off")

# Poll cadence + wall-clock cap for the payment gate (webhook backstop).
PAYMENT_POLL_INTERVAL_S = 2.5
PAYMENT_TIMEOUT_S = 15 * 60  # 15 minutes


def _price_plan(plan, run_dir):
    """Price the validated plan via producer.py BEFORE production.

    Returns (price_cents, currency). We write plan.json into the run dir (the
    same path orchestrate uses later) so producer.estimate prices the exact plan.
    """
    plan_path = os.path.join(run_dir, "plan.json")
    with open(plan_path, "w") as f:
        json.dump(plan, f, indent=2)
    est = producer.cmd_estimate(plan)
    currency = (plan.get("job") or {}).get("currency", "usd")
    return est.get("suggested_price_cents"), currency, est


def _resolve_brand_theme(url, run_dir):
    """Resolve the brand_theme the VO engine fills, and write it to run_dir.

    PREFERS a curated `branding/<host>-brand-theme.json` fixture (e.g. the
    hand-authored Orinovate light/navy/blue theme that produced the proven-good
    style-fill sample), because the generic `palette_for` fallback returns a
    dark+mint theme that is wrong for these brands (the diagnosis's FIX 3). Falls
    back to brand_extract.extract_brand(url) for any brand without a fixture.

    Returns the absolute path to the written brand_theme.json.
    """
    import remotion_codegen as rc

    host = rc._root_host(url) or ""
    label = host.split(".")[0] if host else ""
    theme = None
    if label:
        fixture = os.path.join(BRANDING, "%s-brand-theme.json" % label)
        if os.path.exists(fixture):
            try:
                with open(fixture) as f:
                    theme = json.load(f)
            except (OSError, ValueError):
                theme = None
    if theme is None:
        # No curated fixture — extract honestly (real name + palette + empty copy).
        import brand_extract
        theme = brand_extract.extract_brand(url)

    out = os.path.join(run_dir, "brand_theme.json")
    with open(out, "w") as f:
        json.dump(theme, f, indent=2)
    return out


def _run_vo_engine(plan, run_id, url, run_dir):
    """Produce the PICTURE via the VO-driven <Timeline> engine and replace the
    run's final.mp4 with it. NEVER-BLANK by construction (ExplainerCard floor).

    Runs entirely on the $0 free tier: edge-tts + local whisper-cli for alignment,
    Remotion for the render. Does NOT touch the ledger/money path — orchestrate has
    already written ledger.json (P&L, scenes, budget gate, Stripe) by the time this
    runs. We only overwrite the picture so the customer never sees a blank scene.

    Returns the path to the engine final.mp4 on success, or None if the engine
    could not run (in which case the legacy picture from orchestrate is left as-is).
    """
    import style_fill

    plan_path = os.path.join(run_dir, "plan.json")
    if not os.path.exists(plan_path):
        with open(plan_path, "w") as f:
            json.dump(plan, f, indent=2)
    brand_path = _resolve_brand_theme(url, run_dir)

    # align_vo -> build_timeline -> style_fill.build_props -> props.json (+ stage
    # audio). do_render=False here so we render once, below, into the run's final.mp4.
    res = style_fill.run_pipeline(plan_path, brand_path, VO_ENGINE_STYLE, run_dir,
                                  fps=30, do_align=True, do_render=False)
    props_path = res["props_path"]

    # Render the Timeline composition with the props into the run's final.mp4 — the
    # exact path the dashboard/stitch already point at, so nothing downstream changes.
    final = os.path.join(run_dir, "final.mp4")
    studio = style_fill.STUDIO_DIR
    abs_props = os.path.abspath(props_path)
    env = dict(os.environ, PATH=os.path.join(studio, "node_modules", ".bin")
               + os.pathsep + os.environ.get("PATH", ""))
    import subprocess
    cmd = ["remotion", "render", "src/index.ts", "Timeline", os.path.abspath(final),
           "--codec=h264", "--concurrency=8", "--props=%s" % abs_props]
    r = subprocess.run(cmd, cwd=studio, env=env)
    if r.returncode != 0 or not os.path.exists(final):
        return None
    return final


def run(url, goal, run_id, mode="mock", target_duration=30, pace=1.2, style="standard",
        quality="standard"):
    run_dir = os.path.join(RUNS, run_id)
    os.makedirs(run_dir, exist_ok=True)
    led_path = os.path.join(run_dir, "ledger.json")
    job = {"company_url": url, "goal": goal, "target_duration_s": target_duration,
           "target_margin": 0.6, "currency": "usd"}

    # QUALITY (the upfront cost-plus choice) drives BOTH pricing + the produce stack.
    # Turn the cost-plus menu ON for dashboard builds so producer/orchestrator honor
    # the quality dimension (standard = Remotion + edge-tts, no Higgsfield/ElevenLabs,
    # price floors at $5; premium = cinematic Higgsfield + ElevenLabs VO, ~$6-9).
    quality = "premium" if str(quality).strip().lower() == "premium" else "standard"
    os.environ["WS_PREMIUM_MENU"] = "1"

    os.environ["PRODUCER_PACE"] = str(pace)
    # User-facing STYLE controls the actual output (scene count / holds / motion
    # intensity), decoupled from PRODUCER_PACE (the console beat). The render layer
    # (remotion_codegen) reads HERMES_STYLE for per-style ease intensity; standard
    # leaves it as today's default so the output stays byte-identical.
    style = style if style in plan_job.VALID_STYLES else "standard"
    os.environ["HERMES_STYLE"] = style
    if mode == "mock":
        os.environ.setdefault("PRODUCER_COST_STUB",
                              json.dumps({"seedance_2_0": 22, "gpt_image_2": 7, "__default__": 10}))

    # immediate 'planning' ledger so the console has something to show at once
    led = ledger_mod.Ledger(run_id, job, mode)
    led.set_status("running")
    led.set_phase("planning")
    led.event("info", "agent visiting %s — reading the site and planning the storyboard…" % url)
    led.write(led_path)

    try:
        # Thread QUALITY into the planner so the storyboard's SCENE TYPES match the
        # produce stack: standard => Remotion-only (title + motion_graphic, no
        # cinematic); premium => cinematic shots allowed. (Previously quality was
        # only stamped onto plan["selection"] AFTER planning, so a standard plan
        # could still list Seedance / GPT-image cinematic scenes.)
        plan = plan_job.plan_job(url, goal, target_duration, style=style, quality=quality)
        # Carry the upfront QUALITY choice onto the plan so producer.cmd_estimate
        # prices it (standard floors at $5; premium includes Higgsfield + ElevenLabs
        # COGS) and orchestrate produces the matching stack.
        plan["selection"] = {"quality": quality}

        # -- PRICE before producing -------------------------------------------
        price_cents, currency, est = _price_plan(plan, run_dir)
        # Surface the priced storyboard so the console can render the script +
        # price the moment planning completes (mirrors orchestrate's projection).
        vo_plan = plan.get("voiceover") or {}
        led.data["plan"] = {
            "voiceover": {"script": vo_plan.get("script", ""), "voice": vo_plan.get("voice")},
            "scenes": [{"id": s.get("id"), "type": s.get("type"), "model": s.get("model"),
                        "duration_s": s.get("duration_s"), "brief": s.get("brief", "")}
                       for s in plan.get("scenes", [])],
        }
        led.set_pricing(est)
        led.event("info", "storyboard decided: %d scenes, priced at %sc"
                  % (len(plan.get("scenes", [])), price_cents))

        # -- EARN / payment gate ---------------------------------------------
        earn = _payment_gate(led, led_path, run_id, price_cents, currency, job, mode)
        if earn is None:
            return  # gate failed/timed out — ledger already records it

        # -- PRODUCE (only after payment) ------------------------------------
        led.event("money", "payment received — $%.2f" % ((price_cents or 0) / 100.0))
        led.set_phase("producing")
        led.write(led_path)

        data, _ = orchestrator.orchestrate(
            plan, run_id, mode=mode,
            overlays=("studio" if mode == "mock" else "mock"),
            earn=earn)

        # PICTURE via the VO-driven engine (the blank-scenes fix). The SACRED money
        # path (budget gate + Stripe authorize + ledger/P&L) has ALREADY run inside
        # orchestrate above; here we only replace the final.mp4 picture with the
        # never-blank <Timeline> render so a cinematic/walkthrough beat with no real
        # footage SHOWS the narrated point (ExplainerCard) instead of a blank.
        # Behind WS_VO_ENGINE (default ON); set WS_VO_ENGINE=0 for the legacy picture.
        if vo_engine_enabled():
            try:
                final = _run_vo_engine(plan, run_id, url, run_dir)
                if final:
                    led.event("info", "VO-ENGINE: rendered never-blank <Timeline> "
                              "picture -> final.mp4 (WS_VO_ENGINE on)")
                else:
                    led.event("info", "VO-ENGINE: engine render unavailable — kept the "
                              "legacy picture for this run")
                led.write(led_path)
            except Exception as e:  # never let the picture step fail a delivered run
                led.event("info", "VO-ENGINE: skipped (%s) — kept the legacy picture" % e)
                led.write(led_path)
        return data
    except SystemExit:
        raise
    except Exception as e:  # surface the failure into the ledger the console polls
        _record_failure(led_path, led, run_id, job, mode, e)
        raise


def _record_failure(led_path, run_led, run_id, job, mode, exc):
    """Flip the run to 'failed' WITHOUT wiping the paid record.

    A post-payment failure (e.g. a production-side parse error) must KEEP the
    earn/pricing/plan/scenes already written to the ledger — otherwise a paid run
    looks like it was never paid (the build-orinovate-edf804 symptom: earn=null
    despite a confirmed payment). The old handler constructed a FRESH Ledger and
    wrote it, clobbering all of that. Instead:
      1. Load the freshest ledger from disk — during production the orchestrator
         writes scenes/plan/pnl (and the carried earn block) there.
      2. Backfill earn/pricing/plan from the in-memory run-level ledger if an EARLY
         failure (before orchestrate set them on disk) beat them to disk; the
         run-level ledger holds them from the planning + payment gate.
      3. Only set status/phase=failed and append the error event.
      4. Refresh runs/index.json so it doesn't go stale at 'running' on failure —
         the index is otherwise only rebuilt by orchestrate on a successful deliver.
    """
    try:
        led = ledger_mod.Ledger.load(led_path)
    except (OSError, ValueError):
        # No readable ledger on disk — fall back to the in-memory run-level ledger,
        # which still carries earn/pricing/plan if the payment gate had passed.
        led = run_led
    # Preserve the paid record across the early-failure window where a disk ledger
    # exists but predates the earn/pricing/plan blocks (the run-level ledger has them).
    for key in ("earn", "pricing", "plan"):
        if not led.data.get(key) and run_led.data.get(key):
            led.data[key] = run_led.data[key]
    led.set_status("failed")
    led.set_phase("failed")
    led.event("error", "build failed: %s" % exc)
    led.write(led_path)
    try:
        orchestrator._update_index(RUNS)
    except OSError:
        pass


def _payment_gate(led, led_path, run_id, price_cents, currency, job, mode):
    """Create a real TEST-mode Checkout Session, write the awaiting_payment ledger,
    then poll the session until paid (or time out).

    Returns the paid `earn` block (to carry into production) or None on
    timeout/failure (the ledger is set to failed in that case).
    """
    brand = (job.get("company_url") or "").replace("https://", "").replace("http://", "")
    brand = brand.replace("www.", "").split("/")[0] or "the product"
    product_name = "%s promo video" % brand

    # Create the real test-mode session ($0 — creating a test session never settles).
    session = stripe_earn.create_checkout_session(
        run_id, int(price_cents or 0), currency=currency, product_name=product_name)

    earn = {
        "enabled": True,
        "provider": "stripe",
        "mode": "test",
        "status": "awaiting_payment",
        "session_id": session.get("session_id"),
        "checkout_url": session.get("url"),
        "price_cents": price_cents,
        "currency": currency,
        "product_name": product_name,
        "livemode": session.get("livemode"),
        "payment_status": session.get("payment_status") or "unpaid",
    }
    led.set_earn(earn)
    led.set_phase("awaiting_payment")
    led.set_status("running")
    led.event("money", "payment gate: Stripe TEST Checkout for $%.2f — awaiting payment"
              % ((price_cents or 0) / 100.0), session_id=earn["session_id"])
    led.write(led_path)

    simulate = os.environ.get("PRODUCER_SIMULATE_PAID") == "1"
    if simulate:
        led.event("info", "PRODUCER_SIMULATE_PAID=1 — dev affordance: resolving payment as paid ($0)")

    deadline = time.monotonic() + PAYMENT_TIMEOUT_S
    while True:
        if simulate:
            status = "paid"
        else:
            try:
                status = stripe_earn.get_session_status(earn["session_id"])
            except Exception as e:
                # transient network/Stripe error — record once and keep polling
                led.event("info", "payment poll error (will retry): %s" % e)
                status = earn.get("payment_status") or "unpaid"

        if status != earn.get("payment_status"):
            earn["payment_status"] = status
            led.set_earn(earn)
            led.write(led_path)

        if status in ("paid", "no_payment_required"):
            earn["status"] = "paid"
            led.set_earn(earn)
            led.write(led_path)
            return earn

        if time.monotonic() >= deadline:
            earn["status"] = "payment_timeout"
            led.set_earn(earn)
            led.set_phase("payment_timeout")
            led.set_status("failed")
            led.event("error", "payment gate timed out after %d min — no payment received; build cancelled"
                      % (PAYMENT_TIMEOUT_S // 60))
            led.write(led_path)
            return None

        time.sleep(PAYMENT_POLL_INTERVAL_S)


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--goal", default="")
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--mode", choices=["mock", "real"], default="mock")
    ap.add_argument("--duration", type=int, default=30)
    ap.add_argument("--pace", type=float, default=1.2)
    ap.add_argument("--style", choices=list(plan_job.VALID_STYLES), default="standard",
                    help="user-facing output style: snappy (more+shorter scenes) | "
                         "standard (today's default) | cinematic (fewer+longer scenes)")
    ap.add_argument("--quality", choices=["standard", "premium"], default="standard",
                    help="video quality (the upfront cost-plus choice): standard "
                         "(Remotion + edge-tts, no Higgsfield/ElevenLabs, ~$5) | premium "
                         "(cinematic Higgsfield + ElevenLabs VO, ~$6-9)")
    a = ap.parse_args()
    goal = a.goal or ("%d-second promo plus a short product walkthrough" % a.duration)
    run(a.url, goal, a.run_id, a.mode, a.duration, a.pace, a.style, quality=a.quality)


if __name__ == "__main__":
    main()
