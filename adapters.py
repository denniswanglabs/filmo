#!/usr/bin/env python3
"""Media adapters for the producer-brain orchestrator.

Each segment skill (higgsfield-scene, walk-agent, motion-graphics, ElevenLabs VO,
video-stitch) gets a thin adapter with two modes:

  mode="mock"  -> ZERO money. Cinematic/walkthrough/title scenes become real but
                  synthetic color-coded MP4 cards (valid clips the stitcher can
                  assemble); VO is synthesized with **edge-tts** (free, real
                  audio, stands in for ElevenLabs during the test phase).
  mode="real"  -> the genuine paid/slow pipeline: higgsfield-scene (PAID),
                  walk-agent (NemoClaw, slow), motion-graphics (Remotion, free),
                  ElevenLabs (PAID). Wired so the eventual paid switch is a flag,
                  not a rewrite. The mock test suite never calls these.

The stitch adapter is REAL in both modes (ffmpeg is free and local) so the test
phase produces a genuine, playable final MP4 from the synthetic clips.

Stdlib only (subprocess to ffmpeg / edge-tts / higgsfield). No third-party deps.
"""

import json
import os
import re
import shlex
import subprocess
import sys
import time
import types

import remotion_codegen

HERE = os.path.dirname(os.path.abspath(__file__))
STUDIO_DIR = os.path.join(HERE, "studio")
STUDIO_ACTIVE = os.path.join(STUDIO_DIR, "src", "generated", "active.tsx")

# Frame spec shared by every clip so the fast concat path stays valid.
W, H, FPS = 1920, 1080, 30

# Color-coded backdrops per scene type (hex, no leading #). The synthetic clips
# are intentionally plain — the rich labeling lives in the dashboard, and this
# ffmpeg build has no drawtext/libfreetype, so we don't burn text.
TYPE_COLOR = {
    "title": "0A0D0C",        # near-black slate
    "cinematic": "1F3A8A",    # indigo (video plate)
    "cinematic_still": "3B2F6B",  # violet (downgraded still)
    "walkthrough": "0F766E",  # teal (app capture)
    "motion_graphic": "B45309",  # amber (overlay card)
    "declined": "3A0D0D",     # dark red (cut scene placeholder; not stitched)
}

# ElevenLabs voice name -> a close edge-tts voice for the free test phase.
EDGE_VOICE_MAP = {
    "adam": "en-US-AndrewNeural",
    "antoni": "en-US-BrianNeural",
    "rachel": "en-US-AriaNeural",
    "bella": "en-US-JennyNeural",
    "josh": "en-US-GuyNeural",
}
EDGE_VOICE_DEFAULT = "en-US-AndrewNeural"


class AdapterError(RuntimeError):
    pass


def _run(cmd, timeout=120, check=True):
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    if check and proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()
        raise AdapterError("cmd failed (%d): %s\n%s" % (
            proc.returncode, shlex.join(cmd), tail[-1] if tail else "?"))
    return proc


def ffprobe_duration(path):
    proc = _run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "csv=p=0", path], timeout=30)
    try:
        return float(proc.stdout.strip())
    except (ValueError, AttributeError):
        return 0.0


# ---------------------------------------------------------------------------
# Synthetic clip (mock generation) — a real, valid, video-only MP4 color card.
# ---------------------------------------------------------------------------

def synth_clip(out_path, color_hex, duration_s):
    """Render a solid-color silent clip at the shared frame spec. Real MP4."""
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    dur = max(1, int(duration_s))
    _run([
        "ffmpeg", "-y", "-nostdin", "-loglevel", "error",
        "-f", "lavfi", "-i", "color=c=0x%s:s=%dx%d:r=%d:d=%d" % (color_hex, W, H, FPS, dur),
        "-vf", "format=yuv420p,setsar=1",
        "-c:v", "libx264", "-crf", "20", "-preset", "veryfast",
        "-movflags", "+faststart", out_path,
    ], timeout=120)
    if not os.path.exists(out_path) or os.path.getsize(out_path) < 1000:
        raise AdapterError("synth_clip produced no output: %s" % out_path)
    return out_path


# ---------------------------------------------------------------------------
# Cinematic scene (higgsfield-scene). PAID in real mode; mock = color card.
# ---------------------------------------------------------------------------

def generate_cinematic(scene, out_path, mode, final_model=None, company_url=None):
    model = final_model or scene.get("model") or "seedance_2_0"
    if mode == "mock":
        color = TYPE_COLOR["cinematic_still"] if model == "gpt_image_2" else TYPE_COLOR["cinematic"]
        synth_clip(out_path, color, scene.get("duration_s", 6))
        return {"output_path": out_path, "model": model, "real": False}
    return _generate_cinematic_real(scene, out_path, model, company_url=company_url)


# ---------------------------------------------------------------------------
# Cinematic PROMPT BUILDER — the winning two-track formula from the real
# Higgsfield gpt_image_2 A/B (OVERNIGHT-LOG Iteration 2; evidence/prompt-ab/).
#
# Feeding the raw plan `brief` to Higgsfield yields a literal screenshot, not a
# brand film. This builder wraps the brief into one of two production prompts:
#
#   kind="hero"      (literal-UI / dashboard plates, typically gpt_image_2):
#                    brief + a fixed cinematography scaffolding string. NO
#                    anti-text clause — the current model (videotape-alpha)
#                    renders UI text legibly, so a hero plate WANTS readable UI.
#                    -> winner = evidence/prompt-ab/b-cinematography.png
#
#   kind="establish" (abstract / establishing / pushed-in motion plates, e.g.
#                    seedance establishing shots): cinematography scaffolding +
#                    a SINGLE-HERO composition cue + SATURATED brand-accent hex
#                    injection (accent/accent2 from `palette`, boosted toward full
#                    saturation) + an abstract anti-text body (only soft light /
#                    bokeh language — NO positive text nouns) + a trailing
#                    pure-negative no-text clause + a negative-space-for-title
#                    composition note (title-overlay room).
#                    -> winner = evidence/prompt-ab/e-fullformula.png
#
# Model-robust: general cinematography + brand-hex + CONDITIONAL anti-text. No
# videotape-alpha-specific hacks — the same tokens carry to Seedance / future
# models. The establish track folds in the iter-5 real-Seedance learnings
# (see .handoff-portfolio-2.md): (1) bias to a SINGLE hero object — multi-element
# "array of cards" layouts reintroduced garbled caption strips; (2) NEVER name a
# UI-text noun positively (even "blurred placeholder labels" cues text rendering)
# — describe only abstract light/shape, push the hard "no text" steer into a
# trailing pure-negative clause; (3) SATURATE the injected brand hex — a
# desaturated brand color (Shopify olive) steered to the wrong hue, while a
# vivid single hue (Robinhood green) steered reliably.
# ---------------------------------------------------------------------------

# Fixed cinematography scaffolding shared by both tracks (lens/light/grade/comp).
# Brand-neutral on purpose — palette specifics are injected separately for the
# "establish" track so the scaffolding itself stays model- and brand-agnostic.
_CINE_SCAFFOLD = (
    "cinematic product still, 50mm f1.8, shallow depth of field, "
    "soft cool key light with brand-accent rim light, premium dark studio, "
    "subtle volumetric haze, filmic high-contrast color grade, glossy reflection, "
    "centered composition, the look of an Apple-keynote product shot"
)

# Single-hero composition cue for the abstract/establishing track (iter-5 finding).
# The real Seedance gens proved single-hero-device / single-object framings stay
# clean, while multi-element "array of cards / multiple panels / converging
# dashboard" layouts reintroduce text-garble surfaces (Shopify's bottom caption
# strip). So the establish track POSITIVELY biases toward one hero object on a
# clean, uncluttered field — never an array/grid of labelled panels.
_SINGLE_HERO = (
    "a single hero object as the sole focal point, clean uncluttered composition, "
    "one device or product silhouette, no array of cards, no grid of panels, "
    "no multiple stacked UI windows"
)

# Anti-text steer for the abstract/establishing track only (iter-5 finding).
# CRITICAL: describe ONLY abstract light/shape content here — do NOT name any
# text-bearing noun positively ("interface text", "labels", "captions", even
# "blurred placeholder labels"). Naming text — even qualified — CUES the model to
# render text, which then garbles. The hard "no text" steer lives entirely in the
# trailing pure-negative `_NO_TEXT` clause below, never as a positive description.
_ANTI_TEXT = (
    "surfaces carry only soft diffuse light, gentle glow and creamy bokeh, "
    "abstract luminous shapes melting into shallow-focus blur"
)

# Pure-negative no-text clause — trailing only. Stated entirely as exclusions so
# the model is never primed with a positive text noun anywhere in the prompt.
_NO_TEXT = "no text, no words, no letters, no wordmarks, no watermarks, no UI labels"

# Negative-space-for-title composition note (establishing plates feed a title
# overlay, so leave room). Described abstractly — no "UI elements"/"labels" noun
# that could cue text; just open empty room and a soft glow drift.
_TITLE_ROOM = (
    "wide open negative space reserved for a title overlay, "
    "the hero object resolving in the lower third with soft glow drifting around it"
)

# Hint tokens that mark a scene as a literal-UI / hero plate vs an abstract /
# establishing plate. Checked against scene id + brief (and the model, below).
_HERO_HINTS = ("hero", "dashboard", "ui", "screenshot", "interface", "product shot", "plate of")
_ESTABLISH_HINTS = ("establish", "aerial", "abstract", "sweeping", "opener",
                    "establishing", "fly", "drone", "landscape", "atmospheric",
                    "push-in", "push in", "pushed-in")


def detect_kind(scene):
    """Classify a cinematic scene into the prompt track it should use.

    Returns "hero" (literal-UI plate) or "establish" (abstract/establishing).
    Heuristics, in priority order:
      1. explicit scene hint: scene["kind"] / scene["plate"] if set to a known value
      2. text hints in the scene id + brief (establish hints beat hero hints for
         a true establishing shot, but an explicit "hero"/"dashboard" wins for UI)
      3. model: a still model (gpt_image_2) with UI-ish brief leans hero; a video
         motion model (seedance_*) with no UI hint leans establish
      4. sensible default: "establish" (the safer track — anti-text guard means a
         mislabeled plate can never garble text, only lose some UI specificity).

    HARD OVERRIDE: video models NEVER return "hero". The Seedance A/B proved video
    garbles literal UI text under motion regardless of hero/dashboard hints, so the
    anti-text "establish" track is mandatory for any video gen. The "hero" track is
    reserved for the gpt_image_2 still alone (videotape-alpha renders text legibly).
    """
    model = (scene.get("model") or "").lower()
    # The literal-UI "hero" track is a still-only property of gpt_image_2. Any
    # other model is a video model → force the anti-text "establish" track.
    if model != "gpt_image_2":
        return "establish"

    explicit = (scene.get("kind") or scene.get("plate") or "").strip().lower()
    if explicit in ("hero", "literal", "literal-ui", "ui", "dashboard"):
        return "hero"
    if explicit in ("establish", "establishing", "abstract"):
        return "establish"

    # Reaching here means model == "gpt_image_2" (the only still). Text hints
    # then decide hero vs establish; with no hint a UI still defaults to hero.
    blob = ("%s %s" % (scene.get("id") or "", scene.get("brief") or "")).lower()
    has_hero = any(h in blob for h in _HERO_HINTS)
    has_establish = any(h in blob for h in _ESTABLISH_HINTS)

    # An explicit establishing word (aerial/sweeping/abstract/...) is a strong
    # signal even if a generic "ui"/"plate" token also appears.
    if has_establish and not has_hero:
        return "establish"
    return "hero"


def _saturate_hex(hex_str, min_sat=0.85, min_val=0.55):
    """Return a more vivid version of a #RRGGBB hex, preserving its hue.

    iter-5 finding: desaturated brand colors steer the model poorly — Shopify's
    muted olive-green (`#5E8E3E`) read as orange because the model under-weighted
    it, while a saturated single hue (Robinhood `#00C805`) steered reliably. So
    when we inject the brand accent we boost its HSV saturation (and lift very
    dark values) toward a fuller, more vivid color while keeping the SAME hue, so
    the steer is stronger without changing the brand's color identity.

    Already-saturated colors are left essentially unchanged (the floor only ever
    raises S/V, never lowers them). Returns an uppercase `#RRGGBB` string; any
    unparseable input is returned stripped/uppercased unchanged (never raises).
    """
    import colorsys
    s = (hex_str or "").strip()
    m = re.fullmatch(r"#?([0-9a-fA-F]{6})", s)
    if not m:
        return s.upper()
    digits = m.group(1)
    r = int(digits[0:2], 16) / 255.0
    g = int(digits[2:4], 16) / 255.0
    b = int(digits[4:6], 16) / 255.0
    h, sat, val = colorsys.rgb_to_hsv(r, g, b)
    # Pure greys (sat==0) have no hue to preserve — leave them be.
    if sat > 0.0:
        sat = max(sat, min_sat)
        val = max(val, min_val)
    r2, g2, b2 = colorsys.hsv_to_rgb(h, sat, val)
    return "#%02X%02X%02X" % (round(r2 * 255), round(g2 * 255), round(b2 * 255))


