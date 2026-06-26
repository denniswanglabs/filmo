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
import os as _os
import re as _re
import subprocess as _subprocess
from typing import Any, Dict, List, Optional

DEFAULT_FPS = 30
# Advisory hold for an unvoiced scene when its duration_s is absent/non-positive.
DEFAULT_HOLD_S = 1.5

# VO-FIT (2026-06-26) — the headline fix for "the voiceover gets cut over every
# change of scene". The renderer plays each scene's OWN per-beat VO file
# (scene.audio.src = voiceover.beatNN.mp3, synthesized by adapters in a SEPARATE
# pass), but the scene's VISUAL span was sized only from the alignment word-span
# (span_frames), which is the span of that beat's words INSIDE the stitched
# continuous track — routinely MUCH shorter than the standalone per-beat mp3. So a
# scene's picture ended before its narration did and the audio was truncated at the
# cut. The fix: FLOOR each scene's frame span to the per-beat mp3's real SPEECH
# length (raw duration minus trailing silence) plus a small tail pad, so the scene
# always holds at least as long as its own voice. We trim trailing silence first so
# we floor to the spoken length, not the padded length (no over-growing).
# Tail pad after the last spoken word so the cut never clips the final phoneme.
# Sized to comfortably cover the per-beat mp3's trailing silence (measured up to
# ~0.5s on ElevenLabs, ~0.25s on edge-tts) PLUS a small margin, so the scene visual
# holds for the WHOLE audio file (raw duration), not just up to the last word — i.e.
# the cut lands in true silence, never on a phoneme. We still measure SPEECH (raw
# minus trailing silence) first so a beat with an EXTRA-long trailing silence does
# not over-grow the scene by that full silence; the pad is the only headroom we add.
_VO_TAIL_PAD_S = 0.55
# Silence detection threshold/min-duration for finding the TRAILING silence run.
_VO_SILENCE_NOISE_DB = -38.0
_VO_SILENCE_MIN_S = 0.20
# Floor on the measured speech length: a beat shorter than this is treated as ~all
# speech (avoids a bad probe collapsing a real line to near-zero).
_VO_MIN_SPEECH_S = 0.30

_SIL_START_RE = _re.compile(r"silence_start:\s*([0-9.]+)")
_SIL_END_RE = _re.compile(r"silence_end:\s*([0-9.]+)")


def _ffprobe_seconds(path: str) -> float:
    """Raw container duration of an audio file in seconds (0.0 on any failure)."""
    try:
        out = _subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", path],
            capture_output=True, text=True, timeout=30).stdout.strip()
        return float(out)
    except Exception:
        return 0.0


def _beat_speech_seconds(path: str) -> float:
    """The SPEECH length of a per-beat VO mp3 = raw duration minus any TRAILING
    silence run.

    ElevenLabs (and edge-tts) mp3s carry a short trailing silence that inflates the
    raw duration; flooring a scene to the raw length would over-grow every scene.
    We run ffmpeg `silencedetect` and, if the LAST detected silence run reaches the
    end of the file (silence_start present with no later silence_end, OR a
    silence_end within a hair of raw duration), subtract that trailing silence so we
    floor to the last spoken moment. Returns 0.0 only when the file is unreadable
    (so the caller leaves the scene span unchanged rather than collapsing it)."""
    raw = _ffprobe_seconds(path)
    if raw <= 0:
        return 0.0
    try:
        proc = _subprocess.run(
            ["ffmpeg", "-nostdin", "-i", path, "-af",
             "silencedetect=noise=%gdB:d=%g" % (_VO_SILENCE_NOISE_DB, _VO_SILENCE_MIN_S),
             "-f", "null", "-"],
            capture_output=True, text=True, timeout=60)
        log = (proc.stderr or "") + (proc.stdout or "")
    except Exception:
        # Can't analyse silence — fall back to the raw duration (never cuts voice).
        return raw

    starts = [float(m) for m in _SIL_START_RE.findall(log)]
    ends = [float(m) for m in _SIL_END_RE.findall(log)]
    speech_end = raw
    if starts:
        last_start = starts[-1]
        # The trailing run reaches EOF when there is no silence_end after the last
        # silence_start, or the last silence_end lands within ~50ms of the raw end.
        trailing_to_eof = (len(ends) < len(starts)) or \
            (ends and abs(ends[-1] - raw) <= 0.05)
        if trailing_to_eof and last_start < raw:
            speech_end = last_start
    # Never collapse a real beat to ~zero on a noisy probe.
    return max(speech_end, min(raw, _VO_MIN_SPEECH_S))


