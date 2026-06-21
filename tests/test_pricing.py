#!/usr/bin/env python3
"""Cost-plus pricing tests (pricing.py + flag-gated producer.py path).

The model (decided with Dennis): NO tiers. Price = the agent's real production
COGS x a markup, with a price floor, rounded to a clean increment. The ONE
customer choice, made UPFRONT, is QUALITY (standard | premium) — it is NOT a flat
add-on; it changes WHAT the agent produces and therefore the plan COGS:

    price = max(price_floor_cents, round_to_nearest(plan_cogs * markup, round_to_cents))

    standard -> Remotion + edge-tts (no Higgsfield, no ElevenLabs) -> COGS ~free
                -> price floors at $5.
    premium  -> cinematic Higgsfield + ElevenLabs VO land in COGS -> price ~$6-9.

Asserts:
  (a) price = max(floor, round50(cogs*6)); a TYPICAL ~$1-COGS video prices $5-9.
  (b) standard floors at $5; premium prices higher (Higgsfield + ElevenLabs COGS
      + a cogs_floor minimum) and needs NO consent.
  (c) the price FLOOR + rounding behave as specified.
  (d) the WS_PREMIUM_MENU=OFF producer path is byte-identical to the legacy path
      (the cost-plus block is a no-op), and the ON path overrides the locked
      budget + price from the cost-plus quote PER QUALITY (standard drops the
      Higgsfield + VO COGS; premium keeps them) while leaving the scene/VO
      estimate report intact.
  (e) OLD selections still PARSE/MAP (legacy premium_vo=true -> premium; legacy
      founder_voice booster -> premium; back-compat shims still callable).

No money, no network: PRODUCER_COST_STUB makes producer's Higgsfield preview offline.
Run with:  python3 -m unittest tests.test_pricing
"""

import copy
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

# Deterministic, offline pricing for the producer estimate calls in (d).
os.environ["PRODUCER_COST_STUB"] = json.dumps(
    {"seedance_2_0": 22, "gpt_image_2": 7, "nano_banana_flash": 4, "__default__": 10})

import pricing      # noqa: E402
import producer     # noqa: E402

MARKUP = 6.0
FLOOR = 500
ROUND_TO = 50
PREMIUM_COGS_FLOOR = 100  # pricing.json quality.premium.cogs_floor_cents


def _plan(scenes=None, selection=None):
    plan = {
        "job": {"company_url": "https://x.test", "goal": "g",
                "target_duration_s": 30, "target_margin": 0.6, "currency": "usd"},
        "scenes": scenes or [
            {"id": "a", "type": "cinematic", "brief": "b", "model": "seedance_2_0",
             "duration_s": 6, "input_image": None},
            {"id": "t", "type": "title", "brief": "b", "model": None,
             "duration_s": 3, "input_image": None},
        ],
        "voiceover": {"script": "z" * 1000, "voice": "Adam"},
    }
    if selection is not None:
        plan["selection"] = selection
    return plan


def _round50(x):
    return int(round(x / ROUND_TO) * ROUND_TO)


def _expected_price(cogs):
    return max(FLOOR, _round50(cogs * MARKUP))


# ===========================================================================
# (a) Cost-plus core + a typical video lands $5-9
# ===========================================================================

class TestCostPlusCore(unittest.TestCase):
    def test_price_is_cogs_times_markup_floored_rounded(self):
        # 200c COGS -> 200*6=1200 -> round50 1200 -> max(500,1200)=1200 ($12)
        self.assertEqual(pricing.base_price_for_cogs(200), 1200)
        # 36c COGS -> 36*6=216 -> round50 200 -> max(500,200)=500 (floor wins) ($5)
        self.assertEqual(pricing.base_price_for_cogs(36), 500)
        # 90c COGS -> 90*6=540 -> round50 550 -> max(500,550)=550 ($5.50)
        self.assertEqual(pricing.base_price_for_cogs(90), 550)

    def test_typical_dollar_cogs_video_prices_5_to_9(self):
        # A typical ~$1 COGS (100 cents) video: 100*6=600 -> $6, in the $5-9 band.
        out = pricing.price_for_plan(100, quality="premium")
        self.assertEqual(out["total_price_cents"], 600)
        self.assertTrue(500 <= out["total_price_cents"] <= 900,
                        "typical video should price $5-9, got %dc" % out["total_price_cents"])
        for cogs in (80, 100, 120, 150):
            tp = pricing.price_for_plan(cogs, quality="premium")["total_price_cents"]
            self.assertTrue(500 <= tp <= 900, "cogs=%dc -> %dc not in $5-9" % (cogs, tp))

    def test_price_floor_applies_to_cheap_plans(self):
        out = pricing.price_for_plan(10, quality="standard")  # 10*6=60 -> floor 500
        self.assertEqual(out["base_price_cents"], 500)
        self.assertEqual(out["total_price_cents"], 500)

    def test_line_items_shape_and_margin(self):
        out = pricing.price_for_plan(100, quality="premium")
        self.assertEqual(out["model"], "cost_plus")
        self.assertEqual(out["quality"], "premium")
        self.assertEqual(out["plan_cogs_cents"], 100)
        self.assertEqual(len(out["line_items"]), 1)
        li = out["line_items"][0]
        self.assertEqual(li["key"], "video_production")
        self.assertEqual(li["label"], "Video production")
        self.assertEqual(li["price_cents"], 600)
        self.assertEqual(li["cogs_cents"], 100)
        self.assertEqual(out["total_cogs_cents"], 100)
        self.assertAlmostEqual(out["margin"], (600 - 100) / 600, places=9)

    def test_default_quality_is_standard(self):
        self.assertEqual(pricing.default_quality(), "standard")
        out = pricing.price_for_plan(100)  # no quality -> default standard
        self.assertEqual(out["quality"], "standard")


