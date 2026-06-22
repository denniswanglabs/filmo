#!/usr/bin/env python3
"""Deterministic, $0 screenshot capture for the Walk Studio `apple-screenshot`
scene archetype.

R3-B hardening (2026-06-22):
- Apex-domain fallback: if the canonical URL uses a ccTLD (e.g. tripadvisor.com.tw,
  shopify.com.tw), attempt capture on the apex .com equivalent first (often less
  aggressively bot-blocked), then fall back to the original.
- UA rotation: added sec-ch-ua, sec-fetch-* and Upgrade-Insecure-Requests headers
  so Playwright looks less like a headless bot to Cloudflare-style challenges.
- The synth fallback in adapters.py now emits populated brand-tinted mocks (not
  a black box); this module's job is just to try harder before admitting failure.

Grabs REAL headless-browser screenshots of a company's website (the homepage,
plus 1-2 key routes if easily discoverable from the homepage nav) and writes
them to `runs/<run_id>/screenshots/shot-NN.png` with a small `manifest.json`.

DESIGN
- MODE-INDEPENDENT: screenshots are free + deterministic, so capture ALWAYS
  runs (mock or real). The studio card renders them in BOTH modes. This is the
  point: a MOCK Standard build shows REAL screenshots in white studio cards.
- NEVER LLM-drawn — real Chromium screenshots only.
- Pure capture: no styling, no overlays. The Remotion `AppleScreenshot`
  archetype owns all framing/motion.

PLAYWRIGHT ENV
- The host python (3.14) has no Playwright wheel. This module is designed to be
  invoked as a SUBPROCESS via a dedicated venv interpreter that DOES have
  Playwright + chromium installed: `.venv-capture/bin/python` at the repo root.
  `capture_url()` (the in-process API) handles that re-exec automatically: if
  Playwright can't import in the current interpreter, it shells out to the
  capture venv and parses the manifest back. Callers (adapters.py) therefore
  just call `capture_screenshots.capture_url(...)` and get a manifest dict.

CLI
    python capture_screenshots.py --url https://stripe.com --out-dir runs/<id>/screenshots
    python capture_screenshots.py --url https://stripe.com --out-dir /tmp/shots --max 2
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
# The dedicated venv that carries Playwright + chromium (see module docstring).
CAPTURE_PY = os.path.join(HERE, ".venv-capture", "bin", "python")

# A desktop-ish viewport. 1600px wide matches the brief ("1600px-ish wide") and
# crops cleanly inside the 16:9 studio card. We capture ABOVE-THE-FOLD by default
# (full_page=False) so the hero/nav reads as a real product shot rather than a
# tall scroll-strip; the archetype can shrink/zoom a clean landing frame.
VIEWPORT = {"width": 1600, "height": 1000}
DEVICE_SCALE = 2  # retina — sharp text when the card scales the PNG up

# Desktop UA that bypasses most mobile/geo redirects. Includes Chrome version so
# sites don't detect a headless Playwright default UA and redirect to zh/mobile.
# R3-B: bumped to Chrome 124 stable + realistic sec-ch-ua to reduce bot-wall hits.
_DESKTOP_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.6367.82 Safari/537.36"
)

# Full realistic request-headers block: sec-ch-ua, sec-fetch-*, and
# Upgrade-Insecure-Requests so the browser context looks like a real Chrome 124.
# Defined here as a plain dict; _re is imported further below.
_EXTRA_HEADERS = {
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "sec-ch-ua": (
        '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"'
    ),
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "none",
    "sec-fetch-user": "?1",
    "Upgrade-Insecure-Requests": "1",
}

# Route path segments that strongly signal a rich content-y inner page.
# Ranked: first match wins when we sort candidates.
_PRIORITY_SEGMENTS = (
    "pricing", "features", "feature", "products", "product",
    "solutions", "solution", "platform", "how-it-works", "why",
    "enterprise", "for-business", "for-teams", "use-cases",
)

# Signals that a page is a bot-block / challenge page. Checked in title + body text.
_BLOCK_SIGNALS = (
    "access is temporarily restricted",
    "access denied",
    "are you a robot",
    "captcha",
    "cloudflare",
    "please verify you are a human",
    "security check",
    "checking your browser",
    "please enable javascript and cookies",
    "just a moment",  # Cloudflare waiting room
    "ray id",         # Cloudflare footer marker
    "enable cookies",
)

# URL path segments that indicate a geo-redirect to a non-English locale.
# e.g. shopify.com/tw/... or tripadvisor.com/zh-TW/... or site.com/fr/...
import re as _re
_GEO_LOCALE_RE = _re.compile(
    r"/(?:"
    r"tw|zh-tw|zh-hk|zh-cn|zh|ja|ko|de|fr|es|pt|it|nl|pl|sv|da|fi|nb|"
    r"ru|ar|he|tr|cs|sk|hu|ro|bg|hr|uk|vi|th|id|ms|"
    r"zh_tw|zh_cn|zh_hk"
    r")(?:/|$)",
    _re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Apex-domain fallback helpers (R3-B)
# ---------------------------------------------------------------------------

# ccTLD suffixes we try to strip to get an apex .com equivalent.
# e.g. "tripadvisor.com.tw" -> "tripadvisor.com"
#      "shopify.com.tw"     -> "shopify.com"
#      "stripe.com"         -> unchanged (no ccTLD)
_CCTLD_RE = _re.compile(
    r"^(.*)\.(com|net|org|co)\."
    r"(?:tw|hk|au|uk|nz|sg|my|ph|id|th|vn|jp|kr|br|mx|ar|cl|pe|in|za|ng|eg|tr|"
    r"pl|cz|sk|hu|ro|bg|hr|rs|si|gr|pt|es|it|fr|de|nl|be|at|ch|se|no|dk|fi|"
    r"ru|ua|by|kz|ae|sa|il|ir|pk)$",
    _re.IGNORECASE,
)


def _apex_url(url: str) -> Optional[str]:
    """Return the apex .com URL if the host uses a ccTLD double-extension, else None.

    E.g. https://tripadvisor.com.tw/... -> https://tripadvisor.com/...
         https://shopify.com.tw        -> https://shopify.com/
         https://stripe.com            -> None (already apex)
    """
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    # Strip port if present.
    host_noport = host.split(":")[0]
    m = _CCTLD_RE.match(host_noport)
    if not m:
        return None
    # e.g. "tripadvisor.com" from "tripadvisor.com.tw"
    apex_host = "%s.%s" % (m.group(1), m.group(2))
    port = (":" + host.split(":")[1]) if ":" in host else ""
    new_netloc = apex_host + port
    new_parsed = parsed._replace(netloc=new_netloc, path="/")
    return new_parsed.geturl()


def _have_playwright() -> bool:
    try:
        import playwright  # noqa: F401
        from playwright.sync_api import sync_playwright  # noqa: F401
        return True
    except Exception:
        return False


def _wait_for_spa_hydration(page, settle_ms: int = 1500) -> None:
    """Gate on semantic content presence before taking a screenshot.

    Heavy-JS SPAs (Linear, Vercel, Notion, etc.) render a blank/black hero
    until their JS bundle hydrates. A naive `networkidle` after goto often
    fires before the React/Vue tree has flushed into the DOM, leaving the
    screenshot near-empty.

    Strategy (per R4-C brief):
      1. Wait for ANY of: h1, h2, main, article, or nav a — a semantic signal
         that the app has rendered at least a structural skeleton. Timeout of
         10s; if nothing appears the page is still better served by giving it
         time than by aborting.
      2. Wait for networkidle (all pending XHR/fetch quiet) — this is the
         reliable "JS done" signal for most SPAs.
      3. A short settle delay to let CSS transitions + lazy images finish.

    Called INSIDE `grab()`, after the initial page.goto, before screenshot.
    Never raises — failures are silenced so a slow page still gets its shot.
    """
    # Step 1: semantic presence gate (h1/h2/main/article/nav a).
    semantic_selector = "h1, h2, main, article, nav a"
    try:
        page.wait_for_selector(semantic_selector, state="attached", timeout=10000)
    except Exception:
        pass  # page may not have these elements; proceed anyway

    # Step 2: networkidle — quiet XHR/fetch traffic signals JS execution done.
    try:
        page.wait_for_load_state("networkidle", timeout=10000)
    except Exception:
        pass

    # Step 3: short settle so CSS transitions + lazy-load images finish.
    try:
        page.wait_for_timeout(settle_ms)
    except Exception:
        pass


def _is_near_empty_png(path: str) -> bool:
    """Return True if the captured PNG is near-black or near-empty.

    Uses ffprobe to compute mean luminance (signalstats filter). A frame is
    considered near-empty when:
      - average luma (Y) < 12 (near-black — JS never painted the page, or a
        WebGL canvas rendered nothing in headless mode; 12 catches Linear's
        dark hero which scores ~9.5 YAVG with only the nav bar visible), OR
      - average luma > 247 (pure white — page loaded a blank white shell).

    Falls back to False (accept the frame) if ffprobe is unavailable or the
    file is missing — we never want a probe failure to discard a real frame.
    """
    if not path or not os.path.exists(path):
        return False
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "frame_tags=lavfi.signalstats.YAVG",
                "-f", "lavfi",
                "-i", "movie=%s,signalstats" % path.replace("\\", "/"),
                "-of", "default=noprint_wrappers=1:nokey=1",
            ],
            capture_output=True, text=True, timeout=15, check=False,
        )
        raw = (result.stdout or "").strip().splitlines()
        if raw:
            yavg = float(raw[0])
            return yavg < 12.0 or yavg > 247.0
    except Exception:
        pass
    return False


def _norm_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return url
    if not urlparse(url).scheme:
        url = "https://" + url
    return url


def _is_blocked(page) -> bool:
    """Return True if the current page looks like a bot-block / challenge page.

    Checks: page title, visible body text (first 2000 chars), and very short
    (or empty) body text length. Block pages are often near-empty or contain
    only the challenge form; a fully-empty body means JS never loaded content.
    """
    try:
        title = (page.title() or "").lower()
    except Exception:
        title = ""
    try:
        body_text = (page.inner_text("body") or "")
    except Exception:
        body_text = ""
    combined = (title + " " + body_text[:2000]).lower()
    for sig in _BLOCK_SIGNALS:
        if sig in combined:
            return True
    # A suspiciously short body (< 300 chars of visible text including EMPTY
    # bodies) is also a red flag — a real product page always has more content
    # than a challenge/spinner page or a blank JS SPA that failed to hydrate.
    if len(body_text.strip()) < 300:
        return True
    return False


def _discover_routes(page, base_url: str, max_routes: int) -> List[str]:
    """Pull up to `max_routes` same-origin, content-y links from the homepage nav.

    PRIORITY: routes containing high-value path segments (/pricing, /features,
    /products, /solutions, /platform …) are returned FIRST, so the 2nd screenshot
    is a genuinely different, content-rich inner page rather than e.g. /about or
    the first link found in the footer.  After high-priority routes are exhausted,
    remaining candidates fill in order of discovery.

    Deterministic: we DON'T use an LLM for ranking — the priority list is static.
    """
    if max_routes <= 0:
        return []
    base_host = urlparse(base_url).netloc.lower()
    base_norm = base_url.rstrip("/")
    skip_words = ("login", "signin", "sign-in", "signup", "sign-up", "register",
                  "logout", "privacy", "terms", "legal", "cookie", "careers",
                  "contact", "support", "status", "blog", "press", "news",
                  "events", "about", "team", "jobs", "partner", "affiliate",
                  "download", "app-store", "play-store", "social", "community")
    try:
        hrefs = page.eval_on_selector_all(
            "a[href]", "els => els.map(e => e.getAttribute('href'))"
        ) or []
    except Exception:
        hrefs = []
    seen: set = set()
    priority: List[str] = []   # high-value inner routes (pricing, features, …)
    fallback: List[str] = []   # everything else that passes the skip filter

    for href in hrefs:
        if not href or href.startswith("#") or href.startswith("mailto:") \
                or href.startswith("tel:") or href.startswith("javascript:"):
            continue
        full = urljoin(base_url, href)
        pu = urlparse(full)
        if pu.scheme not in ("http", "https"):
            continue
        if pu.netloc.lower() != base_host:
            continue
        # normalize away fragment/query so /pricing and /pricing#x dedupe
        norm = f"{pu.scheme}://{pu.netloc}{pu.path.rstrip('/')}"
        if norm == base_norm:
            continue  # the homepage itself
        if norm in seen:
            continue
        low_path = pu.path.lower()
        if any(w in low_path for w in skip_words):
            continue
        # must look like a real route (has a path segment), not an asset
        path = pu.path.rstrip("/")
        if not path or path.count("/") == 0:
            continue
        if path.lower().endswith((".pdf", ".png", ".jpg", ".svg", ".zip", ".xml")):
            continue
        seen.add(norm)
        # Assign to priority bucket if it contains a high-value segment.
        if any(seg in low_path.split("/") for seg in _PRIORITY_SEGMENTS):
            priority.append(full)
        else:
            fallback.append(full)

    # Return priority routes first, then fallback, up to max_routes.
    combined = priority + fallback
    return combined[:max_routes]


def _capture_inproc(url: str, out_dir: str, max_shots: int) -> Dict[str, Any]:
    """Real capture in THIS interpreter (requires Playwright). Returns manifest."""
    from playwright.sync_api import sync_playwright

    url = _norm_url(url)
    os.makedirs(out_dir, exist_ok=True)
    shots: List[Dict[str, Any]] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        ctx = browser.new_context(
            viewport=VIEWPORT,
            device_scale_factor=DEVICE_SCALE,
            locale="en-US",
            user_agent=_DESKTOP_UA,
            extra_http_headers=_EXTRA_HEADERS,
        )
        page = ctx.new_page()

        def _nav_page(pg, tgt: str) -> bool:
            try:
                pg.goto(tgt, wait_until="networkidle", timeout=30000)
                return True
            except Exception:
                try:
                    pg.goto(tgt, wait_until="domcontentloaded", timeout=30000)
                    return True
                except Exception as e:
                    sys.stderr.write(f"[capture] goto failed {tgt}: {e}\n")
                    return False

        def _screenshot_pg(pg, idx: int, target_url: str, label: str,
                           out_d: str) -> Optional[Dict[str, Any]]:
            """Take a screenshot from `pg` and return the shot record, or None."""
            shot_name = f"shot-{idx:02d}.png"
            shot_path = os.path.join(out_d, shot_name)
            try:
                pg.screenshot(path=shot_path, full_page=False)
            except Exception as e:
                sys.stderr.write(f"[capture] screenshot failed {target_url}: {e}\n")
                return None
            size = os.path.getsize(shot_path) if os.path.exists(shot_path) else 0
            if size < 1000:
                return None
            title = ""
            try:
                title = pg.title() or ""
            except Exception:
                pass
            return {
                "index": idx, "file": shot_name, "path": shot_path,
                "url": target_url, "label": label, "title": title,
                "width": VIEWPORT["width"] * DEVICE_SCALE,
                "height": VIEWPORT["height"] * DEVICE_SCALE,
                "bytes": size,
            }

        def grab(target_url: str, idx: int, label: str,
                 allow_scroll: bool = False) -> Optional[Dict[str, Any]]:
            """Navigate to target_url, detect bot-blocks, and screenshot.

            If allow_scroll=True, skips navigation and just scrolls the current
            page down so the 2nd shot is visually distinct from the homepage hero.

            Returns None if the page is bot-blocked (after one retry) or fails.

            R4-C: SPA hydration gate is applied after every navigation so heavy-JS
            sites (Linear, Vercel, Notion, etc.) have time to render their React/Vue
            trees before we screenshot. Additionally, if the captured frame is
            near-empty/near-black (luminance check) we retry once after a longer
            settle, accepting the second shot regardless of its luminance.
            """
            if allow_scroll:
                # Scroll to mid-page to expose a visually different view.
                try:
                    page.evaluate(
                        "window.scrollTo(0, Math.round(document.body.scrollHeight * 0.45))")
                    page.wait_for_timeout(600)
                except Exception:
                    pass
                return _screenshot_pg(page, idx, target_url, label, out_dir)

            if not _nav_page(page, target_url):
                return None

            # R4-C: SPA hydration gate — wait for semantic content + networkidle
            # + settle before checking for bot-blocks or taking the screenshot.
            # This is the key fix for Linear (and other heavy-JS SPAs) rendering
            # black/near-empty frames: we gate on h1/h2/main/article/nav a being
            # present in the DOM, then networkidle, then a short settle.
            _wait_for_spa_hydration(page, settle_ms=1500)

            # Geo-redirect detection: if the final URL contains a non-English
            # locale path segment (/tw/, /zh-tw/, /fr/, …) skip this route.
            try:
                final_url = page.url or ""
            except Exception:
                final_url = ""
            if _GEO_LOCALE_RE.search(final_url):
                sys.stderr.write(
                    f"[capture] geo-redirected to non-en locale, skipping: "
                    f"{target_url} -> {final_url}\n")
                return None

            # Bot-block detection: retry with two strategies in order:
            #   1. Apex .com URL (e.g. tripadvisor.com.tw -> tripadvisor.com) — often
            #      less aggressively bot-blocked than a ccTLD mirror.
            #   2. Same URL on a fresh page (original R2 behaviour).
            if _is_blocked(page):
                sys.stderr.write(
                    f"[capture] bot-block detected on first attempt: {target_url}\n")

                # Strategy 1: try the apex .com equivalent for ccTLD hosts.
                apex = _apex_url(target_url)
                if apex and apex != target_url:
                    sys.stderr.write(
                        f"[capture] trying apex .com equivalent: {apex}\n")
                    try:
                        fresh_apex = ctx.new_page()
                        try:
                            if _nav_page(fresh_apex, apex):
                                _wait_for_spa_hydration(fresh_apex, settle_ms=2000)
                                if not _is_blocked(fresh_apex):
                                    rec = _screenshot_pg(fresh_apex, idx, apex, label, out_dir)
                                    if rec:
                                        sys.stderr.write(
                                            f"[capture] apex retry succeeded: {apex}\n")
                                        return rec
                                sys.stderr.write(
                                    f"[capture] apex still blocked: {apex}\n")
                        finally:
                            try:
                                fresh_apex.close()
                            except Exception:
                                pass
                    except Exception as e:
                        sys.stderr.write(
                            f"[capture] apex page creation failed {apex}: {e}\n")

                # Strategy 2: fresh page with original URL.
                try:
                    fresh = ctx.new_page()
                    try:
                        if not _nav_page(fresh, target_url):
                            return None
                        _wait_for_spa_hydration(fresh, settle_ms=2000)
                        if _is_blocked(fresh):
                            sys.stderr.write(
                                f"[capture] bot-block confirmed after retry, skipping: "
                                f"{target_url}\n")
                            return None
                        return _screenshot_pg(fresh, idx, target_url, label, out_dir)
                    finally:
                        try:
                            fresh.close()
                        except Exception:
                            pass
                except Exception as e:
                    sys.stderr.write(
                        f"[capture] retry page creation failed {target_url}: {e}\n")
                    return None

            # Take the screenshot; if the frame is near-empty/near-black, retry
            # once. Two-branch retry strategy:
            #
            # A) Body text is RICH (>500 chars of visible text — the DOM has
            #    hydrated but a WebGL/Canvas hero renders black in headless
            #    Chromium's software renderer). Scroll down past the hero to
            #    expose real HTML content below the fold, then reshoot.
            #    Covers: Linear, Vercel, Three.js-heavy homepages.
            #
            # B) Body text is THIN (<= 500 chars — the JS bundle hasn't run
            #    yet / true hydration gap). Give a longer settle (3s) then
            #    reshoot in-place.
            rec = _screenshot_pg(page, idx, target_url, label, out_dir)
            if rec and _is_near_empty_png(rec.get("path", "")):
                try:
                    body_text_len = len((page.inner_text("body") or "").strip())
                except Exception:
                    body_text_len = 0
                if body_text_len > 500:
                    # Branch A: WebGL/Canvas hero — scroll past it to real HTML.
                    sys.stderr.write(
                        f"[capture] near-empty frame (WebGL hero likely), "
                        f"body={body_text_len}ch — scrolling past hero for "
                        f"{target_url}\n")
                    try:
                        page.evaluate(
                            "window.scrollTo(0, Math.round(window.innerHeight * 0.9))")
                        page.wait_for_timeout(800)
                    except Exception:
                        pass
                else:
                    # Branch B: true JS hydration gap — longer settle.
                    sys.stderr.write(
                        f"[capture] near-empty frame (hydration gap), "
                        f"body={body_text_len}ch — settling 3s for "
                        f"{target_url}\n")
                    try:
                        page.wait_for_timeout(3000)
                    except Exception:
                        pass
                retry_rec = _screenshot_pg(page, idx, target_url, label, out_dir)
                if retry_rec:
                    sys.stderr.write(
                        f"[capture] near-empty retry completed for {target_url}\n")
                    return retry_rec
            return rec

        first = grab(url, 1, "home")
        if first:
            shots.append(first)
            if max_shots > 1:
                # discover key routes ONLY after we have a valid homepage (we're on it).
                extra_routes = _discover_routes(page, url, max_routes=max_shots - 1)
                placed = False
                for i, route in enumerate(extra_routes, start=2):
                    rec = grab(route, i, "route")
                    if rec:
                        shots.append(rec)
                        placed = True
                        if len(shots) >= max_shots:
                            break
                if not placed:
                    # No usable inner route found — capture a scrolled-down view of
                    # the homepage as a visually distinct 2nd shot instead of
                    # re-shooting the identical above-the-fold frame.
                    sys.stderr.write(
                        "[capture] no distinct inner route found; "
                        "using scrolled homepage as 2nd shot\n")
                    # Navigate back to homepage (we may have wandered to a blocked route).
                    try:
                        page.goto(url, wait_until="domcontentloaded", timeout=30000)
                        page.wait_for_timeout(800)
                    except Exception:
                        pass
                    rec = grab(url, 2, "home-scroll", allow_scroll=True)
                    if rec:
                        shots.append(rec)

        browser.close()

    manifest = {"url": url, "count": len(shots), "shots": shots, "ok": bool(shots)}
    with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)
    return manifest


def capture_url(url: str, out_dir: str, max_shots: int = 2) -> Dict[str, Any]:
    """In-process capture API. Re-execs into `.venv-capture` if Playwright is not
    importable in the current interpreter, then reads the manifest back.

    Returns the manifest dict: {"url","count","shots":[{file,path,url,label,...}],"ok"}.
    Raises RuntimeError if no capture path is available or capture produced nothing.
    """
    url = _norm_url(url)
    os.makedirs(out_dir, exist_ok=True)

    if _have_playwright():
        return _capture_inproc(url, out_dir, max_shots)

    # Fall back to the dedicated capture venv as a subprocess.
    if not os.path.exists(CAPTURE_PY):
        raise RuntimeError(
            "Playwright is not importable here and the capture venv is missing "
            f"({CAPTURE_PY}). Create it: "
            "python3.11 -m venv .venv-capture && .venv-capture/bin/pip install playwright "
            "&& .venv-capture/bin/playwright install chromium")
    cmd = [CAPTURE_PY, os.path.abspath(__file__),
           "--url", url, "--out-dir", os.path.abspath(out_dir),
           "--max", str(max_shots)]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180, check=False)
    manifest_path = os.path.join(out_dir, "manifest.json")
    if not os.path.exists(manifest_path):
        raise RuntimeError(
            "capture subprocess produced no manifest (rc=%s)\nSTDERR:\n%s"
            % (proc.returncode, (proc.stderr or "")[-1500:]))
    with open(manifest_path, encoding="utf-8") as fh:
        manifest = json.load(fh)
    if not manifest.get("ok"):
        raise RuntimeError("capture produced no usable shots for %s" % url)
    return manifest


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Deterministic website screenshot capture.")
    ap.add_argument("--url", required=True, help="company homepage URL")
    ap.add_argument("--out-dir", required=True, help="output dir for shot-NN.png + manifest.json")
    ap.add_argument("--max", type=int, default=2, help="max shots (home + up to max-1 routes)")
    args = ap.parse_args(argv)

    if not _have_playwright():
        # When called as a subprocess we EXPECT to be the capture-venv interpreter
        # that has Playwright; if not, surface a clear error.
        sys.stderr.write(
            "[capture] Playwright not importable in this interpreter. Run via the "
            "capture venv (.venv-capture/bin/python) or call capture_url() which "
            "re-execs there automatically.\n")
        return 3
    manifest = _capture_inproc(_norm_url(args.url), args.out_dir, args.max)
    print(json.dumps(manifest, indent=2))
    return 0 if manifest.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
