#!/usr/bin/env python3
"""Dynamic-banded pricing tests (pricing.py + flag-gated producer.py path).

The model (decided with Dennis): the customer PRICE is DYNAMIC — derived from the
STORYBOARD (scene count, cinematic count, total duration) PLUS a planner token COGS
line, then CLAMPED to a per-quality PRICE BAND:

    standard = 500 + 50*max(0,scenes-3) + 50*ceil(max(0,dur-20)/10) + token_cost
                                                              -> clamp [500, 1000]
    premium  = 1500 + 150*cinematic + 100*ceil(max(0,dur-20)/10) + vo_surcharge
                    + token_cost                              -> clamp [1500, 2500]

The ONE customer choice, made UPFRONT, is QUALITY (standard | premium) — it changes
WHAT the agent produces (and therefore the plan COGS the budget gate locks) AND which
band/formula prices it. The token COGS (planner brain tokens, estimated from VO length
+ scene count) is FOLDED into total COGS for both the budget gate and the price floor.

The OLD cost-plus math is RETAINED as `base_price_for_cogs(...)` for back-compat
(stale callers) and is still tested directly here — its behavior is unchanged.

Asserts:
  (a) price_for_plan(signals=...) returns a BANDED price (model == "dynamic_banded"):
      within the band, near the floor for a small plan, near the ceiling for a large
      plan, never outside the band, price >= cogs, monotonic in scenes & duration.
      base_price_for_cogs still does the old cost-plus math.
  (b) standard prices in [500,1000]; premium prices in [1500,2500] (strictly higher).
  (c) base_price_for_cogs FLOOR + rounding behave as specified (retained math).
  (d) the WS_PREMIUM_MENU=OFF producer path is byte-identical to the legacy path
      (the pricing block is a no-op), and the ON path overrides the locked budget +
      price from the dynamic banded quote PER QUALITY (standard drops the Higgsfield +
      VO media COGS, keeps only token COGS; premium keeps them) while leaving the
      scene/VO estimate report intact. The budget == COGS (incl token); price >= COGS.
  (e) OLD selections still PARSE/MAP (legacy premium_vo=true -> premium; legacy
      founder_voice booster -> premium; back-compat shims still callable).

No money, no network: PRODUCER_COST_STUB makes producer's Higgsfield preview offline.
Run with:  python3 -m unittest tests.test_pricing
"""

import copy
import json
import math
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

# Band bounds (pricing.json quality.<tier>.price_band_cents).
STD_MIN, STD_MAX = 500, 1000
PREM_MIN, PREM_MAX = 1500, 2500


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


def _std_signals(scenes, duration_s, token_cost_cents=0):
    return {"scenes": scenes, "cinematic_count": 0, "duration_s": duration_s,
            "uses_vo": False, "token_cost_cents": token_cost_cents}


def _prem_signals(cinematic, duration_s, uses_vo=True, scenes=None, token_cost_cents=0):
    return {"scenes": scenes if scenes is not None else cinematic,
            "cinematic_count": cinematic, "duration_s": duration_s,
            "uses_vo": uses_vo, "token_cost_cents": token_cost_cents}


# ===========================================================================
# (a) Dynamic banded core + the retained cost-plus math (base_price_for_cogs)
# ===========================================================================

