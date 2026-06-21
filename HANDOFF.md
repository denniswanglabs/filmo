# HANDOFF — Walk Studio (Hermes hackathon video-production agent)
_Rewritten 2026-06-21 (session 2). SUPERSEDES the earlier 2026-06-21 handoff. Self-contained so a fresh chat can carry on. Deeper per-change detail lives in the many `.handoff-*.md` files + `research/` + `docs/`._

## TL;DR
**Walk Studio** = an AI agent that turns a URL + a goal into a finished, on-brand promo video, priced and paid for on Stripe. This session pivoted it hard: the OUTPUT engine went from generic AI b-roll to **VO-driven designed motion-graphics that fill Dennis's curated styles**; the dashboard was rebuilt as a **clean Claude/Jitter-"Hiro"-style customer app**; pricing became **cost-plus with a Standard/Premium toggle**; the operator economics moved to a separate **Analytics tab**; the **walkthrough was dropped**; and a **durable desktop launcher** fixed a Stripe-return bug.

- **Deadline:** EOD Tue **June 30 2026**. Submit: 1–3 min demo video tweet @NousResearch + discord.gg/nousresearch + Typeform. Judged usefulness / viability / presentation.
- **Project root:** `~/Desktop/Projects/Hackathons/hermes-video-agent/`. **NOT a git repo yet** (repo creation is PENDING, below).
- **Run the dashboard:** double-click `~/Desktop/start-walk-studio.command` → open http://localhost:3030 in **Safari**.
- **Tests:** `./run_all_tests.sh --no-eval` → green, $0.

## OPERATING MODEL (how Dennis works — obey this)
- **Every task Dennis asks for → a background subagent** (Agent `run_in_background: true`), so he keeps chatting while I orchestrate. Prepend `~/.claude/templates/subagent-brief-stock.md` to each brief.
- **A persistent Monitor watchdog** (`.watchdog.py`) tracks real subagent ids only (17-hex `a…`), emits a 15-min status + stuck-flag (no growth >180s), prunes completed agents. Benign "STUCK"/prune events on already-completed agents are normal.
- **Fan out independent work in parallel; SERIALIZE agents that touch the same file.** LESSON paid this session: `serve.py` and `run_all_tests.sh` got concurrently edited by parallel agents — always check shared backend files for clobbering, and only let one agent own a given file at a time.
- No emojis. Native SVG over raster. Localhost in Safari. Decide $0 things yourself; only pause before paid-API spend or when Dennis says "brainstorm." Daily-log hook appends to vault `Daily/2026-06-21.md` every ~30 min.

