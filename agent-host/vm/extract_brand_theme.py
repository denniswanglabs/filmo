#!/usr/bin/env python3
"""Host-side brand theme extractor for the Filmo render pipeline.

Turns ANY product URL into a `brand_theme.json` that MATCHES THE RENDER'S EXACT
SHAPE (the kinetic-light Timeline contract that style_fill.py consumes):

  {
    brand, wordmark, tagline,
    palette: {bg, bgCard, bgCardRaised, navy, navyBright, accent, ok, text,
              textMuted, textDim, border},
    fonts:   {fontPrimary, fontMono, fontDisplay},
    features:[{label, value?, sub, accent?}],
    cta_url
  }

It REUSES the proven extraction in `brand_extract.extract_brand()` (live HTML
fetch -> real name / tagline / theme-color / dominant-page accent / features,
all behind that module's honesty guards) and then NORMALIZES the result into the
explicit 11-colour render palette above. The accent is the brand's REAL accent;
the rest of the palette is derived deterministically from that accent + a clean
light surface so every key the render reads is populated with on-brand colour.

CRITICAL honesty rule (inherited from brand_extract): we NEVER fabricate a
tagline or features. A site we cannot learn anything about gets its real name +
a neutral light palette + honest-empty tagline/features — never invented copy.
This is a STRICT IMPROVEMENT over the worker's current placeholder, which writes
fabricated "Product / Fast / Simple / Reliable" features for every brand.

SSRF SAFETY: before any network fetch the target host is resolved and every
returned IP is checked against the private / loopback / link-local / metadata
ranges. A blocked target exits non-zero with a clear message and writes nothing.

CLI:
  python3 extract_brand_theme.py --url <URL> --out <path.json> [--name <override>]

Exit codes: 0 success; 2 SSRF-blocked target; 3 usage/IO error.
"""

import argparse
import html as _html
import ipaddress
import json
import os
import socket
import sys
from urllib.parse import urlparse

# brand_extract lives next to this file in /root/filmo-pipeline; make sure it (and
# its remotion_codegen dependency) import regardless of CWD.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import brand_extract  # noqa: E402


# --------------------------------------------------------------------------- #
# SSRF guard                                                                   #
# --------------------------------------------------------------------------- #
# Literal hostnames that must never be fetched even before DNS resolution.
_BLOCKED_HOSTNAMES = frozenset((
    "localhost", "localhost.localdomain", "ip6-localhost", "ip6-loopback",
))


def _is_blocked_ip(ip_str):
    """True when `ip_str` is a private / loopback / link-local / metadata /
    unique-local / unspecified / reserved address that must not be fetched."""
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return True  # un-parseable -> refuse rather than risk it
    # ipaddress flags cover the required ranges:
    #   is_private  -> 10/8, 172.16/12, 192.168/16, 127/8, ::1, fc00::/7 (ULA)
    #   is_loopback -> 127/8, ::1
    #   is_link_local -> 169.254/16 (incl. 169.254.169.254 metadata), fe80::/10
    if (ip.is_private or ip.is_loopback or ip.is_link_local
            or ip.is_reserved or ip.is_unspecified or ip.is_multicast):
        return True
    # Explicit belt-and-suspenders for the cloud metadata endpoints.
    if ip_str in ("169.254.169.254", "fd00:ec2::254"):
        return True
    # IPv4-mapped / -compatible IPv6 (e.g. ::ffff:127.0.0.1) — unwrap and recheck.
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None and _is_blocked_ip(str(mapped)):
        return True
    return False


def assert_safe_url(url):
    """Resolve the URL's host and REJECT private/internal/metadata targets.

    Raises SSRFBlocked with a clear message if the host is a blocked literal or
    resolves (via socket.getaddrinfo) to ANY blocked IP. Returns the normalized
    URL (https:// prepended when the scheme is missing) on success."""
    u = (url or "").strip()
    if not u:
        raise SSRFBlocked("empty URL")
    if not u.startswith(("http://", "https://")):
        u = "https://" + u
    parsed = urlparse(u)
    if parsed.scheme not in ("http", "https"):
        raise SSRFBlocked("unsupported scheme: %r" % parsed.scheme)
    host = parsed.hostname or ""
    if not host:
        raise SSRFBlocked("URL has no host: %r" % url)
    low = host.lower().rstrip(".")
    if low in _BLOCKED_HOSTNAMES:
        raise SSRFBlocked("blocked hostname: %r" % host)
    # If the host is itself an IP literal, check it directly.
    try:
        ipaddress.ip_address(low)
        if _is_blocked_ip(low):
            raise SSRFBlocked("blocked IP literal: %r" % host)
        return u
    except ValueError:
        pass  # not a literal IP -> resolve it
    # Resolve ALL A/AAAA records; reject if ANY is internal (defends against a
    # name that resolves to a mix of public + private addresses).
    try:
        infos = socket.getaddrinfo(low, None)
    except socket.gaierror as e:
        raise SSRFBlocked("could not resolve host %r: %s" % (host, e))
    resolved = {info[4][0] for info in infos}
    if not resolved:
        raise SSRFBlocked("host %r resolved to no addresses" % host)
    for ip_str in resolved:
        # strip a possible IPv6 scope id ("fe80::1%eth0")
        clean = ip_str.split("%")[0]
        if _is_blocked_ip(clean):
            raise SSRFBlocked(
                "host %r resolves to a blocked address %s" % (host, clean))
    return u


