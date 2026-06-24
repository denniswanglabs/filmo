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


class FullRunSmoke(unittest.TestCase):
    """Drive build_runner.run() end-to-end at $0: every external boundary is stubbed
    (plan = template via no key, payment = simulated, production = stubbed). Proves
    the analyzing ledger event + conversion_read.json are present on a real run() with
    the flag ON, and absent with it OFF -- the demo's $0 parity."""
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._prev_runs = build_runner.RUNS
        build_runner.RUNS = self._tmp.name
        self._saved = {}
        # No OpenRouter key -> planner uses the deterministic template ($0).
        import plan_job, analyze
        self._saved["pk"] = plan_job.brain_mod.brain_key
        self._saved["ak"] = analyze.brain_mod.brain_key
        plan_job.brain_mod.brain_key = lambda: None
        analyze.brain_mod.brain_key = lambda: None
        # Stub the heavy boundaries: pricing, payment gate, orchestrate, VO engine.
        self._saved["price"] = build_runner._price_plan
        self._saved["quote"] = build_runner._build_quote
        self._saved["gate"] = build_runner._payment_gate
        self._saved["orch"] = build_runner.orchestrator.orchestrate
        self._saved["vo"] = build_runner.vo_engine_enabled
        self._saved["facts"] = build_runner._brand_facts
        self._saved["read"] = build_runner._maybe_conversion_read
        build_runner._price_plan = lambda plan, run_dir: (500, "usd", {"menu": None})
        build_runner._build_quote = lambda est, currency="usd": None
        build_runner._payment_gate = lambda *a, **k: {"status": "paid", "price_cents": 500,
                                                      "currency": "usd"}
        build_runner.orchestrator.orchestrate = lambda plan, run_id, **k: ({"status": "delivered"}, None)
        build_runner.vo_engine_enabled = lambda: False
        build_runner._brand_facts = lambda url, rd: {"wordmark": "Acme", "tagline": "", "features": ["a", "b", "c"]}
        # Keep analyze offline/deterministic in the staged helper.
        def _fake_maybe(url, run_dir, brain="super-free", read_pass_fn=None, analyze_fn=None):
            if not build_runner.conversion_read_enabled():
                return None
            import analyze as _a
            read = _a.minimal_read(url, "Acme copy")
            with open(os.path.join(run_dir, "conversion_read.json"), "w") as f:
                json.dump(read, f, indent=2)
            return read
        build_runner._maybe_conversion_read = _fake_maybe

    def tearDown(self):
        build_runner.RUNS = self._prev_runs
        import plan_job, analyze
        plan_job.brain_mod.brain_key = self._saved["pk"]
        analyze.brain_mod.brain_key = self._saved["ak"]
        build_runner._price_plan = self._saved["price"]
        build_runner._build_quote = self._saved["quote"]
        build_runner._payment_gate = self._saved["gate"]
        build_runner.orchestrator.orchestrate = self._saved["orch"]
        build_runner.vo_engine_enabled = self._saved["vo"]
        build_runner._brand_facts = self._saved["facts"]
        build_runner._maybe_conversion_read = self._saved["read"]
        os.environ.pop("PRODUCER_CONVERSION_READ", None)
        self._tmp.cleanup()

    def test_flag_on_run_has_analyzing_event_and_read_file(self):
        os.environ["PRODUCER_CONVERSION_READ"] = "1"
        build_runner.run("https://acme.com", "promo", "build-acme-on", mode="mock",
                         target_duration=30)
        run_dir = os.path.join(build_runner.RUNS, "build-acme-on")
        self.assertTrue(os.path.exists(os.path.join(run_dir, "conversion_read.json")))
        import ledger as ledger_mod
        led = ledger_mod.Ledger.load(os.path.join(run_dir, "ledger.json"))
        msgs = " ".join(e.get("msg", "") for e in led.data["events"])
        self.assertIn("analyzing", msgs.lower())
        self.assertIsInstance(led.data.get("conversion_read"), dict)

    def test_flag_off_run_has_no_read(self):
        build_runner.run("https://acme.com", "promo", "build-acme-off2", mode="mock",
                         target_duration=30)
        run_dir = os.path.join(build_runner.RUNS, "build-acme-off2")
        self.assertFalse(os.path.exists(os.path.join(run_dir, "conversion_read.json")))
        import ledger as ledger_mod
        led = ledger_mod.Ledger.load(os.path.join(run_dir, "ledger.json"))
        self.assertIsNone(led.data.get("conversion_read"))


if __name__ == "__main__":
    unittest.main()
