"""Reviewer cut floors (Dennis 2026-07-20):

The reviewer's lints may propose _CUT and _apply_fixes pops every _CUT beat.
_lint_blank and _lint_redundancy consult _cut_allowed before attaching the
fix, but _lint_treatment_fit attached _pick_repair's _CUT unguarded — three
material-stripped beats in one round each took a cut and the film shrank
below _MIN_BEATS_AFTER_CUT (smoke test 2026-07-20; introduced with the
Tier-1 reviewer patch, 60f0cff).

The class is guarded twice:
1. ONE shared `pending` set per review round, threaded through every lint
   that can propose _CUT — cut capacity is a property of the FILM, so
   per-lint sets let two honest lints jointly cut past the floor.
2. _apply_fixes is the only function that pops beats, so it re-checks the
   floors over the whole round's cuts — lint fixes and critic drops alike.
A refused cut degrades the finding to fix=None: the disclosure the
handover reports, instead of a film with fewer beats than the floor.
"""
import os
import unittest

import proto_walkrec as pw


def _seg_stop(title="Product walk"):
    return {"seg": {"src": "walk.mp4"}, "title": title}


def _starved(title):
    # logo-wall below its 4-partner floor, with nothing for ANY treatment to
    # show (one-word title, no details/chips/quotes): _pick_repair lands on
    # the ladder's bottom rung, _CUT.
    return {"motif": "logo-wall", "title": title, "entities": ["acme"],
            "details": [], "chips": [], "quotes": []}


def _four_beat_cut():
    return [_seg_stop(), _starved("Partners"), _starved("Integrations"),
            _starved("Customers")]


class CutFloors(unittest.TestCase):
    def test_treatment_fit_cuts_stop_at_the_floor(self):
        # 4 beats, 3 below their material floors: one cut fits the floor
        # (4 -> 3); the other two must degrade to fix=None disclosures.
        stops = _four_beat_cut()
        findings = pw._lint_treatment_fit(stops)
        self.assertEqual(len(findings), 3)
        self.assertEqual(
            len([f for f in findings if f["fix"] == pw._CUT]), 1)
        self.assertEqual(
            len([f for f in findings if f["fix"] is None]), 2)
        pw._apply_fixes(stops, [f for f in findings if f["fix"]], [])
        self.assertGreaterEqual(len(stops), pw._MIN_BEATS_AFTER_CUT)
        self.assertTrue(any(s.get("seg") for s in stops))

    def test_apply_fixes_refuses_lint_cuts_past_the_floor(self):
        # A lint that forgot the consult (the treatment-fit defect): the
        # apply step itself holds the floor and degrades the refused cuts
        # in place to fix=None, so they report as disclosures.
        stops = _four_beat_cut()
        findings = [pw._finding(i, stops[i]["title"], "starved", pw._CUT)
                    for i in (1, 2, 3)]
        pw._apply_fixes(stops, findings, [])
        self.assertEqual(len(stops), pw._MIN_BEATS_AFTER_CUT)
        self.assertEqual([f["fix"] for f in findings],
                         [pw._CUT, None, None])

    def test_apply_fixes_refuses_critic_drops_past_the_floor(self):
        # Critic drops are cuts too; the ≤2-drop cap alone still takes a
        # 4-beat film to 2.
        stops = _four_beat_cut()
        actions = [{"beat": b, "action": "drop", "to": "", "issue": ""}
                   for b in (1, 2, 3)]
        pw._apply_fixes(stops, [], actions)
        self.assertEqual(len(stops), pw._MIN_BEATS_AFTER_CUT)

    def test_cut_budget_is_shared_across_lints(self):
        # treatment-fit spends the round's whole cut budget (5 -> 3);
        # redundancy must then be refused its cut, not granted a fresh
        # budget by a private pending set.
        dup = {"motif": "kinetic-line", "title": "Ship your launch film "
               "today", "details": [], "chips": [], "quotes": []}
        stops = [_seg_stop(), dict(dup), dict(dup),
                 _starved("Partners"), _starved("Integrations")]
        results = pw._data_results(stops, [], 30.0)
        fit = results["treatment-fit"][1]
        red = results["no-redundancy"][1]
        self.assertEqual([f["fix"] for f in fit], [pw._CUT, pw._CUT])
        self.assertEqual(len(red), 1)
        self.assertIsNone(red[0]["fix"])
        lint_fixes = [f for c in results.values() for f in c[1] if f["fix"]]
        pw._apply_fixes(stops, lint_fixes, [])
        self.assertEqual(len(stops), pw._MIN_BEATS_AFTER_CUT)

    def test_many_simultaneous_floor_failures_hold_the_floor(self):
        # Every cut source firing at once over one 6-beat set — two redundant
        # kinetic-lines and three starved logo-walls — still cannot take the
        # film below the floor; the excess degrades to fix=None disclosures.
        dup = {"motif": "kinetic-line", "title": "Ship your launch film today",
               "details": [], "chips": [], "quotes": []}
        stops = [_seg_stop(), dict(dup), dict(dup), _starved("Partners"),
                 _starved("Integrations"), _starved("Customers")]
        results = pw._data_results(stops, [], 30.0)
        lint_fixes = [f for c in results.values() for f in c[1] if f["fix"]]
        pw._apply_fixes(stops, lint_fixes, [])
        self.assertGreaterEqual(len(stops), pw._MIN_BEATS_AFTER_CUT)
        self.assertTrue(any(s.get("seg") for s in stops))


