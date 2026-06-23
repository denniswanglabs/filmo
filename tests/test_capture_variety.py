"""Deterministic ($0, no network, no browser) tests for screenshot variety.

Covers:
  - capture_screenshots._images_are_distinct / _image_diff_yavg: identical PNGs read
    as the SAME page; visually different PNGs read as distinct; a missing file (probe
    cannot run) conservatively reads as distinct (never discard a real shot).
  - style_fill.wire_captured_assets: the two screenshot scenes get DISTINCT captured
    pages (one per scene), and a single-shot capture degrades gracefully (2nd scene
    keeps its never-blank floor, no duplicated imageSrc).
"""
import json
import os
import subprocess
import tempfile
import unittest

import capture_screenshots
import style_fill


def _ffmpeg_available():
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=10)
        subprocess.run(["ffprobe", "-version"], capture_output=True, timeout=10)
        return True
    except Exception:
        return False


def _solid_png(path, color):
    """Write a 320x200 solid-color PNG via ffmpeg (lavfi color source)."""
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
         "-i", "color=c=%s:s=320x200" % color, "-frames:v", "1", path],
        capture_output=True, timeout=20, check=False,
    )
    return os.path.exists(path)


@unittest.skipUnless(_ffmpeg_available(), "ffmpeg/ffprobe not available")
class TestImageDistinctness(unittest.TestCase):
    def test_identical_pngs_read_as_same_page(self):
        with tempfile.TemporaryDirectory() as d:
            a = os.path.join(d, "a.png")
            b = os.path.join(d, "b.png")
            self.assertTrue(_solid_png(a, "white"))
            self.assertTrue(_solid_png(b, "white"))
            self.assertLessEqual(capture_screenshots._image_diff_yavg(a, b),
                                 capture_screenshots._SAME_PAGE_DIFF_CEIL)
            self.assertFalse(capture_screenshots._images_are_distinct(a, b))

    def test_different_pngs_read_as_distinct(self):
        with tempfile.TemporaryDirectory() as d:
            a = os.path.join(d, "a.png")
            b = os.path.join(d, "b.png")
            self.assertTrue(_solid_png(a, "white"))
            self.assertTrue(_solid_png(b, "black"))
            diff = capture_screenshots._image_diff_yavg(a, b)
            self.assertGreater(diff, capture_screenshots._SAME_PAGE_DIFF_CEIL)
            self.assertTrue(capture_screenshots._images_are_distinct(a, b))


class TestImageDistinctnessGraceful(unittest.TestCase):
    def test_missing_files_assume_distinct(self):
        # A probe that cannot run must NEVER discard a real shot -> assume distinct.
        self.assertTrue(capture_screenshots._images_are_distinct(
            "/nonexistent-a.png", "/nonexistent-b.png"))
        self.assertIsNone(capture_screenshots._image_diff_yavg(
            "/nonexistent-a.png", "/nonexistent-b.png"))


class TestWireCapturedAssetsVariety(unittest.TestCase):
    def _plan_two_screenshots(self):
        return {"scenes": [
            {"id": "s1", "type": "screenshot", "data": {}},
            {"id": "s2", "type": "screenshot", "data": {}},
        ]}

    def _write_manifest(self, shots_dir, shots):
        os.makedirs(shots_dir, exist_ok=True)
        for s in shots:
            # touch the shot file so the path exists on disk
            with open(os.path.join(shots_dir, s["file"]), "wb") as fh:
                fh.write(b"\x89PNG\r\n")
        manifest = {"url": "https://example.com", "count": len(shots),
                    "shots": shots, "ok": bool(shots)}
        with open(os.path.join(shots_dir, "manifest.json"), "w") as fh:
            json.dump(manifest, fh)

    def test_two_screenshot_scenes_get_distinct_pages(self):
        with tempfile.TemporaryDirectory() as out:
            shots_dir = os.path.join(out, "screenshots")
            self._write_manifest(shots_dir, [
                {"index": 1, "file": "shot-01.png",
                 "path": os.path.join(shots_dir, "shot-01.png"),
                 "url": "https://example.com", "label": "home"},
                {"index": 2, "file": "shot-02.png",
                 "path": os.path.join(shots_dir, "shot-02.png"),
                 "url": "https://example.com/get-started", "label": "route"},
            ])
            plan = style_fill.wire_captured_assets(self._plan_two_screenshots(), out)
            imgs = [s["data"].get("imageSrc") for s in plan["scenes"]]
            caps = [s["data"].get("caption") for s in plan["scenes"]]
            self.assertEqual(len(imgs), 2)
            self.assertTrue(all(imgs), "both screenshot scenes must get an image: %r" % imgs)
            self.assertNotEqual(imgs[0], imgs[1],
                                "the two screenshot scenes share an imageSrc: %r" % imgs)
            self.assertNotEqual(caps[0], caps[1],
                                "the two screenshot scenes share a page URL: %r" % caps)

    def test_single_shot_degrades_gracefully_no_duplicate(self):
        # Only ONE usable page captured -> scene 1 gets it, scene 2 gets NO image
        # (its never-blank archetype floor renders) — never a duplicated imageSrc.
        with tempfile.TemporaryDirectory() as out:
            shots_dir = os.path.join(out, "screenshots")
            self._write_manifest(shots_dir, [
                {"index": 1, "file": "shot-01.png",
                 "path": os.path.join(shots_dir, "shot-01.png"),
                 "url": "https://example.com", "label": "home"},
            ])
            plan = style_fill.wire_captured_assets(self._plan_two_screenshots(), out)
            imgs = [s["data"].get("imageSrc") for s in plan["scenes"]]
            self.assertTrue(imgs[0])
            self.assertFalse(imgs[1], "2nd scene must NOT reuse the 1st shot: %r" % imgs)


if __name__ == "__main__":
    unittest.main()
