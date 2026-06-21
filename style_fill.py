#!/usr/bin/env python3
"""style_fill.py -- Phase 2 keystone of the VO-driven style engine.

Fills one of Dennis's CURATED style templates with a customer's brand + scene
copy, then drives the FULL VO-driven render end to end. This is exactly Dennis's
manual re-skin workflow, automated (see docs/2026-06-21-vo-driven-style-engine-design.md).

Pipeline (all $0 on the free tier):
    plan.json + brand_theme.json
       |  align_vo.py     (edge-tts synth + whisper-cli word timing)  -> vo_alignment.json
       |  build_timeline.py (word spans -> in/out frames, cues -> at_frame) -> timeline.json
       |  style_fill (THIS) merge: timeline + plan copy + brand theme + STYLE -> props.json
       |  remotion render Timeline --props props.json
       v  montage.png (proof the scenes are VO-anchored and reveals land on words)

THE STYLE REGISTRY (extensible -- adding a style = ONE entry):
    A Style maps each plan scene's `role`/`type` -> a Timeline `archetype`
    ("hero-title" | "card-ui") and a `shape_data(scene, brand) -> SceneData` fn
    that builds the archetype's `data` block from plan copy + brand features.
    To add a style later: append a Style(...) to STYLES with its own role->archetype
    map and data shapers. No other code changes.

props.json contract (EXACT shape the <Timeline> composition consumes, one props
object -- studio/src/timeline/types.ts):
    {
      "fps": int, "total_frames": int, "audio_path": str, "lang": str,
      "theme": { bg, bgCard, bgCardRaised, navy, navyBright, accent, ok, text,
                 textMuted, textDim, border, fontPrimary, fontMono, fontDisplay,
                 wordmark },
      "scenes": [ { id, archetype, in_frame, out_frame,
                    cues:[{label, word, at_frame}],   # ABSOLUTE frames (Timeline rebases)
                    data:{...SceneData per archetype} } ]
    }

CLI:
    python3 style_fill.py --plan <plan.json> --brand <brand_theme.json> \
        --style orinovate-kinetic-light --out runs/<id>/ [--fps 30] \
        [--render] [--no-align] [--tier free]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from typing import Any, Callable, Dict, List, Optional

import align_vo
import build_timeline

# --- Timeline archetype ids (must match studio/src/timeline/types.ts Archetype) ---
ARCH_HERO = "hero-title"
ARCH_CARD = "card-ui"
# The never-blank designed card for a cinematic/walkthrough/demo beat that gets no
# real footage on a $0/standard run (the blank-scenes fix). Shows the narrated
# point as kinetic motion-graphics instead of a flat solid color.
ARCH_EXPLAINER = "explainer-card"

# Number of brand feature cards the CardUi 2x2 grid renders.
CARD_COUNT = 4
# Max capability bullets the ExplainerCard renders.
EXPLAINER_BULLET_COUNT = 4


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _plan_scenes(plan: Dict[str, Any]) -> List[Dict[str, Any]]:
    return plan["scenes"] if isinstance(plan, dict) else plan


def _scene_role(scene: Dict[str, Any]) -> str:
    """The classifier key for the registry: explicit `role`, else `type`."""
    return str(scene.get("role") or scene.get("type") or "").strip().lower()


def _scene_by_id(scenes: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {s.get("id"): s for s in scenes}


# ---------------------------------------------------------------------------
# STYLE REGISTRY  (data shapers per archetype, then the Style entries)
# ---------------------------------------------------------------------------
# Shapers receive (plan_scene, brand_theme) and return a SceneData dict for the
# archetype. They prefer explicit copy in scene["data"], falling back to brand.
def _shape_hero(scene: Dict[str, Any], brand: Dict[str, Any]) -> Dict[str, Any]:
    """HeroTitle data: kicker / title / punchWord / subtitle.

    Prefers explicit copy in scene["data"]; falls back to brand tagline/wordmark
    so a thin plan still produces an on-brand hero (open + close variants).
    """
    d = scene.get("data") or {}
    title = d.get("title") or brand.get("tagline") or brand.get("wordmark") or ""
    subtitle = d.get("subtitle")
    if subtitle is None:
        # close/cta variant points at the brand URL; open variant uses the tagline.
        subtitle = brand.get("cta_url") if _scene_role(scene) == "close" else brand.get("tagline")
    out = {
        "kicker": d.get("kicker") or brand.get("wordmark", "").upper(),
        "title": title,
        "subtitle": subtitle or "",
    }
    # punchWord must be a substring of title for the accent split to fire.
    punch = d.get("punchWord")
    if punch and punch in (title or ""):
        out["punchWord"] = punch
    return out


def _shape_cards(scene: Dict[str, Any], brand: Dict[str, Any]) -> Dict[str, Any]:
    """CardUi data: an accent-split heading + the brand's 2x2 feature grid.

    The four cards come from brand["features"]; the heading/accent from plan copy.
    Each card: {label, value?, sub?, accent?}. The first defaults to the accent
    card if none is flagged (so the highlighted-card tail pulse always has a home).
    """
    d = scene.get("data") or {}
    features = list(brand.get("features") or [])[:CARD_COUNT]
    cards: List[Dict[str, Any]] = []
    for f in features:
        # accept {label,value,sub,accent} (fixture) or {title,sub} (brand_extract).
        cards.append({
            "label": f.get("label") or f.get("title") or "",
            "value": f.get("value"),
            "sub": f.get("sub"),
            "accent": bool(f.get("accent")),
        })
    if cards and not any(c["accent"] for c in cards):
        cards[0]["accent"] = True
    return {
        "heading": d.get("heading") or "Built to ship",
        "headingAccent": d.get("headingAccent") or "",
        "cards": cards,
    }


def _title_from_text(text: str, limit: int = 48) -> str:
    """A short, honest title from a scene's brief/VO text: the first clause,
    trimmed. NEVER fabricates marketing copy — it just truncates real text."""
    if not text:
        return ""
    # First sentence/clause, then a hard length clamp on a word boundary.
    head = re.split(r"[.!?\n]", str(text).strip(), maxsplit=1)[0].strip()
    head = re.split(r"\s+[—–-]\s+", head, maxsplit=1)[0].strip()
    if len(head) <= limit:
        return head
    cut = head[:limit].rsplit(" ", 1)[0]
    return cut or head[:limit]


def _shape_explainer(scene: Dict[str, Any], brand: Dict[str, Any]) -> Dict[str, Any]:
    """ExplainerCard data: kicker / title / subtitle / bullets.

    A cinematic/walkthrough/demo beat that gets no real footage still SHOWS the
    narrated point. Prefers explicit copy in scene["data"]; falls back to the
    scene's own brief / VO beat text and the brand's real features — never
    invented marketing copy (honesty rule, brand_extract.py).
    """
    d = scene.get("data") or {}
    brief = scene.get("brief") or ""
    title = d.get("title") or _title_from_text(brief) or brand.get("tagline") \
        or brand.get("wordmark") or ""
    subtitle = d.get("subtitle")
    if subtitle is None:
        subtitle = brand.get("tagline") or ""

    # Bullets: explicit copy wins; else short capability nouns from the brand's
    # real features (CardUi labels), so a "narrate the factory floor" beat shows
    # the actual capabilities rather than a repeated hero title.
    bullets = d.get("bullets")
    if not bullets:
        bullets = []
        for f in list(brand.get("features") or [])[:EXPLAINER_BULLET_COUNT]:
            label = f.get("label") or f.get("title")
            if label:
                bullets.append(label)
    bullets = [b for b in (bullets or []) if b][:EXPLAINER_BULLET_COUNT]

    out: Dict[str, Any] = {
        "kicker": d.get("kicker") or "",
        "title": title,
        "subtitle": subtitle or "",
        "bullets": bullets,
    }
    return out


class Style:
    """One curated template. `role_map` classifies a plan scene -> archetype;
    `shapers` builds each archetype's `data`. Adding a style = one instance."""

    def __init__(self, name: str, role_map: Dict[str, str],
                 default_archetype: str,
                 shapers: Dict[str, Callable[[Dict, Dict], Dict]],
                 theme_fn: Callable[[Dict], Dict]):
        self.name = name
        self.role_map = role_map
        self.default_archetype = default_archetype
        self.shapers = shapers
        self.theme_fn = theme_fn

    def archetype_for(self, scene: Dict[str, Any]) -> str:
        return self.role_map.get(_scene_role(scene), self.default_archetype)

    def shape(self, scene: Dict[str, Any], brand: Dict[str, Any]) -> Dict[str, Any]:
        arch = self.archetype_for(scene)
        return self.shapers[arch](scene, brand)

    def theme(self, brand: Dict[str, Any]) -> Dict[str, Any]:
        return self.theme_fn(brand)