class TestDynamicBandedCore(unittest.TestCase):
    def test_base_price_for_cogs_is_cogs_times_markup_floored_rounded(self):
        # base_price_for_cogs is the RETAINED cost-plus math (back-compat), unchanged.
        self.assertEqual(pricing.base_price_for_cogs(200), 1200)  # 200*6=1200
        self.assertEqual(pricing.base_price_for_cogs(36), 500)    # 36*6=216 -> floor
        self.assertEqual(pricing.base_price_for_cogs(90), 550)    # 90*6=540 -> round50 550

    def test_model_is_dynamic_banded(self):
        out = pricing.price_for_plan(0, quality="standard", signals=_std_signals(6, 32))
        self.assertEqual(out["model"], "dynamic_banded")
        self.assertIn("band", out)
        self.assertEqual(out["band"], {"min_cents": STD_MIN, "max_cents": STD_MAX})

    def test_standard_formula_sample_6_scenes_32s(self):
        # The canonical sample: 500 + 50*3 + 50*ceil(12/10=2) = 750.
        out = pricing.price_for_plan(0, quality="standard", signals=_std_signals(6, 32))
        self.assertEqual(out["total_price_cents"], 750)
        self.assertEqual(out["raw_price_cents"], 750)
        keys = {li["key"]: li["amount_cents"] for li in out["line_items"]}
        self.assertEqual(keys["base"], 500)
        self.assertEqual(keys["scenes"], 150)
        self.assertEqual(keys["duration"], 100)

    def test_premium_formula_sample(self):
        # 1500 + 150*4 + 100*ceil(20/10=2) + 300(vo) + 5(tok) = 2605 -> clamp 2500.
        out = pricing.price_for_plan(120, quality="premium",
                                     signals=_prem_signals(4, 40, uses_vo=True,
                                                           scenes=6, token_cost_cents=5))
        self.assertEqual(out["raw_price_cents"], 2605)
        self.assertEqual(out["total_price_cents"], PREM_MAX)  # clamped

    def test_small_plan_near_floor(self):
        # 3 scenes, 18s, no extras -> just the base = band floor.
        out = pricing.price_for_plan(0, quality="standard", signals=_std_signals(3, 18))
        self.assertEqual(out["total_price_cents"], STD_MIN)
        prem = pricing.price_for_plan(50, quality="premium",
                                      signals=_prem_signals(0, 15, uses_vo=False, scenes=2))
        self.assertEqual(prem["total_price_cents"], PREM_MIN)

    def test_large_plan_near_ceiling(self):
        out = pricing.price_for_plan(0, quality="standard", signals=_std_signals(40, 300))
        self.assertEqual(out["total_price_cents"], STD_MAX)
        self.assertGreater(out["raw_price_cents"], STD_MAX)  # was clamped down
        prem = pricing.price_for_plan(0, quality="premium",
                                      signals=_prem_signals(10, 200, scenes=12))
        self.assertEqual(prem["total_price_cents"], PREM_MAX)

    def test_never_outside_band(self):
        for scenes in (0, 1, 3, 6, 12, 50):
            for dur in (0, 10, 20, 32, 90, 600):
                std = pricing.price_for_plan(0, quality="standard",
                                             signals=_std_signals(scenes, dur))
                self.assertGreaterEqual(std["total_price_cents"], STD_MIN)
                self.assertLessEqual(std["total_price_cents"], STD_MAX)
                prem = pricing.price_for_plan(0, quality="premium",
                                              signals=_prem_signals(scenes, dur, scenes=scenes))
                self.assertGreaterEqual(prem["total_price_cents"], PREM_MIN)
                self.assertLessEqual(prem["total_price_cents"], PREM_MAX)

    def test_price_never_below_cogs(self):
        # The band floor (>=500/1500) always covers a plausible plan COGS.
        for cogs in (0, 10, 52, 100, 300, 499):
            std = pricing.price_for_plan(cogs, quality="standard", signals=_std_signals(3, 18))
            self.assertGreaterEqual(std["total_price_cents"], std["total_cogs_cents"])
        for cogs in (0, 50, 100, 500, 1499):
            prem = pricing.price_for_plan(cogs, quality="premium",
                                          signals=_prem_signals(1, 20, scenes=3))
            self.assertGreaterEqual(prem["total_price_cents"], prem["total_cogs_cents"])

    def test_monotonic_in_scenes(self):
        # More scenes never lowers the (pre-clamp) price; price is non-decreasing.
        prev = -1
        for scenes in range(3, 12):
            out = pricing.price_for_plan(0, quality="standard", signals=_std_signals(scenes, 20))
            self.assertGreaterEqual(out["total_price_cents"], prev)
            prev = out["total_price_cents"]

    def test_monotonic_in_duration(self):
        prev = -1
        for dur in (20, 30, 40, 60, 90, 120):
            out = pricing.price_for_plan(0, quality="standard", signals=_std_signals(4, dur))
            self.assertGreaterEqual(out["total_price_cents"], prev)
            prev = out["total_price_cents"]
        # Premium duration monotonic too (cinematic fixed).
        prev = -1
        for dur in (20, 30, 40, 60):
            out = pricing.price_for_plan(0, quality="premium",
                                         signals=_prem_signals(2, dur, scenes=4))
            self.assertGreaterEqual(out["total_price_cents"], prev)
            prev = out["total_price_cents"]

    def test_token_cost_appears_as_line_item_and_in_margin(self):
        out = pricing.price_for_plan(100, quality="premium",
                                     signals=_prem_signals(1, 20, scenes=3, token_cost_cents=7))
        keys = {li["key"]: li["amount_cents"] for li in out["line_items"]}
        self.assertEqual(keys.get("tokens"), 7)
        self.assertEqual(out["token_cost_cents"], 7)
        self.assertEqual(out["plan_cogs_cents"], 100)
        self.assertAlmostEqual(out["margin"],
                               (out["total_price_cents"] - 100) / out["total_price_cents"],
                               places=9)

    def test_no_signals_prices_at_band_floor(self):
        # Existing-caller path (no storyboard signals) -> band minimum, single base line.
        std = pricing.price_for_plan(50, quality="standard")
        self.assertEqual(std["total_price_cents"], STD_MIN)
        self.assertEqual([li["key"] for li in std["line_items"]], ["base"])
        prem = pricing.price_for_plan(50, quality="premium")
        self.assertEqual(prem["total_price_cents"], PREM_MIN)

    def test_default_quality_is_standard(self):
        self.assertEqual(pricing.default_quality(), "standard")
        out = pricing.price_for_plan(100, signals=_std_signals(3, 18))  # no quality
        self.assertEqual(out["quality"], "standard")


