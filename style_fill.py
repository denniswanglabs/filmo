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
import html as _html_mod
import json
import os
import re
import subprocess
import sys
from typing import Any, Callable, Dict, List, Optional

import align_vo
import build_timeline

# ---------------------------------------------------------------------------
# HTML-ENTITY DECODE  (R5 fix — must be the LAST pass on every user-facing string)
# Handles numeric (&#x27; &#39; &#38; &#34; &#60; &#62; &#160;) AND named
# (&amp; &quot; &lt; &gt; &nbsp; &apos;) entities so raw HTML entities never
# reach the renderer. Applied via _decode() at prop-finalization time.
# ---------------------------------------------------------------------------
def _decode(s: object) -> str:
    """html.unescape() wrapper — safe on None/non-str inputs, returns str."""
    if not s:
        return "" if s is None or s == "" else str(s)
    return _html_mod.unescape(str(s))


# --- Timeline archetype ids (must match studio/src/timeline/types.ts Archetype) ---
ARCH_HERO = "hero-title"
ARCH_CARD = "card-ui"
# The never-blank designed card for a cinematic/walkthrough/demo beat that gets no
# real footage on a $0/standard run (the blank-scenes fix). Shows the narrated
# point as kinetic motion-graphics instead of a flat solid color.
ARCH_EXPLAINER = "explainer-card"
# A produced walkthrough MP4 (Walk Agent capture) played INSIDE the branded studio
# composition, so the clip inherits Walk Studio overlays + per-scene VO. Used for a
# `walkthrough` role ONLY when a real clip exists; otherwise the role falls back to
# ARCH_EXPLAINER (the never-blank designed card) so a clip-less run is never blank.
ARCH_WALKTHROUGH = "walkthrough-player"
# A REAL captured website screenshot shown inside a brand-tinted browser card (the
# "here is the actual site" proof beat). Used for a `screenshot` role; the captured
# PNG is wired into data.imageSrc from runs/<id>/screenshots/. Falls back to the
# explainer card only if no image staged (the archetype itself has a never-blank floor).
ARCH_SCREENSHOT = "apple-screenshot"

# Plan-scene keys that may carry the produced walkthrough clip path (the producer
# writes `output_path`; some plans pre-stage it as `videoSrc`/`media_path`).
_WALKTHROUGH_CLIP_KEYS = ("videoSrc", "video_path", "output_path", "media_path", "clip_path")

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
# A tagline sourced from a raw <meta name="description"> is hard-cut at 80 chars by
# brand_extract and routinely ends MID-WORD ("Try Shopify free… Get more than ecomme",
# "easy, safe and re"). Such a fragment must NEVER be used as a title/headline. We
# detect it and prefer a clean, COMPLETE source instead.
def _is_truncated_meta(text: str) -> bool:
    """True when `text` looks like a truncated meta-description fragment unsuitable
    as a headline: an explicit ellipsis, OR a long-ish string whose final token is
    cut mid-word (no terminal punctuation and the tail isn't a clean word ending).
    Conservative — short, complete phrases (real taglines) are NOT flagged."""
    t = (text or "").strip()
    if not t:
        return False
    if t.endswith(("…", "...")) or "…" in t:
        return True
    # brand_extract caps at 80 chars; a fragment at/near that length with no terminal
    # punctuation is almost certainly a mid-word cut of a sentence-y meta description.
    if len(t) >= 70 and not t.rstrip().endswith((".", "!", "?", '"', "'")):
        # also true mid-word giveaways: ends on a lone 1-2 char tail like "re"/"ecomme"
        # after a longer sentence. Treat any 70+ char unpunctuated meta as truncated.
        return True
    # Mid-WORD chop guard: works even on shorter strings where the last "word" looks
    # like a word fragment (a partial token produced by slicing mid-word).
    # Heuristic: last token is all-alphabetic, 1-4 chars, NOT a known short complete
    # English word/acronym, AND is preceded by a longer sentence (3+ words before it).
    # This catches "…all in Webf" where "Webf" is a 4-char partial brand name.
    if _ends_mid_word(t):
        return True
    return False


# Short complete English words/acronyms that are valid final tokens (do NOT flag
# as mid-word fragments). Extend as needed, but keep it conservative.
_KNOWN_SHORT_WORDS = frozenset((
    "ai", "ml", "ui", "ux", "api", "sdk", "saas", "b2b", "b2c", "erp", "crm",
    "on", "in", "at", "by", "up", "to", "do", "go", "no", "so", "is", "it",
    "all", "any", "app", "can", "you", "for", "now", "pay", "buy", "new",
    "top", "get", "run", "try", "use", "see", "set", "add", "let", "cut",
    "put", "out", "off", "one", "two", "the", "and", "but", "not", "yet",
    "an", "a",
))


def _ends_mid_word(text: str) -> bool:
    """True when `text` appears to end mid-word — the last token looks like a
    partial prefix, not a complete English word.

    Conservative heuristic: last alphabetic-only token is 1-4 chars, NOT in the
    known-short-words allowlist, AND the string has at least 3 words before it
    (so a genuine 1-word brand name like "Webf" is not flagged when it IS the
    brand rather than a mid-word cut).
    """
    if not text:
        return False
    # Only applies when the string ends on a plain letter (no punctuation tail).
    if not text[-1].isalpha():
        return False
    words = text.split()
    if len(words) < 2:
        return False  # single-word strings: can't distinguish brand from fragment
    last = words[-1].lower()
    # If it's a known short complete word, it's fine.
    if last in _KNOWN_SHORT_WORDS:
        return False
    # Flag short (1-4 char) all-alpha tokens that aren't in our allowlist when
    # there are at least 2 words before them (i.e., sentence context exists).
    if len(last) <= 4 and last.isalpha() and len(words) >= 3:
        return True
    return False


def _is_ui_nav_label(text: str) -> bool:
    """True when `text` is a UI/nav-label string scraped from interactive chrome,
    NOT a real brand headline or tagline.

    Detects two patterns:
      (a) Explicit known UI-chrome phrases: "Added to Cart", "New Arrivals",
          "Become a host", "Homes on", "What's happening", "Sign in", "Log in",
          "Sign up", "New Arrivals", "Shop Now", etc.
      (b) Two nav-tab items joined by " · " (e.g. "Homes on Airbnb · Become a host",
          "What's happening · Enable any billing model") — a dot-bullet join is a
          dead giveaway this is a tab-bar or breadcrumb, never a real headline.

    Conservative: doesn't flag genuine taglines that happen to share a word.
    """
    t = (text or "").strip()
    if not t:
        return False
    # (b) Nav-tab join: 2+ segments separated by a rail separator — middot/bullet/
    # pipe (with optional spaces) or a spaced en/em-dash. A brand tagline never uses
    # these to join clauses; it's a UI navigation pattern. Reject the WHOLE string
    # when it splits into a multi-segment join (regardless of segment content), AND
    # reject when ANY segment is itself a nav label.
    parts = [p.strip() for p in re.split(r"\s*[·•|]\s*|\s+[–—]\s+", t) if p.strip()]
    if len(parts) >= 2:
        return True

    # (a) Single-segment nav/section label (no separator): gendered store category,
    # support rail, leading nav-action token, or a known UI-chrome phrase.
    return _is_nav_label_segment(t)


# Nav SECTION / category labels (single segment) that are navigation destinations,
# not headlines: gendered store categories, support/account rails, "find a …"
# actions. Mirrors brand_extract._NAV_SECTION_EXACT so a feature label scraped as a
# nav item ("Men's Shoes", "Help Center", "Find a co-host") is rejected at render.
_NAV_SECTION_EXACT = frozenset((
    "men's shoes", "mens shoes", "women's shoes", "womens shoes",
    "men's clothing", "women's clothing", "kids' shoes", "kids shoes",
    "apparel & accessories", "apparel and accessories", "accessories",
    "customer favorites", "customer favourites", "fan favorites",
    "help center", "help centre", "support center", "contact support",
    "find a co-host", "find a cohost", "find a store", "find a host",
    "all products", "all collections", "shop by category", "browse all",
    "gift guide", "gift guides", "size guide", "size chart",
    "latest news", "latest posts", "latest stories",
    "popular", "featured", "collections", "categories",
))

_NAV_LEADING_TOKENS = (
    "find a ", "find an ", "shop ", "browse ", "explore ", "discover ",
    "view all ", "see all ", "go to ", "visit the ", "back to ",
)

# Known UI-chrome phrases — matched as a substring so "Homes on Airbnb" is caught.
_UI_CHROME_PHRASES = (
    "added to cart", "new arrivals", "become a host", "homes on",
    "what's happening", "sign in", "log in", "sign up", "log out", "sign out",
    "shop now", "learn more", "get started", "view all", "see all", "load more",
    "cookie settings", "privacy policy", "terms of service", "skip to content",
)


def _is_nav_label_segment(text: str) -> bool:
    """True when a SINGLE segment (no rail separator) is a UI/nav-section label
    rather than a real headline: a gendered store category, a support/account rail,
    a leading nav-action token, or a known UI-chrome phrase. Conservative — short
    section labels only; genuine taglines are not flagged."""
    low = (text or "").strip().lower().strip(" .!·•|-—–")
    if not low:
        return False
    if low in _NAV_SECTION_EXACT:
        return True
    if any(low.startswith(tok) for tok in _NAV_LEADING_TOKENS):
        return True
    for phrase in _UI_CHROME_PHRASES:
        if phrase in low:
            return True
    return False


def _is_prompt_artifact(text: str) -> bool:
    """True when `text` contains instruction/stage-direction fragments that leaked
    from the LLM prompt into a rendered string.

    Catches patterns like:
      - "Show call-to-action: ..." (the notion artifact: 'Show call-to-action: 'Start')
      - "Display the ..."
      - "Animated ..."  (when used as a stage direction)
      - "Present the ..."
      - A leading verb-colon like "Scene:", "Title:", "CTA:" etc.
      - Generic instruction openings: "Insert ", "Place ", "Add a "

    Conservative: only flags strings where the WHOLE string looks like an
    instruction, not just strings that contain any of these words.
    """
    t = (text or "").strip()
    if not t:
        return False
    lower = t.lower()

    # Verb-colon prefixes — instruction fragments that escaped into display copy.
    _INSTRUCTION_VERB_COLONS = (
        "show call-to-action:",
        "show cta:",
        "display the ",
        "display a ",
        "present the ",
        "present a ",
        "animate ",
        "animated ",
        "insert ",
        "add a cta",
        "add cta",
        "scene:",
        "title:",
        "subtitle:",
        "cta:",
        "headline:",
        "caption:",
    )
    for prefix in _INSTRUCTION_VERB_COLONS:
        if lower.startswith(prefix):
            return True

    # Also catch mid-string instruction fragments that are a dead giveaway:
    # e.g. "Show call-to-action" anywhere in the string.
    _INSTRUCTION_SUBSTRINGS = (
        "call-to-action:",
        "call to action:",
    )
    for sub in _INSTRUCTION_SUBSTRINGS:
        if sub in lower:
            return True

    return False


# Fancy / non-ASCII hyphen variants that a model (or a meta-description scrape) may
# emit in place of an ASCII "-": non-breaking hyphen U+2011, figure dash U+2012,
# en/em dash U+2013/U+2014, horizontal bar U+2015, minus sign U+2212. Normalizing
# these to "-" lets a single phrase set ("call-to-action") match regardless of which
# hyphen the source used ("call‑to‑action" with U+2011, "call—to—action" with em-dash).
_FANCY_HYPHENS = "‐‑‒–—―−"
_HYPHEN_NORM_RE = re.compile("[" + _FANCY_HYPHENS + "]")


def _normalize_hyphens(text: str) -> str:
    """Fold every fancy-hyphen codepoint to an ASCII '-' so phrase matching is robust
    to the unicode-hyphen variants a model emits ("call‑to‑action" → "call-to-action")."""
    return _HYPHEN_NORM_RE.sub("-", text or "")


