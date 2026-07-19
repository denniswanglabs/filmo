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
from run_events import emit  # noqa: E402

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
            continue  # light pass first — most SaaS pages
        q = (r // 16, g // 16, b // 16)
        counts[q] += 1
        buckets.setdefault(q, []).append((r, g, b))
    if not counts or counts.most_common(1)[0][1] < 96:
        # DARK site (InsForge-class): most frequent dark pixel instead.
        counts.clear(); buckets.clear()
        for i in range(0, len(raw) - 2, 3):
            r, g, b = raw[i], raw[i + 1], raw[i + 2]
            lum = (r * 299 + g * 587 + b * 114) // 1000
            if lum > 90:
                continue
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


def _extract_json_list(raw: str):
    r"""First decodable JSON list-of-dicts anywhere in `raw`. Survives markdown
    fences, prose around the array, and bracketed text BEFORE it — the greedy
    `\[.*\]` regex this replaces grabbed first-[ to last-] and died on
    'Extra data' whenever the reply contained any other bracket."""
    import re as _re
    raw = (raw or "").strip()
    if raw.startswith("```"):
        raw = _re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", raw, flags=_re.S)
    dec = json.JSONDecoder()
    for i, ch in enumerate(raw):
        if ch != "[":
            continue
        try:
            val, _end = dec.raw_decode(raw[i:])
        except Exception:
            continue
        if isinstance(val, list) and val and all(isinstance(x, dict) for x in val):
            return val
    return None


def _harvest_details(corpus: str, target: str, title: str, want: int = 4):
    """Short REAL fragments from around the target section — verbatim by
    construction (substrings of the corpus), used when the brain's details
    fail the verbatim gate. No model in the loop."""
    pos = corpus.lower().find((target or title or "").lower())
    window = corpus[max(0, pos - 300):pos + 1200] if pos >= 0 else corpus[:1500]
    window = window[window.find("\n") + 1:max(0, window.rfind("\n"))]
    _CTA = ("start", "read", "learn", "contact", "get ", "view", "try",
            "book", "see ", "join", "explore", "create your", "log in",
            "sign ")
    out = []
    for line in window.split("\n"):
        frag = line.strip()
        if not (8 <= len(frag) <= 45) or not (2 <= len(frag.split()) <= 6):
            continue
        if not frag[0].isalnum() or frag.lower().startswith(_CTA):
            continue
        if title and frag.lower() in title.lower():
            continue
        if any(frag.lower() == o.lower() or frag.lower() in o.lower() for o in out):
            continue
        out.append(frag)
        if len(out) >= want:
            break
    return out


def _norm_ws(s: str) -> str:
    """Whitespace-collapsed lowercase — a heading that wraps across two lines
    on the page is still VERBATIM (both Nemotron and Sonnet lost a real title
    to a line break under exact matching, 2026-07-18)."""
    import re as _re
    return _re.sub(r"\s+", " ", s or "").strip().lower()


def _harvest_chips(corpus: str, target: str, title: str, want: int = 10):
    """SHORT real labels near the target (service/feature names) — the Night
    chip-sweep's material, mined verbatim. 1-3 words, tight length caps."""
    pos = corpus.lower().find((target or title or "").lower())
    window = corpus[max(0, pos - 200):pos + 2200] if pos >= 0 else corpus[:2400]
    window = window[window.find("\n") + 1:max(0, window.rfind("\n"))]
    import re as _re
    NAV = {"products", "product", "blog", "blogs", "docs", "documentation",
           "careers", "roadmap", "pricing", "templates", "integrations",
           "home", "about", "customers", "changelog", "community", "legal",
           "terms", "privacy", "login", "log in", "sign in", "sign up",
           "demo", "features", "download", "how it works", "faq", "support",
           "and more", "common questions"}
    CTA_START = ("start", "read", "learn", "contact", "get ", "view", "try",
                 "book", "see ", "join", "request", "explore", "works ",
                 "create ", "how ", "tell ", "download", "install", "replay")
    out = []
    for line in window.split("\n"):
        frag = line.strip().strip("·•|-–")
        if not (5 <= len(frag) <= 24) or not (1 <= len(frag.split()) <= 3):
            continue
        if not frag[0].isalnum() or not all(ord(ch) < 128 for ch in frag):
            continue  # symbol-bearing fragments are UI controls, not labels
        lc = frag.lower()
        if lc in NAV or lc.startswith(CTA_START):
            continue
        if _re.fullmatch(r"[\d:.,%$€£+/kKmM ]+", frag):
            continue  # bare times/numbers are not feature labels
        if title and lc in title.lower():
            continue
        if any(lc == o.lower() for o in out):
            continue
        out.append(frag)
        if len(out) >= want:
            break
    return out


def _verbatim_entities(cand: dict, corpus_lc: str):
    """Third-party names the site itself mentions — verbatim-gated; logos are
    then resolved by name via entity_logos (the agent chooses, code fetches)."""
    out = []
    for e in (cand.get("entities") or []):
        e = str(e).strip().strip('"')
        if (e and 2 <= len(e) <= 24 and len(e.split()) <= 3
                and _norm_ws(e) in corpus_lc and e not in out):
            out.append(e)
    return out[:8]


# Tight markers only: nav words like "Integrations" window the site's OWN
# services grid and produce first-party names as "partners" (v13 finding).
_ENTITY_MARKERS = ("works perfectly with", "works with", "compatible with",
                   "integrated with")

_LOGO_ALT_JS = """
() => {
  const clean = (s) => (s || "").trim().replace(/[-_]/g, " ")
    .replace(/\\.(svg|png|webp|jpg|jpeg)$/i, "").replace(/\\s+logo$/i, "").trim();
  const all = Array.from(document.querySelectorAll("section,div"));
  let host = null;
  for (const el of all) {
    const t = (el.textContent || "").trim().toLowerCase();
    if ((t.startsWith("works perfectly with") || t.startsWith("works with") ||
         t.startsWith("integrated with")) &&
        el.querySelectorAll("img,svg").length >= 3 &&
        (el.textContent || "").length < 400) { host = el; }
  }
  if (!host) return [];
  const out = [];
  for (const img of host.querySelectorAll("img")) {
    let n = clean(img.alt || img.getAttribute("aria-label") || img.title);
    if (!n) {
      const src = img.getAttribute("src") || "";
      n = clean(src.split("/").pop().split("?")[0]);
    }
    if (n && n.length <= 24 && !out.some((o) => o.toLowerCase() === n.toLowerCase()))
      out.push(n);
  }
  return out.slice(0, 14);
}
"""


_TESTIMONIAL_MARKERS = ("from founders", "testimonial", "what people say",
                        "loved by", "customers say", "wall of love")

_QUOTES_JS = """
() => {
  let host = null;
  for (const el of document.querySelectorAll("*")) {
    const t = (el.textContent || "").trim().toLowerCase();
    if ((t.includes("testimonial") || t.includes("from founders") ||
         t.includes("wall of love") || t.includes("what people say")) &&
        (!host || t.length < (host.textContent || "").length))
      host = el;
  }
  if (!host) return [];
  let sec = host;
  for (let i = 0; i < 6 && sec.parentElement; i++) {
    sec = sec.parentElement;
    if ((sec.innerText || "").length > 300) break;
  }
  const lines = (sec.innerText || "").split("\\n").map(s => s.trim()).filter(Boolean);
  const attrRe = /@|^(founder|co-founder|ceo|cto|head of|director)\\b/i;
  const out = [];
  for (let i = 0; i < lines.length; i++) {
    const l = lines[i];
    const isQ = /^[\\u201C\\u201D"']/.test(l) || (l.length >= 40 && !attrRe.test(l));
    if (!isQ || l.length < 25 || l.length > 300) continue;
    let name = "", attr = "";
    for (let j = i + 1; j <= i + 2 && j < lines.length; j++) {
      if (attrRe.test(lines[j])) attr = lines[j];
      else if (!name && lines[j].length <= 40 && /^[A-Z]/.test(lines[j])) name = lines[j];
    }
    if (attr) out.push({ q: l.replace(/^[\\u201C\\u201D"']+|[\\u201C\\u201D"']+$/g, ""), name, a: attr });
    if (out.length >= 3) break;
  }
  return out;
}
"""


def _harvest_quotes(url: str):
    """REAL testimonial quotes from the marker page's live DOM (the sections
    are lazy-loaded and quote sentences exceed label-length caps, so neither
    static corpus nor the detail harvester can see them). Never raises."""
    try:
        import walk_native as wn
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = wn._launch_browser(p)
            ctx = browser.new_context(viewport=wn.VIEWPORT,
                                      user_agent=wn._DESKTOP_UA,
                                      extra_http_headers=wn._EXTRA_HEADERS)
            ctx.add_init_script(wn._STEALTH_INIT_JS)
            page = ctx.new_page()
            page.goto(wn._norm_url(url), wait_until="domcontentloaded",
                      timeout=45000)
            wn._wait_for_spa_hydration(page)
            page.evaluate("""async () => {
              const h = document.body.scrollHeight;
              for (let y = 0; y <= h; y += 600) {
                window.scrollTo(0, y);
                await new Promise(r => setTimeout(r, 120));
              }
            }""")
            page.wait_for_timeout(1000)
            quotes = page.evaluate(_QUOTES_JS) or []
            browser.close()
        return [q for q in quotes if q.get("q") and q.get("a")][:3]
    except Exception:
        return []


def _harvest_logo_alt_names(url: str):
    """Partner names from the works-with section's OWN logo images (alt text
    or filename) — the tools are usually rendered as images with no text
    nodes, so the text harvest can't see them. Dedupes hover variants
    ('cursor color' -> covered by 'Cursor'). Best-effort, never raises."""
    try:
        import walk_native as wn
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = wn._launch_browser(p)
            ctx = browser.new_context(viewport=wn.VIEWPORT,
                                      user_agent=wn._DESKTOP_UA,
                                      extra_http_headers=wn._EXTRA_HEADERS)
            ctx.add_init_script(wn._STEALTH_INIT_JS)
            page = ctx.new_page()
            page.goto(wn._norm_url(url), wait_until="domcontentloaded",
                      timeout=45000)
            wn._wait_for_spa_hydration(page)
            page.wait_for_timeout(1200)
            raw = page.evaluate(_LOGO_ALT_JS) or []
            browser.close()
        out = []
        for n in raw:
            nl = n.lower()
            if nl.endswith((" color", " dark", " light", " white", " black")):
                continue  # hover/theme image variants of another mark
            if any(nl.startswith(o.lower() + " ") or nl == o.lower()
                   or o.lower().endswith(" " + nl) for o in out):
                continue
            out.append(n)
        return out[:8]
    except Exception:
        return []


def _harvest_entities(corpus: str, want: int = 8):
    """Fallback: short capitalized labels right after a works-with marker."""
    lc = corpus.lower()
    for marker in _ENTITY_MARKERS:
        pos = lc.find(marker)
        if pos < 0:
            continue
        window = corpus[pos + len(marker):pos + 700]
        window = window[window.find("\n") + 1:max(0, window.rfind("\n"))]
        _CTA = ("learn", "see ", "read", "and more", "view", "get ", "try",
                "start", "download", "contact", "more")
        out = []
        for line in window.split("\n"):
            frag = line.strip().strip("·•|,")
            if not (2 <= len(frag) <= 24) or not (1 <= len(frag.split()) <= 3):
                continue
            if not frag[0].isalnum() or not any(c.isupper() for c in frag):
                continue
            if frag.lower().startswith(_CTA):
                continue
            if any(frag.lower() == o.lower() for o in out):
                continue
            out.append(frag)
            if len(out) >= want:
                break
        if len(out) >= 3:
            return out
    return []


def _verbatim_details(cand: dict, corpus_lc: str):
    """Keep only supporting details that exist VERBATIM on the site — the
    vignettes render real information, never model-written text (Dennis
    2026-07-18: "provide actual information... find it in the website")."""
    out = []
    for d in (cand.get("details") or []):
        d = str(d).strip().strip('"')
        if d and len(d) <= 48 and _norm_ws(d) in corpus_lc and d not in out:
            out.append(d)
    return out[:4]


def plan_tour(url: str, run_dir: str, brain: str = "sonnet5", max_stops: int = 3):
    """v4 'check the website first': read the site, then have the brain pick the
    3 things a visitor actually cares about. Every stop is {title, page, target}
    where BOTH title and target must be VERBATIM text from the site (enforced in
    code) — the brain chooses, it never writes. Deterministic fallback: hero +
    pricing + first feature page."""
    import re as _re
    import read_pass
    import site_read

    rp = read_pass.read_pass(url, run_dir)
    home_text = rp.get("body_text", "") or ""
    emit(run_dir, "read.page", f"Read {url}",
         f"{len(home_text)} chars of copy",
         artifact=rp.get("hero_screenshot_path") or "")
    _logo_png = os.path.join(run_dir, "screenshots-read", "brand", "logo.png")
    if os.path.exists(_logo_png):
        emit(run_dir, "brand.logo", "Brand mark captured", "",
             artifact=_logo_png)
    ledger = site_read.browse_site(url, run_dir, brain=None,
                                   homepage_text=home_text)
    for p in (ledger.get("pages") or []):
        shot = os.path.join(run_dir, "site-read", p["slug"], "shot-01.png")
        emit(run_dir, "read.page", f"Read /{p['slug']}",
             f"{len(p.get('body_text') or '')} chars of copy",
             artifact=shot if os.path.exists(shot) else "")
    pages = {"home": home_text}
    page_urls = {"home": url}
    for p in (ledger.get("pages") or []):
        pages[p["slug"]] = p.get("body_text", "") or ""
        page_urls[p["slug"]] = p.get("url") or url
    corpus_lc = _norm_ws(" ".join(pages.values()))

    stops = None
    try:
        import validate_planner as vp
        menu = "\n\n".join(f"[PAGE {slug}]\n{text[:4000]}" for slug, text in pages.items())
        msgs = [
            {"role": "system", "content": (
                "You are planning the SHOT LIST for a product launch video. From "
                "the site text below, pick up to %d moments a potential customer "
                "most cares about (the core promise, the standout capability, "
                "pricing/social proof), ordered most important first. Return "
                "STRICT JSON: an array of objects "
                '{"title": a short VERBATIM HEADING copied exactly from the '
                "text — a real heading, UNDER 60 characters and at most 8 words, "
                'NEVER a full sentence or paragraph, "page": the [PAGE ...] slug '
                'it appears on, "target": the exact on-page heading text to '
                'scroll to (usually the same as title), "details": up to 4 SHORT '
                "verbatim strings copied exactly from the site text that support "
                "this moment (property names, feature labels, form fields, plan "
                "names — each 2-6 words, under 45 chars), "
                '"entities": names of '
                "third-party tools, products, or companies the page says it "
                "works with or integrates (copied exactly, 1-3 words each, up "
                "to 8; [] if none)}. Copy text EXACTLY — do not write your own "
                "words. No prose outside the JSON."
                % (max_stops + 2))},
            {"role": "user", "content": menu},
        ]
        raw = vp.call_model(msgs, brain=brain) or ""
        cand = _extract_json_list(raw)
        if cand is None:
            with open(os.path.join(run_dir, "tour-plan-raw.txt"), "w") as f:
                f.write(raw)
            print("[tour] unparseable plan reply (saved raw); retrying once",
                  file=sys.stderr)
            raw = vp.call_model(msgs, brain=brain) or ""
            cand = _extract_json_list(raw)
        if cand:
            # Prefer sentence-case value lines over ALL-CAPS UI labels
            # ("Your real estate website, ready in minutes." beats "FEATURED
            # PROPERTY") — stable sort keeps the brain's importance order
            # within each class.
            cand = sorted(cand, key=lambda c: str(c.get("title") or "").isupper())
            stops = []
            for c in cand[:max_stops * 2]:
                if len(stops) >= max_stops:
                    break
                title = str(c.get("title") or "").strip()
                slug = str(c.get("page") or "home").strip()
                target = str(c.get("target") or title).strip()
                # HARD grounding: verbatim on the site, AND heading-shaped —
                # short. A 150-char paragraph is not a section title.
                if not title or _norm_ws(title) not in corpus_lc:
                    continue
                if len(title) > 60 or len(title.split()) > 8:
                    continue
                if slug not in page_urls:
                    slug = "home"
                # DIVERSITY: after the first stop, skip targets living in the
                # hero region of a page another stop already films (two shots
                # of the same fold made v4's footage repeat).
                page_text_lc = pages.get(
                    next((k for k, u in page_urls.items() if u == page_urls[slug]), "home"),
                    "").lower()
                hero_lc = page_text_lc[:500]
                same_page_used = any(s["page"] == page_urls[slug] for s in stops)
                if stops and same_page_used and target.lower() in hero_lc:
                    continue
                if any(s["title"].lower() == title.lower() for s in stops):
                    continue
                stops.append({"title": title, "page": page_urls[slug],
                              "target": target,
                              "details": _verbatim_details(c, corpus_lc),
                              "entities": _verbatim_entities(c, corpus_lc)})
            if len(stops) < max_stops:
                # Top-up pass: relax only the hero-region diversity rule (the
                # strictest filter) — on dense one-pagers it can kill every
                # candidate and leave a one-stop film.
                for c in cand[:max_stops * 2]:
                    if len(stops) >= max_stops:
                        break
                    title = str(c.get("title") or "").strip()
                    slug = str(c.get("page") or "home").strip()
                    target = str(c.get("target") or title).strip()
                    if not title or _norm_ws(title) not in corpus_lc:
                        continue
                    if len(title) > 60 or len(title.split()) > 8:
                        continue
                    if slug not in page_urls:
                        slug = "home"
                    if any(s["title"].lower() == title.lower() for s in stops):
                        continue
                    stops.append({"title": title, "page": page_urls[slug],
                                  "target": target,
                                  "details": _verbatim_details(c, corpus_lc),
                                  "entities": _verbatim_entities(c, corpus_lc)})
            stops = stops or None
    except (Exception, SystemExit) as e:
        print(f"[tour] brain plan failed ({e}); deterministic fallback",
              file=sys.stderr)
        stops = None

    if not stops:
        stops = [{"title": (rp.get("headline") or "The product").split("—")[0].strip()[:60],
                  "page": url, "target": ""}]
        for slug in ("pricing", "how-it-works", "features", "customers"):
            if slug in page_urls and len(stops) < max_stops:
                stops.append({"title": slug.replace("-", " ").title(),
                              "page": page_urls[slug],
                              "target": slug.split("-")[0].title()})
    corpus_nl = "\n".join(pages.values())
    # The hero recording deserves the hero's own words: promote the stop whose
    # title lives in the top of the homepage (a pricing title over hero footage
    # reads as WRONG information).
    hero_head = _norm_ws(home_text)[:700]

    def _heroish(t):
        return len(t.split()) >= 3 and _norm_ws(t) in hero_head

    promoted = _heroish(stops[0]["title"])
    for idx, s in enumerate(stops):
        if idx and _heroish(s["title"]):
            stops.insert(0, stops.pop(idx))
            promoted = True
            break
    if not promoted:
        # No planned stop carries the hero's words — the hero RECORDING must
        # not wear an unrelated title (a "Pricing" headline over hero footage
        # is wrong information). Front a synthetic stop with the page's own
        # headline, verbatim.
        _CTAISH = ("start", "read", "learn", "contact", "get ", "view", "try",
                   "log in", "sign ", "create ")
        for line in home_text.split("\n"):
            frag = line.strip()
            if (12 <= len(frag) <= 60 and 3 <= len(frag.split()) <= 9
                    and frag[0].isalnum()
                    and not frag.lower().startswith(_CTAISH)):
                stops.insert(0, {"title": frag, "page": url, "target": "",
                                 "details": [], "entities": []})
                stops[:] = stops[:max_stops + 1]
                break
    for s in stops:
        s["chips"] = _harvest_chips(corpus_nl, s.get("target", ""), s["title"])
        # Entities are STOP-LOCAL (model-provided, verbatim-gated); the
        # marker harvest belongs exclusively to the ecosystem auto-stop —
        # smearing it across stops made arbitrary beats wall-eligible.
        s["entities"] = [e for e in (s.get("entities") or [])
                         if e.lower() not in {c.lower() for c in (s.get("chips") or [])}]
    # Ecosystem beat assembles ITSELF: when the site names >=4 partner tools
    # and no planned stop covers them, add the works-with section as a stop
    # (title = the site's own marker line) so the logo wall always appears
    # when the site earns it.
    ents = []
    if any(m in corpus_nl.lower() for m in _ENTITY_MARKERS):
        ents = _harvest_logo_alt_names(url)
    if len(ents) < 4:
        ents = _harvest_entities(corpus_nl)
    covered = any(any(k in s["title"].lower() for k in
                      ("works with", "works perfectly", "integrat"))
                  for s in stops[1:])
    if len(ents) >= 4 and not covered:
        marker_line = next(
            (ln.strip() for ln in corpus_nl.split("\n")
             if 8 <= len(ln.strip()) <= 60
             and any(m in ln.lower() for m in _ENTITY_MARKERS)),
            "")
        if marker_line:
            stops.append({"title": marker_line, "page": url,
                          "target": marker_line, "details": [],
                          "entities": ents, "chips": []})
            # CONTENT-ONCE: the wall owns these names — no other beat may
            # present them (the chip sweep was duplicating the model list).
            reserved = {e.lower() for e in ents}
            for s in stops[:-1]:
                s["chips"] = [c for c in (s.get("chips") or [])
                              if c.lower() not in reserved]
                s["details"] = [d for d in (s.get("details") or [])
                                if d.lower() not in reserved]
        if len(s.get("details") or []) < 2:
            have = s.get("details") or []
            mined = _harvest_details(corpus_nl, s.get("target", ""), s["title"])
            s["details"] = (have + [m for m in mined if m not in have])[:4]
    marker_slug = next((slug for slug, text in pages.items()
                        if any(m in text.lower() for m in _TESTIMONIAL_MARKERS)),
                       "")
    if marker_slug:
        for s in stops:
            hay = (s["title"] + " " + " ".join(s.get("details") or [])).lower()
            if any(m in hay for m in _TESTIMONIAL_MARKERS) or \
                    any("@" in d for d in (s.get("details") or [])):
                s["quotes"] = _harvest_quotes(page_urls.get(marker_slug, url))
                emit(run_dir, "read.quotes",
                     f"Harvested {len(s['quotes'])} real quotes from /{marker_slug}",
                     (s["quotes"][0]["q"][:90] + "…") if s.get("quotes") else "")
                break
    emit(run_dir, "decide.plan",
         f"Planned {len(stops)} moments a customer cares about",
         "\n".join(f"{i + 1}. {s['title']}" for i, s in enumerate(stops)))
    return stops


def _smooth60(seg_in: str, seg_out: str) -> str:
    """Motion-interpolate a shot to 60fps (kills residual capture stutter).
    Falls back to the original on any failure."""
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", seg_in,
             "-vf", "minterpolate=fps=60:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1",
             "-c:v", "libx264", "-crf", "19", "-preset", "fast",
             "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart",
             seg_out],
            check=True, timeout=600)
        return seg_out if os.path.exists(seg_out) else seg_in
    except Exception:
        return seg_in


