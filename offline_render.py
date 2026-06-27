#!/usr/bin/env python3
"""Offline (no-network) Timeline render from an EXISTING run's plan.json.

Bypasses capture + VO synthesis (the flaky SSL/streaming stages) by feeding
build_timeline a SYNTHETIC EMPTY alignment, so every scene holds for its
`duration_s` floor (silent render). This is a deterministic, $0, network-free
way to VISUALLY verify card layout / read-time / badge changes -- the cards
render identically with or without audio. NOT a substitute for a hosted gen of
the production pipeline; it only re-renders an already-planned run.

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

    # Synthetic EMPTY alignment -> span_frames/beat_audio_frames = 0 ->
    # build_timeline length = max(plan_frames(duration_s), media_frames). Silent.
    align_path = os.path.join(run_dir, "vo_alignment.json")
    with open(align_path, "w", encoding="utf-8") as fh:
        json.dump({"beats": [], "words": [], "total_duration_s": 0.0,
                   "audio_path": None, "lang": "en"}, fh)

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