# ===========================================================================
# (b) quality dimension — standard floors at $5, premium prices higher, no consent
# ===========================================================================

class TestQualityDimension(unittest.TestCase):
    def test_default_selection_is_standard(self):
        sel = pricing.default_selection()
        self.assertEqual(sel, {"quality": "standard"})
        self.assertEqual(pricing.quality_from_selection(sel), "standard")

    def test_quality_flags(self):
        self.assertFalse(pricing.quality_uses_higgsfield("standard"))
        self.assertFalse(pricing.quality_uses_elevenlabs("standard"))
        self.assertTrue(pricing.quality_uses_higgsfield("premium"))
        self.assertTrue(pricing.quality_uses_elevenlabs("premium"))

    def test_premium_cogs_floor_lifts_price_above_standard(self):
        # On a thin plan (cogs below the premium floor), premium still reads richer.
        std = pricing.price_for_plan(0, quality="standard")          # -> floor $5
        prem = pricing.price_for_plan(PREMIUM_COGS_FLOOR, quality="premium")  # 100*6=600
        self.assertEqual(std["total_price_cents"], FLOOR)
        self.assertEqual(prem["total_price_cents"], 600)
        self.assertGreater(prem["total_price_cents"], std["total_price_cents"])

    def test_premium_needs_no_consent(self):
        # A plain quality choice buys premium — no consent argument/guardrail.
        out = pricing.price_for_selection({"quality": "premium"}, 100)
        self.assertEqual(out["quality"], "premium")
        self.assertEqual(out["total_price_cents"], 600)
        ok, _reason = pricing.validate_consent({"quality": "premium"})
        self.assertTrue(ok)

    def test_price_for_selection_reads_quality(self):
        std = pricing.price_for_selection({"quality": "standard"}, 0)
        prem = pricing.price_for_selection({"quality": "premium"}, 100)
        self.assertEqual(std["quality"], "standard")
        self.assertEqual(prem["quality"], "premium")


# ===========================================================================
# (c) rounding + floor edge cases
# ===========================================================================

class TestRoundingAndFloor(unittest.TestCase):
    def test_rounds_to_nearest_50(self):
        # 84c*6 = 504 -> round50 = 500 ; 92c*6 = 552 -> round50 = 550
        self.assertEqual(pricing.base_price_for_cogs(84), 500)
        self.assertEqual(pricing.base_price_for_cogs(92), 550)

    def test_bad_cogs_raises(self):
        with self.assertRaises(pricing.PricingError):
            pricing.price_for_plan("not-a-number", quality="standard")

    def test_zero_cogs_floors(self):
        out = pricing.price_for_plan(0, quality="standard")
        self.assertEqual(out["total_price_cents"], FLOOR)


# ===========================================================================
# (d) Flag-gated producer path
# ===========================================================================

