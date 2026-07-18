#!/usr/bin/env python3
"""PROTOTYPE (local only — Dennis 2026-07-17/18): the walkthrough-RECORDING film.

An AI agent tours the site live (walk_native smart-nav records the session as a
CDP screencast -> mp4); this assembler cuts that REAL footage into the classic
Walk Studio composition: branded open -> walkthrough-player beats playing the
recording -> branded close. No voiceover (out of scope per Dennis) — the music
bed carries the film.

Usage:
  python3 proto_walkrec.py --url https://homefeed.me --run-id walkrec-homefeed \
      --clip runs/walkrec-homefeed/walk-tour.mp4 [--logo-from runs/v4c-night-homefeed]

Writes runs/<run-id>/film.mp4 (via `npx remotion render Timeline`).
Nothing here touches the hosted pipeline.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import brand_extract  # noqa: E402
import style_fill  # noqa: E402

FPS = 30


def _probe_duration(path: str) -> float:
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", path]).decode().strip()
    return float(out)


def build_film(url: str, run_id: str, clip: str, logo_from: str = "") -> str:
    run_dir = os.path.join(HERE, "runs", run_id)
    os.makedirs(run_dir, exist_ok=True)
    pub = os.path.join(HERE, "studio", "public")

    # Brand theme with the REAL pixel accent (logo_from threads a prior capture).
    theme_src = brand_extract.extract_brand(url, logo_from=logo_from or run_dir)
    pal = theme_src["palette"]
    name = theme_src.get("name") or url
    # The classic Timeline theme contract (mirrors style_fill's classic mapping).
    theme = {
        "bg": pal["bg"], "bgCard": pal["bg"], "bgCardRaised": "#F7F9FC",
        "navy": pal["accent2"], "navyBright": pal["accent2"],
        "accent": pal["accent"], "ok": pal.get("success") or pal["accent"],
        "text": pal["ink"], "textMuted": "#3D4A5C", "textDim": "#6B7589",
        "border": "#E5E9F0",
        "fontPrimary": theme_src["fonts"]["display"],
        "fontMono": theme_src["fonts"]["mono"],
        "fontDisplay": theme_src["fonts"]["display"],
        "wordmark": name,
    }
    # Stage the real captured logo when available.
    logo = theme_src.get("logo_src")
    if logo and os.path.exists(logo):
        ext = os.path.splitext(logo)[1] or ".png"
        rel = f"walkrec-logo-{run_id}{ext}"
        shutil.copyfile(logo, os.path.join(pub, rel))
        theme["logoSrc"] = rel
    # Music bed (calm default), VO-free film.
    music_src = os.path.join(HERE, "assets", "music", "calm.mp3")
    if os.path.exists(music_src):
        rel = f"walkrec-music-{run_id}.mp3"
        shutil.copyfile(music_src, os.path.join(pub, rel))
        theme["music"] = rel

    # Stage the agent's recording.
    clip_abs = os.path.abspath(clip)
    clip_dur = _probe_duration(clip_abs)
    clip_rel = f"walkrec-clip-{run_id}.mp4"
    shutil.copyfile(clip_abs, os.path.join(pub, clip_rel))

    # Cut structure: open (3.5s) -> the real tour footage -> close (4s).
    open_f = int(3.5 * FPS)
    walk_f = int(min(clip_dur, 30.0) * FPS)
    close_f = int(4.0 * FPS)
    t = 0
    scenes = []

    def add(scene_id, archetype, dur_f, data):
        nonlocal t
        scenes.append({
            "id": scene_id, "archetype": archetype,
            "in_frame": t, "out_frame": t + dur_f, "cues": [], "data": data,
        })
        t += dur_f

    tagline = (theme_src.get("tagline") or "").strip()
    add("open", "hero-title", open_f, {
        "title": name,
        "subtitle": tagline or "A live tour, recorded by the launch agent.",
        "kicker": "LAUNCH FILM",
    })
    add("tour", "walkthrough-player", walk_f, {
        "videoSrc": clip_rel,
        "overlayTitle": f"{name} — live product tour",
        "muteClip": True,
    })
    add("close", "hero-title", close_f, {
        "title": name,
        "subtitle": f"See it live — {theme_src.get('host') or url}",
        "kicker": "GET STARTED",
    })

    props = {
        "fps": FPS, "total_frames": t, "audio_path": "", "lang": "en",
        "theme": theme, "scenes": scenes,
    }
    props_path = os.path.join(run_dir, "walkrec-props.json")
    with open(props_path, "w") as f:
        json.dump(props, f, indent=2)

    out = os.path.join(run_dir, "film.mp4")
    cmd = ["npx", "remotion", "render", "Timeline", out,
           f"--props={props_path}", "--log=error"]
    print("[walkrec] rendering:", " ".join(cmd), file=sys.stderr)
    subprocess.run(cmd, cwd=os.path.join(HERE, "studio"), check=True, timeout=900)
    print(f"[walkrec] film: {out} ({t / FPS:.1f}s, clip {clip_dur:.1f}s)")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--clip", required=True)
    ap.add_argument("--logo-from", default="")
    a = ap.parse_args()
    build_film(a.url, a.run_id, a.clip, a.logo_from)


if __name__ == "__main__":
    main()