# Theme keys the <Timeline> composition reads (studio/src/timeline/types.ts Theme).
_THEME_PALETTE_KEYS = ("bg", "bgCard", "bgCardRaised", "navy", "navyBright",
                       "accent", "ok", "text", "textMuted", "textDim", "border")
_THEME_FONT_KEYS = ("fontPrimary", "fontMono", "fontDisplay")
# Fallbacks lifted from the Orinovate kinetic-light theme.ts (keeps a thin brand
# fixture from producing an undefined-color render).
_KINETIC_LIGHT_DEFAULTS = {
    "bg": "#ffffff", "bgCard": "#ffffff", "bgCardRaised": "#f9fafc",
    "navy": "#1a3a5c", "navyBright": "#4a7aa8", "accent": "#2563eb",
    "ok": "#10b981", "text": "#0f2338", "textMuted": "#3d4a5c",
    "textDim": "#6b7589", "border": "#e5e9f0",
    "fontPrimary": "Inter, system-ui, -apple-system, sans-serif",
    "fontMono": "ui-monospace, SFMono-Regular, Menlo, monospace",
    "fontDisplay": "Inter, system-ui, sans-serif",
}


def _theme_kinetic_light(brand: Dict[str, Any]) -> Dict[str, Any]:
    """Map a brand_theme.json (palette/fonts/wordmark) -> the Timeline theme block.

    Per-template adapter (spec: "the style-fill contract must normalize" differing
    brand shapes). Accepts BOTH the hand-authored kinetic-light fixture
    (palette.{bg,accent,navy,text,...}, fonts.{fontPrimary,...}) AND brand_extract.py's
    normalized shape (palette.{bg,ink,accent,accent2,success}, fonts.{display,mono}).
    Every composition key resolves to a brand value, then an alias, then a default.
    """
    palette = brand.get("palette") or {}
    fonts = brand.get("fonts") or {}

    def pick(key: str, *aliases: str) -> str:
        for src in (palette.get(key), *(palette.get(a) for a in aliases)):
            if src:
                return src
        return _KINETIC_LIGHT_DEFAULTS[key]

    theme: Dict[str, Any] = {
        "bg": pick("bg"),
        "bgCard": pick("bgCard", "bg"),
        "bgCardRaised": pick("bgCardRaised"),
        "navy": pick("navy", "accent2"),
        "navyBright": pick("navyBright", "accent2"),
        "accent": pick("accent"),
        "ok": pick("ok", "success", "accent2"),
        "text": pick("text", "ink", "fg"),
        "textMuted": pick("textMuted"),
        "textDim": pick("textDim"),
        "border": pick("border"),
    }
    theme["fontPrimary"] = fonts.get("fontPrimary") or fonts.get("display") or _KINETIC_LIGHT_DEFAULTS["fontPrimary"]
    theme["fontMono"] = fonts.get("fontMono") or fonts.get("mono") or _KINETIC_LIGHT_DEFAULTS["fontMono"]
    theme["fontDisplay"] = fonts.get("fontDisplay") or fonts.get("display") or _KINETIC_LIGHT_DEFAULTS["fontDisplay"]
    theme["wordmark"] = brand.get("wordmark") or brand.get("brand") or brand.get("name") or ""
    return theme