def _color_hue_name(deg):
    """Base hue name from a 0-360 hue angle, via a FINE hue wheel (v4).

    iter-8 finding (`.handoff-portfolio-4.md`): the iter-7 12-name wheel was too
    COARSE for in-between hues. Shopify's warm olive (`#468E15`, ~96°) mapped to
    the bare prototype "green", which on real Seedance yanked the whole frame to a
    bright EMERALD/TEAL (~170°) — ~74° off the brand olive — because the model
    anchors on its prototypical "green" and the bare name out-votes the hex. The
    fix is a FINER wheel with intermediate prototypes (lime, yellow-green, olive
    green, emerald, teal) so an in-between hue anchors on the NEAREST specific
    prototype instead of the nearest coarse bucket. ~96° → "olive green" (NOT
    "green"); ~82° → "lime"; ~141°/145° → "emerald green"; ~168° → "teal".

    Boundaries are placed so the two Shopify greens (raw 96.0° / saturated 95.7°)
    both land in the olive-green band, and the iter-5 saturation boost never
    crosses a band edge for the documented brand accents (hue-preserving).
    """
    if deg < 15 or deg >= 348:
        return "red"
    if deg < 33:
        return "orange"
    if deg < 45:
        return "amber"
    if deg < 56:
        return "gold"
    if deg < 64:
        return "yellow"
    if deg < 78:
        return "yellow-green"
    if deg < 88:
        return "lime"
    if deg < 106:                 # ~88-106 — Shopify olive 95.7/96.0 lives here
        return "olive green"
    if deg < 135:
        return "green"
    if deg < 158:
        return "emerald green"
    if deg < 178:
        return "teal"
    if deg < 200:
        return "cyan"
    if deg < 232:
        return "blue"
    if deg < 258:                 # Stripe #635BFF ~243° — pure-blue side
        return "blue"
    if deg < 278:
        return "indigo"
    if deg < 318:                 # aubergine #4A154B ~299° lives here
        return "purple"
    if deg < 334:
        return "magenta"
    return "pink"


# Hue bands where a DARK + MUTED variant has a well-known specific brand name that
# steers harder than the qualified base (the model knows "aubergine" as a precise
# dark-purple prototype far better than "deep muted purple"). Keyed by base name.
_DARK_MUTED_SPECIFIC = {
    "purple": "aubergine",
}


def _color_name(hex_str):
    """Map a #RRGGBB hex to a SPECIFIC human color name (v4).

    iter-7 finding: a saturated HEX alone does NOT steer the model for a MUTED
    brand hue — Shopify's olive `#5E8E3E` rendered with the model's default
    amber/purple rim even after the saturation boost. A plain-English color NAME
    is a much stronger semantic anchor than a hex string, so v3 paired the
    saturated hex with its human name in the color-dominance phrase.

    iter-8 finding (`.handoff-portfolio-4.md`): v3's NAME *over*-steered an
    in-between hue — naming Shopify olive (~96°) the bare prototype "green" pulled
    the whole real-Seedance frame to bright teal/emerald (~74° off). v4 returns a
    MORE SPECIFIC name two ways:
      1. a FINER hue wheel (`_color_hue_name`) with intermediate prototypes
         (yellow-green / lime / olive green / emerald / teal …) so an in-between
         hue anchors on the NEAREST prototype, not the nearest coarse bucket;
      2. saturation / value QUALIFIERS ("muted", "deep", "dark", "warm") so a
         dark muted brand hue is named as such (e.g. "muted olive green"), and a
         dark muted purple resolves to its specific prototype "aubergine".

    Returns a lowercase (possibly multi-word) name, or "" for unparseable /
    pure-grey / near-black input (so the caller falls back to hex-only phrasing).
    Hue is taken from HSV so the name tracks the brand identity regardless of how
    dark/muted the original was; the BASE hue name is hue-preserving through the
    iter-5 saturation boost (only the qualifier may change). Never raises.
    """
    import colorsys
    s = (hex_str or "").strip()
    m = re.fullmatch(r"#?([0-9a-fA-F]{6})", s)
    if not m:
        return ""
    digits = m.group(1)
    r = int(digits[0:2], 16) / 255.0
    g = int(digits[2:4], 16) / 255.0
    b = int(digits[4:6], 16) / 255.0
    h, sat, val = colorsys.rgb_to_hsv(r, g, b)
    if sat <= 0.08 or val <= 0.06:
        # Near-grey / near-black: no meaningful hue to name.
        return ""
    base = _color_hue_name(h * 360.0)

    # Dark + muted hues sometimes have a precise prototype the model knows well
    # (dark muted purple = "aubergine"). Prefer it over a qualified base.
    if val <= 0.45 and sat <= 0.80 and base in _DARK_MUTED_SPECIFIC:
        return _DARK_MUTED_SPECIFIC[base]

    # Lightness / saturation qualifier — only where it sharpens the steer. A muted
    # mid-tone ("muted olive green") and a dark tone ("deep teal") both read truer
    # than the bare name; a fully-saturated bright primary needs no qualifier (its
    # prototype is already unambiguous), so leave those bare to avoid over-wording.
    qual = ""
    if val <= 0.40:
        qual = "dark"
    elif sat <= 0.50 and val <= 0.72:
        qual = "muted"
    elif sat >= 0.85 and val >= 0.85:
        qual = ""  # already a vivid prototype; no qualifier
    return ("%s %s" % (qual, base)).strip()


# Color-DOMINANCE builder for the abstract/establishing track (iter-7/8 findings).
# A SATURATED hex alone under-steered for MUTED brand hues (Shopify olive read
# amber/purple even after the saturation boost) because the model's default
# cool-studio + warm-rim look beat a mere rim-light accent. The fix is to grade
# the WHOLE FRAME toward the brand accent — make the brand color the DOMINANT
# scene color, not just a rim — and to NAME the color (plain English is a stronger
# semantic anchor than a hex).
#
# iter-8 (`.handoff-portfolio-4.md`): v3 repeated the BARE name (e.g. "green") 5×
# and the hex only 1×, so a name that doesn't exactly match the brand hue
# OUT-VOTED the hex and over-steered (Shopify olive → bright teal). v4 fixes the
# imbalance two ways: (1) the name is now SPECIFIC (e.g. "olive green") from the
# finer `_color_name` wheel, and (2) we PAIR the specific name with its hex up
# front — "olive green (#468E15)" — and REPEAT the hex alongside the name later
# instead of repeating a bare generic color word many times. The model gets BOTH
# anchors (a precise word + the exact hex) at comparable weight.
#
# Built abstractly — NO text noun anywhere (so the no-positive-text-noun rule
# holds): it talks only about light, haze, reflections, and background tint.
def _color_dominance(name, hexes):
    """Build the whole-frame color-grade phrase for one brand accent.

    `name`  — SPECIFIC human color name from `_color_name` (may be "" if
              unnameable, e.g. grey/garbage).
    `hexes` — already-saturated brand hex(es) to reference; `hexes[0]` is primary.
    """
    primary = hexes[0] if hexes else ""
    if name:
        # Pair the specific name WITH the hex so neither out-weights the other.
        anchor = "%s (%s)" % (name, primary) if primary else name
        lead = "%s-dominant color grade, the entire scene bathed in %s light" % (name, anchor)
        # Repeat the hex (not a bare generic word) as the second anchor so the
        # exact brand hue — not the model's prototype of the name — is what tints
        # the whole frame.
        second = "%s (%s)" % (name, primary) if primary else name
        tint = ("its glow tinting the volumetric haze, the reflections and the "
                "background, %s as the single dominant color of the whole frame" % second)
    else:
        # No nameable hue (grey/garbage) — fall back to hex-only phrasing.
        anchor = "the brand accent (%s)" % primary if primary else "the brand accent"
        lead = "brand-accent-dominant color grade, the entire scene bathed in %s light" % anchor
        tint = ("its glow tinting the volumetric haze, the reflections and the "
                "background, %s as the single dominant color of the whole frame" % anchor)
    return lead + ", " + tint


def cinematic_prompt(brief, palette, kind):
    """Build the production prompt for a cinematic plate from the winning formula.

    `brief`   — the raw scene brief (the subject; always preserved verbatim).
    `palette` — a brand palette dict (remotion_codegen.palette_for(...)); only
                `accent` / `accent2` are consumed, and only for the "establish"
                track.
    `kind`    — "hero" (literal-UI: scaffolding only, NO anti-text) or
                "establish" (abstract: scaffolding + single-hero cue + SATURATED
                brand hex + abstract anti-text + trailing pure-negative no-text +
                title room). Any other value is treated as "establish".

    Returns a single well-formed prompt string (always starts from `brief`).

    The "establish" track bakes in the iter-5 real-Seedance learnings:
      1. SINGLE-HERO framing — one focal object, never an array of labelled cards
         (multi-element layouts reintroduced garbled caption strips).
      2. NO positive UI-text nouns anywhere — only abstract light/shape language
         in the body; the "no text" steer is a TRAILING pure-negative clause.
      3. SATURATED brand hex — the injected accent is boosted toward full
         saturation (keeping hue) + a "vivid/saturated" cue, because desaturated
         brand colors steer the model poorly (read as the wrong hue entirely).
      4. (v3) COLOR-DOMINANCE grade — the whole frame is graded toward the brand
         accent (haze/reflections/background tinted that color), and the color is
         NAMED in plain English, not just hexed. iter-7 proved a saturated hex
         alone still under-steers a MUTED brand hue (Shopify olive read amber);
         making the brand color the DOMINANT scene color (not just a rim light)
         is what finally lets a muted brand green read clearly green. Phrased
         abstractly — NO positive text noun — so the no-text rule still holds.
    """
    brief = (brief or "").strip()
    parts = [brief] if brief else []
    parts.append(_CINE_SCAFFOLD)

    if kind == "hero":
        # Literal-UI / hero plate: cinematography only. No brand-hex, no anti-text
        # — the model renders UI text legibly and a hero plate wants it readable.
        # (Hero track is gpt_image_2-only and intentionally UNCHANGED by iter-5.)
        return ". ".join(parts) + "."

    # "establish" (and any unknown kind): full abstract-plate formula.
    # 1. Single-hero / clean-composition cue (bias away from multi-element garble).
    parts.append(_SINGLE_HERO)

    # 3. Brand-accent hex — SATURATED so it steers reliably (vivid > muted).
    pal = palette or {}
    accent = (pal.get("accent") or "").strip()
    accent2 = (pal.get("accent2") or "").strip()
    hexes = [_saturate_hex(h) for h in (accent, accent2) if h]
    if hexes:
        parts.append("vivid saturated brand-accent palette: " + " and ".join(hexes)
                     + " on a deep, premium background")
        # 4. (v3) COLOR-DOMINANCE: grade the WHOLE frame toward the brand accent
        #    (named + hexed), not just a rim light. iter-7: a saturated hex alone
        #    under-steers a muted brand hue (Shopify olive read amber/purple) —
        #    making the brand color the dominant scene color is what makes even a
        #    muted brand green read clearly green. Anchored on the PRIMARY accent.
        parts.append(_color_dominance(_color_name(accent), hexes))

    # 2. Abstract anti-text body (no text nouns) + trailing PURE-NEGATIVE no-text.
    parts.append(_ANTI_TEXT)
    parts.append(_TITLE_ROOM)
    parts.append(_NO_TEXT)
    return ". ".join(parts) + "."


def _generate_cinematic_real(scene, out_path, model, company_url=None):
    """Real Higgsfield generation. Only reached in --mode real. No auto-retry.

    Stills (gpt_image_2) are one-shot; video (seedance_2_0) submits async then
    polls. Downloads the hosted asset to out_path. Mirrors higgsfield-scene.

    The raw scene `brief` is the SUBJECT only — it is wrapped by
    `cinematic_prompt(...)` into the winning two-track production formula
    (cinematography scaffolding for hero plates; + brand hex + anti-text + title
    room for establishing plates). The brand palette is resolved from
    `company_url` (falling back to scene["company_url"]) via
    remotion_codegen.palette_for so the brand's accent hexes steer establishing
    plates without any new wiring at the call site.
    """
    brief = scene.get("brief", "")
    if not brief:
        raise AdapterError("cinematic scene %r has no brief" % scene.get("id"))
    kind = detect_kind(scene)
    palette = remotion_codegen.palette_for(company_url or scene.get("company_url"))
    prompt = cinematic_prompt(brief, palette, kind)
    status = _run(["higgsfield", "account", "status"], timeout=30, check=False)
    if status.returncode != 0:
        raise AdapterError("higgsfield not authenticated — run `higgsfield auth login` (no paid retry)")

    if model == "gpt_image_2":
        proc = _run(["higgsfield", "generate", "create", model, "--prompt", prompt,
                     "--aspect_ratio", "16:9", "--resolution", "2k", "--wait", "--json"],
                    timeout=600)
        url = _extract_asset_url(proc.stdout)
        # Persist the asset url before download so the (paid) still is recoverable at
        # $0 if the curl/ffmpeg step below fails. Still jobs use --wait, so the job id
        # (if present in the response) is best-effort.
        _persist_higgsfield_artifact(out_path, scene, model, proc.stdout,
                                     job_id=_extract_job_id(proc.stdout), asset_url=url)
        png = out_path.rsplit(".", 1)[0] + ".png"
        _run(["curl", "-fsSL", url, "-o", png], timeout=120)
        # Turn the still into a clip of the scene's duration.
        dur = max(1, int(scene.get("duration_s", 6)))
        _run(["ffmpeg", "-y", "-nostdin", "-loglevel", "error", "-loop", "1", "-i", png,
              "-t", str(dur), "-vf", "scale=%d:%d,format=yuv420p,setsar=1" % (W, H),
              "-r", str(FPS), "-c:v", "libx264", "-crf", "18", "-preset", "medium",
              "-movflags", "+faststart", out_path], timeout=300)
        return {"output_path": out_path, "model": model, "real": True, "asset_url": url}

    # Video: submit async, capture id, poll, download.
    sub = _run(["higgsfield", "generate", "create", model, "--prompt", prompt,
                "--duration", str(min(15, max(4, int(scene.get("duration_s", 6))))),
                "--aspect_ratio", "16:9", "--json"], timeout=120)
    job_id = _extract_job_id(sub.stdout)
    if not job_id:
        # The submit may already have spent credits server-side; persist the raw
        # response so the (paid) job is recoverable, and surface the raw text so a
        # parse miss is debuggable instead of a dead-end "could not parse".
        _persist_higgsfield_artifact(out_path, scene, model, sub.stdout, job_id=None)
        raise AdapterError(
            "could not parse higgsfield job id for scene %r — raw `generate create` "
            "response was: %s" % (scene.get("id"), _truncate(sub.stdout)))
    # Persist job_id + raw response IMMEDIATELY, before wait/download, so a later
    # failure (poll timeout, curl error) never silently loses already-paid work.
    # See PRODUCTION-READINESS-REVIEW §4.5 / recommendation #5.
    _persist_higgsfield_artifact(out_path, scene, model, sub.stdout, job_id=job_id)
    _run(["higgsfield", "generate", "wait", job_id, "--timeout", "20m", "--interval", "5s", "--json"],
         timeout=1300)
    got = _run(["higgsfield", "generate", "get", job_id, "--json"], timeout=60)
    url = _extract_asset_url(got.stdout)
    # Re-persist with the resolved asset_url so the clip is recoverable at $0 even if
    # the download below fails (downloading an already-generated asset costs no credits).
    _persist_higgsfield_artifact(out_path, scene, model, got.stdout, job_id=job_id, asset_url=url)
    _run(["curl", "-fsSL", url, "-o", out_path], timeout=300)
    return {"output_path": out_path, "model": model, "real": True, "asset_url": url, "job_id": job_id}


