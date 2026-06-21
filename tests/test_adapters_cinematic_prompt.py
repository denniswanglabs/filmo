#!/usr/bin/env python3
"""Unit tests for the cinematic PROMPT BUILDER in adapters.py.

$0 — NO real Higgsfield calls. Exercises `cinematic_prompt(brief, palette, kind)`
and `detect_kind(scene)`, which operationalize the winning two-track formula from
the real gpt_image_2 A/B (OVERNIGHT-LOG Iteration 2; evidence/prompt-ab/).

Asserts the formula's invariants across both tracks and two brands (Stripe =
kitted/visually-rich, plus a generic/unkitted brand that falls back to the
`_default` palette):
  - cinematography scaffolding present in BOTH kinds
  - brand-accent hex injected ONLY for "establish"
  - anti-text guard present ONLY for "establish"
  - the raw brief is preserved verbatim in both
  - output is a single well-formed prompt string

Also asserts the iter-5 real-Seedance refinements on the "establish" track
(see .handoff-portfolio-2.md and TestEstablishIter5Refinements below):
  - a SINGLE-HERO composition cue is present (and multi-element layouts steered off)
  - NO positive UI-text noun appears anywhere except the trailing pure-negative
    "no text ..." clause
  - the injected brand accent is SATURATED/vivid (a "vivid saturated" cue + a
    saturation-boosted hex), with hue preserved
  - the "hero" (gpt_image_2) track is UNCHANGED by the refinements

Also asserts the iter-7 v3 COLOR-DOMINANCE refinement on the "establish" track
(see .handoff-portfolio-3.md and TestEstablishV3ColorDominance below):
  - a whole-frame COLOR-DOMINANCE grade phrase is present (the entire scene
    graded/bathed in the brand accent — haze/reflections/background tinted that
    color), so even a MUTED brand hue (Shopify olive) reads clearly as its color
  - the phrase REFERENCES the brand color (a plain-English color NAME + the
    saturated hex), because a hex alone under-steers a muted hue
  - the existing single-hero cue, the no-positive-text-noun rule, and the
    trailing pure-negative all remain intact
  - the "hero" (gpt_image_2) track is STILL byte-for-byte UNCHANGED

Also proves the MOCK generation path is signature-/behavior-unchanged by the new
`company_url` kwarg.

Run: python3 -m unittest tests.test_adapters_cinematic_prompt
"""

import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import adapters  # noqa: E402
import remotion_codegen  # noqa: E402

# Real verbatim brief from runs/demo-1-approve/plan.json `cine-hero-still`.
HERO_BRIEF = "Clean hero plate of the Stripe Dashboard developer tools"
# Real verbatim brief from `cine-establish` (the establishing/abstract plate).
ESTABLISH_BRIEF = "Sweeping look at a global payments network powering businesses"

STRIPE = remotion_codegen.palette_for("https://docs.stripe.com")        # kitted
GENERIC = remotion_codegen.palette_for("https://acme-unkitted-co.example")  # _default

# A fragment of the fixed cinematography scaffolding, guaranteed present in both
# tracks. (Substring, not full string, so the test survives minor wording tweaks.)
CINE_MARKER = "50mm"
# The anti-text steer is now a TRAILING pure-negative clause (iter-5: never name a
# text noun positively). "no wordmarks" is the durable marker for "anti-text on".
ANTI_TEXT_MARKER = "no wordmarks"

# The single-hero composition cue marker (iter-5: bias to one focal object).
SINGLE_HERO_MARKER = "single hero object"

# Positive UI-text nouns that must NEVER appear positively in an establish prompt
# (even qualified). They are allowed ONLY inside the trailing pure-negative
# "no text, no words, ..." clause, which the test slices off before scanning.
FORBIDDEN_TEXT_NOUNS = (
    "interface text", "readable", "label", "caption", "headline",
    "wordmark", "watermark", "placeholder text", "lettering", "typeface",
)


