#!/usr/bin/env python3
"""Phase 2 — turn a company URL into a brand THEME the style-fill engine uses to
re-skin a curated template.

Consolidates the existing brand logic (do NOT duplicate it):
  * remotion_codegen.palette_for(url)  -> the canonical palette + _name/_host
  * remotion_codegen._brand_name/_root_host
and layers an OPTIONAL live fetch (WebFetch-shaped, injectable) on top to learn a
brand's real tagline / accent / features — then NORMALIZES everything into the
Phase-2 `brand_theme.json` contract.

CRITICAL honesty rule (a real past bug — `_copy_from_brief` once leaked hardcoded
"Stripe" copy into every build): we NEVER fabricate a tagline, hook, cta, or
feature. A brand we cannot learn anything about gets its real name + a sensible
generic palette + HONEST empty/neutral strings, never invented marketing copy.

CLI:
  python3 brand_extract.py --url <url> [--name <override>] \
      --out runs/<id>/brand_theme.json

Stdlib only at import time. The live fetch is dependency-injected (default uses
the same network-free path as the tests) so this module imports with zero side
effects and the test suite stays deterministic + $0.
"""

import argparse
import json
import os
import re
import sys
import urllib.request

import remotion_codegen as rc


# brand_theme.json schema (the style-fill contract this module owns):
# {
#   "name": str,                      # real display name (never invented)
#   "host": str,                      # root host for the CTA line
#   "tagline": str,                   # real one-liner or "" — NEVER fabricated
#   "palette": {bg, ink, accent, accent2, success},
#   "fonts":   {display, mono},
#   "wordmark_svg": str | None,       # inline SVG if derivable, else None
#   "features": [{title, sub}, ...],  # real capabilities or [] — never invented
#   "copy":    {hook, cta},           # hook honest/"" ; cta domain-agnostic
# }

# A tasteful mono stack for the secondary type slot the curated templates expose.
# The existing palettes only carry a single display `font`; the style-fill
# contract wants display + mono, so we pair the brand display face with a
# widely-installed mono chain (never pulled over the network — same rationale as
# remotion_codegen's font note).
_MONO_STACK = ('"Berkeley Mono", "GT America Mono", ui-monospace, "SF Mono", '
               'Menlo, monospace')

# A neutral success/positive accent for templates that need a third hue. Derived
# from the palette accent2 when present, else a calm green that reads on dark.
_DEFAULT_SUCCESS = "#56D8A0"

# CLEAN LIGHT default for any brand we cannot kit. The curated templates (HeroTitle,
# ExplainerCard, CardUi) are DESIGNED light — a dark bg + mint accent (the old
# remotion_codegen `_default`) rendered sparse-white-on-black "blank" cards (the
# confirmed build-com bug). These hues are lifted from the proven Orinovate
# kinetic-light theme so a no-fixture brand still reads as a polished light video:
#   bg light, ink near-black, accent a tasteful blue, accent2 a DEEP navy (it maps
#   to the Timeline navy/navyBright slots — must be dark, never a pale mint).
_LIGHT_DEFAULT = {
    "bg": "#FFFFFF",
    "ink": "#0F2338",       # near-black ink for legible body text
    "accent": "#2563EB",    # tasteful blue
    "accent2": "#1A3A5C",   # deep navy (Timeline navy/navyBright)
    "success": "#10B981",   # calm green
}


def _is_known_brand(palette):
    """True when palette_for matched a real BRAND_PALETTES entry (not _default)."""
    return palette.get("_brand") not in (None, "", "generic")


def _palette_to_theme_colors(palette):
    """Map the existing palette dict -> the Phase-2 palette contract.

    {bg, ink, accent, accent2, success}. For a KNOWN brand we trust its curated
    (often dark, intentionally on-brand) palette. For an UNKNOWN/generic brand we
    DO NOT use remotion_codegen's dark `_default` (#0A0D0C + mint) — that rendered
    sparse white-on-black cards on the light-designed templates (the build-com bug).
    Instead we return a clean LIGHT default the curated cards are built for."""
    if not _is_known_brand(palette):
        return dict(_LIGHT_DEFAULT)
    accent = palette.get("accent") or "#7CFFB2"
    accent2 = palette.get("accent2") or accent
    # Prefer accent2 as the success hue when it is a distinct color from accent;
    # otherwise fall back to a calm green that reads on a dark backdrop.
    success = accent2 if accent2.lower() != accent.lower() else _DEFAULT_SUCCESS
    return {
        "bg": palette.get("bg") or "#0A0D0C",
        "ink": palette.get("fg") or "#F4F7F5",
        "accent": accent,
        "accent2": accent2,
        "success": success,
    }


def _fonts_for(palette):
    """{display, mono} from the palette display `font` + a curated mono stack."""
    return {
        "display": palette.get("font") or rc._DEFAULT_FONT,
        "mono": _MONO_STACK,
    }


def _theme_from_palette(palette, name, host):
    """Assemble colors + fonts + name/host into the theme skeleton (no copy yet)."""
    colors = _palette_to_theme_colors(palette)
    return {
        "name": name,
        "host": host,
        "tagline": "",
        "palette": colors,
        "fonts": _fonts_for(palette),
        "wordmark_svg": _wordmark_svg(name, colors["accent"], colors["ink"]),
        "features": [],
        "copy": {"hook": "", "cta": "Get started"},
    }


def _wordmark_svg(name, accent, ink):
    """Derive a clean inline wordmark SVG from the brand NAME (a real, honest
    construct — it is just the brand's own name set in type, not invented copy).
    Returns inline SVG string, or None if no usable name.

    A leading accent block + the brand name set in a strong display stack. Width
    scales with the name length so long names don't clip. No network font."""
    if not name or not name.strip():
        return None
    label = name.strip()
    # Conservative monospace-ish width estimate for the viewBox so the text fits.
    text_w = int(len(label) * 30 + 40)
    w = 56 + text_w
    safe = (label.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
    font = '"SF Pro Display", "Helvetica Neue", "Avenir Next", -apple-system, sans-serif'
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d 96" '
        'width="%d" height="96" role="img" aria-label="%s">'
        '<rect x="16" y="30" width="14" height="36" rx="4" fill="%s"/>'
        '<text x="46" y="62" font-size="44" font-weight="800" '
        'letter-spacing="-0.02em" font-family=\'%s\' fill="%s">%s</text>'
        '</svg>'
    ) % (w, w, safe, accent, font, ink, safe)