# Keys the higgsfield CLI uses for a generation job id. The native binary's JSON
# struct tags carry BOTH `id` and `job_id`; wrapper/plural variants are handled too.
# (Verified against `higgsfield generate get/list --json` live output + binary tags,
# v0.1.34. The exact `generate create` *without* --wait wrapper is documented as
# "you get the job IDs" — shape unconfirmed without spending, so we search broadly.)
_JOB_ID_KEYS = ("id", "job_id", "jobId", "job_set_id", "jobSetId", "jobSetID")
_JOB_ID_LIST_KEYS = ("ids", "job_ids", "jobIds", "jobs", "job_sets", "data", "results", "items")
_ASSET_URL_KEYS = ("result_url", "url", "video_url", "asset_url", "preview_url")
# A higgsfield job id is a UUID. Used to validate scraped candidates and as a
# last-resort scan of non-JSON / partially-JSON output.
_UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


def _looks_like_job_id(val):
    return isinstance(val, str) and bool(_UUID_RE.fullmatch(val.strip()))


def _extract_job_id(stdout):
    """Pull a job id out of a `generate create` response, defensively.

    Handles every plausible shape of the (no --wait) submit response:
      - bare UUID string (possibly quoted, possibly newline-delimited list of ids)
      - single job object  {"id": "<uuid>", ...} / {"job_id": "<uuid>", ...}
      - array of job objects  [{"id": "<uuid>", ...}, ...]
      - wrapper object  {"jobs": [{"id": ...}]} / {"job_ids": ["<uuid>"]} / {"ids": [...]}
    Returns the first UUID-shaped id found, or None (never raises — the caller
    decides whether a None is fatal and gets to log the raw response).
    """
    if not stdout or not stdout.strip():
        return None
    text = stdout.strip()
    try:
        d = json.loads(text)
    except (ValueError, json.JSONDecodeError):
        # Not JSON (or only partially) — fall back to scanning for the first UUID
        # so a plain-text "Created job <uuid>" line still works.
        m = _UUID_RE.search(text)
        return m.group(0) if m else None
    jid = _find_job_id(d)
    if jid:
        return jid
    # Parsed fine but no id key matched — last resort: scan the raw text for a UUID.
    m = _UUID_RE.search(text)
    return m.group(0) if m else None


def _find_job_id(node, _depth=0):
    """Recursively locate the first UUID-shaped job id under a known id key."""
    if _depth > 6:
        return None
    if _looks_like_job_id(node):
        return node.strip()
    if isinstance(node, list):
        for item in node:
            jid = _find_job_id(item, _depth + 1)
            if jid:
                return jid
        return None
    if isinstance(node, dict):
        # Prefer an explicit id key on this object.
        for k in _JOB_ID_KEYS:
            if _looks_like_job_id(node.get(k)):
                return node[k].strip()
        # Then known list/wrapper keys (ids could be bare strings or nested objects).
        for k in _JOB_ID_LIST_KEYS:
            if k in node:
                jid = _find_job_id(node[k], _depth + 1)
                if jid:
                    return jid
        # Finally, descend into any remaining values (catches unforeseen wrappers).
        for v in node.values():
            if isinstance(v, (dict, list)):
                jid = _find_job_id(v, _depth + 1)
                if jid:
                    return jid
    return None


def _extract_asset_url(stdout):
    try:
        d = json.loads(stdout)
    except (ValueError, json.JSONDecodeError):
        raise AdapterError(
            "higgsfield returned non-JSON asset response: %s" % _truncate(stdout))
    url = _find_asset_url(d)
    if not url:
        raise AdapterError("no asset url in higgsfield result: %s" % _truncate(stdout))
    return url


def _find_asset_url(node, _depth=0):
    """Recursively locate the first http(s) asset URL under a known url key."""
    if _depth > 6:
        return None
    if isinstance(node, str):
        return node if node.startswith("http") else None
    if isinstance(node, list):
        for item in node:
            url = _find_asset_url(item, _depth + 1)
            if url:
                return url
        return None
    if isinstance(node, dict):
        for k in _ASSET_URL_KEYS:
            v = node.get(k)
            if isinstance(v, str) and v.startswith("http"):
                return v
        for k in ("results", "data", "items", "jobs"):
            if k in node:
                url = _find_asset_url(node[k], _depth + 1)
                if url:
                    return url
        for v in node.values():
            if isinstance(v, (dict, list)):
                url = _find_asset_url(v, _depth + 1)
                if url:
                    return url
    return None


def _truncate(s, limit=1200):
    s = (s or "").strip()
    return s if len(s) <= limit else s[:limit] + "… [truncated %d chars]" % (len(s) - limit)


def _as_text(v):
    """Coerce subprocess stdout/stderr (str | bytes | None) to a str."""
    if v is None:
        return ""
    if isinstance(v, bytes):
        return v.decode("utf-8", "replace")
    return str(v)


def _persist_higgsfield_artifact(out_path, scene, model, raw_response, job_id=None, asset_url=None):
    """Write a sidecar JSON next to the clip recording the raw higgsfield response,
    job_id and asset_url AS SOON AS they're known — before any wait/download — so a
    later failure never loses already-paid work (prod-review §4.5). Best-effort: a
    failure to persist must not mask the real generation error, so it's swallowed.
    """
    try:
        path = out_path.rsplit(".", 1)[0] + ".higgsfield.json"
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        record = {
            "scene_id": scene.get("id"),
            "model": model,
            "job_id": job_id,
            "asset_url": asset_url,
            "persisted_at": time.time(),
            "raw_response": _truncate(raw_response, limit=20000),
        }
        # Merge rather than clobber: the second (resolved) call should not erase the
        # submit-time record if it somehow carries less info.
        if os.path.exists(path):
            try:
                with open(path) as f:
                    prev = json.load(f)
                record["job_id"] = record["job_id"] or prev.get("job_id")
                record["asset_url"] = record["asset_url"] or prev.get("asset_url")
            except (ValueError, OSError):
                pass
        with open(path, "w") as f:
            json.dump(record, f, indent=2)
        return path
    except OSError:
        return None


# ---------------------------------------------------------------------------
# Walkthrough (walk-agent). FREE but slow. Mock AND real run the SAME genuine
# walk_native capture (a $0 mock build matches a paid Standard build); they
# differ only in payment + brain. The synth color card is a last-resort fallback
# (mock only) when the native capture fails.
# ---------------------------------------------------------------------------

def _norm_hex(color, fallback):
    """Coerce a palette color (possibly '#RRGGBB' or 'RRGGBB' or None) to the bare
    6-hex-digit form synth_clip wants (it formats `color=c=0x%s`). Falls back to
    `fallback` (already bare) when the input is missing or not a clean hex triple."""
    s = (color or "").strip().lstrip("#")
    if len(s) == 6 and all(c in "0123456789abcdefABCDEF" for c in s):
        return s.upper()
    return fallback


def _salvage_walk_frames(run_dir, out_path, duration):
    """Parent-side recovery (R2 gap-3): stitch the screencast frames walk_native
    already captured into <run_dir>/walk/frames/f*.jpg into a real clip at out_path.

    walk_native streams a live CDP screencast frame-by-frame, but the FINAL stitch
    runs only after the smart-nav loop finishes. When the subprocess hits the parent
    timeout (or the child's SIGALRM fires inside a Playwright/ffmpeg call and the
    `finally`-stitch never completes before the parent SIGKILLs it), the mp4 is never
    written — yet dozens of genuine frames of the brand's real UI are sitting on disk
    (R1: 140 real Stripe frames abandoned). This salvages them into a REAL walkthrough
    instead of dropping the scene to a flat placeholder.

    Returns True on a valid mp4 written to out_path, else False (caller then falls
    back to the synth placeholder / scene-drop). Never raises."""
    if not run_dir:
        return False
    import glob
    frames_dir = os.path.join(run_dir, "walk", "frames")
    if not os.path.isdir(frames_dir):
        return False
    pics = sorted(glob.glob(os.path.join(frames_dir, "f*.jpg")))
    # Need enough frames to read as motion, not a 1-frame freeze. 8 ~= <1s of footage.
    if len(pics) < 8:
        return False
    try:
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
        dur = max(2.0, float(duration or 12))
        # framerate so the clip length ~= duration, kept watchable (matches
        # walk_native._stitch's 8-18fps clamp).
        fps = max(8.0, min(18.0, len(pics) / dur))
        cmd = [
            "ffmpeg", "-y", "-nostdin", "-loglevel", "error",
            "-framerate", "%.4f" % fps,
            "-pattern_type", "glob", "-i", os.path.join(frames_dir, "f*.jpg"),
            "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2,format=yuv420p,setsar=1",
            "-c:v", "libx264", "-crf", "20", "-preset", "veryfast", "-an",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", out_path,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=120, check=False)
    except Exception:
        return False
    return (proc.returncode == 0 and os.path.exists(out_path)
            and os.path.getsize(out_path) > 1000)


def generate_walkthrough(scene, out_path, mode, job_url=None, run_dir=None,
                         accent_hex=None):
    # CACHE OVERRIDE (mode-independent, $0/no-NIM): if WS_WALKTHROUGH_CACHE points at
    # an existing mp4, use THAT clip instead of synthesizing (mock) or running
    # walk-agent (real). The cached clip is re-encoded with +faststart into the run's
    # out_path so OffthreadVideo can seek it. This is the verification path — a real
    # walk-agent capture is proven; reusing the cached clip spends nothing.
    cache = (os.environ.get("WS_WALKTHROUGH_CACHE") or "").strip()
    if cache and os.path.exists(cache):
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
        try:
            _run([
                "ffmpeg", "-y", "-nostdin", "-loglevel", "error", "-i", cache,
                "-c", "copy", "-movflags", "+faststart", out_path,
            ], timeout=120)
        except Exception:
            # stream-copy can fail on odd containers; fall back to a real re-encode.
            _run([
                "ffmpeg", "-y", "-nostdin", "-loglevel", "error", "-i", cache,
                "-c:v", "libx264", "-crf", "20", "-preset", "veryfast", "-an",
                "-movflags", "+faststart", out_path,
            ], timeout=300)
        if not os.path.exists(out_path) or os.path.getsize(out_path) < 1000:
            raise AdapterError("walkthrough cache re-encode produced no output: %s" % out_path)
        # A cached clip is a PROVEN real walk-agent capture being reused ($0 verify
        # path) — NOT a synthetic placeholder. Mark it so the orchestrator keeps it
        # (and its narrated VO beat) just like a fresh real capture.
        return {"output_path": out_path, "real": False, "cached": True,
                "placeholder": False}

    # NATIVE-CAPTURE DECISION. The genuine walk_native capture runs whenever we want a
    # real per-brand walkthrough: ALWAYS in real mode, and in MOCK mode for every real
    # product build (build_runner.run sets WS_WALKTHROUGH_NATIVE=1). That makes a $0
    # mock build produce exactly the SAME walkthrough a paying Standard customer gets —
    # mock and real differ only in payment (mock keeps PRODUCER_SIMULATE_PAID) and brain
    # ($0 super-free), not in the walkthrough asset.
    #
    # When the flag is NOT set and mode is mock (the offline orchestrator-judgment unit
    # tests, which call orchestrate directly and never set the flag), we keep the fast
    # deterministic SYNTH placeholder card so the suite stays $0/offline/green and never
    # launches a live browser capture against the scenario URL.
    native_walkthrough = (mode == "real") or bool(
        (os.environ.get("WS_WALKTHROUGH_NATIVE") or "").strip())
    if not native_walkthrough:
        # SYNTHETIC PLACEHOLDER (test/offline mock): a solid brand-accent color card,
        # NOT a real per-brand capture. placeholder:True -> the orchestrator's gate
        # drops the scene + its VO beat (same as a real-mode skip).
        color = _norm_hex(accent_hex, TYPE_COLOR["walkthrough"])
        synth_clip(out_path, color, scene.get("duration_s", 10))
        return {"output_path": out_path, "real": False, "placeholder": True,
                "synth_color": color}
    # MODE-INDEPENDENT NATIVE CAPTURE: both mock (real product builds) and real run the
    # GENUINE per-brand walk_native capture (the same code path). The synthetic color
    # card is now a LAST-RESORT FALLBACK reached only when the native capture genuinely
    # fails (see _walkthrough_fallback below).
    #
    # walk_native is a clean OUR-python Playwright subprocess (.venv-capture) — the
    # SAME venv capture_screenshots uses — with default close_fds and a hard timeout,
    # so it cannot inherit a gateway pipe and cannot hang the caller. (This REPLACES
    # the old tutorial-maker.sh → NemoClaw-sandbox path, which DEADLOCKED on a pipe
    # held open by the openshell-gateway daemon.) It also streams a live CDP screencast
    # into <run_dir>/walk/ (frame.jpg + state.json) for the dashboard.
    #
    # NON-FATAL: on any failure, REAL mode returns a graceful-SKIP sentinel (None) so
    # the orchestrator drops just this scene and still ships the build; MOCK mode falls
    # back to the synthetic placeholder card (placeholder:True) so a test build never
    # crashes. Either way the orchestrator's placeholder/None gate drops the scene + its
    # VO beat, so mock and real degrade identically (no brand VO over generic footage).
    def _walkthrough_fallback():
        # R2 gap-3: BEFORE degrading to a placeholder/skip, try to SALVAGE the real
        # screencast frames walk_native already captured (a timeout/kill loses only
        # the final stitch, not the frames on disk). A successful salvage is a GENUINE
        # per-brand capture (real:True), so the orchestrator keeps the scene + its VO.
        if _salvage_walk_frames(rd, out_path, scene.get("duration_s", 12)):
            return {"output_path": out_path, "real": True, "native": True,
                    "placeholder": False, "salvaged": True}
        # In MOCK, never crash on a failed native capture — emit the brand-tinted
        # synthetic card as a last resort (placeholder:True -> orchestrator drops it,
        # same as a real-mode skip). In REAL, the contract is graceful-skip (None).
        if mode == "mock":
            color = _norm_hex(accent_hex, TYPE_COLOR["walkthrough"])
            synth_clip(out_path, color, scene.get("duration_s", 10))
            return {"output_path": out_path, "real": False, "placeholder": True,
                    "synth_color": color}
        return None

    import capture_screenshots  # exposes CAPTURE_PY (.venv-capture/bin/python)
    url = job_url or scene.get("input_image") or ""
    goal = scene.get("brief", "") or ""
    emphasis = scene.get("emphasis") or scene.get("brief", "") or ""
    duration = str(int(scene.get("duration_s", 12) or 12))
    rd = run_dir or _run_dir_from_out(out_path) or os.path.dirname(
        os.path.dirname(os.path.abspath(out_path)))
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)

    capture_py = capture_screenshots.CAPTURE_PY
    script = os.path.join(HERE, "walk_native.py")
    if not os.path.exists(capture_py) or not os.path.exists(script):
        # No Playwright venv / script → last-resort fallback (skip in real).
        return _walkthrough_fallback()
    try:
        # Parent timeout 230s > the child's own 190s SIGALRM wall-clock guard, so the
        # child's `finally`-stitch has ~40s of headroom to write the mp4 before the
        # parent kills it (the old 200s left only 10s and routinely lost the frames —
        # R1). If the child STILL fails to stitch in time, _walkthrough_fallback
        # salvages the on-disk frames parent-side.
        proc = subprocess.run(
            [capture_py, script, url, goal, emphasis, out_path, rd, duration],
            capture_output=True, text=True, timeout=230, check=False)
    except subprocess.TimeoutExpired as e:
        # TimeoutExpired has stdout/stderr (maybe bytes) but no .returncode, so
        # wrap it in a tiny shim _write_walkagent_log can consume uniformly.
        shim = types.SimpleNamespace(
            returncode="timeout",
            stdout=_as_text(getattr(e, "stdout", None)),
            stderr=_as_text(getattr(e, "stderr", None)) or "walk_native timed out (>230s)")
        _write_walkagent_log(out_path, scene, shim, url, goal)
        return _walkthrough_fallback()  # never raise — fall back / drop the scene
    # Success requires a real mp4; otherwise last-resort fallback (skip in real).
    if proc.returncode == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 1000:
        # GENUINE per-brand capture — explicitly NOT a placeholder, so the
        # orchestrator keeps the scene + its narrated VO beat. Same in mock and real.
        return {"output_path": out_path, "real": True, "native": True,
                "placeholder": False}
    # Capture the cause to a sidecar log (same forensic trail as before) but DO
    # NOT raise — the walkthrough is non-fatal by contract.
    _write_walkagent_log(out_path, scene, proc, url, goal)
    return _walkthrough_fallback()


