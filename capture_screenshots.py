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
    # Pin a US English preference. The server may still IP-geo-redirect (see the
    # SHOPIFY-HARDENING section in OVERHAUL-LOOP-STATE.md: a non-US egress is a
    # money-gated proxy fix, not a header fix), but for sites that honor the header
    # this keeps the capture English.
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Upgrade-Insecure-Requests": "1",
    # NOTE (gate/interstitial overhaul, 2026-06-23): we DELIBERATELY do NOT pin
    # `sec-ch-ua*` / `sec-fetch-*` client-hint headers here. Hand-setting them on
    # a real Chromium nav OVERRIDES the accurate native client-hints with stale,
    # mismatched values — which is itself a bot-tell. Allbirds (and other CDN-
    # fronted storefronts) detect the mismatch and serve a CSS-STRIPPED degraded
    # shell (observed: 4 stylesheets + a stuck loading spinner instead of 110
    # sheets + the styled homepage), and the region modal never renders as a
    # positioned overlay so it can't be answered. Chromium already sends correct
    # sec-ch-ua / sec-fetch headers for each request; let it. Verified: dropping
    # these restores the styled Allbirds render AND surfaces the shipping modal so
    # the gate handler selects US + confirms. Stripe is unaffected (no regression).
}

# ---------------------------------------------------------------------------
# Stealth + hardened launch (R8 SHOPIFY-HARDENING) — make the headless capture
# look like a real desktop Chrome so bot-detection (UA sniff / navigator.webdriver
# / missing chrome.runtime / WebGL vendor) does not serve a degraded page or a
# challenge. NOTE: this defeats BOT-DETECTION only. A server-side geo-IP redirect
# (shopify.com -> /tw from a Taiwan egress) is keyed on the request IP and CANNOT
# be beaten by any in-browser/header trick — that needs a US-egress proxy (set
# WALK_PROXY; see the SHOPIFY-HARDENING note in OVERHAUL-LOOP-STATE.md).
# ---------------------------------------------------------------------------

# Applied via add_init_script BEFORE any navigation so the page never observes the
# headless tells. playwright-stealth-style, dependency-free (no new packages).
_STEALTH_INIT_JS = r"""
(() => {
  try { Object.defineProperty(navigator, 'webdriver', {get: () => undefined}); } catch (e) {}
  try { Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']}); } catch (e) {}
  try {
    Object.defineProperty(navigator, 'plugins', {
      get: () => [1, 2, 3, 4, 5].map(i => ({name: 'Plugin ' + i, filename: 'p' + i})),
    });
    Object.defineProperty(navigator, 'mimeTypes', {get: () => [1, 2].map(i => ({type: 'application/x-' + i}))});
  } catch (e) {}
  try { window.chrome = window.chrome || {runtime: {}, app: {isInstalled: false}}; } catch (e) {}
  try {
    const _q = window.navigator.permissions && window.navigator.permissions.query;
    if (_q) {
      window.navigator.permissions.query = (p) => (
        p && p.name === 'notifications'
          ? Promise.resolve({state: Notification.permission})
          : _q(p)
      );
    }
  } catch (e) {}
  // WebGL vendor/renderer spoof — headless reports "Google SwiftShader" which is a
  // strong bot-tell; report a plausible desktop GPU instead.
  try {
    const _gp = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = function (p) {
      if (p === 37445) return 'Intel Inc.';            // UNMASKED_VENDOR_WEBGL
      if (p === 37446) return 'Intel Iris OpenGL Engine'; // UNMASKED_RENDERER_WEBGL
      return _gp.call(this, p);
    };
  } catch (e) {}
})();
"""


def _proxy_settings() -> Optional[Dict[str, str]]:
    """Optional Playwright proxy from the WALK_PROXY env var (OFF by default).

    The ONLY way to beat a server-side geo-IP redirect (e.g. shopify.com forcing
    /tw from a Taiwan egress) is to egress from a US IP. Set
    WALK_PROXY=http://user:pass@host:port (or socks5://...) to route the capture
    through a US proxy. Unset => no proxy => normal (free) behavior. Documented but
    NOT required: every existing brand captures fine without it."""
    raw = (os.environ.get("WALK_PROXY") or "").strip()
    if not raw:
        return None
    return {"server": raw}


def _launch_browser(p):
    """Launch a hardened Chromium that looks like a real desktop Chrome.

    Preference order (most-realistic first), each falling back to the next:
      1. channel='chrome' + --headless=new  (the user's installed Google Chrome —
         the least bot-detectable; uses real Chrome's TLS/JA3 + feature set)
      2. bundled Chromium + --headless=new   (new headless mode, far less
         detectable than the legacy --headless=old)
      3. bundled Chromium, default headless  (last-resort, original behavior)
    Returns the launched browser. The proxy (if WALK_PROXY is set) is applied at
    launch so it covers the whole context."""
    base_args = ["--no-sandbox", "--disable-blink-features=AutomationControlled"]
    proxy = _proxy_settings()
    common: Dict[str, Any] = {}
    if proxy:
        common["proxy"] = proxy
        sys.stderr.write("[capture] using WALK_PROXY egress\n")
    # 1) real installed Chrome channel + new headless.
    try:
        return p.chromium.launch(channel="chrome",
                                 args=base_args + ["--headless=new"], **common)
    except Exception as e:
        sys.stderr.write("[capture] chrome channel unavailable (%s); "
                         "using bundled chromium\n" % e)
    # 2) bundled chromium + new headless.
    try:
        return p.chromium.launch(args=base_args + ["--headless=new"], **common)
    except Exception as e:
        sys.stderr.write("[capture] --headless=new failed (%s); "
                         "using default headless\n" % e)
    # 3) original behavior.
    return p.chromium.launch(args=base_args, **common)


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


def _page_looks_english(page) -> bool:
    """True when the CURRENT page renders in English (not a geo locale).

    A clean URL is NOT enough — Shopify re-redirects www.shopify.com?locale=en back
    to /tw AND ignores the param, so the URL momentarily looks English while the
    BODY stays zh-TW. We confirm with two cheap signals: the document language is
    English-ish, and the visible body is not dominated by CJK characters. Never
    raises; an unreadable page is treated as not-English (conservative)."""
    try:
        lang = (page.evaluate("() => document.documentElement.lang") or "").lower()
    except Exception:
        lang = ""
    if lang and not (lang.startswith("en") or lang in ("", "x-default")):
        return False
    try:
        body = (page.inner_text("body") or "")[:4000]
    except Exception:
        body = ""
    if not body:
        return True  # nothing to judge; don't penalize on an empty read
    cjk = sum(1 for ch in body if "一" <= ch <= "鿿")
    # >5% CJK in the first 4000 visible chars => a CJK locale page, not English.
    return cjk <= max(20, len(body) * 0.05)


def _try_force_english(page, original_url: str) -> bool:
    """Brand-AGNOSTIC attempt to recover an English page after a geo-redirect.

    A site that geo-redirected (final URL carries a non-en locale segment) MIGHT
    still expose an English path. We try, in order, the cheapest corrections that
    work WITHOUT a US IP:
      1. strip the locale segment  (site.com/tw/ -> site.com/)
      2. append ?locale=en          (some CMSs honor a locale query param)
    A correction is kept ONLY when the resulting page both (a) lands on a non-geo
    URL AND (b) actually RENDERS in English (`_page_looks_english`) — a clean URL
    that still serves the geo locale (Shopify ignores ?locale=en and re-redirects
    to /tw) is rejected. Returns True only on a genuinely English page.

    LIMITATION: a server that 302s to /tw purely on egress IP (Shopify) re-redirects
    every English path back to /tw and exposes NO /en or /us path — no in-browser
    correction can beat it (confirmed; see OVERHAUL-LOOP-STATE.md SHOPIFY-HARDENING).
    This helper recovers the sites where the redirect is path-based, not IP-locked."""
    try:
        landed = page.url or original_url
    except Exception:
        landed = original_url
    if not _GEO_LOCALE_RE.search(landed) and _page_looks_english(page):
        return True  # already English, nothing to do
    candidates = []
    stripped = _GEO_LOCALE_RE.sub("/", landed, count=1)
    if stripped != landed:
        candidates.append(stripped)
    sep = "&" if "?" in original_url else "?"
    candidates.append(original_url.rstrip("/") + sep + "locale=en")
    for cand in candidates:
        try:
            page.goto(cand, wait_until="domcontentloaded", timeout=20000)
            _wait_for_spa_hydration(page, settle_ms=1000)
        except Exception:
            continue
        try:
            now = page.url or cand
        except Exception:
            now = cand
        # BOTH: a non-geo URL AND a body that actually renders English.
        if not _GEO_LOCALE_RE.search(now) and _page_looks_english(page):
            sys.stderr.write(
                "[capture] recovered English via %s (was %s)\n" % (cand, landed))
            return True
    sys.stderr.write(
        "[capture] could not recover English from geo-redirect (%s); "
        "server is IP-geo-locked (needs WALK_PROXY)\n" % landed)
    return False


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


# ===========================================================================
# PRE-CONTENT GATE HANDLER (brand-agnostic, idempotent)
# ===========================================================================
# Many sites open a BLOCKING modal/overlay that gates the real content. The
# naive "click the first close affordance" approach FAILS on a gate that
# REQUIRES a choice — e.g. Allbirds' "Where are we shipping to?" region selector
# (you must SELECT a country to proceed; there is no close-X). The bot then
# captures the modal instead of the product.
#
# This handler distinguishes ANSWER-to-proceed gates from DISMISS overlays:
#   - region/shipping/country/location selector -> SELECT a US/English option
#     (or confirm the pre-selected default) -> click proceed/confirm/continue.
#   - age gate -> confirm the affirmative (Yes / over 21 / Enter).
#   - cookie/GDPR consent -> Accept / Agree / OK (or dismiss).
#   - newsletter/promo/discount popup -> close (X / No thanks).
#   - generic "continue to site"/"enter" -> proceed.
#
# Flow: DETECT a blocking overlay -> CLASSIFY by visible text -> take the RIGHT
# action -> WAIT for it to disappear + re-check -> RETRY/escalate (ESC, close-X,
# click-outside) -> log. Idempotent: a clean page is a fast no-op. Never raises.
#
# This block is duplicated (self-contained) in walk_native.py per the L16
# duplicated-helper convention (capture + walk run as separate subprocesses).

# Keyword sets for classifying a gate from its visible text (lowercased).
# Order of CHECKS in _classify_gate matters: region/age/consent before the
# generic "enter/continue" catch so a region modal that also says "continue"
# is treated as a selector, not a blind proceed.
_GATE_KW_REGION = (
    "ship", "shipping", "region", "country", "where are you", "where are we",
    "location", "choose your", "select your country", "select a country",
    "select your region", "ship to", "shopping from", "deliver to",
    "store", "your destination", "you're visiting from", "are you in",
)
_GATE_KW_AGE = (
    "are you 21", "are you 18", "21 or older", "18 or older", "over 21",
    "over 18", "of legal", "old enough", "your age", "verify your age",
    "i am over", "are you of", "must be 21", "must be 18", "age verification",
    "drinking age", "21+", "18+",
)
_GATE_KW_CONSENT = (
    "cookie", "cookies", "consent", "privacy", "gdpr", "we use",
    "your data", "tracking", "personalize", "we value your privacy",
)
_GATE_KW_NEWSLETTER = (
    "subscribe", "newsletter", "sign up", "email", "discount", "% off",
    "save 10", "save 15", "save 20", "get 10", "first order", "join our",
    "unlock", "promo", "coupon", "deal",
)
_GATE_KW_GENERIC = (
    "enter", "continue", "continue to site", "enter site", "proceed",
    "skip", "no thanks", "maybe later",
)

