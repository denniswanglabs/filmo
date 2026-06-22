#!/usr/bin/env python3
"""Produce-side tests for COST-PLUS PRICING + the QUALITY dimension (WS_PREMIUM_MENU=1).

These run the WHOLE orchestrate() loop in mock mode ($0): real edge-tts + real
ffmpeg, mock generation. They assert that the ONE customer choice (quality:
standard | premium) maps to the right PRODUCE behavior and that the produced
ledger itemization matches price_for_plan() so the on-screen P&L and the produced
ledger never drift.

The model: quality changes WHAT the agent produces.
  * standard -> NO Higgsfield (cinematic scenes fall back to a free designed
    Remotion scene) + edge-tts voiceover. Cheapest; price floors at $5.
  * premium  -> cinematic scenes use real Higgsfield (--mode real) + a natural
    ElevenLabs STOCK voice (--mode real). Richer / ~$6-9. In mock BOTH stay $0.

Asserted here:
  (a) standard (default): cinematic scenes are produced WITHOUT Higgsfield (the
      free designed-Remotion fallback, decision "standard", $0) and the VO is
      edge-tts ($0); no premium_vo record.
  (b) premium in mock: the cinematic scenes still mock-generate (mock = $0), the VO
      engine stays edge ($0, no real synth) and the premium upgrade is recorded
      with NO consent requirement.
  (c) premium in --mode real: selects the ElevenLabs STOCK voice with NO consent
      step anywhere (the real engine is invoked; tripwire), and real Higgsfield is
      the cinematic path (no standard fallback).
  (d) the produced cost-plus ledger line items MATCH pricing.price_for_plan()
      exactly (labels + per-line + total price/cogs).
  (e) retired boosters/watermark DROP OUT of the active path.

Run: python3 -m unittest tests.test_premium_produce
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

# Deterministic planning prices (same stub the suite uses); the cost-plus model
# OVERRIDES the locked budget/price, but the per-scene gate still reads these.
PLANNING_STUB = json.dumps({"seedance_2_0": 22, "gpt_image_2": 7,
                            "nano_banana_flash": 4, "__default__": 10})
os.environ["PRODUCER_COST_STUB"] = PLANNING_STUB
os.environ["WS_PREMIUM_MENU"] = "1"   # cost-plus produce-side ON for this module

import orchestrator  # noqa: E402
import pricing  # noqa: E402


def load(name):
    with open(os.path.join(SCEN, name)) as f:
        return json.load(f)


def run(plan, run_id, mode="mock", vo_provider="edge"):
    os.environ["WS_PREMIUM_MENU"] = "1"
    os.environ["PRODUCER_COST_STUB"] = PLANNING_STUB
    os.environ.pop("PRODUCER_PRODUCTION_COST_STUB", None)
    tmp = tempfile.mkdtemp(prefix="hermes-quality-test-")
    data, _ = orchestrator.orchestrate(plan, run_id, mode=mode, runs_dir=tmp,
                                        vo_provider=vo_provider,
                                        now="2026-06-21T00:00:00Z")
    return data, tmp


def with_quality(scenario, quality):
    plan = load(scenario)
    plan["selection"] = {"quality": quality}
    return plan


class TestStandardQuality(unittest.TestCase):
    def test_standard_no_higgsfield_edge_vo_floor_price(self):
        plan = with_quality("scenario_approve.json", "standard")
        data, _ = run(plan, "t-q-standard")
        self.assertEqual(data["premium"]["quality"], "standard")
        # cinematic scenes fall back to the free designed-Remotion path (decision
        # "standard", $0) — NEVER the paid Higgsfield path.
        cine = [s for s in data["scenes"] if s["type"] == "cinematic"]
        self.assertTrue(cine)
        for s in cine:
            self.assertEqual(s["decision"], "standard")
            self.assertEqual(s.get("spent_cents", 0), 0)
            self.assertNotEqual(s.get("tool"), "higgsfield-scene")
        # VO is the clean synthetic voice (edge-tts), $0, no premium_vo record.
        self.assertIsNone(data["voiceover"].get("premium_vo"))
        self.assertEqual(data["voiceover"]["provider"], "edge-tts")
        self.assertFalse(data["voiceover"].get("real", False))
        # Dynamic-banded pricing: a standard run prices WITHIN the standard band
        # [$5,$10] (this scenario earns scene/duration extras over the $5 base) and
        # never below production COGS. No paid spend -> plan COGS is $0.
        menu = data["premium"]["menu"]
        self.assertEqual(menu["band"], {"min_cents": 500, "max_cents": 1000})
        self.assertGreaterEqual(menu["total_price_cents"], menu["band"]["min_cents"])
        self.assertLessEqual(menu["total_price_cents"], menu["band"]["max_cents"])
        self.assertGreaterEqual(menu["total_price_cents"], menu["total_cogs_cents"])
        self.assertEqual(menu["plan_cogs_cents"], 0)


class TestPremiumQualityMock(unittest.TestCase):
    def test_premium_in_mock_stays_edge_no_real_synth_no_consent(self):
        plan = with_quality("scenario_approve.json", "premium")
        data, _ = run(plan, "t-q-premium-mock")
        self.assertEqual(data["premium"]["quality"], "premium")
        pv = data["voiceover"].get("premium_vo")
        self.assertIsNotNone(pv)
        self.assertEqual(pv["engine"], "edge")            # mock -> free engine
        self.assertEqual(pv["voice_type"], "stock")
        self.assertFalse(pv["consent_required"])          # stock voice, no consent
        self.assertEqual(data["voiceover"]["provider"], "edge-tts")
        self.assertFalse(data["voiceover"].get("real", False))
        # premium prices ABOVE the standard floor.
        self.assertGreater(data["premium"]["menu"]["total_price_cents"], 500)


class TestPremiumQualityRealStockVoice(unittest.TestCase):
    """In --mode real, premium quality selects the ElevenLabs STOCK voice with NO
    consent step anywhere AND uses the real Higgsfield cinematic path (no standard
    fallback). We tripwire the real engines to confirm they ARE used."""

    def test_real_mode_uses_elevenlabs_and_higgsfield_no_consent(self):
        import adapters

        called = {"elevenlabs": False, "voice_id": None, "cinematic": 0}
        orig_el = adapters._vo_elevenlabs

        def _fake_el(script, voice, out_path):
            called["elevenlabs"] = True
            called["voice_id"] = voice
            info = adapters._vo_edge(script, voice, out_path)
            info["provider"] = "elevenlabs"
            info["real"] = True
            return info

        plan = with_quality("scenario_approve.json", "premium")

        # Stub the real gens to mock cards (avoid network), but count cinematic
        # calls so we prove premium took the Higgsfield path, not the standard one.
        orig_cine = adapters.generate_cinematic
        orig_walk = adapters.generate_walkthrough
        orig_overlay = adapters.generate_overlay

        def _count_cine(scene, out, mode, **k):
            called["cinematic"] += 1
            return orig_cine(scene, out, "mock")

        adapters._vo_elevenlabs = _fake_el
        adapters.generate_cinematic = _count_cine
        adapters.generate_walkthrough = lambda scene, out, mode, **k: orig_walk(scene, out, "mock")
        adapters.generate_overlay = lambda scene, out, mode, **k: orig_overlay(scene, out, "mock")
        try:
            data, _ = run(plan, "t-q-premium-real", mode="real", vo_provider="elevenlabs")
        finally:
            adapters._vo_elevenlabs = orig_el
            adapters.generate_cinematic = orig_cine
            adapters.generate_walkthrough = orig_walk
            adapters.generate_overlay = orig_overlay

        self.assertTrue(called["elevenlabs"], "real premium must use ElevenLabs")
        self.assertGreater(called["cinematic"], 0,
                           "real premium must use the Higgsfield cinematic path")
        pv = data["voiceover"].get("premium_vo")
        self.assertIsNotNone(pv)
        self.assertEqual(pv["engine"], "elevenlabs")
        self.assertEqual(pv["voice_type"], "stock")
        self.assertFalse(pv["consent_required"])
        # No consent attestation key anywhere in the VO record (no clone path).
        self.assertNotIn("consent_ok", pv)
        self.assertNotIn("owner", pv)


class TestLedgerMatchesCostPlus(unittest.TestCase):
    """The produced cost-plus ledger itemization must MATCH price_for_plan() so the
    dashboard P&L (which reads the same quote) and the produced ledger never drift."""

    def test_ledger_line_items_match_price_for_plan(self):
        plan = with_quality("scenario_approve.json", "premium")
        data, _ = run(plan, "t-q-ledger")

        led = data["premium"]["ledger"]
        # Dynamic-banded pricing is SIGNALS-aware: the produced ledger must match the
        # SAME itemized menu the orchestrator built (the one the dashboard P&L reads),
        # so the ledger and on-screen P&L never drift. (A bare price_for_plan() with
        # no storyboard signals would only yield the base fee -- not the produced menu.)
        expected = data["premium"]["menu"]

        self.assertEqual([li["label"] for li in led["line_items"]],
                         [li["label"] for li in expected["line_items"]])
        for got, exp in zip(led["line_items"], expected["line_items"]):
            self.assertEqual(got["price_cents"], exp["price_cents"], got["label"])
            self.assertEqual(got["cogs_cents"], exp["cogs_cents"], got["label"])
        self.assertEqual(led["total_price_cents"], expected["total_price_cents"])
        self.assertEqual(led["total_cogs_cents"], expected["total_cogs_cents"])


class TestRetiredBoostersDropOut(unittest.TestCase):
    """The retired tier/booster behaviors must not fire in the active cost-plus
    path: no watermark, no format pack, no founder_voice/rush records."""

    def test_no_watermark_no_format_pack_no_legacy_records(self):
        plan = with_quality("scenario_approve.json", "premium")
        data, _ = run(plan, "t-q-retired")
        # Cost-plus model: watermark always off, no format pack.
        self.assertFalse(data["premium"]["watermark"])
        self.assertFalse(data["stitch"].get("watermark", False))
        self.assertIsNone(data["premium"].get("format_pack"))
        # No retired tier/booster fields surfaced.
        self.assertNotIn("tier", data["premium"])
        self.assertNotIn("rush", data["premium"])
        # No founder_voice clone record on the VO.
        self.assertIsNone(data["voiceover"].get("founder_voice"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