# Self-referential META-DESCRIPTION phrases: a string that DESCRIBES the CTA/closing
# card ("a call-to-action card urging users…") instead of BEING the CTA copy addressed
# to the viewer. These leak when the LLM planner's closing beat is a STAGE DIRECTION
# rather than a line of copy. plan_job's `_degut_stage_direction_beats` (R7-G3) caught
# the "Show call-to-action:" verb-colon form but NOT this descriptive phrasing — so
# style_fill is the LAST line of defense on the rendered CTA. Hyphen-normalized + lower.
_CTA_META_DESCRIPTION_PHRASES = (
    "call-to-action",          # "call-to-action card", "closing call-to-action…"
    "call to action",          # spaced form (no hyphen at all)
    "closing card",
    "closing call",            # "Closing call-to-action card…"
    "urging users",            # "…card urging users to sign up"
    "urging the user",
    "urging viewers",
    "card urging",
    "stage direction",
    "using the brand",         # "Call-to-action card using the brand color"
    "brand color",             # "…using the brand color"
    "brand colour",
    "the wordmark",            # "Closing card with the wordmark"
    "cta card",
    "the cta",                 # "Show the CTA"
    "closing scene",
    "closing beat",
    "final card",
    "outro card",
)

# A meta-description often OPENS with a stage-direction verb + a noun that names the
# card itself ("Closing …", "Show …", "Display …", "Animate …"). When a candidate CTA
# starts with one of these AND describes the card (rather than addressing the viewer
# with an imperative product action), it is a stage direction, not real CTA copy.
_CTA_STAGE_OPENERS = (
    "closing", "close ", "show ", "display ", "displays ", "animate ",
    "animated ", "present ", "presents ", "render ", "renders ", "reveal ",
    "fade ", "fades ", "cut to", "end on", "ends on", "end card", "wrap ",
)
# Nouns that, when they follow a stage-opener, confirm the string is describing the
# card/scene rather than telling the viewer to do something ("Closing card…",
# "Show the call-to-action…", "Display the wordmark…").
_CTA_CARD_NOUNS = (
    "card", "call-to-action", "call to action", "cta", "scene", "wordmark",
    "title", "lockup", "screen", "frame", "logo", "tagline", "the brand",
)


def _is_cta_stage_direction(text: str) -> bool:
    """True when `text` is a self-referential STAGE-DIRECTION / meta-description of the
    closing CTA card rather than real CTA copy addressed to the viewer.

    Catches the leaked-planner-beat class that R7-G3's sanitizer missed:
      - "Closing call‑to‑action card urging users"          (U+2011 hyphens)
      - "Call-to-action card using the brand color"
      - "Closing card with the wordmark"
      - "Show the CTA"

    Robust to fancy unicode hyphens (U+2010–U+2015, U+2212) and case. Two signals:
      (1) the string CONTAINS a meta-description phrase that names the card/CTA/scene
          ("call-to-action", "closing card", "urging users", "the wordmark", "cta card",
          "using the brand", "brand color", "stage direction", "the cta", …), OR
      (2) the string OPENS with a stage-direction verb ("Closing"/"Show"/"Display"/
          "Animate"/…) AND a card-noun ("card"/"call-to-action"/"wordmark"/…) appears,
          i.e. it directs the card rather than addressing the viewer.

    Conservative: a REAL imperative CTA addressed to the viewer ("Shop Allbirds",
    "Begin your free trial", "Start your trip on Tripadvisor", "Visit theverge.com",
    "Start accepting payments") contains none of these phrases and does not open with a
    card-directing stage verb, so it is NOT flagged.
    """
    raw = (text or "").strip()
    if not raw:
        return False
    norm = _normalize_hyphens(raw).lower()
    # (1) Contains a meta-description phrase that names the card / CTA / scene.
    for phrase in _CTA_META_DESCRIPTION_PHRASES:
        if phrase in norm:
            return True
    # (2) Opens with a stage-direction verb + a card-noun somewhere in the string.
    for opener in _CTA_STAGE_OPENERS:
        if norm.startswith(opener):
            if any(noun in norm for noun in _CTA_CARD_NOUNS):
                return True
            break
    return False


# Capture / screenshot STAGE-DIRECTION phrases: a string that DESCRIBES the
# screenshot SHOT ("Real captured homepage … in a branded browser card") rather
# than the PRODUCT value-prop. The planner-prompt forbids these in the VO, but a
# screenshot scene's `brief` is itself this kind of camera/capture direction — so it
# must never leak into the on-screen headline. Hyphen-normalized + lowercased.
_CAPTURE_STAGE_PHRASES = (
    "captured homepage", "captured home page", "captured key page",
    "captured view", "captured page", "captured site", "captured website",
    "real captured", "screenshot of", "screen shot of", "browser card",
    "branded browser", "in a browser", "the real site", "the real website",
    "real website of", "real site of", "homepage of", "home page of",
    "key page of", "inner page of", "landing page of",
)
# Stage-opener verbs that, with a capture/shot noun, confirm a screenshot direction.
_CAPTURE_STAGE_OPENERS = (
    "real captured", "captured", "screenshot", "screen shot", "show the real",
    "showing the", "display the", "capture the", "the homepage", "the home page",
    "the inner page", "the landing page", "the key page",
)
_CAPTURE_SHOT_NOUNS = (
    "homepage", "home page", "screenshot", "browser card", "browser", "site",
    "website", "page", "capture", "view",
)


def _is_capture_stage_direction(text: str) -> bool:
    """True when `text` is a screenshot/capture STAGE-DIRECTION describing the SHOT
    ("Real captured homepage of The Verge in a branded browser card") rather than a
    grounded product value-prop. Used to keep a screenshot scene's camera-direction
    `brief` out of the on-screen headline.

    Two signals (hyphen-normalized, lowercased):
      (1) the string CONTAINS a capture/shot meta-phrase ("real captured",
          "browser card", "homepage of", "the real site", …), OR
      (2) it OPENS with a capture verb AND a shot-noun appears somewhere.
    Conservative: a real value-prop ("Breaking tech news, in-depth reviews …")
    contains none of these and is NOT flagged.
    """
    raw = (text or "").strip()
    if not raw:
        return False
    norm = _normalize_hyphens(raw).lower()
    for phrase in _CAPTURE_STAGE_PHRASES:
        if phrase in norm:
            return True
    for opener in _CAPTURE_STAGE_OPENERS:
        if norm.startswith(opener):
            if any(noun in norm for noun in _CAPTURE_SHOT_NOUNS):
                return True
            break
    return False


def _is_fragment_subtitle(text: str) -> bool:
    """True when `text` is an unusable subtitle/tagline fragment that must be DROPPED.

    Rejects strings that are clearly a mid-sentence scrape artifact rather than a
    complete brand tagline:
      (a) Starts with a lowercase letter — a mid-sentence fragment (e.g. "store they
          line up for"). Real taglines are title-cased or sentence-cased.
      (b) Ends on a preposition, article, coordinating conjunction, or relative
          pronoun — an open clause that was truncated (e.g. "store they line up for",
          "brands you can rely on", "the platform built with", "brands for men who").
          The set covers prepositions/articles that are NEVER a natural sentence-final
          word, plus relative pronouns (who/that/which/where) that introduce a
          following clause which was chopped.
      (c) Fewer than 2 words — too thin to be a subtitle (single-word fragments).
      (d) UI/nav-label copy (see _is_ui_nav_label).
      (e) Prompt/instruction artifact (see _is_prompt_artifact).

    Conservative: only rejects clear fragments; short complete taglines like
    "For everyone." (capital F) or "Do more." are NOT rejected.
    """
    t = (text or "").strip()
    if not t:
        return False
    # (d) UI/nav-label copy
    if _is_ui_nav_label(t):
        return True
    # (e) Prompt artifact
    if _is_prompt_artifact(t):
        return True
    # (c) Single-word fragment
    words = t.split()
    if len(words) < 2:
        return True
    # (a) Starts lowercase — mid-sentence fragment
    if t[0].islower():
        return True
    # (b) Ends on a preposition/article/conjunction/relative pronoun — open clause
    _FRAGMENT_TERMINALS = frozenset((
        "for", "to", "the", "a", "an", "with", "of", "on", "in", "at",
        "by", "from", "and", "or", "but", "nor", "so", "yet",
        "up", "out", "over", "into", "onto", "upon", "about",
        # Relative/subordinating words that introduce a following clause (chopped mid-clause)
        "who", "that", "which", "where", "when", "while", "than",
    ))
    last = words[-1].lower().rstrip(".,!?;:")
    if last in _FRAGMENT_TERMINALS:
        return True
    return False


def _clean_complete_headline(text: str, limit: int = 72) -> str:
    """Return a clean, COMPLETE headline derived from `text`, or "" if nothing usable.

    NEVER returns a mid-word cut: prefers the first full sentence/clause that fits;
    if even the first clause overflows, truncates on a WORD boundary and drops a
    dangling function word (reusing _title_from_text). Rejects an obviously truncated
    meta-description fragment up front so a mangled `…ecomme` never surfaces.

    Also rejects UI/nav-label strings (e.g. "Added to Cart · New Arrivals") and
    prompt/stage-direction artifacts (e.g. "Show call-to-action: 'Start") — these
    must never reach the rendered title/subtitle/CTA props.
    """
    t = (text or "").strip()
    if not t:
        return ""
    # Reject UI chrome and prompt artifacts before any further processing.
    if _is_ui_nav_label(t) or _is_prompt_artifact(t):
        return ""
    if _is_truncated_meta(t):
        # Salvage a complete leading sentence if one exists before the cut; else "".
        sent = re.split(r"(?<=[.!?])\s+", t, maxsplit=1)[0].strip()
        if sent and not _is_truncated_meta(sent) and len(sent) <= limit:
            return sent
        return ""
    return _title_from_text(t, limit=limit)


def _brand_fallback_title(brand: Dict[str, Any]) -> str:
    """A NEVER-empty on-brand title: CLEAN tagline -> wordmark -> brand name.

    A truncated meta-description tagline (mid-word cut) is rejected here so it can
    never become the headline; we fall through to the wordmark/brand instead.
    A UI/nav-label string or prompt artifact is also rejected so "Added to Cart ·
    New Arrivals" or "Show call-to-action: 'Start" never becomes a display title.
    A fragment subtitle (lowercase-leading or preposition-final/relative-clause scrape
    artifact) is also rejected so "store they line up for" or "brands for men who"
    never becomes a display title."""
    tag = (brand.get("tagline") or "").strip()
    clean_tag = _clean_complete_headline(tag) if tag else ""
    # Also reject a fragment subtitle so it never becomes the display title.
    if clean_tag and _is_fragment_subtitle(clean_tag):
        clean_tag = ""
    return (clean_tag or brand.get("wordmark")
            or brand.get("brand") or brand.get("name") or "").strip()


def _distinct_tagline(brand: Dict[str, Any], avoid: str = "") -> str:
    """A short tagline/subtitle DISTINCT from the wordmark and from `avoid`.

    Priority:
      1. The brand's clean tagline — but only when it is meaningfully different
         from the wordmark (case-insensitive) AND different from `avoid`.
      2. Synthesize a short one from the first two feature labels joined with " · "
         (e.g. "Payment Processing · Billing") — still on-brand, never invented.
      3. Empty string (caller decides the graceful fallback).

    Never returns a string that is the same word (case-insensitive) as `avoid` or
    as the brand wordmark, so eyebrow ≠ display ≠ tagline.
    """
    wordmark = (brand.get("wordmark") or brand.get("brand") or brand.get("name") or "").strip()
    avoid_lower = (avoid or "").strip().lower()
    wordmark_lower = wordmark.lower()

    # 1. Clean tagline that is distinct from both wordmark and avoid.
    tag = _clean_complete_headline(brand.get("tagline") or "")
    # Reject a fragment subtitle (lowercase-leading / preposition/relative-final, UI label, artifact).
    if tag and (_is_fragment_subtitle(tag) or _is_ui_nav_label(tag) or _is_prompt_artifact(tag)):
        tag = ""
    if tag and tag.lower() != wordmark_lower and tag.lower() != avoid_lower:
        return tag

    # 2. Feature-label synthesis: take up to 2 short feature labels. A lone bare
    #    category noun ("Products", "Pricing") is REJECTED here — it reads as a nav
    #    label, never a punchy display headline (the Plaid title='Products' bug).
    #    NAV-LABEL GUARD (R8): a feature scraped as a nav/section item ("Men's Shoes",
    #    "Customer Favorites", "Help Center", "Find a co-host") must NOT seed a synth
    #    — that's the "Men's Shoes · Customer Favorites" hero-title bug. Drop any
    #    candidate that is a nav-label segment, and never RETURN a string that the
    #    UI/nav guard flags (the synth itself is a " · " join → _is_ui_nav_label).
    feats = [f.get("label") or f.get("title") or "" for f in (brand.get("features") or [])]
    feats = [f.strip() for f in feats if f.strip()]
    candidates = [f for f in feats
                  if f.lower() != wordmark_lower and f.lower() != avoid_lower
                  and not _is_weak_headline(f)
                  and not _is_nav_label_segment(f)]
    if candidates:
        short = [f for f in candidates if len(f) <= 26][:2]
        if len(short) >= 2:
            # Only synthesize a " · " pair from TWO real capability labels; a single
            # label paired with nothing is not a join. The synth must not itself read
            # as a nav-tab join (defensive: candidates already passed the nav filter).
            synth = " · ".join(short)
            if synth.lower() != avoid_lower and not _is_ui_nav_label(synth):
                return synth
        # One short label, or no SHORT label but a longer real feature phrase exists:
        # distill a punchy phrase from the first one rather than emit a " · " join or
        # fall through to the bare wordmark.
        punchy = _punchy_headline(candidates[0])
        if (punchy and punchy.lower() != avoid_lower
                and not _is_weak_headline(punchy)
                and not _is_nav_label_segment(punchy)
                and not _is_fragment_subtitle(punchy)):
            return punchy

    return ""


