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
    out = []
    for line in window.split("\n"):
        frag = line.strip()
        if not (8 <= len(frag) <= 45) or not (2 <= len(frag.split()) <= 6):
            continue
        if not frag[0].isalnum():
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
    ledger = site_read.browse_site(url, run_dir, brain=None,
                                   homepage_text=home_text)
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
                "names — each 2-6 words, under 45 chars)}. Copy text EXACTLY — "
                "do not write your own words. No prose outside the JSON."
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
                              "details": _verbatim_details(c, corpus_lc)})
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
                                  "details": _verbatim_details(c, corpus_lc)})
            if stops:
                corpus_raw = " ".join(pages.values())
                for s in stops:
                    if len(s.get("details") or []) < 2:
                        have = s.get("details") or []
                        mined = _harvest_details(corpus_raw, s.get("target", ""),
                                                 s["title"])
                        s["details"] = (have + [m for m in mined
                                                if m not in have])[:4]
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
    print("[tour] plan: " + " | ".join(s["title"] for s in stops), file=sys.stderr)
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


def _clips_similar(fa, fb, thresh: float = 10.0) -> bool:
    """True when two clips share a near-identical frame (SPA-mirror guard).
    Calibrated 2026-07-18 on homefeed: genuinely different folds of the SAME
    page measure 13.9+; only true visual mirrors fall under 10."""
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
    ("price-card", ("price", "pricing", "plan", "pay", "subscription", "cost", "free ", "offer")),
    ("globe", ("language", "languages", "global", "world", "international", "translat")),
    ("card", ("link", "profile", "page", "website", "site", "portfolio")),
    ("house", ("real ", "rent")),
]

_VIGNETTES = {"request-table", "context-cards", "chat-exchange", "price-card",
              "check-list"}


def _pick_motif(text: str, used) -> str:
    """Domain-themed motif for a motion-graphic beat, keyword-scored from the
    stop's own words; never repeats within a film."""
    lc = (text or "").lower()
    for motif, kws in _MOTIF_KEYWORDS:
        if motif not in used and any(k in lc for k in kws):
            return motif
    for motif, _ in _MOTIF_KEYWORDS:
        if motif not in used:
            return motif
    return "card"


def build_tour_film(url: str, run_id: str, logo_from: str = "",
                    brain: str = "sonnet5") -> str:
    """v4: planned shots -> titled Vevara film on the site's own palette.
    Film = brand open -> per stop [verbatim TITLE beat -> that stop's planned
    footage] -> CTA settle."""
    run_dir = os.path.join(HERE, "runs", run_id)
    os.makedirs(run_dir, exist_ok=True)
    pub = os.path.join(HERE, "studio", "public")

    stops = plan_tour(url, run_dir, brain=brain)

    # Execute planned shots. Each additional screen recording must EARN its
    # place (Dennis 2026-07-18: "each screen recording should be different") —
    # one recording per distinct PAGE; a stop on an already-filmed page (or
    # whose footage mirrors a kept clip) becomes a motion-graphic beat instead.
    import walk_shot
    filmed_pages, kept_fps, used_motifs = [], [], set()
    for i, s in enumerate(stops):
        s["seg"] = ""
        if s["page"] in filmed_pages:
            s["motif"] = _pick_motif(s["title"] + " " + s.get("target", ""), used_motifs)
            if (s["motif"] not in _VIGNETTES and len(s.get("details") or []) >= 2
                    and "check-list" not in used_motifs):
                s["motif"] = "check-list"  # real info beats line art
            used_motifs.add(s["motif"])
            print(f"[tour] stop {i + 1}: page already filmed -> motion graphic "
                  f"({s['motif']})", file=sys.stderr)
            continue
        seg = os.path.join(run_dir, f"shot-{i + 1}.mp4")
        ok = walk_shot.shot(s["page"], "" if i == 0 else s["target"], seg,
                            run_dir, duration=9.0)
        if ok and os.path.exists(seg):
            smooth = _smooth60(seg, os.path.join(run_dir, f"shot-{i + 1}-60.mp4"))
            fp = _clip_fp(smooth)
            if any(_clips_similar(fp, kf) for kf in kept_fps):
                s["motif"] = _pick_motif(s["title"] + " " + s.get("target", ""), used_motifs)
                used_motifs.add(s["motif"])
                print(f"[tour] stop {i + 1}: footage mirrors a kept clip -> "
                      f"motion graphic ({s['motif']})", file=sys.stderr)
            else:
                s["seg"] = smooth
                kept_fps.append(fp)
                filmed_pages.append(s["page"])
        else:
            s["motif"] = _pick_motif(s["title"] + " " + s.get("target", ""), used_motifs)
            used_motifs.add(s["motif"])
    stops = [s for s in stops if s.get("seg") or s.get("motif")]
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
    cluster_pos = [(3600, 700), (700, 2800), (4200, 3400), (1800, 5000)]
    for i, s in enumerate(stops):
        cx, cy = cluster_pos[i % len(cluster_pos)]
        # Title beat — the site's own words, section-title sized.
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
            t_f += int(min(seg_dur, 9.5) * FPS)
        else:
            # Motion-graphic beat — a concept vignette that ENACTS the title
            # (or a line-art motif fallback) instead of a redundant recording.
            motif = s.get("motif", "card")
            elements.append({"id": f"g{i}", "kind": "graphic", "x": cx,
                             "y": cy + 300, "w": 760, "at": t_f + 12,
                             "motif": motif, "text": s["title"],
                             "lines": s.get("details") or []})
            # Push in on graphic beats — vignettes must fill the frame.
            moments.append({"at": t_f, "x": cx, "y": cy + 310, "scale": 1.15})
            t_f += int((6.5 if motif in _VIGNETTES else 5.5) * FPS)

    elements.append({"id": "cta", "kind": "cta", "x": 6200, "y": 1800,
                     "at": t_f + 16, "text": f"See it live at {host}",
                     "value": "Get started", "logoSrc": logo_rel or None, "dir": "bottom"})
    moments.append({"at": t_f, "x": 6200, "y": 1810, "scale": 0.98})
    t_f += int(4.6 * FPS)

    props = {"fps": FPS, "total_frames": t_f, "theme": theme,
             "elements": elements, "moments": moments}
    props_path = os.path.join(run_dir, "walkrec-tour-props.json")
    with open(props_path, "w") as f:
        json.dump(props, f, indent=2)
    out = os.path.join(run_dir, "film-tour.mp4")
    subprocess.run(["npx", "remotion", "render", "WalkrecWorld", out,
                    f"--props={props_path}", "--log=error"],
                   cwd=os.path.join(HERE, "studio"), check=True, timeout=900)
    print(f"[walkrec] tour film: {out} ({t_f / FPS:.1f}s, {len(stops)} planned shots, bg {site_bg})")
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
        build_tour_film(a.url, a.run_id, a.logo_from)
    elif a.vevara:
        build_vevara_film(a.url, a.run_id, a.clip, a.logo_from)
    elif a.night:
        build_night_film(a.url, a.run_id, a.clip, a.logo_from)
    else:
        build_film(a.url, a.run_id, a.clip, a.logo_from)


if __name__ == "__main__":
    main()
