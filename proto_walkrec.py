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
import re
import shutil
import signal
import subprocess
import sys
import time

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
    _kept = sum(1 for s in stops if s.get("seg"))
    _say(run_dir,
         f"Footage is in — {_kept} recording{'s' if _kept != 1 else ''} kept. "
         "Now let me cut it into a film on your own palette: the graphic "
         "beats between the recordings only say what I could quote from "
         "your pages, so nothing in the cut is invented.")
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

    _kept = sum(1 for s in stops if s.get("seg"))
    _say(run_dir,
         f"Footage is in — {_kept} recording{'s' if _kept != 1 else ''} kept. "
         "Now let me cut it into a film on your own palette: the graphic "
         "beats between the recordings only say what I could quote from "
         "your pages, so nothing in the cut is invented.")
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


def _srgb_lum(r: int, g: int, b: int) -> float:
    """WCAG relative luminance. Same maths the run header's RunMark uses, so a
    mark is judged by ONE standard whether it is drawn in chrome or in film."""
    def ch(v: int) -> float:
        c = v / 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def _contrast(a: float, b: float) -> float:
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


def _hex_rgb(h: str):
    """[r, g, b] from '#rrggbb' / '#rgb'; None when unparseable."""
    h = (h or "").strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) < 6:
        return None
    try:
        return [int(h[i:i + 2], 16) for i in (0, 2, 4)]
    except ValueError:
        return None


def _contrast_hex(a: str, b: str) -> float:
    """WCAG contrast ratio between two colours: 1.0 (identical) … 21.0.
    Hex-string face of `_contrast` above (which takes luminances — _logo_plate
    already leans on it), so both are ONE standard rather than two."""
    ra, rb = _hex_rgb(a), _hex_rgb(b)
    if not ra or not rb:
        return 21.0  # unparseable: do not "rescue" a colour we cannot read
    return _contrast(_srgb_lum(*ra), _srgb_lum(*rb))


def _legible_ink(ink: str, ground: str, min_ratio: float = 4.5,
                 target: float = 13.0) -> str:
    """The ink this GROUND can carry.

    A harvested ink carries no memory of the background that made it legible.
    BRAND_PALETTES['stripe.com'] pairs fg #FFFFFF with bg #0A2540 — 15.9:1,
    correct in its own pair. The callers below keep that ink and replace the
    ground with the site's OWN measured background (#FEFDFE), where #FFFFFF is
    1.01:1: the 2026-07-19 stripe.com film shipped with an invisible headline,
    an invisible 2.9% stat and an invisible check-list. So an ink is never
    accepted without the ground it will actually land on.

    An ink that already passes is returned UNCHANGED — a genuinely dark world
    keeps its harvested white, and a brand accent that reads keeps its hue. A
    failing ink is shaded toward the ground's opposite pole, preserving hue,
    until it clears `target` (a margin past the bar, so a rescued headline
    reads as ink rather than as a grey that merely passes)."""
    if not ink or not ground:
        return ink
    if _contrast_hex(ink, ground) >= min_ratio:
        return ink
    src, gnd = _hex_rgb(ink), _hex_rgb(ground)
    if not src or not gnd:
        return ink
    poles = ((0, 0, 0), (255, 255, 255))
    if _srgb_lum(*gnd) <= 0.179:            # dark ground -> lighten first
        poles = poles[::-1]
    best, best_ratio = ink, _contrast_hex(ink, ground)
    for pole in poles:
        k = 0.04
        while k <= 1.0001:
            cand = "#%02x%02x%02x" % tuple(
                int(round(src[i] + (pole[i] - src[i]) * k)) for i in range(3))
            ratio = _contrast_hex(cand, ground)
            if ratio > best_ratio:
                best, best_ratio = cand, ratio
            if ratio >= target:
                return cand
            k += 0.04
    return best


def _logo_ink(logo_path: str):
    """(is_self_grounded, ink_luminance) for a harvested mark, or None when it
    cannot be read. Local file only — NO network, no new dependency: rasters go
    through ffmpeg rawvideo + stdlib parse (the discipline _site_bg_from_shot
    and brand_extract._accent_from_pixels already use), SVGs are read as text.

    'Self-grounded' means the asset carries its own opaque background (the
    app-icon .ico/.png case, 59 of the 63 marks staged to date). Those never let
    the world colour touch their ink, so they need no plate."""
    if not logo_path or not os.path.exists(logo_path):
        return None
    ext = os.path.splitext(logo_path)[1].lower()
    try:
        if ext == ".svg":
            import re as _re
            with open(logo_path, encoding="utf-8", errors="ignore") as fh:
                s = fh.read()
            # A full-bleed <rect> is the SVG way of carrying your own ground.
            grounded = bool(_re.search(r"<rect[^>]*width=\"(?:100%|\d+)\"", s))
            cols = [c for c in _re.findall(
                r"(?:fill|stroke)=\"#([0-9a-fA-F]{6})\"", s)]
            if not cols:
                return None
            vals = [_srgb_lum(int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16))
                    for c in cols]
            return grounded, sum(vals) / len(vals)
        raw = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", logo_path, "-vf", "scale=48:48",
             "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgba", "-"],
            capture_output=True, timeout=30).stdout
        if len(raw) < 16:
            return None
        total = opaque = 0
        acc = wgt = 0.0
        for i in range(0, len(raw) - 3, 4):
            a = raw[i + 3]
            total += 1
            if a >= 250:
                opaque += 1
            if a < 24:
                continue
            w = a / 255.0
            acc += _srgb_lum(raw[i], raw[i + 1], raw[i + 2]) * w
            wgt += w
        if not total or wgt < 1:
            return None
        return (opaque / total) > 0.90, acc / wgt
    except Exception:
        return None


def _logo_plate(logo_path: str, world_bg: str) -> str:
    """The colour the mark must sit on so its own ink survives the world it is
    dropped into — '' when the world already serves it and no plate is owed.

    THE DEFECT THIS KILLS: the walkrec world paints `bg` with a colour sampled
    from the CUSTOMER'S OWN PAGE, then drew the harvested logo straight onto it
    with no contrast check (WalkrecWorld cta). A brand's logo ink and its site
    chrome come from the same palette by construction, so 'sampled from their
    page' is precisely the colour most likely to swallow their mark. dark_world
    was already computed one line above to flip `ink`, `inkMuted` and `card` —
    the logo simply never consulted it. This closes that asymmetry, and does it
    by MEASURING the mark rather than by trusting the world's own flag."""
    read = _logo_ink(logo_path)
    if not read:
        return ""
    grounded, ink = read
    if grounded:
        return ""  # carries its own background; the world never touches it
    try:
        wr, wg, wb = (int(world_bg[i:i + 2], 16) for i in (1, 3, 5))
    except Exception:
        return ""
    world = _srgb_lum(wr, wg, wb)
    if _contrast(ink, world) >= 3.0:
        return ""  # already legible where it lands
    # Two candidates are provably enough: every ink clears 3:1 against one.
    return "#FFFFFF" if _contrast(ink, 1.0) >= _contrast(ink, 0.0109) else "#14161A"


def _stage_mark(src: str, dest: str) -> None:
    """Copy a harvested mark into studio/public, enforcing asset hygiene on the
    way in (raster: max 800px on the long edge; SVG: passed through, it is
    vector). Marks arrive at whatever size the site happened to publish — an
    apple-touch-icon is routinely 1024px, which is 1.3x the cap and pure render
    cost for something drawn at 84px. Downscale only, never upscale: a small
    mark is never inflated to meet a floor it cannot really meet.

    Local ffmpeg only, no network. Any failure falls back to the plain copy, so
    hygiene can never be the reason a film loses its logo."""
    try:
        ext = os.path.splitext(src)[1].lower()
        if ext != ".svg":
            probe = subprocess.run(
                ["ffprobe", "-v", "error", "-select_streams", "v:0",
                 "-show_entries", "stream=width,height", "-of", "csv=p=0:s=x",
                 src], capture_output=True, timeout=20, text=True).stdout.strip()
            w, h = (int(v) for v in probe.split("x")[:2])
            if max(w, h) > 800:
                r = subprocess.run(
                    ["ffmpeg", "-v", "error", "-y", "-i", src, "-vf",
                     "scale='if(gt(iw,ih),800,-1)':'if(gt(iw,ih),-1,800)':flags=lanczos",
                     dest], capture_output=True, timeout=60)
                if r.returncode == 0 and os.path.getsize(dest) > 0:
                    return
    except Exception:
        pass
    shutil.copyfile(src, dest)


def build_vevara_film(url: str, run_id: str, clip: str, logo_from: str = "") -> str:
    """v3 (Dennis 2026-07-18): the Vevara-grammar film ON THE BRAND'S OWN
    PALETTE — world bg sampled from the captured page, camera moments with the
    fitted swift-S curve, blur+slide+fade chords, footage in rounded cards."""
    run_dir = os.path.join(HERE, "runs", run_id)
    os.makedirs(run_dir, exist_ok=True)
    pub = os.path.join(HERE, "studio", "public")

    _kept = sum(1 for s in stops if s.get("seg"))
    _say(run_dir,
         f"Footage is in — {_kept} recording{'s' if _kept != 1 else ''} kept. "
         "Now let me cut it into a film on your own palette: the graphic "
         "beats between the recordings only say what I could quote from "
         "your pages, so nothing in the cut is invented.")
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

    # THE GROUND DECIDES THE INK. `site_bg` is measured off the screenshot's
    # pixels; `pal["ink"]` is harvested from a curated palette that supplied
    # its OWN background. Marrying them without a contrast test is what put a
    # white headline on a white world.
    theme = {
        "bg": site_bg,
        "ink": _legible_ink(pal.get("ink") or "#0F2338", site_bg),
        "inkMuted": _legible_ink(
            "#6B6257" if site_bg.lower() != "#ffffff" else "#5A6472",
            site_bg, target=6.0),
        "accent": _legible_ink(pal["accent"], site_bg,
                               min_ratio=3.0, target=3.3),
        "card": "#FFFFFF",
        "fontDisplay": "Manrope, sans-serif",
        "fontBody": "Inter, sans-serif",
        "wordmark": name,
    }
    logo = theme_src.get("logo_src")
    logo_rel = ""
    if logo and os.path.exists(logo):
        logo_rel = f"walkrec-logo-{run_id}{os.path.splitext(logo)[1] or '.png'}"
        _stage_mark(logo, os.path.join(pub, logo_rel))
        theme["logoSrc"] = logo_rel
        # A mark is either legible on the world it lands in, or it gets the
        # plate that makes it so. '' = the world already serves it (the common
        # case), and the renderer then draws exactly what it drew before.
        plate = _logo_plate(logo, site_bg)
        if plate:
            theme["logoPlate"] = plate
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
                    f"--props={props_path}", "--log=error",
                    "--concurrency=1",
                    "--offthreadvideo-cache-size-in-bytes=314572800"],
                   cwd=os.path.join(HERE, "studio"), check=True, timeout=1800)
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


def _say(run_dir: str, text: str) -> None:
    """The agent SPEAKING — one prose line at a phase turn, rendered as
    speech in the thread (work receipts stay collapsed beneath it). Say what
    is happening and why it matters to the film; never restate the receipts."""
    emit(run_dir, "say.step", text, "")


def _harvest_quotes(url: str, run_dir: str = ""):
    """REAL testimonial quotes from the marker page's live DOM (lazy-loaded
    sections the static corpus can't see). Capture-interpreter aware."""
    import page_harvest
    return page_harvest.run(url, "quotes", run_dir) or []