# Title-scene roles / id markers that mean the CLOSING title (a call-to-action),
# as opposed to the OPENING title (the brand lockup). build_timeline derives role
# "close" for a closing-id title; build_props also flags the final scene.
_CLOSING_ROLES = ("close", "cta", "closing", "outro", "end")


def _is_closing_title(scene: Dict[str, Any]) -> bool:
    """True when a title/hero scene is the CLOSING lockup (CTA), not the opening one.

    Signals (any): role/id marks it as a close/cta/outro, OR build_props flagged it
    as the final scene (data._is_closing). The opening title is everything else.
    """
    d = scene.get("data") or {}
    if d.get("_is_closing"):
        return True
    role = _scene_role(scene)
    if role in _CLOSING_ROLES:
        return True
    sid = str(scene.get("id") or "").strip().lower()
    return any(kw in sid for kw in ("clos", "cta", "outro"))


def _brand_name(brand: Dict[str, Any]) -> str:
    """The display brand name for an anchored CTA: wordmark -> brand -> name."""
    return (str(brand.get("wordmark") or brand.get("brand")
                or brand.get("name") or "")).strip()


def _brand_domain(brand: Dict[str, Any]) -> str:
    """A clean visit-able domain from the brand's cta_url/url, WITHOUT scheme/path,
    KEEPING the TLD ('.com') intact (R10 keep-the-.com). '' if none usable."""
    raw = (str(brand.get("cta_url") or brand.get("url") or "")).strip()
    if not raw:
        return ""
    # Strip scheme and any path/query so only the host remains: "https://theverge.com/x"
    # -> "theverge.com". A bare "theverge.com" passes through unchanged.
    host = re.sub(r"^[a-z]+://", "", raw, flags=re.IGNORECASE)
    host = host.split("/", 1)[0].split("?", 1)[0].strip().strip(".")
    return host


def _derive_cta(brand: Dict[str, Any], raw_threaded: str = "") -> str:
    """Derive a REAL, brand-anchored CTA when the planned closing copy is unusable
    (a stage-direction / meta-description, a UI label, or a prompt artifact).

    An imperative addressed to the viewer, anchored to the brand. Priority:
      1. The GROUNDED closing copy salvaged from the threaded VO beat — but ONLY when
         it is itself a real imperative CTA (passes the stage-direction / artifact /
         nav-label guards). This preserves a legitimately-narrated close
         ("Start accepting payments") and keeps the R10 keep-the-.com win
         ("Visit theverge.com" stays intact, domain preserved).
      2. "Get started with <Brand>" / "Start with <Brand>" — a brand-anchored imperative
         (R9 imperative CTA win) when a brand name exists.
      3. "Visit <domain>" — KEEPING the '.com' (R10) — when only a domain is known.
      4. The bare wordmark — never empty.
    """
    # 1. Salvage a real imperative from the grounded closing beat.
    grounded = _punchy_headline(raw_threaded or "")
    if (grounded and not _is_cta_stage_direction(grounded)
            and not _is_ui_nav_label(grounded) and not _is_prompt_artifact(grounded)
            and not _is_fragment_subtitle(grounded)):
        return grounded

    name = _brand_name(brand)
    domain = _brand_domain(brand)
    if name:
        return "Get started with %s" % name
    if domain:
        return "Visit %s" % domain  # keep the .com (R10)
    return name or domain or ""


def _is_section_label_subtitle(text: str) -> bool:
    """True when `text` is a bare SECTION/nav label unsuitable as a subtitle.

    The subtitle may legitimately be a short value-prop tagline that is NOT a full
    clause ("On-demand manufacturing", "Payment Processing") — so we do NOT gate the
    subtitle through the full _looks_like_headline test (that would reject a real
    tagline). Instead reject only the e-commerce SECTION-HEADER class: a short (<=3
    word) PURE Title-Case noun phrase (every significant word capitalized) that reads
    like rotating store chrome ("All Sale", "Customer Favorites", "New Arrivals",
    "Popular Picks", "Best Sellers", "Top Rated").

    Distinguishing signal vs a real tagline: a real value-prop tagline is
    sentence-cased — at least one interior content word is lowercase
    ("On-demand manufacturing", "Built for builders"). A section label capitalizes
    EVERY significant word. So: pure Title-Case + short + no verb/clause = chrome.
    """
    t = (text or "").strip()
    if not t:
        return False
    words = t.split()
    if not (1 <= len(words) <= 3):
        return False  # longer phrases are taglines/headlines, not section chrome
    # A real headline/value-prop is never a section label.
    if _looks_like_headline(t):
        return False
    _TITLECASE_FUNCTION = frozenset((
        "a", "an", "the", "of", "and", "or", "in", "on", "to", "for", "with",
        "by", "at", "from", "as", "&",
    ))
    # Pure Title-Case = every significant (non-function) word starts uppercase.
    has_significant = False
    for w in words:
        cw = w.strip(".,!?;:\"'’“”()")
        if not cw:
            continue
        if cw.lower() in _TITLECASE_FUNCTION:
            continue
        has_significant = True
        if not cw[0].isupper():
            return False  # a lowercase significant word → sentence-cased tagline, keep it
    return has_significant


def _grounded_headline(raw_threaded: str, brand: Dict[str, Any],
                       avoid: str = "", limit: int = 56) -> str:
    """Distill the GROUNDED opening value-prop into a punchy hero headline, or "".

    Source priority (R9 — derive the OPENING title from the grounded value-prop, NOT
    scraped feature/section labels):
      1. The planner's OPENING VO BEAT (`raw_threaded`) — a complete grounded sentence
         like "Allbirds makes comfortable shoes from natural, sustainable materials."
         distilled via _punchy_headline (clause-end + numeral guards) into a crisp
         headline ("Allbirds makes comfortable shoes from natural, sustainable
         materials"). This is the world-grounded line the planner produced for THIS
         brand, so it is always on-topic.
      2. The brand's world-knowledge / real tagline — _clean_complete_headline of
         brand.tagline (a hand-verified known-brand tagline, or a clean scraped one).
      3. "" — caller falls to the wordmark.

    Every candidate must pass the POSITIVE _looks_like_headline test (a real
    headline/value-prop, not a section label) AND not be a weak/nav/artifact string
    AND differ from `avoid` (the wordmark). Entity-decoded by the caller's _decode().
    """
    avoid_l = (avoid or "").strip().lower()

    def _ok(cand: str) -> bool:
        if not cand:
            return False
        c = cand.strip()
        if c.lower() == avoid_l:
            return False
        if _is_weak_headline(c) or _is_ui_nav_label(c) or _is_prompt_artifact(c):
            return False
        return _looks_like_headline(c)

    # 1. Distill the grounded opening VO beat.
    cand = _punchy_headline(raw_threaded or "", limit=limit)
    if _ok(cand):
        return cand
    # Some VO beats are short enough that _punchy_headline returns "" (it requires
    # >=2 words AND trims tails); fall back to a plain clause clamp of the same line.
    cand = _title_from_text(raw_threaded or "", limit=72)
    if _ok(cand):
        return cand
    # 2. World-knowledge / real tagline.
    cand = _clean_complete_headline(brand.get("tagline") or "")
    if _ok(cand):
        return cand
    return ""


