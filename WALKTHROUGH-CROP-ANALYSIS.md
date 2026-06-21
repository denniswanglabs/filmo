# Walkthrough Crop Analysis — cropped-out Stripe window

**Date:** 2026-06-20
**Mode:** READ-ONLY investigation ($0, local ffmpeg/ffprobe only). No edits, no rebuilds, no paid calls.
**Subject:** Cropped-out window in a Stripe walkthrough clip; suspected cause = hardcoded
`WT_CROP=(1440,960,240,60)` in `apply_real_media.py`.

---

## TL;DR

- **Affected video:** `runs/demo-1-approve/clips/03_walkthrough.mp4` **and** `runs/demo-3-decline/clips/02_walkthrough.mp4`
  — these are **byte-identical** (same md5 `2b510cb3…`), the same real walk-agent capture reused in both runs.
- **What's cropped:** The Stripe Docs page is clipped on **both horizontal edges**. The Stripe wordmark
  reads "**…e DOCS**" (the "Strip" is gone, left), and the right-side nav ("Create acco**unt** / **Si**gn in /
  APIs & S**DKs** / **H**elp") is cut at the right edge.
- **Root cause:** **NOT** primarily our hardcoded crop rect. Two things:
  1. The clip currently on disk is the **RAW, UNPROCESSED walk-agent capture** — it was **never run through
     `apply_real_media`'s walkthrough normalize path**. Proof: it is still 14.0 s (not the `WT_DUR`=7.5 s trim),
     it still opens on the green "EXPLAINER AGENT · FEASIBILITY DEMO" intro card at t≈0.5 s (which `WT_SS`=2.6 s
     is supposed to skip), and it still has the baked-in black letterbox bars (a processed clip would fill
     1920×1080). The ledger's `real_media: {source: walk-agent}` marker was written, but the file on disk is the
     raw capture, not a normalized one.
  2. The **page itself was captured clipped** by the walk-agent. The page content fills the full 1440-px-wide
     card edge-to-edge and is cut at **both** card boundaries — i.e. the page rendered wider than the 1440-px
     capture card, so its own chrome (logo on the left, account nav on the right) is sliced off. This is a
     **capture-geometry / pre-existing problem**, not something a crop rect can recover (the pixels were never
     captured).
- **Does WT_CROP match this capture?** The card rect itself matches well: cropdetect (threshold 24) returns
  exactly `crop=1440:…:240:60` — `width=1440, x=240, y=60` are spot-on. Only the height is slightly off
  (`WT_CROP h=960` vs measured 960–986; the 986 reading is the walk-agent's dark caption bar bleeding in below
  the card, so 960 is actually a reasonable choice). **WT_CROP is correctly tuned to THIS capture's baked card.**
  It would still faithfully reproduce the already-clipped page, and it would clip wrong on any future capture
  whose card geometry differs.

---

## 1. Which run + clip is affected

Walkthrough clips across the five Stripe runs:

| Run | Walkthrough clip | dur | size | real or placeholder |
|---|---|---|---|---|
| `demo-1-approve` | `clips/03_walkthrough.mp4` | **14.0s** | 2,210,221 B | **REAL capture (clipped)** |
| `demo-2-downgrade` | `clips/02_walkthrough.mp4` | 10.0s | 633,057 B | storyboard placeholder card |
| `demo-3-decline` | `clips/02_walkthrough.mp4` | **14.0s** | 2,210,221 B | **REAL capture (clipped)** — identical md5 to demo-1 |
| `demo-4-vo-over` | `clips/03_walkthrough.mp4` | 10.0s | 633,057 B | storyboard placeholder card |
| `build-stripe-9e7829` | `clips/03_walkthrough.mp4` | 8.0s | 531,951 B | storyboard placeholder card (`studio.kind: placeholder`) |

The placeholders render the navy "WALK AGENT — … storyboard placeholder · real media generated in --mode real"
title card (verified by frame read). Only **demo-1-approve** and **demo-3-decline** carry the real walk-agent
capture, and both show the cropped Stripe Docs window.

---

## 2. True content geometry vs hardcoded WT_CROP

All clips are container 1920×1080 / 30fps. cropdetect on the real capture (demo-1, content window t=3–10s):

| cropdetect threshold | dominant result | reading |
|---|---|---|
| 24 (default) | `crop=1440:960:240:60` / `1440:986:240:60` | matches WT_CROP's w/x/y exactly |
| 16 (sensitive) | `crop=1562:988:118:60` / `1562:960:118:60` | picks up faint page edge pixels left of x=240 |

- **Width / X:** WT_CROP `w=1440, x=240` **matches** the baked white card (threshold-24 cropdetect agrees).
  The threshold-16 `1562:118` reading is cropdetect grabbing very-low-contrast antialiased pixels just outside the
  card — visually the card edge is at x≈240. So **the crop rect is centered correctly on the card.**
- **Height:** WT_CROP `h=960` → rows 60..1020. Measured content runs to ~986 (rows 60..1046) — but rows 1020..1046
  are the walk-agent's dark instruction caption bar, not page content. So **h=960 is fine** (it correctly trims
  most of the caption bar).
