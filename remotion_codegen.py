#!/usr/bin/env python3
"""The producer agent WRITING Remotion code for a motion-graphics scene.

Given a scene (a title / divider brief) and the client's brand palette, this emits
a complete, standalone, idiomatic Remotion component as real TSX source — the code
the agent "wrote" — which `studio/` then renders to a real clip. The source is
recorded in the run ledger so the dashboard can replay the agent typing the exact
code that produced the clip (honest: shown code == rendered code).

Three layout archetypes (chosen deterministically from the scene id) keep the
output varied while always compiling: a centered title, a left editorial block,
and a numbered divider. Each uses useCurrentFrame / interpolate / spring — no
props, every value baked in, so it renders as the registered "Scene" composition.

Stdlib only. `string.Template` ($-substitution) avoids clashing with JSX braces.
"""

import json
import os
import string

FPS = 30
W, H = 1920, 1080

# Client brand palettes — colors come from the TARGET brand, never a fixed studio
# palette (style = genre, not palette). `tagline` is the brand's real one-liner,
# used as the open-title subtitle. Domains are matched as substrings of the URL,
# so a subdomain (docs.stripe.com) still resolves to the brand. Add domains as needed.
#
# `font` is an optional per-brand display type system. It is a CSS font-family STACK,
# not a single name: the lead face is the brand's real type when present on the render
# host, then a curated chain of strong, widely-installed grotesques/serifs, ending in a
# generic family. We deliberately do NOT pull a webfont over the network — the studio's
# node_modules has neither `@remotion/google-fonts` nor `@remotion/fonts`, and a Google
# Fonts @import is not guaranteed to finish loading before Remotion's headless Chrome
# captures the first frame (the classic "blank/fallback font" render bug). System-stack
# resolution is synchronous and was proven loadable by the sibling apple-style-demo that
# renders through this exact node_modules. So this is reliable-by-construction headless.
# (Caveat surfaced in the handoff: a brand's *exact* proprietary face — Söhne, Geist,
# Inter Display — only renders if that file is installed on the host; otherwise the next
# strong fallback in the stack renders, which still reads far better than bare Helvetica.)
_FALLBACK_SANS = '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif'
_FALLBACK_SERIF = 'Georgia, "Times New Roman", serif'

BRAND_PALETTES = {
    "stripe.com": {"bg": "#0A2540", "panel": "#0E2D4D", "accent": "#635BFF",
                   "accent2": "#80E9FF", "fg": "#FFFFFF", "dim": "#7A9CC6",
                   "tagline": "Build internet businesses",
                   "font": '"Sohne", "Helvetica Neue", ' + _FALLBACK_SANS},
    "linear.app": {"bg": "#0B0C0E", "panel": "#16181D", "accent": "#5E6AD2",
                   "accent2": "#8A93E0", "fg": "#F7F8F8", "dim": "#8A8F98",
                   "tagline": "Plan and build products",
                   "font": '"Inter Display", "Inter", "Helvetica Neue", ' + _FALLBACK_SANS},
    "notion.so": {"bg": "#191919", "panel": "#202020", "accent": "#2383E2",
                  "accent2": "#5BA3F0", "fg": "#FFFFFF", "dim": "#9B9B9B",
                  "tagline": "One workspace. Every team.",
                  "font": '"Lyon Display", ui-serif, ' + _FALLBACK_SERIF},
    "notion.com": {"bg": "#191919", "panel": "#202020", "accent": "#2383E2",
                   "accent2": "#5BA3F0", "fg": "#FFFFFF", "dim": "#9B9B9B",
                   "tagline": "One workspace. Every team.",
                   "font": '"Lyon Display", ui-serif, ' + _FALLBACK_SERIF},
    "vercel.com": {"bg": "#000000", "panel": "#0A0A0A", "accent": "#FFFFFF",
                   "accent2": "#888888", "fg": "#FFFFFF", "dim": "#888888",
                   "tagline": "Develop. Preview. Ship.",
                   "font": '"Geist", "Inter", "Helvetica Neue", ' + _FALLBACK_SANS},
    # Strong, tasteful default for any brand we don't have a kit for. A modern
    # geometric/grotesque stack — never bare Helvetica.
    "_default": {"bg": "#0A0D0C", "panel": "#111613", "accent": "#7CFFB2",
                 "accent2": "#9A8CFF", "fg": "#F4F7F5", "dim": "#7E8C84",
                 "font": '"SF Pro Display", "Helvetica Neue", "Avenir Next", '
                         + _FALLBACK_SANS},
}

