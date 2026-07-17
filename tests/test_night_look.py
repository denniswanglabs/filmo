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


class NightMusic(unittest.TestCase):
    def test_bed_maps_climax_earlier_than_source(self):
        out = "/tmp/test-night-bed.mp3"
        ok = night_music.build_bed(target_climax_s=30.0, total_s=34.0, out_path=out)
        self.assertTrue(ok)
        dur = float(subprocess.check_output(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", out]).strip())
        self.assertGreaterEqual(dur, 34.0)
        os.remove(out)

    def test_bed_refuses_degenerate_targets(self):
        self.assertFalse(night_music.build_bed(1.0, 2.0, "/tmp/nope.mp3"))


if __name__ == "__main__":
    unittest.main()
