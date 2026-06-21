#!/usr/bin/env python3
"""Unit tests for the post-payment failure handler in build_runner.py.

$0 — NO real build, NO Higgsfield/Stripe/ElevenLabs calls. Exercises
`build_runner._record_failure` + `ledger.Ledger.load` against synthetic failed
runs to prove that a post-payment production failure KEEPS the paid record
(earn/pricing/plan/scenes) instead of clobbering it — the build-orinovate-edf804
bug where the except handler wrote a fresh Ledger and left earn=null despite a
confirmed payment. Also proves runs/index.json is refreshed on failure.

Run: python3 -m unittest tests.test_build_runner_failure
"""

import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import build_runner  # noqa: E402
import ledger as ledger_mod  # noqa: E402

JOB = {"company_url": "https://orinovate.com", "goal": "promo", "currency": "usd"}
PAID_EARN = {
    "enabled": True, "provider": "stripe", "mode": "test", "status": "paid",
    "session_id": "cs_test_abc123", "price_cents": 4200, "currency": "usd",
    "payment_status": "paid",
}
PRICING = {"suggested_price_cents": 4200, "currency": "usd"}
PLAN = {"voiceover": {"script": "hello", "voice": "adam"},
        "scenes": [{"id": "cinematic-motion", "type": "cinematic", "model": "seedance_2_0"}]}
SCENES = [{"id": "00_opening-title", "type": "title", "decision": "approve", "spent_cents": 0},
          {"id": "cinematic-motion", "type": "cinematic", "decision": "approve", "spent_cents": 22}]


def _run_led(run_id="build-x"):
    """The in-memory run-level ledger as it stands after planning + the paid gate
    (earn/pricing/plan populated; no scenes — those are added by orchestrate)."""
    led = ledger_mod.Ledger(run_id, JOB, "real")
    led.data["plan"] = PLAN
    led.set_pricing(PRICING)
    led.set_earn(PAID_EARN)
    led.set_status("running")
    led.set_phase("producing")
    led.event("money", "payment received — $42.00")
    return led


class _TempRuns:
    """Point build_runner.RUNS at a temp dir for the duration of a test so the
    on-failure index refresh scans the synthetic run, not the real runs/ dir."""

    def __enter__(self):
        self._d = tempfile.TemporaryDirectory()
        self._prev = build_runner.RUNS
        build_runner.RUNS = self._d.name
        return self._d.name

    def __exit__(self, *a):
        build_runner.RUNS = self._prev
        self._d.cleanup()


def _led_path(runs_dir, run_id):
    return os.path.join(runs_dir, run_id, "ledger.json")


def _read(path):
    with open(path) as f:
        return json.load(f)


