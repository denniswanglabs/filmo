# WIN-PLAN.md — the execution layer (how we actually cross the line by 6/30)

_Read-only execution plan, 2026-06-20. **Deadline: EOD Tue 2026-06-30 — ~10 days.** Judged on
usefulness / viability / presentation. Submission = a 1–3 min demo-video tweet tagging @NousResearch +
a Discord post + a form + (almost certainly) a public repo._

This sits **on top of `WINNING-STRATEGY.md`** (the strategy layer) and `COHERENCE-SYNTHESIS.md` (the
capstone). It does NOT re-derive the thesis, the beat order, or the per-axis analysis — read those for
the "why." This doc answers four operational questions: **how far are we, what exactly must ship, in
what order, and who does each piece.**

**One-line distance-to-win:** _The product is ~90% done and genuinely strong on all three axes; the
gap is almost entirely the **submission itself** — a video that doesn't exist yet, plus ~3 gated steps
only Dennis can take (rules-verify, `stripe login` for the real money-shot, approve the paid re-run) and
a public repo + LICENSE. We are **assembling and recording**, not building._

---

## 1. DISTANCE-TO-WIN — honest readout per axis

Scoring convention: **DONE** (in a committed artifact a judge can see) · **READY** (built, needs one
gated/recording step to become visible) · **GAP** (not done, must happen). I am deliberately conservative
— "done in the code" ≠ "done in the watched artifact," and only the latter scores.

### USEFULNESS — STRONGEST axis. ~85% there.
- **DONE:** A real service Dennis sells (promo + walkthrough outreach video). URL+goal → finished MP4.
  Nemotron judgment eval 7/7 and skill-routing eval 19/19 are committed (`runs/judgment-eval.json`,
  `runs/skill-eval.json`) — proof the open model makes the right calls, not a happy-path script. A
  fresh, clean end-to-end run exists and is verified: `runs/validate-e2e-01/` (32KB ledger + 7.1MB
  `final.mp4`, scene-aligned VO beats, real `cs_test_` earn block).
- **READY:** The walkthrough framing fix (the single biggest quality tell) is **code-applied and
  `node --check`-verified** in `walk-ultra/explainer-agent/agent.sandbox-v26.js` (`.handoff-walkagent-beam-fix.md`),
  but is **not yet proven on a real capture** — that proof is the gated paid Orinovate re-run.
- **GAP:** The finished video must read as "a real agency made it" **inside the submission cut**. The
  walkthrough is still the weakest, most-on-screen scene until a framing-fixed real clip is captured and
  dropped in. This is the one quality gap that can undercut an otherwise-strong usefulness story.
- **How far:** the *capability* is done; the *proof-in-the-cut* (one good walkthrough clip + the
  finished film playing) is the remaining work, and it lands as a by-product of producing the video.

### VIABILITY — STRONG, and now better-evidenced than the strategy doc assumed. ~75% there.
- **DONE (NEW since `WINNING-STRATEGY.md` was written):** A committed ledger now contains a **real
  `cs_test_` Stripe Checkout session** — `runs/validate-e2e-01/ledger.json` carries
  `earn.mode=test · status=paid · session_id=cs_test_a1KuZh… · livemode=false`. This closes the
  strategy doc's "every committed ledger is dev_mode, no real cs_test_ anywhere" gap. **The Stripe
  EARN side is now proven in an artifact, not just claimed.** The deterministic money engine + the
  never-print-key Stripe posture are called the strongest part of the codebase
  (`PRODUCTION-READINESS-REVIEW.md` §5.1/§3.7). The P&L (80¢ price / 32¢ COGS / 60% margin) is real
  math in every ledger.
- **READY / GAP — the auto-decline money-shot:** The budget governor is real and runs as a tool, but the
  on-camera decline is still `simulated:true` with a hardcoded `spending_controls` reason
  (`stripe_money.py:178`); committed ledgers carry `iauth_sim_…`. A **real declined Issuing
  authorization object** needs `stripe login` + `stripe listen` + the webhook (Dennis-gated). This is
  the difference between a knockout differentiator and a careful-honest one (see R1).
- **GAP — the agentic SPEND side:** `stripe-link-cli` (agent *buys* its own credits) is installed but
  never executed (`STRATEGY.md`). This is what Stripe grades hardest; today it's the weakest-evidenced
  pillar. Optional, real-money, Dennis-gated (R-B3 / V5).
