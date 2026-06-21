# Competition Compliance Review — Hermes Agent Accelerated Business Hackathon

_Read-only audit, 2026-06-19. Scope: are we following the competition rules and using the four
sponsor pillars (Hermes / Nemotron / NemoClaw / Stripe) the right way? This is a compliance / rules-fit
review only — NOT UX (see `UX-IMPROVEMENTS.md`), NOT video quality (see `VIDEO-GENERATION-REVIEW.md`),
NOT infra hardening (see `PRODUCTION-READINESS-REVIEW.md`). $0 spent; no builds; no paid API calls; no
serve.py restart._

> **Authoritative-rules caveat.** The canonical rules live on the @NousResearch X post + a Discord
> pinned message + the official entry form, which cannot be fetched headlessly. Everything below
> labelled "verified from a public source" came from the NVIDIA blogs + Nous's own X/docs. Everything
> else is **our internal understanding** (memory + STRATEGY.md) and is flagged for Dennis to confirm
> against the live rules. See the MUST-VERIFY list at the end.

---

## TL;DR — the four verdicts

| Pillar | Verdict | One-line |
|---|---|---|
| **Hermes agent** | **AT-RISK** | The real engine is a standalone Python pipeline (`build_runner.py` → `orchestrator.py`) spawned by the dashboard via `subprocess.Popen(["zsh","-lc", …])`. The Hermes *runtime* never drives an end-to-end run. For an *agent* hackathon, a hand-built orchestrator is substituting for the agent — our single biggest compliance risk. |
| **Nemotron** | **COMPLIANT** | Genuinely the brain: real chat-completions calls to the free `nvidia/nemotron-3-super-120b-a12b` (the exact model NVIDIA names) for storyboard planning and budget-gate judgment, proven load-bearing by two live evals. |
| **NemoClaw** | **PARTIAL** | The integration is real (`tutorial-maker.sh` calls the `nemoclaw` binary to run a Nemotron agent in the `walk-ultra` sandbox), but it is gated to `--mode real`; every committed demo/build ledger ran `mode: mock`, so the artifacts show only a "walk-agent" placeholder card, not a sandbox run. |
| **Stripe** | **PARTIAL** | Earn side is correct and honest (real TEST-mode Checkout, refuses live keys, asserts `livemode==false`). Spend side is mostly *simulated*; a real declined Issuing authorization was proven once in a shell but is NOT in the pipeline by default, and the clean `spending_controls` decline needs the still-unwired webhook. The committed demos record `earn: dev_mode` (no Stripe session at all). |

---

## What the hackathon is (verified from public sources)

From the NVIDIA blogs and Nous's X/docs:
- **The prompt:** "builders making agents that can **earn, spend, and run real operations at any scale**."
- **The stack the sponsors want exercised:**
  - **Hermes Agent** = the **harness/runtime** — "skills, sessions, memory, bridges, hooks"; the
    operational engine that orchestrates agent behavior and lets it self-improve.
  - **Nemotron 3 Super (120B)** = the open reasoning model — "reasoning, tool selection, drafting."
  - **NemoClaw** = "a blueprint for open agents built with harnesses powered by open models in a
    **secure runtime**" — network policy as code, credential brokering, sandboxed execution.
  - **Stripe Skills for Hermes** = agentic commerce: the agent can "**buy things, pay per-call APIs,
    and provision its own SaaS, with configurable safety limits on every action**."
- **Prizes (verified):** 1st $10k + DGX Spark + $5k Stripe credits; 2nd $5k + DGX Spark + $3k; 3rd
  $2.5k + DGX Spark + $1k.
- **Submission (verified):** tweet a **1–3 min demo video tagging @NousResearch** + a short writeup,
  and drop the link in the **submissions channel on the Nous Research Discord**.

The through-line: the sponsors are grading **an agent running on their runtime**, not a clever
standalone program. That makes pillar 1 the decisive axis.

---

## Pillar 1 — Hermes agent  →  **AT-RISK** (highest severity)

