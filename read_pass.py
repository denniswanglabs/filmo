#!/usr/bin/env python3
"""Cheap 'text + hero only' read pass over the real page, for the Conversion Read.

REUSES capture_screenshots.capture_url (max_shots=1) for ONE hero screenshot, and
pulls the page's visible copy from the shot's body_text. This deliberately does NOT
fire the full walkthrough / smart-nav / multi-shot flow -- that stays at produce
time. Best-effort: any failure returns a degraded result so the pipeline proceeds.

The read pass writes into a SEPARATE `screenshots-read/` subdir (NOT the produce-time
`screenshots/` dir) so the cheap hero shot can never shadow / clobber the real
produce-time capture that runs later in the same run.

Returns: {"url", "body_text" (<=4000 chars), "hero_screenshot_path" or None,
          "headline" or "", "degraded" bool}.
"""
import os
import sys

BODY_TEXT_CAP = 4000


def _default_capture(url, out_dir, max_shots=1):
    import capture_screenshots
    return capture_screenshots.capture_url(url, out_dir, max_shots=max_shots)


def read_pass(url, run_dir, capture_fn=None):
    """Run the cheap read pass. `capture_fn(url, out_dir, max_shots)` is injectable
    for tests; defaults to capture_screenshots.capture_url. Never raises."""
    capture_fn = capture_fn or _default_capture
    shots_dir = os.path.join(run_dir, "screenshots-read")
    result = {"url": url, "body_text": "", "hero_screenshot_path": None,
              "headline": "", "degraded": False}
    try:
        manifest = capture_fn(url, shots_dir, max_shots=1)
    except Exception as e:
        print("[read_pass] capture failed: %s" % e, file=sys.stderr)
        result["degraded"] = True
        return result
    shots = (manifest or {}).get("shots") or []
    if not shots:
        result["degraded"] = True
        return result
    hero = shots[0]
    result["hero_screenshot_path"] = hero.get("path")
    result["headline"] = (hero.get("title") or "").strip()
    result["body_text"] = (hero.get("body_text") or "")[:BODY_TEXT_CAP]
    if not result["body_text"]:
        # we got a shot but no readable copy -- degraded (the Read will lean on
        # world-knowledge / minimal), but we still have a hero for the panel.
        result["degraded"] = True
    return result
