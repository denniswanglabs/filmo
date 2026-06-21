#!/usr/bin/env python3
"""Layer 2 — judgment tests for the producer-brain orchestrator.

Each test runs the WHOLE loop ($0, mock mode) on a crafted scene plan and asserts
the agent made the right per-scene call: approve, downgrade, decline (the
money-shot), and a declined voiceover. Real edge-tts + ffmpeg run, so each test
also proves a genuine final MP4 is produced. Planning costs come from
PRODUCER_COST_STUB; production-time overruns come from PRODUCER_PRODUCTION_COST_STUB.

Run: python3 -m unittest tests.test_orchestrator
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


def load(name):
    with open(os.path.join(SCEN, name)) as f:
        return json.load(f)


def run(plan, run_id, production_stub=None):
    """Run a scenario into a temp runs dir and return the ledger dict."""
    if production_stub is None:
        os.environ.pop("PRODUCER_PRODUCTION_COST_STUB", None)
    else:
        os.environ["PRODUCER_PRODUCTION_COST_STUB"] = json.dumps(production_stub)
    os.environ["PRODUCER_COST_STUB"] = PLANNING_STUB
    tmp = tempfile.mkdtemp(prefix="hermes-test-")
    data, _ = orchestrator.orchestrate(plan, run_id, mode="mock", runs_dir=tmp,
                                        vo_provider="edge", now="2026-06-19T00:00:00Z")
    return data


def scenes_by_id(data):
    return {s["id"]: s for s in data["scenes"]}


class TestApprove(unittest.TestCase):
    def test_all_cinematic_approved(self):
        data = run(load("scenario_approve.json"), "t-approve")
        s = scenes_by_id(data)
        self.assertEqual(s["cine-establish"]["decision"], "approve")
        self.assertEqual(s["cine-hero-still"]["decision"], "approve")
        self.assertEqual(data["voiceover"]["decision"], "approve")
        self.assertEqual(data["pnl"]["declines"], [])
        self.assertEqual(data["pnl"]["overage_avoided_cents"], 0)
        self.assertEqual(data["status"], "delivered")
        self.assertTrue(data["stitch"]["has_audio"])
        # studio is profitable at roughly the target margin
        self.assertGreaterEqual(data["pnl"]["margin"], 0.55)


class TestDowngrade(unittest.TestCase):
    def test_seedance_hero_downgrades_to_still(self):
        data = run(load("scenario_downgrade.json"), "t-downgrade",
                   production_stub={"cine-hero-motion": 38})
        s = scenes_by_id(data)
        hero = s["cine-hero-motion"]
        self.assertEqual(hero["decision"], "downgrade")
        self.assertEqual(hero["downgraded_from"], "seedance_2_0")
        self.assertEqual(hero["final_model"], "gpt_image_2")
        self.assertIsNotNone(hero["output_path"])      # it STILL produced a clip
        self.assertEqual(hero["spent_cents"], 7)        # at the cheaper price
        self.assertEqual(s["cine-still"]["decision"], "approve")
        self.assertEqual(data["status"], "delivered")


class TestDeclineMoneyShot(unittest.TestCase):
    def test_over_budget_hero_is_declined_and_video_still_ships(self):
        data = run(load("scenario_decline.json"), "t-decline",
                   production_stub={"hero-still": 60})
        s = scenes_by_id(data)
        hero = s["hero-still"]
        self.assertEqual(hero["decision"], "decline")            # the money-shot
        self.assertIsNone(hero["output_path"])                   # NOT generated
        self.assertEqual(hero["spent_cents"], 0)                 # no spend
        self.assertEqual(hero["would_have_cost_cents"], 60)
        # the budget gate SAVED the overage and the studio still shipped at profit
        self.assertEqual(data["pnl"]["overage_avoided_cents"], 60)
        self.assertEqual([d["id"] for d in data["pnl"]["declines"]], ["hero-still"])
        self.assertIn("hero-still", data["stitch"]["scenes_cut"])
        self.assertGreater(data["pnl"]["margin"], data["job"]["target_margin"])
        self.assertEqual(data["status"], "delivered")
        # a real Stripe-shaped authorization object exists and is NOT approved
        auth = hero["stripe_authorization"]
        self.assertIsNotNone(auth)
        self.assertFalse(auth["approved"])

    def test_earlier_scene_was_approved(self):
        data = run(load("scenario_decline.json"), "t-decline2",
                   production_stub={"hero-still": 60})
        self.assertEqual(scenes_by_id(data)["cine-establish"]["decision"], "approve")


class TestVoiceoverOverBudget(unittest.TestCase):
    def test_vo_declined_when_over_budget(self):
        data = run(load("scenario_vo_over_budget.json"), "t-vo",
                   production_stub={"__voiceover__": 40})
        self.assertEqual(data["voiceover"]["decision"], "decline")
        self.assertIsNone(data["voiceover"]["output_path"])
        self.assertFalse(data["stitch"]["has_audio"])     # no VO muxed
        # the cinematic scenes still ran and the video still ships
        s = scenes_by_id(data)
        self.assertEqual(s["cine-a"]["decision"], "approve")
        self.assertEqual(s["cine-b"]["decision"], "approve")
        self.assertEqual(data["status"], "delivered")


class TestInvalidPlanRejected(unittest.TestCase):
    def test_bad_plan_raises_before_spend(self):
        bad = load("scenario_approve.json")
        bad["scenes"][1]["type"] = "bogus_type"
        with self.assertRaises(ValueError):
            run(bad, "t-bad")


if __name__ == "__main__":
    unittest.main(verbosity=2)
