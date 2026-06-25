#!/usr/bin/env python3
"""$0, offline unit tests for analyze.py (no network, no Nemotron call)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import analyze


def _good_read():
    dims = [{"key": k, "score": 3, "finding": "f", "evidence": "e", "fix": "x"}
            for k in analyze.DIMENSION_KEYS]
    return {
        "url": "https://acme.com",
        "verdict": "feature-led hero, thin proof",
        "dimensions": dims,
        "priority_fixes": [{"rank": 1, "fix": "add a proof beat", "maps_to": "proof"}],
        "headline_fix": "Ship 10x faster",
    }


class ValidateRead(unittest.TestCase):
    def test_good_read_has_no_problems(self):
        self.assertEqual(analyze.validate_read(_good_read()), [])

    def test_missing_dimension_is_flagged(self):
        r = _good_read()
        r["dimensions"] = r["dimensions"][:5]  # drop cta
        problems = analyze.validate_read(r)
        self.assertTrue(any("cta" in p for p in problems), problems)

    def test_score_out_of_range_is_flagged(self):
        r = _good_read()
        r["dimensions"][0]["score"] = 9
        self.assertTrue(analyze.validate_read(r))

    def test_missing_headline_fix_is_flagged(self):
        r = _good_read()
        del r["headline_fix"]
        self.assertTrue(analyze.validate_read(r))


class MinimalRead(unittest.TestCase):
    def test_minimal_read_is_valid(self):
        r = analyze.minimal_read("https://acme.com", body_text="Acme builds widgets.")
        self.assertEqual(analyze.validate_read(r), [])

    def test_minimal_read_is_marked_degraded(self):
        r = analyze.minimal_read("https://acme.com", body_text="")
        self.assertTrue(r["degraded"])

    def test_minimal_read_carries_url(self):
        r = analyze.minimal_read("https://acme.com", body_text="x")
        self.assertEqual(r["url"], "https://acme.com")


class AnalyzeRead(unittest.TestCase):
    def setUp(self):
        self._orig_call = analyze.vp.call_model
        self._orig_key = analyze.brain_mod.brain_key

    def tearDown(self):
        analyze.vp.call_model = self._orig_call
        analyze.brain_mod.brain_key = self._orig_key

    def _good_json(self):
        dims = [{"key": k, "score": 2, "finding": "f", "evidence": "e", "fix": "x"}
                for k in analyze.DIMENSION_KEYS]
        return analyze.json.dumps({
            "url": "https://acme.com", "verdict": "v", "dimensions": dims,
            "priority_fixes": [{"rank": 1, "fix": "add proof", "maps_to": "proof"}],
            "headline_fix": "Ship 10x faster"})

    def test_valid_model_output_is_returned(self):
        analyze.brain_mod.brain_key = lambda: "k"
        analyze.vp.call_model = lambda messages, brain=None, meta=None: self._good_json()
        r = analyze.analyze_read("https://acme.com", "Acme copy", hero_path=None)
        self.assertEqual(analyze.validate_read(r), [])
        self.assertFalse(r.get("degraded"))

    def test_malformed_then_minimal(self):
        analyze.brain_mod.brain_key = lambda: "k"
        analyze.vp.call_model = lambda messages, brain=None, meta=None: "I cannot help with that."
        r = analyze.analyze_read("https://acme.com", "Acme copy", hero_path=None)
        self.assertEqual(analyze.validate_read(r), [])  # still valid (minimal)
        self.assertTrue(r["degraded"])

    def test_no_key_returns_minimal(self):
        analyze.brain_mod.brain_key = lambda: None
        called = []
        analyze.vp.call_model = lambda *a, **k: called.append(1) or "{}"
        r = analyze.analyze_read("https://acme.com", "Acme copy", hero_path=None)
        self.assertTrue(r["degraded"])
        self.assertEqual(called, [])  # never hit the network without a key

    def test_url_is_forced_onto_read(self):
        analyze.brain_mod.brain_key = lambda: "k"
        analyze.vp.call_model = lambda messages, brain=None, meta=None: self._good_json()
        r = analyze.analyze_read("https://other.com", "copy", hero_path=None)
        self.assertEqual(r["url"], "https://other.com")  # model's url is overwritten


class TieredFallbackAndEngineTag(unittest.TestCase):
    """The Conversion Read keeps Hermes as the honest primary but stays RELIABLE:
    429s on the free Hermes tier are retried after a short backoff, and if Hermes
    ultimately fails we fall to Nemotron Ultra BEFORE the bare minimal_read. Every
    Read is tagged read["engine"] with the model that actually produced it."""

    def setUp(self):
        self._orig_call = analyze.vp.call_model
        self._orig_key = analyze.brain_mod.brain_key
        self._orig_sleep = analyze.time.sleep
        analyze.brain_mod.brain_key = lambda: "k"
        analyze.time.sleep = lambda s: self._slept.append(s)  # never really wait
        self._slept = []

    def tearDown(self):
        analyze.vp.call_model = self._orig_call
        analyze.brain_mod.brain_key = self._orig_key
        analyze.time.sleep = self._orig_sleep

    def _good_json(self):
        dims = [{"key": k, "score": 2, "finding": "f", "evidence": "e", "fix": "x"}
                for k in analyze.DIMENSION_KEYS]
        return analyze.json.dumps({
            "url": "https://acme.com", "verdict": "v", "dimensions": dims,
            "priority_fixes": [{"rank": 1, "fix": "add proof", "maps_to": "proof"}],
            "headline_fix": "Ship 10x faster"})

    def _http_429(self):
        import urllib.error
        return urllib.error.HTTPError("u", 429, "Too Many Requests", {}, None)

    def test_hermes_success_tags_hermes_engine(self):
        analyze.vp.call_model = lambda messages, brain=None, meta=None: self._good_json()
        r = analyze.analyze_read("https://acme.com", "copy")
        self.assertFalse(r.get("degraded"))
        self.assertEqual(r["engine"], "nous-hermes-3-405b")

    def test_429_then_success_retries_same_brain_no_fallback(self):
        calls = {"n": 0}

        def call(messages, brain=None, meta=None):
            calls["n"] += 1
            if calls["n"] == 1:
                raise self._http_429()
            self.assertEqual(brain, "hermes")  # retried the SAME brain, not Ultra
            return self._good_json()

        analyze.vp.call_model = call
        r = analyze.analyze_read("https://acme.com", "copy")
        self.assertEqual(r["engine"], "nous-hermes-3-405b")  # Hermes still produced it
        self.assertEqual(len(self._slept), 1)  # backed off once

    def test_hermes_exhausted_falls_to_ultra(self):
        seen = []

        def call(messages, brain=None, meta=None):
            seen.append(brain)
            if brain == "hermes":
                raise self._http_429()  # never recovers within backoff budget
            return self._good_json()    # Ultra succeeds

        analyze.vp.call_model = call
        r = analyze.analyze_read("https://acme.com", "copy")
        self.assertFalse(r.get("degraded"))
        self.assertEqual(r["engine"], "nemotron-ultra-fallback")
        self.assertIn("ultra-paid", seen)  # the fallback brain was actually called

    def test_both_fail_falls_to_minimal_tagged(self):
        analyze.vp.call_model = lambda messages, brain=None, meta=None: "I cannot help."
        r = analyze.analyze_read("https://acme.com", "copy")
        self.assertTrue(r["degraded"])
        self.assertEqual(r["engine"], "minimal")

    def test_minimal_read_is_tagged_minimal(self):
        r = analyze.minimal_read("https://acme.com", "copy")
        self.assertEqual(r["engine"], "minimal")


class AnalyzerPromptDoc(unittest.TestCase):
    def test_doc_exists_and_lists_all_dimensions(self):
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        path = os.path.join(here, "analyzer-prompt.md")
        self.assertTrue(os.path.exists(path), "analyzer-prompt.md missing")
        with open(path) as f:
            doc = f.read()
        for k in analyze.DIMENSION_KEYS:
            self.assertIn(k, doc, "dimension %r not documented" % k)
        for field in ("headline_fix", "priority_fixes", "verdict"):
            self.assertIn(field, doc)


if __name__ == "__main__":
    unittest.main()
