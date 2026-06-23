"""Deterministic ($0) tests for style_fill.py (Phase 2 keystone).

No synth, no whisper, no render -- a hand-built alignment + plan + brand exercise
the STYLE REGISTRY (role->archetype), the data shapers, the theme mapping, and the
MERGE that emits the exact <Timeline> props contract. run_pipeline is tested with
do_align=False against a written alignment fixture (so it stays offline + free).
"""
import json
import os
import tempfile
import unittest

import style_fill
import build_timeline


def _brand():
    return {
        "brand": "Orinovate",
        "wordmark": "Orinovate",
        "tagline": "On-demand manufacturing",
        "palette": {
            "bg": "#ffffff", "accent": "#2563eb", "navy": "#1a3a5c",
            "text": "#0f2338",
        },
        "fonts": {"fontPrimary": "Inter, sans-serif"},
        "features": [
            {"label": "3D Printing", "value": "24h", "sub": "FDM / SLA"},
            {"label": "CNC Machining", "sub": "Milling"},
            {"label": "Sheet Metal", "sub": "Laser cut"},
            {"label": "Laser Sintering", "sub": "Titanium"},
            {"label": "EXTRA-IGNORED", "sub": "should not appear"},
        ],
        "cta_url": "orinovate.com",
    }


def _plan():
    return {
        "scenes": [
            {"id": "open", "role": "open",
             "data": {"kicker": "INTRODUCING", "title": "Quotes in seconds",
                      "punchWord": "seconds", "subtitle": "One upload."},
             "cues": [{"label": "title-in", "word": "quotes"},
                      {"label": "punch", "word": "seconds"}]},
            {"id": "caps", "role": "feature",
             "data": {"heading": "Ship in 24 hours", "headingAccent": "24 hours"},
             "cues": [{"label": "heading-in", "word": "ship"},
                      {"label": "card-1", "word": "printing"}]},
            {"id": "close", "role": "close",
             "data": {"title": "Start your quote", "punchWord": "quote"},
             "cues": [{"label": "title-in", "word": "quote"}]},
        ],
        "voiceover": {"voice": "v", "beats": [
            {"scene_id": "open", "text": "Quotes in seconds"},
            {"scene_id": "caps", "text": "Ship printing machining sheet laser"},
            {"scene_id": "close", "text": "Start your quote"},
        ]},
    }


def _alignment():
    """Hand-built alignment matching _plan beats; words carry beat_scene_id."""
    def w(word, s, e, sid):
        return {"word": word, "start_s": s, "end_s": e, "beat_scene_id": sid}
    words = [
        w("Quotes", 0.0, 0.4, "open"), w("in", 0.4, 0.6, "open"),
        w("seconds", 0.6, 1.2, "open"),
        w("Ship", 1.2, 1.6, "caps"), w("printing", 1.6, 2.0, "caps"),
        w("machining", 2.0, 2.4, "caps"), w("sheet", 2.4, 2.8, "caps"),
        w("laser", 2.8, 3.2, "caps"),
        w("Start", 3.2, 3.6, "close"), w("your", 3.6, 3.8, "close"),
        w("quote", 3.8, 4.4, "close"),
    ]
    beats = [
        {"scene_id": "open", "start_s": 0.0, "end_s": 1.2, "text": "Quotes in seconds"},
        {"scene_id": "caps", "start_s": 1.2, "end_s": 3.2, "text": "Ship printing machining sheet laser"},
        {"scene_id": "close", "start_s": 3.2, "end_s": 4.4, "text": "Start your quote"},
    ]
    return {"audio_path": "voiceover.mp3", "lang": "en",
            "total_duration_s": 4.4, "words": words, "beats": beats}


class TestRegistry(unittest.TestCase):
    def test_known_style_routes_roles(self):
        st = style_fill.STYLES["orinovate-kinetic-light"]
        self.assertEqual(st.archetype_for({"role": "open"}), style_fill.ARCH_HERO)
        self.assertEqual(st.archetype_for({"role": "close"}), style_fill.ARCH_HERO)
        # Animated feature beats route to the designed EXPLAINER card (title +
        # synthesized bullets), not the card-grid. The card-grid is reserved for
        # explicit capability/grid roles.
        self.assertEqual(st.archetype_for({"role": "feature"}), style_fill.ARCH_EXPLAINER)
        self.assertEqual(st.archetype_for({"type": "capabilities"}), style_fill.ARCH_CARD)
        # unknown role -> default archetype, never a crash.
        self.assertEqual(st.archetype_for({"role": "mystery"}), st.default_archetype)

    def test_walkthrough_routes_to_player_only_with_clip(self):
        # P2: a walkthrough/demo role earns the video PLAYER only when a real clip
        # exists; with no clip it falls back to the never-blank explainer card.
        st = style_fill.STYLES["orinovate-kinetic-light"]
        with_clip = {"role": "walkthrough", "data": {"videoSrc": "/tmp/walk.mp4"}}
        self.assertEqual(st.archetype_for(with_clip), style_fill.ARCH_WALKTHROUGH)
        # clip on the scene root (producer attaches output_path) also routes to player.
        root_clip = {"role": "demo", "output_path": "runs/x/walkthrough.mp4"}
        self.assertEqual(st.archetype_for(root_clip), style_fill.ARCH_WALKTHROUGH)
        # no clip -> never-blank fallback (designed explainer card).
        self.assertEqual(
            st.archetype_for({"role": "walkthrough"}), style_fill.ARCH_EXPLAINER)
        # the player shaper fills videoSrc + a muted clip + an on-brand overlay title.
        data = st.shape(with_clip, {"wordmark": "Stripe"})
        self.assertEqual(data["videoSrc"], "/tmp/walk.mp4")
        self.assertTrue(data["muteClip"])
        self.assertIn("Stripe", data["overlayTitle"])

    def test_unknown_style_raises(self):
        tl = build_timeline.build_timeline(_plan()["scenes"], _alignment())
        with self.assertRaises(KeyError):
            style_fill.build_props(tl, _plan(), _brand(), "no-such-style")


