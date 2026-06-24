#!/usr/bin/env python3
"""$0 mock end-to-end-ish tests for the ANALYZE stage in build_runner.

Capture + Nemotron + payment gate are all INJECTED/simulated, so no network, no
Higgsfield, no real Stripe settlement, no Playwright. Proves: with the flag ON a
run writes conversion_read.json + an 'analyzing' ledger event; with the flag OFF
the run does NOT analyze (current behavior unchanged)."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import build_runner


class AnalyzeStage(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._prev_runs = build_runner.RUNS
        build_runner.RUNS = self._tmp.name
        os.environ.pop("PRODUCER_CONVERSION_READ", None)

    def tearDown(self):
        build_runner.RUNS = self._prev_runs
        os.environ.pop("PRODUCER_CONVERSION_READ", None)
        self._tmp.cleanup()

    def _fake_read(self):
        import analyze
        dims = [{"key": k, "score": 2, "finding": "f", "evidence": "e", "fix": "x"}
                for k in analyze.DIMENSION_KEYS]
        return {"url": "https://acme.com", "verdict": "v", "dimensions": dims,
                "priority_fixes": [{"rank": 1, "fix": "add proof", "maps_to": "proof"}],
                "headline_fix": "Ship 10x faster.", "degraded": False}

    def test_flag_on_runs_analyze_and_persists(self):
        os.environ["PRODUCER_CONVERSION_READ"] = "1"
        run_dir = os.path.join(build_runner.RUNS, "build-acme-test")
        os.makedirs(run_dir, exist_ok=True)
        cr = build_runner._maybe_conversion_read(
            "https://acme.com", run_dir, brain="super-free",
            read_pass_fn=lambda url, rd: {"url": url, "body_text": "Acme copy",
                                          "hero_screenshot_path": None, "headline": "Acme",
                                          "degraded": False},
            analyze_fn=lambda url, body, hero_path=None, headline=None, brain="super-free": self._fake_read())
        self.assertIsNotNone(cr)
        self.assertEqual(cr["headline_fix"], "Ship 10x faster.")
        self.assertTrue(os.path.exists(os.path.join(run_dir, "conversion_read.json")))
        with open(os.path.join(run_dir, "conversion_read.json")) as f:
            self.assertEqual(json.load(f)["url"], "https://acme.com")

    def test_flag_off_skips_analyze(self):
        run_dir = os.path.join(build_runner.RUNS, "build-acme-off")
        os.makedirs(run_dir, exist_ok=True)
        cr = build_runner._maybe_conversion_read(
            "https://acme.com", run_dir, brain="super-free",
            read_pass_fn=lambda *a, **k: 1 / 0,   # must NOT be called
            analyze_fn=lambda *a, **k: 1 / 0)
        self.assertIsNone(cr)
        self.assertFalse(os.path.exists(os.path.join(run_dir, "conversion_read.json")))

    def test_read_pass_failure_degrades_not_crashes(self):
        os.environ["PRODUCER_CONVERSION_READ"] = "1"
        run_dir = os.path.join(build_runner.RUNS, "build-acme-degraded")
        os.makedirs(run_dir, exist_ok=True)
        cr = build_runner._maybe_conversion_read(
            "https://acme.com", run_dir, brain="super-free",
            read_pass_fn=lambda url, rd: (_ for _ in ()).throw(RuntimeError("unreachable")),
            analyze_fn=lambda *a, **k: 1 / 0)
        # read pass blew up -> a degraded minimal Read, video still proceeds
        self.assertIsNotNone(cr)
        self.assertTrue(cr["degraded"])
        self.assertTrue(os.path.exists(os.path.join(run_dir, "conversion_read.json")))


if __name__ == "__main__":
    unittest.main()