class SSRFBlocked(Exception):
    """Raised when a URL targets a private/internal/metadata address."""


# --------------------------------------------------------------------------- #
# Colour helpers (stdlib only) — derive the 11-colour render palette from the  #
# brand's REAL accent + surface.                                               #
# --------------------------------------------------------------------------- #
def _saturation(hex_color):
    """HSV saturation (0.0-1.0) of a hex colour; 0 for grayscale/invalid. Used to
    detect a desaturated (monochrome-brand) accent that should be replaced with a
    perceptible per-brand hue instead of rendering as a flat grey."""
    r, g, b = _hex_to_rgb(hex_color, (-1, -1, -1))
    if r < 0:
        return 0.0
    mx, mn = max(r, g, b), min(r, g, b)
    return 0.0 if mx == 0 else (mx - mn) / mx


def _decode_entities(s):
    """Decode any residual HTML entities (e.g. &#x27;) the upstream strip left."""
    return _html.unescape(s or "")


def _hex_to_rgb(hex_color, fallback=(0, 0, 0)):
    h = (hex_color or "").lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        return fallback
    try:
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except ValueError:
        return fallback


def _rgb_to_hex(rgb):
    r, g, b = (max(0, min(255, int(round(v)))) for v in rgb)
    return "#%02x%02x%02x" % (r, g, b)


def _mix(c1, c2, t):
    """Linear blend of two hex colours; t=0 -> c1, t=1 -> c2."""
    r1, g1, b1 = _hex_to_rgb(c1)
    r2, g2, b2 = _hex_to_rgb(c2)
    return _rgb_to_hex((r1 + (r2 - r1) * t,
                        g1 + (g2 - g1) * t,
                        b1 + (b2 - b1) * t))


def _luma(hex_color):
    r, g, b = _hex_to_rgb(hex_color)
    return (r * 299 + g * 587 + b * 114) / 1000.0


def _darken_to_navy(accent):
    """A deep, on-brand navy/ink derived from the accent hue (used for the
    `navy` / heading slots). Pulls the accent ~70% toward near-black so it stays
    in the brand family but reads as a dark structural colour."""
    return _mix(accent, "#0a1626", 0.62)


def _palette_from(accent, bg, ink):
    """Build the explicit 11-colour render palette from the brand's real accent
    and surface (bg/ink). Light-surface design (the curated templates are built
    light); every value is a real derivation of the brand accent, never a fixed
    generic. `ok` is a calm green that reads on the light bg."""
    bg = bg or "#ffffff"
    # Force a light working surface for the kinetic-light templates even if the
    # brand's own bg is dark — a dark bg + light cards rendered the "blank card"
    # bug. We keep the brand ACCENT (the real signal) and build light surfaces.
    if _luma(bg) < 200:
        bg = "#ffffff"
    text = ink if (ink and _luma(ink) < 110) else "#0f1b2d"
    navy = _darken_to_navy(accent)
    return {
        "bg": bg,
        "bgCard": bg,
        # a barely-tinted raised card surface (accent mixed 4% into white)
        "bgCardRaised": _mix("#ffffff", accent, 0.04),
        "navy": navy,
        # navyBright: lighten the navy ~28% toward the accent for the secondary
        # heading / bright-navy slot
        "navyBright": _mix(navy, accent, 0.32),
        "accent": accent,
        "ok": "#10b981",
        "text": text,
        "textMuted": _mix(text, bg, 0.32),
        "textDim": _mix(text, bg, 0.55),
        "border": _mix("#ffffff", text, 0.10),
    }


# --------------------------------------------------------------------------- #
# Shape mapping: brand_extract.extract_brand() output -> the render's theme    #
# --------------------------------------------------------------------------- #
_FONT_PRIMARY = "Inter, system-ui, -apple-system, sans-serif"
_FONT_MONO = "ui-monospace, SFMono-Regular, Menlo, monospace"
_FONT_DISPLAY = "Inter, system-ui, sans-serif"