class TestCinematicPromptHero(unittest.TestCase):
    """kind="hero": cinematography scaffolding only — NO brand hex, NO anti-text."""

    def _check_hero(self, palette):
        p = adapters.cinematic_prompt(HERO_BRIEF, palette, "hero")
        # well-formed: non-empty single string, ends cleanly.
        self.assertIsInstance(p, str)
        self.assertTrue(p.strip())
        self.assertTrue(p.endswith("."))
        # brief preserved verbatim, at the front.
        self.assertIn(HERO_BRIEF, p)
        self.assertTrue(p.startswith(HERO_BRIEF))
        # cinematography scaffolding present.
        self.assertIn(CINE_MARKER, p)
        # NO anti-text clause for hero.
        self.assertNotIn(ANTI_TEXT_MARKER, p)
        self.assertNotIn("no wordmarks", p)
        return p

    def test_hero_stripe(self):
        p = self._check_hero(STRIPE)
        # NO brand hex injected for hero (even for a kitted brand).
        self.assertNotIn(STRIPE["accent"], p)
        self.assertNotIn(STRIPE["accent2"], p)

    def test_hero_generic(self):
        p = self._check_hero(GENERIC)
        self.assertNotIn(GENERIC["accent"], p)
        self.assertNotIn(GENERIC["accent2"], p)


class TestCinematicPromptEstablish(unittest.TestCase):
    """kind="establish": scaffolding + brand hex + anti-text + title room."""

    def _check_establish(self, palette):
        p = adapters.cinematic_prompt(ESTABLISH_BRIEF, palette, "establish")
        self.assertIsInstance(p, str)
        self.assertTrue(p.strip())
        self.assertTrue(p.endswith("."))
        # brief preserved verbatim, at the front.
        self.assertIn(ESTABLISH_BRIEF, p)
        self.assertTrue(p.startswith(ESTABLISH_BRIEF))
        # cinematography scaffolding present (same as hero).
        self.assertIn(CINE_MARKER, p)
        # anti-text guard present (ONLY for establish).
        self.assertIn(ANTI_TEXT_MARKER, p)
        # negative-space-for-title note present.
        self.assertIn("title", p.lower())
        return p

    def test_establish_stripe(self):
        p = self._check_establish(STRIPE)
        # brand accent hexes injected (ONLY for establish) — iter-5: SATURATED.
        self.assertIn(adapters._saturate_hex(STRIPE["accent"]), p)    # #635BFF -> vivid
        self.assertIn(adapters._saturate_hex(STRIPE["accent2"]), p)   # #80E9FF -> vivid

    def test_establish_generic(self):
        p = self._check_establish(GENERIC)
        # generic/unkitted brand still gets ITS (_default) accents injected, vivid.
        self.assertIn(adapters._saturate_hex(GENERIC["accent"]), p)   # #7CFFB2 -> vivid
        self.assertIn(adapters._saturate_hex(GENERIC["accent2"]), p)  # #9A8CFF -> vivid


class TestCinematicPromptCrossKind(unittest.TestCase):
    """Cross-track invariants the formula depends on."""

    def test_anti_text_only_for_establish(self):
        hero = adapters.cinematic_prompt(HERO_BRIEF, STRIPE, "hero")
        est = adapters.cinematic_prompt(ESTABLISH_BRIEF, STRIPE, "establish")
        self.assertNotIn(ANTI_TEXT_MARKER, hero)
        self.assertIn(ANTI_TEXT_MARKER, est)

    def test_brand_hex_only_for_establish(self):
        hero = adapters.cinematic_prompt(HERO_BRIEF, STRIPE, "hero")
        est = adapters.cinematic_prompt(ESTABLISH_BRIEF, STRIPE, "establish")
        sat = adapters._saturate_hex(STRIPE["accent"])
        # No brand hex (raw OR saturated) in the hero track.
        self.assertNotIn(STRIPE["accent"], hero)
        self.assertNotIn(sat, hero)
        # establish gets the SATURATED brand hex (iter-5 refinement 3).
        self.assertIn(sat, est)

    def test_cinematography_in_both(self):
        hero = adapters.cinematic_prompt(HERO_BRIEF, STRIPE, "hero")
        est = adapters.cinematic_prompt(ESTABLISH_BRIEF, STRIPE, "establish")
        self.assertIn(CINE_MARKER, hero)
        self.assertIn(CINE_MARKER, est)

    def test_unknown_kind_treated_as_establish(self):
        # Any non-"hero" kind must take the safer establish track (anti-text on).
        p = adapters.cinematic_prompt(ESTABLISH_BRIEF, STRIPE, "weird")
        self.assertIn(ANTI_TEXT_MARKER, p)
        self.assertIn(adapters._saturate_hex(STRIPE["accent"]), p)

    def test_empty_brief_still_well_formed(self):
        # No brief: still a valid prompt (scaffolding-only) that doesn't crash or
        # start with a stray separator.
        p = adapters.cinematic_prompt("", STRIPE, "hero")
        self.assertIsInstance(p, str)
        self.assertTrue(p.strip())
        self.assertIn(CINE_MARKER, p)
        self.assertFalse(p.startswith("."))

    def test_missing_palette_establish_no_crash(self):
        # establish with a palette lacking accents -> no hex line, but valid + anti-text.
        p = adapters.cinematic_prompt(ESTABLISH_BRIEF, {}, "establish")
        self.assertIn(ANTI_TEXT_MARKER, p)
        self.assertIn(ESTABLISH_BRIEF, p)
        self.assertTrue(p.endswith("."))


