"""Agentic site read + VO grounding guard (docs: the video may only claim what
the site actually says)."""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import plan_job
import site_read
import style_fill


class Discovery(unittest.TestCase):
    def test_nav_links_same_origin_only(self):
        html = ('<a href="/pricing">Pricing</a> <a href="/how-it-works">How</a>'
                '<a href="https://evil.example/x">out</a>'
                '<a href="#anchor">anchor</a> <a href="/logo.png">img</a>'
                '<a href="mailto:hi@x.com">mail</a>')
        links = site_read._nav_links("https://acme.example", html)
        self.assertEqual(links, ["https://acme.example/pricing",
                                 "https://acme.example/how-it-works"])

    def test_slug_of(self):
        self.assertEqual(site_read._slug_of("https://x.com/how-it-works/"), "how-it-works")
        self.assertEqual(site_read._slug_of("https://x.com/"), "home")

    def test_pick_pages_fallback_is_slug_priority(self):
        cands = [{"url": "u/about", "slug": "about", "source": "nav"},
                 {"url": "u/pricing", "slug": "pricing", "source": "probe"},
                 {"url": "u/blog", "slug": "blog", "source": "nav"}]
        picked = site_read._pick_pages(cands, brain=None, max_pages=2)
        # brain=None path raises inside -> fallback; pricing outranks about/blog.
        self.assertEqual(picked[0]["slug"], "pricing")
        self.assertEqual(len(picked), 2)

    def test_browse_never_raises_and_writes_ledger(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            led = site_read.browse_site("https://nonexistent.invalid", d, brain=None)
            self.assertIn("pages", led)
            self.assertTrue(os.path.exists(os.path.join(d, "site_read.json")))

    def test_combined_corpus_tags_provenance(self):
        led = {"pages": [{"slug": "pricing", "title": "Pricing", "body_text": "€59.99/year"}]}
        c = site_read.combined_corpus("HOMEPAGE TEXT", led)
        self.assertIn("HOMEPAGE TEXT", c)
        self.assertIn("[PAGE /pricing", c)
        self.assertIn("€59.99/year", c)


class GroundingGuard(unittest.TestCase):
    CORPUS = ("your real estate website ready in minutes founding offer 50 spots "
              "€99.99 €59.99/year 135+ currencies viewing request").replace(",", "")

    def _plan(self, *texts):
        return {"voiceover": [{"scene_id": f"s{i}", "text": t} for i, t in enumerate(texts)]}

    def test_grounded_claims_pass(self):
        p = self._plan("Founding offer: 50 spots at €59.99/year.")
        self.assertEqual(plan_job._grounding_violations(p, self.CORPUS), [])

    def test_invented_number_flagged(self):
        p = self._plan("Launch your site in under 10 minutes")
        v = plan_job._grounding_violations(p, self.CORPUS)
        self.assertTrue(any("'10'" in x or '"10"' in x or "10" in x for x in v))

    def test_free_flagged_when_not_on_site(self):
        p = self._plan("Build your listing site free")
        self.assertTrue(plan_job._grounding_violations(p, self.CORPUS))

    def test_spelled_number_flagged(self):
        p = self._plan("Agents report five new clients in their first month")
        self.assertTrue(plan_job._grounding_violations(p, self.CORPUS))

    def test_strip_removes_free_and_numbers_with_qualifiers(self):
        p = self._plan("Build your listing site free",
                       "Launch your site in under 10 minutes")
        plan_job._strip_ungrounded(p, self.CORPUS)
        self.assertEqual(p["voiceover"][0]["text"], "Build your listing site")
        self.assertEqual(p["voiceover"][1]["text"], "Launch your site in minutes")

    def test_strip_keeps_grounded_numbers(self):
        p = self._plan("135+ currencies, €59.99/year.")
        plan_job._strip_ungrounded(p, self.CORPUS)
        self.assertEqual(p["voiceover"][0]["text"], "135+ currencies, €59.99/year.")

    def test_strip_never_guts_a_beat(self):
        p = self._plan("Ten million")
        plan_job._strip_ungrounded(p, self.CORPUS)
        self.assertEqual(p["voiceover"][0]["text"], "Ten million")  # kept, logged

    def test_number_grounding_is_not_substring_sloppy(self):
        # '13' must NOT be grounded by '135+' in the corpus.
        p = self._plan("13 tools included")
        self.assertTrue(plan_job._grounding_violations(p, self.CORPUS))


class ProductionShapes(unittest.TestCase):
    """The live-run regressions: the guard must read the PRODUCTION voiceover
    dict shape, and SPA catch-alls must not pollute the ledger."""

    CORPUS = "your real estate website ready in minutes viewing request"

    def test_guard_reads_dict_shaped_voiceover(self):
        # The exact shipped failure: {"voice","beats","script"} — 'free' beat.
        plan = {"voiceover": {"voice": "Adam", "beats": [
            {"scene_id": "close", "text": "Build your site free at homefeed.me."}],
            "script": "..."}}
        v = plan_job._grounding_violations(plan, self.CORPUS)
        self.assertTrue(v, "dict-shaped voiceover must be inspected")
        plan_job._strip_ungrounded(plan, self.CORPUS)
        self.assertEqual(plan["voiceover"]["beats"][0]["text"],
                         "Build your site at homefeed.me.")

    def test_guard_still_reads_list_shape(self):
        plan = {"voiceover": [{"scene_id": "s", "text": "Ships in 10 minutes"}]}
        self.assertTrue(plan_job._grounding_violations(plan, self.CORPUS))

    def test_spa_catch_all_pages_are_dropped(self):
        home = "home feed How it works Pricing Demo EN Log in Get started BUILT FOR AGENTS " * 8
        def fake_capture(url, out_dir, max_shots=1):
            os.makedirs(out_dir, exist_ok=True)
            return {"shots": [{"body_text": home, "title": "Homefeed", "path": "/x.png"}]}
        import tempfile
        from unittest import mock
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(site_read, "discover_candidates", return_value=[
                    {"url": "https://x.example/pricing", "slug": "pricing", "source": "probe"}]):
                led = site_read.browse_site("https://x.example", d, brain=None,
                                            capture_fn=fake_capture, homepage_text=home)
        self.assertEqual(led["pages"], [])
        self.assertTrue(led["ok"])

    def test_distinct_page_survives_dedupe(self):
        home = "homepage content " * 30
        page = "PRICING founding offer 50 spots €59.99/year " * 10
        def fake_capture(url, out_dir, max_shots=1):
            os.makedirs(out_dir, exist_ok=True)
            return {"shots": [{"body_text": page, "title": "Pricing", "path": "/p.png"}]}
        import tempfile
        from unittest import mock
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(site_read, "discover_candidates", return_value=[
                    {"url": "https://x.example/pricing", "slug": "pricing", "source": "probe"}]):
                led = site_read.browse_site("https://x.example", d, brain=None,
                                            capture_fn=fake_capture, homepage_text=home)
        self.assertEqual(len(led["pages"]), 1)
        self.assertEqual(led["pages"][0]["slug"], "pricing")


class PageShotMatching(unittest.TestCase):
    BRAND = {"_night_site_pages": [
        {"slug": "pricing", "title": "Pricing", "shot": "/x/pricing.png"},
        {"slug": "how-it-works", "title": "How it works", "shot": "/x/how.png"},
    ], "_night_shot_raw": "/x/home.png"}

    def test_pricing_beat_gets_pricing_page(self):
        s = style_fill._night_page_shot_for("Founding offer €59.99 per year pricing", self.BRAND)
        self.assertEqual(s, "/x/pricing.png")

    def test_steps_beat_gets_how_it_works(self):
        s = style_fill._night_page_shot_for("Create your site and launch in minutes", self.BRAND)
        self.assertEqual(s, "/x/how.png")

    def test_no_match_returns_empty(self):
        self.assertEqual(style_fill._night_page_shot_for("hello world", self.BRAND), "")
        self.assertEqual(style_fill._night_page_shot_for("pricing", {}), "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