def _harvest_partner_marks(url: str, run_dir: str = ""):
    """Partner marks — name AND the site's own logo image — from the
    works-with block itself. Runs under the capture interpreter when the
    main one has no Playwright (see page_harvest)."""
    import page_harvest
    return page_harvest.marks(url, run_dir)


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

    host = url.replace("https://", "").replace("http://", "").split("/")[0]
    _say(run_dir,
         f"Opening {host} now: reading your site the way a first-time "
         "visitor would, so every line in the film comes from your own "
         "words. Taking the homepage first to get your brand — palette, "
         "type, and mark — before anything else.")
    rp = read_pass.read_pass(url, run_dir)
    home_text = rp.get("body_text", "") or ""
    emit(run_dir, "read.page", f"Read {url}",
         f"{len(home_text)} chars of copy",
         artifact=rp.get("hero_screenshot_path") or "")
    # The capture saves brand/logo.<ext> (inline <svg> -> .svg,
    # apple-touch-icon/icon -> .png/.ico) — checking only .png silently
    # skipped every SVG-logo brand (insforge.dev among them).
    import glob as _glob
    _logos = sorted(_glob.glob(os.path.join(
        run_dir, "screenshots-read", "brand", "logo.*")))
    if _logos:
        emit(run_dir, "brand.logo", "Brand mark captured", "",
             artifact=_logos[0])
    _say(run_dir,
         "Homepage read. Now let me follow the pages a buyer would actually "
         "open — pricing, customers, the product pages — so the film can "
         "argue with real detail instead of adjectives.")
    ledger = site_read.browse_site(url, run_dir, brain=None,
                                   homepage_text=home_text)
    for p in (ledger.get("pages") or []):
        shot = os.path.join(run_dir, "site-read", p["slug"], "shot-01.png")
        emit(run_dir, "read.page", f"Read /{p['slug']}",
             f"{len(p.get('body_text') or '')} chars of copy",
             artifact=shot if os.path.exists(shot) else "")
    pages = {"home": home_text}
    page_urls = {"home": url}
    # THE READ PASS ALREADY PHOTOGRAPHED EVERY PAGE, at the recorder's own
    # viewport (capture_screenshots uses full_page=False, so these are the
    # same framing a shot opens on). Keeping the paths turns the recorder's
    # duplicate question into a free lookup instead of a 9s capture — see
    # _mirrors_a_kept_page. Indexed by URL because that is all a stop carries.
    home_shot = (rp.get("hero_screenshot_path")
                 or os.path.join(run_dir, "screenshots-read", "shot-01.png"))
    page_shots = {url: home_shot if os.path.exists(home_shot) else ""}
    for p in (ledger.get("pages") or []):
        pages[p["slug"]] = p.get("body_text", "") or ""
        page_urls[p["slug"]] = p.get("url") or url
        shot = os.path.join(run_dir, "site-read", p["slug"], "shot-01.png")
        page_shots.setdefault(p.get("url") or url,
                              shot if os.path.exists(shot) else "")
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
                "pricing/social proof), ordered most important first. "
                # PAGE SPREAD IS THE BRIEF, not a post-filter: the recorder
                # films one shot per page, so moments stacked on one page
                # cannot become footage no matter how good they are.
                "SPREAD THEM ACROSS PAGES: at most ONE moment per [PAGE ...] "
                "slug, and cover as many different pages as you can — this is "
                "a tour, and a tour that revisits one page is not one. Only "
                "return a second moment from a page when the site has fewer "
                "pages than moments worth filming. Return "
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
            # URL DIVERSITY IS A PLANNING CONSTRAINT (F14). The recorder
            # keeps ONE shot per page, so a stop sharing a page with an
            # earlier stop can never become footage — it is a graphic beat
            # the moment it is chosen, whatever the plan pretends. Six stops
            # that resolved to two filmable URLs shipped a "tour" that was
            # two-thirds motion graphics (insforge.dev 2026-07-19); the
            # guards each did the right thing with a plan that could not
            # work. So the plan is built filmable-first:
            #   PASS 1 takes the most important moment on each DISTINCT page.
            #   PASS 2 backfills same-page moments, DECLARED graphic-only and
            #          never outnumbering the filmable stops.
            # A site with two worthwhile pages therefore yields a SHORTER
            # film, which is the honest outcome — never a padded one.
            stops, spare = [], []
            for c in cand[:max_stops * 3]:
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
                st = {"title": title, "page": page_urls[slug],
                      "target": target,
                      "details": _verbatim_details(c, corpus_lc),
                      "entities": _verbatim_entities(c, corpus_lc)}
                if any(s["title"].lower() == title.lower()
                       for s in stops + spare):
                    continue
                # The old hero-region rule (skip a target in the hero fold of
                # a page another stop films) is SUBSUMED: no two filmable
                # stops share a page at all now.
                if any(s["page"] == st["page"] for s in stops):
                    spare.append(st)
                elif len(stops) < max_stops:
                    stops.append(st)
            filmable = len(stops)
            for st in spare:
                if len(stops) >= max_stops or len(stops) - filmable >= filmable:
                    break
                st["graphic_only"] = True
                stops.append(st)
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
    # PROVENANCE: a partner wall may ONLY name what the works-with block
    # itself contains. The old corpus-window fallback took the 700 chars
    # after the marker — for an image-only strip that's the NEXT section,
    # which is how a features grid shipped as an integration wall. No
    # marks in the block = no wall.
    marks = []
    if any(m in corpus_nl.lower() for m in _ENTITY_MARKERS):
        marks = _harvest_partner_marks(url, run_dir)
    ents = [m["name"] for m in marks]
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
            # EARNED, AND A GRAPHIC BY NATURE: the wall exists only when the
            # site names >=4 partners with real marks, and it is a vignette
            # rather than footage — so it declares itself graphic-only up
            # front instead of being discovered as unfilmable at the
            # recorder, and it is exempt from the graphics-vs-filmable cap.
            stops.append({"title": marker_line, "page": url,
                          "target": marker_line, "details": [],
                          "entities": ents, "chips": [],
                          "graphic_only": True, "earned": True,
                          "marks": {m["name"]: m.get("src", "")
                                    for m in marks}})
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
    # PAGE-ONCE, ENFORCED AT THE END (F14): every path into this list passes
    # through here — the brain's picks, the promoted hero, the synthetic hero
    # stop, the deterministic fallback and the ecosystem wall. The first stop
    # on a page is the filmable one; any later stop on that page declares
    # itself a graphic beat in the PLAN, so the film's shape is decided while
    # it can still be reasoned about rather than discovered one wasted
    # capture at a time. ONE enforcement point, so no path can bypass it.
    # RE-DERIVED, NOT INHERITED: the flag is recomputed in FINAL beat order,
    # because the order changes after selection (hero promotion reorders the
    # list). Carrying a stale flag forward put a graphic first and the
    # recording second on the same page — the reverse of what the hero
    # promotion above is for. Only the ecosystem wall keeps its own flag: it
    # is a vignette by nature, not because a page was taken.
    claimed = set()
    for s in stops:
        # Every stop carries the read pass's photograph of its own page,
        # attached HERE for the same reason graphic_only is decided here: one
        # enforcement point that every construction path flows through (the
        # brain's picks, the promoted hero, the synthetic hero stop, the
        # deterministic fallback, the ecosystem wall). "" when the page was
        # never browsed — the recorder then has no cheap signal and pays the
        # normal price, which is the correct behaviour, not a fallback.
        s["read_shot"] = page_shots.get(s["page"], "")
        if s.get("earned"):
            continue
        if s["page"] in claimed:
            s["graphic_only"] = True
        else:
            s["graphic_only"] = False
            claimed.add(s["page"])
    _filmable = sum(1 for s in stops if not s.get("graphic_only"))
    emit(run_dir, "decide.plan",
         f"Planned {len(stops)} moments a customer cares about",
         "\n".join(f"{i + 1}. {s['title']}"
                   + (" (graphic — page already covered)"
                      if s.get("graphic_only") and not s.get("earned")
                      else " (graphic)" if s.get("graphic_only") else "")
                   for i, s in enumerate(stops)))
    _say(run_dir,
         f"Here's the tour I'd film — {len(stops)} moments across "
         f"{_filmable} page{'s' if _filmable != 1 else ''} I can record, "
         f"opening on “{stops[0]['title']}” and closing on "
         f"“{stops[-1]['title']}”. Rolling now: I glide through "
         "each page rather than cutting between screenshots, so it reads "
         "like someone showing you around.")
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


def _still_fp(png: str):
    """The SAME fingerprint as _clip_fp, taken from a still the read pass
    already saved. Returned as a 1-frame list so it drops straight into
    _clips_similar — the pre-capture guard and the post-capture guard must
    compare like with like or their verdicts drift apart (see the pre-capture
    gate in build_tour_film). ~0.04s: no browser, no network, no decode."""
    if not png or not os.path.exists(png):
        return []
    try:
        r = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", png, "-frames:v", "1",
             "-vf", "scale=16:16,format=gray", "-f", "rawvideo", "-"],
            capture_output=True, timeout=30)
        return [r.stdout] if len(r.stdout) == 256 else []
    except Exception:
        return []


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


def _mirrors_a_kept_page(still, kept) -> str:
    """PRE-CAPTURE half of the duplicate guard: does this page's already-saved
    read screenshot mirror a page we have ALREADY filmed? Returns that page's
    stop title (a truthy receipt) or "".

    TWO agreements required, deliberately. A page is skipped only when its
    still mirrors BOTH (a) the still of an already-filmed page and (b) the
    footage actually kept from it. A post-capture drop is fully informed and
    costs only the capture; a pre-capture skip is unrecoverable and would lose
    footage we would have kept — so the cheap tier must be the more
    conservative one, not merely the earlier one.

    Measured 2026-07-19 on the three calibration worlds, using each run's own
    on-disk read screenshots and kept clips (still-vs-still / still-vs-clip):
      insforge.dev (dark) — agents 1.70/1.45, alternatives 1.91/1.71,
        customers 4.34/3.76 vs the kept home shot: all three skip, matching
        the post-capture guard's verdict on the same three pages exactly.
        pricing 8.38/8.07: captured, and kept. 5/5 agreement.
      palmier (light) — demo-vs-pricing stills read 4.22, inside the
        threshold; their footage reads 30.6, far outside. Rule (b) refuses
        the skip. A single-signal gate would have thrown away a real shot.
      homefeed (SPA) — home/pricing stills are a literal 0.00 mirror, but the
        kept footage is a deep scroll at 22.38. No skip; the post-capture
        guard still catches it. A miss here costs one capture, not a shot.
    Both signals reuse _clips_similar at its calibrated threshold — there is
    no second magic number to keep in sync."""
    for k in kept:
        if not k["still"] or not k["clip"]:
            continue
        if (_clips_similar(still, k["still"])
                and _clips_similar(still, k["clip"])):
            return k["title"]
    return ""


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


# ---- THE GREEN-CHECK GATE -------------------------------------------------
# A ticked row asserts "the product does this for you". Harvested strings are
# verbatim by construction but NOT automatically benefit-shaped: "Test Failed"
# is the status label of a preview-branch demo widget, and the check-list
# treatment promoted it into a benefits list under a green tick (insforge.dev
# 2026-07-19) — the words traced to the page, the meaning was inverted.
# SHAPE decides what may wear a check, never provenance.
# The gate is deliberately biased toward DROPPING: "No credit card needed"
# reads as a negation and goes with it. A list one item shorter is honest; a
# list padded back up with a failure state is not.
_TICKED_MOTIFS = frozenset({"check-list", "price-card"})

_STATUS_WORDS = (
    "failed", "failure", "error", "errors", "denied", "rejected", "invalid",
    "expired", "unavailable", "offline", "timeout", "timed out", "unknown",
    "unauthorized", "forbidden", "missing", "broken", "crashed", "deprecated",
    "disabled", "blocked", "warning", "pending", "aborted", "cancelled",
    "canceled", "declined", "revoked", "suspended", "throttled", "not found",
    "coming soon", "beta", "waitlist",
)
_NEGATION_START = ("no ", "not ", "never", "cannot", "can't", "won't",
                   "don't", "doesn't", "isn't", "aren't", "without ")
# A short line ending in a past participle reports an OUTCOME ("Test Failed",
# "Build Passed", "Payment Declined") — including the ones that sound good.
_PAST_OUTCOME = re.compile(r"\b[a-z]{3,}ed\b\s*$", re.I)


def _is_benefit_shaped(item: str) -> bool:
    """May this line wear a green check? A status, an error, a negation or a
    bare past-tense outcome describes what HAPPENED on a page, not what the
    product does for you — each is true as text and a lie under a tick."""
    t = (item or "").strip()
    if not t:
        return False
    lc = t.lower()
    if any(re.search(r"\b" + re.escape(w) + r"\b", lc) for w in _STATUS_WORDS):
        return False
    if lc.startswith(_NEGATION_START):
        return False
    if len(t.split()) <= 3 and _PAST_OUTCOME.search(lc):
        return False
    return True


def _beat_lines(s: dict, motif: str):
    """The detail lines a beat renders. Treatments that TICK their rows only
    ever receive rows that may be ticked. The gate lives at the one place
    lines reach the props, so a treatment added later cannot bypass it."""
    details = s.get("details") or []
    return _tickable(details) if motif in _TICKED_MOTIFS else details


def _tickable(items):
    """The subset of a list eligible for a green check. Callers use the
    LENGTH of this for a treatment's material floor and the list itself for
    the beat's lines, so a gated-out item can never be counted toward a floor
    it then fails to fill."""
    return [i for i in (items or []) if _is_benefit_shaped(i)]


