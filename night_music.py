"""Engineered Night music mapper (spec §7): one continuous build whose climax
lands EXACTLY on the brand-lockup resolve.

The bed is a pre-generated, brand-agnostic ElevenLabs Music piece measured with
librosa (assets/night/bed-60.json records duration/climax/bpm). Per run we map
bed_climax -> the close scene's lockup moment:

  * lockup later than bed climax  -> slow the bed down (atempo, floor 0.92)
  * lockup earlier                -> trim the bed's head so the build starts
                                     mid-rise, then fine-tune with atempo <=1.08

ffmpeg-only (no python audio deps) so it runs identically in the Railway image.
Never raises: on ANY failure the caller keeps the classic music path.
"""
from __future__ import annotations

import json
import os
import subprocess


ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "night")
BED = os.path.join(ASSETS, "bed-60.mp3")
BED_META = os.path.join(ASSETS, "bed-60.json")
ATEMPO_MIN, ATEMPO_MAX = 0.92, 1.08


def build_bed(target_climax_s: float, total_s: float, out_path: str) -> bool:
    """Write a bed whose climax hits `target_climax_s`, at least `total_s` long
    (the composition's own volume envelope handles the tail fade). True on success."""
    try:
        meta = json.load(open(BED_META))
        bed_climax = float(meta["climax_s"])
        bed_dur = float(meta["duration_s"])
        if target_climax_s <= 3 or total_s <= 4 or not os.path.exists(BED):
            return False

        trim_head = 0.0
        atempo = 1.0
        if target_climax_s >= bed_climax:
            # Slow down so the build stretches to the later lockup.
            atempo = max(ATEMPO_MIN, bed_climax / target_climax_s)
        else:
            # Start mid-build: cut the head so the remaining rise fits the film.
            trim_head = bed_climax - target_climax_s
            remaining = bed_dur - trim_head
            if remaining < total_s:
                atempo = max(ATEMPO_MIN, min(ATEMPO_MAX, remaining / total_s))

        filters = [f"atempo={atempo:.4f}"] if abs(atempo - 1.0) > 0.005 else []
        af = ",".join(filters) if filters else "anull"
        cmd = ["ffmpeg", "-y", "-v", "error", "-ss", f"{trim_head:.3f}", "-i", BED,
               "-af", af, "-t", f"{total_s + 2.0:.3f}", "-c:a", "libmp3lame",
               "-b:a", "160k", out_path]
        subprocess.run(cmd, check=True, timeout=120)
        return os.path.exists(out_path) and os.path.getsize(out_path) > 10_000
    except Exception:
        return False
