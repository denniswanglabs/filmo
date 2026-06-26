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

## This is a HOSTED product (for other users) — it cannot rely on local gen
- **Web** (Next.js) → Vercel. Deploy: `cd web && vercel --prod --yes` THEN re-alias the apex: `vercel alias set <new-deploy-url> filmostudio.vercel.app` (the apex alias does NOT auto-follow — always re-alias).
- **Worker** (Docker: python pipeline + node `worker/run.js`) → Railway. Deploy: `railway up --service walk-studio-hosted` (CLI authed as Dennis; project `walk-studio-hosted`, env `production`). Deploy-source branch = `hosted-saas`.
- The worker polls InsForge `jobs` (claim_next_job) and runs `build_runner.py`. A build is created via the web app or by inserting a run+job into InsForge.
- Local pipeline run (debug only): `set -a; source ~/.hermes/.env; set +a; python3 build_runner.py --url <url> --run-id <id> --mode mock --brain ultra-paid`. Renders `runs/<id>/final.mp4`. (`mode mock` = real Remotion cards, $0 production; planning costs Nemotron tokens.)

## Keys / data
- OpenRouter/ElevenLabs/NVIDIA keys in `~/.hermes/.env`. InsForge admin key in `web/.env.local` (`INSFORGE_API_KEY` bypasses RLS — use `@insforge/sdk createAdminClient` to query `runs`, joined to `auth.users`).

## Current branches
- `landing-polish` = active web+pipeline work (deployed to Vercel). `hosted-saas` = worker deploy source. `cards` = original treatment branch (merged into landing-polish). `main` = the `hermes-video-agent` worktree.

## Latest handoff
See the newest `HANDOFF-*.md` in this dir for in-progress state.