def _beat_audio_floor_frames(beat_path: Optional[str], fps: int) -> int:
    """Frames the scene must hold so its OWN per-beat VO is never cut:
    round((speech_seconds + tail_pad) * fps). 0 when there is no readable beat file
    (the caller then falls back to the alignment span / plan / media floors)."""
    if not beat_path or not _os.path.exists(beat_path):
        return 0
    speech_s = _beat_speech_seconds(beat_path)
    if speech_s <= 0:
        return 0
    return max(1, round((speech_s + _VO_TAIL_PAD_S) * fps))

# R5 (L9 confirmed on Stripe/Notion/Shopify) — the walkthrough scene must not exceed
# the pacing budget. The captured walk clip's own length (media_frames floor) pushed
# the scene window to 10-11s on all three brands, dragging pacing below 4.
# DARKFIX (2026-06-23) — the walkthrough is the LONGEST scene (~1/3 of a 24s video)
# and DRAGS on a dark site (the captured page reads heavy). Tighten the cap to ~5.5s
# so the tour is brisk + intentional. Cap the walkthrough SCENE WINDOW (not the clip):
# the device-frame player just shows the first WALKTHROUGH_MAX_FRAMES of the clip. The
# clamp below is max(WALKTHROUGH_MAX_FRAMES, span_frames) so a longer VO span (and the
# media floor, which is itself min()'d to this cap) is NEVER cut. Roles that get it.
WALKTHROUGH_MAX_FRAMES = 165  # ~5.5s @ 30fps (was 270/9.0s — tightened to cut drag)
_WALKTHROUGH_ROLES = ("walkthrough", "demo")

# DURATION ROBUSTNESS — the per-scene HOLD budget. A non-walkthrough scene (title /
# screenshot / explainer) holds at most this long on its finished card; growing a
# sparse plan toward target spreads the deficit across scenes up to this cap so no
# single card stares. == the walkthrough budget so every scene shares one ceiling.
_SCENE_MAX_FRAMES = 270  # 9.0s @ 30fps

# DURATION ROBUSTNESS — tolerance before the over-target shrink bites. A film may run
# up to target * (1 + tol) before holds are squeezed back toward the ceiling; some
# slack keeps a near-target plan untouched. The VO condense (style_fill) already pulls
# a dense plan most of the way; this catches the residue.
_OVER_TARGET_TOL = 0.08

# Map a plan scene `type` (or id keyword) -> a semantic ROLE that style_fill's
# registry can route to an archetype. The plan describes scenes by `type`
# ("title" | "motion_graphic" | "cinematic" | "walkthrough" | "demo" | ...) but
# style_fill's role_map keys on roles like "title"/"feature"/"explainer". Without
# this bridge a `motion_graphic` feature beat has NO role_map entry and silently
# falls to the hero-title default -> every scene renders the same (blank) hero.
# This is the threading the blank-scenes bug needs: role travels plan -> timeline
# -> props so the feature beats actually reach the explainer-card.
_TYPE_TO_ROLE = {
    "title": "title",
    "hero": "hero",
    "intro": "intro",
    "open": "open",
    "close": "close",
    "cta": "cta",
    "outro": "outro",
    # animated feature beats (the bug's victims) -> the designed explainer card.
    "motion_graphic": "feature",
    "motion-graphic": "feature",
    "feature": "feature",
    "capability": "capability",
    "capabilities": "capabilities",
    "cards": "cards",
    "grid": "grid",
    # cinematic / walkthrough / demo beats with no real footage -> explainer card.
    "cinematic": "cinematic",
    "walkthrough": "walkthrough",
    "demo": "demo",
    "explainer": "explainer",
    # a real captured website view -> the apple-screenshot browser card.
    "screenshot": "screenshot",
    "site": "screenshot",
}

# Keywords in a scene id that hint a role when `type` is missing/unknown.
_ID_ROLE_HINTS = (
    ("close", "close"), ("cta", "cta"), ("outro", "outro"), ("end", "close"),
    ("open", "open"), ("intro", "intro"), ("hero", "hero"), ("title", "title"),
    ("feature", "feature"), ("how", "feature"), ("what", "feature"),
    ("why", "feature"), ("stat", "feature"),
)


