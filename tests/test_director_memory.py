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
import run_events
import workspace_store


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


def _event_kinds(run_dir):
    """The kind of every event emitted so far, in order."""
    out = []
    try:
        with open(os.path.join(run_dir, "events.jsonl")) as f:
            for line in f:
                out.append(json.loads(line).get("kind"))
    except FileNotFoundError:
        pass
    return out


# ── Part 1 (persist every turn) + Part 3 (a rerun that actually ships), driven
# through handle_job as production does — a fresh process, chat.jsonl the only
# memory, the render/credits/ship/persist tail mocked so the suite is free ────
class DirectorHardeningTests(unittest.TestCase):
    def setUp(self):
        self.key = "test-director-hardening"
        self.run_dir = _write_fixture(self.key)
        self.brain = _Brain()
        self.persisted = []      # (run_key, reason) per workspace_store.persist

        def fake_assemble(run_id, run_dir, pub, stops, ctx):
            with open(os.path.join(run_dir, "stops.json"), "w") as f:
                json.dump({"stops": stops, "ctx": ctx}, f)
            return ("final.mp4", [], 10.0)

        def fake_persist(run_dir, run_key, reason="build"):
            self.persisted.append((run_key, reason))
            return None

        self.charge = mock.Mock(return_value=None)
        self.ship = mock.Mock(return_value="https://cdn.test/final.mp4?v=1")
        self.flush = mock.Mock(return_value=None)
        # build_tour_film RETURNS the new film path (the real one writes a new
        # stops.json + clips then returns `out`); the rerun branch must ship it.
        self.build = mock.Mock(
            return_value=os.path.join(self.run_dir, "film-tour.mp4"))
        self._patches = [
            mock.patch("validate_planner.call_model", self.brain),
            mock.patch("proto_walkrec._assemble_and_render",
                       side_effect=fake_assemble),
            mock.patch("proto_walkrec.build_tour_film", self.build),
            mock.patch("run_events.charge_credits", self.charge),
            mock.patch("run_events.ship_final", self.ship),
            mock.patch("run_events.flush_sinks", self.flush),
            mock.patch("workspace_store.persist", side_effect=fake_persist),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()
        shutil.rmtree(self.run_dir, ignore_errors=True)

    def test_clarification_turn_persists_chat_delta(self):
        """A pure clarification (no actions) must persist reason="chat" so a
        mid-conversation redeploy + rehydrate does not drop the turn — and it
        neither ships nor charges."""
        self.brain.queue = [json.dumps({
            "reply": "Which one — the getting started checklist or the "
                     "everything-you-need one?", "actions": []})]
        director.handle_job(self.key, "", "change the checklist scene")
        self.assertIn((self.key, "chat"), self.persisted)
        self.assertFalse(self.ship.called)
        self.assertFalse(self.charge.called)

    def test_applied_edit_persists_edit_not_chat(self):
        """The regression guard: an APPLIED edit still persists reason="edit"
        (its heavier workspace), charges, and does NOT also fire a chat delta."""
        self.brain.queue = [json.dumps({
            "reply": "Perfect — switching that beat to a logo wall.",
            "actions": [{"action": "swap_treatment",
                         "beat_title": "Getting started in three steps",
                         "to": "logo-wall"}]})]
        director.handle_job(self.key, "",
                            "make the getting started beat a logo wall")
        self.assertIn((self.key, "edit"), self.persisted)
        self.assertNotIn((self.key, "chat"), self.persisted)
        self.assertTrue(self.charge.called)

    def test_rerun_ships_persists_and_emits_completion(self):
        """Part 3: 'redo the whole film' re-produces AND delivers — it ships the
        film build_tour_film returned, emits run.done, flushes, and re-persists
        with edit semantics so the next edit rehydrates THIS re-run."""
        self.brain.queue = [json.dumps({
            "reply": "Redoing the whole film from scratch.",
            "actions": [{"action": "rerun"}]})]
        rc = director.handle_job(self.key, "", "redo the whole film")
        self.assertEqual(rc, 0)
        # re-produced from the site host carried in ctx
        self.build.assert_called_once()
        self.assertEqual(self.build.call_args[0][0], "https://acme.test/")
        # shipped exactly the film build_tour_film returned
        self.ship.assert_called_once()
        self.assertEqual(self.ship.call_args[0][2],
                         os.path.join(self.run_dir, "film-tour.mp4"))
        # completion narrated through the same event grammar
        kinds = _event_kinds(self.run_dir)
        self.assertIn("run.start", kinds)
        self.assertIn("run.done", kinds)
        # re-persisted (edit semantics) and flushed
        self.assertIn((self.key, "edit"), self.persisted)
        self.assertTrue(self.flush.called)

    def test_rerun_charges_nothing_pending_pricing(self):
        """Part 3 pricing: a rerun charge is UNDEFINED (web gates on the 70
        edit allowance; a full production is 640). Until Dennis decides, NO
        charge is written — the rerun must not silently debit an edit or a
        video price."""
        self.brain.queue = [json.dumps({
            "reply": "Redoing the whole film from scratch.",
            "actions": [{"action": "rerun"}]})]
        director.handle_job(self.key, "", "regenerate the entire film")
        self.assertFalse(self.charge.called)


# ── Part 2: provenance survives a redeploy — _events_tail prefers the local
# ledger and falls back to the run's agent_events in InsForge when it is thin ─
class EventsTailTests(unittest.TestCase):
    def setUp(self):
        self.key = "test-events-tail"
        self.run_dir = _write_fixture(self.key)

    def tearDown(self):
        shutil.rmtree(self.run_dir, ignore_errors=True)

    def test_local_full_is_the_fast_path_no_db(self):
        with open(os.path.join(self.run_dir, "events.jsonl"), "w") as f:
            for i in range(20):
                f.write(json.dumps({"seq": i, "kind": "decide.motif",
                                    "title": f"beat {i}", "detail": ""}) + "\n")
        with mock.patch("run_events._if_req") as ifreq:
            out = director._events_tail(self.run_dir, n=18)
        ifreq.assert_not_called()        # a warm replica never hits the DB
        self.assertIn("beat 19", out)

    def test_falls_back_to_db_when_local_absent(self):
        # a rehydrated replica: events.jsonl was never persisted, so it is gone
        self.assertFalse(
            os.path.exists(os.path.join(self.run_dir, "events.jsonl")))
        with open(os.path.join(self.run_dir, "insforge-run-id"), "w") as f:
            f.write("run-abc")
        rows = [   # newest-first, as PostgREST returns order=seq.desc
            {"kind": "review.done", "title": "Change applied", "detail": ""},
            {"kind": "decide.motif",
             "title": "Getting started -> check-list",
             "detail": "Four labeled steps read as a checklist, not a stat."}]
        resp = mock.Mock()
        resp.read.return_value = json.dumps(rows).encode()
        with mock.patch.multiple("run_events", _IF_BASE="https://if.test",
                                 _IF_KEY="k"), \
                mock.patch("run_events._if_req", return_value=resp) as ifreq:
            out = director._events_tail(self.run_dir, n=18)
        ifreq.assert_called_once()
        method, path = ifreq.call_args[0][0], ifreq.call_args[0][1]
        self.assertEqual(method, "GET")
        self.assertIn("agent_events?run_id=eq.run-abc", path)
        self.assertIn("order=seq.desc", path)
        self.assertIn("limit=18", path)
        # provenance is present and re-ordered oldest-first for the prompt
        self.assertIn("decide.motif", out)
        self.assertIn("Four labeled steps", out)
        self.assertLess(out.index("decide.motif"), out.index("review.done"))
        self.assertNotEqual(out, "(no events)")

    def test_no_events_when_off_hosted(self):
        # no local ledger, no insforge-run-id -> honest "(no events)", no DB
        with mock.patch("run_events._if_req") as ifreq:
            out = director._events_tail(self.run_dir, n=18)
        self.assertEqual(out, "(no events)")
        ifreq.assert_not_called()


# ── Part 1 at the storage layer: reason="chat" is a chat.jsonl + manifest
# DELTA; reason="edit" keeps the pre-existing always-upload-stops contract ────
class WorkspaceChatDeltaTests(unittest.TestCase):
    def setUp(self):
        self.key = "test-ws-chat-delta"
        self.run_dir = _write_fixture(self.key)
        with open(os.path.join(self.run_dir, "chat.jsonl"), "w") as f:
            f.write(json.dumps({"role": "user", "text": "hi there"}) + "\n")
        self.uploaded = []
        self.env = mock.patch.dict(os.environ,
                                   {"INSFORGE_BASE_URL": "https://if.test",
                                    "INSFORGE_API_KEY": "k"})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        shutil.rmtree(self.run_dir, ignore_errors=True)

    def _prior_manifest(self):
        """A prior build manifest listing stops.json + the clip at their CURRENT
        sizes (so a chat delta sees them unchanged) and chat.jsonl at an OLD
        size (so the delta sees it changed)."""
        run_dir, clip = self.run_dir, "shot-1-60.mp4"
        return {"schema": 1, "run_key": self.key, "revision": 3,
                "reason": "build", "created_ts": 1.0,
                "files": [
                    {"key": f"workspace/{self.key}/stops.json",
                     "name": "stops.json", "dest": "run", "role": "essential",
                     "bytes": os.path.getsize(
                         os.path.join(run_dir, "stops.json"))},
                    {"key": f"workspace/{self.key}/{clip}", "name": clip,
                     "dest": "run", "role": "essential",
                     "bytes": os.path.getsize(os.path.join(run_dir, clip))},
                    {"key": f"workspace/{self.key}/chat.jsonl",
                     "name": "chat.jsonl", "dest": "run", "role": "asset",
                     "bytes": 1}]}

    def _run_persist(self, reason):
        def fake_upload(key, path, overwrite=False):
            self.uploaded.append(os.path.basename(key))
            return f"https://if.test/{key}"
        with mock.patch("workspace_store._read_manifest",
                        return_value=self._prior_manifest()), \
                mock.patch("workspace_store.upload_object",
                           side_effect=fake_upload):
            return workspace_store.persist(self.run_dir, self.key, reason=reason)

    def test_chat_delta_uploads_only_chat_and_manifest(self):
        manifest = self._run_persist("chat")
        self.assertIsNotNone(manifest)
        # unchanged stops.json + clip are NOT re-uploaded (the delta win)
        self.assertNotIn("stops.json", self.uploaded)
        self.assertNotIn("shot-1-60.mp4", self.uploaded)
        # only the changed chat.jsonl and the commit-point manifest go up
        self.assertEqual(set(self.uploaded), {"chat.jsonl", "workspace.json"})
        # the manifest still LISTS every file, so rehydrate stays whole
        self.assertEqual({f["name"] for f in manifest["files"]},
                         {"stops.json", "shot-1-60.mp4", "chat.jsonl"})

    def test_edit_delta_still_reuploads_stops(self):
        # the control: reason="edit" keeps the pre-existing contract intact
        self._run_persist("edit")
        self.assertIn("stops.json", self.uploaded)


if __name__ == "__main__":
    unittest.main()
