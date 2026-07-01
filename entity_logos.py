"""entity_logos.py — BUILD-TIME logo staging for split-mosaic / logo-wall tiles.

The split-mosaic / logo-wall feature cards show a grid of REAL company names
(scene.data.featureEntities, e.g. ["Airbnb","Stripe","Dropbox"]). This module
fetches each entity's real brand mark and stages it as a SELF-CONTAINED data URI
on scene.data.entityLogos[i] — index-aligned with featureEntities — so the
headless Remotion render on the Railway worker needs ZERO render-time network.

DATA CONTRACT (studio/src/timeline/types.ts):
  scene.data.entityLogos: string[]   # index-aligned with scene.data.featureEntities
    each entry is "data:image/<mime>;base64,…"  OR  ""  (empty = no logo found ->
    the tile honestly falls back to the entity name/initial). NEVER invented.
  Only populated for scenes whose data.treatment is "split-mosaic" or "logo-wall".

HONESTY: an empty string is the correct, honest output when no real mark is found
(unknown brand, a TV-show / generic-phrase entity, a fetch error). We never invent
a logo and never block a render — every failure path degrades to "".

NETWORK: logos come from DuckDuckGo's icon proxy
(https://icons.duckduckgo.com/ip3/<domain>.ico), which returns the real favicon
bytes (PNG / JPEG / ICO depending on the site) despite the .ico extension. Fetched
ONCE per build, cached by domain within a single attach call.
"""

from __future__ import annotations

import base64
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

# A normal browser UA — DDG serves the generic/blank icon to unknown clients.
_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36")

# DDG's blank/placeholder for an unknown domain comes back tiny; anything under
# this many bytes is treated as "no real mark".
_MIN_LOGO_BYTES = 400

# Cap an individual encoded data URI so a fat favicon can't bloat props.json.
_MAX_DATA_URI_BYTES = 250 * 1024  # ~250KB

_TIMEOUT_S = 6

# Treatments whose tiles can carry per-entity logos.
_LOGO_TREATMENTS = {"split-mosaic", "logo-wall"}

# Name -> domain exceptions where the lowercase-strip-append-".com" heuristic
# fails. Map to None for entities that are NOT companies (TV shows, generic
# phrases) so we never fetch a wrong/misleading mark. Keep this CONSERVATIVE —
# only well-known collisions; everything else uses the default heuristic.
KNOWN_OVERRIDES: Dict[str, Optional[str]] = {
    "scale ai": "scale.com",
    "scale": "scale.com",
    "y combinator": "ycombinator.com",
    "ycombinator": "ycombinator.com",
    "yc": "ycombinator.com",
    "the ringer": "theringer.com",
    "gimlet media": "gimletmedia.com",
    "gimlet": "gimletmedia.com",
    "openai": "openai.com",
    "open ai": "openai.com",
    "hugging face": "huggingface.co",
    "huggingface": "huggingface.co",
    "ramp": "ramp.com",
    "brex": "brex.com",
    "the new york times": "nytimes.com",
    "new york times": "nytimes.com",
    "google cloud": "cloud.google.com",
    "amazon web services": "aws.amazon.com",
    "aws": "aws.amazon.com",
    # Not companies -> never fetch (would pull a wrong/irrelevant mark).
    "stranger things": None,
    "the crown": None,
    "the office": None,
    "breaking bad": None,
    "game of thrones": None,
}

# Magic-byte -> MIME map for the favicon formats DDG actually returns.
# (key bytes, mime). Order matters: ICO and "GIF8" are checked by prefix below.
_PNG_MAGIC = b"\x89PNG"
_JPEG_MAGIC = b"\xff\xd8"
_GIF_MAGIC = b"GIF8"
_ICO_MAGIC = b"\x00\x00\x01\x00"


def _resolve_domain(name: str) -> Optional[str]:
    """Heuristic entity-name -> domain.

    Default: lowercase, strip every non-alphanumeric char, append ".com"
    ("Airbnb"->"airbnb.com", "DoorDash"->"doordash.com", "Reddit"->"reddit.com").
    KNOWN_OVERRIDES wins for common exceptions; an override mapped to None means
    "not a company, don't fetch" -> returns None. Returns None for empty input.
    """
    if not name or not str(name).strip():
        return None
    key = str(name).strip().lower()
    if key in KNOWN_OVERRIDES:
        return KNOWN_OVERRIDES[key]  # may be a domain OR None (intentional skip)
    slug = "".join(ch for ch in key if ch.isalnum())
    if not slug:
        return None
    return slug + ".com"