def _shown_material(s: dict, motif: str):
    """What the beat will ACTUALLY put on screen under `motif` — the same list
    its vignette renders. The degrade ladder's bottom rung and the reviewer's
    beat-content check both read this, so "has content" means ONE thing in the
    film and in the review, and a new treatment has one place to declare
    itself. The line-art tier returns [] on purpose: a drawing shows nothing
    of the site."""
    if s.get("seg"):
        return [s["seg"]]
    details = s.get("details") or []
    if motif in _TICKED_MOTIFS:
        return _tickable(details)
    if motif == "chip-sweep":
        return (s.get("chips") or [])[:10]
    if motif == "logo-wall":
        return s.get("entities") or []
    if motif == "quote-card":
        return s.get("quotes") or []
    if motif == "people-wall":
        return (s.get("quotes") or []) or [d for d in details if "@" in d]
    if motif == "stat-pop":
        return [d for d in details if _is_stat_line(d)]
    if motif == "kinetic-line":
        t = s.get("title") or ""
        return [t] if len(t.split()) >= 3 else []
    if motif in ("request-table", "context-cards", "chat-exchange"):
        return details
    return []


# The ladder's bottom rung returns this instead of a treatment: there is no
# treatment that could carry this stop, so the stop leaves the film.
_CUT = "cut"


def _refine_motif(motif: str, s: dict, used) -> str:
    """Content beats keywords: a chip-sweep needs >=6 real chips; a stat-pop
    needs a number; anything data-rich beats line art; a punchy title beats a
    bare drawing (kinetic word-by-word)."""
    import re as _re
    details = s.get("details") or []
    chips = s.get("chips") or []
    # EVERY check-list rung below counts TICKABLE rows, not raw harvested
    # lines: a treatment's material floor has to be measured in the material
    # it will actually SHOW, or the ladder lands on a treatment that renders
    # less than it was chosen for (three harvested lines, one of them "Test
    # Failed", is a two-row list — see _is_benefit_shaped).
    ticks = _tickable(details)
    people = sum(1 for d in details if _re.search(r"@", d))
    # A WALL NEEDS MARKS: a logo wall whose tiles are mostly initial badges
    # is the system announcing it has no logos (eight lettered circles under
    # "Works perfectly with", insforge.dev 2026-07-19). Fewer than half the
    # partners carrying a real mark = not a wall.
    if motif == "logo-wall":
        ents = s.get("entities") or []
        marks = s.get("marks") or {}
        real = sum(1 for n in ents if marks.get(n))
        if len(ents) < 4 or real * 2 < len(ents):
            motif = "chip-sweep" if len(chips) >= 6 else "check-list"
    if motif == "chip-sweep" and len(chips) < 6:
        motif = "check-list" if len(ticks) >= 2 else "kinetic-line"
    if motif == "stat-pop" and not any(_is_stat_line(d) for d in details):
        motif = "check-list" if len(ticks) >= 2 else "kinetic-line"
    if motif == "quote-card" and not s.get("quotes"):
        motif = ("people-wall" if people >= 2
                 else ("check-list" if len(ticks) >= 2 else "card"))
    if motif == "people-wall" and not (s.get("quotes") or people >= 2):
        motif = "check-list" if len(ticks) >= 2 else "card"
    # MINIMUM-MATERIAL contract: a beat must carry real content. kinetic-line
    # needs a >=3-word line AND must never swallow a stop that has details
    # (the 'Testimonials' one-word empty scene, Palmier 2026-07-18).
    if motif == "kinetic-line":
        words = len((s.get("title") or "").split())
        if s.get("quotes"):
            motif = "quote-card"
        elif people >= 2:
            motif = "people-wall"
        elif len(ticks) >= 2:
            motif = "check-list"
        elif words < 3:
            motif = "card"
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
        if len(_tickable(details)) >= 2:
            return "check-list"  # may repeat: real info beats line art
        if (not details and 3 <= len((s.get("title") or "").split()) <= 8
                and "kinetic-line" not in used):
            return "kinetic-line"
    # BOTTOM RUNG (F4). Every rung above only ever SWAPS one treatment for
    # another, so a stop with nothing behind it always landed somewhere
    # rather than nowhere: 8.4s of a title beside a decorative wireframe
    # globe ("Customer Stories", insforge.dev 2026-07-19 — a 638-char page
    # whose duplicate footage was correctly dropped, leaving the beat with
    # no content and no film). Same shape as the wall-needs-marks gate at
    # the top: when the treatment would show nothing OF THE SITE, there is
    # no treatment left to fall back to, so the STOP goes and the film runs
    # one beat shorter. This supersedes the old "better a drawing than a
    # word" fallback — a drawing shows nothing, which is the defect.
    if not s.get("seg") and not _shown_material(s, motif):
        return _CUT
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


def _stop_logos(s: dict, want: int = 8):
    """The wall's marks for one stop, in provenance order: the image the
    site itself renders for that partner, then a mapped favicon, then ''
    (an honest initial badge). Fetched marks are memoised per build."""
    out = []
    marks = s.get("marks") or {}
    for n in (s.get("entities") or [])[:want]:
        src_url = marks.get(n) or ""
        uri = ""
        if src_url:
            if src_url in _MARK_CACHE:
                uri = _MARK_CACHE[src_url]
            else:
                import page_harvest
                uri = page_harvest.mark_data_uri(src_url)
                _MARK_CACHE[src_url] = uri
        out.append({"name": n, "src": uri or _logo_uri(n)})
    return out


_MARK_CACHE: dict = {}


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


# ---- THE PACING CEILING ---------------------------------------------------
# Project budget: no scene over 9s. A beat's SPAN is what a viewer sits
# through — its own dwell PLUS whatever plays before the next beat announces
# itself (a stacked beat's title card, or the closing CTA). That is exactly
# how the design.beat timestamps read back, and read back it shipped beats of
# 9.4s and 9.7s (insforge.dev 2026-07-19).
# The ceiling is enforced HERE, in the assembler, where dwells are FINAL: a
# treatment swap changes a beat's length after planning, so a planner-side
# budget can always be reopened by review. Every dwell in the layout goes
# through _dwell_frames, so a new treatment cannot add an uncapped one.
BEAT_CEILING_S = 9.0
TITLE_LEAD_S = 2.4   # a stacked beat's title card plays before the beat
CTA_S = 4.6          # the closing card, charged to the last beat's span
OPEN_S = 4.4         # the branded open, charged to the first beat's span
# A beat cannot be shorter than its own entrance. If a lead-in ever grows so
# large that the floor wins, _lint_pacing reports the overrun rather than
# letting it pass silently.
MIN_DWELL_S = 2.5

_GLAYOUT_CYCLE = ("stacked", "split-left", "split-right")


def _beat_forms(stops):
    """The visual FORM each stop takes, decided ONCE. The pacing ceiling needs
    to know what follows a beat before it can size it, and the layout loop
    needs the same answer — two copies of this branch would drift. 'stacked'
    beats are preceded by their own title card; 'center'/'kinetic'/'split-*'
    carry their title inside the beat."""
    forms, seen, gi = [], set(), 0
    for s in stops:
        dup = s["title"].lower() in seen
        seen.add(s["title"].lower())
        if s.get("seg"):
            forms.append("stacked")
        elif dup:
            forms.append("center")
        elif s.get("motif") == "kinetic-line":
            forms.append("kinetic")
        else:
            forms.append(_GLAYOUT_CYCLE[gi % len(_GLAYOUT_CYCLE)])
            gi += 1
    return forms


def _lead_after(forms, i: int) -> float:
    """Seconds between beat i's dwell ending and beat i+1 appearing — the next
    beat's title card, or the closing CTA when i is the last beat."""
    if i + 1 >= len(forms):
        return CTA_S
    return TITLE_LEAD_S if forms[i + 1] == "stacked" else 0.0


def _dwell_frames(dwell_s: float, lead_next_s: float) -> int:
    """Frames a beat holds the screen, capped so its SPAN (dwell + the lead-in
    of whatever follows) stays inside BEAT_CEILING_S."""
    capped = min(dwell_s, BEAT_CEILING_S - lead_next_s)
    return int(max(MIN_DWELL_S, capped) * FPS)


def _lint_pacing(beats, film_s):
    """POST-CONDITION on the rendered cut, measured exactly as the thread
    reports it: one design.beat timestamp to the next, and the last one to the
    end of the film. Structurally guaranteed by _dwell_frames — checked anyway
    because a new lead-in constant could reopen the budget silently."""
    out = []
    if beats and beats[0]["at"] / FPS > BEAT_CEILING_S + 0.05:
        out.append(_finding(None, "the opening card",
                            f"holds {beats[0]['at'] / FPS:.1f}s before the "
                            f"first beat (ceiling {BEAT_CEILING_S:.0f}s)"))
    for k, b in enumerate(beats):
        end = beats[k + 1]["at"] / FPS if k + 1 < len(beats) else film_s
        span = end - b["at"] / FPS
        if span > BEAT_CEILING_S + 0.05:
            out.append(_finding(
                b["i"], b["title"],
                f"runs {span:.1f}s (ceiling {BEAT_CEILING_S:.0f}s)"))
    return out


def _film_seconds(path: str, planned_s: float) -> float:
    """The film's REAL length, read off the rendered artifact. Falls back to
    the planned length — which Remotion renders frame-exactly — so a missing
    ffprobe degrades to an exact number rather than to an estimate."""
    try:
        return _probe_duration(path)
    except Exception:
        return planned_s