# Affirmative phrases that SELECT a US/English option or proceed past a gate.
# Used to score candidate buttons/options. Higher score = stronger preference.
# US/English region wins first; then a generic confirm/proceed.
_GATE_US_PREFER = (
    "united states", "shop us", "shop usa", "usa", "u.s.", "us store",
    "stay on", "stay here", "current site", "this site", "english",
    "en-us", "go to us", "shop in usd", "$ usd", "usd",
)
_GATE_PROCEED_PREFER = (
    "confirm", "continue", "proceed", "shop now", "enter", "enter site",
    "go to site", "submit", "done", "save", "apply", "ok", "okay", "got it",
    "i agree", "agree", "accept all", "accept",
)
_GATE_AGE_AFFIRM = (
    "yes", "i am over", "i'm over", "21", "18", "of legal age", "enter",
    "i am of", "over 21", "over 18", "confirm",
)
_GATE_CONSENT_AFFIRM = (
    "accept all", "accept", "agree", "i agree", "allow all", "ok", "okay",
    "got it", "continue",
)
# Close/dismiss affordances for newsletter/promo overlays (no answer needed).
_GATE_DISMISS_PREFER = (
    "no thanks", "no, thanks", "not now", "maybe later", "close", "dismiss",
    "skip", "x", "×",
)

# JS that DETECTS a blocking overlay and reports its visible text + the clickable
# candidates inside it (buttons / links / [role=button] / options / labels). A
# gate qualifies when ANY of: an open role=dialog / aria-modal=true element; OR a
# fixed/absolute element with z-index >= 1000 covering >= 35% of the viewport; OR
# the body/html scroll is locked (overflow hidden / position fixed) AND a large
# high-layer element is present. Returns null when nothing blocks (fast no-op).
_GATE_DETECT_JS = r"""
() => {
  const vw = window.innerWidth, vh = window.innerHeight;
  const vArea = Math.max(1, vw * vh);
  const isShown = (el) => {
    const s = getComputedStyle(el);
    if (s.display === 'none' || s.visibility === 'hidden' || s.opacity === '0') return false;
    const r = el.getBoundingClientRect();
    return r.width > 1 && r.height > 1;
  };
  // Body/html scroll-lock is a strong "a modal is open" signal.
  const be = document.body, he = document.documentElement;
  const bs = be ? getComputedStyle(be) : null, hs = he ? getComputedStyle(he) : null;
  const scrollLocked = !!(
    (bs && (bs.overflow === 'hidden' || bs.position === 'fixed')) ||
    (hs && (hs.overflow === 'hidden'))
  );
  // A translucent/dimming backdrop (rgba with alpha, or a *-black/50 layer) is a
  // strong "modal is open" signal even with no role + no scroll-lock.
  const hasDimBg = (s) => {
    const bg = s.backgroundColor || '';
    const m = bg.match(/rgba?\(([^)]+)\)/);
    if (!m) return false;
    const parts = m[1].split(',').map(x => parseFloat(x));
    if (parts.length === 4) return parts[3] > 0.05 && parts[3] < 0.98;
    // Opaque rgb full-viewport layer also dims the page behind it.
    return false;
  };
  // Candidate blocking containers.
  const all = Array.from(document.querySelectorAll(
    '[role="dialog"], [aria-modal="true"], dialog[open], div, section, aside'
  ));
  let best = null, bestArea = 0, bestBackdrop = null, bestBdArea = 0;
  for (const el of all) {
    if (!isShown(el)) continue;
    const s = getComputedStyle(el);
    const pos = s.position;
    const z = parseInt(s.zIndex, 10);
    const role = (el.getAttribute('role') || '').toLowerCase();
    const ariaModal = el.getAttribute('aria-modal') === 'true';
    const isDialogRole = role === 'dialog' || role === 'alertdialog' ||
                         ariaModal || el.tagName === 'DIALOG';
    const r = el.getBoundingClientRect();
    const frac = (Math.max(0, Math.min(r.right, vw) - Math.max(r.left, 0)) *
                 Math.max(0, Math.min(r.bottom, vh) - Math.max(r.top, 0))) / vArea;
    const isOverlayPos = pos === 'fixed' || pos === 'absolute' || pos === 'sticky';
    // High layer: a positioned element with a real stacking z-index. Tailwind
    // ships z-50 / z-100 (NOT 1000), so the bar is 50, not 1000 (the old bug:
    // Allbirds' region modal is `fixed inset-0 z-100` and was being missed).
    const highLayer = isOverlayPos && (!isNaN(z) && z >= 50);
    // A near-full-viewport fixed element is a modal backdrop/container even when
    // it carries no role and no z (covers + intercepts the page beneath it).
    const fixedBackdrop = pos === 'fixed' && frac >= 0.85;
    const dimBackdrop = isOverlayPos && frac >= 0.6 && hasDimBg(s);
    // Qualify: explicit dialog, OR a high-z layer over a big chunk, OR a
    // full-viewport fixed/dimming backdrop, OR (scroll-locked AND any overlay).
    const qualifies =
      (isDialogRole && frac >= 0.05) ||
      (highLayer && frac >= 0.3) ||
      (fixedBackdrop) ||
      (dimBackdrop) ||
      (scrollLocked && isOverlayPos && frac >= 0.15);
    if (qualifies && frac > bestArea) { best = el; bestArea = frac; }
    // Track a dimming/backdrop layer separately: when the winning container IS a
    // full-viewport backdrop, the real interactive panel (with the buttons) is
    // usually a SMALLER child — but querySelectorAll on the backdrop still
    // reaches it, so `best` = the backdrop is fine. We keep this for a fallback.
    if ((fixedBackdrop || dimBackdrop) && frac > bestBdArea) {
      bestBackdrop = el; bestBdArea = frac;
    }
  }
  if (!best) best = bestBackdrop;
  if (!best) return null;
  // Gather visible clickable candidates INSIDE the gate (and immediate overlay
  // siblings, since some close-X buttons render just outside the dialog node).
  const root = best;
  const candEls = Array.from(root.querySelectorAll(
    'button, a, [role="button"], [role="option"], [role="radio"], ' +
    '[role="menuitemradio"], input[type="submit"], input[type="button"], ' +
    'label, li[role], option, [data-country], [data-locale], select'
  ));
  const seen = new Set();
  const candidates = [];
  for (const el of candEls) {
    if (!isShown(el)) continue;
    const r = el.getBoundingClientRect();
    if (r.bottom < 0 || r.top > vh || r.right < 0 || r.left > vw) continue;
    let text = (el.innerText || el.textContent || el.value || '').trim()
      .replace(/\s+/g, ' ').slice(0, 120);
    const aria = (el.getAttribute('aria-label') || '').trim();
    const title = (el.getAttribute('title') || '').trim();
    const val = (el.getAttribute('value') || '').trim();
    const label = (text || aria || title || val);
    const key = el.tagName + '|' + label + '|' + Math.round(r.x) + ',' + Math.round(r.y);
    if (seen.has(key)) continue;
    seen.add(key);
    candidates.push({
      tag: el.tagName.toLowerCase(),
      text: text, aria: aria, title: title, value: val,
      type: (el.getAttribute('type') || '').toLowerCase(),
      cx: r.x + r.width / 2, cy: r.y + r.height / 2,
      w: r.width, h: r.height,
    });
    if (candidates.length >= 60) break;
  }
  const gateText = (root.innerText || root.textContent || '')
    .replace(/\s+/g, ' ').trim().slice(0, 600);
  return {
    text: gateText, frac: bestArea, scrollLocked: scrollLocked,
    candidates: candidates,
  };
}
"""


def _classify_gate(text: str) -> str:
    """Classify a gate by its visible text -> one of:
    'region' | 'age' | 'consent' | 'newsletter' | 'generic'.
    Region/age/consent are checked BEFORE the generic enter/continue catch so a
    selector that also contains "continue" is treated as a selector."""
    t = (text or "").lower()
    if any(k in t for k in _GATE_KW_AGE):
        return "age"
    if any(k in t for k in _GATE_KW_REGION):
        return "region"
    if any(k in t for k in _GATE_KW_CONSENT):
        return "consent"
    if any(k in t for k in _GATE_KW_NEWSLETTER):
        return "newsletter"
    if any(k in t for k in _GATE_KW_GENERIC):
        return "generic"
    return "generic"


def _cand_label(c: dict) -> str:
    """Lowercased best label for a candidate (text > aria > title > value)."""
    return (c.get("text") or c.get("aria") or c.get("title")
            or c.get("value") or "").strip().lower()


def _score_candidate(c: dict, prefer: tuple, *, exact_bonus=True) -> int:
    """Score a gate candidate against a preference keyword tuple. Earlier
    keywords in `prefer` rank higher; an exact label match gets a bonus."""
    label = _cand_label(c)
    if not label:
        return -1
    best = -1
    for i, kw in enumerate(prefer):
        if kw in label:
            score = (len(prefer) - i) * 10
            if exact_bonus and label == kw:
                score += 100
            if score > best:
                best = score
    return best


def _click_candidate(page, c: dict, *, settle_ms: int = 350) -> bool:
    """Click a gate candidate by its viewport-center coordinates (robust to
    detached locators since the JS already resolved a visible element). Returns
    True on a click that didn't raise."""
    try:
        page.mouse.click(float(c["cx"]), float(c["cy"]))
        try:
            page.wait_for_timeout(settle_ms)
        except Exception:
            pass
        return True
    except Exception:
        return False


def _pick_and_click(page, candidates: list, prefer: tuple) -> bool:
    """Pick the highest-scoring candidate matching `prefer` and click it."""
    best_c, best_s = None, -1
    for c in candidates:
        s = _score_candidate(c, prefer)
        if s > best_s:
            best_s, best_c = s, c
    if best_c is not None and best_s >= 0:
        return _click_candidate(page, best_c)
    return False


def _act_on_gate(page, kind: str, candidates: list) -> str:
    """Take the RIGHT action for a classified gate. Returns a short human label
    of the action taken (for logging), or '' if nothing was clicked."""
    if kind == "region":
        # SELECT a US/English option first (this is the key Allbirds fix: a
        # region selector REQUIRES a choice — closing it leaves the site gated).
        if _pick_and_click(page, candidates, _GATE_US_PREFER):
            # Then click a proceed/confirm if one exists (two-step selectors:
            # pick country -> Confirm). Re-detect happens in the caller loop.
            _pick_and_click(page, candidates, _GATE_PROCEED_PREFER)
            return "selected US/English region + confirm"
        # No explicit US option: confirm the pre-selected default to proceed.
        if _pick_and_click(page, candidates, _GATE_PROCEED_PREFER):
            return "confirmed default region"
        return ""
    if kind == "age":
        if _pick_and_click(page, candidates, _GATE_AGE_AFFIRM):
            return "confirmed age (affirmative)"
        return ""
    if kind == "consent":
        if _pick_and_click(page, candidates, _GATE_CONSENT_AFFIRM):
            return "accepted cookie/consent"
        return ""
    if kind == "newsletter":
        if _pick_and_click(page, candidates, _GATE_DISMISS_PREFER):
            return "closed newsletter/promo"
        return ""
    # generic: try proceed, else dismiss.
    if _pick_and_click(page, candidates, _GATE_PROCEED_PREFER):
        return "proceeded (generic)"
    if _pick_and_click(page, candidates, _GATE_DISMISS_PREFER):
        return "dismissed (generic)"
    return ""


