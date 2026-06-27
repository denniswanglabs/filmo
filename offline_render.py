#!/usr/bin/env python3
"""Offline (no-network) Timeline render from an EXISTING run's plan.json.

Bypasses capture + VO synthesis (the flaky SSL/streaming stages) by feeding
build_timeline a SYNTHETIC alignment built from the plan's OWN voiceover beats
(real per-scene text, zero timing), so every scene holds for its `duration_s`
floor (silent render) BUT each scene still carries the line it would be narrated
over. This matters because the title shapers derive the on-screen headline from
the threaded VO text (`_beat_text` -> `_derive_text` -> scene `_text`): an EMPTY
alignment would make the opening fall back to its scene-direction `brief`
("<Brand> wordmark cold-open with kinetic-light canvas") instead of the real
value-prop headline a production VO gen would show. Threading the plan's VO text
(no audio, zero span) keeps timing at the `duration_s` floor while making the
copy FAITHFUL to a hosted gen. Deterministic, $0, network-free; a way to VISUALLY
verify card layout / read-time / badge / opening copy. NOT a substitute for a
hosted gen -- it only re-renders an already-planned run, silently.

    python3 offline_render.py <run-id>     # reads runs/<run-id>/plan.json
"""
import json
import os
import subprocess
import sys

import build_timeline
import style_fill

RUNS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "runs")
VO_ENGINE_STYLE = "orinovate-kinetic-light"


def main(run_id: str) -> int:
    run_dir = os.path.join(RUNS, run_id)
    plan_path = os.path.join(run_dir, "plan.json")
    brand_path = os.path.join(run_dir, "brand_theme.json")
    for p in (plan_path, brand_path):
        if not os.path.exists(p):
            print("missing %s" % p, file=sys.stderr)
            return 2

    # Synthetic alignment: carry the plan's OWN per-scene VO TEXT (so the title
    # shapers see the real narrated line, not the scene-direction brief) but with
    # ZERO timing + no audio -> span_frames/beat_audio_frames = 0 -> build_timeline
    # length = max(plan_frames(duration_s), media_frames). Silent, faithful copy.
    with open(plan_path, encoding="utf-8") as fh:
        plan = json.load(fh)
    plan_beats = ((plan.get("voiceover") or {}).get("beats")) or []
    beats = [{"scene_id": b.get("scene_id"), "text": str(b.get("text") or "").strip(),
              "start_s": 0.0, "end_s": 0.0}
             for b in plan_beats if b.get("scene_id") and str(b.get("text") or "").strip()]
    align_path = os.path.join(run_dir, "vo_alignment.json")
    with open(align_path, "w", encoding="utf-8") as fh:
        json.dump({"beats": beats, "words": [], "total_duration_s": 0.0,
                   "audio_path": None, "lang": "en"}, fh)
    print("[offline_render] threaded %d VO beat(s) (text-only, zero timing)" % len(beats))

    # do_align=False reuses the synthetic alignment; do_render=False -> we render below.
    res = style_fill.run_pipeline(plan_path, brand_path, VO_ENGINE_STYLE, run_dir,
                                  fps=30, do_align=False, do_render=False)
    props_path = res["props_path"]
    print("[offline_render] props: %s (%d scenes)"
          % (props_path, len(res["props"]["scenes"])))

    final = os.path.join(run_dir, "final.mp4")
    studio = style_fill.STUDIO_DIR
    env = dict(os.environ, PATH=os.path.join(studio, "node_modules", ".bin")
               + os.pathsep + os.environ.get("PATH", ""))
    cmd = ["remotion", "render", "src/index.ts", "Timeline", os.path.abspath(final),
           "--codec=h264", "--concurrency=50%", "--props=%s" % os.path.abspath(props_path)]
    r = subprocess.run(cmd, cwd=studio, env=env)
    if r.returncode != 0 or not os.path.exists(final):
        print("[offline_render] RENDER FAILED rc=%s" % r.returncode, file=sys.stderr)
        return 1
    print("[offline_render] OK -> %s" % final)
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__, file=sys.stderr)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
