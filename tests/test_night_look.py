"""Engineered Night style knob — registry routing, shapers, and music mapping."""
import json
import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import night_music
import style_fill


def scene(role="motion_graphic", treatment=None, sid="s1", data=None, dur=6):
    d = dict(data or {})
    if treatment:
        d["treatment"] = treatment
    return {"id": sid, "type": role, "brief": "b", "model": None,
            "duration_s": dur, "input_image": None, "data": d}


class NightRegistry(unittest.TestCase):
    def setUp(self):
        self.style = style_fill.STYLES["engineered-night"]

    def test_registered_alongside_classic(self):
        self.assertIn("orinovate-kinetic-light", style_fill.STYLES)
        self.assertIn("engineered-night", style_fill.STYLES)

    def test_role_routing(self):
        self.assertEqual(self.style.archetype_for(scene(role="title", sid="opening-title")), "night-hero")
        self.assertEqual(self.style.archetype_for(scene(role="title", sid="closing-cta")), "night-close")
        self.assertEqual(self.style.archetype_for(scene(role="screenshot")), "night-panel")

    def test_treatment_refinement(self):
        self.assertEqual(self.style.archetype_for(scene(treatment="pull-quote")), "night-quote")
        self.assertEqual(self.style.archetype_for(scene(treatment="split-stat")), "night-credibility")
        self.assertEqual(self.style.archetype_for(scene(treatment="split-mosaic")), "night-ecosystem")
        self.assertEqual(self.style.archetype_for(scene(treatment="process-pipeline")), "night-terminal")
        self.assertEqual(self.style.archetype_for(scene(treatment="icon-headline")), "night-ladder")
        self.assertEqual(self.style.archetype_for(scene()), "night-ladder")

    def test_data_signal_routing_without_treatment_tags(self):
        # The hosted regression: treatments are assigned late in the classic flow,
        # so night routing must read the seeded data directly.
        self.assertEqual(self.style.archetype_for(scene(
            data={"quote": "Real quote from the page here.", "quoteAttribution": "P. Person"})), "night-quote")
        self.assertEqual(self.style.archetype_for(scene(
            data={"stat": {"value": "135+", "label": "currencies"}})), "night-credibility")
        self.assertEqual(self.style.archetype_for(scene(
            data={"steps": [{"label": "a"}, {"label": "b"}]})), "night-terminal")
        self.assertEqual(self.style.archetype_for(scene(
            data={"featureEntities": ["Amazon", "Shopify", "Instacart"]})), "night-ecosystem")

    def test_quote_shaper_scales_hold_to_duration(self):
        s = scene(treatment="pull-quote", dur=13,
                  data={"quote": "Real words here from the page.", "quoteAttribution": "A. Person"})
        out = self.style.shape(s, {})
        self.assertEqual(out["holdFrames"], 390)
        self.assertEqual(out["quote"], "Real words here from the page.")

    def test_terminal_stashes_close_motif(self):
        brand = {}
        s = scene(treatment="process-pipeline",
                  data={"steps": [{"label": "step one"}, {"label": "step two"}, {"label": "step three"}]})
        out = self.style.shape(s, brand)
        self.assertEqual(out["lines"][:2], ["step one", "step two"])
        self.assertEqual(brand["_night_terminal_lines"], ["step one", "step two"])

    def test_accent_split_marks_one_phrase(self):
        lines = style_fill._night_accent_split("Ship production-ready backends in minutes")
        flat = [p for line in lines for p in line]
        self.assertEqual(sum(1 for p in flat if p.get("accent")), 1)
        joined = "".join(p["text"] for p in flat)
        self.assertIn("production-ready", joined)


