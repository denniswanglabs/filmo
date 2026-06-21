"""Deterministic ($0) tests for style_fill.py (Phase 2 keystone).

No synth, no whisper, no render -- a hand-built alignment + plan + brand exercise
the STYLE REGISTRY (role->archetype), the data shapers, the theme mapping, and the
MERGE that emits the exact <Timeline> props contract. run_pipeline is tested with
do_align=False against a written alignment fixture (so it stays offline + free).
"""
import json
import os
import tempfile
import unittest

import style_fill
import build_timeline


def _brand():
    return {
        "brand": "Orinovate",
        "wordmark": "Orinovate",
        "tagline": "On-demand manufacturing",
        "palette": {
            "bg": "#ffffff", "accent": "#2563eb", "navy": "#1a3a5c",
            "text": "#0f2338",
        },
        "fonts": {"fontPrimary": "Inter, sans-serif"},
        "features": [
            {"label": "3D Printing", "value": "24h", "sub": "FDM / SLA"},
            {"label": "CNC Machining", "sub": "Milling"},
            {"label": "Sheet Metal", "sub": "Laser cut"},
            {"label": "Laser Sintering", "sub": "Titanium"},
            {"label": "EXTRA-IGNORED", "sub": "should not appear"},
        ],
        "cta_url": "orinovate.com",
    }


def _plan():
    return {
        "scenes": [
            {"id": "open", "role": "open",
             "data": {"kicker": "INTRODUCING", "title": "Quotes in seconds",
                      "punchWord": "seconds", "subtitle": "One upload."},
             "cues": [{"label": "title-in", "word": "quotes"},
                      {"label": "punch", "word": "seconds"}]},
            {"id": "caps", "role": "feature",
             "data": {"heading": "Ship in 24 hours", "headingAccent": "24 hours"},
             "cues": [{"label": "heading-in", "word": "ship"},
                      {"label": "card-1", "word": "printing"}]},
            {"id": "close", "role": "close",
             "data": {"title": "Start your quote", "punchWord": "quote"},
             "cues": [{"label": "title-in", "word": "quote"}]},
        ],
        "voiceover": {"voice": "v", "beats": [
            {"scene_id": "open", "text": "Quotes in seconds"},
            {"scene_id": "caps", "text": "Ship printing machining sheet laser"},
            {"scene_id": "close", "text": "Start your quote"},
        ]},
    }


def _alignment():
    """Hand-built alignment matching _plan beats; words carry beat_scene_id."""
    def w(word, s, e, sid):
        return {"word": word, "start_s": s, "end_s": e, "beat_scene_id": sid}
    words = [
        w("Quotes", 0.0, 0.4, "open"), w("in", 0.4, 0.6, "open"),
        w("seconds", 0.6, 1.2, "open"),
        w("Ship", 1.2, 1.6, "caps"), w("printing", 1.6, 2.0, "caps"),
        w("machining", 2.0, 2.4, "caps"), w("sheet", 2.4, 2.8, "caps"),
        w("laser", 2.8, 3.2, "caps"),
        w("Start", 3.2, 3.6, "close"), w("your", 3.6, 3.8, "close"),
        w("quote", 3.8, 4.4, "close"),
    ]
    beats = [
        {"scene_id": "open", "start_s": 0.0, "end_s": 1.2, "text": "Quotes in seconds"},
        {"scene_id": "caps", "start_s": 1.2, "end_s": 3.2, "text": "Ship printing machining sheet laser"},
        {"scene_id": "close", "start_s": 3.2, "end_s": 4.4, "text": "Start your quote"},
    ]
    return {"audio_path": "voiceover.mp3", "lang": "en",
            "total_duration_s": 4.4, "words": words, "beats": beats}


class TestRegistry(unittest.TestCase):
    def test_known_style_routes_roles(self):
        st = style_fill.STYLES["orinovate-kinetic-light"]
        self.assertEqual(st.archetype_for({"role": "open"}), style_fill.ARCH_HERO)
        self.assertEqual(st.archetype_for({"role": "close"}), style_fill.ARCH_HERO)
        self.assertEqual(st.archetype_for({"role": "feature"}), style_fill.ARCH_CARD)
        self.assertEqual(st.archetype_for({"type": "capabilities"}), style_fill.ARCH_CARD)
        # unknown role -> default archetype, never a crash.
        self.assertEqual(st.archetype_for({"role": "mystery"}), st.default_archetype)

    def test_unknown_style_raises(self):
        tl = build_timeline.build_timeline(_plan()["scenes"], _alignment())
        with self.assertRaises(KeyError):
            style_fill.build_props(tl, _plan(), _brand(), "no-such-style")


