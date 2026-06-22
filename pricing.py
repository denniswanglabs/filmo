#!/usr/bin/env python3
"""Walk Studio DYNAMIC BANDED PRICING — thin loader/API over pricing.json.

Single dependency-free module that the produce-side (producer.py / orchestrator)
and the dashboard both price against. pricing.json is the ONLY source of numbers;
this module loads it and turns the storyboard signals + a token-cost COGS line into
a customer price, clamped to the chosen quality tier's PRICE BAND.

THE MODEL (decided with Dennis): the customer PRICE is DYNAMIC — derived from the
STORYBOARD (scene count, cinematic scene count, total duration) PLUS the planner
token COGS, then CLAMPED to a per-tier band:

    standard = 500 + 50*max(0, scenes-3) + 50*ceil(max(0, dur_s-20)/10)
                   + token_cost_cents,                       clamp [500, 1000]
    premium  = 1500 + 150*cinematic_count + 100*ceil(max(0, dur_s-20)/10)
                    + vo_surcharge + token_cost_cents,        clamp [1500, 2500]

`price_for_plan(plan_cogs_cents, quality, signals=...)` is the single customer-price
function. WITHOUT `signals` it still resolves a coherent quote (price = the tier's
band MINIMUM, so existing callers keep working). WITH `signals` (threaded from the
producer est) it computes the dynamic banded price and an ITEMIZED breakdown.

There is exactly ONE customer choice, made UPFRONT: a QUALITY dimension
(standard | premium). It changes WHAT THE AGENT PRODUCES (and therefore the plan
COGS the budget gate locks) AND which band/formula prices it:

  * standard ($5-$10 band) = Remotion designed motion-graphics + edge-tts voiceover.
    NO Higgsfield, NO ElevenLabs. Media COGS ~free; only the planner token COGS
    lands. Cheapest, deterministic, fast.
  * premium ($15-$25 band) = adds cinematic AI footage (Higgsfield) + a natural
    ElevenLabs voiceover. Those land in COGS (the budget-gate ceiling); the price
    scales with cinematic count + duration + VO inside the band. Richer/lifelike.

TOKEN COST -> COGS: the planner (brain) tokens used to plan the storyboard are
estimated from the VO script length + scene count and priced via
`token_rate_cents_per_1k` (per brain) in pricing.json. The token COGS is FOLDED into
total COGS for BOTH the budget gate AND the price floor. `walkthrough_steps` is a
future hook (Walk-Agent walkthroughs ~15 ultra-proposer + ~30 nano-judge calls per
run) — defaults to 0 today.

The old cost-plus knobs (markup / price_floor_cents / round_to_cents) and
`base_price_for_cogs`, and the flat `tier_price_cents`, are RETAINED for back-compat
but no longer drive the customer price; `price_for_plan` returns the banded price.

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
price_for_plan(plan_cogs_cents, quality="standard", signals=None) output shape
--------------------------------------------------------------------------------
    {
      "model": "dynamic_banded",
      "quality": "standard" | "premium",
      "line_items": [                       # itemized, storyboard-derived
        {"key": "base",       "label": "Base fee",        "amount_cents": <int>},
        {"key": "scenes",     "label": "+N extra scenes", "amount_cents": <int>},
        {"key": "duration",   "label": "+Ns over base",   "amount_cents": <int>},
        {"key": "cinematic",  "label": "N cinematic shots","amount_cents": <int>},
        {"key": "voiceover",  "label": "Studio voiceover", "amount_cents": <int>},
        {"key": "tokens",     "label": "Planner tokens",   "amount_cents": <int>}
      ],
      "band": {"min_cents": <int>, "max_cents": <int>},
      "base_price_cents": <price>,          # == total_price (the clamped banded price)
      "plan_cogs_cents": <plan_cogs_cents>, # the production COGS (incl token) that drove margin
      "total_price_cents": <int>,           # banded price, clamped to [band.min, band.max]
      "total_cogs_cents": <int>,
      "margin": <float>                     # (price - cogs) / price, 0.0 when price == 0
    }

Each line item carries {key, label, amount_cents}; the sum of amounts (before the
band clamp) is the raw banded price. `total_price_cents` is that sum CLAMPED to the
tier band. The COGS handed in is expected to already be the QUALITY-RESOLVED plan
COGS INCLUDING the planner token COGS (the producer zeroes Higgsfield/ElevenLabs for
standard, keeps them for premium, and adds the token COGS, before calling here).
WITHOUT `signals`, line_items collapses to a single base line at the band minimum.

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
import math
import os
import time

HERE = os.path.dirname(os.path.abspath(__file__))
# NOTE: pricing.json is read by load_pricing() each call. If any process ever writes
# this config (or any sibling config file) at runtime, it MUST do so ATOMICALLY —
# write a temp file then os.replace(tmp, path) — so a concurrent reader never sees a
# half-written/torn file (see ledger.py:write for the canonical pattern). A raw
# `open(path, "w")` + `json.dump` is NOT safe: the reader can catch it mid-write and
# raise JSONDecodeError (the failed luceostudio build). Today nothing writes
# pricing.json at runtime (it is static config), so the loader's retry is the only
# guard; keep it that way or use the atomic helper.
PRICING_PATH = os.path.join(HERE, "pricing.json")

# Quality tier keys (the single customer choice, made upfront).
QUALITY_STANDARD = "standard"
QUALITY_PREMIUM = "premium"
VALID_QUALITY = (QUALITY_STANDARD, QUALITY_PREMIUM)

# Stable, human-readable labels per line-item key. Consumers may match on these.
# `video_production` is the legacy single-line label (still used by the back-compat
# single-line path); the dynamic banded path uses the itemized labels below.
LINE_LABELS = {
    "video_production": "Video production",
    "base": "Base fee",
    "scenes": "Extra scenes",
    "duration": "Duration",
    "cinematic": "Cinematic shots",
    "voiceover": "Studio voiceover",
    "tokens": "Planner tokens",
}

# Band defaults, used only if pricing.json is missing price_band_cents for a tier.
# Mirror the brief: standard $5-$10, premium $15-$25.
_PRICE_BAND_FALLBACK_CENTS = {
    QUALITY_STANDARD: {"min": 500, "max": 1000},
    QUALITY_PREMIUM: {"min": 1500, "max": 2500},
}

# Token-rate fallback (cents per 1000 tokens, per brain). Used only if pricing.json
# is missing token_rate_cents_per_1k. Derived from brain.py per-1M rates / 1000.
_TOKEN_RATE_FALLBACK = {
    "super-free": {"input": 0.0, "output": 0.0},
    "super-paid": {"input": 0.009, "output": 0.045},
    "ultra-paid": {"input": 0.05, "output": 0.22},
}

# Per-tier price-formula constants (the brief's locked numbers). Kept in code (not
# pricing.json) because they ARE the model; the band clamp lives in pricing.json.
STANDARD_BASE_CENTS = 500
STANDARD_PER_SCENE_CENTS = 50           # per scene beyond the first 3
STANDARD_PER_DURATION_BLOCK_CENTS = 50  # per 10s beyond the first 20s
PREMIUM_BASE_CENTS = 1500
PREMIUM_PER_CINEMATIC_CENTS = 150       # per cinematic scene
PREMIUM_PER_DURATION_BLOCK_CENTS = 100  # per 10s beyond the first 20s
PREMIUM_VO_SURCHARGE_CENTS = 300        # natural ElevenLabs voiceover, when present
DURATION_BASE_S = 20                    # free duration before the per-block charge
DURATION_BLOCK_S = 10                   # block size for the duration charge
FREE_SCENES = 3                         # scenes included before the per-scene charge

# Planner token estimation. Storyboard planning consumes prompt tokens roughly
# proportional to the brief + brand facts + per-scene reasoning, and completion
# tokens proportional to the produced plan (VO script + scene list). These are
# deliberately rough, deterministic estimates — token COGS is a small COGS line,
# not a billed meter.
TOKENS_PROMPT_BASE = 600                 # system prompt + brief + facts overhead
TOKENS_PROMPT_PER_SCENE = 40             # per-scene planning context
TOKENS_OUTPUT_PER_SCENE = 60             # per-scene plan emitted
TOKENS_OUTPUT_PER_VO_CHAR = 0.4         # completion tokens ~ VO script chars * this
# Future Walk-Agent walkthrough hook: each walkthrough step drives ~15 ultra
# proposer + ~30 nano judge Nemotron calls. Left as a costed hook; default 0 steps.
TOKENS_PER_WALKTHROUGH_STEP_PROMPT = 0   # TODO: cost real walkthrough proposer tokens
TOKENS_PER_WALKTHROUGH_STEP_OUTPUT = 0   # TODO: cost real walkthrough judge tokens


class PricingError(ValueError):
    """Selection violated a shape rule (4xx-style, caller's fault)."""


class ConsentRefused(PricingError):
    """RETIRED guardrail (kept for back-compat). The active cost-plus flow uses a
    STOCK voice for the premium tier, so no voice clone is ever consent-gated."""


class PricingConfigError(PricingError):
    """pricing.json is missing or malformed (corrupt JSON / torn mid-write).

    Raised by load_pricing() with a clear message + path instead of leaking a raw
    json.JSONDecodeError, so a config-race crash is diagnosable rather than cryptic.
    Subclasses PricingError (ValueError) so existing `except PricingError`/
    `except ValueError` callers still catch it (back-compatible)."""


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

def load_pricing(path=None):
    """Load and return the parsed pricing.json dict. Reads from disk each call
    (cheap, and keeps tests free to point at a temp file via the `path` arg or
    the WS_PRICING_PATH env override).

    Hardened against the reader-sees-partial-file race (the failed luceostudio
    build): if json.load hits a JSONDecodeError, a writer may be mid-save, so we
    retry ONCE after a tiny sleep. If it still won't parse, raise a clear
    PricingConfigError naming the path instead of leaking the raw decode error.
    Returns the parsed dict unchanged, so all existing callers are unaffected."""
    p = path or os.environ.get("WS_PRICING_PATH") or PRICING_PATH
    for attempt in range(2):  # one retry: a writer may be mid-save
        try:
            with open(p, "r") as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            if attempt == 0:
                time.sleep(0.05)  # let an in-flight (non-atomic) write finish
                continue
            raise PricingConfigError(
                "malformed pricing config %s: %s" % (p, e)) from e


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
    """A minimum plan COGS for the tier (premium reads richer even on a thin plan).

    NOTE: this is on the COGS/budget side, NOT the customer price. The customer
    price is the fixed tier price (see `tier_price_cents`)."""
    try:
        return int(quality_def(quality, pricing=pricing).get("cogs_floor_cents") or 0)
    except (TypeError, ValueError):
        return 0


# Fallback fixed tier prices, used only if pricing.json is missing tier_price_cents
# for a tier (it shouldn't be). standard -> $9.99, premium -> $19.99.
_TIER_PRICE_FALLBACK_CENTS = {
    QUALITY_STANDARD: 999,
    QUALITY_PREMIUM: 1999,
}


def tier_price_cents(quality, pricing=None):
    """The FIXED customer price for a quality tier, in integer cents.

    This is the single source of truth for what the customer PAYS:
      standard -> 999 ($9.99), premium -> 1999 ($19.99).
    Reads quality.<tier>.tier_price_cents from pricing.json; falls back to the
    built-in defaults if that key is absent. This is the customer PRICE only and
    is independent of the plan COGS / budget-gate ceiling."""
    pricing = pricing or load_pricing()
    q = normalize_quality(quality, pricing=pricing)
    raw = quality_def(q, pricing=pricing).get("tier_price_cents")
    if raw is None:
        return _TIER_PRICE_FALLBACK_CENTS[q]
    try:
        return int(raw)
    except (TypeError, ValueError):
        return _TIER_PRICE_FALLBACK_CENTS[q]


def price_band_cents(quality, pricing=None):
    """The (min_cents, max_cents) PRICE BAND the dynamic price is clamped to.

    Reads quality.<tier>.price_band_cents from pricing.json; falls back to the
    built-in band defaults (standard $5-$10, premium $15-$25) if absent. The band
    is the customer-price clamp: the storyboard-derived raw price can never fall
    below min or rise above max for the chosen tier."""
    pricing = pricing or load_pricing()
    q = normalize_quality(quality, pricing=pricing)
    band = quality_def(q, pricing=pricing).get("price_band_cents") or {}
    fb = _PRICE_BAND_FALLBACK_CENTS[q]
    try:
        lo = int(band.get("min", fb["min"]))
        hi = int(band.get("max", fb["max"]))
    except (TypeError, ValueError):
        lo, hi = fb["min"], fb["max"]
    if hi < lo:
        lo, hi = hi, lo
    return lo, hi


# ---------------------------------------------------------------------------
# Token-cost COGS (planner brain tokens -> cents)
# ---------------------------------------------------------------------------

def _token_rate(brain, pricing=None):
    """The {input, output} cents-per-1k-tokens rate for a brain key.

    Reads token_rate_cents_per_1k.<brain> from pricing.json (falls back to the
    built-in table). Unknown/empty brain -> super-free (0/0), so token COGS never
    surprises a free build."""
    pricing = pricing or load_pricing()
    table = pricing.get("token_rate_cents_per_1k") or {}
    b = str(brain or "").strip().lower() or "super-free"
    rate = table.get(b) or _TOKEN_RATE_FALLBACK.get(b) or {"input": 0.0, "output": 0.0}
    try:
        return float(rate.get("input", 0.0)), float(rate.get("output", 0.0))
    except (TypeError, ValueError):
        return 0.0, 0.0


def estimate_planner_tokens(scenes=0, vo_chars=0, walkthrough_steps=0):
    """Estimate (prompt_tokens, output_tokens) the planner brain spends on a plan.

    Rough, deterministic estimate from the storyboard size: prompt tokens scale
    with a fixed overhead + per-scene planning context; output tokens scale with
    the per-scene plan + the VO script length. `walkthrough_steps` is the future
    Walk-Agent hook (default 0 -> no token cost today; see the TODO constants)."""
    scenes = max(0, int(scenes or 0))
    vo_chars = max(0, int(vo_chars or 0))
    steps = max(0, int(walkthrough_steps or 0))
    prompt = (TOKENS_PROMPT_BASE
              + TOKENS_PROMPT_PER_SCENE * scenes
              + TOKENS_PER_WALKTHROUGH_STEP_PROMPT * steps)
    output = (TOKENS_OUTPUT_PER_SCENE * scenes
              + int(round(TOKENS_OUTPUT_PER_VO_CHAR * vo_chars))
              + TOKENS_PER_WALKTHROUGH_STEP_OUTPUT * steps)
    return int(prompt), int(output)


def token_cost_cents(brain, scenes=0, vo_chars=0, walkthrough_steps=0, pricing=None):
    """Planner token COGS in integer cents for a (brain, storyboard) pair.

    Estimates planner tokens (estimate_planner_tokens) and prices them at the
    brain's per-1k rate. super-free -> 0. Rounded up to the next whole cent when
    non-zero so a tiny real cost never disappears into 0 (but free stays free)."""
    prompt_tok, output_tok = estimate_planner_tokens(
        scenes=scenes, vo_chars=vo_chars, walkthrough_steps=walkthrough_steps)
    in_rate, out_rate = _token_rate(brain, pricing=pricing)
    cents = (prompt_tok / 1000.0) * in_rate + (output_tok / 1000.0) * out_rate
    if cents <= 0:
        return 0
    return int(math.ceil(cents))


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


def _duration_blocks(duration_s):
    """Number of charged duration blocks: ceil(max(0, dur-20)/10)."""
    over = max(0, float(duration_s or 0) - DURATION_BASE_S)
    if over <= 0:
        return 0
    return int(math.ceil(over / float(DURATION_BLOCK_S)))


def _dynamic_line_items(quality, signals, token_cost):
    """Build the itemized {key,label,amount_cents} list for the dynamic price.

    `signals` carries the storyboard: scenes, cinematic_count, duration_s, uses_vo.
    `token_cost` is the already-computed planner token COGS in cents. Returns the
    raw (pre-clamp) line items; the caller sums + clamps them to the band."""
    scenes = max(0, int(signals.get("scenes") or 0))
    cinematic = max(0, int(signals.get("cinematic_count") or 0))
    duration_s = float(signals.get("duration_s") or 0)
    uses_vo = bool(signals.get("uses_vo"))
    blocks = _duration_blocks(duration_s)
    items = []

    if quality == QUALITY_PREMIUM:
        items.append({"key": "base", "label": "Base fee (premium)",
                      "amount_cents": PREMIUM_BASE_CENTS})
        if cinematic > 0:
            items.append({"key": "cinematic",
                          "label": "%d cinematic shot%s" % (cinematic, "" if cinematic == 1 else "s"),
                          "amount_cents": PREMIUM_PER_CINEMATIC_CENTS * cinematic})
        if blocks > 0:
            items.append({"key": "duration",
                          "label": "+%ds over %ds" % (int(blocks * DURATION_BLOCK_S), DURATION_BASE_S),
                          "amount_cents": PREMIUM_PER_DURATION_BLOCK_CENTS * blocks})
        if uses_vo and PREMIUM_VO_SURCHARGE_CENTS:
            items.append({"key": "voiceover", "label": LINE_LABELS["voiceover"],
                          "amount_cents": PREMIUM_VO_SURCHARGE_CENTS})
    else:
        items.append({"key": "base", "label": "Base fee (standard)",
                      "amount_cents": STANDARD_BASE_CENTS})
        extra_scenes = max(0, scenes - FREE_SCENES)
        if extra_scenes > 0:
            items.append({"key": "scenes",
                          "label": "+%d scene%s over %d" % (extra_scenes, "" if extra_scenes == 1 else "s", FREE_SCENES),
                          "amount_cents": STANDARD_PER_SCENE_CENTS * extra_scenes})
        if blocks > 0:
            items.append({"key": "duration",
                          "label": "+%ds over %ds" % (int(blocks * DURATION_BLOCK_S), DURATION_BASE_S),
                          "amount_cents": STANDARD_PER_DURATION_BLOCK_CENTS * blocks})

    if token_cost > 0:
        items.append({"key": "tokens", "label": LINE_LABELS["tokens"],
                      "amount_cents": int(token_cost)})
    return _with_legacy_line_keys(items)


def _with_legacy_line_keys(items):
    """Backfill each {key,label,amount_cents} line with the LEGACY per-line keys
    (`qty`, `price_cents`, `cogs_cents`) the orchestrator's premium-ledger itemizer
    and the dashboard P&L still read. price_cents == amount_cents (the customer-facing
    per-line amount); cogs_cents == 0 per line (COGS is a quote TOTAL in the banded
    model, not a per-line split — the orchestrator reads total_cogs_cents). Mutates
    each dict in place and returns the list."""
    for li in items:
        amt = int(li.get("amount_cents") or 0)
        li.setdefault("qty", 1)
        li["price_cents"] = amt
        li.setdefault("cogs_cents", 0)
    return items


def price_for_plan(plan_cogs_cents, quality=None, pricing=None, signals=None):
    """Resolve the agent's (quality-resolved) plan COGS + storyboard into a DYNAMIC
    BANDED quote.

    `quality` is "standard"|"premium" (default = the configured default).

    WITHOUT `signals` (the existing-caller path): the price is the tier band's
    MINIMUM, with a single base line item, so legacy callers still get a coherent
    in-band quote.

    WITH `signals` (a dict with scenes / cinematic_count / duration_s / uses_vo /
    token_cost_cents / walkthrough_steps): the price is built from the storyboard
    per the tier formula, itemized, and CLAMPED to the tier's price band. The token
    COGS in `signals["token_cost_cents"]` is added BOTH as a price line item AND
    folded into the quote's total_cogs (the caller is expected to have already
    folded it into `plan_cogs_cents` for the budget gate; we record it on the quote).

    `plan_cogs_cents` is the production COGS (incl token) that records the budget
    ceiling and drives margin = (price - cogs) / price. Raises only on a non-integer
    plan_cogs_cents.
    """
    pricing = pricing or load_pricing()
    q = normalize_quality(quality, pricing=pricing)
    try:
        plan_cogs = max(0, int(plan_cogs_cents))
    except (TypeError, ValueError):
        raise PricingError("plan_cogs_cents must be an integer (got %r)" % plan_cogs_cents)

    band_min, band_max = price_band_cents(q, pricing=pricing)
    signals = signals or {}
    token_cost = max(0, int(signals.get("token_cost_cents") or 0))

    if not signals:
        # Existing-caller path: no storyboard signals -> price at the band floor,
        # single base line. (Token cost is 0 here because signals is empty.)
        line_items = _with_legacy_line_keys([
            {"key": "base", "label": LINE_LABELS["base"], "amount_cents": band_min}])
        raw_price = band_min
    else:
        line_items = _dynamic_line_items(q, signals, token_cost)
        raw_price = sum(li["amount_cents"] for li in line_items)

    # Clamp the raw storyboard-derived price to the tier band.
    price = max(band_min, min(band_max, raw_price))

    # Keep base_price_cents == the clamped customer price (back-compat field name).
    margin = 0.0 if price == 0 else (price - plan_cogs) / price

    return {
        "model": "dynamic_banded",
        "quality": q,
        "line_items": line_items,
        "band": {"min_cents": band_min, "max_cents": band_max},
        "base_price_cents": price,
        "plan_cogs_cents": plan_cogs,
        "token_cost_cents": token_cost,
        "raw_price_cents": raw_price,        # pre-clamp, for transparency/debugging
        "total_price_cents": price,
        "total_cogs_cents": plan_cogs,
        "margin": margin,
    }


def price_for_selection(selection, plan_cogs_cents, pricing=None, signals=None):
    """Convenience: resolve a SELECTION + the plan's (quality-resolved) COGS into a
    dynamic banded quote. The active produce path uses the producer wrapper, which
    threads `signals`; this stays callable (signals optional -> band-floor quote)."""
    return price_for_plan(plan_cogs_cents,
                          quality=quality_from_selection(selection, pricing=pricing),
                          pricing=pricing, signals=signals)


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
