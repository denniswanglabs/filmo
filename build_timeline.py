#!/usr/bin/env python3
"""build_timeline.py — invert the duration lock: build the picture from the voice.

Phase 1, module 2 of the VO-driven style engine
(docs/2026-06-21-vo-driven-style-engine-design.md).

Root cause this kills (plan_job.py:117 / _restyle_durations): scene durations are
locked BEFORE the voiceover exists, then the VO is squeezed into fixed slots. Here
we do the opposite — the word-aligned voiceover owns the timeline, and each scene's
in_frame/out_frame is derived from the span of the words spoken over it.

Inputs:
  - scenes.json       ordered scenes from the plan. `duration_s` is ADVISORY only
                      (pricing hint) and is NEVER used to lay out a VOICED scene.
                      Shape: [{id, archetype, duration_s?, cues?:[{label, word|word_index}]}]
  - vo_alignment.json the contract from align_vo.py:
                      {audio_path, lang, total_duration_s,
                       words:[{word, start_s, end_s, beat_scene_id}],
                       beats:[{scene_id, start_s, end_s, text}]}

Output: timeline.json
  {fps, total_frames, audio_path, lang,
   scenes:[{id, archetype, in_frame, out_frame,
            cues:[{label, word, at_frame}]}]}

Rules (the contract this module guarantees):
  1. Voiced scene (has a VO beat / owned words) -> in/out from its word span.
  2. Unvoiced scene (e.g. a logo hold) -> advisory hold from duration_s
     (default 1.5s), SLID in after the previous scene (no gap).
  3. Cut scenes (in the plan but removed/declined: no beat AND not present) ->
     skipped; the rest slide earlier (no dead air).
  4. Reveal cues map a scene cue's word / word_index -> at_frame.
  5. Contiguity: no overlaps, no gaps; the last scene's out_frame == total_frames.
  6. duration_s is advisory/pricing-only — only the fallback hold for unvoiced.

CLI:
  python3 build_timeline.py --scenes-file scenes.json \
      --alignment runs/<id>/vo_alignment.json --fps 30 --out runs/<id>/timeline.json
"""

from __future__ import annotations

import argparse
import json
from typing import Any, Dict, List, Optional

DEFAULT_FPS = 30
# Advisory hold for an unvoiced scene when its duration_s is absent/non-positive.
DEFAULT_HOLD_S = 1.5


def _scene_word_span(scene_id: str, alignment: Dict[str, Any]):
    """Return (start_s, end_s, words) for the words/beat owned by scene_id.

    Prefers explicit per-scene beats (beats[].scene_id), falling back to the union
    of words whose beat_scene_id matches. Returns (None, None, []) when the scene
    has no voice at all (an unvoiced hold or a cut scene).
    """
    words = [w for w in alignment.get("words", []) if w.get("beat_scene_id") == scene_id]
    beat = None
    for b in alignment.get("beats", []):
        if b.get("scene_id") == scene_id:
            beat = b
            break

    if beat is not None and beat.get("start_s") is not None and beat.get("end_s") is not None:
        # Beat boundaries are authoritative; keep the owned words for cue resolution.
        return float(beat["start_s"]), float(beat["end_s"]), words

    if words:
        start = min(float(w["start_s"]) for w in words)
        end = max(float(w["end_s"]) for w in words)
        return start, end, words

    return None, None, []


def _resolve_cues(scene: Dict[str, Any], words: List[Dict[str, Any]], fps: int):
    """Map each scene cue (by word text or word_index, within the scene's span)
    to {label, word, at_frame}. Cues that cannot be resolved are skipped."""
    resolved: List[Dict[str, Any]] = []
    for cue in scene.get("cues") or []:
        label = cue.get("label")
        target: Optional[Dict[str, Any]] = None
        word_text: Optional[str] = None

        if "word_index" in cue and cue["word_index"] is not None:
            idx = int(cue["word_index"])
            if 0 <= idx < len(words):
                target = words[idx]
                word_text = target.get("word")
        elif cue.get("word") is not None:
            want = str(cue["word"]).strip().lower().strip(".,!?;:")
            for w in words:
                if str(w.get("word", "")).strip().lower().strip(".,!?;:") == want:
                    target = w
                    word_text = cue["word"]
                    break

        if target is None:
            continue
        resolved.append({
            "label": label,
            "word": word_text,
            "at_frame": round(float(target["start_s"]) * fps),
        })
    return resolved


def _is_cut(scene: Dict[str, Any]) -> bool:
    """A scene explicitly marked as cut/declined/removed by upstream is skipped.

    Upstream (the money gate) may flag a removed scene rather than deleting it from
    scenes.json. Any of these truthy markers drops the scene; the rest slide earlier.
    """
    if scene.get("cut") or scene.get("declined") or scene.get("removed"):
        return True
    status = str(scene.get("status", "")).strip().lower()
    return status in ("cut", "declined", "removed", "dropped")