# Used if a palette somehow lacks `font` (defensive — every entry above has one).
_DEFAULT_FONT = '"SF Pro Display", "Helvetica Neue", "Avenir Next", ' + _FALLBACK_SANS


def _brand_name(url):
    """Display brand name from a URL: https://docs.stripe.com -> 'Stripe'."""
    u = (url or "").lower().replace("https://", "").replace("http://", "").replace("www.", "")
    parts = [p for p in u.split("/")[0].split(".") if p]
    name = parts[-2] if len(parts) >= 2 else (parts[0] if parts else "")
    return name.capitalize() if name else "The product"


def _root_host(url):
    """Bare root host for the CTA: https://docs.stripe.com -> 'stripe.com'."""
    u = (url or "").lower().replace("https://", "").replace("http://", "").replace("www.", "")
    parts = [p for p in u.split("/")[0].split(".") if p]
    return ".".join(parts[-2:]) if len(parts) >= 2 else (parts[0] if parts else "")


def palette_for(company_url):
    u = (company_url or "").lower()
    name, host = _brand_name(company_url), _root_host(company_url)
    for domain, pal in BRAND_PALETTES.items():
        if domain != "_default" and domain in u:
            return dict(pal, _brand=domain, _name=name, _host=host)
    return dict(BRAND_PALETTES["_default"], _brand="generic", _name=name, _host=host)


# Per-style entrance-speed factor consumed by the generated `ease` helper. 1.0 is
# the historical default — for "standard" (or no style set) the substituted code is
# byte-identical to before this feature existed. snappy quickens, cinematic slows.
_STYLE_SPD = {"snappy": 0.6, "standard": 1.0, "cinematic": 1.45}


def _style_spd():
    """Resolve the entrance-speed factor from the HERMES_STYLE env (set by
    build_runner). Defaults to 1.0 (standard) when unset/unknown so existing
    callers and the test suite render exactly as before."""
    style = (os.environ.get("HERMES_STYLE") or "standard").strip().lower()
    spd = _STYLE_SPD.get(style, 1.0)
    # Emit "1.0" exactly for standard so the template text is unchanged.
    return ("%g" % spd) if spd != 1.0 else "1.0"


def _archetype_for(scene_id, variant):
    if variant == "motion_graphic":
        return "divider"
    # deterministic but well-distributed pick between the two title archetypes
    sid = scene_id or "x"
    return "centered" if ((sum(ord(c) for c in sid) + len(sid)) % 2 == 0) else "editorial"