class TestShapers(unittest.TestCase):
    def test_hero_open_uses_copy_and_punch(self):
        d = style_fill._shape_hero(_plan()["scenes"][0], _brand())
        self.assertEqual(d["title"], "Quotes in seconds")
        self.assertEqual(d["punchWord"], "seconds")  # substring of title
        self.assertEqual(d["subtitle"], "One upload.")

    def test_hero_close_falls_back_to_cta_url(self):
        sc = {"id": "close", "role": "close", "data": {"title": "Start your quote"}}
        d = style_fill._shape_hero(sc, _brand())
        self.assertEqual(d["subtitle"], "orinovate.com")

    def test_hero_drops_punch_not_in_title(self):
        sc = {"id": "x", "role": "open", "data": {"title": "Hello", "punchWord": "WORLD"}}
        d = style_fill._shape_hero(sc, _brand())
        self.assertNotIn("punchWord", d)

    def test_cards_grid_from_brand_features(self):
        d = style_fill._shape_cards(_plan()["scenes"][1], _brand())
        self.assertEqual(len(d["cards"]), style_fill.CARD_COUNT)  # capped at 4
        self.assertEqual(d["cards"][0]["label"], "3D Printing")
        self.assertEqual(d["cards"][0]["value"], "24h")
        # exactly one accent card (first one promoted since none flagged).
        self.assertEqual(sum(1 for c in d["cards"] if c["accent"]), 1)
        self.assertTrue(d["cards"][0]["accent"])
        self.assertEqual(d["heading"], "Ship in 24 hours")


class TestR8NavLabelTitle(unittest.TestCase):
    """R8: a UI/nav-label or separator-joined nav pair must NEVER render as the
    hero title or subtitle. Root cause: _distinct_tagline synthesized a " · " join
    from nav-section feature labels (allbirds "Men's Shoes · Customer Favorites")."""

    def _nav_brand(self):
        # Mirrors the bad g7-allbirds brand_theme: features are nav-section labels.
        return {
            "name": "Allbirds", "wordmark": "Allbirds",
            "tagline": ("Allbirds: The world’s most comfortable shoes, flats, "
                        "and clothing made with natu"),  # truncated meta fragment
            "features": [
                {"title": "Men's Shoes", "sub": ""},
                {"title": "Customer Favorites", "sub": ""},
                {"title": "Apparel & Accessories", "sub": ""},
                {"title": "Women's Shoes", "sub": ""},
            ],
        }

    def test_is_ui_nav_label_catches_separators(self):
        for s in ("Men's Shoes · Customer Favorites",   # middot
                  "Help Center · Find a co-host",
                  "Added to Cart • New Arrivals",        # bullet
                  "Help Center | Find a co-host",              # pipe
                  "Homes on Airbnb – Become a host",     # en-dash
                  "Men's Shoes — Customer Favorites"):   # em-dash
            self.assertTrue(style_fill._is_ui_nav_label(s), "%r is a nav label" % s)

    def test_distinct_tagline_never_returns_nav_join(self):
        out = style_fill._distinct_tagline(self._nav_brand())
        self.assertNotIn("·", out)
        self.assertFalse(style_fill._is_ui_nav_label(out))

    def test_hero_open_rejects_nav_label_title(self):
        brand = self._nav_brand()
        vo = "Allbirds makes comfortable shoes from natural wool and tree fibers."
        sc = {"id": "opening-title", "role": "open", "data": {"_text": vo}}
        d = style_fill._shape_hero(sc, brand)
        self.assertFalse(style_fill._is_ui_nav_label(d["title"]),
                         "title leaked a nav label: %r" % d["title"])
        self.assertNotIn("·", d["title"])
        self.assertFalse(style_fill._is_ui_nav_label(d["subtitle"] or ""),
                         "subtitle leaked a nav label: %r" % d["subtitle"])
        # Grounded headline derived from the VO line (not the wordmark alone).
        self.assertIn("Allbirds", d["title"])

    def test_good_titles_pass_through(self):
        for good in ("Build internet businesses", "Plan and build products"):
            sc = {"id": "o", "role": "open", "data": {"title": good}}
            d = style_fill._shape_hero(sc, {"name": "Acme", "wordmark": "Acme"})
            self.assertEqual(d["title"], good)