def _clip_fp(mp4: str, n: int = 3):
    """n tiny grayscale frames spread across the clip (16x16 rawvideo)."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", mp4], capture_output=True, text=True, timeout=30)
        dur = float(out.stdout.strip() or 9)
    except Exception:
        dur = 9.0
    frames = []
    for i in range(n):
        t = dur * (i + 1) / (n + 1)
        try:
            r = subprocess.run(
                ["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", mp4,
                 "-frames:v", "1", "-vf", "scale=16:16,format=gray",
                 "-f", "rawvideo", "-"], capture_output=True, timeout=60)
            if len(r.stdout) == 256:
                frames.append(r.stdout)
        except Exception:
            pass
    return frames


def _clips_similar(fa, fb, thresh: float = 5.0) -> bool:
    """True when two clips share a near-identical frame (SPA-mirror guard).
    Calibrated 2026-07-18 on BOTH worlds: homefeed (light) distinct folds
    13.9+, mirrors ~0; insforge (dark) distinct sections 7.0+, lookalikes
    0-2.8. Threshold 5 separates cleanly on both."""
    for a in fa:
        for b in fb:
            if sum(abs(x - y) for x, y in zip(a, b)) / 256.0 < thresh:
                return True
    return False


# Concept vignettes first (they ENACT the title — Dennis 2026-07-18: "there
# should be infographics or animations of [the title], maybe like a table");
# plain line-art motifs remain the fallback tier for unmatched titles.
_MOTIF_KEYWORDS = [
    ("request-table", ("request", "inquir", "booking", "viewing", "schedul",
                       "appointment", "preferred time")),
    ("chat-exchange", ("chat", "message", "whatsapp", "tell ", "ask ",
                       "contact", "talk", "conversation")),
    ("context-cards", ("present", "context", "home", "house", "propert",
                       "listing", "estate", "apartment", "showcase")),
    ("logo-wall", _ENTITY_MARKERS + ("integrations", "supported tools")),
    ("quote-card", ("testimonial", "loved by", "what people say", "founders say",
                    "customers say", "from founders")),
    ("price-card", ("price", "pricing", "plan", "pay", "subscription", "cost", "free ", "offer")),
    ("chip-sweep", ("everything", "features", "services", "platform",
                    "need for", "built for", "all-in-one", "toolkit")),
    ("stat-pop", ("stars", "developers", "teams", "companies", "downloads",
                  "backed by", "customers", "users")),
    ("globe", ("language", "languages", "global", "world", "international", "translat")),
    ("card", ("link", "profile", "page", "website", "site", "portfolio")),
    ("house", ("real ", "rent")),
]

_VIGNETTES = {"request-table", "context-cards", "chat-exchange", "price-card",
              "check-list", "chip-sweep", "stat-pop", "kinetic-line",
              "logo-wall", "quote-card", "people-wall"}


_STAT_RE = __import__("re").compile(
    r"(?<![\w-])(?:[$€£]\d[\d,.]*|\d[\d,.]*\s*(?:k|K|M|%|\+)|\d{2,}(?:[,.]\d+)?)(?![\w-])")


def _is_stat_line(line: str) -> bool:
    """A REAL statistic: currency, magnitude suffix, or a standalone number.
    Digits glued to letters (YC W26, Kling V3) are codes, not stats — a
    testimonial cohort tag must never become a count-up (Palmier finding)."""
    return bool(_STAT_RE.search(line or ""))


def _refine_motif(motif: str, s: dict, used) -> str:
    """Content beats keywords: a chip-sweep needs >=6 real chips; a stat-pop
    needs a number; anything data-rich beats line art; a punchy title beats a
    bare drawing (kinetic word-by-word)."""
    import re as _re
    details = s.get("details") or []
    chips = s.get("chips") or []
    if motif == "logo-wall" and len(s.get("entities") or []) < 4:
        motif = "chip-sweep" if len(chips) >= 6 else "check-list"
    if motif == "chip-sweep" and len(chips) < 6:
        motif = "check-list" if len(details) >= 2 else "kinetic-line"
    if motif == "stat-pop" and not any(_is_stat_line(d) for d in details):
        motif = "check-list" if len(details) >= 2 else "kinetic-line"
    if motif == "quote-card" and not s.get("quotes"):
        motif = ("people-wall"
                 if sum(1 for d in details if _re.search(r"@", d)) >= 2
                 else ("check-list" if len(details) >= 2 else "card"))
    if motif == "people-wall" and not (
            s.get("quotes")
            or sum(1 for d in details if _re.search(r"@", d)) >= 2):
        motif = "check-list" if len(details) >= 2 else "card"
    # MINIMUM-MATERIAL contract: a beat must carry real content. kinetic-line
    # needs a >=3-word line AND must never swallow a stop that has details
    # (the 'Testimonials' one-word empty scene, Palmier 2026-07-18).
    if motif == "kinetic-line":
        words = len((s.get("title") or "").split())
        if s.get("quotes"):
            motif = "quote-card"
        elif details:
            motif = ("people-wall" if sum(
                1 for d in details if _re.search(r"@", d)) >= 2
                else "check-list")
        elif words < 3:
            motif = "card"  # line-art fallback; better a drawing than a word
    if motif not in _VIGNETTES:  # line-art tier
        if len(s.get("entities") or []) >= 4 and "logo-wall" not in used:
            return "logo-wall"
        if any(_is_stat_line(d) for d in details) and "stat-pop" not in used:
            return "stat-pop"
        if s.get("quotes") and "quote-card" not in used:
            return "quote-card"
        if (sum(1 for d in details if _re.search(r"@", d)) >= 2
                and "people-wall" not in used):
            return "people-wall"
        if len(details) >= 2:
            return "check-list"  # may repeat: real info beats line art
        if (not details and 3 <= len((s.get("title") or "").split()) <= 8
                and "kinetic-line" not in used):
            return "kinetic-line"
    return motif


def _pick_motif(text: str, used) -> str:
    """Domain-themed motif for a motion-graphic beat, keyword-scored from the
    stop's own words; never repeats within a film."""
    lc = (text or "").lower()
    for motif, kws in _MOTIF_KEYWORDS:
        if motif not in used and any(k in lc for k in kws):
            return motif
    # No keyword match: rotate LINE-ART only — a domain vignette (request
    # table, chat) makes no sense for an unmatched title; _refine_motif
    # upgrades from here based on the stop's actual content.
    for motif, _ in _MOTIF_KEYWORDS:
        if motif not in _VIGNETTES and motif not in used:
            return motif
    return "card"


