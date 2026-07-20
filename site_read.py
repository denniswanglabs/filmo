#!/usr/bin/env python3
"""Agentic SITE READ (Dennis 2026-07-17: "have an AI agent browse around the
website and then decide on the video").

The single-page read pass starves the planner: features live on /features,
testimonials on /customers, pricing on /pricing — pages the pipeline never saw.
This module lets the run BROWSE:

  1. DISCOVER candidate pages — same-origin nav links from the static HTML plus
     a probe of the common marketing slugs (/pricing, /features, ...). Every URL
     passes url_guard before any request.
  2. PICK — one focused brain call chooses up to `max_pages` pages likely to
     carry value props / real stats / testimonials / steps / pricing. A
     deterministic slug-priority fallback covers brain failures ($0 path).
  3. VISIT — capture each page with the existing Playwright capture (rendered
     body_text + a real screenshot per page).

Output: runs/<id>/site_read.json — a PROVENANCE LEDGER:

  {"ok": true, "pages": [{"url", "slug", "title", "body_text", "shot"}, ...]}

The ledger is both the planner's corpus (richer material -> richer archetypes)
and the VO-grounding guard's database (the video may only claim what a page
actually says). Best-effort throughout: any failure degrades to the single-page
behavior — browsing must NEVER break a build.
"""
from __future__ import annotations

import concurrent.futures as _futures
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

from url_guard import assert_public_url

# Slugs that carry launch-video material, in deterministic priority order (the
# $0 fallback when the brain pick fails). Probed against the site root.
COMMON_SLUGS = (
    "pricing", "features", "how-it-works", "product", "customers",
    "testimonials", "solutions", "about", "use-cases", "docs", "faq", "demo",
)

_PAGE_TEXT_CAP = 3000
_CORPUS_CAP = 12000
_FETCH_TIMEOUT_S = 8
_UA = "Mozilla/5.0 (Macintosh) FilmoSiteRead/1.0"

# How many picked pages are captured AT ONCE. Each concurrent capture is a whole
# Chromium (in prod a whole capture subprocess), and this container has already
# OOM-SIGKILLed the Remotion compositor once — which is why the render is pinned
# to --concurrency=1. Measured, not guessed: peak memory rises linearly with
# width (~+1.1 GB per browser), so 4-wide doubles the 2-wide peak to save a
# further ~6s on a 31s read. See the table in `browse_site` for the numbers.
# SITE_READ_CONCURRENCY=1 reverts to the old strictly-serial read if a host ever
# proves too tight; the explicit `max_workers=` argument beats both.
_DEFAULT_CONCURRENCY = 2

# How many COMMON_SLUGS are probed at once. Unrelated to the capture width above:
# a probe is one HTTP request, not a browser, so this is bounded by politeness to
# the customer's origin (6 = what a browser opens per host), not by memory.
_PROBE_CONCURRENCY = 6


def _norm_origin(url: str) -> str:
    p = urllib.parse.urlparse(url if "://" in url else "https://" + url)
    return f"{p.scheme or 'https'}://{p.netloc}"


def _slug_of(url: str) -> str:
    path = urllib.parse.urlparse(url).path.strip("/") or "home"
    return re.sub(r"[^a-z0-9-]+", "-", path.lower())[:40] or "home"


def _fetch_html(url: str) -> str:
    """Static HTML (SPA shells return little — that's fine, the slug probe and
    the rendered capture cover them). '' on any failure."""
    try:
        assert_public_url(url)
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=_FETCH_TIMEOUT_S) as r:
            if "html" not in (r.headers.get("Content-Type") or ""):
                return ""
            return r.read(400_000).decode("utf-8", "replace")
    except Exception:
        return ""


def _page_exists(url: str) -> bool:
    try:
        assert_public_url(url)
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=_FETCH_TIMEOUT_S) as r:
            ct = r.headers.get("Content-Type") or ""
            return r.status == 200 and "html" in ct
    except Exception:
        return False