def _escalate_gate(page) -> bool:
    """Escalation when no classified action cleared the gate: ESC, then any
    close-X affordance, then a click on the backdrop (top-left corner outside a
    centered dialog). Returns True if something plausibly closed it."""
    acted = False
    try:
        page.keyboard.press("Escape")
        page.wait_for_timeout(250)
        acted = True
    except Exception:
        pass
    for sel in ("[aria-label*='close' i]", "[aria-label*='dismiss' i]",
                "button[class*='close' i]", "[data-testid*='close' i]"):
        try:
            loc = page.locator(sel).first
            if loc.count() and loc.is_visible(timeout=300):
                loc.click(timeout=600, no_wait_after=True)
                page.wait_for_timeout(250)
                acted = True
                break
        except Exception:
            continue
    return acted


def _handle_content_gate(page, *, log=None, max_tries: int = 3) -> bool:
    """Robust pre-content gate handler. Detects a blocking modal/overlay,
    classifies it, takes the RIGHT action (SELECT-to-proceed for region/age vs
    DISMISS for newsletter/cookie), waits for it to disappear, and retries /
    escalates if still blocked. Idempotent + non-destructive: a clean page is a
    fast no-op. Never raises. Returns True if it acted on at least one gate.

    `log` is an optional callable(str) for tracing what was detected + the
    action taken on each gate (defaults to a no-op)."""
    if log is None:
        log = lambda *_a, **_k: None  # noqa: E731
    acted_any = False
    for attempt in range(1, max_tries + 1):
        try:
            gate = page.evaluate(_GATE_DETECT_JS)
        except Exception:
            gate = None
        if not gate:
            if attempt == 1:
                log("[gate] no blocking overlay detected (clean page)")
            else:
                log("[gate] overlay cleared after action")
            return acted_any
        text = gate.get("text", "") or ""
        cands = gate.get("candidates", []) or []
        kind = _classify_gate(text)
        snippet = text[:90].replace("\n", " ")
        log("[gate] try %d: detected %s gate (frac=%.2f, scrollLocked=%s) — "
            "text='%s'" % (attempt, kind, gate.get("frac", 0.0),
                           gate.get("scrollLocked"), snippet))
        action = _act_on_gate(page, kind, cands)
        if action:
            acted_any = True
            log("[gate] action: %s" % action)
        else:
            esc = _escalate_gate(page)
            if esc:
                acted_any = True
                log("[gate] no classified action matched -> escalated "
                    "(ESC / close-X / backdrop)")
            else:
                log("[gate] could not act on the gate (no candidate matched)")
        # Wait + re-check that the overlay is gone before deciding to retry.
        try:
            page.wait_for_timeout(450)
        except Exception:
            pass
    # Final escalation pass if still blocked after max_tries.
    try:
        if page.evaluate(_GATE_DETECT_JS):
            if _escalate_gate(page):
                acted_any = True
            still = None
            try:
                still = page.evaluate(_GATE_DETECT_JS)
            except Exception:
                still = None
            if still:
                log("[gate] STILL blocked after %d tries + escalation — "
                    "proceeding anyway (capture may be occluded)" % max_tries)
    except Exception:
        pass
    return acted_any


# JS: True while the page still shows a full-page LOADING SPINNER (a large
# animating SVG circle / [class*=spinner] / [class*=loading]) and no real content
# has painted, OR while a blocking gate has NOT yet appeared on a known modal-
# gating site. Brand-agnostic — used only to delay the gate check a beat so a
# late-injected region/age modal (Allbirds injects its shipping modal AFTER
# hydration) and the page CSS both have time to render before we shoot.
_PAGE_LOADING_JS = r"""
() => {
  const vw = innerWidth, vh = innerHeight;
  // A large, roughly-centered spinner element still on screen = still loading.
  const spin = Array.from(document.querySelectorAll(
    'svg, [class*="spinner" i], [class*="loading" i], [class*="loader" i], ' +
    '[role="progressbar"]'
  ));
  for (const el of spin) {
    const s = getComputedStyle(el);
    if (s.display === 'none' || s.visibility === 'hidden' || s.opacity === '0') continue;
    const r = el.getBoundingClientRect();
    // A big element (>= 1/3 of the min viewport dimension) parked mid-viewport.
    const big = Math.min(r.width, r.height) >= Math.min(vw, vh) / 3;
    const onScreen = r.top < vh && r.bottom > 0 && r.left < vw && r.right > 0;
    if (!big || !onScreen) continue;
    // Only count it as a LOADING spinner if it is ANIMATING (real spinners spin)
    // or carries a spinner/loader class — never a big static decorative hero SVG.
    const cls = (el.className && el.className.toString
                 ? el.className.toString() : '').toLowerCase();
    const animating = (s.animationName && s.animationName !== 'none') ||
                      (s.transitionDuration && parseFloat(s.transitionDuration) > 0 &&
                       s.transitionProperty.includes('transform'));
    const named = /spinner|loading|loader|progress/.test(cls) ||
                  el.getAttribute('role') === 'progressbar';
    if (animating || named) return true;
  }
  return false;
}
"""


def _wait_for_gate_or_settle(page, *, max_ms: int = 6000, step_ms: int = 400) -> None:
    """Brief grace poll BEFORE the gate check: many storefronts inject the region/
    age modal AFTER hydration (Allbirds shows 'Where are we shipping to?' a beat
    after the page mounts), and some render a full-page loading spinner first. We
    poll up to `max_ms` for EITHER a blocking gate to appear (so the gate handler
    can answer it) OR the loading spinner to clear (so we don't shoot the spinner
    phase). Returns as soon as a gate is detected. Never raises."""
    waited = 0
    while waited < max_ms:
        try:
            if page.evaluate(_GATE_DETECT_JS):
                return  # a gate appeared — hand straight to the gate handler
        except Exception:
            pass
        try:
            still_loading = bool(page.evaluate(_PAGE_LOADING_JS))
        except Exception:
            still_loading = False
        if not still_loading and waited >= step_ms:
            # No spinner and no gate after at least one tick — page has settled.
            return
        try:
            page.wait_for_timeout(step_ms)
        except Exception:
            break
        waited += step_ms


def _dismiss_interstitial(page) -> bool:
    """Public entry point (name kept for the existing call sites). Gives a late-
    appearing modal / loading spinner a brief beat to settle, then runs the full
    detect -> classify -> act -> verify -> retry/escalate gate handler so a
    region/shipping/age gate that REQUIRES a choice is answered (not just
    closed). Brand-agnostic, idempotent, never raises. Returns True if it acted
    on at least one gate."""
    _wait_for_gate_or_settle(page)
    return _handle_content_gate(
        page, log=lambda m: sys.stderr.write("[capture]%s\n" % m))


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


# Mean-luma difference (0-255) below which two downscaled grayscale frames are
# considered the SAME page. Empirically: distinct pages score ~30+; identical
# frames score 0; minor cookie-banner / animation jitter on the same page stays
# under ~2. We use 3.0 as a conservative "these are the same page" ceiling.
_SAME_PAGE_DIFF_CEIL = 3.0

# R5 (diagnosis FIX-2) — a captured surface whose mean luma is below this reads as a
# DARK marketing hero. Inside the near-white browser card on a near-white page these
# read "muddy" and fight the left headline (Notion's "Meet the night shift" hero was
# the actual 10-pt coherence gap vs Stripe's light captures). When the above-the-fold
# homepage hero is this dark, we prefer a scrolled-down/cleaner content surface.
_DARK_HERO_YAVG_CEIL = 80.0


def _frame_yavg(path: str) -> Optional[float]:
    """Mean luminance (0-255) of a PNG via ffprobe signalstats, or None on failure.
    Reuses the same probe as _is_near_empty_png; None => unknown (never penalize)."""
    if not path or not os.path.exists(path):
        return None
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
            return float(raw[0])
    except Exception:
        pass
    return None


def _image_diff_yavg(path_a: str, path_b: str) -> Optional[float]:
    """Mean luminance (0-255) of the per-pixel difference between two PNGs, after
    downscaling both to a small grayscale frame. Returns None when the comparison
    cannot run (ffmpeg/ffprobe missing, a file absent, or any failure) so the caller
    treats an unknowable comparison as "assume distinct" and never discards a real
    shot on a probe error. A return near 0 means visually identical pages."""
    if not (path_a and path_b and os.path.exists(path_a) and os.path.exists(path_b)):
        return None
    diff_png = path_b + ".diff.png"
    try:
        rc = subprocess.run(
            [
                "ffmpeg", "-y", "-v", "error", "-i", path_a, "-i", path_b,
                "-filter_complex",
                "[0:v]scale=96:60,format=gray[a];"
                "[1:v]scale=96:60,format=gray[b];"
                "[a][b]blend=all_mode=difference",
                "-frames:v", "1", diff_png,
            ],
            capture_output=True, text=True, timeout=30, check=False,
        )
        if rc.returncode != 0 or not os.path.exists(diff_png):
            return None
        probe = subprocess.run(
            [
                "ffprobe", "-v", "error", "-f", "lavfi",
                "-i", "movie=%s,signalstats" % diff_png.replace("\\", "/"),
                "-show_entries", "frame_tags=lavfi.signalstats.YAVG",
                "-of", "default=noprint_wrappers=1:nokey=1",
            ],
            capture_output=True, text=True, timeout=15, check=False,
        )
        raw = (probe.stdout or "").strip().splitlines()
        if raw:
            return float(raw[0])
    except Exception:
        return None
    finally:
        try:
            if os.path.exists(diff_png):
                os.remove(diff_png)
        except Exception:
            pass
    return None


def _images_are_distinct(path_a: str, path_b: str) -> bool:
    """True when two captured PNGs show DIFFERENT pages. Conservative: a comparison
    that cannot run (probe failure) returns True (assume distinct) so we never drop a
    genuinely useful shot. Only an explicit near-zero luma difference (<= the
    same-page ceiling) is treated as a duplicate."""
    diff = _image_diff_yavg(path_a, path_b)
    if diff is None:
        return True  # unknowable -> assume distinct, never discard on probe error
    return diff > _SAME_PAGE_DIFF_CEIL


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


# ---------------------------------------------------------------------------
# Logo capture (Task F) — pull the brand's REAL logo during the same Playwright
# pass. Priority: inline header <svg> -> apple-touch-icon/icon/mask-icon ->
# og:image. Saved to <out_dir>/brand/logo.<ext>; the source is recorded in the
# manifest so brand_extract can prefer it over the derived wordmark. NEVER
# fabricates — any failure leaves no logo file and the caller degrades to the
# derived wordmark.
# ---------------------------------------------------------------------------

# Selectors for an inline site-logo <svg>, most-specific first. A header/nav
# brand link is the highest-confidence "this is the logo" signal.
_LOGO_SVG_SELECTORS = (
    "header a[href='/'] svg",
    "header a[href='./'] svg",
    "a[href='/'][aria-label*='ome' i] svg",   # "Home" / "homepage"
    "[class*='ogo' i] a svg",                  # *Logo* container
    "a[class*='ogo' i] svg",
    "header [class*='ogo' i] svg",
    "nav a[href='/'] svg",
    "header svg",
)


def _logo_svg_outer_html(page) -> Optional[str]:
    """Return the outerHTML of the first plausible inline site-logo <svg>, or None.

    Filters out tiny icon glyphs (search/menu/chevron) by requiring a bounding box
    at least 40px wide — a real wordmark/lockup logo is wide, a hamburger icon is
    square and small. Pure DOM read; never raises."""
    js = """
    (selectors) => {
      for (const sel of selectors) {
        let els;
        try { els = Array.from(document.querySelectorAll(sel)); }
        catch (e) { continue; }
        for (const el of els) {
          const r = el.getBoundingClientRect();
          // a real logo svg is reasonably wide and visible
          if (r && r.width >= 40 && r.height >= 8 && r.width <= 600) {
            const html = el.outerHTML || '';
            if (html && html.toLowerCase().startsWith('<svg')) return html;
          }
        }
      }
      return null;
    }
    """
    try:
        html = page.evaluate(js, list(_LOGO_SVG_SELECTORS))
    except Exception:
        return None
    if not html or not isinstance(html, str):
        return None
    html = html.strip()
    # Ensure the SVG declares a namespace so it renders standalone in an <Img>.
    if "xmlns" not in html[:200]:
        html = html.replace(
            "<svg", '<svg xmlns="http://www.w3.org/2000/svg"', 1)
    return html


