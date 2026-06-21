#!/usr/bin/env python3
"""Swap real generated media into a run and re-stitch the final cut.

The $0 demo runs ship with labelled storyboard placeholders for the cinematic
(Higgsfield) and walkthrough (walk-agent) scenes. Once those are generated for
real, this normalizes each to the pipeline frame spec (1920x1080 / 30fps / h264),
replaces the placeholder clip in the run dir (same filename → same timeline slot),
marks the scene record as real media, and re-stitches final.mp4 with the existing
voiceover. Idempotent; the P&L is unchanged (this is media only, not money).

Usage:
  python3 apply_real_media.py <run_id> <scene_id>=<source.mp4|png> [<scene_id>=...]
"""

import json
import os
import subprocess
import sys

import adapters

HERE = os.path.dirname(os.path.abspath(__file__))
RUNS = os.path.join(HERE, "runs")
W, H, FPS = 1920, 1080, 30

# Walk-agent walkthrough windowing + de-letterboxing.
#  (a) The capture composites the browser viewport as a 1440x960 card onto a
#      1920x1080 black canvas — ~33% of the frame is black BARS BAKED INTO THE
#      PIXELS (cropdetect=1440:960:240:60, stable across runs). A plain
#      scale:increase+crop fill (as in finish_cut.py:61) is a no-op here because
#      the source is already 16:9, so the baked bars survive. We must first crop
#      to the content rect, THEN scale up to fill 1920x1080.
#  (b) The clip opens on the walk-agent's own off-brand green "EXPLAINER AGENT ·
#      FEASIBILITY DEMO" title card (~0-2s) + a black transition; WT_SS skips it.
#  (c) It runs ~14s and dominates the cut; WT_DUR trims to one tight task loop.
WT_SS = 2.6    # start offset (s) — past the green intro card + black dip
WT_DUR = 7.5   # trimmed length (s) — ~7-8s of the most useful content
WT_CROP = (1440, 960, 240, 60)  # content rect (w,h,x,y) inside the 1920x1080 capture


def normalize(src, dst, duration_s=None, is_walkthrough=False):
    """Re-encode src to the uniform frame spec (video-only, no audio). A still
    image (.png) is held for duration_s; a video is scaled to FILL + cropped
    (no black bars) and fps-locked. Walkthrough captures are additionally
    de-letterboxed (crop to the browser content rect, then fill) and windowed
    (offset + trim) to drop the agent's intro card and tighten length."""
    is_image = src.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))
    if is_walkthrough:
        # Crop to the real browser content rect FIRST (removes the baked-in black
        # bars that a plain fill can't), THEN scale up to fill the frame.
        cw, ch, cx, cy = WT_CROP
        vf = ("crop=%d:%d:%d:%d,scale=%d:%d:force_original_aspect_ratio=increase,"
              "crop=%d:%d,fps=%d,format=yuv420p,setsar=1"
              % (cw, ch, cx, cy, W, H, W, H, FPS))
    else:
        # Fill-and-crop (matches finish_cut.py:61), NOT letterbox+pad: scale up to
        # cover the frame on the long axis, then crop to spec — no black bars.
        vf = ("scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d,"
              "fps=%d,format=yuv420p,setsar=1"
              % (W, H, W, H, FPS))
    cmd = ["ffmpeg", "-y", "-nostdin", "-loglevel", "error"]
    if is_image:
        cmd += ["-loop", "1", "-t", str(max(2, int(duration_s or 6))), "-i", src]
    elif is_walkthrough:
        # Input-seek past the intro card, then trim to one tight task loop.
        cmd += ["-ss", str(WT_SS), "-t", str(WT_DUR), "-i", src]
    else:
        cmd += ["-i", src]
    cmd += ["-vf", vf, "-an", "-c:v", "libx264", "-crf", "18", "-preset", "medium",
            "-movflags", "+faststart", dst]
    subprocess.run(cmd, check=True, timeout=300)
    if not os.path.exists(dst) or os.path.getsize(dst) < 1000:
        raise RuntimeError("normalize produced no output: " + dst)


def apply(run_id, mapping):
    run_dir = os.path.join(RUNS, run_id)
    led_path = os.path.join(run_dir, "ledger.json")
    led = json.load(open(led_path))
    swapped = []
    for s in led["scenes"]:
        sid = s.get("id")
        if sid in mapping and s.get("output_path"):
            dst = os.path.join(run_dir, s["output_path"])
            normalize(mapping[sid], dst, duration_s=s.get("duration_s"),
                      is_walkthrough=s.get("type") == "walkthrough")
            source = "higgsfield" if s.get("type") == "cinematic" else "walk-agent"
            s["real_media"] = {"source": source, "model": s.get("final_model") or s.get("model"),
                               "clip": s["output_path"]}
            # reflect on the studio block so the dashboard stops calling it a placeholder
            if s.get("studio"):
                s["studio"]["kind"] = "real_media"
                s["studio"]["real_media"] = True
            swapped.append(sid)
    if not swapped:
        print("no matching scenes for", run_id, list(mapping))
        return

    # re-stitch produced clips in plan order + the existing VO
    clips = sorted([(s["order"], os.path.join(run_dir, s["output_path"]))
                    for s in led["scenes"] if s.get("output_path")], key=lambda c: c[0])
    vo = os.path.join(run_dir, "voiceover.mp3")
    vo = vo if os.path.exists(vo) else None
    final = os.path.join(run_dir, "final.mp4")
    rec = adapters.stitch([c[1] for c in clips], vo, final)
    rec["output_path"] = "final.mp4"
    order_to_id = {s["order"]: s["id"] for s in led["scenes"]}
    rec["scenes_included"] = [order_to_id[c[0]] for c in clips]
    rec["scenes_cut"] = [s["id"] for s in led["scenes"]
                         if s.get("type") == "cinematic" and not s.get("output_path")]
    led["stitch"] = rec
    led.setdefault("real_media_scenes", [])
    for sid in swapped:
        if sid not in led["real_media_scenes"]:
            led["real_media_scenes"].append(sid)
    json.dump(led, open(led_path, "w"), indent=2)
    print("RUN %s: swapped %s -> re-stitched %ss (%d clips)"
          % (run_id, ", ".join(swapped), rec["duration_s"], rec["clip_count"]))


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    run_id = sys.argv[1]
    mapping = {}
    for pair in sys.argv[2:]:
        sid, _, path = pair.partition("=")
        mapping[sid] = os.path.expanduser(path)
    apply(run_id, mapping)


if __name__ == "__main__":
    main()
