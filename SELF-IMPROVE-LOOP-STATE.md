# Filmo Self-Improving Video Loop — STATE & AUTONOMY DIRECTIVE

> **AUTONOMY DIRECTIVE (read first).** This is a Dennis-authorized **2-hour fully-autonomous** self-improvement loop, started 2026-06-26 ~21:00. If you are a fresh context: DO NOT wait for Dennis (he is asleep). Read this file + repo `CLAUDE.md`, then RESUME the loop from the last incomplete iteration in the Iteration Log below. Keep going until the 2 hours are up OR the rubric is satisfied on YC. Then deploy to production (see "Deploy at end") and write a full report. Money is cents/gen and pre-approved; production deploy at the END is pre-approved. Do NOT re-ask Dennis to continue.

## The goal (Dennis's words)
Any link in → a **fancy, well-built video** that **gathers real data from the website** and renders it with **rich layouts**. It must generalize so anyone's link works. Today the pipeline works end-to-end but output collapses to bare fallback layouts because data extraction is weak and the layout vocabulary is thin.

## Locked architecture (see repo CLAUDE.md — do NOT re-litigate)
- **Hermes = the HARNESS** (agent runtime/orchestration). **NVIDIA Nemotron = the BRAIN** (every LLM call; 550B = `ultra-paid`). **Stripe = payments.** Hermes is NOT a model call.
- Brand = **Filmo**, https://filmostudio.vercel.app.
- **The video RENDER uses `studio/`** (`build_runner.py` → `remotion render … Timeline`), NOT `web/app/runs/[id]/edit/_composition` (that's the editor preview). **Both `ExplainerCard.tsx` copies + types must stay in sync.**

## THE RUBRIC (all four matter equally — Dennis selected all)
1. **Data truth** — real stats / company names / hard claims pulled from the ACTUAL site; zero fabrication; no generic filler.
2. **Layout richness** — fancy treatments used well + varied (not bare/repetitive). "Fancy = BOTH: add NEW layout types AND make existing ones reliably fire with real data."
3. **Visual polish** — correct brand colors/logo/type, clean composition, no white-space gaps.
4. **Motion + narrative** — smooth intentional motion, good pacing (see memory `reference_video_pacing_budgets`), coherent hook→value→proof→CTA arc.
(+ audio balance: VO + music per memory `feedback_bgm_level_depends_on_vo`.)

## Eval focus
**YC first, deep** (https://www.ycombinator.com) — must match Dennis's target screenshot (icon-stat $500K · split-mosaic of Stripe/Airbnb/Coinbase/DoorDash tiles · split-stat $800B+ + bars). Nail YC before broadening.

## The two levers (Dennis: improve "skills for Hermes OR system prompts for Nemotron")
- **BRAIN prompts (Nemotron):** `planner-prompt.md` (how it plans + extracts data + picks treatments) and the site-read/`analyze.py` prompt (how it reads the site + what structured data it returns).
- **HARNESS code/skills:** extraction + treatment logic in `plan_job.py` (`_assign_card_treatments`, `_mine_named_entities`, `_stat_is_real`) + `style_fill.py`; and the RENDER ARCHETYPES (`studio/src/timeline/archetypes/*` and the mirror `web/app/runs/[id]/edit/_composition/archetypes/*`) — the actual layouts. NEW layout types are added here.

## Loop mechanics (FAST + LOCAL; deploy only at end)
A worker redeploy is ~5-7 min, so DO NOT deploy per iteration. Iterate locally:
1. **Generate YC locally:** read→plan→style_fill→render. Plan-only check first (fast, ~30s, `python3 plan_job.py --url https://www.ycombinator.com --brain ultra-paid` — but note it lacks a conversion_read; prefer the full local `build_runner.py … --mode mock --brain ultra-paid` for representative scenes). Re-add the studio deps symlink for local render: `ln -s /Users/dennis/Desktop/Projects/Hackathons/hermes-video-agent/studio/node_modules studio/node_modules`. Set keys: `set -a; source ~/.hermes/.env; set +a`.
2. **Judge** the contact sheet scene-by-scene against the 4 rubric dims (memory `feedback_judge_whole_video_not_frame` — judge the whole video, never one frame). Score each dim 0-5. Record the SPECIFIC failures.
3. **Root-cause** each failure → assign to a lever (brain prompt vs harness code/layout).
4. **Improve ONE thing** (one behavior change → measure → keep/revert, per memory `feedback_self_improving_orchestrator`). Use background subagents for the work (full-force is ON); watchdog when 2+ in flight.
5. **Re-run + re-judge.** KEEP only if the rubric score went UP with NO regression on other dims/scenes. Else `git revert`/restore. Commit each kept improvement.
6. **Log** every iteration (below) + promote recurring lessons to `LESSONS.md`.

## Safety / guards
- Frozen known-good baseline = current git HEAD (`git log` to find it). Always revertible.
- No-regression rule: a change that helps one dim but hurts another is REVERTED unless net-positive across the rubric.
- Money: each gen ≈ <1¢ planning (Nemotron) + $0 mock render — pre-approved. Don't switch to premium/Higgsfield (real $) without Dennis.
- Production deploy: ONLY at the end, after verifying no regressions.
- House rules stay on: no emojis, native SVG, honesty (never fabricate stats/entities), studio+web archetypes in lockstep.

## Deploy at end
1. Commit all kept improvements. 2. `railway up --service walk-studio-hosted --ci` (worker). 3. If web archetypes changed: `cd web && vercel --prod --yes` THEN `vercel alias set <url> filmostudio.vercel.app`. 4. Re-gen YC on the HOSTED path (insert run+job via admin SDK — see `web/app/actions.ts createBuild` shape; user_id `c96a76b9-8571-41ff-b29e-f358143a925f`) to confirm rich cards live. 5. Write the full report + update this file's Iteration Log.

## Starting state (2026-06-26 ~21:00)
- Just deployed (worker `bt0bbnk6i`, exit 0): entity honesty-guard broadened + `_mine_named_entities` proper-noun miner so split-mosaic fires for entity-rich scenes (commit on `landing-polish`). NOT yet validated on a fresh hosted YC gen.
- Last hosted YC gen (pre-fix) `1ba4208c…`: all cards `icon-headline` (the bug). Delivered video at `~/Desktop/filmo-videos/yc-nemotron-hosted-v1.mp4`.
- Known gaps to attack: (a) STAT extraction (icon-stat/split-stat never fire — no structured number source); (b) only 4 card treatments — need NEW layout types (charts, comparison, timeline, logo-wall, big-number, quote); (c) visual polish on the non-card scenes; (d) reliable real-data extraction in the conversion read.

## Iteration Log
| # | Lever changed | Hypothesis | Rubric before→after | Kept? | Notes |
|---|---|---|---|---|---|
| 0 | (baseline) | — | TBD | — | validate the just-shipped mosaic fix on a fresh YC gen |
