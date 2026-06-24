# Self-improving loop — WIN RUN (read FIRST on each firing)

_Self-paced /loop. MISSION: win the Hermes×NVIDIA×Stripe hackathon (due 2026-06-30) —
beat the rival VED/StoryPrompting. Dennis is ASLEEP (~02:00, 2026-06-25) — FULL AUTONOMY.
Spend ceiling: **$20 EXTERNAL** (paid Nemotron 550B for sharper diagnoses; flag before any
Higgsfield burst). `main` = untouched fallback. Backup: commit+push after every change._

## ✓ DENNIS BLOCKERS CLEARED (~03:40) — railway login + Docker BOTH DONE
P0 redeploy in flight (agent `ab03a8679fd3f0e23`: redeploy → bind 8GB → enqueue → prove delivery);
NemoClaw in flight (agent `aebbe0d84f2a68543`: recover gateway → install in walk-ultra → capture).
The two asks below are now satisfied — kept for context.

## ~~⚠ WAITING ON DENNIS~~ (CLEARED — do first thing — unblocks P0 + the NVIDIA sandbox)
**1) Run `railway login`, then ping me** — unblocks P0 "works for everyone". The hosted worker
can't deliver until it's REDEPLOYED to bind the new 8GB Hobby plan (still the starved ~512MB
container `worker-2808d1734f1f`, SIGKILLs on trivial ffmpeg). After login I redeploy (`railway
up` — redeploy NOT upgrade, **no spend**) → re-enqueue → re-poll to `delivered`.
**2) Start Docker Desktop** (GUI, ~30-60s) — unblocks the NemoClaw/NVIDIA sandbox capture. The
local Docker daemon is down so NemoClaw's OpenShell gateway can't start (every sandbox `exec` =
Connection refused). NemoClaw + the NVIDIA inference route are healthy; only the sandbox layer
needs Docker. Then I run install+capture (prefer the `walk-ultra` sandbox — it carries the
`playwright-cdn` policy `promo-agent` lacks). Full path in `.handoff-nemoclaw.md`.

## WIN THESIS
VED is real, polished, spectacular — but makes a SYNTHETIC FILM. We win on GROUNDING +
RELIABILITY + INTELLIGENCE: a hosted tool anyone can use that READS a real product,
DIAGNOSES how it fails to convert (the Conversion Read), and PRODUCES the video that fixes
it — billed autonomously, Stripe declining the agent's own over-budget spend, no human.
Don't out-spectacle the film; out-substance it.

## DESIGN GATE (Dennis is meticulous — NEW HARD REQUIREMENT)
Every UI surface AND every produced video frame must clear a researched design bar.
Reference: `docs/DESIGN-BEST-PRACTICES.md` (Track C DONE ✓, verified grounded — 399 lines,
concrete numbers/ratios/frames/beziers). NO polish or video ships that doesn't meet it.
Judge videos WHOLE (ffmpeg contact sheet, scene-by-scene), never a frame.
KEY PALETTE FACT (corrects an earlier wrong "dark console" assumption): the **Producer Console
is a LIGHT theme** — `--bg #F4F5F7`, cards `#FFFFFF`, ink `#14171C`, coral `#D6351C` (primary),
green `#0E9F6E` (approve), crimson `#C01A2B` (decline-ONLY), Hanken Grotesk + Newsreader, easings
`--ease-rise` / `--ease-spring`. The **video output is DARK** (`#0C0E12`). The Conversion Read
Analysis panel must use the LIGHT console tokens — never apply the wrong palette to the wrong surface.

## ACTIVE TRACKS (launched ~02:00; monitor + verify each firing)
- **Track A — Cloud delivery (P0)** agent `a26ec6e905f7463a4`: prove the hosted worker
  delivers on the new 8GB (enqueue a $0 build → InsForge `runs.status` → `delivered`, else
  diagnose+fix). BLOCKER WATCH: Railway CLI is UNAUTHORIZED — if it needs logs/redeploy that's
  Dennis's `railway login` (queue it for morning).
- **Track B — Conversion Read build (P1)** agent `a7a1c8c464bdeb474`: execute the 15-task TDD
  plan in `walk-studio-conversion-read` (`conversion-read`), test-first, commit+push per few
  tasks. The differentiator. Flag-gated `PRODUCER_CONVERSION_READ`; `main` byte-identical when off.
- **Track C — Design research** agent `afdaeb7c72280db13`: write `docs/DESIGN-BEST-PRACTICES.md`
  (UI/UX + motion-graphics, CONCRETE rules). Feeds the DESIGN GATE.
