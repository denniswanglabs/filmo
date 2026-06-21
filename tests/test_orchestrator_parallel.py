#!/usr/bin/env python3
"""Layer 2b — failure isolation + parallel walkthrough ($0, mock mode).

Covers the two changes that took the slow/flaky walkthrough off the critical path:

  A) FAILURE ISOLATION (default ON, the bug fix). A run died because ONE scene's
     walk-agent failure raised AdapterError and the SERIAL produce loop turned that
     into a total run loss — the 2 later scenes never ran and no video stitched.
     Now a single scene's failure is isolated: the run COMPLETES, stitches the
     survivors, marks that scene status='failed', and reports status
     'completed_with_warnings' (degradation VISIBLE, never masked as 'delivered').

  B) PARALLEL WALKTHROUGH (behind HERMES_PARALLEL=1, default off). The walkthrough's
     generation runs off-thread and is joined at its slot, overlapping the other
     scenes. A timing test with injected sleeps proves the wall-clock win. The money
     path (gate/authorize/spend) stays serial: the money-shot regression below runs
     with the flag both OFF and ON and asserts identical gate sequence + spend.

Everything here is mock/$0: real edge-tts + real ffmpeg, mock generation, no Stripe,
no Higgsfield. Run: python3 -m unittest tests.test_orchestrator_parallel
"""

import json
import os
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SCEN = os.path.join(HERE, "scenarios")
sys.path.insert(0, ROOT)

PLANNING_STUB = json.dumps({"seedance_2_0": 22, "gpt_image_2": 7, "__default__": 10})
os.environ["PRODUCER_COST_STUB"] = PLANNING_STUB

import adapters  # noqa: E402
import orchestrator  # noqa: E402


def load(name):
    with open(os.path.join(SCEN, name)) as f:
        return json.load(f)


def run(plan, run_id, production_stub=None, parallel=False, runs_dir=None):
    """Run a scenario into a temp runs dir; return (ledger, runs_dir)."""
    if production_stub is None:
        os.environ.pop("PRODUCER_PRODUCTION_COST_STUB", None)
    else:
        os.environ["PRODUCER_PRODUCTION_COST_STUB"] = json.dumps(production_stub)
    os.environ["PRODUCER_COST_STUB"] = PLANNING_STUB
    if parallel:
        os.environ["HERMES_PARALLEL"] = "1"
    else:
        os.environ["HERMES_PARALLEL"] = "0"
    tmp = runs_dir or tempfile.mkdtemp(prefix="hermes-parallel-")
    try:
        data, _ = orchestrator.orchestrate(plan, run_id, mode="mock", runs_dir=tmp,
                                            vo_provider="edge", now="2026-06-19T00:00:00Z")
    finally:
        os.environ.pop("HERMES_PARALLEL", None)
        os.environ.pop("PRODUCER_PRODUCTION_COST_STUB", None)
    return data, tmp


def scenes_by_id(data):
    return {s["id"]: s for s in data["scenes"]}


def gate_event_sequence(data):
    """The ordered gate/spend/decline/money events — the money-shot fingerprint."""
    keep = ("gate", "spend", "decline", "money")
    return [(e["level"], e["msg"]) for e in data["events"] if e["level"] in keep]


# ---------------------------------------------------------------------------
# A) FAILURE ISOLATION — the headline fix.
# ---------------------------------------------------------------------------