# --- Captured-logo consumption (Task F) ----------------------------------------
# capture_screenshots.py records the brand's REAL logo (inline header <svg> ->
# apple-touch-icon/icon -> og:image) in the screenshot manifest under "logo":
#   {"file": "logo.svg", "path": "<abs>", "source": "inline-svg"}.
# We prefer that real asset over the NAME-DERIVED wordmark_svg. Honest fallback:
# when no captured logo exists, the theme keeps its derived wordmark unchanged.
# This adds two theme fields (both OPTIONAL, absent when no logo was captured):
#   "logo_src":    str   # filesystem path to the captured logo asset
#   "logo_source": str   # provenance ("inline-svg" / "link-or-og:<url>")

def _find_capture_manifest(loc):
    """Resolve `loc` (a manifest.json path, a run dir, or a screenshots dir) to a
    manifest.json path that exists, or None. Tolerant of the common layouts the
    pipeline produces: runs/<id>/screenshots-read/manifest.json (the EARLY read pass
    that captures the brand logo) and runs/<id>/screenshots/manifest.json (the
    produce pass that captures page shots).

    `screenshots-read/` is checked FIRST: it is the dedicated brand-extraction pass
    that reliably captures `brand/logo.svg`, whereas the produce pass captures page
    screenshots and may carry no logo record. Looking only in `screenshots/` was why
    a real captured logo (e.g. Airbnb's wordmark) never reached theme.logoSrc and the
    badge fell back to the initial-in-a-square."""
    if not loc:
        return None
    loc = str(loc)
    if os.path.isfile(loc):
        return loc
    cands = (
        os.path.join(loc, "manifest.json"),
        os.path.join(loc, "screenshots-read", "manifest.json"),
        os.path.join(loc, "screenshots", "manifest.json"),
    )
    for c in cands:
        if os.path.isfile(c):
            return c
    return None