class TestShapers(unittest.TestCase):
    def test_hero_open_uses_copy_and_punch(self):
        d = style_fill._shape_hero(_plan()["scenes"][0], _brand())
        self.assertEqual(d["title"], "Quotes in seconds")
        self.assertEqual(d["punchWord"], "seconds")  # substring of title
        self.assertEqual(d["subtitle"], "One upload.")

    def test_hero_close_falls_back_to_cta_url(self):
        sc = {"id": "close", "role": "close", "data": {"title": "Start your quote"}}
        d = style_fill._shape_hero(sc, _brand())
        self.assertEqual(d["subtitle"], "orinovate.com")

    def test_hero_drops_punch_not_in_title(self):
        sc = {"id": "x", "role": "open", "data": {"title": "Hello", "punchWord": "WORLD"}}
        d = style_fill._shape_hero(sc, _brand())
        self.assertNotIn("punchWord", d)

    def test_cards_grid_from_brand_features(self):
        d = style_fill._shape_cards(_plan()["scenes"][1], _brand())
        self.assertEqual(len(d["cards"]), style_fill.CARD_COUNT)  # capped at 4
        self.assertEqual(d["cards"][0]["label"], "3D Printing")
        self.assertEqual(d["cards"][0]["value"], "24h")
        # exactly one accent card (first one promoted since none flagged).
        self.assertEqual(sum(1 for c in d["cards"] if c["accent"]), 1)
        self.assertTrue(d["cards"][0]["accent"])
        self.assertEqual(d["heading"], "Ship in 24 hours")


class TestTheme(unittest.TestCase):
    def test_theme_has_every_composition_key(self):
        th = style_fill._theme_kinetic_light(_brand())
        for k in style_fill._THEME_PALETTE_KEYS + style_fill._THEME_FONT_KEYS:
            self.assertIn(k, th)
            self.assertTrue(th[k], f"theme key {k} empty")
        self.assertEqual(th["accent"], "#2563eb")     # from brand
        self.assertEqual(th["bgCardRaised"], "#f9fafc")  # default fill
        self.assertEqual(th["wordmark"], "Orinovate")


class TestMergeContract(unittest.TestCase):
    def test_props_shape_and_provenance(self):
        tl = build_timeline.build_timeline(_plan()["scenes"], _alignment())
        props = style_fill.build_props(tl, _plan(), _brand(), "orinovate-kinetic-light")
        # top-level contract
        for k in ("fps", "total_frames", "audio_path", "lang", "theme", "scenes"):
            self.assertIn(k, props)
        self.assertEqual(len(props["scenes"]), 3)
        sc_open, sc_caps, sc_close = props["scenes"]
        # frames + cues come from the timeline (VO-anchored)
        self.assertEqual(sc_open["in_frame"], tl["scenes"][0]["in_frame"])
        self.assertEqual(sc_open["out_frame"], tl["scenes"][0]["out_frame"])
        self.assertEqual(sc_open["cues"], tl["scenes"][0]["cues"])
        # archetype decided by the STYLE, not the plan field
        self.assertEqual(sc_open["archetype"], style_fill.ARCH_HERO)
        self.assertEqual(sc_caps["archetype"], style_fill.ARCH_CARD)
        self.assertEqual(sc_close["archetype"], style_fill.ARCH_HERO)
        # data filled per archetype
        self.assertIn("title", sc_open["data"])
        self.assertIn("cards", sc_caps["data"])

    def test_cues_anchor_to_word_frames(self):
        """A reveal cue must land on the frame of the word it names."""
        align = _alignment()
        tl = build_timeline.build_timeline(_plan()["scenes"], align)
        props = style_fill.build_props(tl, _plan(), _brand(), "orinovate-kinetic-light")
        caps = props["scenes"][1]
        card1 = next(c for c in caps["cues"] if c["label"] == "card-1")
        # 'printing' starts at 1.6s -> 48f @30fps; clamped within the scene.
        self.assertEqual(card1["word"], "printing")
        self.assertGreaterEqual(card1["at_frame"], caps["in_frame"])
        self.assertLessEqual(card1["at_frame"], caps["out_frame"])


class TestPipelineOffline(unittest.TestCase):
    def test_run_pipeline_no_align(self):
        with tempfile.TemporaryDirectory() as d:
            plan_p = os.path.join(d, "plan.json")
            brand_p = os.path.join(d, "brand.json")
            align_p = os.path.join(d, "vo_alignment.json")
            with open(plan_p, "w") as f:
                json.dump(_plan(), f)
            with open(brand_p, "w") as f:
                json.dump(_brand(), f)
            with open(align_p, "w") as f:
                json.dump(_alignment(), f)
            res = style_fill.run_pipeline(plan_p, brand_p,
                                          "orinovate-kinetic-light", d,
                                          fps=30, do_align=False, do_render=False)
            self.assertTrue(os.path.exists(res["props_path"]))
            self.assertTrue(os.path.exists(res["timeline_path"]))
            with open(res["props_path"]) as f:
                props = json.load(f)
            self.assertEqual(len(props["scenes"]), 3)
            # audio_path is rewritten to a public-relative name (no leading slash)
            # so Remotion's staticFile() can serve it from studio/public/.
            self.assertFalse(props["audio_path"].startswith("/"))
            self.assertTrue(props["audio_path"].endswith(".mp3"))


if __name__ == "__main__":
    unittest.main()