# --- header shared by every generated component --------------------------------
# The header carries: the font stack, the easing helper, a deterministic
# continuous-motion driver (`drift`, a slow frame-based sine that runs the WHOLE
# scene so no archetype freezes after its entrance — Hera L2), and `AnimatedBg`,
# a brand-accent gradient field that drifts/breathes behind the text for the full
# duration (Hera L3). Both are purely frame-derived (useCurrentFrame) — NO
# Math.random / Date — so every render is byte-identical and deterministic.
_HEADER = """// ${SCENE_ID} — generated by the Hermes producer agent
// archetype: ${ARCH} · brand: ${BRAND} · ${DUR}s @ ${FPS}fps
import React from "react";
import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

export const activeMeta = {
  durationInFrames: ${DUR_FRAMES},
  fps: ${FPS},
  width: ${W},
  height: ${H},
};

// Brand display type system (a system-font STACK; see remotion_codegen.py header).
const FONT = '${FONT}';
const TOTAL = ${DUR_FRAMES};

// Per-style ENTRANCE SPEED factor (snappy < 1 = quicker eases / faster cuts feel;
// cinematic > 1 = slower, more luxurious eases; standard = 1.0 = today's exact
// timing, byte-identical). It scales every ease window's start/end frame so the
// motion intensity matches the user-selected style without changing scene length.
const SPD = ${SPD};
const ease = (f: number, a: number, b: number, c: number, d: number) =>
  interpolate(f, [a * SPD, b * SPD], [c, d], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });

// L2 — continuous motion driver: a slow sine over the FULL scene (period ~6.4s)
// plus an optional phase. Frame-based and deterministic. Returns roughly [-1, 1].
const drift = (frame: number, phase = 0) =>
  Math.sin((frame / TOTAL) * Math.PI * 2 * 1.4 + phase);

// L3 — animated, brand-accent background field that runs the whole scene. A large
// soft radial bloom in the accent colour drifts on a slow Lissajous path, a second
// fainter bloom in accent2 counter-drifts, and the whole field breathes 1.0->1.04.
// Low opacity so the foreground text stays fully legible. `seed` shifts the path so
// the three archetypes don't share an identical background motion.
const AnimatedBg: React.FC<{ seed?: number }> = ({ seed = 0 }) => {
  const frame = useCurrentFrame();
  const bx = 50 + drift(frame, seed) * 16;
  const by = 42 + drift(frame, seed + 1.7) * 12;
  const cx = 50 - drift(frame, seed + 0.9) * 20;
  const cy = 64 - drift(frame, seed + 2.3) * 10;
  const breathe = 1 + (drift(frame, seed) + 1) * 0.02;
  const fadeIn = ease(frame, 0, 24, 0, 1);
  return (
    <AbsoluteFill
      style={{
        opacity: fadeIn,
        transform: "scale(" + breathe + ")",
        background:
          "radial-gradient(46% 56% at " + bx + "% " + by + "%, ${ACCENT}38 0%, transparent 60%)," +
          "radial-gradient(40% 50% at " + cx + "% " + cy + "%, ${ACCENT2}26 0%, transparent 62%)," +
          "radial-gradient(120% 120% at 50% 120%, ${PANEL} 0%, transparent 70%)",
      }}
    />
  );
};
"""

_CENTERED = _HEADER + """
export const Active: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // L5 motion vocab for CENTERED: a soft BLUR-IN title (filter: blur -> 0) that
  // also springs up, with a gentle overshoot. Distinct from the editorial stagger
  // and the divider pop.
  const rise = spring({ frame, fps, config: { damping: 200, mass: 0.6 } });
  const titleY = interpolate(rise, [0, 1], [26, 0]);
  const titleBlur = ease(frame, 0, 22, 14, 0);
  const kickerO = ease(frame, 2, 14, 0, 1);
  const ruleW = ease(frame, 12, 30, 0, 560);
  const subO = ease(frame, 18, 32, 0, 1);

  // L2 continuous motion through the hold: the accent rule keeps breathing in
  // width/glow and the whole stack drifts a few px the entire scene, so the frame
  // is never frozen after the entrance.
  const ruleGlow = 8 + (drift(frame, 0.4) + 1) * 9;
  const floatY = drift(frame, 0) * 5;

  return (
    <AbsoluteFill style={{ backgroundColor: "${BG}", fontFamily: FONT }}>
      <AnimatedBg seed={0} />
      <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", transform: "translateY(" + floatY + "px)" }}>
        <div style={{ opacity: kickerO, letterSpacing: 8, fontSize: 24, fontWeight: 600, color: "${ACCENT}", textTransform: "uppercase" }}>
          ${KICKER}
        </div>
        <div style={{ transform: "translateY(" + titleY + "px)", opacity: rise, filter: "blur(" + titleBlur + "px)", marginTop: 22, fontSize: 116, fontWeight: 800, color: "${FG}", letterSpacing: -2, textAlign: "center", lineHeight: 1.02 }}>
          ${TITLE}
        </div>
        <div style={{ width: ruleW, height: 4, marginTop: 30, borderRadius: 2, background: "linear-gradient(90deg, ${ACCENT}, ${ACCENT2})", boxShadow: "0 0 " + ruleGlow + "px ${ACCENT}" }} />
        <div style={{ opacity: subO, marginTop: 26, fontSize: 30, fontWeight: 400, color: "${DIM}", textAlign: "center" }}>
          ${SUBTITLE}
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
"""