class BenefitShape(unittest.TestCase):
    """TASK 2a — the check-shape predicate, written from the delivered corpus
    (runs/*/stops.json). A CTA or an audience/scope phrase is not a benefit and
    may not wear a check; a real feature row that merely opens with a verb is
    left alone."""

    # The exact rows the stripe rescue proof ticked (must now be REJECTED):
    REJECTS = [
        "Contact sales", "Start accepting payments",
        "from scaling startups to global enterprises",
        # neighbouring conversion CTAs / scope phrases:
        "Get started", "Book a demo", "Talk to sales", "Learn more",
        "Sign Up", "Read Docs", "businesses of all sizes",
        # controls the predicate already rejected before this change:
        "Test Failed", "No credit card needed",
    ]
    # Real benefit rows delivered across the corpus (must still be ACCEPTED):
    ACCEPTS = [
        "Export to Premiere and DaVinci",           # opens with a verb
        "Trim, split, speed, opacity, and transform",
        "Multi-track video, audio, image, and text",
        "AI images, videos, and audio", "directly in the timeline",
        "AI native backend platform",
        "exposes the backend through an MCP server",
        "How Zeabur shipped a RAG-powered forum",
        "Hermes builds a personalized AI email platform",
        "How Peak Mojo replaced NoSQL",
        "$25 / month", "100,000 monthly active users",
        "$10 in InsForge Compute credits included", "Most Popular",
    ]

    def test_ctas_and_scope_phrases_are_rejected(self):
        for s in self.REJECTS:
            self.assertFalse(pw._is_benefit_shaped(s),
                             f"should reject {s!r}")

    def test_real_benefits_are_accepted(self):
        for s in self.ACCEPTS:
            self.assertTrue(pw._is_benefit_shaped(s),
                            f"should accept {s!r}")

    def test_stripe_rescue_check_list_now_ticks_nothing(self):
        # The whole point: the beat whose only rows were CTAs/scope now has no
        # tickable material, so the film cannot tick a CTA as a benefit.
        beat = {"motif": "check-list", "title": "Unified, global payments",
                "details": ["Start accepting payments", "Contact sales",
                            "from scaling startups to global enterprises"]}
        self.assertEqual(pw._tickable(beat["details"]), [])
        self.assertEqual(pw._lint_ticks([beat]), [])


