#!/usr/bin/env python3
"""Bridge test — orchestrator <-> stripe_webhook budget state ($0, no Stripe).

THE GAP (TECHNICAL-ROADMAP 1.1B): stripe_webhook.py decides approve/decline from
runs/active_budget.json {"budget_cents", "spent_cents"}, but the orchestrator never
wrote that file -> a live listener would decide against {0,0}. These tests prove the
bridge: the orchestrator now externalizes the locked budget + running spend, and the
webhook's decide() returns approve (in-budget) and DECLINE (over-budget) using the
REAL numbers the brain used — so a live `stripe listen` over an over-budget run fires
a genuine declined issuing_authorization.

No Stripe key, no `stripe login`, no real charge: decide() is pure arithmetic and is
fed the file the orchestrator actually wrote on a mock ($0) run.

Run: python3 -m unittest tests.test_orchestrator_budget_bridge
"""

import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SCEN = os.path.join(HERE, "scenarios")
sys.path.insert(0, ROOT)

PLANNING_STUB = json.dumps({"seedance_2_0": 22, "gpt_image_2": 7, "__default__": 10})
os.environ["PRODUCER_COST_STUB"] = PLANNING_STUB

import orchestrator  # noqa: E402
import stripe_webhook  # noqa: E402


def load(name):
    with open(os.path.join(SCEN, name)) as f:
        return json.load(f)


def run(plan, run_id, production_stub=None):
    """Run a scenario into a temp runs dir; return (ledger, runs_dir)."""
    if production_stub is None:
        os.environ.pop("PRODUCER_PRODUCTION_COST_STUB", None)
    else:
        os.environ["PRODUCER_PRODUCTION_COST_STUB"] = json.dumps(production_stub)
    os.environ["PRODUCER_COST_STUB"] = PLANNING_STUB
    tmp = tempfile.mkdtemp(prefix="hermes-bridge-")
    data, _ = orchestrator.orchestrate(plan, run_id, mode="mock", runs_dir=tmp,
                                        vo_provider="edge", now="2026-06-19T00:00:00Z")
    return data, tmp


def active_budget(runs_dir):
    with open(os.path.join(runs_dir, orchestrator.ACTIVE_BUDGET_FILENAME)) as f:
        return json.load(f)


class TestBridgeFileWritten(unittest.TestCase):
    def test_orchestrator_writes_active_budget_with_real_numbers(self):
        data, runs_dir = run(load("scenario_approve.json"), "t-bridge-approve")
        ab = active_budget(runs_dir)
        # exact schema stripe_webhook.read_state expects
        self.assertIn("budget_cents", ab)
        self.assertIn("spent_cents", ab)
        self.assertIsInstance(ab["budget_cents"], int)
        self.assertIsInstance(ab["spent_cents"], int)
        # the locked budget matches the ledger's locked production budget
        self.assertEqual(ab["budget_cents"], data["pricing"]["production_budget_cents"])
        # NOT the {0,0} the gap would have left
        self.assertGreater(ab["budget_cents"], 0)

    def test_active_budget_path_is_webhook_state_default_dirname(self):
        # In a real run runs_dir == HERE/runs, so the file the orchestrator writes
        # is exactly stripe_webhook.STATE_DEFAULT (no --state flag needed live).
        self.assertEqual(os.path.basename(stripe_webhook.STATE_DEFAULT),
                         orchestrator.ACTIVE_BUDGET_FILENAME)


class TestWebhookApprovesInBudget(unittest.TestCase):
    def test_decide_approves_charge_within_remaining(self):
        _, runs_dir = run(load("scenario_approve.json"), "t-bridge-approve2")
        ab = active_budget(runs_dir)
        remaining = ab["budget_cents"] - ab["spent_cents"]
        # a charge at-or-under remaining is APPROVED, using the REAL state file
        approved, rem = stripe_webhook.decide(remaining, ab)
        self.assertTrue(approved)
        self.assertEqual(rem, remaining)


class TestWebhookDeclinesOverBudget(unittest.TestCase):
    """The money-shot: feed the orchestrator's real active_budget.json to the
    webhook and confirm the over-budget hero charge is DECLINED with real numbers."""

    def test_real_decline_fires_with_real_numbers(self):
        data, runs_dir = run(load("scenario_decline.json"), "t-bridge-decline",
                             production_stub={"hero-still": 60})
        # sanity: the in-process brain declined the over-budget hero
        hero = {s["id"]: s for s in data["scenes"]}["hero-still"]
        self.assertEqual(hero["decision"], "decline")
        over_amount = hero["would_have_cost_cents"]  # 60c, the charge that fired

        ab = active_budget(runs_dir)
        remaining = ab["budget_cents"] - ab["spent_cents"]
        # the listener, reading the SAME file, must DECLINE that charge
        approved, rem = stripe_webhook.decide(over_amount, ab)
        self.assertFalse(approved, "webhook must DECLINE the over-budget charge")
        self.assertEqual(rem, remaining)
        # and the numbers are REAL (not the {0,0} the gap would have produced)
        self.assertGreater(ab["budget_cents"], 0)
        self.assertGreater(over_amount, remaining)
        # the brain's own remaining (committed spent so far) matches the file
        self.assertEqual(ab["spent_cents"], hero["spent_before_cents"])

    def test_same_file_both_verdicts(self):
        # One state file yields BOTH a real approve and a real decline depending
        # only on the charge amount — exactly the live webhook's behavior.
        _, runs_dir = run(load("scenario_decline.json"), "t-bridge-both",
                          production_stub={"hero-still": 60})
        ab = active_budget(runs_dir)
        remaining = ab["budget_cents"] - ab["spent_cents"]
        self.assertTrue(stripe_webhook.decide(remaining, ab)[0])       # in-budget -> approve
        self.assertFalse(stripe_webhook.decide(remaining + 1, ab)[0])  # 1c over   -> DECLINE


if __name__ == "__main__":
    unittest.main()