# ===========================================================================
# (b) quality dimension — standard band below premium band, no consent
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

    def test_price_band_helper(self):
        self.assertEqual(pricing.price_band_cents("standard"), (STD_MIN, STD_MAX))
        self.assertEqual(pricing.price_band_cents("premium"), (PREM_MIN, PREM_MAX))

    def test_premium_band_strictly_above_standard_band(self):
        # Any premium price exceeds any standard price (bands do not overlap).
        std = pricing.price_for_plan(0, quality="standard", signals=_std_signals(40, 300))  # std ceil
        prem = pricing.price_for_plan(0, quality="premium",
                                      signals=_prem_signals(0, 15, uses_vo=False, scenes=2))  # prem floor
        self.assertEqual(std["total_price_cents"], STD_MAX)
        self.assertEqual(prem["total_price_cents"], PREM_MIN)
        self.assertGreater(prem["total_price_cents"], std["total_price_cents"])

    def test_premium_needs_no_consent(self):
        out = pricing.price_for_selection({"quality": "premium"}, 100,
                                          signals=_prem_signals(2, 30, scenes=4))
        self.assertEqual(out["quality"], "premium")
        self.assertGreaterEqual(out["total_price_cents"], PREM_MIN)
        ok, _reason = pricing.validate_consent({"quality": "premium"})
        self.assertTrue(ok)

    def test_price_for_selection_reads_quality(self):
        std = pricing.price_for_selection({"quality": "standard"}, 0, signals=_std_signals(3, 18))
        prem = pricing.price_for_selection({"quality": "premium"}, 100,
                                           signals=_prem_signals(1, 20, scenes=3))
        self.assertEqual(std["quality"], "standard")
        self.assertEqual(prem["quality"], "premium")


# ===========================================================================
# (c) base_price_for_cogs rounding + floor edge cases (retained cost-plus math)
# ===========================================================================

class TestRoundingAndFloor(unittest.TestCase):
    def test_rounds_to_nearest_50(self):
        self.assertEqual(pricing.base_price_for_cogs(84), 500)   # 504 -> 500
        self.assertEqual(pricing.base_price_for_cogs(92), 550)   # 552 -> 550

    def test_base_price_for_cogs_floor(self):
        self.assertEqual(pricing.base_price_for_cogs(0), FLOOR)

    def test_bad_cogs_raises(self):
        with self.assertRaises(pricing.PricingError):
            pricing.price_for_plan("not-a-number", quality="standard")

    def test_zero_cogs_prices_in_band(self):
        out = pricing.price_for_plan(0, quality="standard", signals=_std_signals(3, 18))
        self.assertGreaterEqual(out["total_price_cents"], STD_MIN)
        self.assertLessEqual(out["total_price_cents"], STD_MAX)


