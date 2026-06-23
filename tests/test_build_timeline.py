#!/usr/bin/env python3
"""Unit tests for build_timeline.py — the VO-driven timeline inversion.

Deterministic, $0, offline. Fed a hand-built fixture vo_alignment.json (NOT the
output of align_vo.py — this module must stand alone). Asserts:
  - voiced scene  -> in/out from its word span (NOT duration_s)
  - unvoiced hold -> advisory duration_s (fallback 1.5s), slid in with no gap
  - a cut scene   -> skipped; the rest slide earlier (no dead air)
  - cue resolution (by word text and by word_index)
  - contiguity (no gaps, no overlaps) + last-scene out_frame == total_frames

Run with either:
    python3 -m unittest tests.test_build_timeline
    python3 -m pytest tests/test_build_timeline.py
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import build_timeline as bt  # noqa: E402

FPS = 30


def alignment():
    """A small, self-contained vo_alignment.json matching the align_vo.py contract.
    Total 6.0s. s1 voiced 0.5-2.0s, s2 voiced 3.0-4.5s. (Gaps in absolute time on
    purpose, to prove the slide rule closes them.)"""
    return {
        "audio_path": "voiceover.mp3",
        "lang": "en",
        "total_duration_s": 6.0,
        "words": [
            {"word": "Stripe", "start_s": 0.5, "end_s": 1.0, "beat_scene_id": "s1"},
            {"word": "payments", "start_s": 1.0, "end_s": 2.0, "beat_scene_id": "s1"},
            {"word": "Dashboard", "start_s": 3.0, "end_s": 3.6, "beat_scene_id": "s2"},
            {"word": "keys", "start_s": 4.0, "end_s": 4.5, "beat_scene_id": "s2"},
        ],
        "beats": [
            {"scene_id": "s1", "start_s": 0.5, "end_s": 2.0, "text": "Stripe payments"},
            {"scene_id": "s2", "start_s": 3.0, "end_s": 4.5, "text": "Dashboard keys"},
        ],
    }


def base_scenes():
    return [
        {"id": "logo", "archetype": "title", "duration_s": 1.0},
        {"id": "s1", "archetype": "kinetic",
         "cues": [{"label": "hl", "word": "payments"}]},
        {"id": "s2", "archetype": "walkthrough",
         "cues": [{"label": "k", "word_index": 1}]},
    ]


def _byid(tl):
    return {s["id"]: s for s in tl["scenes"]}


class TestVoicedSpan(unittest.TestCase):
    def test_voiced_scene_length_from_word_span_not_duration_s(self):
        # Duration contract: scene length = max(plan duration_s, VO word span). s1's
        # word span is 1.5s -> 45 frames. A plan duration_s SMALLER than the span must
        # never cut the voice short: the VO span wins.
        scenes = base_scenes()
        scenes[1]["duration_s"] = 1.0  # 30f, below the 45f span -> span wins
        tl = bt.build_timeline(scenes, alignment(), fps=FPS)
        s1 = _byid(tl)["s1"]
        self.assertEqual(s1["out_frame"] - s1["in_frame"], 45)

    def test_audio_path_and_lang_passthrough(self):
        tl = bt.build_timeline(base_scenes(), alignment(), fps=FPS)
        self.assertEqual(tl["fps"], FPS)
        self.assertEqual(tl["audio_path"], "voiceover.mp3")
        self.assertEqual(tl["lang"], "en")

    def test_media_duration_floors_scene_length(self):
        # P2 walkthrough floor: a scene carrying a produced clip must HOLD at least
        # the clip's length so OffthreadVideo never truncates. s2's VO span is 1.5s
        # (45f); a 4.0s clip (120f) must win even though the voice + plan are shorter.
        scenes = base_scenes()
        scenes[2]["media_duration_s"] = 4.0  # 120f, above the 45f span
        tl = bt.build_timeline(scenes, alignment(), fps=FPS)
        s2 = _byid(tl)["s2"]
        self.assertEqual(s2["out_frame"] - s2["in_frame"], 120)

    def test_media_duration_does_not_shrink_longer_voice(self):
        # A clip SHORTER than the voice never cuts the VO: the larger floor wins.
        scenes = base_scenes()
        scenes[2]["media_duration_s"] = 0.5  # 15f, below the 45f span -> span wins
        tl = bt.build_timeline(scenes, alignment(), fps=FPS)
        s2 = _byid(tl)["s2"]
        self.assertEqual(s2["out_frame"] - s2["in_frame"], 45)


class TestUnvoicedHold(unittest.TestCase):
    def test_unvoiced_uses_advisory_duration_and_slides_in(self):
        tl = bt.build_timeline(base_scenes(), alignment(), fps=FPS)
        logo = _byid(tl)["logo"]
        self.assertEqual(logo["in_frame"], 0)
        self.assertEqual(logo["out_frame"], 30)  # 1.0s * 30
        # The next scene slides in immediately after (no gap).
        self.assertEqual(_byid(tl)["s1"]["in_frame"], 30)

    def test_unvoiced_default_hold_when_no_duration(self):
        scenes = base_scenes()
        del scenes[0]["duration_s"]  # force the 1.5s fallback
        tl = bt.build_timeline(scenes, alignment(), fps=FPS)
        logo = _byid(tl)["logo"]
        self.assertEqual(logo["out_frame"] - logo["in_frame"],
                         round(bt.DEFAULT_HOLD_S * FPS))


class TestCutScene(unittest.TestCase):
    def test_cut_scene_skipped_and_rest_slide_earlier(self):
        scenes = base_scenes()
        scenes[0]["cut"] = True  # cut the logo hold
        tl = bt.build_timeline(scenes, alignment(), fps=FPS)
        ids = [s["id"] for s in tl["scenes"]]
        self.assertNotIn("logo", ids)
        # s1 now starts at 0 (slid earlier into the freed slot), no dead air.
        self.assertEqual(_byid(tl)["s1"]["in_frame"], 0)

    def test_status_marker_also_cuts(self):
        scenes = base_scenes()
        scenes[1]["status"] = "declined"  # a middle scene declined at the gate
        tl = bt.build_timeline(scenes, alignment(), fps=FPS)
        ids = [s["id"] for s in tl["scenes"]]
        self.assertEqual(ids, ["logo", "s2"])
        # logo 0-30, then s2 slides right after it (no gap left by the cut s1).
        self.assertEqual(_byid(tl)["s2"]["in_frame"], 30)


class TestCueResolution(unittest.TestCase):
    def test_cue_by_word_and_by_index_land_inside_scene(self):
        tl = bt.build_timeline(base_scenes(), alignment(), fps=FPS)
        s1, s2 = _byid(tl)["s1"], _byid(tl)["s2"]
        cue1 = s1["cues"][0]
        self.assertEqual(cue1["label"], "hl")
        self.assertEqual(cue1["word"], "payments")
        self.assertTrue(s1["in_frame"] <= cue1["at_frame"] <= s1["out_frame"])
        cue2 = s2["cues"][0]
        self.assertEqual(cue2["word"], "keys")  # word_index 1 within s2's words
        self.assertTrue(s2["in_frame"] <= cue2["at_frame"] <= s2["out_frame"])

    def test_unresolvable_cue_is_dropped(self):
        scenes = base_scenes()
        scenes[1]["cues"] = [{"label": "ghost", "word": "nonexistent"}]
        tl = bt.build_timeline(scenes, alignment(), fps=FPS)
        self.assertEqual(_byid(tl)["s1"]["cues"], [])


class TestContiguity(unittest.TestCase):
    def _assert_contiguous(self, tl):
        scenes = tl["scenes"]
        self.assertEqual(scenes[0]["in_frame"], 0)
        for prev, nxt in zip(scenes, scenes[1:]):
            self.assertEqual(prev["out_frame"], nxt["in_frame"],
                             "gap or overlap between scenes")
            self.assertLess(prev["in_frame"], prev["out_frame"])
        # last scene clamped to total_frames
        self.assertEqual(scenes[-1]["out_frame"], tl["total_frames"])

    def test_contiguity_and_last_frame_clamp(self):
        tl = bt.build_timeline(base_scenes(), alignment(), fps=FPS)
        # Duration contract: total = sum of per-scene lengths (each = max(plan
        # duration_s, VO span)); with no target_duration_s there is no pad to the VO
        # total. logo hold 1.0s=30f + s1 span 1.5s=45f + s2 span 1.5s=45f = 120f.
        self.assertEqual(tl["total_frames"], 120)
        self._assert_contiguous(tl)

    def test_contiguity_holds_with_a_cut(self):
        scenes = base_scenes()
        scenes[0]["cut"] = True
        self._assert_contiguous(bt.build_timeline(scenes, alignment(), FPS))

    def test_scenes_dict_wrapper_accepted_via_core(self):
        # build_timeline takes a list; a {scenes:[...]} wrapper is unwrapped at the
        # CLI. Confirm the list path works on the same fixture.
        tl = bt.build_timeline(base_scenes(), alignment(), fps=FPS)
        self.assertEqual(len(tl["scenes"]), 3)


# ---------------------------------------------------------------------------
# DURATION ROBUSTNESS — pull a SPARSE plan up and a DENSE plan down toward target,
# spreading the change across scenes and NEVER cutting a VO span or a media clip.
# ---------------------------------------------------------------------------
def _sparse_alignment():
    """4 short voiced beats summing to ~12s of VO — a sparse plan that under-fills a
    30s target (mirrors the Super A/B run)."""
    words, beats = [], []
    t = 0.0
    for i in range(4):
        sid = f"s{i}"
        words.append({"word": f"w{i}", "start_s": t, "end_s": t + 3.0,
                      "beat_scene_id": sid})
        beats.append({"scene_id": sid, "start_s": t, "end_s": t + 3.0,
                      "text": f"beat {i}"})
        t += 3.0
    return {"audio_path": "vo.mp3", "lang": "en", "total_duration_s": t,
            "words": words, "beats": beats}


def _sparse_scenes():
    return [{"id": f"s{i}", "archetype": "kinetic", "type": "screenshot",
             "duration_s": 3.0} for i in range(4)]


def _dense_alignment():
    """4 long voiced beats summing to ~40s of VO — a dense plan that OVERRUNS a 30s
    target (mirrors, exaggerated, the Ultra A/B run)."""
    words, beats = [], []
    t = 0.0
    for i in range(4):
        sid = f"s{i}"
        words.append({"word": f"w{i}", "start_s": t, "end_s": t + 10.0,
                      "beat_scene_id": sid})
        beats.append({"scene_id": sid, "start_s": t, "end_s": t + 10.0,
                      "text": f"long beat {i}"})
        t += 10.0
    return {"audio_path": "vo.mp3", "lang": "en", "total_duration_s": t,
            "words": words, "beats": beats}


def _dense_scenes():
    return [{"id": f"s{i}", "archetype": "kinetic", "type": "screenshot",
             "duration_s": 6.0} for i in range(4)]


class TestDurationRobustness(unittest.TestCase):
    def test_sparse_plan_grows_to_target_spread_across_scenes(self):
        # A 4x3s=12s-VO plan must reach the 30s target...
        tl = bt.build_timeline(_sparse_scenes(), _sparse_alignment(), fps=FPS,
                               target_duration_s=30)
        self.assertEqual(tl["total_frames"], 30 * FPS)
        lengths = [s["out_frame"] - s["in_frame"] for s in tl["scenes"]]
        # ...and the growth is SPREAD, not dumped on one scene: every scene grew well
        # past its 3s VO span (no single staring close holding all the slack).
        for ln in lengths:
            self.assertGreater(ln, 3.5 * FPS, "a scene was left thin (deficit not spread)")
            self.assertLessEqual(ln, bt._SCENE_MAX_FRAMES, "a scene blew the per-scene cap")

    def test_sparse_grow_is_contiguous(self):
        tl = bt.build_timeline(_sparse_scenes(), _sparse_alignment(), fps=FPS,
                               target_duration_s=30)
        sc = tl["scenes"]
        self.assertEqual(sc[0]["in_frame"], 0)
        for prev, nxt in zip(sc, sc[1:]):
            self.assertEqual(prev["out_frame"], nxt["in_frame"])
        self.assertEqual(sc[-1]["out_frame"], tl["total_frames"])

    def test_dense_plan_never_cuts_vo_span(self):
        # A 4x10s=40s-VO plan overruns 30s. The VO floors ALONE exceed the ceiling, so
        # the film holds at its floor — VO is NEVER cut. Each scene >= its 10s span.
        tl = bt.build_timeline(_dense_scenes(), _dense_alignment(), fps=FPS,
                               target_duration_s=30)
        for s in tl["scenes"]:
            self.assertGreaterEqual(s["out_frame"] - s["in_frame"], 10 * FPS - 1,
                                    "a VO span was cut by the shrink")

    def test_dense_with_holds_shrinks_holds_to_floor(self):
        # Generous duration_s gives each window HOLD slack above its VO span; the
        # shrink removes that slack (never the VO) when the film overruns the ceiling.
        scenes = [{"id": f"s{i}", "archetype": "kinetic", "type": "screenshot",
                   "duration_s": 11.0} for i in range(4)]  # 11s hold > 10s VO span
        tl = bt.build_timeline(scenes, _dense_alignment(), fps=FPS,
                               target_duration_s=30)
        # Floors (4x10s=40s) > ceiling, so the shrink removes ALL hold slack (11->10s)
        # and stops at the floor — never below the VO.
        self.assertLessEqual(tl["total_frames"], 40 * FPS + 4)
        for s in tl["scenes"]:
            self.assertGreaterEqual(s["out_frame"] - s["in_frame"], 10 * FPS - 1)

    def test_apportion_never_loops_and_respects_caps(self):
        # Largest-remainder split: sums to min(amount, sum caps), never exceeds a cap.
        out = bt._apportion(100, [10, 20, 5])
        self.assertEqual(sum(out), 35)            # capped by total capacity
        self.assertTrue(all(o <= c for o, c in zip(out, [10, 20, 5])))
        out2 = bt._apportion(17, [10, 20, 5])
        self.assertEqual(sum(out2), 17)
        self.assertTrue(all(o <= c for o, c in zip(out2, [10, 20, 5])))
        self.assertEqual(bt._apportion(0, [1, 2]), [0, 0])
        self.assertEqual(bt._apportion(5, [0, 0]), [0, 0])


if __name__ == "__main__":
    unittest.main()