def _shape_hero(scene: Dict[str, Any], brand: Dict[str, Any]) -> Dict[str, Any]:
    """HeroTitle data: kicker / title / punchWord / subtitle.

    OPENING title -> brand lockup: wordmark + tagline headline (the spoken line for
    an opening title just narrates the wordmark, so the tagline reads better).
    CLOSING title -> call-to-action: the scene's OWN closing line (from its threaded
    VO beat / brief) becomes the headline, the brand wordmark renders as a smaller
    sub-line (HeroTitle draws theme.wordmark above the title whenever it differs
    from the title), and the brand URL sits under it. NEVER the wordmark twice; the
    kicker is dropped on the close so the wordmark isn't echoed as the eyebrow.
    The title is NEVER empty.

    DISTINCT TAGLINE RULE: eyebrow ≠ display ≠ subtitle. When the would-be title is
    effectively the same word as the wordmark (no meaningful tagline), _distinct_tagline
    synthesizes a short value-prop line from brand features so the hierarchy is never
    redundant ("PLAID" / "Plaid" / "Plaid" -> "PLAID" / tagline / url instead).
    """
    d = scene.get("data") or {}
    wordmark = (brand.get("wordmark") or brand.get("brand") or brand.get("name") or "").strip()
    raw_threaded = d.get("_text") or scene.get("brief") or ""
    threaded = _title_from_text(d.get("_text") or "") or _title_from_text(scene.get("brief") or "")

    if _is_closing_title(scene):
        # CTA headline = the closing line actually narrated, distilled into a PUNCHY
        # phrase ("Start building better financial products") — NOT the raw spoken
        # sentence, which truncates mid-URL ("...with Plaid at plaid"). _punchy_headline
        # strips the trailing CTA tail ("at <domain>", "with <brand>", "today"). Fall
        # back to a tagline/wordmark only if the plan threaded no closing copy.
        punchy_cta = _punchy_headline(d.get("_text") or "") or _punchy_headline(scene.get("brief") or "")
        # Sanitize explicit plan title: reject UI-label, prompt-artifact, OR a
        # self-referential STAGE-DIRECTION / meta-description that DESCRIBES the CTA card
        # instead of addressing the viewer (R11 — "Closing call‑to‑action card urging
        # users", "Call-to-action card using the brand color", "Closing card with the
        # wordmark", "Show the CTA"). R7-G3's planner sanitizer caught only the
        # "Show call-to-action:" verb-colon form; this is the last line of defense.
        explicit_title = d.get("title") or ""
        if explicit_title and (_is_ui_nav_label(explicit_title)
                               or _is_prompt_artifact(explicit_title)
                               or _is_cta_stage_direction(explicit_title)):
            explicit_title = ""
        # The threaded/distilled closing line can ALSO be a stage direction (the leak
        # came in via the planner's closing VO beat → d["_text"]); reject it the same way.
        if punchy_cta and _is_cta_stage_direction(punchy_cta):
            punchy_cta = ""
        if threaded and _is_cta_stage_direction(threaded):
            threaded = ""
        title = (explicit_title or punchy_cta or threaded).strip()
        # R11: the plan THREADED closing copy but EVERY usable source was rejected as a
        # stage-direction / artifact. Don't fall to the bare wordmark — that's not a CTA.
        # DERIVE a real brand-anchored imperative ("Get started with <Brand>" / "Visit
        # <domain>"). Only when NO copy was threaded at all do we keep the tagline/wordmark
        # lockup fallback (an opening-style brand close, which is a legitimate design).
        had_closing_copy = bool((d.get("title") or "").strip()
                                or (d.get("_text") or "").strip()
                                or (scene.get("brief") or "").strip())
        if not title and had_closing_copy:
            title = _derive_cta(brand, d.get("_text") or scene.get("brief") or "")
        if not title:
            title = (_brand_fallback_title(brand) or wordmark or "").strip()
        # FINAL CTA GUARD: if we somehow still hold a stage-direction/meta-description
        # (or nothing usable), DERIVE a real brand-anchored imperative CTA.
        if not title or _is_cta_stage_direction(title) or _is_prompt_artifact(title):
            title = (_derive_cta(brand, d.get("_text") or scene.get("brief") or "")
                     or wordmark)
        subtitle = d.get("subtitle")
        if subtitle is None:
            subtitle = (brand.get("cta_url")
                        or _clean_complete_headline(brand.get("tagline") or "") or "")
        # Ensure subtitle ≠ title (distinct tagline rule for CTA).
        if subtitle and subtitle.strip().lower() == title.strip().lower():
            subtitle = brand.get("cta_url") or ""
        # FRAGMENT GUARD: reject a subtitle that is a scrape fragment (lowercase-leading,
        # preposition-final, or single-word). Fall back to cta_url or drop.
        if _is_fragment_subtitle(subtitle):
            subtitle = brand.get("cta_url") or ""
        # R11 SUBTITLE GUARD: a stage-direction / meta-description must not survive as
        # the closing SUBTITLE either ("Call-to-action card using the brand color"
        # threaded as the subtitle). Fall back to the brand URL, else drop.
        if subtitle and (_is_cta_stage_direction(subtitle) or _is_prompt_artifact(subtitle)):
            subtitle = brand.get("cta_url") or ""
        out = {
            # No kicker on the close: the wordmark already renders as the sub-line,
            # so a "ORINOVATE" eyebrow would show the wordmark twice.
            "kicker": _decode(d.get("kicker") or ""),
            "title": _decode(title),
            "subtitle": _decode(subtitle or ""),
        }
    else:
        # OPENING title (R9): DERIVE the headline from the GROUNDED value-prop, NOT
        # from scraped feature/section labels. E-commerce homepages surface endless
        # rotating section headers ("Popular Picks", "Customer Favorites", "New
        # Arrivals") that denylisting can never fully enumerate; the POSITIVE
        # _looks_like_headline test rejects the whole class (a Title-Case noun phrase
        # with no verb is chrome, by construction), and the grounded opening VO beat
        # supplies a real value-prop headline for ANY brand.

        # 1. An EXPLICIT plan title is authoritative ONLY when it reads like a real
        #    headline — reject UI-label/prompt-artifact copy AND any scraped phrase
        #    that fails the positive headline test ("Popular Picks", "All Sale").
        explicit_title_open = (d.get("title") or "").strip()
        if explicit_title_open and not (
                _looks_like_headline(explicit_title_open)
                and not _is_ui_nav_label(explicit_title_open)
                and not _is_prompt_artifact(explicit_title_open)):
            explicit_title_open = ""

        if explicit_title_open:
            title = explicit_title_open
        else:
            # 2. No real H1 / explicit headline → DERIVE from the grounded value-prop:
            #    distill the planner's opening VO beat, else the world-knowledge / real
            #    tagline, else the wordmark. NEVER pick or synthesize the opening title
            #    from scraped feature/section labels (no _distinct_tagline here — that
            #    synthesizes from feature labels, the "Popular Picks · All Sale" bug).
            grounded = _grounded_headline(raw_threaded, brand, avoid=wordmark, limit=56)
            title = grounded or wordmark or threaded or ""

        # FINAL HEADLINE GUARD: a weak display title (a bare category noun like
        # "Products", or a lone wordmark) is never a punchy on-card headline. Distill
        # a real grounded phrase from the threaded opening VO line / world tagline
        # before falling back to the wordmark. (Grounded-first; no feature-label synth.)
        if _is_weak_headline(title) or (wordmark and title.lower() == wordmark.lower()):
            grounded = _grounded_headline(raw_threaded, brand, avoid=wordmark, limit=56)
            if grounded:
                title = grounded

        # NAV-LABEL RENDER GUARD (R8, belt-and-suspenders): a UI/nav-label or a
        # separator-joined nav pair ("Men's Shoes · Customer Favorites") must NEVER be
        # the rendered hero title even if some path produced one. Fall to the grounded
        # value-prop headline and finally the wordmark.
        if _is_ui_nav_label(title) or _is_prompt_artifact(title):
            title = _grounded_headline(raw_threaded, brand, avoid=wordmark, limit=56) \
                or wordmark or ""

        subtitle = d.get("subtitle")
        if subtitle is None:
            # Subtitle must be distinct from both title AND wordmark.
            sub_cand = _distinct_tagline(brand, avoid=title)
            subtitle = sub_cand if sub_cand else ""
        # Final guard: never show wordmark in subtitle when it already shows as eyebrow/title.
        if subtitle and subtitle.strip().lower() == wordmark.lower():
            subtitle = ""
        # FRAGMENT GUARD + SALVAGE: a scrape fragment (lowercase-leading, preposition-
        # final, or single-word) must never render. Before blanking it, salvage —
        # (a) a complete leading sentence from the fragment's own text, then (b) the
        # brand's real distinct value-prop / tagline. Empty only if nothing usable and
        # distinct remains ("store they line up for", the Shopify residual: dropped,
        # never rendered verbatim).
        if subtitle and _is_fragment_subtitle(subtitle):
            salvaged = _clean_complete_headline(subtitle)
            if (salvaged and not _is_fragment_subtitle(salvaged)
                    and salvaged.strip().lower() not in (wordmark.lower(),
                                                         title.strip().lower())):
                subtitle = salvaged
            else:
                sub_cand = _distinct_tagline(brand, avoid=title)
                subtitle = sub_cand if (sub_cand and not _is_fragment_subtitle(sub_cand)) else ""
        # NAV-LABEL / SECTION-LABEL GUARD: a UI/nav-label, separator-joined nav pair,
        # OR a bare section label that fails the positive headline test ("All Sale",
        # "Customer Favorites") must not render as the subtitle either (allbirds
        # subtitle was "Men's Shoes" / "All Sale"). A real value-prop subtitle passes
        # _looks_like_headline; a section-chrome label does not. We keep multi-word
        # value-prop taglines that aren't full clauses (e.g. "On-demand manufacturing")
        # by only rejecting strings the nav/label guards positively flag.
        if subtitle and (_is_ui_nav_label(subtitle) or _is_prompt_artifact(subtitle)
                         or _is_section_label_subtitle(subtitle)):
            subtitle = ""
        out = {
            "kicker": _decode(d.get("kicker") or wordmark.upper()),
            "title": _decode(title),
            "subtitle": _decode(subtitle or ""),
        }
    # punchWord must be a substring of title for the accent split to fire.
    punch = d.get("punchWord")
    decoded_title = out["title"]
    if punch and _decode(punch) in decoded_title:
        out["punchWord"] = _decode(punch)
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
    # Decode entities in card labels/values/subs.
    decoded_cards = [
        {
            "label": _decode(c.get("label") or ""),
            "value": _decode(c["value"]) if c.get("value") is not None else None,
            "sub": _decode(c["sub"]) if c.get("sub") is not None else None,
            "accent": c["accent"],
        }
        for c in cards
    ]
    return {
        "heading": _decode(d.get("heading") or "Built to ship"),
        "headingAccent": _decode(d.get("headingAccent") or ""),
        "cards": decoded_cards,
    }


_DANGLING_WORDS = frozenset((
    "from", "to", "and", "with", "at", "of", "for", "the", "a", "an",
    "in", "on", "or", "by", "as", "but", "so", "nor", "yet",
    # Determiners / possessives / articles that introduce a following noun — a
    # headline must never end on one (mid-possessive chop, e.g. "that keep your",
    # "powers its", "for their"). "their" is already covered as a bare-quantifier
    # but listing it here keeps the dangling-tail strip self-contained.
    "your", "its", "their", "our", "his", "her", "my", "this", "these", "those",
    # Relative/subordinating words that open a following clause — a headline must
    # never end on these (mid-relative-clause chop, e.g. "brands for men who",
    # "builds apps that", "a platform where", "markets which").
    "who", "that", "which", "where", "when", "while", "than", "whose", "whom",
))

# Trailing present-participle / gerund "helper" words. When a distilled headline ends
# on one of these AFTER a complete clause, the participle opens a following subordinate
# clause that was clipped ("...self-driving, letting", "...runners keeping", "...gear
# making"). A headline must NOT end on a dangling participle-helper. This set is the
# COMMON clause-bridge participles; a content-word -ing ending ("Linear makes shipping
# faster") is NOT in here, so it is preserved.
_DANGLING_PARTICIPLES = frozenset((
    "letting", "keeping", "making", "helping", "giving", "bringing", "turning",
    "allowing", "enabling", "powering", "driving", "creating", "building",
    "delivering", "providing", "offering", "connecting", "growing", "scaling",
    "saving", "earning", "moving", "sending", "putting", "getting", "showing",
    "leaving", "letting", "having", "using", "doing", "being", "going",
    "starting", "ensuring", "guiding", "leading",
))


# A sentence-terminating "." (or ! or ?) is followed by whitespace or end-of-string.
# A "." glued to a following alnum token is part of a domain/decimal ("theverge.com",
# "12.5") and is NOT a sentence boundary — splitting there drops the TLD ("Visit
# theverge.com" -> "Visit theverge"), the theverge CTA bug. "!" / "?" / newlines are
# always boundaries (they don't appear mid-domain).
_SENTENCE_BOUNDARY_RE = re.compile(r"(?:\.(?=\s|$))|[!?\n]")


def _split_first_sentence(text: str) -> str:
    """First sentence of `text`, treating a "." inside a domain/decimal as NON-terminal
    so a trailing CTA domain (".com") is preserved ("Visit theverge.com" stays whole)."""
    m = _SENTENCE_BOUNDARY_RE.search(text)
    return (text[:m.start()] if m else text).strip()


def _strip_dangling_tail(text: str) -> str:
    """Drop a trailing comma AND any dangling tail word — a function word
    (preposition/conjunction/article/relative-pronoun in _DANGLING_WORDS), a
    determiner/possessive ("your"/"its"), or a clause-bridge participle-helper
    ("letting"/"keeping") — so the phrase ends on a CONTENT word that completes the
    thought, never on a dangling token. Idempotent; strips repeatedly so a
    "..., letting" tail collapses past both the participle AND the trailing comma.
    """
    head = (text or "").strip().rstrip(",").strip()
    words = head.split()
    while words:
        last = words[-1].lower().rstrip(",.")
        if last in _DANGLING_WORDS or last in _DANGLING_PARTICIPLES:
            words.pop()
            continue
        # A trailing comma glued to a content word ("wikis,") means the clause was cut
        # mid-list — drop the comma (the word stays; "...docs, wikis" reads complete).
        if words[-1].endswith(","):
            words[-1] = words[-1].rstrip(",")
        break
    return " ".join(words)


# Clause-boundary punctuation/words at which a long sentence can be cut to a COMPLETE
# leading clause rather than hard-chopped mid-phrase. A comma/semicolon/colon ends a
# clause; a relative/subordinating pronoun OPENS a trailing clause (so we cut BEFORE
# it). We never cut inside a domain (the "." guard lives in _split_first_sentence).
_CLAUSE_CUT_RE = re.compile(r"[,;:]")
_CLAUSE_OPENERS = frozenset((
    "that", "which", "who", "whom", "whose", "where", "when", "while", "so",
    "letting", "keeping", "making", "helping", "giving", "allowing", "enabling",
))


def _first_complete_clause(text: str, limit: int) -> str:
    """Prefer the FIRST COMPLETE CLAUSE that fits within `limit` over a hard word-count
    chop, so a long VO beat distills to a clean complete phrase instead of a dangling
    mid-clause tail. "Allbirds makes comfortable wool runners that keep your feet warm"
    -> "Allbirds makes comfortable wool runners" (cut before the relative-clause opener)
    rather than "...that keep your". Returns "" when no in-limit clause boundary exists
    (the caller then falls back to the hard-chop-then-strip path).
    """
    t = (text or "").strip()
    if not t:
        return ""
    # Candidate cut points: each clause-punctuation position, plus the position just
    # BEFORE each clause-opener word. Keep the LONGEST complete clause that still fits.
    cuts = [m.start() for m in _CLAUSE_CUT_RE.finditer(t)]
    words = t.split()
    # Word-start offsets, to locate clause-opener boundaries by character position.
    pos, offsets = 0, []
    for w in words:
        idx = t.find(w, pos)
        offsets.append(idx)
        pos = idx + len(w)
    for i, w in enumerate(words):
        if i > 0 and w.lower().strip(".,!?;:") in _CLAUSE_OPENERS:
            cuts.append(offsets[i] - 1)  # cut just before the opener
    best = ""
    for c in sorted(set(cuts)):
        cand = _strip_dangling_tail(t[:c])
        if cand and len(cand) <= limit and len(cand.split()) >= 2:
            best = cand  # longest fitting complete clause wins
    return best