- Watchdog: bg `bmxm3deqt` (alerts if any track's output stalls >180s).

## PRIORITIES (top-down; tracks run parallel where independent)
- **P0** hosted delivery works for everyone (Track A).
- **P1** Conversion Read built + integrated (Track B) → then ADVERSARIALLY verified.
- **P2** Stripe money-shot: lock the autonomous Issuing decline as a clean demo artifact;
  experimentally land `webhook_declined` (high card limit + webhook up; see prior lessons).
- **P3** NemoClaw/NVIDIA: wire sandbox capture + write the TRUE security narrative.
- **P4** Polish to the DESIGN GATE: dashboard Analysis panel + run view + a recorded demo;
  judge whole videos per real brand (Stripe, Linear, Notion, Vercel, Beside, Ashlar).
- **P5** The pitch: tight narrative + demo cut hitting all 3 sponsors + the grounding wedge.

## SELF-IMPROVING MECHANICS (each firing)
1. Read this file + `LESSONS.md`. Check the 3 tracks (completion notifications + watchdog).
2. When a track completes: ADVERSARIALLY VERIFY with a fresh verifier subagent (no
   self-certification) before accepting; judge any video whole.
3. Advance the next highest-impact open priority — dispatch fresh-context subagent(s), fan out.
4. Log the lesson below; promote recurring ones to a `feedback_*` memory. Post-mortem any
   premature subagent failure (forensic root-cause, patch the brief, then re-dispatch).
5. Commit+push backups on every branch. Gate money/outward for Dennis's morning.

## GUARDRAILS (hard)
`main` untouched (branches only). Money + irreversible/outward GATED → queue for Dennis,
never execute (except ≤$20 external as authorized). Secret-scan → commit → push each change.
No unilateral aesthetic flips. No premature "ship what's done" — match Dennis's commitment.

## WORKING DIRS
- `hermes-video-agent` (`main`) = local demo baseline (real Stripe Issuing decline; demo runs
  here). DON'T commit to main.
- `walk-studio-hosted` (`hosted-saas`) = cloud build + this loop-state + the design doc; backup target.
- `walk-studio-conversion-read` (`conversion-read`) = the Conversion Read feature build.

## MORNING SUMMARY (write before Dennis wakes)
Leave a tight summary: what shipped, what was learned, what's waiting on him (esp. `railway
login` if Track A needs it), and the state of each priority P0–P5.

## Lessons log (append each pass; prior lessons in git history)
- iter-winrun-kickoff (~02:00, 2026-06-25): launched 3 parallel tracks (cloud delivery /
  Conversion Read build / design research) + watchdog `bmxm3deqt`. $20 external ceiling.
  Design is now a hard gate. Awaiting track completions.
- iter-winrun-1 (~02:15): **Track C DONE + verified** — `docs/DESIGN-BEST-PRACTICES.md` (399
  lines; cited tokens confirmed real in styles.css; LIGHT console / DARK video). The polish bar.
  **Track A DONE → P0 BLOCKED on Dennis `railway login` + REDEPLOY** — the 8GB upgrade is INERT
  until redeploy (worker still the starved same-container `worker-2808d1734f1f`; SIGKILL on
  trivial ffmpeg). APPLIED a real worker fix: `run.js:137` now also accepts
  `completed_with_warnings` (was `delivered`-only), so a partial-but-shipped video isn't thrown
  away — committed, ships on redeploy, confirms on the first post-redeploy render. **Track B
  (Conversion Read build) still running.** Held off new speculative tracks (P2 Dennis-gated,
  P3 premature pre-sandbox, P4 polish blocked on B) — disciplined wait, not idle fan-out.
- iter-winrun-2 (~02:35): **Track B (Conversion Read) DONE** — 15 TDD tasks, all tests green,
  pushed `conversion-read` @323dca3 (14 ahead of main; flag-OFF byte-identical). The
  differentiator is built. Dispatched 2 state-isolated tracks: **verifier `afe1c81186b235fe4`**
  (adversarial e2e — does the Read genuinely drive the plan + render a video; flag-OFF parity;
  whole-video judgment vs the design bar; symlink heavy deps from main for the e2e) + **NemoClaw
  `a2a7b3ce91dea1692`** (P3 NVIDIA story — install Playwright+Chromium in `promo-agent` + test
  capture, fail-fast if down). Retired watchdog bmxm3deqt; new watchdog over the 2. P4 polish
  HELD until the verifier confirms the feature (don't polish something that might be buggy).
- iter-winrun-3 (~02:40): **NemoClaw track DONE → BLOCKED on Dennis (start Docker Desktop).**
  NemoClaw up (v0.0.50; sandboxes promo-agent/walk-ultra/walk-ultra-2) + NVIDIA inference route
  healthy, but the local Docker daemon is DOWN → OpenShell gateway can't start → every sandbox
  `exec` = Connection refused. Fail-fast (didn't spin). Integration path + key finding
  (`promo-agent` lacks `playwright-cdn` egress → use `walk-ultra`) in `.handoff-nemoclaw.md`.
  Verifier `afe1c81186b235fe4` still running — disciplined wait (P4 polish held on it; P2 + P3
  now both Dennis-gated; nothing non-premature to dispatch).
- iter-winrun-4 (~03:00): **Conversion Read adversarially VERIFIED — the feature WORKS.**
  Prescribe→produce confirmed LIVE (real Nemotron on linear.app: scored proof=1/show=1 → outcome
  headline → 27s video opens on the fix, real customer logos = proof made visible, single CTA;
  on the design bar; LIGHT panel tokens correct). All tests green, flag-OFF byte-identical, $0.
  BUT the verify caught a **demo-critical bug the unit tests MISSED**: `conversion_read` is
  clobbered out of the DELIVERED ledger (orchestrator rebuilds Ledger; VO-tail reloads disk_led
  w/o it) → Analysis panel renders EMPTY on finished runs. Dispatched TDD fix-and-reverify
  `aae194149a8626d50` (re-attach to the delivered ledger, both VO-on/off; new test asserts the
  on-disk delivered ledger — the gap the old tests left). Watchdog retired → new over the fix.
  **LESSON (promote): test/verify the DELIVERED artifact, not the in-memory run-level state** —
  the unit tests checked `led` in memory; only adversarial e2e caught that the on-disk delivered
  ledger lost the data. NEXT after fix lands + demo-ready: per-brand build→judge cycles (P4
  quality across Stripe/Notion/Vercel, judge whole) — that's the remaining autonomous work; P0/P3
  stay gated on Dennis.
- iter-winrun-5 (~03:15): **Ledger fix DONE + verified → Conversion Read is DEMO-READY.** The
  fix-agent applied the fix correctly but STALLED on its e2e build (idled waiting for a completion
  notification that never reaches a subagent). I took over: confirmed the fix (re-attaches
  conversion_read to the delivered ledger after orchestrate; guarded; both VO paths), ran the
  authoritative tests myself — all 7 green incl. `test_delivered_ledger_carries_read_vo_off/on`.
  Cleaned the agent's leftovers (reverted generated active.tsx; removed the `.venv-capture`
  symlink), committed+pushed (build_runner.py + tests). Differentiator built+verified+demo-ready
  (linear.app). Dispatched per-brand validation `a5cb2f7290f18039d` (Stripe — build+judge whole vs
  the design bar; anti-stall: background build + poll, not wait-for-notification). **LESSON
  (promote): a subagent that runs a >600s build then idles for a completion notification STRANDS**
  — subagents aren't re-invoked by background processes; the orchestrator must finish it, OR the
  build subagent must background+poll in <600s chunks.
- iter-winrun-6 (~03:25): **Stripe per-brand validation PASSED — demo-quality.** Delivered a 30s
  video; the delivered-ledger fix holds on a 2nd brand; the diagnosis is real+grounded (rewards
  Stripe's strengths proof4/cta4, flags only the vague hero; cites real $1.9T/99.999% metrics);
  whole-video on the design bar, no violations. BUT caught a **demo-reliability bug**: on the FREE
  Nemotron tier the Read DEGRADES to a generic fallback ~2 of 3 runs — the 120B packs comma-
  separated strings into `evidence`, breaking JSON parse (analyze.py:159 →
  validate_planner.extract_json:483). A live judge demo would show a generic diagnosis 2/3 of the
  time. Dispatched JSON-hardening fix `a5895796eaaee1bb1` (tighten analyzer-prompt + analyze-local
  robust json-repair + retry budget; TDD on the exact malformed JSON; target degrade <1/5; MUST
  work on free — the hosted product runs on free; 550B is a quality bonus, not the reliability
  crutch). Watchdog `bpipa8zti` over the fix. After this the differentiator should be robustly
  demo-ready; remaining wins (P0 cloud, P3 NemoClaw) stay gated on Dennis.
- iter-winrun-7 (~03:40): **BOTH Dennis blockers CLEARED.** Helped Dennis live: ran `railway
  login` (he approved → authed as Dennis Wang; service walk-studio-hosted online sfo) + launched
  Docker (`open -a Docker` → daemon up, 16GB). GOTCHA: my first `railway whoami` raced the login
  and showed `invalid_grant`; the login TASK then completed fine — re-check after the login task
  EXITS, not immediately. Dispatched the 2 now-unblocked big wins: **P0 redeploy+verify
  `ab03a8679fd3f0e23`** (redeploy → bind 8GB → enqueue → prove delivery; anti-stall remote-poll) +
  **NemoClaw `aebbe0d84f2a68543`** (recover gateway → install Playwright+Chromium in walk-ultra →
  test capture). JSON-reliability fix `a5895796eaaee1bb1` still running. 3 live tracks; watchdogs
  `bpipa8zti` (json-fix) + `bor1iw9jr` (p0+nemoclaw).