def _captured_logo_from_manifest(manifest_path):
    """Return {"path","source"} for a captured logo asset that EXISTS, else None.

    Reads the screenshot manifest's "logo" record. The recorded path is preferred;
    if it is missing (e.g. the run dir moved) we resolve the recorded basename next
    to the manifest under brand/. Never raises — any failure => None (fall back to
    the derived wordmark)."""
    if not manifest_path or not os.path.isfile(manifest_path):
        return None
    try:
        with open(manifest_path, encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        return None
    logo = (data or {}).get("logo")
    if not isinstance(logo, dict):
        return None
    base_dir = os.path.dirname(os.path.abspath(manifest_path))
    file_name = logo.get("file") or (
        os.path.basename(logo["path"]) if logo.get("path") else None)
    cands = []
    if logo.get("path"):
        cands.append(logo["path"])
    if file_name:
        cands.append(os.path.join(base_dir, "brand", file_name))
        cands.append(os.path.join(base_dir, file_name))
    for c in cands:
        if c and os.path.isfile(c):
            return {"path": os.path.abspath(c),
                    "source": logo.get("source") or "captured"}
    return None


def apply_captured_logo(theme, loc):
    """Prefer the brand's REAL captured logo over the derived wordmark, IN PLACE.

    `loc` may be a manifest.json path, a run dir, or a screenshots dir. When a real
    captured logo asset exists, set theme["logo_src"]/["logo_source"]; the derived
    wordmark_svg stays as the honest fallback. No-op (theme unchanged) when no logo
    was captured. Returns the (possibly-mutated) theme."""
    if not isinstance(theme, dict):
        return theme
    manifest = _find_capture_manifest(loc)
    found = _captured_logo_from_manifest(manifest)
    if found:
        theme["logo_src"] = found["path"]
        theme["logo_source"] = found["source"]
    return theme


# The fetch prompt — asks the fetcher to return STRICT JSON and to leave a field
# EMPTY rather than guess. This instruction is the first honesty guard; the parser
# below is the second (it drops anything that smells invented).
FETCH_PROMPT = (
    "From this company's homepage, extract ONLY facts that are literally present. "
    "Return a strict JSON object with keys: "
    '"tagline" (the brand\'s real one-line hero headline/slogan, verbatim; '
    'empty string if none is clearly shown), '
    '"accent" (the dominant brand/accent color as a #RRGGBB hex if discoverable, '
    "else empty string), "
    '"features" (an array of up to 4 real product capabilities, each {"title", '
    '"sub"}, both short and taken from the page; empty array if none are clear). '
    "Do NOT invent, paraphrase into marketing copy, or guess. If unsure, leave it "
    "empty. Return JSON only, no prose."
)

_HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")

# World-knowledge display-name map: registrable label (lowercase, despaced) ->
# the brand's REAL multi-word display name. The registrable host label collapses
# spaces ("theverge.com" -> "Theverge"), so a multi-word wordmark loses its space
# and the kicker renders "THEVERGE". This restores the canonical spelling. Only
# brands whose correct multi-word casing is public knowledge belong here.
_WELL_KNOWN_NAMES = {
    "theverge":      "The Verge",
    "producthunt":   "Product Hunt",
    "hackernews":    "Hacker News",
    "ycombinator":   "Y Combinator",
    "techcrunch":    "TechCrunch",
    "businessinsider": "Business Insider",
    "linkedin":      "LinkedIn",
    "github":        "GitHub",
    "gitlab":        "GitLab",
    "youtube":       "YouTube",
    "paypal":        "PayPal",
    "doordash":      "DoorDash",
    "wholefoods":    "Whole Foods",
    "redbull":       "Red Bull",
    "wordpress":     "WordPress",
    "soundcloud":    "SoundCloud",
    "mailchimp":     "Mailchimp",
}


def _resolve_display_name(label, fetched_name, host):
    """Restore a real multi-word display name for a collapsed registrable label.

    The host-derived label despaces the brand ("theverge" -> "Theverge"), so a
    multi-word brand renders as one CamelCase word. Resolution order (safest →
    heuristic):
      1. A curated public name (_WELL_KNOWN_NAMES) keyed on the despaced label.
      2. A fetched og:site_name / <title> brand segment whose DESPACED form equals
         the label (case-insensitive) — i.e. the same brand, just better-spaced
         ("The Verge" despaces to "theverge" == label). This earns the real spacing
         without letting an unrelated page title hijack the name.
      3. The label unchanged (single-word brands stay intact — Stripe, Linear,
         Notion, Plaid, Vercel, Shopify, Webflow, Allbirds, Huckberry, Airbnb).
    Never splits a genuinely single-word name; only RESTORES a known space.
    """
    if not label:
        return label
    key = label.lower().replace(" ", "")
    known = _WELL_KNOWN_NAMES.get(key)
    if known:
        return known
    fetched = (fetched_name or "").strip()
    if fetched and " " in fetched:
        if fetched.lower().replace(" ", "") == key:
            return fetched
    return label


# World-knowledge accent map: brand registrable label (lowercase) -> curated hex.
# Used ONLY for thin-data / bot-blocked brands that cannot be found in BRAND_PALETTES
# and whose live fetch didn't produce a real saturated accent. Covers well-known brands
# where the correct color is public knowledge. DO NOT add brands already in
# remotion_codegen.BRAND_PALETTES — those are handled by the known-brand path.
_WELL_KNOWN_ACCENTS = {
    # Green brands
    "shopify":      "#96BF48",  # Shopify green (Polaris)
    "tripadvisor":  "#34E0A1",  # TripAdvisor mint-green
    "spotify":      "#1DB954",  # Spotify green
    "whatsapp":     "#25D366",  # WhatsApp green
    "robinhood":    "#00C805",  # Robinhood green
    "duolingo":     "#58CC02",  # Duolingo green
    "hulu":         "#1CE783",  # Hulu green
    # Blue / purple brands
    "plaid":        "#1D64DC",  # Plaid blue (perceptible; #0C2340 navy ≈ ink on white)
    "atlassian":    "#0052CC",  # Atlassian blue
    "salesforce":   "#00A1E0",  # Salesforce blue
    "slack":        "#4A154B",  # Slack aubergine
    "zoom":         "#2D8CFF",  # Zoom blue
    "dropbox":      "#0061FF",  # Dropbox blue
    "twilio":       "#F22F46",  # Twilio red
    "hubspot":      "#FF7A59",  # HubSpot orange
    "figma":        "#F24E1E",  # Figma red-orange
    "notion":       "#2383E2",  # Notion blue (already in BRAND_PALETTES but safe dupe)
    "airtable":     "#FCB400",  # Airtable yellow
    "canva":        "#00C4CC",  # Canva teal
    "monday":       "#FF3D57",  # Monday red
    "asana":        "#F06A6A",  # Asana coral
    "intercom":     "#1F8DED",  # Intercom blue
    "zendesk":      "#03363D",  # Zendesk dark teal
    "datadog":      "#632CA6",  # Datadog purple
    "amplitude":    "#1153FC",  # Amplitude blue
    "segment":      "#52BD95",  # Segment green
    "brex":         "#0500FF",  # Brex blue
    "rippling":     "#FFD700",  # Rippling gold
    "gusto":        "#F45D48",  # Gusto salmon
    "mercury":      "#0E1C96",  # Mercury navy
}


def _hex_rgb(hex_color):
    """(r, g, b) ints from a #RRGGBB string, or None if invalid."""
    h = (hex_color or "").lstrip("#")
    if len(h) != 6:
        return None
    try:
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except ValueError:
        return None


def _hex_luminance(hex_color):
    """Approximate perceptual luminance (0-255) of a #RRGGBB hex string.
    Returns -1 for invalid input."""
    rgb = _hex_rgb(hex_color)
    if rgb is None:
        return -1
    r, g, b = rgb
    # ITU-R BT.601 luma approximation — fast, no floats needed.
    return (r * 299 + g * 587 + b * 114) // 1000


def _hex_saturation(hex_color):
    """HSV saturation (0.0-1.0) of a #RRGGBB hex string; 0 for grayscale/invalid.

    Saturation tells brand colours (a vivid blue/green/red) apart from the
    near-grey structural colours (#E0E2DC, #242729, #888) that dominate a page's
    CSS. We use it to PICK the real accent out of the page's colour soup."""
    rgb = _hex_rgb(hex_color)
    if rgb is None:
        return 0.0
    r, g, b = rgb
    mx, mn = max(r, g, b), min(r, g, b)
    return 0.0 if mx == 0 else (mx - mn) / mx


def _hsl_to_hex(h, s, l):
    """Deterministic HSL (h in [0,360), s/l in [0,1]) -> #RRGGBB. Stdlib only."""
    c = (1 - abs(2 * l - 1)) * s
    x = c * (1 - abs((h / 60.0) % 2 - 1))
    m = l - c / 2
    if   h < 60:  rp, gp, bp = c, x, 0
    elif h < 120: rp, gp, bp = x, c, 0
    elif h < 180: rp, gp, bp = 0, c, x
    elif h < 240: rp, gp, bp = 0, x, c
    elif h < 300: rp, gp, bp = x, 0, c
    else:         rp, gp, bp = c, 0, x
    r, g, b = (int(round((v + m) * 255)) for v in (rp, gp, bp))
    return "#%02X%02X%02X" % (max(0, min(255, r)),
                              max(0, min(255, g)),
                              max(0, min(255, b)))


def _deterministic_brand_accent(seed):
    """A tasteful, SATURATED, brand-specific accent derived deterministically from
    a seed string (the registrable label / host). This is the LAST resort when no
    real accent can be learned — so two different unknown brands NEVER collapse to
    the same generic blue (the R7 generality bug). The hue is spread across the
    full wheel by a hash of the seed; saturation/lightness are fixed in a range
    that always reads as a perceptible accent on a light theme (never white, never
    near-black). Stable across runs (no randomness) so a brand always gets the
    same colour."""
    s = (seed or "brand").strip().lower() or "brand"
    # FNV-1a-ish stable hash over the bytes — deterministic, stdlib only.
    h = 2166136261
    for ch in s.encode("utf-8"):
        h = ((h ^ ch) * 16777619) & 0xFFFFFFFF
    hue = h % 360
    # Saturation 0.62, lightness 0.46: vivid + mid-dark so it pops on white AND is
    # never confused with near-white bg or near-black ink.
    return _hsl_to_hex(hue, 0.62, 0.46)


def _is_valid_accent(hex_color):
    """True when the hex is a real saturated brand color — not near-white (L>240)
    or near-black (L<15). Those are structural/background colors, not accents."""
    if not hex_color or not _HEX_RE.match(hex_color):
        return False
    lum = _hex_luminance(hex_color)
    return 15 <= lum <= 240


# Minimum luminance gap required for an accent to be PERCEPTIBLE against a surface.
# Below this threshold the accent is indistinguishable from the bg or ink and will
# render as "just a dark (or light) line" rather than a visible brand pop.
# Calibrated so: Plaid #0C2340 (lum=31) on ink #0F2338 (lum=31) → gap=0 → FAILS;
# Plaid #1D64DC (lum=92) vs ink (lum=31) → gap=61 → PASSES. Stripe #635BFF
# (lum=112) vs bg #0A2540 (lum=27) → gap=85 → PASSES.
_MIN_ACCENT_CONTRAST = 40


def _is_perceptible_accent(accent_hex, bg_hex, ink_hex):
    """True when `accent_hex` is visually distinct from BOTH the bg and ink.

    An accent that is too close to the bg is invisible (white accent on white bg).
    An accent that is too close to the ink reads as "more text", not a colour pop.
    Both cases result in D7/D9 scores of 3 instead of ≥4.

    We require a luminance gap of at least _MIN_ACCENT_CONTRAST (40) against BOTH
    surfaces. This passes Stripe indigo, Linear purple, Shopify green, TripAdvisor
    mint — and rejects Plaid #0C2340 (gap vs ink = 0)."""
    if not _is_valid_accent(accent_hex):
        return False
    a_lum = _hex_luminance(accent_hex)
    bg_lum = _hex_luminance(bg_hex or "#FFFFFF")
    ink_lum = _hex_luminance(ink_hex or "#000000")
    gap_vs_bg = abs(a_lum - bg_lum)
    gap_vs_ink = abs(a_lum - ink_lum)
    return gap_vs_bg >= _MIN_ACCENT_CONTRAST and gap_vs_ink >= _MIN_ACCENT_CONTRAST


def _clean_str(v, limit):
    if not isinstance(v, str):
        return ""
    s = v.strip().strip("\"'").strip()
    return s[:limit]


def _parse_fetch_payload(text):
    """Parse the free-form WebFetch answer into {tagline, accent, features}.

    The fetch prompt asks for a strict JSON object; we parse it defensively and
    DROP anything we cannot trust. Returns a dict with only the keys we could
    honestly extract. Never raises."""
    out = {"name": "", "tagline": "", "accent": "", "brand_color": "",
           "features": []}
    if not text or not isinstance(text, str):
        return out
    # Tolerate fences / surrounding prose: grab the first {...} block.
    m = re.search(r"\{.*\}", text, re.DOTALL)
    raw = m.group(0) if m else text
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return out
    if not isinstance(data, dict):
        return out

    out["name"] = _clean_str(data.get("name"), 50)
    tagline = _clean_str(data.get("tagline"), 80)
    out["tagline"] = "" if _is_ui_label(tagline) else tagline   # drop nav chrome

    accent = _clean_str(data.get("accent"), 7)
    out["accent"] = accent if (_HEX_RE.match(accent) and _is_valid_accent(accent)) else ""

    bc = _clean_str(data.get("brand_color"), 7)
    out["brand_color"] = bc if (_HEX_RE.match(bc) and _is_valid_accent(bc)) else ""

    feats = data.get("features")
    if isinstance(feats, list):
        clean = []
        for f in feats[:4]:
            if not isinstance(f, dict):
                continue
            title = _clean_str(f.get("title"), 40)
            sub = _clean_str(f.get("sub"), 80)
            if title and not _is_ui_label(title):  # real title, not nav chrome
                clean.append({"title": title, "sub": sub})
        out["features"] = clean
    return out


def extract_brand(url, name_override=None, fetcher=None, logo_from=None):
    """URL -> brand_theme dict. `fetcher(url, prompt) -> str` is injectable; the
    default is network-free. Known brands resolve from BRAND_PALETTES; unknown
    brands get real name + generic palette + HONEST empty copy.

    `logo_from` (optional): a screenshot manifest path / run dir / screenshots dir.
    When it carries a captured real logo, theme["logo_src"]/["logo_source"] are set
    so style_fill prefers the real asset over the derived wordmark (Task F). Absent
    or no-logo => the derived wordmark stays as the honest fallback."""
    palette = rc.palette_for(url)
    label = (palette.get("_name") or "").strip()      # part-A registrable label
    name = (name_override or label or "").strip() or "The product"
    host = palette.get("_host") or ""
    known = _is_known_brand(palette)

    # Live fetch (default is the real stdlib web fetcher) can add a real name /
    # tagline / accent / features. Everything it returns has already passed the
    # honesty parser; we still only OVERWRITE empty fields so a curated value wins.
    fetch = fetcher or _live_webfetch
    try:
        payload = _parse_fetch_payload(fetch(url, FETCH_PROMPT))
    except Exception:  # a flaky fetch must never fabricate or crash extraction
        payload = {"name": "", "tagline": "", "accent": "", "features": []}

    # Refine the DISPLAY name from the fetched og:site_name/<title> ONLY when it is
    # a better-cased version of the same brand (case-insensitively contains the
    # registrable label) and the caller did not pin a name. This earns nicer casing
    # ("TripAdvisor") without risking a junk page title becoming the brand name; the
    # part-A label ("Tripadvisor") is always a correct, safe floor.
    if not name_override and payload.get("name") and label:
        fetched = payload["name"]
        if label.lower() in fetched.lower() and len(fetched) <= len(label) + 6:
            name = fetched

    # COLLAPSED MULTI-WORD NAME REPAIR (R8): the host-derived registrable label
    # despaces the brand ("theverge.com" -> "Theverge"), so a multi-word wordmark
    # loses its space and the kicker renders "THEVERGE". Restore the real spacing
    # from a curated public name or a fetched name whose despaced form matches the
    # label. Single-word brands (Stripe/Linear/Notion/Plaid/Vercel/Shopify/Webflow/
    # Allbirds/Huckberry/Airbnb) are returned unchanged. Skip when the caller pinned
    # a name or the fetch already produced a spaced display name above.
    if not name_override and " " not in name:
        name = _resolve_display_name(name, payload.get("name"), host)

    theme = _theme_from_palette(palette, name, host)

    # Known brands carry a real, hand-verified tagline in BRAND_PALETTES — trust it.
    if known and palette.get("tagline"):
        theme["tagline"] = palette["tagline"]

    if payload["tagline"] and not theme["tagline"]:
        theme["tagline"] = payload["tagline"]
    # A discovered real accent refines the palette for unknown brands (theme-color
    # first, then the page's dominant brand colour); for known brands the curated
    # hex stays authoritative. The accent-quality guard below validates/repairs it.
    if not known:
        discovered = payload.get("accent") or payload.get("brand_color")
        if discovered and _is_valid_accent(discovered):
            theme["palette"]["accent"] = discovered
            theme["wordmark_svg"] = _wordmark_svg(
                name, discovered, theme["palette"]["ink"])
    if payload["features"]:
        theme["features"] = payload["features"]

    # --- Accent quality guard ---------------------------------------------------
    # Goal (R7 generality): EVERY brand resolves to a DISTINCT, perceptible accent.
    # Never the same generic blue for every unknown brand; never an invisible white.
    #
    # Signal priority for the accent (best → last resort):
    #   1. curated BRAND_PALETTES accent (known brands)        — authoritative
    #   2. world-knowledge map (_WELL_KNOWN_ACCENTS)           — public brand colour
    #   3. live theme-color / fetched accent (payload.accent)  — real page signal
    #   4. page's most-saturated prominent colour (brand_color)— real page signal
    #   5. deterministic domain-hash accent                    — distinct-per-brand
    # Every candidate must pass the perceptibility check (distinct from bg AND ink),
    # so a near-white (vercel #FFFFFF) / near-ink (plaid #0C2340) colour is rejected.
    bg = theme["palette"].get("bg", "#FFFFFF")
    ink = theme["palette"].get("ink", "#000000")
    registrable = (palette.get("_name") or "").lower().replace(" ", "")
    host_seed = host or registrable or name

    def _first_perceptible(*candidates):
        """First candidate that is a perceptible accent vs the current bg/ink."""
        for c in candidates:
            if c and _is_perceptible_accent(c, bg, ink):
                return c
        return None

    current_accent = theme["palette"]["accent"]
    if not known:
        world_accent = _WELL_KNOWN_ACCENTS.get(registrable)
        # World-knowledge is a hand-verified public brand colour and OUTRANKS any
        # scraped page signal: a brand in the map always gets its canonical accent
        # (e.g. Plaid #1D64DC, not a slightly-off page blue), keeping the known-good
        # subset stable. Otherwise rebuild from the priority chain whenever the
        # current accent is bogus, imperceptible, or the shared generic blue.
        if world_accent and _is_perceptible_accent(world_accent, bg, ink):
            needs_replacement = current_accent.upper() != world_accent.upper()
        else:
            needs_replacement = (
                not _is_valid_accent(current_accent)
                or not _is_perceptible_accent(current_accent, bg, ink)
                or current_accent == _LIGHT_DEFAULT["accent"]   # never leave generic blue
            )
        if needs_replacement:
            new_accent = _first_perceptible(
                world_accent,
                payload.get("accent"),
                payload.get("brand_color"),
            )
            if not new_accent:
                # Last resort: a deterministic, brand-SPECIFIC saturated hue so two
                # unknown brands never collapse to the same colour. Guaranteed
                # perceptible by construction (sat 0.62 / lightness 0.46).
                new_accent = _deterministic_brand_accent(host_seed)
            theme["palette"]["accent"] = new_accent
            theme["wordmark_svg"] = _wordmark_svg(name, new_accent, ink)
    else:
        # KNOWN brand: the curated palette is authoritative EXCEPT when its accent
        # is imperceptible against its own surfaces — e.g. Vercel's curated accent
        # is #FFFFFF on a #000000 bg with #FFFFFF ink (accent == ink → invisible
        # pop). In that one case promote a perceptible brand colour rather than
        # render an invisible accent.
        if not _is_perceptible_accent(current_accent, bg, ink):
            world_accent = _WELL_KNOWN_ACCENTS.get(registrable)
            new_accent = _first_perceptible(
                world_accent,
                palette.get("accent2"),     # curated secondary brand hue
            ) or _deterministic_brand_accent(host_seed)
            theme["palette"]["accent"] = new_accent
            theme["wordmark_svg"] = _wordmark_svg(name, new_accent, ink)

    # HONESTY: hook mirrors the real tagline ONLY (never synthesized brand copy);
    # the CTA is domain-agnostic ("Get started"), never a leaked-brand imperative.
    theme["copy"]["hook"] = theme["tagline"]

    # Task F: prefer the brand's REAL captured logo over the derived wordmark when a
    # capture manifest is supplied and carries one. No-op otherwise (honest fallback).
    if logo_from:
        apply_captured_logo(theme, logo_from)
    return theme


def _default_fetch(url, prompt):
    """Network-free fetch (tests inject this explicitly to stay deterministic+$0).
    Returns "" so the unknown-brand path stays honest with no network."""
    return ""


# --- the real web fetcher ------------------------------------------------------
# A bounded stdlib HTTP GET + a small, dependency-free HTML parser. It returns the
# SAME strict-JSON-string shape `_parse_fetch_payload` already consumes ({name,
# tagline, accent, features}), so wiring it as the default fetcher needs no caller
# change. ROBUST BY CONSTRUCTION: hard timeout, browser UA, follow redirects, and a
# blanket try/except so any failure (timeout, bot-block, TLS, empty/garbled HTML)
# degrades to "" — extraction then keeps the correct part-A name + clean LIGHT
# default palette + honest-empty copy, and NEVER hangs the build.

_FETCH_TIMEOUT_S = 8
_FETCH_MAX_BYTES = 600_000     # cap the read so a huge page can't stall us
_FETCH_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
             "AppleWebKit/537.36 (KHTML, like Gecko) "
             "Chrome/124.0 Safari/537.36")

