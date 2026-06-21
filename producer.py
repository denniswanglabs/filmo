#!/usr/bin/env python3
"""Hermes video-agent producer brain: deterministic pricing + budget engine.

Standard library only. Non-interactive. Prints JSON to stdout.

This is the §B "producer brain" cost/budget layer from STRIPE-PRODUCER-DESIGN.md.
It NEVER triggers a real generation. The only external call it makes is the FREE
Higgsfield price preview `higgsfield generate cost <model> --prompt "..."`, which
estimates credits without creating a job and without spending.

Subcommands
-----------
  estimate --plan <plan.json>
      Per-scene est_cost_cents, total_cogs_cents,
      suggested_price_cents = round(total_cogs / (1 - target_margin)),
      and per_scene_budget_cents (COGS distributed across scenes
      proportional to each scene's est cost).

  gate --plan <plan.json> --scene <id> --proposed_cost_cents N --spent_cents M
      Decision approve | downgrade | decline for one scene's proposed spend.
        proposed fits remaining budget                 -> approve
        over budget but a cheaper model exists         -> downgrade (names it)
        over budget with no cheaper option             -> decline

Scene type -> tool (and whether it costs money)
-----------------------------------------------
  cinematic       -> higgsfield-scene   (PAID; real cost via `generate cost`)
  walkthrough     -> walk-agent         (FREE; NVIDIA Nemotron tier)
  motion_graphic  -> motion-graphics    (FREE; local Remotion)
  title           -> motion-graphics    (FREE; local Remotion)
  voiceover track -> ElevenLabs TTS     (PAID; estimated from script length)
"""

import argparse
import json
import os
import subprocess
import sys

# ---------------------------------------------------------------------------
# Cost-model constants (documented in SCHEMA.md)
# ---------------------------------------------------------------------------

# ElevenLabs has no free "cost preview" call, so VO is estimated from the
# script's character count at this rate. ~$0.30 per 1000 characters.
ELEVENLABS_PER_1K_CHARS_CENTS = 30

# The Higgsfield CLI prices everything in *credits*, not dollars; it exposes no
# USD rate. We convert credits -> cents with this documented constant. Higgsfield
# credit packs price at roughly $0.01/credit, so 1 credit == 1 cent is the
# defensible default. Override here if Dennis's plan rate differs.
HIGGSFIELD_CENTS_PER_CREDIT = 1.0

# Default models per the brief.
DEFAULT_CINEMATIC_VIDEO_MODEL = "seedance_2_0"   # cinematic video
DEFAULT_CINEMATIC_STILL_MODEL = "gpt_image_2"    # cheaper still fallback

# Cheaper-model map for the downgrade path, keyed by scene type. A cinematic
# video scene can fall back to a still image (gpt_image_2) instead of video.
CHEAPER_MODEL = {
    "cinematic": DEFAULT_CINEMATIC_STILL_MODEL,
}

# Scene types that incur no marginal API spend (local / NVIDIA-tier compute).
FREE_SCENE_TYPES = {"walkthrough", "motion_graphic", "title"}

# Scene type -> production tool, for reporting/traceability.
SCENE_TOOL = {
    "title": "motion-graphics",
    "motion_graphic": "motion-graphics",
    "cinematic": "higgsfield-scene",
    "walkthrough": "walk-agent",
}


# ---------------------------------------------------------------------------
# Higgsfield free cost preview
# ---------------------------------------------------------------------------

def _stub_preview_cents(model):
    """Deterministic offline cost preview, used when PRODUCER_COST_STUB is set.

    Lets the whole pipeline (and the test harness) run WITHOUT the Higgsfield CLI
    and WITHOUT touching the network, while keeping producer.py the single source
    of truth for pricing. The env var holds JSON:
      - a number            -> that many credits for EVERY model
      - an object {model: credits, "__default__": credits}  -> per-model credits
    Returns (cents, note) or None if the env var is unset/unparseable.
    """
    raw = os.environ.get("PRODUCER_COST_STUB")
    if not raw:
        return None
    try:
        spec = json.loads(raw)
    except (ValueError, json.JSONDecodeError):
        return None
    if isinstance(spec, (int, float)):
        credits = float(spec)
    elif isinstance(spec, dict):
        if model in spec:
            credits = float(spec[model])
        elif "__default__" in spec:
            credits = float(spec["__default__"])
        else:
            return None
    else:
        return None
    cents = round(credits * HIGGSFIELD_CENTS_PER_CREDIT)
    return cents, "stubbed preview: %s credits (PRODUCER_COST_STUB)" % credits