_EDITORIAL = _HEADER + """
export const Active: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // entrance: a vertical accent rule grows, then the lines stagger in from the left.
  const grow = spring({ frame, fps, config: { damping: 200 } });
  const barH = interpolate(grow, [0, 1], [0, 232]);

  // L5 motion vocab for EDITORIAL: a per-line STAGGERED build where each line
  // springs in with a slight overshoot (lower damping = bouncier than centered),
  // so the lines arrive in sequence rather than sharing one move.
  const line = (delay: number) => {
    const s = spring({ frame: frame - delay, fps, config: { damping: 14, stiffness: 120, mass: 0.7 } });
    return {
      opacity: ease(frame, delay, delay + 10, 0, 1),
      transform: "translateX(" + interpolate(s, [0, 1], [-34, 0]) + "px)",
    };
  };

  // L2 continuous motion through the hold: the vertical accent bar keeps a slow
  // travelling gradient + glow for the whole scene, and the corner badge drifts.
  const barGlow = 6 + (drift(frame, 0.6) + 1) * 8;
  const barShift = 50 + drift(frame, 0) * 50;
  const badgeY = drift(frame, 1.2) * 6;

  return (
    <AbsoluteFill style={{ backgroundColor: "${BG}", fontFamily: FONT }}>
      <AnimatedBg seed={2.1} />
      <div style={{ position: "absolute", left: 180, top: 360, display: "flex", gap: 40 }}>
        <div style={{ width: 6, height: barH, borderRadius: 3, background: "linear-gradient(180deg, ${ACCENT}, ${ACCENT2})", backgroundSize: "100% 200%", backgroundPosition: "0% " + barShift + "%", boxShadow: "0 0 " + barGlow + "px ${ACCENT}" }} />
        <div>
          <div style={{ ...line(6), letterSpacing: 6, fontSize: 22, fontWeight: 600, color: "${ACCENT}", textTransform: "uppercase" }}>
            ${KICKER}
          </div>
          <div style={{ ...line(12), marginTop: 16, fontSize: 104, fontWeight: 800, color: "${FG}", letterSpacing: -2, lineHeight: 1.0 }}>
            ${TITLE}
          </div>
          <div style={{ ...line(20), marginTop: 22, fontSize: 30, fontWeight: 400, color: "${DIM}", maxWidth: 900 }}>
            ${SUBTITLE}
          </div>
        </div>
      </div>
      <div style={{ position: "absolute", right: 120, top: 120, opacity: ease(frame, 4, 18, 0, 0.5), transform: "translateY(" + badgeY + "px)", fontSize: 22, letterSpacing: 4, color: "${DIM}" }}>
        ${BADGE}
      </div>
    </AbsoluteFill>
  );
};
"""

