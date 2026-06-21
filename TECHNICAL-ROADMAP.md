# TECHNICAL-ROADMAP.md — engineering path to winning

**Project:** `~/Desktop/Projects/Hackathons/hermes-video-agent`
**Competition:** NVIDIA × Stripe × Nous · due 2026-06-30 (~10 days) · judged on usefulness / viability / presentation
**Scope of THIS doc:** the *engineering* work only. Submission/video/packaging logistics live in `DEMO-BEAT-SHEET.md` + `WIN-PLAN.md` and are deliberately out of scope here.
**Anchored to current state (verified 2026-06-20):** agentic pipeline works; a real Hermes agent drove it end-to-end on the free NVIDIA Nemotron (`evidence/hermes-driven-run/transcript.md`, session `20260620_000754_46aa2a`) → the **compliance floor is cleared**. The Stripe auto-decline is **SIMULATED** (`iauth_sim_…`, `stripe_money.py:171-180`). `$0` mock e2e validation was in flight (no `runs/validate-e2e-01/` dir on disk yet → did not complete). The one real run, `build-orinovate-edf804`, is `status: failed` (the now-patched Higgsfield parse bug) but left a recoverable `final.mp4`.

**How to read this:** every item is what / why-it-wins / effort / owner ([D]=Dennis-gated, [A]=I-can-build) / dependencies. Prioritized by **win-impact**, not generic best practice. Production-hardening that does not move the win is explicitly parked in Tier 3.

---

## Orientation: what is already shipped (do not re-do)

From the `.handoff-*.md` change-log, all verified:
- Scene-aligned VO (`orchestrator.py:376-440`; per-beat `start_s`, dropped cut-scene beats) — `.handoff-vo-align.md`
- Art-directed Remotion titles (animated brand-accent bg, brand font, motion) — `.handoff-artdirection.md` / `.handoff-orinovate-remotion.md`
- Higgsfield job-id parse hardening + `<clip>.higgsfield.json` sidecar persisted on submit (`adapters.py` `_extract_job_id`/`_persist_higgsfield_artifact`; 25 unit tests pass) — `.handoff-higgsfield-parse.md`
- −14 LUFS loudness normalization in finish — `.handoff-loudness-fix.md`
- Pay-gate + post-payment landing (real `cs_test_` Checkout via `stripe_earn.py`; `PRODUCER_SIMULATE_PAID=1` $0 affordance) — `.handoff-paygate-postpay.md`
- Dashboard declutter / motion / light palette — `.handoff-dashboard-*.md`
- Walk-agent BEAM viewport fix 1280×720→1440×900 (`walk-ultra/explainer-agent/agent.sandbox-v26.js`, `node --check` passes; **real-capture proof still pending**) — `.handoff-walkagent-beam-fix.md`

These are done. The roadmap below is only what *remains* and *moves the win*.

---

## TIER 1 — technical win-movers

These are the moves that change a judge's score. Two of three are Stripe-axis or generation-path *proof* artifacts that a JSON-output competitor ("HermesCo") structurally cannot produce.

### 1.1 — Make the Stripe money-shot REAL (THE top technical move)

**What:** Replace the simulated `iauth_sim_…` decline with a genuine Stripe `issuing_authorization` object whose `approved:false` decision is the *producer brain's own budget verdict* (`webhook_declined`), produced on an over-budget agent spend with no human in the loop.

