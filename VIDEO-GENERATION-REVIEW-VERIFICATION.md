# Verification — VIDEO-GENERATION-REVIEW.md

_Adversarial, read-only verification, 2026-06-19. No edits, no builds, no money, no paid APIs.
Method: opened every cited `file:line`, re-ran `ffprobe`/`cropdetect`/`loudnorm` on the real runs
(`demo-1-approve`, `demo-3-decline`) and mock runs (`build-stripe-9e7829`, `build-linear`, `build-notion`),
and extracted + visually inspected frames from the walkthrough, the Seedance cinematic, the GPT-Image-2
still, and the motion-graphic divider. Temp PNGs deleted after inspection._

## VERDICT

**The review is reliable and well-grounded — every load-bearing technical claim checks out against the
actual code and the actual pixels.** All five claims the orchestrator asked me to fact-check are
TRUE. The Top-7 ordering is sound: the #1 item (walkthrough letterbox) is correctly identified as the
biggest impact-per-effort win. Corrections needed are minor: two off-by-one/range line citations, one
**understated** black-bar percentage (27% should be 33%), and one **conflated** walkthrough-share stat
(demo-3 is 52%, not 43%). The review's one real omission that matters for winning is **audio loudness
normalization** — the finals ship at ~−20 LUFS, ~6 LU under the streaming standard, and the review never
mentions it. Net: trust the review; apply the small corrections below; add loudness + a couple of missing
items to the shortlist.

---

## Claim-by-claim

### Claim 1 — Letterbox defect (walkthrough padded with black; inconsistent with finish_cut crop) — **TRUE, and UNDERSTATED**
- `apply_real_media.py:31` — `scale=…:force_original_aspect_ratio=decrease, pad=…:color=black` — CONFIRMED verbatim.
- `finish_cut.py:61` — `scale=…:force_original_aspect_ratio=increase, crop=…` — CONFIRMED verbatim. The
  inconsistency (swap step letterboxes, finish step crops the already-letterboxed frame) is real.
- `cropdetect` on the real demo-1 walkthrough (`03_walkthrough.mp4`):
  - t≈2s: `52× crop=1440:982:240:60`
  - t≈8s: `59× crop=1440:960:240:60`
  - demo-3 (`02_walkthrough.mp4`) t≈5s: `35× crop=1440:960:240:60`, `24× crop=1440:986:240:60`
  Active content is **1440×960 inside 1920×1080, offset x=240/y=60** — exactly the review's `1440:960:240:60`.
- **Correction:** the black fraction is **33.3%**, not the review's "~27%": (1920·1080 − 1440·960)/(1920·1080)
  = 691200/2073600 = 0.333. The review *undersells its own strongest finding*. Bump the number to ~⅓.

### Claim 2 — Direction rendered as on-screen copy (`brief[:48]`) — **TRUE (a real, embarrassing bug)**
- Extracted frame from `build-stripe-9e7829/clips/04_motion-divider.mp4` literally renders:
  **"Simple animated divider with the text 'Built for"** under a "2" badge. This is the planner's *scene
  direction* printed verbatim and truncated — confirmed visually, not just inferred.
- Root cause: `remotion_codegen.py:322` `return brief[:48] or "Section", "", "", "2"` inside `_copy_from_brief`,
  reached **only when `scene.get("type") == "motion_graphic"`** (guard at line 321). So the review is correct
  that it affects *only* `motion_graphic` scenes — title/divider-by-id scenes use the safe word-extraction
  fallback (line 324-326). Among the 5 verified runs only `build-stripe` had a motion_graphic, and it
  rendered the bug; the demos have no motion_graphic scene, so the demo cut is not affected.
- **Citation nit:** review says `remotion_codegen.py:321`; the `brief[:48]` line is **322** (321 is the guard).
- "PRODUCER CUT"/"CALL TO ACTION" leak: source strings are lowercase **"Producer cut"** (`:319`) and
  **"Call to action"** (`:316`), but the templates apply `textTransform: "uppercase"` to the kicker, so the
  **on-screen text really is "PRODUCER CUT"/"CALL TO ACTION"** — the review's caps rendering is accurate.
  Severity verdict: **"PRODUCER CUT" is a fair HIGH-ish flag** — "cut" is editing-room/internal language and
  reads as a placeholder on a client open card; "CALL TO ACTION" is more "generic kicker that forgot to be
  written" than "leaked internal tooling," so MEDIUM is fairer for that one. The review lumping both as HIGH
  is *slightly* overstated for "CALL TO ACTION" but defensible — neither is real creative copy. (Citation
  range "315-319" is approximately right: actual 316 + 319.)

