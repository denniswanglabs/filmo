#!/usr/bin/env python3
"""Unit tests for resolution normalization in adapters.stitch().

$0 — NO real generation. Regression guard for the mixed-resolution stitch crash
found by a real parallel run: failure-isolation can leave a heterogeneous set of
surviving clips (e.g. 1920x1080 title + 1280x720 cinematic + 2560x1440
walkthrough, at different fps / SAR / pix_fmt). The old stitch() fed these raw to
ffmpeg `concat`, which rejects mismatched link params (error 234) -> no final.mp4.

stitch() now normalizes every input (scale-to-fit + pad + setsar=1 + fps +
yuv420p) to the project frame spec (1920x1080) before concat. These tests build
real, tiny mixed-resolution clips via ffmpeg lavfi and assert the OFFICIAL
adapters.stitch() path produces a valid 1920x1080 H.264 (+audio when VO present)
output with no crash — and that loudnorm/audio behavior is preserved.

Run: python3 -m unittest tests.test_adapters_stitch_mixed_res
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import adapters  # noqa: E402

# The three real survivor resolutions/fps from runs/demo-parallel-stripe (the run
# that crashed): 1080p30 title, 720p24 cinematic, 1440p60 walkthrough.
MIXED_SPECS = [
    (1920, 1080, 30, "0A0D0C"),   # title
    (1280, 720, 24, "1F3A8A"),    # cinematic (Seedance)
    (2560, 1440, 60, "0F766E"),   # walkthrough (BEAM capture)
]


def _have_ffmpeg():
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def _make_clip(path, w, h, fps, color_hex, dur=2):
    """A real, small, video-only MP4 at an ARBITRARY resolution/fps (NOT the
    project spec) — exactly the heterogeneous input stitch() must normalize.
    A gradient test pattern (not a flat color) gives the encoder real entropy so
    the stitched output clears stitch()'s >10 KB `verified` size floor, the way
    real Seedance/walkthrough footage does."""
    subprocess.run(
        ["ffmpeg", "-y", "-nostdin", "-loglevel", "error",
         "-f", "lavfi",
         "-i", "testsrc2=s=%dx%d:r=%d:d=%d" % (w, h, fps, dur),
         "-c:v", "libx264", "-crf", "23", "-preset", "ultrafast",
         "-pix_fmt", "yuv420p", "-movflags", "+faststart", path],
        check=True, capture_output=True, timeout=60)


def _make_vo(path, dur=3):
    """A real, short AAC track (a quiet sine tone, NOT digital silence) to
    exercise the VO mux + loudnorm pass. loudnorm cannot normalize pure silence
    (-inf LUFS), and real voiceover is never pure silence — a tone is the
    faithful stand-in."""
    subprocess.run(
        ["ffmpeg", "-y", "-nostdin", "-loglevel", "error",
         "-f", "lavfi", "-i", "sine=frequency=220:sample_rate=44100",
         "-t", str(dur), "-c:a", "aac", path],
        check=True, capture_output=True, timeout=60)


def _probe_video(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height,codec_name,sample_aspect_ratio",
         "-of", "json", path],
        check=True, capture_output=True, text=True, timeout=30).stdout
    return json.loads(out)["streams"][0]


def _has_audio(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type",
         "-of", "json", path],
        check=True, capture_output=True, text=True, timeout=30).stdout
    return any(s.get("codec_type") == "audio" for s in json.loads(out).get("streams", []))


@unittest.skipUnless(_have_ffmpeg(), "ffmpeg/ffprobe not on PATH")
class StitchMixedResolution(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="stitch_mixed_")
        self.clips = []
        for i, (w, h, fps, color) in enumerate(MIXED_SPECS):
            p = os.path.join(self.tmp, "clip%d_%dx%d.mp4" % (i, w, h))
            _make_clip(p, w, h, fps, color)
            self.clips.append(p)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_mixed_resolution_no_vo_normalizes_to_1080p(self):
        """Heterogeneous clips, no VO -> valid 1920x1080 H.264, no crash."""
        out = os.path.join(self.tmp, "out_novo.mp4")
        rec = adapters.stitch(self.clips, vo_path=None, out_path=out)

        self.assertTrue(os.path.exists(out), "stitch produced no output")
        self.assertTrue(rec["verified"])
        self.assertEqual(rec["clip_count"], 3)

        v = _probe_video(out)
        self.assertEqual(v["codec_name"], "h264")
        self.assertEqual((v["width"], v["height"]), (1920, 1080),
                         "output must be normalized to the project spec")
        # SAR must be square (1:1 or N/A) — no distortion baked in.
        self.assertIn(v.get("sample_aspect_ratio", "N/A"), ("1:1", "N/A"))
        # No VO supplied -> no audio stream.
        self.assertFalse(_has_audio(out))

    def test_mixed_resolution_with_vo_keeps_audio_and_loudnorm(self):
        """Same heterogeneous clips WITH a VO -> 1920x1080 H.264 + AAC audio
        (loudnorm pass runs; preserved alongside the normalization fix)."""
        vo = os.path.join(self.tmp, "vo.aac")
        _make_vo(vo, dur=2)
        out = os.path.join(self.tmp, "out_vo.mp4")
        rec = adapters.stitch(self.clips, vo_path=vo, out_path=out)

        self.assertTrue(os.path.exists(out))
        self.assertTrue(rec["verified"])
        self.assertTrue(rec["has_audio"], "VO mux must yield an audio stream")

        v = _probe_video(out)
        self.assertEqual(v["codec_name"], "h264")
        self.assertEqual((v["width"], v["height"]), (1920, 1080))
        self.assertTrue(_has_audio(out))

    def test_uniform_resolution_path_still_works(self):
        """The pre-existing uniform-1080p path must not regress: three project-
        spec synth clips stitch cleanly to 1920x1080."""
        uniform = []
        for i in range(3):
            p = os.path.join(self.tmp, "u%d.mp4" % i)
            adapters.synth_clip(p, "1F3A8A", 1)
            uniform.append(p)
        out = os.path.join(self.tmp, "out_uniform.mp4")
        rec = adapters.stitch(uniform, vo_path=None, out_path=out)

        # Validate by probe rather than rec["verified"]: that flag is a >10 KB
        # size heuristic tuned for real footage, but flat-color synth clips at the
        # project spec compress below it. The point of this case is no-regression
        # on the uniform path, which is proven by a valid 1920x1080 H.264 result.
        self.assertEqual(rec["clip_count"], 3)
        self.assertTrue(os.path.getsize(out) > 0)
        v = _probe_video(out)
        self.assertEqual((v["width"], v["height"]), (1920, 1080))
        self.assertEqual(v["codec_name"], "h264")


if __name__ == "__main__":
    unittest.main()
