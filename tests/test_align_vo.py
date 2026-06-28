#!/usr/bin/env python3
"""Unit tests for align_vo.py -- the VO word-alignment module (Phase 1, mod 1).

$0 -- the fast suite NEVER synthesizes audio or runs whisper. It exercises the
word->beat SEQUENCE mapping, the whisper JSON parser, and the ElevenLabs
char-grouping parser with INJECTED fakes (synth_fn + whisper_fn seams on
align_vo.align). A real edge-tts + whisper end-to-end smoke is included but
guarded behind ALIGN_VO_SMOKE=1 so it is not wired into ./run_all_tests.sh.

Run fast suite:   python3 -m unittest tests.test_align_vo -v
Run real smoke:   ALIGN_VO_SMOKE=1 python3 -m unittest tests.test_align_vo.RealSmoke -v
"""
import json
import os
import tempfile
import unittest

import align_vo


def _fake_synth(script, voice, out_path, provider):
    """Stand-in for adapters.synthesize_voiceover: writes a tiny dummy file."""
    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    with open(out_path, "wb") as f:
        f.write(b"\x00" * 600)  # >500 bytes so any size guard would pass
    return {"output_path": out_path, "provider": "edge-tts",
            "voice": "en-US-AndrewNeural", "real": False}


def _whisper_returning(words):
    """Build an injectable whisper_fn that returns a fixed hypothesis word list."""
    def _fn(audio_path):
        return [dict(w) for w in words]
    return _fn


class TestBuildWordIndex(unittest.TestCase):
    def test_owners_track_scene_ranges(self):
        beats = [{"scene_id": "a", "text": "one two"},
                 {"scene_id": "b", "text": "three four five"}]
        owners, toks, clean = align_vo.build_word_index(beats)
        self.assertEqual(owners, ["a", "a", "b", "b", "b"])
        self.assertEqual(toks, ["one", "two", "three", "four", "five"])
        self.assertEqual([b["scene_id"] for b in clean], ["a", "b"])

    def test_blank_and_idless_beats_dropped(self):
        beats = [{"scene_id": "a", "text": "  "},
                 {"scene_id": "", "text": "x"},
                 {"scene_id": "b", "text": "hello"}]
        owners, toks, clean = align_vo.build_word_index(beats)
        self.assertEqual(owners, ["b"])
        self.assertEqual([b["scene_id"] for b in clean], ["b"])


