#!/usr/bin/env python3
"""Deterministic unit tests for analytics.py (the operator-analytics data layer).

$0 — NO network, NO real ledgers. Writes 3 fixture ledgers into a temp runs/ and
asserts the aggregation that the Analytics tab (and GET /api/analytics) consumes:

  1. per-build math is correct for a clean decline run (price, cogs, gross,
     margin, the [{scene, saved_cents}] decline list, overage_saved);
  2. a LEGACY ledger with no `pnl` / `premium` block does NOT crash and is
     reconstructed from its scene records;
  3. totals roll up only the REAL (terminal + priced) builds, while overage and
     declines sum across ALL builds; a `running` build is excluded from revenue;
  4. the decline run's overage_saved is summed into totals.

Run: python3 -m unittest tests.test_analytics -v
"""

import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import analytics  # noqa: E402


# -- fixtures ---------------------------------------------------------------

# A: clean decline run — has a full `pnl` block (the canonical money-shot shape).
LEDGER_DECLINE = {
    "run_id": "fix-decline",
    "schema_version": 1,
    "mode": "mock",
    "created_at": "2026-06-19T01:03:00Z",
    "job": {"company_url": "https://docs.stripe.com"},
    "status": "delivered",
    "pricing": {"suggested_price_cents": 92},
    "scenes": [],
    "voiceover": None,
    "pnl": {
        "price_cents": 92,
        "cogs_spent_cents": 30,
        "overage_avoided_cents": 60,
        "gross_profit_cents": 62,
        "margin": 0.6739,
        "declines": [{"id": "hero-still", "would_have_cost_cents": 60}],
        "cost_lines": [],
    },
}

# B: clean approve run — full pnl, no declines, terminal + priced.
LEDGER_APPROVE = {
    "run_id": "fix-approve",
    "schema_version": 1,
    "mode": "mock",
    "created_at": "2026-06-19T01:01:00Z",
    "job": {"company_url": "https://linear.app"},
    "status": "delivered",
    "pricing": {"suggested_price_cents": 100},
    "scenes": [],
    "voiceover": None,
    "pnl": {
        "price_cents": 100,
        "cogs_spent_cents": 40,
        "overage_avoided_cents": 0,
        "gross_profit_cents": 60,
        "margin": 0.6,
        "declines": [],
        "cost_lines": [],
    },
}

# C: LEGACY ledger — NO `pnl` and NO `premium` block (an older / in-flight schema).
# Must be reconstructed from the scene + voiceover records without crashing.
# spent: 22 (approved scene) + 8 (vo) = 30 cogs. One declined scene saved 50.
# price comes from pricing.suggested_price_cents (110). Status `running` => NOT a
# real build (excluded from revenue totals) but its overage/declines still count.
LEDGER_LEGACY = {
    "run_id": "fix-legacy",
    "schema_version": 1,
    "mode": "real",
    "created_at": None,
    "job": {"company_url": "https://notion.so"},
    "status": "running",
    "pricing": {"suggested_price_cents": 110},
    "scenes": [
        {"id": "s1", "type": "title", "decision": "free", "spent_cents": 0},
        {"id": "s2", "type": "cinematic", "decision": "approve", "spent_cents": 22},
        {"id": "s3", "type": "cinematic", "decision": "decline",
         "spent_cents": 0, "would_have_cost_cents": 50},
    ],
    "voiceover": {"id": "__voiceover__", "decision": "approve", "spent_cents": 8},
    # no "pnl", no "premium", no "quality"
}


def _write_runs(tmp, ledgers):
    """Materialize fixture ledgers into <tmp>/<run_id>/ledger.json."""
    for led in ledgers:
        d = os.path.join(tmp, led["run_id"])
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "ledger.json"), "w") as fh:
            json.dump(led, fh)


class AnalyticsTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="analytics-test-")
        _write_runs(self._tmp, [LEDGER_DECLINE, LEDGER_APPROVE, LEDGER_LEGACY])
        self.summary = analytics.summarize(runs_dir=self._tmp)
        self.builds = {b["run_id"]: b for b in self.summary["builds"]}
        self.totals = self.summary["totals"]

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmp, ignore_errors=True)

    # -- per-build math -----------------------------------------------------
    def test_per_build_decline_math(self):
        b = self.builds["fix-decline"]
        self.assertEqual(b["brand"], "https://docs.stripe.com")
        self.assertEqual(b["price_charged_cents"], 92)
        self.assertEqual(b["cogs_spent_cents"], 30)
        self.assertEqual(b["gross_profit_cents"], 62)
        self.assertEqual(b["margin"], 0.6739)
        self.assertEqual(b["mode"], "mock")
        self.assertEqual(b["status"], "delivered")
        # decline list is normalized to {scene, saved_cents}
        self.assertEqual(b["declines"], [{"scene": "hero-still", "saved_cents": 60}])
        self.assertEqual(b["overage_saved_cents"], 60)

    def test_per_build_approve_no_declines(self):
        b = self.builds["fix-approve"]
        self.assertEqual(b["price_charged_cents"], 100)
        self.assertEqual(b["cogs_spent_cents"], 40)
        self.assertEqual(b["gross_profit_cents"], 60)
        self.assertEqual(b["margin"], 0.6)
        self.assertEqual(b["declines"], [])
        self.assertEqual(b["overage_saved_cents"], 0)

    # -- legacy ledger does NOT crash & is reconstructed --------------------
    def test_legacy_ledger_reconstructed_without_crash(self):
        b = self.builds["fix-legacy"]
        # price from pricing.suggested_price_cents (no pnl block present)
        self.assertEqual(b["price_charged_cents"], 110)
        # cogs reconstructed from scene + vo spent: 22 + 8 = 30
        self.assertEqual(b["cogs_spent_cents"], 30)
        # gross derived: 110 - 30 = 80
        self.assertEqual(b["gross_profit_cents"], 80)
        # margin derived: (110 - 30)/110 = 0.7273
        self.assertEqual(b["margin"], round((110 - 30) / 110, 4))
        # declined scene reconstructed into the {scene, saved_cents} shape
        self.assertEqual(b["declines"], [{"scene": "s3", "saved_cents": 50}])
        self.assertEqual(b["overage_saved_cents"], 50)
        self.assertEqual(b["status"], "running")

    # -- totals -------------------------------------------------------------
    def test_totals_rollup(self):
        t = self.totals
        self.assertEqual(t["builds"], 3)
        # only the two terminal+priced runs are "real"; the running legacy one is not
        self.assertEqual(t["real_builds"], 2)
        # revenue/cogs/gross over the REAL builds only (92+100 / 30+40)
        self.assertEqual(t["total_revenue_cents"], 192)
        self.assertEqual(t["total_cogs_cents"], 70)
        self.assertEqual(t["total_gross_profit_cents"], 122)
        # avg margin = mean(0.6739, 0.6) over real builds
        self.assertEqual(t["avg_margin"], round((0.6739 + 0.6) / 2, 4))
        # overage + declines sum across ALL builds incl. the legacy running one
        self.assertEqual(t["total_overage_saved_cents"], 60 + 0 + 50)
        self.assertEqual(t["total_declines"], 1 + 0 + 1)

    def test_decline_run_overage_in_totals(self):
        # the decline run's 60c overage is part of the headline total
        self.assertGreaterEqual(self.totals["total_overage_saved_cents"], 60)

    # -- shape contract -----------------------------------------------------
    def test_summary_shape(self):
        self.assertEqual(set(self.summary.keys()), {"builds", "totals"})
        for b in self.summary["builds"]:
            self.assertEqual(
                set(b.keys()),
                {"run_id", "brand", "created_at", "mode", "price_charged_cents",
                 "cogs_spent_cents", "gross_profit_cents", "margin", "declines",
                 "overage_saved_cents", "status"},
            )
        self.assertEqual(
            set(self.totals.keys()),
            {"builds", "real_builds", "total_revenue_cents", "total_cogs_cents",
             "total_gross_profit_cents", "avg_margin", "total_overage_saved_cents",
             "total_declines"},
        )

    def test_empty_runs_dir_is_safe(self):
        empty = tempfile.mkdtemp(prefix="analytics-empty-")
        try:
            s = analytics.summarize(runs_dir=empty)
            self.assertEqual(s["builds"], [])
            self.assertEqual(s["totals"]["builds"], 0)
            self.assertEqual(s["totals"]["real_builds"], 0)
            self.assertIsNone(s["totals"]["avg_margin"])
            self.assertEqual(s["totals"]["total_revenue_cents"], 0)
        finally:
            import shutil
            shutil.rmtree(empty, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
