#!/usr/bin/env python3
"""$0, offline unit tests for read_pass.py (capture is injected; no Playwright)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import read_pass


class ReadPassSuccess(unittest.TestCase):
    def test_returns_body_text_and_hero(self):
        def fake_capture(url, out_dir, max_shots=1):
            return {"ok": True, "url": url,
                    "shots": [{"file": "shot-00.png",
                               "path": os.path.join(out_dir, "shot-00.png"),
                               "title": "Acme — ship faster",
                               "body_text": "Acme helps teams ship faster. Powerful."}]}
        r = read_pass.read_pass("https://acme.com", "/tmp/acme-run",
                                capture_fn=fake_capture)
        self.assertEqual(r["url"], "https://acme.com")
        self.assertTrue(r["body_text"].startswith("Acme helps"))
        self.assertTrue(r["hero_screenshot_path"].endswith("shot-00.png"))
        self.assertEqual(r["headline"], "Acme — ship faster")
        self.assertFalse(r["degraded"])

    def test_body_text_is_capped_at_4000_chars(self):
        big = "x" * 9000
        def fake_capture(url, out_dir, max_shots=1):
            return {"ok": True, "url": url,
                    "shots": [{"file": "shot-00.png", "path": "/tmp/s.png",
                               "title": "t", "body_text": big}]}
        r = read_pass.read_pass("https://acme.com", "/tmp/x", capture_fn=fake_capture)
        self.assertLessEqual(len(r["body_text"]), 4000)


class CaptureExposesBodyText(unittest.TestCase):
    def test_screenshot_record_helper_includes_body_text(self):
        # The capture module exposes a pure helper that maps a (title, body) pair
        # onto the shot record's body_text field, capped. We test the helper, not
        # Playwright, so this stays $0/offline.
        import capture_screenshots as cs
        rec = {"index": 0, "file": "shot-00.png"}
        cs._attach_read_text(rec, title="Acme", body_text="y" * 5000)
        self.assertIn("body_text", rec)
        self.assertLessEqual(len(rec["body_text"]), 4000)
        self.assertEqual(rec["body_text"], "y" * 4000)


if __name__ == "__main__":
    unittest.main()