# --- THE REGISTRY -----------------------------------------------------------
# orinovate-kinetic-light: open/close -> HeroTitle, feature/capability -> CardUi.
STYLES: Dict[str, Style] = {
    "orinovate-kinetic-light": Style(
        name="orinovate-kinetic-light",
        role_map={
            "open": ARCH_HERO, "hero": ARCH_HERO, "title": ARCH_HERO,
            "intro": ARCH_HERO, "close": ARCH_HERO, "cta": ARCH_HERO,
            "outro": ARCH_HERO,
            "feature": ARCH_CARD, "capability": ARCH_CARD,
            "capabilities": ARCH_CARD, "cards": ARCH_CARD, "grid": ARCH_CARD,
            # A cinematic/walkthrough/demo beat with no real footage -> the designed
            # explainer card (never the old flat solid-color blank).
            "cinematic": ARCH_EXPLAINER, "walkthrough": ARCH_EXPLAINER,
            "demo": ARCH_EXPLAINER, "explainer": ARCH_EXPLAINER,
        },
        default_archetype=ARCH_HERO,
        shapers={ARCH_HERO: _shape_hero, ARCH_CARD: _shape_cards,
                 ARCH_EXPLAINER: _shape_explainer},
        theme_fn=_theme_kinetic_light,
    ),
}