class TestR9GroundedOpeningTitle(unittest.TestCase):
    """R9: the OPENING hero title is DERIVED from the grounded value-prop (the
    planner's opening VO beat), NOT from scraped feature/section labels. The negative
    nav-label denylist is replaced by a POSITIVE _looks_like_headline test — a short
    Title-Case noun-phrase section label ("Popular Picks", "Customer Favorites") is
    NOT eligible as the title, regardless of whether it was enumerated."""

    def _ecom_brand(self):
        # Mirrors the bad r8-allbirds brand_theme: tagline is a truncated meta
        # fragment, every feature is a rotating store-section label, no real H1.
        return {
            "name": "Allbirds", "brand": "Allbirds", "wordmark": None,
            "tagline": ("Allbirds: The world’s most comfortable shoes, flats, and "
                        "clothing made with natu"),  # truncated meta fragment
            "features": [
                {"title": "Popular Picks"}, {"title": "Men's"},
                {"title": "Women's"}, {"title": "All Sale"},
            ],
            "cta_url": "allbirds.com",
        }

    def test_looks_like_headline_rejects_section_labels(self):
        # The whole CLASS of Title-Case noun-phrase section labels — not an enumerated
        # denylist — must fail the positive headline test.
        for label in ("Popular Picks", "Customer Favorites", "New Arrivals",
                      "Best Sellers", "Featured", "Shop All", "Help Center",
                      "Men's Shoes", "Gift Guide", "Top Rated", "Most Loved",
                      "Trending Now", "All Sale", "Free Shipping", "Our Story"):
            self.assertFalse(style_fill._looks_like_headline(label),
                             "%r should NOT read as a headline" % label)

    def test_looks_like_headline_accepts_real_value_props(self):
        for good in ("Build internet businesses", "Plan and build products",
                     "Allbirds makes comfortable shoes from natural wool",
                     "Stripe processes payments in over 135 currencies",
                     "Plaid connects your apps to over 12,000 banks securely"):
            self.assertTrue(style_fill._looks_like_headline(good),
                            "%r should read as a headline" % good)

    def test_section_label_title_replaced_by_grounded_value_prop(self):
        brand = self._ecom_brand()
        vo = "Allbirds makes comfortable shoes from natural, sustainable materials."
        for raw in ("Popular Picks", "Customer Favorites", "New Arrivals",
                    "Best Sellers", "Featured", "Shop All",
                    "Men's Shoes · Customer Favorites"):
            sc = {"id": "title-open", "role": "open",
                  "data": {"title": raw, "_text": vo}}
            d = style_fill._shape_hero(sc, brand)
            # The scraped section label is REJECTED and the grounded value-prop wins.
            self.assertNotEqual(d["title"], raw, "leaked section label %r" % raw)
            self.assertFalse(style_fill._is_ui_nav_label(d["title"]))
            self.assertTrue(style_fill._looks_like_headline(d["title"]),
                            "title is not a real headline: %r" % d["title"])
            self.assertIn("Allbirds makes comfortable shoes", d["title"])
            # Subtitle must not be a bare section label either.
            self.assertFalse(style_fill._is_ui_nav_label(d["subtitle"] or ""))
            self.assertFalse(style_fill._is_section_label_subtitle(d["subtitle"] or ""))

    def test_no_grounded_vo_falls_to_wordmark_not_section_label(self):
        # With a section-label raw title and NO grounded VO, fall to the wordmark/
        # brand — NEVER a scraped section label.
        brand = self._ecom_brand()
        sc = {"id": "title-open", "role": "open", "data": {"title": "Popular Picks"}}
        d = style_fill._shape_hero(sc, brand)
        self.assertNotEqual(d["title"], "Popular Picks")
        self.assertEqual(d["title"], "Allbirds")  # brand/name fallback

    def test_real_opening_headlines_pass_unchanged(self):
        for good in ("Build internet businesses", "Plan and build products",
                     "Allbirds makes comfortable shoes from natural wool"):
            sc = {"id": "o", "role": "open", "data": {"title": good}}
            d = style_fill._shape_hero(sc, {"name": "Acme", "wordmark": "Acme"})
            self.assertEqual(d["title"], good)