def _nav_links(base_url: str, html: str) -> list:
    """Same-origin <a href> targets from the static shell. Anchors (#...),
    files, and off-origin links are dropped; paths are normalized absolute."""
    origin = _norm_origin(base_url)
    out, seen = [], set()
    for m in re.finditer(r'<a[^>]+href=["\']([^"\'#?]+)["\']', html or "", re.I):
        href = m.group(1).strip()
        if not href or href.startswith(("mailto:", "tel:", "javascript:")):
            continue
        if href.startswith("http"):
            if not href.startswith(origin):
                continue
            absu = href
        elif href.startswith("/"):
            absu = origin + href
        else:
            continue
        path = urllib.parse.urlparse(absu).path.rstrip("/")
        if not path or path in seen:
            continue
        if re.search(r"\.(png|jpe?g|svg|gif|webp|pdf|zip|css|js|ico)$", path, re.I):
            continue
        seen.add(path)
        out.append(origin + path)
        if len(out) >= 24:
            break
    return out


def _probe_slugs(origin: str, slugs: list) -> dict:
    """{slug: exists} for `slugs`, probed CONCURRENTLY.

    These are plain HTTP probes, not browsers: they carry none of the memory
    cost that caps the page-capture width, and they are pure connect-and-wait.
    Serially, 12 slugs against a slow or unresponsive host burned up to
    12 x _FETCH_TIMEOUT_S = 96 seconds before a single page had been read — a
    cost that sits inside the site-read window with no event of its own, so it
    is mostly invisible until it is enormous. Width 6 is what a browser opens
    against one origin, so an unresponsive host now costs two timeouts, not
    twelve. _page_exists swallows every exception, so no probe can fail the set.
    """
    if not slugs:
        return {}
    width = max(1, min(_PROBE_CONCURRENCY, len(slugs)))
    with _futures.ThreadPoolExecutor(max_workers=width,
                                     thread_name_prefix="slug-probe") as ex:
        return dict(zip(slugs, ex.map(
            lambda s: _page_exists(f"{origin}/{s}"), slugs)))


def discover_candidates(url: str) -> list:
    """Candidate subpages: nav links first (they're the brand's own map), then
    common-slug probes for anything the nav didn't surface. Each entry:
    {"url", "slug", "source": "nav"|"probe"}. Root page is excluded."""
    origin = _norm_origin(url)
    cands, seen = [], set()
    for u in _nav_links(url, _fetch_html(url)):
        s = _slug_of(u)
        if s != "home" and s not in seen:
            seen.add(s)
            cands.append({"url": u, "slug": s, "source": "nav"})

    todo = [s for s in COMMON_SLUGS if s not in seen]
    # The old loop stopped the moment `cands` hit 16, so when the nav alone had
    # already filled the list only the FIRST unseen slug was ever requested.
    # Trimming to match keeps the request count identical in that case too.
    if len(cands) >= 16:
        todo = todo[:1]
    exists = _probe_slugs(origin, todo)
    # Replays the original serial loop verbatim against the pre-probed results,
    # so the candidate list — membership, ORDER, and the 16 cap — is unchanged.
    # (When the cap is reached partway, the probes for the remaining slugs were
    # already issued rather than skipped: more requests, identical output.)
    for slug in COMMON_SLUGS:
        if slug in seen:
            continue
        if exists.get(slug):
            seen.add(slug)
            cands.append({"url": f"{origin}/{slug}", "slug": slug,
                          "source": "probe"})
        if len(cands) >= 16:
            break
    return cands


def _pick_pages_brain(candidates: list, brain: str, max_pages: int) -> list:
    """One focused brain call: which pages carry launch-video material? Returns
    a list of candidate dicts (subset), or None on any failure. Catches
    SystemExit too — call_model exits when no API key is present, and a missing
    key must degrade to the slug fallback, never kill the build."""
    if not brain:
        return None
    try:
        import validate_planner as vp
        menu = "\n".join(f"- {c['url']} (slug: {c['slug']})" for c in candidates)
        msgs = [
            {"role": "system", "content": (
                "You choose which pages of a company website to read before "
                "producing its launch video. Pick pages likely to contain: the "
                "value proposition, REAL numbers/stats, customer names or "
                "testimonials, how-it-works steps, and pricing. Return STRICT "
                "JSON: an array of at most %d URL strings chosen from the menu. "
                "No prose." % max_pages)},
            {"role": "user", "content": "Menu:\n" + menu},
        ]
        raw = vp.call_model(msgs, brain=brain) or ""
        m = re.search(r"\[.*\]", raw, re.S)
        if not m:
            return None
        chosen = json.loads(m.group(0))
        by_url = {c["url"]: c for c in candidates}
        picked = [by_url[u] for u in chosen if isinstance(u, str) and u in by_url]
        return picked[:max_pages] or None
    except (Exception, SystemExit) as e:
        print(f"[site-read] brain pick failed ({e}); slug-priority fallback",
              file=sys.stderr)
        return None


