# Walkthrough Invocation Fix — why the page clips ONLY via Hermes

**Date:** 2026-06-20
**Mode:** READ-ONLY investigation ($0, no walk-agent/NemoClaw capture run, no edits). Pure source read.
**Builds on:** `WALKTHROUGH-CROP-ANALYSIS.md` (which proved the page was *captured* clipped — content fills a
1440px card and slices both horizontal edges). This doc answers the new question: **why does that only happen
when Walk Ultra is run through Hermes, never when Dennis runs Walk Ultra directly?**

---

## TL;DR

The clipping is caused by a **viewport mismatch introduced by BEAM mode**, and **Hermes turns BEAM on while
Dennis's direct Walk Ultra runs leave it off.**

- The Hermes pipeline invokes the walk-agent via `adapters.py` → `walk-ultra/tutorial-maker.sh`.
  **`tutorial-maker.sh` defaults `BEAM="${BEAM:-1}"` (line 61) — BEAM ON.**
- Dennis's direct runs call `walk-ultra/explainer-agent/make-explainer.sh`, which defaults
  **`BEAM="${BEAM:-0}"` (line 19) — BEAM OFF.**
- In BEAM mode the agent runs candidate "scout" tabs in fresh browser contexts created at
  **`viewport: { width: 1280, height: 720 }`** (`agent.sandbox-v26.js:2883`, and the executors'
  `setViewportSize({ width: 1280, height: 720 })` at lines 1115 / 1226). The **winning** scout's
  `before.png` / `after.png` are copied verbatim into `screenshots/step_N_*.png` (lines 3040–3043) — these
  are the exact frames the Remotion `Explainer` composition renders.
- In single-tab (BEAM=0) mode all screenshots come from the **lead** page, which is sized
  **1440×900** (`agent.sandbox-v26.js:1441`, window `--window-size=1440,900` at line 1401). Those fill the
  card 1:1, so **no clip**.
- The Remotion `Explainer` composition (`explainer-agent/remotion/src/Explainer.tsx`) hardcodes
  `SCREEN_W = 1440, SCREEN_H = 900` and draws every screenshot with **`objectFit: "cover"`**. A 1280×720
  image placed in a 1440×900 box with `cover` is scaled by `max(1440/1280, 900/720) = max(1.125, 1.25) = 1.25`,
  so it renders **1600px wide inside a 1440px box → ~160px of width is clipped (~80px each side)**. That is
  exactly the reported symptom: the Stripe wordmark loses "Strip" on the left and the account-nav loses its
  right edge.
- Compounding bug: the winner page is **never resized back to 1440×900** after promotion to lead
  (`agent.sandbox-v26.js:3096` sets `leadPage = winnerPage` but only re-points the *observer* screencast's
  `maxWidth:1440` — the page DOM stays at 1280 wide), so **every subsequent BEAM round is also 1280×720.**
- Second compounding bug: the final `action-log.json` hardcodes `viewport: { width: 1440, height: 900 }`
  (`agent.sandbox-v26.js:3190`) regardless of which context actually captured the frames. So the log lies about
  the geometry, and the click-coord scaler (`auto-overlay-config.js` `buildScaler`, `Explainer.tsx` `OFFSET_X`)
  trusts 1440 while the pixels are 1280 — coords drift too.

This matches Dennis's clue precisely: *Walk Ultra alone never clips (BEAM=0, 1440×900 lead); only Hermes clips
(BEAM=1, 1280×720 scout winners stretched by `cover`).*

---

## The exact discrepancy (Hermes invocation vs Walk-Ultra-direct)

| | Walk-Ultra-direct (Dennis) | Hermes pipeline |
|---|---|---|
| Entry script | `explainer-agent/make-explainer.sh` | `adapters.py` → `tutorial-maker.sh` → `make-explainer.sh` |
| BEAM default | `BEAM="${BEAM:-0}"` → **OFF** | `tutorial-maker.sh: BEAM="${BEAM:-1}"` → **ON**, exported into `make-explainer.sh` |
| Screenshot source | lead page **1440×900** | winning scout context **1280×720** |
| Fit into 1440×900 `Explainer` card | 1:1, exact | `objectFit:cover` upscales 1.25× → 1600px wide → **clips ~80px/side** |
| Result | clean | **page chrome sliced off both edges** |

`adapters.py` itself passes **no** viewport / window-size / device-scale / zoom flag — it calls
`["bash", "./tutorial-maker.sh", url, goal, out_path]` with only `OPEN_RESULT=0` added (line 351–354). So the
geometry is NOT set in `adapters.py`. The differential is entirely **`tutorial-maker.sh`'s `BEAM=1` default**
flowing into the scout-context viewport in `agent.sandbox-v26.js`.

---

## The fix

There are two viable fixes. **Recommended is (A)** — it keeps BEAM's multi-tab search quality (which is
presumably why Hermes wants it on) and fixes the geometry at the source so any consumer benefits.

### (A) RECOMMENDED — make BEAM scout/winner contexts capture at the same 1440×900 the card expects

In `walk-ultra/explainer-agent/agent.sandbox-v26.js`, change the scout/candidate viewport from 1280×720 to
1440×900 in the three places it is set, and resize the promoted winner page to match:

1. Line **2883** — beam context creation:
   `browser.newContext({ viewport: { width: 1280, height: 720 }, ... })`
   → `viewport: { width: 1440, height: 900 }`
2. Line **1115** (`trySearchScout`) and line **1226** (`executeCandidate`):
   `page.setViewportSize({ width: 1280, height: 720 })`
   → `{ width: 1440, height: 900 }`