def generate_screenshots(url, out_dir, mode="mock", max_shots=2):
    """Capture REAL website screenshots for the apple-screenshot archetype.

    LIKE generate_walkthrough (now mode-independent native capture), screenshots
    ALWAYS do real headless-browser capture regardless of mode — they are $0 +
    deterministic, so a mock build shows the real site too.

    On capture failure (bot-blocked or no Playwright): fall back to POPULATED,
    BRAND-TINTED mock cards — one "home/hero" layout (slot 0) and one
    "feature/list" layout (slot 1).  Both are distinct (different md5s) and
    visually represent the brand via its accent colour.  Never a black box or
    an empty "Brand" card again (R3-B fix).

    Returns the capture manifest dict
    {"url","count","shots":[{file,path,url,label,...}],"ok", "real": bool}.
    On capture failure: {"ok": False, "real": False, "shots": [...mocks...], "error": str}.
    """
    import capture_screenshots
    os.makedirs(out_dir, exist_ok=True)
    try:
        manifest = capture_screenshots.capture_url(url, out_dir, max_shots=max_shots)
        manifest["real"] = True
        return manifest
    except Exception as e:
        # Capture failed (no Playwright, bot-blocked, unreachable, etc.).
        # R3-B: instead of a solid-black box, render 2 populated brand-tinted
        # mock cards that DIFFER structurally so the two apple-screenshot scenes
        # are visually distinct (different layouts -> different md5s).
        shots = []
        n_mocks = max(1, int(max_shots))
        for slot in range(n_mocks):
            fname = "shot-%02d.png" % (slot + 1)
            mock_path = os.path.join(out_dir, fname)
            try:
                _brand_mock_png(mock_path, url, slot)
                size = os.path.getsize(mock_path) if os.path.exists(mock_path) else 0
                shots.append({
                    "index": slot + 1,
                    "file": fname,
                    "path": mock_path,
                    "url": url,
                    "label": "mock-home" if slot == 0 else "mock-list",
                    "title": "",
                    "bytes": size,
                    "mock": True,
                })
            except Exception as e2:
                # Ultra-fallback: solid colour card (black box is gone; this
                # colour is at least a neutral slate, not opaque black).
                try:
                    _synth_card_png(mock_path, "1A2436")
                    size = os.path.getsize(mock_path) if os.path.exists(mock_path) else 0
                    shots.append({
                        "index": slot + 1, "file": fname, "path": mock_path,
                        "url": url, "label": "synth-floor", "title": "",
                        "bytes": size, "mock": True,
                        "note": "brand-mock failed: %s" % e2,
                    })
                except Exception:
                    pass
        manifest = {"url": url, "count": len(shots), "shots": shots,
                    "ok": False, "real": False, "error": str(e)}
        with open(os.path.join(out_dir, "manifest.json"), "w") as fh:
            json.dump(manifest, fh, indent=2)
        return manifest


def generate_screenshot_clip(scene, out_path, mode, shots_dir=None):
    """A short clip for a `screenshot` scene from a captured shot-NN.png.

    The captured PNG (runs/<id>/screenshots/shot-NN.png) is scaled/padded to the
    frame spec and held for the scene duration. Mode-INDEPENDENT (screenshots are
    $0 deterministic). The orchestrator's clip is bookkeeping — the customer-facing
    picture is the VO-engine Timeline render (the apple-screenshot archetype), which
    shows the same PNG inside a branded browser card. Falls back to a synth color
    card if no screenshot is available so the scene is never blank.

    `shots_dir` defaults to <run_dir>/screenshots derived from out_path's grandparent
    (clips/ -> run_dir). Picks the shot by the scene's 0-based screenshot index when
    present (scene["_shot_index"]), else the first shot.
    """
    dur = scene.get("duration_s", 5)
    if not shots_dir:
        # out_path is runs/<id>/clips/NN_<sid>.mp4 -> run_dir is two levels up.
        run_dir = os.path.dirname(os.path.dirname(os.path.abspath(out_path)))
        shots_dir = os.path.join(run_dir, "screenshots")
    shot_path = None
    manifest_path = os.path.join(shots_dir, "manifest.json")
    shots = []
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path) as f:
                shots = (json.load(f).get("shots") or [])
        except (OSError, ValueError):
            shots = []
    idx = int(scene.get("_shot_index", 0) or 0)
    if shots:
        s = shots[idx] if idx < len(shots) else shots[0]
        cand = s.get("path") or os.path.join(shots_dir, s.get("file", ""))
        if cand and os.path.exists(cand):
            shot_path = cand
    if not shot_path and os.path.isdir(shots_dir):
        import glob
        pics = sorted(glob.glob(os.path.join(shots_dir, "shot-*.png")))
        if pics:
            shot_path = pics[idx] if idx < len(pics) else pics[0]
    if not shot_path:
        # never-blank floor: a synth card so the scene still ships a clip.
        synth_clip(out_path, TYPE_COLOR.get("title", "0A0D0C"), dur)
        return {"output_path": out_path, "real": False, "note": "no screenshot captured"}

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    d = max(1, int(dur))
    _run([
        "ffmpeg", "-y", "-nostdin", "-loglevel", "error",
        "-loop", "1", "-t", "%d" % d, "-i", shot_path,
        "-vf", ("scale=%d:%d:force_original_aspect_ratio=decrease,"
                "pad=%d:%d:(ow-iw)/2:(oh-ih)/2:color=white,format=yuv420p,setsar=1"
                % (W, H, W, H)),
        "-r", "%d" % FPS, "-c:v", "libx264", "-crf", "20", "-preset", "veryfast",
        "-movflags", "+faststart", out_path,
    ], timeout=120)
    if not os.path.exists(out_path) or os.path.getsize(out_path) < 1000:
        raise AdapterError("screenshot clip produced no output: %s" % out_path)
    return {"output_path": out_path, "real": True, "screenshot": shot_path}


def _synth_card_png(out_path, color_hex):
    """A single solid-color PNG (bare capture-failure floor). Uses ffmpeg so we don't
    take a PIL dependency. Real PNG at the shared frame spec.

    NOTE: callers that have brand context should use _brand_mock_png() instead —
    it produces a populated, brand-tinted card rather than a solid-color box.
    This is kept for non-brand contexts (e.g. format-cut stubs, test helpers).
    """
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    _run([
        "ffmpeg", "-y", "-nostdin", "-loglevel", "error",
        "-f", "lavfi", "-i", "color=c=0x%s:s=%dx%d:d=1" % (color_hex, W, H),
        "-frames:v", "1", out_path,
    ], timeout=30)
    if not os.path.exists(out_path) or os.path.getsize(out_path) < 200:
        raise AdapterError("synth card png produced no output: %s" % out_path)
    return out_path


# ---------------------------------------------------------------------------
# Brand-tinted mock card (R3-B / R10-Y): the populated placeholder the
# apple-screenshot scene shows when real capture fails / is bot-blocked
# (shopify, tripadvisor.com.tw, huckberry all bot-wall the headless browser).
#
# It is a BRANDED PLACEHOLDER, never a claimed real screenshot. The bar (Dim-5):
# it must read as a populated product SURFACE, not an empty green skeleton.
#
# Design goals:
#   1. ON-BRAND ACCENT — the mock's accent is the brand's REAL extracted accent
#      (huckberry rust #BE512D, shopify green #96BF48, tripadvisor green
#      #34E0A1) so the card MATCHES the rest of the video, NOT a generic green.
#      The real accent lives in runs/<id>/brand_theme.json (palette.accent) the
#      brand-extract step already wrote — `palette_for()` only knows the dark
#      mint `_default`, which is the source of the old "generic green" bug.
#   2. POPULATED — a genre-appropriate product scaffold: an e-commerce listing
#      grid (filled card tiles + product labels + price chips) for retail
#      brands, or a review/listing feed (rated rows + score badges) for travel
#      brands, under a header bar carrying the real brand WORDMARK. Solid filled
#      elements with realistic proportions + a couple of plausible numbers
#      (prices / ratings), NOT empty outline bars.
#   3. DE-DUPLICATED — slot 0 ("home / catalog") and slot 1 ("feature / detail")
#      differ structurally so the two apple-screenshot scenes look different.
#
# Rendered with Pillow (real text: wordmark + labels + price/rating numbers).
# Falls back to an ffmpeg drawbox card if Pillow is unavailable (ffmpeg here has
# no drawtext, so that path is text-free — Pillow is the primary path).
# ---------------------------------------------------------------------------

# Known-brand accent map (by normalised hostname token) — the LAST resort if a
# run-local brand_theme.json is unavailable. Covers the full 12-brand roster so
# the mock is on-brand even outside a build dir. Hex with leading '#'.
_BRAND_ACCENT_FALLBACK = {
    "tripadvisor": "#34E0A1",   # TripAdvisor green
    "shopify": "#96BF48",       # Shopify lime-green
    "huckberry": "#BE512D",     # Huckberry rust/clay
    "stripe": "#635BFF",        # Stripe indigo
    "linear": "#5E6AD2",        # Linear purple-blue
    "plaid": "#1D64DC",         # Plaid blue
    "vercel": "#111111",        # Vercel mono (near-black; brand-true)
    "notion": "#2383E2",        # Notion blue
    "allbirds": "#F0C511",      # Allbirds yellow
    "airbnb": "#FF385C",        # Airbnb rausch/coral
    "theverge": "#BE2D62",      # The Verge magenta
    "webflow": "#146EF5",       # Webflow blue
}

