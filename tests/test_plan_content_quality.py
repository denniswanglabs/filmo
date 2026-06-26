import unittest
import plan_schema


def _plan(beats):
    return {
        "job": {"company_url": "https://x.com", "goal": "g", "target_duration_s": 30},
        "scenes": [{"id": b["scene_id"], "type": "motion_graphic"} for b in beats],
        "voiceover": {"voice": "Adam", "beats": beats},
    }


class TestContentQuality(unittest.TestCase):
    def test_flags_repeated_beat(self):
        p = _plan([
            {"scene_id": "a", "text": "Y Combinator created a new model for funding startups."},
            {"scene_id": "b", "text": "Y Combinator created a new model for funding startups."},
        ])
        issues = plan_schema.validate_plan_content_quality(p, {})
        self.assertTrue(any("repeat" in i.lower() for i in issues))

    def test_flags_nav_label_beat(self):
        p = _plan([
            {"scene_id": "a", "text": "Stripe powers online payments for millions of businesses."},
            {"scene_id": "b", "text": "Knowledge & News"},
        ])
        issues = plan_schema.validate_plan_content_quality(p, {"nav_labels": ["knowledge & news"]})
        self.assertTrue(any("nav" in i.lower() for i in issues))

    def test_flags_thin_beat(self):
        p = _plan([{"scene_id": "a", "text": "Stripe."}])
        issues = plan_schema.validate_plan_content_quality(p, {"wordmark": "Stripe"})
        self.assertTrue(any("thin" in i.lower() or "short" in i.lower() for i in issues))

    def test_flags_no_proof_arc(self):
        p = _plan([
            {"scene_id": "a", "text": "We make powerful seamless innovative software for everyone."},
            {"scene_id": "b", "text": "It is next generation and revolutionary and great to use."},
        ])
        issues = plan_schema.validate_plan_content_quality(p, {})
        self.assertTrue(any("proof" in i.lower() for i in issues))

    def test_clean_arc_passes(self):
        p = _plan([
            {"scene_id": "a", "text": "Stripe powers payments for millions of businesses worldwide."},
            {"scene_id": "b", "text": "Accept cards and wallets in 135 currencies with one integration."},
            {"scene_id": "c", "text": "Block fraud automatically and settle funds in two days."},
            {"scene_id": "d", "text": "Start accepting payments today at stripe.com."},
        ])
        issues = plan_schema.validate_plan_content_quality(p, {"wordmark": "Stripe"})
        self.assertEqual(issues, [])

    def test_wordmark_substring_not_proof(self):
        # Wordmark "cat" appearing only as part of a larger word ("cats", "category",
        # "vacation") must NOT count as proof — the match must be word-boundary anchored.
        p = _plan([
            {"scene_id": "a", "text": "We love cats here and adopt many cats today."},
            {"scene_id": "b", "text": "Our cats live in many categories of vacation spots."},
        ])
        issues = plan_schema.validate_plan_content_quality(p, {"wordmark": "cat"})
        self.assertTrue(any("proof" in i.lower() for i in issues),
                        f"Expected a proof-arc issue but got: {issues}")