**(a) What the hackathon expects.** Hermes is the *harness* and the deliverable is *an agent*. The
agent (Hermes runtime, driven by Nemotron, with skills) should DRIVE the end-to-end production. The
self-improving, skill-routing harness is the thing being judged — not a Python program that happens to
call an NVIDIA endpoint.

**(b) Our actual usage (evidence).**
- The producer flow is implemented as a **standalone Python pipeline** and is launched **directly**,
  bypassing the Hermes runtime entirely:
  - `dashboard/serve.py:124-128` — `/api/build` builds an inner command string and runs
    `subprocess.Popen(["zsh", "-lc", inner], …)` where `inner` = `python3 build_runner.py --url … --mode …`.
  - `build_runner.py:114` — `orchestrator.orchestrate(...)` is a **direct Python function call**.
  - `orchestrator.py` docstring (lines 5-7) is explicit: _"This is the deterministic Python harness for
    the producer-brain SKILL flow… the test suite asserts against it, and a live Hermes/Nemotron run
    should reproduce its gate verdicts."_ — i.e. the harness is the reference impl that Hermes is
    *supposed to* reproduce, not the thing Hermes runs.
- **No project code invokes the `hermes` binary.** A broad grep for `hermes chat` / `hermes` exec /
  subprocess across all `*.py`/`*.sh`/`*.js` returns nothing. The Hermes runtime is never in the
  execution path of a build.
- **What Hermes IS used for:**
  - A `producer-brain/SKILL.md` exists at `~/.hermes/skills/producer-brain/` describing the loop as a
    Hermes skill (it even hardcodes `python …/producer.py` as "the deterministic glue") — but nothing
    proves Hermes actually *runs* this skill end to end; the SKILL.md "Worked Example" cites a manual
    DRY-RUN transcript, not an autonomous Hermes run.
  - The **skill-routing eval** (`hermes_skill_eval.py`) tests whether Nemotron picks the right
    skill from `description:` lines — a Hermes-flavored test, but it routes *to a name*, it does not
    *execute* the skill.
  - The memory's **budget posture is explicit**: _"use Hermes ONLY for final orchestration validation."_
    That is exactly the substitution anti-pattern: the agent runtime is relegated to a rubber-stamp.

**(c) Verdict: AT-RISK.** Today, if a judge asks "show me the Hermes agent producing the video," we
show a Python pipeline in a browser console. The deliverable for an *agent* hackathon is an autonomous
agent that drives the work; ours is a hand-built orchestrator with Hermes bolted on for evals. This is
the classic "the agent is the deliverable, don't substitute a hand-built orchestrator" failure.

