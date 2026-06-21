# UX-IMPROVEMENTS.md — Adversarial Verification

_Read-only verification pass, 2026-06-19. Method: every concrete file/line/string/number claim in
`UX-IMPROVEMENTS.md` was opened against the live source, the seven run ledgers, `runs/index.json`,
and the running `:3030` server (curl). No files edited, no builds, no API calls, no server restart._

---

## (a) VERDICT — overall reliability

**The review is HIGHLY RELIABLE and largely ship-quality.** Essentially every concrete citation
checks out: file paths, line numbers, code strings, event strings, and the dollar figures are all
accurate. I found **no hallucinated findings** and **no fabricated file:line references**. The
prioritization is sound and the "out of scope vs PRODUCTION-READINESS" boundary is honored (it does
not re-list infra issues as UX; where it touches the same code — cancel §4.2, errors §7.1 — it
explicitly cross-references the prod review and argues the *felt* angle, which is legitimate).

What keeps it from a perfect score: a handful of claims are **technically true but rest on an
unstated caveat** (the pay-gate / live-build states the review critiques have **no on-disk fixture**
— every saved run is `earn.status: dev_mode`, gate skipped), and the review **missed two concrete,
in-code defects** in the very phase-track / live-render path it reviewed. Details below. None of
this undermines the Top-7; it sharpens it.

**Confidence: the report can be acted on as-is.** Corrections are refinements, not retractions.

---

## (b) Claims fact-checked — VERIFIED, and the few that need a caveat/correction

### Spot-on (verified exactly as written)
- **§5.1 "No Download/Share anywhere though final.mp4 is served at /runs/<id>/final.mp4" — TRUE.**
  `grep` of `app.js`+`index.html` finds **zero** `<a>` tags, **zero** `download` attribute, and the
  only delivery affordance is `<video controls>` in `viewer()` (`app.js:320-326`) + the literal word
  "delivered" in the caption (`app.js:325`). Confirmed the file IS served:
  `curl :3030/runs/build-linear-54d446/final.mp4` → **HTTP 200**, and all 7 runs have `final.mp4` on
  disk with `stitch.output_path: "final.mp4"`. The "one button, file already served" framing is
  correct. **This is the strongest, best-grounded finding in the report.**
- **§8.2 "Mobile hides the build bar entirely" — TRUE.** `styles.css:490-492`: `@media (max-width:
  940px){ … .rail { display: none; } }`. The build bar lives inside `.rail` (`index.html:39-48`), so
  it is gone on narrow viewports. Verified there is no alternate mobile entry point in the markup.
- **§4.2 / §7.1 "No cancel; 15-min trap; payment_timeout" — TRUE.** `build_runner.py:50`
  `PAYMENT_TIMEOUT_S = 15*60`; `:192-200` sets `status:"failed"`, `phase:"payment_timeout"`. No
  cancel button exists anywhere in `app.js`/`index.html` (verified). `simulate` (`:165-167`) is the
  only fast-exit and it is a dev env flag.
- **§7.1 "Raw Python exception shown to users" — TRUE.** `build_runner.py:125`
  `led2.event("error", "build failed: %s" % e)` writes the raw exception into the ledger; `app.js`
  `liveFailed` (`:630-634`) renders `events[-1].msg` verbatim in red. The exception string reaches the
  customer.
- **§7.1 "payment_timeout rendered as red FAILED" — TRUE.** `build_runner.py:195` sets
  `status:"failed"`; `beginPoll` (`app.js:395`) routes any `status==="failed"` to `finishBuild(…,
  false)` → `liveFailed` red pill. Timeout and crash are indistinguishable to the user. Correct.
- **§3.1 "On-screen price is sub-dollar ($0.92–$1.30)" — TRUE.** `runs/index.json` `price_cents`
  values: 95, 98, 105, 92, 92, 92, 130 → **$0.92–$1.30**. `cents()` (`app.js:11`) renders e.g.
  "$0.92" at the pay gate (`app.js:465`) and as "NET MARGIN 67%" in the P&L. The credibility concern
  is well-founded for a "real agency" pitch.
- **§2.2 "Duplicate 'Script' captions" — TRUE.** `app.js:424` `"Script · the agent priced it before
  shooting"` (awaiting_payment branch) vs `app.js:432` `"Script · the agent wrote it before
  shooting"` (production branch). Same panel, two near-identical captions. Exact.