class TestR6NumeralNounAndFragmentSubtitle(unittest.TestCase):
    """R6 distiller residuals, fixed FORWARD in style_fill.

    FIX 1 — a number followed by a unit + noun must KEEP the noun. The R5 clause-end
    guard chopped "...over 800 million trusted reviews" down to "...over 800 million"
    (a dangling quantifier on screen); the later numeral guard then backed up past the
    WHOLE stat to "...access" — both drop the most compelling part of the headline.
    The complete numeric claim (number + magnitude + noun) is preserved instead, while
    a SOURCE that genuinely ends on a bare number still backs up (never a dangling tail).

    FIX 2 — a subtitle scrape fragment (lowercase-leading or preposition-final) is
    rejected and the salvage path falls back to the brand's real tagline / a complete
    leading sentence rather than rendering the fragment verbatim ("store they line up
    for", the Shopify residual)."""

    TRIPADVISOR_VO = ("Tripadvisor gives travelers access to over 800 million "
                      "trusted reviews.")

    # ---- FIX 1: a number + unit + noun keeps the noun ----
    def test_punchy_keeps_noun_completing_a_number(self):
        out = style_fill._punchy_headline(self.TRIPADVISOR_VO, limit=56)
        # The noun that COMPLETES the numeric claim must survive.
        self.assertTrue(out.endswith("trusted reviews"),
                        "dropped the noun completing the number: %r" % out)
        # NOT the R5 dangling-quantifier chop, and NOT the over-aggressive back-up.
        self.assertNotEqual(out, "Tripadvisor gives travelers access to over 800 million")
        self.assertNotEqual(out, "Tripadvisor gives travelers access")
        self.assertIn("800 million trusted reviews", out)

    def test_hero_opening_title_keeps_numeric_noun(self):
        # The real data.title path for a hero-title scene (grounded headline, limit=56).
        sc = {"id": "opening-title", "role": "open",
              "data": {"_text": self.TRIPADVISOR_VO}}
        d = style_fill._shape_hero(sc, {"name": "Tripadvisor", "wordmark": "Tripadvisor"})
        self.assertTrue(d["title"].endswith("trusted reviews"),
                        "hero title dropped the numeric noun: %r" % d["title"])
        self.assertNotEqual(
            d["title"], "Tripadvisor gives travelers access to over 800 million")

    def test_genuinely_dangling_number_still_backs_up(self):
        # When the SOURCE itself ends on a bare number (no completing noun), the guard
        # must still back up past the number phrase — never leave a dangling quantifier.
        out = style_fill._punchy_headline(
            "Tripadvisor gives travelers access to over 800 million", limit=56)
        self.assertFalse(out.rstrip(".").lower().endswith(("over", "800", "million")),
                         "left a dangling number tail: %r" % out)
        self.assertEqual(out, "Tripadvisor gives travelers access")

    def test_number_with_noun_unchanged_when_it_fits(self):
        # Regression guard: a short complete numeric value-prop is untouched.
        for s in ("Stripe processes payments in over 135 currencies",
                  "Plaid connects apps to over 12,000 banks"):
            self.assertEqual(style_fill._punchy_headline(s, limit=56), s)

    # ---- FIX 2: subtitle fragment is rejected + salvaged ----
    def test_is_fragment_subtitle_rejects_lowercase_and_prep_final(self):
        for frag in ("store they line up for",     # lowercase-leading + prep-final
                     "growth they line up for",     # prep-final
                     "The platform built with",     # preposition-final (capitalized)
                     "brands you can rely on",       # preposition-final
                     "everything you need to"):      # lowercase-leading + prep-final
            self.assertTrue(style_fill._is_fragment_subtitle(frag),
                            "%r should be rejected as a fragment" % frag)
        # Real, complete taglines are NOT rejected.
        for ok in ("Make commerce better for everyone", "For everyone.",
                   "On-demand manufacturing"):
            self.assertFalse(style_fill._is_fragment_subtitle(ok),
                             "%r is a valid tagline, not a fragment" % ok)

    def test_hero_opening_drops_fragment_subtitle(self):
        # Shopify residual: an explicit fragment subtitle must never render verbatim.
        sc = {"id": "opening-title", "role": "open",
              "data": {"title": "Try Shopify free.",
                       "subtitle": "store they line up for"}}
        d = style_fill._shape_hero(sc, {"name": "Shopify", "wordmark": "Shopify"})
        self.assertNotEqual(d["subtitle"], "store they line up for")
        self.assertFalse(style_fill._is_fragment_subtitle(d["subtitle"] or ""),
                         "subtitle is still a fragment: %r" % d["subtitle"])

    def test_hero_opening_salvages_fragment_subtitle_to_tagline(self):
        # When a real distinct tagline exists, a fragment subtitle is REPLACED by it
        # (fall back to the wordmark tagline) rather than blanked.
        brand = {"name": "Acme", "wordmark": "Acme",
                 "tagline": "Make commerce better for everyone"}
        sc = {"id": "opening-title", "role": "open",
              "data": {"title": "Try Acme free.",
                       "subtitle": "growth they line up for"}}
        d = style_fill._shape_hero(sc, brand)
        self.assertEqual(d["subtitle"], "Make commerce better for everyone")


class TestR10DanglingTailAndCtaDomain(unittest.TestCase):
    """R10-X: the opening-headline distiller must NOT chop mid-clause and leave a
    dangling tail (gerund "letting", relative "that", possessive "your", trailing
    comma), the CTA must KEEP its domain (".com"), and a homepage section label
    ("Quick Posts") must be rejected as the opening title in favor of the grounded
    value-prop."""

    # ---- FIX 1: dangling-tail guard — back up to a COMPLETE clause ----
    def test_punchy_drops_dangling_gerund_helper(self):
        out = style_fill._punchy_headline(
            "Linear makes product operations self-driving, letting teams move faster.",
            limit=56)
        self.assertEqual(out, "Linear makes product operations self-driving")
        self.assertFalse(out.rstrip(".").endswith("letting"))
        self.assertFalse(out.endswith(","))

    def test_punchy_drops_trailing_comma(self):
        out = style_fill._punchy_headline(
            "Notion is the connected workspace for docs, wikis, and projects.",
            limit=56)
        self.assertFalse(out.endswith(","), "left a trailing comma: %r" % out)
        self.assertTrue(out.startswith("Notion is the connected workspace"))

    def test_punchy_drops_dangling_possessive_and_relative(self):
        out = style_fill._punchy_headline(
            "Allbirds makes comfortable wool runners that keep your feet warm.",
            limit=56)
        self.assertEqual(out, "Allbirds makes comfortable wool runners")
        self.assertFalse(out.rstrip(".").lower().endswith(("your", "that", "keep your")))

    def test_punchy_backs_up_off_explicit_dangling_strings(self):
        # Each dangling source must back up to a complete clause (no dangling tail).
        for src, must_not_end in (
            ("Linear makes product operations self-driving, letting", "letting"),
            ("Notion is the connected workspace for docs, wikis,", ","),
            ("Allbirds makes comfortable wool runners that keep your feet warm", "your"),
            ("Huckberry curates rugged gear for men who", "who"),
            ("Vercel is the platform for", "for"),
        ):
            out = style_fill._punchy_headline(src, limit=56)
            self.assertTrue(out, "empty result for %r" % src)
            self.assertFalse(out.endswith(","), "trailing comma: %r" % out)
            last = out.split()[-1].lower().rstrip(",.")
            self.assertNotIn(last, style_fill._DANGLING_WORDS,
                             "dangling function word %r in %r" % (last, out))
            self.assertNotIn(last, style_fill._DANGLING_PARTICIPLES,
                             "dangling participle %r in %r" % (last, out))

    def test_complete_headlines_pass_unchanged(self):
        for good in ("Stripe powers businesses of all sizes",
                     "Build internet businesses"):
            self.assertEqual(style_fill._punchy_headline(good, limit=56), good)

    def test_strip_dangling_tail_helper(self):
        self.assertEqual(
            style_fill._strip_dangling_tail("Linear makes it self-driving, letting"),
            "Linear makes it self-driving")
        self.assertEqual(style_fill._strip_dangling_tail("docs, wikis,"), "docs, wikis")
        self.assertEqual(
            style_fill._strip_dangling_tail("keep your feet warm"), "keep your feet warm")

    # ---- FIX 2: CTA must KEEP the domain ----
    def test_punchy_keeps_cta_domain(self):
        for vo in ("Visit theverge.com", "Visit theverge.com.",
                   "Visit theverge.com for the latest tech news."):
            out = style_fill._punchy_headline(vo)
            self.assertIn("theverge.com", out, "dropped .com from %r -> %r" % (vo, out))

    def test_hero_close_keeps_cta_domain(self):
        sc = {"id": "close", "role": "close", "data": {"_text": "Visit theverge.com"}}
        d = style_fill._shape_hero(
            sc, {"name": "The Verge", "wordmark": "The Verge", "cta_url": "theverge.com"})
        self.assertIn("theverge.com", d["title"],
                      "CTA dropped the domain: %r" % d["title"])
        self.assertNotEqual(d["title"], "Visit theverge")

    def test_title_from_text_does_not_split_domain(self):
        # The "." inside a domain is NOT a sentence boundary.
        self.assertEqual(style_fill._title_from_text("Visit theverge.com"),
                         "Visit theverge.com")
        # A real sentence period still splits.
        self.assertEqual(
            style_fill._title_from_text("Build internet businesses. Sign up today."),
            "Build internet businesses")

    # ---- FIX 3: reject section-label-as-opening-title ----
    def test_section_label_opening_title_rejected(self):
        vo = ("The Verge covers technology, science, and culture with original "
              "reporting.")
        for raw in ("Quick Posts", "Featured", "Latest Stories"):
            self.assertFalse(style_fill._looks_like_headline(raw),
                             "%r should NOT read as a headline" % raw)
            sc = {"id": "title-open", "role": "open",
                  "data": {"title": raw, "_text": vo}}
            d = style_fill._shape_hero(sc, {"name": "The Verge", "wordmark": "The Verge"})
            self.assertNotEqual(d["title"], raw, "leaked section label %r" % raw)
            self.assertTrue(style_fill._looks_like_headline(d["title"]),
                            "title is not a real headline: %r" % d["title"])