# Id keywords that mark a TITLE scene as the CLOSING title (CTA), not the opening
# one. Both opening + closing carry type "title" / role "title", so the id is the
# only signal that separates them. A closing title gets role "close" so style_fill
# shapes it as a call-to-action (its CTA line as the headline) instead of repeating
# the brand wordmark. Opening titles keep role "title" -> brand wordmark + tagline.
_CLOSING_ID_HINTS = ("clos", "cta", "outro", "end")


def _derive_role(scene: Dict[str, Any]) -> str:
    """A semantic role for a plan scene, NEVER None.

    Priority: explicit `role` -> closing-title override -> mapped `type` -> id
    keyword hint -> generic "feature" (a content card) so an unknown scene still
    gets a real archetype and real copy rather than falling to an empty hero. This
    is half the blank-scenes fix: role threads plan -> timeline -> props.
    """
    explicit = str(scene.get("role") or "").strip().lower()
    if explicit:
        return explicit
    stype = str(scene.get("type") or "").strip().lower()
    sid = str(scene.get("id") or "").strip().lower()
    # A title scene whose id signals the close (e.g. "closing-title") is the CTA,
    # not the opening lockup — give it role "close" so style_fill shows its own CTA
    # line. (Without this both titles map to role "title" -> identical wordmark.)
    if stype in ("title", "hero", "intro") and any(kw in sid for kw in _CLOSING_ID_HINTS):
        return "close"
    if stype in _TYPE_TO_ROLE:
        return _TYPE_TO_ROLE[stype]
    for kw, role in _ID_ROLE_HINTS:
        if kw in sid:
            return role
    # Unknown -> a content card (feature), not an empty hero. Never None.
    return stype or "feature"


def _beat_text(scene_id: str, alignment: Dict[str, Any]) -> str:
    """The VO beat text owned by scene_id (the line actually narrated over it)."""
    for b in alignment.get("beats", []):
        if b.get("scene_id") == scene_id:
            return str(b.get("text") or "").strip()
    return ""


def _derive_text(scene: Dict[str, Any], alignment: Dict[str, Any],
                 brand_fallback: str = "") -> str:
    """The card TEXT for a scene, NEVER empty.

    Priority (per the blank-scenes fix): the scene's VO beat text (what is
    actually spoken over it) -> the plan scene `brief` -> any explicit
    data.title -> a brand-derived fallback (tagline/wordmark). The text threads
    plan/VO -> timeline -> props so style_fill can populate a real title even
    when the plan scene carries no `data` block.
    """
    sid = scene.get("id")
    vo = _beat_text(sid, alignment)
    if vo:
        return vo
    brief = str(scene.get("brief") or "").strip()
    if brief:
        return brief
    d = scene.get("data") or {}
    explicit = str(d.get("title") or d.get("heading") or "").strip()
    if explicit:
        return explicit
    return str(brand_fallback or "").strip()


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


def _scene_audio(scene_index: int, scene_id: str, alignment: Dict[str, Any],
                 full_audio_path: Optional[str]) -> Optional[Dict[str, Any]]:
    """The per-beat VO audio for this scene, so each scene's <Audio> can start at
    its OWN in_frame (the picture is stretched to the planned duration, so a single
    continuous track from frame 0 would no longer land each beat on its scene).

    align_vo writes the full VO to `<run>/voiceover.mp3` AND one file per beat as
    `<run>/voiceover.beat{NN}.mp3` (00-indexed, in plan/beat order). Resolve the
    per-beat path by index next to the full track. Returns None when there is no
    per-beat file (a scene with no VO, or a build that didn't emit beat files) so
    the caller can fall back to the single continuous track.
    """
    if not full_audio_path:
        return None
    # Only emit audio for a scene that actually owns a VO beat.
    has_beat = any(b.get("scene_id") == scene_id for b in alignment.get("beats", []))
    if not has_beat:
        return None
    import os as _os
    base, ext = _os.path.splitext(full_audio_path)
    if not ext:
        ext = ".mp3"
    beat_path = f"{base}.beat{scene_index:02d}{ext}"
    if not _os.path.exists(beat_path):
        return None
    return {"src": beat_path}


