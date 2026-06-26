"""Deterministic ($0) tests for the curated pattern catalog + assembler selection."""
import unittest
import patterns_catalog
import style_fill


class TestCatalog(unittest.TestCase):
    def test_loads_seven_seed_patterns(self):
        ids = patterns_catalog.pattern_ids()
        for pid in ("split-stat", "split-mosaic", "big-number", "icon-stat",
                    "icon-headline", "logo-wall", "feature-list"):
            self.assertIn(pid, ids)

    def test_every_pattern_has_required_fields_and_example(self):
        for p in patterns_catalog.load_catalog():
            self.assertTrue(p["exampleProps"].get("treatment") == p["id"],
                            "exampleProps.treatment must equal id for %s" % p["id"])


class TestAssemblerLegibility(unittest.TestCase):
    def _shape(self, data):
        out = dict(data)
        scene = {"data": dict(data)}
        style_fill._assign_treatment_from_filled_copy(out, scene, {"wordmark": "YC"})
        return out

    def test_split_stat_records_reason(self):
        out = self._shape({"title": "Companies funded 5,000+"})
        self.assertEqual(out.get("treatment"), "split-stat")
        self.assertTrue(out.get("patternReason"))
        self.assertIn("5,000+", out["patternReason"])

    def test_no_data_degrades_to_icon_headline_with_reason(self):
        out = self._shape({"title": "Be in the room"})
        self.assertEqual(out.get("treatment"), "icon-headline")
        self.assertIn("no real", out.get("patternReason", "").lower())


class TestMetricRow(unittest.TestCase):
    def _shape(self, data):
        out = dict(data); scene = {"data": dict(data)}
        style_fill._assign_treatment_from_filled_copy(out, scene, {"wordmark": "X"})
        return out

    def test_three_real_metrics_select_metric_row(self):
        out = self._shape({"title": "By the numbers",
                           "metrics": [{"value": "150M+", "label": "users"},
                                       {"value": "$9.9B", "label": "revenue"},
                                       {"value": "7M+", "label": "listings"}]})
        self.assertEqual(out.get("treatment"), "metric-row")

    def test_fewer_than_three_metrics_does_not_select_metric_row(self):
        out = self._shape({"title": "Just one", "metrics": [{"value": "1", "label": "x"}]})
        self.assertNotEqual(out.get("treatment"), "metric-row")


class TestDeviceFrame(unittest.TestCase):
    def _shape(self, data):
        out = dict(data); scene = {"data": dict(data)}
        style_fill._assign_treatment_from_filled_copy(out, scene, {"wordmark": "Stripe"})
        return out

    def test_product_screenshot_selects_device_frame(self):
        # A real captured screenshot on a product beat -> device-frame.
        out = self._shape({"title": "See it in action",
                           "imageSrc": "shot-g7-stripe-screenshot-home.png",
                           "kind": "product"})
        self.assertEqual(out.get("treatment"), "device-frame")
        self.assertEqual(out.get("imageSrc"), "shot-g7-stripe-screenshot-home.png")
        self.assertIn("screenshot", out.get("patternReason", "").lower())

    def test_pre_emitted_device_frame_treatment_selects(self):
        # Planner may pre-emit treatment="device-frame" alongside a real screenshot.
        out = self._shape({"title": "The dashboard",
                           "imageSrc": "shot-g7-stripe-screenshot-home.png",
                           "treatment": "device-frame"})
        self.assertEqual(out.get("treatment"), "device-frame")

    def test_no_screenshot_does_not_select_device_frame(self):
        # No captured screenshot -> never device-frame (honest floor applies).
        out = self._shape({"title": "See it in action", "kind": "product"})
        self.assertNotEqual(out.get("treatment"), "device-frame")


class TestComparisonColumns(unittest.TestCase):
    def _shape(self, data):
        out = dict(data); scene = {"data": dict(data)}
        style_fill._assign_treatment_from_filled_copy(out, scene, {"wordmark": "Filmo"})
        return out

    def test_real_contrast_selects_comparison_columns(self):
        # A real extracted contrast with >=2 items per side -> comparison-columns.
        out = self._shape({"title": "Old way vs Filmo",
                           "compare": {
                               "leftTitle": "The old way",
                               "leftItems": ["Hire an agency", "Wait 3 weeks", "$10k+ per video"],
                               "rightTitle": "With Filmo",
                               "rightItems": ["Paste a URL", "Ready in minutes", "A few dollars"]}})
        self.assertEqual(out.get("treatment"), "comparison-columns")
        self.assertIsInstance(out.get("compare"), dict)
        self.assertIn("items", out.get("patternReason", "").lower())

    def test_short_sides_do_not_select_comparison_columns(self):
        # Fewer than 2 items on a side -> NOT comparison-columns (never half-empty).
        out = self._shape({"title": "Old vs new",
                           "compare": {
                               "leftTitle": "The old way",
                               "leftItems": ["Hire an agency"],
                               "rightTitle": "With Filmo",
                               "rightItems": ["Paste a URL", "Ready in minutes"]}})
        self.assertNotEqual(out.get("treatment"), "comparison-columns")

    def test_missing_compare_does_not_select_comparison_columns(self):
        # Absent compare -> never invented.
        out = self._shape({"title": "See it in action"})
        self.assertNotEqual(out.get("treatment"), "comparison-columns")