class TestEstablishIter5Refinements(unittest.TestCase):
    """The three iter-5 real-Seedance refinements on the establish track.

    See .handoff-portfolio-2.md:
      1. SINGLE-HERO framing — multi-element "array of cards" layouts garble.
      2. NO positive UI-text nouns — naming text (even "blurred labels") cues it.
      3. SATURATED brand hex — desaturated brand colors steer to the wrong hue.
    """

    # Real desaturated brand color from iter-5 (Shopify olive read as orange).
    SHOPIFY = dict(remotion_codegen.palette_for("https://shopify.com"),
                   accent="#5E8E3E", accent2="#95BF47")
    # Real already-saturated brand color from iter-5 (Robinhood steered cleanly).
    ROBINHOOD = dict(remotion_codegen.palette_for("https://robinhood.com"),
                     accent="#00C805", accent2="#7BF1A8")

    # --- Refinement 1: single-hero composition cue -------------------------

    def test_single_hero_cue_present_in_establish(self):
        p = adapters.cinematic_prompt(ESTABLISH_BRIEF, STRIPE, "establish")
        self.assertIn(SINGLE_HERO_MARKER, p.lower())

    def test_establish_steers_off_multi_element_layouts(self):
        # The cue must NEGATE the garble-prone multi-element compositions.
        p = adapters.cinematic_prompt(ESTABLISH_BRIEF, STRIPE, "establish").lower()
        self.assertIn("no array of cards", p)
        self.assertIn("no grid of panels", p)

    def test_single_hero_cue_absent_from_hero_track(self):
        # The hero (gpt_image_2) track is unchanged — no single-hero cue there.
        p = adapters.cinematic_prompt(HERO_BRIEF, STRIPE, "hero")
        self.assertNotIn(SINGLE_HERO_MARKER, p.lower())

    # --- Refinement 2: never name a UI-text noun positively ----------------

    def _body_before_no_text(self, prompt):
        """Everything before the trailing pure-negative no-text clause.

        The pure-negative clause is the ONLY place a text noun may appear (as an
        exclusion). Splitting on its anchor lets us scan the positive body alone.
        """
        anchor = "no text, no words"
        self.assertIn(anchor, prompt, "trailing pure-negative no-text clause missing")
        return prompt.split(anchor)[0]

    def test_no_positive_ui_text_noun_in_establish_body(self):
        for name, pal in (("stripe", STRIPE), ("generic", GENERIC),
                          ("shopify", self.SHOPIFY), ("robinhood", self.ROBINHOOD)):
            p = adapters.cinematic_prompt(ESTABLISH_BRIEF, pal, "establish")
            body = self._body_before_no_text(p).lower()
            for noun in FORBIDDEN_TEXT_NOUNS:
                self.assertNotIn(
                    noun, body,
                    "positive UI-text noun %r leaked into establish body (%s): %s"
                    % (noun, name, body))

    def test_no_text_steer_is_trailing_pure_negative(self):
        # The anti-text steer is expressed ONLY as exclusions, at the END.
        p = adapters.cinematic_prompt(ESTABLISH_BRIEF, STRIPE, "establish")
        self.assertIn("no text", p)
        self.assertIn("no words", p)
        self.assertIn("no wordmarks", p)
        self.assertIn("no watermarks", p)
        self.assertIn("no ui labels", p.lower())
        # ... and it sits at the very end of the prompt (trailing).
        tail = p.rsplit(". ", 1)[-1].lower()
        self.assertTrue(tail.startswith("no text"),
                        "no-text clause is not the trailing segment: %r" % tail)

    def test_establish_has_no_legible_text_phrasing(self):
        # The OLD positive phrasing ("interface text illegible") is gone — that
        # named "interface text", which itself cues text rendering.
        p = adapters.cinematic_prompt(ESTABLISH_BRIEF, STRIPE, "establish").lower()
        self.assertNotIn("interface text", p)
        self.assertNotIn("illegible", p)
        self.assertNotIn("placeholder label", p)

    # --- Refinement 3: saturated / vivid brand hex -------------------------

    def test_vivid_saturated_cue_present(self):
        p = adapters.cinematic_prompt(ESTABLISH_BRIEF, self.SHOPIFY, "establish").lower()
        self.assertIn("vivid saturated", p)

    def test_desaturated_brand_hex_is_boosted(self):
        # Shopify olive #5E8E3E is desaturated; the injected hex must be MORE
        # saturated (and the muted original must NOT appear verbatim).
        p = adapters.cinematic_prompt(ESTABLISH_BRIEF, self.SHOPIFY, "establish")
        boosted = adapters._saturate_hex("#5E8E3E")
        self.assertNotEqual(boosted.upper(), "#5E8E3E")
        self.assertIn(boosted, p)
        self.assertNotIn("#5E8E3E", p)  # the muted original is not injected

    def test_saturation_increases_and_preserves_hue(self):
        import colorsys
        for hex_in in ("#5E8E3E", "#95BF47", "#635BFF", "#80E9FF"):
            out = adapters._saturate_hex(hex_in)
            ri, gi, bi = (int(hex_in[i:i + 2], 16) / 255.0 for i in (1, 3, 5))
            ro, go, bo = (int(out[i:i + 2], 16) / 255.0 for i in (1, 3, 5))
            hi, si, vi = colorsys.rgb_to_hsv(ri, gi, bi)
            ho, so, vo = colorsys.rgb_to_hsv(ro, go, bo)
            self.assertGreaterEqual(so + 1e-6, si, "%s: saturation dropped" % hex_in)
            # hue preserved (within rounding from the 8-bit round-trip).
            self.assertAlmostEqual(ho, hi, delta=0.02,
                                   msg="%s: hue shifted %.3f->%.3f" % (hex_in, hi, ho))

    def test_already_saturated_hex_essentially_unchanged(self):
        # Robinhood #00C805 is already vivid — the boost must not distort it.
        self.assertEqual(adapters._saturate_hex("#00C805").upper(), "#00C805")

    def test_saturate_hex_handles_garbage(self):
        # Never raises; non-hex input returned uppercased/stripped, pure grey kept.
        self.assertEqual(adapters._saturate_hex("not-a-hex"), "NOT-A-HEX")
        self.assertEqual(adapters._saturate_hex(""), "")
        self.assertEqual(adapters._saturate_hex(None), "")
        # Pure grey has no hue to preserve -> returned unchanged.
        self.assertEqual(adapters._saturate_hex("#808080").upper(), "#808080")

    def test_hero_track_unchanged_by_iter5(self):
        # The whole point: refinements touch establish ONLY. Hero = brief +
        # scaffolding, period. No single-hero cue, no hex, no saturation cue, no
        # no-text clause.
        p = adapters.cinematic_prompt(HERO_BRIEF, self.SHOPIFY, "hero")
        self.assertTrue(p.startswith(HERO_BRIEF))
        self.assertIn(CINE_MARKER, p)
        self.assertNotIn(SINGLE_HERO_MARKER, p.lower())
        self.assertNotIn("vivid saturated", p.lower())
        self.assertNotIn("no wordmarks", p)
        self.assertNotIn("no text", p)
        # No brand hex (raw or boosted) in the hero plate.
        self.assertNotIn(self.SHOPIFY["accent"], p)
        self.assertNotIn(adapters._saturate_hex(self.SHOPIFY["accent"]), p)
        # Hero is exactly brief + scaffolding (two sentences) — nothing appended.
        self.assertEqual(p, HERO_BRIEF + ". " + adapters._CINE_SCAFFOLD + ".")