- **The card is NOT mis-centered.** WT_CROP would NOT cut off real page content beyond what the capture already lost.

**Conclusion:** WT_CROP is accurately fitted to this specific capture's baked card. It is a *correct constant for
this one geometry* — which is exactly the brittleness the implementer flagged. It does not match anything; it
matches *this* capture.

---

## 3. Root cause

Three candidates were on the table; the evidence resolves them:

- **(a) hardcoded crop rect not matching this clip → NO.** Cropdetect confirms WT_CROP (1440:240:60) matches the
  baked card precisely. The crop rect is not the source of the clipping.
- **(b) walk-agent captured a differently-sized / offset window → PARTIAL / underlying.** The capture composites
  the page into a fixed 1440×960 card on a 1920×1080 black canvas. The Stripe page rendered **wider than that
  card**, so the page's own left logo ("Strip") and right account-nav are clipped at the card edges. The window
  is "cropped out" because the browser viewport / capture card was narrower than the page's natural layout. The
  lost pixels were never captured — no downstream crop can recover them.
- **(c) pre-existing in the original capture → YES.** Decisively, the clip on disk **was not processed by
  `apply_real_media`'s walkthrough branch**:
  - duration is 14.0 s, not `WT_DUR`=7.5 s (no trim happened),
  - it still opens on the green "EXPLAINER AGENT · FEASIBILITY DEMO" card at t≈0.5 s (`WT_SS`=2.6 s never skipped it),
  - cropdetect on the full clip still shows the baked black bars (`1440:…:240:60`) — a normalized clip would be
    a full-bleed 1920×1080 with no bars.
  The raw walk-agent capture was swapped into the run dir and the ledger `real_media` marker set, but the
  WT_CROP/WT_SS/WT_DUR normalization was **never actually applied to the bytes on disk** (or was applied earlier
  and then overwritten by the raw file at 16:29). `finish_cut.py` (the stitcher that produced these `final.mp4`s)
  does **not** crop the walkthrough to a content rect — its walkthrough branch does a plain
  `scale:increase+crop` fill (a no-op on a 16:9 source) plus a `zoompan` push-in — so the baked bars and the
  clipped page survive into the final cut.

**So the cropped window Dennis saw is the raw walk-agent capture's own clipping, carried straight through — not
damage introduced by our WT_CROP constant.** WT_CROP would actually *improve* the framing (it removes the bars
and the intro card) if it were applied, but it cannot un-clip a page the agent captured already clipped, and it
will mis-crop any future capture whose card geometry differs.

---

## 4. How / when WT_CROP is applied (`apply_real_media.py`)

- Constants at lines 36–38: `WT_SS=2.6`, `WT_DUR=7.5`, `WT_CROP=(1440,960,240,60)`.
- `normalize(src, dst, …, is_walkthrough=True)` (lines 41–73):
  - builds vf `crop=1440:960:240:60, scale=1920:1080:force_original_aspect_ratio=increase, crop=1920:1080,
    fps=30, format=yuv420p, setsar=1` — i.e. **crop to the constant card rect first, then fill** (lines 48–54);
  - input-seeks `-ss WT_SS -t WT_DUR` to skip the intro card and trim (lines 64–66).
- `apply(run_id, mapping)` (lines 76–118): only normalizes scenes whose `id` is in the CLI `mapping` and that have
  an `output_path`; sets `is_walkthrough = (s["type"] == "walkthrough")`; marks `real_media`, flips
  `studio.kind="real_media"`, then re-stitches `final.mp4` via `adapters.stitch`.
- **Trigger:** WT_CROP is applied **only** when you run `python3 apply_real_media.py <run_id> walkthrough=<src.mp4>`
  for a walkthrough scene. The demo-1/demo-3 clips currently on disk did not get this treatment (see §3c).

---

## 5. Proposed fix (for a clean fix-agent to apply — NOT applied here)

**Primary: auto-detect the content rect at apply time via cropdetect, instead of the hardcoded `WT_CROP` constant.**
This adapts to any capture geometry (different card size/offset, future walk-agent changes).

