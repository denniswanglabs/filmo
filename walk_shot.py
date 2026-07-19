#!/usr/bin/env python3
"""PLANNED SHOT executor (walkrec v4 — Dennis 2026-07-18: "check the website
first, figure out what a user might like, and show THAT — not random scrolls").

One deliberate, cinematic recording per PLANNED stop: open the page, settle,
locate the target section by its own heading text, slow-pan it to center, hold,
drift gently, hold. No LLM in the loop at capture time — the thinking happened
in the tour PLAN; execution is scripted, so the footage has zero mid-recording
pauses and every second shows something chosen on purpose.

Reuses walk_native's hardened machinery (launch args, stealth, hydration gate,
interstitial dismissal, smooth-scroll tween, webm->mp4 contract) and records
with Playwright's continuous 30fps recorder.

CLI:
    python3 walk_shot.py <url> <target_text> <out_path> <run_dir> [duration]

`target_text` — a heading/phrase FROM THE PAGE marking the section to feature
("Pricing", "How it works", ""=hero top). Exit 0 on a valid mp4.
"""
from __future__ import annotations

import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import walk_native as wn  # noqa: E402

# LIVE VIEWPORT contract (Dennis 2026-07-18: "see the agent screen record
# live"): while a shot session is open, the agent publishes its viewport to
# runs/<id>/live/current.jpg (~3fps, atomic replace). Publishing is built
# into the PACING — every wait slices into publish ticks — so no code path
# can hold the page without showing it. The viewer hides the pane when the
# frame goes stale (>3s).


_LIVE_TICK = {"n": 0}


def _publish_frame(page, run_dir: str) -> None:
    try:
        live = os.path.join(run_dir, "live")
        os.makedirs(live, exist_ok=True)
        tmp = os.path.join(live, ".frame.tmp")
        page.screenshot(path=tmp, type="jpeg", quality=55)
        cur = os.path.join(live, "current.jpg")
        os.replace(tmp, cur)
        # Hosted: ~1fps of the ~3fps local cadence uploads to storage so the
        # web workspace can show the agent's screen live. Best-effort.
        _LIVE_TICK["n"] += 1
        if _LIVE_TICK["n"] % 3 == 0:
            try:
                import run_events as _re
                rid = _re._hosted_run_id(run_dir)
                if rid and _re._IF_BASE and _re._IF_KEY:
                    import threading

                    def _up(p=cur, r=rid):
                        try:
                            with open(p, "rb") as f:
                                _re._if_req(
                                    "PUT",
                                    f"/api/storage/buckets/{_re._IF_BUCKET}"
                                    f"/objects/agent/{r}/live.jpg",
                                    f.read(), "image/jpeg")
                        except Exception:
                            pass
                    threading.Thread(target=_up, daemon=True).start()
            except Exception:
                pass
    except Exception:
        pass


def _pace(page, run_dir: str, ms: int) -> None:
    """Wait `ms` while publishing the viewport every ~300ms."""
    left = int(ms)
    while left > 0:
        step = min(300, left)
        page.wait_for_timeout(step)
        _publish_frame(page, run_dir)
        left -= step

# Trapezoid-velocity glide: short ease caps, CONSTANT speed in the middle.
# The cubic in-out tween reads as "inconsistent scrolling speed" on long pans
# (Dennis 2026-07-18); a constant-velocity glide with 15% ease caps doesn't.
_GLIDE_JS = """
(args) => {
  const [targetY, ms] = args;
  return new Promise((resolve) => {
    const startY = window.scrollY;
    const dist = targetY - startY;
    const t0 = performance.now();
    const CAP = 0.15;
    const ease = (p) => {
      if (p < CAP) { const u = p / CAP; return CAP * u * u / 2 * 2 / (2 - CAP); }
      if (p > 1 - CAP) { const u = (1 - p) / CAP; return 1 - (CAP * u * u / 2 * 2 / (2 - CAP)); }
      return (CAP / (2 - CAP)) + (p - CAP) * (2 / (2 - CAP));
    };
    const step = (now) => {
      const p = Math.min(1, (now - t0) / ms);
      window.scrollTo(0, Math.round(startY + dist * ease(p)));
      if (p < 1) requestAnimationFrame(step); else resolve(true);
    };
    requestAnimationFrame(step);
  });
}
"""


def _glide(page, target_y: int, ms: int, run_dir: str = "") -> None:
    """Glide while PUBLISHING: the tween runs in-page on rAF (unaffected by
    CDP screenshots); python ticks frames out until it lands."""
    try:
        page.evaluate(
            "(args) => { window.__glideDone = false;"
            " (" + _GLIDE_JS + ")(args).then(() => { window.__glideDone = true; }); }",
            [int(target_y), int(ms)])
        waited = 0
        while waited < ms + 1500:
            page.wait_for_timeout(300)
            waited += 300
            if run_dir:
                _publish_frame(page, run_dir)
            try:
                if page.evaluate("() => window.__glideDone === true"):
                    break
            except Exception:
                break
    except Exception:
        wn._smooth_scroll_to(page, target_y, ms=ms)

_FIND_TARGET_JS = """
(needle) => {
  if (!needle) return null;
  const n = needle.toLowerCase();
  const els = Array.from(document.querySelectorAll('h1,h2,h3,h4,[class*="head"],[class*="title"],section,p,span,div'));
  let best = null, bestLen = 1e9;
  for (const el of els) {
    const t = (el.textContent || '').trim();
    if (!t || t.length > 400) continue;
    if (t.toLowerCase().includes(n)) {
      // Prefer the TIGHTEST match (the heading itself, not a giant container).
      if (t.length < bestLen) { best = el; bestLen = t.length; }
    }
  }
  if (!best) return null;
  const r = best.getBoundingClientRect();
  return { y: r.top + window.scrollY, h: r.height };
}
"""