_DIVIDER = _HEADER + """
export const Active: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // L5 motion vocab for DIVIDER: a pronounced OVERSHOOT pop on the number badge
  // (low damping spring, scale 0.6 -> overshoot -> settle) — punchier than the
  // centered blur-in and the editorial stagger.
  const pop = spring({ frame, fps, config: { damping: 9, stiffness: 140, mass: 0.6 } });
  const badgeS = interpolate(pop, [0, 1], [0.6, 1]);
  const ruleW = ease(frame, 8, 34, 0, 1320);
  const labelO = ease(frame, 16, 30, 0, 1);

  // L2 continuous motion through the hold: the badge breathes + its ring glow
  // pulses, and the hairline rule carries a travelling sheen the whole scene.
  const badgeBreathe = 1 + (drift(frame, 0) + 1) * 0.015;
  const ringGlow = 10 + (drift(frame, 0.5) + 1) * 12;
  const sheen = 50 + drift(frame, 0) * 50;

  return (
    <AbsoluteFill style={{ backgroundColor: "${BG}", fontFamily: FONT, alignItems: "center", justifyContent: "center" }}>
      <AnimatedBg seed={4.2} />
      <div style={{ transform: "scale(" + (badgeS * badgeBreathe) + ")", opacity: pop, width: 132, height: 132, borderRadius: 26, border: "3px solid ${ACCENT}", boxShadow: "0 0 " + ringGlow + "px ${ACCENT}55", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 64, fontWeight: 800, color: "${ACCENT}" }}>
        ${BADGE}
      </div>
      <div style={{ width: ruleW, height: 2, marginTop: 46, opacity: 0.6, background: "linear-gradient(90deg, transparent, ${ACCENT}, ${ACCENT2}, transparent)", backgroundSize: "200% 100%", backgroundPosition: sheen + "% 0%" }} />
      <div style={{ opacity: labelO, marginTop: 30, fontSize: 52, fontWeight: 700, color: "${FG}", letterSpacing: -1, textAlign: "center" }}>
        ${TITLE}
      </div>
    </AbsoluteFill>
  );
};
"""

_PLACEHOLDER = _HEADER + """
export const Active: React.FC = () => {
  const frame = useCurrentFrame();

  // a labelled storyboard frame: this scene's real media is produced elsewhere
  // (Higgsfield for cinematic, walk-agent for walkthrough). A scan line sweeps
  // to read as 'pending render', not a dead color card.
  const scanY = ((frame * 9) % 1080);
  const labelO = ease(frame, 2, 16, 0, 1);
  const briefO = ease(frame, 10, 26, 0, 1);

  return (
    <AbsoluteFill style={{ backgroundColor: "${BG}", fontFamily: FONT }}>
      <AnimatedBg seed={1.3} />
      <div style={{ position: "absolute", top: scanY, left: 0, width: ${W}, height: 2, background: "${ACCENT}", opacity: 0.18 }} />
      <AbsoluteFill style={{ alignItems: "center", justifyContent: "center" }}>
        <div style={{ opacity: labelO, padding: "10px 20px", border: "1px solid ${ACCENT}", borderRadius: 999, fontSize: 22, letterSpacing: 4, color: "${ACCENT}", textTransform: "uppercase" }}>
          ${KICKER}
        </div>
        <div style={{ opacity: briefO, marginTop: 34, maxWidth: 1200, fontSize: 46, fontWeight: 600, color: "${FG}", textAlign: "center", lineHeight: 1.18 }}>
          ${TITLE}
        </div>
        <div style={{ opacity: briefO, marginTop: 26, fontSize: 24, color: "${DIM}" }}>
          ${SUBTITLE}
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
"""

_TEMPLATES = {"centered": _CENTERED, "editorial": _EDITORIAL,
              "divider": _DIVIDER, "placeholder": _PLACEHOLDER}


# Scene type -> the producing tool, for the storyboard-placeholder label.
_TOOL_LABEL = {
    "cinematic": "Higgsfield",
    "walkthrough": "Walk Agent",
}


