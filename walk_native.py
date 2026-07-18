#!/usr/bin/env python3
"""Native Python Playwright walkthrough capture for Walk Studio.

Phase 2 of "incorporate the walk-agent natively": SMART, GOAL-DIRECTED NAVIGATION.
Replaces the Phase-1 scripted scroll-through with a perceive -> propose -> execute
step loop ported from the original walk-ultra explainer-agent. The walk-agent now
intelligently NAVIGATES to the emphasized feature — it CLICKS the right nav link /
button to reach it (e.g. clicks "Pricing" to land on the pricing page) — instead of
blindly scrolling the homepage. (Phase 1 also fixed the deadlock: the old real-mode
path shelled walk-ultra/tutorial-maker.sh into a NemoClaw sandbox and blocked forever
on a gateway pipe. This module is a STANDALONE subprocess — no NemoClaw, no sandbox —
so it cannot inherit that pipe and cannot deadlock the parent.)

WHAT IT DOES
  1. Launch Chromium via Playwright (reusing capture_screenshots' launch args,
     en-US locale, desktop UA, realistic headers, and the SPA hydration gate).
  2. Start a CDP screencast and, on every Page.screencastFrame event:
       - atomically write the JPEG to  <run_dir>/walk/frame.jpg   (LIVE preview)
       - also save it to               <run_dir>/walk/frames/fNNNNN.jpg
       - ack the frame so the stream keeps flowing.
     The screencast runs THROUGHOUT the smart-nav loop, so every click/scroll/nav
     lands as live frames.
  3. SMART NAV (perceive -> propose -> execute), capped at MAX_STEPS / the
     wall-clock alarm:
       PERCEIVE — gather the visible clickables (nav links, buttons, CTAs) +
         page text + scroll metrics via Playwright (ported gatherClickables).
       PROPOSE  — ask Nemotron (via brain.py / OpenRouter) for the next action:
         click <ref> / scroll / done. Uses the ported walk-ultra proposer prompt
         (goal-directed nav, keyword-anchor preference). Model via WS_WALK_BRAIN
         env (DEFAULT super-free = free 120B, $0; ultra-paid = 550B for the real
         deliverable).
       EXECUTE  — click the ref's element (scroll into view -> mouse-click center)
         or scroll, then wait for nav + the hydration/settle gate.
     Each step writes <run_dir>/walk/state.json = {"url","step","action","ts"}
     (atomically). Loops until Nemotron says `done` or max-steps / timeout.
     If smart-nav errors as a whole, it FALLS BACK to the Phase-1 scroll-through.
  4. Stitch <run_dir>/walk/frames/*.jpg -> <out_path> via ffmpeg
     (H.264, yuv420p, even dims, ~12-15fps).

NON-FATAL by construction: the whole run is wrapped in try/except plus an overall
wall-clock alarm. A bad/empty/garbled Nemotron response degrades to a scroll step;
a whole-smart-nav failure degrades to the Phase-1 scroll-through. On ANY hard
failure it prints `WALK_NATIVE: failed <reason>`, writes state.json action="failed",
and exits 1 — it never hangs and never raises an uncaught exception. The
browser/context are always closed in `finally`.

CLI
    <.venv-capture python> walk_native.py <url> <goal> <emphasis> \
        <out_path> <run_dir> [duration]

Env
    WS_WALK_BRAIN  super-free (default, $0 free 120B) | ultra-paid (550B) |
                   super-paid. Falls back to super-free for unknown values.
    OPENROUTER_API_KEY  required for smart nav; if unset, smart nav is skipped
                   and the Phase-1 scroll-through runs (graceful degradation).

Exit codes
    0  -> a valid mp4 was written to <out_path>      (prints WALK_NATIVE: ok ...)
    1  -> graceful failure / skip                    (prints WALK_NATIVE: failed ...)
"""
from __future__ import annotations

import base64
import glob
import json
import os
import re
import signal
import subprocess
import sys
import time
import traceback
import urllib.request
import urllib.error

# Brain registry (single source of truth for the Nemotron planner brain). Reused
# here for the smart-nav PROPOSER call: same OpenRouter endpoint + model slugs +
# OPENROUTER_API_KEY, just a different (navigation) prompt. Import is best-effort
# so the module still loads (and degrades to Phase-1) if brain.py is ever absent.
try:
    import brain as _brain  # type: ignore
except Exception:  # pragma: no cover - brain.py ships alongside this file
    _brain = None

# ---------------------------------------------------------------------------
# Launch config — mirrored from capture_screenshots.py so the two Playwright
# entry points behave identically (same UA, locale, headers, hydration gate).
# ---------------------------------------------------------------------------
VIEWPORT = {"width": 1280, "height": 800}  # matches the screencast maxWidth/maxHeight

_DESKTOP_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.6367.82 Safari/537.36"
)

_EXTRA_HEADERS = {
    # R5 (Shopify bug #5) — pin a BARE "en" so the walkthrough never drifts to a
    # non-English locale (Shopify served zh-TW Traditional Chinese against an English
    # script). A bare "en" (no regional "en-US,en;q=0.9") is the strongest signal to
    # serve English regardless of the request's geo-IP. The context still sets
    # locale="en-US" so JS-side Intl/navigator.language agrees.
    "Accept-Language": "en",
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Upgrade-Insecure-Requests": "1",
    # NOTE (gate/interstitial overhaul, 2026-06-23): deliberately NO pinned
    # `sec-ch-ua*` / `sec-fetch-*` here. Hand-set client-hints override Chromium's
    # accurate native ones with stale, mismatched values — a bot-tell that makes
    # Allbirds (and similar CDN-fronted storefronts) serve a CSS-stripped degraded
    # shell where the region modal never renders as a positioned overlay. Letting
    # Chromium send its own restores the styled walk + surfaces the gate. Mirrors
    # capture_screenshots._EXTRA_HEADERS.
}

# R5 (Shopify bug #5) — URL path segments that indicate a geo-redirect to a
# non-English locale (shopify.com/tw/..., site.com/zh-TW/..., /fr/...). When the
# landed URL matches, we re-navigate to the locale-stripped path so the walkthrough
# stays in English even when the site geo-redirects on IP (Accept-Language alone did
# not stop Shopify). Mirrors capture_screenshots._GEO_LOCALE_RE.
_GEO_LOCALE_RE = re.compile(
    r"/(?:"
    r"tw|zh-tw|zh-hk|zh-cn|zh|ja|ko|de|fr|es|pt|it|nl|pl|sv|da|fi|nb|"
    r"ru|ar|he|tr|cs|sk|hu|ro|bg|hr|uk|vi|th|id|ms|"
    r"zh_tw|zh_cn|zh_hk"
    r")(?:/|$)",
    re.IGNORECASE,
)