# AI coding-agent tools live under domains the generic heuristic can't guess.
_AGENT_TOOL_DOMAINS = {
    "claude code": "claude.com", "claude": "claude.com",
    "codex": "openai.com", "openai codex": "openai.com",
    "cursor": "cursor.com", "windsurf": "windsurf.com",
    "google antigravity": "google.com", "antigravity": "google.com",
    "gemini cli": "google.com", "github copilot": "github.com",
    "copilot": "github.com", "devin": "devin.ai", "cline": "cline.bot",
    "aider": "aider.chat", "v0": "v0.dev", "bolt": "bolt.new",
    "lovable": "lovable.dev", "replit": "replit.com", "whatsapp": "whatsapp.com",
    "xai": "x.ai", "kling ai": "klingai.com", "kling": "klingai.com",
    "bytedance": "bytedance.com", "google": "google.com", "veo": "google.com",
    "grok": "x.ai", "grok imagine": "x.ai", "premiere": "adobe.com",
    "adobe premiere": "adobe.com", "davinci": "blackmagicdesign.com",
    "davinci resolve": "blackmagicdesign.com",
}


def _logo_uri(name: str) -> str:
    """Real favicon as a data URI — resolved ONLY via explicit maps (a
    guessed domain can fetch a WRONG mark, which is fabrication; unmapped
    names render an honest initial badge). Version suffixes strip before
    lookup ('Kling V3' -> 'kling'). Never raises."""
    try:
        import re as _re
        import entity_logos as _el
        key = name.strip().lower()
        base = _re.sub(r"\s+v?\d[\d.]*$", "", key).strip()
        domain = (_AGENT_TOOL_DOMAINS.get(key)
                  or _AGENT_TOOL_DOMAINS.get(base)
                  or _el.KNOWN_OVERRIDES.get(key)
                  or _el.KNOWN_OVERRIDES.get(base))
        got = _el._fetch_logo(domain) if domain else None
        return _el._data_uri(*got) if got else ""
    except Exception:
        return ""