Sketch (drop-in for `normalize`'s walkthrough branch in `apply_real_media.py`):

```python
def detect_content_rect(src, ss, dur, w_full=1920, h_full=1080):
    """Run cropdetect over the windowed content region and return (w,h,x,y).
    Falls back to a full frame if detection is unstable."""
    import re, collections
    cmd = ["ffmpeg", "-nostdin", "-hide_banner", "-ss", str(ss), "-t", str(dur),
           "-i", src, "-vf", "cropdetect=24:2:0", "-f", "null", "-"]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=120).stderr
    rects = re.findall(r"crop=(\d+):(\d+):(\d+):(\d+)", out)
    if not rects:
        return (w_full, h_full, 0, 0)
    # pick the most common rect across sampled frames (stable card geometry)
    best = collections.Counter(rects).most_common(1)[0][0]
    cw, ch, cx, cy = (int(v) for v in best)
    # sanity: reject degenerate/tiny detections, snap to even numbers for yuv420p
    if cw < w_full * 0.4 or ch < h_full * 0.4:
        return (w_full, h_full, 0, 0)
    cw -= cw % 2; ch -= ch % 2; cx -= cx % 2; cy -= cy % 2
    return (cw, ch, cx, cy)
```

Then in `normalize`, for the walkthrough branch, replace the constant unpack with:

```python
cw, ch, cx, cy = detect_content_rect(src, WT_SS, WT_DUR)
```

Keep `WT_SS` / `WT_DUR` as is (cropdetect should run over the *post-intro* window so the green card / black dip
don't skew the detection — sample at `-ss WT_SS -t WT_DUR`).

**Edge cases to handle in the robust version:**

1. **Unstable cropdetect (page scroll/animation).** Content height legitimately changes as the agent scrolls.
   Use the *mode* (most-common rect) over the window, not the last frame, and prefer the WIDEST stable rect so a
   transient scroll doesn't shrink the crop. (Demo-1 oscillates 960↔986 purely from the caption bar appearing.)
2. **Caption-bar contamination.** The walk-agent burns a dark instruction caption at the bottom (~rows 1020–1080).
   cropdetect at threshold 16 includes it; threshold 24 mostly excludes it. Keep threshold ≥24, OR clamp detected
   `ch` so the bottom doesn't dip into the caption band (e.g. cap `cy+ch ≤ 1020`).
3. **Page-already-clipped capture (THIS bug).** Auto-detect will faithfully crop to the card, but it **cannot
   recover** the logo/nav the agent never captured. The *real* fix for the clipped-page symptom is upstream in
   the **walk-agent capture** — render at a viewport wide enough that the page's chrome fits the card (e.g.
   match the card's CSS width to the page min-width, or zoom-to-fit), or capture full-page width and let
   cropdetect frame it. Note this so the fix-agent doesn't think auto-crop alone "fixes" the cropped window.
4. **No black bars at all (already full-bleed).** `detect_content_rect` returns ~`1920:1080:0:0`; the subsequent
   `scale:increase+crop` becomes a safe no-op. Good.
5. **Idempotency / re-processing.** If a clip was already normalized (full-bleed, 7.5 s), re-running auto-detect
   on it is harmless (detects full frame). But guard against double-trimming: `apply_real_media` always works from
   the supplied `src`, so always feed it the RAW capture, never a previously-normalized clip.
6. **Even dimensions for yuv420p** — snap w/h/x/y to even numbers (shown above) or libx264 yuv420p will error.

**Secondary (independent of the constant):** the demo-1 / demo-3 run dirs currently hold the **raw** capture, so
even a perfect WT_CROP isn't in those finals. A reprocess of those runs through `apply_real_media` (with the
auto-detect crop) would remove the bars + intro card. **Per the constraints this analysis does NOT reprocess the
protected runs** — flagging it for the fix-agent / Dennis to decide.

---

## Evidence summary (all measured, $0 local ffmpeg)

- demo-1 & demo-3 walkthroughs: 1920×1080, 30fps, **14.0s**, **identical md5** `2b510cb31b7ef37196bb21d6c4de4d5a`.
- Frame reads (t=0.5 green intro card; t=3 & t=8 clipped Stripe Docs; left/right/bottom edge strips) confirm:
  page clipped at both card edges; intro card still present; baked black bars still present.
- cropdetect: card rect `1440:…:240:60` (thr 24) — matches WT_CROP w/x/y; `1562:…:118:60` (thr 16) is faint-edge
  noise. Height 960–986 (986 = caption bar).
- Ledgers: demo-1 & demo-3 marked `real_media: walk-agent`; build-stripe-9e7829 = `placeholder`; demo-2 & demo-4
  = placeholder cards.
- `finish_cut.py` walkthrough branch does a plain fill + zoompan, no content-rect crop → raw bars survive to final.
- Temp frames written to `/tmp/wt-frames/` were deleted.