# Sub-page hint: if the emphasis mentions one of these, try to click an obvious
# matching nav link. Phase 1 only follows ONE such link and degrades gracefully.
_SUBPAGE_HINTS = (
    "pricing", "features", "feature", "products", "product",
    "solutions", "platform", "how it works", "how-it-works",
    "enterprise", "use cases", "use-cases", "about",
)

# ---------------------------------------------------------------------------
# Stealth + hardened launch (R8 SHOPIFY-HARDENING) — mirror of
# capture_screenshots._STEALTH_INIT_JS / _launch_browser / _proxy_settings so the
# two Playwright entry points behave identically. A local copy (not a shared
# import) keeps walk_native a standalone subprocess, consistent with the existing
# duplicated _wait_for_spa_hydration / _GEO_LOCALE_RE / _dismiss_interstitial.
# Defeats BOT-DETECTION only; a server-side geo-IP redirect (Taiwan egress -> /tw)
# needs a US-egress proxy (WALK_PROXY) — see OVERHAUL-LOOP-STATE.md.
# ---------------------------------------------------------------------------
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
  try {
    const _gp = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = function (p) {
      if (p === 37445) return 'Intel Inc.';
      if (p === 37446) return 'Intel Iris OpenGL Engine';
      return _gp.call(this, p);
    };
  } catch (e) {}
})();
"""


def _proxy_settings():
    """Optional Playwright proxy from WALK_PROXY (OFF by default). The only way to
    beat a server-side geo-IP redirect (Taiwan egress -> /tw) is a US IP; set
    WALK_PROXY=http://user:pass@host:port to route through one. Unset => no proxy."""
    raw = (os.environ.get("WALK_PROXY") or "").strip()
    if not raw:
        return None
    return {"server": raw}


def _launch_browser(p):
    """Launch a hardened Chromium that looks like a real desktop Chrome.

    Order (most-realistic first, each falling through): real installed Chrome
    channel + --headless=new -> bundled chromium + --headless=new -> bundled
    chromium with the legacy launch args (original behavior). Keeps the existing
    NetworkServiceInProcess + ignore-certificate-errors flags the promo-agent rule
    requires. WALK_PROXY (if set) is applied at launch."""
    # The promo-agent/NemoClaw launch rule: NetworkServiceInProcess avoids the
    # netlink sandbox issue; ignore-cert keeps redirect chains from aborting.
    legacy_args = [
        "--no-sandbox",
        "--enable-features=NetworkService,NetworkServiceInProcess",
        "--ignore-certificate-errors",
        "--disable-blink-features=AutomationControlled",
    ]
    common = {}
    proxy = _proxy_settings()
    if proxy:
        common["proxy"] = proxy
        print("WALK_NATIVE: using WALK_PROXY egress")
    try:
        return p.chromium.launch(channel="chrome",
                                 args=legacy_args + ["--headless=new"], **common)
    except Exception as e:
        print("WALK_NATIVE: chrome channel unavailable (%s); using bundled chromium" % e)
    try:
        return p.chromium.launch(args=legacy_args + ["--headless=new"], **common)
    except Exception as e:
        print("WALK_NATIVE: --headless=new failed (%s); using default headless" % e)
    return p.chromium.launch(args=legacy_args, **common)


FFMPEG_FPS = 14  # ~12-15fps so the clip duration ≈ the captured motion span

# --- smart-nav config ------------------------------------------------------
# Max perceive->propose->execute iterations. Also bounded by the wall-clock
# alarm in main(); whichever fires first stops the loop. ~9 is enough to reach a
# named sub-page (homepage -> nav click -> settle -> a couple scrolls -> done)
# while leaving headroom under the duration+slack alarm.
MAX_STEPS = 9

# Operator-selectable nav brain. DEFAULT super-free so a build never bills nav
# tokens; ultra-paid (550B) is for the real deliverable. Resolved at run time
# from the WS_WALK_BRAIN env (falls back to super-free for unknown/empty).
def _walk_brain() -> str:
    if _brain is None:
        return "super-free"
    return _brain.normalize_brain(os.environ.get("WS_WALK_BRAIN"))


# ---------------------------------------------------------------------------
# Tiny atomic-write helpers (temp + os.replace) — the dashboard polls these
# files live, so a half-written frame/state must never be observable.
# ---------------------------------------------------------------------------

def _atomic_write_bytes(path: str, data: bytes) -> None:
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)


def _atomic_write_json(path: str, obj: dict) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f)
    os.replace(tmp, path)


def _write_state(state_path: str, url: str, step: str, action: str) -> None:
    """Best-effort atomic state.json write. Never raises."""
    try:
        _atomic_write_json(state_path, {
            "url": url or "",
            "step": step or "",
            "action": action,
            "ts": int(time.time()),
        })
    except Exception:
        pass


def _norm_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return url
    if "://" not in url:
        url = "https://" + url
    return url


# ---------------------------------------------------------------------------
# SPA hydration gate — identical strategy to capture_screenshots._wait_for_spa_hydration
# ---------------------------------------------------------------------------

def _wait_for_spa_hydration(page, settle_ms: int = 1200) -> None:
    """Gate on semantic content presence before stepping. Never raises."""
    try:
        page.wait_for_selector("h1, h2, main, article, nav a",
                               state="attached", timeout=10000)
    except Exception:
        pass
    try:
        page.wait_for_load_state("networkidle", timeout=10000)
    except Exception:
        pass
    try:
        page.wait_for_timeout(settle_ms)
    except Exception:
        pass


# ===========================================================================
# PRE-CONTENT GATE HANDLER (brand-agnostic, idempotent)
# ===========================================================================
# Self-contained duplicate of capture_screenshots' gate handler (per the L16
# duplicated-helper convention — walk + capture run as separate subprocesses).
# We run it BEFORE the screencast starts so the recorded walk shows real product,
# not a "Where are we shipping to?" overlay. The naive "click first close" handler
# FAILS on a gate that REQUIRES a choice (Allbirds' region selector has no
# close-X); this handler SELECTS a US/English option + confirms for selectors and
# only DISMISSES for newsletter/cookie overlays. Detect -> classify -> act ->
# verify-gone -> retry/escalate -> log. Idempotent + non-destructive; never raises.

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
_GATE_DISMISS_PREFER = (
    "no thanks", "no, thanks", "not now", "maybe later", "close", "dismiss",
    "skip", "x", "×",
)

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
  const be = document.body, he = document.documentElement;
  const bs = be ? getComputedStyle(be) : null, hs = he ? getComputedStyle(he) : null;
  const scrollLocked = !!(
    (bs && (bs.overflow === 'hidden' || bs.position === 'fixed')) ||
    (hs && (hs.overflow === 'hidden'))
  );
  const hasDimBg = (s) => {
    const bg = s.backgroundColor || '';
    const m = bg.match(/rgba?\(([^)]+)\)/);
    if (!m) return false;
    const parts = m[1].split(',').map(x => parseFloat(x));
    if (parts.length === 4) return parts[3] > 0.05 && parts[3] < 0.98;
    return false;
  };
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
    const highLayer = isOverlayPos && (!isNaN(z) && z >= 50);
    const fixedBackdrop = pos === 'fixed' && frac >= 0.85;
    const dimBackdrop = isOverlayPos && frac >= 0.6 && hasDimBg(s);
    const qualifies =
      (isDialogRole && frac >= 0.05) ||
      (highLayer && frac >= 0.3) ||
      (fixedBackdrop) ||
      (dimBackdrop) ||
      (scrollLocked && isOverlayPos && frac >= 0.15);
    if (qualifies && frac > bestArea) { best = el; bestArea = frac; }
    if ((fixedBackdrop || dimBackdrop) && frac > bestBdArea) {
      bestBackdrop = el; bestBdArea = frac;
    }
  }
  if (!best) best = bestBackdrop;
  if (!best) return null;
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
    return (c.get("text") or c.get("aria") or c.get("title")
            or c.get("value") or "").strip().lower()


