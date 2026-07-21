"""Director memory + honest-edit guards (Dennis 2026-07-20, after the director
failed him twice in one thread).

TWO live failures this pins:
  1. AMNESIA — _SYSTEM templated {beats} and {events} but never the
     conversation, and the hosted path (_handle_job) never even wrote
     chat.jsonl. Every turn saw only its own sentence, so "change the checklist
     scene" -> "which?" -> "the getting started one" -> "which?" looped for
     seven turns. FIX: _say writes every turn to chat.jsonl; _chat_tail feeds
     the last ~12 turns back into the prompt; a FRESH process reads them.
  2. INVENTED TREATMENT — a swap_treatment's `to` came straight from the model
     ("swapped Getting Started to context-cards" — a treatment nobody named).
     FIX: _resolve_actions rejects a swap whose target the USER never said, and
     tells the honest limit when a request is aimed at a recording.

Every turn in production is a FRESH PROCESS, so the tests drive director the
same way: no in-memory state survives between turns — chat.jsonl on disk is the
only memory. The brain (call_model) and the render/credits/persist tail are
mocked, so the whole suite is deterministic and free.
"""
import json
import os
import shutil
import unittest
from unittest import mock

import director


HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ── fixture: an opening RECORDING + two check-list vignettes (production shape,
# mirrored from a real runs/<id>/stops.json — recordings carry a seg path and
# no motif; graphic beats carry motif and seg="") ──────────────────────────
def _fixture_state(run_dir):
    ents = ["Stripe", "Vercel", "GitHub", "Linear", "Notion"]

    def vign(title, details, entities=None, marks=None, motif="check-list"):
        return {"title": title, "page": "https://acme.test/", "target": "",
                "details": details, "entities": entities or [],
                "marks": marks or {}, "chips": [], "read_shot": True,
                "graphic_only": True, "seg": "", "motif": motif,
                "motif_locked": True}

    rec = {"title": "See Acme in action", "page": "https://acme.test/",
           "target": "", "details": [], "entities": [], "chips": [],
           "read_shot": True, "graphic_only": False,
           "seg": os.path.join(run_dir, "shot-1-60.mp4")}
    s1 = vign("Getting started in three steps",
              ["Create your account", "Connect your data",
               "Invite your team", "Ship your first project"],
              entities=ents, marks={n: "logo" for n in ents})
    s2 = vign("Everything you need to ship",
              ["Built-in analytics", "One-click deploys",
               "Automatic backups"])
    return {"stops": [rec, s1, s2], "ctx": {"host": "https://acme.test/"}}


def _write_fixture(run_key):
    run_dir = os.path.join(HERE, "runs", run_key)
    os.makedirs(run_dir, exist_ok=True)
    with open(os.path.join(run_dir, "stops.json"), "w") as f:
        json.dump(_fixture_state(run_dir), f)
    # A real seg file so no code path trips on a missing clip.
    open(os.path.join(run_dir, "shot-1-60.mp4"), "wb").close()
    return run_dir


def _director_state(run_dir):
    with open(os.path.join(run_dir, "stops.json")) as f:
        return json.load(f)


def _director_lines(run_dir):
    """Every chat.director line emitted so far, in order (the actual replies)."""
    out = []
    try:
        with open(os.path.join(run_dir, "events.jsonl")) as f:
            for line in f:
                e = json.loads(line)
                if e.get("kind") == "chat.director":
                    out.append(e["title"])
    except FileNotFoundError:
        pass
    return out


class _Brain:
    """A stand-in for validate_planner.call_model. Records the system prompt of
    every call and returns the pre-queued director JSON for that turn."""

    def __init__(self):
        self.prompts = []
        self.queue = []

    def __call__(self, messages, brain=None, meta=None):
        self.prompts.append(messages[0]["content"])
        return self.queue.pop(0)


class DirectorGuardTests(unittest.TestCase):
    """The code-level guards in _resolve_actions — deterministic, no brain."""

    def setUp(self):
        self.key = "test-director-guards"
        self.run_dir = _write_fixture(self.key)
        self.state = _director_state(self.run_dir)

    def tearDown(self):
        shutil.rmtree(self.run_dir, ignore_errors=True)

    def test_user_named_swap_applies(self):
        stops = self.state["stops"]
        applied, rejected, rerun = director._resolve_actions(
            stops,
            [{"action": "swap_treatment",
              "beat_title": "Getting started in three steps",
              "to": "logo-wall"}],
            said={"logo-wall"})
        self.assertEqual(rejected, [])
        self.assertEqual(applied, [("swap", "Getting started in three steps",
                                    "logo-wall")])
        got = next(s for s in stops
                   if s["title"] == "Getting started in three steps")
        self.assertEqual(got["motif"], "logo-wall")

    def test_invented_treatment_is_rejected_and_never_applied(self):
        """The exact wrong-edit failure: a swap to a treatment nobody named."""
        stops = self.state["stops"]
        before = {s["title"]: s.get("motif") for s in stops}
        applied, rejected, rerun = director._resolve_actions(
            stops,
            [{"action": "swap_treatment",
              "beat_title": "Getting started in three steps",
              "to": "context-cards"}],
            said={"logo-wall"})          # user said "logo wall", never context-cards
        self.assertEqual(applied, [])
        self.assertEqual(len(rejected), 1)
        self.assertEqual(rejected[0][2], "unnamed_treatment")
        after = {s["title"]: s.get("motif") for s in stops}
        self.assertEqual(before, after)   # nothing changed on the film
        # No applied action anywhere carries a treatment the user never said.
        self.assertNotIn("context-cards",
                         [a[2] for a in applied if a[0] == "swap"])

    def test_recording_target_gets_honest_limit(self):
        """Delete/drop aimed at the opening RECORDING is refused with the truth,
        not a forced choice among unrelated beats."""
        stops = self.state["stops"]
        applied, rejected, rerun = director._resolve_actions(
            stops,
            [{"action": "drop", "beat_title": "See Acme in action"}],
            said=set())
        self.assertEqual(applied, [])
        self.assertEqual(rejected[0][2], "recording")
        reply = director._outcome_reply(stops, applied, rejected)
        self.assertIn("real footage", reply)
        # It lists the editable graphic beats, never a coerced either/or.
        self.assertIn("Getting started in three steps", reply)
        self.assertIn("Everything you need to ship", reply)

    def test_floor_downgrade_declines_not_silent_swap(self):
        """logo-wall can't hold on the thin beat; the floor would land it on
        request-table (a treatment the user never named) — so it DECLINES."""
        stops = self.state["stops"]
        applied, rejected, rerun = director._resolve_actions(
            stops,
            [{"action": "swap_treatment",
              "beat_title": "Everything you need to ship",
              "to": "logo-wall"}],
            said={"logo-wall"})
        self.assertEqual(applied, [])
        self.assertEqual(rejected[0][2], "floor")
        got = next(s for s in stops
                   if s["title"] == "Everything you need to ship")
        self.assertEqual(got["motif"], "check-list")   # untouched

    def test_true_cut_floor_still_declines(self):
        """A genuinely empty beat can hold nothing -> _pick_repair returns _CUT
        -> the original floor contract still declines the swap."""
        state = _director_state(self.run_dir)
        state["stops"][2] = {"title": "Learn more", "page": "", "target": "",
                             "details": [], "entities": [], "marks": {},
                             "chips": [], "read_shot": True,
                             "graphic_only": True, "seg": "", "motif": "card",
                             "motif_locked": True}
        applied, rejected, rerun = director._resolve_actions(
            state["stops"],
            [{"action": "swap_treatment", "beat_title": "Learn more",
              "to": "stat-pop"}],
            said={"stat-pop"})
        self.assertEqual(applied, [])
        self.assertEqual(rejected[0][2], "floor")

    def test_floor_lands_on_named_treatment_applies(self):
        """Guard is not over-broad: when the user NAMES request-table and the
        floor lands exactly there, the swap applies."""
        stops = self.state["stops"]
        applied, rejected, rerun = director._resolve_actions(
            stops,
            [{"action": "swap_treatment",
              "beat_title": "Everything you need to ship",
              "to": "request-table"}],
            said={"request-table"})
        self.assertEqual(rejected, [])
        self.assertEqual(applied[0][:2], ("swap", "Everything you need to ship"))
        self.assertEqual(applied[0][2], "request-table")


class DirectorMemoryTests(unittest.TestCase):
    """The FEED: a fresh handle_job process reads the prior turns from
    chat.jsonl and resolves references against them."""

    def setUp(self):
        self.key = "test-director-memory"
        self.run_dir = _write_fixture(self.key)
        self.brain = _Brain()

        # Faithful stand-in for the assemble step: the real _plan_beats writes
        # stops.json at assemble time (proto_walkrec.py:2163), which is how the
        # NEXT turn sees the applied motifs. Mirror that, skip the render.
        def fake_assemble(run_id, run_dir, pub, stops, ctx):
            with open(os.path.join(run_dir, "stops.json"), "w") as f:
                json.dump({"stops": stops, "ctx": ctx}, f)
            return ("final.mp4", [], 10.0)

        # Mock the brain and the whole render/credits/persist tail so a turn is
        # deterministic and free.
        self._patches = [
            mock.patch("validate_planner.call_model", self.brain),
            mock.patch("proto_walkrec._assemble_and_render",
                       side_effect=fake_assemble),
            mock.patch("proto_walkrec.build_tour_film", return_value=None),
            mock.patch("run_events.charge_credits", return_value=None),
            mock.patch("run_events.ship_final", return_value=None),
            mock.patch("run_events.flush_sinks", return_value=None),
            mock.patch("workspace_store.persist", return_value=None),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()
        shutil.rmtree(self.run_dir, ignore_errors=True)

    def test_chat_is_written_and_a_fresh_process_reads_it(self):
        # TURN 1 (fresh process): the vague opener; director asks which beat.
        self.brain.queue = [json.dumps({
            "reply": "Which one — the getting started checklist or the "
                     "everything-you-need one?", "actions": []})]
        director.handle_job(self.key, "", "change the checklist scene to a "
                            "logo wall")

        rows = [json.loads(l) for l in
                open(os.path.join(self.run_dir, "chat.jsonl"))]
        self.assertEqual([r["role"] for r in rows], ["user", "director"])
        self.assertIn("logo wall", rows[0]["text"])

        # TURN 2 (a brand-new process — nothing in memory but chat.jsonl): the
        # answer. The prompt must now carry the conversation so far.
        self.brain.queue = [json.dumps({
            "reply": "Perfect — switching that beat to a logo wall.",
            "actions": [{"action": "swap_treatment",
                         "beat_title": "Getting started in three steps",
                         "to": "logo-wall"}]})]
        director.handle_job(self.key, "", "the getting started one")

        prompt = self.brain.prompts[-1]
        self.assertIn("THE CONVERSATION SO FAR", prompt)
        self.assertIn("change the checklist scene to a logo wall", prompt)
        self.assertIn("the getting started checklist", prompt)  # turn-1 reply
        # The current turn is NOT in the memory section (logged only AFTER the
        # prompt is built), and the turn-1 note appears once, not duplicated.
        self.assertNotIn("the getting started one", prompt)
        self.assertEqual(
            prompt.count("change the checklist scene to a logo wall"), 1)

        # And the swap actually applied (action + target both determined).
        stops = _director_state(self.run_dir)["stops"]
        got = next(s for s in stops
                   if s["title"] == "Getting started in three steps")
        self.assertEqual(got["motif"], "logo-wall")

    def test_wrong_edit_never_applies_an_unnamed_treatment(self):
        # The real wrong-edit shape: a delete aimed at the opening, then a stale
        # invented treatment. Whatever the brain emits, no unnamed treatment may
        # reach the film.
        self.brain.queue = [json.dumps({
            "reply": "The opening is real footage — I can only touch the "
                     "graphic beats.", "actions": []})]
        director.handle_job(self.key, "", "can you delete the first scene?")

        # Brain (wrongly) tries to swap to a treatment the user never named.
        self.brain.queue = [json.dumps({
            "reply": "Done — swapped Getting Started to context-cards.",
            "actions": [{"action": "swap_treatment",
                         "beat_title": "Getting started in three steps",
                         "to": "context-cards"}]})]
        director.handle_job(self.key, "", "getting started")

        stops = _director_state(self.run_dir)["stops"]
        motifs = [s.get("motif") for s in stops]
        self.assertNotIn("context-cards", motifs)   # the invention never landed
        got = next(s for s in stops
                   if s["title"] == "Getting started in three steps")
        self.assertEqual(got["motif"], "check-list")
        # The spoken reply asked for the treatment instead of inventing one.
        self.assertIn("Swap", _director_lines(self.run_dir)[-1])


class DirectorHelperTests(unittest.TestCase):
    def setUp(self):
        self.key = "test-director-helpers"
        self.run_dir = os.path.join(HERE, "runs", self.key)
        os.makedirs(self.run_dir, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.run_dir, ignore_errors=True)

    def test_canon_treatment(self):
        self.assertEqual(director._canon_treatment("logo wall"), "logo-wall")
        self.assertEqual(director._canon_treatment("Logo-Wall"), "logo-wall")
        self.assertEqual(director._canon_treatment("  context   cards "),
                         "context-cards")

    def test_said_treatments_reads_user_turns_and_message(self):
        with open(os.path.join(self.run_dir, "chat.jsonl"), "w") as f:
            f.write(json.dumps({"role": "user",
                                "text": "make it a logo wall"}) + "\n")
            f.write(json.dumps({"role": "director",
                                "text": "which beat?"}) + "\n")
        said = director._said_treatments(self.run_dir, "actually a stat pop")
        self.assertIn("logo-wall", said)     # earlier user turn
        self.assertIn("stat-pop", said)      # this message
        self.assertNotIn("context-cards", said)

    def test_chat_tail_excludes_the_current_message(self):
        with open(os.path.join(self.run_dir, "chat.jsonl"), "w") as f:
            f.write(json.dumps({"role": "user", "text": "first note"}) + "\n")
            f.write(json.dumps({"role": "director", "text": "which one?"}) + "\n")
            f.write(json.dumps({"role": "user", "text": "the second"}) + "\n")
        tail = director._chat_tail(self.run_dir, message="the second")
        self.assertIn("User: first note", tail)
        self.assertIn("You (the director): which one?", tail)
        # The just-logged current turn is dropped (passed separately as user).
        self.assertEqual(tail.count("the second"), 0)

    def test_chat_tail_empty_for_fresh_thread(self):
        self.assertEqual(director._chat_tail(self.run_dir, "hi"), "")


if __name__ == "__main__":
    unittest.main()
