# WINNING-STRATEGY.md — how this entry wins (the ~10-day plan)

_Read-only strategic review, 2026-06-20. Deadline: EOD Tue 2026-06-30 (timezone UNVERIFIED — Lane C #1).
Judged on usefulness / viability / presentation. Submission = a 1–3 min demo video tweet tagging
@NousResearch + a Discord post + a form._

This builds on `COHERENCE-SYNTHESIS.md` but supersedes its central verdict. That capstone's headline —
"the agent doesn't drive the run; this coheres into a standalone tool, not an agent submission" — was
written BEFORE the Hermes-driven run shipped. **That single highest-leverage move is now DONE**
(`evidence/hermes-driven-run/transcript.md`, session `20260620_000754_46aa2a`). The strategic center of
gravity has moved. This doc reflects the post-fix-wave state.

---

## (a) THE WINNING THESIS — one line

> **An autonomous Hermes agent — reasoning on free NVIDIA Nemotron — runs a real video-production
> company end to end: it plans, quotes and charges the customer, governs its own budget with a live
> auto-decline to protect margin, writes its own Remotion on camera, produces in a NemoClaw sandbox, and
> ships a finished, on-brand video — a profitable P&L, live, on the sponsors' stack.**

Everything we build in the next 10 days serves that one sentence being *literally true on camera*.

---

## (b) PER-AXIS STANDING + TOP PLAY + BIGGEST GAP

### USEFULNESS — STRONG (our most defensible axis)
- **Where we stand:** This is a service real businesses pay for (promo + walkthrough outreach video).
  Dennis sells exactly this. The agent takes a URL + goal and ships a finished MP4. Not a toy demo —
  a real job, automated. The Nemotron judgment eval (7/7) and skill-routing eval (19/19) prove the open
  model makes the right calls, not just a happy-path script.
- **Top play:** Lead the narrative with "we replaced a $2k agency job with an agent that does it for
  cents and ships in minutes." Usefulness is *obvious* here — don't over-argue it, *show the finished
  video* and let it speak.
- **Biggest gap:** The finished video must look like "a real agency made it." Today the walkthrough is
  the weakest, most-on-screen element (~40%+ of the cut, ~27–33% black bars from the BEAM viewport bug —
  `WALKTHROUGH-INVOCATION-FIX.md`). A judge who sees letterboxed screen-capture concludes "B-grade tool."
  **This is the one quality gap that can undercut the usefulness story.**

### VIABILITY — STRONG (the differentiator, but evidence is thin in artifacts)
- **Where we stand:** It's *profitable on camera* — the P&L (price 80¢ / COGS 32¢ / 60% margin) on cheap
  open models + real payment rails is a demonstrated business model, not a pitch. The deterministic money
  engine + never-print-key Stripe posture are called the strongest part of the codebase
  (`PRODUCTION-READINESS-REVIEW.md` §5.1/§3.7).
- **Top play:** The **autonomous Issuing budget auto-decline** is the single most "agentic-commerce" beat
  in the whole entry and it's the thing Stripe grades hardest. An agent that *refuses to overspend to
  protect its own margin* is a memorable, rare money-shot. Lean on it hard.
- **Biggest gap:** The viability proof is mostly *claimed*, not *in a committed artifact*. Every committed
  ledger is `mode: mock` with `earn: dev_mode` and only a **simulated** `iauth_sim` decline; no ledger
  contains a real `cs_test_` Stripe session (`COMPETITION-COMPLIANCE-REVIEW-VERIFICATION.md` §4). The
  agentic-commerce SPEND side (the agent *buying* its own credits via `stripe-link-cli`) is installed but
  never executed. **The viability story is real but under-evidenced where a judge actually looks.**

### PRESENTATION — STRONG on dashboard, UNRESOLVED on the submission video
- **Where we stand:** The Producer Console is genuinely striking — live build console, P&L ticker,
  phase track, "agent writes Remotion" Studio replay, per-brand palettes, declutter + motion polish, and
  an in-flight light/Hera redesign. The delivered-state payoff (video-led + Download + Share) closed the
  UX review's #1/#2. This is the prettiest artifact in the room — Dennis's edge.
- **Top play:** The submission video is Dennis's superpower and carries this axis. The dashboard is the
  *set*; the cut is the *film*. See (c).
- **Biggest gap:** **The 1–3 min submission video does not exist yet.** It is the single highest-value
  unbuilt thing. Presentation is 1/3 of the score and the only deliverable the judges actually watch.

**Net:** all three axes are in strong shape on capability; the gaps are all about *getting the proof into
the watched artifact* (the cut) and *one quality fix* (the walkthrough). We are closing, not building.

---

## (c) DIFFERENTIATORS — our edge vs HermesCo and the field

**The flagship competitor (HermesCo) is on this exact stack. Per our docs, their output is JSON
deliverables and they have NO real Stripe Issuing.** Our edges, ranked by how hard to lean on them:

1. **Cinematic finished VIDEO as the deliverable (lean HARDEST).** HermesCo ships JSON; we ship a
   watchable, on-brand promo + walkthrough with VO, music bed, grade, and crossfades. On a *presentation*
   axis judged by humans watching a video tweet, a beautiful finished film beats a JSON blob every time.
   This is Dennis's craft moat and the field can't easily copy it in 10 days.

2. **A REAL Stripe Issuing auto-decline (lean HARD — but make it real, see risk R1).** HermesCo has no
   real Issuing. An agent that autonomously declines its own over-budget spend to protect margin is the
   purest "agent runs a business with safety limits" beat Stripe asked for. **Caveat that decides whether
   this is a weapon or a liability:** today the decline is `simulated:true` with a hardcoded
   `spending_controls` reason (`stripe_money.py:178`). We have proven a *real* declined authorization
   object once in a shell. To beat HermesCo here we must show the REAL declined-authorization object on
   camera (needs `stripe login` + the webhook), NOT narrate the sim as real. A real decline is a
   knockout; a sim narrated as real is a disqualifier-grade overclaim.

3. **The agent writes its own Remotion ON CAMERA (lean HARD — unique and visual).** The Studio view
   replaying the agent authoring a real, compiling, rendering Remotion component per scene is a striking,
   legible "the agent is actually doing the creative work" moment that JSON-deliverable competitors
   structurally cannot show. Cheap to feature, high-impact.

4. **A genuine Hermes runtime run, recorded (now our floor, not our ceiling).** We have the proof
   artifact that the Hermes agent — on free Nemotron — drove plan→price→gate→produce→P&L calling our
   engine as tools (`evidence/hermes-driven-run/`). This closes the compliance floor every serious entry
   must clear. It is table stakes now, not the differentiator — but if a competitor *fakes* the agent
   layer and we can prove ours is real (session id, verbose log, free-model verification), that's a
   credibility edge under scrutiny.

**What we lean on hardest, in order:** (1) the finished video, (2) the real auto-decline money-shot,
(3) the agent coding on camera. Those three are what a JSON-on-Stripe-without-Issuing competitor cannot
match.

---

## (d) THE SUBMISSION DEMO VIDEO — the winning narrative

**This is the deliverable that wins or loses. Spend the most craft here.** Target the upper bound of the
1–3 min window (~2:15–2:45) — long enough to show all four pillars actually running, short enough to keep
energy. Verify exact length bounds (Lane C #2).

### The hook (first 5–8 seconds — non-negotiable)
Open on the money line, not on a logo or a dashboard tour. Cold open:
> "This is an AI agent running a video-production company. It just quoted a customer, charged them,
> built the video itself — and refused to overspend doing it. Watch."
Then immediately cut to the live build starting. **Do not** open with "Hi, this is our hackathon entry."
The first frame should be the agent doing something a human normally does.

### Beat order (the spine — each beat = one pillar made visible)
1. **HOOK + THE AGENT WAKES (0:00–0:10).** The cold-open line over the Producer Console as a real
   `hermes chat` run kicks off. On-screen tag: "Hermes agent · Nemotron brain." (Pillar: Hermes runtime —
   show the actual session starting, this is our hard-won proof.)
2. **PLAN (0:10–0:30).** The Script panel types in the VO narration + ordered shot list as Nemotron
   plans a site-specific storyboard from the URL. Caption: "NVIDIA Nemotron-3-Super-120B — free, open."
   (Pillar: Nemotron, the visible decision-maker.)
3. **PRICE + THE PAY GATE (0:30–0:50).** The agent prices the job and the pay-gate card appears: amber
   $X.XX + "Pay to produce." Show the real `cs_test_` Stripe Checkout opening (test card 4242). The agent
   gets PAID before it produces. (Pillar: Stripe earn — must be a real `cs_test_` session in the ledger.)
4. **THE MONEY-SHOT — AUTO-DECLINE (0:50–1:10).** THE centerpiece. The per-scene budget governor hits an
   over-budget scene and **autonomously declines/downgrades it** to protect margin — the P&L ticker holds
   green. Show the real declined Issuing authorization object if R1 is closed; otherwise show the
   deterministic gate verdict and narrate it honestly as "the agent's budget governor." This is the beat
   that out-differentiates HermesCo. Give it room — slow down, let it land.
5. **THE AGENT WRITES REMOTION (1:10–1:30).** Studio view: the agent authoring a real Remotion component,
   it compiles, it renders. "The agent isn't filling a template — it's writing the motion graphics."
   (Unique vs JSON competitors.)
6. **PRODUCE IN A SANDBOX (1:30–1:50).** The walkthrough scene produced by Nemotron inside a NemoClaw
   sandbox. Narrate: "the walkthrough was captured by an agent in a secure NemoClaw sandbox." (Pillar:
   NemoClaw — needs ONE real free walk-ultra clip, framing-fixed, in the cut.)
7. **THE FINISHED VIDEO (1:50–2:20).** Play the delivered promo, full-bleed, with audio. This is the
   payoff and the proof of usefulness/presentation. Let it breathe — 20–30s of the actual film.
8. **THE P&L CLOSE (2:20–2:40).** Land on the receipt: "price 80¢ · COGS 32¢ · margin 60% · 0 budget
   overruns." Closing line: "An agent that earns, spends within its limits, and ships — a company in a
   box." End on the thesis.

### What it MUST show (a judge ticking sponsor boxes)
- The **Hermes agent** visibly driving (the real session, not a Python console).
- **Nemotron** named on screen as the brain doing the planning/judgment.
- A **real Stripe `cs_test_` Checkout** (earn) AND the **auto-decline** (spend governance) — both visible.
- A **NemoClaw sandbox** producing the walkthrough (narrated, one real clip).
- The **agent writing code** + the **finished video** playing.
- The **P&L** as the closing frame.

### Honesty discipline (protects us on a judged stage)
- Narrate mock scenes as mock if the recorded run is mock; narrate sim declines as "the budget governor,"
  never as "Stripe declined it," unless the real Issuing object is on screen.
- Keep the on-screen TEST-MODE / "modeled, not physical" honesty badges. Every reviewer praised this; it
  reads as credible, not weak. Lean into it.

---

## (e) DEADLINE-AWARE PRIORITIZED TO-WIN LIST

Ordered by win-probability impact. **MOVES THE WIN** = changes a judge's score; **POLISH** = nice, won't.

### TIER 0 — VERIFY FIRST (gates everything; only Dennis can; ~30 min)
These can flip items below from "advised" to "pass/fail." Do before committing craft time.
- **V1. The rules mandate.** Is running ON the Hermes runtime mandatory? Must the demo visibly show the
  agent using EACH sponsor pillar? (We're now covered on Hermes; this confirms the bar.)
- **V2. Submission mechanics:** exact video length bounds, exact @NousResearch tag, writeup required +
  where, exact Discord channel, the form + its fields, deadline TIMEZONE.
- **V3. Eligibility / prior-work:** is reusing a prior hackathon-WINNING entry (Walk Agent / walk-ultra,
  the NemoClaw walkthrough engine) permitted? The producer-brain IP is new; the walkthrough engine is
  reused, prior-winning IP. Some rules forbid this. **Higher-stakes than it looks.**
- **V4. Open-source / LICENSE + submission package:** is a public repo / OSS license required? **No
  LICENSE file exists.** Pillar evidence is spread across 3 locations (`hermes-video-agent/`,
  `walk-ultra/`, `~/.hermes/skills/`) — a judge cloning the main repo alone sees neither NemoClaw nor the
  producer-brain skill. Decide the artifact (mono-repo / zip / hosted) and add a LICENSE.
- **V5. Stripe sub-criteria:** does Stripe weight REAL agentic spend? If yes, R-B3 (real `stripe-link-cli`
  buy) jumps in value.

### TIER 1 — MOVES THE WIN (do these; mostly clear builds)
1. **[SPINE] Produce the submission video** (Dennis's craft piece). Everything else feeds this. This is
   THE highest-leverage build now that the Hermes run is done. Start storyboarding against (c) immediately;
   it can be cut in parallel with the asset fixes below.
2. **[CLEAR BUILD] Fix the walkthrough framing** (`WALKTHROUGH-INVOCATION-FIX.md` fix A): set the BEAM
   scout/winner viewport to 1440×900 in `walk-ultra/explainer-agent/agent.sandbox-v26.js`, OR the
   defensive `objectFit: contain` in `Explainer.tsx`, OR the quick `BEAM=0` in `tutorial-maker.sh`. This
   is the biggest single quality lift — it removes the ~27–33% black bars on the most-on-screen scene and
   the "internal tooling" tell. Files are in the sibling repo and free to edit; does NOT touch the
   in-flight `adapters.py`. **High win-impact, bounded effort.**
3. **[CLEAR BUILD, $0] Capture ONE real free NemoClaw walkthrough clip** (after #2's framing fix) and put
   it in the submission cut, narrated as sandboxed. Converts NemoClaw PARTIAL→demonstrated at $0. One
   asset serves both the NemoClaw pillar AND the video-quality fix. (~3–5 min run; 403 →
   `nemoclaw credentials reset nvidia-prod --yes`.)
4. **[CLEAR BUILD, $0] Run ONE build through the pay-gate so a committed ledger shows a real `cs_test_`
   session** (`awaiting_payment` → paid, test card 4242, no real money). Puts the Stripe earn proof in an
   artifact instead of memory. Makes beat 3 of the video real.
5. **[CLEAR BUILD] Confirm the in-flight quality fixes landed and are in the cut:** walkthrough trim to
   ~7–8s + kill the green "EXPLAINER AGENT" intro card / QA captions; authored-card placeholder/meta copy
   killed (`remotion_codegen.py` direction strings, "PRODUCER CUT"/"CALL TO ACTION" kickers); −14 LUFS
   loudness in `finish_cut.py`; scene-aligned VO (no CTA-over-walkthrough, no silent tail). These are the
   "this is a template" tells a judge catches in a 30s look. Per the handoffs these shipped — verify on
   the actual submission cut, don't re-do.
6. **[CLEAR BUILD] Clean the on-camera leaks:** stop surfacing `"MONEY-SHOT:"`, `PRODUCER_SIMULATE_PAID`,
   literal `stripe login`, raw Python tracebacks in the customer feed/error states. Add `earning` to the
   `app.js` PHASES array so a live post-payment build doesn't render all-grey/"hung." These are cheap and
   are exactly what embarrasses you if you screen-record the live console. (UX §3.3/§7.1 + verifier #1.)

### TIER 2 — DENNIS-GATED DECISIONS (positioning + money)
- **D-B1. Sub-dollar price framing.** Frame the cents as "marginal COGS unit economics (demo)" rather
  than a retail price — reinforces the agentic-commerce P&L thesis and is a copy change. Recommended.
- **D-B2. ElevenLabs hero VO pass** on the submission cut (`--vo elevenlabs` wired; ~263 chars ≈ cents).
  Biggest perceived-quality-per-dollar lift on the film. Recommend YES (sub-dollar).
- **D-B3. REAL Stripe spend beat (the strongest Stripe move, optional).** Wire ONE real `stripe-link-cli`
  buy so the agent actually purchases its generation credits (human-approved in Link), paired with the
  autonomous Issuing decline. This is STRATEGY.md's own path-to-win and what Stripe grades hardest (V5).
  Higher effort + real money. If not greenlit, the Tier-1 #4 `cs_test_` artifact is the honest fallback.

### TIER 3 — POLISH (only if Tier 0–2 are done; will NOT move the win)
- The light/Hera dashboard redesign — finish ONLY if it doesn't risk the demo; the dark console already
  reads well on camera. Don't let a palette refactor consume the final 48h.
- The one-by-one audit + fresh end-to-end validation — valuable as insurance, but it's verification, not
  win-moving. Run it once before recording, not as an open-ended task.
- All production-hardening BLOCKERs (active.tsx race, auth, queue) — **PARK.** Out of scope for a
  controlled single-operator demo. The one exception: a one-line "don't double-click Build" guard so the
  live recording can't render a silently-wrong video. Don't surface `build.log`/source over HTTP if you
  screen-share the browser.

---

## (f) THE HONEST RISKS TO WINNING + DE-RISK

| # | Risk | Why it could lose / embarrass | De-risk |
|---|---|---|---|
| **R1** | **Narrating the SIMULATED decline as a real Stripe decline.** `stripe_money.py:178` hardcodes `spending_controls` even in sim; ledgers carry `iauth_sim`. | Overclaiming a sponsor's product on a judged stage is the worst possible look — and Stripe is a judge. A fact-check fails us. | EITHER close the real path (`stripe login` + `stripe listen` + webhook → show the real declined-auth object) OR narrate honestly as "the agent's budget governor" and never imply Stripe's native cap fired. Decide in Tier 0. |
| **R2** | **The submission video doesn't exist yet** and is the #1 scored deliverable. | No video = no entry. A rushed video wastes the strong system underneath. | Make it Tier-1 spine #1; storyboard now against (c); cut in parallel with asset fixes. Protect the last 2–3 days for editing only. |
| **R3** | **Prior-winner reuse (Walk Agent / NemoClaw engine) may be disallowed.** | Could disqualify the NemoClaw pillar or the whole entry depending on rules. | Tier 0 V3 — verify explicitly. Fallback if disallowed: the producer-brain + Remotion + Stripe pillars stand on their own; lead with the *new* IP and treat the walkthrough as one optional scene, not the spine. |
| **R4** | **Submission-package gap:** no LICENSE; evidence across 3 locations. | A judge cloning the main repo sees no NemoClaw, no Hermes skill → "where are the pillars?" | Tier 0 V4 — decide the artifact, vendor the skill + walk-ultra integration (or document paths clearly), add a LICENSE. |
| **R5** | **The walkthrough looks B-grade on camera** (black bars / internal-tooling tells). | Undercuts the "real agency made it" usefulness story in the most-watched scene. | Tier-1 #2 framing fix + #3 fresh capture + #5 trim. Highest quality-per-effort fix in the project. |
| **R6** | **Live-console leaks on screen-record** (dev affordances, tracebacks, secrets in served files). | A `stripe login` string or a Python traceback on camera reads as unfinished. | Tier-1 #6 leak cleanup; don't HTTP-serve source if screen-sharing; rehearse the exact click-path before recording. |
| **R7** | **Rules mandate unverified** (Hermes-runtime requirement, must-show-each-pillar). | We're now likely covered, but an unverified assumption is a gamble on the decisive axis. | Tier 0 V1/V2 — confirm against the live @NousResearch post / Discord / form before locking the cut. |

---

## (g) THE SINGLE HIGHEST-LEVERAGE MOVE RIGHT NOW

**Produce the 1–3 minute submission video.** The compliance floor is now cleared (the Hermes-driven run
is recorded and verified), the system is mature, and the only scored deliverable a judge actually watches
does not yet exist. It is also Dennis's strongest skill and our biggest differentiator vs a JSON-output
competitor. Storyboard it against the (c) beat order today, cut it against the real assets as the
walkthrough-framing fix and the `cs_test_` ledger land, and protect the final 2–3 days for editing only.

**The trap to avoid:** spending the last 10 days making the (already-strong) dashboard prettier — the
in-flight light redesign, more motion polish, hardening backlog. The capstone warned of polishing the
wrong layer; the warning still holds, it has just moved. The win now lives in the *cut*, not the console.

---

## Appendix — what shipped this session (so nothing above re-flags it as TODO)
- **Hermes agent genuinely drives a run** (`evidence/hermes-driven-run/transcript.md`, session
  `20260620_000754_46aa2a`, free Nemotron verified) — **closes the only HIGH compliance risk** from
  `COHERENCE-SYNTHESIS.md`.
- Scene-aligned VO (`.handoff-vo-align.md`); art-directed Remotion archetypes (`.handoff-artdirection.md`);
  Higgsfield job-id parse + failure-ledger merge (`.handoff-paygate-postpay.md`, `.handoff-higgsfield-*`);
  −14 LUFS loudness; pay-gate + post-payment landing fix; dashboard declutter + run-delete + motion polish.
- IN FLIGHT: light/Hera dashboard palette (`.handoff-dashboard-light.md`).
- DIAGNOSED but UNFIXED: the walkthrough BEAM viewport clip (`WALKTHROUGH-INVOCATION-FIX.md`) — the fix is
  scoped and free to apply in `walk-ultra/`. **This is Tier-1 #2.**
- PARKED on Dennis: `stripe login` (real webhook/decline), full paid Orinovate re-run, serve.py restart,
  splicing the recovered Seedance clip.
