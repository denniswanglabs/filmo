# Walk Studio — STANDARD Build Loop: LIVE STATE
_2026-06-22 (loop session). **Living resume anchor — read this FIRST to continue the experiment in any fresh context.** Update after every milestone._

## ===== MORNING REPORT — Dennis, read this first (2026-06-22 ~01:35) =====
**The core goal is MET, and the recurring ORANGE is dead.**

**WATCH THE DELIVERABLE:** `runs/hero-stripe/final.mp4` — a complete, on-brand **Stripe** Standard video: branded open → REAL stripe.com homepage screenshot → REAL stripe.com/pricing screenshot → walkthrough in a branded frame → grounded "Start building at Stripe" CTA. **Zero orange. Grounded VO. $0.** (Also `runs/p3-standard-verify/final.mp4` = the orinovate version; `runs/verify-decouple/final.mp4` = the orange-fix proof.)

**Shipped + verified this session (all $0, mock-pay, no card):**
- **ORANGE KILLED** — verified white in REAL mode (the thing you were most frustrated by; `runs/verify-decouple`).
- Instant-quote pricing (live $6.50 itemized) + **real Stripe payment path** (you validated it end-to-end).
- **P1** screenshots archetype · **P2** walkthrough-player archetype · **P3** the integration (planner now emits screenshot+walkthrough for Standard) · **P4** dashboard 3-field input (URL·goal·**emphasis** — confirmed live in the UI).

**Known polish / your call (NOT blockers):**
- Walkthrough overlay TEXT didn't tightly match the emphasis ("subscription plan" vs "the pricing page") — **DONE 2026-06-22** (FIX 1). Overlay title now derives from the run EMPHASIS (`data._emphasis` threaded by build_props), not the planner's free VO. Verified plan-level: stripe.com + emphasis="the pricing page" → brief "...demonstrate the pricing page..." AND overlayTitle "Stripe — Pricing page" (was "Stripe — Follow along as we create a payment link..."). Also fixed two double-"the" grammar bugs. See `.handoff-polish-hardening.md`.
- `load_pricing` hardening + atomic config writes (prevents the config-race crash that hit the failed luceostudio build) — **DONE 2026-06-22** (FIX 2). `load_pricing` retries once on JSONDecodeError then raises clear `PricingConfigError`; nothing writes pricing.json at runtime (static config) so added an atomic-write guard comment (temp+os.replace, per ledger.py:write). Tests green. See `.handoff-polish-hardening.md`.
- Dashboard end-to-end build (UI proof): the 3-field composer is LIVE; run one yourself or I'll do it when you're up. NOTE: a mock dashboard build's walkthrough is a PLACEHOLDER unless walk-agent runs — decide whether mock builds should spend ~1 NIM (~7 min) for a real walkthrough, or keep walkthroughs to real/paid builds.
- P6 grounded VO only matters for bot-blocked brands (TripAdvisor); fetchable brands (Stripe/Orinovate) already ground fine.

**Full detail + per-phase verdicts below, and in the `.handoff-*.md` files.**
## =====================================================================