# Genre signal by hostname token → which scaffold the mock draws. Travel and
# media read as review/listing feeds; retail/e-commerce read as product grids;
# everything else gets a generic SaaS dashboard scaffold.
_BRAND_GENRE = {
    "shopify": "shop", "huckberry": "shop", "allbirds": "shop",
    "tripadvisor": "travel", "airbnb": "travel",
    "theverge": "media",
}

# Per-genre realistic, on-brand-but-generic placeholder content. Short labels
# (NOT lorem ipsum) + plausible numbers (price / rating). Used to populate the
# scaffold; the wordmark itself comes from the real brand name.
_MOCK_CONTENT = {
    "shop": {
        "nav": ["Shop", "New", "Collections", "Sale"],
        "hero": "Shop the new arrivals",
        "sub": "Free shipping over $75 · 30-day returns",
        "cta": "Shop now",
        "cards": [
            ("Field Jacket", "$148"), ("Waxed Canvas Bag", "$98"),
            ("Merino Crewneck", "$72"), ("Trail Boots", "$215"),
            ("Flannel Shirt", "$64"), ("Leather Wallet", "$58"),
            ("Wool Beanie", "$34"), ("Insulated Flask", "$42"),
        ],
        "rows": [
            ("Best Sellers", "Shop the most-loved gear", "$58–$215"),
            ("New This Week", "Fresh drops from the workshop", "32 items"),
            ("Last Chance", "Final markdowns, while they last", "Up to 40% off"),
        ],
    },
    "travel": {
        "nav": ["Hotels", "Things to Do", "Restaurants", "Forums"],
        "hero": "Find your next stay",
        "sub": "Compare prices across 1M+ hotels worldwide",
        "cta": "Search hotels",
        "cards": [
            ("Harbor View Hotel", "4.8"), ("Old Town Guesthouse", "4.6"),
            ("Seaside Resort & Spa", "4.9"), ("City Center Suites", "4.5"),
            ("Mountain Lodge", "4.7"), ("Riverside Inn", "4.4"),
            ("Boutique Hotel No. 9", "4.8"), ("Grand Plaza", "4.6"),
        ],
        "rows": [
            ("Harbor View Hotel", "1,284 traveler reviews · Free cancellation", "4.8"),
            ("Old Town Guesthouse", "902 reviews · Breakfast included", "4.6"),
            ("Seaside Resort & Spa", "3,517 reviews · Beachfront", "4.9"),
        ],
    },
    "media": {
        "nav": ["Tech", "Reviews", "Science", "Video"],
        "hero": "The latest in tech",
        "sub": "Reviews, news, and how the future is made",
        "cta": "Read more",
        "cards": [
            ("The week in gadgets", "Reviews"), ("Inside the new chip", "Feature"),
            ("Hands-on first look", "Hands-on"), ("The state of AI", "Analysis"),
            ("Best laptops 2026", "Buyer's guide"), ("What we're watching", "Culture"),
            ("Space, explained", "Science"), ("The big interview", "Interview"),
        ],
        "rows": [
            ("Hands-on with the new flagship", "12 min read · Reviews", "★ Editor's pick"),
            ("The chip race heats up", "8 min read · Analysis", "Trending"),
            ("Everything announced today", "5 min read · News", "Live"),
        ],
    },
    "saas": {
        "nav": ["Product", "Solutions", "Pricing", "Docs"],
        "hero": "Build faster, ship sooner",
        "sub": "The platform teams trust to move quickly",
        "cta": "Get started",
        "cards": [
            ("Active projects", "24"), ("Deploys today", "318"),
            ("Avg build time", "1.4s"), ("Uptime", "99.99%"),
            ("Team members", "57"), ("Open issues", "12"),
            ("Requests / min", "9.2k"), ("P95 latency", "84ms"),
        ],
        "rows": [
            ("Workspace overview", "All projects, one dashboard", "24 active"),
            ("Recent activity", "Deploys, builds, and reviews", "Live"),
            ("Usage this month", "Within plan limits", "62%"),
        ],
    },
}


def _hex_to_rgb(hex_str: str):
    """Parse '#RRGGBB' or 'RRGGBB' -> (r, g, b) ints. Returns (79,110,245) on error."""
    s = (hex_str or "").strip().lstrip("#")
    if len(s) != 6:
        return (79, 110, 245)
    try:
        return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
    except ValueError:
        return (79, 110, 245)