class TestRecordFailure(unittest.TestCase):
    def test_preserves_paid_record_from_disk(self):
        """The real bug: orchestrate already wrote a rich ledger (earn + scenes) to
        disk during production. A production-side raise must keep it."""
        with _TempRuns() as runs_dir:
            run_id = "build-disk"
            led_path = _led_path(runs_dir, run_id)
            # Disk state as orchestrate left it mid-production: earn carried in, plan,
            # two produced scenes, its own event timeline.
            disk = ledger_mod.Ledger(run_id, JOB, "real")
            disk.data["plan"] = PLAN
            disk.set_pricing(PRICING)
            disk.set_earn(PAID_EARN)
            for s in SCENES:
                disk.add_scene(s)
            disk.set_status("running")
            disk.set_phase("producing")
            disk.event("info", "producing scene cinematic-motion")
            disk.write(led_path)

            build_runner._record_failure(
                led_path, _run_led(run_id), run_id, JOB, "real",
                RuntimeError("could not parse higgsfield job id for scene 'cinematic-motion'"))

            d = _read(led_path)
            self.assertEqual(d["status"], "failed")
            self.assertEqual(d["phase"], "failed")
            # PAID RECORD PRESERVED (the whole point):
            self.assertEqual(d["earn"], PAID_EARN)
            self.assertEqual(d["earn"]["payment_status"], "paid")
            self.assertEqual(d["pricing"], PRICING)
            self.assertEqual(d["plan"], PLAN)
            self.assertEqual(len(d["scenes"]), 2)
            # Error event appended, carrying the real message, with a non-colliding seq.
            errs = [e for e in d["events"] if e["level"] == "error"]
            self.assertTrue(errs and errs[-1]["msg"].startswith("build failed: could not parse"))
            seqs = [e["seq"] for e in d["events"]]
            self.assertEqual(len(seqs), len(set(seqs)), "event seq numbers must be unique")
            self.assertEqual(seqs, sorted(seqs))

    def test_refreshes_index_on_failure(self):
        with _TempRuns() as runs_dir:
            run_id = "build-idx"
            led_path = _led_path(runs_dir, run_id)
            _run_led(run_id).write(led_path)  # a 'running' ledger on disk
            build_runner._record_failure(led_path, _run_led(run_id), run_id, JOB, "real",
                                         RuntimeError("boom"))
            idx = _read(os.path.join(runs_dir, "index.json"))
            row = next(r for r in idx["runs"] if r["run_id"] == run_id)
            self.assertEqual(row["status"], "failed")  # not stale at 'running'

    def test_early_failure_backfills_from_run_ledger(self):
        """Failure before orchestrate wrote earn to disk (e.g. plan validation): the
        sparse disk ledger lacks earn/pricing/plan; backfill them from the run-level
        ledger so the paid record still survives."""
        with _TempRuns() as runs_dir:
            run_id = "build-early"
            led_path = _led_path(runs_dir, run_id)
            sparse = ledger_mod.Ledger(run_id, JOB, "real")  # no earn/pricing/plan yet
            sparse.set_phase("planning")
            sparse.write(led_path)

            build_runner._record_failure(led_path, _run_led(run_id), run_id, JOB, "real",
                                         ValueError("invalid plan"))
            d = _read(led_path)
            self.assertEqual(d["status"], "failed")
            self.assertEqual(d["earn"], PAID_EARN)      # backfilled
            self.assertEqual(d["pricing"], PRICING)     # backfilled
            self.assertEqual(d["plan"], PLAN)           # backfilled

    def test_no_disk_ledger_falls_back_to_run_ledger(self):
        """If no ledger.json exists yet, fall back to the in-memory run-level ledger
        (which still carries earn post-gate) rather than a bare fresh ledger."""
        with _TempRuns() as runs_dir:
            run_id = "build-nodisk"
            led_path = _led_path(runs_dir, run_id)
            os.makedirs(os.path.dirname(led_path), exist_ok=True)
            self.assertFalse(os.path.exists(led_path))
            build_runner._record_failure(led_path, _run_led(run_id), run_id, JOB, "real",
                                         RuntimeError("died before first write"))
            d = _read(led_path)
            self.assertEqual(d["status"], "failed")
            self.assertEqual(d["earn"], PAID_EARN)

    def test_does_not_construct_fresh_empty_ledger(self):
        """Regression guard for the exact old bug: a fresh Ledger(run_id, job, mode)
        would leave earn=None. Assert that never happens when a paid ledger exists."""
        with _TempRuns() as runs_dir:
            run_id = "build-regress"
            led_path = _led_path(runs_dir, run_id)
            _run_led(run_id).write(led_path)
            build_runner._record_failure(led_path, _run_led(run_id), run_id, JOB, "real",
                                         RuntimeError("x"))
            d = _read(led_path)
            self.assertIsNotNone(d["earn"], "earn must NOT be wiped on post-payment failure")


class TestLedgerLoad(unittest.TestCase):
    def test_restores_seq_counter(self):
        with tempfile.TemporaryDirectory() as dpath:
            p = os.path.join(dpath, "ledger.json")
            led = ledger_mod.Ledger("r", JOB, "real")
            led.event("info", "a"); led.event("info", "b"); led.event("info", "c")
            led.write(p)
            reloaded = ledger_mod.Ledger.load(p)
            ev = reloaded.event("error", "next")
            self.assertEqual(ev["seq"], 4)  # continues 1,2,3 -> 4 (no collision)

    def test_preserves_all_blocks(self):
        with tempfile.TemporaryDirectory() as dpath:
            p = os.path.join(dpath, "ledger.json")
            _run_led("r").write(p)
            reloaded = ledger_mod.Ledger.load(p)
            self.assertEqual(reloaded.data["earn"], PAID_EARN)
            self.assertEqual(reloaded.data["plan"], PLAN)
            self.assertEqual(reloaded.run_id, "r")

    def test_missing_file_raises_oserror(self):
        with self.assertRaises(OSError):
            ledger_mod.Ledger.load("/nonexistent/path/ledger.json")


