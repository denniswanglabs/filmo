#!/usr/bin/env python3
"""Layer 1 — deterministic unit tests for the pricing + budget engine (producer.py).

No money, no network: PRODUCER_COST_STUB makes the Higgsfield preview offline and
fixed, so every estimate/gate branch is asserted exactly. Run with either:
    python3 -m unittest tests.test_producer
    python3 -m pytest tests/test_producer.py
"""

import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

# Deterministic, offline pricing for every test in this module.
os.environ["PRODUCER_COST_STUB"] = json.dumps(
    {"seedance_2_0": 22, "gpt_image_2": 7, "nano_banana_flash": 4, "__default__": 10})

import producer  # noqa: E402


def plan(scenes, margin=0.6, script="x" * 400):
    return {
        "job": {"company_url": "https://x.test", "goal": "g",
                "target_duration_s": 30, "target_margin": margin, "currency": "usd"},
        "scenes": scenes,
        "voiceover": {"script": script, "voice": "Adam"},
    }


def scene(sid, stype, model=None, dur=6):
    return {"id": sid, "type": stype, "brief": "b " + sid, "model": model,
            "duration_s": dur, "input_image": None}


class TestEstimate(unittest.TestCase):
    def test_free_scenes_cost_zero(self):
        est = producer.cmd_estimate(plan([
            scene("t", "title"), scene("w", "walkthrough"), scene("m", "motion_graphic")]))
        for s in est["scenes"]:
            self.assertEqual(s["est_cost_cents"], 0, s["id"])

    def test_cinematic_uses_stubbed_preview(self):
        est = producer.cmd_estimate(plan([
            scene("a", "cinematic", "seedance_2_0"),
            scene("b", "cinematic", "gpt_image_2")]))
        costs = {s["id"]: s["est_cost_cents"] for s in est["scenes"]}
        self.assertEqual(costs["a"], 22)
        self.assertEqual(costs["b"], 7)

    def test_voiceover_from_char_count(self):
        # 1000 chars @ 30c/1k = 30c
        est = producer.cmd_estimate(plan([scene("t", "title")], script="y" * 1000))
        self.assertEqual(est["voiceover"]["est_cost_cents"], 30)

    def test_total_cogs_and_price_formula(self):
        est = producer.cmd_estimate(plan([
            scene("a", "cinematic", "seedance_2_0"),
            scene("b", "cinematic", "gpt_image_2")], margin=0.6, script="z" * 1000))
        # COGS = 22 + 7 + 30(VO) = 59 ; price = round(59 / 0.4) = 148
        self.assertEqual(est["total_cogs_cents"], 59)
        self.assertEqual(est["suggested_price_cents"], 148)
        self.assertEqual(est["production_budget_cents"], 59)

    def test_per_scene_budget_sums_to_cogs(self):
        est = producer.cmd_estimate(plan([
            scene("a", "cinematic", "seedance_2_0"),
            scene("b", "cinematic", "gpt_image_2"),
            scene("t", "title")], script="z" * 1000))
        alloc = [s["per_scene_budget_cents"] for s in est["scenes"]]
        alloc.append(est["voiceover"]["per_scene_budget_cents"])
        self.assertEqual(sum(alloc), est["total_cogs_cents"])

    def test_margin_one_yields_null_price(self):
        est = producer.cmd_estimate(plan([scene("a", "cinematic", "seedance_2_0")], margin=1.0))
        self.assertIsNone(est["suggested_price_cents"])


class TestDistribute(unittest.TestCase):
    def test_sums_exactly(self):
        self.assertEqual(sum(producer._distribute(100, [22, 7, 0, 12])), 100)

    def test_even_split_when_all_zero(self):
        out = producer._distribute(10, [0, 0, 0])
        self.assertEqual(sum(out), 10)
        self.assertTrue(max(out) - min(out) <= 1)


class TestGate(unittest.TestCase):
    def _plan(self):
        return plan([
            scene("a", "cinematic", "seedance_2_0"),
            scene("b", "cinematic", "gpt_image_2"),
            scene("w", "walkthrough")], script="z" * 1000)

    def test_approve_when_fits(self):
        # budget locked at 100; propose 22 with 30 spent -> remaining 70 -> approve
        g = producer.cmd_gate(self._plan(), "a", 22, 30, budget_cents=100)
        self.assertEqual(g["decision"], "approve")
        self.assertEqual(g["remaining_budget_cents"], 70)

    def test_downgrade_when_over_and_cheaper_exists(self):
        # seedance scene over budget -> downgrade to gpt_image_2
        g = producer.cmd_gate(self._plan(), "a", 90, 30, budget_cents=100)
        self.assertEqual(g["decision"], "downgrade")
        self.assertEqual(g["suggested_cheaper_model"], "gpt_image_2")

    def test_decline_when_over_and_already_cheapest(self):
        # gpt_image_2 scene is already the cheapest cinematic model -> no downgrade
        g = producer.cmd_gate(self._plan(), "b", 90, 30, budget_cents=100)
        self.assertEqual(g["decision"], "decline")
        self.assertIsNone(g["suggested_cheaper_model"])

    def test_walkthrough_over_budget_declines(self):
        # a free type has no cheaper model entry; over budget -> decline
        g = producer.cmd_gate(self._plan(), "w", 90, 30, budget_cents=100)
        self.assertEqual(g["decision"], "decline")

    def test_budget_lock_overrides_recompute(self):
        # With an explicit budget the plan's own COGS must NOT be used.
        g = producer.cmd_gate(self._plan(), "a", 40, 0, budget_cents=50)
        self.assertEqual(g["production_budget_cents"], 50)
        self.assertEqual(g["remaining_budget_cents"], 50)
        self.assertEqual(g["decision"], "approve")


if __name__ == "__main__":
    unittest.main(verbosity=2)