def _mix_rgb(a, b, t):
    """Linear blend of two (r,g,b) tuples; t=0 -> a, t=1 -> b."""
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def _relative_luminance(rgb):
    """Perceptual luminance 0..1 (sRGB approximation) for contrast decisions."""
    r, g, b = (c / 255.0 for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _on_accent_text(accent_rgb):
    """Pick white or near-black text that reads on the accent (contrast)."""
    return (17, 17, 17) if _relative_luminance(accent_rgb) > 0.6 else (255, 255, 255)


def _run_dir_from_out(out_path: str) -> str:
    """out_path is <run_dir>/screenshots/shot-NN.png → return <run_dir> (or '')."""
    try:
        screenshots_dir = os.path.dirname(os.path.abspath(out_path))
        return os.path.dirname(screenshots_dir)
    except Exception:
        return ""


def _accent_from_brand_theme(run_dir: str) -> str:
    """Read the REAL extracted accent from <run_dir>/brand_theme.json (palette.accent).

    This is the canonical brand accent the rest of the video uses, so the mock
    matches it. Returns '' when no usable accent is found.
    """
    if not run_dir:
        return ""
    path = os.path.join(run_dir, "brand_theme.json")
    if not os.path.exists(path):
        return ""
    try:
        with open(path) as f:
            theme = json.load(f)
    except (OSError, ValueError):
        return ""
    pal = theme.get("palette") if isinstance(theme, dict) else None
    accent = ""
    if isinstance(pal, dict):
        accent = (pal.get("accent") or "").strip()
    if not accent and isinstance(theme, dict):
        accent = (theme.get("accent") or "").strip()
    return accent


def _wordmark_from_brand_theme(run_dir: str) -> str:
    """Read the real brand display name from <run_dir>/brand_theme.json."""
    if not run_dir:
        return ""
    path = os.path.join(run_dir, "brand_theme.json")
    if not os.path.exists(path):
        return ""
    try:
        with open(path) as f:
            theme = json.load(f)
    except (OSError, ValueError):
        return ""
    if not isinstance(theme, dict):
        return ""
    name = (theme.get("wordmark") or theme.get("name") or theme.get("brand") or "").strip()
    if name.lower() in ("", "the product"):
        return ""
    return name


def _host_token(url: str) -> str:
    """Normalised brand token from a URL host: tripadvisor.com.tw -> 'tripadvisor'."""
    try:
        return remotion_codegen._brand_name(url).lower()
    except Exception:
        try:
            from urllib.parse import urlparse
            host = urlparse(url).netloc.lower().lstrip("www.")
            return host.split(".")[0] if host else ""
        except Exception:
            return ""


def _is_default_palette_accent(url: str, accent: str) -> bool:
    """True when `accent` is just the generic dark-mint `_default` (the green bug)."""
    try:
        pal = remotion_codegen.palette_for(url)
        if pal.get("_brand") in (None, "", "generic"):
            return True  # _default palette -> its accent is the generic green
    except Exception:
        pass
    return (accent or "").strip().lower() == "#7cffb2"


def _brand_accent_for_url(url: str, run_dir: str = "") -> str:
    """Resolve the REAL brand accent for the mock, never the generic green default.

    Priority: (1) the run's brand_theme.json palette.accent (what the rest of the
    video uses), (2) the curated known-brand map, (3) palette_for() ONLY when it
    matched a real BRAND_PALETTES entry (NOT _default), (4) a generic blue.
    """
    # 1. Run-local extracted accent (canonical — matches the video).
    accent = _accent_from_brand_theme(run_dir)
    if accent:
        return accent
    # 2. Curated known-brand map (covers the bot-blocked roster incl. huckberry).
    token = _host_token(url)
    if token and token in _BRAND_ACCENT_FALLBACK:
        return _BRAND_ACCENT_FALLBACK[token]
    # 2b. Substring match for hosts the token split missed.
    try:
        from urllib.parse import urlparse
        host = urlparse(url).netloc.lower()
        for brand, color in _BRAND_ACCENT_FALLBACK.items():
            if brand in host:
                return color
    except Exception:
        pass
    # 3. palette_for(), but ONLY a real brand entry — skip the _default green.
    try:
        pal = remotion_codegen.palette_for(url)
        cand = (pal.get("accent") or "").strip()
        if cand and pal.get("_brand") not in (None, "", "generic"):
            return cand
    except Exception:
        pass
    # 4. Generic blue (last resort — never the leaked _default mint).
    return "#4F6EF5"


def _genre_for_url(url: str) -> str:
    """Map a brand to a mock scaffold genre: 'shop' | 'travel' | 'media' | 'saas'."""
    token = _host_token(url)
    if token in _BRAND_GENRE:
        return _BRAND_GENRE[token]
    try:
        from urllib.parse import urlparse
        host = urlparse(url).netloc.lower()
        for brand, genre in _BRAND_GENRE.items():
            if brand in host:
                return genre
    except Exception:
        pass
    return "saas"


def _load_mock_font(size: int, bold: bool = False):
    """Load a real TrueType face at `size` (bold optional), with graceful fallbacks."""
    from PIL import ImageFont
    candidates = (
        ["/System/Library/Fonts/Supplemental/Arial Bold.ttf",
         "/System/Library/Fonts/Helvetica.ttc",
         "/Library/Fonts/Arial Bold.ttf"]
        if bold else
        ["/System/Library/Fonts/Supplemental/Arial.ttf",
         "/System/Library/Fonts/Helvetica.ttc",
         "/Library/Fonts/Arial.ttf",
         "/System/Library/Fonts/Geneva.ttf"]
    )
    for p in candidates:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except (OSError, ValueError):
                continue
    return ImageFont.load_default()


def _brand_mock_png(out_path: str, url: str, slot: int) -> str:
    """Render a populated, on-brand mock product surface PNG (1920x1000).

    `slot` 0 -> "home / catalog" view (hero + product/listing grid).
    `slot` 1 -> "feature / detail" view (header + ranked rows with scores).

    The accent is the brand's REAL extracted accent (run-local brand_theme.json
    when available, else the curated map) so it matches the rest of the video —
    NOT the generic green default. Content is a genre-appropriate scaffold
    (product grid for retail, review feed for travel, etc.) with real text:
    wordmark, short labels, and plausible price/rating numbers. The two slots
    differ structurally so their md5s differ.

    Primary renderer is Pillow (real text). On any Pillow failure it falls back
    to the legacy ffmpeg drawbox card (text-free but still brand-tinted).
    """
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    run_dir = _run_dir_from_out(out_path)
    accent_hex = _brand_accent_for_url(url, run_dir)
    wordmark = _wordmark_from_brand_theme(run_dir) or _host_token(url).capitalize() or "Brand"
    genre = _genre_for_url(url)
    try:
        return _brand_mock_png_pil(out_path, accent_hex, wordmark, genre, slot)
    except Exception as e:
        # Pillow unavailable / failed — fall back to the brand-tinted ffmpeg card
        # so the scene still ships a populated-ish, on-accent placeholder.
        try:
            return _brand_mock_png_ffmpeg(out_path, accent_hex, slot)
        except Exception:
            raise AdapterError("brand mock png produced no output: %s (%s)" % (out_path, e))


def _brand_mock_png_pil(out_path, accent_hex, wordmark, genre, slot):
    """Pillow renderer — the credible, text-bearing product surface."""
    from PIL import Image, ImageDraw

    Wm, Hm = 1920, 1000
    accent = _hex_to_rgb(accent_hex)
    bg = (247, 248, 250)
    panel = (255, 255, 255)
    border = (228, 231, 236)
    ink = (28, 33, 45)
    sub = (124, 132, 146)
    accent_soft = _mix_rgb(accent, (255, 255, 255), 0.86)   # tinted wash
    accent_chip = _mix_rgb(accent, (255, 255, 255), 0.0)    # solid accent
    on_accent = _on_accent_text(accent)
    content = _MOCK_CONTENT.get(genre, _MOCK_CONTENT["saas"])

    img = Image.new("RGB", (Wm, Hm), bg)
    d = ImageDraw.Draw(img)

    f_word = _load_mock_font(34, bold=True)
    f_nav = _load_mock_font(22)
    f_hero = _load_mock_font(58, bold=True)
    f_sub = _load_mock_font(26)
    f_card = _load_mock_font(24, bold=True)
    f_price = _load_mock_font(26, bold=True)
    f_small = _load_mock_font(20)
    f_chip = _load_mock_font(22, bold=True)

    def text(x, y, s, font, fill):
        d.text((x, y), s, font=font, fill=fill)

    def text_right(x_right, y, s, font, fill):
        w = d.textlength(s, font=font)
        d.text((x_right - w, y), s, font=font, fill=fill)

    # --- Header bar (accent) with real wordmark + nav, both slots ---
    nav_h = 84
    d.rectangle([0, 0, Wm, nav_h], fill=accent)
    text(48, 24, wordmark, f_word, on_accent)
    # nav items (right-aligned cluster)
    nav_items = content["nav"]
    nx = Wm - 48
    for label in reversed(nav_items):
        w = d.textlength(label, font=f_nav)
        nx -= w
        text(nx, 31, label, f_nav, on_accent)
        nx -= 40

    if slot == 0:
        # ---- SLOT 0: home / catalog ----
        # Hero band (soft accent wash) with headline + sub + CTA pill.
        hero_top, hero_bot = nav_h, nav_h + 300
        d.rectangle([0, hero_top, Wm, hero_bot], fill=accent_soft)
        d.rectangle([0, hero_top, 10, hero_bot], fill=accent)  # accent edge
        text(60, hero_top + 60, content["hero"], f_hero, ink)
        text(60, hero_top + 140, content["sub"], f_sub, sub)
        # CTA pill
        cta = content["cta"]
        cw = d.textlength(cta, font=f_chip)
        d.rounded_rectangle([60, hero_top + 200, 60 + cw + 56, hero_top + 252],
                            radius=26, fill=accent)
        text(60 + 28, hero_top + 212, cta, f_chip, on_accent)

        # Product / listing GRID: 4 cards across, 2 rows.
        cards = content["cards"]
        grid_top = hero_bot + 40
        cols, rows = 4, 2
        gutter = 28
        margin = 48
        cw_tile = (Wm - 2 * margin - (cols - 1) * gutter) // cols
        ch_tile = (Hm - grid_top - margin - (rows - 1) * gutter) // rows
        for i in range(min(cols * rows, len(cards))):
            r, c = divmod(i, cols)
            x = margin + c * (cw_tile + gutter)
            y = grid_top + r * (ch_tile + gutter)
            # tile
            d.rounded_rectangle([x, y, x + cw_tile, y + ch_tile], radius=14,
                                fill=panel, outline=border, width=2)
            # image area (accent-tinted block)
            img_h = ch_tile - 96
            d.rounded_rectangle([x + 1, y + 1, x + cw_tile - 1, y + img_h], radius=14,
                                fill=accent_soft)
            # a little accent motif in the image area
            d.rounded_rectangle([x + 24, y + img_h - 44, x + 24 + 56, y + img_h - 20],
                                radius=10, fill=accent)
            label, num = cards[i]
            text(x + 20, y + img_h + 14, label, f_card, ink)
            # price/score chip bottom-right
            num_is_rating = genre == "travel"
            chip = ("★ " + num) if num_is_rating else num
            pcw = d.textlength(chip, font=f_price)
            d.rounded_rectangle([x + cw_tile - pcw - 36, y + img_h + 48,
                                 x + cw_tile - 12, y + img_h + 84],
                                radius=16, fill=accent)
            text(x + cw_tile - pcw - 24, y + img_h + 52, chip, f_price, on_accent)
            # a faint secondary label line
            d.rectangle([x + 20, y + img_h + 58, x + 20 + int(cw_tile * 0.45), y + img_h + 62],
                        fill=border)
    else:
        # ---- SLOT 1: feature / detail (ranked rows + scores) ----
        # Filter tab strip under the header.
        tab_top = nav_h
        d.rectangle([0, tab_top, Wm, tab_top + 56], fill=(238, 240, 244))
        tabs = ["All", "Top Rated", "Nearby", "Newest"]
        tx = 48
        for i, t in enumerate(tabs):
            tw = d.textlength(t, font=f_small)
            if i == 0:
                d.rounded_rectangle([tx - 14, tab_top + 12, tx + tw + 14, tab_top + 44],
                                    radius=16, fill=accent)
                text(tx, tab_top + 16, t, f_small, on_accent)
            else:
                text(tx, tab_top + 16, t, f_small, sub)
            tx += tw + 48
        # result count (a number)
        text_right(Wm - 48, tab_top + 16, "248 results", f_small, sub)

        # Ranked rows (3) with rank badge, title, sub, and a score on the right.
        rows = content["rows"]
        row_top = tab_top + 56 + 24
        row_h = 250
        for i, (title, subline, score) in enumerate(rows[:3]):
            y = row_top + i * (row_h + 18)
            d.rounded_rectangle([48, y, Wm - 48, y + row_h], radius=16,
                                fill=panel, outline=border, width=2)
            # accent rank stripe + number
            d.rounded_rectangle([48, y, 60, y + row_h], radius=8, fill=accent)
            d.ellipse([88, y + 28, 144, y + 84], fill=accent_soft, outline=accent, width=3)
            rank = str(i + 1)
            rw = d.textlength(rank, font=f_card)
            text(88 + 28 - rw / 2, y + 42, rank, f_card, accent)
            # thumbnail block
            d.rounded_rectangle([176, y + 28, 176 + 280, y + row_h - 28], radius=12,
                                fill=accent_soft)
            d.rounded_rectangle([200, y + row_h - 84, 200 + 72, y + row_h - 56],
                                radius=8, fill=accent)
            # title + subline
            tx0 = 176 + 280 + 40
            text(tx0, y + 40, title, f_hero if False else _load_mock_font(34, bold=True), ink)
            text(tx0, y + 96, subline, f_sub, sub)
            # secondary detail bars (filled, not empty outlines)
            d.rounded_rectangle([tx0, y + 150, tx0 + 360, y + 168], radius=6, fill=(232, 235, 240))
            d.rounded_rectangle([tx0, y + 182, tx0 + 240, y + 200], radius=6, fill=(232, 235, 240))
            # score badge (a real number) on the right
            score_str = str(score)
            sw = d.textlength(score_str, font=f_price)
            bx1 = Wm - 80
            bx0 = bx1 - sw - 44
            d.rounded_rectangle([bx0, y + 36, bx1, y + 36 + 56], radius=16, fill=accent)
            text(bx0 + 22, y + 48, score_str, f_price, on_accent)
            text_right(Wm - 80, y + 110, "Reviews", f_small, sub)

    img.save(out_path, "PNG")
    if not os.path.exists(out_path) or os.path.getsize(out_path) < 500:
        raise AdapterError("brand mock png (pil) produced no output: %s" % out_path)
    return out_path


def _brand_mock_png_ffmpeg(out_path, accent_hex, slot):
    """Legacy brand-tinted card via ffmpeg drawbox (no text). Defensive fallback
    when Pillow is unavailable — still uses the REAL accent, not the green default."""
    acc = "0x" + (accent_hex or "#4F6EF5").lstrip("#")
    bg   = "0xF7F8FA"
    mid  = "0xE2E5EA"
    dark = "0xC8CDD5"
    base = "color=c=%s:s=%dx%d:d=1" % (bg, W, 1000)
    if slot == 0:
        filters = [
            "drawbox=x=0:y=0:w=%d:h=84:color=%s@1.0:t=fill" % (W, acc),
            "drawbox=x=48:y=24:w=240:h=36:color=0xFFFFFF@0.92:t=fill",
            "drawbox=x=%d:y=28:w=160:h=32:color=0xFFFFFF@0.30:t=fill" % (W - 200),
            "drawbox=x=0:y=84:w=%d:h=300:color=%s@0.14:t=fill" % (W, acc),
            "drawbox=x=0:y=84:w=10:h=300:color=%s@0.95:t=fill" % acc,
            "drawbox=x=60:y=160:w=820:h=56:color=%s@0.22:t=fill" % acc,
            "drawbox=x=60:y=232:w=620:h=28:color=%s@0.14:t=fill" % acc,
            "drawbox=x=60:y=300:w=240:h=52:color=%s@0.95:t=fill" % acc,
        ]
        # product grid: 4 x 2 filled tiles
        margin, gutter, cols, rows_n = 48, 28, 4, 2
        cw = (W - 2 * margin - (cols - 1) * gutter) // cols
        gtop = 420
        ch = (1000 - gtop - margin - (rows_n - 1) * gutter) // rows_n
        for i in range(cols * rows_n):
            r, c = divmod(i, cols)
            x = margin + c * (cw + gutter)
            y = gtop + r * (ch + gutter)
            filters.append("drawbox=x=%d:y=%d:w=%d:h=%d:color=0xFFFFFF@1.0:t=fill" % (x, y, cw, ch))
            filters.append("drawbox=x=%d:y=%d:w=%d:h=%d:color=%s@0.16:t=fill" % (x, y, cw, ch - 90, acc))
            filters.append("drawbox=x=%d:y=%d:w=%d:h=20:color=%s@0.30:t=fill" % (x + 16, y + ch - 70, int(cw * 0.6), acc))
            filters.append("drawbox=x=%d:y=%d:w=70:h=30:color=%s@0.95:t=fill" % (x + cw - 86, y + ch - 40, acc))
    else:
        filters = [
            "drawbox=x=0:y=0:w=%d:h=84:color=%s@1.0:t=fill" % (W, acc),
            "drawbox=x=48:y=24:w=220:h=36:color=0xFFFFFF@0.92:t=fill",
            "drawbox=x=0:y=84:w=%d:h=56:color=%s@1.0:t=fill" % (W, mid),
            "drawbox=x=48:y=98:w=150:h=28:color=%s@0.40:t=fill" % acc,
            "drawbox=x=216:y=98:w=130:h=28:color=%s@1.0:t=fill" % dark,
        ]
        row_top, row_h = 164, 250
        for i in range(3):
            y = row_top + i * (row_h + 18)
            filters.append("drawbox=x=48:y=%d:w=%d:h=%d:color=0xFFFFFF@1.0:t=fill" % (y, W - 96, row_h))
            filters.append("drawbox=x=48:y=%d:w=12:h=%d:color=%s@0.95:t=fill" % (y, row_h, acc))
            filters.append("drawbox=x=176:y=%d:w=280:h=%d:color=%s@0.16:t=fill" % (y + 28, row_h - 56, acc))
            filters.append("drawbox=x=496:y=%d:w=420:h=30:color=%s@0.30:t=fill" % (y + 40, acc))
            filters.append("drawbox=x=496:y=%d:w=360:h=18:color=%s@1.0:t=fill" % (y + 96, dark))
            filters.append("drawbox=x=%d:y=%d:w=140:h=56:color=%s@0.95:t=fill" % (W - 220, y + 36, acc))
    vf = ",".join(filters)
    _run([
        "ffmpeg", "-y", "-nostdin", "-loglevel", "error",
        "-f", "lavfi", "-i", base,
        "-vf", vf,
        "-frames:v", "1", out_path,
    ], timeout=60)
    if not os.path.exists(out_path) or os.path.getsize(out_path) < 500:
        raise AdapterError("brand mock png (ffmpeg) produced no output: %s" % out_path)
    return out_path


def _proc_tail(proc, lines=15):
    """Last `lines` of stderr (preferred) or stdout from a completed process."""
    text = (proc.stderr or "").strip() or (proc.stdout or "").strip()
    if not text:
        return "(walk-agent produced no stdout/stderr)"
    return "\n".join(text.splitlines()[-lines:])


def _write_walkagent_log(out_path, scene, proc, url, goal):
    """Persist the full walk-agent stdout/stderr to <out>.walkagent.log so a failed
    walkthrough is diagnosable after the fact. Best-effort: a logging failure must
    not mask the real generation error, so it's swallowed."""
    try:
        log_path = out_path.rsplit(".", 1)[0] + ".walkagent.log"
        os.makedirs(os.path.dirname(os.path.abspath(log_path)), exist_ok=True)
        with open(log_path, "w") as f:
            f.write("# walk-agent failure log\n")
            f.write("scene_id: %s\n" % scene.get("id"))
            f.write("url: %s\n" % url)
            f.write("goal: %s\n" % goal)
            f.write("returncode: %s\n" % proc.returncode)
            f.write("output_exists: %s\n" % os.path.exists(out_path))
            f.write("\n===== STDOUT =====\n")
            f.write(proc.stdout or "(empty)")
            f.write("\n===== STDERR =====\n")
            f.write(proc.stderr or "(empty)")
            f.write("\n")
        return log_path
    except OSError:
        return None


# ---------------------------------------------------------------------------
# Title / motion_graphic (motion-graphics, Remotion). FREE; mock = color card.
# ---------------------------------------------------------------------------

def generate_overlay(scene, out_path, mode, company_url=None):
    stype = scene.get("type", "title")
    if mode == "mock":
        synth_clip(out_path, TYPE_COLOR.get(stype, "0A0D0C"), scene.get("duration_s", 3))
        return {"output_path": out_path, "real": False}
    # Real motion-graphics is free/local but needs the kit; the mock test suite
    # never exercises it. Fall back to a synthetic card if the kit is missing.
    kit = "/Users/dennis/Desktop/Projects/Hackathons/motion-graphics-kit"
    if not os.path.isdir(kit):
        synth_clip(out_path, TYPE_COLOR.get(stype, "0A0D0C"), scene.get("duration_s", 3))
        return {"output_path": out_path, "real": False, "note": "motion-graphics-kit missing; synthesized"}
    variant = "divider" if stype == "motion_graphic" else "title"
    last = int(scene.get("duration_s", 3)) * FPS - 1
    # Brand-thread the overlay: resolve the client palette and parse on-brand copy
    # from the brief (reuses the studio path's helpers). EXPLICIT props are passed
    # so the kit's leftover defaults can never leak a stale client identity, and so
    # the accent is the brand's real color (NOT a hardcoded lime).
    palette = remotion_codegen.palette_for(company_url)
    title, subtitle, kicker, _badge = remotion_codegen._copy_from_brief(
        scene, scene.get("brief", ""), palette)
    props = json.dumps({"variant": variant, "kicker": kicker, "title": title,
                        "subtitle": subtitle, "badge": _badge,
                        "accent": palette["accent"], "accent2": palette.get("accent2"),
                        "fg": palette["fg"], "bg": palette["bg"], "solidBg": True})
    env = dict(os.environ, PATH=os.path.join(kit, "node_modules/.bin") + ":" + os.environ.get("PATH", ""))
    proc = subprocess.run(
        ["remotion", "render", "src/index.ts", "Overlay", out_path, "--codec=h264",
         "--frames=0-%d" % last, "--props=%s" % props, "--concurrency=8"],
        cwd=kit, env=env, capture_output=True, text=True, timeout=300, check=False)
    if proc.returncode != 0 or not os.path.exists(out_path):
        synth_clip(out_path, TYPE_COLOR.get(stype, "0A0D0C"), scene.get("duration_s", 3))
        return {"output_path": out_path, "real": False, "note": "remotion failed; synthesized"}
    return {"output_path": out_path, "real": True}


# ---------------------------------------------------------------------------
# Studio — the agent WRITES a Remotion component and renders it (FREE, local).
# This is the "watch the agent code the motion-graphics" path. The generated
# source is real TSX that actually renders, recorded in the ledger for replay.
# ---------------------------------------------------------------------------

def _studio_render(source_tsx, out_path):
    """Write the agent's component to the studio's active scene and render it.

    Returns the elapsed render time in ms. Raises AdapterError on failure (no
    silent fallback — a broken render must surface, not ship a blank clip).
    """
    os.makedirs(os.path.dirname(STUDIO_ACTIVE), exist_ok=True)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(STUDIO_ACTIVE, "w") as f:
        f.write(source_tsx)
    env = dict(os.environ, PATH=os.path.join(STUDIO_DIR, "node_modules/.bin") + ":" + os.environ.get("PATH", ""))
    t0 = time.time()
    proc = subprocess.run(
        ["remotion", "render", "src/index.ts", "Scene", os.path.abspath(out_path), "--codec=h264"],
        cwd=STUDIO_DIR, env=env, capture_output=True, text=True, timeout=300, check=False)
    render_ms = int((time.time() - t0) * 1000)
    if proc.returncode != 0 or not os.path.exists(out_path):
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()
        raise AdapterError("studio render failed: " + (tail[-1] if tail else "?"))
    return render_ms


def studio_overlay(scene, out_path, palette):
    """title / motion_graphic — the agent authors a real component, then renders it."""
    source, meta = remotion_codegen.generate(scene, palette)
    render_ms = _studio_render(source, out_path)
    return {"output_path": out_path, "real": True, "kind": "authored",
            "generated_code": source, "archetype": meta["archetype"],
            "code_lines": meta["lines"], "render_ms": render_ms,
            "brand": palette.get("_name"), "composition": "Scene"}


def studio_placeholder(scene, out_path, palette):
    """cinematic / walkthrough — a labelled storyboard frame (NOT agent-authored
    creative code; the real media is Higgsfield/walk-agent in --mode real)."""
    source, meta = remotion_codegen.generate_placeholder(scene, palette)
    render_ms = _studio_render(source, out_path)
    # `real: True` here means "a real MP4 was rendered" (a labelled storyboard frame),
    # NOT a genuine walk-agent/Higgsfield capture. `placeholder: True` is the honest
    # signal the orchestrator gates on so a brand VO never narrates over this stand-in
    # in a real walkthrough delivery.
    return {"output_path": out_path, "real": True, "kind": "placeholder",
            "placeholder": True,
            "archetype": "placeholder", "render_ms": render_ms, "composition": "Scene"}


# ---------------------------------------------------------------------------
# Voiceover. edge-tts (test, FREE) | ElevenLabs (real, PAID).
# ---------------------------------------------------------------------------

def synthesize_voiceover(script, voice, out_path, provider):
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    if provider == "edge":
        return _vo_edge(script, voice, out_path)
    if provider == "elevenlabs":
        return _vo_elevenlabs(script, voice, out_path)
    raise AdapterError("unknown VO provider %r" % provider)


def synthesize_voiceover_aligned(beats, voice, out_path, provider, total_s=None):
    """Scene-aligned VO: synthesize each beat to its OWN segment, then lay every
    segment down at its scene's start offset on one full-length track.

    `beats` is a list of {scene_id, text, start_s} — start_s is the cumulative
    clip-start offset of the scene the beat belongs to (the orchestrator computes
    it from produced-clip durations, so beats for CUT scenes are simply never
    passed in). Each beat is `adelay`'d to its start_s and the segments are mixed,
    so the resulting voiceover.mp3 already has every line on the correct picture.
    Muxing it at t=0 (the existing stitch/finish path) therefore needs no change.

    Returns {output_path, provider, voice, real, segments:[{scene_id,start_s,path,dur_s}]}.
    Reuses the same per-provider synth (edge-tts free / ElevenLabs paid) as the
    single-track path — no new dependency, no new paid call.
    """
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    beats = [b for b in (beats or []) if (b.get("text") or "").strip()]
    if not beats:
        raise AdapterError("synthesize_voiceover_aligned got no usable beats")

    base = out_path.rsplit(".", 1)[0]
    segments = []
    provider_name = None
    edge_voice = None
    for i, b in enumerate(beats):
        seg_path = "%s.beat%02d.mp3" % (base, i)
        info = synthesize_voiceover(b["text"], voice, seg_path, provider)
        provider_name = info["provider"]
        edge_voice = info["voice"]
        segments.append({
            "scene_id": b.get("scene_id"),
            "start_s": round(float(b.get("start_s") or 0.0), 3),
            "path": seg_path,
            "dur_s": round(ffprobe_duration(seg_path), 3),
        })

    # Lay each segment at its start offset on one track via adelay, then mix.
    # adelay takes integer milliseconds; mixing with normalize=0 keeps levels flat
    # (the finish pass does the loudnorm). A long enough tail comes from the
    # padded total duration so the muxer never truncates the last beat.
    inputs = []
    filt = []
    for i, seg in enumerate(segments):
        inputs += ["-i", seg["path"]]
        ms = int(round(seg["start_s"] * 1000))
        filt.append("[%d:a]aresample=48000,adelay=%d|%d[a%d]" % (i, ms, ms, i))
    mixlabels = "".join("[a%d]" % i for i in range(len(segments)))
    tail = "-map", "[mix]"
    if total_s and total_s > 0:
        # Pad to the full video length so the track spans the whole picture and
        # the muxer never truncates the last beat; -t pins the exact length.
        filt.append("%samix=inputs=%d:duration=longest:normalize=0,apad[mix]"
                    % (mixlabels, len(segments)))
        tail = "-map", "[mix]", "-t", "%.3f" % total_s
    else:
        filt.append("%samix=inputs=%d:duration=longest:normalize=0[mix]"
                    % (mixlabels, len(segments)))
    cmd = ["ffmpeg", "-y", "-nostdin", "-loglevel", "error", *inputs,
           "-filter_complex", ";".join(filt), *tail,
           "-c:a", "libmp3lame", "-q:a", "4", "-ar", "48000", out_path]
    _run(cmd, timeout=180)
    if not os.path.exists(out_path) or os.path.getsize(out_path) < 500:
        raise AdapterError("aligned VO produced no audio")
    return {"output_path": out_path, "provider": provider_name, "voice": edge_voice,
            "real": provider == "elevenlabs", "segments": segments}


def _vo_edge(script, voice, out_path):
    """Free edge-tts synth, made ROBUST: edge-tts is a network service and
    intermittently raises NoAudioReceived (empty stream). Retry a few times with
    short backoff; on PERSISTENT failure DON'T crash the build — fall back to a
    silent segment of a plausible duration so the picture/stitch still completes.
    The warning is logged so the failure is visible without being fatal."""
    edge_voice = EDGE_VOICE_MAP.get((voice or "").strip().lower(), EDGE_VOICE_DEFAULT)
    last_err = None
    for attempt in range(3):
        try:
            _run(["edge-tts", "--voice", edge_voice, "--text", script,
                  "--write-media", out_path], timeout=180)
            if os.path.exists(out_path) and os.path.getsize(out_path) >= 500:
                return {"output_path": out_path, "provider": "edge-tts",
                        "voice": edge_voice, "real": False}
            last_err = "edge-tts produced no audio (empty file)"
        except Exception as e:  # subprocess timeout / NoAudioReceived / cmd-failed
            last_err = str(e)
        if attempt < 2:
            time.sleep(0.8 * (attempt + 1))
    # Persistent failure: synthesize a silent segment of the right length instead
    # of raising. Estimate from word count at ~150 wpm (0.4 s/word), min 1.2 s.
    words = len((script or "").split())
    dur = max(1.2, round(words * 0.4, 2))
    sys.stderr.write(
        "adapters._vo_edge: WARNING edge-tts failed after 3 tries (%s); "
        "writing %.1fs SILENT fallback so the build does not crash.\n"
        % (last_err, dur))
    _run(["ffmpeg", "-y", "-nostdin", "-loglevel", "error",
          "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono",
          "-t", "%.3f" % dur, "-c:a", "libmp3lame", "-q:a", "4", out_path],
         timeout=60)
    if not os.path.exists(out_path) or os.path.getsize(out_path) < 200:
        raise AdapterError("edge-tts failed and silent fallback could not be written: %s" % last_err)
    return {"output_path": out_path, "provider": "edge-tts-silent-fallback",
            "voice": edge_voice, "real": False, "fallback": True, "fallback_reason": last_err}


# ElevenLabs STOCK voice ids (premium_vo add-on). These are pre-made library
# voices — NOT clones — so using them needs NO consent. A friendly name passed as
# `voice` ("Adam", "Rachel", ...) resolves to the matching stock id; an explicit
# 20-char id passes through unchanged. (The retired founder_voice CLONE path is
# gone; premium_vo always uses one of these stock voices.)
ELEVENLABS_STOCK_VOICE_IDS = {
    "adam": "pNInz6obpgDQGcFmaJgB",
    "rachel": "21m00Tcm4TlvDq8ikWAM",
    "antoni": "ErXwobaYiN019PkySvjV",
    "bella": "EXAVITQu4vr4xnSDxMaL",
    "josh": "TxGEqnHWrfWFTfGW9XjX",
}
ELEVENLABS_STOCK_VOICE_DEFAULT = "pNInz6obpgDQGcFmaJgB"  # 'Adam'


def _vo_elevenlabs(script, voice, out_path):
    """Real ElevenLabs synthesis using a STOCK (library) voice — premium_vo add-on.

    Only runs in --mode real with --vo elevenlabs. Stock voices are pre-made
    library voices, NOT clones, so this requires NO consent. A friendly voice name
    resolves to its stock voice id; an explicit id passes through. Uses the key in
    ~/.hermes/.env. Kept minimal; the test phase never hits this.
    """
    key = _read_hermes_env().get("ELEVENLABS_API_KEY") or os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        raise AdapterError("ELEVENLABS_API_KEY not found (in ~/.hermes/.env or env)")
    name = (voice or "").strip()
    voice_id = (ELEVENLABS_STOCK_VOICE_IDS.get(name.lower())
                or (name if name else ELEVENLABS_STOCK_VOICE_DEFAULT))
    import urllib.request
    url = "https://api.elevenlabs.io/v1/text-to-speech/%s" % voice_id
    body = json.dumps({"text": script, "model_id": "eleven_multilingual_v2"}).encode()
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "xi-api-key": key, "Content-Type": "application/json", "Accept": "audio/mpeg"})
    with urllib.request.urlopen(req, timeout=180) as resp, open(out_path, "wb") as f:
        f.write(resp.read())
    return {"output_path": out_path, "provider": "elevenlabs", "voice": voice_id, "real": True}