class NightDevelopmentPass(unittest.TestCase):
    """docs/night-development-pass.md — §C/§D acceptance at the shaper level."""

    def setUp(self):
        self.style = style_fill.STYLES["engineered-night"]

    def test_balanced_split_keeps_real_estate_together(self):
        # The observed hero bug: "…independent real / estate agent…". The
        # penalty-balanced split must not break right after the short word.
        lines = style_fill._night_balanced_split(
            "Give every independent real estate agent a professional site".split())
        self.assertEqual(len(lines), 2)
        self.assertFalse(lines[0][-1].lower() == "real",
                         f"split still breaks the compound: {lines}")

    def test_balanced_split_prefers_natural_boundary(self):
        lines = style_fill._night_balanced_split(
            "Launch a professional real estate agent site".split())
        self.assertEqual(lines[0], ["Launch", "a", "professional"])

    def test_chips_harvest_priority_entities_first(self):
        d = {"featureEntities": ["Alpha", "Beta", "Gamma"]}
        brand = {"features": [{"title": "PageFeat"}]}
        self.assertEqual(style_fill._night_harvest_chips(d, brand)[:2], ["Alpha", "Beta"])

    def test_chips_harvest_falls_back_to_brand_features(self):
        brand = {"features": [{"title": "Collect inquiries"}, {"title": "Publish fast"}]}
        chips = style_fill._night_harvest_chips({}, brand)
        self.assertEqual(chips, ["Collect inquiries", "Publish fast"])

    def test_chips_harvest_reads_story_shape(self):
        brand = {"_plan_design_brief": {"story_shape": {
            "features": [{"title": "Ship Faster"}, {"title": "Safe for Agents"}]}}}
        chips = style_fill._night_harvest_chips({}, brand)
        self.assertEqual(chips, ["Ship Faster", "Safe for Agents"])

    def test_chips_harvest_empty_stays_honest(self):
        # One item is not a ladder; nothing real -> [] -> statement mode.
        self.assertEqual(style_fill._night_harvest_chips({"featureEntities": ["Solo"]}, {}), [])
        self.assertEqual(style_fill._night_harvest_chips({}, {}), [])

    def test_chips_harvest_steps_only_without_terminal(self):
        d = {"steps": [{"title": "Choose your name"}, {"title": "Create your site"}]}
        # No terminal in the film -> steps may ladder.
        self.assertEqual(len(style_fill._night_harvest_chips(d, {})), 2)
        # Terminal already types these lines -> chips must NOT repeat them.
        self.assertEqual(
            style_fill._night_harvest_chips(d, {"_night_terminal_lines": ["Choose your name"]}), [])

    def test_statement_support_threads_spoken_text_only(self):
        s = scene(treatment=None, data={
            "_text": "A client messages on WhatsApp and the structured request lands in your inbox."})
        out = style_fill._shape_night_ladder(s, {})
        self.assertEqual(out["chips"], [])
        self.assertTrue(out["support"])
        self.assertIn("WhatsApp", out["support"])

    def test_statement_support_absent_when_headline_is_the_text(self):
        s = scene(treatment=None, data={"_text": "Collect every inquiry"})
        out = style_fill._shape_night_ladder(s, {})
        self.assertFalse(out.get("support"))

    def test_statement_gets_shot_fragment_when_capture_exists(self):
        # v4: with a stashed capture, a statement beat carries a page fragment.
        brand = {"_night_shot_raw": "/runs/x/screenshots/shot-01.png"}
        s = scene(treatment=None, data={"_text": "Collect every inquiry from one link today"})
        out = style_fill._shape_night_ladder(s, brand)
        self.assertEqual(out["chips"], [])
        self.assertEqual(out["imageSrc"], "/runs/x/screenshots/shot-01.png")
        # No capture -> no fragment key (renders the centered statement).
        out2 = style_fill._shape_night_ladder(s, {})
        self.assertNotIn("imageSrc", out2)

    def test_close_recaps_the_chip_family(self):
        brand = {"features": [{"title": "Payments"}, {"title": "Billing"}]}
        ladder = style_fill._shape_night_ladder(scene(treatment=None, data={}), brand)
        self.assertEqual(ladder["chips"], ["Payments", "Billing"])
        close = style_fill._shape_night_close(scene(role="title", treatment=None, data={}), brand)
        self.assertEqual(close["recapChips"], ["Payments", "Billing"])

    def test_build_props_stashes_design_brief_for_shapers(self):
        # §D channel: build_props must expose plan.design_brief on the brand dict.
        import inspect
        src = inspect.getsource(style_fill.build_props)
        self.assertIn("_plan_design_brief", src)


class NightMusic(unittest.TestCase):
    def test_bed_maps_climax_earlier_than_source(self):
        out = "/tmp/test-night-bed.mp3"
        ok = night_music.build_bed(target_climax_s=30.0, total_s=34.0, out_path=out)
        self.assertTrue(ok)
        # §B: the mapper now reports the output-time beat grid.
        self.assertTrue(ok.get("ok"))
        self.assertGreater(ok.get("spb_s", 0), 0.3)
        self.assertGreaterEqual(ok.get("first_beat_s", -1), 0.0)
        self.assertLess(ok["first_beat_s"], ok["spb_s"] + 1e-6)
        dur = float(subprocess.check_output(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", out]).strip())
        self.assertGreaterEqual(dur, 34.0)
        os.remove(out)

    def test_bed_refuses_degenerate_targets(self):
        self.assertFalse(night_music.build_bed(1.0, 2.0, "/tmp/nope.mp3"))

    def test_beat_grid_math(self):
        g = night_music.beat_grid(trim_head_s=22.9, atempo=1.0, bpm=99.4)
        spb = 60.0 / 99.4
        self.assertAlmostEqual(g["spb_s"], spb, places=6)
        self.assertGreaterEqual(g["first_beat_s"], 0.0)
        self.assertLess(g["first_beat_s"], spb)
        # atempo speeds the audio: beats get closer together in output time.
        fast = night_music.beat_grid(0.0, 1.08, 99.4)
        self.assertAlmostEqual(fast["spb_s"], spb / 1.08, places=6)
        self.assertAlmostEqual(fast["first_beat_s"], 0.0, places=6)


if __name__ == "__main__":
    unittest.main()