def _logo_link_href(page) -> Optional[str]:
    """Return an absolute URL for the best icon/og:image asset, or None.

    Priority: apple-touch-icon (biggest, square brand mark) -> mask-icon ->
    rel=icon -> og:image. Returns the absolute href; the caller downloads it."""
    js = """
    () => {
      const pick = (sel, attr) => {
        const el = document.querySelector(sel);
        return el ? (el.getAttribute(attr) || '') : '';
      };
      return {
        appleTouch: pick("link[rel='apple-touch-icon']", 'href')
                 || pick("link[rel='apple-touch-icon-precomposed']", 'href'),
        maskIcon:   pick("link[rel='mask-icon']", 'href'),
        icon:       pick("link[rel='icon']", 'href')
                 || pick("link[rel='shortcut icon']", 'href'),
        ogImage:    pick("meta[property='og:image']", 'content')
                 || pick("meta[name='og:image']", 'content'),
      };
    }
    """
    try:
        info = page.evaluate(js) or {}
    except Exception:
        info = {}
    for key in ("appleTouch", "maskIcon", "icon", "ogImage"):
        href = (info.get(key) or "").strip()
        if href:
            try:
                base = page.url or ""
            except Exception:
                base = ""
            full = urljoin(base, href) if base else href
            if urlparse(full).scheme in ("http", "https"):
                return full
    return None


def _download_asset(ctx, asset_url: str, dest_no_ext: str) -> Optional[str]:
    """Download an icon/image asset via the Playwright request context. Returns the
    saved path (with an extension inferred from URL/content-type), or None. Never
    raises — a failed download just means no captured logo."""
    try:
        resp = ctx.request.get(asset_url, timeout=15000)
        if not resp.ok:
            return None
        body = resp.body()
        if not body or len(body) < 64:
            return None
        ctype = (resp.headers.get("content-type") or "").lower()
    except Exception:
        return None
    # Infer extension: URL suffix first, then content-type.
    path = urlparse(asset_url).path.lower()
    ext = ""
    for cand in (".svg", ".png", ".ico", ".jpg", ".jpeg", ".webp", ".gif"):
        if path.endswith(cand):
            ext = cand
            break
    if not ext:
        if "svg" in ctype:
            ext = ".svg"
        elif "png" in ctype:
            ext = ".png"
        elif "icon" in ctype or "ico" in ctype:
            ext = ".ico"
        elif "jpeg" in ctype or "jpg" in ctype:
            ext = ".jpg"
        elif "webp" in ctype:
            ext = ".webp"
        else:
            ext = ".png"
    dest = dest_no_ext + ext
    try:
        with open(dest, "wb") as fh:
            fh.write(body)
    except Exception:
        return None
    return dest


def _capture_logo(page, ctx, out_dir: str) -> Optional[Dict[str, str]]:
    """Capture the brand's real logo into <out_dir>/brand/. Returns
    {"file","path","source"} relative-friendly record, or None when no logo found.

    Order: inline header <svg> (serialized) -> apple-touch-icon/icon/mask-icon ->
    og:image -> the well-known /favicon.ico (R5 last-resort: every site serves one
    even when it declares NO <link rel=icon>, which is why shopify.com fell back to
    the derived wordmark SILENTLY). Honest fallback (None) leaves the derived wordmark
    in place. EVERY fallback step logs to stderr so a silent degrade is impossible."""
    brand_dir = os.path.join(out_dir, "brand")
    try:
        os.makedirs(brand_dir, exist_ok=True)
    except Exception:
        return None

    # 1) Inline header <svg> — the highest-confidence real wordmark/lockup.
    svg = _logo_svg_outer_html(page)
    if svg:
        dest = os.path.join(brand_dir, "logo.svg")
        try:
            with open(dest, "w", encoding="utf-8") as fh:
                fh.write(svg)
            return {"file": "logo.svg", "path": dest, "source": "inline-svg"}
        except Exception:
            pass
    sys.stderr.write("[capture] logo: no inline header <svg>; trying icon/og:image\n")

    # 2) Link icons -> og:image (downloaded).
    asset_url = _logo_link_href(page)
    if asset_url:
        saved = _download_asset(ctx, asset_url, os.path.join(brand_dir, "logo"))
        if saved:
            return {
                "file": os.path.basename(saved),
                "path": saved,
                "source": "link-or-og:%s" % asset_url,
            }
        sys.stderr.write(
            "[capture] logo: icon/og asset download failed (%s); trying /favicon.ico\n"
            % asset_url)
    else:
        sys.stderr.write(
            "[capture] logo: no declared icon/og:image link; trying /favicon.ico\n")

    # 3) LAST RESORT — the well-known /favicon.ico at the site root. A site that
    #    declares no <link rel=icon> (Shopify) still serves a favicon here. Better
    #    than a derived wordmark even if it's a square mark, and it is the REAL brand
    #    asset. Resolve against the current origin.
    try:
        base = page.url or ""
    except Exception:
        base = ""
    if base:
        favicon_url = urljoin(base, "/favicon.ico")
        if urlparse(favicon_url).scheme in ("http", "https"):
            saved = _download_asset(ctx, favicon_url, os.path.join(brand_dir, "logo"))
            if saved:
                sys.stderr.write("[capture] logo: using /favicon.ico fallback\n")
                return {
                    "file": os.path.basename(saved),
                    "path": saved,
                    "source": "favicon:%s" % favicon_url,
                }
    sys.stderr.write(
        "[capture] logo: ALL sources failed (svg/icon/og/favicon); "
        "falling back to derived wordmark\n")
    return None


# ---------------------------------------------------------------------------
# Focus rect (Task F) — compute a card-local % rectangle marking a prominent UI
# element the headline can name (so the archetype's highlight-box / zoom can
# target it). Card-local fractions (0..1) relative to the captured VIEWPORT box,
# matching the spec's `data.focus = {x,y,w,h,label}` contract (§2). Best-effort;
# absent => archetype shows a plain shot with no highlight.
# ---------------------------------------------------------------------------
def _normalize_focus_rect(rect: Any) -> Optional[Dict[str, Any]]:
    """Coerce one raw {x,y,w,h,label,score?} (0..1 fractions) -> a clamped focus
    rect, or None when degenerate. Shared by the single + multi-candidate paths."""
    if not isinstance(rect, dict):
        return None
    try:
        x = float(rect.get("x"))
        y = float(rect.get("y"))
        w = float(rect.get("w"))
        h = float(rect.get("h"))
    except (TypeError, ValueError):
        return None
    x = max(0.0, min(1.0, x))
    y = max(0.0, min(1.0, y))
    w = max(0.0, min(1.0 - x, w))
    h = max(0.0, min(1.0 - y, h))
    if w < 0.02 or h < 0.01:
        return None
    out: Dict[str, Any] = {"x": round(x, 4), "y": round(y, 4),
                           "w": round(w, 4), "h": round(h, 4)}
    label = (rect.get("label") or "").strip()
    if label:
        out["label"] = label
    return out


def _compute_focus(page) -> Optional[Dict[str, Any]]:
    """Pick a prominent above-the-fold element and return its card-local % rect.

    Heuristic, deterministic (no LLM): prefer a primary CTA button / nav item /
    hero card that sits within the captured viewport and is comfortably sized.
    Returns {"x","y","w","h","label"} in 0..1 fractions of the VIEWPORT box, or
    None. Never raises.

    Also returns up to a handful of OTHER labelled candidate rects (sorted by score)
    so the downstream copy step can pick the rect whose LABEL best matches the
    scene's headline subject — making the highlight point at what the headline NAMES
    rather than at the single most-prominent CTA (R2 coherence gap). The extra
    candidates ride along under the "_candidates" key (a list of focus rects); the
    primary rect's own fields stay at the top level so existing callers are
    byte-compatible."""
    vw = VIEWPORT["width"]
    vh = VIEWPORT["height"]
    js = """
    (vp) => {
      const W = vp.w, H = vp.h;
      const cands = [];
      const sels = [
        "a[class*='button' i]", "button", "[role='button']",
        "a[href*='pricing' i]", "a[href*='start' i]", "a[href*='signup' i]",
        "[class*='card' i]", "[class*='hero' i] a", "main a[href]",
        "h1", "h2", "h3", "nav a", "[class*='feature' i]",
      ];
      const seen = new Set();
      for (const sel of sels) {
        let els;
        try { els = document.querySelectorAll(sel); } catch (e) { continue; }
        for (const el of els) {
          if (seen.has(el)) continue;
          seen.add(el);
          const r = el.getBoundingClientRect();
          // must be fully-ish inside the captured viewport box and a real size
          if (r.width < 60 || r.height < 18) continue;
          if (r.width > W * 0.95 || r.height > H * 0.7) continue;
          if (r.left < 0 || r.top < 0) continue;
          if (r.left + r.width > W || r.top + r.height > H) continue;
          // prefer elements in the upper 75% (visible in an above-the-fold shot)
          if (r.top > H * 0.75) continue;
          const txt = (el.innerText || el.textContent || '').trim().slice(0, 60);
          // score: favor mid-page, reasonably wide, with a text label
          const centerBias = 1 - Math.abs((r.left + r.width / 2) / W - 0.5);
          const score = r.width * 0.6 + (txt ? 120 : 0) + centerBias * 80;
          cands.push({ x: r.left / W, y: r.top / H, w: r.width / W,
                       h: r.height / H, label: txt, score: score });
        }
      }
      if (!cands.length) return null;
      cands.sort((a, b) => b.score - a.score);
      // Keep a small, labelled set: the top primary + the best labelled others,
      // de-duplicated by label, capped at 8 so the manifest stays small.
      const out = [];
      const labels = new Set();
      for (const c of cands) {
        const key = (c.label || '').toLowerCase().replace(/\\s+/g, ' ').trim();
        if (out.length && key && labels.has(key)) continue;
        if (key) labels.add(key);
        out.push(c);
        if (out.length >= 8) break;
      }
      return out;
    }
    """
    try:
        raw = page.evaluate(js, {"w": vw, "h": vh})
    except Exception:
        return None
    # Back-compat: the JS now returns a list; tolerate an old single-dict too.
    if isinstance(raw, dict):
        raw = [raw]
    if not isinstance(raw, list) or not raw:
        return None
    rects = [r for r in (_normalize_focus_rect(c) for c in raw) if r]
    if not rects:
        return None
    primary = dict(rects[0])
    extras = [r for r in rects[1:] if r.get("label")]
    if extras:
        primary["_candidates"] = extras
    return primary