def _read_hermes_env():
    path = os.path.expanduser("~/.hermes/.env")
    out = {}
    if not os.path.exists(path):
        return out
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip().strip('"').strip("'")
    return out


# ---------------------------------------------------------------------------
# Stitch (video-stitch). REAL ffmpeg in both modes.
# ---------------------------------------------------------------------------

def stitch(clips, vo_path, out_path, watermark=False, music_path=None):
    """Concat clips in order (they share the frame spec) then mux the VO + BGM bed.

    Returns a record with the output path, duration, and the verification probe.
    Trims the VO to the video length so a long VO can't overrun the picture and
    a short VO simply leaves trailing silence (video is never cut).

    `watermark` — premium-menu no_watermark booster lever. When True the Walk
    Studio watermark is burned into the bottom-right corner during the concat
    pass (the STARTER tier default; the booster removes it -> watermark=False).
    Default False keeps the pre-premium stitch byte-identical. The mark is a
    drawn corner badge (this ffmpeg build has no drawtext/libfreetype, so we use
    drawbox — always available — as the watermark glyph). The record carries a
    `watermark` bool either way so the ledger/dashboard reflect it.

    `music_path` — OPTIONAL background-music bed (an mp3/wav). The per-scene clip
    render path concatenates scene clips and muxes ONLY the VO, so Remotion's
    Timeline `<Audio>` music bed never reaches final.mp4 (the long-standing "music
    slot stubbed with silence"). When provided, the track is looped to cover the
    video, then mixed UNDER the VO via a VO-keyed sidechain compressor so it ducks
    automatically: BGM ~0.45 in VO gaps, ducked to ~0.16 while the VO speaks
    (feedback_bgm_level_depends_on_vo). The bed fades in at the head and out past
    the visual close. None => no music (byte-identical to the prior VO-only mux).
    The record carries `has_music` so the ledger/dashboard reflect it.
    """
    if not clips:
        raise AdapterError("stitch got no clips")
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)

    # Concat. Inputs are NOT guaranteed uniform: failure-isolation can leave a
    # heterogeneous set of survivors (e.g. 1920x1080 title + 1280x720 cinematic
    # + 2560x1440 walkthrough, at different fps/SAR/pix_fmt). Raw `concat` rejects
    # mismatched link params (ffmpeg error 234 -> no final.mp4). So normalize EVERY
    # input to the project frame spec (W x H, FPS, SAR 1, yuv420p) before concat:
    #   scale-to-fit (force_original_aspect_ratio=decrease, never distort)
    #   + pad (letterbox/pillarbox, centered) to exactly W x H.
    # This keeps aspect ratio intact and produces uniform links the concat accepts.
    inputs = []
    filt = []
    maps = ""
    for i, c in enumerate(clips):
        inputs += ["-i", c]
        filt.append(
            "[%d:v:0]scale=%d:%d:force_original_aspect_ratio=decrease,"
            "pad=%d:%d:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=%d,format=yuv420p[v%d]"
            % (i, W, H, W, H, FPS, i)
        )
        maps += "[v%d]" % i
    filt.append("%sconcat=n=%d:v=1:a=0[v]" % (maps, len(clips)))
    video_map = "[v]"
    if watermark:
        # Walk Studio watermark — a drawn corner badge (drawbox; no font dep). A
        # filled brand-tinted bar + a brighter inset stripe in the bottom-right
        # corner reads as a deliberate watermark glyph without needing drawtext.
        bw, bh = 360, 64
        x, y = "iw-%d-32" % bw, "ih-%d-28" % bh
        filt.append(
            "[v]drawbox=x=%s:y=%s:w=%d:h=%d:color=0x0A0D0C@0.55:t=fill,"
            "drawbox=x=%s:y=%s:w=6:h=%d:color=0x9AE600@0.95:t=fill[vw]"
            % (x, y, bw, bh, x, y, bh))
        video_map = "[vw]"
    silent_master = out_path.rsplit(".", 1)[0] + ".__video.mp4"
    _run(["ffmpeg", "-y", "-nostdin", "-loglevel", "error", *inputs,
          "-filter_complex", ";".join(filt),
          "-map", video_map, "-c:v", "libx264", "-crf", "18", "-preset", "medium",
          "-pix_fmt", "yuv420p", "-movflags", "+faststart", silent_master], timeout=600)

    vdur = ffprobe_duration(silent_master)

    has_vo = bool(vo_path and os.path.exists(vo_path))
    has_music = bool(music_path and os.path.exists(music_path))

    # BGM duck levels (project rule feedback_bgm_level_depends_on_vo):
    #   - with VO present: bed sits at ~0.45 open, ducked to ~0.16 under the VO.
    #   - solo (no VO): bed plays louder (~0.85) since nothing competes.
    # The duck is automatic: a VO-keyed sidechaincompress pulls the 0.45 bed down
    # to ~0.16 whenever the VO is speaking and lets it ride back up in the gaps.
    BGM_OPEN = 0.45
    BGM_SOLO = 0.85
    # head fade-in + a tail fade that OUTLASTS the visual close (feedback_audio_
    # outlasts_visual_fade): start the bed fade ~1.5s before the end and run past it.
    FADE_IN = 0.6
    TAIL = 1.5
    tail_start = max(0.0, vdur - TAIL)

    if has_vo and has_music:
        # VO + ducked music. Loop the bed to cover the video, set it to the OPEN
        # level + fade, then sidechain-duck it against the VO so it dips to ~0.16
        # under speech. amix the ducked bed with the VO; loudnorm the sum to the
        # -14 LUFS delivery target (the VO stays clearly dominant after the duck).
        fc = (
            # VO chain: split — one copy drives the mix, one keys the sidechain.
            "[1:a]aresample=48000,aformat=channel_layouts=stereo,"
            "apad=whole_dur=%.3f,atrim=0:%.3f,asplit=2[vo][vokey];"
            # Music bed: loop, trim to length, OPEN level, head+tail fades.
            "[2:a]aresample=48000,aformat=channel_layouts=stereo,"
            "aloop=loop=-1:size=2e9,atrim=0:%.3f,"
            "volume=%.3f,afade=t=in:st=0:d=%.3f,afade=t=out:st=%.3f:d=%.3f[bed];"
            # Duck the bed against the VO key: ~0.45 -> ~0.16 under speech.
            "[bed][vokey]sidechaincompress="
            "threshold=0.03:ratio=8:attack=20:release=300:makeup=1[duck];"
            # Mix VO + ducked bed (VO dominant), then normalize delivery loudness.
            "[vo][duck]amix=inputs=2:duration=first:dropout_transition=0:"
            "weights=1 1:normalize=0[mixed];"
            "[mixed]loudnorm=I=-14:TP=-1.0:LRA=11[aout]"
            % (vdur, vdur, vdur, BGM_OPEN, FADE_IN, tail_start, TAIL)
        )
        _run(["ffmpeg", "-y", "-nostdin", "-loglevel", "error",
              "-i", silent_master, "-i", vo_path, "-i", music_path,
              "-filter_complex", fc,
              "-map", "0:v:0", "-map", "[aout]", "-t", "%.3f" % vdur,
              "-c:v", "copy", "-c:a", "aac", "-ar", "48000", "-ac", "2",
              "-movflags", "+faststart", out_path], timeout=300)
    elif has_vo:
        # VO only (no music). EBU R128 delivery loudness on the muxed audio
        # (mirrors finish_cut.py's loudnorm) so the e2e cut lands at the ~-14 LUFS
        # streaming standard. Without this the VO ships ~6 LU quiet (~-20 LUFS).
        _run(["ffmpeg", "-y", "-nostdin", "-loglevel", "error",
              "-i", silent_master, "-i", vo_path,
              "-map", "0:v:0", "-map", "1:a:0", "-t", "%.3f" % vdur,
              "-af", "loudnorm=I=-14:TP=-1.0:LRA=11",
              "-c:v", "copy", "-c:a", "aac", "-ar", "48000", "-ac", "2",
              "-movflags", "+faststart", out_path], timeout=300)
    elif has_music:
        # Music only (no VO): the bed rides louder since nothing competes. Loop to
        # cover the video, head+tail fade, loudnorm to delivery.
        fc = (
            "[1:a]aresample=48000,aformat=channel_layouts=stereo,"
            "aloop=loop=-1:size=2e9,atrim=0:%.3f,"
            "volume=%.3f,afade=t=in:st=0:d=%.3f,afade=t=out:st=%.3f:d=%.3f,"
            "loudnorm=I=-16:TP=-1.0:LRA=11[aout]"
            % (vdur, BGM_SOLO, FADE_IN, tail_start, TAIL)
        )
        _run(["ffmpeg", "-y", "-nostdin", "-loglevel", "error",
              "-i", silent_master, "-i", music_path,
              "-filter_complex", fc,
              "-map", "0:v:0", "-map", "[aout]", "-t", "%.3f" % vdur,
              "-c:v", "copy", "-c:a", "aac", "-ar", "48000", "-ac", "2",
              "-movflags", "+faststart", out_path], timeout=300)
    else:
        # No VO and no music: the concat master was built with a=0, so there is no
        # audio stream — passthrough (byte-identical to the prior no-VO path).
        os.replace(silent_master, out_path)
        silent_master = None

    if silent_master and os.path.exists(silent_master):
        os.remove(silent_master)

    # Verify: probe streams + duration.
    probe = _run(["ffprobe", "-v", "error", "-show_entries",
                  "stream=codec_type,codec_name,width,height:format=duration",
                  "-of", "json", out_path], timeout=30)
    info = json.loads(probe.stdout)
    has_audio = any(s.get("codec_type") == "audio" for s in info.get("streams", []))
    duration = float(info.get("format", {}).get("duration", vdur) or vdur)
    rec = {
        "output_path": out_path,
        "duration_s": round(duration, 2),
        "has_audio": has_audio,
        "has_music": has_music,
        "clip_count": len(clips),
        "verified": os.path.getsize(out_path) > 10000,
    }
    # Only surface the `watermark` key when the premium lever was actually used, so
    # the default (watermark=False) stitch record stays byte-identical to the
    # pre-premium shape. The orchestrator's OFF path always passes watermark=False.
    if watermark:
        rec["watermark"] = True
    return rec