# Nav/marketing link text that is NOT a product capability — dropped from features.
_FEATURE_STOPWORDS = frozenset((
    "home", "login", "log in", "sign in", "sign up", "signup", "register",
    "contact", "contact us", "about", "about us", "careers", "blog", "news",
    "press", "support", "help", "faq", "pricing", "privacy", "terms", "cookies",
    "legal", "search", "menu", "more", "get started", "learn more", "read more",
    "download", "subscribe", "newsletter", "français", "english", "language",
    "my account", "account", "cart", "settings", "back", "next", "skip",
))

# Store/app CHROME strings that leak in from JS homepages and must NEVER become a
# tagline, headline, or feature: cart/checkout toasts, account chrome, nav tabs,
# CTA buttons, and listing-page section labels. These are UI labels, not product
# copy — when one slips into the title it reads as a bug (the R7 contamination:
# allbirds "Added to Cart", airbnb "Become a host", stripe "What's happening").
_UI_LABEL_EXACT = frozenset((
    "added to cart", "add to cart", "remove from cart", "view cart", "your cart",
    "your bag", "added to bag", "checkout", "continue shopping", "keep shopping",
    "new arrivals", "best sellers", "bestsellers", "shop all", "shop now",
    "on sale", "sale", "gift cards", "gift card", "wishlist", "favorites",
    "become a host", "become a member", "list your space", "list your home",
    "homes on airbnb", "experiences", "host an experience",
    "what's happening", "whats happening", "trending", "for you",
    "sign in", "log in", "login", "sign up", "signup", "create account",
    "my account", "account", "profile", "settings", "log out", "logout",
    "mens", "womens", "men", "women", "kids", "sale items", "clearance",
    "free shipping", "track order", "order status", "returns", "store locator",
    "find a store", "book now", "reserve", "add to bag", "quick view",
    "most popular", "latest", "see all", "view all", "show more",
))

