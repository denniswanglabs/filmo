#!/usr/bin/env python3
"""Finishing pass — turn a raw stitched run into a B+ promo cut (all $0).

Raw stitch = hard cuts, no music, flat. This adds the craft layer:
  - a unifying color grade across every clip (so cinematic + screen-cap + titles cohere)
  - a slow push-in (zoompan) on the otherwise-static walkthrough screen capture
  - crossfade dissolves between scenes (no hard cuts)
  - a royalty-free music bed sidechain-DUCKED under the edge-tts VO, with fades
  - fade from / to black; the audio tail outlasts the visual fade

Reads the run's produced clips (in plan order) from the ledger and overwrites
final.mp4. The P&L / money layer are untouched — this is finishing, not money.

Usage: python3 finish_cut.py <run_id> [<music.mp3>]
"""

import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RUNS = os.path.join(HERE, "runs")
MUSIC_DEFAULT = os.path.join(HERE, "assets", "music-bed.mp3")
W, H, FPS = 1920, 1080, 30
XF = 0.45  # crossfade seconds
GRADE = "eq=contrast=1.07:saturation=1.14:brightness=0.012:gamma=0.98,unsharp=3:3:0.25"


def dur(p):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", p], capture_output=True, text=True).stdout.strip()
    return float(out)