class TestR11CtaStageDirection(unittest.TestCase):
    """R11: a self-referential STAGE-DIRECTION / meta-description must never render as
    the closing CTA. The planner's closing beat is sometimes a description of the card
    ("Closing call‑to‑action card urging users") rather than CTA copy; R7-G3's planner
    sanitizer caught only the "Show call-to-action:" verb-colon form. style_fill is the
    LAST line of defense — reject the meta-description and DERIVE a real brand-anchored
    imperative CTA, while real CTAs (incl. "Visit theverge.com" with its domain) pass."""

    _NOTION = {"name": "Notion", "wordmark": "Notion", "cta_url": "notion.so"}

    # robust to fancy unicode hyphens (U+2011 in the leaked notion title) + spaced form
    _STAGE_DIRECTIONS = (
        "Closing call‑to‑action card urging users",   # U+2011 non-breaking hyphen
        "Call-to-action card using the brand color",            # ASCII hyphen
        "Call to action card urging users to sign up",          # no hyphen at all
        "Closing card with the wordmark",
        "Show the CTA",
        "Display the call-to-action using the brand colour",
        "Animate the closing scene",
    )

    def test_detector_flags_stage_directions(self):
        for sd in self._STAGE_DIRECTIONS:
            self.assertTrue(style_fill._is_cta_stage_direction(sd),
                            "should flag stage direction: %r" % sd)

    def test_detector_is_hyphen_robust(self):
        # The SAME phrase with each hyphen variant must all flag.
        for hy in ("-", "‐", "‑", "‒", "–", "—", "―", "−"):
            s = "Closing call%sto%saction card" % (hy, hy)
            self.assertTrue(style_fill._is_cta_stage_direction(s),
                            "hyphen %r not handled: %r" % (hy, s))

    def test_detector_passes_real_ctas(self):
        for good in ("Shop Allbirds", "Begin your free trial",
                     "Start your trip on Tripadvisor", "Visit theverge.com",
                     "Start accepting payments", "Get started with Stripe",
                     "Plan your next trip"):
            self.assertFalse(style_fill._is_cta_stage_direction(good),
                             "false-positive on real CTA: %r" % good)

    def test_closing_title_rejects_stage_direction_via_text(self):
        # The leak path: the planner's closing VO beat → data._text.
        for sd in self._STAGE_DIRECTIONS:
            sc = {"id": "close", "role": "close", "data": {"_text": sd}}
            title = style_fill._shape_hero(sc, self._NOTION)["title"]
            self.assertFalse(style_fill._is_cta_stage_direction(title),
                             "leaked stage direction into title: %r (from %r)" % (title, sd))
            self.assertTrue(title, "empty CTA title for %r" % sd)
            # Derived CTA is anchored to the brand.
            self.assertIn("Notion", title, "CTA not brand-anchored: %r" % title)

    def test_closing_title_rejects_stage_direction_via_explicit_title(self):
        # The other leak path: an explicit plan title that is a stage direction.
        for sd in self._STAGE_DIRECTIONS:
            sc = {"id": "close", "role": "close", "data": {"title": sd}}
            title = style_fill._shape_hero(sc, self._NOTION)["title"]
            self.assertFalse(style_fill._is_cta_stage_direction(title),
                             "leaked stage direction into title: %r (from %r)" % (title, sd))
            self.assertTrue(title)

    def test_derived_cta_is_a_real_imperative_not_bare_wordmark(self):
        # When the threaded close was a rejected stage direction, derive an imperative
        # ("Get started with <Brand>"), NOT the bare wordmark (that's not a CTA).
        sc = {"id": "close", "role": "close",
              "data": {"_text": "Closing call‑to‑action card urging users"}}
        title = style_fill._shape_hero(sc, self._NOTION)["title"]
        self.assertEqual(title, "Get started with Notion")

    def test_real_ctas_pass_unchanged_via_text(self):
        cases = [
            ("Shop Allbirds", {"name": "Allbirds", "wordmark": "Allbirds", "cta_url": "allbirds.com"}),
            ("Begin your free trial", {"name": "Allbirds", "wordmark": "Allbirds"}),
            ("Start your trip on Tripadvisor",
             {"name": "Tripadvisor", "wordmark": "Tripadvisor", "cta_url": "tripadvisor.com"}),
            ("Start accepting payments", {"name": "Stripe", "wordmark": "Stripe"}),
        ]
        for vo, brand in cases:
            sc = {"id": "close", "role": "close", "data": {"_text": vo}}
            title = style_fill._shape_hero(sc, brand)["title"]
            self.assertEqual(title, vo, "real CTA was altered: %r -> %r" % (vo, title))

    def test_cta_keeps_domain_still_holds(self):
        # R10 keep-the-.com survives the R11 guard.
        sc = {"id": "close", "role": "close", "data": {"_text": "Visit theverge.com"}}
        title = style_fill._shape_hero(
            sc, {"name": "The Verge", "wordmark": "The Verge", "cta_url": "theverge.com"})["title"]
        self.assertIn("theverge.com", title)
        self.assertNotEqual(title, "Visit theverge")

    def test_closing_subtitle_rejects_stage_direction(self):
        # A stage-direction threaded as the SUBTITLE must not survive either.
        sc = {"id": "close", "role": "close",
              "data": {"_text": "Start accepting payments",
                       "subtitle": "Call-to-action card using the brand color"}}
        d = style_fill._shape_hero(
            sc, {"name": "Stripe", "wordmark": "Stripe", "cta_url": "stripe.com"})
        self.assertFalse(style_fill._is_cta_stage_direction(d["subtitle"]),
                         "stage direction leaked into subtitle: %r" % d["subtitle"])
        self.assertEqual(d["subtitle"], "stripe.com")

    def test_no_closing_copy_keeps_brand_lockup(self):
        # No threaded copy at all → legit brand lockup close (NOT a derived imperative).
        sc = {"id": "close", "role": "close", "data": {}}
        d = style_fill._shape_hero(sc, self._NOTION)
        self.assertEqual(d["title"], "Notion")

    def test_brand_domain_strips_scheme_keeps_tld(self):
        self.assertEqual(style_fill._brand_domain({"cta_url": "https://theverge.com/tech"}),
                         "theverge.com")
        self.assertEqual(style_fill._brand_domain({"url": "stripe.com"}), "stripe.com")
        self.assertEqual(style_fill._brand_domain({}), "")


