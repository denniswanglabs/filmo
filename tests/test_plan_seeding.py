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


if __name__ == "__main__":
    unittest.main()
