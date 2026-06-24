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