class TestTheme(unittest.TestCase):
    def test_theme_has_every_composition_key(self):
        th = style_fill._theme_kinetic_light(_brand())
        for k in style_fill._THEME_PALETTE_KEYS + style_fill._THEME_FONT_KEYS:
            self.assertIn(k, th)
            self.assertTrue(th[k], f"theme key {k} empty")
        self.assertEqual(th["accent"], "#2563eb")     # from brand
        self.assertEqual(th["bgCardRaised"], "#f9fafc")  # default fill
        self.assertEqual(th["wordmark"], "Orinovate")


class TestMergeContract(unittest.TestCase):
    def test_props_shape_and_provenance(self):
        tl = build_timeline.build_timeline(_plan()["scenes"], _alignment())
        props = style_fill.build_props(tl, _plan(), _brand(), "orinovate-kinetic-light")
        # top-level contract
        for k in ("fps", "total_frames", "audio_path", "lang", "theme", "scenes"):
            self.assertIn(k, props)
        self.assertEqual(len(props["scenes"]), 3)
        sc_open, sc_caps, sc_close = props["scenes"]
        # frames + cues come from the timeline (VO-anchored)
        self.assertEqual(sc_open["in_frame"], tl["scenes"][0]["in_frame"])
        self.assertEqual(sc_open["out_frame"], tl["scenes"][0]["out_frame"])
        self.assertEqual(sc_open["cues"], tl["scenes"][0]["cues"])
        # archetype decided by the STYLE, not the plan field. A feature beat routes
        # to the EXPLAINER card (title + synthesized bullets).
        self.assertEqual(sc_open["archetype"], style_fill.ARCH_HERO)
        self.assertEqual(sc_caps["archetype"], style_fill.ARCH_EXPLAINER)
        self.assertEqual(sc_close["archetype"], style_fill.ARCH_HERO)
        # data filled per archetype
        self.assertIn("title", sc_open["data"])
        self.assertIn("bullets", sc_caps["data"])

    def test_cues_anchor_to_word_frames(self):
        """A reveal cue must land on the frame of the word it names."""
        align = _alignment()
        tl = build_timeline.build_timeline(_plan()["scenes"], align)
        props = style_fill.build_props(tl, _plan(), _brand(), "orinovate-kinetic-light")
        caps = props["scenes"][1]
        card1 = next(c for c in caps["cues"] if c["label"] == "card-1")
        # 'printing' starts at 1.6s -> 48f @30fps; clamped within the scene.
        self.assertEqual(card1["word"], "printing")
        self.assertGreaterEqual(card1["at_frame"], caps["in_frame"])
        self.assertLessEqual(card1["at_frame"], caps["out_frame"])