### Claim 3 — Walkthrough content (green internal card, docs not product, 14s ≈ 43%) — **TRUE on all three**
- **Green internal card:** frame at t=1s is a full-bleed black card, **"EXPLAINER AGENT · FEASIBILITY DEMO /
  Open the Stripe Dashboard… / Nemotron 3 Super 120B · driving Chromium · docs.stripe.com"** with the kicker
  in **studio-default green (#7CFFB2)** — confirmed visually. Off-brand for Stripe-purple. CONFIRMED.
- **Docs not product:** frames at t=7s and t=12s show **docs.stripe.com** ("Developer resources" landing,
  then a "Developers Dashboard" *doc article*) — documentation *about* the dashboard, not the live app
  performing the task. CONFIRMED. Also confirms the green QA-caption claim: lower-thirds read
  "2 Click 'Developers Dashboard…'", "3 Click 'Developers'" baked in green.
- **Duration:** `03_walkthrough.mp4` = **14.00s** (ffprobe). demo-1 final = **32.30s** → walkthrough = **43.3%**. CONFIRMED.
- **Correction (conflation):** the review says "14s (demo-1/3) — 43% of the 32.3s real cut." demo-3 final is
  **26.73s, not 32.3s** (it has no hero-still scene — 4 clips not 5), so in demo-3 the same 14s walkthrough is
  **52.4%** of the cut, *worse* than demo-1. The "43% of 32.3s" figure is demo-1-only; demo-3 should be cited
  separately (and it strengthens the argument).
- Windowing claim verified against `HANDOFF.md:122-123` ("66s canonical Explainer … trim/window it") and
  `:159` (NEXT #6 "shorten the walkthrough to ~7-8s"). The 66s WAS windowed to 14s but the window kept the
  intro card and is still 2× too long. Review's framing is correct.

### Claim 4 — Uniform specs across all 5 runs — **TRUE**
All five `final.mp4` re-probed: **1920×1080, 30/1 fps, h264, AAC 48000 Hz stereo**, no drift.
Durations: demo-1 32.30s, demo-3 26.73s, build-stripe/lin/notion 30.00s each. Per-clip probes also uniform
(title clips 3.05/4.05/5.06s, cinematic 6.03/6.06s, walkthrough 14.0s real / 8.04s mock). The fast-concat
assumption (`adapters.stitch`) is valid. CONFIRMED.

### Claim 5 — GPT-Image-2 still text garble under hold — **TRUE**
Frame from `demo-1/clips/02_cine-hero-still.mp4`: a convincing dark Stripe "Developers" dashboard — the
"stripe" wordmark and layout read as real at a glance, **but the body text is genuinely garbled** (API-key
rows, nav labels, panel headings, the "Create" button are fuzzy non-text). It would pass for ~1s but the
clip **holds it static for 6.0s** (ffprobe), where the fake text is catchable. Nuance: the review says "hold
6s **or zoom it**" — `finish_cut.py:63` applies the zoompan push-in **only to `walkthrough` type**, so the
still is *not* zoomed, only held. The "held 6s" risk is real; "zoom" is hypothetical-if-you-did. Minor.
The "minimal-motion + overlay-real-text" workaround being Seedance-only (not applied to stills) is correct —
no overlay-text compositing step exists for cinematic in `finish_cut.py` or `adapters.py`.

---

## Other cited lines spot-checked (all accurate)
- `orchestrator.py:223-237` free-type routing — CONFIRMED (FREE_TYPES at :48; branches 227/232/235/237).
  Minor: cinematic routing is actually in the *paid* path at :274/276/302/305, not inside 223-237 — the
  review's prose folds cinematic into the same paragraph, slightly imprecise but the routing description is right.
- `adapters.py:121` cinematic passes `scene.get("brief","")` verbatim, no negative/style prompt — CONFIRMED.
- `adapters.py:145` Seedance `--duration min(15, max(4, …))` — CONFIRMED.
- `adapters.py:189-205` walkthrough = raw `tutorial-maker.sh` capture, no production tool — CONFIRMED.
- `adapters.py:232-234` `generate_overlay` silently degrades to flat synth color on Remotion failure — CONFIRMED.
- `adapters.py:298` edge-tts voice map; `:307` ElevenLabs wired — CONFIRMED.
- `finish_cut.py:27` grade `eq(contrast=1.07:sat=1.14:bright=0.012:gamma=0.98),unsharp=3:3:0.25` applied to
  ALL clips; `:71` single 0.45s `xfade=fade`; `:80-86` real sidechain-duck mix — all CONFIRMED.
- `finish_cut.py:47` `total = sum(durs) - XF*(n-1)` and the plan(10s)-vs-delivered(14s) walkthrough divergence
  — CONFIRMED (demo-1 plan.json walkthrough `duration_s:10`, delivered 14.0s; `apply_real_media.normalize`
  doesn't trim to planned duration).
- `plan_job.py:82` filler fallback script — CONFIRMED verbatim.
- `planner-prompt.md` :93 "Prefer at least one of each", :99 VO timing, :104 voice="Adam" — CONFIRMED.

---

## CLAIMS WRONG / OVERSTATED / MIS-CITED (corrected)
1. **Black-bar % understated:** "~27%" → **33.3%** (cropdetect `1440:960:240:60`; 691200/2073600). Fix upward.
2. **Walkthrough-share conflated:** "14s … 43% of the 32.3s real cut (demo-1/3)" — true for demo-1 only.
   demo-3 final is **26.73s** → walkthrough is **52.4%** there. Cite both; demo-3 is the worse case.
3. **Line citations off by a hair:** `brief[:48]` is `remotion_codegen.py:**322**` (review says 321); hardcoded
   kickers are lines **316/319** (review says 315-319 — close). The padded-vs-cropped sites (`apply_real_media.py:31`,
   `finish_cut.py:61`) are spot-on.
4. **"hold 6s OR zoom" (still garble):** zoompan is walkthrough-only; the still is held, not zoomed. Drop "or zoom."
5. **"CALL TO ACTION" as HIGH "internal tooling leak":** mildly overstated — it's generic-placeholder copy, not
   internal-tool language. "PRODUCER CUT" is the genuinely bad one. Net flag still valid; severity split.

None of these change the review's conclusions; if anything #1 and #2 make the headline defect *worse*.

---

## MOST IMPORTANT MISSING ITEMS (not in the review)
1. **HIGH — Audio loudness normalization (NEW; the review's biggest omission).** Re-measured with
   `loudnorm=print_format=summary`:
   - demo-1 final: **Input Integrated −19.8 LUFS, True Peak −6.2 dBTP, LRA 1.8 LU**
   - build-stripe final: **Input Integrated −20.6 LUFS, True Peak −6.6 dBTP**
   Streaming target is ~−14 LUFS (YouTube/social). The submission will play **~5–6 LU quieter** than other
   entries — a real perceived-quality hit on a competition stage, fixable with one `loudnorm`/two-pass at −14
   LUFS, −1 dBTP in `finish_cut`. The review covers the *mix* (ducking) but never the *delivery loudness*. Add this.
2. **MEDIUM — Walkthrough not trimmed to planned duration.** `apply_real_media.normalize` re-encodes the
   14s source as-is; the plan asked for 10s. There's no `-t` trim to the scene's `duration_s`. The review notes
   the divergence in §6/§8 but doesn't pin that `apply_real_media` is the place to fix it (a `-t duration_s`
   on the video branch would both rebalance the cut AND drop the trailing docs frames — cheap, ties to Top-2).
3. **LOW-MEDIUM — color consistency across heterogeneous sources** is asserted-good by the review but the
   single global grade is applied uniformly; the Seedance globe is the only true-camera source and the
   amber/blue happens to suit Stripe — for a non-blue brand the generated cinematic could clash. The review
   flags this (§2 LOW) but it deserves a "verify per-brand" gate, not just a note.
4. Captions/SRT, real logo, 9:16/1:1 variants, thumbnail, music-library/licensing — all already in the
   review's §10 (MISSING) list; no need to re-add. Music *licensing* specifically: one fixed
   `assets/music-bed.mp3` with no license record — the review mentions it (§10 MEDIUM) but for a *submission*
   this is a compliance risk worth elevating (provenance must be clean for a judged entry).

---

## CORRECTED TOP-PRIORITY SHORTLIST (for WINNING: usefulness/viability/presentation)
The review's Top-7 ordering is sound; this is the same spine with the corrections folded in:

1. **Fix the walkthrough letterbox (fill, not pad).** `apply_real_media.py:31` `decrease`+`pad(black)` →
   `increase`+`crop`. Reclaims **33%** (corrected from 27%) of the most-on-screen scene. Tiny diff, biggest lift.
2. **Trim the walkthrough to ~7-8s AND drop the green "EXPLAINER AGENT" intro card + green QA captions.**
   Add `-t duration_s` in `apply_real_media` and window past the intro card. Rebalances the cut (43% demo-1 /
   **52% demo-3**) and removes the off-brand internal-tooling tell. (Highest presentation risk after #1.)
3. **Kill placeholder/meta copy on authored cards.** Fix `remotion_codegen.py:322` `brief[:48]` (renders the
   *direction* "Simple animated divider with the text 'Built for") and replace `:316/:319` "Call to action"/
   "Producer cut" kickers. Two obvious "this is a template" tells, cheap to remove.
4. **NEW — normalize delivery loudness to ~−14 LUFS / −1 dBTP in `finish_cut`.** Finals are ~−20 LUFS;
   on a judged stage the video will sound conspicuously quiet. One filter, large perceived-quality ROI.
5. **Don't hold the GPT-Image-2 still 6s with fake text.** Steer the prompt off legible text ("soft focus,
   no readable UI text") or rebuild the UI in Remotion / use a real screenshot for UI plates (`adapters.py:128-141`).
6. **`cinematic_prompt(brief, brand)` builder + burned-in captions/SRT.** Wrap the bare brief with style +
   negative prompts + brand accent (`adapters.py:121`); add VO-synced captions in `finish_cut` (muted-watch table stakes).
7. **One ElevenLabs pass on the submission hero + rough per-scene VO sync.** `--vo elevenlabs` is wired
   (`adapters.py:307`); biggest perceived-quality-per-dollar lift. Confirm music-bed license provenance while here.

_Out of scope (other reviews): render race, /api/build auth, restart resilience, static-server lockdown._
