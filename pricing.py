#!/usr/bin/env python3
"""Walk Studio COST-PLUS PRICING — thin loader/API over pricing.json.

Single dependency-free module that the produce-side (producer.py / orchestrator)
and the dashboard both price against. pricing.json is the ONLY source of numbers;
this module just loads it and turns the agent's real production COGS (its scene
plan) into a customer price.

THE MODEL (decided with Dennis): NO TIERS. The price is the agent's REAL
production COGS x a MARKUP, with a price FLOOR, rounded to a clean increment:

    price_cents = max(price_floor_cents,
                      round_to_nearest(plan_cogs_cents * markup, round_to_cents))

There is exactly ONE customer choice, made UPFRONT: a QUALITY dimension
(standard | premium). It is NOT a flat add-on — it changes WHAT THE AGENT
PRODUCES and therefore the plan COGS that drives the cost-plus price:

  * standard = Remotion designed motion-graphics + edge-tts voiceover. NO
    Higgsfield, NO ElevenLabs. COGS is ~free, so the price lands at the floor
    (~$5). Cheapest, deterministic, fast.
  * premium = adds cinematic AI footage (Higgsfield) + a natural ElevenLabs
    voiceover. Those land in COGS, so the cost-plus price rises (~$6-9). Richer
    and more lifelike.

All money is integer CENTS (USD), matching producer.py.

This module is import-safe and has NO side effects beyond reading pricing.json off
disk on demand. It is only WIRED INTO producer.py behind env WS_PREMIUM_MENU=1; on
its own it changes nothing.

--------------------------------------------------------------------------------
SELECTION shape (the contract the dashboard + plan_schema.selection share)
--------------------------------------------------------------------------------
    { "quality": "standard" | "premium" }

The default selection is {"quality": "standard"}.

BACK-COMPAT: the previous shapes still PARSE. A legacy
{"options": {"premium_vo": true}} maps to "premium"; an even older
{"boosters": ["founder_voice", ...]} also maps to "premium". `quality_from_selection`
(and the retained `addons_from_selection` shim) absorb all of them.

--------------------------------------------------------------------------------
price_for_plan(plan_cogs_cents, quality="standard") output shape
--------------------------------------------------------------------------------
    {
      "model": "cost_plus",
      "quality": "standard" | "premium",
      "line_items": [
        {"key": "video_production", "label": "Video production", "qty": 1,
         "unit_price_cents": <price>, "unit_cogs_cents": <plan_cogs_cents>,
         "price_cents": <price>,       "cogs_cents": <plan_cogs_cents>}
      ],
      "base_price_cents": <price>,          # == total_price (no add-ons in this model)
      "plan_cogs_cents": <plan_cogs_cents>, # the production COGS that drove the price
      "total_price_cents": <int>,
      "total_cogs_cents": <int>,
      "margin": <float>                     # (price - cogs) / price, 0.0 when price == 0
    }

There is exactly ONE line item ("Video production"); quality is reflected in the
COGS that drove the price (and recorded as `quote["quality"]`), NOT as a separate
surcharge line. The COGS handed in is expected to already be the QUALITY-RESOLVED
plan COGS (the producer zeroes Higgsfield/ElevenLabs for standard and includes
them for premium before calling here).

--------------------------------------------------------------------------------
RETIRED (kept in code, DORMANT — not surfaced or selected anymore)
--------------------------------------------------------------------------------
  * `price_selection(selection)` — the old tier+booster pricer. Kept as a
    BACK-COMPAT SHIM that maps an old/new selection onto the cost-plus model.
  * `addons_from_selection(selection)` — kept for back-compat; now derives the
    boolean {premium_vo} purely from the resolved quality (premium -> True).
  * `validate_consent(selection)` + the public-figure / third-party refusal
    heuristic — the voice-clone guardrail. There is NO voice cloning in the active
    flow (premium uses an ElevenLabs STOCK voice), so this is UNUSED by the active
    path. It remains importable so nothing that referenced it breaks.
"""

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
PRICING_PATH = os.path.join(HERE, "pricing.json")

# Quality tier keys (the single customer choice, made upfront).
QUALITY_STANDARD = "standard"
QUALITY_PREMIUM = "premium"
VALID_QUALITY = (QUALITY_STANDARD, QUALITY_PREMIUM)

# Stable, human-readable labels per line-item key. Consumers may match on these.
LINE_LABELS = {
    "video_production": "Video production",
}


class PricingError(ValueError):
    """Selection violated a shape rule (4xx-style, caller's fault)."""


class ConsentRefused(PricingError):
    """RETIRED guardrail (kept for back-compat). The active cost-plus flow uses a
    STOCK voice for the premium tier, so no voice clone is ever consent-gated."""


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

def load_pricing(path=None):
    """Load and return the parsed pricing.json dict. Reads from disk each call
    (cheap, and keeps tests free to point at a temp file via the `path` arg or
    the WS_PRICING_PATH env override)."""
    p = path or os.environ.get("WS_PRICING_PATH") or PRICING_PATH
    with open(p, "r") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Quality helpers