# Token sequences that mark a string as nav/chrome even mid-phrase.
_UI_LABEL_SUBSTR = (
    "add to cart", "added to cart", "become a host", "become a member",
    "homes on ", "list your ", "what's happening", "whats happening",
    "sign in", "log in", "sign up", "new arrivals", "best sellers",
    "shop now", "shop all", "view cart", "your cart", "your bag",
)

# Generic verbs/labels that a SINGLE-word title is when it's just a nav tab.
_NAV_SINGLE_WORDS = frozenset((
    "apps", "agents", "platforms", "products", "solutions", "company",
    "resources", "developers", "docs", "guides", "tech", "reviews", "science",
    "entertainment", "deals", "video", "podcasts", "newsletters", "features",
    "enterprise", "teams", "customers", "partners", "integrations", "stories",
))

# Nav SECTION / category labels — short capitalized rail items that are navigation
# destinations, not product capabilities. These slipped past _UI_LABEL_EXACT in R7
# (allbirds "Men's Shoes"/"Customer Favorites", airbnb "Help Center"/"Find a co-host")
# and got synthesized into a " · "-joined hero title. Two detectors:
#   - exact category/section phrases (gendered store categories, support/account rails)
#   - a leading function-token ("find a …", "shop …", "browse …") that
#     marks an imperative nav action, not a headline.
_NAV_SECTION_EXACT = frozenset((
    "men's shoes", "mens shoes", "women's shoes", "womens shoes",
    "men's clothing", "women's clothing", "kids' shoes", "kids shoes",
    "apparel & accessories", "apparel and accessories", "accessories",
    "customer favorites", "customer favourites", "fan favorites",
    "help center", "help centre", "support center", "contact support",
    "find a co-host", "find a cohost", "find a store", "find a host",
    "all products", "all collections", "shop by category", "browse all",
    "gift guide", "gift guides", "size guide", "size chart",
    "the latest", "latest news", "latest posts", "latest stories",
    "popular", "featured", "collections", "categories",
))