def _apportion(amount: int, capacities: List[int]) -> List[int]:
    """Split a non-negative integer `amount` across buckets, each capped by its
    capacity, proportional to capacity, summing to min(amount, sum(capacities)).
    Largest-remainder method — deterministic, bounded, NEVER loops (the old
    `while drift` round-robin could spin when rounding overshot). Used by both the
    grow (capacity = headroom) and shrink (capacity = slack) passes."""
    n = len(capacities)
    total_cap = sum(capacities)
    give = min(max(0, amount), total_cap)
    if n == 0 or give <= 0 or total_cap <= 0:
        return [0] * n
    # Floor share + fractional remainder per bucket.
    raw = [give * c / total_cap for c in capacities]
    out = [min(int(r), cap) for r, cap in zip(raw, capacities)]
    left = give - sum(out)
    # Hand the remaining units one-by-one to the buckets with the largest fraction
    # that still have headroom. Bounded by `left` (<= n in the worst case after the
    # proportional pass, but loop on remaining-capacity buckets to be safe).
    order = sorted(range(n), key=lambda i: (raw[i] - int(raw[i])), reverse=True)
    idx = 0
    guard = left + n  # hard upper bound on iterations — can never infinite-loop
    while left > 0 and guard > 0:
        i = order[idx % n]
        if out[i] < capacities[i]:
            out[i] += 1
            left -= 1
        idx += 1
        guard -= 1
    return out


def _relayout(out_scenes: List[Dict[str, Any]], lengths: List[int]) -> None:
    """Rewrite in/out frames contiguously from per-scene lengths (no gaps/overlaps),
    sliding each scene's cues by the same delta its in_frame moved so a word-anchored
    reveal stays put relative to its scene."""
    cursor = 0
    for s, length in zip(out_scenes, lengths):
        delta = cursor - s["in_frame"]
        s["in_frame"] = cursor
        s["out_frame"] = cursor + length
        if delta and s.get("cues"):
            for c in s["cues"]:
                c["at_frame"] = min(max(c["at_frame"] + delta, s["in_frame"]),
                                    s["out_frame"])
        cursor = s["out_frame"]


def _grow_scenes_to_target(out_scenes: List[Dict[str, Any]], target_frames: int,
                           fps: int) -> None:
    """SPARSE-plan fill: grow scene HOLDS to reach target_frames, spread across ALL
    scenes (each capped at the per-scene budget) rather than dumped on the last one.

    A sparse planner (Super) sets short scenes whose VO under-fills the target; the
    old code padded only the LAST scene and the 9s cap then left the film short. Here
    every scene can grow up to _SCENE_MAX_FRAMES (walkthroughs to WALKTHROUGH_MAX),
    so the deficit is absorbed evenly and the film reaches target without one staring
    card. If even all scenes maxed out cannot reach target, the film simply lands as
    long as it can (every scene at its cap) — a slightly short film beats a dead hold.
    """
    lengths = [s["out_frame"] - s["in_frame"] for s in out_scenes]
    caps = [WALKTHROUGH_MAX_FRAMES if s.get("role") in _WALKTHROUGH_ROLES
            else _SCENE_MAX_FRAMES for s in out_scenes]
    # Never shrink here; the cap floor is the scene's current (content-driven) length.
    caps = [max(cap, ln) for cap, ln in zip(caps, lengths)]

    deficit = target_frames - sum(lengths)
    if deficit <= 0:
        return
    # Spread the deficit proportional to each scene's headroom (toward its cap).
    headroom = [cap - ln for cap, ln in zip(caps, lengths)]
    total_head = sum(headroom)
    if total_head <= 0:
        return
    grown = _apportion(deficit, headroom)
    lengths = [ln + g for ln, g in zip(lengths, grown)]
    _relayout(out_scenes, lengths)


