# Coherence Synthesis — the "from very up" view

_Read-only capstone, 2026-06-19. Synthesizes six expert passes (UX, video-gen, compliance,
production-readiness, plus the two adversarial verifications of UX/video/compliance) into ONE
deadline-aware judgment for the Hermes Agent Accelerated Business Hackathon (NVIDIA × Stripe × Nous).
Deadline EOD Tue 2026-06-30. Judged on usefulness / viability / presentation. I did not re-do the
underlying reviews; I judge whether they cohere into a winning entry and where they pull apart._

Inputs: `UX-IMPROVEMENTS.md` (+verification), `VIDEO-GENERATION-REVIEW.md` (+verification),
`COMPETITION-COMPLIANCE-REVIEW.md` (+verification), `PRODUCTION-READINESS-REVIEW.md`, `HANDOFF.md`.
Implementation-state deltas from `HANDOFF.md` are honored (see "What is already handled").

---

## 0. What is already handled (so nothing below re-flags it)

- **DONE this session:** per-brand palettes + the hardcoded-Stripe-copy bug; the live Script panel;
  `stripe_earn.py` (TEST-mode Checkout); the pre-production PAY-GATE; **and the UX delivered-state
  payoff — video-led + Download + Share.** That last item resolves the UX review's #1 and #2 findings
  (§5.1 Download/Share, §5.2/§5.3 lead-with-the-video) and its verifier's unchanged #1/#2. **The single
  highest-rated UX win is closed.** This materially changes the UX roadmap below.
- **IN FLIGHT (treat as addressed):** walkthrough letterbox→fill + trim (`apply_real_media.py`) — this
  is video-gen Top-1 AND Top-2; authored-card direction/meta copy fix (`remotion_codegen.py`) —
  video-gen Top-3; final-audio loudness to −14 LUFS (`finish_cut.py`) — the video verifier's NEW #4.

So **four of the video reviewers' Top-7 and the two biggest UX findings are done or in-flight.** The
standalone-tool polish layer is nearly closed. That is precisely what sharpens the central tension below.

---

## (a) VERDICT ON OVERALL COHERENCE

**The parts are individually excellent and the work is real, but the entry does NOT yet cohere into one
winning *agent-hackathon* submission — it coheres into a winning *standalone AI video tool*. The gap is
not quality; it is the subject of the demonstration.**

Three of the four reviews (UX, video-gen, production-readiness) are all optimizing the same artifact: a
beautiful, honest, localhost video producer with a striking live console. They agree with each other and
their verifications confirm them as ship-quality. The fourth review (compliance) is looking at a
different axis entirely and reaches a divergent conclusion: on the axis Nous grades hardest — *is this a
Hermes agent driving the work* — the answer today is **no**. The dashboard spawns `python3
build_runner.py` via `subprocess.Popen`; the Hermes binary is never in the execution path
(`COMPETITION-COMPLIANCE-REVIEW.md` Pillar 1; verified by grep in `COMPETITION-COMPLIANCE-REVIEW-
VERIFICATION.md` §1).

The crucial, hopeful nuance from the compliance *verifier* (§1, "NUANCE the audit under-states"): a
runnable Hermes path **already exists and is wired** — `~/.hermes/skills/producer-brain/SKILL.md:94-185`
has a concrete `hermes chat -Q -q …` PLAN call, `config.yaml:404-406` points at the right Nemotron model,
the `hermes` binary is present. It has simply never been **recorded driving an autonomous end-to-end
run.** So the through-line fix is not "re-architect" — it is **"execute and film the skill that already
exists."** That is a days-not-weeks task, and it is the difference between a tool with an agent bolted on
for evals and an agent that demonstrably runs the business.

**Bottom line:** the sum is a pile of locally-excellent fixes that, left as-is, polish the wrong layer
for *this* competition. One move — make the recorded demo a genuine Hermes run — converts the same parts
into a coherent winning entry. Everything else is supporting craft.

---

## (b) THE REAL CONTRADICTIONS / TENSIONS — and how to resolve each