def generate_placeholder(scene, palette, fps=FPS):
    """Return (tsx_source, meta) for a cinematic/walkthrough STORYBOARD placeholder.

    This is NOT 'agent-authored creative code' — it's a labelled stand-in so the
    mock final cut reads as a clean animatic. The ledger marks it kind=placeholder
    so the dashboard does not present it as a code-replay.
    """
    dur_s = max(2, int(scene.get("duration_s", 6)))
    dur_frames = dur_s * fps
    stype = scene.get("type", "cinematic")
    tool = _TOOL_LABEL.get(stype, stype)
    model = scene.get("model")
    kicker = (tool + " · " + model) if model else tool
    tpl = string.Template(_PLACEHOLDER)
    src = tpl.substitute(
        SCENE_ID=scene.get("id", "scene"), ARCH="placeholder",
        BRAND=palette.get("_brand", "generic"),
        DUR=dur_s, DUR_FRAMES=dur_frames, FPS=fps, W=W, H=H,
        BG=palette["bg"], ACCENT=palette["accent"], ACCENT2=palette.get("accent2", palette["accent"]),
        PANEL=palette.get("panel", palette["bg"]), FONT=palette.get("font", _DEFAULT_FONT),
        FG=palette["fg"], DIM=palette["dim"], SPD=_style_spd(),
        KICKER=_txt(kicker), TITLE=_txt(scene.get("brief", "")[:120]),
        SUBTITLE=_txt("storyboard placeholder · real media generated in --mode real"),
        BADGE=_txt(""),
    )
    meta = {"durationInFrames": dur_frames, "fps": fps, "width": W, "height": H,
            "archetype": "placeholder", "kind": "placeholder", "lines": src.count("\n") + 1}
    return src, meta


def _js(s):
    """Safe JS/JSX string literal (drops the surrounding quotes for {…} contexts
    we instead inline as text — here we keep quotes and use it inside JSX text by
    stripping them)."""
    return json.dumps(s or "", ensure_ascii=False)


def _txt(s):
    """JSX text content: escape braces and the few HTML-sensitive chars."""
    s = (s or "").replace("{", "&#123;").replace("}", "&#125;")
    return s.replace("<", "&lt;").replace(">", "&gt;")


def generate(scene, palette, fps=FPS):
    """Return (tsx_source, meta) for a title/motion_graphic scene."""
    variant = scene.get("type", "title")
    arch = _archetype_for(scene.get("id"), variant)
    dur_s = max(2, int(scene.get("duration_s", 3)))
    dur_frames = dur_s * fps

    brief = scene.get("brief", "")
    # derive on-card text from the brief (kicker / title / subtitle / badge)
    title, subtitle, kicker, badge = _copy_from_brief(scene, brief, palette)

    tpl = string.Template(_TEMPLATES[arch])
    src = tpl.substitute(
        SCENE_ID=scene.get("id", "scene"),
        ARCH=arch, BRAND=palette.get("_brand", "generic"),
        DUR=dur_s, DUR_FRAMES=dur_frames, FPS=fps, W=W, H=H,
        BG=palette["bg"], ACCENT=palette["accent"], ACCENT2=palette.get("accent2", palette["accent"]),
        PANEL=palette.get("panel", palette["bg"]), FONT=palette.get("font", _DEFAULT_FONT),
        FG=palette["fg"], DIM=palette["dim"], SPD=_style_spd(),
        KICKER=_txt(kicker), TITLE=_txt(title), SUBTITLE=_txt(subtitle), BADGE=_txt(badge),
    )
    meta = {"durationInFrames": dur_frames, "fps": fps, "width": W, "height": H,
            "archetype": arch, "lines": src.count("\n") + 1}
    return src, meta