def _score_candidate(c: dict, prefer: tuple, *, exact_bonus=True) -> int:
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
    best_c, best_s = None, -1
    for c in candidates:
        s = _score_candidate(c, prefer)
        if s > best_s:
            best_s, best_c = s, c
    if best_c is not None and best_s >= 0:
        return _click_candidate(page, best_c)
    return False


def _act_on_gate(page, kind: str, candidates: list) -> str:
    if kind == "region":
        if _pick_and_click(page, candidates, _GATE_US_PREFER):
            _pick_and_click(page, candidates, _GATE_PROCEED_PREFER)
            return "selected US/English region + confirm"
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
    if _pick_and_click(page, candidates, _GATE_PROCEED_PREFER):
        return "proceeded (generic)"
    if _pick_and_click(page, candidates, _GATE_DISMISS_PREFER):
        return "dismissed (generic)"
    return ""


def _escalate_gate(page) -> bool:
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
    """Robust pre-content gate handler. Detect -> classify -> act (SELECT-to-
    proceed for region/age vs DISMISS for newsletter/cookie) -> verify-gone ->
    retry/escalate. Idempotent, non-destructive, never raises. Returns True if it
    acted on at least one gate."""
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
        try:
            page.wait_for_timeout(450)
        except Exception:
            pass
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
                    "proceeding anyway (walk may be occluded)" % max_tries)
    except Exception:
        pass
    return acted_any


# JS: True while a full-page LOADING SPINNER is still on screen and no gate has
# appeared yet — used to delay the gate check a beat so a late-injected region/age
# modal (Allbirds injects its shipping modal AFTER hydration) and the page CSS
# both render before the screencast starts. Mirrors capture_screenshots.
_PAGE_LOADING_JS = r"""
() => {
  const vw = innerWidth, vh = innerHeight;
  const spin = Array.from(document.querySelectorAll(
    'svg, [class*="spinner" i], [class*="loading" i], [class*="loader" i], ' +
    '[role="progressbar"]'
  ));
  for (const el of spin) {
    const s = getComputedStyle(el);
    if (s.display === 'none' || s.visibility === 'hidden' || s.opacity === '0') continue;
    const r = el.getBoundingClientRect();
    const big = Math.min(r.width, r.height) >= Math.min(vw, vh) / 3;
    const onScreen = r.top < vh && r.bottom > 0 && r.left < vw && r.right > 0;
    if (!big || !onScreen) continue;
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
    """Brief grace poll BEFORE the gate check: poll up to `max_ms` for EITHER a
    blocking gate to appear (Allbirds injects its shipping modal AFTER hydration)
    OR a full-page loading spinner to clear, so the recorded walk doesn't open on
    the spinner phase. Returns as soon as a gate is detected. Never raises."""
    waited = 0
    while waited < max_ms:
        try:
            if page.evaluate(_GATE_DETECT_JS):
                return
        except Exception:
            pass
        try:
            still_loading = bool(page.evaluate(_PAGE_LOADING_JS))
        except Exception:
            still_loading = False
        if not still_loading and waited >= step_ms:
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
        page, log=lambda m: print("WALK_NATIVE:%s" % m))


# ===========================================================================
# SMART NAV — perceive -> propose -> execute (ported from walk-ultra's
# explainer-agent: gatherClickables / pickNextAction proposer / click branch).
# ===========================================================================

# ---- PERCEIVE -------------------------------------------------------------
# DOM query mirrored from walk-ultra gatherClickables (same selector set, same
# rect/visibility filters, same dedup key, same 80-element cap). Returns a list
# of {tag,text,aria,href,rect}; the list INDEX is the stable ref the proposer
# clicks ("click 3"). scrollIntoView for a ref re-runs the identical selector so
# index->element stays aligned (matching walk-ultra's scrollAndMark contract).
_CLICKABLE_SELECTOR = (
    'a, button, [role="button"], [role="link"], '
    '[role="menuitem"], [role="tab"], [role="option"], select'
)

# JS evaluated for both gather + scroll-into-view. Parameterised by a mode so the
# index mapping cannot drift between perception and execution.
_PERCEIVE_JS = r"""
(args) => {
  const SEL = args.sel;
  const mode = args.mode;       // 'gather' | 'scroll'
  const wantIdx = args.idx;     // used when mode === 'scroll'
  const all = Array.from(document.querySelectorAll(SEL));
  const seen = new Set();
  const visible = [];
  const out = [];
  for (const el of all) {
    const r = el.getBoundingClientRect();
    const s = window.getComputedStyle(el);
    if (r.width < 4 || r.height < 4) continue;
    if (s.visibility === 'hidden' || s.display === 'none' || s.opacity === '0') continue;
    if (r.bottom < 0 || r.top > window.innerHeight + 800) continue;
    const text = (el.innerText || el.textContent || '').trim().replace(/\s+/g, ' ');
    const aria = el.getAttribute('aria-label') || '';
    const key = `${el.tagName}|${text}|${aria}|${Math.round(r.x)},${Math.round(r.y)}`;
    if (seen.has(key)) continue;
    seen.add(key);
    visible.push(el);
    out.push({
      tag: el.tagName.toLowerCase(),
      text: text.slice(0, 120),
      aria: aria,
      href: el.getAttribute('href') || '',
      rect: { x: r.x, y: r.y, w: r.width, h: r.height },
    });
    if (visible.length >= 80) break;
  }
  if (mode === 'scroll') {
    const target = visible[wantIdx];
    if (!target) return null;
    target.scrollIntoView({ block: 'center', inline: 'center', behavior: 'instant' });
    const r = target.getBoundingClientRect();
    return { x: r.x, y: r.y, w: r.width, h: r.height };
  }
  return out;
}
"""


def _gather_clickables(page):
    try:
        out = page.evaluate(_PERCEIVE_JS, {"sel": _CLICKABLE_SELECTOR,
                                           "mode": "gather", "idx": -1})
        return out or []
    except Exception:
        return []


def _scroll_ref_into_view(page, idx):
    """Scroll the idx-th clickable to center and return its live viewport rect."""
    try:
        return page.evaluate(_PERCEIVE_JS, {"sel": _CLICKABLE_SELECTOR,
                                            "mode": "scroll", "idx": idx})
    except Exception:
        return None


def _gather_page_text(page) -> str:
    try:
        return page.evaluate(
            "() => ((document.querySelector('main') || document.body)"
            ".innerText || '').trim().replace(/\\s+/g, ' ')") or ""
    except Exception:
        return ""


def _scroll_metrics(page) -> dict:
    try:
        return page.evaluate(
            "() => ({scrollY: window.scrollY, "
            "fullPageHeight: document.documentElement.scrollHeight, "
            "viewportHeight: window.innerHeight})")
    except Exception:
        return {"scrollY": 0, "fullPageHeight": 0, "viewportHeight": VIEWPORT["height"]}


# ---- PROPOSE --------------------------------------------------------------
# Ported walk-ultra proposer prompt, trimmed to the THREE navigation actions a
# brand-explainer needs (click / scroll / done). The canvas-drawing branches
# (drag / freedraw / clickAt / keyboard / search) are dropped — they never apply
# to "navigate to the emphasized feature". The KEYWORD-ANCHOR preference, the
# WHEN-LOST scroll-first rule, and the strict DONE rule are kept verbatim in
# spirit because they are exactly what makes the nav goal-directed.
_PROPOSER_SYSTEM = """You drive a web browser to record a short brand walkthrough video.
Your job: NAVIGATE to the part of the site the goal emphasizes, by CLICKING the right
nav link or button to reach it (e.g. click "Pricing" to open the pricing page), then
stop. Reply with valid JSON ONLY — no prose, no markdown fences.