class TestPullQuote(unittest.TestCase):
    def _shape(self, data):
        out = dict(data); scene = {"data": dict(data)}
        style_fill._assign_treatment_from_filled_copy(out, scene, {"wordmark": "Acme"})
        return out

    def test_real_quote_with_attribution_selects_pull_quote(self):
        # A real, substantial quote (>=6 words) + attribution -> pull-quote.
        out = self._shape({
            "title": "What customers say",
            "quote": "This product completely changed how our whole team ships.",
            "quoteAttribution": "Jane Doe, VP of Engineering"})
        self.assertEqual(out.get("treatment"), "pull-quote")
        self.assertEqual(out.get("quote"),
                         "This product completely changed how our whole team ships.")
        self.assertEqual(out.get("quoteAttribution"), "Jane Doe, VP of Engineering")
        self.assertIn("testimonial", out.get("patternReason", "").lower())

    def test_short_quote_does_not_select_pull_quote(self):
        # A too-short quote (<6 words) -> never pull-quote (no fabrication / padding).
        out = self._shape({"title": "What customers say",
                           "quote": "Love it",
                           "quoteAttribution": "Jane Doe"})
        self.assertNotEqual(out.get("treatment"), "pull-quote")

    def test_quote_without_attribution_does_not_select_pull_quote(self):
        # A real quote but NO attribution -> never pull-quote (unattributed = unverifiable).
        out = self._shape({"title": "What customers say",
                           "quote": "This product completely changed how our whole team ships."})
        self.assertNotEqual(out.get("treatment"), "pull-quote")

    def test_empty_quote_does_not_select_pull_quote(self):
        # Absent / empty quote -> never invented.
        out = self._shape({"title": "What customers say", "quoteAttribution": "Jane Doe"})
        self.assertNotEqual(out.get("treatment"), "pull-quote")


class TestKineticStatement(unittest.TestCase):
    """kinetic-statement (HARVESTED from cluely-promo / Luceo Studio) is OPT-IN only:
    a scene must flag itself a hook (kind=="hook" or treatment=="kinetic-statement")
    AND carry real title/lines text AND carry no competing data. A generic no-data
    scene must NOT regress into it (stays icon-headline)."""

    def _shape(self, data):
        out = dict(data); scene = {"data": dict(data)}
        style_fill._assign_treatment_from_filled_copy(out, scene, {"wordmark": "Filmo"})
        return out

    def test_hook_with_title_selects_kinetic_statement_and_populates_lines(self):
        # An opt-in hook beat with a real title -> kinetic-statement; `lines` derived
        # from the title (verbatim words, split into <=2 balanced lines).
        out = self._shape({"kind": "hook", "title": "Paste a URL. Get a launch video."})
        self.assertEqual(out.get("treatment"), "kinetic-statement")
        lines = out.get("lines")
        self.assertTrue(isinstance(lines, list) and 1 <= len(lines) <= 2)
        # every word read VERBATIM from the title (no fabrication)
        joined = " ".join(lines)
        for w in "Paste a URL. Get a launch video.".split():
            self.assertIn(w, joined)
        self.assertIn("kinetic-statement", out.get("patternReason", ""))

    def test_explicit_treatment_opt_in_selects_kinetic_statement(self):
        out = self._shape({"treatment": "kinetic-statement",
                           "title": "Your launch, produced."})
        self.assertEqual(out.get("treatment"), "kinetic-statement")

    def test_emphasis_and_underline_kept_only_when_verbatim(self):
        out = self._shape({"kind": "hook", "title": "Get a launch video.",
                           "emphasisWord": "launch", "underlineWord": "video",
                           "eyebrow": "FILMO"})
        self.assertEqual(out.get("treatment"), "kinetic-statement")
        self.assertEqual(out.get("emphasisWord"), "launch")
        self.assertEqual(out.get("underlineWord"), "video")
        self.assertEqual(out.get("eyebrow"), "FILMO")

    def test_non_verbatim_emphasis_word_dropped(self):
        # An emphasis word that does NOT appear verbatim is dropped (no tint), not an error.
        out = self._shape({"kind": "hook", "title": "Paste a URL.",
                           "emphasisWord": "magic"})
        self.assertEqual(out.get("treatment"), "kinetic-statement")
        self.assertIsNone(out.get("emphasisWord"))

    def test_generic_no_data_scene_does_not_select_kinetic_statement(self):
        # NON-REGRESSION: a generic scene with NO hook flag stays icon-headline.
        out = self._shape({"title": "Be in the room"})
        self.assertEqual(out.get("treatment"), "icon-headline")
        self.assertNotEqual(out.get("treatment"), "kinetic-statement")

    def test_hook_with_competing_stat_does_not_select_kinetic_statement(self):
        # Competing data (a real stat) means the hook is NOT a pure statement beat;
        # it must fall through to the data-driven treatments, not kinetic-statement.
        out = self._shape({"kind": "hook", "title": "Companies funded 5,000+"})
        self.assertNotEqual(out.get("treatment"), "kinetic-statement")


if __name__ == "__main__":
    unittest.main()