class TestFailureIsolation(unittest.TestCase):
    """A failing scene must NOT kill the run. The run completes, stitches the
    survivors, marks the scene failed, and reports completed_with_warnings."""

    def _run_with_failing_walkthrough(self, parallel):
        plan = load("scenario_decline.json")  # has a walkthrough at idx 2
        orig = adapters.generate_walkthrough

        def boom(scene, out, mode, **kw):
            raise adapters.AdapterError(
                "walk-agent failed for scene %r (rc=1); log: x.walkagent.log\n"
                "Traceback: simulated tutorial-maker.sh crash" % scene.get("id"))

        adapters.generate_walkthrough = boom
        try:
            data, _ = run(plan, "t-isolate-%s" % ("par" if parallel else "ser"),
                          production_stub={"hero-still": 60}, parallel=parallel)
        finally:
            adapters.generate_walkthrough = orig
        return data

    def test_failing_scene_does_not_kill_run_serial(self):
        data = self._run_with_failing_walkthrough(parallel=False)
        self._assert_isolated(data)

    def test_failing_scene_does_not_kill_run_parallel(self):
        data = self._run_with_failing_walkthrough(parallel=True)
        self._assert_isolated(data)

    def _assert_isolated(self, data):
        s = scenes_by_id(data)
        # the walkthrough is marked failed, with a diagnosable error, and no clip
        self.assertEqual(s["walkthrough"]["status"], "failed")
        self.assertIn("walk-agent failed", s["walkthrough"]["error"])
        self.assertIsNone(s["walkthrough"]["output_path"])
        # the run STILL completed and STILL stitched a final video
        self.assertIsNotNone(data["stitch"])
        self.assertTrue(data["stitch"]["verified"])
        self.assertGreater(data["stitch"]["clip_count"], 0)
        # degradation is VISIBLE — not masked as a clean "delivered"
        self.assertEqual(data["status"], "completed_with_warnings")
        self.assertIn("walkthrough", [w["id"] for w in data.get("warnings", [])])
        # scenes AFTER the failed one still ran (the whole point: no run loss)
        self.assertEqual(s["hero-still"]["decision"], "decline")  # money-shot survived
        self.assertEqual(s["title-close"]["status"], "produced")
        # the walkthrough is NOT in the stitched scenes; the survivors are
        self.assertNotIn("walkthrough", data["stitch"]["scenes_included"])
        self.assertIn("title-open", data["stitch"]["scenes_included"])

    def test_two_failures_still_ship(self):
        """More than one scene can fail and the run still ships the rest."""
        plan = load("scenario_decline.json")
        orig_w = adapters.generate_walkthrough
        orig_o = adapters.generate_overlay

        def boom_w(scene, out, mode, **kw):
            raise adapters.AdapterError("walk-agent failed for scene %r" % scene.get("id"))

        # fail the FIRST title (title-open) but not title-close
        def maybe_boom_o(scene, out, mode, **kw):
            if scene.get("id") == "title-open":
                raise adapters.AdapterError("overlay render crashed for %r" % scene.get("id"))
            return orig_o(scene, out, mode, **kw)

        adapters.generate_walkthrough = boom_w
        adapters.generate_overlay = maybe_boom_o
        try:
            data, _ = run(plan, "t-isolate-two", production_stub={"hero-still": 60})
        finally:
            adapters.generate_walkthrough = orig_w
            adapters.generate_overlay = orig_o
        s = scenes_by_id(data)
        self.assertEqual(s["title-open"]["status"], "failed")
        self.assertEqual(s["walkthrough"]["status"], "failed")
        self.assertEqual(data["status"], "completed_with_warnings")
        self.assertEqual(sorted(w["id"] for w in data["warnings"]),
                         ["title-open", "walkthrough"])
        # the run still produced a video from the survivors
        self.assertTrue(data["stitch"]["verified"])

    def test_all_scenes_failing_is_a_true_abort(self):
        """If NOTHING produces a clip, the run is a true failure (not a clean ship)."""
        plan = load("scenario_approve.json")
        orig_w = adapters.generate_walkthrough
        orig_o = adapters.generate_overlay
        orig_c = adapters.generate_cinematic

        def boom(*a, **k):
            sid = a[0].get("id") if a and isinstance(a[0], dict) else "?"
            raise adapters.AdapterError("simulated total failure for %r" % sid)

        adapters.generate_walkthrough = boom
        adapters.generate_overlay = boom
        adapters.generate_cinematic = boom
        try:
            data, _ = run(plan, "t-isolate-allfail")
        finally:
            adapters.generate_walkthrough = orig_w
            adapters.generate_overlay = orig_o
            adapters.generate_cinematic = orig_c
        # nothing stitched -> true whole-run abort, status 'failed' (preserved)
        self.assertEqual(data["status"], "failed")
        self.assertIsNone(data["stitch"])


# ---------------------------------------------------------------------------
# B) PARALLELISM — the walkthrough overlaps the other scenes ($0 timing proof).
# ---------------------------------------------------------------------------

# Module-level timing numbers, captured by the timing test and printed in tearDown
# so the orchestrator can report the serial-vs-parallel evidence.
TIMING = {}


