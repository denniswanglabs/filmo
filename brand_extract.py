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


def _is_known_brand(palette):
    """True when palette_for matched a real BRAND_PALETTES entry (not _default)."""
    return palette.get("_brand") not in (None, "", "generic")


def _palette_to_theme_colors(palette):
    """Map the existing palette dict -> the Phase-2 palette contract.

    {bg, ink, accent, accent2, success}. `ink` is the foreground text color
    (palette `fg`); `success` reuses accent2 when distinct, else a calm green."""
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
    out = {"tagline": "", "accent": "", "features": []}
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

    out["tagline"] = _clean_str(data.get("tagline"), 80)

    accent = _clean_str(data.get("accent"), 7)
    out["accent"] = accent if _HEX_RE.match(accent) else ""

    feats = data.get("features")
    if isinstance(feats, list):
        clean = []
        for f in feats[:4]:
            if not isinstance(f, dict):
                continue
            title = _clean_str(f.get("title"), 40)
            sub = _clean_str(f.get("sub"), 80)
            if title:  # a feature must at least have a real title
                clean.append({"title": title, "sub": sub})
        out["features"] = clean
    return out


def extract_brand(url, name_override=None, fetcher=None):
    """URL -> brand_theme dict. `fetcher(url, prompt) -> str` is injectable; the
    default is network-free. Known brands resolve from BRAND_PALETTES; unknown
    brands get real name + generic palette + HONEST empty copy."""
    palette = rc.palette_for(url)
    name = (name_override or palette.get("_name") or "").strip() or "The product"
    host = palette.get("_host") or ""
    known = _is_known_brand(palette)

    theme = _theme_from_palette(palette, name, host)

    # Known brands carry a real, hand-verified tagline in BRAND_PALETTES — trust it.
    if known and palette.get("tagline"):
        theme["tagline"] = palette["tagline"]

    # Live fetch (only when a real fetcher is injected) can add a real tagline /
    # accent / features. Everything it returns has already passed the honesty
    # parser; we still only OVERWRITE empty fields so a curated value wins.
    fetch = fetcher or _default_fetch
    try:
        payload = _parse_fetch_payload(fetch(url, FETCH_PROMPT))
    except Exception:  # a flaky fetch must never fabricate or crash extraction
        payload = {"tagline": "", "accent": "", "features": []}

    if payload["tagline"] and not theme["tagline"]:
        theme["tagline"] = payload["tagline"]
    if payload["accent"]:
        # A discovered real accent refines the palette for unknown brands; for
        # known brands the curated hex stays authoritative.
        if not known:
            theme["palette"]["accent"] = payload["accent"]
            theme["wordmark_svg"] = _wordmark_svg(
                name, payload["accent"], theme["palette"]["ink"])
    if payload["features"]:
        theme["features"] = payload["features"]

    # HONESTY: hook mirrors the real tagline ONLY (never synthesized brand copy);
    # the CTA is domain-agnostic ("Get started"), never a leaked-brand imperative.
    theme["copy"]["hook"] = theme["tagline"]
    return theme


def _default_fetch(url, prompt):
    """Network-free default fetch (used by tests / when no fetcher is injected).
    Returns "" so the unknown-brand path stays honest and deterministic."""
    return ""


def _live_webfetch(url, prompt):
    """Real fetch path for the CLI. WebFetch is an AGENT tool, not importable
    Python — so the CLI cannot call it directly. We expose this seam so the agent
    (or a future wrapper) can inject a fetcher; on the bare CLI it returns "" and
    the extraction stays honest (real name + generic palette + empty copy)."""
    return ""


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Extract a brand theme (brand_theme.json) from a company URL.")
    ap.add_argument("--url", required=True, help="company URL, e.g. https://stripe.com")
    ap.add_argument("--name", default=None, help="override the display brand name")
    ap.add_argument("--out", required=True, help="output path for brand_theme.json")
    args = ap.parse_args(argv)

    theme = extract_brand(args.url, name_override=args.name, fetcher=_live_webfetch)

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