# ---------------------------------------------------------------------------
# MERGE + DRIVER  (filled below)
# ---------------------------------------------------------------------------
def build_props(timeline: Dict[str, Any], plan: Dict[str, Any],
                brand: Dict[str, Any], style_name: str) -> Dict[str, Any]:
    """MERGE: timeline (frames + cues) + plan copy + brand theme + style ->
    the exact one-object props the <Timeline> composition consumes.

    timeline.json owns frames/cues; the plan owns copy; the style decides each
    scene's archetype and shapes its `data`; the brand owns palette/fonts/wordmark.
    """
    if style_name not in STYLES:
        raise KeyError(
            f"unknown style {style_name!r}; known: {sorted(STYLES)}")
    style = STYLES[style_name]
    plan_scenes = _plan_scenes(plan)
    by_id = _scene_by_id(plan_scenes)

    scenes: List[Dict[str, Any]] = []
    for tl_scene in timeline.get("scenes", []):
        sid = tl_scene.get("id")
        plan_scene = by_id.get(sid, {"id": sid})
        archetype = style.archetype_for(plan_scene)  # style decides, not the plan
        scenes.append({
            "id": sid,
            "archetype": archetype,
            "in_frame": tl_scene["in_frame"],
            "out_frame": tl_scene["out_frame"],
            # cues stay ABSOLUTE (Timeline.tsx rebases to scene-local at the seam).
            "cues": tl_scene.get("cues", []),
            "data": style.shape(plan_scene, brand),
        })

    return {
        "fps": timeline.get("fps", 30),
        "total_frames": timeline.get("total_frames", 0),
        "audio_path": timeline.get("audio_path"),
        "lang": timeline.get("lang", "en"),
        "theme": style.theme(brand),
        "scenes": scenes,
    }


STUDIO_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "studio")


def _stage_audio(props: Dict[str, Any], out_dir: str) -> Dict[str, Any]:
    """Stage the run's voiceover into studio/public/ and rewrite audio_path to a
    public-relative name. Remotion serves <Audio> via staticFile() under public/;
    an absolute filesystem path gets joined onto the webpack bundle root and 404s.
    Copies to a run-scoped name so parallel runs don't clobber each other.
    Mutates + returns props. Remote (http) paths pass through untouched."""
    ap = props.get("audio_path")
    if not ap or ap.startswith("http"):
        return props
    # resolve the real file: absolute, or relative to out_dir, or as given.
    cands = [ap, os.path.join(out_dir, os.path.basename(ap)), os.path.join(out_dir, ap)]
    src = next((c for c in cands if os.path.exists(c)), None)
    run_tag = os.path.basename(os.path.normpath(out_dir)) or "run"
    rel = f"vo-{run_tag}.mp3"
    if src:
        pub = os.path.join(STUDIO_DIR, "public")
        os.makedirs(pub, exist_ok=True)
        import shutil
        shutil.copyfile(src, os.path.join(pub, rel))
    # public-relative (no leading slash) -> Timeline.tsx staticFile()s it.
    props["audio_path"] = rel
    return props