## PROMPT-OPTIMIZATION LOOP (ACTIVE objective — 2026-06-22, Dennis directed)
GOAL: make Walk Studio's STANDARD video quality **on par with Dennis's HANDPICKED reference films** (dashboard lookbook), across the **MAJORITY of websites** (generality). Mechanism: generate Standard videos for diverse brands → critique each vs the reference RUBRIC → synthesize gaps → improve the planner SYSTEM PROMPTS (`validate_planner.SYSTEM_PROMPT`, `_QUALITY_PROMPT`, `planner-prompt.md`) + style → regenerate → re-score → repeat until generated ≈ handpicked.
**MANDATE (2026-06-22, Dennis sleeping ~8h, wants a COMPLETE PRODUCT by morning):** run MANY rounds to CONVERGENCE ("iterate until not iterable anymore"). Pursue BOTH tracks INDEPENDENTLY — **Track A = Dim-3 copy grounding** (prompt files), **Track B = Dim-5 real imagery/screenshots** (capture+render files, $0). LEARN every round → append to `LEARNINGS.md` (READ IT ON RESUME; never repeat a failed hypothesis). Eval discipline + track definitions + convergence rules all live in `LEARNINGS.md`. Disjoint files → the two tracks can run in parallel and be scored per-dimension independently.
- **TOKEN BUDGET = MAX** (Dennis: "use as many tokens as possible"): many brands × critiques × prompt iterations. Spend liberally; favor breadth + adversarial critique.
- **NIM stays modest:** during prompt-tuning use CACHED/placeholder walkthroughs (`WS_WALKTHROUGH_CACHE=/tmp/walk-smoke.mp4`) — the prompts control VO/copy/structure, NOT walk-agent navigation. Save fresh NIM captures for final brand-correct deliverables.
- **Quality levers = the planner prompts** (VO grounding, scene structure, copy concreteness) + style tokens. HARD case = bot-blocked brands (TripAdvisor → hollow copy); the P6 grounding fix (world-knowledge for known brands + anti-"describe-the-animation") is part of THIS loop.
- **Avoid render thrash:** generate builds SERIALLY (≤2-3 concurrent renders); critique in PARALLEL (frame-reads are cheap). [LESSONS: parallel render fleets thrash one machine.]
- **SETUP DONE** → spec at `OPTIMIZATION-SPEC.md` (5 reference films, 9-dim rubric [target ≥4 each, ≥4.3 mean], 12-brand roster). Widest gaps to the bar: Dim 3 (copy grounding) + Dim 5 (real-UI fidelity).
- **GATE CLEARED** (polish a5d5e04 DONE: emphasis→overlay fix + load_pricing hardening, tests green; plan_job.py free). **ROUND 1 generate IN FLIGHT: agent a4b1e850** — baseline videos for stripe / tripadvisor.com.tw / linear / shopify / plaid (serial, cached walkthrough, $0, current prompts). On completion → fan out PARALLEL critic subagents (one per brand) scoring vs OPTIMIZATION-SPEC.md → baseline table → synthesize → edit prompts (default Round-1 focus: **Dim-3 copy grounding** = the clearest system-prompt win + the bot-blocked weak point; Dim-5 native-UI is a bigger architectural lift flagged for Dennis) → Round 2 regenerate same subset + re-score to measure the lift.
- **ROUND 1 plan:** generate baseline Standard videos for a REPRESENTATIVE SUBSET first (stripe=good baseline, tripadvisor.com.tw=hard grounding case, linear=heavy-JS, shopify=e-commerce, + ~2 more) — SERIAL renders, `WS_WALKTHROUGH_CACHE=/tmp/walk-smoke.mp4`, $0. Then a critic subagent scores each vs `OPTIMIZATION-SPEC.md` (frame-read + VO) → baseline table → synthesize Dim-3/Dim-5 gaps → edit `validate_planner.SYSTEM_PROMPT` / `_QUALITY_PROMPT` / `planner-prompt.md` → regenerate the same subset → re-score → log the round. Expand the roster in later rounds.
- **ITERATION LOG** (append per round): `round N | prompt-version | per-brand scores vs rubric (1-5) | top gaps | prompt change applied`.

## GOAL (definition of done)
One **Standard** run — **URL + emphasis** — produces a complete, on-brand ~30s video:
**branded open → real site screenshots → guided Walk Agent walkthrough to the emphasized feature → grounded VO → CTA.**
No orange placeholders, no hollow/self-referential copy, no crashes. Instant-quoted, Stripe-test-paid, delivered. Verified by reading the actual rendered frames.