# ===========================================================================
# (c2) token cost COGS
# ===========================================================================

class TestTokenCost(unittest.TestCase):
    def test_super_free_is_zero(self):
        self.assertEqual(pricing.token_cost_cents("super-free", scenes=6, vo_chars=600), 0)

    def test_paid_brains_round_up_to_whole_cent(self):
        # Non-zero real cost never disappears to 0; both paid tiers cost >= 1c here.
        self.assertGreaterEqual(pricing.token_cost_cents("super-paid", scenes=6, vo_chars=600), 1)
        self.assertGreaterEqual(pricing.token_cost_cents("ultra-paid", scenes=6, vo_chars=600), 1)

    def test_ultra_costs_more_than_super_paid(self):
        # Real plan token volumes are sub-cent, so the ceil'd cents can tie at small
        # inputs; at a large enough volume the per-1k rate difference is visible.
        u = pricing.token_cost_cents("ultra-paid", scenes=200, vo_chars=20000)
        s = pricing.token_cost_cents("super-paid", scenes=200, vo_chars=20000)
        self.assertGreater(u, s)

    def test_estimate_planner_tokens_scales_with_inputs(self):
        few = pricing.estimate_planner_tokens(scenes=2, vo_chars=100)
        many = pricing.estimate_planner_tokens(scenes=10, vo_chars=1000)
        self.assertGreater(many[0], few[0])  # prompt tokens
        self.assertGreater(many[1], few[1])  # output tokens

    def test_walkthrough_steps_hook_default_zero(self):
        # Future hook: walkthrough steps are costed at 0 today, so adding steps does
        # not change the token estimate yet (the constants are 0).
        a = pricing.estimate_planner_tokens(scenes=4, vo_chars=200, walkthrough_steps=0)
        b = pricing.estimate_planner_tokens(scenes=4, vo_chars=200, walkthrough_steps=5)
        self.assertEqual(a, b)


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
        # No dynamic-pricing keys leak into the OFF result.
        self.assertNotIn("pricing_mode", off)
        self.assertNotIn("menu", off)
        self.assertNotIn("quality", off)
        self.assertNotIn("signals", off)

    def test_off_path_equals_plan_without_selection(self):
        os.environ.pop("WS_PREMIUM_MENU", None)
        with_sel = producer.cmd_estimate(_plan(selection={"quality": "premium"}))
        without = producer.cmd_estimate(_plan(selection=None))
        self.assertEqual(with_sel, without)

    def test_on_path_standard_drops_media_cogs_prices_in_band(self):
        os.environ["WS_PREMIUM_MENU"] = "1"
        on = producer.cmd_estimate(_plan(selection={"quality": "standard", "brain": "super-free"}))
        self.assertEqual(on["pricing_mode"], "cost_plus")
        self.assertEqual(on["quality"], "standard")
        self.assertEqual(on["menu"]["model"], "dynamic_banded")
        # standard drops the cinematic (22) + VO (30) media cogs; super-free token = 0.
        self.assertEqual(on["token_cost_cents"], 0)
        self.assertEqual(on["production_budget_cents"], 0)   # no paid media + 0 token
        # 2 scenes, 9s total -> base only -> band floor $5.00.
        self.assertEqual(on["suggested_price_cents"], STD_MIN)
        self.assertGreaterEqual(on["suggested_price_cents"], on["production_budget_cents"])
        # The per-scene estimate report is left intact (gate reasoning unchanged).
        self.assertEqual([s["id"] for s in on["scenes"]], ["a", "t"])
        self.assertEqual(on["scenes"][0]["est_cost_cents"], 22)

    def test_on_path_premium_keeps_cogs_and_prices_in_premium_band(self):
        os.environ["WS_PREMIUM_MENU"] = "1"
        on = producer.cmd_estimate(_plan(selection={"quality": "premium", "brain": "super-free"}))
        self.assertEqual(on["quality"], "premium")
        # premium keeps the 52c media spend, floored to the premium cogs_floor (100c);
        # super-free token = 0 -> budget = 100.
        self.assertEqual(on["token_cost_cents"], 0)
        self.assertEqual(on["production_budget_cents"], PREMIUM_COGS_FLOOR)
        # Price is in the PREMIUM band, strictly above any standard price.
        self.assertGreaterEqual(on["suggested_price_cents"], PREM_MIN)
        self.assertLessEqual(on["suggested_price_cents"], PREM_MAX)
        self.assertGreater(on["suggested_price_cents"], STD_MAX)
        # SACRED: price covers COGS.
        self.assertGreaterEqual(on["suggested_price_cents"], on["production_budget_cents"])
        self.assertNotIn("price_below_cogs_warning", on)

    def test_on_path_premium_paid_brain_folds_token_cogs(self):
        os.environ["WS_PREMIUM_MENU"] = "1"
        on = producer.cmd_estimate(_plan(selection={"quality": "premium", "brain": "ultra-paid"}))
        # Token COGS is non-zero for a paid brain and folds into the budget ceiling.
        self.assertGreaterEqual(on["token_cost_cents"], 1)
        # budget = media floor (100) + token cost.
        self.assertEqual(on["production_budget_cents"], PREMIUM_COGS_FLOOR + on["token_cost_cents"])
        # Token cost also shows up as a price line item.
        keys = {li["key"] for li in on["menu"]["line_items"]}
        self.assertIn("tokens", keys)
        self.assertGreaterEqual(on["suggested_price_cents"], on["production_budget_cents"])

    def test_on_path_default_selection_when_plan_omits_it(self):
        os.environ["WS_PREMIUM_MENU"] = "1"
        on = producer.cmd_estimate(_plan(selection=None))
        self.assertEqual(on["menu"]["model"], "dynamic_banded")
        self.assertEqual(on["quality"], "standard")                  # default
        self.assertGreaterEqual(on["suggested_price_cents"], STD_MIN)
        self.assertLessEqual(on["suggested_price_cents"], STD_MAX)
        self.assertEqual(on["production_budget_cents"], 0)

    def test_on_path_price_scales_with_storyboard(self):
        os.environ["WS_PREMIUM_MENU"] = "1"
        small = producer.cmd_estimate(_plan(
            scenes=[{"id": "t", "type": "title", "model": None, "duration_s": 3, "brief": "b"},
                    {"id": "m", "type": "motion_graphic", "model": None, "duration_s": 4, "brief": "b"}],
            selection={"quality": "standard", "brain": "super-free"}))
        big = producer.cmd_estimate(_plan(
            scenes=[{"id": "s%d" % i, "type": "motion_graphic", "model": None,
                     "duration_s": 6, "brief": "b"} for i in range(8)],
            selection={"quality": "standard", "brain": "super-free"}))
        # More scenes + longer duration -> a higher (or equal-at-ceiling) price.
        self.assertGreater(big["suggested_price_cents"], small["suggested_price_cents"])


