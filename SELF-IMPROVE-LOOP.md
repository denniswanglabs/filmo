# Self-improving loop — WIN RUN (read FIRST on each firing)

_Self-paced /loop. MISSION: win the Hermes×NVIDIA×Stripe hackathon (due 2026-06-30) —
beat the rival VED/StoryPrompting. Dennis is ASLEEP (~02:00, 2026-06-25) — FULL AUTONOMY.
Spend ceiling: **$20 EXTERNAL** (paid Nemotron 550B for sharper diagnoses; flag before any
Higgsfield burst). `main` = untouched fallback. Backup: commit+push after every change._

## WIN THESIS
VED is real, polished, spectacular — but makes a SYNTHETIC FILM. We win on GROUNDING +
RELIABILITY + INTELLIGENCE: a hosted tool anyone can use that READS a real product,
DIAGNOSES how it fails to convert (the Conversion Read), and PRODUCES the video that fixes
it — billed autonomously, Stripe declining the agent's own over-budget spend, no human.
Don't out-spectacle the film; out-substance it.

## DESIGN GATE (Dennis is meticulous — NEW HARD REQUIREMENT)
Every UI surface AND every produced video frame must clear a researched design bar.
Reference: `docs/DESIGN-BEST-PRACTICES.md` (Track C is writing it). NO polish or video ships
that doesn't meet it. Judge videos WHOLE (ffmpeg contact sheet, scene-by-scene), never a frame.

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
