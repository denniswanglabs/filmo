# Filmo — LOCKED FACTS (read this first, every chat)

Filmo is an AI Product Launch Producer (hosted SaaS) for the **Hermes × NVIDIA × Stripe** hackathon. URL in → Conversion Read → plan → price → pay → produce → ship a launch video.

## Architecture — DO NOT muddle this (I have repeatedly; don't)
- **Hermes = the AI HARNESS** — the agent runtime / orchestration. It is NOT a model that does a step.
- **NVIDIA Nemotron = the BRAIN** — every LLM/reasoning call (Conversion Read AND planning). The flagship is the **550B** = `ultra-paid` = `nvidia/nemotron-3-ultra-550b-a55b`.
- **Stripe = payments.**
- Use **PAID Nemotron** so there are no free-tier OpenRouter 429s. Do NOT reintroduce a Hermes/Nous *model* brain for any step (the old `analyze.py` "one real Nous-model usage" comment is wrong per Dennis).
- Wiring: `analyze.py ANALYZE_BRAIN_CHAIN = ("ultra-paid","super-paid")`; `build_runner ANALYZE_BRAIN = "ultra-paid"`; planner brain = `ultra-paid`.

## Brand
- Product = **Filmo**, live at **https://filmostudio.vercel.app**. "Walk Studio" / `walk.studio` is RETIRED — do not use it.