def build_tour_film(url: str, run_id: str, logo_from: str = "",
                    brain: str = "sonnet5") -> str:
    """v4: planned shots -> titled Vevara film on the site's own palette.
    Film = brand open -> per stop [verbatim TITLE beat -> that stop's planned
    footage] -> CTA settle."""
    run_dir = os.path.join(HERE, "runs", run_id)
    os.makedirs(run_dir, exist_ok=True)
    pub = os.path.join(HERE, "studio", "public")

    stops = plan_tour(url, run_dir, brain=brain, max_stops=5)

    # Execute planned shots. Each additional screen recording must EARN its
    # place (Dennis 2026-07-18: "each screen recording should be different") —
    # one recording per distinct PAGE; a stop on an already-filmed page (or
    # whose footage mirrors a kept clip) becomes a motion-graphic beat instead.
    import walk_shot
    filmed_pages, kept_fps, used_motifs = [], [], set()
    for i, s in enumerate(stops):
        s["seg"] = ""
        if s["page"] in filmed_pages:
            s["motif"] = ""  # graphic; treatment assigned at build
            emit(run_dir, "decide.guard",
                 f"\u201c{s['title'][:48]}\u201d: page already filmed",
                 "This stop becomes a motion graphic instead of a second recording.")
            continue
        seg = os.path.join(run_dir, f"shot-{i + 1}.mp4")
        emit(run_dir, "film.recording",
             f"Recording: {s['title'][:56]}",
             f"Gliding through {s['page']}")
        ok = walk_shot.shot(s["page"], "" if i == 0 else s["target"], seg,
                            run_dir, duration=9.0)
        if not ok:
            # Hosted worker: the main python has no playwright — the capture
            # venv does (same contract as capture_screenshots). Subprocess
            # walk_shot's CLI under that interpreter.
            import capture_screenshots as _cs
            if (os.path.exists(_cs.CAPTURE_PY)
                    and os.path.realpath(_cs.CAPTURE_PY)
                    != os.path.realpath(sys.executable)):
                r = subprocess.run(
                    [_cs.CAPTURE_PY, os.path.join(HERE, "walk_shot.py"),
                     s["page"], "" if i == 0 else s["target"], seg, run_dir,
                     "9.0"], timeout=240)
                ok = r.returncode == 0 and os.path.exists(seg)
        if ok and os.path.exists(seg):
            smooth = _smooth60(seg, os.path.join(run_dir, f"shot-{i + 1}-60.mp4"))
            fp = _clip_fp(smooth)
            if any(_clips_similar(fp, kf) for kf in kept_fps):
                s["motif"] = ""
                emit(run_dir, "decide.guard",
                     f"\u201c{s['title'][:48]}\u201d: footage mirrors a kept clip",
                     "Dropping the duplicate recording; this beat becomes a motion graphic.")
            else:
                s["seg"] = smooth
                kept_fps.append(fp)
                filmed_pages.append(s["page"])
                emit(run_dir, "film.shot", f"Shot kept: {s['title'][:56]}",
                     "Smoothed to 60fps.", artifact=smooth)
        else:
            s["motif"] = ""
    stops = [s for s in stops if s.get("seg") or s.get("motif") is not None]
    if not stops:
        raise RuntimeError("no shots captured")

    theme_src = brand_extract.extract_brand(url, logo_from=logo_from or run_dir)
    pal = theme_src["palette"]
    name = theme_src.get("name") or url
    host = theme_src.get("host") or url
    tagline = (theme_src.get("tagline") or "").strip()
    manifest = brand_extract._find_capture_manifest(logo_from or run_dir)
    shot_png = brand_extract._shot_path_from_manifest(manifest) if manifest else ""
    site_bg = _site_bg_from_shot(shot_png) or pal.get("bg") or "#FFFFFF"
    _r, _g, _b = (int(site_bg[i:i + 2], 16) for i in (1, 3, 5))
    dark_world = (_r * 299 + _g * 587 + _b * 114) // 1000 < 120
    theme = {"bg": site_bg,
             "ink": "#F2F5F9" if dark_world else (pal.get("ink") or "#0F2338"),
             "inkMuted": "#9AA3B2" if dark_world else "#6B6257",
             "accent": pal["accent"],
             "card": "#191C22" if dark_world else "#FFFFFF",
             "fontDisplay": "Manrope, sans-serif", "fontBody": "Inter, sans-serif",
             "wordmark": name}
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

    ctx = {"theme": theme, "name": name, "host": host, "tagline": tagline,
           "logo_rel": logo_rel, "site_bg": site_bg, "accent": pal["accent"]}
    out, beats = _assemble_and_render(run_id, run_dir, pub, stops, ctx)
    fixed = _review_and_fix(run_id, run_dir, pub, stops, ctx, beats)
    return fixed or out


