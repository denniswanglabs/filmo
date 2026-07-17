"""Deterministic plan guards (D Dennis 2026-07-17):

1. _trim_quote_sentences — pull-quote testimonials trim to WHOLE sentences within
   ~26 words at the SEED (card + VO + duration derive from the same short quote),
   never mid-sentence (the 2026-07-02 no-guillotine rule stands).
2. _ensure_screenshot_beat — every plan carries the homepage screenshot beat; when
   the planner LLM omits it (taipei-flix 2026-07-14) it is inserted deterministically
   right after the opening title, with a matching VO beat, and the result still
   passes the strict plan schema (the hosted 'invalid plan' crash gate).
"""
import copy
import unittest

import plan_job
from plan_schema import validate_plan


def _base_plan(with_screenshot=False):
    scenes = [
        {"id": "opening-title", "type": "title",
         "brief": "Brand open", "model": None, "duration_s": 4, "input_image": None},
        {"id": "feature-one", "type": "motion_graphic",
         "brief": "Feature card", "model": None, "duration_s": 6, "input_image": None},
        {"id": "closing-title", "type": "title",
         "brief": "CTA close", "model": None, "duration_s": 4, "input_image": None},
    ]
    beats = [
        {"scene_id": "opening-title", "text": "Acme in one line."},
        {"scene_id": "feature-one", "text": "The feature that matters."},
        {"scene_id": "closing-title", "text": "Start now."},
    ]
    if with_screenshot:
        scenes.insert(1, {"id": "homepage-screenshot", "type": "screenshot",
                          "brief": "The homepage.", "model": None,
                          "duration_s": 6, "input_image": None})
        beats.insert(1, {"scene_id": "homepage-screenshot", "text": "The real page."})
    return {
        "job": {"company_url": "https://acme.com", "goal": "A 30-second brand explainer",
                "target_duration_s": 30, "target_margin": 0.6, "currency": "usd"},
        "scenes": scenes,
        "voiceover": {"voice": "Rachel", "beats": beats},
    }


class TrimQuoteSentences(unittest.TestCase):
    LONG = ("One platform gave me auth, AI model access, embeddings, real-time, file "
            "storage and PostgreSQL. Everything we needed to connect eleven tools in "
            "one agent. No stitching together six different services. Just build.")

    def test_long_quote_trims_to_whole_sentences_within_budget(self):
        out = plan_job._trim_quote_sentences(self.LONG, max_words=26)
        self.assertLess(len(out.split()), len(self.LONG.split()))
        self.assertLessEqual(len(out.split()), 30)  # whole-sentence overshoot is small
        self.assertTrue(out.endswith((".", "!", "?")))
        self.assertIn(out, self.LONG)  # a prefix of whole sentences, nothing rewritten

    def test_never_cuts_mid_sentence(self):
        out = plan_job._trim_quote_sentences(self.LONG, max_words=26)
        self.assertFalse(out.rstrip().endswith(("and", "the", "to", "…", ",")))

    def test_single_runon_sentence_kept_whole(self):
        runon = ("This product changed absolutely everything about the way our team "
                 "ships software every single week of the year without exception")
        self.assertEqual(plan_job._trim_quote_sentences(runon, max_words=10), runon)

    def test_short_quote_unchanged(self):
        q = "Filmo just works. Loved it."
        self.assertEqual(plan_job._trim_quote_sentences(q), q)

    def test_empty_safe(self):
        self.assertEqual(plan_job._trim_quote_sentences(""), "")
        self.assertEqual(plan_job._trim_quote_sentences(None), "")


class EnsureScreenshotBeat(unittest.TestCase):
    def test_inserts_after_opening_title_with_vo_beat(self):
        plan = plan_job._ensure_screenshot_beat(_base_plan())
        types = [s["type"] for s in plan["scenes"]]
        self.assertEqual(types[0], "title")
        self.assertEqual(types[1], "screenshot")
        sid = plan["scenes"][1]["id"]
        beat_ids = [b["scene_id"] for b in plan["voiceover"]["beats"]]
        self.assertEqual(beat_ids[1], sid)  # VO beat right after the opening beat
        self.assertIsNone(plan["scenes"][1]["model"])

    def test_guarded_plan_passes_strict_schema(self):
        plan = plan_job._ensure_screenshot_beat(_base_plan())
        self.assertEqual(validate_plan(plan), [])

    def test_plan_with_screenshot_untouched(self):
        before = _base_plan(with_screenshot=True)
        after = plan_job._ensure_screenshot_beat(copy.deepcopy(before))
        self.assertEqual(before, after)

    def test_non_title_open_inserts_at_front(self):
        plan = _base_plan()
        plan["scenes"] = plan["scenes"][1:]  # drop the opening title
        plan["voiceover"]["beats"] = plan["voiceover"]["beats"][1:]
        out = plan_job._ensure_screenshot_beat(plan)
        self.assertEqual(out["scenes"][0]["type"], "screenshot")
        self.assertEqual(out["voiceover"]["beats"][0]["scene_id"], out["scenes"][0]["id"])

    def test_id_collision_gets_suffix(self):
        plan = _base_plan()
        plan["scenes"][1]["id"] = "homepage-screenshot"  # motion_graphic squatting the id
        out = plan_job._ensure_screenshot_beat(plan)
        shot = [s for s in out["scenes"] if s["type"] == "screenshot"]
        self.assertEqual(len(shot), 1)
        self.assertEqual(shot[0]["id"], "homepage-screenshot-guard")

    def test_malformed_plan_never_raises(self):
        self.assertEqual(plan_job._ensure_screenshot_beat({"scenes": []}),
                         {"scenes": []})
        out = plan_job._ensure_screenshot_beat({})
        self.assertEqual(out, {})


if __name__ == "__main__":
    unittest.main()