class TestProducerFlag(unittest.TestCase):
    def setUp(self):
        self._saved = os.environ.pop("WS_PREMIUM_MENU", None)

    def tearDown(self):
        if self._saved is None:
            os.environ.pop("WS_PREMIUM_MENU", None)
        else:
            os.environ["WS_PREMIUM_MENU"] = self._saved

    def test_off_path_unchanged(self):
        plan = _plan(selection={"quality": "premium"})
        os.environ.pop("WS_PREMIUM_MENU", None)
        off = producer.cmd_estimate(copy.deepcopy(plan))
        # Legacy numbers: COGS = 22 (seedance) + 0 (title) + 30 (1000-char VO) = 52
        self.assertEqual(off["total_cogs_cents"], 52)
        self.assertEqual(off["production_budget_cents"], 52)
        self.assertEqual(off["suggested_price_cents"], round(52 / 0.4))
        # No cost-plus keys leak into the OFF result.
        self.assertNotIn("pricing_mode", off)
        self.assertNotIn("menu", off)
        self.assertNotIn("quality", off)

    def test_off_path_equals_plan_without_selection(self):
        os.environ.pop("WS_PREMIUM_MENU", None)
        with_sel = producer.cmd_estimate(_plan(selection={"quality": "premium"}))
        without = producer.cmd_estimate(_plan(selection=None))
        self.assertEqual(with_sel, without)

    def test_on_path_standard_floors_and_drops_higgsfield_vo_cogs(self):
        os.environ["WS_PREMIUM_MENU"] = "1"
        on = producer.cmd_estimate(_plan(selection={"quality": "standard"}))
        self.assertEqual(on["pricing_mode"], "cost_plus")
        self.assertEqual(on["quality"], "standard")
        # standard drops the cinematic (22) + VO (30) cogs -> 0 -> price floors $5.
        self.assertEqual(on["menu"]["plan_cogs_cents"], 0)
        self.assertEqual(on["suggested_price_cents"], 500)
        self.assertEqual(on["production_budget_cents"], 0)   # no paid spend at all
        # The per-scene estimate report is left intact (gate reasoning unchanged).
        self.assertEqual([s["id"] for s in on["scenes"]], ["a", "t"])
        self.assertEqual(on["scenes"][0]["est_cost_cents"], 22)

    def test_on_path_premium_keeps_cogs_and_prices_higher(self):
        os.environ["WS_PREMIUM_MENU"] = "1"
        on = producer.cmd_estimate(_plan(selection={"quality": "premium"}))
        self.assertEqual(on["quality"], "premium")
        # premium keeps the 52c spend, floored to the premium cogs_floor (100c).
        self.assertEqual(on["menu"]["plan_cogs_cents"], PREMIUM_COGS_FLOOR)
        # 100*6=600 -> $6 — a typical $5-9 video, ABOVE standard's $5 floor.
        self.assertEqual(on["suggested_price_cents"], 600)
        self.assertTrue(500 <= on["suggested_price_cents"] <= 900)
        self.assertGreater(on["suggested_price_cents"], 500)
        self.assertEqual(on["production_budget_cents"], PREMIUM_COGS_FLOOR)

    def test_on_path_default_selection_when_plan_omits_it(self):
        os.environ["WS_PREMIUM_MENU"] = "1"
        on = producer.cmd_estimate(_plan(selection=None))
        self.assertEqual(on["menu"]["model"], "cost_plus")
        self.assertEqual(on["quality"], "standard")            # default
        self.assertEqual(on["suggested_price_cents"], 500)     # floor
        self.assertEqual(on["production_budget_cents"], 0)


# ===========================================================================
# (e) back-compat: OLD selections still parse + map onto quality
# ===========================================================================

class TestLegacySelectionBackCompat(unittest.TestCase):
    def test_legacy_premium_vo_maps_to_premium(self):
        legacy = {"options": {"premium_vo": True}}
        self.assertEqual(pricing.quality_from_selection(legacy), "premium")
        out = pricing.price_for_selection(legacy, 100)
        self.assertEqual(out["quality"], "premium")
        self.assertEqual(out["total_price_cents"], 600)

    def test_legacy_founder_voice_booster_maps_to_premium(self):
        legacy = {"tier": "studio", "boosters": ["rush", "founder_voice"], "options": {}}
        self.assertEqual(pricing.quality_from_selection(legacy), "premium")
        # The retained addons shim still reports the old boolean shape.
        self.assertTrue(pricing.addons_from_selection(legacy)["premium_vo"])

    def test_legacy_plain_old_selection_defaults_standard(self):
        legacy = {"tier": "pro", "boosters": ["rush"], "options": {}}
        self.assertEqual(pricing.quality_from_selection(legacy), "standard")
        self.assertFalse(pricing.addons_from_selection(legacy)["premium_vo"])

    def test_price_selection_shim_still_callable(self):
        out = pricing.price_selection({"quality": "premium"}, plan_cogs_cents=100)
        self.assertEqual(out["model"], "cost_plus")
        self.assertEqual(out["total_price_cents"], 600)


if __name__ == "__main__":
    unittest.main(verbosity=2)