# Leading nav-action tokens: a string starting with one of these (followed by more
# words) is an imperative nav link / breadcrumb action, never a brand headline.
_NAV_LEADING_TOKENS = (
    "find a ", "find an ", "shop ", "browse ",
    "view all ", "see all ", "go to ", "visit the ", "back to ",
)

# Nouns that appear in "&"-joined nav section labels ("Knowledge & News",
# "Press & Media"). The "&" rule only fires when BOTH sides are in this set,
# preventing false matches on product feature phrases like "Billing & invoicing".
_NAV_AMP_NOUNS = frozenset((
    "news", "press", "media", "blog", "careers", "resources",
    "community", "events", "knowledge", "about", "stories", "insights",
))


def _is_ui_label(text):
    """True when `text` is obvious UI/nav chrome (a cart toast, a nav tab, an
    account/CTA button, a listing section header, or a ' · '-joined nav-tab pair)
    rather than real brand/product copy. Used to keep such strings OUT of the
    tagline, headline, and feature slots downstream (the R7 contamination fix)."""
    if not text or not isinstance(text, str):
        return True
    t = text.strip()
    low = t.lower().strip(" .!·•|-—–")
    if not low:
        return True
    if _is_nav_segment(low):
        return True
    # " · "-joined nav-tab pairs ("Homes on Airbnb · Become a host",
    # "Added to Cart · New Arrivals", "What's happening · Enable any billing",
    # "Men's Shoes · Customer Favorites", "Help Center · Find a co-host").
    # Split on the middot/bullet/pipe/dash separators a nav rail uses and reject
    # when ANY segment is itself a UI/nav label.
    parts = [p.strip() for p in re.split(r"\s*[·•|]\s*|\s+[–—]\s+", t) if p.strip()]
    if len(parts) >= 2:
        for p in parts:
            pl = p.lower().strip(" .!·•|-—–")
            if _is_nav_segment(pl):
                return True
    return False


