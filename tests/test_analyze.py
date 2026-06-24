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


if __name__ == "__main__":
    unittest.main()