- **§2.4 "Live P&L ticker hidden at the pay gate" — TRUE.** `renderLive` (`app.js:419-436`): the
  `awaiting_payment` branch (`:422-429`) does NOT call `livePnl`; only the else/production branch
  (`:431-434`) appends `livePnl(l)`. Verified `livePnl` (`:615`) is omitted exactly as claimed.
- **§5.3 "Final cut is section 5 of 6, buried below P&L/gate/studio/source" — TRUE.** `renderDetail`
  section order (`app.js:95-101`): P&L → gate → studio → source media → **Final cut** → money log.
  Final cut is 5th of 6. Correct.
- **§5.4 "demo-4 silent video, VO declined over budget, caption 'audio off'" — TRUE.** demo-4 ledger:
  `voiceover.decision:"decline"`, `stitch.has_audio:false`; event 14 = `"VOICEOVER declined — 40c
  exceeds remaining 8c"`. `viewer()` renders "audio off" (`app.js:324`). All accurate. (Minor: the
  report paraphrases the decline string as "40c exceeds remaining 8c" — the on-disk event is exactly
  that; fine.)
- **§7.4 "demo-2/demo-4 have phase:null → all chips render 'future'" — TRUE.** Both ledgers carry
  `phase: null`; `PHASES.indexOf(null) === -1` (`app.js:566`) so no chip is `done`/`now`. Verified.