def _is_nav_segment(low):
    """True when a single (already lowercased, stripped) segment is UI/nav chrome:
    an exact cart/account/section label, a nav-action substring, a gendered store
    category / support-rail label, a leading nav-action token, or a lone nav tab."""
    if not low:
        return True
    if low in _UI_LABEL_EXACT or low in _NAV_SECTION_EXACT:
        return True
    if any(sub in low for sub in _UI_LABEL_SUBSTR):
        return True
    if any(low.startswith(tok) for tok in _NAV_LEADING_TOKENS):
        return True
    if low in _NAV_SINGLE_WORDS:
        return True
    # Section-heading phrases that are site chrome, not product value props:
    #  - "<X> & <Y>" two-noun section labels ("Knowledge & News", "Press & Media")
    #    Only fires when BOTH words are nav nouns — prevents matching product
    #    feature phrases like "Billing & invoicing" or "Save & sync".
    #  - possessive editorial sections ("In Founders’ Words", "In Their Words")
    #  - distinctive directive nav blurbs ("Be in the room with ...", "Join the conversation")
    m = re.match(r"^(\w+)\s*&\s*(\w+)$", low)
    if m and m.group(1) in _NAV_AMP_NOUNS and m.group(2) in _NAV_AMP_NOUNS:
        return True
    if low.startswith("in ") and ("words" in low or "'s" in low or "’s" in low):
        return True
    if low.startswith(("be in ", "join the ")):
        return True
    return False


# RGB color literals (rgb()/rgba()) — harvested alongside #hex when scoring the
# page's most-saturated prominent brand colour.
_RGB_RE = re.compile(
    r"rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})", re.IGNORECASE)
_HEX6_RE = re.compile(r"#([0-9A-Fa-f]{6})\b")
_HEX3_RE = re.compile(r"#([0-9A-Fa-f]{3})\b")


def _dominant_page_accent(html):
    """Pick the most-saturated PROMINENT non-neutral colour out of a page's CSS /
    inline styles — the brand's real accent when there's no usable theme-color.

    Harvests #RRGGBB, #RGB, and rgb()/rgba() literals, counts occurrences, and
    scores each candidate by saturation × log-ish prominence. Near-neutral greys
    (low saturation) and structurally-invalid colours (near-white >240 / near-black
    <15 luma) are discarded — those are background/border/text colours, not accents.
    Returns a #RRGGBB string or "" when the page exposes no usable brand colour
    (e.g. a page that only uses rgb()-via-CSS-vars, like The Verge)."""
    if not html:
        return ""
    counts = {}

    def _bump(hx):
        hx = hx.upper()
        counts[hx] = counts.get(hx, 0) + 1

    for m in _HEX6_RE.finditer(html):
        _bump("#" + m.group(1))
    for m in _HEX3_RE.finditer(html):
        r, g, b = m.group(1)
        _bump("#%s%s%s%s%s%s" % (r, r, g, g, b, b))
    for m in _RGB_RE.finditer(html):
        r, g, b = (min(255, int(x)) for x in m.groups())
        _bump("#%02X%02X%02X" % (r, g, b))

    best, best_score = "", 0.0
    for hx, n in counts.items():
        if not _is_valid_accent(hx):        # drops near-white / near-black
            continue
        sat = _hex_saturation(hx)
        if sat < 0.30:                      # drop near-grey structural colours
            continue
        # Prominence matters but shouldn't let a slightly-more-frequent dull colour
        # beat a vivid one: weight saturation heavily, frequency sub-linearly.
        score = (sat ** 2) * (1.0 + (n ** 0.5))
        if score > best_score:
            best, best_score = hx, score
    return best


def _strip_tags(s):
    """Collapse an HTML fragment to clean visible text."""
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = (s.replace("&amp;", "&").replace("&nbsp;", " ").replace("&#39;", "'")
          .replace("&rsquo;", "'").replace("&quot;", '"').replace("&mdash;", "-"))
    return re.sub(r"\s+", " ", s).strip()


def _meta_content(html, attr, value):
    """Return the `content` of a <meta {attr}="{value}">, order-insensitive."""
    for pat in (
        r'<meta[^>]+%s=["\']%s["\'][^>]*\bcontent=["\']([^"\']*)["\']' % (attr, re.escape(value)),
        r'<meta[^>]+content=["\']([^"\']*)["\'][^>]*%s=["\']%s["\']' % (attr, re.escape(value)),
    ):
        m = re.search(pat, html, re.IGNORECASE)
        if m:
            return _strip_tags(m.group(1))
    return ""


def _clean_title(raw):
    """A <title> often trails the slogan: 'Brand | Do things' / 'Brand - Tagline'.
    Keep the leading segment (the brand) for the NAME slot."""
    raw = _strip_tags(raw)
    return re.split(r"\s*[|\-–—:·•]\s*", raw)[0].strip() if raw else ""