def _mime_from_magic(data: bytes) -> str:
    """Sniff the image MIME from leading magic bytes. Defaults to PNG.

    Definitive binary raster magics are checked first; SVG/XML is detected by
    content sniff. WHY SVG matters: some brands (e.g. Stripe) return an SVG
    favicon. A data URI that labels SVG bytes as `image/png` makes Chrome /
    Remotion's <Img> try the PNG decoder on XML -> "EncodingError: The source
    image cannot be decoded" -> the ENTIRE render aborts (one bad logo tile
    silently killed every stripe.com render for ~1.3 days). Labeling it honestly
    as image/svg+xml routes it to the browser's SVG renderer instead.
    """
    if data.startswith(_PNG_MAGIC):
        return "image/png"
    if data.startswith(_JPEG_MAGIC):
        return "image/jpeg"
    if data.startswith(_GIF_MAGIC):
        return "image/gif"
    if data.startswith(_ICO_MAGIC):
        return "image/x-icon"
    sniff = data[:512].lstrip().lower()
    if sniff.startswith(b"<?xml") or sniff.startswith(b"<svg") or b"<svg" in sniff:
        return "image/svg+xml"
    return "image/png"  # DDG's documented default; render handles a generic data:image/png


def _fetch_logo(domain: str) -> Optional[Tuple[bytes, str]]:
    """Fetch a real favicon for `domain` from DDG. Returns (bytes, mime) or None.

    None means "no usable mark" — HTTP error, network failure, or a too-small
    body (DDG's blank placeholder for unknown domains). NEVER raises.
    """
    if not domain:
        return None
    url = "https://icons.duckduckgo.com/ip3/%s.ico" % domain
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as resp:
            if getattr(resp, "status", 200) and resp.status >= 400:
                return None
            data = resp.read()
    except (urllib.error.HTTPError, urllib.error.URLError, OSError, ValueError):
        return None
    except Exception:
        # Defensive: any unexpected failure degrades to "no logo", never raises.
        return None
    if not data or len(data) < _MIN_LOGO_BYTES:
        return None  # blank/placeholder icon -> treat as no mark
    return data, _mime_from_magic(data)


def _data_uri(data: bytes, mime: str) -> str:
    """Encode raw image bytes as a self-contained base64 data URI."""
    return "data:%s;base64,%s" % (mime, base64.b64encode(data).decode("ascii"))


def attach_entity_logos(scenes: Any) -> Any:
    """Stage per-entity logo data URIs onto every split-mosaic / logo-wall scene.

    For each scene dict whose data.treatment is in {"split-mosaic","logo-wall"}
    and whose data.featureEntities is a non-empty list, build
    data["entityLogos"] — a list ALIGNED with featureEntities, each entry a logo
    data URI or "" (no mark found). Fetches are cached by domain within the call.
    Every entity is wrapped in try/except -> "" on any failure. NEVER raises out
    of this function; scenes without a logo treatment are left untouched.

    Mutates the scene dicts in place AND returns `scenes` for chaining.
    """
    if not isinstance(scenes, list):
        return scenes
    domain_cache: Dict[str, str] = {}  # domain -> data URI ("" = fetched-but-empty)

    for scene in scenes:
        try:
            if not isinstance(scene, dict):
                continue
            data = scene.get("data")
            if not isinstance(data, dict):
                continue
            treatment = str(data.get("treatment") or "").strip()
            if treatment not in _LOGO_TREATMENTS:
                continue  # leave non-logo scenes completely untouched (no entityLogos key)
            entities = data.get("featureEntities")
            if not isinstance(entities, list) or not entities:
                continue

            logos: List[str] = []
            for entity in entities:
                uri = ""
                try:
                    domain = _resolve_domain(str(entity))
                    if domain:
                        if domain in domain_cache:
                            uri = domain_cache[domain]
                        else:
                            fetched = _fetch_logo(domain)
                            if fetched is not None:
                                candidate = _data_uri(*fetched)
                                # Cap: skip an oversized logo so props.json stays lean.
                                if len(candidate.encode("utf-8")) <= _MAX_DATA_URI_BYTES:
                                    uri = candidate
                            domain_cache[domain] = uri  # cache "" too (don't re-fetch misses)
                except Exception:
                    uri = ""  # any per-entity failure -> honest empty tile
                logos.append(uri)

            data["entityLogos"] = logos
        except Exception:
            # A malformed scene must never break logo staging for the rest.
            continue

    return scenes
