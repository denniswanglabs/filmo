#!/usr/bin/env python3
"""PaaS-subdomain branding: a product hosted on a platform subdomain
(taipei-flix.onrender.com) must brand as the PRODUCT, never the platform.

The shipped bug (run af097f39, verified 2026-07-14): for
https://taipei-flix.onrender.com the wordmark read "ONRENDER", the logo was the
platform favicon, and the CTA said "Start now -> onrender.com" — because
_registrable_label/_root_host treated onrender.com as the brand. Known PaaS
suffixes (remotion_codegen._PAAS_SUFFIXES) now act as EFFECTIVE TLDs:
  * brand label = the product SUBDOMAIN, humanized ("taipei-flix" -> "Taipei Flix")
  * CTA host    = the FULL product host, never the platform root
  * extract_brand prefers the page's own og:site_name/<title> casing when it is
    the same brand as the slug ("TaipeiFlix"), and junk titles cannot hijack it
Normal domains are pinned byte-for-byte unchanged (www.stripe.com -> stripe.com,
tripadvisor.com.tw -> Tripadvisor, hyphenated registrable labels NOT humanized).

Deterministic, $0, network-free (fetcher injected).
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import remotion_codegen as rc
import brand_extract as be


def _no_fetch(url, prompt):
    return ""


TAIPEI = "https://taipei-flix.onrender.com"


class PaasSubdomainBranding(unittest.TestCase):
    def test_brand_name_is_humanized_subdomain(self):
        self.assertEqual(rc._brand_name(TAIPEI), "Taipei Flix")

    def test_root_host_is_full_product_host(self):
        self.assertEqual(rc._root_host(TAIPEI), "taipei-flix.onrender.com")

    def test_deep_subdomain_collapses_to_product_host(self):
        deep = "https://api.taipei-flix.onrender.com/v1"
        self.assertEqual(rc._brand_name(deep), "Taipei Flix")
        self.assertEqual(rc._root_host(deep), "taipei-flix.onrender.com")

    def test_every_known_paas_suffix(self):
        for sfx in sorted(rc._PAAS_SUFFIXES):
            with self.subTest(suffix=sfx):
                url = "https://my-app.%s/x" % sfx
                self.assertEqual(rc._brand_name(url), "My App")
                self.assertEqual(rc._root_host(url), "my-app.%s" % sfx)

    def test_platform_root_itself_still_brands_as_platform(self):
        # The platform's OWN homepage (no product subdomain) is a normal domain.
        self.assertEqual(rc._brand_name("https://onrender.com"), "Onrender")
        self.assertEqual(rc._root_host("https://onrender.com"), "onrender.com")
        self.assertEqual(rc._brand_name("https://vercel.app"), "Vercel")

    def test_paas_product_palette_is_generic_with_fixed_identity(self):
        pal = rc.palette_for(TAIPEI)
        self.assertEqual(pal.get("_brand"), "generic")
        self.assertEqual(pal.get("_name"), "Taipei Flix")
        self.assertEqual(pal.get("_host"), "taipei-flix.onrender.com")


class NormalDomainsUnchanged(unittest.TestCase):
    def test_www_collapses_to_registrable(self):
        self.assertEqual(rc._brand_name("https://www.stripe.com"), "Stripe")
        self.assertEqual(rc._root_host("https://www.stripe.com"), "stripe.com")

    def test_subdomain_collapses_to_registrable(self):
        self.assertEqual(rc._brand_name("https://docs.stripe.com"), "Stripe")
        self.assertEqual(rc._root_host("https://docs.stripe.com"), "stripe.com")

    def test_multi_part_country_tld(self):
        u = "https://www.tripadvisor.com.tw"
        self.assertEqual(rc._brand_name(u), "Tripadvisor")
        self.assertEqual(rc._root_host(u), "tripadvisor.com.tw")

    def test_hyphenated_normal_domain_is_not_humanized(self):
        # Humanization is PaaS-only: a real registrable label keeps the
        # historical capitalize() exactly (pins the existing extract test too).
        self.assertEqual(rc._brand_name("https://acme-rockets.example"),
                         "Acme-rockets")

    def test_known_brand_palette_lookup_unaffected(self):
        pal = rc.palette_for("https://www.stripe.com")
        self.assertEqual(pal.get("_brand"), "stripe.com")
        self.assertEqual(pal.get("_name"), "Stripe")
        self.assertEqual(pal.get("_host"), "stripe.com")
        self.assertEqual(pal.get("accent"),
                         rc.BRAND_PALETTES["stripe.com"]["accent"])


class ExtractBrandPaas(unittest.TestCase):
    def test_theme_uses_subdomain_name_and_full_host(self):
        t = be.extract_brand(TAIPEI, fetcher=_no_fetch)
        self.assertEqual(t["name"], "Taipei Flix")
        self.assertEqual(t["host"], "taipei-flix.onrender.com")
        self.assertIn("Taipei Flix", t["wordmark_svg"])
        self.assertNotIn("Onrender", json.dumps(t))

    def test_fetched_site_name_preferred_when_same_brand(self):
        # The page's own og:site_name/<title> carries the REAL casing
        # ("TaipeiFlix") — adopt it when it de-spaces to the same slug.
        def fetch(url, prompt):
            return json.dumps({"name": "TaipeiFlix", "tagline": "",
                               "accent": "", "features": []})
        t = be.extract_brand(TAIPEI, fetcher=fetch)
        self.assertEqual(t["name"], "TaipeiFlix")

    def test_junk_page_title_cannot_hijack_the_name(self):
        def fetch(url, prompt):
            return json.dumps({"name": "Vite + React", "tagline": "",
                               "accent": "", "features": []})
        t = be.extract_brand(TAIPEI, fetcher=fetch)
        self.assertEqual(t["name"], "Taipei Flix")

    def test_normal_domain_extract_unchanged(self):
        t = be.extract_brand("https://acme-rockets.example", fetcher=_no_fetch)
        self.assertEqual(t["name"], "Acme-rockets")
        self.assertEqual(t["host"], "acme-rockets.example")


class PlanJobBrandName(unittest.TestCase):
    def test_paas_subdomain(self):
        import plan_job
        self.assertEqual(plan_job._brand_name(TAIPEI), "Taipei Flix")

    def test_normal_domain(self):
        import plan_job
        self.assertEqual(plan_job._brand_name("https://www.stripe.com"), "Stripe")


class CtaLine(unittest.TestCase):
    def test_brand_domain_keeps_full_paas_host(self):
        # style_fill's CTA lockup ("Start now → <domain>") reads theme host
        # verbatim — the full product host must survive to the pill.
        import style_fill
        self.assertEqual(
            style_fill._brand_domain({"host": "taipei-flix.onrender.com"}),
            "taipei-flix.onrender.com")


if __name__ == "__main__":
    unittest.main()