class TestRunEndToEnd(unittest.TestCase):
    """Drive the ACTUAL build_runner.run() flow through plan -> paid gate ->
    (production raise), with the external/paid steps stubbed, to prove the wired
    except path preserves the paid record end-to-end. $0: no Stripe/Higgsfield/
    network — the gate is resolved via PRODUCER_SIMULATE_PAID and orchestrate is a
    stub that mimics the real one's disk writes (earn + queued scenes) then raises,
    exactly as the build-orinovate-edf804 Seedance parse error did mid-production."""

    def test_postpayment_failure_preserves_earn_through_run(self):
        fake_plan = {
            "job": JOB,
            "voiceover": {"script": "hi", "voice": "adam"},
            "scenes": [{"id": "cinematic-motion", "type": "cinematic",
                        "model": "seedance_2_0", "duration_s": 7, "brief": "aerial workspace"}],
        }

        def fake_orchestrate(plan, run_id, mode="mock", overlays=None, earn=None, **kw):
            # Mirror real orchestrate: set the carried (paid) earn + queued scenes and
            # flush to disk, THEN the production loop raises (the parse error).
            o = ledger_mod.Ledger(run_id, plan["job"], mode)
            o.data["plan"] = {"voiceover": plan["voiceover"], "scenes": plan["scenes"]}
            o.set_earn(earn)
            o.set_status("running")
            o.set_phase("producing")
            for i, s in enumerate(plan["scenes"]):
                o.add_scene({"id": s["id"], "type": s["type"], "order": i, "status": "queued"})
            o.write(os.path.join(build_runner.RUNS, run_id, "ledger.json"))
            raise RuntimeError("could not parse higgsfield job id for scene 'cinematic-motion'")

        orig = {
            "plan": build_runner.plan_job.plan_job,
            "est": build_runner.producer.cmd_estimate,
            "sess": build_runner.stripe_earn.create_checkout_session,
            "orch": build_runner.orchestrator.orchestrate,
            "sim": os.environ.get("PRODUCER_SIMULATE_PAID"),
        }
        build_runner.plan_job.plan_job = lambda url, goal, dur, **kw: fake_plan
        build_runner.producer.cmd_estimate = lambda plan: {"suggested_price_cents": 4200}
        build_runner.stripe_earn.create_checkout_session = lambda run_id, cents, currency="usd", product_name="": {
            "session_id": "cs_test_e2e", "url": "http://localhost/x",
            "livemode": False, "payment_status": "unpaid"}
        build_runner.orchestrator.orchestrate = fake_orchestrate
        os.environ["PRODUCER_SIMULATE_PAID"] = "1"
        try:
            with _TempRuns() as runs_dir:
                run_id = "build-e2e"
                with self.assertRaises(RuntimeError):
                    build_runner.run("https://orinovate.com", "promo", run_id,
                                     mode="mock", target_duration=7, pace=0)
                d = _read(_led_path(runs_dir, run_id))
                self.assertEqual(d["status"], "failed")
                self.assertEqual(d["phase"], "failed")
                # The paid record survives the real run() except path (NOT earn=null):
                self.assertIsNotNone(d["earn"])
                self.assertEqual(d["earn"]["payment_status"], "paid")
                self.assertEqual(d["earn"]["session_id"], "cs_test_e2e")
                self.assertTrue(d["plan"]["scenes"])
                self.assertTrue(d["scenes"])
                self.assertTrue(any("could not parse higgsfield job id" in e["msg"]
                                    for e in d["events"] if e["level"] == "error"))
                # And the index is refreshed to 'failed', not stale 'running'.
                idx = _read(os.path.join(runs_dir, "index.json"))
                self.assertEqual(next(r for r in idx["runs"] if r["run_id"] == run_id)["status"],
                                 "failed")
        finally:
            build_runner.plan_job.plan_job = orig["plan"]
            build_runner.producer.cmd_estimate = orig["est"]
            build_runner.stripe_earn.create_checkout_session = orig["sess"]
            build_runner.orchestrator.orchestrate = orig["orch"]
            if orig["sim"] is None:
                os.environ.pop("PRODUCER_SIMULATE_PAID", None)
            else:
                os.environ["PRODUCER_SIMULATE_PAID"] = orig["sim"]


if __name__ == "__main__":
    unittest.main(verbosity=2)