def build_tour_film(url: str, run_id: str, logo_from: str = "",
                    brain: str = "sonnet5") -> str:
    """v4: planned shots -> titled Vevara film on the site's own palette.
    Film = brand open -> per stop [verbatim TITLE beat -> that stop's planned
    footage] -> CTA settle."""
    run_dir = os.path.join(HERE, "runs", run_id)
    os.makedirs(run_dir, exist_ok=True)
    pub = os.path.join(HERE, "studio", "public")
    # THE WHOLE BUILD'S CLOCK, started before the read pass — the capture
    # backstop below spends against the same ceiling the worker enforces, and
    # the read + plan phases are charged to it. Starting this at the first
    # capture would let a slow read phase (the worker's InsForge calls were
    # timing out at 10s each during run 58badcac) hand the recorder a budget
    # the build could no longer afford.
    t_build0 = time.monotonic()

    stops = plan_tour(url, run_dir, brain=brain, max_stops=5)

    # Execute planned shots. Each additional screen recording must EARN its
    # place (Dennis 2026-07-18: "each screen recording should be different") —
    # one recording per distinct PAGE; a stop on an already-filmed page (or
    # whose footage mirrors a kept clip) becomes a motion-graphic beat instead.
    #
    # COST INVARIANT (2026-07-19): NEVER PAY FOR A CAPTURE TO LEARN SOMETHING A
    # CHEAPER CHECK ALREADY KNOWS. The duplicate question is now asked at three
    # tiers, cheapest first, and a tier may only skip what the tier below it
    # would also have thrown away:
    #   FREE      plan time — graphic_only: this page is already another stop's
    #             (F14 page-once, decided while the film's shape is still
    #             arguable).
    #   ~0.04s    pre-capture — _mirrors_a_kept_page: the read pass's own
    #             photograph of this page mirrors a page we already filmed.
    #   ~90s+     post-capture — the footage itself mirrors a kept clip. STILL
    #             THE AUTHORITY, unchanged: it is the only tier that has seen
    #             the actual shot, and it decides every case the cheap tiers
    #             decline to.
    # The regression this closes: F14 made the plan name 5 distinct recordable
    # pages (correct — it used to collapse to 2), but the recorder attempted a
    # full 9s scripted glide + 60fps minterpolate on each and discovered three
    # duplicates only afterwards. insforge.dev run 58badcac spent its whole
    # 25-minute build budget on capture and was SIGKILLed before it rendered;
    # the delivered run of the same site kept the same 2 shots from 3 attempts.
    # The fix is the cost, not the ceiling — the plan is not walked back.
    import walk_shot
    filmed_pages, kept, used_motifs = [], [], set()
    # WALL-CLOCK BACKSTOP, SELF-CALIBRATING. The tiers above remove waste; this
    # bounds what is left when a site genuinely has many distinct pages on a
    # slow worker. It measures what a capture costs on THIS machine from the
    # attempts already made, and stops before the next one would breach the
    # budget — so a slow worker takes fewer shots and a fast one takes more,
    # with no per-machine constant to keep true. Budget tracks the worker's own
    # ceiling through the env it already inherits (curated-claimer spawns the
    # pipeline with `env: {...process.env}`), so the two cannot drift. The
    # clock (t_build0) starts at the top of the build, not here.
    try:
        _total_budget_s = float(os.environ.get("RENDER_TIMEOUT_MS") or 1500000) / 1000.0
    except ValueError:
        _total_budget_s = 1500.0
    try:
        _capture_frac = float(os.environ.get("WALKREC_CAPTURE_BUDGET_FRAC") or 0.55)
    except ValueError:
        _capture_frac = 0.55
    capture_budget_s = _total_budget_s * max(0.1, min(0.9, _capture_frac))
    attempt_costs = []
    for i, s in enumerate(stops):
        s["seg"] = ""
        if s.get("graphic_only"):
            # DECLARED IN THE PLAN, not discovered here (see plan_tour's
            # page-once pass). The recorder no longer spends a 9s capture to
            # learn what the planner already knew.
            s["motif"] = ""  # graphic; treatment assigned at build
            emit(run_dir, "decide.guard",
                 f"“{s['title'][:48]}”: planned as a graphic beat",
                 "Its page is already covered by another shot, so this beat "
                 "is built from your own copy instead of a second recording.")
            continue
        if s["page"] in filmed_pages:
            s["motif"] = ""  # graphic; treatment assigned at build
            emit(run_dir, "decide.guard",
                 f"“{s['title'][:48]}”: page already filmed",
                 "This stop becomes a motion graphic instead of a second recording.")
            continue
        # TIER 2 — the cheap question, asked BEFORE the expensive one.
        twin = _mirrors_a_kept_page(_still_fp(s.get("read_shot", "")), kept)
        if twin:
            s["motif"] = ""  # graphic; treatment assigned at build
            emit(run_dir, "decide.guard",
                 f"“{s['title'][:48]}”: page looks like one I've filmed",
                 f"It reads almost identically to “{twin[:48]}”, so a second "
                 "glide would retread the same screen. Skipping the recording "
                 "before filming it; this beat is built from your own copy.")
            continue
        # WALL-CLOCK BACKSTOP. Only ever applies once the film HAS footage —
        # the no-recordings refusal below stays reachable, so a slow site
        # cannot quietly become a film of nothing but graphics.
        elapsed = time.monotonic() - t_build0
        if kept and attempt_costs and elapsed + max(attempt_costs) > capture_budget_s:
            s["motif"] = ""  # graphic; treatment assigned at build
            emit(run_dir, "decide.guard",
                 f"“{s['title'][:48]}”: out of filming time",
                 f"{len(kept)} recording{'s' if len(kept) != 1 else ''} in and "
                 f"{elapsed / 60:.0f} minutes spent; another glide would not "
                 "leave room to cut and render the film. Building this beat "
                 "from your own copy instead.")
            continue
        seg = os.path.join(run_dir, f"shot-{i + 1}.mp4")
        emit(run_dir, "film.recording",
             f"Recording: {s['title'][:56]}",
             f"Gliding through {s['page']}")
        t_attempt0 = time.monotonic()
        ok = walk_shot.shot(s["page"], "" if i == 0 else s["target"], seg,
                            run_dir, duration=9.0)
        capture_err = ""
        if not ok:
            # Hosted worker: the main python has no playwright — the capture
            # venv does (same contract as capture_screenshots). Subprocess
            # walk_shot's CLI under that interpreter, CAPTURING its output:
            # the audit runs shipped films with zero recordings because every
            # failure here was silent (no event, stderr discarded).
            import capture_screenshots as _cs
            # ABSPATH, NEVER REALPATH: a venv's bin/python is a SYMLINK to
            # the base interpreter, so realpath() said "same interpreter"
            # on every Linux container and silently skipped the retry —
            # zero recordings in every hosted film. The venv-ness lives in
            # the path (pyvenv.cfg beside it), not the binary.
            if (os.path.exists(_cs.CAPTURE_PY)
                    and os.path.abspath(_cs.CAPTURE_PY)
                    != os.path.abspath(sys.executable)):
                # PROCESS-GROUP TIMEOUT: subprocess.run(capture_output=True,
                # timeout=...) deadlocks on timeout — it kills the child but
                # then blocks on the pipe, which the orphaned chromium
                # GRANDCHILD keeps open (observed: one wedged shot pinned a
                # run for 15 minutes). Kill the whole group instead.
                proc = subprocess.Popen(
                    [_cs.CAPTURE_PY, os.path.join(HERE, "walk_shot.py"),
                     s["page"], "" if i == 0 else s["target"], seg,
                     run_dir, "9.0"],
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, start_new_session=True)
                try:
                    out_txt, _ = proc.communicate(timeout=240)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                    except Exception:
                        proc.kill()
                    try:
                        out_txt, _ = proc.communicate(timeout=15)
                    except Exception:
                        out_txt = ""
                    capture_err = "capture timed out after 240s"
                ok = proc.returncode == 0 and os.path.exists(seg)
                if not ok and not capture_err:
                    capture_err = (out_txt or "").strip()[-400:]
                    print(f"[walkrec] shot retry rc={proc.returncode}: "
                          f"{capture_err}", file=sys.stderr)
            else:
                capture_err = "no capture interpreter available"
        if not ok:
            # LOUD FAILURE CONTRACT: a lost recording must be visible in the
            # thread with its reason, never silently degraded.
            emit(run_dir, "film.failed",
                 f"Recording failed: {s['title'][:56]}",
                 capture_err or "capture returned no video")
        if ok and os.path.exists(seg):
            smooth = _smooth60(seg, os.path.join(run_dir, f"shot-{i + 1}-60.mp4"))
            fp = _clip_fp(smooth)
            # TIER 3 \u2014 the authority. Unchanged: it is the only tier that has
            # seen the real footage, and it still decides every case tier 2
            # declined to (a page whose top is distinct but whose target
            # section retreads kept ground reaches here and is dropped).
            if any(_clips_similar(fp, k["clip"]) for k in kept):
                s["motif"] = ""
                emit(run_dir, "decide.guard",
                     f"\u201c{s['title'][:48]}\u201d: footage mirrors a kept clip",
                     "Dropping the duplicate recording; this beat becomes a motion graphic.")
            else:
                s["seg"] = smooth
                # The kept record carries BOTH fingerprints: the footage for
                # tier 3, and this page's still so tier 2 can answer the same
                # question about the NEXT stop without filming it.
                kept.append({"title": s["title"], "clip": fp,
                             "still": _still_fp(s.get("read_shot", ""))})
                filmed_pages.append(s["page"])
                emit(run_dir, "film.shot", f"Shot kept: {s['title'][:56]}",
                     "Smoothed to 60fps.", artifact=smooth)
        else:
            s["motif"] = ""
        # What one attempt cost on THIS machine, measured whatever the outcome
        # \u2014 a failed capture still burns the wall clock, so the backstop must
        # count it.
        attempt_costs.append(time.monotonic() - t_attempt0)
    stops = [s for s in stops if s.get("seg") or s.get("motif") is not None]
    if not any(s.get("seg") for s in stops):
        raise RuntimeError(
            "no recordings captured — refusing to ship a walkrec film with "
            "no screen footage (see the Recording failed events for causes)")

    _kept = sum(1 for s in stops if s.get("seg"))
    _say(run_dir,
         f"Footage is in — {_kept} recording{'s' if _kept != 1 else ''} kept. "
         "Now let me cut it into a film on your own palette: the graphic "
         "beats between the recordings only say what I could quote from "
         "your pages, so nothing in the cut is invented.")
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
    # `dark_world` only ever chose between two CONSTANTS — the harvested
    # `pal["ink"]` sat in the light branch unguarded, so a brand whose curated
    # palette is dark (stripe.com: fg #FFFFFF / bg #0A2540) but whose real
    # homepage is near-white got #FFFFFF ink on a #FEFDFE ground: 1.01:1.
    _card = "#191C22" if dark_world else "#FFFFFF"
    theme = {"bg": site_bg,
             "ink": _legible_ink(
                 "#F2F5F9" if dark_world else (pal.get("ink") or "#0F2338"),
                 site_bg),
             "inkMuted": _legible_ink(
                 "#9AA3B2" if dark_world else "#6B6257", site_bg, target=6.0),
             "accent": _legible_ink(pal["accent"], site_bg,
                                    min_ratio=3.0, target=3.3),
             "card": _card,
             "fontDisplay": "Manrope, sans-serif", "fontBody": "Inter, sans-serif",
             "wordmark": name}
    logo = theme_src.get("logo_src")
    logo_rel = ""
    if logo and os.path.exists(logo):
        logo_rel = f"walkrec-logo-{run_id}{os.path.splitext(logo)[1] or '.png'}"
        _stage_mark(logo, os.path.join(pub, logo_rel))
        theme["logoSrc"] = logo_rel
        # A mark is either legible on the world it lands in, or it gets the
        # plate that makes it so. '' = the world already serves it (the common
        # case), and the renderer then draws exactly what it drew before.
        plate = _logo_plate(logo, site_bg)
        if plate:
            theme["logoPlate"] = plate
    music_src = os.path.join(HERE, "assets", "music", "calm.mp3")
    if os.path.exists(music_src):
        rel = f"walkrec-music-{run_id}.mp3"
        shutil.copyfile(music_src, os.path.join(pub, rel))
        theme["music"] = rel

    ctx = {"theme": theme, "name": name, "host": host, "tagline": tagline,
           "logo_rel": logo_rel, "site_bg": site_bg, "accent": pal["accent"]}
    # TIER 2 — REVIEW THE PLAN BEFORE PAYING FOR PIXELS. Six of the eight checks
    # read stops/beats, not frames, and were complete before the render yet ran
    # after it — so a data finding bought a ~262s re-render instead of a free
    # re-plan, and the round budget spent on re-renders (REVIEWER-FINDINGS §7).
    # They run here now, looping cheaply at the plan level; the film is rendered
    # ONCE, from a plan already repaired. Only beat-visible and title-match —
    # the two that need the rendered stills — are left for the post-render pass,
    # so the 2-round budget buys what only pixels can catch.
    beats, t_f, props_path, out = _review_plan(run_id, run_dir, pub, stops, ctx)
    out, beats, film_s = _render_planned(run_dir, props_path, out, beats, t_f,
                                         stops, ctx)
    out, beats, film_s, unresolved = _review_and_fix(
        run_id, run_dir, pub, stops, ctx, beats, film_s, brain=brain)
    # The one long message the thread earns: what it is, what's in it, and
    # the invitation to change it. Composed from the film's OWN FINAL state —
    # the measured length of the cut that shipped, the stops that survived
    # review, and whatever the review could not clear. It can neither
    # describe a cut that wasn't made nor a length that wasn't rendered.
    shots = sum(1 for s in stops if s.get("seg"))
    graphics = len(stops) - shots
    _say(run_dir,
         f"Done \u2014 your {ctx['host']} film runs {film_s:.0f} seconds: a "
         f"branded open, {len(stops)} beat{'s' if len(stops) != 1 else ''} "
         f"({shots} real recording{'s' if shots != 1 else ''} gliding through "
         f"the site and {graphics} built from your own copy), and the closing "
         f"card. It closes on \u201c{stops[-1]['title']}\u201d."
         + ((f" {len(unresolved)} thing"
             + ("s" if len(unresolved) != 1 else "")
             + " I couldn't settle: "
             + "; ".join(f["issue"] for f in unresolved) + ".")
            if unresolved else "")
         + " Tell me what to change \u2014 drop a beat, swap how one is "
         "treated, or ask why I made a call \u2014 and I'll recut it.")
    return out