class TestEstablishV3ColorDominance(unittest.TestCase):
    """The COLOR-DOMINANCE refinement on the establish track (v3 + iter-8 v4).

    See .handoff-portfolio-3.md: a SATURATED hex alone under-steered for a MUTED
    brand hue — Shopify's olive `#5E8E3E` rendered amber/purple even after the
    saturation boost, because the model's default cool-studio + warm-rim look beat
    a mere rim-light accent. v3's fix: grade the WHOLE FRAME toward the brand
    accent (the dominant scene color, not just a rim) and NAME the color.

    iter-8 (`.handoff-portfolio-4.md`): v3's NAME *over*-steered an in-between hue
    — the bare prototype "green" pulled Shopify olive to bright teal (~74° off) on
    real Seedance, because the coarse 12-name wheel mis-named ~96° olive as plain
    "green" AND the repeated bare name out-voted the hex. v4 fixes both: a FINER
    hue wheel returns a SPECIFIC name ("olive green") and the grade PAIRS that name
    with its hex ("olive green (#468E15)") so neither anchor out-weights the other.
    """

    SHOPIFY = dict(remotion_codegen.palette_for("https://shopify.com"),
                   accent="#5E8E3E", accent2="#95BF47")
    NVIDIA = dict(remotion_codegen.palette_for("https://nvidia.com"),
                  accent="#76B900", accent2="#A4D233")

    # --- the color-dominance grade phrase --------------------------------

    def test_color_dominance_phrase_present_in_establish(self):
        # The whole-frame grade must appear (not just the rim-light scaffold).
        for name, pal in (("stripe", STRIPE), ("generic", GENERIC),
                          ("shopify", self.SHOPIFY), ("nvidia", self.NVIDIA)):
            p = adapters.cinematic_prompt(ESTABLISH_BRIEF, pal, "establish").lower()
            self.assertIn("dominant color", p,
                          "color-dominance grade missing (%s)" % name)
            # "the entire scene bathed in ... light" — whole frame, not a rim.
            self.assertIn("the entire scene bathed in", p,
                          "whole-frame bathing phrase missing (%s)" % name)
            # haze/reflections/background tinted toward the accent.
            self.assertIn("tinting the volumetric haze", p, name)
            self.assertIn("the reflections and the background", p, name)

    def test_color_dominance_references_brand_color_name(self):
        # The phrase must NAME the brand color (plain English), the v3 lever — and
        # v4 makes the name SPECIFIC: Shopify olive -> "olive green" (NOT bare
        # "green", the iter-8 over-steer fix); NVIDIA -> "lime"; Stripe -> "blue".
        cases = ((self.SHOPIFY, "olive green"), (self.NVIDIA, "lime"),
                 (STRIPE, "blue"))
        for pal, name in cases:
            p = adapters.cinematic_prompt(ESTABLISH_BRIEF, pal, "establish").lower()
            self.assertIn("%s-dominant color grade" % name, p,
                          "expected %r color-name grade for %s" % (name, pal["accent"]))
            # v4 pairs the specific name WITH its hex: "bathed in <name> (#hex) light".
            self.assertIn("bathed in %s" % name, p)

    def test_color_dominance_references_saturated_hex(self):
        # The grade also references the SATURATED primary accent hex (name+hex).
        p = adapters.cinematic_prompt(ESTABLISH_BRIEF, self.SHOPIFY, "establish")
        sat = adapters._saturate_hex(self.SHOPIFY["accent"])  # #468E15
        self.assertIn(sat, p)
        # the hex appears parenthetically inside the dominance grade, after the name.
        grade = p.lower().split("dominant color grade", 1)[1]
        self.assertIn(sat.lower(), grade)

    def test_v4_pairs_specific_name_with_hex_both_anchors(self):
        # iter-8 fix: v3 repeated the BARE name (e.g. "green") ~5x and the hex 1x,
        # so the name out-voted the hex and over-steered. v4 PAIRS the specific
        # name with its hex — "olive green (#468E15)" — wherever it anchors the
        # color, so both the precise word and the exact hue carry comparable weight.
        sat = adapters._saturate_hex(self.SHOPIFY["accent"]).lower()  # #468e15
        grade = adapters._color_dominance("olive green", [sat]).lower()
        paired = "olive green (%s)" % sat
        # The name+hex pair appears at BOTH the "bathed in" anchor and the
        # "single dominant color" anchor (the hex rides alongside the name twice).
        self.assertEqual(grade.count(paired), 2,
                         "name+hex pair should anchor the grade twice, got: %r" % grade)
        # The hex is repeated alongside the name (>=2x) rather than once vs a
        # 5x-repeated bare name — closing the v3 name-out-weights-hex imbalance.
        self.assertGreaterEqual(grade.count(sat), 2)
        # Every standalone name occurrence beyond the grade label is hex-paired:
        # name appears 3x (label + 2 anchors), hex 2x (both anchors).
        self.assertEqual(grade.count("olive green"), 3)
        self.assertEqual(grade.count(sat), 2)

    def test_v4_does_not_repeat_a_bare_generic_color_word(self):
        # The bare hue word ("green") must not be spammed standalone (that was the
        # v3 over-steer). It may appear only as part of the specific name
        # "olive green" — never as a free-standing repeated token.
        grade = adapters._color_dominance("olive green", ["#468e15"]).lower()
        # Every "green" occurrence must be immediately preceded by "olive ".
        idx = 0
        while True:
            idx = grade.find("green", idx)
            if idx == -1:
                break
            self.assertEqual(grade[max(0, idx - 6):idx], "olive ",
                             "bare 'green' token leaked at %d in %r" % (idx, grade))
            idx += 5

    def test_muted_olive_reads_olive_not_amber_or_teal(self):
        # The headline iter-7/8 case: Shopify olive must be graded as OLIVE GREEN
        # end-to-end (v4 fixes v3's bare "green", which over-steered to teal), and
        # must NOT introduce a competing warm-rim color word into the prompt.
        p = adapters.cinematic_prompt(ESTABLISH_BRIEF, self.SHOPIFY, "establish").lower()
        self.assertIn("olive green-dominant color grade", p)
        # v4 pairs the specific name with its hex as the dominant-color anchor.
        self.assertIn(
            "olive green (#468e15) as the single dominant color of the whole frame", p)
        # The build must not name amber/orange/copper/purple (warm rim) NOR teal/
        # emerald (the v3 cool over-steer the specific name is meant to prevent).
        for bad in ("amber", "copper", "orange", "purple", "teal", "emerald"):
            self.assertNotIn(bad, p, "competing/over-steer color %r leaked" % bad)

    # --- v3 must NOT regress the iter-5 invariants ------------------------

    def test_v3_keeps_single_hero_cue(self):
        p = adapters.cinematic_prompt(ESTABLISH_BRIEF, self.SHOPIFY, "establish").lower()
        self.assertIn(SINGLE_HERO_MARKER, p)
        self.assertIn("no array of cards", p)
        self.assertIn("no grid of panels", p)

    def test_v3_keeps_no_positive_text_noun_rule(self):
        # The color-dominance phrase is abstract (light/haze/reflections) — it must
        # not introduce ANY positive UI-text noun before the trailing exclusions.
        for name, pal in (("shopify", self.SHOPIFY), ("nvidia", self.NVIDIA),
                          ("stripe", STRIPE), ("generic", GENERIC)):
            p = adapters.cinematic_prompt(ESTABLISH_BRIEF, pal, "establish")
            anchor = "no text, no words"
            self.assertIn(anchor, p)
            body = p.split(anchor)[0].lower()
            for noun in FORBIDDEN_TEXT_NOUNS:
                self.assertNotIn(noun, body,
                                 "v3 leaked text noun %r into body (%s)" % (noun, name))

    def test_v3_keeps_trailing_pure_negative(self):
        p = adapters.cinematic_prompt(ESTABLISH_BRIEF, self.SHOPIFY, "establish")
        tail = p.rsplit(". ", 1)[-1].lower()
        self.assertTrue(tail.startswith("no text"),
                        "no-text clause no longer trailing: %r" % tail)

    def test_v3_keeps_saturated_palette_line(self):
        # The existing "vivid saturated brand-accent palette: <hex>" line stays.
        p = adapters.cinematic_prompt(ESTABLISH_BRIEF, self.SHOPIFY, "establish").lower()
        self.assertIn("vivid saturated brand-accent palette", p)

    # --- color-dominance absent without a brand accent / on hero track ---

    def test_no_color_dominance_without_accent(self):
        # No accents -> no palette line AND no dominance grade (nothing to grade).
        p = adapters.cinematic_prompt(ESTABLISH_BRIEF, {}, "establish").lower()
        self.assertNotIn("dominant color", p)
        # still a valid establish prompt (anti-text + brief intact).
        self.assertIn(ANTI_TEXT_MARKER, p)

    def test_color_dominance_absent_from_hero_track(self):
        p = adapters.cinematic_prompt(HERO_BRIEF, self.SHOPIFY, "hero").lower()
        self.assertNotIn("dominant color", p)
        self.assertNotIn("bathed in", p)

    def test_hero_track_still_byte_identical_after_v3(self):
        # The whole point of v3: establish-only. Hero = brief + scaffolding, exact.
        p = adapters.cinematic_prompt(HERO_BRIEF, self.SHOPIFY, "hero")
        self.assertEqual(p, HERO_BRIEF + ". " + adapters._CINE_SCAFFOLD + ".")

    # --- _color_name helper ----------------------------------------------

    def test_color_name_maps_common_hues(self):
        # v4: a FINER hue wheel returns SPECIFIC names. Shopify olive (~96°) must
        # land on "olive green" (NOT bare "green" — that was the iter-8 over-steer).
        self.assertEqual(adapters._color_name("#5E8E3E"), "olive green")  # Shopify olive (raw)
        self.assertEqual(adapters._color_name("#468E15"), "olive green")  # Shopify olive (sat)
        self.assertEqual(adapters._color_name("#00C805"), "green")        # Robinhood, true green
        # NVIDIA #76B900 (~82°) is a lime/yellow-green — "lime" satisfies lime/green.
        self.assertEqual(adapters._color_name("#76B900"), "lime")         # NVIDIA
        self.assertEqual(adapters._color_name("#635BFF"), "blue")         # Stripe (blue/indigo)
        # Slack aubergine #4A154B: dark muted purple -> its specific prototype.
        self.assertEqual(adapters._color_name("#4A154B"), "aubergine")    # Slack

    def test_color_name_olive_is_not_bare_green(self):
        # The crux of v4: an in-between warm green must NOT collapse to "green",
        # which on real Seedance dragged the whole frame to teal/emerald.
        for olive in ("#5E8E3E", "#468E15"):
            name = adapters._color_name(olive)
            self.assertIn("olive", name, "expected an olive name for %s" % olive)
            self.assertNotEqual(name, "green")

    def test_color_name_strong_primaries_sane(self):
        # Strong, unambiguous primaries keep simple, expected names.
        self.assertEqual(adapters._color_name("#FF0000"), "red")
        self.assertEqual(adapters._color_name("#00FF00"), "green")
        self.assertEqual(adapters._color_name("#0000FF"), "blue")
        self.assertEqual(adapters._color_name("#FF6B00"), "orange")
        self.assertEqual(adapters._color_name("#0A66C2"), "blue")   # LinkedIn

    def test_color_name_handles_grey_and_garbage(self):
        # Pure grey / near-black / unparseable -> "" (caller falls back to hex).
        self.assertEqual(adapters._color_name("#808080"), "")
        self.assertEqual(adapters._color_name("#000000"), "")
        self.assertEqual(adapters._color_name("not-a-hex"), "")
        self.assertEqual(adapters._color_name(""), "")
        self.assertEqual(adapters._color_name(None), "")

    def test_color_name_preserves_base_hue_through_saturation(self):
        # Saturating a muted hue must not change its BASE hue name (same brand
        # identity). v4 may add/drop an S/V qualifier ("muted"/"dark") across the
        # boost, but the underlying hue prototype must be stable, so compare the
        # _color_hue_name (the qualifier-free base).
        import colorsys

        def base_of(hx):
            hx2 = hx.lstrip("#")
            r, g, b = (int(hx2[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
            h, _, _ = colorsys.rgb_to_hsv(r, g, b)
            return adapters._color_hue_name(h * 360.0)

        for hex_in in ("#5E8E3E", "#95BF47", "#76B900", "#4A154B"):
            self.assertEqual(base_of(hex_in),
                             base_of(adapters._saturate_hex(hex_in)),
                             "base hue name shifted under saturation for %s" % hex_in)


class TestDetectKind(unittest.TestCase):
    """Scene -> track classification."""

    def test_hero_brief_detected(self):
        # The real hero-still scene (gpt_image_2, "hero plate ... dashboard").
        scene = {"id": "cine-hero-still", "model": "gpt_image_2", "brief": HERO_BRIEF}
        self.assertEqual(adapters.detect_kind(scene), "hero")

    def test_establish_brief_detected(self):
        # The real establishing scene (seedance, "Sweeping look ...").
        scene = {"id": "cine-establish", "model": "seedance_2_0", "brief": ESTABLISH_BRIEF}
        self.assertEqual(adapters.detect_kind(scene), "establish")

    def test_explicit_kind_overrides(self):
        scene = {"id": "x", "model": "gpt_image_2", "brief": HERO_BRIEF, "kind": "establish"}
        self.assertEqual(adapters.detect_kind(scene), "establish")

    def test_aerial_motion_plate(self):
        scene = {"id": "s", "model": "seedance_2_0", "brief": "Aerial drone shot over a city"}
        self.assertEqual(adapters.detect_kind(scene), "establish")

    def test_still_model_no_hint_defaults_hero(self):
        scene = {"id": "s", "model": "gpt_image_2", "brief": "A product on a table"}
        self.assertEqual(adapters.detect_kind(scene), "hero")

    def test_video_model_no_hint_defaults_establish(self):
        scene = {"id": "s", "model": "seedance_2_0", "brief": "A product on a table"}
        self.assertEqual(adapters.detect_kind(scene), "establish")

    def test_video_model_with_hero_hint_forced_to_establish(self):
        # The exact garble case: a VIDEO scene with hero/dashboard/UI hints must
        # NOT pick the hero (no-anti-text) track — Seedance garbles literal UI
        # text under motion. HERO_BRIEF carries "hero"/"dashboard"/"plate of".
        scene = {"id": "cine-hero-still", "model": "seedance_2_0", "brief": HERO_BRIEF}
        self.assertEqual(adapters.detect_kind(scene), "establish")

    def test_video_model_explicit_hero_kind_still_establish(self):
        # Even an explicit hero/dashboard hint cannot promote a video model to the
        # hero track — the anti-text guard is mandatory for any video gen.
        scene = {"id": "x", "model": "seedance_2_0", "brief": HERO_BRIEF, "kind": "hero"}
        self.assertEqual(adapters.detect_kind(scene), "establish")
        scene = {"id": "x", "model": "kling_3_0", "brief": "ui screenshot", "plate": "dashboard"}
        self.assertEqual(adapters.detect_kind(scene), "establish")

    def test_still_model_with_same_hero_hint_stays_hero(self):
        # Control: the gpt_image_2 still with the same hint still returns "hero"
        # (videotape-alpha renders literal UI text legibly).
        scene = {"id": "cine-hero-still", "model": "gpt_image_2", "brief": HERO_BRIEF}
        self.assertEqual(adapters.detect_kind(scene), "hero")


class TestMockPathUnaffectedByCompanyUrl(unittest.TestCase):
    """The new company_url kwarg must not touch the mock path (still $0)."""

    def test_mock_still_with_company_url(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "still.mp4")
            scene = {"id": "s2", "type": "cinematic", "model": "gpt_image_2", "duration_s": 2}
            res = adapters.generate_cinematic(scene, out, "mock",
                                              company_url="https://docs.stripe.com")
            self.assertFalse(res["real"])
            self.assertTrue(os.path.exists(out) and os.path.getsize(out) > 1000)
            # Mock must NOT touch higgsfield / write a sidecar.
            self.assertFalse(os.path.exists(out.rsplit(".", 1)[0] + ".higgsfield.json"))

    def test_mock_video_default_kwarg(self):
        # Existing call shape (no company_url) must behave exactly as before.
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "clip.mp4")
            scene = {"id": "s1", "type": "cinematic", "model": "seedance_2_0", "duration_s": 2}
            res = adapters.generate_cinematic(scene, out, "mock")
            self.assertFalse(res["real"])
            self.assertEqual(res["output_path"], out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