- **How far:** earn is now proven; the decline is honestly-narratable today and knockout-grade only with
  the gated real path; agentic spend is the one genuine "not done" on this axis.

### PRESENTATION — STRONG on the set, the FILM doesn't exist yet. ~50% there.
- **DONE:** The Producer Console is the prettiest artifact in the room — live build console, P&L ticker,
  phase track, "agent writes Remotion" Studio replay, per-brand palettes, declutter + run-delete + motion
  polish, delivered-state payoff (video-led + Download + Share, which closed the UX review's #1/#2).
- **READY:** A light/Hera dashboard palette re-base is **code-complete and 25/25 $0-verified**
  (`.handoff-dashboard-light.md`) but awaits Dennis's Safari eye on contrast + motion-on-white. This is
  polish, not win-moving (Tier 3) — do **not** let it eat the cut.
- **GAP — the decisive one:** **The 1–3 min submission video does not exist.** Presentation is 1/3 of
  the score and the only deliverable judges actually watch. This is the single highest-value unbuilt
  thing in the entire project.
- **How far:** the set is built and beautiful; the film — the thing that wins this axis — is at zero.

### OVERALL — how far
> **The system is ~90% done; the *submission* is ~25% done.** Every "build" risk is closing or closed.
> What remains is (a) **record + edit the video** (the spine), (b) **~3 Dennis-only gated steps**
> (rules-verify, `stripe login` for the real decline, approve the paid re-run), and (c) the
> **submission package** (public repo + LICENSE + the tweet/Discord/form). We are in the
> assemble-and-ship phase, not the build phase. The big risk is **mis-spending the 10 days polishing the
> already-strong console instead of cutting the missing film.**

---

## 2. DEFINITION OF A WINNING SUBMISSION — exactly what must exist on 6/30

A submission that can win must contain ALL of the following. Treat this as the acceptance checklist.

**A. The demo video (the scored deliverable).** A 1–3 min film (target ~2:15–2:45 — VERIFY exact bounds,
V2) that visibly shows, in this order, all four sponsor pillars actually running:
1. The **Hermes agent** driving the run (the real `hermes chat` session kicking off — the proof we
   already captured, `evidence/hermes-driven-run/`), NOT a `python3 build_runner.py` console.
2. **NVIDIA Nemotron** named on screen as the brain doing the plan/price/judgment.
3. A **real Stripe `cs_test_` Checkout** (earn — we now HAVE this in `validate-e2e-01`) **and** the
   **auto-decline** money-shot (spend governance). Both visible.
4. A **NemoClaw sandbox** producing the walkthrough (narrated; ideally one real framing-fixed clip).
5. The **agent writing Remotion** on camera (Studio replay) + the **finished video** playing full-bleed.
6. The **P&L** as the closing frame (price 80¢ · COGS 32¢ · margin 60% · 0 overruns).
   — Honesty discipline baked in: mock narrated as mock; the sim decline narrated as "the agent's budget
   governor," NEVER as "Stripe declined it," unless the real Issuing object is on screen (R1).

**B. The tweet** — posts the video, **tags @NousResearch** (verify exact handle + any required hashtag, V2).

**C. The Discord post** — in the exact submissions channel (verify name, V2).

**D. The form** — submitted with all required fields (verify fields + whether a writeup is required, V2).

**E. A public repo + LICENSE** — almost certainly required for an OSS-stack hackathon. Today: **no
LICENSE file exists, and the repo is not even git-initialized** (verified: `hermes-video-agent/` has no
`.git`). Pillar evidence is split across three locations (`hermes-video-agent/`, sibling `walk-ultra/`,
`~/.hermes/skills/producer-brain/`) — a judge cloning the main repo alone sees neither NemoClaw nor the
Hermes skill. Must be resolved (R4 / V4).

**Win-bar, not just submit-bar:** B–E make it a *valid* entry; A at Dennis's craft level (cinematic cut,
the decline given room to land, the finished film breathing for 20–30s) is what makes it *win*
presentation, the axis we're built to dominate.

---

## 3. CRITICAL PATH — the ordered spine (the few things that MUST happen)

Everything else is in service of these. If only these happen, we have a valid, competitive entry.

1. **VERIFY THE RULES (Dennis, ~30 min).** Gates everything; can flip items from "advised" to "pass/fail."
   Especially: is the Hermes runtime mandatory, is prior-winner reuse (Walk Agent) allowed, is a public
   repo/LICENSE required, exact submission mechanics + deadline TZ. (V1–V5.)