## THE OUTPUT ENGINE (VO-driven, designed) — BUILT + verified ($0)
The old pipeline locked scene durations BEFORE the VO (`plan_job.py`), so the VO never matched. New engine inverts it:
- **`align_vo.py`** — script + per-scene beats → `vo_alignment.json` (word-level timestamps). Free path = edge-tts + local `whisper-cli` (`/opt/homebrew/bin/whisper-cli`, model `~/.cache/whisper/ggml-base.en.bin`). Premium = ElevenLabs `with-timestamps` (per-char timings in one call).
- **`build_timeline.py`** — scenes + alignment → `timeline.json` (each scene's in/out frame from its word span; picture built FROM the voice; `duration_s` demoted to advisory).
- **`studio/` Remotion `<Timeline>` composition** — `<Audio>` + per-scene `<Sequence>` at word-anchored frames, reveals on cue frames. Archetypes ported: Orinovate kinetic-light (`hero-title`, `card-ui`) + Apple-style (`apple-hero`, `apple-registry`, `apple-statement`). Behind a flag; the old single-`Scene` path stays green.
- **`style_fill.py`** (keystone) — style registry; given brand_theme + timeline + style → `props.json` → render. End-to-end driver (align→timeline→fill→render) PROVEN $0 mock on Orinovate (montage in `runs/style-fill-sample/`).
- **`brand_extract.py`** — URL → `brand_theme.json` (palette/fonts/wordmark/copy/features). Honesty rule enforced: never fabricates a tagline (the old `_copy_from_brief` Stripe-leak bug is not reintroduced).
- **Curated styles** (Dennis's picks): Orinovate kinetic-light (primary), Apple-style, JGB cinematic (Higgsfield plates). NOTE the Ploy reframe below: these are NOT exposed as a "pick a style" menu.

## PRICING — cost-plus + Standard/Premium — BUILT
- **`pricing.json` / `pricing.py`** — `model: cost_plus`. `price = max($5 floor, round_to_$0.50(plan_cogs_cents × 6))`. Single source of truth (producer + dashboard read it).
- **STANDARD vs PREMIUM** = `selection.quality`. **Standard** = Remotion designed motion-graphics + edge-tts (COGS ~$0 → ~$5). **Premium** = adds Higgsfield cinematic footage + ElevenLabs natural voice (→ ~$6–9). No tiers, no consent gate (premium VO uses an ElevenLabs STOCK voice, not a clone).
- Produce gating (`orchestrator.py`/`adapters.py`): premium → real Higgsfield + ElevenLabs (`--mode real`); standard → cinematic falls back to a Remotion scene + edge-tts. Mock = $0 both. Behind `WS_PREMIUM_MENU` (default OFF = byte-identical).
- **SACRED, untouched:** the serial budget-gate + Stripe authorize sequence in `orchestrator.py`.
- **Stripe earn:** `stripe_earn.py`, `DASHBOARD_BASE = http://localhost:3030`, `success_url = .../dashboard/index.html?paid=<job>`. Quote shows at the pay-gate (`awaiting_payment`).

## DASHBOARD — Claude/Hiro-style CUSTOMER app — BUILT
- `dashboard/` shell: left sidebar (Walk Studio logo + "New build" + past builds with **descriptive titles** like "Stripe — explainer" + recency groups + hover delete); center = the **Hiro empty-state composer** (warm coral glow, bold "Got a video idea, Dennis?", aspect + pacing pills, clean composer with a coral circular send button, example chips) OR the live build view.
- **Ploy reframe:** NO style-name labels (kinetic-light/Apple/cinematic gone from the UI). The curated films are a visible **lookbook** — "A few we're proud of · The bar we hold every video to" — the taste/quality signal.
- Branding: horizontal two-tone **Walk Studio** logo (glyph + "Walk" ink + "Studio" coral), bigger/tighter; matching favicon. Canonical at `branding/logo-walkstudio-{light,dark}.svg`.
- `dashboard/serve.py`: ThreadingServer on :3030 (resilient, `allow_reuse_address`), Range support, routes `/api/build` `/api/active` `/api/delete` `/api/analytics`.
- **`analytics.py` + `GET /api/analytics`** — operator economics aggregator: per-build {price, COGS, margin, declines, overage_saved, status} + totals {revenue, COGS, gross, avg_margin, overage_saved, #builds, #declines}. Over the real runs/: 22 builds, $455.71 rev, $8.52 COGS, 64% avg margin, $1.48 overage auto-saved.

## IN FLIGHT when this handoff was written (VERIFY they landed on resume)
- **Walkthrough removal (planner level)** — `plan_job.py` + `planner-prompt.md` + `serve.py` default goal: stop PLANNING any walkthrough scene (the orchestrator/adapters walk-agent code is left dormant). Check `.handoff-nowalkthrough.md`.
- **Analytics tab FRONTEND** — `dashboard/{index.html,app.js,styles.css}`: strip economics (margin/COGS/budget/P&L/declines) from the CUSTOMER view, add an **Analytics tab** (consumes `/api/analytics`) for the operator, remove the "Product walkthrough" example chip. Check `.handoff-analytics-ui.md`.

## PENDING — do next (in order)
1. **QUALITY-AWARE PLANNER (active bug Dennis flagged).** On STANDARD the shot list still includes cinematic `seedance_2_0` / `gpt_image_2` scenes — produce downgrades them to Remotion, but they should NOT be PLANNED on Standard. Make `plan_job.py` + `planner-prompt.md` quality-aware: **Standard plans ONLY `title` + `motion-graphic` (Remotion); Premium may include cinematic.** Thread `selection.quality` into the planner. (Do AFTER the walkthrough-removal agent lands — same files.)
2. **VERIFY `serve.py` integrity.** Three agents (Standard/Premium toggle, analytics-backend, walkthrough-removal) edited `serve.py` in/near parallel. Confirm it still has ALL of: the `/api/analytics` route, the `--quality` threading into `build_runner`, and the new walkthrough-free default goal. Re-apply anything clobbered.
3. **Wire `tests/test_analytics.py` into `run_all_tests.sh`** (left un-wired to avoid a write race). Then run the full suite green.
4. **Restart the dashboard server** so the `serve.py` changes take effect (via the launcher, or `preview_start hermes-dashboard`). Then $0 mock end-to-end for BOTH Standard and Premium and confirm the shot lists + prices are correct.
5. **Create the PRIVATE GitHub repo** (project is not git yet): `git init` + thorough `.gitignore` (exclude `.env*`, any keys, `node_modules`, `*.mp4`/large media, `runs/*/clips`, `__pycache__`, `*.bak`, `*.output`, `studio/out`), **scan for secrets** (`sk_`, API keys) BEFORE committing, `gh repo create` PRIVATE, commit, push. For the hackathon SUBMISSION later: flip public + add an OSI LICENSE (deliberate step Dennis decides).

## KEY GOTCHAS / DURABLE FACTS
- **Stripe-return blank bug (FIXED, root cause important):** after paying, the page went blank because the **dashboard server was DOWN** when Stripe redirected to `localhost:3030` (the ephemeral preview/session server had died). Routing + `?paid` handler are CORRECT. FIX = the durable launcher `~/Desktop/start-walk-studio.command` (nohup serve.py on :3030, idempotent, opens Safari). Never rely on an ephemeral/preview server for the live Stripe round-trip.
- Preview-MCP screenshots can return a **3px-wide viewport** after a programmatic navigation (looks blank) — `preview_resize` to 1280 to actually see the page.
- **Costs:** Higgsfield Seedance ~$0.27/6s clip, gpt_image ~$0.07; walk-agent + Remotion ~free; ElevenLabs ~$0.20/VO. Real per-video COGS < ~$1. Higgsfield is a FLAT subscription (no per-use buy — the unresolved "spend axis" gap). Keys in `~/.hermes/.env` (`ELEVENLABS_API_KEY`, `STRIPE_SECRET_KEY` sk_test, NVIDIA); `NVIDIA_API_KEY` also in `~/.zshrc`.
- **Brain = Nemotron Super-120B** (FREE, build.nvidia.com), not Ultra. Emits hidden reasoning tokens → keep `max_tokens` 8000+ or JSON truncates.
- **POSITIONING — "Ploy, but for video"** (Bryant Chou / Ploy YC interview; memory `reference_ploy_interview_taste_moat`): curation is the moat; the curated films are the lookbook (the bar for good), `brand_extract` is the "slurper," agent + Dennis's taste = anti-slop video. No AI-tell style labels.
- **Customer app vs operator:** the dashboard is the CUSTOMER product (no economics shown). The **Analytics tab** holds the P&L / margin / auto-decline money-shot — that's what you show JUDGES, while customers see a clean app.
- With the walkthrough dropped, the launcher's NemoClaw warm-up is unnecessary (`SKIP_WALK=1`).

## POINTERS
- `.handoff-*.md` (per-change): align-vo, build-timeline, timeline-comp, style-fill, brand-extract, apple-archetypes, pricing-foundation, premium-produce, premium-dashboard, costplus-pricing, pricingux, redesign, sidebar, hiro, ploy, quality, analytics-backend, analytics-ui, nowalkthrough, launcher.
- `docs/2026-06-21-vo-driven-style-engine-design.md` — the engine spec.
- `research/{ELEVENLABS-RESEARCH, CURATED-DESIGN-LIBRARY, PIPELINE-PIVOT-ARCHITECTURE}.md`.
- Memory `project_hermes_hackathon` + vault `Daily/2026-06-21.md` (full running log of this session).

## RECOMMENDED NEXT STEP ON RESUME
Verify the two in-flight agents landed (walkthrough removal + analytics tab), then do PENDING #1 (quality-aware planner — the Standard shot-list fix), #2 (serve.py integrity), #3–4 (wire test + restart + mock both qualities), then #5 (private repo). The demo video + the two rule checks remain Dennis-gated.