def _capture_inproc(url: str, out_dir: str, max_shots: int) -> Dict[str, Any]:
    """Real capture in THIS interpreter (requires Playwright). Returns manifest."""
    from playwright.sync_api import sync_playwright

    url = _norm_url(url)
    os.makedirs(out_dir, exist_ok=True)
    shots: List[Dict[str, Any]] = []

    with sync_playwright() as p:
        # R8 SHOPIFY-HARDENING: hardened launch (real Chrome channel + new headless
        # + optional WALK_PROXY) so bot-detection serves the real page, not a
        # degraded shell / challenge.
        browser = _launch_browser(p)
        ctx = browser.new_context(
            viewport=VIEWPORT,
            device_scale_factor=DEVICE_SCALE,
            locale="en-US",
            # US timezone + geolocation so JS-side geo checks agree with the en-US
            # locale (a Taipei timezone against an en-US locale is itself a tell).
            timezone_id="America/New_York",
            geolocation={"latitude": 40.7128, "longitude": -74.0060},
            permissions=["geolocation"],
            user_agent=_DESKTOP_UA,
            extra_http_headers=_EXTRA_HEADERS,
        )
        # Stealth init runs BEFORE every navigation in this context.
        ctx.add_init_script(_STEALTH_INIT_JS)
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
            rec = {
                "index": idx, "file": shot_name, "path": shot_path,
                "url": target_url, "label": label, "title": title,
                "width": VIEWPORT["width"] * DEVICE_SCALE,
                "height": VIEWPORT["height"] * DEVICE_SCALE,
                "bytes": size,
            }
            # READ-PASS copy: pull the visible body text ONCE for the hero shot so
            # the Conversion Read's read_pass can diagnose the real page copy without
            # a second navigation. Best-effort; an unreadable body just leaves "".
            try:
                _btext = (pg.inner_text("body") or "")
            except Exception:
                _btext = ""
            _attach_read_text(rec, title=title, body_text=_btext)
            # Focus rect (Task F): mark a prominent UI element so the archetype's
            # highlight-box / zoom can target it (the headline<->UI tie). Best-
            # effort; a None just degrades to a plain shot with no highlight.
            focus = _compute_focus(pg)
            if focus:
                rec["focus"] = focus
            return rec

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

            # R7 gap 4 — dismiss a geo/shipping/region/cookie interstitial that
            # would occlude the shot (Allbirds' "Where are we shipping to?" modal).
            _dismiss_interstitial(page)

            # Geo-redirect detection: if the final URL contains a non-English
            # locale path segment (/tw/, /zh-tw/, /fr/, …) first PREFER English via a
            # brand-agnostic recovery (strip locale / ?locale=en). When English is
            # genuinely unreachable (server IP-geo-locks every English path back to
            # the locale, e.g. Shopify from a Taiwan egress), KEEP and capture the
            # foreign-language page — a valid foreign page is a SUCCESS, not a
            # failure. Dennis okayed bilingual output (English planner copy over a
            # foreign screenshot); the goal is a COMPLETE video, not English purity.
            # We degrade to empty ONLY on a GENUINE capture failure (bot-wall,
            # blank/error page, nav failure) — handled by the _is_blocked /
            # near-empty checks below — never merely because the page is non-English.
            try:
                final_url = page.url or ""
            except Exception:
                final_url = ""
            if _GEO_LOCALE_RE.search(final_url):
                if not _try_force_english(page, target_url):
                    sys.stderr.write(
                        f"[capture] geo-redirected to non-en locale and English is "
                        f"unreachable (server IP-geo-locked; set WALK_PROXY for an "
                        f"English shot). KEEPING the foreign-language capture — "
                        f"bilingual output is acceptable: {target_url} -> {final_url}\n")
                # Whether we recovered English or kept the foreign page, re-hydrate
                # + re-dismiss any interstitial before shooting the live page.
                _wait_for_spa_hydration(page, settle_ms=1200)
                _dismiss_interstitial(page)

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
                                _dismiss_interstitial(fresh_apex)
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
                        _dismiss_interstitial(fresh)
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

        logo_rec: Optional[Dict[str, str]] = None
        first = grab(url, 1, "home")
        if first:
            # R5 (diagnosis FIX-2) — PREFER A CLEANER SURFACE over a dark, text-heavy
            # marketing hero. The above-the-fold homepage hero on a dark-brand site
            # (Notion's "Meet the night shift", Shopify's dark splash) reads muddy
            # inside the near-white browser card and fights the left headline — the
            # actual 10-pt coherence gap vs Stripe's light captures. When the hero is
            # DARK and the body is content-rich (so a cleaner section exists below the
            # fold), scroll past the hero and reshoot; keep the scrolled view only when
            # it is genuinely LIGHTER (a real cleaner surface), else keep the hero.
            try:
                hero_yavg = _frame_yavg(first.get("path", ""))
            except Exception:
                hero_yavg = None
            if hero_yavg is not None and hero_yavg < _DARK_HERO_YAVG_CEIL:
                try:
                    body_len = len((page.inner_text("body") or "").strip())
                except Exception:
                    body_len = 0
                if body_len > 500 and first.get("path") and os.path.exists(first["path"]):
                    sys.stderr.write(
                        "[capture] dark homepage hero (YAVG=%.1f); scrolling past it "
                        "for a cleaner surface\n" % hero_yavg)
                    # Back up the dark hero (grab(idx=1) overwrites shot-01.png IN
                    # PLACE), reshoot the scrolled view, compare luma. Keep the
                    # scrolled view only when it is meaningfully LIGHTER; else restore
                    # the dark hero from the backup so we never lose the original.
                    hero_path = first["path"]
                    backup = hero_path + ".darkhero.bak"
                    try:
                        import shutil
                        shutil.copy2(hero_path, backup)
                    except Exception:
                        backup = ""
                    cleaner = grab(url, 1, "home", allow_scroll=True)  # overwrites shot-01.png
                    cleaner_yavg = _frame_yavg(cleaner.get("path", "")) if cleaner else None
                    if (cleaner and cleaner_yavg is not None
                            and cleaner_yavg > hero_yavg + 15.0):
                        sys.stderr.write(
                            "[capture] using cleaner scrolled surface "
                            "(YAVG %.1f -> %.1f)\n" % (hero_yavg, cleaner_yavg))
                        first = cleaner  # cleaner["path"] == shot-01.png (overwritten)
                    else:
                        # Scrolled view not meaningfully cleaner — restore the hero.
                        sys.stderr.write(
                            "[capture] scrolled surface not cleaner; keeping hero\n")
                        if backup and os.path.exists(backup):
                            try:
                                import shutil
                                shutil.move(backup, hero_path)
                            except Exception:
                                pass
                    # Clean up any leftover backup.
                    try:
                        if backup and os.path.exists(backup):
                            os.remove(backup)
                    except Exception:
                        pass
            shots.append(first)
            # Logo capture (Task F): the homepage is loaded on `page` now, so pull
            # the brand's REAL logo (inline header <svg> -> icon/og:image) during
            # the same pass. Honest fallback (None) leaves the derived wordmark.
            try:
                logo_rec = _capture_logo(page, ctx, out_dir)
                if logo_rec:
                    sys.stderr.write(
                        "[capture] logo captured (%s): %s\n"
                        % (logo_rec.get("source", "?"), logo_rec.get("path", "")))
                else:
                    sys.stderr.write(
                        "[capture] no logo found; will fall back to wordmark\n")
            except Exception as e:
                sys.stderr.write("[capture] logo capture errored: %s\n" % e)
                logo_rec = None
            if max_shots > 1:
                # discover key routes ONLY after we have a valid homepage (we're on it).
                # Over-fetch candidate routes so a route that renders IDENTICALLY to the
                # homepage (redirect / shell / soft-404) can be skipped for the next one
                # — the two screenshot scenes MUST show different pages.
                extra_routes = _discover_routes(
                    page, url, max_routes=max(max_shots - 1, 0) + 4)
                first_norm = _norm_url(first.get("url") or url).rstrip("/")
                placed = False
                next_idx = len(shots) + 1  # the slot the next distinct shot fills
                for route in extra_routes:
                    rec = grab(route, next_idx, "route")
                    if not rec:
                        continue
                    # DISTINCT-PAGE GUARD: a route that landed on the same final URL
                    # as the homepage (redirect) OR renders a visually identical frame
                    # is a duplicate — discard its shot file and try the next route so
                    # the two screenshot scenes never show the same page.
                    rec_norm = _norm_url(rec.get("url") or route).rstrip("/")
                    if rec_norm == first_norm or not _images_are_distinct(
                            first.get("path", ""), rec.get("path", "")):
                        sys.stderr.write(
                            f"[capture] route duplicates homepage, skipping: {route}\n")
                        try:
                            if rec.get("path") and os.path.exists(rec["path"]):
                                os.remove(rec["path"])
                        except Exception:
                            pass
                        continue
                    shots.append(rec)
                    placed = True
                    next_idx = len(shots) + 1
                    if len(shots) >= max_shots:
                        break
                if not placed:
                    # No DISTINCT inner route found — capture a scrolled-down view of
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
                    rec = grab(url, next_idx, "home-scroll", allow_scroll=True)
                    # Even the scrolled fallback must differ from the above-the-fold
                    # homepage; if the page was too short to scroll (identical frame),
                    # keep it only when it is genuinely distinct. A short homepage that
                    # cannot produce a 2nd distinct view degrades gracefully to a single
                    # shot (the 2nd screenshot scene then shows its never-blank floor).
                    if rec:
                        if _images_are_distinct(first.get("path", ""), rec.get("path", "")):
                            shots.append(rec)
                        else:
                            sys.stderr.write(
                                "[capture] scrolled homepage not distinct from hero; "
                                "keeping a single shot (graceful degrade)\n")
                            try:
                                if rec.get("path") and os.path.exists(rec["path"]):
                                    os.remove(rec["path"])
                            except Exception:
                                pass

        browser.close()

    manifest = {"url": url, "count": len(shots), "shots": shots, "ok": bool(shots)}
    # Logo (Task F): record the captured logo asset so brand_extract can prefer it
    # over the derived wordmark. Absent key => no logo captured (honest fallback).
    if logo_rec:
        manifest["logo"] = logo_rec
    with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)
    return manifest


# ---------------------------------------------------------------------------
# NemoClaw sandbox capture backend (CAPTURE_BACKEND=nemoclaw)
#
# The on-camera NVIDIA flourish: the site is captured by Playwright running
# INSIDE the NemoClaw / OpenShell sandbox (Nemotron, NVIDIA), not on the host.
# This is feature-flagged and ALWAYS falls back to native in-process capture on
# ANY failure — the sandbox is a flourish, never a hard dependency. The exact
# working exec invocations come from walk-studio-hosted/.handoff-nemoclaw.md
# (proven capturing nvidia.com). See that file for the why behind each flag.
#
# Default CAPTURE_BACKEND=native is byte-identical to today's behaviour: none of
# this code runs unless CAPTURE_BACKEND=="nemoclaw" is set explicitly.
# ---------------------------------------------------------------------------

# Sandbox carrying the playwright-cdn + demo-targets policies (handoff §"Use the").
_NEMOCLAW_SANDBOX = os.environ.get("NEMOCLAW_SANDBOX", "walk-ultra")
_NEMOCLAW_BIN = os.environ.get("NEMOCLAW_BIN", "nemoclaw")
# Lower-level OpenShell CLI (the gateway-native binary under nemoclaw). The
# `nemoclaw policy-add` wrapper bumps the policy version but does NOT reprogram
# the LIVE egress proxy; `openshell policy set <sandbox> --policy <file>` (a full
# REPLACE) does. So runtime egress-allowlisting goes through openshell directly.
_NEMOCLAW_OPENSHELL_BIN = os.environ.get("NEMOCLAW_OPENSHELL_BIN", "openshell")
# Egress-allowlist strategy. "policy-set" (default) does the working full-replace
# via openshell; "policy-add" keeps the legacy nemoclaw wrapper (version-only,
# does not reprogram the live proxy on OpenShell 0.0.44); "off" disables runtime
# egress changes (only already-allowed hosts are capturable in-sandbox).
_NEMOCLAW_EGRESS_MODE = os.environ.get("NEMOCLAW_EGRESS_MODE", "policy-set").strip().lower()
# Browser cache dir inside the sandbox (Playwright lands chromium-1223 here).
_NEMOCLAW_BROWSERS_PATH = "/tmp/.cache/ms-playwright"
_NEMOCLAW_CHROMIUM_DIR = _NEMOCLAW_BROWSERS_PATH + "/chromium-1223"
# Sandbox viewport (matches the handoff's proven capture line). The native
# backend uses a 1600x1000@2x retina shot; the sandbox path keeps a 1440x900
# logical viewport (the handoff-verified geometry) but records the SAME
# width/height contract so downstream framing is identical in shape.
_NEMOCLAW_VW, _NEMOCLAW_VH = 1440, 900

