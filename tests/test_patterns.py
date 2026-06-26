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


if __name__ == "__main__":
    unittest.main()
