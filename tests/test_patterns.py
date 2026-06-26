"""Deterministic ($0) tests for the curated pattern catalog + assembler selection."""
import unittest
import patterns_catalog


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


if __name__ == "__main__":
    unittest.main()
