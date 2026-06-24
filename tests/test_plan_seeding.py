#!/usr/bin/env python3
"""$0, offline tests for Read->plan seeding (facts block + STANDARD backstop)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import validate_planner as vp


def _read():
    return {
        "url": "https://acme.com", "verdict": "feature-led, no proof",
        "dimensions": [
            {"key": "promise", "score": 3, "finding": "", "evidence": "", "fix": ""},
            {"key": "outcome", "score": 2, "finding": "", "evidence": "", "fix": "lead with outcome"},
            {"key": "proof", "score": 1, "finding": "no numbers", "evidence": "", "fix": "add a proof beat"},
            {"key": "show", "score": 2, "finding": "", "evidence": "", "fix": ""},
            {"key": "specificity", "score": 2, "finding": "", "evidence": "", "fix": ""},
            {"key": "cta", "score": 2, "finding": "", "evidence": "", "fix": "single CTA"},
        ],
        "priority_fixes": [
            {"rank": 1, "fix": "Add a proof beat with a real number", "maps_to": "proof"},
            {"rank": 2, "fix": "One clear closing CTA", "maps_to": "cta"},
        ],
        "headline_fix": "Ship 10x faster with Acme.",
    }


class FactsBlockWithRead(unittest.TestCase):
    def test_read_block_appends_prescriptions(self):
        facts = {"wordmark": "Acme", "tagline": "", "features": ["a", "b", "c"]}
        block = vp.company_facts_block(facts, company_url="https://acme.com",
                                       conversion_read=_read())
        self.assertIn("CONVERSION READ", block)
        self.assertIn("Add a proof beat with a real number", block)
        self.assertIn("Ship 10x faster with Acme.", block)

    def test_absent_read_is_byte_identical_to_before(self):
        facts = {"wordmark": "Acme", "tagline": "", "features": ["a", "b", "c"]}
        with_none = vp.company_facts_block(facts, company_url="https://acme.com",
                                           conversion_read=None)
        without = vp.company_facts_block(facts, company_url="https://acme.com")
        self.assertEqual(with_none, without)


import plan_job


def _std_plan():
    return {
        "job": {"company_url": "https://acme.com", "goal": "promo",
                "target_duration_s": 30, "_wordmark": "Acme"},
        "scenes": [
            {"id": "00_open", "type": "title", "brief": "", "model": None, "duration_s": 4, "input_image": None},
            {"id": "shot", "type": "screenshot", "brief": "", "model": None, "duration_s": 8, "input_image": None},
            {"id": "walk", "type": "walkthrough", "brief": "", "model": None, "duration_s": 10, "input_image": None},
            {"id": "99_close", "type": "title", "brief": "", "model": None, "duration_s": 4, "input_image": None},
        ],
        "voiceover": {"voice": "adam", "beats": [
            {"scene_id": "00_open", "text": "Acme."},
            {"scene_id": "shot", "text": "A screenshot."},
            {"scene_id": "walk", "text": "A walkthrough."},
            {"scene_id": "99_close", "text": "Try Acme."},
        ]},
    }


class StandardBackstopSeeding(unittest.TestCase):
    def test_headline_fix_becomes_opening_title_beat(self):
        plan = plan_job.seed_plan_with_read(_std_plan(), _read())
        beats = {b["scene_id"]: b["text"] for b in plan["voiceover"]["beats"]}
        self.assertEqual(beats["00_open"], "Ship 10x faster with Acme.")

    def test_top_proof_fix_lands_as_a_beat_brief(self):
        plan = plan_job.seed_plan_with_read(_std_plan(), _read())
        # the rank-1 fix text must appear somewhere in a scene brief OR a vo beat
        briefs = " ".join(s.get("brief", "") for s in plan["scenes"])
        beats = " ".join(b["text"] for b in plan["voiceover"]["beats"])
        self.assertIn("proof beat", (briefs + " " + beats).lower())

    def test_no_read_is_a_noop(self):
        before = _std_plan()
        after = plan_job.seed_plan_with_read(_std_plan(), None)
        self.assertEqual(after["voiceover"]["beats"][0]["text"], before["voiceover"]["beats"][0]["text"])


if __name__ == "__main__":
    unittest.main()
