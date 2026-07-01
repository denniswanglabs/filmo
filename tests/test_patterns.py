"""Deterministic ($0) tests for the curated pattern catalog + assembler selection."""
import unittest
import patterns_catalog
import plan_job
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


class TestDesignBriefParse(unittest.TestCase):
    """Unit 1 — the honesty-guarded Design Brief parser (no model; $0)."""

    def _parse(self, obj):
        import analyze
        return analyze._parse_design_brief(obj)

    def test_non_dict_returns_empty(self):
        self.assertEqual(self._parse("nope"),
                         {"story_shape": {}, "brand_vibe": {}})
        self.assertEqual(self._parse(None),
                         {"story_shape": {}, "brand_vibe": {}})

    def test_empty_object_is_empty_brief(self):
        self.assertEqual(self._parse({}),
                         {"story_shape": {}, "brand_vibe": {}})

    def test_rich_real_material_is_kept(self):
        out = self._parse({
            "story_shape": {
                "stats": [{"value": "$500K", "label": "per company"},
                          {"value": "$800B+", "label": "combined value"}],
                "customers": ["Airbnb", "Stripe", "Dropbox"],
                "process_steps": [{"title": "Apply", "body": "Submit"},
                                  {"title": "Build", "body": "We fund"}],
                "contrast": {"before": "Cold outreach", "after": "Warm intros"},
                "testimonial": {"quote": "YC changed everything", "who": "Founder"},
                "scored_results": [{"name": "Speed", "score": "9.2"}],
                "corpus": {"count": "5,000+", "label": "companies"},
                "has_screenshot": True,
                "hero_metric": {"value": "$800B+", "label": "value"},
            },
            "brand_vibe": {"label": "startup-bold", "motion": "energetic"},
        })
        ss = out["story_shape"]
        self.assertEqual(len(ss["stats"]), 2)
        self.assertEqual(ss["customers"], ["Airbnb", "Stripe", "Dropbox"])
        self.assertEqual(len(ss["process_steps"]), 2)
        self.assertEqual(ss["contrast"]["before"], "Cold outreach")
        self.assertEqual(ss["testimonial"]["quote"], "YC changed everything")
        self.assertEqual(ss["scored_results"][0]["score"], "9.2")
        self.assertEqual(ss["corpus"]["count"], "5,000+")
        self.assertIs(ss["has_screenshot"], True)
        self.assertEqual(out["brand_vibe"], {"label": "startup-bold", "motion": "energetic"})

    def test_stat_without_number_is_dropped(self):
        out = self._parse({"story_shape": {
            "stats": [{"value": "powerful", "label": "x"},
                      {"value": "10x", "label": "faster"}]}})
        # only the numbered stat survives -> honesty floor for the fake one
        self.assertEqual(out["story_shape"]["stats"], [{"value": "10x", "label": "faster"}])

    def test_generic_customers_dropped(self):
        out = self._parse({"story_shape": {
            "customers": ["businesses", "teams", "solutions"]}})
        self.assertNotIn("customers", out["story_shape"])

    def test_step_without_title_dropped(self):
        out = self._parse({"story_shape": {
            "process_steps": [{"title": "", "body": "no title"}]}})
        self.assertNotIn("process_steps", out["story_shape"])

    def test_partial_contrast_dropped(self):
        out = self._parse({"story_shape": {"contrast": {"before": "old"}}})
        self.assertNotIn("contrast", out["story_shape"])

    def test_score_without_number_dropped(self):
        out = self._parse({"story_shape": {
            "scored_results": [{"name": "Speed", "score": "fast"}]}})
        self.assertNotIn("scored_results", out["story_shape"])

    def test_invalid_vibe_enums_dropped(self):
        out = self._parse({"brand_vibe": {"label": "mega-bold", "motion": "fast"}})
        self.assertEqual(out["brand_vibe"], {})

    def test_has_screenshot_false_is_absent(self):
        # absence == unknown/false (honesty): only explicit True is carried.
        out = self._parse({"story_shape": {"has_screenshot": False}})
        self.assertNotIn("has_screenshot", out["story_shape"])

    def test_minimal_read_carries_empty_brief(self):
        import analyze
        read = analyze.minimal_read("https://example.com")
        self.assertEqual(read["design_brief"], {"story_shape": {}, "brand_vibe": {}})