# ---------------------------------------------------------------------------

def default_quality(pricing=None):
    """The configured default quality tier ('standard')."""
    pricing = pricing or load_pricing()
    q = ((pricing.get("quality") or {}).get("default") or QUALITY_STANDARD)
    return q if q in VALID_QUALITY else QUALITY_STANDARD


def normalize_quality(quality, pricing=None):
    """Coerce an arbitrary quality value onto a valid tier (default on miss)."""
    q = str(quality or "").strip().lower()
    return q if q in VALID_QUALITY else default_quality(pricing=pricing)


def quality_def(quality, pricing=None):
    """The full config block for a quality tier (label/blurb/uses_* flags/cogs_floor)."""
    pricing = pricing or load_pricing()
    q = normalize_quality(quality, pricing=pricing)
    return (pricing.get("quality") or {}).get(q) or {}


def quality_uses_higgsfield(quality, pricing=None):
    """True iff the tier produces cinematic AI footage via Higgsfield (premium)."""
    return bool(quality_def(quality, pricing=pricing).get("uses_higgsfield"))


def quality_uses_elevenlabs(quality, pricing=None):
    """True iff the tier voices with a natural ElevenLabs voice (premium)."""
    return bool(quality_def(quality, pricing=pricing).get("uses_elevenlabs"))


def quality_cogs_floor_cents(quality, pricing=None):
    """A minimum plan COGS for the tier (premium reads richer even on a thin plan)."""
    try:
        return int(quality_def(quality, pricing=pricing).get("cogs_floor_cents") or 0)
    except (TypeError, ValueError):
        return 0


def quality_from_selection(selection, pricing=None):
    """Resolve a SELECTION (new or legacy) onto a valid quality tier.

    New selection: {"quality": "standard"|"premium"}.
    Legacy: {"options": {"premium_vo": true}} -> premium; an even older
    {"boosters": ["founder_voice"]} -> premium. Anything else -> the default.
    """
    selection = selection or {}
    if "quality" in selection:
        return normalize_quality(selection.get("quality"), pricing=pricing)
    # Legacy bridges.
    options = selection.get("options") or {}
    if bool(options.get("premium_vo")):
        return QUALITY_PREMIUM
    if "founder_voice" in list(selection.get("boosters") or []):
        return QUALITY_PREMIUM
    return default_quality(pricing=pricing)


# ---------------------------------------------------------------------------
# Cost-plus math
# ---------------------------------------------------------------------------

def _round_to(value, increment):
    """Round `value` to the nearest `increment` (>=1). Half-up on the increment."""
    increment = int(increment)
    if increment <= 1:
        return int(round(value))
    return int(round(value / increment) * increment)


def base_price_for_cogs(plan_cogs_cents, pricing=None):
    """The cost-plus price: max(floor, round(plan_cogs * markup, round_to)).

    The agent's real COGS x markup, floored, rounded. This IS the full price in
    the quality model (no flat add-ons).
    """
    pricing = pricing or load_pricing()
    try:
        cogs = max(0, int(plan_cogs_cents))
    except (TypeError, ValueError):
        raise PricingError("plan_cogs_cents must be an integer (got %r)" % plan_cogs_cents)
    markup = float(pricing.get("markup", 6.0))
    floor = int(pricing.get("price_floor_cents", 500))
    round_to = int(pricing.get("round_to_cents", 50))
    marked_up = _round_to(cogs * markup, round_to)
    return max(floor, marked_up)


def price_for_plan(plan_cogs_cents, quality=None, pricing=None):
    """Resolve the agent's (quality-resolved) plan COGS into a cost-plus quote.

    `quality` is "standard"|"premium" (default = the configured default). The COGS
    handed in is expected to already reflect the quality (the producer zeroes
    Higgsfield/ElevenLabs for standard and includes them for premium). Returns the
    documented cost-plus dict. Raises only on a non-integer plan_cogs_cents.
    """
    pricing = pricing or load_pricing()
    q = normalize_quality(quality, pricing=pricing)
    base_price = base_price_for_cogs(plan_cogs_cents, pricing=pricing)
    plan_cogs = max(0, int(plan_cogs_cents))

    line_items = [{
        "key": "video_production",
        "label": LINE_LABELS["video_production"],
        "qty": 1,
        "unit_price_cents": base_price,
        "unit_cogs_cents": plan_cogs,
        "price_cents": base_price,
        "cogs_cents": plan_cogs,
    }]

    total_price = sum(li["price_cents"] for li in line_items)
    total_cogs = sum(li["cogs_cents"] for li in line_items)
    margin = 0.0 if total_price == 0 else (total_price - total_cogs) / total_price

    return {
        "model": "cost_plus",
        "quality": q,
        "line_items": line_items,
        "base_price_cents": base_price,
        "plan_cogs_cents": plan_cogs,
        "total_price_cents": total_price,
        "total_cogs_cents": total_cogs,
        "margin": margin,
    }


