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
        # generic _default palette, not a leaked known-brand palette.
        self.assertEqual(t["palette"]["accent"], "#7CFFB2")

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


class FetchEnrichment(unittest.TestCase):
    def test_fetch_supplies_real_tagline_and_features_for_unknown_brand(self):
        def fetch(url, prompt):
            return json.dumps({
                "tagline": "Ship faster",
                "accent": "#123456",
                "features": [
                    {"title": "Fast builds", "sub": "Sub-second"},
                    {"title": "Edge deploy", "sub": ""},
                ],
            })
        t = be.extract_brand("https://newco.test", fetcher=fetch)
        self.assertEqual(t["tagline"], "Ship faster")
        self.assertEqual(t["copy"]["hook"], "Ship faster")
        self.assertEqual(t["palette"]["accent"], "#123456")
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
        # invalid hex dropped -> generic _default accent retained.
        self.assertEqual(t["palette"]["accent"], "#7CFFB2")

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