# ===========================================================================
# (e) back-compat: OLD selections still parse + map onto quality
# ===========================================================================

class TestLegacySelectionBackCompat(unittest.TestCase):
    def test_legacy_premium_vo_maps_to_premium(self):
        legacy = {"options": {"premium_vo": True}}
        self.assertEqual(pricing.quality_from_selection(legacy), "premium")
        out = pricing.price_for_selection(legacy, 100)
        self.assertEqual(out["quality"], "premium")
        self.assertGreaterEqual(out["total_price_cents"], PREM_MIN)

    def test_legacy_founder_voice_booster_maps_to_premium(self):
        legacy = {"tier": "studio", "boosters": ["rush", "founder_voice"], "options": {}}
        self.assertEqual(pricing.quality_from_selection(legacy), "premium")
        self.assertTrue(pricing.addons_from_selection(legacy)["premium_vo"])

    def test_legacy_plain_old_selection_defaults_standard(self):
        legacy = {"tier": "pro", "boosters": ["rush"], "options": {}}
        self.assertEqual(pricing.quality_from_selection(legacy), "standard")
        self.assertFalse(pricing.addons_from_selection(legacy)["premium_vo"])

    def test_price_selection_shim_still_callable(self):
        out = pricing.price_selection({"quality": "premium"}, plan_cogs_cents=100)
        self.assertEqual(out["model"], "dynamic_banded")
        self.assertGreaterEqual(out["total_price_cents"], PREM_MIN)


if __name__ == "__main__":
    unittest.main(verbosity=2)