def price_for_selection(selection, plan_cogs_cents, pricing=None):
    """Convenience: resolve a SELECTION + the plan's (quality-resolved) COGS into a
    cost-plus quote. The active produce path uses this — it reads the plan's
    estimated COGS and the customer's quality choice."""
    return price_for_plan(plan_cogs_cents,
                          quality=quality_from_selection(selection, pricing=pricing),
                          pricing=pricing)


def default_selection():
    """The documented default selection: standard quality."""
    return {"quality": QUALITY_STANDARD}


# ---------------------------------------------------------------------------
# RETIRED back-compat shims (dormant — not surfaced or selected in the active flow)
# ---------------------------------------------------------------------------

def addons_from_selection(selection):
    """BACK-COMPAT shim. The active model has no flat add-ons; the only customer
    choice is quality. We keep this returning the old {premium_vo: bool} shape so a
    stale caller still works — premium quality maps to premium_vo=True."""
    return {"premium_vo": quality_from_selection(selection) == QUALITY_PREMIUM}


def price_selection(selection, pricing=None, plan_cogs_cents=0):
    """BACK-COMPAT SHIM for the retired tier+booster pricer.

    Maps whatever selection it is handed (old or new) onto the cost-plus model via
    `price_for_selection`, using `plan_cogs_cents` (default 0 -> the price floor)
    as the production COGS. Kept ONLY so a stale caller still gets a coherent quote;
    the active path calls price_for_plan / price_for_selection directly.
    """
    return price_for_selection(selection, plan_cogs_cents, pricing=pricing)


# --- RETIRED voice-clone consent guardrail (UNUSED by the active flow) ------
# The active cost-plus flow uses an ElevenLabs STOCK voice for the premium tier,
# which is NOT a clone, so nothing is consent-gated anymore. These are kept
# importable so any lingering reference does not break, but the active produce path
# no longer calls validate_consent. Do NOT re-surface voice cloning without
# re-instating a consent gate.
_THIRD_PARTY_MARKERS = (
    "friend", "celebrity", "public figure", "famous", "the president",
    "president ", "senator", "governor", "ceo of", "actor", "actress",
    "singer", "musician", "influencer", "youtuber", "streamer", "podcaster",
    "someone else", "third party", "third-party", "client's", "their voice",
    "on behalf of", "impersonat",
)
_PUBLIC_FIGURE_DENYLIST = (
    "morgan freeman", "david attenborough", "barack obama", "donald trump",
    "elon musk", "taylor swift", "oprah", "scarlett johansson", "joe rogan",
    "snoop dogg", "samuel l jackson", "samuel l. jackson",
)
_GENERIC_PLACEHOLDERS = (
    "n/a", "na", "none", "unknown", "anonymous", "test", "someone", "owner",
    "founder",
)


def _looks_third_party(owner):
    """RETIRED. Return (is_refused, why) for an owner string. Unused by active flow."""
    low = owner.strip().lower()
    for fig in _PUBLIC_FIGURE_DENYLIST:
        if fig in low:
            return True, "named owner %r matches a known public figure" % owner
    for marker in _THIRD_PARTY_MARKERS:
        if marker in low:
            return True, "named owner %r reads as a third party / public figure" % owner
    if low in _GENERIC_PLACEHOLDERS:
        return True, "named owner %r is a generic placeholder, not a first-party identity" % owner
    return False, ""


def validate_consent(selection):
    """RETIRED voice-clone consent guardrail (kept importable, UNUSED).

    The active flow no longer clones voices (premium = stock voice), so there is
    nothing to consent-gate; this always returns ok=True for the active shape. If a
    legacy `founder_voice` booster is present it still evaluates the old heuristic so
    historical callers behave as before, but the active produce path never calls it.
    """
    selection = selection or {}
    boosters = list(selection.get("boosters") or [])
    if "founder_voice" not in boosters:
        return True, "no consent-gated boosters (cost-plus uses a stock voice)"
    # Legacy path only — evaluate the old heuristic for back-compat.
    options = selection.get("options") or {}
    consent = options.get("consent") or {}
    attested = consent.get("attested")
    owner = str(consent.get("owner") or "").strip()
    if attested is not True:
        return False, ("founder_voice requires an explicit consent attestation "
                       "(options.consent.attested must be true)")
    if not owner:
        return False, ("founder_voice requires a named first-party voice owner "
                       "(options.consent.owner must be non-empty)")
    refused, why = _looks_third_party(owner)
    if refused:
        return False, ("refusing to clone a voice that is not the consenting "
                       "first party: " + why)
    return True, "consent attested by %r" % owner


if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 2 and sys.argv[1] == "price":
        cogs = int(sys.argv[2]) if len(sys.argv) > 2 else 0
        quality = sys.argv[3] if len(sys.argv) > 3 else None
        print(json.dumps(price_for_plan(cogs, quality), indent=2))
    else:
        print(json.dumps(load_pricing(), indent=2))
