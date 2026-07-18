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


def _split_clip(clip: str, run_dir: str) -> list:
    """Split the tour recording at its midpoint into two segments (the film
    alternates kinetic beats with footage beats). Returns [seg1, seg2] paths
    (falls back to [clip] when too short to split)."""
    dur = _probe_duration(clip)
    if dur < 8.0:
        return [clip]
    mid = dur / 2.0
    segs = []
    for i, (ss, t) in enumerate(((0.0, mid), (mid, dur - mid))):
        seg = os.path.join(run_dir, f"tour-seg{i + 1}.mp4")
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{ss:.2f}",
             "-i", clip, "-t", f"{t:.2f}", "-c:v", "libx264", "-crf", "20",
             "-preset", "veryfast", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-movflags", "+faststart", seg],
            check=True, timeout=180)
        segs.append(seg)
    return segs


def _real_stat_from_text(text: str):
    """A REAL stat (value, label) from the site's own text, else None. Looks for
    price-per-period first, then a big count — deterministic, never invented."""
    import re
    m = re.search(r"([$€£]\d[\d,.]*)\s*/\s*(year|month|yr|mo)", text or "", re.I)
    if m:
        return (f"{m.group(1)}/{m.group(2).lower()}", "on the site today")
    m = re.search(r"(\d[\d,]*\+)\s+([a-z][a-z ]{6,40})", text or "")
    if m:
        return (m.group(1), m.group(2).strip())
    return None


def build_night_film(url: str, run_id: str, clip: str, logo_from: str = "") -> str:
    """v2 (Dennis 2026-07-18): the SaaS-style film — Engineered Night kinetic
    beats alternating with the agent's REAL smooth recording playing inside the
    Night browser panel. Copy is grounded by construction: only the brand's own
    headline/tagline and a stat regexed from the captured page text."""
    run_dir = os.path.join(HERE, "runs", run_id)
    os.makedirs(run_dir, exist_ok=True)
    pub = os.path.join(HERE, "studio", "public")

    theme_src = brand_extract.extract_brand(url, logo_from=logo_from or run_dir)
    pal = theme_src["palette"]
    name = theme_src.get("name") or url
    host = theme_src.get("host") or url
    tagline = (theme_src.get("tagline") or "").strip()

    theme = {
        "bg": "#000000", "bgCard": "#161616", "bgCardRaised": "#1D1D1D",
        "navy": "#0A0A0A", "navyBright": "#161616",
        "accent": pal["accent"], "ok": pal.get("success") or pal["accent"],
        "text": "#FFFFFF", "textMuted": "rgba(255,255,255,0.62)",
        "textDim": "rgba(255,255,255,0.38)", "border": "rgba(255,255,255,0.08)",
        "fontPrimary": "Inter, sans-serif",
        "fontMono": '"SF Mono", Menlo, monospace',
        "fontDisplay": "Manrope, sans-serif",
        "wordmark": name.upper(),
    }
    logo = theme_src.get("logo_src")
    if logo and os.path.exists(logo):
        rel = f"walkrec-logo-{run_id}{os.path.splitext(logo)[1] or '.png'}"
        shutil.copyfile(logo, os.path.join(pub, rel))
        theme["logoSrc"] = rel

    # Real corpus for the grounded stat: a prior run's read corpus when present.
    corpus = ""
    read_json = os.path.join(logo_from or run_dir, "conversion_read.json")
    if os.path.exists(read_json):
        try:
            corpus = json.load(open(read_json)).get("_ground_corpus", "") or ""
        except Exception:
            corpus = ""
    stat = _real_stat_from_text(corpus)

    segs = _split_clip(os.path.abspath(clip), run_dir)
    seg_rels = []
    for i, s in enumerate(segs):
        rel = f"walkrec-{run_id}-seg{i + 1}.mp4"
        shutil.copyfile(s, os.path.join(pub, rel))
        seg_rels.append((rel, _probe_duration(s)))

    t = 0
    scenes = []

    def add(scene_id, archetype, dur_s, data):
        nonlocal t
        dur_f = int(dur_s * FPS)
        scenes.append({"id": scene_id, "archetype": archetype,
                       "in_frame": t, "out_frame": t + dur_f, "cues": [], "data": data})
        t += dur_f

    hero_line = tagline or f"{name} — a live product tour"
    add("open", "night-hero", 4.5, {
        "eyebrow": "LAUNCH FILM",
        "lines": style_fill._night_accent_split(hero_line),
        "sub": f"Recorded live on {host} by the launch agent.",
        "ctaPrimary": "Watch the tour",
    })
    add("tour-1", "night-panel", min(seg_rels[0][1], 12.0), {
        "videoSrc": seg_rels[0][0], "caption": f"{host} — recorded live",
    })
    if stat:
        add("stat", "night-credibility", 4.5, {
            "stat": {"value": stat[0], "label": stat[1]},
        })
    else:
        add("statement", "night-ladder", 4.0, {
            "headline": hero_line, "chips": [], "activeIndex": 0,
        })
    if len(seg_rels) > 1:
        add("tour-2", "night-panel", min(seg_rels[1][1], 12.0), {
            "videoSrc": seg_rels[1][0], "caption": f"{host} — the pricing page",
        })
    add("close", "night-close", 5.0, {
        "tagline": f"See it live at {host}",
        "accentWord": host,
    })

    # Night music bed mapped so the climax lands on the close arrival.
    import night_music
    bed_rel = f"walkrec-bed-{run_id}.mp3"
    bed_out = os.path.join(pub, bed_rel)
    target_climax = scenes[-1]["in_frame"] / FPS + 1.0
    bed = night_music.build_bed(target_climax, t / FPS, bed_out)
    if bed:
        theme["music"] = bed_rel
        if bed.get("spb_s"):
            theme["musicMeta"] = {"spbFrames": bed["spb_s"] * FPS,
                                  "phaseFrames": bed.get("first_beat_s", 0.0) * FPS}

    props = {"fps": FPS, "total_frames": t, "audio_path": "", "lang": "en",
             "theme": theme, "scenes": scenes}
    props_path = os.path.join(run_dir, "walkrec-night-props.json")
    with open(props_path, "w") as f:
        json.dump(props, f, indent=2)

    out = os.path.join(run_dir, "film-night.mp4")
    subprocess.run(["npx", "remotion", "render", "NightTimeline", out,
                    f"--props={props_path}", "--log=error"],
                   cwd=os.path.join(HERE, "studio"), check=True, timeout=900)
    print(f"[walkrec] night film: {out} ({t / FPS:.1f}s, {len(seg_rels)} footage beats)")
    return out