def _title_from_text(text: str, limit: int = 72) -> str:
    """A short, honest title from a scene's brief/VO text: the first clause,
    trimmed. NEVER fabricates marketing copy — it just truncates real text.

    The result reads as a COMPLETE phrase:
      - Trailing commas are stripped.
      - A dangling function word (preposition, conjunction, article, or relative
        pronoun like "who"/"that"/"which"/"where") at the end is ALWAYS dropped,
        whether the string was truncated or not — so "brands for men who" becomes
        "brands for men" (the mid-relative-clause chop guard).
      - Prefer ending at the last full sentence that fits over a hard mid-clause cut.
    """
    if not text:
        return ""
    # First sentence/clause, then a hard length clamp on a word boundary.
    # DOMAIN GUARD: a "." inside a domain ("theverge.com", "stripe.com") is NOT a
    # sentence boundary — it must NOT split "Visit theverge.com" into "Visit theverge"
    # (dropping ".com", the theverge CTA bug). Only split on a "." that is followed by
    # whitespace or end-of-string (a real sentence terminator), never on a "." glued to
    # a following TLD-like token.
    head = _split_first_sentence(str(text).strip())
    head = re.split(r"\s+[—–-]\s+", head, maxsplit=1)[0].strip()
    if len(head) > limit:
        # COMPLETE-CLAUSE-FIRST: prefer the first complete clause that fits (cut at a
        # comma/semicolon/colon or before a relative-clause opener) over a hard
        # mid-clause word chop, so "...runners that keep your feet warm" distills to
        # "...runners", never "...that keep your".
        clause = _first_complete_clause(head, limit)
        if clause:
            head = clause
        else:
            cut = head[:limit].rsplit(" ", 1)[0]
            head = cut or head[:limit]
    # Strip a trailing comma + any dangling tail (function word, possessive, or a
    # clause-bridge participle-helper) — applies BOTH when the string was truncated AND
    # when it naturally ends on a dangling token ("brands for men who" -> "brands for
    # men"; "...docs, wikis," -> "...docs, wikis"; "...self-driving, letting" ->
    # "...self-driving").
    out = _strip_dangling_tail(head)
    return out if out else head


# Bare generic nouns that read as a label, not a punchy headline. A feature scraped
# as just "Products" / "Pricing" must NEVER become the on-card display title (the
# Plaid `title='Products'` failure). A real punchy headline is a verb-led imperative
# or a multi-word benefit phrase, not a lone category noun.
_BARE_NOUN_HEADLINES = frozenset((
    "products", "product", "pricing", "features", "feature", "solutions",
    "solution", "platform", "overview", "company", "about", "home", "docs",
    "developers", "customers", "resources", "enterprise", "use cases", "use case",
))


def _is_weak_headline(text: str) -> bool:
    """True when `text` is too weak to be an on-CARD display headline: empty, a lone
    bare category noun ("Products", "Pricing"), or a 1-word fragment. These read as a
    nav label, not the punchy imperative/benefit phrase the reference films use."""
    t = (text or "").strip().strip(" .!?,:;—-").strip()
    if not t:
        return True
    if t.lower() in _BARE_NOUN_HEADLINES:
        return True
    # A single word (with no real verb-object) is never a headline.
    return len(t.split()) <= 1


# ---------------------------------------------------------------------------
# POSITIVE HEADLINE TEST  (R9 — replaces the negative nav-label denylist for the
# OPENING title). A scraped phrase may be used as the hero title ONLY if it reads
# like a real headline / value-prop: it contains a VERB or is a full clause/sentence,
# NOT a short Title-Case noun phrase. E-commerce homepages surface endless rotating
# section headers ("Popular Picks", "Customer Favorites", "New Arrivals", "Best
# Sellers", "Featured", "Shop All", "Help Center", "Men's Shoes", "Gift Guide",
# "Top Rated") — these are nav/section chrome and must NEVER be eligible as the title.
# Denylisting them is whack-a-mole; the positive test rejects the WHOLE class:
# a Title-Case noun phrase with no verb is chrome, by construction.
# ---------------------------------------------------------------------------

# Common English verbs (base + frequent inflections) that signal a real clause.
# Covers the imperative/3rd-person value-prop verbs the reference films use
# ("Build internet businesses", "Allbirds makes comfortable shoes"). Not exhaustive
# — the morphological -s/-ing/-ed signal below catches the long tail.
_HEADLINE_VERBS = frozenset((
    "build", "builds", "make", "makes", "made", "ship", "ships", "create",
    "creates", "plan", "plans", "design", "designs", "power", "powers",
    "help", "helps", "connect", "connects", "process", "processes", "manage",
    "manages", "track", "tracks", "run", "runs", "grow", "grows", "scale",
    "scales", "sell", "sells", "buy", "buys", "find", "finds", "search",
    "searches", "discover", "discovers", "deliver", "delivers", "launch",
    "launches", "automate", "automates", "is", "are", "lets", "let", "turn",
    "turns", "bring", "brings", "give", "gives", "send", "sends", "move",
    "moves", "pay", "pays", "save", "saves", "earn", "earns", "learn",
    "learns", "work", "works", "do", "does", "get", "gets", "start", "starts",
    "join", "joins", "explore", "explores", "compare", "compares", "book",
    "books", "order", "orders", "trust", "trusts", "love", "loves", "see",
    "sees", "meet", "meets", "use", "uses", "drive", "drives", "fuel",
    "fuels", "unlock", "unlocks", "enable", "enables", "transform",
    "transforms", "accelerate", "accelerates", "simplify", "simplifies",
    "streamline", "streamlines", "empower", "empowers", "support", "supports",
    "lead", "leads", "serve", "serves", "offer", "offers", "provide",
    "provides", "reach", "reaches", "list", "lists", "rent", "rents", "stay",
    "stays", "travel", "travels", "read", "reads", "write", "writes",
))

# Linking/auxiliary words whose presence implies a clause is being formed
# ("X is the platform that…", "we help teams…"). A bare label never contains these.
_CLAUSE_SIGNALS = frozenset((
    "is", "are", "was", "were", "be", "been", "your", "you", "we", "our",
    "they", "their", "it", "its", "every", "everyone", "anything", "everything",
    "that", "which", "who", "where", "when", "how", "why", "into", "from",
    "with", "without", "across", "through", "for", "so", "to",
))


def _looks_like_headline(text: str) -> bool:
    """POSITIVE test: True when `text` reads like a real headline / value-prop and is
    therefore eligible to be used as the OPENING hero title.

    A phrase qualifies when it has the SHAPE of a clause, not a label:
      (1) it contains a recognizable VERB (from _HEADLINE_VERBS or a clear -ing/-ed/
          3rd-person -s/-es inflection on a non-capitalized content word), OR
      (2) it is a FULL clause/sentence: ends with terminal punctuation, OR it carries
          a clause signal (a linking/auxiliary/pronoun word), OR it has a lowercase
          content word (a value-prop is sentence-cased, not Title-Cased).

    DISQUALIFIES the whole class of short Title-Case noun-phrase section labels
    ("Popular Picks", "Customer Favorites", "New Arrivals", "Best Sellers",
    "Featured", "Shop All", "Help Center", "Men's Shoes", "Gift Guide", "Top Rated"):
    every significant word capitalized, no verb, no clause signal → label, not headline.

    Conservative on real headlines: "Build internet businesses", "Plan and build
    products", "Allbirds makes comfortable shoes from natural wool" all PASS.
    """
    t = (text or "").strip()
    if not t:
        return False
    # Hard rejects up front: nav chrome / prompt artifacts are never headlines, and a
    # bare category noun ("Products") is too weak.
    if _is_ui_nav_label(t) or _is_prompt_artifact(t) or _is_weak_headline(t):
        return False
    words = t.split()
    if len(words) < 2:
        return False  # a lone word is a label, never a headline

    # (2a) Ends on terminal sentence punctuation → a full sentence/clause.
    if t.rstrip().endswith((".", "!", "?")):
        return True

    lower_words = [w.lower().strip(".,!?;:\"'’“”()") for w in words]

    # (1) Contains a recognizable verb. Known verbs match regardless of case (an
    # imperative headline often leads with a capitalized verb — "Build …", "Plan …").
    # The MORPHOLOGICAL -ing/-ed signal only counts on a LOWERCASE token, because a
    # Title-Cased "-ed"/"-ing" word is part of a section label ("Top Rated", "Most
    # Loved", "Trending Now"), not a clause verb — a real value-prop verb is
    # sentence-cased ("Allbirds makes …", "powered by …").
    for i, w in enumerate(lower_words):
        if w in _HEADLINE_VERBS:
            return True
        orig = words[i].strip(".,!?;:\"'’“”()")
        if (orig and orig[0].islower() and len(w) >= 5
                and (w.endswith("ing") or w.endswith("ed"))):
            return True

    # (2b) Carries a clause signal (linking/auxiliary/pronoun/subordinator word).
    # Require >=3 words so a 2-word Title-Case about/section label that merely starts
    # with a pronoun ("Our Story", "Your Account") is NOT mistaken for a clause — a
    # real clause-signal value-prop ("We help your team ship", "Built for the way you
    # work") has more than two words.
    if len(lower_words) >= 3 and any(w in _CLAUSE_SIGNALS for w in lower_words):
        return True

    # (2c) A value-prop is sentence-cased: at least one INTERIOR content word is
    # lowercase (not Title-Cased). A pure Title-Case noun phrase ("Popular Picks",
    # "Customer Favorites") capitalizes every significant word → has NO lowercase
    # interior content word → fails here → classified as a label.
    # Skip the first word (often a leading cap regardless) and very short function
    # words (a/an/the/of/and/or/in/on/to/for/with/by — lowercase by convention even
    # in Title Case, so their lowercase-ness is not evidence of a clause).
    _TITLECASE_FUNCTION = frozenset((
        "a", "an", "the", "of", "and", "or", "in", "on", "to", "for", "with",
        "by", "at", "from", "as", "&",
    ))
    for w in words[1:]:
        cw = w.strip(".,!?;:\"'’“”()")
        if not cw:
            continue
        low = cw.lower()
        if low in _TITLECASE_FUNCTION:
            continue
        # An interior content word that is all-lowercase → sentence-cased → headline.
        if cw[0].islower() and cw.isalpha():
            return True
    return False


# A standalone trailing temporal CTA marker ("... today", "... right now").
_CTA_TEMPORAL_RE = re.compile(
    r"\s*(?:[—–-]\s*)?\b(?:today|now|right\s+now|right\s+away)\b\.?\s*$",
    re.IGNORECASE,
)
# A trailing prepositional CTA tail that points at a SITE/BRAND, e.g. "at stripe.com",
# "with Plaid at plaid.com", "on Tripadvisor". We strip it ONLY when the tail names a
# domain (contains a dot) — that is what makes it a CTA address, not mid-sentence
# content. A descriptive "with over 800 million reviews" has no domain, so it stays.
_CTA_DOMAIN_TAIL_RE = re.compile(
    r"\s*\b(?:at|on|with|via|using|through)\b\s+[^.,;:!?]*\b\w+\.\w{2,}\b.*$",
    re.IGNORECASE,
)