class TestMapping(unittest.TestCase):
    def _align(self, beats, hyp_words):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "vo_alignment.json")
            return align_vo.align(
                beats, out, tier="free", synth_fn=_fake_synth,
                whisper_fn=_whisper_returning(hyp_words))

    def test_clean_mapping(self):
        beats = [{"scene_id": "s1", "text": "Stripe powers checkout"},
                 {"scene_id": "s2", "text": "Build faster today"}]
        hyp = [{"word": w, "start_s": i * 0.5, "end_s": i * 0.5 + 0.4}
               for i, w in enumerate(
                   ["Stripe", "powers", "checkout", "Build", "faster", "today"])]
        res = self._align(beats, hyp)
        got = [w["beat_scene_id"] for w in res["words"]]
        self.assertEqual(got, ["s1", "s1", "s1", "s2", "s2", "s2"])
        self.assertEqual(res["tier"], "free")
        self.assertEqual([b["scene_id"] for b in res["beats"]], ["s1", "s2"])

    def test_tokenization_drift_mishear_and_split(self):
        # whisper mishears 'Stripe'->'Strike' and SPLITS 'checkout'->'check out'
        # (one extra hypothesis word) and the second beat is fine.
        beats = [{"scene_id": "s1", "text": "Stripe powers checkout"},
                 {"scene_id": "s2", "text": "Ship it"}]
        hyp = [
            {"word": "Strike", "start_s": 0.2, "end_s": 0.4},
            {"word": "powers", "start_s": 0.4, "end_s": 0.8},
            {"word": "check", "start_s": 0.8, "end_s": 1.1},
            {"word": "out", "start_s": 1.1, "end_s": 1.4},   # extra/split word
            {"word": "Ship", "start_s": 1.6, "end_s": 1.9},
            {"word": "it", "start_s": 1.9, "end_s": 2.1},
        ]
        res = self._align(beats, hyp)
        got = [w["beat_scene_id"] for w in res["words"]]
        # The first 4 words all belong to s1, the last 2 to s2 -- the extra
        # 'out' must NOT bleed into s2.
        self.assertEqual(got, ["s1", "s1", "s1", "s1", "s2", "s2"])

    def test_beat_with_no_words(self):
        # A middle beat that whisper never produced words for (e.g. dropped /
        # fully misaligned) must still appear in beats with null spans, and no
        # word should be attributed to it.
        beats = [{"scene_id": "s1", "text": "alpha beta"},
                 {"scene_id": "s2", "text": "gamma delta"},
                 {"scene_id": "s3", "text": "epsilon zeta"}]
        # Hypothesis skips s2 entirely (only s1 + s3 words present).
        hyp = [
            {"word": "alpha", "start_s": 0.0, "end_s": 0.3},
            {"word": "beta", "start_s": 0.3, "end_s": 0.6},
            {"word": "epsilon", "start_s": 0.7, "end_s": 1.0},
            {"word": "zeta", "start_s": 1.0, "end_s": 1.3},
        ]
        res = self._align(beats, hyp)
        scenes = {b["scene_id"]: b for b in res["beats"]}
        self.assertEqual(len(res["beats"]), 3)
        self.assertIsNone(scenes["s2"]["start_s"])
        self.assertIsNone(scenes["s2"]["end_s"])
        self.assertNotIn("s2", [w["beat_scene_id"] for w in res["words"]])
        # s1 + s3 still got real spans.
        self.assertIsNotNone(scenes["s1"]["start_s"])
        self.assertIsNotNone(scenes["s3"]["end_s"])

    def test_contract_shape_and_audio_relocation(self):
        beats = [{"scene_id": "s1", "text": "hello world"}]
        hyp = [{"word": "hello", "start_s": 0.0, "end_s": 0.4},
               {"word": "world", "start_s": 0.4, "end_s": 0.9}]
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "vo_alignment.json")
            res = align_vo.align(beats, out, tier="free", lang="en",
                                 synth_fn=_fake_synth,
                                 whisper_fn=_whisper_returning(hyp))
            self.assertEqual(set(res.keys()), {
                "audio_path", "lang", "voice", "tier", "total_duration_s",
                "words", "beats",
                # VO engine provenance (run artifact; safe re: plan allowed_top).
                "vo_engine", "vo_fallback", "vo_fallback_reason"})
            # With no ElevenLabs key (the test injects synth_fn) the free path
            # runs and is recorded as a fallback from the ElevenLabs default.
            self.assertEqual(res["vo_engine"], "edge-tts")
            self.assertTrue(res["vo_fallback"])
            # audio relocated to voiceover.mp3 beside the alignment json.
            self.assertTrue(res["audio_path"].endswith("voiceover.mp3"))
            self.assertTrue(os.path.exists(res["audio_path"]))
            self.assertAlmostEqual(res["total_duration_s"], 0.9, places=3)
            for w in res["words"]:
                self.assertEqual(set(w.keys()),
                                 {"word", "start_s", "end_s", "beat_scene_id"})
            for b in res["beats"]:
                self.assertEqual(set(b.keys()),
                                 {"scene_id", "start_s", "end_s", "text"})


