#!/usr/bin/env python3
"""Deterministic, $0 tests for brand_extract.py.

The live fetch is dependency-injected, so every test runs network-free. Three
pillars:
  1. known-brand palette path  -> resolves BRAND_PALETTES + curated tagline.
  2. unknown-brand fallback    -> REAL name + generic palette + NO fabricated
                                  tagline/copy/features (the regressed past bug).
  3. output schema shape       -> the brand_theme.json contract is complete.
Plus: the fetch parser honesty guards, and the CLI writes valid JSON.
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import brand_extract as be


def _no_fetch(url, prompt):
    """Inject the network-free path explicitly (mirrors production default)."""
    return ""


class KnownBrandPath(unittest.TestCase):
    def test_stripe_resolves_curated_palette_and_tagline(self):
        t = be.extract_brand("https://docs.stripe.com", fetcher=_no_fetch)
        self.assertEqual(t["name"], "Stripe")
        self.assertEqual(t["host"], "stripe.com")
        # curated, hand-verified tagline from BRAND_PALETTES — trusted.
        self.assertEqual(t["tagline"], "Build internet businesses")
        self.assertEqual(t["palette"]["accent"].lower(), "#635bff")
        self.assertEqual(t["palette"]["bg"], "#0A2540")
        # hook mirrors the real tagline, never synthesized.
        self.assertEqual(t["copy"]["hook"], "Build internet businesses")

    def test_known_brand_curated_accent_wins_over_fetch(self):
        # Even if a fetch suggests a different accent, the curated hex stays.
        def fetch(url, prompt):
            return json.dumps({"accent": "#FF0000", "tagline": "", "features": []})
        t = be.extract_brand("https://linear.app", fetcher=fetch)
        self.assertEqual(t["palette"]["accent"].lower(), "#5e6ad2")


class UnknownBrandHonesty(unittest.TestCase):
    def test_unknown_brand_has_real_name_and_no_fabricated_copy(self):
        t = be.extract_brand("https://acme-rockets.example", fetcher=_no_fetch)
        self.assertEqual(t["name"], "Acme-rockets")
        self.assertEqual(t["host"], "acme-rockets.example")
        # THE REGRESSION GUARD: no invented tagline / hook / features.
        self.assertEqual(t["tagline"], "")
        self.assertEqual(t["copy"]["hook"], "")
        self.assertEqual(t["features"], [])
        # clean LIGHT default bg (NOT the old dark #0A0D0C+mint that rendered
        # blank cards), and not a leaked known-brand palette.
        self.assertEqual(t["palette"]["bg"], "#FFFFFF")
        # POLICY 2026-07-17 (supersedes R7 hash-distinctness): the accent is the
        # site's REAL color (pixels/fetch) or the honest shared neutral — never
        # a synthesized per-brand hue. The homefeed.me user saw hash-green on a
        # cream/orange site and flagged it instantly. No capture here -> neutral.
        acc = t["palette"]["accent"].upper()
        self.assertEqual(acc, be._LIGHT_DEFAULT["accent"].upper())
        self.assertTrue(
            be._is_perceptible_accent(acc, t["palette"]["bg"], t["palette"]["ink"]),
            "the neutral accent must be perceptible vs both bg and ink")

    def test_unknown_brands_share_the_honest_neutral_without_capture(self):
        # POLICY 2026-07-17: with NO captured pixels and no learnable accent, two
        # unknown brands correctly SHARE the neutral — per-brand distinctness now
        # comes from real pixel extraction (every hosted run captures the page),
        # never from an invented hash hue.
        a = be.extract_brand("https://alpha-co.example", fetcher=_no_fetch)
        b = be.extract_brand("https://beta-co.example", fetcher=_no_fetch)
        self.assertEqual(a["palette"]["accent"].upper(),
                         be._LIGHT_DEFAULT["accent"].upper())
        self.assertEqual(a["palette"]["accent"], b["palette"]["accent"])

    def test_no_leaked_brand_strings_anywhere(self):
        # The old _copy_from_brief leaked "Stripe" into every non-Stripe build.
        t = be.extract_brand("https://widgets.test", fetcher=_no_fetch)
        blob = json.dumps(t).lower()
        for leaked in ("stripe", "linear", "notion", "vercel", "operon"):
            self.assertNotIn(leaked, blob)

    def test_name_override_is_respected(self):
        t = be.extract_brand("https://x.test", name_override="Acme Co",
                             fetcher=_no_fetch)
        self.assertEqual(t["name"], "Acme Co")

    def test_empty_url_does_not_crash_or_fabricate(self):
        t = be.extract_brand("", fetcher=_no_fetch)
        self.assertEqual(t["tagline"], "")
        self.assertEqual(t["features"], [])
        self.assertIn("palette", t)


class PerceptibilityGuard(unittest.TestCase):
    """R4-B: accent must be visually distinct from BOTH bg AND ink."""

    def test_plaid_resolves_to_perceptible_blue_not_near_black_navy(self):
        # Plaid's old well-known accent #0C2340 (lum=31) is nearly identical to
        # ink #0F2338 (lum=31) on the white light theme → gap=0, imperceptible.
        # The guard must promote #1D64DC (lum=92, gap_vs_ink=61, gap_vs_bg=163).
        t = be.extract_brand("https://plaid.com", fetcher=_no_fetch)
        acc = t["palette"]["accent"].upper()
        self.assertEqual(acc, "#1D64DC",
                         "Plaid accent should be the perceptible blue, not near-black")
        # Verify the promoted accent actually passes the perceptibility check.
        self.assertTrue(
            be._is_perceptible_accent(acc, t["palette"]["bg"], t["palette"]["ink"]),
            "Plaid accent must be perceptible vs both bg and ink")

    def test_near_ink_accent_is_replaced_even_when_structurally_valid(self):
        # #0C2340 passes _is_valid_accent (lum=31 in [15,240]) but is imperceptible
        # on a light theme (too close to ink). Simulate via a fictional brand whose
        # fetch returns the near-ink hex.
        def fetch(url, prompt):
            return json.dumps({"accent": "#0C2340", "tagline": "", "features": []})
        t = be.extract_brand("https://darkcorp.test", fetcher=fetch)
        acc = t["palette"]["accent"]
        bg = t["palette"]["bg"]
        ink = t["palette"]["ink"]
        self.assertTrue(
            be._is_perceptible_accent(acc, bg, ink),
            "Near-ink accent #0C2340 must be rejected and replaced with a perceptible one")
        self.assertNotEqual(acc.upper(), "#0C2340")

    def test_near_bg_accent_is_replaced(self):
        # Near-white accent on a white bg is invisible.
        def fetch(url, prompt):
            return json.dumps({"accent": "#F0F0F5", "tagline": "", "features": []})
        t = be.extract_brand("https://whiteco.test", fetcher=fetch)
        acc = t["palette"]["accent"]
        bg = t["palette"]["bg"]
        ink = t["palette"]["ink"]
        self.assertTrue(
            be._is_perceptible_accent(acc, bg, ink),
            "Near-bg accent #F0F0F5 must be rejected and replaced with a perceptible one")


class UiLabelFilter(unittest.TestCase):
    """R7: UI/nav chrome must never become the tagline / a feature."""

    def test_ui_label_predicate(self):
        for chrome in ("Added to Cart", "New Arrivals", "Become a host",
                       "Homes on Airbnb · Become a host", "What's happening",
                       "Sign in", "Log in", "Best Sellers",
                       "Added to Cart · New Arrivals"):
            self.assertTrue(be._is_ui_label(chrome), "%r should be a UI label" % chrome)
        for real in ("Build internet businesses", "One workspace. Every team.",
                     "Develop. Preview. Ship.", "Search 8 million hotels"):
            self.assertFalse(be._is_ui_label(real), "%r is real copy" % real)

    def test_r8_nav_section_labels_are_ui_labels(self):
        # R8: the nav-section labels that slipped past G2 in the R7 12-brand run —
        # both the single segments and the separator-joined pairs (·/•/|).
        for chrome in ("Men's Shoes", "Customer Favorites", "Help Center",
                       "Find a co-host", "Women's Shoes",
                       "Men's Shoes · Customer Favorites",
                       "Help Center · Find a co-host",
                       "Help Center • Find a co-host",
                       "Help Center | Find a co-host"):
            self.assertTrue(be._is_ui_label(chrome),
                            "%r should be a nav/UI label" % chrome)

    def test_r8_nav_section_features_dropped_real_kept(self):
        def fetch(url, prompt):
            return json.dumps({"tagline": "", "accent": "", "features": [
                {"title": "Men's Shoes", "sub": ""},
                {"title": "Sustainable wool insoles", "sub": ""},
                {"title": "Customer Favorites", "sub": ""},
                {"title": "Find a co-host", "sub": ""},
            ]})
        t = be.extract_brand("https://shopco.test", fetcher=fetch)
        titles = [f["title"] for f in t["features"]]
        self.assertIn("Sustainable wool insoles", titles)
        for nav in ("Men's Shoes", "Customer Favorites", "Find a co-host"):
            self.assertNotIn(nav, titles)


class CollapsedNameRepair(unittest.TestCase):
    """R8: a collapsed multi-word brand name (host label "Theverge") must be
    restored to its real spacing ("The Verge"); single-word brands stay intact."""

    def test_theverge_name_restored_via_curated_map(self):
        t = be.extract_brand("https://www.theverge.com", fetcher=_no_fetch)
        self.assertEqual(t["name"], "The Verge")

    def test_collapsed_name_restored_from_fetched_site_name(self):
        # An og:site_name whose despaced form equals the label earns the spacing.
        def fetch(url, prompt):
            return json.dumps({"name": "The Verge", "tagline": "",
                               "accent": "", "features": []})
        t = be.extract_brand("https://www.theverge.com", fetcher=fetch)
        self.assertEqual(t["name"], "The Verge")

    def test_single_word_brands_stay_intact(self):
        cases = {
            "https://stripe.com": "Stripe",
            "https://linear.app": "Linear",
            "https://www.notion.so": "Notion",
            "https://www.plaid.com": "Plaid",
            "https://vercel.com": "Vercel",
            "https://www.shopify.com": "Shopify",
            "https://www.webflow.com": "Webflow",
            "https://www.allbirds.com": "Allbirds",
            "https://www.huckberry.com": "Huckberry",
            "https://www.airbnb.com": "Airbnb",
        }
        for url, want in cases.items():
            t = be.extract_brand(url, fetcher=_no_fetch)
            self.assertEqual(t["name"], want,
                             "%s name must stay %r, got %r" % (url, want, t["name"]))

    def test_unrelated_fetched_name_does_not_hijack(self):
        # A fetched name that does NOT despace to the label must be ignored.
        def fetch(url, prompt):
            return json.dumps({"name": "Best Travel Deals 2026", "tagline": "",
                               "accent": "", "features": []})
        t = be.extract_brand("https://www.theverge.com", fetcher=fetch)
        # Curated map still wins (safe), never the junk page title.
        self.assertEqual(t["name"], "The Verge")

    def test_ui_label_tagline_is_dropped_from_fetch(self):
        def fetch(url, prompt):
            return json.dumps({"tagline": "Added to Cart · New Arrivals",
                               "accent": "", "features": []})
        t = be.extract_brand("https://shopco.test", fetcher=fetch)
        self.assertEqual(t["tagline"], "")
        self.assertEqual(t["copy"]["hook"], "")

    def test_ui_label_features_are_dropped_from_fetch(self):
        def fetch(url, prompt):
            return json.dumps({"tagline": "", "accent": "", "features": [
                {"title": "Added to Cart", "sub": ""},
                {"title": "Real-time inventory", "sub": ""},
                {"title": "Become a host", "sub": ""},
            ]})
        t = be.extract_brand("https://shopco.test", fetcher=fetch)
        titles = [f["title"] for f in t["features"]]
        self.assertIn("Real-time inventory", titles)
        self.assertNotIn("Added to Cart", titles)
        self.assertNotIn("Become a host", titles)


class KnownBrandAccentPerceptibility(unittest.TestCase):
    """R7: a known brand whose curated accent is imperceptible (Vercel #FFFFFF on
    #000000 with #FFFFFF ink) must be repaired, never rendered invisible."""

    def test_vercel_white_accent_is_repaired(self):
        t = be.extract_brand("https://vercel.com", fetcher=_no_fetch)
        acc = t["palette"]["accent"].upper()
        self.assertNotEqual(acc, "#FFFFFF", "white accent on black bg is invisible")
        self.assertTrue(
            be._is_perceptible_accent(acc, t["palette"]["bg"], t["palette"]["ink"]),
            "repaired Vercel accent must be perceptible vs its own bg and ink")


class DominantPageAccent(unittest.TestCase):
    """R7: derive the brand accent from the page's CSS when theme-color misses."""

    def test_most_saturated_prominent_color_wins(self):
        # A page soup of near-grey structure + one vivid brand colour.
        html = ("<style>body{background:#E0E2DC;color:#242729}"
                ".btn{background:#9B433F}.btn2{background:#9B433F}</style>"
                "<a style='color:#888888'>x</a>")
        acc = be._dominant_page_accent(html)
        self.assertEqual(acc, "#9B433F")  # the saturated brick red, not the greys

    def test_no_usable_color_returns_empty(self):
        # Only near-neutral structure colours -> nothing usable.
        html = "<style>body{background:#FAFAFA;color:#111111;border:#888}</style>"
        self.assertEqual(be._dominant_page_accent(html), "")

    def test_rgb_literals_are_harvested(self):
        html = "<div style='background:rgb(29,100,220)'>x</div>" * 3
        acc = be._dominant_page_accent(html)
        self.assertEqual(acc, "#1D64DC")


class FetchEnrichment(unittest.TestCase):
    def test_fetch_supplies_real_tagline_and_features_for_unknown_brand(self):
        def fetch(url, prompt):
            return json.dumps({
                "tagline": "Ship faster",
                # #123456 (lum=45) is too close to ink #0F2338 (lum=31, gap=14) on
                # a light theme — the perceptibility guard rejects it and falls back
                # to the LIGHT_DEFAULT blue. Tagline and features still flow through.
                "accent": "#123456",
                "features": [
                    {"title": "Fast builds", "sub": "Sub-second"},
                    {"title": "Edge deploy", "sub": ""},
                ],
            })
        t = be.extract_brand("https://newco.test", fetcher=fetch)
        self.assertEqual(t["tagline"], "Ship faster")
        self.assertEqual(t["copy"]["hook"], "Ship faster")
        # #123456 is imperceptible on the light theme (too close to ink) → the
        # accent guard rejects it. With no world-knowledge / page colour to fall
        # back on, a deterministic brand-specific perceptible accent is derived
        # (R7: never the shared blue, never invisible). Tagline/features still flow.
        acc = t["palette"]["accent"].upper()
        self.assertNotEqual(acc, "#123456", "near-ink fetched accent must be rejected")
        self.assertNotEqual(acc, "#FFFFFF")
        self.assertTrue(
            be._is_perceptible_accent(acc, t["palette"]["bg"], t["palette"]["ink"]))
        self.assertEqual(len(t["features"]), 2)
        self.assertEqual(t["features"][0]["title"], "Fast builds")

    def test_malformed_fetch_never_fabricates(self):
        for bad in ("not json", "", "{broken", "[1,2,3]", None):
            t = be.extract_brand("https://newco.test", fetcher=lambda u, p, b=bad: b)
            self.assertEqual(t["tagline"], "")
            self.assertEqual(t["features"], [])

    def test_raising_fetcher_is_swallowed(self):
        def boom(url, prompt):
            raise RuntimeError("network down")
        t = be.extract_brand("https://newco.test", fetcher=boom)
        self.assertEqual(t["tagline"], "")
        self.assertEqual(t["features"], [])

    def test_bad_accent_hex_is_dropped(self):
        def fetch(url, prompt):
            return json.dumps({"accent": "blue", "tagline": "", "features": []})
        t = be.extract_brand("https://newco.test", fetcher=fetch)
        # invalid hex dropped -> a deterministic, perceptible brand accent is
        # derived (R7: not the shared default blue, never invisible white).
        acc = t["palette"]["accent"].upper()
        self.assertNotEqual(acc, "#FFFFFF")
        self.assertTrue(
            be._is_perceptible_accent(acc, t["palette"]["bg"], t["palette"]["ink"]))

    def test_perceptible_fetched_accent_is_accepted(self):
        # A genuinely perceptible fetched accent (good contrast vs both bg and ink)
        # MUST be kept, not replaced. #4B7BF5 (lum≈115) on white (lum=255, gap=140)
        # and vs ink #0F2338 (lum=31, gap=84) → both > 40 → PASS.
        def fetch(url, prompt):
            return json.dumps({"accent": "#4B7BF5", "tagline": "Build fast", "features": []})
        t = be.extract_brand("https://newco.test", fetcher=fetch)
        self.assertEqual(t["palette"]["accent"], "#4B7BF5")
        self.assertEqual(t["tagline"], "Build fast")

    def test_feature_without_title_is_dropped(self):
        payload = be._parse_fetch_payload(json.dumps({
            "features": [{"sub": "only a sub"}, {"title": "Real", "sub": "ok"}],
        }))
        self.assertEqual(len(payload["features"]), 1)
        self.assertEqual(payload["features"][0]["title"], "Real")


class SchemaShape(unittest.TestCase):
    def _assert_contract(self, t):
        for key in ("name", "host", "tagline", "palette", "fonts",
                    "wordmark_svg", "features", "copy"):
            self.assertIn(key, t, "missing top-level key %r" % key)
        for key in ("bg", "ink", "accent", "accent2", "success"):
            self.assertIn(key, t["palette"], "missing palette.%s" % key)
        for key in ("display", "mono"):
            self.assertIn(key, t["fonts"], "missing fonts.%s" % key)
        for key in ("hook", "cta"):
            self.assertIn(key, t["copy"], "missing copy.%s" % key)
        self.assertIsInstance(t["features"], list)
        self.assertTrue(t["copy"]["cta"])  # CTA is always non-empty + neutral.

    def test_known_brand_shape(self):
        self._assert_contract(be.extract_brand("https://stripe.com", fetcher=_no_fetch))

    def test_unknown_brand_shape(self):
        self._assert_contract(be.extract_brand("https://zzz.test", fetcher=_no_fetch))

    def test_wordmark_svg_is_inline_svg(self):
        t = be.extract_brand("https://zzz.test", fetcher=_no_fetch)
        self.assertTrue(t["wordmark_svg"].startswith("<svg"))
        self.assertIn("Zzz", t["wordmark_svg"])  # brand's OWN name, not invented.


class CliWritesValidJson(unittest.TestCase):
    def test_main_writes_brand_theme_json(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "nested", "brand_theme.json")
            rc = be.main(["--url", "https://stripe.com", "--out", out])
            self.assertEqual(rc, 0)
            self.assertTrue(os.path.exists(out))
            with open(out) as f:
                data = json.load(f)
            self.assertEqual(data["name"], "Stripe")
            self.assertIn("palette", data)


class PixelAccent(unittest.TestCase):
    """The accent comes from the site's REAL pixels, never a synthesized hue
    (the homefeed.me green bug: hash("homefeed") -> #31BE2D on a cream/orange
    site, spotted by the user immediately)."""

    def _make(self, color, name):
        import subprocess
        path = os.path.join(tempfile.gettempdir(), f"px-{name}.png")
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
                        "-i", f"color=c={color}:s=48x48", "-frames:v", "1", path],
                       check=True, timeout=30)
        return path

    def test_saturated_brand_color_is_read_from_pixels(self):
        p = self._make("0xE8734A", "orange")
        got = be._accent_from_pixels([p], "#FFFFFF", "#0F2338")
        self.assertIsNotNone(got)
        r, g, b = (int(got[i:i + 2], 16) for i in (1, 3, 5))
        self.assertGreater(r, g)   # warm: red dominates
        self.assertGreater(g, b)
        os.remove(p)

    def test_near_white_image_yields_none(self):
        p = self._make("0xFAFAFA", "white")
        self.assertIsNone(be._accent_from_pixels([p], "#FFFFFF", "#0F2338"))
        os.remove(p)

    def test_missing_paths_yield_none(self):
        self.assertIsNone(be._accent_from_pixels(["/nope/x.png", None], "#FFFFFF", "#0F2338"))
        self.assertIsNone(be._accent_from_pixels([], "#FFFFFF", "#0F2338"))

    def test_no_capture_stays_honest_neutral_never_hash(self):
        # Unknown brand with no capture: the honest shared neutral — and NEVER
        # the old deterministic hash color for the domain.
        t = be.extract_brand("https://homefeed.me")
        self.assertEqual(t["palette"]["accent"], be._LIGHT_DEFAULT["accent"])
        self.assertNotEqual(t["palette"]["accent"].upper(), "#31BE2D")

    def test_capture_pixels_win_over_neutral(self):
        # A synthetic capture layout: manifest + logo of a saturated brand color.
        import subprocess
        with tempfile.TemporaryDirectory() as d:
            shots = os.path.join(d, "screenshots-read")
            brand = os.path.join(shots, "brand")
            os.makedirs(brand)
            logo = os.path.join(brand, "logo.png")
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
                            "-i", "color=c=0xCB7C5A:s=48x48", "-frames:v", "1", logo],
                           check=True, timeout=30)
            with open(os.path.join(shots, "manifest.json"), "w") as f:
                json.dump({"shots": [], "logo": {"file": "logo.png", "path": logo,
                                                 "source": "test"}}, f)
            t = be.extract_brand("https://homefeed.me", logo_from=d)
            got = t["palette"]["accent"]
            r, g, b = (int(got[i:i + 2], 16) for i in (1, 3, 5))
            self.assertGreater(r, b)  # warm terracotta family, not blue/green
            self.assertNotEqual(got, be._LIGHT_DEFAULT["accent"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