def _punchy_headline(text: str, limit: int = 48) -> str:
    """Distill a SHORT, punchy headline phrase from a longer spoken line.

    Strips a trailing CTA tail that points at the site/brand ("at stripe.com",
    "with Plaid at plaid.com") plus a trailing temporal marker ("today", "right
    now"), and any leftover dangling function word — so a long closing-CTA beat
    becomes a crisp imperative phrase ("Start building better financial products")
    instead of a mid-URL truncation. It is CONSERVATIVE: a descriptive prepositional
    phrase with no domain ("with over 800 million reviews") is NOT a CTA tail and is
    preserved, so an OPENING line stays a complete clause. NEVER fabricates — it only
    trims the real text. Returns "" if nothing usable remains.
    """
    t = (text or "").strip()
    if not t:
        return ""
    # Peel the CTA tails on the RAW text FIRST — before any sentence clamp — because a
    # naive sentence split breaks "stripe.com" at its dot and would hide the domain
    # from the domain-tail matcher. Strip the temporal marker, then a trailing
    # sentence period, then the domain-pointing prepositional tail, repeatedly (handles
    # "... with Plaid at plaid.com today.").
    head = t
    prev = None
    while head and head != prev:
        prev = head
        head = head.rstrip().rstrip(".").strip()
        head = _CTA_TEMPORAL_RE.sub("", head).strip()
        head = _CTA_DOMAIN_TAIL_RE.sub("", head).strip()
    # Now take the first remaining sentence/clause and clamp to length.
    head = _title_from_text(head, limit=max(limit, 72))
    # Strip a trailing comma + any dangling tail word (function word, possessive, OR a
    # clause-bridge participle-helper like "letting"/"keeping") so the phrase never ends
    # on a dangling token ("...self-driving, letting" -> "...self-driving").
    head = _strip_dangling_tail(head)
    # The COMPLETE clause (<=72 chars), captured BEFORE the soft-limit truncation
    # below. A number followed by a unit + noun must keep its noun: when a dangling
    # number tail below is merely a truncation artifact, we restore from this clause.
    full_clause = head
    # Final length clamp to a word boundary (keep the lead verb-object, not the tail).
    # COMPLETE-CLAUSE GUARD: if truncation (or the raw text itself) ends mid-clause,
    # back up past the dangling prepositional/conjunction bridge so the headline ends
    # on a COMPLETE phrase, not a dangling tail like "to millions", "access to",
    # "of reviews". Applies BOTH when the text exceeds limit (truncation case) AND
    # when it fits within limit but the last two words form an incomplete prep phrase
    # (e.g. VO beat ends mid-sentence: "...gives travelers access to millions").
    _was_truncated = len(head) > limit
    if _was_truncated:
        # COMPLETE-CLAUSE-FIRST: prefer the first complete clause that fits the limit
        # (cut at a comma/semicolon/colon or BEFORE a relative-clause / participle
        # opener) over a hard mid-clause word chop. "...wool runners that keep your
        # feet warm" -> "...wool runners" (never "...that keep your"); "...workspace
        # for docs, wikis, and projects" -> "...workspace for docs" (never "wikis,").
        clause = _first_complete_clause(head, limit)
        if clause:
            truncated = clause
        else:
            truncated = head[:limit].rsplit(" ", 1)[0].rstrip(",").strip()
            truncated = _strip_dangling_tail(truncated)
        head = truncated
        # DANGLING-PREP-PHRASE guard (only when truncation actually cut the source):
        # a tail of "PREP + one short object" ("from natural", "with sharp", "for
        # businesses") is an INCOMPLETE prepositional phrase whose object was clipped.
        # Back up past the whole prep phrase to the last complete clause so the
        # grounded headline ends cleanly ("Allbirds makes comfortable shoes from
        # natural" -> "Allbirds makes comfortable shoes"). Only fires on truncation,
        # so a naturally-complete tail ("made from wool", "built for builders") is
        # preserved (that text fit within the limit and never entered this branch).
        _PREP_BRIDGES = frozenset((
            "from", "with", "for", "of", "in", "on", "at", "to", "into", "onto",
            "by", "as", "about", "over", "across", "through",
        ))
        w2 = head.split()
        if (len(w2) >= 3
                and w2[-2].lower().rstrip(",.") in _PREP_BRIDGES):
            # Drop the prep + its clipped object, then any newly-dangling tail word.
            w2 = w2[:-2]
            while w2 and w2[-1].lower().rstrip(",.") in _DANGLING_WORDS:
                w2.pop()
            if len(w2) >= 2:  # keep only if a real clause remains
                head = " ".join(w2)

    # Mid-clause chop guard (applies after truncation AND on raw sub-limit text):
    # Cases that produce a semantically incomplete tail:
    #   1. The last word itself is a function word ("access to", "hotels and") — already
    #      handled by the dangling-word strip above (the while loop).
    #   2. The last word is a vague quantifier (e.g. "millions", "thousands") that reads
    #      as incomplete without a following noun phrase — especially when preceded by
    #      "to"/"of"/"for" etc. (e.g. "access to millions", "see of hundreds").
    #   3. The last word is a NUMERAL or MAGNITUDE WORD (e.g. "800", "12,000", "million",
    #      "billion") — these always need a following noun to be complete. A headline must
    #      NEVER end on a bare number or magnitude word like "over 800 million" (the
    #      TripAdvisor residual: "…access to over 800 million" dropped "trusted reviews").
    #      Detection: last token matches a numeral pattern OR is a magnitude-scale word;
    #      if preceded by a function/quantifier word OR another numeral, back up past the
    #      entire dangling number phrase to the nearest content word.
    _BARE_QUANTIFIERS = frozenset((
        "millions", "thousands", "hundreds", "billions", "dozens",
        "many", "some", "few", "several", "various", "multiple",
        "all", "both", "each", "every", "those", "these", "their",
        # singular magnitude scale words (case 3)
        "million", "billion", "trillion", "thousand", "hundred",
    ))
    # A token is a bare numeral when it consists of digits, commas, dots, and optional
    # trailing scale suffix (k/m/b). Examples: "800", "12,000", "1.3m", "4b".
    _NUMERAL_RE = re.compile(r"^\d[\d,.]*(k|m|b)?$", re.IGNORECASE)

    def _is_dangling_number_tail(words: list) -> bool:
        """True when the word list ends on an incomplete number/quantifier phrase."""
        if not words:
            return False
        last = words[-1].lower().rstrip(",.")
        # Case 2: bare vague quantifier (e.g. "millions")
        if last in _BARE_QUANTIFIERS:
            # Only flag it when preceded by a function word or another number token
            # (avoids flagging "Stripe serves millions" where "millions" is complete).
            if len(words) >= 2:
                prev = words[-2].lower().rstrip(",.")
                if prev in _DANGLING_WORDS or _NUMERAL_RE.match(prev) or prev in _BARE_QUANTIFIERS:
                    return True
            return False
        # Case 3: bare numeral token (e.g. "800", "12,000", "1.3m")
        if _NUMERAL_RE.match(last):
            return True
        return False

    # Quantifier-modifier words that precede numbers/magnitudes (e.g. "over 800",
    # "about 12,000", "more than 5 million") — strip these alongside the numeral so
    # "access to over 800" becomes "access" (not "access to over").
    _QUANTIFIER_MODIFIERS = frozenset((
        "over", "about", "approximately", "around", "nearly", "roughly",
        "more", "less", "than", "almost", "exactly", "just", "only",
    ))

    w2 = head.split()
    if _is_dangling_number_tail(w2):
        # KEEP-THE-NOUN guard: the dangling number tail is usually a TRUNCATION
        # ARTIFACT — the complete clause continues with the unit/noun that completes
        # the numeric claim (e.g. "...over 800 million" was clipped from "...over 800
        # million trusted reviews"). When the complete clause does NOT itself end on a
        # bare number, restore it whole so the stat keeps its noun, rather than dropping
        # the most compelling part of the headline. A number+unit+noun must keep the noun.
        if full_clause != head and not _is_dangling_number_tail(full_clause.split()):
            head = full_clause
        else:
            # The SOURCE genuinely ends on a bare number (no completing noun). Strip
            # back past the entire dangling number phrase (may be multiple tokens, e.g.
            # "over 800 million" needs stripping of "over", "800", "million"; "access to
            # over 800" -> strip "800", then "over", then "to" -> "access").
            while w2 and (
                w2[-1].lower().rstrip(",.") in _DANGLING_WORDS
                or w2[-1].lower().rstrip(",.") in _BARE_QUANTIFIERS
                or w2[-1].lower().rstrip(",.") in _QUANTIFIER_MODIFIERS
                or _NUMERAL_RE.match(w2[-1].lower().rstrip(",."))
            ):
                w2.pop()
            head = " ".join(w2)
    elif len(w2) >= 2 and w2[-2].lower() in _DANGLING_WORDS and w2[-1].lower() in _BARE_QUANTIFIERS:
        # Original guard: "PREP QUANTIFIER" tail (kept as belt-and-suspenders).
        w2 = w2[:-2]
        while w2 and w2[-1].lower() in _DANGLING_WORDS:
            w2.pop()
        head = " ".join(w2)

    return head if len(head.split()) >= 2 else ""


# Tokens too generic to identify a feature (avoid a spurious "best match").
_FEATURE_STOPWORDS = frozenset((
    "the", "and", "or", "a", "an", "of", "to", "for", "with", "your", "our",
    "machine", "machining", "part", "parts", "metal", "service", "services",
    "manufacturing", "instant", "quote", "quotes", "get", "file", "fast", "today",
))


def _feature_tokens(text: str) -> set:
    """Lowercase content tokens (>=2 chars, not stopwords) for overlap matching."""
    return {t for t in re.findall(r"[a-z0-9]+", str(text).lower())
            if len(t) >= 2 and t not in _FEATURE_STOPWORDS}


def _match_feature(features: List[str], scene_text: str) -> Optional[int]:
    """Index of the feature whose distinctive label words best overlap scene_text,
    or None when nothing meaningfully matches (so the caller falls back to a
    positional rotation). Only REAL features are considered — no fabrication."""
    want = _feature_tokens(scene_text)
    if not want:
        return None
    best_i, best_score = None, 0
    for i, label in enumerate(features):
        score = len(_feature_tokens(label) & want)
        if score > best_score:
            best_i, best_score = i, score
    return best_i


def _shape_explainer(scene: Dict[str, Any], brand: Dict[str, Any]) -> Dict[str, Any]:
    """ExplainerCard data: kicker / title / subtitle / bullets.

    A cinematic/walkthrough/demo beat that gets no real footage still SHOWS the
    narrated point. Prefers explicit copy in scene["data"]; falls back to the
    scene's own brief / VO beat text and the brand's real features — never
    invented marketing copy (honesty rule, brand_extract.py).
    """
    d = scene.get("data") or {}
    brief = scene.get("brief") or ""
    # Title source priority: explicit plan copy -> threaded VO beat / brief text
    # -> the scene's own brief -> brand fallback. NEVER empty (blank-scenes fix):
    # an empty input falls through to the brand tagline/wordmark, never "".
    title = (d.get("title")
             or _title_from_text(d.get("_text") or "")
             or _title_from_text(brief)
             or _brand_fallback_title(brand)
             or brand.get("wordmark") or "").strip()
    subtitle = d.get("subtitle")
    if subtitle is None:
        # Don't echo the title as the subtitle; prefer the brand tagline, but if the
        # title already IS the tagline, leave the subtitle empty rather than dup it.
        # Reject a truncated meta-description so a mid-word fragment never shows.
        tag = _clean_complete_headline(brand.get("tagline") or "")
        subtitle = "" if tag and tag == title else tag
    # FRAGMENT GUARD: reject a subtitle that is a scrape fragment (lowercase-leading,
    # preposition-final, or single-word). Drop it — a missing subtitle is better
    # than a dangling fragment.
    if _is_fragment_subtitle(subtitle):
        subtitle = ""

    # Bullets: explicit copy wins; else short capability nouns from the brand's
    # real features (CardUi labels). Each feature scene gets a DISTINCT, on-topic
    # ordering so the explainer scenes don't all show the identical list (BUG C).
    # This only REORDERS the real fixture features — it never invents copy (honesty
    # rule) and keeps every real capability on screen so the scenes read as a set.
    # Ordering priority:
    #   1. Match the feature whose label words overlap THIS scene's spoken/title
    #      text and lead with it (so the CNC scene leads "CNC Machining", the laser
    #      scene leads "Laser Sintering"), even when scene count != feature count.
    #   2. Fall back to a positional rotation by `data._feature_index` (build_props
    #      threads the scene's 0-based order among feature scenes) so distinct
    #      scenes still differ when no keyword matches.
    bullets = d.get("bullets")
    if not bullets:
        feats = [f.get("label") or f.get("title") for f in (brand.get("features") or [])]
        feats = [f for f in feats if f]
        lead = _match_feature(feats, f"{d.get('_text') or ''} {brief} {title}")
        if lead is not None:
            feats = feats[lead:] + feats[:lead]
        else:
            idx = d.get("_feature_index")
            if isinstance(idx, int) and feats:
                start = idx % len(feats)
                feats = feats[start:] + feats[:start]
        bullets = feats[:EXPLAINER_BULLET_COUNT]

    # BUG 2 FIX: When real features are unavailable (bot-blocked brand, empty
    # features list), synthesize 2-3 concise bullet phrases from the scene's
    # own content (VO text / brief / title) so the explainer card is never hollow.
    # Only fires when bullets is still empty after the feature-lookup above.
    if not bullets:
        source = " ".join(filter(None, [d.get("_text") or "", brief, title]))
        if source.strip():
            # Split on sentence boundaries and em-dashes to surface short clauses.
            raw_phrases = re.split(r"[.!?,;—–\n]+", source)
            synth: List[str] = []
            seen: set = set()
            for phrase in raw_phrases:
                # Collapse whitespace, cap at ~40 chars, min 3 words.
                p = " ".join(phrase.split())
                if len(p.split()) < 3:
                    continue
                # Drop fragments that open with a conjunction/article (split
                # artifacts like "and experiences at every destination").
                first_word = p.split()[0].lower()
                if first_word in _DANGLING_WORDS:
                    continue
                # Hard-truncate at the last word boundary within 40 chars.
                if len(p) > 40:
                    p = p[:40].rsplit(" ", 1)[0].strip()
                # After truncation, drop a dangling tail word.
                p_words = p.split()
                while p_words and p_words[-1].lower() in _DANGLING_WORDS:
                    p_words.pop()
                p = " ".join(p_words)
                if len(p.split()) < 3:
                    continue
                p = p[0].upper() + p[1:]  # sentence-case
                key = p.lower()
                if key not in seen:
                    seen.add(key)
                    synth.append(p)
                if len(synth) >= 3:
                    break
            bullets = synth[:EXPLAINER_BULLET_COUNT]

    bullets = [b for b in (bullets or []) if b][:EXPLAINER_BULLET_COUNT]

    out: Dict[str, Any] = {
        "kicker": _decode(d.get("kicker") or ""),
        "title": _decode(title),
        "subtitle": _decode(subtitle or ""),
        "bullets": [_decode(b) for b in bullets],
    }
    return out