### Tension 1 (THE central one) — Polishing a standalone tool vs. demonstrating an agent
**Who pulls apart:** UX + video-gen + production-readiness (all deepening the standalone product) vs.
COMPLIANCE (the agent doesn't drive the pipeline; `COMPETITION-COMPLIANCE-REVIEW.md` risk #1, HIGH).
The pay-gate work, while genuinely strong, *added more standalone Python + dashboard surface* — it made
the tool better, not the agent more present. For an **agent** hackathon judged by the runtime's own
maker, that is optimizing the wrong layer.

**Are we polishing the wrong layer? Mostly yes — but cheaply fixable, not a re-architecture.** The
compliance verifier is explicit: the Hermes on-ramp is built (`producer-brain/SKILL.md` + `config.yaml`
+ binary), just never run/recorded. So this is a *recording-and-wiring* problem, not a *rebuild* problem.

**Resolution (decisive):** **Make the submission demo a real `hermes chat` run of the `producer-brain`
skill, with `producer.py`/`orchestrator.py` kept as the deterministic tools the agent calls.** Do NOT
rewrite the engine (the producer brain is the good IP — `PRODUCTION-READINESS-REVIEW.md` §5.1 calls the
pricing/gate engine the strongest part of the codebase). The pretty live console stays as the
*visualization*; the *run it narrates* must be a Hermes run. Concretely:
1. Execute the existing skill end-to-end via `hermes chat` once, capture the transcript/session as proof
   (compliance Pillar 1 fix (d.4)).
2. For the on-camera path, either point `/api/build` (or a dedicated submission path) at
   `hermes chat -Q -q "<producer-brain brief>"`, **or** be scrupulously honest in the VO that the console
   visualizes a pipeline the Hermes agent drives (compliance fix (d.3–4)).
This single move closes the only HIGH compliance risk and unifies the work: the standalone polish now
serves an *agent's* on-camera run instead of competing with it.

### Tension 2 — "Looks like a real agency made it" vs. the sub-dollar on-screen price
**Who pulls apart:** UX §3.1 (the $0.92–$1.30 price "silently undercuts the real-agency story… reads as a
toy"; verified TRUE, `UX-IMPROVEMENTS-VERIFICATION.md` §3.1) vs. the product's own positioning and the P&L
that brags "NET MARGIN 67%". The video-gen reviews push hard to raise *production* quality to agency-grade
(letterbox fix, loudness, ElevenLabs hero pass), while the headline *price* on screen says "this isn't
real money." The two halves of the credibility story contradict each other.

**Resolution:** this is a **positioning decision, not a code bug** (both UX docs agree). Recommended:
**frame the cents figure as "marginal COGS-based unit economics (demo)" rather than a retail price** —
the cheapest credible move (a copy change, UX verifier #6), and it actually *reinforces* the agentic-
commerce thesis (the agent runs a real P&L at true marginal cost). Alternative: a configurable "list
price" floor the margin is computed against. Either is fine; the current bare "$0.92 for an agency promo"
is the only unacceptable option. **Gated on Dennis** (it's a framing call), pairs naturally with the
already-done delivered-state redesign.

### Tension 3 — Production-readiness BLOCKERs vs. "it's a hackathon demo, don't harden"
**Who pulls apart:** `PRODUCTION-READINESS-REVIEW.md` raises BLOCKERs (shared `active.tsx` render race
§1.1; unauthenticated `/api/build` + client-controlled `mode:"real"` §3.1/§3.2; whole-repo static serving
§3.3). HANDOFF NEXT-action #3 lists a "production hardening backlog." But the prod review *itself* opens
by scoping these to "a *production* product, not the hackathon demo," and the UX/compliance work assumes a
single trusted operator on one Mac.

**Resolution (deadline-aware triage):** **Most prod-hardening items are explicitly out of scope for
6/30 and should be parked** — they do not move usefulness/viability/presentation for a controlled demo,
and building them burns the scarce 11 days. BUT pull **three** forward because they protect the *live
demo itself*, not "production":
- **The `active.tsx` render race (§1.1)** — only bites if two builds run at once. **Mitigation, not the
  full fix:** a one-line client guard / don't double-click Build during the demo. Cheap insurance against
  silently-wrong video on camera. (UX verifier MISSED #2 flags the same "second build" UX gap.)
- **Don't surface `build.log`/source over HTTP IF you screen-share the browser** — low effort, avoids a
  key/secret leaking on camera. Otherwise park.
- Everything else in the prod Top-5 (auth, queue, heartbeat/reaper, restart resilience) is **post-
  deadline**. Viability is *argued* by the demo + writeup, not proven by hardened infra, for a hackathon.

The prod review's *strengths* call-outs (deterministic money engine §5.1; never-print Stripe key posture
§3.7/§5.3; atomic ledger write §1.3; "modeled, not physical" honesty §5.4) are **assets to showcase**, not
work to do — they directly support the viability/honesty story.

### (Non-tension worth stating) Where the four reviews AGREE — these are the safe bets
- **Honesty is a strength, not a liability** (UX §3.2, prod §5.3, compliance Stripe earn-side, video
  verifier on license provenance). Every reviewer independently praises the TEST-MODE / "simulated" /
  "modeled not physical" transparency. **Keep it and lean into it on camera** — it is rare and credible.
- **The distinctive edit-bay visual language + no-emoji SVG discipline** (UX §8.1) — protect, don't
  dilute.
- **The walkthrough is the weakest on-screen element** (video-gen §3 Top-1/2, already in-flight) — fixing
  framing+trim is the biggest cheap quality lift; all video docs agree.
- **Nemotron is genuinely compliant** (compliance Pillar 2 COMPLIANT, verified) — no work needed beyond
  one *visible live* gate call in the demo (compliance risk #4, LOW).

---

## (c) ONE INTEGRATED, DEADLINE-AWARE ROADMAP

Ordered as requested: **do-now clear builds → Dennis-gated decisions → must-verify-against-rules.**
Sequencing rationale: compliance risk #1 (the only HIGH that can *disqualify*) and the demo recording are
the spine; everything else is in service of that one recorded run. Where an item is already DONE/in-flight
per HANDOFF it is marked so and excluded from new effort.

### LANE A — DO NOW (clear builds, no decision/spend needed)

1. **[SPINE] Record one real end-to-end `hermes chat` run of `producer-brain`** so the agent visibly
   drives plan → price → (gate/decline) → produce, capturing the session transcript as artifact.
   _(compliance Pillar 1 fix d.4; verifier §1 confirms the path is built and only needs executing.)_
   **This is the highest-leverage item in the whole project — see (d).**
2. **[SPINE] Run ONE real (free) walk-ultra/NemoClaw walkthrough and put that sandbox-produced clip in
   the submission cut**, narrated as "the agent did this inside a NemoClaw sandbox." Converts NemoClaw
   PARTIAL→demonstrated at $0 (only ~3–5 min slow; 403→`nemoclaw credentials reset nvidia-prod`).
   _(compliance risk #3; this clip is ALSO the walkthrough whose framing/trim is already in-flight — one
   asset serves both the compliance and the video-quality reviews.)_
3. **[SPINE] Run ONE build through the new pay-gate so a committed ledger shows a real `cs_test_`
   session** (`awaiting_payment` → paid). Makes the Stripe earn side visible in an *artifact*, not just
   claimed in memory; no real money (test card 4242). _(compliance risk #2 cheaper fix; verified no
   committed ledger currently contains `cs_test_`.)_
4. **[in-flight — confirm landed] Walkthrough letterbox→fill + trim to ~7–8s + drop the green
   "EXPLAINER AGENT" intro card + green QA captions.** Reclaims ~⅓ of the most-on-screen scene (33%, not
   27% — video verifier correction #1) and removes the internal-tooling tell. _(video-gen Top-1/2.)_
5. **[in-flight — confirm landed] Kill placeholder/meta copy on authored cards:** `remotion_codegen.py`
   `brief[:48]` renders the *direction* ("Simple animated divider with the text 'Built for"), and the
   "PRODUCER CUT"/"CALL TO ACTION" kickers. _(video-gen Top-3; both are obvious "this is a template" tells
   a judge catches in a 30s click-through.)_
6. **[in-flight — confirm landed] Normalize delivery loudness to ~−14 LUFS / −1 dBTP in `finish_cut`.**
   Finals ship ~−20 LUFS (~6 LU quiet) — will play conspicuously quiet on a competition stage.
   _(video verifier NEW #4, the video reviews' one real omission.)_
7. **Clean the customer-facing leaks** (LOW effort, HIGH presentation, promoted by UX verifier to #3):
   stop surfacing `"MONEY-SHOT:"`, `PRODUCER_SIMULATE_PAID`/"dev affordance", literal `stripe login`, and
   raw Python exception strings in the customer feed/error states. Separate `payment_timeout` (soft "start
   again?") from `failed` (clean message, log the trace). Add `earning` (and either set `pricing` or drop
   it) to the `app.js` `PHASES` array so a *live* build doesn't render all-grey/"hung" right after the
   user pays. _(UX §3.3/§7.1/§9.3 + UX verifier MISSED #1 — the live phase-track bug; these are the things
   most likely to embarrass the team on camera, and they're cheap.)_
8. **One ElevenLabs pass on the submission hero VO** (`--vo elevenlabs` already wired, `adapters.py:307`;
   ~263 chars ≈ a few cents). Biggest perceived-quality-per-dollar lift on the cut. _(video-gen Top-7 —
   **this is a paid spend, see Lane B, but it's a trivial sub-dollar amount.**)_

### LANE B — DENNIS-GATED DECISIONS (positioning + money)

- **B1 — The sub-dollar price framing (Tension 2).** Decide: frame the cents as "marginal COGS unit
  economics (demo)" (cheapest, recommended) vs. a configurable list-price floor. Copy/config change once
  decided. _(UX §3.1; UX verifier #6 — "a positioning call for Dennis, not pure dev.")_
- **B2 — ElevenLabs hero pass spend** (Lane A item 8). Sub-dollar; needs Dennis's OK per the money rule.
  Recommend YES — highest quality-per-dollar lift for the hero cut.
- **B3 — Real Stripe SPEND for the agentic-commerce beat (the strongest Stripe move, optional).** Wire
  ONE real `stripe-link-cli` purchase so the agent actually *buys* the generation credits it needs
  (human-approved in Link), paired with the autonomous Issuing budget-decline. This is STRATEGY.md's own
  path-to-win and the thing Stripe grades hardest. **Higher effort + real money + Dennis-gated.** If not
  greenlit, the Lane A pay-gate `cs_test_` artifact (item 3) is the honest fallback. _(compliance risk #2
  best fix.)_  **Do NOT narrate the simulated `iauth_sim` decline as a real Stripe decline** (overclaim
  trap — `stripe_money.py:178` hardcodes `spending_controls` even in sim; verified).
- **B4 — Submission package scope + LICENSE.** Decide what "the submission" is (repo / zip / hosted demo).
  Today the pillar evidence is spread across three locations — `hermes-video-agent/`, sibling
  `walk-ultra/` (the NemoClaw driver), and `~/.hermes/skills/` (the Hermes skill). A judge cloning the
  main repo alone sees neither the NemoClaw integration nor the producer-brain skill. **No `LICENSE` file
  exists.** _(compliance verifier MISSED #1/#2, raised to MED.)_

### LANE C — MUST-VERIFY AGAINST THE LIVE RULES (only Dennis can; gates everything above)

The canonical rules live on the @NousResearch X post + Discord pinned + the official form (not fetchable
headlessly). **Verify these BEFORE committing the roadmap — #1 can change Lane A from "strongly advised"
to "disqualifying-if-skipped":**
1. **Is running on the Hermes *runtime* mandatory, or just "use the ecosystem"?** If "must be a Hermes-
   runtime agent" is mandated, Lane A item 1 is **pass/fail**, not polish. Same question for NemoClaw and
   the Stripe skills. _(compliance MUST-VERIFY #1 — the disqualification axis.)_
2. **Submission mechanics:** video length bounds (1–3 min), exact tag (@NousResearch), writeup required +
   where, exact Discord channel name, separate form + its fields. **Must the demo visibly show the agent
   using each sponsor pillar?** (Today 3 of 4 are "capability exists, not in the recorded artifact.")
3. **Deadline timezone** — "EOD Tue 6/30" in which TZ; posted-by vs received-by.
4. **Judging axes + weights** — confirm usefulness/viability/presentation (memory says user-supplied) and
   any sponsor sub-criteria (e.g. Stripe weighting real agentic spend → raises B3's value).
5. **Eligibility / prior-work** — specifically: **is reusing a prior hackathon-WINNING entry (Walk Agent /
   walk-ultra) permitted?** The walkthrough engine is reused, prior-winning IP; some rules forbid this.
   _(compliance verifier MISSED #3 — higher-stakes than a generic "reuse?" line.)_ Plus open-source/code-
   submission requirement (→ B4 LICENSE).
6. **Prize terms** + any "real vs test-mode Stripe / no real charges" constraint that changes the
   earn/spend posture.

---

## (d) THE SINGLE HIGHEST-LEVERAGE MOVE TO WIN

**Record the submission demo as a genuine Hermes-agent run — execute the already-built
`producer-brain` skill via `hermes chat`, driving plan → price → auto-decline → produce, with
`producer.py`/`orchestrator.py` as the tools the agent calls — and film that, not `python3
build_runner.py`.**

Why this one move, above all the polish:
- It closes the **only HIGH compliance risk** and the single axis the runtime's own maker grades hardest.
  Every other reviewer is improving a tool that, on this axis, demonstrates the wrong thing.
- It is **cheap and de-risked**: the Hermes path is built and wired (`producer-brain/SKILL.md:94-185` +
  `config.yaml:404-406` + the binary); it has only never been *recorded running*. Days, not a rebuild.
- It **unifies the whole entry**: every locally-excellent fix (the letterbox, the loudness, the delivered-
  state payoff, the leak cleanup, the honest Stripe transparency) stops competing for the spotlight and
  instead becomes the production value *around an agent visibly running a profitable video business on the
  sponsors' stack.* That is the coherent winning story: **an autonomous Hermes agent, reasoning on
  Nemotron, operating in a NemoClaw sandbox, earning and pricing on Stripe rails — and shipping a finished,
  agency-grade video as a P&L on camera.**

**Biggest risk to winning:** that the team spends the final 11 days making the standalone video tool more
beautiful (it's already the strong, nearly-finished part) while the demo still shows a Python pipeline in
a browser — and a judge concludes "great tool, but where's the *agent*?" The polish reviews, taken
literally and in isolation, *lead the team toward exactly this trap.* The verifications already nudge away
from it (the UX verifier even demotes the plan-editor as premature for the deadline); this synthesis makes
it explicit: **the demo's subject, not the demo's gloss, is what wins an agent hackathon.**

---

## Appendix — citation map (which review each point draws from)

- Standalone-tool polish (deliver/reveal/leaks/first-run/price-credibility): `UX-IMPROVEMENTS.md` Top-7 +
  `UX-IMPROVEMENTS-VERIFICATION.md` corrected ranking (delivered-state #1/#2 now DONE; phase-track bug =
  verifier MISSED #1; plan-editor demoted).
- Produced-video quality (walkthrough letterbox 33% / trim / authored-card copy / GPT-Image-2 garble /
  cinematic prompt / captions / ElevenLabs / loudness): `VIDEO-GENERATION-REVIEW.md` Top-7 +
  `VIDEO-GENERATION-REVIEW-VERIFICATION.md` (33% correction, demo-3 52% conflation, loudness NEW #4).
- Agent-hackathon fit (Hermes AT-RISK, Nemotron COMPLIANT, NemoClaw/Stripe PARTIAL, overclaim trap,
  MUST-VERIFY): `COMPETITION-COMPLIANCE-REVIEW.md` + `COMPETITION-COMPLIANCE-REVIEW-VERIFICATION.md`
  (Hermes path is built-but-unrecorded nuance; LICENSE/package-scope/prior-winner MISSED items).
- Hardening-vs-demo triage + engine/honesty strengths: `PRODUCTION-READINESS-REVIEW.md` (BLOCKERs scoped
  to production; §5.1/§3.7/§5.3/§1.3 strengths to showcase).
- Implementation state (what's DONE/in-flight): `HANDOFF.md`.