- **Line-number citations spot-checked and CORRECT:** `serve.py:115` (https:// prepend), `:119`
  (`duration = int(... or 30)`), `validate_planner.py:114` (`urlopen(req, timeout=300)`),
  `build_runner.py:71-72` (`target_duration_s`, `target_margin:0.6` hardcoded), `:74`
  (`PRODUCER_PACE`), `app.js:357` `startBuild`, `:365` btn disable, `:407/:410` `finishBuild`,
  `:320` `viewer`, `styles.css:192` margin-fig **64px**, `:456` pg-price **58px**. Every spot-check
  matched.

### Internal-jargon leak (§3.3) — TRUE, with one part needing a precision note
- **"MONEY-SHOT" leaks into the customer feed — TRUE and confirmed live.** demo-3 event seq 11 =
  `"MONEY-SHOT: Stripe declined authorization for 'hero-still' — $0.60 cut, no human"`
  (ledger line 399). The string is generated in `orchestrator.py:336` and rendered verbatim by BOTH
  the live `liveAgent` action feed (`app.js:590`, `esc(e.msg)`) and the detail "RUN LOG"
  (`app.js:338-340`). So it genuinely appears in customer-facing UI. **Correct.**
- **`PRODUCER_SIMULATE_PAID` / "dev affordance" — TRUE but PRECISION CORRECTION.** The report says
  this "would appear verbatim in a user's feed in dev runs." Verified the source: `build_runner.py:167`
  emits `led.event("info", "PRODUCER_SIMULATE_PAID=1 — dev affordance: resolving payment as paid
  ($0)")`. It IS rendered (level `info`, not filtered). **Correction/nuance the report should state:**
  this string only fires when the env flag is set (dev path), and **no on-disk ledger contains it**
  (the demos went through DEV MODE, not the simulate-paid pay gate). So it's a real latent leak in the
  live dev path, not something currently visible in any saved fixture. The report's "would appear …
  in dev runs" is accurate but slightly overstates present visibility — flag as latent.
- **"dev · $0" — TRUE.** `index.html:45` label literally reads `mock (dev · $0)` in the primary
  build bar. Confirmed.
- **"stripe login" in the customer surface — TRUE.** `app.js:475` pg-note contains literal
  `<code>stripe login</code>`. Confirmed. (Caveat: only renders in the `awaiting_payment` pay-gate,
  which — see below — has no saved fixture, so it's only seen in a real live build.)

### The one systemic caveat the review should disclose (affects §2.1, §2.4, §3.3 simulate, §4.x, §9.3)
**Every saved run is `earn.status: "dev_mode"` (payment gate skipped); there is NO on-disk
`awaiting_payment` or `payment_timeout` fixture.** Verified all 7 ledgers: demo-1/2/3/4 have
`phase:null, earn.status:dev_mode`; the three `build-*` runs have `phase:"delivered",
earn.status:"dev_mode"` and event seq 3 = `"EARN: DEV MODE — no Stripe key, payment gate skipped"`.
**Implication:** the pay-gate UX the review critiques (the price card, the `stripe login` note, the
"trapped 15 min," the missing pay-gate P&L) is **real in code** (`build_runner._payment_gate` +
`payGate()` render path both exist and are correct) but is **exercised only on a live `mode:real`
build with a Stripe key**, not by any browsable demo. This does NOT make the findings wrong — the
code paths are present and the critique holds — but the review reads as though these states are
routinely visible. It should add one line: "these pay-gate states require a live keyed build; the
seeded demos all run DEV-MODE and skip the gate." For a judge clicking through the seeded runs, the
pay-gate findings won't reproduce without a live build.

### Nothing found WRONG / fabricated
No claim was found to be false, mis-cited to the wrong file/line, or unsupported. The review is clean
on grounding.

---

## (c) Material MISSING items (re-examined the full arc; these are concrete, in-code, not in the report)

1. **MISSED IN-CODE BUG — the live phase track skips `pricing` and breaks on `earning`.** This sits
   squarely in the live-render path the review covered (§2.x, §7.4) and is more concrete than 7.4's
   null-phase note. `PHASES = ["planning","pricing","awaiting_payment","producing","voiceover",
   "stitching","delivered"]` (`app.js:354`). But:
   - The live `build_runner` path sets only `planning → awaiting_payment → producing` (`build_runner.py:82,159,111`)
     — it **never sets `pricing`**, so the "pricing" chip never lights during the pre-pay phase; the
     track jumps planning→payment, making the chip purely decorative in the live arc.
   - After payment, `orchestrator.orchestrate` sets `phase:"earning"` (`orchestrator.py:170`).
     `"earning"` is **not in `PHASES`**, so `PHASES.indexOf("earning") === -1` and — exactly like the
     §7.4 null bug — **every chip renders "future" (stalled) for the whole earning phase of a live
     build.** The review flagged this only for stale demos (§7.4 LOW); it is in fact reachable in a
     normal live run and deserves to be folded into §7.4 and bumped, because it makes a *live* build
     look hung at the moment right after the user pays. (Fix: add `earning` to `PHASES`, or have
     `build_runner` set `pricing` and skip `earning`; align the array to the actual phase vocabulary.)

2. **MISSED — the build is single-flight but the UI never says so / can't queue.** `serve.py` writes
   each build to its own `run_dir` and `/api/active` returns running ledgers, but there is no
   client-side guard preventing a user from clicking Build again while one is in flight (`startBuild`
   only disables the button until `finishBuild`; a second tab or a resumed poll can race). The review
   covers the *button* state (§8.4) but not the "what if I start a second build" UX. Minor, but a
   judge may try it.

3. **MISSED — no audio/mute affordance discoverability on autoplaying storyboard/agent videos.** The
   live storyboard cards and the agent "browser" video autoplay `muted loop` (`app.js:584,600`) — fine
   — but the *final* viewer is `controls` with sound; there is no "unmute"/volume cue tying the silent
   build preview to the audible deliverable. Small cohesion gap adjacent to §5.4.

4. **MISSED — `created_at: null` for live builds means runs sort/label with no timestamp in the rail.**
   `index.json` shows `created_at:null` for all three `build-*` runs (live), vs ISO strings for demos.
   The rail (`renderRail`, `app.js:47-67`) shows no date at all, so a user with many builds can't tell
   newest from oldest. (Prod review flags `created_at:null` as §2.3 LOW infra; the *UX* consequence —
   no recency cue in history — is a distinct, legitimate UX item not in this report.)

5. **MISSED — the "REAL · source" vs "placeholder" badge (`app.js:111-112`) is the only signal that a
   mock build is placeholder footage, and it's buried in section 4 (source media).** The review's §3.2
   notes the finished view doesn't loudly say "this is a $0 mock with placeholders," but doesn't point
   at the existing-but-buried `sm-badge ph` "placeholder" tag as the half-built honesty hook to promote.
   Concrete hook for the §3.2/§5.4 fix.

6. **MISSED (a11y, beyond §8.3) — there is literally one focus style in the whole stylesheet.**
   Verified: the ONLY `:focus` rule is `styles.css:347` (`.build-in:focus`), and there is **zero**
   `:focus-visible` and **zero** `aria-live` anywhere (`grep` confirmed). The review's §8.3 is right
   but undersells how bare it is — every `<button>` (run cards, studio tabs, pay, refresh) has only the
   UA default ring. Worth stating as "one focus rule exists, for the URL input only."

None of these overturn the report; #1 is the most important addition (a real live-build visual bug),
and it strengthens §7.4.

---

## (d) Corrected Top-priority shortlist FOR WINNING (usefulness / viability / presentation, due 6/30)

The report's Top-7 is well-judged. I'd keep its #1 unchanged, **promote the jargon/error-leak cleanup
and add the phase-track fix**, and **demote the plan-review step** as premature for the deadline.

**Corrected ranking:**

1. **Download / Share on the finished video (report §5.1).** UNCHANGED #1. Highest leverage, ~1
   button, file already served (verified 200). Closes the core promise. Nothing beats it.

2. **Make delivery a reveal — lead with the video, collapse the receipt (report §5.2/§5.3/§9.1).**
   UNCHANGED #2. This is the single biggest *presentation* win for a judge: the current anticlimax
   (live drama → spreadsheet) actively hurts the demo. High ROI.

3. **Clean the leaks + fix the failed/timeout states + the phase-track bug (report §3.3/§7.1/§9.3 +
   MISSED #1).** **PROMOTED from #7 to #3.** Rationale: these are LOW-effort, HIGH-presentation, and
   they're the things most likely to *embarrass the team live in front of judges* — "MONEY-SHOT" in
   the customer log, a raw Python traceback rendered red, `stripe login` in the pay card, and a phase
   track that goes all-grey ("hung") right after the user pays (MISSED #1). A judge will see these in a
   30-second click-through. Cheap to fix, disproportionately protective of the "finished product" read.

4. **Cover the ~90s planning dead-air + add Cancel (report §2.1/§4.2/§8.4).** Was #3. Strong, but for
   a *scripted demo* the team controls the URL and can pre-warm; the dead-air bites a judge doing a
   cold live build. Keep it high, just below the leak cleanup which is lower-effort/higher-certainty.

5. **First-run framing + price/duration anchor in the input (report §1.1/§1.2/§1.3).** Was #4.
   Genuinely important for "usefulness" and the cold-open impression. Medium effort. Keep ~here.

6. **Resolve the sub-dollar price credibility (report §3.1).** Was #5. Mostly a *decision* + a config
   line — but it's a positioning call for Dennis, not pure dev. The cheapest credible move (frame the
   cents as "marginal COGS-based unit economics, demo" rather than a retail price) is a copy change and
   pairs naturally with #2's delivered-state redesign. Keep, but it's a decision-gated item.

7. **Pay-gate P&L + deliverable summary on the pay card (report §2.4/§3.4).** **PROMOTED into the
   top-7** (replacing the plan-review step). Low effort (the `livePnl` and shot-list data already
   exist), directly reinforces the product's whole thesis (margin/guardrail) at the decision moment,
   and demos well. Better deadline ROI than a plan editor.

**DEMOTE out of the Top-7 for the deadline: plan-review/approve/edit before paying (report §6.1,
its #6).** It's the right *product* instinct and a great "you direct the producer" story, but it's
**MEDIUM-HIGH effort** (editable VO, scene reorder/remove, model swap, then re-price round-trip) and
risks introducing money-correctness bugs near a 6/30 freeze. For *presentation/viability* scoring it's
out-leveraged by items 3 and 7. Park it as the headline "what's next" slide rather than build it now.

**Also note one report item that's lower-impact than its placement implies:** §2.5 (scene "N of M"
counter) and §6.3 (re-run from old run) are nice but won't move a judge; keep them MEDIUM/LOW as the
report already does. The report does not over-rank anything in its Top-7 except the plan editor (#6),
addressed above.

---

## (e) No-overlap sanity check vs PRODUCTION-READINESS-REVIEW.md

**Confirmed clean.** The UX review explicitly scopes infra/security/reliability/perf out (header,
lines 4-9) and where it brushes the same code it flags the *felt* experience and cross-references the
prod review by section:
- Cancel: UX §4.2 explicitly cites "production review §7.1" — verified `PRODUCTION-READINESS-REVIEW.md`
  §7.1 "No way to cancel/abort a build — HIGH" exists (line 312). Different lens (felt trap vs missing
  endpoint). Legitimate.
- Errors: UX §7.x (felt error states) vs prod §6.2 "Errors surface to the UI thinly" / §4.2 (Nemotron
  timeout) — UX argues the *customer-facing copy*, prod argues the *engineering*. No double-counting.
- The prod review's BLOCKERs (unauth `/api/build`, client-controlled `mode:real`, path traversal,
  concurrent-build TSX corruption) appear **nowhere** in the UX review — correctly, they're infra.

The two documents are complementary, not redundant. The UX review did not smuggle infra issues in as
UX.