def _assemble_and_render(run_id, run_dir, pub, stops, ctx):
    """Assembly tail: motif assignment -> world layout -> props -> render ->
    per-beat design stills. Split from build_tour_film so the REVIEWER can
    re-run it with adjusted stops (auto-apply). Returns (film, beats_meta)."""
    theme = ctx["theme"]; name = ctx["name"]; host = ctx["host"]
    tagline = ctx["tagline"]; logo_rel = ctx["logo_rel"]
    site_bg = ctx["site_bg"]
    beats = []
    elements, moments = [], [{"at": 0, "x": 960, "y": 540, "scale": 1.0}]
    hero_line = tagline or f"{name} — see it live"
    accent_word = max(hero_line.split(), key=len).strip(".,")
    elements += [
        {"id": "wm", "kind": "wordmark", "x": 960, "y": 330, "at": 4, "text": name, "dir": "top"},
        {"id": "h1", "kind": "headline", "x": 960, "y": 520, "w": 1300, "at": 8,
         "text": hero_line, "accentWord": accent_word, "dir": "bottom"},
        {"id": "sub", "kind": "sub", "x": 960, "y": 724, "w": 980, "at": 20,
         "text": f"A planned tour of {host}, filmed by the launch agent.", "dir": "bottom"},
    ]
    t_f = int(4.4 * FPS)

    # Spatial clusters spread FAR apart (>=2400px) so no neighbor bleeds into
    # another beat's framing; camera zooms slightly on titles.
    cluster_pos = [(3600, 700), (700, 2800), (4200, 3400), (1800, 5000),
                   (6400, 4600), (900, 6600)]
    # MOTIF ASSIGNMENT (single pass): content-once dedupe in beat order,
    # then refine on what each beat will ACTUALLY show, then a film-wide
    # variety guarantee — >=4 graphic beats include at least one line-art
    # drawing (flip the weakest data beat).
    _LINE_ART = ("house", "chat", "tag", "globe", "card")
    presented, used_motifs = set(), set()
    gstops = [s for s in stops if not s.get("seg")]
    for s in gstops:
        s["chips"] = [c for c in (s.get("chips") or [])
                      if c.lower() not in presented]
        s["details"] = [d for d in (s.get("details") or [])
                        if d.lower() not in presented]
        if s.get("motif_locked"):
            used_motifs.add(s["motif"])  # reviewer's decision stands
        else:
            s["motif"] = _refine_motif(
                _pick_motif(s["title"] + " " + s.get("target", ""), used_motifs),
                s, used_motifs)
            used_motifs.add(s["motif"])
        presented.update(x.lower() for x in (s.get("chips") or [])[:10])
        presented.update(x.lower() for x in (s.get("details") or []))
        presented.update(e.lower() for e in (s.get("entities") or []))
    if len(gstops) >= 4 and not any(s["motif"] in _LINE_ART for s in gstops):
        data = [s for s in gstops if s["motif"] in
                ("check-list", "chip-sweep", "request-table", "context-cards")
                and not s.get("motif_locked")]
        if data:
            weakest = min(data, key=lambda s: len(s.get("details") or [])
                          + len((s.get("chips") or [])[:10]))
            weakest["motif"] = _pick_motif(weakest["title"], set(_VIGNETTES))
    emit(run_dir, "decide.treatments", "Treatments assigned",
         "\n".join(f"\u201c{s['title'][:44]}\u201d \u2192 "
                    f"{'recording' if s.get('seg') else s['motif']}"
                    for s in stops))

    seen_titles = set()
    glayout_cycle = ["stacked", "split-left", "split-right"]
    glayout_i = 0
    for i, s in enumerate(stops):
        cx, cy = cluster_pos[i % len(cluster_pos)]
        # CONTRACT: a title text renders as a beat at most once per film —
        # a graphic stop whose title an earlier beat already carries plays
        # title-less at its cluster center (the vignette IS the content).
        dup_title = s["title"].lower() in seen_titles
        seen_titles.add(s["title"].lower())
        if dup_title and not s.get("seg"):
            motif = s.get("motif", "card")
            logos = ([{"name": n, "src": _logo_uri(n)}
                      for n in (s.get("entities") or [])[:8]]
                     if motif == "logo-wall" else [])
            elements.append({"id": f"g{i}", "kind": "graphic", "x": cx, "y": cy,
                             "at": t_f + 12, "motif": motif, "text": s["title"],
                             "lines": s.get("details") or [],
                             "chips": s.get("chips") or [], "logos": logos})
            moments.append({"at": t_f, "x": cx, "y": cy + 10, "scale": 1.12})
            beats.append({"i": i, "title": s["title"], "treatment": motif,
                          "layout": "center", "at": t_f})
            beat_s = {"chip-sweep": 5.5, "stat-pop": 4.0, "kinetic-line": 3.5,
                      "logo-wall": 5.0, "people-wall": 5.0}.get(motif, 5.5)
            t_f += int(beat_s * FPS)
            continue
        if s.get("motif") == "kinetic-line" and not s.get("seg"):
            # The kinetic line IS the title — one beat, no duplicate headline.
            elements.append({"id": f"g{i}", "kind": "graphic", "x": cx, "y": cy,
                             "at": t_f + 12, "motif": "kinetic-line",
                             "text": s["title"]})
            moments.append({"at": t_f, "x": cx, "y": cy + 10, "scale": 1.12})
            beats.append({"i": i, "title": s["title"],
                          "treatment": "kinetic-line", "layout": "center",
                          "at": t_f})
            t_f += int(3.5 * FPS)
            continue
        if not s.get("seg"):
            layout = glayout_cycle[glayout_i % len(glayout_cycle)]
            glayout_i += 1
            if layout != "stacked":
                # SPLIT beat: title and vignette side by side, ONE framing —
                # a different rhythm and geometry from stacked beats
                # (variability contract + Dennis's split-layout preference).
                sign = -1 if layout == "split-left" else 1
                motif = s.get("motif", "card")
                logos = ([{"name": n, "src": _logo_uri(n)}
                          for n in (s.get("entities") or [])[:8]]
                         if motif == "logo-wall" else [])
                elements.append({"id": f"t{i}", "kind": "headline",
                                 "x": cx + sign * -390, "y": cy, "w": 560,
                                 "at": t_f + 12, "text": s["title"], "size": 60,
                                 "align": "left",
                                 "accentWord": max(s["title"].split(), key=len).strip(".,"),
                                 "dir": "left" if sign < 0 else "right"})
                elements.append({"id": f"g{i}", "kind": "graphic",
                                 "x": cx + sign * 330, "y": cy, "at": t_f + 20,
                                 "motif": motif, "text": s["title"],
                                 "lines": s.get("details") or [],
                                 "chips": s.get("chips") or [],
                                 "quotes": s.get("quotes") or [],
                                 "logos": logos, "narrow": True})
                moments.append({"at": t_f, "x": cx, "y": cy + 10, "scale": 1.05})
                beats.append({"i": i, "title": s["title"], "treatment": motif,
                              "layout": layout, "at": t_f})
                beat_s = {"chip-sweep": 6.0, "stat-pop": 4.5, "logo-wall": 5.5,
                          "quote-card": 5.5, "people-wall": 5.5}.get(motif, 6.0)
                t_f += int(beat_s * FPS)
                continue
        # Title beat — the site's own words, section-title sized (stacked).
        elements.append({"id": f"t{i}", "kind": "headline", "x": cx, "y": cy - 340,
                         "w": 1180, "at": t_f + 14, "text": s["title"], "size": 72,
                         "accentWord": max(s["title"].split(), key=len).strip(".,"),
                         "dir": "bottom"})
        moments.append({"at": t_f, "x": cx, "y": cy - 320, "scale": 1.12})
        t_f += int(2.4 * FPS)
        if s.get("seg"):
            # Footage beat — the planned shot below its title.
            seg_dur = _probe_duration(s["seg"])
            rel = f"walkrec-{run_id}-shot{i + 1}.mp4"
            shutil.copyfile(s["seg"], os.path.join(pub, rel))
            elements.append({"id": f"v{i}", "kind": "video", "x": cx, "y": cy + 330,
                             "w": 1300, "at": t_f + 12, "videoSrc": rel})
            moments.append({"at": t_f, "x": cx, "y": cy + 340, "scale": 1.0})
            beats.append({"i": i, "title": s["title"], "treatment": "recording",
                          "layout": "stacked", "at": t_f})
            t_f += int(min(seg_dur, 7.0) * FPS)
        else:
            # Motion-graphic beat — a concept vignette that ENACTS the title
            # (or a line-art motif fallback) instead of a redundant recording.
            motif = s.get("motif", "card")
            logos = ([{"name": n, "src": _logo_uri(n)}
                      for n in (s.get("entities") or [])[:8]]
                     if motif == "logo-wall" else [])
            elements.append({"id": f"g{i}", "kind": "graphic", "x": cx,
                             "y": cy + 300, "at": t_f + 12,
                             "motif": motif, "text": s["title"],
                             "lines": s.get("details") or [],
                             "chips": s.get("chips") or [],
                             "quotes": s.get("quotes") or [],
                             "logos": logos})
            # Push in on graphic beats — vignettes must fill the frame.
            moments.append({"at": t_f, "x": cx, "y": cy + 310, "scale": 1.15})
            beats.append({"i": i, "title": s["title"], "treatment": motif,
                          "layout": "stacked", "at": t_f})
            beat_s = {"chip-sweep": 5.5, "stat-pop": 4.0, "kinetic-line": 3.5,
                      "logo-wall": 5.0,
                      "request-table": 5.5, "context-cards": 5.5,
                      "chat-exchange": 5.5, "price-card": 5.0,
                      "check-list": 5.0}.get(motif, 5.5)
            t_f += int(beat_s * FPS)

    elements.append({"id": "cta", "kind": "cta", "x": 6200, "y": 1800,
                     "at": t_f + 16, "text": "See it live", "label": host,
                     "value": "Get started", "logoSrc": logo_rel or None, "dir": "bottom"})
    moments.append({"at": t_f, "x": 6200, "y": 1810, "scale": 0.98})
    t_f += int(4.6 * FPS)

    try:
        with open(os.path.join(run_dir, "stops.json"), "w") as f:
            json.dump({"stops": stops, "ctx": ctx}, f, indent=2, default=str)
    except Exception:
        pass
    props = {"fps": FPS, "total_frames": t_f, "theme": theme,
             "elements": elements, "moments": moments}
    props_path = os.path.join(run_dir, "walkrec-tour-props.json")
    with open(props_path, "w") as f:
        json.dump(props, f, indent=2)
    run_dir = os.path.abspath(run_dir)
    out = os.path.join(run_dir, "film-tour.mp4")
    emit(run_dir, "assemble.render",
         f"Rendering the film — {t_f / FPS:.1f}s, {len(stops)} beats",
         f"World palette {site_bg}, accent {ctx['accent']}.")
    subprocess.run(["npx", "remotion", "render", "WalkrecWorld", out,
                    f"--props={props_path}", "--log=error"],
                   cwd=os.path.join(HERE, "studio"), check=True, timeout=900)
    emit(run_dir, "assemble.film", "Film rendered", f"{t_f / FPS:.1f}s",
         artifact=out)
    for b in beats:
        fsec = min((b["at"] + 84) / FPS, t_f / FPS - 0.3)
        still = os.path.join(run_dir, f"beat-{b['i']}.jpg")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss",
                        f"{fsec:.2f}", "-i", out, "-frames:v", "1",
                        "-vf", "scale=960:-1", still], check=False, timeout=60)
        if os.path.exists(still):
            b["still"] = still
            emit(run_dir, "design.beat",
                 f"Beat {b['i'] + 1}: {b['treatment']} ({b['layout']})",
                 f"\u201c{b['title'][:60]}\u201d \u00b7 {b['at'] / FPS:.1f}s",
                 artifact=still)
    print(f"[walkrec] tour film: {out} ({t_f / FPS:.1f}s, {len(stops)} planned shots, bg {site_bg})")
    return out, beats