## CONTEXT-SURVIVAL PROTOCOL (how to continue despite running out of context — pictures are the hog)
- **This file is the source of truth.** Update it after each milestone; on resume, read it first.
- **DELEGATE all image/frame/screenshot reading to subagents** — they read pixels in THEIR context and return TEXT verdicts. The orchestrator keeps only text.
- **Inspect state as TEXT**, not screenshots: `ledger.json` (Bash), Chrome `read_page`/`get_page_text`. Screenshot ONLY key visual milestones.
- **Poll builds via background Bash on `ledger.json`** (never zsh `read` into `$status` — it's read-only; use other var names).
- Dashboard driving: Chrome MCP, **tab 156232332**, http://localhost:3030 (durable `serve.py`).

## AUTONOMY MODE (Dennis asleep — HOLD THESE GUARDRAILS, even on a fresh context)
- **MOCK-PAY ONLY.** Never start a real-mode dashboard build; never open the Stripe card gate. The real-payment path is ALREADY validated — do not repeat it (the orchestrator cannot type card numbers, and that won't change).
- **STANDARD ONLY.** No Premium, no Higgsfield, no ElevenLabs — nothing that costs real money.
- **Modest NVIDIA NIM use:** walk-agent is proven; cap fresh `tutorial-maker.sh` captures at ~5 total overnight; reuse `/tmp/walk-smoke.mp4` / cached captures where possible. Everything else is $0 (free brain, edge-tts, deterministic screenshots).
- **Iterate via CLI mock-pay builds** (robust, no browser dependency): `PRODUCER_SIMULATE_PAID=1 python3 build_runner.py --url <url> --goal <g> --run-id <id> --mode mock --quality standard --brain super-free`. Verify by a SUBAGENT reading frames (text verdict). Chrome dashboard validation is a checkpoint/morning task, not the inner loop.
- **Self-drive:** each phase = a background subagent; on completion, verify → dispatch next. Always keep one task in flight so completions re-wake the loop. Auto-retry a failed step ~2x, then log it in this file and MOVE ON — never hang.
- **Stop + write a morning report** in this file at the definition-of-done OR if genuinely blocked (and say exactly what's blocked + why).

## ENV / PREREQS (all green as of session 4)
- Server: durable `dashboard/serve.py` (PID 63375), :3030. Restart = `kill <pid>` then `SKIP_WALK=1 zsh ~/Desktop/start-walk-studio.command`.
- Keys present: NVIDIA, OpenRouter, Stripe(test), ElevenLabs.
- NemoClaw `walk-ultra` sandbox has nim/playwright-cdn/demo-targets; `walk-ultra/tutorial-maker.sh` present.
- **Mock builds auto-pay**: serve.py sets `PRODUCER_SIMULATE_PAID=1` when `mode==mock`. Real mode = genuine test-Stripe gate (needs the 4242 test card entered by Dennis — orchestrator must NOT type card numbers).

## PLAN (phases) + STATUS
- Unblock: dynamic banded pricing + instant-quote card — **DONE, verified live**. mock-auto-pay + band labels — **DONE**. Decouple studio-overlays-from-mock — **DONE, VERIFIED 2026-06-22** (real-mode build runs/verify-decouple: all 5 scenes WHITE studio cards, zero orange; full test suite OK, $0). Ground copy — **TODO**. Atomic config writes — **TODO**.
- **P1** screenshots + Remotion `apple-screenshot` (Img) archetype — **NEXT** (after tests green). Make screenshot capture mode-INDEPENDENT (always capture, render in studio cards) to sidestep the orange coupling.
- **P2** `walkthrough-player` (OffthreadVideo) archetype — after P1. SMOKE TEST PASSED (walk-agent made a real 62s stripe.com clip). **INTEGRATION INSIGHT:** walk-ultra's "Canonical Explainer" output BAKES IN its own cursor-ring + numbered step bar + "Goal reached" banner. For clean Walk Studio branding, consume the **raw `base.mp4`** (replay-60fps.js output, PRE-overlay) — not the finished explainer — then add OUR overlays. Also: walkthrough GOAL quality matters — vague goals loop on one nav link (13× "Click Pricing"); P3 must map emphasis→a specific multi-step goal.
- **P3** planner re-admits walkthrough/screenshot for Standard (currently "retired") + emphasis→goal.
- **P4** 3-field input (URL·emphasis·path) [parallel]. **P5** token-cost pricing hookup [parallel]. **P6** grounded VO [dependency].

## VERIFIED LIVE (Chrome)
floating sidebar · serif greeting · no URL icon · "from $5 / from $15" labels · instant-quote card ($6.50 itemized, "Capped at $10").

## KNOWN ISSUES (found this session)
- Real mode disables studio overlays → orange placeholder cards (`adapters.py:46` motion_graphic `#B45309`; gate `orchestrator.py:187`; `build_runner.py:374`). DECOUPLE = keystone for Standard.
- Hollow/self-referential copy when planner ungrounded (bot-block / free-brain template fallback). Ranked fix: `validate_planner.py` world-knowledge + anti-"describe-the-animation"; `brand_extract.py` headless fetch.
- Dashboard opens on a stale frozen "producing" view (cosmetic).
- 4 stale test assertions being rebaselined (test_premium_produce / test_build_timeline / test_style_fill).

## VALIDATED (session 4, all PASSED)
- **Walk-agent works standalone** — produced a real 62s stripe.com walkthrough (`/tmp/walk-smoke.mp4`). Walkthrough pillar viable.
- **Mock auto-pay → DELIVERED** in 68s (run e0ffa7); baseline orinovate output = CLEAN white studio cards (verified by frame-read).
- **Real Stripe payment path works END-TO-END** (run 0b0aa5): real checkout session → card entered (Dennis) → polling detected `paid` → production resumed → delivered. No problems.
- Test base GREEN. Composer band labels + "instant quote" label live.

## DONE — STRIPE HERO (brand-coherent, frame-verified) (2026-06-22, $0, no fresh NIM)
- `WS_WALKTHROUGH_CACHE=/tmp/walk-smoke.mp4 PRODUCER_SIMULATE_PAID=1 build_runner.py --url https://stripe.com --goal "A 30-second brand explainer" --emphasis "the pricing page" --run-id hero-stripe --mode mock --quality standard --brain super-free --duration 30` → **delivered**. `runs/hero-stripe/final.mp4` (14.3MB, 1920x1080@30, 35.8s, has audio).
- **brand_extract GROUNDED the build**: palette = Stripe purple #635BFF / dark navy #0A2540, tagline "Build internet businesses", Söhne font — all real stripe.com facts. Background is Stripe's brand navy (NOT white) — correct per "style=palette from brand", and ZERO orange.
- **Frames (/tmp/hero-stripe):** (0) Stripe wordmark + "Build internet businesses", legible; (1) REAL stripe.com homepage "Financial infrastructure to grow your revenue" in browser card, caption https://stripe.com, real customer logos; (2) REAL stripe.com/pricing "Pricing built for businesses of all sizes" Standard/Custom cards, caption https://stripe.com/pricing (matches emphasis); (3) walkthrough clip in branded frame, overlay "Stripe — Follow along as we create a subscription plan…"; (4) CTA "Start building your online business today at Stripe".
- **VO is GROUNDED in Stripe's real product** (NOT hollow): "Stripe builds internet businesses…", "the backbone of global commerce, connecting merchants and shoppers", "On the Billing page, Stripe enables any billing model—subscriptions, one-time sales, or usage-based pricing", CTA "Start building your online business today at Stripe.com." → **P6 grounding gap is NOT present here** (stripe.com fetchable → brand_extract worked).
- **CAVEAT (cached-clip mismatch, expected):** walkthrough overlay narrates "create a subscription plan, add a customer" but the cached `/tmp/walk-smoke.mp4` actually shows the Pricing page + "Click Pricing" step badge. Content↔overlay mismatch is an artifact of reusing the cached clip per AUTONOMY MODE; a real build would carry the actual pricing-page capture matching the emphasis.

## DONE (this session)
- **P1 — VERIFIED.** screenshots capture (`capture_screenshots.py` + `.venv-capture/` for Playwright on py3.11, host-py auto-re-execs) + Remotion `apple-screenshot` archetype. Verified: real orinovate.com homepage renders in a white brand browser card w/ Apple shrink/zoom. Capture is mode-independent. Planner doesn't emit screenshot scenes yet (P3).

## DONE — ORANGE KILLED (2026-06-22, agent a7eb5a73) — VERIFIED
- `build_runner.py` overlays="studio" ALWAYS + `orchestrator.py` `studio_active=(overlays=="studio")`, plus `and mode=="mock"` guards added to the 3 real-media branches (walkthrough gen ~368, paid cinematic approve ~517, downgrade ~556) so real walk-agent/Higgsfield STILL fire in real mode. Re-rendered orinovate in REAL mode (runs/verify-decouple, mode=real): all 5 scenes WHITE studio cards, ZERO orange; full suite green, $0. **Payment/real-mode videos are now clean white-card — the recurring orange is gone.**

## DONE — P2 walkthrough-player (2026-06-22, agent a67d) — VERIFIED
- Remotion `walkthrough-player` (OffthreadVideo) plays a walkthrough mp4 inside a brand-tinted frame with overlay title bar; contain-fit, muted (VO owns audio); `build_timeline.py` media-duration floor (clip never truncated); `style_fill.py` role walkthrough→walkthrough-player w/ explainer-card fallback. apple-screenshot (P1) coexists (tsc clean). Tests green, $0, no NIM (reused cached clip). Re-encode: OffthreadVideo needs faststart h264 (`-movflags +faststart -c:v libx264 -an`).

## DONE — P3 THE INTEGRATION (2026-06-22) — VERIFIED (frame-read, $0, no NIM)
A mock-pay STANDARD build now produces a COMPLETE video: branded open → real site screenshots → guided walkthrough → CTA. Details in `.handoff-p3-integration.md`.
- **Planner re-admits screenshot+walkthrough for STANDARD.** `plan_job`: STANDARD prompt + NEW `_enforce_standard_structure` backstop forces `title → 1-2 screenshot → 1 walkthrough → title` (re-types stray scenes, synthesizes a walkthrough if missing); `_standard_template_plan` rebuilt to that shape. `validate_planner.schema_check` `allowed_types` quality-gated (standard={title,screenshot,walkthrough}); `plan_schema.ALLOWED_TYPES += screenshot` (model-null); `planner-prompt.md` "NEVER include a walkthrough" → STANDARD structure. PREMIUM unchanged.
- **`emphasis` → specific walkthrough goal** (avoids the P2 one-nav-link loop). Threaded plan_job→job→build_runner argparse/run; walkthrough brief = "From the homepage, navigate to and demonstrate the {emphasis} feature, showing 2-3 distinct steps."
- **Real assets wired.** `style_fill.wire_captured_assets` maps shot-NN.png→screenshot scenes' `data.imageSrc` (+caption=page URL) and the clip→walkthrough `data.videoSrc`; runs in `run_pipeline` before build_props (`_stage_audio` stages both into public/). `adapters.generate_walkthrough` CACHE OVERRIDE honors `WS_WALKTHROUGH_CACHE` (mode-independent, $0). NEW `adapters.generate_screenshot_clip`; orchestrator `FREE_TYPES += screenshot` + screenshot branch; `_walkthrough_gen` mode-independent (cache wins).
- **VERIFIED:** `WS_WALKTHROUGH_CACHE=/tmp/walk-smoke.mp4 PRODUCER_SIMULATE_PAID=1 build_runner.py --url orinovate.com --emphasis "instant quoting" --run-id p3-standard-verify --mode mock --quality standard` → **delivered**. Frames (/tmp/p3-verify): (1) white Orinovate title; (2) REAL orinovate.com homepage in a browser card; (3) REAL orinovate.com/materials in a browser card; (4) walkthrough clip in a branded frame ("Orinovate — …" title bar, cached Stripe clip stands in, no NIM); (5) grounded CTA "Get an instant quote at Orinovate". ALL white/on-brand, ZERO orange, no hollow copy. `./run_all_tests.sh --no-eval` → ALL PASSED, $0, **no rebaselining needed**.
- NOTE: in a REAL build the walkthrough scene carries the actual Orinovate walk-agent capture; verification reused the cached clip per AUTONOMY MODE (no fresh NIM).

## NEXT ACTIONS (in order)
1. DONE: orange-kill · P1 screenshots · P2 walkthrough-player · P3 integration (complete Standard build verified, all white, no orange, no hollow copy).
2. [IN FLIGHT] **Hero STRIPE Standard video** (agent a2cc844609d381db5) — watchable, brand-coherent deliverable (real stripe screenshots + cached stripe walkthrough + grounded VO), $0 no-NIM; also assesses VO grounding.
   - **P4 dashboard EMPHASIS field — DONE** (agent a15f0a84): index.html input + app.js POST `emphasis` + serve.py `--emphasis` (shlex-quoted, empty-safe). REQUIRES a `:3030` restart + hard-refresh to go live — batch with the dashboard UI proof.
3. If hero VO comes back HOLLOW (brand not grounded): **P6 grounded VO** — `validate_planner.py`: let the planner use world knowledge of known brands when scraped facts are thin + an anti-"describe-the-animation" rule; `plan_job` de-stage-direction the template beats. (Stripe is fetchable so may already ground; TripAdvisor-class bot-blocked brands need this.)
4. After P4 lands: **orchestrator restarts :3030**, Chrome-verify the 3-field composer, then run ONE full Standard build through the DASHBOARD (mock-pay) end-to-end as the UI proof.
5. Optional (~1 NIM): one FRESH walk-agent capture for a brand-correct walkthrough (stripe safest; orinovate if reachable) → swap into a hero build.
6. **Morning report** for Dennis at the top of this file.