# Curated ubiquitous asset hosts allowlisted alongside the target so arbitrary
# customer pages can pull their fonts/CDN assets and render. This is the whole
# security story: we allow the target + these few asset CDNs, NOT open egress.
_NEMOCLAW_ASSET_HOSTS = (
    "fonts.googleapis.com",
    "fonts.gstatic.com",
    "cdnjs.cloudflare.com",
    "cdn.jsdelivr.net",
    "unpkg.com",
    "images.unsplash.com",
)


import re as _nc_re

# nemoclaw status colorizes labels (e.g. "\x1b[2mPhase:\x1b[0m Ready"), so a
# literal "Phase: Ready" substring never matches the raw bytes. Strip ANSI SGR
# sequences before any text match on CLI output.
_ANSI_RE = _nc_re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(s: str) -> str:
    return _ANSI_RE.sub("", s or "")


def _nemoclaw_exec(args: List[str], *, timeout: int) -> subprocess.CompletedProcess:
    """Run a `nemoclaw <sandbox> ...` subcommand. Single mockable seam for all
    sandbox I/O. `args` is the subcommand + its args (sandbox name is prepended).
    Never raises on a non-zero exit — callers inspect returncode/stdout."""
    cmd = [_NEMOCLAW_BIN, _NEMOCLAW_SANDBOX] + list(args)
    return subprocess.run(cmd, capture_output=True, text=True,
                          timeout=timeout, check=False)


def _nemoclaw_exec_sh(one_line: str, *, timeout: int) -> subprocess.CompletedProcess:
    """Run a shell pipeline inside the sandbox. NemoClaw `exec` execs argv
    directly (no shell), so shell pipelines MUST be wrapped in `bash -lc`
    (handoff's load-bearing correction). `one_line` must be a single line."""
    return _nemoclaw_exec(
        ["exec", "--timeout", str(timeout), "--", "bash", "-lc", one_line],
        timeout=timeout + 30,
    )


def _openshell_exec(args: List[str], *, timeout: int) -> subprocess.CompletedProcess:
    """Run an `openshell <args>` command (gateway resolved from stored metadata).
    Single mockable seam for all OpenShell policy I/O. The sandbox NAME is passed
    by callers as a positional arg where the subcommand expects it. Never raises
    on non-zero exit — callers inspect returncode/stdout/stderr."""
    cmd = [_NEMOCLAW_OPENSHELL_BIN] + list(args)
    return subprocess.run(cmd, capture_output=True, text=True,
                          timeout=timeout, check=False)


def _host_apex(host: str) -> Optional[str]:
    """Best-effort apex (last two labels) of a host, or None if host is an apex
    already / a bare label. `app.notion.so` -> `notion.so`; `notion.so` -> None."""
    if not host:
        return None
    labels = host.split(".")
    if len(labels) <= 2:
        return None
    return ".".join(labels[-2:])


def _nemoclaw_policy_yaml(host: str) -> str:
    """Build a minimal policy-preset YAML allowing ONLY `host` (+ its apex +
    a `*.apex` wildcard so subdomain assets resolve) plus the curated asset
    CDNs. Each host is an `access: full` endpoint WITHOUT `tls: skip` — exactly
    the shape the working `demo-targets` preset uses (the proxy TLS-terminates,
    which is why the capture launches Chromium with `--ignore-certificate-errors`
    + `ignore_https_errors=True`). The `tls: skip` raw-tunnel shape was rejected
    by the live proxy as "Policy unchanged"; this shape loads as a new policy
    version. This is NOT open egress: only the target + curated assets are listed.

    Pure string builder so it is unit-testable without a sandbox."""
    host = (host or "").strip().lower()
    seen: List[str] = []

    def _add(h: str) -> None:
        h = (h or "").strip().lower()
        if h and h not in seen:
            seen.append(h)

    _add(host)
    apex = _host_apex(host)
    if apex:
        _add(apex)
        _add("*." + apex)
    for h in _NEMOCLAW_ASSET_HOSTS:
        _add(h)

    lines = [
        "preset:",
        "  name: demo-dynamic",
        '  description: "Walk Studio per-job dynamic capture target + curated asset CDNs"',
        "network_policies:",
        "  demo_dynamic:",
        "    name: demo_dynamic",
        "    endpoints:",
    ]
    for h in seen:
        lines.append('      - host: "%s"' % h)
        lines.append("        port: 443")
        lines.append("        access: full")
    return "\n".join(lines) + "\n"


# Marker for the demo-targets preset's endpoints list inside the live policy
# YAML. The live policy is emitted with 2-space indent per level (preset key at
# 2 spaces, its fields at 4, list items at 4 + "- "), matching `policy get
# --full` output. We inject new endpoints immediately AFTER this line.
_DEMO_TARGETS_ENDPOINTS_MARKER = (
    "  demo-targets:\n    name: demo-targets\n    endpoints:\n")


def _nemoclaw_inject_hosts(policy_yaml: str, hosts: List[str]) -> str:
    """Return `policy_yaml` with each host in `hosts` added to the `demo-targets`
    preset's endpoints (the proven working shape: `access: full`, NO `tls: skip`
    — the live egress proxy only honours that preset's full-terminate entries
    after a `policy set` full-replace). Hosts already present are skipped (no
    duplicates). Pure string transform so it is unit-testable without a sandbox.

    Raises ValueError if the policy has no demo-targets endpoints block (so the
    caller fails closed to native rather than applying a broken replace)."""
    start = policy_yaml.find(_DEMO_TARGETS_ENDPOINTS_MARKER)
    if start < 0:
        raise ValueError("live policy has no demo-targets endpoints block")
    # The demo-targets endpoints span from the marker up to the next sibling key
    # ("  <name>:\n", a preset at the same 2-space indent) — typically the next
    # preset or this preset's own "binaries:" / "name:". We only dedup within
    # this block: hosts present in OTHER presets (e.g. demo_dynamic) do NOT count
    # as honoured, because the live proxy only enforces demo-targets after a
    # `policy set` full-replace. So a host in demo_dynamic alone must still be
    # injected here.
    block_start = start + len(_DEMO_TARGETS_ENDPOINTS_MARKER)
    rest = policy_yaml[block_start:]
    # Next sibling key at 2-space indent ("  word:") ends the demo-targets block.
    m = _nc_re.search(r"\n  \S[^\n]*:\n", rest)
    block_end = block_start + (m.start() + 1 if m else len(rest))
    demo_block = policy_yaml[block_start:block_end]

    new_entries: List[str] = []
    queued: set = set()
    for raw in hosts:
        h = (raw or "").strip().lower()
        if not h or h in queued:
            continue
        # Skip only if already an endpoint WITHIN demo-targets (quoted or not).
        if ("host: %s\n" % h) in demo_block or ("host: '%s'\n" % h) in demo_block \
                or ('host: "%s"\n' % h) in demo_block:
            continue
        # ALWAYS single-quote the host value. A bare value starting with '*'
        # (the *.apex wildcard) is otherwise parsed as a YAML alias and rejected
        # ("did not find expected alphabetic or numeric character ... alias").
        # Quoting matches how `policy get --full` itself emits special hosts.
        new_entries.append(
            "    - host: '%s'\n      port: 443\n      access: full\n" % h)
        queued.add(h)
    if not new_entries:
        return policy_yaml
    return (policy_yaml[:block_start] + "".join(new_entries)
            + policy_yaml[block_start:])


def _nemoclaw_host_allowed(host: str, *, timeout: int = 60) -> bool:
    """True if `host` (or its apex) is already reachable from the sandbox: a
    cheap DNS/connect probe via curl. A reachable host needs no policy change.
    Conservative: any probe failure returns False (we then add the policy)."""
    host = (host or "").strip().lower()
    if not host:
        return False
    # -I head request; --max-time bounds it. Exit 0 means the egress proxy let
    # the CONNECT through (even a 4xx/5xx HTTP status is exit 0 for curl -I).
    probe = ("curl -sS -o /dev/null --max-time 12 -I "
             "'https://%s/' && echo NC_HOST_OK" % host.replace("'", ""))
    try:
        r = _nemoclaw_exec_sh(probe, timeout=timeout)
    except Exception:
        return False
    return r.returncode == 0 and "NC_HOST_OK" in (r.stdout or "")


def _nemoclaw_allowlist_hosts_for(host, *extra_hosts) -> List[str]:
    """The set of hosts to allowlist for a capture of `host` (plus any
    `extra_hosts`, e.g. cross-domain redirect targets — FIX 2): each seed host,
    its apex, a `*.apex` subdomain wildcard, plus the curated asset CDNs. Mirrors
    the security story of _nemoclaw_policy_yaml — targets + curated assets, NOT
    open egress.

    `host` may be a single host string; `extra_hosts` are additional host
    strings (each expanded to apex + *.apex the same way)."""
    out: List[str] = []

    def _add(h: str) -> None:
        h = (h or "").strip().lower()
        if h and h not in out:
            out.append(h)

    seeds: List[str] = [host]
    seeds.extend(extra_hosts)
    for seed in seeds:
        seed = (seed or "").strip().lower()
        if not seed:
            continue
        _add(seed)
        apex = _host_apex(seed)
        if apex:
            _add(apex)
            _add("*." + apex)
    for h in _NEMOCLAW_ASSET_HOSTS:
        _add(h)
    return out


def _nemoclaw_resolve_exec(argv: List[str], *, timeout: int) -> subprocess.CompletedProcess:
    """Run a command on the LOCAL host (where this orchestrator runs), NOT inside
    the sandbox. The host has unrestricted egress, so it can follow an arbitrary
    URL's redirect chain to discover every domain the page touches. Single
    mockable seam for the FIX-2 redirect probe. Never raises on non-zero exit."""
    return subprocess.run(argv, capture_output=True, text=True,
                          timeout=timeout, check=False)


# A realistic desktop-browser UA so sites that branch on UA (and redirect
# bots elsewhere) return the SAME redirect chain a real Chromium capture hits.
_NEMOCLAW_RESOLVE_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


# Sentinel curl prints (via -w) the FINAL effective URL after following the
# whole chain. We GET (not HEAD): notion's cross-apex hop (www.notion.so ->
# www.notion.com) fires only on GET — a HEAD returns 200 and hides it.
_NC_EFFECTIVE_MARK = "__NC_EFFECTIVE_URL__"


