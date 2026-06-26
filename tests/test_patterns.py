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


if __name__ == "__main__":
    unittest.main()