class TestParallelTiming(unittest.TestCase):
    """Patch the generators with injected sleeps and assert HERMES_PARALLEL=1 is
    materially faster because the slow walkthrough overlaps the other scenes."""

    WALK_DELAY = 1.2     # the slow/flaky scene
    OTHER_DELAY = 0.35   # each of the other generated scenes

    def _patched_run(self, parallel):
        plan = load("scenario_decline.json")  # title, cinematic, walkthrough, cinematic, title
        orig_w = adapters.generate_walkthrough
        orig_o = adapters.generate_overlay
        orig_c = adapters.generate_cinematic

        def slow_walk(scene, out, mode, **kw):
            time.sleep(self.WALK_DELAY)
            adapters.synth_clip(out, adapters.TYPE_COLOR["walkthrough"],
                                scene.get("duration_s", 10))
            return {"output_path": out, "real": False}

        def slow_overlay(scene, out, mode, **kw):
            time.sleep(self.OTHER_DELAY)
            return orig_o(scene, out, mode, **kw)

        def slow_cine(scene, out, mode, **kw):
            time.sleep(self.OTHER_DELAY)
            return orig_c(scene, out, mode, **kw)

        adapters.generate_walkthrough = slow_walk
        adapters.generate_overlay = slow_overlay
        adapters.generate_cinematic = slow_cine
        try:
            t0 = time.time()
            data, _ = run(plan, "t-timing-%s" % ("par" if parallel else "ser"),
                          parallel=parallel)
            elapsed = time.time() - t0
        finally:
            adapters.generate_walkthrough = orig_w
            adapters.generate_overlay = orig_o
            adapters.generate_cinematic = orig_c
        # both runs must actually ship a clean video so we're comparing like for like
        self.assertEqual(data["status"], "delivered")
        self.assertTrue(data["stitch"]["verified"])
        return elapsed

    def test_parallel_is_materially_faster(self):
        serial = self._patched_run(parallel=False)
        parallel = self._patched_run(parallel=True)
        TIMING["serial_s"] = round(serial, 3)
        TIMING["parallel_s"] = round(parallel, 3)
        TIMING["saved_s"] = round(serial - parallel, 3)
        TIMING["walk_delay_s"] = self.WALK_DELAY
        # The walkthrough (WALK_DELAY) overlaps the 4 other generated scenes
        # (~4*OTHER_DELAY = 1.4s of other work). With the flag on, the walkthrough's
        # wall-clock is hidden under that other work, so we save a large fraction of
        # WALK_DELAY. Assert a conservative win to stay robust on a busy CI box.
        self.assertLess(parallel, serial,
                        "parallel must be faster than serial")
        self.assertGreater(serial - parallel, self.WALK_DELAY * 0.4,
                           "parallel should hide most of the walkthrough's delay "
                           "(serial=%.3fs parallel=%.3fs)" % (serial, parallel))

    @classmethod
    def tearDownClass(cls):
        if TIMING:
            print("\n[parallel-timing] serial=%(serial_s)ss parallel=%(parallel_s)ss "
                  "saved=%(saved_s)ss (walk_delay=%(walk_delay_s)ss)" % TIMING)


# ---------------------------------------------------------------------------
# MONEY-SHOT REGRESSION — the gate sequence + spend are byte-for-byte the same
# with the flag OFF and ON (the parallelism never touches the money path).
# ---------------------------------------------------------------------------

class TestMoneyShotInvariant(unittest.TestCase):
    def _money_fingerprint(self, data):
        s = scenes_by_id(data)
        hero = s["hero-still"]
        return {
            "gate_events": gate_event_sequence(data),
            "hero_decision": hero["decision"],
            "hero_would_have": hero["would_have_cost_cents"],
            "hero_spent": hero["spent_cents"],
            "hero_auth_approved": hero["stripe_authorization"]["approved"],
            "cogs_spent": data["pnl"]["cogs_spent_cents"],
            "overage_avoided": data["pnl"]["overage_avoided_cents"],
            "declines": [d["id"] for d in data["pnl"]["declines"]],
        }

    def test_money_shot_identical_flag_off_and_on(self):
        off, off_dir = run(load("scenario_decline.json"), "t-money-off",
                           production_stub={"hero-still": 60}, parallel=False)
        on, on_dir = run(load("scenario_decline.json"), "t-money-on",
                         production_stub={"hero-still": 60}, parallel=True)

        fp_off = self._money_fingerprint(off)
        fp_on = self._money_fingerprint(on)
        self.assertEqual(fp_off, fp_on,
                         "the money-shot must be byte-for-byte preserved flag off vs on")

        # spot-check the sacred specifics on BOTH runs
        for data in (off, on):
            hero = scenes_by_id(data)["hero-still"]
            self.assertEqual(hero["decision"], "decline")           # the decline
            self.assertEqual(hero["spent_cents"], 0)                # no spend
            self.assertEqual(hero["would_have_cost_cents"], 60)
            self.assertFalse(hero["stripe_authorization"]["approved"])
            self.assertEqual(data["pnl"]["overage_avoided_cents"], 60)
            self.assertEqual([d["id"] for d in data["pnl"]["declines"]], ["hero-still"])
            self.assertEqual(scenes_by_id(data)["cine-establish"]["decision"], "approve")

        # the active_budget.json the live webhook reads is identical too
        with open(os.path.join(off_dir, orchestrator.ACTIVE_BUDGET_FILENAME)) as f:
            ab_off = json.load(f)
        with open(os.path.join(on_dir, orchestrator.ACTIVE_BUDGET_FILENAME)) as f:
            ab_on = json.load(f)
        self.assertEqual(ab_off, ab_on)

    def test_approve_scenario_identical_flag_off_and_on(self):
        off, _ = run(load("scenario_approve.json"), "t-appr-off", parallel=False)
        on, _ = run(load("scenario_approve.json"), "t-appr-on", parallel=True)
        self.assertEqual(gate_event_sequence(off), gate_event_sequence(on))
        self.assertEqual(off["pnl"]["cogs_spent_cents"], on["pnl"]["cogs_spent_cents"])
        self.assertEqual(off["status"], "delivered")
        self.assertEqual(on["status"], "delivered")


if __name__ == "__main__":
    unittest.main(verbosity=2)
