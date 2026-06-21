# Hermes Hackathon — strategy to win (NVIDIA × Stripe × Nous)

_Drafted 2026-06-19. Judged on **usefulness · viability · presentation**. Submit by EOD Tue Jun 30:
a 1–3 min demo video tweet tagging @NousResearch + the submissions channel + the form._

## The frame: three judges, three different wants
This is presented by **NVIDIA × Stripe × Nous Research** "for builders making agents that can
**earn, spend, and run real operations at any scale**." Each sponsor is grading for their own thing.

| Judge | What they actually want to see | How we hit it |
|---|---|---|
| **Stripe** | **Agentic commerce** — an agent that *buys what it needs, provisions its own SaaS, and pays for the services it uses* on Stripe rails. They shipped 3 skills for exactly this. | The studio EARNS from a customer, then SPENDS on Stripe rails to buy the generation credits / provision the delivery infra it needs. Plus the autonomous Issuing budget-decline. |
| **NVIDIA** | An **open model** (Nemotron) doing real reasoning, **safely sandboxed** (NemoClaw), fast. | Nemotron IS the producer brain (plan/price/gate) — and our evals *prove* it makes the right calls. NemoClaw runs the walkthrough. |
| **Nous / Hermes** | Hermes as the **agent runtime + skills ecosystem**, on open models. | The whole studio runs on Hermes skills — ours, theirs (the payment skills), and skills we port in — driven by Nemotron. |

## The Stripe Skills for Hermes (the spend axis) — already installed
`~/.hermes/skills/` now has the three official payment skills, which map 1:1 to the prompt:
- **`stripe-link-cli`** → *buy what it needs* — purchases via one-time virtual cards / Shared
  Payment Tokens; pays HTTP 402 APIs. Spends are **human-approved in the Link app** (Hermes can't
  self-approve) — the *safe-agent* story.
- **`stripe-projects`** → *provision its own SaaS* — spin up Neon/Postgres, Twilio, Vercel, etc.;
  sync credentials to `.env`; manage billing.
- **`mpp-agent`** → *pay for the services it uses* — per-request HTTP 402 / Machine Payments Protocol.

**Why this matters:** it fixes our biggest honesty hole. Today we hand-wave "Stripe doesn't actually
move Higgsfield's money." With `stripe-link-cli` the agent can **actually buy the production credits**
it needs — the spend becomes real Stripe behavior, not theater.

## Sharpened thesis (one line)
> **A video-production *company* run end-to-end by a Hermes agent on Nemotron: it quotes + charges a
> customer (Stripe earn), buys/provisions/pays for the exact services it needs to make the video
> (Stripe Skills for Hermes), governs its own budget to stay profitable (the autonomous Issuing
> decline), and ships a finished, on-brand video — a P&L on camera.**

That is the prompt's "fully automated company," hits all three judges, and the **delivered video is
the prettiest artifact in the room** (Dennis's edge → the presentation axis).

## The honest design tension (narrate it precisely)
`stripe-link-cli` spends are human-approved in Link — which is the *safe-agent* story NVIDIA/Stripe
want. So split the narrative: **routine spend = approved via Link (safe)**; **budget governance =
autonomous Issuing auto-decline (no human)**. Both are real Stripe.

## Mapping to the judging axes
- **Usefulness** — a service businesses actually want (outreach / promo / walkthrough videos); Dennis
  can sell it. Not a toy.
- **Viability** — it's literally *profitable on camera* (the P&L), on cheap open models + real payment
  rails. A business model, demonstrated.
- **Presentation** — the finished video + the Producer Console dashboard make the agent's reasoning
  and spend legible and beautiful.

## Status vs the win (2026-06-19)
- DONE: producer-brain (plan/price/gate), the autonomous decline money-shot, the dashboard, the
  "agent writes Remotion" Studio feature, the test harness (26 checks), Nemotron judgment eval (7/7),
  Stripe key validated + Issuing real-declined-object proven, the 3 payment skills installed, and a
  **skill-routing eval** proving Nemotron drives the skill set on the open model (see
  `hermes_skill_eval.py`).
- DECIDED 2026-06-19: keep the SPEND **simulated for now** (don't wire real Stripe-skill spend yet);
  $0 tonight. The real-spend reframe above is the path to strengthen the Stripe axis when ready —
  it needs `stripe login` + a small real charge (buy credits / provision the delivery host).

## Next moves toward the win (in priority order)
1. **(Stripe axis, when greenlit)** wire ONE real Stripe-skill beat: the agent uses `stripe-link-cli`
   to buy the generation credits it needs (human-approved), or `stripe-projects` to provision the
   host it delivers the video to. Keep the Issuing decline as the autonomous-governance shot.
2. **(NVIDIA axis)** keep Nemotron the visible decision-maker; lean on the judgment + routing evals
   as on-camera proof the open model runs the business correctly.
3. **(Hermes axis)** keep porting/sharpening skills so the small model drives them reliably
   (`hermes_skill_eval.py` is the regression gate — sharpen any `description:` that mis-routes).
4. **The demo video** (Dennis's superpower) — the agent producing a video + the P&L/decline beat +
   the Studio "agent coding" moment. 1–3 min, tag @NousResearch.