def _section_label(brief):
    """Derive a SHORT, presentable section label from a divider/motion_graphic brief.

    The brief is a scene *direction*, not on-screen copy — e.g.
      "Simple animated divider with the text 'Built for developers'"
    so dumping `brief[:48]` would literally render the instruction. Strip the leading
    directive scaffold, prefer any quoted on-screen phrase the direction names, and
    otherwise fall back to a few title-cased keywords. Returns "" if nothing clean is
    left — the divider then shows just its number badge, which is always presentable.
    """
    import re
    b = (brief or "").strip()
    if not b:
        return ""
    # 1) prefer an explicitly-quoted phrase ("...with the text 'Built for developers'").
    #    A naive search treats a POSSESSIVE apostrophe ("Figma's brand colors") as an
    #    opening quote, capturing "s brand colors and the text " — garbage. To be robust
    #    to an apostrophe anywhere before the intended phrase, only match a quote that
    #    OPENS at a word boundary (not flanked by letters/digits on its left), and prefer
    #    the LAST such pair so a trailing "'Built for teams'" wins over an earlier stray.
    #    Curly quotes (‘ ’ “ ”) are never used for possessives in briefs, so they match
    #    freely; straight ' and " must be at a boundary to dodge the possessive trap.
    quoted = re.findall(
        r"(?:(?<![A-Za-z0-9])['\"]|[‘“])\s*([^'\"‘’“”]+?)\s*(?:['\"]|[’”])",
        b,
    )
    phrase, from_quote = "", False
    for cand in reversed(quoted):
        c = cand.strip()
        # ignore a captured fragment that is itself just a possessive remnant
        # (e.g. a lone "s" or a chunk that begins mid-word) — require real words.
        if c and re.search(r"[A-Za-z]{2,}", c):
            phrase, from_quote = c, True
            break
    if not phrase:
        # 2) strip a leading directive clause up to a connector ("... the text X", "... reading X")
        lowered = b.lower()
        cut = b
        for marker in (" the text ", " reading ", " that reads ", " saying ", " labelled ", " labeled ", ": "):
            i = lowered.find(marker)
            if i != -1:
                cut = b[i + len(marker):]
                break
        # drop common direction lead-ins / filler words from the front
        words = cut.split()
        directive = {"a", "an", "the", "simple", "animated", "clean", "minimal", "short",
                     "divider", "section", "transition", "card", "title", "intro", "interstitial",
                     "with", "showing", "show", "display", "displaying", "featuring", "of"}
        while words and words[0].lower().strip(".,;:'\"") in directive:
            words.pop(0)
        # drop a possessive ("Stripe's") that survived as the first keyword so it never
        # renders an apostrophe-S remnant in the fallback label.
        words = [re.sub(r"['’]s\b", "", w) for w in words]
        phrase = " ".join(w for w in words[:4] if w)
    phrase = phrase.strip(" .,;:'\"‘’“”")
    if not phrase:
        return ""
    # An explicitly-quoted phrase is deliberate on-screen copy — preserve the author's
    # casing (only ensure the first letter is capitalized). The keyword fallback is a
    # synthesized label, so title-case it (unless it already carries capitalization).
    if from_quote:
        label = phrase[0].upper() + phrase[1:]
    else:
        label = phrase if any(c.isupper() for c in phrase[1:]) else phrase.title()
    return label[:42]