def _map_features(src_features):
    """brand_extract features [{title, sub}] -> render features
    [{label, value?, sub, accent?}]. First feature gets accent:true so the
    CardUi grid has a highlighted tile, matching the fixtures. Honest: only
    real, already-filtered features pass through (empty list stays empty)."""
    out = []
    for i, f in enumerate(src_features or []):
        if not isinstance(f, dict):
            continue
        label = _decode_entities((f.get("label") or f.get("title") or "").strip())
        if not label:
            continue
        sub = _decode_entities((f.get("sub") or "").strip())
        item = {"label": label[:40], "sub": sub[:80]}
        if i == 0:
            item["accent"] = True
        out.append(item)
        if len(out) >= 4:
            break
    return out


def build_theme(url, name_override=None):
    """Run the real extraction and normalize it into the render's theme shape.

    Assumes assert_safe_url() has already passed for `url`. Never fabricates copy;
    falls back to a neutral light palette + honest-empty tagline/features when the
    site yields nothing."""
    src = brand_extract.extract_brand(url, name_override=name_override)

    brand_name = (src.get("name") or "").strip()
    if not brand_name or brand_name.lower() == "the product":
        # honest floor: use the registrable host label if extract gave nothing
        host = (src.get("host") or "").strip()
        brand_name = (host.split(".")[0].capitalize() if host else "") or "The product"

    src_palette = src.get("palette") or {}
    accent = src_palette.get("accent") or "#2563eb"
    bg = src_palette.get("bg") or "#ffffff"
    ink = src_palette.get("ink") or src_palette.get("fg") or "#0f1b2d"

    # A monochrome brand (Vercel) exposes no saturated accent — the page's
    # dominant colour comes back a flat grey (#888888). A grey "accent" reads as
    # no accent at all on the light render. Replace a desaturated extracted accent
    # with brand_extract's deterministic, distinct-per-brand saturated hue (the
    # SAME last-resort the module uses for thin-data brands) so every brand still
    # gets a perceptible, on-the-wheel pop that is stable across runs.
    if _saturation(accent) < 0.18:
        seed = (src.get("host") or brand_name or url)
        accent = brand_extract._deterministic_brand_accent(seed)

    palette = _palette_from(accent, bg, ink)

    tagline = _decode_entities((src.get("tagline") or "").strip())
    host = (src.get("host") or "").strip()
    cta_url = host or url.replace("https://", "").replace("http://", "").rstrip("/")

    theme = {
        "brand": brand_name,
        "wordmark": brand_name,
        "tagline": tagline,                 # honest: "" when none found
        "palette": palette,
        "fonts": {
            "fontPrimary": _FONT_PRIMARY,
            "fontMono": _FONT_MONO,
            "fontDisplay": _FONT_DISPLAY,
        },
        "features": _map_features(src.get("features")),
        "cta_url": cta_url,
    }

    # Preserve the brand's real captured/derived logo + wordmark SVG when present
    # so the render can prefer the real asset over plain wordmark text (the render
    # ignores unknown keys, so this is additive and safe).
    if src.get("wordmark_svg"):
        theme["wordmark_svg"] = src["wordmark_svg"]
    if src.get("logo_src"):
        theme["logo_src"] = src["logo_src"]
        theme["logo_source"] = src.get("logo_source", "captured")
    return theme


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Extract a REAL brand_theme.json (render shape) from a URL.")
    ap.add_argument("--url", required=True, help="product URL, e.g. https://stripe.com")
    ap.add_argument("--out", required=True, help="output path for brand_theme.json")
    ap.add_argument("--name", default=None, help="override the display brand name")
    args = ap.parse_args(argv)

    # 1) SSRF guard FIRST — refuse private/internal/metadata targets, write nothing.
    try:
        safe_url = assert_safe_url(args.url)
    except SSRFBlocked as e:
        sys.stderr.write("SSRF blocked: %s\n" % e)
        return 2

    # 2) Extract + normalize. Extraction never raises (brand_extract is guarded),
    #    but wrap defensively so a surprise can't crash the worker.
    try:
        theme = build_theme(safe_url, name_override=args.name)
    except Exception as e:  # pragma: no cover - defensive
        sys.stderr.write("extraction error: %s\n" % e)
        return 3

    # 3) Write the theme.
    try:
        out_dir = os.path.dirname(os.path.abspath(args.out))
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(theme, f, indent=2, ensure_ascii=False)
            f.write("\n")
    except OSError as e:
        sys.stderr.write("write error: %s\n" % e)
        return 3

    sys.stderr.write(
        "brand_theme written: brand=%r tagline=%r accent=%s features=%d -> %s\n"
        % (theme["brand"], theme["tagline"], theme["palette"]["accent"],
           len(theme["features"]), args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