def higgsfield_preview_cents(model, prompt):
    """Return (cents, note) for a Higgsfield model+prompt via the FREE preview.

    Runs `higgsfield generate cost <model> --prompt "<prompt>" --json`. This
    estimates credits WITHOUT creating a job and WITHOUT spending. No retry on
    failure (paid-job safety habit carried over): on any error we surface a note
    and fall back to 0 cents so the engine stays deterministic and non-blocking.

    If PRODUCER_COST_STUB is set in the environment, a deterministic offline
    estimate is used instead of calling the CLI (for tests / no-network runs).
    """
    stubbed = _stub_preview_cents(model)
    if stubbed is not None:
        return stubbed

    cmd = [
        "higgsfield", "generate", "cost", model,
        "--prompt", prompt, "--json",
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except FileNotFoundError:
        return 0, "higgsfield CLI not found on PATH"
    except subprocess.TimeoutExpired:
        return 0, "higgsfield cost preview timed out"

    if proc.returncode != 0:
        msg = (proc.stderr or proc.stdout or "").strip().splitlines()
        return 0, "higgsfield cost preview failed: " + (msg[0] if msg else "unknown error")

    try:
        data = json.loads(proc.stdout)
    except (ValueError, json.JSONDecodeError):
        return 0, "could not parse higgsfield cost JSON"

    # Prefer the exact (fractional) credit count when present.
    credits = data.get("credits_exact")
    if credits is None:
        credits = data.get("credits")
    if credits is None:
        return 0, "no credits field in higgsfield cost JSON"

    cents = round(float(credits) * HIGGSFIELD_CENTS_PER_CREDIT)
    return cents, "higgsfield preview: %s credits" % credits


# ---------------------------------------------------------------------------
# Per-scene cost estimation
# ---------------------------------------------------------------------------

def estimate_scene_cents(scene):
    """Return (cents, note) for one scene, by type. PAID types hit previews."""
    stype = scene.get("type")
    if stype in FREE_SCENE_TYPES:
        return 0, "%s -> %s (free, $0 marginal)" % (stype, SCENE_TOOL.get(stype, "?"))

    if stype == "cinematic":
        model = scene.get("model") or DEFAULT_CINEMATIC_VIDEO_MODEL
        cents, note = higgsfield_preview_cents(model, scene.get("brief", ""))
        return cents, "cinematic via %s -- %s" % (model, note)

    # Unknown type: treat as free but flag it so it surfaces in output.
    return 0, "unknown scene type '%s' -- treated as $0" % stype


def estimate_voiceover_cents(voiceover):
    """Return (cents, note) for the VO track from script length. PAID."""
    if not voiceover:
        return 0, "no voiceover"
    script = voiceover.get("script", "") or ""
    chars = len(script)
    cents = round(chars / 1000.0 * ELEVENLABS_PER_1K_CHARS_CENTS)
    return cents, "ElevenLabs: %d chars @ %dc/1k chars" % (chars, ELEVENLABS_PER_1K_CHARS_CENTS)


# ---------------------------------------------------------------------------
# estimate subcommand
# ---------------------------------------------------------------------------

def cmd_estimate(plan):
    job = plan.get("job", {})
    target_margin = float(job.get("target_margin", 0.0))
    currency = job.get("currency", "usd")

    scenes_out = []
    total_cogs = 0

    for scene in plan.get("scenes", []):
        cents, note = estimate_scene_cents(scene)
        total_cogs += cents
        scenes_out.append({
            "id": scene.get("id"),
            "type": scene.get("type"),
            "tool": SCENE_TOOL.get(scene.get("type"), "unknown"),
            "model": scene.get("model"),
            "est_cost_cents": cents,
            "note": note,
        })

    vo_cents, vo_note = estimate_voiceover_cents(plan.get("voiceover"))
    total_cogs += vo_cents

    # Suggested customer price targeting the margin.
    if target_margin >= 1.0:
        suggested_price = None  # undefined; would divide by zero / be infinite
    else:
        suggested_price = round(total_cogs / (1.0 - target_margin))

    # Per-scene budget: distribute COGS proportional to each scene's est cost.
    # The VO line is included in the proportional split so allocations sum to COGS.
    cost_items = scenes_out + [{
        "id": "__voiceover__",
        "type": "voiceover",
        "tool": "elevenlabs-tts",
        "model": (plan.get("voiceover") or {}).get("voice"),
        "est_cost_cents": vo_cents,
        "note": vo_note,
    }]

    budget_alloc = _distribute(total_cogs, [c["est_cost_cents"] for c in cost_items])
    for item, alloc in zip(cost_items, budget_alloc):
        item["per_scene_budget_cents"] = alloc

    # Split scenes from the VO line for a clean report shape.
    vo_item = cost_items[-1]
    scenes_report = cost_items[:-1]

    result = {
        "currency": currency,
        "target_margin": target_margin,
        "scenes": scenes_report,
        "voiceover": vo_item,
        "total_cogs_cents": total_cogs,
        "suggested_price_cents": suggested_price,
        "production_budget_cents": total_cogs,  # the variable-spend ceiling == COGS
    }

    # -- COST-PLUS PRICING (flag-gated) -------------------------------------
    # When WS_PREMIUM_MENU=1, the LOCKED budget + customer price come from the
    # COST-PLUS model (pricing.py): the customer price is the plan's REAL COGS x a
    # markup (floored, rounded). The ONE customer choice — QUALITY (standard |
    # premium) — changes WHAT the plan COGS IS: standard zeroes the Higgsfield
    # (cinematic) + ElevenLabs (VO) spend (Remotion + edge-tts are free) so the
    # price floors at $5; premium keeps that spend so the price rises (~$6-9). We
    # OVERRIDE the price NUMBER only; the per-scene/VO estimate report (and the
    # gate's per-scene reasoning) is unchanged, and the budget gate + Stripe
    # authorize paths are untouched. With the flag OFF this block does nothing and
    # the return above is byte-identical to baseline.
    if _premium_menu_enabled():
        _apply_premium_menu(result, plan)

    return result


# ---------------------------------------------------------------------------
# Cost-plus pricing (flag-gated; OFF path byte-identical)
# ---------------------------------------------------------------------------

def _premium_menu_enabled():
    """True iff env WS_PREMIUM_MENU is a truthy flag ('1'/'true'/'yes', case-insensitive)."""
    return os.environ.get("WS_PREMIUM_MENU", "").strip().lower() in ("1", "true", "yes", "on")


def _quality_resolved_cogs(result, quality, pricing):
    """The plan COGS the cost-plus price is computed FROM, after applying quality.

    The estimate report's `total_cogs_cents` is the FULL spend if every cinematic
    scene used Higgsfield and the VO used ElevenLabs. The quality choice changes
    which of those actually get produced:

      * standard -> NO Higgsfield (cinematic scenes fall back to free Remotion) and
        NO ElevenLabs (VO uses free edge-tts). So we SUBTRACT the cinematic scene
        costs + the VO cost from the rollup -> only the free scenes remain (= 0) ->
        the price floors at $5.
      * premium  -> keep the full spend (Higgsfield clips + ElevenLabs VO), then
        apply the tier's `cogs_floor_cents` minimum so premium always reads as the
        richer tier even on a thin plan.

    Returns the integer COGS (cents) to price the chosen quality from.
    """
    full_cogs = int(result.get("total_cogs_cents") or 0)
    if pricing.quality_uses_higgsfield(quality):
        # premium: full Higgsfield + ElevenLabs spend, floored to the tier minimum.
        return max(full_cogs, pricing.quality_cogs_floor_cents(quality))
    # standard: drop the Higgsfield (cinematic) spend + the ElevenLabs (VO) spend.
    cinematic_cents = sum(int(s.get("est_cost_cents") or 0)
                          for s in result.get("scenes", [])
                          if s.get("type") == "cinematic")
    vo_cents = int((result.get("voiceover") or {}).get("est_cost_cents") or 0)
    standard_cogs = full_cogs - cinematic_cents - vo_cents
    return max(0, standard_cogs, pricing.quality_cogs_floor_cents(quality))


def _apply_premium_menu(result, plan):
    """Override the locked budget + customer price with the COST-PLUS quote.

    Mutates `result` IN PLACE, adding:
      * pricing_mode = "cost_plus"
      * selection                (the resolved {quality} selection)
      * quality                  (the resolved tier: "standard" | "premium")
      * menu = price_for_plan(quality_resolved_cogs, quality) output (line items)
      * production_budget_cents <- menu total_cogs (the variable-spend ceiling: the
                                   plan's REAL spend AT THE CHOSEN QUALITY)
      * suggested_price_cents   <- menu total_price (quality-resolved COGS x markup,
                                   floored, rounded)
      * menu_total_cogs_cents

    The PRICE is driven by the QUALITY-RESOLVED plan COGS: standard zeroes the
    Higgsfield + ElevenLabs spend (price floors at $5), premium keeps it (price
    rises). A plan with no `selection` uses pricing.default_selection() (standard).
    Import of pricing is local so the OFF path never even imports it.
    """
    import pricing  # local import: only loaded on the premium path

    selection = plan.get("selection") or pricing.default_selection()
    quality = pricing.quality_from_selection(selection)
    plan_cogs = _quality_resolved_cogs(result, quality, pricing)
    # Cost-plus quote: price = quality-resolved plan COGS x markup (floored/rounded).
    menu = pricing.price_for_plan(plan_cogs, quality=quality)

    result["pricing_mode"] = "cost_plus"
    result["selection"] = selection
    result["quality"] = quality
    result["menu"] = menu
    # The cost-plus quote is now the SOURCE OF TRUTH for the locked budget + price.
    # The locked budget (variable-spend ceiling) = the plan's real spend at the
    # chosen quality (premium covers Higgsfield + ElevenLabs; standard ~$0).
    result["production_budget_cents"] = menu["total_cogs_cents"]
    result["suggested_price_cents"] = menu["total_price_cents"]
    # Keep a menu COGS mirror so downstream readers (ledger, dashboard) stay consistent.
    result["menu_total_cogs_cents"] = menu["total_cogs_cents"]


def _distribute(total, weights):
    """Split `total` across len(weights) buckets proportional to weights.

    Uses a largest-remainder method so the parts sum exactly to `total`
    (integer cents, no rounding drift). If all weights are zero, splits evenly.
    """
    n = len(weights)
    if n == 0:
        return []
    wsum = sum(weights)
    if wsum <= 0:
        base = total // n
        out = [base] * n
        for i in range(total - base * n):
            out[i] += 1
        return out

    raw = [total * w / wsum for w in weights]
    floors = [int(r) for r in raw]
    remainder = total - sum(floors)
    # Hand out the leftover cents to the largest fractional remainders.
    order = sorted(range(n), key=lambda i: raw[i] - floors[i], reverse=True)
    for i in range(remainder):
        floors[order[i % n]] += 1
    return floors


# ---------------------------------------------------------------------------
# gate subcommand
# ---------------------------------------------------------------------------

def cmd_gate(plan, scene_id, proposed_cost_cents, spent_cents, budget_cents=None):
    job = plan.get("job", {})
    target_margin = float(job.get("target_margin", 0.0))

    # Production budget == COGS (the variable-spend ceiling). It is LOCKED at job
    # start from the original estimate; the orchestrator passes it back here via
    # budget_cents so a mid-job model downgrade (which lowers a re-priced plan's
    # COGS) can never silently shrink the ceiling. With no override we recompute
    # from the plan (the original CLI contract, still used by ad-hoc gate calls).
    if budget_cents is not None:
        production_budget = budget_cents
    else:
        est = cmd_estimate(plan)
        production_budget = est["total_cogs_cents"]
    remaining = production_budget - spent_cents

    scene = next((s for s in plan.get("scenes", []) if s.get("id") == scene_id), None)
    stype = scene.get("type") if scene else None
    cheaper = CHEAPER_MODEL.get(stype)

    # No real downgrade if the scene is already on the cheapest model for its
    # type (e.g. a cinematic already on gpt_image_2). Otherwise we'd "downgrade"
    # a model to itself; over budget with no cheaper option must decline.
    current_model = scene.get("model") if scene else None
    if cheaper is not None and current_model == cheaper:
        cheaper = None

    if proposed_cost_cents <= remaining:
        decision = "approve"
        reason = ("proposed %dc fits remaining budget %dc"
                  % (proposed_cost_cents, remaining))
        suggested = None
    elif cheaper is not None:
        decision = "downgrade"
        reason = ("proposed %dc exceeds remaining %dc; cheaper model available "
                  "for a %s scene" % (proposed_cost_cents, remaining, stype))
        suggested = cheaper
    else:
        decision = "decline"
        reason = ("proposed %dc exceeds remaining %dc and no cheaper model "
                  "exists for a %s scene -- cut the scene or approve overage"
                  % (proposed_cost_cents, remaining, stype if stype else "unknown"))
        suggested = None

    return {
        "scene": scene_id,
        "scene_type": stype,
        "decision": decision,
        "reason": reason,
        "remaining_budget_cents": remaining,
        "suggested_cheaper_model": suggested,
        "production_budget_cents": production_budget,
        "spent_cents": spent_cents,
        "proposed_cost_cents": proposed_cost_cents,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def load_plan(path):
    with open(path, "r") as f:
        return json.load(f)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="producer.py",
        description="Hermes video-agent deterministic pricing + budget engine.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_est = sub.add_parser("estimate", help="price a scene plan")
    p_est.add_argument("--plan", required=True, help="path to plan.json")

    p_gate = sub.add_parser("gate", help="approve/downgrade/decline a scene spend")
    p_gate.add_argument("--plan", required=True, help="path to plan.json")
    p_gate.add_argument("--scene", required=True, help="scene id")
    p_gate.add_argument("--proposed_cost_cents", required=True, type=int)
    p_gate.add_argument("--spent_cents", required=True, type=int)
    p_gate.add_argument("--budget_cents", type=int, default=None,
                        help="lock the production budget (skip estimate recompute)")

    args = parser.parse_args(argv)
    plan = load_plan(args.plan)

    if args.command == "estimate":
        result = cmd_estimate(plan)
    elif args.command == "gate":
        result = cmd_gate(plan, args.scene, args.proposed_cost_cents, args.spent_cents,
                          budget_cents=args.budget_cents)
    else:  # pragma: no cover - argparse enforces this
        parser.error("unknown command")

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