def _nemoclaw_redirect_chain_hosts(url: str, *, timeout: int = 25) -> List[str]:
    """FIX 2: resolve `url`'s top-level redirect chain FROM THE HOST (which has no
    egress restriction) and return EVERY host in that chain — the final effective
    URL's host plus every intermediate `Location:` host. This catches cross-apex
    redirects (e.g. notion.so 30x -> www.notion.com) that the sandbox's allowlist
    would otherwise miss, killing Playwright with ERR_TUNNEL_CONNECTION_FAILED.

    Runs a GET with `-L` (follow the FULL chain a real navigation hits), dumping
    each response's headers (`-D -`) and the final effective URL (`-w`), with a
    realistic desktop UA and `--max-time`. Parses the host out of the original
    URL, every `Location:` header (absolute or relative), AND the effective URL.
    We GET rather than HEAD because some sites (notion) only emit the cross-apex
    301 on GET — HEAD returns 200 and hides the hop. On ANY failure/timeout,
    returns just the original URL's host so the caller never blocks the capture
    (best-effort widening, never a gate)."""
    orig_host = (urlparse(url).hostname or "").strip().lower()
    fallback = [orig_host] if orig_host else []
    if not orig_host:
        return fallback
    # GET, discard body, dump headers to stdout, print final effective URL.
    argv = ["curl", "-sL", "-o", os.devnull, "-D", "-",
            "--max-time", str(int(timeout)), "-A", _NEMOCLAW_RESOLVE_UA,
            "-w", "\n%s %%{url_effective}\n" % _NC_EFFECTIVE_MARK, url]
    try:
        r = _nemoclaw_resolve_exec(argv, timeout=timeout + 10)
    except Exception as e:
        sys.stderr.write("[capture/nemoclaw] redirect resolve raised: %s\n" % e)
        return fallback
    if r.returncode != 0:
        sys.stderr.write(
            "[capture/nemoclaw] redirect resolve failed (rc=%s); using original "
            "host only.\n" % r.returncode)
        return fallback
    out: List[str] = []

    def _add(h: str) -> None:
        h = (h or "").strip().lower()
        if h and h not in out:
            out.append(h)

    _add(orig_host)
    # Parse every Location: header in the -L chain (curl prints each response's
    # headers in order) plus the final effective URL from the -w sentinel.
    current = url
    for line in (r.stdout or "").splitlines():
        s = line.strip()
        if s.startswith(_NC_EFFECTIVE_MARK):
            eff = s[len(_NC_EFFECTIVE_MARK):].strip()
            h = (urlparse(eff).hostname or "").strip().lower()
            if h:
                _add(h)
            continue
        if not s.lower().startswith("location:"):
            continue
        loc = s.split(":", 1)[1].strip()
        if not loc:
            continue
        # Location may be absolute (https://notion.com/...) or relative (/x).
        # urljoin against the current URL resolves both; only a scheme/host
        # change yields a new host to allowlist.
        try:
            nxt = urljoin(current, loc)
        except Exception:
            continue
        h = (urlparse(nxt).hostname or "").strip().lower()
        if h:
            _add(h)
        current = nxt
    return out