class TickedClaim(unittest.TestCase):
    """TASK 2b — the claim describes reality: it says "check" (the render draws
    the mark in the brand ACCENT, never green), and it is only asserted when the
    film actually ticks something."""

    def test_claim_wording_drops_the_colour(self):
        claim = dict((n, c) for n, c, _ in pw._CHECKS)["ticked-items"]
        self.assertNotIn("green", claim)
        self.assertIn("check", claim)

    def test_no_ticked_beat_means_no_ticked_claim(self):
        # A film with no check-list/price-card beat must not assert the property
        # at all — the check is absent from the results, so _checks_from omits it
        # and the pass sentence cannot claim it.
        stops = [{"motif": "kinetic-line", "title": "See it live",
                  "details": []}]
        self.assertNotIn("ticked-items", pw._data_results(stops, [], 10.0))

    def test_ticked_beat_present_when_the_film_ticks(self):
        stops = [{"motif": "check-list", "title": "What it does",
                  "details": ["AI native backend platform",
                              "exposes the backend through an MCP server"]}]
        results = pw._data_results(stops, [], 10.0)
        self.assertIn("ticked-items", results)
        self.assertEqual(results["ticked-items"][1], [])   # clean, claim earned


class FindingText(unittest.TestCase):
    """TASK 1 — a finding's full text reaches the customer. The event TITLE may
    be shortened for the feed, but the DETAIL and the disclosure carry the whole
    sentence, so a customer never reads half a sentence about their own film."""

    LONG = ("a clean price-card would read far better here than the current "
            "treatment, which crowds four rows into a space built for two and "
            "loses the price entirely on a light world background")

    def test_title_clips_but_detail_and_disclosure_are_full(self):
        f = pw._finding(2, "Pricing", self.LONG, None)
        title = pw._finding_title(f)
        detail = pw._finding_detail(f, "title-match")
        self.assertLessEqual(len(title), pw._TITLE_CLIP)
        self.assertTrue(title.endswith("…"))
        self.assertIn(self.LONG, detail)           # detail carries it whole
        # the disclosure builders compose from f["issue"] directly:
        self.assertEqual(f["issue"], self.LONG)
        self.assertNotIn("…", "; ".join(x["issue"] for x in [f]))

    def test_short_finding_is_not_decorated_with_an_ellipsis(self):
        f = pw._finding(0, "Beat", "chip-sweep below material floor", None)
        self.assertFalse(pw._finding_title(f).endswith("…"))

    def test_ticked_finding_keeps_the_whole_row_text(self):
        # The _lint_ticks finding used to embed d[:40]; it must now carry the
        # full row so the disclosure names the actual offending line.
        row = ("this is a deliberately long non-benefit row that used to be "
               "sliced to forty characters before it ever reached the customer")
        f = pw._finding(0, "T", f"“{row}” is ticked but isn't a benefit")
        self.assertIn(row, f["issue"])
        self.assertIn(row, pw._finding_detail(f, "ticked-items"))


class UploadMime(unittest.TestCase):
    """RIDER — upload_object stamps an honest content-type on every extension it
    actually uploads (.json/.mp3 used to be labelled image/png)."""

    def _ctype_for(self, ext):
        import json as _json
        import tempfile
        import run_events as re_
        captured = {}

        def fake_if_req(method, path, body, ctype):
            if body and b"contentType" in body:
                captured["ctype"] = _json.loads(body).get("contentType")
            raise RuntimeError("short-circuit before any network call")

        orig = re_._if_req
        re_._if_req = fake_if_req
        try:
            fp = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
            fp.write(b"x")
            fp.close()
            re_.upload_object("k" + ext, fp.name)
            os.unlink(fp.name)
        finally:
            re_._if_req = orig
        return captured.get("ctype")

    def test_content_types(self):
        for ext, expect in [(".json", "application/json"),
                            (".mp3", "audio/mpeg"), (".mp4", "video/mp4"),
                            (".png", "image/png"), (".jpg", "image/jpeg"),
                            (".jpeg", "image/jpeg"), (".svg", "image/svg+xml"),
                            (".bin", "application/octet-stream")]:
            self.assertEqual(self._ctype_for(ext), expect, f"{ext} mislabelled")


if __name__ == "__main__":
    unittest.main()