class TestPipelineOffline(unittest.TestCase):
    def test_run_pipeline_no_align(self):
        with tempfile.TemporaryDirectory() as d:
            plan_p = os.path.join(d, "plan.json")
            brand_p = os.path.join(d, "brand.json")
            align_p = os.path.join(d, "vo_alignment.json")
            with open(plan_p, "w") as f:
                json.dump(_plan(), f)
            with open(brand_p, "w") as f:
                json.dump(_brand(), f)
            with open(align_p, "w") as f:
                json.dump(_alignment(), f)
            res = style_fill.run_pipeline(plan_p, brand_p,
                                          "orinovate-kinetic-light", d,
                                          fps=30, do_align=False, do_render=False)
            self.assertTrue(os.path.exists(res["props_path"]))
            self.assertTrue(os.path.exists(res["timeline_path"]))
            with open(res["props_path"]) as f:
                props = json.load(f)
            self.assertEqual(len(props["scenes"]), 3)
            # audio_path is rewritten to a public-relative name (no leading slash)
            # so Remotion's staticFile() can serve it from studio/public/.
            self.assertFalse(props["audio_path"].startswith("/"))
            self.assertTrue(props["audio_path"].endswith(".mp3"))


class TestClipToClauseOrphanConnector(unittest.TestCase):
    """Boundary-safe clause clipping: a distilled headline / overlay title must end
    on a COMPLETE phrase, never on a dangling connector whose object was severed by a
    comma/limit cut. Regression for build-stripe-d0cf77 props.json:
      - screenshot headline "Developers integrate Stripe Payments in minutes using clear"
      - walkthrough overlayTitle "Stripe — Go to Get started, then go to Migrate to"
    """

    # --- the exact delivered-bug inputs ---
    BEAT_USING_CLEAR = ("Developers integrate Stripe Payments in minutes using "
                        "clear, comprehensive documentation for global scale.")
    BEAT_API_LIST = ("The Payments API reference shows request parameters, error "
                     "codes, and live examples.")
    EMPHASIS_MIGRATE = "Go to Get started, then go to Migrate to"

    def _ends_on_connector(self, text):
        """A phrase ending on a bare connector word is the failure we forbid."""
        words = [w.lower().strip(".,;:!?—–-") for w in text.split() if w]
        return bool(words) and words[-1] in style_fill._ORPHAN_CONNECTORS

    def test_clip_drops_severed_object_keeps_complete_phrase(self):
        out = style_fill._clip_to_clause(self.BEAT_USING_CLEAR, 64)
        # Must NOT preserve the orphaned "using clear" tail.
        self.assertNotIn("using clear", out.lower())
        self.assertFalse(out.lower().endswith(" using"))
        self.assertFalse(out.lower().endswith(" clear"))
        # The complete lead clause survives (keeps the meaningful "in minutes").
        self.assertEqual(out, "Developers integrate Stripe Payments in minutes")

    def test_grounded_headline_no_dangling_connector(self):
        for beat in (self.BEAT_USING_CLEAR, self.BEAT_API_LIST):
            h = style_fill._grounded_headline(
                beat, {"wordmark": "Stripe"}, avoid="Stripe", limit=64)
            self.assertTrue(h, "headline should be non-empty for %r" % beat)
            self.assertFalse(self._ends_on_connector(h),
                             "headline ends on a dangling connector: %r" % h)
            # never a mid-word cut: the headline is a substring-of-words of the source
            self.assertNotIn("using clear", h.lower())

    def test_emphasis_phrase_clips_at_clause(self):
        e = style_fill._emphasis_phrase(self.EMPHASIS_MIGRATE)
        self.assertFalse(self._ends_on_connector(e),
                         "emphasis ends on a dangling connector: %r" % e)
        self.assertEqual(e, "Go to Get started")

    def test_walkthrough_overlay_title_is_complete(self):
        scene = {
            "id": "wt", "type": "walkthrough",
            "data": {"videoSrc": "/clip.mp4",
                     "_emphasis": self.EMPHASIS_MIGRATE},
        }
        out = style_fill._shape_walkthrough(scene, {"wordmark": "Stripe"})
        title = out["overlayTitle"]
        self.assertFalse(self._ends_on_connector(title),
                         "overlayTitle ends on a dangling connector: %r" % title)
        self.assertTrue(title.startswith("Stripe"))
        self.assertIn("Get started", title)

    def test_complete_sub_limit_phrases_preserved(self):
        # Naturally-complete lines that FIT the limit must pass through UNCHANGED —
        # the orphan guard must not back-trim a complete trailing connector phrase.
        for good in (
            "Accept payments online with Stripe",
            "Stripe powers payments for millions of internet businesses",
            "Developers integrate Stripe Payments in minutes",
            "Built for builders",
            "Allbirds makes comfortable shoes from natural materials",
            "Linear makes shipping faster",
        ):
            self.assertEqual(style_fill._punchy_headline(good, limit=64), good,
                             "complete phrase was altered: %r" % good)
            self.assertEqual(style_fill._clip_to_clause(good, 64), good,
                             "_clip_to_clause altered a complete phrase: %r" % good)

    def test_ends_on_orphan_connector_requires_cut(self):
        # was_cut=False -> a trailing connector phrase is a COMPLETE phrase, not orphan.
        self.assertFalse(style_fill._ends_on_orphan_connector(
            "Accept payments with Stripe", was_cut=False))
        self.assertFalse(style_fill._ends_on_orphan_connector(
            "integrate Payments in minutes", was_cut=False))
        # was_cut=True -> a connector with a short trailing object is an orphan.
        self.assertTrue(style_fill._ends_on_orphan_connector(
            "integrate Payments in minutes using clear", was_cut=True))

    def test_drop_orphan_connector_single_backup(self):
        # Single back-up over the right-most orphan; the complete prep phrase stays.
        self.assertEqual(
            style_fill._drop_orphan_connector_phrase(
                "Developers integrate Stripe Payments in minutes using clear"),
            "Developers integrate Stripe Payments in minutes")

    def test_clip_empty_input(self):
        self.assertEqual(style_fill._clip_to_clause("", 64), "")
        self.assertEqual(style_fill._clip_to_clause("   ", 64), "")


