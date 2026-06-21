# OVERNIGHT EXPERIMENT LOG — 2026-06-20 (autonomous; Dennis asleep)

## Mandate
Run loops overnight: experiment with videos for various companies × styles (snappy/standard/cinematic), improve the dashboard UI onboarding for first-time users, and experiment with real Higgsfield generation within a HARD $5 cap. Weight toward win-relevant learnings.

## BUDGET — HARD CAP (most important)
- Higgsfield baseline at start: **2423.3 credits** (ultra plan).
- **HARD CAP 400 credits** (Dennis tightened from 500) → **STOP all paid gens when balance reaches ~2023.3** (400 consumed). Use them fully but never exceed.
- `higgsfield account status` BEFORE every real gen; record before/after. Most work = $0/mock.
- **NO other paid APIs** (ElevenLabs etc. OFF). Walk-agent/NemoClaw compute is free → OK.

## Rules
- **Serial builds only** (one at a time) — avoids the `active.tsx` concurrent-build race.
- $0-first. Real credits only on informative experiments (cinematic prompt A/Bs, a couple of real style comparisons, the Orinovate re-run).
- **Do NOT touch:** the submission video (Dennis's craft), `stripe login` / the real-money-shot, the rules-verify, or protected runs (demo-1..4, build-stripe-9e7829, hermes-driven-01).
- Checkpoint every iteration below. Morning: summary + one PushNotification to Dennis.

## Win-weighted agenda
- **A. Experiments (Dennis's ask):** companies × styles (mock $0) → portfolio + generalization bugs; real Higgsfield cinematic prompt A/Bs (metered); Orinovate paid re-run (within cap, validates BEAM + real path).
- **B. UI onboarding (Dennis's ask):** make the console self-explanatory for a first-timer (frontend-design).
- **C. $0 win-mover engineering (bonus, from TECHNICAL-ROADMAP):** verify the loudness-into-build-path fix; serialize the `active.tsx` race; build the orchestrator↔webhook budget bridge (so the real money-shot is ready for Dennis's `stripe login`).

## Iterations
_(appended below as each completes)_

## Iteration 1 — figma.com × 3 styles ($0)
_2026-06-20 ~01:50. $0/mock, SERIAL builds, read-only on code. No paid gens. Higgsfield balance untouched._

**What ran.** 3 mock builds for `https://figma.com` (a brand NOT in BRAND_PALETTES), goal "30-second explainer plus a short walkthrough", via `PRODUCER_SIMULATE_PAID=1 ... build_runner.py --mode mock --pace {0.6|1.2|2.0}`. Mapped snappy→0.6, standard→1.2 (default), cinematic→2.0. All three delivered:
- `runs/overnight-figma-snappy` (pace 0.6) — delivered, 6 scenes, final.mp4 30.00s
- `runs/overnight-figma-standard` (pace 1.2) — delivered, 6 scenes, final.mp4 30.00s
- `runs/overnight-figma-cinematic` (pace 2.0) — delivered, 6 scenes, final.mp4 30.00s
All: 1920×1080 @ 30fps, exactly 30.000s, with audio. Kept as portfolio.

### KEY FINDING — styles do NOT differentiate the OUTPUT (architectural, not stochastic)
`--pace`/`PRODUCER_PACE`/the dashboard "Snappy/Standard/Cinematic" pill have **zero effect on the rendered video.** Evidence chain:
- `build_runner.py:74` sets `PRODUCER_PACE=str(pace)`; the ONLY consumer is `orchestrator.py:110-117`, where it is used solely as `time.sleep(pace)` between ledger writes — a live-console watchability beat. It never reaches the planner, scene durations, cut rhythm, motion, or music.
- The Nemotron planner (`plan_job.py` → `validate_planner.SYSTEM_PROMPT`) receives ONLY `company_url, goal, target_duration_s`. Pace/style is never passed in. The planner-prompt enforces a FIXED structure (open title, 2-3 cinematic, exactly 1 walkthrough, close title) regardless.
- **The dashboard pill is silently dropped at the server.** `app.js` POSTs `{pace: "snappy|standard|cinematic"}` to `/api/build` (and its own comment admits "the backend may map it ... or ignore it harmlessly"). `dashboard/serve.py:_api_build` reads only url/goal/mode/duration and builds the `build_runner.py` cmd WITHOUT `--pace` (serve.py:205-207). So from the dashboard, all three pills produce the identical build. Even via CLI, `--pace` only changes how long the console animation lingers.
- Hard proof: the 3 opening-title frames are byte-identical (md5 `8bce51ae...` ×3). The plans DO differ (durations 7+7 vs 6+5 vs 8+7; scene-id naming) but that is Nemotron per-call stochasticity, NOT a pace response — and it's non-monotonic (snappy walkthrough=8s > cinematic walkthrough=6s, the opposite of what "cinematic" implies). All 3 sum to 30s because the planner anchors to the identical `target_duration_s`.

**Proposal to make styles actually differ (no new paid surface):**
1. Map the pill to a `style` enum and thread it through `serve.py → build_runner --style → plan_job.plan_job(...) → planner prompt`. Today `--pace` is a float that does the wrong job; add a real `--style {snappy,standard,cinematic}`.
2. Inject style into the planner SYSTEM_PROMPT as duration/rhythm guidance: snappy = 6-8 short scenes, 2-3s holds, more motion_graphic cuts; cinematic = 4-5 scenes, longer 6-9s holds, fewer cuts, prefer `seedance_2_0` motion plates over stills. Keep `target_duration_s` constant so the total stays 30s but the cut count/hold length changes.
3. Cheap deterministic backstop if you don't want to trust the LLM: a post-plan re-timer in `build_runner`/`orchestrator` that redistributes the fixed 30s across scenes per style (snappy: compress holds, split into more beats; cinematic: merge/extend holds) and sets a per-style transition/motion-intensity flag consumed by `remotion_codegen` (e.g. faster ease + whip-cuts for snappy, slow cross-dissolves for cinematic). Music tempo flag can ride the same enum.
4. Keep `PRODUCER_PACE` as-is for console watchability, but decouple its name from the user-facing "pace" pill so they stop being conflated.

### Generalization verdict — ACCEPTABLE but OFF-BRAND, with 3 real bugs
figma.com → `_default` palette (`_brand=generic`, `_name="Figma"`, `_host="figma.com"`): dark `#0A0D0C` bg, lime `#7CFFB2` + violet `#9A8CFF` aurora, SF-Pro stack. Title frames are clean and professional (NOT broken/amateur) — see "INTRODUCING / Figma" open and "GET STARTED / Start building / figma.com" close. BUT it's the generic lime/violet aurora, not Figma's real identity (white bg, multi-color red/purple/green/blue). So a viewer who knows Figma reads it as a generic SaaS template, not "a Figma video." For a true fresh-brand pitch you'd want a brand-color fetch (Chrome MCP) → palette, which BRAND_PALETTES hardcoding doesn't do.

**Planner quality (fresh brand): GOOD.** Nemotron produced sensible, genuinely Figma-specific plans every time — VO beats reference live multiplayer canvas, assets panel, components, "4 million designers", prototyping. VO is scene-aligned (one beat per non-... scene, keyed by scene_id). Strong on a brand it has no kit for.

**Bug 1 (HIGH, on-screen garble — input-dependent).** Snappy's motion-graphic divider rendered "**S Brand Colors And The Text**" instead of "Built for teams". Root cause: `_section_label` in `remotion_codegen.py` (~line 411) extracts the first quoted phrase with `re.search(r"['\"...]([^...]+)['\"...]", b)`. The brief was *"...divider with Figma**'s** brand colors and the text 'Built for teams'."* — the possessive apostrophe in "Figma's" is matched as an opening quote, so the capture spans `"s brand colors and the text "`. Any apostrophe BEFORE the intended quoted phrase breaks it. Stripe/Linear/Notion/Vercel briefs didn't trigger it; a brand name that invites possessive phrasing does. Fix: ignore intra-word apostrophes (require quote to be at a word boundary / not flanked by letters), or prefer the LAST quoted pair, or strip possessives before matching. The standard & cinematic builds (briefs with clean `'...'` and no preceding apostrophe) rendered their stat label correctly — confirms it's the apostrophe, not the extractor in general.

**Bug 2 (MED, off-domain CTA + VO/title contradiction).** Every closing title is hardcoded `"Start building"` (`_copy_from_brief` ~line 465: `return "Start building", host or name, "Get started", "→"`). For a design tool this is wrong-domain, and it directly contradicts the brand-aware VO beat "Start designing for free at figma.com." The title ignores the scene brief/VO entirely. Fix: derive the CTA verb from the plan (brief/VO beat) or from a brand-category hint, not a Stripe-flavored constant.

**Bug 3 (LOW, cosmetic).** `_default` palette has no `tagline` key, so the open card's subtitle line is empty for any non-kitted brand (Figma open shows only "INTRODUCING / Figma", no tagline — Stripe would show "Build internet businesses"). Fix: synthesize a tagline from goal/VO, or pull it from the site.

**Bugs that did NOT appear:** payment gate, pricing, plan validation, VO generation (6 beats, scene-keyed), index refresh, mp4 finishing all worked clean across all 3 runs at $0. Art-directed titles render correctly except the two cases above.

## Orchestrator progress log
_Appended by the orchestrator (sole writer of this section)._
- **Branding (DONE, $0):** `NAMING-AND-LOGO.md` + `branding/` (6 SVGs). Top names: **Walkwright** (Walk-lineage, "-wright = maker", recommended) and **Showrunner** (fresh; needs a name-collision check). For Dennis to pick.
- **Card-copy bug fixes (DONE, $0):** all 3 iter-1 bugs fixed in `remotion_codegen.py` — apostrophe garble (now "Built for teams", frame-verified), per-brand CTA (Figma→"Start designing"), tagline fallback. 24 new tests + 43 total green. Other brands unaffected.
- **UI onboarding (DONE, $0):** first-run landing (eyebrow → word-built hero → 4-beat Plans→Prices→Produces→Ships strip → "Paste a URL" + "See a finished example" CTAs) + labeled inputs/placeholders/tooltips + distinctiveness (frontend-design). 23/23 checks. serve.py untouched.
- **IN FLIGHT:** real-Higgsfield prompt A/B (gpt_image_2 stills, ≤40cr this round, sole spender); styles-differentiation feature (`--style` enum; standard = unchanged).
- **QUEUED:** continue the real-gen loop toward the 400 cap (then a few Seedance videos with the honed prompt) · orchestrator↔webhook budget bridge ($0) · verify loudness-in-build-path · Orinovate real re-run (within cap).
- **serve.py:** restarted ~01:55 (pid 92067) → run-delete + `?paid=` redirect ARE live. The styles-feature's serve.py change (pill→`--style`) will need ANOTHER restart after it lands — flag for morning.

## Iteration 2 — real Higgsfield prompt A/B (gpt_image_2 stills) — 35cr
_Spend 2423.3 → 2388.3 (**35cr; cumulative 35/400**). Stills only, capped, cost-previewed, no retries._
- **MODEL SHIFT (important):** gpt_image_2 now runs `videotape-alpha` and renders UI text **legibly** (real Stripe API tokens/curl correct). The video-gen review's "garbles all text" HIGH is **largely OBSOLETE for stills** — re-verify before acting on that item.
- **Winning formula → two-track `cinematic_prompt(brief,brand,kind)`:** (1) literal-UI/hero = brief + cinematography scaffolding only (NO anti-text); (2) abstract/establishing = cinematography + brand-hex injection + anti-text guard + negative-space-for-title. Model-robust tokens (carry to Ultra): cinematography style string, brand-hex injection, conditional anti-text clause.
- Best stills: `evidence/prompt-ab/b-cinematography.png` (literal-UI hero), `e-fullformula.png` (abstract establishing).
- **Next:** implement the `cinematic_prompt` builder in `adapters.py` ($0), then real **Seedance video** with it (metered, ~365cr left to the cap).

## cinematic_prompt builder (DONE, $0)
- `adapters.cinematic_prompt(brief, palette, kind)` + `detect_kind(scene)` wired into `_generate_cinematic_real` (verbatim brief → honed two-track formula). 18 new tests + orchestrator 6 + higgsfield-parse 25 green; mock path unchanged.
- **$0 follow-up (after styles-feature frees orchestrator):** scenes have `company_url:null`; real value is `job["company_url"]` — pass `company_url=job.get("company_url")` at `orchestrator.py:288` & `:317` so establishing plates get real brand hexes (until then `palette_for(None)`→`_default`).

## Iteration: styles differentiation (DONE, $0)
- `--style {snappy,standard,cinematic}` threaded serve.py→build_runner→plan_job→planner + a deterministic re-timer + per-style entrance-speed (SPD) in remotion_codegen. **standard = byte-identical to today (verified — no demo regression).** 3 distinct figma mock builds: snappy 7 scenes/4.6s holds/SPD0.6, standard 5/8.0s/1.0, cinematic 5/8.7s+2s-titles/1.45 — 3 distinct md5s. Tests green.
- serve.py changed → needs a restart for the live dashboard pill→style path (CLI-verified for now; same restart that activates delete). Honest limit: at 30s the ≥3-content-scene schema floor caps cinematic-vs-standard distinctness; snappy is robustly distinct; the re-timer guarantees the three never render identical.

## Iteration 3 — real Seedance VIDEO A/B (54cr; cumulative 89/400)
_Spend 2388.3 → 2334.3 (54cr = 2 × 27cr; **Seedance 6s/720p = 27cr/clip**, not 22.5). Floor fine._
- **The honed `cinematic_prompt` formula DECISIVELY beats the verbatim baseline on real video.** Baseline garbled text under motion ("Plusiyly be Dos Datas", gibberish toast); formula = cinematic floating glass device, brand rim-light, slow drift, title-room, NO garbled text.
- **KEY nuance:** videotape-alpha's still text-legibility does NOT carry to Seedance VIDEO — video garbles text under motion → the anti-text guard IS needed for video.
- **Refinement (spinning the $0 fix):** `detect_kind` should route ALL video models to the anti-text "establish" track (never "hero" for video).
- Best clip: `evidence/seedance-ab/formula.mp4` (canonical establishing-plate exemplar). **Cumulative spend 89/400.**

## detect_kind fix (DONE, $0)
- `detect_kind` now forces ALL video models to the anti-text "establish" track (hard override: `if model != "gpt_image_2": return "establish"`). "hero"/no-anti-text is reachable only for the gpt_image_2 still (where videotape-alpha renders text legibly). 46 tests OK + run_all_tests green. Fixes the exact video-garble case from iter-3.

## Webhook bridge (DONE, $0) — the REAL money-shot is wired & ready
- `orchestrator.write_active_budget()` writes `runs/active_budget.json` ({budget_cents,spent_cents}) at budget-lock + before each authorize + a final refresh — exactly what `stripe_webhook.py` reads (closes the {0,0} gap). Over-budget cinematic charge → REAL decline via the listener, no human.
- **Dry-run verified ($0, no stripe login):** scenario_decline → orchestrator wrote {budget:37,spent:22}; 60c → DECLINE, 15c → APPROVE via a full local HTTP dry-run of the listener (crafted `issuing_authorization.request` events). 5 new tests + run_all_tests green.
- **company_url fix DONE:** cinematic gen call sites pass `job["company_url"]` → establishing plates get real brand hexes (Stripe→635bff injected).
- **MORNING STEPS (Dennis) to capture a real declined auth:** `stripe login` → `python3 stripe_webhook.py` → `stripe listen --events issuing_authorization.request` → an over-budget `--mode real --stripe-live` run → declined auth appears in the dashboard. (In `.handoff-webhook-bridge.md`.)
- **Regression found (fixing):** styles-feature's `style=` kwarg broke `tests/test_build_runner_failure.py` (stale monkeypatch lambda) — missed because that test isn't in `run_all_tests.sh` (audit F1). Fixing the mock + wiring the new test files into the runner.

## Iteration 4 — real portfolio clips (54cr; cumulative 143/400)
_Spend 2334.3 → 2280.3 (54cr = 2×27). detect_kind fix verified e2e — both video gens took the anti-text establish track._
- 2 agency-grade brand-faithful establishing clips: `evidence/portfolio/linear.mp4` (indigo, dev-tool) + `evidence/portfolio/airbnb.mp4` (coral, consumer — LEAD piece). + iter-3 Stripe `formula.mp4` = a 3-brand establish-plate reel. **The formula generalizes across genres + palettes.**
- **Finding:** a Spotify prompt → `nsfw` content-filter false-positive (**$0, no charge**; swapped to Airbnb). Improvement: neutral-phrasing/moderation guard on the establish template (prefer "app interface/device mockup" over "experience/listening"); optional $0 moderation dry-run. Real-gens now use neutral phrasing.

## Verification + test-runner fix (DONE, $0)
- **Loudness-in-build-path VERIFIED:** fresh mock build delivered at **−15.1 LUFS** (ebur128) vs the −19.9 broken baseline → loudnorm IS firing in the build path (in `adapters.stitch()` at `adapters.py:746`, muxing VO over the concat master). ~1.1 LU below −14 = single-pass loudnorm artifact; a two-pass in stitch() would hit exact −14 (flagged, not done).
- **Test regression FIXED:** `test_build_runner_failure.py` monkeypatch now accepts `style=` → 9 tests OK.
- **Audit F1 closed:** `run_all_tests.sh` now runs all new test files (2b unittest + 2c stripe_earn by-path); `--no-eval` → ALL GREEN, $0. The suite now covers the new code.

## Iteration 5 — real portfolio clips (54cr; cumulative 197/400)
_Spend 2280.3 → 2226.3 (54cr = 2×27). Neutral phrasing held (no nsfw)._
- `evidence/portfolio/robinhood.mp4` — single iPhone hero push-in, clean Robinhood green, no garble. **PORTFOLIO-WORTHY.**
- `evidence/portfolio/shopify.mp4` — gorgeous multi-element render but accent read orange (desaturated hexes under-weighted) + faint bottom caption-garble. Portfolio-worthy WITH a lower-third band / bottom crop.
- **Formula learnings (baking into `cinematic_prompt`):** (1) prefer SINGLE-hero/photo-content framing — multi-element UI-label layouts reintroduce garble; (2) NEVER name UI-text nouns — even "blurred placeholder labels" CUES text rendering; (3) SATURATED brand colors steer far better than desaturated. ~half the 400 ceiling left.

## cinematic_prompt v2 (DONE, $0)
- Baked iter-5 learnings into the establish track: single-hero framing (+ multi-element negation), removed ALL positive UI-text nouns (anti-text is now a trailing pure-negative only), saturated brand hex (`_saturate_hex` HSV; Shopify olive→vivid green; already-vivid stays). 33 tests (was 18); hero track byte-identical; suite green. `_generate_cinematic_real` uses it automatically on the next real Seedance gen.

## Iteration 6 — Orinovate COMPLETE real video + BEAM fix VALIDATED (7cr; cumulative 204/400)
- **Complete 5-scene REAL Orinovate video** `runs/build-orinovate-edf804/final.mp4` (28.4s, 1080p, audio −15.1 LUFS): opening title → Seedance cinematic → gpt_image_2 still (team + Orinovate dashboard) → walk-agent walkthrough (real site, **UN-CLIPPED**) → closing title. All real, none cut, ledger status `complete`.
- **BEAM fix VALIDATED:** walkthrough capture shows the Orinovate logo + full top nav intact (the ~80px/side slice is gone). The crystal-clear step-by-step goal navigated correctly. Evidence: `clips/03_walkthrough-demo.beam-evidence-7s.png`.
- **CRITICAL GOTCHA:** the BEAM fix on the HOST `walk-ultra/explainer-agent/agent.sandbox-v26.js` was NOT enough — the SANDBOX runs a stale BAKED `/sandbox/explainer-agent/agent.js`. The agent had to DEPLOY the fixed file into the sandbox (`agent.js.pre-beamfix.bak`). **Editing the host file alone doesn't change a running sandbox — the baked copy must be deployed.** Now deployed + proven.
- Walk-agent: SUCCESS (no 403/hang/reset). 7cr (still only). Cumulative **204/400**.

## Iteration 7 — v2 validation + NVIDIA (54cr; cumulative 258/400)
_Spend 2219.3 → 2165.3 (54cr = 2×27)._
- **Shopify v2 (`evidence/portfolio/shopify-v2.mp4`):** garble FIXED (single-hero killed the caption strip — zero pseudo-text) BUT brand green still NOT steering (saturated `#468E15` read amber/iridescent — the model's default rim beats a muted/olive hue). Garble-fix is a real win; not brand-faithful yet. (iter-5 `shopify.mp4` kept for comparison.)
- **NVIDIA (`evidence/portfolio/nvidia.mp4`):** single GPU hero, vivid NVIDIA-green edge glow — saturated STRONG single hues steer reliably (like Robinhood). Clean, brand-faithful. **PORTFOLIO-WORTHY.**
- **v2 verdict:** single-hero VALIDATED (killed garble both times), no-text-noun VALIDATED, saturated-hex PARTIAL (works for strong hues, insufficient for muted/olive). **Next ($0): color-dominance phrase** (grade the WHOLE frame toward the brand color, not just a rim) → v3.
- Cumulative **258/400** (~142 left).

## cinematic_prompt v3 (DONE, $0) — color-dominance
- Added `_color_name(hex)` (HSV hue→plain name; works on muted/dark hues; "" for grey) + `_color_dominance()` → injects a WHOLE-FRAME brand-color grade ("green-dominant color grade, the entire scene bathed in green light (#468E15), green tinting the haze/reflections/background"). Establish track only; single-hero + no-text-noun + saturated-hex all intact; hero track byte-identical. 47 tests (was 33); suite green. **Not yet confirmed on real video → next real-gen re-tests Shopify under v3.** (A transient API rate-limit killed the first attempt at launch; retry succeeded.)

## Iteration 8 — v3 color-dominance validation (54cr; cumulative 312/400)
_Spend 2165.3 → 2111.3 (54cr = 2×27)._
- **v3 color-dominance WORKS as a steer:** Shopify v3 (`evidence/portfolio/shopify-v3.mp4`) — whole frame now ONE green-family color (rim/haze/floor/bg), ZERO amber/copper/purple chaos (decisive over v2). BUT hue over-steered to teal/emerald (~170°) not Shopify olive (~96°): plain "green" (5×) out-votes the hex (1×) → model anchors on prototypical bright green.
- **Slack v3 (`slack-v3.mp4`):** aubergine `#4A154B`→"magenta" → whole frame magenta-purple, ~on-target (~290° vs 299°) — color-dominance is FAITHFUL when the brand hue sits near a prototypical named color.
- **Verdict:** color-dominance = the answer for muted-hue STEER (kills chaos); PARTIAL on hue ACCURACY (faithful near prototypical names; over-steers in-between hues like olive). **Next ($0): finer color names** (olive→"olive green" not "green") so the prototype anchors closer → v4.
- Cumulative **312/400** (~88 left). Process note: set Bash `timeout:560000` on Seedance poll loops (a 120s-default poll auto-backgrounded but re-attached inline — no orphan).

## cinematic_prompt v4 (DONE, $0) — finer color names
- Finer hue→name map (`_color_hue_name`): 88–106° = "olive green" (both Shopify greens land here) + lime/emerald/teal bands + dark/muted qualifiers + an aubergine table. **Name/hex rebalance** in `_color_dominance`: paired "olive green (#468E15)" at every anchor (3× name / 2× hex vs v3's 5×/1×) — no bare generic color word stands alone. `#468E15`→"olive green", `#4A154B`→"aubergine". 51 tests; hero track byte-identical; suite green. Needs a real-Seedance re-roll to confirm olive lands warm (not teal).

## Iteration 9 — v4 validation (54cr; cumulative 366/400)
_Spend 2111.3 → 2057.3 (54cr = 2×27)._
- **Shopify v4 (`shopify-v4.mp4`):** hue swung 39° WARMER (v3 teal ~170° → v4 warm green ~131°), eliminating the cool teal — overshot the ~96° olive by ~35°. **Finer-name fix HALVED the miss (74°→35°).** Strongest/most-on-brand Shopify yet; v2/v3 = case study.
- **Twitch v4 (`twitch-v4.mp4`):** indigo `#9146FF`→~223° blue (vs ~262° indigo) — ~39° miss, same prototype-skew. Striking cohesive cinematic blue plate, no garble.
- **Cross-brand rule (CONFIRMED):** color-dominance ALWAYS unifies the frame; hue accuracy tracks proximity to the named prototype — near-prototype tight (Slack aubergine ~9°), off-prototype snaps ~35–40° off. Residual fix = a hue-fence ("warm yellow-green, not emerald") — future pure-prompt iter.
- Cumulative **366/400** (~34 left ≈ 1 clip). Portfolio = 10 clips (stripe/linear/airbnb/robinhood/shopify v1-v4/nvidia/slack/twitch) + the complete Orinovate video.

## Iteration 10 (FINAL) — Spotify (27cr; cumulative 393/400 — STOP)
_Spend 2057.3 → 2030.3 (27cr). Last spend; under the 400 cap (+7 over the floor)._
- `evidence/portfolio/spotify-v1.mp4` — Spotify green `#1DB954`→"emerald green": cohesive whole-frame green plate (god-rays, bokeh, neon rim, mirror floor), single hero, zero garble. Hue ~163° vs target ~141° (~22° miss — tighter than off-prototype brands, per the near-prototype rule). PORTFOLIO-WORTHY (strongest unified green of the set). Closes the long-empty Spotify slot. (One free-poll HTTP 502 → re-polled the same job, no paid retry, no orphan.)

---

# MORNING SUMMARY — overnight autonomous loop (Dennis asleep)

**Bottom line:** spent **393/400 credits**; produced an **11-clip real-Seedance portfolio reel** + a **complete real Orinovate video**; shipped a slate of **$0 pipeline fixes** (incl. wiring the **real Stripe money-shot**); ran a 4-stage **prompt-engineering improvement loop**. All verified; nothing exceeded the cap; demo-critical/gated items queued for you below.

## Portfolio reel — `evidence/portfolio/`
11 agency-grade real Seedance establishing plates: **Stripe, Linear, Airbnb (lead), Robinhood, NVIDIA, Slack, Shopify (v1/v2/v3/v4 = the case study), Twitch, Spotify** + the **complete 5-scene real Orinovate video** (`runs/build-orinovate-edf804/final.mp4`, walkthrough un-clipped, BEAM fix validated). Best picks: Airbnb, NVIDIA, Spotify, Shopify-v4, Orinovate (complete).

## Prompt-engineering arc v1→v4 (all $0 code; metered real-video validation)
- **v1** verbatim brief → garbled text under motion, flat screenshots.
- **v2** single-hero + no-UI-text-nouns + saturated hex → killed garble; decisively beats baseline on real video.
- **v3** whole-frame color-dominance → kills off-brand chaos (brand color dominates the frame).
- **v4** finer color names + name/hex rebalance → halved the muted-hue miss (Shopify v3 teal ~170° → v4 warm green ~131°, target ~96°).
- **Durable rule:** color-dominance always *unifies* the frame to one brand color; *hue accuracy* tracks proximity to the named prototype — near-prototype tight (Slack ~9°), off-prototype snaps ~35–40°. Residual fix = a hue-fence ("warm yellow-green, not emerald") — a future $0 iter. (Prompt learnings → carry to Ultra-550B.)

## $0 fixes shipped overnight (pipeline-level — future videos inherit them)
- **Real Stripe money-shot wired & ready** — orchestrator↔webhook budget bridge, dry-run-verified (60c→DECLINE, 15c→APPROVE). [#1 win-mover; needs your `stripe login` to capture.]
- **Styles differentiate** — `--style snappy/standard/cinematic` (standard byte-identical to today). [Needs serve.py restart for the live pill.]
- **cinematic_prompt builder** (v1→v4) + **detect_kind** (video→anti-text track).
- **Loudness verified** in the build path (−15.1 LUFS, was −19.9). **Card-copy bugs** fixed (apostrophe garble, per-brand CTA, tagline). **Test-runner gap closed** (all new tests now in `run_all_tests`; full suite green). **company_url** wiring (real brand hexes in prompts).
- Pre-loop this session: UI declutter + run-delete + motion polish + light/coral palette + onboarding; script panel; pay-gate; per-brand palettes. **Name + logo options** (`NAMING-AND-LOGO.md` + `branding/`; recommend **Walkwright**).

## Gotchas captured
- **Walk-agent BEAM fix:** editing the HOST `agent.sandbox-v26.js` is NOT enough — the sandbox runs a stale BAKED `agent.js` that must be DEPLOYED (done + proven this run).
- `gpt_image_2` now = `videotape-alpha`: renders STILL UI text legibly, but VIDEO garbles under motion (anti-text is video-only). Seedance 6s/720p = 27cr. Neutral phrasing avoids nsfw false-positives.

## Spend ledger (393/400)
still A/B 35 · Seedance A/B 54 · portfolio-1 (Linear/Airbnb) 54 · portfolio-2 (Robinhood/Shopify) 54 · Orinovate still 7 · v2-validate (Shopify/NVIDIA) 54 · v3-validate (Shopify/Slack) 54 · v4-validate (Shopify/Twitch) 54 · final (Spotify) 27 = **393cr**. (Balance 2030.3; floor 2023.3 held.)

## YOUR MORNING TO-DO (prioritized for the 6/30 deadline)
1. **`stripe login` + capture the real declined Issuing auth** — the #1 win-mover; bridge is ready, exact steps in `.handoff-webhook-bridge.md`. Makes the money-shot REAL, not modeled.
2. **Rules-verify** (@NousResearch post / Discord pinned / the form) — gates: is Hermes-must-drive mandatory? is reusing the prior-winning Walk Agent allowed? public repo + LICENSE? (`COMPETITION-COMPLIANCE-REVIEW.md` MUST-VERIFY.)
3. **Pick name + logo** (`NAMING-AND-LOGO.md` + `branding/`; Walkwright recommended; 5-min domain/handle check before locking).
4. **Restart `serve.py`** — activates run-delete + the styles pill→`--style` + the `?paid=` redirect (code-ready, restart-gated).
5. **Record the submission video** (your superpower) — `DEMO-BEAT-SHEET.md` (8 beats, cold-open, honesty guardrail). The #1 scored deliverable.
- ChatGPT cross-check docs: `WINNING-STRATEGY.md`, `TECHNICAL-ROADMAP.md`, `WIN-PLAN.md`, the three reviews + verifications.

**Loop stopped.** All agents done; nothing running. Detail above + in the per-iteration entries + the `.handoff-*.md` checkpoints.