class TestElevenLabsDefaultAndFallback(unittest.TestCase):
    def test_no_key_falls_back_to_free_and_records_engine(self):
        # ElevenLabs is the DEFAULT for every video, but with no key the render
        # must AUTO-FALL-BACK to free edge-tts + whisper and record that it did.
        beats = [{"scene_id": "s1", "text": "default please"}]
        hyp = [{"word": "default", "start_s": 0.0, "end_s": 0.5},
               {"word": "please", "start_s": 0.5, "end_s": 1.0}]
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "vo_alignment.json")
            old = os.environ.pop("ELEVENLABS_API_KEY", None)
            try:
                res = align_vo.align(
                    beats, out, tier="free", synth_fn=_fake_synth,
                    whisper_fn=_whisper_returning(hyp), elevenlabs_key=None)
            finally:
                if old is not None:
                    os.environ["ELEVENLABS_API_KEY"] = old
            self.assertEqual(res["vo_engine"], "edge-tts")
            self.assertTrue(res["vo_fallback"])
            self.assertIsNotNone(res["vo_fallback_reason"])

    def test_explicit_free_provider_is_not_a_fallback(self):
        # WS_VO_PROVIDER=edge is an explicit opt-out, NOT a fallback: the free
        # engine was requested, so vo_fallback must be False.
        beats = [{"scene_id": "s1", "text": "free on purpose"}]
        hyp = [{"word": "free", "start_s": 0.0, "end_s": 0.3},
               {"word": "on", "start_s": 0.3, "end_s": 0.5},
               {"word": "purpose", "start_s": 0.5, "end_s": 0.9}]
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "vo_alignment.json")
            old_prov = os.environ.get("WS_VO_PROVIDER")
            os.environ["WS_VO_PROVIDER"] = "edge"
            try:
                res = align_vo.align(
                    beats, out, tier="free", synth_fn=_fake_synth,
                    whisper_fn=_whisper_returning(hyp), elevenlabs_key=None)
            finally:
                if old_prov is None:
                    os.environ.pop("WS_VO_PROVIDER", None)
                else:
                    os.environ["WS_VO_PROVIDER"] = old_prov
            self.assertEqual(res["vo_engine"], "edge-tts")
            self.assertFalse(res["vo_fallback"])
            self.assertIsNone(res["vo_fallback_reason"])

    def test_elevenlabs_synth_is_shape_only_never_spends(self):
        # The ElevenLabs synth makes a REAL HTTP call; with a bogus key it must
        # raise AlignError (so synth_full_script catches it and falls back) and
        # never silently succeed/spend.
        with self.assertRaises(align_vo.AlignError):
            align_vo._elevenlabs_synth_with_timestamps(
                "x", "Adam", "/tmp/none.mp3", "FAKE_KEY")


class TestParsers(unittest.TestCase):
    def test_parse_whisper_json(self):
        data = {"transcription": [
            {"text": "", "offsets": {"from": 0, "to": 240}},      # leading blank
            {"text": " Stripe", "offsets": {"from": 240, "to": 390}},
            {"text": " powers", "offsets": {"from": 390, "to": 780}},
        ]}
        words = align_vo.parse_whisper_json(data)
        self.assertEqual([w["word"] for w in words], ["Stripe", "powers"])
        self.assertAlmostEqual(words[0]["start_s"], 0.24, places=3)
        self.assertAlmostEqual(words[0]["end_s"], 0.39, places=3)

    def test_parse_elevenlabs_alignment_groups_on_whitespace(self):
        alignment = {
            "characters": list("Hi there"),
            "character_start_times_seconds":
                [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7],
            "character_end_times_seconds":
                [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8],
        }
        words = align_vo.parse_elevenlabs_alignment(alignment)
        self.assertEqual([w["word"] for w in words], ["Hi", "there"])
        self.assertAlmostEqual(words[0]["start_s"], 0.0, places=3)
        self.assertAlmostEqual(words[0]["end_s"], 0.2, places=3)
        self.assertAlmostEqual(words[1]["start_s"], 0.3, places=3)
        self.assertAlmostEqual(words[1]["end_s"], 0.8, places=3)


@unittest.skipUnless(os.environ.get("ALIGN_VO_SMOKE") == "1",
                     "real edge-tts + whisper smoke (set ALIGN_VO_SMOKE=1)")
class RealSmoke(unittest.TestCase):
    def test_one_sentence_end_to_end(self):
        beats = [{"scene_id": "open", "text": "Stripe powers checkout for many companies."}]
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "vo_alignment.json")
            res = align_vo.align(beats, out, tier="free")
            self.assertTrue(os.path.exists(res["audio_path"]))
            self.assertGreater(res["total_duration_s"], 0.5)
            self.assertGreater(len(res["words"]), 3)
            # Every word maps to the single scene.
            self.assertTrue(all(w["beat_scene_id"] == "open" for w in res["words"]))


if __name__ == "__main__":
    unittest.main()