# ---------------------------------------------------------------------------
# Multi-format CUT PACK (premium-menu multi_format booster). REAL ffmpeg in
# both modes (free + local). After the main 16:9 final.mp4 is stitched, the
# orchestrator asks for N extra "cuts" — alternate aspect-ratio reframes and
# duration trims — one per EXTRA format the customer bought (the per_format
# menu line already locked the COGS). Each cut is a genuine, playable MP4
# derived from final.mp4 (reframed via scale+crop / trimmed via -t), so
# outputs/ and the ledger reflect real deliverables, not empty stubs.
# ---------------------------------------------------------------------------

# The cut catalog, in the order extra formats are consumed. Reframes change the
# aspect ratio (center scale+crop, never distort); trims keep 16:9 but cap the
# duration. Picked to cover the common social deliverables (9:16 reel, 1:1 feed,
# and 6/15/30s ad trims).
_FORMAT_PACK = [
    {"label": "9:16", "kind": "reframe", "w": 1080, "h": 1920},
    {"label": "1:1", "kind": "reframe", "w": 1080, "h": 1080},
    {"label": "6s", "kind": "trim", "trim_s": 6},
    {"label": "15s", "kind": "trim", "trim_s": 15},
    {"label": "30s", "kind": "trim", "trim_s": 30},
]


def make_format_pack(final_path, run_dir, n_formats, vo_path=None):
    """Produce up to `n_formats` extra cuts derived from `final_path`.

    Each cut is a REAL MP4 written under <run_dir>/formats/. Returns a list of
    {label, kind, output_path, w, h, duration_s, real} records (one per cut).
    Audio (the muxed VO) is preserved when present. If `final_path` has no
    duration (unreadable) trims are clamped to the source length so they never
    over-run. Renders are best-effort per cut: a single failing cut is recorded
    with real=False + an error and the rest still ship (the booster never aborts
    the run). Stdlib + ffmpeg only.
    """
    out_dir = os.path.join(run_dir, "formats")
    os.makedirs(out_dir, exist_ok=True)
    src_dur = ffprobe_duration(final_path)
    has_audio = _has_audio_stream(final_path)
    pack = []
    for spec in _FORMAT_PACK[:max(0, int(n_formats))]:
        label = spec["label"]
        out = os.path.join(out_dir, "final_%s.mp4" % label.replace(":", "x"))
        rec = {"label": label, "kind": spec["kind"], "output_path": out,
               "real": False}
        try:
            if spec["kind"] == "reframe":
                w, h = spec["w"], spec["h"]
                # Center scale-to-cover then crop to the exact target box (no
                # distortion, no letterbox — fills the new aspect).
                vf = ("scale=%d:%d:force_original_aspect_ratio=increase,"
                      "crop=%d:%d,setsar=1,format=yuv420p" % (w, h, w, h))
                cmd = ["ffmpeg", "-y", "-nostdin", "-loglevel", "error",
                       "-i", final_path, "-vf", vf,
                       "-c:v", "libx264", "-crf", "20", "-preset", "veryfast"]
                cmd += ["-c:a", "copy"] if has_audio else ["-an"]
                cmd += ["-movflags", "+faststart", out]
                _run(cmd, timeout=300)
                rec.update({"w": w, "h": h})
            else:  # trim
                t = spec["trim_s"]
                if src_dur and t > src_dur:
                    t = round(src_dur, 3)  # clamp so a trim never over-runs
                cmd = ["ffmpeg", "-y", "-nostdin", "-loglevel", "error",
                       "-i", final_path, "-t", "%.3f" % t,
                       "-c:v", "libx264", "-crf", "20", "-preset", "veryfast"]
                cmd += ["-c:a", "copy"] if has_audio else ["-an"]
                cmd += ["-movflags", "+faststart", out]
                _run(cmd, timeout=300)
                rec.update({"trim_s": t})
            rec["duration_s"] = round(ffprobe_duration(out), 2)
            rec["real"] = os.path.exists(out) and os.path.getsize(out) > 1000
            if not rec["real"]:
                rec["error"] = "format cut produced no usable output"
        except (AdapterError, OSError, subprocess.SubprocessError) as e:
            # Isolate a single failing cut — record it (so the ledger/outputs are
            # honest) and continue; one bad reframe must not sink the pack.
            rec["error"] = "%s: %s" % (type(e).__name__, e)
            _write_format_stub(out, label, str(e))
            rec["output_path"] = out
            rec["real"] = False
        pack.append(rec)
    return pack


def _has_audio_stream(path):
    """True iff `path` has at least one audio stream (so reframes/trims can copy
    it). Best-effort: any probe failure is treated as no-audio (safe -> -an)."""
    try:
        proc = _run(["ffprobe", "-v", "error", "-select_streams", "a",
                     "-show_entries", "stream=index", "-of", "csv=p=0", path],
                    timeout=30, check=False)
        return bool((proc.stdout or "").strip())
    except (AdapterError, OSError, subprocess.SubprocessError):
        return False


def _write_format_stub(out_path, label, why):
    """Last-resort clearly-labelled stub when a real format cut fails to render.

    Writes a tiny solid-color silent MP4 so outputs/ + the ledger still reflect
    the (failed) deliverable as a clearly-labelled placeholder rather than a
    missing file. Best-effort; swallows its own failure."""
    try:
        synth_clip(out_path, "3A0D0D", 2)  # dark-red = placeholder, matches TYPE_COLOR
        sidecar = out_path.rsplit(".", 1)[0] + ".STUB.txt"
        with open(sidecar, "w") as f:
            f.write("MOCK STUB format cut %s — real render failed: %s\n" % (label, why))
    except (AdapterError, OSError):
        pass