def _shrink_holds_to_ceiling(out_scenes: List[Dict[str, Any]], floors: List[int],
                             ceiling: int) -> None:
    """DENSE-plan clamp: shrink scene HOLDS (length above each scene's content floor)
    proportionally so the film total drops to `ceiling`. NEVER shrinks a scene below
    its floor = max(VO span, media) — narration is never cut, a clip never truncated.

    The VO condense (style_fill) keeps the voice near budget upstream; this is the
    safety net for a plan that STILL overruns (a brain that wrote past the budget). If
    the floors alone already exceed the ceiling (all content, no holds to cut), the
    film is left at its floor total — a faithful (slightly long) film beats cutting
    the voice. Floors must not exceed the scene's current length (a defensive clamp).
    """
    lengths = [s["out_frame"] - s["in_frame"] for s in out_scenes]
    floors = [min(f, ln) for f, ln in zip(floors, lengths)]
    slack = [ln - f for ln, f in zip(lengths, floors)]  # removable hold per scene
    total_slack = sum(slack)
    overshoot = sum(lengths) - ceiling
    if overshoot <= 0 or total_slack <= 0:
        return
    removed = _apportion(overshoot, slack)
    lengths = [ln - r for ln, r in zip(lengths, removed)]
    _relayout(out_scenes, lengths)