def _walkthrough_clip_path(scene: Dict[str, Any]) -> str:
    """The produced walkthrough clip path for a scene, or "" when none exists.

    Looks in scene["data"] AND the scene root (the producer may attach the clip as
    `output_path` on the scene, or a plan may pre-stage it as data.videoSrc). The
    presence of a real clip is what routes a `walkthrough` role to the player
    archetype; absence falls back to the never-blank explainer card.
    """
    d = scene.get("data") or {}
    for key in _WALKTHROUGH_CLIP_KEYS:
        val = d.get(key) or scene.get(key)
        if val and str(val).strip():
            return str(val).strip()
    return ""


def _has_walkthrough_clip(scene: Dict[str, Any]) -> bool:
    return bool(_walkthrough_clip_path(scene))


def _emphasis_phrase(emphasis: str, limit: int = 48) -> str:
    """A clean overlay-title phrase from the run's raw emphasis input.

    The emphasis is user text (e.g. "the pricing page", "instant quoting") that
    feeds the walkthrough goal. For a title bar we want a tidy noun phrase:
      - strip a leading article ("the "/"a "/"an ") so "Stripe — pricing page",
      - capitalize the first letter (leave the rest as-typed to preserve casing
        like "API"),
      - clamp to a word boundary under `limit`.
    Never fabricates — it only trims/cleans the real emphasis string.
    """
    e = (emphasis or "").strip()
    if not e:
        return ""
    e = re.sub(r"^(the|a|an)\s+", "", e, flags=re.IGNORECASE).strip()
    if not e:
        return ""
    if len(e) > limit:
        e = e[:limit].rsplit(" ", 1)[0].rstrip(",").strip() or e[:limit]
    return e[0].upper() + e[1:]


def _shape_walkthrough(scene: Dict[str, Any], brand: Dict[str, Any]) -> Dict[str, Any]:
    """WalkthroughPlayer data: videoSrc / overlayTitle / muteClip (+ optional caption).

    The produced walkthrough MP4 plays INSIDE the branded frame; the scene VO owns
    the audio, so muteClip defaults True. The overlay title is the brand wordmark
    plus the run's EMPHASIS (the user-supplied feature/area, e.g. "the pricing
    page") — the one thing the title bar must stay on-topic with. The emphasis is
    threaded as `data._emphasis` by build_props; if absent we fall back to the
    scene's brief/VO text trimmed to a phrase. NEVER fabricates copy — it trims
    real emphasis/brand/VO text (honesty rule).

    Only reached when a real clip exists (build_props routes a clip-less walkthrough
    role to the explainer card instead), but it still floors every field so a
    mis-route degrades gracefully rather than crashing.
    """
    d = scene.get("data") or {}
    clip = _walkthrough_clip_path(scene)

    # Overlay title: explicit copy -> brand wordmark + emphasis -> wordmark alone.
    # Prefer the run's real emphasis (data._emphasis, threaded by build_props) over
    # the planner's free-text VO, which often narrates a DIFFERENT flow than the
    # emphasized feature (e.g. emphasis="the pricing page" but VO="create a payment
    # link...") and would otherwise leak into the title bar.
    wordmark = (brand.get("wordmark") or brand.get("brand") or brand.get("name") or "").strip()
    emphasis = (_emphasis_phrase(d.get("_emphasis") or "")
                or _title_from_text(d.get("_text") or "")
                or _title_from_text(scene.get("brief") or "")).strip()
    if d.get("overlayTitle"):
        overlay_title = str(d["overlayTitle"]).strip()
    elif wordmark and emphasis and emphasis.lower() != wordmark.lower():
        # "Brand — emphasis" (en-dash join), e.g. "Stripe — Dashboard walkthrough".
        overlay_title = f"{wordmark} — {emphasis}"
    else:
        overlay_title = wordmark or emphasis or _brand_fallback_title(brand)

    out: Dict[str, Any] = {
        "videoSrc": clip,
        "overlayTitle": _decode(overlay_title),
        # VO owns the audio (per-scene <Audio> placed at the scene's in_frame).
        "muteClip": True,
        # contain so a UI walkthrough never crops its chrome; cover only on request.
        "videoFit": d.get("videoFit") or "contain",
    }
    if d.get("caption"):
        out["caption"] = _decode(str(d["caption"]).strip())
    return out


def _shape_screenshot(scene: Dict[str, Any], brand: Dict[str, Any]) -> Dict[str, Any]:
    """AppleScreenshot data: imageSrc / frame / caption / headline.

    The captured PNG is wired onto scene.data.imageSrc by build_props (mapping the
    Nth screenshot scene -> shot-NN.png from the run's screenshots/ dir). This shaper
    carries that imageSrc through, derives the browser address-bar `caption` (the
    captured page URL, else the brand cta_url, else the company URL), AND a meaningful
    `headline` — a short grounded value-prop about what the screenshot shows, rendered
    as on-screen TEXT beside the card so the proof beat communicates, not just an image.

    headline source priority (reuses the shared headline-quality machinery — rejects
    nav-labels, section names, prompt artifacts, weak fragments, and the bare URL):
      1. The scene's THREADED VO beat (`data._text`, set by build_props from the line
         actually narrated over this screenshot, e.g. "Breaking tech news, in-depth
         reviews, and sharp analysis every day.") distilled via _grounded_headline.
      2. The scene's `brief` IF it is a real value-prop and NOT a capture/stage
         direction ("Real captured homepage ... in a branded browser card").
      3. The brand's world-knowledge tagline.
      4. "" — the archetype renders cleanly with no headline (backward-compatible).
    The headline is NEVER the URL and NEVER the address-bar caption (no duplication).

    NEVER fabricates a screenshot — a clip-less scene shows the archetype's
    caption/wordmark placeholder. Honesty rule: caption + headline are real
    captured/narrated/brand text only.
    """
    d = scene.get("data") or {}
    img = (d.get("imageSrc") or "").strip()
    # Caption = the captured page URL (set by build_props), else a brand URL. This
    # feeds the browser address bar; it is NOT the on-screen headline.
    caption = (str(d.get("caption") or "").strip()
               or str(d.get("shotUrl") or "").strip()
               or str(brand.get("cta_url") or "").strip()
               or str(brand.get("url") or "").strip())

    # headline = a grounded value-prop line ABOUT what the screenshot shows. Source the
    # narrated VO beat first; fall back to a non-stage-direction brief; then the brand
    # tagline. _grounded_headline applies the full quality gate (nav-label / weak /
    # artifact rejection + positive _looks_like_headline test), so a section label or a
    # bare capture-direction never becomes the headline.
    raw_threaded = str(d.get("_text") or "").strip()
    # Safety net: the planner-prompt forbids narrating the capture/screenshot, but if a
    # capture stage-direction leaked into the VO beat, do not let it become the headline.
    if raw_threaded and _is_capture_stage_direction(raw_threaded):
        raw_threaded = ""
    brief = str(scene.get("brief") or "").strip()
    # Only feed the brief into the distiller when it is NOT a capture/stage direction
    # (those describe the SHOT — "Real captured homepage ... in a branded browser
    # card" — not the product). _is_capture_stage_direction catches the screenshot
    # camera-direction class; _is_cta_stage_direction the closing-card meta forms;
    # _is_prompt_artifact scaffold leakage.
    brief_seed = "" if (brief and (_is_capture_stage_direction(brief)
                                    or _is_cta_stage_direction(brief)
                                    or _is_prompt_artifact(brief))) else brief
    wordmark = (brand.get("wordmark") or brand.get("brand") or brand.get("name") or "").strip()
    headline = (_grounded_headline(raw_threaded, brand, avoid=wordmark, limit=64)
                or _grounded_headline(brief_seed, brand, avoid=wordmark, limit=64))
    # Last guard: the headline must never echo the address-bar caption / URL.
    if headline and caption and headline.strip().lower() == _decode(caption).strip().lower():
        headline = ""

    out: Dict[str, Any] = {
        "imageSrc": img,
        "frame": d.get("frame") or "browser",
    }
    if caption:
        out["caption"] = _decode(caption)
    if headline:
        out["headline"] = _decode(headline)
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
        arch = self.role_map.get(_scene_role(scene), self.default_archetype)
        # NEVER-BLANK guard for the walkthrough player: a `walkthrough`/`demo`/
        # `cinematic` role only earns the video player when a REAL clip exists.
        # With no clip, fall back to the designed explainer card so a clip-less
        # ($0 / standard, or failed-capture) run is never blank.
        if arch == ARCH_WALKTHROUGH and not _has_walkthrough_clip(scene):
            return self.shapers.get(ARCH_EXPLAINER) and ARCH_EXPLAINER or self.default_archetype
        return arch

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
            # An animated feature beat ("what/how/why") -> the designed explainer
            # card so it SHOWS the narrated point (title + bullets) instead of
            # falling to a blank hero (the content-empty blank-scenes bug).
            "feature": ARCH_EXPLAINER, "motion_graphic": ARCH_EXPLAINER,
            "motion-graphic": ARCH_EXPLAINER,
            # The explicit brand-grid roles still use the 2x2 CardUi grid.
            "capability": ARCH_CARD, "capabilities": ARCH_CARD,
            "cards": ARCH_CARD, "grid": ARCH_CARD,
            # A walkthrough/demo beat plays its PRODUCED clip inside the branded
            # frame (walkthrough-player) WHEN a real clip exists; archetype_for
            # downgrades to the explainer card when it doesn't (never-blank). A
            # cinematic beat (no UI capture) stays on the designed explainer card.
            "walkthrough": ARCH_WALKTHROUGH, "demo": ARCH_WALKTHROUGH,
            "cinematic": ARCH_EXPLAINER, "explainer": ARCH_EXPLAINER,
            # A screenshot beat shows the REAL captured site inside a branded browser
            # card (apple-screenshot). The captured PNG is wired in by build_props.
            "screenshot": ARCH_SCREENSHOT, "site": ARCH_SCREENSHOT,
        },
        default_archetype=ARCH_HERO,
        shapers={ARCH_HERO: _shape_hero, ARCH_CARD: _shape_cards,
                 ARCH_EXPLAINER: _shape_explainer,
                 ARCH_WALKTHROUGH: _shape_walkthrough,
                 ARCH_SCREENSHOT: _shape_screenshot},
        theme_fn=_theme_kinetic_light,
    ),
}