def _lint_stops(stops):
    """Deterministic post-conditions: re-check tonight's contracts on the
    final beat plan. Returns [(stop_index, issue, fix_motif_or_None)]."""
    findings = []
    prev = None
    for i, s in enumerate(stops):
        motif = "recording" if s.get("seg") else s.get("motif", "")
        details = s.get("details") or []
        if motif == prev and motif not in ("recording",):
            findings.append((i, f"adjacent repeated treatment ({motif})", None))
        if motif == "chip-sweep" and len((s.get("chips") or [])) < 6:
            findings.append((i, "chip-sweep below material floor", "check-list"
                             if len(details) >= 2 else "card"))
        if motif == "quote-card" and not s.get("quotes"):
            findings.append((i, "quote-card without a harvested quote",
                             "people-wall" if sum(1 for d in details
                                                  if "@" in d) >= 2 else "card"))
        if motif == "logo-wall" and sum(
                1 for e in (s.get("entities") or []) if e) < 4:
            findings.append((i, "logo wall below 4 partners", "check-list"
                             if len(details) >= 2 else "card"))
        prev = motif
    return findings


_CRITIC_MENU = ("none", "drop", "swap_treatment")
_SWAP_TARGETS = ("check-list", "chip-sweep", "kinetic-line", "quote-card",
                 "people-wall", "stat-pop", "house", "chat", "globe", "card",
                 "tag")