def _plan_beats(run_id, run_dir, pub, stops, ctx):
    """Assemble a cut into beats/elements/props WITHOUT rendering it: motif
    assignment -> world layout -> stops.json + props. The pixel-free half of
    the old _assemble_and_render, split out (Tier 2) so the reviewer can lint
    the PLAN — the six data checks over stops/beats — before a render is paid
    for. A finding here costs a free re-plan; only beat-visible and title-match,
    which need the rendered stills, are left for the post-render pass.
    Returns (beats_meta, total_frames, props_path, out_path) — no film yet."""
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
    t_f = int(OPEN_S * FPS)

    # Spatial clusters spread FAR apart (>=2400px) so no neighbor bleeds into
    # another beat's framing; camera zooms slightly on titles.
    cluster_pos = [(3600, 700), (700, 2800), (4200, 3400), (1800, 5000),
                   (6400, 4600), (900, 6600)]
    # MOTIF ASSIGNMENT (single pass): content-once dedupe in beat order, then
    # refine on what each beat will ACTUALLY show, then cut the stops the
    # ladder could only answer with decoration.
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
    # VARIETY NEVER OUTRANKS CONTENT: the rule here used to flip the weakest
    # data beat to a line-art drawing whenever >=4 graphic beats carried none,
    # for film-wide variety. A drawing shows nothing of the site, so the flip
    # HID real harvested content behind decoration — the same defect the
    # bottom rung below cuts. Variety is carried by the layout cycle instead
    # (stacked / split-left / split-right, plus the camera); a beat's
    # treatment now always follows its material.
    #
    # BOTTOM RUNG OF THE DEGRADE LADDER: every other rung only SWAPS a
    # treatment, so a stop with nothing behind it always landed somewhere
    # rather than nowhere — 8.4s of a title beside a decorative wireframe
    # globe ("Customer Stories", insforge.dev 2026-07-19: a 638-char page
    # whose footage was correctly dropped as a duplicate, leaving the beat
    # with no content and no film). A stop with neither kept footage nor
    # anything showable is CUT and the film runs one beat shorter.
    cut = [s for s in gstops if s.get("motif") == _CUT]
    for s in cut:
        emit(run_dir, "decide.guard",
             f"“{s['title'][:48]}”: nothing to show",
             "No footage and nothing quotable behind this stop — cutting the "
             "beat rather than filling it with decoration.")
    if cut:
        stops[:] = [s for s in stops if s.get("motif") != _CUT]
        gstops = [s for s in stops if not s.get("seg")]
    # STABILITY INVARIANT: treatments are decided ONCE, at first assembly.
    # Re-renders (reviewer swaps, director edits) must never re-roll the
    # other beats — unlocked motifs re-rolled every round, so the film the
    # user saw, stops.json, and the director's summary could all disagree
    # about which beat carried which treatment (the F7 wrong-beat drop).
    for s in gstops:
        s["motif_locked"] = True
    emit(run_dir, "decide.treatments", "Treatments assigned",
         "\n".join(f"\u201c{s['title'][:44]}\u201d \u2192 "
                    f"{'recording' if s.get('seg') else s['motif']}"
                    for s in stops))

    # FORM FIRST, THEN TIME: a beat cannot be sized until we know what plays
    # after it (see _beat_forms / _lead_after), so the layout decision is made
    # for the whole film up front and consumed here.
    forms = _beat_forms(stops)
    for i, s in enumerate(stops):
        cx, cy = cluster_pos[i % len(cluster_pos)]
        form = forms[i]
        lead_next = _lead_after(forms, i)
        motif = s.get("motif", "card")
        logos = _stop_logos(s) if motif == "logo-wall" else []
        lines = _beat_lines(s, motif)
        if form == "center":
            # CONTRACT: a title text renders as a beat at most once per film —
            # a graphic stop whose title an earlier beat already carries plays
            # title-less at its cluster center (the vignette IS the content).
            elements.append({"id": f"g{i}", "kind": "graphic", "x": cx, "y": cy,
                             "at": t_f + 12, "motif": motif, "text": s["title"],
                             "lines": lines,
                             "chips": s.get("chips") or [], "logos": logos})
            moments.append({"at": t_f, "x": cx, "y": cy + 10, "scale": 1.12})
            beats.append({"i": i, "title": s["title"], "treatment": motif,
                          "layout": "center", "at": t_f})
            beat_s = {"chip-sweep": 5.5, "stat-pop": 4.0, "kinetic-line": 3.5,
                      "logo-wall": 5.0, "people-wall": 5.0}.get(motif, 5.5)
            t_f += _dwell_frames(beat_s, lead_next)
            continue
        if form == "kinetic":
            # The kinetic line IS the title — one beat, no duplicate headline.
            elements.append({"id": f"g{i}", "kind": "graphic", "x": cx, "y": cy,
                             "at": t_f + 12, "motif": "kinetic-line",
                             "text": s["title"]})
            moments.append({"at": t_f, "x": cx, "y": cy + 10, "scale": 1.12})
            beats.append({"i": i, "title": s["title"],
                          "treatment": "kinetic-line", "layout": "center",
                          "at": t_f})
            t_f += _dwell_frames(3.5, lead_next)
            continue
        if form in ("split-left", "split-right"):
            # SPLIT beat: title and vignette side by side, ONE framing —
            # a different rhythm and geometry from stacked beats
            # (variability contract + Dennis's split-layout preference).
            sign = -1 if form == "split-left" else 1
            elements.append({"id": f"t{i}", "kind": "headline",
                             "x": cx + sign * -390, "y": cy, "w": 560,
                             "at": t_f + 12, "text": s["title"], "size": 60,
                             "align": "left",
                             "accentWord": max(s["title"].split(), key=len).strip(".,"),
                             "dir": "left" if sign < 0 else "right"})
            elements.append({"id": f"g{i}", "kind": "graphic",
                             "x": cx + sign * 330, "y": cy, "at": t_f + 20,
                             "motif": motif, "text": s["title"],
                             "lines": lines,
                             "chips": s.get("chips") or [],
                             "quotes": s.get("quotes") or [],
                             "logos": logos, "narrow": True})
            moments.append({"at": t_f, "x": cx, "y": cy + 10, "scale": 1.05})
            beats.append({"i": i, "title": s["title"], "treatment": motif,
                          "layout": form, "at": t_f})
            beat_s = {"chip-sweep": 6.0, "stat-pop": 4.5, "logo-wall": 5.5,
                      "quote-card": 5.5, "people-wall": 5.5}.get(motif, 6.0)
            t_f += _dwell_frames(beat_s, lead_next)
            continue
        # Title beat — the site's own words, section-title sized (stacked).
        elements.append({"id": f"t{i}", "kind": "headline", "x": cx, "y": cy - 340,
                         "w": 1180, "at": t_f + 14, "text": s["title"], "size": 72,
                         "accentWord": max(s["title"].split(), key=len).strip(".,"),
                         "dir": "bottom"})
        moments.append({"at": t_f, "x": cx, "y": cy - 320, "scale": 1.12})
        t_f += int(TITLE_LEAD_S * FPS)
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
            t_f += _dwell_frames(min(seg_dur, 7.0), lead_next)
        else:
            # Motion-graphic beat — a concept vignette that ENACTS the title
            # instead of a redundant recording.
            elements.append({"id": f"g{i}", "kind": "graphic", "x": cx,
                             "y": cy + 300, "at": t_f + 12,
                             "motif": motif, "text": s["title"],
                             "lines": lines,
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
            t_f += _dwell_frames(beat_s, lead_next)

    elements.append({"id": "cta", "kind": "cta", "x": 6200, "y": 1800,
                     "at": t_f + 16, "text": "See it live", "label": host,
                     "value": "Get started", "logoSrc": logo_rel or None, "dir": "bottom"})
    moments.append({"at": t_f, "x": 6200, "y": 1810, "scale": 0.98})
    t_f += int(CTA_S * FPS)

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
    return beats, t_f, props_path, out


def _render_planned(run_dir, props_path, out, beats, t_f, stops, ctx):
    """Render an already-planned cut and read its truths off the artifact.

    The pixel-free half (_plan_beats) is done; this is the ~262s render half,
    split out so the Tier-2 build path can render EXACTLY ONCE, after the data
    lints have reviewed and repaired the plan. Measures the length off the
    rendered file (never estimated) and extracts one design still per beat at
    beat_start + 84f for the post-render pixel checks.
    Returns (film, beats_meta, film_seconds)."""
    site_bg = ctx["site_bg"]
    run_dir = os.path.abspath(run_dir)
    emit(run_dir, "assemble.render",
         f"Rendering the film — {t_f / FPS:.1f}s, {len(stops)} beats",
         f"Plus the branded open and the closing card. "
         f"World palette {site_bg}, accent {ctx['accent']}.")
    subprocess.run(["npx", "remotion", "render", "WalkrecWorld", out,
                    f"--props={props_path}", "--log=error",
                    # FIT THE BOX: default concurrency decodes several
                    # 1080p60 clips at once and the compositor gets
                    # OOM-SIGKILLed on the worker (observed the first run
                    # that carried real footage). One frame lane + a
                    # 300MB video cache keeps peak memory inside the box.
                    "--concurrency=1",
                    "--offthreadvideo-cache-size-in-bytes=314572800"],
                   cwd=os.path.join(HERE, "studio"), check=True, timeout=1800)
    # MEASURED, NEVER ESTIMATED (F7): every number the customer reads about
    # this film is authored from the RENDERED ARTIFACT, here, once. The
    # handover line used to be reconstructed from the plan (last beat + 5s)
    # and told the customer "about 48 seconds" for a 53.2s film (insforge.dev
    # 2026-07-19) \u2014 three different lengths in one thread.
    film_s = _film_seconds(out, t_f / FPS)
    emit(run_dir, "assemble.film", "Film rendered", f"{film_s:.1f}s",
         artifact=out)
    _say(run_dir,
         f"The film is printed \u2014 {film_s:.0f} seconds: a branded open, "
         f"{len(beats)} beat{'s' if len(beats) != 1 else ''}, and the closing "
         "card. Before I hand it over, let me watch it back the way a viewer "
         "would: does every title match what's under it, does anything "
         "repeat, does it end well?")
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
    print(f"[walkrec] tour film: {out} ({film_s:.1f}s measured, "
          f"{len(stops)} planned shots, bg {site_bg})")
    return out, beats, film_s


def _assemble_and_render(run_id, run_dir, pub, stops, ctx):
    """Plan a cut and render it in one call — (film, beats_meta, film_seconds).
    The director's re-render path and the post-render pixel recut both need a
    plan AND a film, so this composes _plan_beats + _render_planned for them.
    The Tier-2 build path instead calls the two separately, with the plan-stage
    review in between, so a data finding costs a re-plan rather than a
    re-render."""
    beats, t_f, props_path, out = _plan_beats(run_id, run_dir, pub, stops, ctx)
    return _render_planned(run_dir, props_path, out, beats, t_f, stops, ctx)


# ---- THE REVIEW CONTRACT --------------------------------------------------
# A gate that cannot fail is not a gate, and a pass may only assert what was
# actually evaluated. Both halves failed together on insforge.dev 2026-07-19:
# "Watched it back and it holds — every title matches what's under it and
# nothing repeats" was emitted over a cut carrying a green-ticked "Test
# Failed" and an 8.4s empty Customer Stories beat. No check had looked at
# either property, and no outcome of the review could have stopped the film.
#
#   1. NAMED CHECKS. Every property the reviewer claims is a check below, with
#      a verdict over the CURRENT cut. The pass sentence is composed from the
#      claims of the checks that ran and passed — a property no check covers
#      cannot appear in it.
#   2. A CHECK THAT DID NOT RUN IS NOT A PASS. The stills critic needs a
#      model; when it is unavailable its silence used to be indistinguishable
#      from approval. It now reports that it could not look, and the film
#      narrows its claim instead of inheriting the silence.
#   3. THE GATE CAN FAIL. Findings are re-checked against the RE-CUT rather
#      than assumed fixed. Anything still standing is a rejection: honesty
#      failures (a beat with nothing to show, a green check on a non-benefit)
#      REFUSE DELIVERY; the rest are disclosed in the handover, and the film
#      never describes itself as clean.
#
# name            claim the film may make when the check passes        blocking
_CHECKS = (
    ("beat-content", "every beat carries something real from your pages", True),
    # beat-visible STAYS NON-blocking — decided on the full corpus, not left
    # open (2026-07-20, n=102 text beats across 24 films; see _INK_FLOOR).
    # When this check fires it is wrong 2 times in 3: the sub-floor population
    # was 3 beats, of which 2 settle healthy (4.54->8.35, 4.59->8.04) and 1 is
    # genuinely blank (4.66 at every sample point). The blank one sits BETWEEN
    # the two false positives at the sample offset, so no floor value can
    # separate blank from dim here — and moving the still later trades 2 false
    # positives for up to 13 new ones (the beat-end region reads the exit fade
    # on 13/102 beats). All three sub-floor beats are context-cards on a light
    # world; the fix for that class is upstream contrast, not this gate.
    # Non-blocking already cuts a genuinely blank beat in round 1 via its _CUT
    # fix; blocking would only add refuse-delivery on an alarm with 1-in-3
    # precision. Revisit only if the still-sampling itself changes.
    ("beat-visible", "every beat is actually legible on screen", False),
    ("ticked-items", "nothing wears a green check that isn't a benefit", True),
    ("treatment-fit", "each treatment has the material it needs", False),
    ("no-repeat-run", "no two beats in a row share a treatment", False),
    ("no-redundancy", "no two beats make the same point twice", False),
    ("pacing", "no beat runs past nine seconds", False),
    ("title-match", "every title matches what's under it and the film "
                    "doesn't repeat itself", False),
)
# The check the STILLS CRITIC owns — the only one that needs a model, and so
# the only one that can fail to run at all.
_CRITIC_CHECK = "title-match"

_REVIEW_ROUNDS = 2   # the first cut plus ONE re-cut; a re-render is ~4 minutes


def _finding(beat, what: str, issue: str, fix: str = None) -> dict:
    """One reviewer finding. `beat` is the stop index (None for the parts of
    the film that are not beats, e.g. the opening card); `fix` is a treatment
    the reviewer may swap to, or None when nothing automatic will help."""
    return {"beat": beat, "what": what, "issue": issue, "fix": fix}


def _finding_title(f: dict) -> str:
    head = f"Beat {f['beat'] + 1}" if f["beat"] is not None else f["what"]
    return f"{head}: {f['issue']}"


# Calibrated 2026-07-20 against runs/walkrec-palmier-live/beat-{0..5}.jpg (six
# real beats: std 10.1 / 12.2 / 13.0 / 14.0 / 16.0 / 39.8) and two synthetic
# controls — a flat #FAFAFA field reads 0.00, and a #FBFBFB block on white (the
# white-on-white failure itself) reads 1.02. The populations are a factor of ten
# apart; the floor sits between them, biased LOW so a marginal beat passes.
#
# RE-CALIBRATED 2026-07-20 (daylight) on the full corpus: 102 text beats across
# 24 films, sampled at the production offset (beat start + 84f = 2.8s) AND at
# beat end. The offset sample sits on the settled plateau for ~99% of beats
# (entrances finish by ~2.0s), so the "mid-entrance sample" worry is real but
# rare; median offset std 13.9, dark-world minimum 10.1. What the floor cannot
# do is separate BLANK from DIM: every sub-floor reading (3/102) is a
# context-cards beat on a light world, where the settled plateau itself is only
# ~8 — the genuinely blank one (4.66) reads between the two that settle healthy
# (4.54, 4.59). Hence beat-visible stays non-blocking (see _CHECKS) and the
# floor stays at 6.0: raising it starts eating request-table/chip-sweep on
# light worlds (6.6-7.8), lowering it passes the one true blank.
_INK_FLOOR = 6.0
_MIN_BEATS_AFTER_CUT = 3


def _cut_allowed(stops, i, pending) -> bool:
    """May beat `i` be cut, given the cuts already proposed this round? A lint
    that cuts past these floors has replaced one dishonest film with an empty
    one: a film needs beats, and a tour needs at least one real recording.

    `pending` is ONE set per review round, shared by every lint that can
    propose _CUT — capacity is a property of the FILM, so per-lint sets let
    two honest lints jointly cut past the floor (and treatment-fit, with no
    consult at all, took a 4-beat cut to 1 on 2026-07-20). _apply_fixes
    re-checks the same floors over the round's whole cut set, so nothing
    that skips this consult can pop past them either."""
    remaining = [j for j in range(len(stops)) if j != i and j not in pending]
    if len(remaining) < _MIN_BEATS_AFTER_CUT:
        return False
    if stops[i].get("seg") and not any(stops[j].get("seg") for j in remaining):
        return False
    return True


def _frame_ink(still: str):
    """How much VISIBLE structure a beat's still carries: the spread of the same
    16x16 grayscale fingerprint the duplicate guard already takes (_still_fp —
    ffmpeg, ~0.04s, no browser, no network, no decode). A frame whose ink never
    varies is a frame with nothing on it, whatever the plan says is there.
    Returns None when the still is missing: a check that could not look must not
    be counted as one that looked and approved."""
    fp = _still_fp(still)
    if not fp:
        return None
    b = fp[0]
    mean = sum(b) / 256.0
    return (sum((x - mean) ** 2 for x in b) / 256.0) ** 0.5


def _lint_blank(stops, beats, pending=None):
    """BEAT-VISIBLE: the pixel half of beat-content, measured on the RENDERED
    artifact so it cannot be satisfied by intent. Every other data check reads
    the plan, so a beat whose material renders white-on-white — or whose ticked
    rows render without their labels — satisfies all of them and is blank to the
    viewer (stripe.com 2026-07-20: three of five beats, certified as holding).

    This is a BACKSTOP. Ink is chosen at assembly and a contrast floor belongs
    there, where the failure is impossible rather than detected. What this adds
    is the causes a contrast rule cannot know about: a missing asset, an element
    sized to nothing, an entrance that never ran, a font that never loaded.

    Returns (ran, findings) — `ran` only when a still was read for EVERY beat."""
    out, looked = [], 0
    pending = set() if pending is None else pending
    for b in beats:
        ink = _frame_ink(b.get("still") or "")
        if ink is None:
            continue
        looked += 1
        if ink >= _INK_FLOOR:
            continue
        fix = _CUT if _cut_allowed(stops, b["i"], pending) else None
        if fix:
            pending.add(b["i"])
        out.append(_finding(b["i"], b.get("title", ""),
                            f"renders blank to a viewer (ink {ink:.1f}, "
                            f"floor {_INK_FLOOR:.0f})", fix))
    return (bool(beats) and looked == len(beats)), out


def _lint_content(stops):
    """BEAT-CONTENT: a beat with neither kept footage nor anything its
    treatment can show. Reads the same _shown_material the ladder used to
    pick the treatment, so the film and the review cannot disagree about
    what "has content" means."""
    out = []
    for i, s in enumerate(stops):
        if s.get("seg"):
            continue
        motif = s.get("motif") or ""
        if not _shown_material(s, motif):
            out.append(_finding(i, s.get("title", ""),
                                f"nothing behind this beat for a "
                                f"{motif or 'graphic'} to show"))
    return out


def _lint_ticks(stops):
    """TICKED-ITEMS: a treatment that puts green checks on its rows may only
    carry rows that earned one (see _is_benefit_shaped). Enforced upstream by
    _beat_lines; checked here because a green check on a failure state is a
    claim the film makes on the customer's behalf."""
    out = []
    for i, s in enumerate(stops):
        motif = s.get("motif") or ""
        if s.get("seg") or motif not in _TICKED_MOTIFS:
            continue
        bad = [d for d in (s.get("details") or []) if not _is_benefit_shaped(d)]
        shown = _beat_lines(s, motif)
        for d in bad:
            if d in shown:
                out.append(_finding(i, s.get("title", ""),
                                    f"“{d[:40]}” is ticked as a benefit"))
    return out


def _lint_treatment_fit(stops, pending=None):
    """TREATMENT-FIT: each treatment's material floor, re-checked on the final
    beat plan. Floors count only material the treatment will actually SHOW —
    a check-list's floor counts tickable rows, not raw harvested lines."""
    findings = []
    pending = set() if pending is None else pending
    for i, s in enumerate(stops):
        if s.get("seg"):
            continue
        motif = s.get("motif", "")
        details = s.get("details") or []
        ticks = _tickable(details)
        # A FALLBACK MAY NOT BE A TREATMENT THAT SHOWS NOTHING. "card" (line
        # art) was the old floor here; swapping to it and LOCKING it produced
        # a beat the ladder could no longer rescue and beat-content then had
        # to reject. With no material for any treatment, the honest fix is
        # the ladder's own bottom rung — cut the beat.
        # A fixed default is how a vocabulary repair became a repetition. Ask
        # for check-list, but land on whatever unspent treatment holds here.
        fallback = _pick_repair(stops, i, "check-list" if len(ticks) >= 2
                                else "")
        issues = []
        if motif == "chip-sweep" and len(s.get("chips") or []) < 6:
            issues.append(("chip-sweep below material floor", fallback))
        if motif == "quote-card" and not s.get("quotes"):
            issues.append(("quote-card without a harvested quote",
                           "people-wall" if sum(1 for d in details
                                                if "@" in d) >= 2
                           else fallback))
        if motif == "logo-wall" and sum(
                1 for e in (s.get("entities") or []) if e) < 4:
            issues.append(("logo wall below 4 partners", fallback))
        if motif in _TICKED_MOTIFS and len(ticks) < 2 and motif != "price-card":
            issues.append(("check-list below two real benefits", fallback))
        # THE BOTTOM RUNG IS STILL A CUT, so it consults the floors like
        # every other lint's cut (same shared `pending` — see _cut_allowed).
        # Unguarded, three starved beats in one round took a 4-beat film to
        # a single beat (2026-07-20). A refused cut degrades to fix=None:
        # the finding ships as a disclosure instead of shrinking the film.
        if any(fix == _CUT for _, fix in issues):
            if _cut_allowed(stops, i, pending):
                pending.add(i)
            else:
                issues = [(issue, None if fix == _CUT else fix)
                          for issue, fix in issues]
        for issue, fix in issues:
            findings.append(_finding(i, s.get("title", ""), issue, fix))
    return findings


_STOPWORDS = frozenset(
    "a an and are as at be built by for from get how in into is it its let of "
    "on or our that the their they this to up us we with you your".split())


def _title_words(t: str):
    """A title's meaningful words, in order, for the redundancy comparison.
    Stopwords out so two titles are compared on what they CLAIM rather than on
    the scaffolding they share with every other line of marketing copy."""
    return [w for w in re.findall(r"[a-z0-9]+", (t or "").lower())
            if w not in _STOPWORDS and len(w) > 2]


def _lint_redundancy(stops, pending=None):
    """NO-REDUNDANCY: two beats making one point, in one visual form.

    The critic sees these and says so — "Beat 2: Near-duplicate of beat 0's
    title/promise, redundant hero beat" (stripe.com 2026-07-20) — but its menu
    is per-beat while redundancy is a property of a PAIR, so it reaches for
    `none`, the finding carries no fix, and the film opens with two beats
    making one point. Decided here instead, where a fix can be attached.

    Narrow on purpose. A pair counts only when both beats wear the SAME
    treatment (the thing that makes them read as one long beat) and either
    close on the same claim or are near-identical throughout. The LATER beat
    goes and the film runs one beat shorter — a shorter honest film beats a
    padded one, and dropping a beat cannot invent copy."""
    out = []
    pending = set() if pending is None else pending
    seen = []
    for i, s in enumerate(stops):
        motif = "recording" if s.get("seg") else (s.get("motif") or "")
        words = _title_words(s.get("title", ""))
        if not words:
            seen.append((i, motif, words))
            continue
        for j, jmotif, jwords in seen:
            if jmotif != motif or not jwords:
                continue
            # SAME CLOSING CLAIM: two titles ending on the same two content
            # words promise the same thing, however differently they open.
            tail = words[-2:] == jwords[-2:] and len(words) >= 2
            a, b = set(words), set(jwords)
            near = len(a & b) / max(len(a | b), 1) >= 0.6
            if not (tail or near):
                continue
            fix = _CUT if _cut_allowed(stops, i, pending) else None
            if fix:
                pending.add(i)
            out.append(_finding(
                i, s.get("title", ""),
                f"says what beat {j + 1} already said, in the same "
                f"treatment ({motif})", fix))
            break
        seen.append((i, motif, words))
    return out


def _lint_repeats(stops):
    """NO-REPEAT-RUN: two neighbouring beats wearing the same treatment read
    as one long beat.

    Recordings are NOT exempt. They used to be, so a film could open on two
    consecutive screen recordings while this check passed and the handover then
    claimed "no two beats in a row share a treatment" (stripe.com 2026-07-20,
    beats 1 and 2). A check may not claim more than it tests. There is no
    automatic fix — a recording cannot be swapped to another treatment and
    dropping one is the director's call — so this reaches the customer as a
    disclosure, which is exactly why P5 had to stop reporting only the first."""
    findings, prev = [], None
    for i, s in enumerate(stops):
        motif = "recording" if s.get("seg") else s.get("motif", "")
        if motif and motif == prev:
            findings.append(_finding(i, s.get("title", ""),
                                     f"adjacent repeated treatment ({motif})"))
        prev = motif
    return findings


# ---- THE VARIETY TIE-BREAK ------------------------------------------------
# Treatment is a FILM-WIDE property that was being decided one beat at a time.
# A repair that reads only its own beat re-spends a form the film has already
# worn: stripe.com 2026-07-20 swapped a beat to stat-pop while another stat-pop
# stood two beats along, and the vocabulary violation it was "fixing" was not
# real (see _SWAP_TARGETS). Half of all swap repairs in the run history created
# a duplicate this way.
#
# THIS IS A TIE-BREAK AND NOTHING MORE. Every candidate below has ALREADY
# cleared its own material floor, so variety still never outranks content — the
# rule deleted at the top of the assembly ("a beat's treatment now always
# follows its material") stays deleted. All this does is stop two beats
# spending the same form when a second form fits the same material equally
# well, and degrade to the LEAST-USED option instead of a fixed default.


def _assigned_motifs(stops, skip=None):
    """What the film has already spent, counted by treatment. `skip` is the stop
    being repaired — its own current treatment is not competition for itself."""
    used = {}
    for i, s in enumerate(stops):
        if i == skip or s.get("seg"):
            continue
        m = s.get("motif") or ""
        if m:
            used[m] = used.get(m, 0) + 1
    return used


def _pick_repair(stops, bi, preferred, menu=None):
    """The treatment a repair should actually land on.

    Order: the requested target when it holds AND the film has not spent it;
    otherwise the LEAST-USED candidate that clears its own material floor on
    this beat; otherwise _CUT. Never returns the treatment the beat already
    carries (a no-op that still costs a full re-render), and never returns one
    an immediate neighbour is wearing.

    Callers decide what _CUT means for them — the lint takes it as its fix, the
    critic and the director take it as "reject this swap"."""
    s = stops[bi]
    used = _assigned_motifs(stops, skip=bi)
    current = s.get("motif") or ""
    neighbours = {stops[j].get("motif") for j in (bi - 1, bi + 1)
                  if 0 <= j < len(stops) and not stops[j].get("seg")}
    order = tuple(menu or _SWAP_TARGETS)

    def holds(m):
        return (bool(m) and m != current and m not in neighbours
                and _refine_motif(m, s, set(used)) == m)

    if preferred and preferred not in used and holds(preferred):
        return preferred
    cands = [m for m in order if holds(m)]
    if cands:
        return min(cands, key=lambda m: (used.get(m, 0), order.index(m)))
    # Nothing unspent fits. CONTENT WINS: take the requested target even though
    # it repeats, rather than cut a beat that has real material to show.
    if preferred and holds(preferred):
        return preferred
    return _CUT


_CRITIC_MENU = ("none", "drop", "swap_treatment")
# THE MENU IS THE VOCABULARY. The prompt shows this tuple to the critic as the
# set of legal treatments, so anything assignable that is missing from it reads
# to the critic as a violation to be repaired: price-card is a first-class
# treatment with its own keywords, floor exemption and renderer branch, and the
# critic reported it as "not in allowed vocabulary" and swapped a correct beat
# away from it (stripe.com 2026-07-20). Ordered least-generic first — the
# variety tie-break uses this order to break ties between equally-unused
# candidates, so the specific vignettes should come before the line art.
_SWAP_TARGETS = ("request-table", "context-cards", "chat-exchange",
                 "price-card", "quote-card", "people-wall", "logo-wall",
                 "chip-sweep", "stat-pop", "check-list", "kinetic-line",
                 "house", "chat", "globe", "card", "tag")


def _critic_review(run_dir, stops, beats, brain="sonnet5"):
    """LLM critic with a CLOSED action menu. Sees the beat stills + the plan;
    may only drop a beat or swap its treatment — it can never write content,
    so every honesty gate survives review.

    Returns (ran, actions, objections). `ran` is the honest part: this is the
    only check that needs a model, and a model that never answered used to be
    indistinguishable from one that found nothing — the film then claimed
    every title matched what was under it on the strength of an exception
    swallowed three frames down. `ran` is True only when the reply covered
    EVERY beat, so the claim is backed by a look at each one."""
    import base64
    try:
        import validate_planner as vp
    except Exception:
        return False, [], []
    # ONE BLOCK PER BEAT, image immediately under its own label. The stills used
    # to be appended as an anonymous tail after a single text block listing every
    # beat, so image-to-beat correspondence was positional and implicit \u2014 and the
    # ffmpeg extraction that produces them runs check=False, so one missing still
    # silently shifted every later image against the wrong beat.
    plan_lines = []
    content = []
    shown = 0
    for b in beats:
        s = stops[b["i"]] if b["i"] < len(stops) else {}
        # NO ANSWER KEY. `material=[...]` handed the model the intended content
        # as text beside the frame, so a beat whose copy rendered white-on-white
        # still "matched its title" \u2014 the model reconciled toward the legible
        # input, which was the plan (stripe.com 2026-07-20). The title is the
        # claim under test; what the beat shows must come from the image.
        line = (f"beat {b['i']}: title=\u201c{b['title']}\u201d "
                f"treatment={b['treatment']} layout={b['layout']}")
        plan_lines.append(line)
        still = b.get("still")
        if still and os.path.exists(still):
            with open(still, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
            content.append({"type": "text", "text": f"--- {line}"})
            content.append({"type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})
            shown += 1
    sys_prompt = (
        "You review a product launch film. Each beat below is followed by a "
        "still from the RENDERED film. Judge the IMAGE, not the description. "
        "FIRST, for each still: can you actually read every word of text in "
        "it? Text the same colour as its background, text clipped by its box, "
        "a list whose rows have no labels, or a frame that is essentially "
        "empty is a FAILED beat however good the plan behind it was — say so "
        "and mark it an issue. THEN judge story: does the title match what "
        "the image shows, is any beat redundant with another, does the "
        "sequence flow? You may ONLY act via this menu per beat: none | drop "
        "| swap_treatment (to one of: "
        + ", ".join(_SWAP_TARGETS) + "). You cannot write copy. Return STRICT "
        'JSON: [{"beat": <index>, "verdict": "ok"|"issue", "issue": "<short '
        'reason>", "action": "none"|"drop"|"swap_treatment", "to": "<target '
        'or empty>"}] — one object per beat, no prose.')
    user_content = ([{"type": "text", "text": "\n".join(plan_lines)}] + content
                    if content else "\n".join(plan_lines))
    looked = shown == len(beats) and bool(beats)
    try:
        raw = vp.call_model([{"role": "system", "content": sys_prompt},
                             {"role": "user", "content": user_content}],
                            brain=brain) or ""
    except (Exception, SystemExit):
        try:
            # TEXT-ONLY RETRY. This path has not seen the film, and a check that
            # ran blind must not license the words "Watched it back" — rule 2
            # one level deeper: the call succeeded, the LOOK did not.
            looked = False
            raw = vp.call_model([{"role": "system", "content": sys_prompt},
                                 {"role": "user",
                                  "content": "\n".join(plan_lines)}],
                                brain=brain) or ""
        except (Exception, SystemExit):
            return False, [], []
    cand = _extract_json_list(raw) or []
    actions, objections, seen, drops = [], [], set(), 0
    for c in cand:
        try:
            bi = int(c.get("beat", -1))
        except Exception:
            continue
        act = str(c.get("action") or "none")
        if bi < 0 or bi >= len(stops) or act not in _CRITIC_MENU:
            continue
        seen.add(bi)
        short = (lambda t: t[:117] + "…" if len(t) > 120 else t)(
            str(c.get("issue") or ""))
        # AN OBJECTION IS A FINDING even when the critic asks for nothing.
        # Verdicts whose action was "none" used to be discarded, so a beat the
        # reviewer had flagged as wrong vanished between seeing it and
        # reporting it — and the film shipped described as holding.
        if str(c.get("verdict") or "") == "issue":
            objections.append(_finding(bi, stops[bi].get("title", ""),
                                       short or "the reviewer flagged this beat"))
        if act == "drop":
            if drops >= 2 or stops[bi].get("seg"):
                continue  # never drop recordings; max 2 drops
            drops += 1
        if act == "swap_treatment":
            to = str(c.get("to") or "")
            if to not in _SWAP_TARGETS or stops[bi].get("seg"):
                continue
            # The floor AND the film's other beats. Passing set() here read the
            # target's material while ignoring what the rest of the cut had
            # already spent, so a legal swap could still collide.
            to = _pick_repair(stops, bi, to)
            if to == _CUT:
                continue  # nothing holds on this beat; leave it alone
            c = dict(c, to=to)
        if act != "none":
            actions.append({"beat": bi, "action": act,
                            "to": str(c.get("to") or ""), "issue": short})
    # COVERAGE, NOT PRESENCE: a reply about four of six beats has not
    # evaluated "every title matches what's under it" — and neither has a
    # reply that covered every beat without seeing any of them.
    ran = bool(beats) and all(b["i"] in seen for b in beats) and looked
    return ran, actions, objections


def _data_results(stops, beats, film_s, pending=None):
    """The six DATA lints — pure code over stops/beats, no frames, no model.
    All of them are complete before any render exists, which is why the
    plan-stage review (Tier 2) can run them for free; the post-render pass
    runs the same table again so every claim in the handover is a verdict
    over the FINAL cut, not a memory of the plan that preceded it.

    `pending` is the round's shared cut budget (see _cut_allowed) — every
    lint below that can propose _CUT draws from the same set."""
    pending = set() if pending is None else pending
    return {
        "beat-content": (True, _lint_content(stops)),
        "ticked-items": (True, _lint_ticks(stops)),
        "treatment-fit": (True, _lint_treatment_fit(stops, pending)),
        "no-repeat-run": (True, _lint_repeats(stops)),
        "no-redundancy": (True, _lint_redundancy(stops, pending)),
        "pacing": (True, _lint_pacing(beats, film_s)),
    }


def _checks_from(results):
    """Order lint results into the reviewer's check records, in _CHECKS order.
    Covers only the checks present in `results` — the plan-stage pass has no
    pixel results and must not fabricate rows for checks that did not run."""
    return [{"name": name, "claim": claim, "blocking": blocking,
             "ran": results[name][0], "findings": results[name][1]}
            for name, claim, blocking in _CHECKS if name in results]


def _run_checks(run_dir, stops, beats, film_s, brain="sonnet5"):
    """Every named check, run over the CURRENT rendered cut. Returns
    (checks, actions) where each check is {name, claim, blocking, ran,
    findings}. The reviewer may say nothing this list does not support."""
    critic_ran, actions, objections = _critic_review(run_dir, stops, beats,
                                                     brain=brain)
    # NO-OP GUARD: a swap to the treatment the beat already carries changes
    # nothing but still triggers a full ~4-minute re-render (observed: the
    # critic asked stat-pop -> stat-pop). Filter before deciding to apply.
    actions = [a for a in actions
               if not (a["action"] == "swap_treatment"
                       and a["beat"] < len(stops)
                       and stops[a["beat"]].get("motif") == a["to"])]
    pending = set()
    blank_ran, blank_findings = _lint_blank(stops, beats, pending)
    results = _data_results(stops, beats, film_s, pending)
    results["beat-visible"] = (blank_ran, blank_findings)
    results[_CRITIC_CHECK] = (critic_ran, objections if critic_ran else [])
    return _checks_from(results), actions


def _review_claim(checks) -> str:
    """The sentence the film is allowed to say about itself: the claims of the
    checks that RAN and PASSED, plus an explicit note for any that could not
    run. Composed, never authored — a property no check covers cannot appear
    in it, which is the entire point of the list."""
    held = [c["claim"] for c in checks if c["ran"] and not c["findings"]]
    missed = [c for c in checks if not c["ran"]]
    # Only the stills critic actually LOOKS at the film; the rest read the
    # cut's structure. The verb has to match which of those happened.
    looked = any(c["ran"] for c in checks if c["name"] == _CRITIC_CHECK)
    # "it holds" is a verdict on the WHOLE cut and is forfeited the moment any
    # check has a finding, however many others passed.
    holds = "" if any(c["findings"] for c in checks) else " and it holds"
    if held:
        body = (("Watched it back" if looked else "Checked the cut over")
                + holds + " — " + held[0]
                + ("".join(", " + h for h in held[1:-1]) if len(held) > 2 else "")
                + (", and " + held[-1] if len(held) > 1 else "") + ".")
    else:
        body = "Watched it back."
    if missed:
        body += (" I couldn't run the frame-by-frame look this time, so I'm "
                 "not claiming " + missed[0]["claim"] + " — only what I "
                 "could check on the cut itself.")
    return body


def _apply_fixes(stops, lint_fixes, actions):
    """Apply a round's repairs to `stops`, in place — swaps first, drops last
    (descending, so indices stay true). ONE apply semantics for both review
    passes: the plan-stage loop and the post-render recut repair a cut the
    same way or their films drift apart.

    A fix of _CUT is the ladder's bottom rung reached from review: there is
    no treatment left for this beat, so it leaves the film with the critic's
    drops rather than being locked to a drawing.

    THE FLOORS BIND HERE, over the round's whole cut set at once. Each lint
    consults _cut_allowed as it proposes, but this is the only function that
    pops beats, so it is the one place no cut source — a lint fix, a critic
    drop, a lint yet to be written — can shrink the film past the floors
    (treatment-fit proposed unguarded and a 4-beat cut fell to 1 beat,
    2026-07-20). Lint cuts are granted first: they are honesty repairs the
    floors already vetted, so the critic's drops compete for what remains.
    A refused lint cut degrades in place to fix=None — the disclosure the
    caller reports — and a refused drop is simply not taken."""
    pending, refused = set(), set()
    for f in lint_fixes:
        if f["fix"] != _CUT or f["beat"] in pending:
            continue
        if (f["beat"] not in refused
                and _cut_allowed(stops, f["beat"], pending)):
            pending.add(f["beat"])
        else:
            refused.add(f["beat"])
            f["fix"] = None
    for a in actions:
        if (a["action"] == "drop" and a["beat"] not in pending
                and _cut_allowed(stops, a["beat"], pending)):
            pending.add(a["beat"])
    for f in lint_fixes:
        if f["fix"] == _CUT or f["fix"] is None:
            continue
        stops[f["beat"]]["motif"] = f["fix"]
        stops[f["beat"]]["motif_locked"] = True
    for a in actions:
        if a["action"] == "swap_treatment":
            stops[a["beat"]]["motif"] = a["to"]
            stops[a["beat"]]["motif_locked"] = True
    for i in sorted(pending, reverse=True):
        stops.pop(i)


_PLAN_ROUNDS = 2   # the first plan plus ONE re-plan; a re-plan is free, but
                   # the budget still ends — anything a re-plan could not
                   # clear rides to the post-render pass rather than looping


def _review_plan(run_id, run_dir, pub, stops, ctx):
    """TIER 2 — the plan-stage review: the six data lints, run BEFORE any
    render is paid for. Every one of them reads stops/beats and nothing else,
    yet they used to run after a ~262s Remotion render — so a data finding
    bought a re-render instead of a free re-plan, 5 of 9 builds rendered the
    film twice, and a film shipped with adjacent duplicate treatments because
    round 2 found them with no round left (REVIEWER-FINDINGS, 2026-07-20).

    Loops _plan_beats -> lints -> _apply_fixes until the plan is clean or the
    budget ends, then returns the LAST plan for the single render. Pacing is
    linted against the planned t_f/FPS here (Remotion renders frame-exactly;
    the post-render pass re-checks it against the measured length). No model
    call, no frame, no render happens in this function — and the thread
    narrates it as reviewing the PLAN: "watched it back" stays earned by
    frames only, in the pass that has them.

    A blocking finding that survives the budget refuses the build HERE,
    before the render: the post-render pass re-runs the same lint on the same
    stops and would refuse anyway — the customer gets the same honest refusal
    262s sooner. Returns (beats, t_f, props_path, out)."""
    beats, t_f, props_path, out = _plan_beats(run_id, run_dir, pub, stops, ctx)
    checks = []
    for rnd in range(1, _PLAN_ROUNDS + 1):
        checks = _checks_from(_data_results(stops, beats, t_f / FPS))
        emit(run_dir, "review.start",
             "Reviewing the cut plan before rendering"
             + (f" (round {rnd})" if rnd > 1 else ""),
             f"{len(beats)} beats against {len(checks)} structural checks "
             "that read the plan; the frame-by-frame look comes after the "
             "render" + ("; re-checking the repaired plan." if rnd > 1
                         else "."))
        for c in checks:
            for f in c["findings"]:
                emit(run_dir, "review.lint", _finding_title(f),
                     f"Check {c['name']}. "
                     + ("Fix: cut the beat." if f["fix"] == _CUT
                        else f"Fix: swap to {f['fix']}." if f["fix"]
                        else "No automatic fix."))
        lint_fixes = [f for c in checks for f in c["findings"] if f["fix"]]
        if not lint_fixes:
            break
        if rnd >= _PLAN_ROUNDS:
            # AN UNAPPLIED FIX IS NOT A FIX (same rule as the render pass):
            # the budget is spent, so say so — the post-render review re-runs
            # these lints and can still take the repair, at re-render cost.
            emit(run_dir, "review.note",
                 f"{len(lint_fixes)} fix"
                 f"{'es' if len(lint_fixes) != 1 else ''} found with no "
                 "plan round left to apply",
                 "The plan budget is one re-plan. The film review after the "
                 "render can still take these, at the cost of a re-render.")
            break
        _n = len(lint_fixes)
        _say(run_dir,
             f"{_n} thing{'s' if _n != 1 else ''} bothered me in the plan, "
             f"so I'm fixing {'them' if _n != 1 else 'it'} before I print "
             "a single frame — cheaper to repair a plan than a film.")
        emit(run_dir, "review.apply",
             f"Applying {_n} adjustment{'s' if _n != 1 else ''} to the plan",
             "Re-planning the cut — nothing has been rendered yet.")
        _apply_fixes(stops, lint_fixes, [])
        beats, t_f, props_path, out = _plan_beats(run_id, run_dir, pub,
                                                  stops, ctx)
    blocking = [c for c in checks if c["blocking"] and c["findings"]]
    if blocking:
        # REFUSE BEFORE THE RENDER. Same contract as the render pass — a beat
        # with nothing to show is a claim the film would make on the
        # customer's behalf — but caught while it is still a plan, so the
        # refusal does not cost a render first.
        detail = "; ".join(f"{c['name']} ({len(c['findings'])})"
                           for c in checks if c["findings"])
        emit(run_dir, "review.reject",
             "Plan review did not pass — refusing before the render", detail)
        _say(run_dir,
             "I'm not rendering this: " + blocking[0]["findings"][0]["issue"]
             + ". That's a claim the film would be making for you that I "
             "can't stand behind, and re-planning didn't clear it.")
        raise RuntimeError(
            "walkrec plan review rejected the cut: "
            + "; ".join(f"{c['name']}: {c['findings'][0]['issue']}"
                        for c in blocking))
    open_findings = [f for c in checks for f in c["findings"]]
    emit(run_dir, "review.note",
         "Plan review " + ("clean" if not open_findings
                           else f"done — {len(open_findings)} finding"
                                f"{'s' if len(open_findings) != 1 else ''} "
                                "left for the film review"),
         "Rendering once; the frame-by-frame look comes next.")
    return beats, t_f, props_path, out


def _review_and_fix(run_id, run_dir, pub, stops, ctx, beats, film_s,
                    brain="sonnet5"):
    """The review GATE (auto-apply, per Dennis): named checks over the cut ->
    gated fixes -> re-assemble -> RE-CHECK the new cut. Everything visible in
    the feed as review.* events.

    Returns (film, beats, film_s, unresolved) — the same order
    _assemble_and_render returns, plus whatever review could not clear.
    Raises when a blocking check still fails after the re-cut: a film the
    reviewer has just described as broken must not be handed over as if it
    were finished."""
    film = os.path.join(os.path.abspath(run_dir), "film-tour.mp4")
    recut = False
    checks = []
    for rnd in range(1, _REVIEW_ROUNDS + 1):
        emit(run_dir, "review.start",
             "Reviewing story and architecture"
             + (f" (round {rnd})" if rnd > 1 else ""),
             f"{len(beats)} beats against {len(_CHECKS)} checks"
             + ("; re-checking the new cut." if rnd > 1 else "."))
        checks, actions = _run_checks(run_dir, stops, beats, film_s, brain)
        for c in checks:
            kind = ("review.finding" if c["name"] == _CRITIC_CHECK
                    else "review.lint")
            for f in c["findings"]:
                emit(run_dir, kind, _finding_title(f),
                     f"Check {c['name']}. "
                     + ("Fix: cut the beat." if f["fix"] == _CUT
                        else f"Fix: swap to {f['fix']}." if f["fix"]
                        else "No automatic fix."))
        for a in actions:
            emit(run_dir, "review.finding",
                 f"Beat {a['beat'] + 1}: {a['issue'] or a['action']}",
                 f"Action: {a['action']}"
                 + (f" → {a['to']}" if a['to'] else ""))
        open_findings = [f for c in checks for f in c["findings"]]
        if not open_findings and not actions:
            break   # ALL terminal reporting happens once, below
        lint_fixes = [f for c in checks for f in c["findings"] if f["fix"]]
        # AN ACTION THAT COULD NOT BE APPLIED IS NOT A FIX. The round budget is
        # a cost decision (a re-render is ~4 minutes) and it stands — but the
        # last round used to emit "Action: drop" to the feed and then break
        # before applying it, so the thread showed a decision the film never
        # made (stripe.com 2026-07-20, beat 4). Say so instead.
        if rnd >= _REVIEW_ROUNDS and (lint_fixes or actions):
            emit(run_dir, "review.note",
                 f"{len(lint_fixes) + len(actions)} fix"
                 f"{'es' if len(lint_fixes) + len(actions) != 1 else ''} found "
                 "with no round left to apply",
                 "The review budget is one re-cut. These are reported below "
                 "rather than made.")
        if rnd >= _REVIEW_ROUNDS or (not lint_fixes and not actions):
            break
        _n = len(lint_fixes) + len(actions)
        _say(run_dir,
             f"{_n} thing{'s' if _n != 1 else ''} bothered me on the way "
             f"through, so I'm fixing {'them' if _n != 1 else 'it'} before you "
             "see it — then re-cutting.")
        _apply_fixes(stops, lint_fixes, actions)
        # Keep the pre-review cut for comparison. It is a debugging artifact,
        # not a contract — losing it must never cost the run its film.
        prereview = os.path.join(run_dir, "film-tour-prereview.mp4")
        if not os.path.exists(prereview):
            try:
                shutil.copyfile(film, prereview)
            except OSError as e:
                print(f"[walkrec] prereview copy skipped: {e}", file=sys.stderr)
        emit(run_dir, "review.apply", f"Applying {_n} adjustments",
             "Re-assembling and re-rendering the film.")
        film, beats, film_s = _assemble_and_render(run_id, run_dir, pub,
                                                   stops, ctx)
        recut = True
    # ONE TERMINAL REPORT. The reviewer does not get to round the film up to
    # "it holds" — that was the original defect — and it does not get to end
    # the thread in silence either: a check that could not run is disclosed,
    # a finding that survived is a rejection, and an honesty finding that
    # survived refuses delivery outright.
    unresolved = [f for c in checks for f in c["findings"]]
    blocking = [c for c in checks if c["blocking"] and c["findings"]]
    if not unresolved:
        skipped = [c["name"] for c in checks if not c["ran"]]
        if recut:
            emit(run_dir, "review.done", "Review complete — film updated",
                 artifact=film)
        else:
            emit(run_dir, "review.pass",
                 "Review passed" + (" on the checks that could run"
                                    if skipped else ""),
                 ", ".join(c["name"] for c in checks if c["ran"])
                 + " — all clear."
                 + (f" Could not run: {', '.join(skipped)}." if skipped else ""))
        _say(run_dir, _review_claim(checks) + " Shipping this cut.")
        return film, beats, film_s, []
    detail = "; ".join(f"{c['name']} ({len(c['findings'])})"
                       for c in checks if c["findings"])
    emit(run_dir, "review.reject",
         f"Review did not pass — {len(unresolved)} issue"
         f"{'s' if len(unresolved) != 1 else ''} left in the cut", detail)
    if blocking:
        # REFUSE DELIVERY. A beat with nothing to show, or a green check on a
        # failure state, is the film making a claim on the customer's behalf
        # that isn't true. The assembler prevents both by construction, so
        # reaching here means a contract broke — ship nothing and say why.
        _say(run_dir,
             "I'm not handing this over: " + blocking[0]["findings"][0]["issue"]
             + ". That's a claim the film would be making for you that I "
             "can't stand behind, and re-cutting didn't clear it.")
        raise RuntimeError(
            "walkrec review rejected the cut: "
            + "; ".join(f"{c['name']}: {c['findings'][0]['issue']}"
                        for c in blocking))
    # Not blocking, but not clean: the film ships and the handover names what
    # is still wrong (build_tour_film reads `unresolved`).
    # ALL OF THEM. `unresolved[0]` reported one issue where the reject event
    # beside it counted three (stripe.com 2026-07-20 said "runs 9.1s" and
    # dropped both title-match findings on the floor). The disclosure is the
    # only place a non-blocking finding ever reaches the customer, so it does
    # not get to choose which ones.
    _say(run_dir,
         _review_claim(checks)
         + " What I couldn't settle: "
         + "; ".join(f["issue"] for f in unresolved) + ".")
    return film, beats, film_s, unresolved


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