# ---------------------------------------------------------------------------
# CAPTURED-ASSET WIRING  (screenshots + walkthrough clip -> plan scene data)
# ---------------------------------------------------------------------------
def _load_screenshot_manifest(out_dir: str) -> List[Dict[str, Any]]:
    """Return the captured screenshots as an ordered [{file, path, url}] list.

    Reads runs/<id>/screenshots/manifest.json (written by capture_screenshots), else
    globs shot-NN.png in that dir so a manifest-less capture still wires up. Returns
    [] when nothing was captured (the screenshot scenes then show their never-blank
    placeholder)."""
    shots_dir = os.path.join(out_dir, "screenshots")
    manifest_path = os.path.join(shots_dir, "manifest.json")
    shots: List[Dict[str, Any]] = []
    if os.path.exists(manifest_path):
        try:
            data = _load_json(manifest_path)
            for s in (data.get("shots") or []):
                f = s.get("file") or (os.path.basename(s.get("path")) if s.get("path") else None)
                if f:
                    shots.append({"file": f,
                                  "path": s.get("path") or os.path.join(shots_dir, f),
                                  "url": s.get("url") or ""})
        except (OSError, ValueError):
            shots = []
    if not shots and os.path.isdir(shots_dir):
        import glob
        for p in sorted(glob.glob(os.path.join(shots_dir, "shot-*.png"))):
            shots.append({"file": os.path.basename(p), "path": p, "url": ""})
    return shots


def _walkthrough_clip_for_run(out_dir: str, scene_id: str) -> str:
    """Locate the produced walkthrough clip for a run, or "" if none.

    Priority: env WS_WALKTHROUGH_CACHE (a cached mp4 path, the $0/no-NIM verify
    path) -> the orchestrator's produced clip at runs/<id>/clips/NN_<scene_id>.mp4.
    Returns an absolute path that _stage_audio stages into studio/public/.
    """
    cache = (os.environ.get("WS_WALKTHROUGH_CACHE") or "").strip()
    if cache and os.path.exists(cache):
        return cache
    clips_dir = os.path.join(out_dir, "clips")
    if os.path.isdir(clips_dir):
        import glob
        # the orchestrator names walkthrough clips NN_<scene_id>.mp4
        cands = sorted(glob.glob(os.path.join(clips_dir, "*_%s.mp4" % scene_id)))
        if cands:
            return cands[0]
    return ""


def wire_captured_assets(plan: Dict[str, Any], out_dir: str) -> Dict[str, Any]:
    """Attach REAL captured assets to the plan's screenshot/walkthrough scenes IN
    PLACE so the existing imageSrc/videoSrc staging (build_props + _stage_audio)
    picks them up:

      - each `screenshot` scene (in order) -> the Nth captured shot-NN.png; sets
        data.imageSrc (the PNG) + data.caption (the captured page URL) when the
        scene has no explicit caption.
      - the `walkthrough` scene -> the produced/cached clip; sets data.videoSrc.

    Mutates + returns `plan`. Idempotent-ish: explicit pre-set imageSrc/videoSrc on a
    scene are never overwritten. No-op for scenes that have no captured asset (they
    keep their never-blank archetype floor)."""
    scenes = [s for s in (plan.get("scenes") or []) if isinstance(s, dict)]
    shots = _load_screenshot_manifest(out_dir)

    shot_i = 0
    for s in scenes:
        stype = str(s.get("type") or "").strip().lower()
        d = dict(s.get("data") or {})
        if stype == "screenshot":
            if not d.get("imageSrc") and shot_i < len(shots):
                shot = shots[shot_i]
                d["imageSrc"] = shot["path"]
                if not d.get("caption") and shot.get("url"):
                    d["caption"] = shot["url"]
                shot_i += 1
            s["data"] = d
        elif stype == "walkthrough":
            if not _has_walkthrough_clip(s):
                clip = _walkthrough_clip_for_run(out_dir, str(s.get("id") or ""))
                if clip:
                    d["videoSrc"] = clip
            s["data"] = d
    return plan


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

    # The run's emphasis (user-supplied feature/area). The walkthrough shaper uses
    # this for the overlay title so the title bar stays on the emphasized feature,
    # not whatever flow the planner's free-text VO happened to narrate.
    run_emphasis = str((plan.get("job") or {}).get("emphasis") or "").strip()

    tl_scenes = timeline.get("scenes", [])
    last_idx = len(tl_scenes) - 1
    feature_counter = 0  # 0-based position among explainer/feature scenes (BUG C)
    scenes: List[Dict[str, Any]] = []
    for idx, tl_scene in enumerate(tl_scenes):
        sid = tl_scene.get("id")
        plan_scene = dict(by_id.get(sid, {"id": sid}))

        # build_timeline threads a non-None `role` and non-empty `text` onto each
        # timeline scene (the blank-scenes fix). Prefer them over re-deriving from
        # the raw plan scene: the role decides the archetype, and the threaded text
        # seeds the shaper's title when the plan scene carries no `data` block.
        tl_role = str(tl_scene.get("role") or "").strip().lower()
        if tl_role:
            plan_scene["role"] = tl_role  # so _scene_role / archetype_for agree
        tl_text = str(tl_scene.get("text") or "").strip()
        d = dict(plan_scene.get("data") or {})
        if tl_text:
            # Seed data.title from the threaded VO/brief text so the shaper builds a
            # real title instead of falling straight to the brand tagline. Explicit
            # plan copy (data.title) still wins inside the shaper.
            d.setdefault("_text", tl_text)

        archetype = style.archetype_for(plan_scene)  # role decides the archetype

        # Thread scene-POSITION hints the shapers use for variety:
        #  - the FINAL title scene is the closing CTA (BUG B), even if its id/role
        #    didn't already mark it close.
        #  - each explainer/feature scene gets its 0-based order among feature scenes
        #    so its bullets rotate to lead with the on-topic capability (BUG C).
        if archetype == ARCH_HERO and idx == last_idx and last_idx > 0:
            d.setdefault("_is_closing", True)
        if archetype == ARCH_EXPLAINER:
            d.setdefault("_feature_index", feature_counter)
            feature_counter += 1
        if archetype == ARCH_WALKTHROUGH and run_emphasis:
            # Title bar tracks the emphasized feature, not the planner's VO flow.
            d.setdefault("_emphasis", run_emphasis)
        plan_scene["data"] = d

        data = style.shape(plan_scene, brand)
        scene_obj: Dict[str, Any] = {
            "id": sid,
            "archetype": archetype,
            "in_frame": tl_scene["in_frame"],
            "out_frame": tl_scene["out_frame"],
            # cues stay ABSOLUTE (Timeline.tsx rebases to scene-local at the seam).
            "cues": tl_scene.get("cues", []),
            "data": data,
        }
        # Per-scene VO audio (the per-beat file) so the voice starts at this
        # scene's in_frame even though scenes are stretched to the planned length.
        audio = tl_scene.get("audio")
        if audio and audio.get("src"):
            scene_obj["audio"] = {"src": audio["src"]}
        scenes.append(scene_obj)

    return {
        "fps": timeline.get("fps", 30),
        "total_frames": timeline.get("total_frames", 0),
        "audio_path": timeline.get("audio_path"),
        "lang": timeline.get("lang", "en"),
        "theme": style.theme(brand),
        "scenes": scenes,
    }


STUDIO_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "studio")


def _stage_one_asset(src_path: str, out_dir: str, rel: str) -> Optional[str]:
    """Copy one asset (audio OR image) into studio/public/<rel>, resolving src by
    absolute path, by basename under out_dir, by basename under out_dir's
    screenshots/, or as-given. Returns `rel` (public-relative) on a successful
    copy, else None. Remote (http) paths pass through unchanged.

    Remotion serves staticFile()-resolved assets from public/, so both <Audio>
    and the apple-screenshot <Img> need their file copied there with a
    public-relative name."""
    if not src_path:
        return None
    if src_path.startswith("http"):
        return src_path
    cands = [src_path,
             os.path.join(out_dir, os.path.basename(src_path)),
             os.path.join(out_dir, src_path),
             # screenshots land in runs/<id>/screenshots/ — try there too so a
             # bare "shot-01.png" or a screenshots-relative path resolves.
             os.path.join(out_dir, "screenshots", os.path.basename(src_path)),
             os.path.join(out_dir, "screenshots", src_path)]
    src = next((c for c in cands if os.path.exists(c)), None)
    if not src:
        return None
    pub = os.path.join(STUDIO_DIR, "public")
    os.makedirs(pub, exist_ok=True)
    import shutil
    shutil.copyfile(src, os.path.join(pub, rel))
    return rel


# Back-compat alias: the audio path historically called _stage_one_audio.
_stage_one_audio = _stage_one_asset


def _stage_audio(props: Dict[str, Any], out_dir: str) -> Dict[str, Any]:
    """Stage the run's voiceover(s) into studio/public/ and rewrite paths to
    public-relative names. Remotion serves <Audio> via staticFile() under public/;
    an absolute filesystem path gets joined onto the webpack bundle root and 404s.

    Stages BOTH the full continuous track (top-level audio_path, kept as a fallback)
    AND each scene's per-beat VO file (scene.audio.src), so the Timeline can place
    each beat at its own — now stretched — scene start. Run-scoped names so parallel
    runs don't clobber each other. Mutates + returns props."""
    run_tag = os.path.basename(os.path.normpath(out_dir)) or "run"

    # Full continuous track (fallback path).
    ap = props.get("audio_path")
    if ap and not ap.startswith("http"):
        rel = f"vo-{run_tag}.mp3"
        staged = _stage_one_audio(ap, out_dir, rel)
        # public-relative (no leading slash) -> Timeline.tsx staticFile()s it.
        props["audio_path"] = staged or rel

    # Per-scene beat tracks (authoritative VO placement, one file per voiced scene)
    # AND per-scene screenshot images (apple-screenshot archetype). Both are staged
    # into public/ and rewritten to public-relative names; both DROP on a missing
    # file so the scene is never broken (audio falls back to the full track; the
    # apple-screenshot archetype has its own never-blank floor).
    for i, scene in enumerate(props.get("scenes", [])):
        audio = scene.get("audio")
        if audio and audio.get("src"):
            beat_rel = f"vo-{run_tag}-{scene.get('id', i)}.mp3"
            staged = _stage_one_asset(audio["src"], out_dir, beat_rel)
            if staged:
                audio["src"] = staged
            else:
                scene.pop("audio", None)

        # apple-screenshot image: stage scene.data.imageSrc the same way.
        data = scene.get("data") or {}
        img = data.get("imageSrc")
        if img and not str(img).startswith("http"):
            ext = os.path.splitext(str(img))[1] or ".png"
            img_rel = f"shot-{run_tag}-{scene.get('id', i)}{ext}"
            staged_img = _stage_one_asset(img, out_dir, img_rel)
            if staged_img:
                data["imageSrc"] = staged_img
            else:
                # drop the missing image; the archetype renders its caption/wordmark
                # placeholder rather than a broken <Img>.
                data.pop("imageSrc", None)

        # walkthrough-player clip: stage scene.data.videoSrc the same way. The clip
        # MUST be served from public/ for OffthreadVideo (an absolute fs path 404s
        # against the bundle root). Drop a missing clip so the archetype shows its
        # never-blank placeholder rather than a broken <OffthreadVideo>.
        vid = data.get("videoSrc")
        if vid and not str(vid).startswith("http"):
            vext = os.path.splitext(str(vid))[1] or ".mp4"
            vid_rel = f"walk-{run_tag}-{scene.get('id', i)}{vext}"
            staged_vid = _stage_one_asset(vid, out_dir, vid_rel)
            if staged_vid:
                data["videoSrc"] = staged_vid
            else:
                data.pop("videoSrc", None)
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

    brand_fallback = brand.get("tagline") or brand.get("wordmark") \
        or brand.get("brand") or brand.get("name") or ""
    # Honor the planned film length: the scenes HOLD for plan duration_s (never
    # shorter than their VO), and the timeline is padded to job.target_duration_s.
    target_duration_s = (plan.get("job") or {}).get("target_duration_s") \
        if isinstance(plan, dict) else None
    timeline = build_timeline.build_timeline(plan_scenes, alignment, fps=fps,
                                             brand_fallback=brand_fallback,
                                             target_duration_s=target_duration_s)
    timeline_path = os.path.join(out_dir, "timeline.json")
    with open(timeline_path, "w", encoding="utf-8") as fh:
        json.dump(timeline, fh, indent=2)

    # Wire the REAL captured assets (screenshots + walkthrough clip) onto the plan's
    # screenshot/walkthrough scenes so build_props shapes data.imageSrc/videoSrc and
    # _stage_audio stages them into studio/public/. No-op when nothing was captured.
    wire_captured_assets(plan, out_dir)
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