def _pick_pages(candidates: list, brain: str, max_pages: int) -> list:
    picked = _pick_pages_brain(candidates, brain, max_pages) if candidates else None
    if picked:
        return picked
    prio = {s: i for i, s in enumerate(COMMON_SLUGS)}
    ranked = sorted(candidates, key=lambda c: prio.get(c["slug"], 99))
    return ranked[:max_pages]


def _resolve_workers(max_workers) -> int:
    """Capture width: explicit argument > SITE_READ_CONCURRENCY > default."""
    if max_workers is not None:
        return max(1, int(max_workers))
    raw = (os.environ.get("SITE_READ_CONCURRENCY") or "").strip()
    if raw:
        try:
            return max(1, int(raw))
        except ValueError:
            pass
    return _DEFAULT_CONCURRENCY


def _dedupe_picked(picked: list) -> list:
    """At most ONE capture per slug, first occurrence wins, order preserved.

    A pick's slug IS its output directory (site-read/<slug>/shot-01.png — a path
    proto_walkrec reconstructs by hand), so two picks sharing a slug share a
    directory. Serially that was a harmless overwrite; concurrently it is two
    captures racing on one shot-01.png and one manifest.json. The brain returns
    free-form URL strings, so a repeated pick is one bad completion away."""
    out, seen = [], set()
    for c in picked:
        if c["slug"] in seen:
            continue
        seen.add(c["slug"])
        out.append(c)
    return out


def _capture_page(c: dict, run_dir: str, capture_fn, homepage_text: str) -> tuple:
    """Capture ONE picked page. Returns (page_dict_or_None, log_line).

    NEVER raises: this runs as a pool task, and an exception escaping one task
    must not touch its three siblings. It also touches no shared state — every
    caller-visible result travels back through the return value, so the ledger
    is assembled by ONE thread in `picked` order."""
    try:
        out_dir = os.path.join(run_dir, "site-read", c["slug"])
        manifest = capture_fn(c["url"], out_dir, max_shots=1)
        shots = (manifest or {}).get("shots") or []
        if not shots:
            return None, ""
        hero = shots[0]
        body = (hero.get("body_text") or "")
        if _is_duplicate_of(body, homepage_text):
            return None, (f"[site-read] {c['slug']} mirrors the homepage "
                          "(SPA catch-all); dropped")
        return {
            "url": c["url"],
            "slug": c["slug"],
            "title": (hero.get("title") or "").strip(),
            "body_text": body[:_PAGE_TEXT_CAP],
            "shot": hero.get("path") or "",
        }, ""
    except Exception as e:
        return None, f"[site-read] {c['slug']} capture failed ({e}); skipping"