## Cards (feature-card treatments)
- 4 treatments: `icon-stat` / `split-mosaic` / `split-stat` / `icon-headline` (fallback). Planner picks (LLM + rules guard) with a HONESTY guard: **never fabricate a stat/entities — no real data → `icon-headline`** (centered, full-width, fills the white space).
- Rich cards need a brand with real stats/entities (YC has them: $500K, $800B+, Stripe/Airbnb…). Data-poor brands honestly degrade to `icon-headline`.
- **VERIFIED-KNOWLEDGE ENRICH (loop2, 2026-06-26):** `plan_job.enrich_brand_knowledge(name,url,brain)` = a FOCUSED Nemotron call returning the brand's REAL stats + named customers/products from the model's verified knowledge (strict JSON, honesty-guarded → EMPTY for unknown/obscure brands & name-collisions). `_seed_feature_beats_from_enrichment` then deterministically seeds the feature-beat brief + matching VO text so grounded gens (real homepage) render split-stat/split-mosaic instead of bare cards. This is why a generic homepage (YC/Stripe) now yields rich cards. Honesty is ABSOLUTE — never relax the empty-for-unknown guard. Validated on 11+ brands (see `SELF-IMPROVE-LOOP-STATE.md` LOOP 2).
- Data contract on scene.data: `treatment`, `icon`, `stat{value,label}`, `featureEntities[]` (NOT `entities`), `entityLogos[]`.
- **split-mosaic = LIGHT brand palette + REAL company LOGOS (2026-06-26).** The tile grid uses `theme.bg`/`theme.bgCard`/`theme.border` (NOT the old hardcoded dark `#0B0F1A`/`#161B2E`) so it matches the brand (YC=white/orange, Linear=white/blue — palette adapts). Tiles show the real company logo from `data.entityLogos[i]` (index-aligned with `featureEntities`), with an accent-colored INITIAL badge fallback (never the old generic person-silhouette). Logos are staged at BUILD time by `entity_logos.py` (`attach_entity_logos`, called in `style_fill.run_pipeline` after `build_props`): name→domain heuristic + `KNOWN_OVERRIDES` → DuckDuckGo `icons.duckduckgo.com/ip3/<domain>.ico` → base64 data URI (no render-time network; ""=fallback). BOTH ExplainerCard copies render it (studio bare `<Img src={logo}>`; web editor `<Img src={resolveLogo(logo, resolveSrc)}>` — `resolveLogo`/`resolveSrc` passes `data:` URIs through unchanged).
- **The RENDER uses `studio/` (`build_runner` → `remotion render … Timeline`), NOT `web/app/runs/[id]/edit/_composition` (that's the editor PREVIEW). Both `ExplainerCard.tsx` copies must stay in sync.**

## Curated pattern library + Lookbook (2026-06-27)
- The scene-treatment system is a legible **curated pattern library** (the anti-slop moat). 12 patterns in `studio/src/timeline/patterns.catalog.json` (the single source of truth, mirrored to `web/app/_data/patterns.catalog.json` for the landing): the original 4 + `metric-row`, `device-frame`, `comparison-columns`, `pull-quote`, `big-number`, `logo-wall`, `feature-list`, + `kinetic-statement` (harvested from the cluely-promo Luceo film: word-by-word rise-blur + accent emphasis + highlighter). `style_fill._assign_treatment_from_filled_copy` is the assembler; it records `data.patternReason` (a legible "why this treatment" trace). The visible **Pattern Lookbook** is on the landing (`web/app/components/landing/PatternLookbook.tsx`, beside `LuceoShowcase`); stills in `web/public/lookbook/<id>.png` rendered on a neutral Filmo theme (white bg / `#3B82F6` accent / empty wordmark / `actIndex={-1}`).
- **★ DO-NOT-RE-ATTEMPT finding (tested empirically 2026-06-27): the production video pipeline ALREADY covers these layout niches, so force-wiring the new patterns into real gens adds NO clear value — each is redundant / inert / lateral, and changing approved videos is a regression risk.** Specifics: `device-frame` = REDUNDANT (`AppleScreenshot`'s default already renders text-left + screenshot-in-a-browser-frame-right); `metric-row` = INERT in prod (every STANDARD plan spends its beats on the homepage `screenshot` scene + the mosaic + the planner's own stat beats, so there is no spare beat to consolidate — 0/2 hosted gens fired it; it only fired in an unrepresentative local plan that lacked the screenshot scene); `kinetic-statement` floor-upgrade = LATERAL/redundant (videos already carry an emphasis-word statement scene via the `apple-statement` archetype, e.g. "Y Combinator is the **launchpad**"). All three were implemented, tested, and REVERTED; the new archetypes stay DEPLOYED-but-DORMANT (opt-in only) + showcased in the Lookbook + a harvest backlog (`docs/superpowers/notes/2026-06-27-luceo-harvest-findings.md`).
- **Lesson:** before wiring a "new capability" into this polished pipeline, READ what the production path already renders for that scene type (the actual archetype + a hosted contact sheet) — NOT an isolated local test. Local renders mislead because the real plan always includes the screenshot scene + mosaic + LLM stat beats. The one non-redundant path to add a pattern is a deliberate redesign of an existing beat (e.g. the opening) — gate it on Dennis's sign-off.

## This is a HOSTED product (for other users) — it cannot rely on local gen
- **Web** (Next.js) → Vercel. Deploy: `cd web && vercel --prod --yes` THEN re-alias the apex: `vercel alias set <new-deploy-url> filmostudio.vercel.app` (the apex alias does NOT auto-follow — always re-alias).
- **Worker** (Docker: python pipeline + node `worker/run.js`) → Railway. Deploy: `railway up --service walk-studio-hosted` (CLI authed as Dennis; project `walk-studio-hosted`, env `production`). Deploy-source branch = `hosted-saas`.
- The worker polls InsForge `jobs` (claim_next_job) and runs `build_runner.py`. A build is created via the web app or by inserting a run+job into InsForge.
- Local pipeline run (debug only): `set -a; source ~/.hermes/.env; set +a; python3 build_runner.py --url <url> --run-id <id> --mode mock --brain ultra-paid`. Renders `runs/<id>/final.mp4`. (`mode mock` = real Remotion cards, $0 production; planning costs Nemotron tokens.)
- **★ GOTCHA — `loop_plan.py`/`loop_measure.py` SKIP the orchestrator's `validate_plan` (`plan_schema.py`).** So a change can pass every local loop test and still crash the HOSTED build with `ValueError: invalid plan` (the orchestrator runs `validate_plan` at `orchestrator.py:~238`, build fails "exit 1, ledger failed"). In particular: **adding a new TOP-LEVEL plan key requires adding it to `plan_schema.allowed_top`** (currently `{job, scenes, voiceover, selection, _planner, design_brief}`). When a hosted gen fails, get the real traceback with `railway logs --service walk-studio-hosted | grep -iE "traceback|error|line [0-9]"` — the InsForge "request timed out" lines are noise, not the cause.

## Keys / data
- OpenRouter/ElevenLabs/NVIDIA keys in `~/.hermes/.env`. InsForge admin key in `web/.env.local` (`INSFORGE_API_KEY` bypasses RLS — use `@insforge/sdk createAdminClient` to query `runs`, joined to `auth.users`).

## Repo + branches
- **GitHub repo = `denniswanglabs/filmo`** (renamed from `walk-studio` 2026-06-28; the old URL auto-redirects). Will be flipped PUBLIC for the submission (not yet — scrub internal `*.md` docs first).
- **★ Rename scope — DO NOT rename these (live infra, would break deploys):** the local dir `walk-studio-hosted`, the Railway **service** `walk-studio-hosted`, and the InsForge storage **bucket** `walk-videos`. Only the GitHub repo name + display/brand text changed to Filmo.
- Branches: `landing-polish` = active web+pipeline work (deployed to Vercel). `hosted-saas` = worker deploy source (Railway). `cards` = original treatment branch (merged into landing-polish). `main` = the `hermes-video-agent` worktree.

## Latest handoff
See the newest `HANDOFF-*.md` in this dir for in-progress state.

## Filmo Lab (LOCAL ONLY — do not confuse with production/Hetzner)
- **`filmo-lab/`** = isolated Hermes self-improve experiment on your Mac. Read **`filmo-lab/CLAUDE.md`** before any lab work.
- Lab uses Hermes profile **`filmo-lab`**, runs under **`filmo-lab/runs/`**, never InsForge/Railway/Hetzner/VM.
- Production = `worker/`, `web/`, `agent-host/`, Vercel, Hetzner — **never mix with lab scripts.**