You have THREE possible actions:
  - click a listed element by its id (to follow a nav link / button toward the goal),
  - scroll the page down or up (to reveal content below the fold),
  - finish (done) when the emphasized content is on screen.

Prefer specific, goal-relevant elements over generic navigation.

KEYWORD-ANCHOR PREFERENCE:
If the goal / emphasis names specific text (e.g. "pricing", "features", "platform",
a product name), strongly prefer the clickable whose visible text, aria-label, or
href contains those exact terms. A nav link literally labelled with the goal term is
almost always the right click. Trust text/aria/href matches over visual guesses.

When to CLICK (by id):
  - A clickable element directly advances toward the emphasized feature (e.g. a
    "Pricing" nav link when the goal is the pricing page). Click it.
  - You are still on the homepage / a hub page and the emphasized destination is a
    different page reachable via a nav link.

When to SCROLL:
  - You are already on the right page and the emphasized content is below the fold.
  - No listed clickable matches the goal yet, but the page text suggests it is further
    down (menus and link lists often continue below the fold — scroll first).
  - You just landed on a new page and have not looked below the fold yet.

When DONE:
  - ONLY when the emphasized content is VISIBLE on the CURRENT page — the specific
    page/section the goal names, not a hub or landing page that merely LINKS to it.
  - Your "reasoning" MUST quote the on-page heading/text or the URL that proves you
    arrived (e.g. evidence: URL is /pricing and the heading reads "Pricing").
  - If the current page only LINKS to the target, you are NOT done — click through first.
  - "Genuinely stuck" (the destination is unreachable from here) is the only other
    valid reason to finish.