**(d) Gaps + concrete fix.**
- **Gap:** Hermes does not orchestrate a run; `build_runner.py`/`orchestrator.py` do.
- **Fix (make Hermes the driver, reuse the engine as the agent's tool):**
  1. Keep `producer.py` / `orchestrator.py` as **deterministic tools the agent calls** — do NOT
     rewrite them. The producer brain is good IP; the problem is *who pulls the trigger*.
  2. Turn the real run into a **Hermes skill the Hermes runtime actually executes**: the
     `producer-brain` skill should drive the loop by having **Hermes** make the PLAN call (Nemotron),
     then **Hermes** shell out to `producer.py estimate`/`gate` and the segment skills (walk-agent,
     higgsfield-scene, motion-graphics, video-stitch) step by step — i.e. `hermes chat -q "produce …"`
     is what runs a job, with the deterministic engine as its tools.
  3. Have the dashboard's `/api/build` (or at least the **submission-demo path**) invoke
     `hermes chat -Q -q "<producer-brain brief>"` so the on-camera run is genuinely the Hermes agent
     orchestrating, with `producer.py` as a called tool — not `python3 build_runner.py`.
  4. At minimum for the deadline: **record the demo video of a real `hermes chat` run** of the
     producer-brain skill (even if slower), so the agent visibly drives plan → price → gate → produce.
     The pretty live console can remain the *visualization*, but the run it narrates must be a Hermes
     run, or we must be scrupulously honest that the console is a UI over a Python pipeline.
- **Severity: HIGH.** This is the axis Nous (the runtime owner) grades hardest, and the one most
  likely to read as "you didn't really use Hermes."

---

## Pillar 2 — Nemotron  →  **COMPLIANT**

**(a) What the hackathon expects.** An **open model** (Nemotron) doing **real, load-bearing reasoning**
— planning and tool/judgment calls — not a decorative single ping.

**(b) Our actual usage (evidence).**
- **Right model, right endpoint, free tier:** `nvidia/nemotron-3-super-120b-a12b` over
  `https://integrate.api.nvidia.com/v1/chat/completions` (build.nvidia.com NIM, free). See
  `validate_planner.py:15-16`, `hermes_judgment_eval.py:28-29`, `hermes_skill_eval.py:23-24`,
  and Hermes `config.yaml` (`model.default: nvidia/nemotron-3-super-120b-a12b`,
  `model.base_url: https://integrate.api.nvidia.com/v1`, `model.provider: nvidia`). This is the
  *exact* model NVIDIA's NemoClaw blog names ("Nemotron 3 Super (120B) … reasoning, tool selection").
- **Load-bearing on the critical path:**
  - **Planning** — `plan_job.py:38-56` calls Nemotron (`vp.call_model`) to turn a URL+goal into the
    scene plan; the brief fields are forced and the plan is schema-validated (`plan_schema.validate_plan`).
    A deterministic template is a *fallback only* when the key is absent or the call fails — the real
    path is the model.
  - **Judgment** — the approve/downgrade/decline gate is the money-shot; `hermes_judgment_eval.py`
    proves the *live model* reaches the golden verdict on 7 scenarios incl. the decline (the memory
    records 7/7).
  - **Skill routing** — `hermes_skill_eval.py` proves the small model routes 19/19 requests to the
    right skill (after sharpening descriptions).
- **Reliability handling is real, not hand-wavy:** `max_tokens: 8000` with a JSON extract + one-repair
  guard, because Super-120B emits hidden reasoning tokens (`validate_planner.py:99-103`, `plan_job.py:51-54`).

**(c) Verdict: COMPLIANT.** Nemotron genuinely is the brain for both planning and judgment, on the
named open model and free endpoint, with two evals proving it makes the right calls.

**(d) Gaps + fix (minor).**
- **Gap:** the heavy production path (`build_runner`/`orchestrator`) makes ONE Nemotron call (the plan);
  the per-scene gate verdicts in a build are computed by deterministic `producer.py`, not by a live
  Nemotron call. The evals prove Nemotron *can* make those calls, but the running pipeline doesn't
  *use* it for them. **Fix:** in the demo run, let Nemotron make at least one visible per-scene gate
  call (the decline) live, so the on-camera judgment is the model's, matching what the evals claim.
- **Caveat to confirm:** the model is reached via the **NVIDIA NIM** endpoint directly, not via Hermes.
  Inside Hermes, `config.yaml` is also `provider: nvidia` on the same model — consistent — but see
  pillar 1: the running pipeline calls the endpoint with raw `urllib`, not through Hermes.

---

## Pillar 3 — NemoClaw  →  **PARTIAL**

**(a) What the hackathon expects.** The open model running **safely sandboxed** in NemoClaw — the
secure-runtime story (network-policy-as-code, credential brokering). NVIDIA wants to see the agent
actually *operating inside* the sandbox.

**(b) Our actual usage (evidence).**
- **The integration is real, not aspirational:**
  - `nemoclaw` binary present at `~/.local/bin/nemoclaw` (on PATH).
  - `walk-ultra/tutorial-maker.sh` genuinely drives it: `Step 2/4: NemoClaw agent run` and
    `"$NEMOCLAW" walk-ultra exec --no-tty -- …` (lines ~36, 55-68, 114). It runs a Nemotron agent
    inside the `walk-ultra` sandbox to navigate a site and render a walkthrough MP4.
  - `adapters.generate_walkthrough` (`adapters.py:189-205`) shells out to this script — but **only in
    `mode == "real"`**; `mode == "mock"` just renders a teal color card (`synth_clip`).
  - The memory records this path was validated end-to-end on 2026-06-18 (walk-ultra navigated
    docs.stripe.com, produced a 1440p60 mp4), incl. the `nemoclaw credentials reset nvidia-prod` 403 fix
    — so it genuinely works.
- **But it is not exercised in the committed artifacts:** every ledger in `runs/` is `mode: mock`. The
  `walk-agent` strings in those ledgers are the placeholder card / tool label, not a sandbox run. Only
  `demo-1`/`demo-3` carry `real_media: true`, and per the memory that real walk footage was swapped in
  by `apply_real_media.py` as a separate manual step — the NemoClaw run was not part of the
  orchestrated pipeline that produced the ledger.

**(c) Verdict: PARTIAL.** The NemoClaw integration is real and has been run once, but it is gated off
by default and absent from the demo artifacts. As shipped/visible, NemoClaw is a `--mode real` capability
we *can* show, not one the pipeline *does* show.

**(d) Gaps + fix.**
- **Gap:** the demo and all committed runs skip the actual sandbox; the walkthrough is a placeholder.
- **Fix:** in the submission demo, run **one real walk-ultra/NemoClaw walkthrough** (it's FREE — only
  slow, ~3-5 min) and put that real sandbox-produced clip in the cut, narrated as "the agent did this
  inside a NemoClaw sandbox." This converts NemoClaw from PARTIAL to a genuine on-camera beat at $0.
  The 403/credential-reset gotcha is documented; budget the 3-5 min.

---

## Pillar 4 — Stripe  →  **PARTIAL**

**(a) What the hackathon expects.** **Agentic commerce on Stripe rails** — the agent earns, then
*buys/pays/provisions* what it needs, with safety limits. Stripe shipped 3 Hermes skills
(`stripe-link-cli` = buy, `stripe-projects` = provision SaaS, `mpp-agent` = pay 402 APIs) for exactly
this. STRATEGY.md reads this correctly.

**(b) Our actual usage (evidence).**

_Earn side — correct and honest:_
- `stripe_earn.py` creates a real per-job **TEST-mode Checkout Session** (`mode: payment`, inline
  `price_data`, `client_reference_id = job_id`) — `build_session_params` (lines 92-113),
  `create_checkout_session` (116-152). This matches the memory's verified earn primitive.
- **Safety is rigorous:** `_assert_test_key()` refuses a missing key and **refuses any `sk_live_`/
  `rk_live_` key** (lines 49-69); it **asserts `livemode == false`** on every response and raises
  `LiveModeError` otherwise (138-142, 164-166). The key is detected by presence/length only and never
  printed (`stripe_money.detect_key`).
- **Pay-gate wired:** `build_runner._payment_gate` (130-202) creates the session, writes an
  `awaiting_payment` ledger, and polls `payment_status` to a 15-min cap before producing — production
  is genuinely gated on payment. `PRODUCER_SIMULATE_PAID=1` is a clearly-labelled $0 dev affordance.

_Spend side — mostly simulated:_
- `stripe_money.py` models the SPEND surface: `provision_card` (Issuing virtual card with
  `spending_limits`) and `authorize` (per-scene approve/decline). **In the pipeline these run
  simulated by default** — `orchestrator.py` constructs `StripeMoney(live=stripe_live)` and
  `stripe_live` defaults to `False` (orchestrate signature line 88; `--stripe-live` is opt-in).
  Simulated `authorize` returns `iauth_sim_…` objects (`stripe_money.py:171-180`).
- A **real declined Issuing authorization** was proven *once in a shell* (memory 2026-06-19: real
  virtual card + real declined auth objects created), but it is **not in the default pipeline path**,
  and on a US test account the over-limit decline comes back as `insufficient_funds`, **not**
  `spending_controls` — so the clean "Stripe's native cap declined it" shot needs the **real-time
  webhook** (`stripe_webhook.py`), which is **not wired** (blocked on Dennis's interactive `stripe login`
  + `stripe listen`).
- **The 3 Stripe Hermes skills are installed but unused at runtime.** STRATEGY.md is candid: the
  "agent actually BUYS the production credits via `stripe-link-cli`" reframe is the path-to-win but
  **"keep the SPEND simulated for now."** So the literal "agent spends on Stripe rails to buy what it
  needs" — the thing Stripe most wants — is **not demonstrated**; the spend is an Issuing *model* of
  the Higgsfield/ElevenLabs cost, not a real Stripe purchase of those services.
- **The committed demos don't even show the earn side:** every `runs/*/ledger.json` records
  `earn: {provider: dev, status: dev_mode}` and no `awaiting_payment` phase — i.e. those artifacts were
  produced by the older `orchestrator.py` path *before* the pay-gate, so the only Stripe evidence in
  the artifacts is the simulated `iauth_sim` decline. The real `cs_test_` session exists per the memory
  but isn't captured in a committed run ledger.

**(c) Verdict: PARTIAL.** Earn is real, safe, and honest. Spend is simulated by default; the one real
Stripe artifact (a declined Issuing auth) was a manual shell proof, not a pipeline beat, and the
cleanest version needs the unwired webhook. The agentic-commerce *spend* story Stripe wants most
(buy/provision via the Stripe skills) is documented but deliberately not built yet.

**(d) Gaps + fix.**
- **Honesty gaps to fix before the demo (these are overclaim traps):**
  - Do **not** narrate the simulated `iauth_sim` decline as "Stripe declined it." It is the brain's
    verdict mirrored into a Stripe-shaped object. The SKILL.md "Do NOT overclaim the money layer" rule
    already says this — hold the demo VO to it.
  - If showing a real declined auth, be precise: an unfunded US test balance declines as
    `insufficient_funds`; only the webhook yields a budget-reason decline. Narrate whichever you film.
- **Strongest fix for the Stripe axis (if greenlit for a small real spend):** wire ONE real
  `stripe-link-cli` purchase — the agent buys the generation credits it needs (human-approved in Link)
  — so there is *actual* Stripe spend, the thing Stripe is grading. Pair it with the autonomous Issuing
  budget-decline for the "safety limits on every action" beat. This is STRATEGY.md's own path-to-win.
- **Cheaper fix (no real money):** at least run ONE build through the **new pay-gate** so a committed
  ledger shows a real `cs_test_` session (`awaiting_payment` → `paid`) — that makes the earn side visible
  in an artifact, not just claimed in memory.

---

## Submission requirements checklist (DONE vs PENDING)

| Requirement (verified public) | Status | Note |
|---|---|---|
| 1–3 min demo video | **PENDING** | The console + decline + "agent codes Remotion" beats are built; the actual cut is not recorded. Dennis's craft piece. |
| Tweet tagging **@NousResearch** | **PENDING** | Account/tweet not yet posted. |
| Short writeup (in the tweet) | **PENDING** | STRATEGY.md is the raw material; no published writeup yet. |
| Post link in **Nous Discord submissions channel** | **PENDING** | Requires Discord membership + the right channel (verify the channel name against the pinned message). |
| Official **entry form** (if one exists) | **PENDING / UNCONFIRMED** | The memory references "a form"; confirm it exists and its fields/deadline against the live rules. |
| Deadline **EOD Tue 2026-06-30** | On track date-wise | **Timezone unconfirmed** — "EOD" in which TZ? Confirm (likely PT/ET). 11 days out. |
| Judged on **usefulness / viability / presentation** | Design aligns | Axes are our internal understanding (memory says user-supplied) — confirm against live rules. |
| Eligibility / team rules / IP / prize terms | **UNCONFIRMED** | Not verified from any public source. |

Build-side readiness that supports the submission: producer engine + tests green (26 checks per memory),
dashboard/live console built, demo runs exist, Stripe earn helper + pay-gate built. The *content* of the
submission (the video, tweet, post, form) is the open work.

---

## Top compliance RISKS (prioritized)

1. **[HIGH] Hermes doesn't drive the run.** The deliverable for an agent hackathon is an agent; ours is
   a Python pipeline (`build_runner.py`/`orchestrator.py`) spawned via `subprocess.Popen` with Hermes
   used only for evals/"final validation." Fix: make the demo run a real `hermes chat` invocation of the
   `producer-brain` skill, with `producer.py` as a tool the agent calls — or be scrupulously honest that
   the console visualizes a Python pipeline. **This is the most likely reason a judge says "you didn't
   use Hermes."**
2. **[MED] Stripe spend is simulated; agentic-commerce spend not demonstrated.** The thing Stripe grades
   (agent buys/pays/provisions on Stripe rails) is documented but not built; the only real Stripe
   artifact is a one-off shell-proved declined auth. Fix: either wire one real `stripe-link-cli`
   purchase (best) or at minimum run a build through the pay-gate so an artifact shows a real
   `cs_test_` session. Also: don't narrate the simulated decline as a real Stripe decline.
3. **[MED] NemoClaw absent from the demo artifacts.** Real integration, but gated to `--mode real` and
   not in any committed run. Fix: include one real (free) walk-ultra/NemoClaw walkthrough clip in the
   submission cut and narrate the sandbox.
4. **[LOW] Nemotron judgment is proven in evals but the running pipeline computes gates
   deterministically.** Fix: let Nemotron make at least one visible per-scene gate call live in the demo.
5. **[LOW] Submission mechanics unverified.** Form existence, Discord channel, deadline timezone,
   judging axes, eligibility, prize terms all come from our memory, not the live rules.

---

## MUST-VERIFY (Dennis, against the authoritative live rules)

Confirm each against the **live @NousResearch X post + the Discord pinned message + the official entry
form** — these are the canonical sources and could not be fetched headlessly:

1. **Required stack / "must use X" mandate.** Is there an explicit requirement to run on the **Hermes
   runtime** (vs. just "use the Hermes ecosystem")? If "the agent must be a Hermes agent" is mandated,
   risk #1 is **disqualifying**, not just weak. Same question for NemoClaw and the Stripe skills —
   mandatory or merely encouraged?
2. **Submission mechanics.** Exact deliverables: video length bounds (1–3 min?), must the tweet tag
   **@NousResearch** specifically, is a writeup required and where, which **Discord channel** (exact
   name), and is there a **separate form** — and what does it ask?
3. **Deadline + timezone.** "EOD Tue June 30 2026" in **which timezone**? Is it submission-received or
   posted-by?
4. **Judging criteria + weights.** Confirm the axes are **usefulness / viability / presentation** (memory
   says these were user-supplied) and whether there are sponsor-specific sub-criteria (e.g. Stripe
   weighting real agentic spend).
5. **Eligibility / team rules.** Solo vs team, region, prior-work allowed (we reused walk-ultra +
   Higgsfield + Remotion IP — is reuse permitted?), open-source requirement, code-submission requirement.
6. **Prize terms.** Confirm the prize structure and any terms (DGX Spark logistics, Stripe-credit terms,
   tax/eligibility) — the figures here are verified from public NVIDIA/Nous posts but cross-check the
   official rules.
7. **Money / safety constraints.** Any rule about real vs test-mode Stripe in the demo, or any "no real
   charges" / "must show real spend" expectation that changes the earn/spend posture.

---

## Sources (public, verified)
- [Nous Research (@NousResearch) on X](https://x.com/NousResearch/status/2066921443548348436)
- [Nous Research on X — Stripe Skills for Hermes](https://x.com/NousResearch/status/2066647737613832624)
- [Hermes Unlocks Self-Improving AI Agents, Powered by NVIDIA RTX PCs and DGX Spark — NVIDIA Blog](https://blogs.nvidia.com/blog/rtx-ai-garage-hermes-agent-dgx-spark/)
- [Deploy Self-Evolving Agents … with a Hermes Agent and NVIDIA NemoClaw — NVIDIA Technical Blog](https://developer.nvidia.com/blog/deploy-self-evolving-agents-for-faster-more-secure-research-with-a-hermes-agent-and-nvidia-nemoclaw/)
- [AI Providers — Hermes Agent docs](https://hermes-agent.nousresearch.com/docs/integrations/providers)
