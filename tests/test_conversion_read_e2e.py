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


class DeliveredLedgerCarriesRead(unittest.TestCase):
    """The clobber regression the FullRunSmoke tests above MISSED.

    Those tests stub orchestrate with a lambda that returns ({...}, None) WITHOUT
    writing a fresh ledger to disk — so the run-level `led` (which carries
    conversion_read) is never overwritten, and Ledger.load just re-reads it. The
    REAL orchestrate() mints a FRESH Ledger and writes it to the SAME
    runs/<id>/ledger.json, with NO conversion_read — clobbering the diagnosis from
    the DELIVERED record. The dashboard Analysis panel reads l.conversion_read ONLY
    from that delivered ledger (dashboard/app.js:772), so the panel renders empty on
    every finished run.

    These tests reproduce the clobber faithfully at $0: the orchestrate stub writes
    a fresh on-disk Ledger exactly like the real one, then we assert the DELIVERED
    ledger RE-LOADED FROM DISK carries conversion_read with the full 6-dim contract.
    Covered for BOTH render paths: VO-OFF (orchestrate is the last writer) and VO-ON
    (build_runner reloads as disk_led and re-writes — the 565 tail).
    """
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._prev_runs = build_runner.RUNS
        build_runner.RUNS = self._tmp.name
        self._saved = {}
        import plan_job, analyze
        self._saved["pk"] = plan_job.brain_mod.brain_key
        self._saved["ak"] = analyze.brain_mod.brain_key
        plan_job.brain_mod.brain_key = lambda: None       # no key -> $0 template plan
        analyze.brain_mod.brain_key = lambda: None
        self._saved["price"] = build_runner._price_plan
        self._saved["quote"] = build_runner._build_quote
        self._saved["gate"] = build_runner._payment_gate
        self._saved["orch"] = build_runner.orchestrator.orchestrate
        self._saved["vo_enabled"] = build_runner.vo_engine_enabled
        self._saved["vo_run"] = build_runner._run_vo_engine
        self._saved["facts"] = build_runner._brand_facts
        self._saved["read"] = build_runner._maybe_conversion_read
        self._saved["caps"] = build_runner._capture_screenshots_for_run
        build_runner._price_plan = lambda plan, run_dir: (500, "usd", {"menu": None})
        build_runner._build_quote = lambda est, currency="usd": None
        build_runner._payment_gate = lambda *a, **k: {"status": "paid", "price_cents": 500,
                                                      "currency": "usd"}
        build_runner._brand_facts = lambda url, rd: {"wordmark": "Acme", "tagline": "",
                                                     "features": ["a", "b", "c"]}
        build_runner._capture_screenshots_for_run = lambda url, rd: {"ok": False}

        # FAITHFUL orchestrate stub: mint a FRESH Ledger and WRITE it to the run's
        # ledger.json, exactly as orchestrator.orchestrate does — NO conversion_read.
        # This is the clobber. (Heavy production is skipped; the ledger write is the
        # only behavior this regression depends on.)
        import ledger as ledger_mod

        def _fake_orchestrate(plan, run_id, **k):
            run_dir = os.path.join(build_runner.RUNS, run_id)
            os.makedirs(run_dir, exist_ok=True)
            fresh = ledger_mod.Ledger(run_id, plan["job"], k.get("mode", "mock"),
                                      now=k.get("now"))
            fresh.set_status("delivered")
            fresh.set_phase("delivered")
            fresh.event("info", "DELIVERED — fresh production ledger (no conversion_read)")
            led_path = fresh.write(os.path.join(run_dir, "ledger.json"))
            return fresh.to_dict(), led_path

        build_runner.orchestrator.orchestrate = _fake_orchestrate

        # Deterministic, offline, FULL-contract Read (not the degraded minimal one) so
        # the assertions exercise the real 6-dim shape.
        def _fake_maybe(url, run_dir, brain="super-free", read_pass_fn=None, analyze_fn=None):
            if not build_runner.conversion_read_enabled():
                return None
            import analyze as _a
            dims = [{"key": kk, "score": 3, "finding": "f", "evidence": "e", "fix": "x"}
                    for kk in _a.DIMENSION_KEYS]
            read = {"url": url, "verdict": "Lead with the outcome.", "dimensions": dims,
                    "priority_fixes": [{"rank": 1, "fix": "add proof", "maps_to": "proof"}],
                    "headline_fix": "Ship 10x faster.", "degraded": False}
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
        build_runner.vo_engine_enabled = self._saved["vo_enabled"]
        build_runner._run_vo_engine = self._saved["vo_run"]
        build_runner._brand_facts = self._saved["facts"]
        build_runner._maybe_conversion_read = self._saved["read"]
        build_runner._capture_screenshots_for_run = self._saved["caps"]
        os.environ.pop("PRODUCER_CONVERSION_READ", None)
        os.environ.pop("WS_VO_ENGINE", None)
        self._tmp.cleanup()

    def _assert_delivered_ledger_carries_read(self, run_id):
        """The contract the dashboard depends on: the DELIVERED on-disk ledger,
        RE-LOADED FROM DISK, carries conversion_read with all 6 dimensions + the
        'analyzing' event in run history."""
        import ledger as ledger_mod
        import analyze
        run_dir = os.path.join(build_runner.RUNS, run_id)
        led_path = os.path.join(run_dir, "ledger.json")
        led = ledger_mod.Ledger.load(led_path)   # exactly what dashboard data comes from
        # status must still be the delivered production record (not clobbered to a stub)
        self.assertEqual(led.data.get("status"), "delivered")
        cr = led.data.get("conversion_read")
        self.assertIsInstance(cr, dict,
                              "DELIVERED ledger lost conversion_read -> Analysis panel renders empty")
        self.assertEqual([], analyze.validate_read(cr),
                         "delivered conversion_read must satisfy the 6-dim contract")
        keys = sorted(d.get("key") for d in cr.get("dimensions", []))
        self.assertEqual(sorted(analyze.DIMENSION_KEYS), keys)
        msgs = " ".join(e.get("msg", "") for e in led.data.get("events", [])).lower()
        self.assertIn("analyzing", msgs,
                      "run history lost the 'analyzing' event on the delivered ledger")

    def test_delivered_ledger_carries_read_vo_off(self):
        os.environ["PRODUCER_CONVERSION_READ"] = "1"
        os.environ["WS_VO_ENGINE"] = "0"   # VO-OFF: orchestrate is the LAST disk writer
        build_runner.vo_engine_enabled = lambda: False
        build_runner.run("https://acme.com", "promo", "build-acme-read-vooff",
                         mode="mock", target_duration=30)
        self._assert_delivered_ledger_carries_read("build-acme-read-vooff")

    def test_delivered_ledger_carries_read_vo_on(self):
        os.environ["PRODUCER_CONVERSION_READ"] = "1"
        os.environ["WS_VO_ENGINE"] = "1"   # VO-ON: build_runner reloads disk_led (the 565 tail)
        build_runner.vo_engine_enabled = lambda: True
        build_runner._run_vo_engine = lambda plan, run_id, url, run_dir: None  # skip Remotion
        build_runner.run("https://acme.com", "promo", "build-acme-read-voon",
                         mode="mock", target_duration=30)
        self._assert_delivered_ledger_carries_read("build-acme-read-voon")


if __name__ == "__main__":
    unittest.main()