def _parse_html_brand(html):
    """Extract {name, tagline, accent, brand_color, features} from homepage HTML.
    Honest: every field is only filled from text literally present; unknowns stay
    empty. UI/nav chrome (cart toasts, nav tabs, account/CTA buttons) is filtered
    out of the tagline + features so it never becomes the title downstream."""
    out = {"name": "", "tagline": "", "accent": "", "brand_color": "",
           "features": []}
    if not html:
        return out

    # NAME: og:site_name -> cleaned <title>.
    name = _meta_content(html, "property", "og:site_name")
    if not name:
        mt = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        if mt:
            name = _clean_title(mt.group(1))
    out["name"] = name[:50]

    # TAGLINE: meta description -> og:description -> first <h1>. Reject UI/nav
    # chrome (a cart toast / nav-tab pair must never become the tagline).
    tagline = (_meta_content(html, "name", "description")
               or _meta_content(html, "property", "og:description"))
    if not tagline:
        mh = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.IGNORECASE | re.DOTALL)
        if mh:
            tagline = _strip_tags(mh.group(1))
    if _is_ui_label(tagline):
        tagline = ""
    out["tagline"] = tagline[:80]

    # ACCENT (preferred): <meta name="theme-color"> if it is a usable, perceptible
    # hex. Many sites ship a near-white/near-black theme-color (allbirds #ECE9E2,
    # vercel #FAFAFA) — _is_valid_accent rejects those so we fall through to the
    # page's dominant brand colour below.
    tc = _meta_content(html, "name", "theme-color")
    if not tc:
        tc = _meta_content(html, "property", "theme-color")
    tc = (tc or "").strip()
    if _HEX_RE.match(tc) and _is_valid_accent(tc):
        out["accent"] = tc.upper()

    # BRAND_COLOR (secondary signal): the most-saturated prominent colour in the
    # page's CSS/inline styles. extract_brand uses this when theme-color and the
    # world-knowledge map both miss, so an unknown brand still gets its REAL accent
    # rather than a generic blue.
    out["brand_color"] = _dominant_page_accent(html)

    # FEATURES: short capability phrases from <h2>/<h3>, nav-ish <a>, and <li>.
    # Deduped, stop-worded, length-bounded. We only ever surface what we parsed.
    seen, feats = set(), []
    candidates = []
    for tag in ("h2", "h3"):
        candidates += re.findall(r"<%s[^>]*>(.*?)</%s>" % (tag, tag), html,
                                 re.IGNORECASE | re.DOTALL)
    nav = re.search(r"<nav[\s>].*?</nav>", html, re.IGNORECASE | re.DOTALL)
    if nav:
        candidates += re.findall(r"<a[^>]*>(.*?)</a>", nav.group(0),
                                 re.IGNORECASE | re.DOTALL)
    candidates += re.findall(r"<li[^>]*>(.*?)</li>", html,
                             re.IGNORECASE | re.DOTALL)[:30]
    for c in candidates:
        t = _strip_tags(c)
        # keep concise, presentable phrases (a short word/phrase up to ~40 chars).
        if not t or len(t) > 40 or len(t) < 3:
            continue
        low = t.lower()
        if low in _FEATURE_STOPWORDS or low in seen:
            continue
        if not re.search(r"[A-Za-z]{3,}", t):
            continue
        if _is_ui_label(t):       # drop cart toasts / nav tabs / account chrome
            continue
        seen.add(low)
        feats.append({"title": t[:40], "sub": ""})
        if len(feats) >= 5:
            break
    out["features"] = feats
    return out


def _live_webfetch(url, prompt):
    """Real default fetcher: bounded stdlib GET + HTML parse -> strict-JSON string
    for `_parse_fetch_payload`. Returns "" on ANY failure so extraction degrades
    gracefully (correct part-A name + clean LIGHT palette + honest-empty copy) and
    NEVER hangs the build. `prompt` is unused (kept for the injected-fetcher seam)."""
    u = (url or "").strip()
    if not u:
        return ""
    if not u.startswith(("http://", "https://")):
        u = "https://" + u
    try:
        req = urllib.request.Request(u, headers={
            "User-Agent": _FETCH_UA,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
        })
        # urllib follows 3xx redirects by default via HTTPRedirectHandler.
        with urllib.request.urlopen(req, timeout=_FETCH_TIMEOUT_S) as resp:
            raw = resp.read(_FETCH_MAX_BYTES)
        html = raw.decode("utf-8", "replace")
    except Exception:
        return ""
    parsed = _parse_html_brand(html)
    if not any(parsed.get(k) for k in ("name", "tagline", "accent", "features")):
        return ""
    return json.dumps(parsed)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Extract a brand theme (brand_theme.json) from a company URL.")
    ap.add_argument("--url", required=True, help="company URL, e.g. https://stripe.com")
    ap.add_argument("--name", default=None, help="override the display brand name")
    ap.add_argument("--out", required=True, help="output path for brand_theme.json")
    ap.add_argument("--logo-from", default=None,
                    help="screenshot manifest.json / run dir / screenshots dir to "
                         "read a captured real logo from (Task F). Defaults to the "
                         "run dir inferred from --out.")
    args = ap.parse_args(argv)

    # Auto-discover the capture manifest from the run dir the brand_theme.json lives
    # in (runs/<id>/brand_theme.json -> runs/<id>/screenshots/manifest.json) unless
    # the caller pinned --logo-from explicitly.
    logo_from = args.logo_from
    if not logo_from:
        run_dir = os.path.dirname(os.path.abspath(args.out))
        if _find_capture_manifest(run_dir):
            logo_from = run_dir

    theme = extract_brand(args.url, name_override=args.name,
                          fetcher=_live_webfetch, logo_from=logo_from)

    out_dir = os.path.dirname(os.path.abspath(args.out))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(theme, f, indent=2)
        f.write("\n")
    sys.stderr.write(
        "brand_theme written: name=%r host=%r tagline=%r features=%d -> %s\n"
        % (theme["name"], theme["host"], theme["tagline"],
           len(theme["features"]), args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