3. After line **3096** (`leadPage = winnerPage`), add
   `await leadPage.setViewportSize({ width: 1440, height: 900 });` so post-promotion rounds also capture at
   1440×900. (The lead init at line 1441 already does this for round 0; the promotion path drops it.)

This makes the 1280-vs-1440 mismatch impossible, the screenshots fill the `Explainer` 1440×900 card 1:1, and
the hardcoded `viewport: 1440×900` in the action-log (line 3190) becomes *true* again, so the click-coord
scalers stop drifting too. **File:** `walk-ultra/explainer-agent/agent.sandbox-v26.js`.

> Note the sandbox `RLIMIT_NPROC=512` constraint (BEAM_K already dropped 4→2 for this reason — `tutorial-maker.sh`
> lines 59–60). 1440×900 is a larger surface than 1280×720 but does not add processes/contexts, so it should not
> reintroduce the `pthread_create EAGAIN` thunder. If a per-context memory regression appears, keep BEAM_K=2.

### (B) ALTERNATIVE / defensive — make the renderer tolerant of any capture width

In `walk-ultra/explainer-agent/remotion/src/Explainer.tsx`, change `objectFit: "cover"` → `objectFit: "contain"`
on the four screenshot `<Img>` styles (ClickStep before/after lines ~329 & ~344, GenericStep `frameStyle`
line ~579, DoneStep line ~692). `contain` letterboxes instead of clipping, so a 1280×720 frame fits inside the
1440×900 card without losing the page chrome (it pillarboxes a little instead). This is a robustness backstop;
it does **not** fix the underlying 1280/1440 inconsistency or the wrong click-coord scale, so prefer (A) and
optionally add (B) as belt-and-suspenders. **File:** `walk-ultra/explainer-agent/remotion/src/Explainer.tsx`.

### (C) Quick mitigation if a code fix can't ship in time

Force BEAM off for the Hermes path. Either set `BEAM=0` in `adapters.py`'s `env` for `generate_walkthrough`
(blocked — see below), or change `tutorial-maker.sh` line 61 default to `BEAM="${BEAM:-0}"`. This sidesteps the
1280×720 scout path entirely (single-tab lead = 1440×900 = no clip) at the cost of losing BEAM's multi-tab
search. **File:** `walk-ultra/tutorial-maker.sh` (free to edit) — preferred over editing `adapters.py`.

---

## Which file the fix lives in & whether it's free to edit now

| Fix | File | In `hermes-video-agent`? | Free to edit now? |
|---|---|---|---|
| **(A) RECOMMENDED** | `walk-ultra/explainer-agent/agent.sandbox-v26.js` | No (separate `walk-ultra` repo) | **YES — free.** Not the file another agent is editing; mtime 13:34 today, idle. |
| (B) defensive | `walk-ultra/explainer-agent/remotion/src/Explainer.tsx` | No | **YES — free.** Idle. |
| (C) mitigation | `walk-ultra/tutorial-maker.sh` | No | **YES — free.** Idle. |
| (not the fix) | `hermes-video-agent/adapters.py` | Yes | **BLOCKED — another agent is editing it.** The fix does NOT need this file; avoid it. |

**Bottom line:** the real fix is in **`walk-ultra/explainer-agent/agent.sandbox-v26.js`** (option A), a file in
the *separate* `walk-ultra` project that is **free to edit independently right now**. It does **not** require
touching `adapters.py`, so it is **not** blocked by the agent currently editing `adapters.py`. Do **not** route
the fix through `adapters.py` env vars while it is in flight; the geometry bug isn't there anyway.

---

## Evidence (all source-read, $0, no capture run)

- `hermes-video-agent/adapters.py:341–357` — `generate_walkthrough` invokes `tutorial-maker.sh url goal out_path`
  with only `OPEN_RESULT=0`; passes no viewport/window/scale/zoom.
- `walk-ultra/tutorial-maker.sh:61` — `BEAM="${BEAM:-1}"` (Hermes path → BEAM ON); calls `make-explainer.sh`
  (line 69) and ships its canonical Remotion `Explainer` output (lines 90–108).
- `walk-ultra/explainer-agent/make-explainer.sh:19` — `BEAM="${BEAM:-0}"` (direct path → BEAM OFF); renders the
  `Explainer` composition (line 113).
- `agent.sandbox-v26.js`: lead `--window-size=1440,900` (1401) + `setViewportSize(1440,900)` (1441); scout
  contexts `viewport:{1280,720}` (2883) + `setViewportSize(1280,720)` (1115, 1226); winner screenshots copied
  into rendered `screenshots/step_N_*.png` (3040–3043); winner page never resized post-promotion (3096);
  action-log viewport hardcoded `1440×900` (3190) regardless of real capture size.
- `explainer-agent/remotion/src/Explainer.tsx`: `SCREEN_W=1440, SCREEN_H=900`, `OFFSET_X=(1920-1440)/2=240`,
  `OFFSET_Y=60` (lines 20–23) — matches the `crop=1440:…:240:60` measured in `WALKTHROUGH-CROP-ANALYSIS.md`;
  all screenshot `<Img>` use `objectFit:"cover"` (329, 344, 579, 692) → upscales/clips a sub-1440 frame.
- 1280→1440 cover math: `max(1440/1280, 900/720) = 1.25` → 1280×1.25 = 1600px wide in a 1440 box →
  160px clipped, ~80px per horizontal edge. Matches "logo on left + nav on right sliced off."