def browse_site(url: str, run_dir: str, brain: str = "ultra-paid",
                max_pages: int = 4, capture_fn=None, homepage_text: str = "",
                max_workers=None) -> dict:
    """The agentic read. Returns the ledger dict (and writes site_read.json).
    Never raises; {"ok": False, "pages": []} on total failure.

    `homepage_text`: the already-captured homepage body. SPA catch-alls answer
    200 for ANY path with the same shell (homefeed.me served the homepage as
    "/pricing"), so a captured page whose text mirrors the homepage is a
    DUPLICATE, not new material — it is dropped from the ledger.

    `max_workers`: how many of the picked pages are captured at once. The pages
    are wholly independent reads, so the old strictly-serial loop was dead
    serialisation — but each concurrent capture is another Chromium against a
    container that has OOM-killed a renderer before, so the width is measured,
    not assumed. Measured 2026-07-19, two trials each, reading the same four
    ycombinator.com pages (peak = summed RSS of the whole process tree, so
    Chromium's shared framework is counted once PER PROCESS and the absolute MB
    over-states real cost; the SHAPE across widths is the signal):

        serial (pre-change)   31.6s, 31.6s      1352 MB, 1297 MB
        width 1               31.1s, 30.3s      1354 MB, 1297 MB
        width 2               17.8s, 17.5s      2364 MB, 2368 MB
        width 4               10.3s, 11.5s      4822 MB, 4630 MB

    Peak scales LINEARLY with width — about +1.1 GB per extra browser, with no
    sharing benefit — so 4-wide costs ~2x the 2-wide peak to save a further ~6s.
    On a container that has already OOM-SIGKILLed the Remotion compositor (which
    is why the render is pinned to --concurrency=1) that trade buys speed with
    the one currency a build cannot spend: 2-wide it is. Width 1 reproduces the
    pre-change timing and memory exactly, so SITE_READ_CONCURRENCY=1 is a true
    revert. Both trials returned byte-identical page text, in identical order,
    at every width.

    `ledger["pages"]` stays in `picked` order at every width (see
    `_capture_page`) — downstream ties break on list position."""
    ledger = {"ok": False, "pages": []}
    try:
        candidates = discover_candidates(url)
        print(f"[site-read] {len(candidates)} candidate pages "
              f"({sum(1 for c in candidates if c['source'] == 'nav')} nav, "
              f"{sum(1 for c in candidates if c['source'] == 'probe')} probed)",
              file=sys.stderr)
        if not candidates:
            ledger["ok"] = True  # single-page site — honest, not a failure
            return _write(ledger, run_dir)
        picked = _dedupe_picked(_pick_pages(candidates, brain, max_pages))
        workers = max(1, min(_resolve_workers(max_workers), len(picked)))
        print("[site-read] reading %d page(s) %d-wide: %s"
              % (len(picked), workers, ", ".join(c["slug"] for c in picked)),
              file=sys.stderr)

        if capture_fn is None:
            import capture_screenshots
            capture_fn = capture_screenshots.capture_url

        def _one(c):
            return _capture_page(c, run_dir, capture_fn, homepage_text)

        # The pages are independent reads, so they run concurrently — but the
        # LEDGER IS NOT allowed to come back in completion order. `map` yields
        # strictly in input order, and _capture_page returns rather than
        # appending, so `pages` is assembled here, on one thread, in `picked`
        # order — the order combined_corpus concatenates and the order
        # style_fill._night_page_shot_for breaks a scoring tie on.
        if workers > 1:
            with _futures.ThreadPoolExecutor(
                    max_workers=workers, thread_name_prefix="site-read") as ex:
                results = list(ex.map(_one, picked))
        else:
            results = [_one(c) for c in picked]

        for page, log in results:
            if log:
                # One write, so concurrent captures cannot tear a line in half.
                sys.stderr.write(log + "\n")
            if page:
                ledger["pages"].append(page)
        ledger["ok"] = True
        return _write(ledger, run_dir)
    except Exception as e:
        print(f"[site-read] browse failed entirely ({e}); single-page behavior",
              file=sys.stderr)
        return _write(ledger, run_dir)


def _is_duplicate_of(body: str, homepage_text: str) -> bool:
    """True when a captured page is the homepage wearing a different URL."""
    a = re.sub(r"\s+", " ", (body or "")[:400]).strip().lower()
    b = re.sub(r"\s+", " ", (homepage_text or "")[:400]).strip().lower()
    return bool(a) and bool(b) and a == b


def _write(ledger: dict, run_dir: str) -> dict:
    try:
        with open(os.path.join(run_dir, "site_read.json"), "w") as f:
            json.dump(ledger, f, indent=2)
    except Exception:
        pass
    return ledger


def combined_corpus(homepage_text: str, ledger: dict) -> str:
    """Homepage + per-page sections, provenance-tagged, capped. This is BOTH the
    planner's reading material and the grounding guard's database."""
    parts = [(homepage_text or "")[:4000]]
    for p in (ledger or {}).get("pages") or []:
        body = (p.get("body_text") or "").strip()
        if not body:
            continue
        parts.append(f"\n\n[PAGE /{p.get('slug')} — {p.get('title', '')}]\n{body}")
    return "".join(parts)[:_CORPUS_CAP]
