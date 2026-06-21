#!/usr/bin/env python3
"""Card-copy regression tests for remotion_codegen.py.

Covers three bugs surfaced by the overnight figma.com experiment (OVERNIGHT-LOG
Iteration 1):

  Bug 1 (HIGH) — `_section_label` treated a POSSESSIVE apostrophe ("Figma's") as an
                 opening quote, so a divider brief
                 "...with Figma's brand colors and the text 'Built for teams'"
                 rendered "S Brand Colors And The Text" instead of "Built for teams".
  Bug 2 (MED)  — closing CTA was a hardcoded "Start building" (Stripe-flavored),
                 wrong-domain and contradicting the brand-aware VO.
  Bug 3 (LOW)  — the `_default` palette has no `tagline`, so the open card subtitle
                 was blank for any non-kitted brand.

All $0 / offline.  Run:  python3 -m unittest tests.test_remotion_codegen_cardcopy -v
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import remotion_codegen as rc  # noqa: E402


class TestSectionLabel(unittest.TestCase):
    """Bug 1 — quote extraction must ignore possessive/intra-word apostrophes."""

    def test_possessive_then_quoted_phrase(self):
        # THE garble case. Must extract the trailing quoted phrase, not the possessive.
        brief = ("Simple animated divider with Figma's brand colors and the text "
                 "'Built for teams'")
        out = rc._section_label(brief)
        self.assertEqual(out, "Built for teams")
        # explicit anti-regression: the old garble must NOT appear
        self.assertNotIn("Brand Colors", out)
        self.assertFalse(out.lower().startswith("s "))

    def test_clean_single_quote(self):
        brief = "Simple animated divider with the text 'Built for developers'"
        self.assertEqual(rc._section_label(brief), "Built for developers")

    def test_no_quote_falls_back_to_keywords(self):
        # No quoted phrase -> keyword fallback (directive lead-ins stripped). Must be a
        # clean short label, and must NOT be empty-from-garble.
        brief = "A clean animated section transition showing the product dashboard"
        out = rc._section_label(brief)
        self.assertTrue(out)
        self.assertNotIn("'", out)
        # the directive words ("clean", "animated", "section", "transition", "showing")
        # are stripped; what remains is real content
        self.assertIn("Product", out)

    def test_multiple_quotes_prefers_last(self):
        brief = "Divider reading 'fast' then 'reliable' then 'Built for teams'"
        self.assertEqual(rc._section_label(brief), "Built for teams")

    def test_possessive_only_no_quote_is_ignored(self):
        # An apostrophe with NO real quoted phrase must not produce a possessive remnant.
        brief = "Show Stripe's developer tools and api panel"
        out = rc._section_label(brief)
        self.assertFalse(out.lower().startswith("s "))
        self.assertNotIn("'", out)

    def test_curly_quotes(self):
        self.assertEqual(
            rc._section_label("Divider with the text ‘Built for teams’"),
            "Built for teams")

    def test_double_quotes(self):
        self.assertEqual(
            rc._section_label('Divider with the text "Ship faster"'),
            "Ship faster")

    def test_apostrophe_anywhere_before_phrase(self):
        # Robust to MULTIPLE apostrophes before the intended quoted phrase.
        brief = "It's Figma's canvas and the text 'Real-time'"
        self.assertEqual(rc._section_label(brief), "Real-time")

    def test_empty_brief(self):
        self.assertEqual(rc._section_label(""), "")
        self.assertEqual(rc._section_label(None), "")


class TestCtaTitle(unittest.TestCase):
    """Bug 2 — CTA derived from the brief, never a hardcoded 'Start building'."""

    def test_design_brand_cta(self):
        out = rc._cta_title("Start designing for free at figma.com", "Figma")
        self.assertEqual(out, "Start designing")

    def test_stripe_brand_cta_unchanged(self):
        out = rc._cta_title(
            "Call to action: Start building with Stripe today – visit docs.stripe.com",
            "Stripe")
        self.assertEqual(out, "Start building")

    def test_cta_scaffold_stripped(self):
        self.assertEqual(rc._cta_title("CTA: Try Notion now", "Notion"), "Try Notion")

    def test_get_started_with_brand(self):
        self.assertEqual(rc._cta_title("Get started with Linear", "Linear"), "Get started")

    def test_ship_verb(self):
        self.assertEqual(
            rc._cta_title("Ship faster — deploy with Vercel", "Vercel"),
            "Ship faster")

    def test_no_verb_neutral_fallback(self):
        self.assertEqual(
            rc._cta_title("A closing card thanking the viewer", "Figma"),
            "Get started")

    def test_never_blank(self):
        for b in ("", None, "   ", ":::"):
            self.assertTrue(rc._cta_title(b, "Brand"))


class TestSynthTagline(unittest.TestCase):
    """Bug 3 — non-blank open-card subtitle for non-kitted brands."""

    def test_quoted_tagline_used(self):
        out = rc._synth_tagline(
            "Show Figma logo and tagline: 'Where teams design together'", "Figma")
        self.assertEqual(out, "Where teams design together")

    def test_no_quote_neutral_fallback(self):
        # No quoted tagline -> neutral, NOT a directive remnant ("Figma Logo And Brand").
        out = rc._synth_tagline("Show Figma logo and brand mark", "Figma")
        self.assertEqual(out, "See what you can build")

    def test_never_blank(self):
        for b in ("", None, "Show logo"):
            self.assertTrue(rc._synth_tagline(b, "Brand"))


class TestCopyFromBriefIntegration(unittest.TestCase):
    """End-to-end through _copy_from_brief: figma (default palette) fixed,
    kitted brands (Stripe/Linear/Notion/Vercel) unaffected."""

    def test_figma_default_palette_open_and_close(self):
        pal = rc.palette_for("https://figma.com")
        self.assertEqual(pal.get("_brand"), "generic")
        self.assertIsNone(pal.get("tagline"))  # _default has no tagline

        # open: synthesized subtitle, not blank
        title, subtitle, kicker, badge = rc._copy_from_brief(
            {"id": "title-opening", "type": "title"},
            "Show Figma logo and tagline: 'Where teams design together'", pal)
        self.assertEqual(title, "Figma")
        self.assertTrue(subtitle.strip(), "open-card subtitle must not be blank")
        self.assertEqual(subtitle, "Where teams design together")

        # close: brand-aware CTA, not "Start building"
        title, subtitle, kicker, badge = rc._copy_from_brief(
            {"id": "title-closing", "type": "title"},
            "Call to action: Start designing for free at figma.com", pal)
        self.assertEqual(title, "Start designing")
        self.assertNotEqual(title, "Start building")
        self.assertEqual(subtitle, "figma.com")

    def test_figma_open_no_quoted_tagline_not_blank(self):
        pal = rc.palette_for("https://figma.com")
        title, subtitle, _k, _b = rc._copy_from_brief(
            {"id": "title-opening", "type": "title"}, "Show Figma brand mark", pal)
        self.assertEqual(title, "Figma")
        self.assertTrue(subtitle.strip())  # never blank

    def test_figma_divider_garble_gone(self):
        # Bug 1 through the full path: the snappy divider that garbled.
        pal = rc.palette_for("https://figma.com")
        title, subtitle, kicker, badge = rc._copy_from_brief(
            {"id": "mg-1", "type": "motion_graphic"},
            "Simple animated divider with Figma's brand colors and the text "
            "'Built for teams'", pal)
        self.assertEqual(title, "Built for teams")
        self.assertNotIn("Brand Colors", title)

    def test_kitted_brands_unaffected(self):
        # Stripe / Linear / Notion / Vercel keep their REAL tagline on the open card,
        # and their close CTA is still derived correctly from the brief.
        cases = {
            "https://docs.stripe.com": ("Build internet businesses",
                                        "Call to action: Start building with Stripe today",
                                        "Start building"),
            "https://linear.app": ("Plan and build products",
                                   "Get started with Linear today",
                                   "Get started"),
            "https://notion.so": ("One workspace. Every team.",
                                  "Try Notion for free",
                                  "Try Notion"),
            "https://vercel.com": ("Develop. Preview. Ship.",
                                   "Start deploying with Vercel",
                                   "Start deploying"),
        }
        for url, (real_tagline, close_brief, expect_cta) in cases.items():
            pal = rc.palette_for(url)
            self.assertEqual(pal.get("tagline"), real_tagline,
                             f"{url}: kitted palette must keep its real tagline")
            # open card uses the REAL palette tagline (not a synthesized one)
            _t, subtitle, _k, _b = rc._copy_from_brief(
                {"id": "title-opening", "type": "title"}, "logo and tagline", pal)
            self.assertEqual(subtitle, real_tagline, f"{url}: open subtitle")
            # close CTA derived from the brief
            cta, _s, _k, _b = rc._copy_from_brief(
                {"id": "title-closing", "type": "title"}, close_brief, pal)
            self.assertEqual(cta, expect_cta, f"{url}: close CTA")

    def test_generate_compiles_for_garble_divider(self):
        # The full codegen path must still emit TSX (no exception) for the garble case.
        pal = rc.palette_for("https://figma.com")
        src, meta = rc.generate(
            {"id": "mg-1", "type": "motion_graphic", "duration_s": 3,
             "brief": "Simple animated divider with Figma's brand colors and the "
                      "text 'Built for teams'"}, pal)
        self.assertIn("Built for teams", src)
        self.assertNotIn("Brand Colors And The Text", src)
        self.assertEqual(meta["archetype"], "divider")


if __name__ == "__main__":
    unittest.main(verbosity=2)