def _critic_review(run_dir, stops, beats, brain="sonnet5"):
    """LLM critic with a CLOSED action menu. Sees the beat stills + the plan;
    may only drop a beat or swap its treatment — it can never write content,
    so every honesty gate survives review. Returns gated actions."""
    import base64
    try:
        import validate_planner as vp
    except Exception:
        return []
    plan_lines = []
    content = []
    for b in beats:
        s = stops[b["i"]] if b["i"] < len(stops) else {}
        plan_lines.append(
            f"beat {b['i']}: title=\u201c{b['title']}\u201d "
            f"treatment={b['treatment']} layout={b['layout']} "
            f"material={ (s.get('details') or [])[:3] }")
        still = b.get("still")
        if still and os.path.exists(still):
            with open(still, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
            content.append({"type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})
    sys_prompt = (
        "You review a product launch film. Judge STORY and COHERENCE: does "
        "each beat's title match what the beat shows, is any beat empty or "
        "redundant, does the sequence flow? You may ONLY act via this menu "
        "per beat: none | drop | swap_treatment (to one of: "
        + ", ".join(_SWAP_TARGETS) + "). You cannot write copy. Return STRICT "
        'JSON: [{"beat": <index>, "verdict": "ok"|"issue", "issue": "<short '
        'reason>", "action": "none"|"drop"|"swap_treatment", "to": "<target '
        'or empty>"}] — one object per beat, no prose.')
    user_content = ([{"type": "text", "text": "\n".join(plan_lines)}] + content
                    if content else "\n".join(plan_lines))
    try:
        raw = vp.call_model([{"role": "system", "content": sys_prompt},
                             {"role": "user", "content": user_content}],
                            brain=brain) or ""
    except (Exception, SystemExit):
        try:
            raw = vp.call_model([{"role": "system", "content": sys_prompt},
                                 {"role": "user",
                                  "content": "\n".join(plan_lines)}],
                                brain=brain) or ""
        except (Exception, SystemExit):
            return []
    cand = _extract_json_list(raw) or []
    actions, drops = [], 0
    for c in cand:
        try:
            bi = int(c.get("beat", -1))
        except Exception:
            continue
        act = str(c.get("action") or "none")
        if bi < 0 or bi >= len(stops) or act not in _CRITIC_MENU:
            continue
        if act == "drop":
            if drops >= 2 or stops[bi].get("seg"):
                continue  # never drop recordings; max 2 drops
            drops += 1
        if act == "swap_treatment":
            to = str(c.get("to") or "")
            if to not in _SWAP_TARGETS or stops[bi].get("seg"):
                continue
            if _refine_motif(to, stops[bi], set()) != to:
                continue  # target's material floor must hold
        if act != "none":
            actions.append({"beat": bi, "action": act,
                            "to": str(c.get("to") or ""),
                            "issue": str(c.get("issue") or "")[:120]})
    return actions


def _review_and_fix(run_id, run_dir, pub, stops, ctx, beats):
    """One review cycle (auto-apply, per Dennis): deterministic linter +
    stills-seeing critic -> gated actions -> re-assemble once. Everything
    visible in the feed as review.* events. Returns the fixed film or None."""
    emit(run_dir, "review.start", "Reviewing story and architecture",
         f"{len(beats)} beats: linter + critic pass.")
    findings = _lint_stops(stops)
    for i, issue, fix in findings:
        emit(run_dir, "review.lint", f"Beat {i + 1}: {issue}",
             f"Fix: swap to {fix}." if fix else "Flagged for the critic.")
    actions = _critic_review(run_dir, stops, beats)
    for a in actions:
        emit(run_dir, "review.finding",
             f"Beat {a['beat'] + 1}: {a['issue'] or a['action']}",
             f"Action: {a['action']}"
             + (f" \u2192 {a['to']}" if a['to'] else ""))
    lint_fixes = [(i, fix) for i, _, fix in findings if fix]
    if not lint_fixes and not actions:
        emit(run_dir, "review.pass", "Review passed",
             "Story and treatments hold; shipping the first cut.")
        return None
    drop_idx = sorted({a["beat"] for a in actions if a["action"] == "drop"},
                      reverse=True)
    for i, fix in lint_fixes:
        stops[i]["motif"] = fix
        stops[i]["motif_locked"] = True
    for a in actions:
        if a["action"] == "swap_treatment":
            stops[a["beat"]]["motif"] = a["to"]
            stops[a["beat"]]["motif_locked"] = True
    for i in drop_idx:
        stops.pop(i)
    shutil.copyfile(os.path.join(run_dir, "film-tour.mp4"),
                    os.path.join(run_dir, "film-tour-prereview.mp4"))
    emit(run_dir, "review.apply",
         f"Applying {len(lint_fixes) + len(actions)} adjustments",
         "Re-assembling and re-rendering the film.")
    out, _beats2 = _assemble_and_render(run_id, run_dir, pub, stops, ctx)
    emit(run_dir, "review.done", "Review complete — film updated",
         artifact=out)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--clip", default="")
    ap.add_argument("--logo-from", default="")
    ap.add_argument("--night", action="store_true",
                    help="v2: Engineered Night kinetic beats around the footage")
    ap.add_argument("--vevara", action="store_true",
                    help="v3: Vevara world-moments grammar on the site's own palette")
    ap.add_argument("--tour", action="store_true",
                    help="v4: planned shot-list tour (analyze -> decide -> film)")
    a = ap.parse_args()
    if a.tour:
        run_dir = os.path.join(HERE, "runs", a.run_id)
        emit(run_dir, "run.start", f"Launch agent started for {a.url}",
             "Reading the site, planning the shots, filming.")
        try:
            build_tour_film(a.url, a.run_id, a.logo_from)
            emit(run_dir, "run.done", "Run finished",
                 "The film is rendered and ready.")
        except BaseException as e:
            emit(run_dir, "run.error", "Run failed", f"{type(e).__name__}: {e}")
            raise
    elif a.vevara:
        build_vevara_film(a.url, a.run_id, a.clip, a.logo_from)
    elif a.night:
        build_night_film(a.url, a.run_id, a.clip, a.logo_from)
    else:
        build_film(a.url, a.run_id, a.clip, a.logo_from)


if __name__ == "__main__":
    main()