def build_timeline(scenes: List[Dict[str, Any]], alignment: Dict[str, Any],
                   fps: int = DEFAULT_FPS) -> Dict[str, Any]:
    """Core: scenes + alignment -> contiguous, VO-anchored timeline dict.

    Slide rule (guarantees contiguity): every scene's in_frame == the previous
    kept scene's out_frame (first scene starts at 0, no gaps, no overlaps). A
    voiced scene's length comes from its word span; an unvoiced scene's length is
    the advisory hold from duration_s (default DEFAULT_HOLD_S). Cut scenes are
    skipped so the rest slide earlier. The last scene's out_frame is clamped to
    total_frames so the picture exactly covers the audio.
    """
    total_s = float(alignment.get("total_duration_s") or 0.0)
    total_frames = round(total_s * fps)

    out_scenes: List[Dict[str, Any]] = []
    cursor = 0  # the running out_frame of the last placed scene (== next in_frame)

    for scene in scenes:
        if _is_cut(scene):
            continue  # skip; following scenes slide earlier (rule 3)

        sid = scene.get("id")
        start_s, end_s, words = _scene_word_span(sid, alignment)
        in_frame = cursor

        if start_s is not None and end_s is not None:
            # Voiced: length from the word span. NEVER from duration_s (the bug). The
            # span's own frame length is preserved; the scene slides to `cursor` so
            # there are no gaps even if the beat's absolute start drifted.
            span_frames = max(1, round(end_s * fps) - round(start_s * fps))
            out_frame = in_frame + span_frames
        else:
            # Unvoiced hold (e.g. a logo hold) or a beatless scene: advisory only.
            hold_s = scene.get("duration_s")
            try:
                hold_s = float(hold_s)
            except (TypeError, ValueError):
                hold_s = 0.0
            if hold_s <= 0:
                hold_s = DEFAULT_HOLD_S
            out_frame = in_frame + max(1, round(hold_s * fps))

        out_scenes.append({
            "id": sid,
            "archetype": scene.get("archetype"),
            "in_frame": in_frame,
            "out_frame": out_frame,
            # Cue at_frame anchors to the absolute word start; rebase into the slid
            # scene by the same offset the scene moved (in_frame - span start frame).
            "_cues_raw": _resolve_cues(scene, words, fps),
            "_span_in": (round(start_s * fps) if start_s is not None else in_frame),
        })
        cursor = out_frame

    # Rebase cue frames onto the slid (contiguous) scene positions, then finalize.
    for s in out_scenes:
        offset = s["in_frame"] - s.pop("_span_in")
        cues = []
        for c in s.pop("_cues_raw"):
            at = c["at_frame"] + offset
            at = min(max(at, s["in_frame"]), s["out_frame"])  # clamp inside the scene
            cues.append({"label": c["label"], "word": c["word"], "at_frame": at})
        s["cues"] = cues

    # Clamp the last scene to exactly cover the audio (no silent tail / no overrun).
    if out_scenes:
        if total_frames <= out_scenes[-1]["in_frame"]:
            # Audio shorter than the laid-out picture: keep a >=1-frame last scene.
            total_frames = out_scenes[-1]["in_frame"] + 1
        out_scenes[-1]["out_frame"] = total_frames
        # Re-clamp last scene's cues to the new out_frame.
        for c in out_scenes[-1]["cues"]:
            c["at_frame"] = min(c["at_frame"], total_frames)
    else:
        total_frames = max(total_frames, 0)

    return {
        "fps": fps,
        "total_frames": total_frames,
        "audio_path": alignment.get("audio_path"),
        "lang": alignment.get("lang"),
        "scenes": out_scenes,
    }


def _load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Build a VO-driven timeline.json.")
    ap.add_argument("--scenes-file", required=True, help="ordered scenes JSON (list or {scenes:[...]})")
    ap.add_argument("--alignment", required=True, help="vo_alignment.json from align_vo.py")
    ap.add_argument("--fps", type=int, default=DEFAULT_FPS)
    ap.add_argument("--out", required=True, help="output timeline.json path")
    args = ap.parse_args(argv)

    raw_scenes = _load_json(args.scenes_file)
    scenes = raw_scenes["scenes"] if isinstance(raw_scenes, dict) else raw_scenes
    alignment = _load_json(args.alignment)

    timeline = build_timeline(scenes, alignment, fps=args.fps)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(timeline, fh, indent=2)
    print(f"wrote {args.out}: {timeline['total_frames']} frames, "
          f"{len(timeline['scenes'])} scenes @ {timeline['fps']}fps")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