def build_timeline(scenes: List[Dict[str, Any]], alignment: Dict[str, Any],
                   fps: int = DEFAULT_FPS,
                   brand_fallback: str = "",
                   target_duration_s: Optional[float] = None,
                   honor_plan_durations: bool = True) -> Dict[str, Any]:
    """Core: scenes + alignment -> contiguous timeline dict that HOLDS its content.

    Duration contract (the fix): each scene's length is
        max(plan duration_s, its VO word span)
    so the scene HOLDS for its planned time (reveals finish, card is read) but is
    NEVER shorter than its voice (the VO is never cut off). in/out frames are the
    cumulative sum of these lengths (first scene at 0, no gaps, no overlaps). When
    `target_duration_s` is given and the laid-out picture is shorter, the LAST scene
    is padded so the total equals target_duration_s exactly (or stays >= target if a
    beat's VO overran its planned slot). Cut scenes are skipped (rest slide earlier).

    `honor_plan_durations=False` (or a missing target AND no positive duration_s on
    any scene) falls back to the OLD VO-span-drives-everything behavior, so a caller
    without plan timing still gets a graceful, voice-length timeline.

    Word-anchored reveals stay INSIDE each scene: cue at_frames remain anchored to
    the VO word timings relative to the (slid) scene start; after the reveal the
    scene simply holds its finished card until out_frame.

    AUDIO: each voiced scene carries an `audio` block ({src}) for its OWN per-beat
    VO file, rendered at the scene's in_frame so the voice still lands on its scene
    even though scenes are stretched. The top-level `audio_path` (full continuous
    track) is kept as a fallback for the composition.

    Each emitted scene also carries a `role` (never None) and `text` (never empty)
    threading plan/VO content to props (the separate blank-scenes fix).
    """
    total_s = float(alignment.get("total_duration_s") or 0.0)
    audio_frames = round(total_s * fps)
    full_audio_path = alignment.get("audio_path")

    out_scenes: List[Dict[str, Any]] = []
    cursor = 0  # the running out_frame of the last placed scene (== next in_frame)
    scene_index = 0  # parallels align_vo's beat ordering (skips cut scenes)

    for scene in scenes:
        if _is_cut(scene):
            continue  # skip; following scenes slide earlier (rule 3)

        sid = scene.get("id")
        start_s, end_s, words = _scene_word_span(sid, alignment)
        in_frame = cursor

        # VO word-span length (frames) for this scene, 0 when unvoiced.
        if start_s is not None and end_s is not None:
            span_frames = max(1, round(end_s * fps) - round(start_s * fps))
        else:
            span_frames = 0

        # VO-FIT FLOOR (the headline fix): the scene plays its OWN per-beat mp3
        # (resolved below as scene.audio.src). That standalone file is routinely
        # LONGER than span_frames (which is only the beat's words inside the stitched
        # track), so the picture used to end before the voice and the narration was
        # cut at the scene change. Measure the per-beat mp3's real SPEECH length
        # (trailing silence trimmed) + a tail pad and FLOOR the scene to it. 0 when
        # the scene has no per-beat file (unvoiced / not yet synthesized).
        beat_path = _scene_audio(scene_index, sid, alignment, full_audio_path)
        beat_audio_frames = _beat_audio_floor_frames(
            (beat_path or {}).get("src"), fps)

        # Planned hold (frames) from the plan scene's duration_s (the FLOOR).
        plan_hold_s = scene.get("duration_s")
        try:
            plan_hold_s = float(plan_hold_s)
        except (TypeError, ValueError):
            plan_hold_s = 0.0
        plan_frames = max(0, round(plan_hold_s * fps)) if plan_hold_s > 0 else 0

        # Media-length FLOOR (frames) from a real produced clip's duration. A
        # walkthrough-player (or any scene carrying a fixed-length clip) must HOLD
        # at least as long as its media so OffthreadVideo never truncates the clip.
        # ffprobe it ONCE at build time, or accept a precomputed `media_duration_s`.
        media_dur_s = scene.get("media_duration_s")
        try:
            media_dur_s = float(media_dur_s)
        except (TypeError, ValueError):
            media_dur_s = 0.0
        if media_dur_s <= 0:
            media_path = scene.get("media_path") or scene.get("video_path")
            if media_path:
                try:
                    import adapters  # local import; build_timeline stays import-light
                    media_dur_s = float(adapters.ffprobe_duration(media_path) or 0.0)
                except Exception:
                    media_dur_s = 0.0
        media_frames = max(0, round(media_dur_s * fps)) if media_dur_s > 0 else 0

        if honor_plan_durations:
            # HOLD for the planned time, but never shorter than the voice OR a
            # real clip's own length. `beat_audio_frames` (the per-beat mp3's real
            # speech length) is the VO-FIT floor that keeps the narration from being
            # cut at the scene change. A scene with neither a plan duration, a VO
            # span/audio, nor media falls back to DEFAULT_HOLD_S.
            length = max(plan_frames, span_frames, media_frames, beat_audio_frames)
            if length <= 0:
                length = max(1, round(DEFAULT_HOLD_S * fps))
            out_frame = in_frame + length
        elif span_frames > 0 or beat_audio_frames > 0:
            # Legacy: voiced scene length == its voice (max of the word span and the
            # per-beat mp3 speech length), never shorter than a real clip's length.
            out_frame = in_frame + max(span_frames, media_frames, beat_audio_frames)
        else:
            # Legacy unvoiced hold (advisory only), floored by the clip length.
            hold_s = plan_hold_s if plan_hold_s > 0 else DEFAULT_HOLD_S
            out_frame = in_frame + max(1, round(hold_s * fps), media_frames)

        # R5 — CLAMP the walkthrough scene window to the 9s/270f pacing budget. The
        # media_frames floor above lets a 10-11s captured clip blow the budget (L9,
        # confirmed on 3 brands). Cap the SCENE WINDOW so the device-hero player shows
        # only the first 9s of the clip. Only clamp DOWN (never extend a short scene),
        # and respect a longer VO span so narration is never cut — keep max(span, cap).
        if _derive_role(scene) in _WALKTHROUGH_ROLES:
            scene_len = out_frame - in_frame
            # Floor the cap at the voice (word span AND per-beat mp3 speech length)
            # so capping the walkthrough window can never cut its narration.
            cap_len = max(WALKTHROUGH_MAX_FRAMES, span_frames, beat_audio_frames)
            if scene_len > cap_len:
                out_frame = in_frame + cap_len

        out_scenes.append({
            "id": sid,
            "archetype": scene.get("archetype"),
            # role + text thread plan/VO content through to props (blank-scenes
            # fix): role is NEVER None, text is NEVER empty.
            "role": _derive_role(scene),
            "text": _derive_text(scene, alignment, brand_fallback),
            "in_frame": in_frame,
            "out_frame": out_frame,
            # Per-scene VO audio so the voice starts at this (stretched) scene start.
            # Reuse the path already resolved above for the VO-FIT floor.
            "audio": beat_path,
            # Cue at_frame anchors to the absolute word start; rebase into the slid
            # scene by the same offset the scene moved (in_frame - span start frame).
            "_cues_raw": _resolve_cues(scene, words, fps),
            "_span_in": (round(start_s * fps) if start_s is not None else in_frame),
            # Content FLOORS for the duration-robustness grow/shrink passes: a scene
            # may be grown above these (a hold) or shrunk back to them, but NEVER below
            # — the VO is never cut, a media clip is never truncated. The VO floor is
            # max(word span, per-beat mp3 speech length) so the shrink pass can never
            # bring a scene below its own narration. Walkthrough roles are capped at
            # WALKTHROUGH_MAX_FRAMES, so their media floor must not exceed the cap
            # (else the shrink pass could never bring an over-long clip down).
            "_span_frames": max(span_frames, beat_audio_frames),
            "_media_frames": (min(media_frames, WALKTHROUGH_MAX_FRAMES)
                              if _derive_role(scene) in _WALKTHROUGH_ROLES
                              else media_frames),
        })
        cursor = out_frame
        scene_index += 1

    # Rebase cue frames onto the slid (contiguous) scene positions, then finalize.
    for s in out_scenes:
        offset = s["in_frame"] - s.pop("_span_in")
        cues = []
        for c in s.pop("_cues_raw"):
            at = c["at_frame"] + offset
            at = min(max(at, s["in_frame"]), s["out_frame"])  # clamp inside the scene
            cues.append({"label": c["label"], "word": c["word"], "at_frame": at})
        s["cues"] = cues

    # -----------------------------------------------------------------------
    # DURATION ROBUSTNESS — pull EITHER a sparse (Super) or dense (Ultra) plan
    # toward the target ~duration. The VO condense (style_fill) keeps the voice
    # near budget; this is the picture-side complement that fills/clamps the holds.
    # -----------------------------------------------------------------------
    if out_scenes:
        total_frames = out_scenes[-1]["out_frame"]
        if honor_plan_durations and target_duration_s and target_duration_s > 0:
            target_frames = round(float(target_duration_s) * fps)
            # Per-scene content FLOOR = max(VO span, media) — the length the scene must
            # hold so narration is never cut and a clip is never truncated. We may
            # GROW a scene above its floor (a hold) or SHRINK a hold back toward it,
            # but NEVER below the floor.
            floors = [max(s.get("_span_frames", 0), s.get("_media_frames", 0))
                      for s in out_scenes]

            if target_frames > total_frames:
                # SPARSE plan (Super, 23.6s on a 30s target): DISTRIBUTE the deficit
                # across scenes — each grows toward the per-scene budget — instead of
                # dumping it all on the last scene (which the 9s cap then blocked,
                # leaving the film short). Spreading the hold across every scene fills
                # the target more evenly and keeps any one card from staring.
                _grow_scenes_to_target(out_scenes, target_frames, fps)
            else:
                # DENSE plan (Ultra, 33.1s): if the laid-out film overruns the target
                # beyond tolerance, SHRINK the holds (scene length above its content
                # floor) proportionally back down toward the ceiling. Never cut a VO
                # span or a media clip (floors are hard). The VO condense already does
                # most of this upstream; this is the safety net for a plan that still
                # overruns (e.g. a brain that ignored the budget entirely).
                ceiling = round(target_frames * (1.0 + _OVER_TARGET_TOL))
                if total_frames > ceiling:
                    _shrink_holds_to_ceiling(out_scenes, floors, ceiling)
            total_frames = out_scenes[-1]["out_frame"]
    else:
        total_frames = max(audio_frames, 0)

    # Strip the internal floor markers from the emitted scenes (kept only for the
    # grow/shrink passes above).
    for s in out_scenes:
        s.pop("_span_frames", None)
        s.pop("_media_frames", None)

    return {
        "fps": fps,
        "total_frames": total_frames,
        # Full continuous VO track kept as a composition fallback; per-scene `audio`
        # blocks are authoritative for landing each beat on its (stretched) scene.
        "audio_path": full_audio_path,
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
    ap.add_argument("--brand-fallback", default="",
                    help="brand tagline/wordmark used as last-resort scene text")
    ap.add_argument("--target-duration-s", type=float, default=None,
                    help="plan job.target_duration_s; pads the last scene so the "
                         "timeline holds for the planned length (default: VO length)")
    ap.add_argument("--out", required=True, help="output timeline.json path")
    args = ap.parse_args(argv)

    raw_scenes = _load_json(args.scenes_file)
    scenes = raw_scenes["scenes"] if isinstance(raw_scenes, dict) else raw_scenes
    # If a full plan dict was passed, lift the target duration from job when not set.
    target = args.target_duration_s
    if target is None and isinstance(raw_scenes, dict):
        target = (raw_scenes.get("job") or {}).get("target_duration_s")
    alignment = _load_json(args.alignment)

    timeline = build_timeline(scenes, alignment, fps=args.fps,
                              brand_fallback=args.brand_fallback,
                              target_duration_s=target)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(timeline, fh, indent=2)
    print(f"wrote {args.out}: {timeline['total_frames']} frames, "
          f"{len(timeline['scenes'])} scenes @ {timeline['fps']}fps")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