2. **LOCK THE STORYBOARD** against `WINNING-STRATEGY.md` (d) beat order — using the assets we *have*
   today (the `hermes-driven` session, `validate-e2e-01` final.mp4, the decline-demo ledgers, the Studio
   replay). This can start in parallel with #1 and does not block on any gated step.
3. **DECIDE THE DECLINE PATH (Dennis, R1).** Either `stripe login` → real declined-auth object (knockout),
   OR narrate honestly as "the budget governor" off the existing sim ledgers (safe). The storyboard's
   centerpiece beat depends on this single fork.
4. **CAPTURE THE REAL ASSETS** the cut needs: one framing-fixed NemoClaw walkthrough clip (paid Orinovate
   re-run, Dennis-approved) + (recommended) one ElevenLabs hero VO pass. These raise the film from B+ to
   agency-grade.
5. **RECORD + EDIT THE VIDEO (Dennis's craft piece).** The spine. Protect the final 2–3 days for editing only.
6. **PACKAGE + SUBMIT:** public repo + LICENSE + clean leaks → tweet (tag @NousResearch) + Discord + form,
   before the deadline in the verified TZ.

---

## 4. EXECUTION PLAN — deadline-aware (~10 days to 6/30)

**Owner key:** **[D]** = Dennis-only (rules, recording, `stripe login`, approving spend / paid runs);
**[A]** = I/agents can run as clear builds at $0; **[D→A]** = Dennis decides/greenlights, then I execute.
**Flags:** 🔒 gated on a Dennis decision · 💲 spends real money · 🎥 recording/craft.

### CLEAR BUILDS I CAN RUN AT $0 (no decision, no spend) — start immediately
- **[A] Add a LICENSE + `git init` the repo + write a top-level README** that maps the three evidence
  locations (`hermes-video-agent/` engine, `walk-ultra/` NemoClaw driver, `~/.hermes/skills/producer-brain/`
  Hermes skill) so a judge cloning the main repo sees all four pillars. (Closes R4; license choice is a
  one-line [D] pick — MIT/Apache-2.0 — then I apply it.)
- **[A] Clean the on-camera leaks** (WINNING-STRATEGY Tier-1 #6 / Lane A #7): stop surfacing
  `"MONEY-SHOT:"`, `PRODUCER_SIMULATE_PAID`, literal `stripe login`, and raw Python tracebacks in the
  customer feed/error states; add `earning` to the `app.js` PHASES array so a live post-payment build
  doesn't render all-grey; one-line "don't double-click Build" guard. These are exactly what embarrasses
  a screen-recording.
- **[A] Confirm the in-flight quality fixes are in the *submission cut*, don't re-do** (Tier-1 #5):
  walkthrough trim ~7–8s + kill the green "EXPLAINER AGENT" intro/QA captions; authored-card placeholder/
  meta copy killed (`remotion_codegen.py` direction strings, "PRODUCER CUT"/"CALL TO ACTION" kickers);
  −14 LUFS in `finish_cut.py`; scene-aligned VO. Per the handoffs these shipped — verify on the actual
  cut. (`validate-e2e-01` already exercises the VO-beats + loudness path; spot-check it.)
- **[A] Run the scene-aligned-VO verification** still listed as TODO in `.handoff-vo-align.md` (mock,
  throwaway id, ffprobe per-beat offsets, confirm cut-beat dropped + no silent tail). Insurance, $0.
- **[A] Finish OR park the light/Hera dashboard** (Tier 3): code is done + 25/25 verified; it only awaits
  Dennis's Safari eye. Do **not** invest more here — the dark console already reads on camera. If Dennis
  doesn't sign off the light palette quickly, ship dark.

### DENNIS-ONLY STEPS (cannot be delegated)
- **[D] 🔒 Verify the rules** (V1–V5): Hermes-runtime mandate, must-show-each-pillar, video length bounds,
  exact @NousResearch tag, Discord channel, form fields/writeup, deadline TZ, prior-winner reuse, OSS/
  LICENSE requirement, Stripe sub-criteria. ~30 min on the @NousResearch post / Discord pinned / the form.
- **[D] 🔒💲 `stripe login` + `stripe listen` + webhook** to produce a **real declined Issuing
  authorization object** for the money-shot (R1). If skipped, we narrate the existing sim honestly — that
  is the safe fallback, not a failure.
- **[D] 🔒💲 Approve + run the paid Orinovate re-run** to capture one real, framing-fixed NemoClaw
  walkthrough clip for the cut (after the BEAM fix, which is already applied). ~3–5 min run; 403 →
  `nemoclaw credentials reset nvidia-prod --yes`.
- **[D] 🔒💲 ElevenLabs hero VO pass** (~263 chars ≈ cents; `--vo elevenlabs` already wired). Recommend
  YES — biggest perceived-quality-per-dollar lift on the film.
- **[D] 🔒💲 (optional) The real `stripe-link-cli` SPEND beat** — only if V5 says Stripe weights real
  agentic spend. Higher effort + real money. Otherwise the `validate-e2e-01` `cs_test_` earn artifact is
  the honest fallback.
- **[D] 🎥 Record + edit the submission video.** Dennis's craft piece and superpower.
- **[D] Post the tweet / Discord / form** (and switch to the right channel binding if a personal handle
  is involved).

### ROUGH PHASE / DAY-BY-DAY (10 days; compresses gracefully if rules verify clean)

| Phase | Days | Owner | What happens |
|---|---|---|---|
| **P0 — Verify + lock direction** | **D1 (6/20)** | [D] rules · [A] builds | [D] runs V1–V5 (the gate). [A] in parallel: `git init` + LICENSE + README map; leak cleanup; confirm in-flight fixes on the cut; VO-align verification. **Storyboard locked against the assets we already have.** |
| **P1 — Decide the gated forks** | **D2–D3 (6/21–22)** | [D] | [D] decides R1 (real decline vs. honest sim) and does `stripe login` if YES; approves the paid Orinovate re-run + ElevenLabs pass; decides B1 price framing + B4 package scope + (if relevant) B3 real spend. These are quick decisions that unblock asset capture. |
| **P2 — Capture the hero assets** | **D3–D5 (6/22–24)** | [D]💲 run, [A] integrate | Paid Orinovate walkthrough capture (framing-fixed) → trim → drop into the cut. ElevenLabs hero VO. If R1=YES: capture the real declined-auth object on camera. [A] re-stitches / `finish_cut.py` polishes the assembled cut. |
| **P3 — Cut v1 + review** | **D5–D7 (6/24–26)** | [D]🎥 | First full assembly of the video against the locked storyboard. Rehearse the exact on-camera click-path. Internal review (and the ChatGPT cross-check). |
| **P4 — Lock + polish the cut** | **D7–D9 (6/26–28)** | [D]🎥 | Editing only — pacing, the decline beat given room, the finished film breathing 20–30s, audio at −14 LUFS, honesty badges on. Freeze the system; no new features. |
| **P5 — Package + submit (buffer)** | **D9–D10 (6/28–30)** | [D] | Final repo push (public + LICENSE), tweet tagging @NousResearch, Discord post, form. **Submit by D9 (6/28), leaving 6/29–30 as buffer** against TZ ambiguity (V2). Never submit on the literal deadline hour. |

**Sequencing logic:** the storyboard and most builds need **nothing gated** and start Day 1. The
Dennis-only forks (R1, paid runs) front-load to Days 2–3 so asset capture isn't blocked late. The last
~3 days are reserved for editing and a submission buffer — the #1 way this loses is a rushed cut or a
TZ-missed deadline, both avoidable by finishing the spine early.

---

## 5. RISKS + MITIGATIONS

| # | Risk | Why it loses / embarrasses | Mitigation |
|---|---|---|---|
| **R1 — the honesty trap (highest-stakes)** | Narrating the **simulated** decline (`stripe_money.py:178` hardcodes `spending_controls`; ledgers carry `iauth_sim`) as a **real Stripe decline**. | **Stripe is a judge.** Overclaiming a sponsor's product on a judged stage is the worst possible look — a single fact-check disqualifies the credibility of the whole entry. | EITHER close the real path (`stripe login` → real declined-auth object on camera) OR narrate as "the agent's budget governor," never "Stripe declined it." Decide in P1. The safe path still scores — the governor *behavior* is real; only the Stripe-native attribution is the line not to cross. |
| **R2 — the video doesn't exist** | The #1 scored deliverable is at zero; a rushed cut wastes the strong system. | No video = no entry; a bad video squanders the presentation edge. | Spine item; storyboard Day 1 off existing assets; protect D7–D9 for editing only; submit by D9. |
| **R3 — rules unverified** | Hermes-runtime mandate / must-show-each-pillar / prior-winner reuse all assumed, not confirmed. | An unverified assumption on the decisive axis is a gamble. We're *likely* covered (the Hermes run is recorded) but "likely" isn't "verified." | V1–V5 Day 1, before locking the cut. |
| **R4 — submission package gap** | No LICENSE; repo not git-initialized; pillar evidence across 3 repos. | A judge cloning the main repo sees no NemoClaw, no Hermes skill → "where are the pillars?" Possibly an invalid OSS submission. | [A] `git init` + LICENSE + a README that maps/vendors the three locations. Day 1 clear build. |
| **R5 — prior-winner reuse** | Reusing Walk Agent / the NemoClaw walk-ultra engine (a prior hackathon *winner*) may be disallowed. | Could disqualify the NemoClaw pillar or the entry. | V3 verify explicitly. **Fallback:** the producer-brain + Remotion + Stripe pillars are *new* IP and stand alone; if disallowed, lead with the new IP and treat the walkthrough as one optional scene, not the spine. |
| **R6 — walkthrough still B-grade in the cut** | Black bars / internal-tooling tells in the most-watched scene. | Undercuts the "real agency made it" usefulness story. | BEAM framing fix is applied + verified ($0); the paid re-run proves it on a real capture; trim to 7–8s. Highest quality-per-effort fix in the project. |
| **R7 — live-console leaks on screen-record** | `stripe login` strings, tracebacks, dev affordances, served source. | Reads as unfinished on camera. | [A] leak cleanup; don't HTTP-serve source if screen-sharing; rehearse the click-path (P3). |
| **R8 — polishing the wrong layer** | Spending the 10 days on the light-palette/motion/hardening backlog instead of the cut. | The capstone's central warning: a great tool with no film loses an *agent presentation* contest. | This plan front-loads builds and reserves the back half for the cut. Light palette is Tier 3; hardening BLOCKERs are PARKED except the one-line double-click guard. |

---

## 6. THE SINGLE MOST IMPORTANT NEXT ACTION

> **Dennis verifies the rules (V1–V5) today, and in the same sitting locks the storyboard against the
> assets we already have** (the recorded `hermes-driven` session, `validate-e2e-01`'s finished MP4 + real
> `cs_test_` earn block, the decline-demo ledgers, the Studio replay).

Why this and not "start cutting": the rules verification can flip the decline path (R1), the prior-winner
reuse (R5), and the package requirement (R4) from "advised" to "pass/fail" — and we should not lock a
storyboard that a rule then invalidates. But it's a 30-minute gate, after which the storyboard can lock
immediately because **every asset the spine needs to begin already exists in a committed artifact.** The
build risk is essentially closed; the win now lives in the *cut*, and the cut can start the moment the
rules are confirmed. In parallel, I begin the $0 clear builds (git init + LICENSE + README map, leak
cleanup) so the submission package is never the thing that's late.

---

## Appendix — state deltas this plan corrects vs. `WINNING-STRATEGY.md`

`WINNING-STRATEGY.md` (written ~01:11) listed two items this plan re-grades from "GAP/IN-FLIGHT" to
**DONE**, verified on disk 2026-06-20:
- **The `cs_test_` ledger artifact** (its Tier-1 #4, and the viability axis's "no committed real Stripe
  session" gap): **DONE** — `runs/validate-e2e-01/ledger.json` has `earn.mode=test · status=paid ·
  session_id=cs_test_a1KuZh… · livemode=false`.
- **The fresh $0 end-to-end pipeline validation** (listed IN-FLIGHT in the brief): **COMPLETE** —
  `runs/validate-e2e-01/` holds a valid 7.1MB `final.mp4` + scene-aligned VO beat files + the full ledger.
- The **walkthrough BEAM framing fix** is **code-applied + `node --check`-verified** in
  `walk-ultra/explainer-agent/agent.sandbox-v26.js` (`.handoff-walkagent-beam-fix.md`) — its only
  remaining proof is the gated paid capture.
- The **light/Hera dashboard** is **code-complete + 25/25 $0-verified** (`.handoff-dashboard-light.md`),
  pending only Dennis's Safari eye — correctly Tier 3, not on the critical path.

Net effect: viability is better-evidenced than the strategy doc assumed, the walkthrough quality fix is
de-risked, and the critical path is even more cleanly "record + package," with the build column nearly empty.