def _trim_head(mp4_path: str, off_s: float) -> None:
    """Cut the pre-shot head (page load, and for targeted shots the instant
    pre-position jump) so the clip opens ON the composed frame. Best-effort."""
    if off_s < 0.3:
        return
    import subprocess
    tmp = mp4_path + ".trim.mp4"
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{off_s:.2f}",
             "-i", mp4_path, "-c:v", "libx264", "-crf", "19", "-preset", "fast",
             "-pix_fmt", "yuv420p", "-c:a", "aac", "-movflags", "+faststart", tmp],
            check=True, timeout=180)
        if os.path.exists(tmp) and os.path.getsize(tmp) > 50000:
            os.replace(tmp, mp4_path)
    except Exception:
        pass
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except Exception:
                pass


def shot(url: str, target: str, out_path: str, run_dir: str,
         duration: float = 9.0) -> bool:
    url = wn._norm_url(url)
    walk_dir = os.path.join(run_dir, "walk-shot")
    video_dir = os.path.join(walk_dir, "video")
    os.makedirs(video_dir, exist_ok=True)

    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        print("WALK_SHOT: failed playwright-import: %s" % e)
        return False

    p = browser = ctx = None
    try:
        p = sync_playwright().start()
        browser = wn._launch_browser(p)
        ctx = browser.new_context(
            viewport=wn.VIEWPORT,
            device_scale_factor=1,
            locale="en-US",
            timezone_id="America/New_York",
            user_agent=wn._DESKTOP_UA,
            extra_http_headers=wn._EXTRA_HEADERS,
            record_video_dir=video_dir,
            record_video_size=wn.VIEWPORT,
        )
        ctx.add_init_script(wn._STEALTH_INIT_JS)
        t_rec0 = time.time()  # video frame 0 ~= page creation
        page = ctx.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        wn._wait_for_spa_hydration(page)
        try:
            wn._dismiss_interstitial(page)
            wn._handle_content_gate(page)
        except Exception:
            pass
        # Everything above happened BEFORE the pose; give the page a beat to
        # finish image loads so the recording opens on a fully painted frame.
        page.wait_for_timeout(1200)

        # THE SHOT: settle on hero -> pan target section to center -> hold ->
        # gentle drift -> hold. All pacing derived from `duration`.
        hold_ms = int(max(1.2, duration * 0.22) * 1000)
        pan_ms = int(max(1.8, duration * 0.28) * 1000)

        target_y = 0
        if target:
            try:
                found = page.evaluate(_FIND_TARGET_JS, target)
            except Exception:
                found = None
            if found:
                vh = wn.VIEWPORT["height"]
                target_y = max(0, int(found["y"] - (vh - min(found["h"], vh)) / 2))
        if target_y > 0:
            # Pre-position just ABOVE the section off-camera, then ONE glide
            # into center — no mid-shot stop-starts (they read as chop).
            approach = max(0, target_y - 220)
            page.evaluate("(y) => window.scrollTo(0, y)", approach)
            _pace(page, run_dir, 600)
            shot_begin = time.time()  # head up to here (load + jump) gets trimmed
            _pace(page, run_dir, int(hold_ms * 0.8))  # opening hold
            glide_ms = int(duration * 1000 * 0.45)
            _glide(page, target_y, glide_ms, run_dir=run_dir)
        else:
            shot_begin = time.time()  # trim the load-flicker head
            _pace(page, run_dir, int(hold_ms * 0.8))  # opening hold (hero)
            # Hero shot: ONE long constant-velocity glide deep into the page.
            try:
                deep = page.evaluate(
                    "() => Math.min(document.body.scrollHeight - innerHeight,"
                    " Math.round(innerHeight * 1.7))")
            except Exception:
                deep = int(wn.VIEWPORT["height"] * 1.2)
            glide_ms = int(duration * 1000 * 0.62)
            _glide(page, max(0, int(deep or 0)), glide_ms, run_dir=run_dir)

        _pace(page, run_dir, hold_ms + int(hold_ms * 0.6))  # settled close hold

        vid = page.video
        ctx.close()
        ctx = None
        video_path = vid.path() if vid else ""
        if video_path and os.path.exists(video_path) and wn._webm_to_mp4(video_path, out_path):
            _trim_head(out_path, max(0.0, shot_begin - t_rec0 - 0.15))
            print("WALK_SHOT: ok %s (target=%r)" % (out_path, target))
            return True
        print("WALK_SHOT: failed no-video")
        return False
    except Exception as e:
        print("WALK_SHOT: failed %s" % e)
        return False
    finally:
        for closer in ((lambda: ctx.close()) if ctx else None,
                       (lambda: browser.close()) if browser else None,
                       (lambda: p.stop()) if p else None):
            if closer is None:
                continue
            try:
                closer()
            except Exception:
                pass


def main(argv):
    if len(argv) < 5:
        print("usage: walk_shot.py <url> <target_text> <out_path> <run_dir> [duration]")
        return 1
    url, target, out_path, run_dir = argv[1:5]
    duration = float(argv[5]) if len(argv) > 5 else 9.0
    return 0 if shot(url, target, out_path, run_dir, duration) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
