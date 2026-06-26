#!/usr/bin/env python3
"""LOOP fast-measure: turn an existing runs/<id>/plan.json (+ brand_theme.json) into
a card-judgeable props.json WITHOUT the edge-tts/whisper VO synth that hangs locally.
Writes a deterministic stub vo_alignment.json (~0.34s/word), runs style_fill with
do_align=False (so the post-fill treatment pass runs on the REAL filled copy), then
strips audio + screenshot/logo srcs so a local Remotion render of the CARD LAYOUTS
succeeds. Prints the treatments. Usage: python3 loop_measure.py <run-id>"""
import json, os, sys
import build_runner, style_fill

run_id = sys.argv[1]
run_dir = f"runs/{run_id}"
plan = json.load(open(f"{run_dir}/plan.json"))
beats = (plan.get("voiceover") or {}).get("beats") or []

# --- deterministic stub alignment (no synth, no network) ---
WPS = 0.34
words, t = [], 0.0
for b in beats:
    sid = b.get("scene_id")
    for w in (b.get("text") or "").split():
        words.append({"word": w, "start_s": round(t, 3), "end_s": round(t + WPS, 3), "beat_scene_id": sid})
        t += WPS
out_beats = []
for b in beats:
    sid = b.get("scene_id")
    bw = [w for w in words if w["beat_scene_id"] == sid]
    if bw:
        out_beats.append({"scene_id": sid, "start_s": bw[0]["start_s"], "end_s": bw[-1]["end_s"], "text": b.get("text", "")})
align = {"audio_path": f"{run_dir}/voiceover.mp3", "lang": "en", "voice": "stub",
         "tier": "free", "total_duration_s": round(t, 3), "words": words, "beats": out_beats}
json.dump(align, open(f"{run_dir}/vo_alignment.json", "w"), indent=2)

# --- style_fill reusing the stub alignment (runs the post-fill treatment pass) ---
res = style_fill.run_pipeline(f"{run_dir}/plan.json", f"{run_dir}/brand_theme.json",
                              build_runner.VO_ENGINE_STYLE, run_dir, do_align=False, do_render=False)
props_path = res["props_path"]

# --- strip un-resolvable-locally assets so the card render doesn't cancel ---
p = json.load(open(props_path))
p["audio_path"] = ""
p["voiceover"] = []
th = p.get("theme", {})
th["music"] = ""
for k in ("logoSrc", "logo_src"):
    th.pop(k, None)
for s in (p.get("scenes") or []):
    s.pop("audio", None)
    d = s.get("data") or {}
    for k in list(d.keys()):
        # Strip un-resolvable-locally asset PATHS (logoSrc/imageSrc/etc.) but NOT
        # entityLogos — those are self-contained data URIs that render fine locally.
        if k == "entityLogos":
            continue
        if any(x in k.lower() for x in ("imagesrc", "screenshot", "logosrc", "imgsrc", "videosrc")):
            d[k] = ""
json.dump(p, open(props_path, "w"))

print("=== TREATMENTS ===")
for s in (p.get("scenes") or []):
    d = s.get("data") or {}
    ty = str(s.get("type", ""))
    if "explainer" in ty or "motion" in ty or d.get("treatment"):
        print("  treatment=", d.get("treatment"), "| stat=", json.dumps(d.get("stat")),
              "| ents=", d.get("featureEntities"), "| title=", (d.get("title") or "")[:42])
print("PROPS:", os.path.abspath(props_path))
print("SCENE_TYPES:", [s.get("type") for s in (p.get("scenes") or [])])