def finish(run_id, music):
    run_dir = os.path.join(RUNS, run_id)
    led_path = os.path.join(run_dir, "ledger.json")
    led = json.load(open(led_path))
    scenes = sorted([s for s in led["scenes"] if s.get("output_path")], key=lambda s: s["order"])
    clips = [(os.path.join(run_dir, s["output_path"]), s["type"]) for s in scenes]
    durs = [dur(c[0]) for c in clips]
    n = len(clips)
    vo = os.path.join(run_dir, "voiceover.mp3")
    has_vo = os.path.exists(vo)
    out = os.path.join(run_dir, "final.mp4")
    total = sum(durs) - XF * (n - 1)

    # Scene start offsets ON THE CROSSFADE TIMELINE (each xfade overlaps XF s, so a
    # clip starts XF earlier than a hard concat would put it). If the ledger has the
    # per-beat VO segments, re-place each beat at its produced scene's crossfade
    # offset so narration stays locked to the picture through the finishing pass too.
    xf_offset = {}
    acc = 0.0
    for (c, _typ), d in zip(clips, durs):
        sid = next((s["id"] for s in scenes
                    if os.path.join(run_dir, s["output_path"]) == c), None)
        if sid is not None:
            xf_offset[sid] = round(acc, 3)
        acc += d - XF
    vo_segments = (led.get("voiceover") or {}).get("segments") or []
    vo_segments = [seg for seg in vo_segments
                   if seg.get("scene_id") in xf_offset
                   and os.path.exists(os.path.join(run_dir, os.path.basename(seg.get("path", ""))))]

    use_beats = bool(vo_segments)
    inputs = []
    for c, _ in clips:
        inputs += ["-i", c]
    music_idx = n
    inputs += ["-i", music]
    # VO inputs: either the per-beat segments (each re-placed at its crossfade
    # offset) or the single pre-mixed track (legacy / no-segment runs).
    beat_idx = []
    vo_idx = None
    if use_beats:
        for seg in vo_segments:
            beat_idx.append(len(inputs) // 2)  # next input index
            inputs += ["-i", os.path.join(run_dir, os.path.basename(seg["path"]))]
    elif has_vo:
        vo_idx = len(inputs) // 2
        inputs += ["-i", vo]

    fc = []
    # per-clip: fit -> grade -> (walkthrough push-in) -> yuv420p
    for i, ((c, typ), d) in enumerate(zip(clips, durs)):
        chain = ("[%d:v]scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d,"
                 "fps=%d,setsar=1,%s" % (i, W, H, W, H, FPS, GRADE))
        if typ == "walkthrough":
            chain += (",zoompan=z='min(max(zoom,1.0)+0.00045,1.12)':d=1:"
                      "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=%dx%d:fps=%d" % (W, H, FPS))
        chain += ",format=yuv420p[v%d]" % i
        fc.append(chain)

    # crossfade chain
    cur, off = "v0", durs[0] - XF
    for k in range(1, n):
        fc.append("[%s][v%d]xfade=transition=fade:duration=%.3f:offset=%.3f[x%d]"
                  % (cur, k, XF, off, k))
        cur = "x%d" % k
        off += durs[k] - XF
    fc.append("[%s]fade=t=in:st=0:d=0.5,fade=t=out:st=%.3f:d=0.7[vout]"
              % (cur, total - 0.7))

    # audio: music bed ducked under the VO
    fc.append("[%d:a]atrim=0:%.3f,asetpts=PTS-STARTPTS,afade=t=in:st=0:d=0.8,"
              "afade=t=out:st=%.3f:d=1.2[musraw]" % (music_idx, total, total - 1.2))
    if use_beats:
        # Re-place each beat at its scene's CROSSFADE-timeline offset so narration
        # stays locked to the picture even after the dissolves compress the cut.
        for j, seg in enumerate(vo_segments):
            ms = int(round(xf_offset[seg["scene_id"]] * 1000))
            fc.append("[%d:a]aresample=48000,adelay=%d|%d[vb%d]" % (beat_idx[j], ms, ms, j))
        labels = "".join("[vb%d]" % j for j in range(len(vo_segments)))
        fc.append("%samix=inputs=%d:duration=longest:normalize=0,asplit=2[vomix][vokey]"
                  % (labels, len(vo_segments)))
        fc.append("[musraw]volume=0.5[musv]")
        fc.append("[musv][vokey]sidechaincompress=threshold=0.02:ratio=7:attack=15:release=380[musduck]")
        fc.append("[musduck][vomix]amix=inputs=2:duration=first:normalize=0[amix]")
    elif has_vo:
        fc.append("[%d:a]adelay=350|350,aresample=48000,asplit=2[vomix][vokey]" % vo_idx)
        fc.append("[musraw]volume=0.5[musv]")
        fc.append("[musv][vokey]sidechaincompress=threshold=0.02:ratio=7:attack=15:release=380[musduck]")
        fc.append("[musduck][vomix]amix=inputs=2:duration=first:normalize=0[amix]")
    else:
        fc.append("[musraw]volume=0.85[amix]")
    # EBU R128 delivery loudness on the final mixed track (after duck/mix), so the
    # cut lands at the ~-14 LUFS streaming standard instead of shipping ~6 LU quiet.
    fc.append("[amix]loudnorm=I=-14:TP=-1.0:LRA=11[aout]")

    cmd = ["ffmpeg", "-y", "-nostdin", "-loglevel", "error", *inputs,
           "-filter_complex", ";".join(fc),
           "-map", "[vout]", "-map", "[aout]", "-t", "%.3f" % total,
           "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-ar", "48000", "-ac", "2", "-movflags", "+faststart", out]
    subprocess.run(cmd, check=True, timeout=600)

    led["finish"] = {"graded": True, "crossfade_s": XF,
                     "music": os.path.relpath(music, HERE), "ducked": has_vo,
                     "duration_s": round(total, 2)}
    if led.get("stitch"):
        led["stitch"]["duration_s"] = round(total, 2)
        led["stitch"]["finished"] = True
    json.dump(led, open(led_path, "w"), indent=2)
    print("FINISHED %s -> %s (%.1fs, %d clips, music=%s, ducked=%s)"
          % (run_id, out, total, n, os.path.basename(music), has_vo))


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    music = sys.argv[2] if len(sys.argv) > 2 else MUSIC_DEFAULT
    finish(sys.argv[1], music)


if __name__ == "__main__":
    main()
