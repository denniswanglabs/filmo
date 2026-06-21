#!/usr/bin/env python3
"""Operator analytics aggregator for Walk Studio.

Reads every `runs/<run_id>/ledger.json` and rolls them up into the operator
P&L view (revenue, COGS, gross profit, margin, the money-shot overage the budget
gate saved, and the per-scene declines). This is the DATA LAYER the customer-
facing dashboard is moving its economics OUT to: the Analytics tab (a separate,
later frontend) consumes `summarize()` via `GET /api/analytics`.

The single source of truth per run is the ledger's `pnl` block (see LEDGER.md /
ledger.compute_pnl). When a ledger predates the `pnl` block, or a run failed /
is still running before the P&L was written, we reconstruct the numbers from the
`scenes` + `voiceover` + `pricing` records so an older or in-flight ledger never
crashes the aggregation and still contributes whatever it can.

Stdlib only. No wall-clock dependency: ordering is by `created_at` (when present)
then `run_id`, matching the dashboard's run rail.
"""

import json
import os

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
RUNS_DIR = os.path.join(PROJECT_ROOT, "runs")

# Runs we never count as a real, revenue-bearing build. `running` has no final
# P&L yet; `failed` never delivered. Everything else (delivered / complete /
# completed_with_warnings) is treated as a real build for the totals.
_NON_REAL_STATUSES = {"running", "failed"}


def _i(value):
    """Coerce a possibly-None / possibly-float cents value to a clean int (0 on None)."""
    if value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _price_charged_cents(led):
    """The price the customer was charged for this build, in cents (or None).

    Prefer the P&L's `price_cents` (the locked, charged price — already reflects
    the premium menu total, e.g. 43400 on premium-demo-01). Fall back to the
    pricing block's `suggested_price_cents` for legacy/in-flight ledgers that
    lack a P&L. None when neither is present (a run that never got priced).
    """
    pnl = led.get("pnl") or {}
    if pnl.get("price_cents") is not None:
        return _i(pnl.get("price_cents"))
    pricing = led.get("pricing") or {}
    if pricing.get("suggested_price_cents") is not None:
        return _i(pricing.get("suggested_price_cents"))
    return None


def _reconstruct_pnl(led):
    """Best-effort P&L for a ledger that has no `pnl` block.

    Mirrors ledger.compute_pnl over the scene + voiceover records:
      cogs_spent  = sum of actual spent_cents across produced scenes + VO
      overage     = sum of would_have_cost_cents on declined scenes/VO
      declines    = [{id, would_have_cost_cents}] for each decline
    Price comes from the pricing block (suggested_price_cents) when available.
    Returns a dict shaped like the real `pnl` block so the rest of the code is
    indifferent to whether it was stored or reconstructed.
    """
    rows = list(led.get("scenes") or [])
    vo = led.get("voiceover")
    if vo:
        rows = rows + [vo]

    cogs = 0
    overage = 0
    declines = []
    for r in rows:
        cogs += _i(r.get("spent_cents"))
        if r.get("decision") == "decline":
            would = _i(r.get("would_have_cost_cents"))
            overage += would
            declines.append({"id": r.get("id"), "would_have_cost_cents": would})

    price = _price_charged_cents(led)
    margin = None
    gross = None
    if price:
        gross = price - cogs
        margin = round((price - cogs) / price, 4)

    return {
        "price_cents": price,
        "cogs_spent_cents": cogs,
        "overage_avoided_cents": overage,
        "gross_profit_cents": gross,
        "margin": margin,
        "declines": declines,
    }


def per_build(led):
    """Flatten one loaded ledger dict into a single operator-analytics row.

    Uses the stored `pnl` block when present; otherwise reconstructs it from the
    scene records (legacy / failed / running ledgers). Every numeric field is a
    clean int in cents; `margin` is a float or None; `price_charged_cents` may be
    None for a run that was never priced.
    """
    pnl = led.get("pnl")
    if not pnl:
        pnl = _reconstruct_pnl(led)

    price = _price_charged_cents(led)
    cogs = _i(pnl.get("cogs_spent_cents"))
    gross = pnl.get("gross_profit_cents")
    if gross is None and price is not None:
        gross = price - cogs
    margin = pnl.get("margin")
    if margin is None and price:
        margin = round((price - cogs) / price, 4)

    declines = [
        {"scene": d.get("id"), "saved_cents": _i(d.get("would_have_cost_cents"))}
        for d in (pnl.get("declines") or [])
    ]

    return {
        "run_id": led.get("run_id"),
        "brand": (led.get("job") or {}).get("company_url"),
        "created_at": led.get("created_at"),
        "mode": led.get("mode"),
        "price_charged_cents": price,
        "cogs_spent_cents": cogs,
        "gross_profit_cents": _i(gross) if gross is not None else None,
        "margin": margin,
        "declines": declines,
        "overage_saved_cents": _i(pnl.get("overage_avoided_cents")),
        "status": led.get("status"),
    }


def _iter_ledgers(runs_dir):
    """Yield (run_id, parsed_dict) for every readable runs/*/ledger.json.

    Skips dirs without a ledger and any ledger that won't parse — a torn or
    truncated file during a live write never breaks the aggregation.
    """
    try:
        names = sorted(os.listdir(runs_dir))
    except OSError:
        return
    for name in names:
        p = os.path.join(runs_dir, name, "ledger.json")
        if not os.path.exists(p):
            continue
        try:
            with open(p) as fh:
                yield name, json.load(fh)
        except (OSError, ValueError):
            continue


def _is_real_build(row):
    """A real, revenue-bearing build: terminal (not running/failed) AND priced.

    A run that was never priced (price_charged_cents is None) is excluded from
    the revenue rollup even if its status is terminal, so totals stay honest.
    """
    if row.get("status") in _NON_REAL_STATUSES:
        return False
    return row.get("price_charged_cents") is not None


def summarize(runs_dir=None):
    """Aggregate every ledger into {builds:[...], totals:{...}}.

    `builds` is one `per_build` row per readable ledger (ALL of them, including
    running/failed, so the Analytics tab can show the full operating history).
    `totals` rolls up only the REAL builds (terminal + priced) so the headline
    revenue / margin numbers reflect money actually transacted. `avg_margin` is
    the simple mean of real-build margins (None when there are no real builds).
    """
    runs_dir = runs_dir or RUNS_DIR
    builds = [per_build(led) for _, led in _iter_ledgers(runs_dir)]
    builds.sort(key=lambda r: (r.get("created_at") or "", r.get("run_id") or ""),
                reverse=True)

    real = [b for b in builds if _is_real_build(b)]
    total_revenue = sum(_i(b["price_charged_cents"]) for b in real)
    total_cogs = sum(_i(b["cogs_spent_cents"]) for b in real)
    total_overage = sum(_i(b["overage_saved_cents"]) for b in builds)
    total_declines = sum(len(b["declines"]) for b in builds)
    margins = [b["margin"] for b in real if b.get("margin") is not None]
    avg_margin = round(sum(margins) / len(margins), 4) if margins else None

    totals = {
        "builds": len(builds),
        "real_builds": len(real),
        "total_revenue_cents": total_revenue,
        "total_cogs_cents": total_cogs,
        "total_gross_profit_cents": total_revenue - total_cogs,
        "avg_margin": avg_margin,
        "total_overage_saved_cents": total_overage,
        "total_declines": total_declines,
    }
    return {"builds": builds, "totals": totals}


if __name__ == "__main__":
    print(json.dumps(summarize(), indent=2))