class TestVoCondenseRobustness(unittest.TestCase):
    """The copy-length guard that makes the framework robust to a DENSE (Ultra) vs
    SPARSE (Super) planner: cap each VO beat to its scene's pacing + the film budget,
    on a clause boundary (never mid-word), leaving a sparse plan untouched."""

    def _dense_plan(self):
        # 5 scenes summing to a 30s plan, dense (Ultra-like) VO beats.
        return {
            "job": {"target_duration_s": 30},
            "scenes": [
                {"id": "title-open", "type": "title", "duration_s": 4},
                {"id": "shot-home", "type": "screenshot", "duration_s": 7},
                {"id": "shot-bill", "type": "screenshot", "duration_s": 7},
                {"id": "walk-bill", "type": "walkthrough", "duration_s": 8},
                {"id": "title-close", "type": "title", "duration_s": 4},
            ],
            "voiceover": {"beats": [
                {"scene_id": "title-open",
                 "text": "Stripe powers global commerce for millions of businesses in 135 currencies."},
                {"scene_id": "shot-home",
                 "text": "Accept payments online with built-in fraud protection, instant payouts, and support for many currencies."},
                {"scene_id": "shot-bill",
                 "text": "Enable any billing model from subscriptions to usage-based pricing with automated invoicing in minutes."},
                {"scene_id": "walk-bill",
                 "text": "Set up recurring billing, customize trial periods, and automate revenue recovery in a single dashboard for global teams."},
                {"scene_id": "title-close",
                 "text": "Start accepting payments worldwide at stripe.com today and scale instantly."},
            ]},
        }

    def _sparse_plan(self):
        return {
            "job": {"target_duration_s": 30},
            "scenes": [
                {"id": "open", "type": "title", "duration_s": 3},
                {"id": "shot", "type": "screenshot", "duration_s": 4},
                {"id": "walk", "type": "walkthrough", "duration_s": 5},
                {"id": "close", "type": "title", "duration_s": 3},
            ],
            "voiceover": {"beats": [
                {"scene_id": "open", "text": "Stripe powers online payments for internet businesses worldwide."},
                {"scene_id": "shot", "text": "The Stripe Dashboard shows real-time payments, payouts, and customer insights."},
                {"scene_id": "walk", "text": "Create a recurring subscription plan, set pricing, and let Stripe handle billing automatically."},
                {"scene_id": "close", "text": "Start accepting payments today with Stripe's simple integration."},
            ]},
        }

    def _words(self, plan):
        return [len(b["text"].split()) for b in plan["voiceover"]["beats"]]

    def test_dense_plan_is_condensed_under_global_budget(self):
        plan = self._dense_plan()
        before = sum(self._words(plan))
        style_fill._condense_vo_beats(plan, fps=30)
        after = sum(self._words(plan))
        # Dense VO is reduced...
        self.assertLess(after, before)
        # ...to under the global word budget (target * w/s * tol, + small slack).
        budget = 30 * style_fill._VO_WORDS_PER_SEC * style_fill._VO_GLOBAL_TOL
        self.assertLessEqual(after, round(budget) + 2)
        # ...and every condensed beat is still a real multi-word phrase (no fragments)
        # that ends cleanly (no trailing comma / mid-clause dangling connector).
        for b in plan["voiceover"]["beats"]:
            t = b["text"].strip()
            self.assertGreaterEqual(len(t.split()), 2)
            self.assertFalse(t.endswith((",", ";", ":")), f"dangling tail: {t!r}")

    def test_sparse_plan_is_left_untouched(self):
        plan = self._sparse_plan()
        before = [b["text"] for b in plan["voiceover"]["beats"]]
        style_fill._condense_vo_beats(plan, fps=30)
        after = [b["text"] for b in plan["voiceover"]["beats"]]
        # A sparse plan already sits under budget — condensing must be a no-op so the
        # duration-fill side (build_timeline) does the work of reaching target.
        self.assertEqual(before, after)

    def test_condense_to_words_never_cuts_mid_word(self):
        out = style_fill._condense_to_words(
            "Stripe powers global commerce for millions of businesses worldwide", 6)
        self.assertLessEqual(len(out.split()), 6)
        self.assertGreaterEqual(len(out.split()), 2)
        # The result is a prefix of real words (no partial token at the end).
        self.assertTrue(out and not out.endswith(("-", ",")))

    def test_explicit_supporting_line_clamped(self):
        # An explicit over-long plan supporting line must be clamped so it can't
        # overflow the split-layout left column. Build a screenshot scene with one.
        long_support = ("Stripe handles payments, billing, fraud prevention, payouts, "
                        "invoicing, and revenue recovery for global teams at scale")
        scene = {"id": "shot", "type": "screenshot",
                 "data": {"imageSrc": "x.png", "supporting": long_support,
                          "_text": "Accept payments online"}}
        out = style_fill._shape_screenshot(scene, _brand())
        if out.get("supporting"):
            self.assertLessEqual(len(out["supporting"]),
                                 style_fill._SUPPORTING_MAX_CHARS + 1)


if __name__ == "__main__":
    unittest.main()