def _nemoclaw_policy_set_egress(host: str, *, url: Optional[str] = None,
                                timeout: int = 120) -> bool:
    """Reprogram the LIVE sandbox egress proxy to allow `host` (+ apex + curated
    assets), via the OpenShell-native FULL-REPLACE path:

        openshell policy get --full <sandbox>     (capture the live policy)
        -> inject the hosts into the demo-targets preset (proven shape)
        -> openshell policy set <sandbox> --policy <edited.yaml> --wait

    Unlike `nemoclaw policy-add` / `openshell policy update` (which only bump the
    policy VERSION but leave the running CONNECT proxy unchanged on OpenShell
    0.0.44), a `policy set` full-replace actually reprograms the live egress
    proxy — verified: a non-allowlisted host goes 000 -> 200 after this call.

    FIX 2: when `url` is given, the URL's full redirect chain is resolved from the
    host FIRST and EVERY host in the chain (+ each one's apex + *.apex) is
    allowlisted alongside the original host — so cross-apex top-level redirects
    (notion.so -> notion.com) don't die with ERR_TUNNEL_CONNECTION_FAILED. If the
    resolve fails/times out we fall back to the original host only.

    Returns True ONLY if the post-apply curl re-probe shows egress actually
    opened. PRESERVES the security story: only the target + redirect-chain +
    curated asset hosts are merged into demo-targets, never open egress; every
    other preset and the full policy body are preserved byte-for-byte from the
    live `get --full`."""
    # 0. Resolve the redirect chain FROM THE HOST (no egress restriction) so
    #    every domain the top-level navigation touches is allowlisted (FIX 2).
    if url:
        chain_hosts = _nemoclaw_redirect_chain_hosts(url)
    else:
        chain_hosts = [host]
    seed_hosts = _nemoclaw_allowlist_hosts_for(host, *chain_hosts)
    # 1. Capture the LIVE policy (must preserve the version + every preset;
    #    `policy set` REPLACES, so we round-trip the exact live document).
    try:
        g = _openshell_exec(
            ["policy", "get", "--full", _NEMOCLAW_SANDBOX], timeout=timeout)
    except Exception as e:
        sys.stderr.write("[capture/nemoclaw] openshell policy get raised: %s\n" % e)
        return False
    if g.returncode != 0:
        sys.stderr.write(
            "[capture/nemoclaw] openshell policy get failed (rc=%s): %s\n"
            % (g.returncode, (g.stderr or g.stdout or "")[-400:]))
        return False
    # `policy get --full` prints a header block then `---` then the YAML body.
    raw = g.stdout or ""
    body = raw.split("\n---\n", 1)[1] if "\n---\n" in raw else raw
    # 2. Inject the target + redirect-chain + curated asset hosts into demo-targets.
    try:
        edited = _nemoclaw_inject_hosts(body, seed_hosts)
    except ValueError as e:
        sys.stderr.write("[capture/nemoclaw] policy inject failed: %s\n" % e)
        return False
    # 3. Apply via full-replace and wait for the gateway to load it.
    import tempfile
    fd, path = tempfile.mkstemp(suffix=".yaml", prefix="nemoclaw-livepolicy-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(edited)
        try:
            r = _openshell_exec(
                ["policy", "set", _NEMOCLAW_SANDBOX, "--policy", path,
                 "--wait", "--timeout", "50"], timeout=timeout)
        except Exception as e:
            sys.stderr.write("[capture/nemoclaw] openshell policy set raised: %s\n" % e)
            return False
        if r.returncode != 0:
            sys.stderr.write(
                "[capture/nemoclaw] openshell policy set failed (rc=%s): %s\n"
                % (r.returncode, (r.stderr or r.stdout or "")[-400:]))
            return False
        # 4. Re-probe: only claim success when the egress tunnel actually opens.
        return _nemoclaw_host_allowed(host)
    finally:
        try:
            os.remove(path)
        except Exception:
            pass


def _nemoclaw_policy_add_egress(host: str, *, timeout: int = 120) -> bool:
    """LEGACY egress path (NEMOCLAW_EGRESS_MODE=policy-add). Writes a minimal
    preset and applies it via `nemoclaw policy-add --from-file --yes`. KNOWN to
    bump the policy version WITHOUT reprogramming the live CONNECT proxy on
    OpenShell 0.0.44 — kept only for parity/diagnostics. The re-probe gate makes
    it fail closed (returns False) on that build, so preflight falls back to
    native. Prefer `policy-set` (the default), which actually reprograms egress."""
    yaml_doc = _nemoclaw_policy_yaml(host)
    import tempfile
    fd, path = tempfile.mkstemp(suffix=".yaml", prefix="nemoclaw-policy-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(yaml_doc)
        try:
            r = _nemoclaw_exec(["policy-add", "--from-file", path, "--yes"],
                               timeout=timeout)
        except Exception as e:
            sys.stderr.write("[capture/nemoclaw] policy-add raised: %s\n" % e)
            return False
        if r.returncode != 0:
            sys.stderr.write(
                "[capture/nemoclaw] policy-add failed (rc=%s): %s\n"
                % (r.returncode, (r.stderr or r.stdout or "")[-400:]))
            return False
        return _nemoclaw_host_allowed(host)
    finally:
        try:
            os.remove(path)
        except Exception:
            pass


def _nemoclaw_allow_host(host: str, *, url: Optional[str] = None,
                         timeout: int = 120) -> bool:
    """Dynamic egress-allowlisting: ensure `host` is reachable from the sandbox.

    If `host` is already reachable, no policy change is made. Otherwise, depending
    on NEMOCLAW_EGRESS_MODE:
      - "policy-set" (default): reprogram the LIVE egress proxy via
        `openshell policy get --full` -> inject host (+ FIX-2 redirect chain when
        `url` is given) into demo-targets -> `openshell policy set --wait`. This
        is the path that ACTUALLY opens egress for an arbitrary customer URL at
        runtime (verified 000 -> 200).
      - "policy-add": legacy `nemoclaw policy-add` (version-only on 0.0.44; fails
        closed via the re-probe).
      - "off": no runtime policy change (only pre-allowlisted hosts capturable).

    Returns True ONLY when a real curl reachability re-probe confirms the egress
    CONNECT tunnel for `host` is open. PRESERVES the security story: only the
    target + redirect chain + apex + curated asset CDNs are allowlisted, never
    open egress."""
    host = (host or "").strip().lower()
    if not host:
        return False
    if _nemoclaw_host_allowed(host):
        return True
    # Read the mode at call time so it is runtime-overridable (and testable).
    mode = (os.environ.get("NEMOCLAW_EGRESS_MODE", _NEMOCLAW_EGRESS_MODE)
            or "").strip().lower()
    if mode == "off":
        sys.stderr.write(
            "[capture/nemoclaw] NEMOCLAW_EGRESS_MODE=off; host %r not "
            "pre-allowlisted -> native fallback.\n" % host)
        return False
    if mode == "policy-add":
        return _nemoclaw_policy_add_egress(host, timeout=timeout)
    # default + any unknown value: the working full-replace path.
    return _nemoclaw_policy_set_egress(host, url=url, timeout=timeout)


def _nemoclaw_install_chromium() -> bool:
    """One-time (per sandbox lifetime) Chromium install per the handoff steps
    1-2: venv Playwright, then Playwright 1.60.0 via npm into the policy-
    allowlisted /sandbox/explainer-agent, then `playwright install chromium`.
    Returns True if chromium-1223 exists afterwards."""
    sys.stderr.write("[capture/nemoclaw] installing Playwright + Chromium "
                     "in sandbox (one-time)...\n")
    steps = [
        ("python3 -m venv /sandbox/.venv; /sandbox/.venv/bin/pip install "
         "--quiet --upgrade pip; /sandbox/.venv/bin/pip install playwright", 300),
        ("cd /sandbox/explainer-agent && npm install --no-save "
         "playwright@1.60.0 playwright-core@1.60.0", 300),
        ("cd /sandbox/explainer-agent && ./node_modules/.bin/playwright "
         "install chromium", 560),
    ]
    for one_line, t in steps:
        try:
            r = _nemoclaw_exec_sh(one_line, timeout=t)
        except Exception as e:
            sys.stderr.write("[capture/nemoclaw] install step raised: %s\n" % e)
            return False
        if r.returncode != 0:
            sys.stderr.write(
                "[capture/nemoclaw] install step failed (rc=%s): %s\n"
                % (r.returncode, (r.stderr or r.stdout or "")[-400:]))
            return False
    return _nemoclaw_chromium_ready()


def _nemoclaw_chromium_ready(*, timeout: int = 60) -> bool:
    """Reachability one-shot: chromium-1223 present in the sandbox cache."""
    try:
        r = _nemoclaw_exec_sh("ls %s && echo NC_BROWSER_OK" % _NEMOCLAW_CHROMIUM_DIR,
                              timeout=timeout)
    except Exception:
        return False
    return r.returncode == 0 and "NC_BROWSER_OK" in (r.stdout or "")


def _nemoclaw_status_ready(*, timeout: int = 90) -> bool:
    """True iff `nemoclaw <sandbox> status` reports the gateway healthy AND
    `Phase: Ready`. The single gate used to decide whether the expensive
    `recover` step is even needed (FIX 1: skip recover when already healthy).
    Conservative: any error/odd status => False (the caller then recovers)."""
    try:
        st = _nemoclaw_exec(["status"], timeout=timeout)
    except Exception as e:
        sys.stderr.write("[capture/nemoclaw] status raised: %s\n" % e)
        return False
    status_out = _strip_ansi((st.stdout or "") + (st.stderr or ""))
    return "Phase: Ready" in status_out


def _nemoclaw_preflight(host: str, url: Optional[str] = None) -> bool:
    """Preflight per the handoff: status healthy + Phase: Ready (recover ONLY if
    not healthy) -> chromium present (install once if missing) -> dynamic-
    allowlist the target host (+ FIX-2 redirect chain when `url` is given).
    Returns True only if every step passes. Any failure => False so capture_url
    falls back to native.

    FIX 1 (snappiness): the previous order ran `recover` UNCONDITIONALLY first,
    which hangs ~180s on an already-healthy gateway and stalled the first cold
    capture ~3 minutes. Now status is checked FIRST; `recover` runs ONLY when the
    gateway is not already healthy / not Ready. A warm gateway skips recover
    entirely, so the cold capture is fast."""
    # 1. status FIRST: if already healthy + Ready, SKIP recover (the slow path).
    if not _nemoclaw_status_ready():
        # Not healthy — recover (idempotent; takes NO --timeout flag) brings the
        # gateway up after a Docker restart. A non-zero exit here is non-fatal;
        # the post-recover status re-check is the real gate.
        try:
            _nemoclaw_exec(["recover"], timeout=180)
        except Exception as e:
            sys.stderr.write("[capture/nemoclaw] recover raised: %s\n" % e)
            # fall through — status is the real gate.
        # 2. re-check status: require gateway healthy AND Phase: Ready.
        if not _nemoclaw_status_ready():
            sys.stderr.write(
                "[capture/nemoclaw] sandbox not Ready after recover; "
                "falling back to native.\n")
            return False
    # 3. chromium reachability one-shot; install once if missing.
    if not _nemoclaw_chromium_ready():
        if not _nemoclaw_install_chromium():
            sys.stderr.write(
                "[capture/nemoclaw] Chromium unavailable and install failed; "
                "falling back to native.\n")
            return False
    # 4. dynamic egress-allowlist the target host + its redirect chain (TASK 2).
    if not _nemoclaw_allow_host(host, url=url):
        sys.stderr.write(
            "[capture/nemoclaw] could not allowlist host %r; "
            "falling back to native.\n" % host)
        return False
    return True


# Sentinels the capture exec prints so we can parse status/title/body out of
# stdout deterministically.
_NC_OK = "CAPTURE_OK"
_NC_BODY_BEGIN = "NC_BODY_BEGIN"
_NC_BODY_END = "NC_BODY_END"


def _nemoclaw_capture_python(url: str, shot_path: str) -> str:
    """Build the single-line python -c body run inside the sandbox venv. Matches
    the handoff's proven step-3 capture line (cert + netlink flags), and ALSO
    base64-prints the page's inner_text('body') between sentinels so the
    Conversion Read gets real page copy without a second navigation."""
    # JSON-encode literals so quoting is safe inside the nested python source.
    url_lit = json.dumps(url)
    shot_lit = json.dumps(shot_path)
    # A real multi-line python script (NOT semicolon-joined) so the try/except
    # for body-text extraction is valid. _shquote wraps the whole thing for the
    # outer `bash -lc`. Body text is base64'd between sentinels so it survives
    # newlines/quotes through stdout.
    lines = [
        "import base64",
        "from playwright.sync_api import sync_playwright",
        "p = sync_playwright().start()",
        "b = p.chromium.launch(args=['--ignore-certificate-errors', "
        "'--enable-features=NetworkService,NetworkServiceInProcess'])",
        "ctx = b.new_context(viewport={'width': %d, 'height': %d}, "
        "ignore_https_errors=True)" % (_NEMOCLAW_VW, _NEMOCLAW_VH),
        "pg = ctx.new_page()",
        "r = pg.goto(%s, wait_until='domcontentloaded', timeout=60000)" % url_lit,
        "print('STATUS', r.status if r else 'NONE', 'TITLE', repr(pg.title()))",
        "pg.wait_for_timeout(3500)",
        "pg.screenshot(path=%s, full_page=False)" % shot_lit,
        "bt = ''",
        "try:",
        "    bt = pg.inner_text('body') or ''",
        "except Exception:",
        "    bt = ''",
        "print('%s' + base64.b64encode(bt[:4000].encode('utf-8', 'replace'))"
        ".decode() + '%s')" % (_NC_BODY_BEGIN, _NC_BODY_END),
        "b.close()",
        "p.stop()",
        "print('%s')" % _NC_OK,
    ]
    return "\n".join(lines)


def _nemoclaw_capture_command(url: str, shot_path: str) -> str:
    """Build the NEWLINE-FREE single-line bash command run inside the sandbox.

    NemoClaw's gRPC `exec` rejects any argv element containing a newline/CR. The
    capture python source is naturally multi-line (a try/except for body text),
    so we base64-encode it and run `python -c "import base64;exec(...)"` — the
    b64 blob carries no newlines, so the whole `bash -lc` argument is one line.
    PLAYWRIGHT_BROWSERS_PATH points the venv Playwright at the shared browser
    cache (handoff step 3)."""
    import base64 as _b64
    src = _nemoclaw_capture_python(url, shot_path)
    b64 = _b64.b64encode(src.encode("utf-8")).decode("ascii")
    return (
        "export PLAYWRIGHT_BROWSERS_PATH=%s; "
        "/sandbox/.venv/bin/python -c "
        "'import base64;exec(base64.b64decode(\"%s\").decode())'"
        % (_NEMOCLAW_BROWSERS_PATH, b64)
    )


def _nemoclaw_pull_png(sandbox_path: str, dest_path: str, *, timeout: int = 90) -> bool:
    """Base64-pull a PNG out of the sandbox to `dest_path` on the host (handoff
    step 4 — the reliable path; no share mount). Returns True if a non-trivial
    file lands on disk."""
    try:
        r = _nemoclaw_exec_sh("base64 %s" % json.dumps(sandbox_path), timeout=timeout)
    except Exception as e:
        sys.stderr.write("[capture/nemoclaw] base64 pull raised: %s\n" % e)
        return False
    if r.returncode != 0 or not (r.stdout or "").strip():
        sys.stderr.write(
            "[capture/nemoclaw] base64 pull failed (rc=%s)\n" % r.returncode)
        return False
    import base64 as _b64
    try:
        raw = _b64.b64decode("".join((r.stdout or "").split()))
    except Exception as e:
        sys.stderr.write("[capture/nemoclaw] base64 decode failed: %s\n" % e)
        return False
    if len(raw) < 3000 or raw[:8] != b"\x89PNG\r\n\x1a\n":
        sys.stderr.write("[capture/nemoclaw] pulled bytes are not a PNG "
                         "(%d bytes)\n" % len(raw))
        return False
    with open(dest_path, "wb") as fh:
        fh.write(raw)
    return True


def _capture_via_nemoclaw(url: str, out_dir: str,
                          max_shots: int) -> Optional[Dict[str, Any]]:
    """Capture `url` with Playwright running INSIDE the NemoClaw sandbox.

    Returns a manifest dict with the SAME shape as _capture_inproc (so the
    Conversion Read + render are identical), or None on ANY failure (caller then
    falls back to native). Best-effort, never raises: the sandbox is the
    on-camera flourish, not a hard dependency.

    Captures the homepage only (max 1 shot). The native backend's multi-route /
    scrolled-2nd-shot logic stays host-side; for the sandbox flourish a single
    real hero shot + real body_text is the contract that matters downstream.
    """
    url = _norm_url(url)
    os.makedirs(out_dir, exist_ok=True)
    host = (urlparse(url).hostname or "").lower()
    if not host:
        return None

    if not _nemoclaw_preflight(host, url):
        return None

    sandbox_png = "/tmp/cap-01.png"
    one_line = _nemoclaw_capture_command(url, sandbox_png)
    try:
        r = _nemoclaw_exec_sh(one_line, timeout=180)
    except Exception as e:
        sys.stderr.write("[capture/nemoclaw] capture exec raised: %s\n" % e)
        return None
    out = (r.stdout or "")
    if _NC_OK not in out:
        sys.stderr.write(
            "[capture/nemoclaw] capture did not print CAPTURE_OK (rc=%s): %s\n"
            % (r.returncode, (r.stderr or out or "")[-400:]))
        return None

    # Pull the PNG back to out_dir/shot-01.png and validate it.
    shot_name = "shot-01.png"
    shot_path = os.path.join(out_dir, shot_name)
    if not _nemoclaw_pull_png(sandbox_png, shot_path):
        return None
    if _is_near_empty_png(shot_path):
        sys.stderr.write("[capture/nemoclaw] pulled PNG is near-empty; "
                         "falling back to native.\n")
        try:
            os.remove(shot_path)
        except Exception:
            pass
        return None

    # Parse STATUS/TITLE + the base64 body text out of stdout.
    title = ""
    for line in out.splitlines():
        if line.startswith("STATUS ") and "TITLE " in line:
            try:
                title = eval(line.split("TITLE ", 1)[1].strip())  # repr() literal
            except Exception:
                title = ""
            break
    body_text = ""
    if _NC_BODY_BEGIN in out and _NC_BODY_END in out:
        try:
            enc = out.split(_NC_BODY_BEGIN, 1)[1].split(_NC_BODY_END, 1)[0]
            import base64 as _b64
            body_text = _b64.b64decode(enc.strip().encode()).decode("utf-8", "replace")
        except Exception:
            body_text = ""

    size = os.path.getsize(shot_path)
    rec: Dict[str, Any] = {
        "index": 1, "file": shot_name, "path": shot_path,
        "url": url, "label": "home", "title": title or "",
        "width": _NEMOCLAW_VW, "height": _NEMOCLAW_VH,
        "bytes": size,
        "backend": "nemoclaw",
    }
    _attach_read_text(rec, title=title, body_text=body_text)

    manifest = {"url": url, "count": 1, "shots": [rec], "ok": True,
                "backend": "nemoclaw"}
    with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)
    return manifest


def _shquote(s: str) -> str:
    """Minimal single-quote shell quoting for embedding a python -c body inside
    the outer `bash -lc '<one line>'` exec. Wraps in single quotes and escapes
    embedded single quotes the POSIX way ('\\'')."""
    return "'" + s.replace("'", "'\\''") + "'"


def _attach_read_text(rec, title="", body_text=""):
    """Attach the read-pass fields (title already on rec; body_text capped at 4000)
    to a shot record. Pure + idempotent; used by the hero shot so read_pass.read_pass
    can pull the page copy from the manifest without a second navigation."""
    if title and not rec.get("title"):
        rec["title"] = title
    rec["body_text"] = (body_text or "")[:4000]
    return rec


def capture_url(url: str, out_dir: str, max_shots: int = 2) -> Dict[str, Any]:
    """In-process capture API. Re-execs into `.venv-capture` if Playwright is not
    importable in the current interpreter, then reads the manifest back.

    Returns the manifest dict: {"url","count","shots":[{file,path,url,label,...}],"ok"}.
    Raises RuntimeError if no capture path is available or capture produced nothing.
    """
    url = _norm_url(url)
    os.makedirs(out_dir, exist_ok=True)

    # CAPTURE_BACKEND switch (feature-flagged; default "native" is byte-identical
    # to today's behaviour). Only when explicitly set to "nemoclaw" do we attempt
    # the sandbox flourish; if the preflight or capture fails for ANY reason it
    # returns None and we fall through to the unchanged native path. The sandbox
    # is the on-camera NVIDIA flourish, NEVER a hard dependency.
    if os.environ.get("CAPTURE_BACKEND") == "nemoclaw":
        nc = _capture_via_nemoclaw(url, out_dir, max_shots)
        if nc is not None:
            return nc
        sys.stderr.write(
            "[capture] CAPTURE_BACKEND=nemoclaw preflight/capture failed; "
            "falling back to native capture.\n")

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