class TestStoryShapeStatSeeding(unittest.TestCase):
    """`_seed_feature_beats_from_story_shape` must seed REAL page-copy stats/customers
    onto feature beats so a data-rich brand the model doesn't KNOW (empty enrich) still
    gets split-stat / split-mosaic cards instead of flooring to icon-headline
    (the beacons.fyi regression). The seeded number must survive into a split-stat via
    style_fill's copy-driven selection."""

    def _plan(self, n=3):
        scenes = [{"id": "s%d" % i, "type": "motion_graphic", "data": {}} for i in range(n)]
        beats = [{"scene_id": "s%d" % i, "text": "generic line"} for i in range(n)]
        return {"scenes": scenes, "voiceover": {"beats": beats}}

    def _briefs(self, plan):
        return [s.get("brief") or "" for s in plan["scenes"]]

    def test_stats_seed_feature_beats(self):
        plan = self._plan(3)
        ss = {"stats": [{"value": "100M+", "label": "agentic transactions"},
                        {"value": "14,000+", "label": "MCP servers scored"}]}
        out = plan_job._seed_feature_beats_from_story_shape(plan, ss, reserve=0)
        joined = " ".join(self._briefs(out))
        self.assertIn("100M+", joined)
        self.assertIn("14,000+", joined)
        # and the matching VO beat text carries it too (title derivation reads beat first)
        texts = " ".join(b.get("text", "") for b in out["voiceover"]["beats"])
        self.assertIn("100M+", texts)

    def test_seeded_stat_text_selects_split_stat(self):
        # end-to-end: the seeded brief -> title -> style_fill selects split-stat (not floor)
        plan = self._plan(2)
        ss = {"stats": [{"value": "100M+", "label": "agentic transactions"}]}
        plan_job._seed_feature_beats_from_story_shape(plan, ss, reserve=0)
        seeded = next(s for s in plan["scenes"] if "100M+" in (s.get("brief") or ""))
        out, scene = {"title": seeded["brief"]}, {"data": {"title": seeded["brief"]}}
        style_fill._assign_treatment_from_filled_copy(out, scene, {"wordmark": "Beacons"})
        self.assertEqual(out.get("treatment"), "split-stat")

    def test_stats_capped_at_two_for_variety(self):
        plan = self._plan(4)
        ss = {"stats": [{"value": "1", "label": "a"}, {"value": "2", "label": "b"},
                        {"value": "3", "label": "c"}]}
        plan_job._seed_feature_beats_from_story_shape(plan, ss, reserve=0)
        seeded = [b for b in self._briefs(plan) if b]
        self.assertEqual(len(seeded), 2)

    def test_customers_seed_mosaic_when_three_plus(self):
        plan = self._plan(3)
        ss = {"customers": ["Stripe", "NVIDIA", "Vercel"]}
        plan_job._seed_feature_beats_from_story_shape(plan, ss, reserve=0)
        joined = " ".join(self._briefs(plan))
        for name in ("Stripe", "NVIDIA", "Vercel"):
            self.assertIn(name, joined)

    def test_two_customers_no_mosaic(self):
        plan = self._plan(3)
        plan_job._seed_feature_beats_from_story_shape(plan, {"customers": ["Stripe", "NVIDIA"]}, reserve=0)
        self.assertTrue(all(not b for b in self._briefs(plan)))

    def test_stat_without_number_ignored(self):
        plan = self._plan(2)
        plan_job._seed_feature_beats_from_story_shape(plan, {"stats": [{"value": "lots", "label": "x"}]}, reserve=0)
        self.assertTrue(all(not b for b in self._briefs(plan)))

    def test_empty_story_shape_is_noop(self):
        plan = self._plan(2)
        plan_job._seed_feature_beats_from_story_shape(plan, {"brand_vibe": {}}, reserve=0)
        self.assertTrue(all(not b for b in self._briefs(plan)))

    def test_reserve_leaves_a_beat_free(self):
        # reserve=1 must leave one feature beat unseeded (for the enrich mosaic pass)
        plan = self._plan(2)
        ss = {"stats": [{"value": "100M+", "label": "a"}, {"value": "14,000+", "label": "b"}]}
        plan_job._seed_feature_beats_from_story_shape(plan, ss, reserve=1)
        seeded = [b for b in self._briefs(plan) if b]
        self.assertEqual(len(seeded), 1)


if __name__ == "__main__":
    unittest.main()