def _site_bg_from_shot(shot_path: str) -> str:
    """The page's REAL background color: the most frequent LIGHT quantized pixel
    in the captured screenshot (ffmpeg rawvideo, stdlib parse — same discipline
    as brand_extract._accent_from_pixels). '' when unreadable."""
    if not shot_path or not os.path.exists(shot_path):
        return ""
    try:
        raw = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", shot_path, "-vf", "scale=48:48",
             "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
            capture_output=True, timeout=30).stdout
    except Exception:
        return ""
    from collections import Counter
    counts = Counter()
    buckets = {}
    for i in range(0, len(raw) - 2, 3):
        r, g, b = raw[i], raw[i + 1], raw[i + 2]
        lum = (r * 299 + g * 587 + b * 114) // 1000
        if lum < 150:
            continue  # background of a SaaS page is light
        q = (r // 16, g // 16, b // 16)
        counts[q] += 1
        buckets.setdefault(q, []).append((r, g, b))
    if not counts:
        return ""
    q, n = counts.most_common(1)[0]
    px = buckets[q]
    return "#%02X%02X%02X" % (sum(p[0] for p in px) // n,
                              sum(p[1] for p in px) // n,
                              sum(p[2] for p in px) // n)


def build_vevara_film(url: str, run_id: str, clip: str, logo_from: str = "") -> str:
    """v3 (Dennis 2026-07-18): the Vevara-grammar film ON THE BRAND'S OWN
    PALETTE — world bg sampled from the captured page, camera moments with the
    fitted swift-S curve, blur+slide+fade chords, footage in rounded cards."""
    run_dir = os.path.join(HERE, "runs", run_id)
    os.makedirs(run_dir, exist_ok=True)
    pub = os.path.join(HERE, "studio", "public")

    theme_src = brand_extract.extract_brand(url, logo_from=logo_from or run_dir)
    pal = theme_src["palette"]
    name = theme_src.get("name") or url
    host = theme_src.get("host") or url
    tagline = (theme_src.get("tagline") or "").strip()

    # THE SITE'S OWN BACKGROUND as the world (the v2 complaint): sample the
    # prior capture's homepage shot; honest white fallback.
    shot = ""
    manifest = brand_extract._find_capture_manifest(logo_from or run_dir)
    if manifest:
        shot = brand_extract._shot_path_from_manifest(manifest) or ""
    site_bg = _site_bg_from_shot(shot) or pal.get("bg") or "#FFFFFF"

    theme = {
        "bg": site_bg,
        "ink": pal.get("ink") or "#0F2338",
        "inkMuted": "#6B6257" if site_bg.lower() != "#ffffff" else "#5A6472",
        "accent": pal["accent"],
        "card": "#FFFFFF",
        "fontDisplay": "Manrope, sans-serif",
        "fontBody": "Inter, sans-serif",
        "wordmark": name,
    }
    logo = theme_src.get("logo_src")
    logo_rel = ""
    if logo and os.path.exists(logo):
        logo_rel = f"walkrec-logo-{run_id}{os.path.splitext(logo)[1] or '.png'}"
        shutil.copyfile(logo, os.path.join(pub, logo_rel))
        theme["logoSrc"] = logo_rel
    music_src = os.path.join(HERE, "assets", "music", "calm.mp3")
    if os.path.exists(music_src):
        rel = f"walkrec-music-{run_id}.mp3"
        shutil.copyfile(music_src, os.path.join(pub, rel))
        theme["music"] = rel

    # Grounded stat from a prior read corpus when available.
    corpus = ""
    read_json = os.path.join(logo_from or run_dir, "conversion_read.json")
    if os.path.exists(read_json):
        try:
            corpus = json.load(open(read_json)).get("_ground_corpus", "") or ""
        except Exception:
            corpus = ""
    if not corpus and shot:
        # fall back to the read-pass body text next to the shot
        pass
    stat = _real_stat_from_text(corpus)

    segs = _split_clip(os.path.abspath(clip), run_dir)
    seg_rels = []
    for i, s in enumerate(segs):
        rel = f"walkrec-{run_id}-vseg{i + 1}.mp4"
        shutil.copyfile(s, os.path.join(pub, rel))
        seg_rels.append((rel, _probe_duration(s)))

    FPSL = FPS
    hero_line = tagline or f"{name} — see it live"
    accent_word = max(hero_line.split(), key=len)

    # World layout (clusters far apart; text travels short, camera travels far).
    elements = []
    moments = [{"at": 0, "x": 960, "y": 540, "scale": 1.0}]
    t_f = 0

    def el(**kw):
        elements.append(kw)

    # Moment 0 — hero cluster at the origin.
    el(id="wm", kind="wordmark", x=960, y=330, at=4, text=name, dir="top")
    el(id="h1", kind="headline", x=960, y=520, w=1300, at=8, text=hero_line,
       accentWord=accent_word.strip(".,"), dir="bottom")
    el(id="sub", kind="sub", x=960, y=724, w=980, at=20,
       text=f"A live tour of {host}, recorded by the launch agent.", dir="bottom")
    t_f = int(4.6 * FPSL)

    # Moment 1 — footage card cluster (far right).
    v1_dur = min(seg_rels[0][1], 11.0)
    el(id="v1", kind="video", x=3120, y=760, w=1300, at=t_f + 18, videoSrc=seg_rels[0][0])
    moments.append({"at": t_f, "x": 3120, "y": 780, "scale": 1.0})
    t_f += int(v1_dur * FPSL)

    # Moment 2 — stat / statement cluster (lower left).
    if stat:
        el(id="st", kind="stat", x=1180, y=1900, at=t_f + 16,
           value=stat[0], label=stat[1], dir="bottom")
    else:
        el(id="st", kind="headline", x=1180, y=1900, w=1200, at=t_f + 16,
           text=hero_line, accentWord=accent_word.strip(".,"), dir="bottom")
    moments.append({"at": t_f, "x": 1180, "y": 1900, "scale": 1.08})
    t_f += int(3.2 * FPSL)

    # Moment 3 — footage 2 (far lower right), when a second segment exists.
    if len(seg_rels) > 1:
        v2_dur = min(seg_rels[1][1], 11.0)
        el(id="v2", kind="video", x=3420, y=2160, w=1300, at=t_f + 18,
           videoSrc=seg_rels[1][0])
        moments.append({"at": t_f, "x": 3420, "y": 2180, "scale": 1.0})
        t_f += int(v2_dur * FPSL)

    # Moment 4 — CTA cluster (center of the world's diagonal), long settle.
    el(id="cta", kind="cta", x=2200, y=1420, at=t_f + 16,
       text=f"See it live at {host}", value="Get started", logoSrc=logo_rel or None,
       dir="bottom")
    moments.append({"at": t_f, "x": 2200, "y": 1430, "scale": 0.96})
    t_f += int(4.6 * FPSL)

    props = {"fps": FPSL, "total_frames": t_f, "theme": theme,
             "elements": elements, "moments": moments}
    props_path = os.path.join(run_dir, "walkrec-vevara-props.json")
    with open(props_path, "w") as f:
        json.dump(props, f, indent=2)

    out = os.path.join(run_dir, "film-vevara.mp4")
    subprocess.run(["npx", "remotion", "render", "WalkrecWorld", out,
                    f"--props={props_path}", "--log=error"],
                   cwd=os.path.join(HERE, "studio"), check=True, timeout=900)
    print(f"[walkrec] vevara film: {out} ({t_f / FPSL:.1f}s, bg {site_bg}, "
          f"{len(seg_rels)} footage beats)")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--clip", required=True)
    ap.add_argument("--logo-from", default="")
    ap.add_argument("--night", action="store_true",
                    help="v2: Engineered Night kinetic beats around the footage")
    ap.add_argument("--vevara", action="store_true",
                    help="v3: Vevara world-moments grammar on the site's own palette")
    a = ap.parse_args()
    if a.vevara:
        build_vevara_film(a.url, a.run_id, a.clip, a.logo_from)
    elif a.night:
        build_night_film(a.url, a.run_id, a.clip, a.logo_from)
    else:
        build_film(a.url, a.run_id, a.clip, a.logo_from)


if __name__ == "__main__":
    main()