def run_pipeline(plan_path: str, brand_path: str, style_name: str, out_dir: str,
                 fps: int = 30, tier: str = "free",
                 do_align: bool = True, do_render: bool = False) -> Dict[str, Any]:
    """END-TO-END driver: plan + brand + style -> props.json (+ optional render).

    Chains align_vo -> build_timeline -> style_fill merge. `do_align=False` reuses
    an existing vo_alignment.json (fast deterministic re-merges / tests).
    Returns {props, props_path, timeline_path, alignment_path, montage_path?}.
    """
    os.makedirs(out_dir, exist_ok=True)
    plan = _load_json(plan_path)
    brand = _load_json(brand_path)
    plan_scenes = _plan_scenes(plan)

    alignment_path = os.path.join(out_dir, "vo_alignment.json")
    if do_align:
        beats = (plan.get("voiceover") or {}).get("beats") or []
        if not beats:
            raise ValueError("plan has no voiceover.beats to align")
        alignment = align_vo.align(beats, out_path=alignment_path, tier=tier,
                                   lang=(plan.get("voiceover") or {}).get("lang", "en"),
                                   voice=(plan.get("voiceover") or {}).get("voice"))
        with open(alignment_path, "w", encoding="utf-8") as fh:
            json.dump(alignment, fh, indent=2)
    else:
        alignment = _load_json(alignment_path)

    timeline = build_timeline.build_timeline(plan_scenes, alignment, fps=fps)
    timeline_path = os.path.join(out_dir, "timeline.json")
    with open(timeline_path, "w", encoding="utf-8") as fh:
        json.dump(timeline, fh, indent=2)

    props = build_props(timeline, plan, brand, style_name)
    _stage_audio(props, out_dir)
    props_path = os.path.join(out_dir, "props.json")
    with open(props_path, "w", encoding="utf-8") as fh:
        json.dump(props, fh, indent=2)

    result = {
        "props": props, "props_path": props_path,
        "timeline_path": timeline_path, "alignment_path": alignment_path,
    }
    print(f"style_fill: wrote {props_path} "
          f"({len(props['scenes'])} scenes, {props['total_frames']} frames @ {props['fps']}fps, "
          f"style={style_name})")

    if do_render:
        result["montage_path"] = render_and_montage(props_path, out_dir)
    return result


def render_and_montage(props_path: str, out_dir: str) -> Optional[str]:
    """Render the Timeline composition with --props, then ffmpeg a tiled montage.

    Foreground + bounded. Returns the montage path (or None on failure)."""
    studio = STUDIO_DIR
    mp4 = os.path.abspath(os.path.join(out_dir, "video.mp4"))
    montage = os.path.abspath(os.path.join(out_dir, "montage.png"))
    abs_props = os.path.abspath(props_path)
    env = dict(os.environ, PATH=os.path.join(studio, "node_modules", ".bin")
               + os.pathsep + os.environ.get("PATH", ""))
    render_cmd = ["remotion", "render", "src/index.ts", "Timeline", mp4,
                  "--codec=h264", "--concurrency=8", f"--props={abs_props}"]
    print("style_fill: rendering ->", mp4)
    r = subprocess.run(render_cmd, cwd=studio, env=env)
    if r.returncode != 0 or not os.path.exists(mp4):
        print("style_fill: render FAILED", file=sys.stderr)
        return None
    subprocess.run(["ffmpeg", "-y", "-i", mp4,
                    "-vf", "fps=1,scale=480:-1,tile=5x2", "-frames:v", "1", montage],
                   cwd=studio, env=env,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print("style_fill: montage ->", montage)
    return montage if os.path.exists(montage) else None


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Fill a curated style template and drive the VO render.")
    ap.add_argument("--plan", required=True, help="plan.json (scenes + voiceover.beats)")
    ap.add_argument("--brand", required=True, help="brand_theme.json (palette/fonts/wordmark/features)")
    ap.add_argument("--style", default="orinovate-kinetic-light",
                    choices=sorted(STYLES), help="curated style template")
    ap.add_argument("--out", required=True, help="run output dir (runs/<id>/)")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--tier", default="free", choices=["free", "premium"])
    ap.add_argument("--no-align", action="store_true",
                    help="reuse existing vo_alignment.json in --out (skip synth)")
    ap.add_argument("--render", action="store_true",
                    help="also render the Timeline composition + a tiled montage")
    args = ap.parse_args(argv)

    run_pipeline(args.plan, args.brand, args.style, args.out, fps=args.fps,
                 tier=args.tier, do_align=not args.no_align, do_render=args.render)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