**Why it wins (highest win-impact in the entire project):**
- It is the single **unbeatable Stripe-axis artifact**. Per `STRIPE-PRODUCER-DESIGN.md §B/§D` and `WINNING-STRATEGY.md §c`, the purest "an agent runs a business under real money controls" beat is *Stripe itself declining the agent's over-budget charge*. HermesCo ships JSON; it has no real Issuing object to show. A real declined-authorization object in the Stripe test dashboard, on camera, is a knockout the field cannot match.
- It **removes the only disqualifier-grade honesty caveat.** `COHERENCE-SYNTHESIS.md R1` and the compliance verification both flag that narrating the current `simulated:true` decline (which hardcodes reason `spending_controls`, `stripe_money.py:178`) as "Stripe declined it" is an overclaim *to a Stripe judge*. Today the truthful narration is weak ("the agent's budget governor"); a real object lets the narration be both true and maximal.
- The design already chose the credible mechanism: **real-time authorization decisioning** (`webhook_declined`), not `spending_controls` (cosmetic) and not `insufficient_funds` (which is what a US test account's `fund_balance`-blocked card actually returns — see `STRIPE-SETUP.md` "one open item"). The webhook reason *is* the brain's verdict, so it is funding-independent and on-message.

**The exact steps (sequenced; the wiring gap is the non-obvious part):**

*Step A — Dennis-gated, ~5 min, [D]:* bring up the Stripe CLI + listener.
```bash
brew install stripe && stripe login                 # one-time, TEST mode
python3 stripe_webhook.py                            # brain-as-money-layer, :4242
stripe listen --forward-to localhost:4242/webhook \
  --events issuing_authorization.request
```
`stripe_webhook.py` already exists, is stdlib-only, decides `approve/decline` from a budget-state file, and calls `POST /v1/issuing/authorizations/<id>/{approve|decline}` within the 2-second window (`stripe_webhook.py:56-104`). It self-checks for a key and refuses to start without one (`:122-124`). A `--dry-run` flag (`:117`) lets it decide+log with no Stripe round-trip for local verification first.

*Step B — [A], the real engineering, ~2-4 h: close the state-file wiring gap.* This is the piece that is currently missing and is **not** in any handoff.
- `stripe_webhook.py:35` reads its live budget from `runs/active_budget.json` → `{"budget_cents": N, "spent_cents": M}`. **The orchestrator never writes that file.** `orchestrator.py:184-341` calls `money.authorize(...)` four times (`:282, :309, :329, :341`) entirely in-process — it locks a budget and tracks `spent`, but does not externalize it. So even with the listener live, the webhook decides against `{0,0}` and approves/declines wrongly.
- Fix: have the orchestrator (a) write `runs/active_budget.json` at budget-lock with the locked `budget_cents`, and update its `spent_cents` after each approved scene; and (b) in `--stripe-live` mode, replace the in-process `money.authorize()` for the paid scenes with a real Stripe Issuing card *charge* via the test helper (`POST /v1/test_helpers/issuing/authorizations` on the provisioned card, `stripe_money.py:182`) so the charge actually fires the `issuing_authorization.request` event the listener is waiting on. Today `provision_card()` (`stripe_money.py:124-158`) makes a real card in live mode, but `authorize()` in live mode creates the test-helper authorization *and reads the verdict back* rather than letting the webhook decide — for the `webhook_declined` reason you want the webhook in the loop, so the over-budget scene's charge must round-trip through the listener.
- Then a single `--stripe-live` run whose final hero scene is priced over the remaining budget produces a **real declined `issuing_authorization`** in the test dashboard, reason = the brain's verdict. Capture it on camera.

**Effort:** Step A ~5 min ([D]); Step B ~2-4 h ([A]). The webhook server, card provisioning, key detection, and decision logic are all written — the remaining work is the orchestrator↔webhook state bridge + routing the over-budget charge through the listener.

**Owner:** [D] for `stripe login`/`stripe listen` (interactive, credential screen — Dennis does credential steps himself); [A] for the state-file + live-authorize wiring.

**Dependencies:** Step B can be built and `--dry-run`-verified *now* with no key in the loop (decision+log path). Step A + the real capture is gated on Dennis's `stripe login`. Decide go/no-go in P1 (`WIN-PLAN.md`); if no-go, the honest fallback is narrate-as-budget-governor (no code, but a materially weaker beat).

---

### 1.2 — Validate the REAL generation path (paid re-run)

**What:** Run one `--mode real` build end-to-end to completion and confirm the two fixes that have only ever been `$0`-verified actually hold on real capture: (a) the Higgsfield real path now persists the job-id and downloads the asset instead of dying at the parse (`.handoff-higgsfield-parse.md`), and (b) the BEAM 1440×900 viewport fix produces a walkthrough capture with no ~80px side-crop / no black bars (`.handoff-walkagent-beam-fix.md`).

**Why it wins:** the walkthrough is the project's weakest on-camera element (letterbox + internal-tooling tells, per the video-gen review) and is *also* the NemoClaw-pillar proof. The BEAM fix is the highest quality-per-effort lift in the project (`COHERENCE-SYNTHESIS.md R5`) — but it is unproven on a real capture. The Higgsfield parse fix is likewise only unit-tested; the one prior real run (`build-orinovate-edf804`) is `status: failed` precisely on this path. A clean real run turns two "should work" claims into shipped artifacts, and is the only way the NemoClaw + Higgsfield pillars appear in a recorded artifact rather than as `mode: mock` placeholders (all 9 committed runs except orinovate are mock).

**Effort:** ~5-10 min of paid wall-clock + spend (Higgsfield credits + ElevenLabs cents). The orinovate completed Seedance job (`cb5acbc2-…`) is already recoverable at $0; a fresh run re-submits and spends.

**Owner:** [D] — this is a paid call; per the money-gate rule, Dennis approves the spend. [A] integrates/verifies the output (ffprobe specs, frame spot-check, no crop) afterward.

**Dependencies:** independent of 1.1. Should run *after* 1.3 confirms the mock path is clean (don't burn money debugging a bug a $0 run would have caught). The Higgsfield parser is defensive but its create-without-`--wait` wrapper shape is still `UNCONFIRMED` (`.handoff-higgsfield-parse.md`) — if it misses, the new raise prints the raw response for a one-line key addition.

---

### 1.3 — Finish the `$0` mock end-to-end validation (in flight)

**What:** Complete the `$0` mock validation that was running (`.handoff-e2e-validation.md`, run-id `validate-e2e-01`) — it has **no run dir on disk**, so it did not finish. Re-run `orchestrator.py … --mode mock --vo edge` (or `build_runner.py` with `PRODUCER_SIMULATE_PAID=1`) and confirm the 6 documented checks: phase flow planning→awaiting_payment→producing→delivered with a real `cs_test_` earn block; complete cut (all scenes, valid 1920×1080); scene-aligned VO with dropped cut-scene beat; art-directed Remotion mid-hold frame; ~−14 LUFS; on-brand cards with no leaked direction-text.

**Why it wins:** it is the cheap regression gate that protects every Tier-1 spend. The repo has had a cascade of fixes land across ~20 handoffs (VO align, art direction, loudness, parse, pay-gate) — a single clean mock run proves they compose without regressions *before* 1.2 spends money or 1.1 goes live on camera. It also produces a committed delivered ledger showing the real `cs_test_` session (viability proof) at $0.

**Effort:** ~30 min including the 6 checks ([A], no spend).

**Owner:** [A].

**Dependencies:** none — do this first. It gates 1.2 (don't pay to discover a mock-catchable bug).

---

## TIER 2 — demo-safety hardening (so a live screen-record can't break/embarrass)

These are pulled forward from `PRODUCTION-READINESS-REVIEW.md` **specifically because they affect the live demo**, not because they are good production practice. A double-click or an on-camera file-leak during the screen-record is a presentation-axis loss.

### 2.1 — Serialize concurrent builds (the `active.tsx` race)

**What:** The Remotion render reads from one global file, `studio/src/generated/active.tsx` (`adapters.py:32`, render at `adapters.py:250-258`). `POST /api/build` (`serve.py:106`) fires an unbounded `subprocess.Popen` with no queue. Two overlapping builds — a double-click, or starting a second demo before the first finishes — have one build overwrite the other's component mid-render, silently producing a **wrong scene in the output video**. The prod-review rates this **BLOCKER** and demo-critical.

**Fix (either; the first is cleaner):** render each scene from a per-run temp file (`run_dir/_active_<scene>.tsx`) so builds never share the path; OR serialize `/api/build` behind a single-worker queue and return "queued"/429 on overlap.

**Why it's Tier 2 not Tier 3:** the failure mode is *undetectable on camera* (the video just contains the wrong scene) and *fatal to credibility* if a judge notices. A live demo with two clicks is exactly the trigger.

**Effort:** ~1-2 h ([A]). Per-run temp file is the smaller change.

**Owner:** [A]. **Dependencies:** none.

### 2.2 — Lock the static server + move `build.log` out of the web tree

**What:** `serve.py` serves `PROJECT_ROOT` over HTTP with a custom static/Range handler (`serve.py:31, :154, :236`) and no path-traversal guard. Everything is readable: `plan.json`, source, the `.handoff-*.md` change-log, and `runs/<id>/build.log` (`serve.py:123`) — which can contain printed env/diagnostics. During a screen-share, a stray tab or a directory listing **leaks internal scaffolding on camera** (the prod-review and `COHERENCE-SYNTHESIS.md R6` both call this out).

**Fix:** add a `realpath(...).startswith(realpath(root))` guard in `send_head`; serve only `dashboard/` + the media dir, not the project root; move `build.log` outside the served tree (or gate `/api/log/<run>`).

**Why it's Tier 2:** purely a *demo-leak* concern here (localhost-only, so not a real security exposure during the hackathon) — but a directory listing of `.handoff-*.md` / tracebacks on a recorded screen reads "unfinished."

**Effort:** ~1 h ([A]). **Owner:** [A]. **Dependencies:** none.

> Adjacent, cheap, same spirit (do alongside 2.2): suppress on-camera leak strings the dashboard/console currently surfaces — `"MONEY-SHOT:"`, `stripe login`, raw tracebacks, the `PRODUCER_SIMULATE_PAID` affordance label (`COHERENCE-SYNTHESIS.md R6`). ~30 min, [A]. Cosmetic but presentation-axis.

---

## TIER 3 — production robustness (PARKED unless time)

These are **real-product** concerns, **not hackathon-win** moves. A judge watching a 1-3 min recorded demo never exercises them. Park them; pick up only if Tier 1+2 are done with days to spare. Listed so a cross-check can see they were considered and deliberately deprioritized.

| Item | What | Prod-review severity | Why parked (not a win-mover) |
|---|---|---|---|
| Auth on `/api/build` | No token / Origin / CSRF check; client controls `mode:"real"` (`serve.py:106, :118`) → arbitrary local process can trigger real spend | BLOCKER (production) | Demo is single-operator on localhost; no multi-user threat in a recorded demo. Real product blocker only. |
| Crash/restart resilience | Server restart mid-build orphans the run; ledger frozen at `running`; dashboard polls forever (`serve.py` `start_new_session=True`, `build_runner.py:53`) | HIGH | Fix = heartbeat + stale-run reaper + cancel endpoint. Matters for an always-on service; a demo is a clean single run. Don't spend the 10 days here. |
| Atomic run-index | `_update_index` plain `open(...,"w")`, full rewrite per flush, written only at finish; crashed runs invisible (`orchestrator.py:395, :411`) | MEDIUM | Eventual-consistency cosmetic; rebuild-from-scan is the real fix. No demo impact. |
| Per-scene try/except + planner truncation guard | One ffmpeg/edge-tts failure aborts the whole job (`orchestrator.py:209+`); `finish_reason=="length"` can ship a truncated plan (`validate_planner.py:117-119`) | MEDIUM | *Borderline* — a transient failure mid-demo would hurt. But the mock validation (1.3) + a rehearsed click-path covers the demo path; the robustness version is product-grade. If 1.3 ever flakes, promote the per-scene wrap to Tier 2. |
| `generate_overlay` silent degrade | Remotion failure silently falls back to a color card (`adapters.py:232`) | MEDIUM (honesty) | Make the policy surface a `gate` event instead of burying it. Quality-honesty, not a win-mover; rehearsal catches it. |

**Note for the cross-check:** items here are correctly *real* (the prod-review is right that they're BLOCKER/HIGH for a shipped product). The judgment call is that a hackathon judged on a recorded demo does not exercise them, so spending the scarce 10 days on auth/restart-resilience instead of the Tier-1 Stripe artifact would be optimizing the wrong axis.

---

## Dependency-ordered execution sequence

```
[A] 1.3  $0 mock e2e validation        ── gates everything paid; no spend
            │   (clean mock run = regression gate before money/camera)
            ▼
[A] 2.1  serialize active.tsx race  ┐
[A] 2.2  lock server + move log     ┘  ── demo-safety, independent, do in parallel with 1.3
            │
            ▼
[A] 1.1B orchestrator → active_budget.json + route over-budget charge through webhook
            │   (buildable + --dry-run-verifiable NOW, no key needed)
            ▼
[D] 1.1A stripe login + stripe listen + python3 stripe_webhook.py
            │   (gated on Dennis; produces the REAL declined-auth artifact)
            ▼
[D] 1.2  paid --mode real re-run    ── after mock is clean; proves Higgsfield real path + BEAM capture
            │
            ▼
        (assets feed DEMO-BEAT-SHEET.md / video cut — out of scope here)
```

Rationale for the order: `1.3` is free and catches regressions, so it precedes every paid/live step. `2.1`/`2.2` are independent and can run alongside. `1.1B` (the orchestrator↔webhook state bridge) is the real engineering and is buildable+verifiable today with no credentials, so it should not wait on Dennis — only the *capture* (`1.1A`) is gated. `1.2` runs last among the paid steps because a clean mock (`1.3`) de-risks spending money to find a mock-catchable bug.

---

## The single highest-value technical move

**Build the orchestrator↔webhook state bridge and capture a real declined `issuing_authorization` (item 1.1).**

It is the only move that produces an artifact a JSON-output competitor structurally cannot — a genuine Stripe Issuing object, `approved:false`, reason = the agent's own budget verdict (`webhook_declined`), fired by an autonomous over-budget spend with no human in the loop — *and* it simultaneously removes the entry's one disqualifier-grade honesty caveat (narrating the current `iauth_sim_…` simulation as a real Stripe decline to a Stripe judge). Everything needed is already written (`stripe_webhook.py`, `provision_card`, key detection, the decision logic); the missing piece is small and buildable today without credentials: the orchestrator must write `runs/active_budget.json` and route the over-budget scene's charge through the live listener so the webhook — not in-process code — renders the verdict. That ~2-4 h of wiring plus Dennis's 5-minute `stripe login` converts the project's weakest, most-scrutinized beat into its knockout.