def _cta_title(brief, name):
    """Derive the closing CTA headline from the scene brief instead of a hardcoded
    Stripe-flavored "Start building" (wrong-domain for a design/data/etc. product and
    contradicts the brand-aware VO, e.g. "Start designing…at figma.com").

    Briefs phrase the CTA as an imperative — "Call to action: Start building with
    Stripe today", "Start designing for free at figma.com", "Get started with Linear".
    Pull a leading "<Verb> [object]" imperative (1-3 words) when present; otherwise
    fall back to a neutral, domain-agnostic "Get started". Never returns "".
    """
    import re
    b = (brief or "").strip()
    # Drop a leading "Call to action:"/"CTA:"/"Closing:" scaffold so the imperative is first.
    b = re.sub(r"(?i)^\s*(call to action|cta|closing|outro|end\s*card)\s*[:\-–—]\s*", "", b).strip()
    # A CTA imperative starts with a verb. Match a short "<Verb> <particle?> <object?>"
    # phrase and stop before trailing fluff ("…with Stripe today", "…for free at …").
    cta_verbs = (
        "start", "get", "try", "build", "design", "create", "ship", "launch",
        "explore", "discover", "join", "sign", "begin", "make", "plan",
    )
    m = re.match(
        r"(?i)\b(" + "|".join(cta_verbs) + r")\b((?:\s+[A-Za-z][A-Za-z'-]*){0,2})",
        b,
    )
    if m:
        head = m.group(1)
        rest_words = m.group(2).split()
        # Stop the object at the first connector/filler so we don't drag in
        # "…with Stripe today" / "…for free at figma.com".
        stop = {"with", "for", "at", "to", "in", "on", "today", "now", "free",
                "your", "the", "a", "an", "and", "using", "via"}
        kept = []
        for w in rest_words:
            if w.lower().strip(".,;:") in stop:
                break
            kept.append(w)
        phrase = (head + " " + " ".join(kept)).strip()
        phrase = phrase[0].upper() + phrase[1:]
        return phrase[:28]
    return "Get started"


def _synth_tagline(brief, name):
    """Synthesize a clean open-card subtitle when the palette carries no real
    `tagline` (the `_default` palette for any non-kitted brand). Prefer a tagline
    the brief explicitly QUOTES ("…logo and tagline: 'Build internet businesses'");
    otherwise fall back to a neutral one-liner — never a blank subtitle, and never a
    directive remnant ("Figma Logo And Brand"), so we only trust a quoted phrase here.
    """
    import re
    b = (brief or "").strip()
    quoted = re.findall(
        r"(?:(?<![A-Za-z0-9])['\"]|[‘“])\s*([^'\"‘’“”]+?)\s*(?:['\"]|[’”])",
        b,
    )
    for cand in reversed(quoted):
        c = cand.strip(" .,;:'\"‘’“”")
        if c and re.search(r"[A-Za-z]{2,}", c) and c.lower() != (name or "").lower():
            return c[:60]
    return "See what you can build"


def _copy_from_brief(scene, brief, palette):
    """Turn a scene brief into card copy. Deterministic, no model call needed —
    the agent's 'authoring' is the component composition, not ad copy. Brand name,
    tagline and host come from the CLIENT palette so every build is on-brand
    (no hardcoded Stripe copy)."""
    sid = (scene.get("id") or "").lower()
    name = palette.get("_name") or "The product"
    host = palette.get("_host") or ""
    tagline = palette.get("tagline") or ""
    # close FIRST: "closing-title" contains "title" but is a CTA, not the open card.
    if any(k in sid for k in ("clos", "cta", "-end", "outro")):
        # CTA verb derived from the brief (brand-aware), not a hardcoded constant.
        return _cta_title(brief, name), host or name, "Get started", "→"
    if "open" in sid or "title" in sid:
        # open / brand title card: wordmark + the brand's own tagline (synthesize a
        # clean fallback when the palette has none, so the subtitle is never blank).
        return name, tagline or _synth_tagline(brief, name), "Introducing", "01"
    # divider / motion_graphic: a SHORT section label (or just the number badge),
    # never the raw scene direction.
    if scene.get("type") == "motion_graphic":
        return _section_label(brief), "", "", "2"
    # generic title fallback from the brief
    words = (brief or "Title").split()
    title = " ".join(words[:4])[:42] or "Title"
    return title, " ".join(words[4:10])[:60], "Section", "01"


if __name__ == "__main__":
    import sys
    demo = {"id": "title-open", "type": "title", "brief": "Stripe logo and tagline", "duration_s": 3}
    src, meta = generate(demo, palette_for("https://docs.stripe.com"))
    sys.stderr.write(json.dumps(meta) + "\n")
    print(src)