Reply with EXACTLY ONE of these JSON shapes:
  {"id": <number>, "description": "Click ...", "reasoning": "..."}
  {"scroll": "down" | "up", "px": <number, default 600>, "description": "Scroll to see ...", "reasoning": "..."}
  {"done": true, "reasoning": "..."}"""


def _parse_decision_loose(raw: str):
    """Parse the proposer's JSON decision; tolerate fences / surrounding prose.

    Returns a dict (click/scroll/done) or None if nothing usable is found. Never
    raises — a None return means "fall back to a scroll step".
    """
    if not raw:
        return None
    t = raw.strip()
    t = re.sub(r"^```(?:json)?\s*", "", t)
    t = re.sub(r"\s*```$", "", t)
    # Try the largest balanced { ... } blocks, biggest first.
    candidates = re.findall(r"\{[\s\S]*?\}", t)
    candidates.sort(key=len, reverse=True)
    # Also try the first { to the last } (handles nested objects).
    s, e = t.find("{"), t.rfind("}")
    if s != -1 and e != -1 and e > s:
        candidates.insert(0, t[s:e + 1])
    for c in candidates:
        try:
            obj = json.loads(c)
        except Exception:
            continue
        if not isinstance(obj, dict):
            continue
        if obj.get("done") is True:
            return {"done": True, "reasoning": str(obj.get("reasoning", ""))}
        if isinstance(obj.get("id"), (int, float)):
            return {"id": int(obj["id"]),
                    "description": str(obj.get("description", "")),
                    "reasoning": str(obj.get("reasoning", ""))}
        sc = obj.get("scroll")
        if sc in ("down", "up"):
            return {"scroll": sc, "px": obj.get("px", 600),
                    "description": str(obj.get("description", "")),
                    "reasoning": str(obj.get("reasoning", ""))}
    # Last-ditch regex mining (model emitted reasoning-only / malformed JSON).
    if re.search(r'"done"\s*:\s*true', t, re.I):
        return {"done": True, "reasoning": "parsed from partial output"}
    m = re.search(r'"id"\s*:\s*(\d+)', t)
    if m:
        return {"id": int(m.group(1)), "description": "Click (recovered)",
                "reasoning": "parsed from partial output"}
    m = re.search(r'"scroll"\s*:\s*"(up|down)"', t, re.I)
    if m:
        return {"scroll": m.group(1).lower(), "px": 600,
                "description": "Scroll (recovered)",
                "reasoning": "parsed from partial output"}
    return None


def _call_nemotron(messages, brain_key_name: str, timeout_s: int = 60):
    """POST the proposer messages to OpenRouter (OpenAI-compatible) and return the
    assistant content string. Returns "" on any failure (caller degrades to scroll).

    Mirrors validate_planner's call shape (same endpoint, headers, body).
    """
    if _brain is None:
        return ""
    key = _brain.brain_key()
    if not key:
        return ""
    bdef = _brain.brain_def(brain_key_name)
    payload = {
        "model": bdef["slug"],
        "messages": messages,
        "temperature": 0.2,
        # This Nemotron tier emits hidden reasoning tokens against the completion
        # budget; give headroom so the JSON decision is not truncated.
        "max_tokens": 2000,
    }
    req = urllib.request.Request(
        _brain.brain_endpoint(),
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": "Bearer %s" % key,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "HTTP-Referer": "https://filmostudio.vercel.app",
            "X-Title": "Filmo",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        choice = body["choices"][0]
        msg = choice.get("message", {}) or {}
        # Prefer content; fall back to reasoning_content (the JSON sometimes lands
        # there when the model emits a reasoning trace and an empty content).
        return (msg.get("content") or msg.get("reasoning_content") or "").strip()
    except Exception:
        return ""


def _propose_next_action(brain_key_name, goal, emphasis, url, title, page_text,
                         clickables, history, metrics):
    """Ask Nemotron for the next nav action. Returns (decision_dict, n_calls).

    decision_dict is {id|scroll|done ...}; on a bad/empty/garbled response the
    caller treats a None decision as "scroll down" so the loop never hangs.
    """
    listing = "\n".join(
        "[%d] <%s> \"%s\"%s" % (
            i, c.get("tag", "?"),
            (c.get("text") or c.get("aria") or "(no text)")[:70],
            (" href=%s" % c.get("href", "")[:60]) if c.get("href") else "",
        )
        for i, c in enumerate(clickables)
    ) or "  (none on screen)"
    hist = "\n".join("  %d. %s" % (i + 1, h) for i, h in enumerate(history)) or "  (none yet)"
    sy = metrics.get("scrollY", 0)
    fh = metrics.get("fullPageHeight", 0)
    vh = metrics.get("viewportHeight", VIEWPORT["height"])
    can_down = fh > sy + vh + 40
    can_up = sy > 40
    scroll_hint = (
        "Scroll position: %dpx / %dpx total (viewport %dpx). %s %s"
        % (sy, fh, vh,
           "CAN scroll DOWN." if can_down else "At bottom — cannot scroll down.",
           "CAN scroll UP." if can_up else "")
    )
    user = (
        "Goal: %s\nEmphasized feature to reach: %s\nURL: %s\nPage title: %s\n"
        "Visible text (first 600 chars): %s\n\n%s\n\n"
        "Actions taken so far (judged good):\n%s\n\n"
        "Clickable elements on screen:\n%s\n\n"
        "Reply with EXACTLY ONE JSON action (click id / scroll / done)."
        % (goal or "(none)", emphasis or "(none)", url, title,
           (page_text or "")[:600], scroll_hint, hist, listing)
    )
    messages = [
        {"role": "system", "content": _PROPOSER_SYSTEM},
        {"role": "user", "content": user},
    ]
    raw = _call_nemotron(messages, brain_key_name)
    decision = _parse_decision_loose(raw)
    return decision, 1


# ---------------------------------------------------------------------------
# ffmpeg stitch — matches the repo's libx264/yuv420p/+faststart style.
# ---------------------------------------------------------------------------

def _webm_to_mp4(webm_path: str, out_path: str) -> bool:
    """Playwright's continuous webm -> the pipeline's h264 mp4 contract (even
    dims, yuv420p, SILENT stereo track so Remotion's a:0 probe succeeds on
    linux-x64). True on a valid mp4."""
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    cmd = [
        "ffmpeg", "-y", "-nostdin", "-loglevel", "error",
        "-i", webm_path,
        "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
        "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2,format=yuv420p,setsar=1",
        "-r", "30",
        "-c:v", "libx264", "-crf", "20", "-preset", "veryfast",
        "-c:a", "aac", "-shortest",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart", out_path,
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=120, check=False)
    except Exception:
        return False
    return (proc.returncode == 0 and os.path.exists(out_path)
            and os.path.getsize(out_path) > 1000)


# SMOOTH-CAPTURE v2: an eased requestAnimationFrame scroll tween. The old
# window.scrollTo({behavior:'smooth'}) is browser-paced (~0.3-0.5s) and reads as
# a jump on film; this pans like a camera move (default ~1.6s, cubic in-out).
_SMOOTH_SCROLL_JS = """
async ([targetY, ms]) => {
  const startY = window.scrollY;
  const dist = targetY - startY;
  if (Math.abs(dist) < 2) return;
  const t0 = performance.now();
  await new Promise((resolve) => {
    const step = (now) => {
      const p = Math.min(1, (now - t0) / ms);
      const e = p < 0.5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2;
      window.scrollTo(0, startY + dist * e);
      if (p < 1) requestAnimationFrame(step); else resolve();
    };
    requestAnimationFrame(step);
  });
}
"""


def _smooth_scroll_to(page, target_y, ms: int = 1600) -> None:
    """Cinematic pan to an absolute Y (never raises)."""
    try:
        page.evaluate(_SMOOTH_SCROLL_JS, [target_y, ms])
    except Exception:
        try:
            page.evaluate("y => window.scrollTo(0, y)", target_y)
        except Exception:
            pass


def _smooth_scroll_to_delta(page, delta, ms: int = 1400) -> None:
    """Cinematic pan by a RELATIVE amount (never raises)."""
    try:
        target = page.evaluate("d => window.scrollY + d", delta)
        _smooth_scroll_to(page, target, ms=ms)
    except Exception:
        pass


def _stitch(frames_dir: str, out_path: str, duration: float) -> bool:
    """Stitch frames_dir/f*.jpg -> out_path so the clip ≈ `duration` seconds.

    The CDP screencast emits a variable number of sequential frames (f00000.jpg…).
    We feed them straight to ffmpeg's image globber at a framerate chosen so the
    clip length ≈ `duration` (clamped to a watchable 8–18 fps). Direct glob input
    is reliable; the previous concat-demuxer-of-stills approach failed to decode
    the per-entry images (every real run returned "failed stitch").

    Returns True on a valid mp4.
    """
    pics = sorted(glob.glob(os.path.join(frames_dir, "f*.jpg")))
    if len(pics) < 2:
        return False
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)

    # framerate so total length = len(pics)/fps ≈ duration, kept watchable.
    dur = max(2.0, float(duration))
    fps = max(8.0, min(18.0, len(pics) / dur))
    # NOTE: mux a SILENT audio track (anullsrc) rather than -an. Remotion's render
    # probes every asset's audio (ffprobe -select_streams a:0); on linux-x64 that
    # errors on an audio-less mp4 (it tolerates it on arm64), failing the cloud render.
    # A silent stereo track makes a:0 exist everywhere.
    cmd = [
        "ffmpeg", "-y", "-nostdin", "-loglevel", "error",
        "-framerate", "%.4f" % fps,
        "-pattern_type", "glob", "-i", os.path.join(frames_dir, "f*.jpg"),
        "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
        "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2,format=yuv420p,setsar=1",
        "-c:v", "libx264", "-crf", "20", "-preset", "veryfast",
        "-c:a", "aac", "-shortest",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart", out_path,
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=120, check=False)
    except Exception:
        return False
    if proc.returncode != 0:
        return False
    return os.path.exists(out_path) and os.path.getsize(out_path) > 1000


# ---------------------------------------------------------------------------
# Phase-1 scroll-through — the graceful-degradation fallback. Identical behavior
# to the original Phase-1 step plan (scroll top->hero->middle->emphasis->footer,
# plus ONE obvious sub-page if the emphasis names it). Used when smart nav is
# unavailable (no OPENROUTER_API_KEY) or when the whole smart-nav loop errors.
# ---------------------------------------------------------------------------

def _phase1_scrollthrough(page, state_path: str, emphasis: str,
                          duration: float) -> None:
    """Scripted scroll-through (never raises)."""
    emph = (emphasis or "").lower()
    steps = [
        (0.0, "Opening at the top of the page", "scrolling"),
        (0.18, "Scrolling into the hero", "scrolling"),
        (0.42, "Moving through the middle of the page", "scrolling"),
        (0.66, "Highlighting the %s" % (emphasis or "key section"), "scrolling"),
        (0.90, "Reaching the footer and call to action", "scrolling"),
    ]
    per_step = max(0.8, float(duration) / (len(steps) + 1))

    def _scroll_to(frac: float) -> None:
        try:
            target = page.evaluate(
                "f => Math.round((document.body.scrollHeight - innerHeight) * f)", frac)
            _smooth_scroll_to(page, target, ms=1800)
        except Exception:
            pass

    for frac, label, action in steps:
        _write_state(state_path, page.url, label, action)
        _scroll_to(frac)
        try:
            page.wait_for_timeout(int(per_step * 1000))
        except Exception:
            time.sleep(per_step)

    # Optional ONE sub-page (only if emphasis names it).
    wanted = next((h for h in _SUBPAGE_HINTS if h in emph), None)
    if wanted:
        try:
            href = page.evaluate(
                """(want) => {
                    const links = Array.from(document.querySelectorAll('a[href]'));
                    const w = want.replace(/[^a-z]/g,'');
                    for (const a of links) {
                        const t = (a.textContent||'').toLowerCase().replace(/[^a-z]/g,'');
                        const h = (a.getAttribute('href')||'').toLowerCase();
                        if (t.includes(w) || h.includes(w)) return a.href;
                    }
                    return null;
                }""", wanted)
        except Exception:
            href = None
        if href:
            _write_state(state_path, href, "Opening the %s page" % wanted, "clicking")
            try:
                page.goto(href, wait_until="domcontentloaded", timeout=20000)
                _wait_for_spa_hydration(page, settle_ms=800)
                for frac in (0.0, 0.35, 0.7):
                    _scroll_to(frac)
                    try:
                        page.wait_for_timeout(int(per_step * 1000))
                    except Exception:
                        time.sleep(per_step)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Smart nav — perceive -> propose -> execute step loop (the Phase-2 upgrade).
# Returns the number of Nemotron calls made. Never raises: any internal failure
# is caught and turned into a fall-through so run() can degrade to Phase-1.
# ---------------------------------------------------------------------------

def _smart_nav(page, state_path: str, goal: str, emphasis: str,
               duration: float) -> int:
    """Drive goal-directed navigation. Returns the # of Nemotron calls.

    Raises ONLY if the loop cannot be entered at all (so run() falls back to
    Phase-1). Per-step failures degrade to a scroll and keep going.
    """
    brain_name = _walk_brain()
    # No key -> no proposer. Signal "smart nav unavailable" to run() so it falls
    # back to Phase-1 (rather than producing a frozen, action-less clip).
    if _brain is None or not _brain.brain_key():
        raise RuntimeError("smart-nav unavailable: OPENROUTER_API_KEY unset")

    history: list[str] = []
    n_calls = 0
    # Per-step dwell so the captured motion span ≈ duration. The loop is also
    # bounded by MAX_STEPS and the outer wall-clock alarm.
    per_step_ms = int(max(700, min(2200, (float(duration) * 1000) / (MAX_STEPS + 1))))

    def _dwell():
        try:
            page.wait_for_timeout(per_step_ms)
        except Exception:
            time.sleep(per_step_ms / 1000.0)

    def _settle_after_nav():
        _wait_for_spa_hydration(page, settle_ms=600)

    print("WALK_NATIVE: smart-nav brain=%s goal=%r emphasis=%r"
          % (brain_name, (goal or "")[:60], (emphasis or "")[:60]))

    for step in range(MAX_STEPS):
        url = page.url
        try:
            title = page.title()
        except Exception:
            title = ""
        clickables = _gather_clickables(page)
        page_text = _gather_page_text(page)
        metrics = _scroll_metrics(page)

        # PERCEIVE done. PROPOSE next action.
        try:
            decision, calls = _propose_next_action(
                brain_name, goal, emphasis, url, title, page_text,
                clickables, history, metrics)
        except Exception as e:
            print("WALK_NATIVE: smart-nav propose error step %d: %s" % (step, e))
            decision, calls = None, 1
        n_calls += calls

        # ROBUSTNESS: bad/empty/garbled response -> scroll step (never hang).
        if not decision:
            print("WALK_NATIVE: step %d no/garbled decision -> scroll" % step)
            decision = {"scroll": "down", "px": 600,
                        "description": "Scroll down", "reasoning": "fallback"}

        # --- DONE ----------------------------------------------------------
        if decision.get("done"):
            reason = (decision.get("reasoning") or "")[:160]
            print("WALK_NATIVE: step %d done: %s" % (step, reason))
            _write_state(state_path, url,
                         "Reached the %s" % (emphasis or "destination"), "done")
            _dwell()
            return n_calls

        # --- SCROLL --------------------------------------------------------
        if decision.get("scroll") in ("down", "up"):
            px = 600
            try:
                px = int(max(120, min(2000, float(decision.get("px", 600)))))
            except Exception:
                px = 600
            dy = px if decision["scroll"] == "down" else -px
            label = decision.get("description") or ("Scroll %s" % decision["scroll"])
            print("WALK_NATIVE: step %d scroll %s %dpx" % (step, decision["scroll"], px))
            _write_state(state_path, url, label, "scrolling")
            # Stepped scroll so the screencast records smooth motion.
            n_sub = max(1, px // 300)
            for _ in range(n_sub):
                try:
                    _smooth_scroll_to_delta(page,
                                  dy / n_sub)
                    page.wait_for_timeout(int(per_step_ms / max(1, n_sub)))
                except Exception:
                    time.sleep(0.2)
            history.append(label)
            continue

        # --- CLICK (the goal-directed nav action) --------------------------
        cid = decision.get("id")
        if not isinstance(cid, int) or cid < 0 or cid >= len(clickables):
            print("WALK_NATIVE: step %d invalid id %r -> scroll" % (step, cid))
            try:
                _smooth_scroll_to_delta(page, 600)
                _dwell()
            except Exception:
                pass
            continue

        target = clickables[cid]
        label = decision.get("description") or (
            "Clicking %s" % (target.get("text") or target.get("aria") or "a link"))
        # Human-readable step text (e.g. "Clicking Pricing in the nav").
        human = label if label.lower().startswith("click") else ("Clicking %s" % label)
        print("WALK_NATIVE: step %d click id=%d text=%r"
              % (step, cid, (target.get("text") or target.get("aria") or "")[:50]))
        _write_state(state_path, url, human, "clicking")

        rect = _scroll_ref_into_view(page, cid)
        if not rect or rect.get("w", 0) < 1:
            print("WALK_NATIVE: step %d could not locate id=%d -> skip" % (step, cid))
            history.append("(tried to click but element vanished)")
            continue
        _dwell()  # let the cursor land + the scroll-into-view settle on camera

        click_x = rect["x"] + rect["w"] / 2.0
        click_y = rect["y"] + rect["h"] / 2.0
        url_before = page.url
        text_before_len = len(page_text)
        try:
            page.mouse.click(click_x, click_y)
        except Exception as e:
            print("WALK_NATIVE: step %d click failed: %s" % (step, e))
            history.append("(click failed)")
            continue

        # Wait for a URL change OR a meaningful page-text change (SPA nav).
        url_changed = False
        t0 = time.time()
        while time.time() - t0 < 8.0:
            try:
                page.wait_for_timeout(250)
            except Exception:
                time.sleep(0.25)
            if page.url != url_before:
                url_changed = True
                break
            now_text = _gather_page_text(page)
            if len(now_text) > 100 and abs(len(now_text) - text_before_len) > 80:
                break
        if url_changed:
            _write_state(state_path, page.url, human, "navigating")
            try:
                page.wait_for_load_state("domcontentloaded", timeout=4000)
            except Exception:
                pass
            _settle_after_nav()
        else:
            _dwell()
        history.append(human)

    print("WALK_NATIVE: smart-nav hit MAX_STEPS (%d)" % MAX_STEPS)
    return n_calls


# ---------------------------------------------------------------------------
# Core run.
# ---------------------------------------------------------------------------

def run(url: str, goal: str, emphasis: str, out_path: str,
        run_dir: str, duration: float) -> bool:
    """Drive the capture. Returns True on a valid mp4, False on graceful skip.

    Never raises — all exceptions are caught and folded into a False return.
    """
    url = _norm_url(url)
    walk_dir = os.path.join(run_dir, "walk")
    frames_dir = os.path.join(walk_dir, "frames")
    os.makedirs(frames_dir, exist_ok=True)
    frame_live = os.path.join(walk_dir, "frame.jpg")
    state_path = os.path.join(walk_dir, "state.json")

    _write_state(state_path, url, "Launching browser", "navigating")

    # Frame counter is mutated by the CDP callback (closure over a 1-elem list so
    # the handler can increment it).
    frame_count = [0]

    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        _write_state(state_path, url, "Playwright unavailable", "failed")
        print("WALK_NATIVE: failed playwright-import: %s" % e)
        return False

    browser = None
    ctx = None
    p = None
    try:
        p = sync_playwright().start()
        # R8 SHOPIFY-HARDENING: hardened launch (real Chrome channel + new headless
        # + stealth) so bot-detection serves the real page; keeps the promo-agent
        # NetworkServiceInProcess + ignore-cert flags + optional WALK_PROXY.
        browser = _launch_browser(p)
        # SMOOTH-CAPTURE v2 (Dennis 2026-07-18: "the scrolling was shuddery —
        # frames per second were very low"): record the session with Playwright's
        # continuous video recorder (steady ~25fps webm) instead of relying on the
        # event-driven CDP screencast, whose variable-timed frames flattened to a
        # constant framerate produced the shudder. The screencast still runs for
        # the live dashboard preview + as the stitch fallback.
        video_dir = os.path.join(walk_dir, "video")
        os.makedirs(video_dir, exist_ok=True)
        ctx = browser.new_context(
            viewport=VIEWPORT,
            device_scale_factor=1,  # screencast is already capped at 1280x800
            locale="en-US",
            # US timezone + geolocation so JS-side geo checks agree with en-US.
            timezone_id="America/New_York",
            geolocation={"latitude": 40.7128, "longitude": -74.0060},
            permissions=["geolocation"],
            user_agent=_DESKTOP_UA,
            extra_http_headers=_EXTRA_HEADERS,
            record_video_dir=video_dir,
            record_video_size=VIEWPORT,
        )
        # Stealth init runs BEFORE every navigation in this context.
        ctx.add_init_script(_STEALTH_INIT_JS)
        page = ctx.new_page()

        # --- CDP screencast --------------------------------------------------
        cdp = page.context.new_cdp_session(page)

        def _on_frame(params):
            # params: {"data": <base64 jpeg>, "metadata": {...}, "sessionId": int}
            try:
                data = base64.b64decode(params["data"])
                # 1) live preview frame (atomic) — dashboard polls this.
                _atomic_write_bytes(frame_live, data)
                # 2) numbered frame for the video.
                n = frame_count[0]
                frame_count[0] = n + 1
                _atomic_write_bytes(
                    os.path.join(frames_dir, "f%05d.jpg" % n), data)
            except Exception:
                pass
            finally:
                # ALWAYS ack or the stream stalls.
                try:
                    cdp.send("Page.screencastFrameAck",
                             {"sessionId": params["sessionId"]})
                except Exception:
                    pass

        cdp.on("Page.screencastFrame", _on_frame)

        # --- navigate --------------------------------------------------------
        _write_state(state_path, url, "Opening the homepage", "navigating")
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            _write_state(state_path, url, "Could not reach the site", "failed")
            print("WALK_NATIVE: failed goto: %s" % e)
            return False

        # R5 (Shopify bug #5) — PREFER English: if the site geo-redirected to a
        # non-English locale path (shopify.com -> shopify.com/tw/), strip the locale
        # segment and re-navigate once so the walkthrough stays English when an
        # English path is reachable. Accept-Language=en alone didn't stop Shopify's
        # IP-based redirect, so this is the belt-and-suspenders correction.
        #
        # POLICY (Dennis, 2026-06-23): when English is genuinely unreachable (the
        # server re-redirects every English path back to the locale on egress IP),
        # KEEP the foreign-language page and record a real walk clip on it — a valid
        # foreign page is a SUCCESS to be captured, not a failure. Bilingual output
        # (English planner copy over a foreign walkthrough) is acceptable; the goal
        # is a COMPLETE video. We only fail the walk on a GENUINE failure (nav failed
        # at goto above, screencast start failed below) — never merely for language.
        try:
            landed = page.url or url
        except Exception:
            landed = url
        if _GEO_LOCALE_RE.search(landed):
            corrected = _GEO_LOCALE_RE.sub("/", landed, count=1)
            if corrected != landed:
                print("WALK_NATIVE: geo-redirect to non-en locale (%s); "
                      "trying English at %s (keep the foreign page if it re-redirects)"
                      % (landed, corrected))
                try:
                    page.goto(corrected, wait_until="domcontentloaded", timeout=30000)
                except Exception:
                    pass  # keep the geo page and walk it rather than fail the walk

        _wait_for_spa_hydration(page)

        # R7 gap 4 — dismiss a geo/shipping/region/cookie interstitial BEFORE the
        # screencast starts, so the recorded walk shows the real product rather
        # than a "Where are we shipping to?" overlay (Allbirds + many storefronts).
        try:
            if _dismiss_interstitial(page):
                print("WALK_NATIVE: dismissed a geo/shipping/cookie interstitial")
        except Exception:
            pass

        # Start the screencast AFTER hydration so the first frames show real
        # content, not a blank shell.
        try:
            cdp.send("Page.startScreencast", {
                "format": "jpeg", "quality": 60,
                "maxWidth": 1280, "maxHeight": 800, "everyNthFrame": 2,
            })
        except Exception as e:
            _write_state(state_path, page.url, "Screencast start failed", "failed")
            print("WALK_NATIVE: failed startScreencast: %s" % e)
            return False

        # --- navigation (Phase 2 smart nav, Phase 1 fallback) ---------------
        # Try goal-directed smart nav first (perceive->propose->execute: it CLICKS
        # the right nav link / button to reach the emphasized feature). If smart
        # nav is unavailable (no OPENROUTER_API_KEY) or errors as a whole, degrade
        # gracefully to the Phase-1 scripted scroll-through. The screencast keeps
        # running across either path.
        try:
            n_calls = _smart_nav(page, state_path, goal, emphasis, duration)
            print("WALK_NATIVE: smart-nav complete (%d nemotron call(s))" % n_calls)
        except Exception as e:
            print("WALK_NATIVE: smart-nav unavailable/failed (%s) -> Phase-1 scroll-through"
                  % e)
            try:
                _phase1_scrollthrough(page, state_path, emphasis, duration)
            except Exception as e2:
                # Even Phase-1 failing is non-fatal — whatever frames we captured
                # still stitch below.
                print("WALK_NATIVE: phase-1 fallback also errored: %s" % e2)

        # --- stop screencast + give the last acks a beat ---------------------
        try:
            cdp.send("Page.stopScreencast")
        except Exception:
            pass
        try:
            page.wait_for_timeout(300)
        except Exception:
            pass

        # --- finalize the recording ------------------------------------------
        _write_state(state_path, page.url, "Stitching the walkthrough", "navigating")
        # SMOOTH-CAPTURE v2: prefer the continuous Playwright recording (closing
        # the context finalizes the webm). The screencast stitch is the fallback.
        final_url = page.url
        video_path = ""
        try:
            vid = page.video
            ctx.close()          # flushes the webm to disk
            ctx = None           # teardown in `finally` skips the closed context
            video_path = vid.path() if vid else ""
        except Exception:
            video_path = ""
        if video_path and os.path.exists(video_path) and _webm_to_mp4(video_path, out_path):
            _write_state(state_path, final_url, "Walkthrough ready", "done")
            print("WALK_NATIVE: ok %s (smooth video)" % out_path)
            return True
        if frame_count[0] < 2:
            _write_state(state_path, final_url, "No frames captured", "failed")
            print("WALK_NATIVE: failed no-frames (%d)" % frame_count[0])
            return False
        if not _stitch(frames_dir, out_path, duration):
            _write_state(state_path, final_url, "Stitch failed", "failed")
            print("WALK_NATIVE: failed stitch (%d frames)" % frame_count[0])
            return False

        _write_state(state_path, final_url, "Walkthrough ready", "done")
        print("WALK_NATIVE: ok %s" % out_path)
        return True

    except Exception as e:
        _write_state(state_path, url, "Unexpected error", "failed")
        sys.stderr.write(traceback.format_exc())
        print("WALK_NATIVE: failed exception: %s" % e)
        return False
    finally:
        # ALWAYS tear down the browser so no chromium leaks.
        for closer in (
            (lambda: ctx.close()) if ctx else None,
            (lambda: browser.close()) if browser else None,
            (lambda: p.stop()) if p else None,
        ):
            if closer is None:
                continue
            try:
                closer()
            except Exception:
                pass


def _alarm_handler(signum, frame):
    # Overall wall-clock guard. Convert to a normal exception so `finally` runs
    # and the browser is torn down; main() then exits 1.
    raise TimeoutError("walk_native overall wall-clock timeout")


def main(argv):
    if len(argv) < 6:
        print("WALK_NATIVE: failed usage: walk_native.py <url> <goal> "
              "<emphasis> <out_path> <run_dir> [duration]")
        return 1
    url, goal, emphasis, out_path, run_dir = argv[1:6]
    duration = 12.0
    if len(argv) >= 7:
        try:
            duration = float(argv[6])
        except ValueError:
            duration = 12.0

    # Overall wall-clock guard: never hang. Budget = duration + generous slack for
    # launch + hydration + the smart-nav step loop (up to MAX_STEPS clicks, each
    # of which can wait ~8s for navigation) + stitch. Hard-capped at 190s so OUR
    # SIGALRM fires BEFORE the parent's 200s subprocess timeout — meaning `finally`
    # runs (browser torn down, frames stitched) instead of the parent SIGKILLing us
    # mid-flight and losing the captured frames.
    overall = int(min(190, max(90, duration + 110)))
    try:
        signal.signal(signal.SIGALRM, _alarm_handler)
        signal.alarm(overall)
    except Exception:
        pass  # SIGALRM may be unavailable on some platforms; rely on parent timeout.

    try:
        ok = run(url, goal, emphasis, out_path, run_dir, duration)
    except Exception as e:
        # Last-resort guard so we NEVER raise uncaught.
        try:
            _write_state(os.path.join(run_dir, "walk", "state.json"),
                         url, "Fatal error", "failed")
        except Exception:
            pass
        print("WALK_NATIVE: failed fatal: %s" % e)
        ok = False
    finally:
        try:
            signal.alarm(0)
        except Exception:
            pass

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
