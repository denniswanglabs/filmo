# Hermes Video Agent — Stripe Money Layer + Producer Brain (Design Proposal)

**Status:** design only. No executable skills written, zero money spent, no Stripe live
calls, no account creation. Everything below is Stripe **TEST mode**.
**Author:** drafted 2026-06-18 for the Hermes Agent Accelerated Business Hackathon
(NVIDIA × Stripe × Nous Research, due 2026-06-30). Judged on usefulness, viability,
presentation.

> One-line pitch: a Hermes (Nemotron) agent runs a video studio as a P&L on camera —
> it **earns** (a customer pays for a video), then **spends** its own production budget on
> Higgsfield + ElevenLabs to make the video, and a Stripe-issued virtual card
> **auto-declines** any generation that would blow the budget, with no human in the loop.

---

## 0. Recon findings (ground truth on this machine, 2026-06-18)

**Stripe is NOT set up at all.** Verified read-only:

| Check | Result |
|---|---|
| `stripe` CLI on PATH | **absent** (`command -v stripe` → nothing) |
| `~/.config/stripe` | **does not exist** |
| `STRIPE_SECRET_KEY` / `STRIPE_API_KEY` in `~/.zshrc` | **absent** |
| `STRIPE_*` in `~/.hermes/.env` | **absent** |
| `sk_test_` / `rk_test_` / `sk_live_` anywhere | **none found** |
| any project `.env` mentioning STRIPE | **none** (the `grep` hits were all `node_modules` minified bundles + a Remotion overlay file literally named `OverlayedExplainerV17Stripe.tsx` from the Walk explainer — not credentials) |

The only `STRIPE`-pattern hit in `~/.hermes` is **`hermes-agent/agent/redact.py`**, which
contains Hermes's own **secret-redaction regexes** (`sk_live_…`, `sk_test_…`, `rk_live_…`)
so the agent never prints keys. That is a safety feature, **not a stored key**. So: a Stripe
test account + test key is a genuine prerequisite Dennis must provide (see §E).

**What IS already in place (the production side is real):**

- **Higgsfield CLI** at `/opt/homebrew/bin/higgsfield` (auth = device-login token file at
  `~/.config/higgsfield/credentials.json`, **not** an env var). Skill: `higgsfield-scene`.
  Critically, it exposes **`higgsfield generate cost <model> --prompt "..."`** — a *price
  preview with no generation*. This is the linchpin of the producer brain: the agent can
  know a scene's cost **before** spending.
- **ElevenLabs** key **is present** in `~/.hermes/.env` (voiceover). Note: there is **no**
  standalone `voiceover` skill dir in `~/.hermes/skills/` — VO is ElevenLabs-based and is
  produced inline / via the `media` skill, then muxed by `video-stitch`. (The brief listed a
  `voiceover` skill; it doesn't exist as a separate skill yet. Minor — treat VO as a spend
  point, not a missing dependency.)
- **walk-agent** (URL → 1080p walkthrough MP4; NVIDIA Nemotron in a NemoClaw sandbox — the
  load-bearing NVIDIA usage).
- **motion-graphics** (Remotion overlay/title/divider/callout clips — **local + free**, no
  API spend).
- **video-stitch** (ffmpeg assembly + VO/music mux — **local + free**).
- **Hermes Agent v0.16.0** on Nemotron 3 Ultra via NVIDIA (`~/.hermes/`), non-interactive
  via `hermes chat -q "..." -Q`; cheap tier `nemotron-3-super-120b-a12b` for sub-decisions.

**The crucial cost-attribution fact (do not let the demo blur this):** Higgsfield and
ElevenLabs spend goes to **Higgsfield's and ElevenLabs' own billing accounts**, drawn from
prepaid credits / their own card on file. **Stripe does not actually move that money.** So a
Stripe virtual card cannot *physically* gate a Higgsfield credit burn. What Stripe gates is
the agent's **own authorization to spend** — see §B for exactly how we make that honest and
still produce a real auto-decline.

---

## A. EARN — a customer pays for the video (Stripe Agent Toolkit, test mode)

**Goal:** a customer commissions a video; payment landing is the gate that starts production.

**Mechanism:** the **Stripe Agent Toolkit** (the agent-facing wrapper over the Stripe API;
also exposed as a tool surface at `mcp.stripe.com`). At job intake the producer brain:

1. **Prices the job** (see §B-i) and lands on a customer price, e.g. **$240**.
2. Calls Stripe (via the Agent Toolkit) to create a **Product + Price + Payment Link** in
   **test mode** — `create_payment_link` returns a hosted `https://buy.stripe.com/test_…`
   URL. (The Agent Toolkit's earn primitives — create product, create price, create payment
   link — are exactly the "agent that earns" surface the Stripe judges built the toolkit
   around.)
3. Hands the link to the customer. In the demo, the "customer" pays with Stripe's test card
   **`4242 4242 4242 4242`** (any future expiry / any CVC). No real money.
4. **Payment-landing gate:** production does NOT start until the agent observes the payment.
   Two ways, pick by demo reliability:
   - **(recommended, robust) Poll** the PaymentIntent / Checkout Session status to `paid`
     via the Agent Toolkit / API. Deterministic, no inbound tunnel, survives a flaky network
     on stage.
   - **(slicker, riskier) Webhook** `checkout.session.completed` → flips a local
     `paid=true` flag. Needs `stripe listen` forwarding (the Stripe CLI) or a public URL.
     We already need a webhook listener for §B's money-shot, so reuse that listener and the
     incremental cost is low — but keep **polling as the on-stage fallback**.

**Why this is credible:** "agent creates a payment link, customer pays, agent sees the money
land and only then starts working" is a clean, honest **earn** loop that is 100% real in test
mode (test mode behaves identically to live; the only difference is no real settlement).

---

## B. BUDGET / SPEND GOVERNANCE — the producer brain

This is the new IP versus Walk Agent. Nemotron runs the studio as a P&L.

### (i) Price the job from the brief/scope — using the Higgsfield cost preview

The agent decomposes the brief into a **scene plan** (e.g. 1 walkthrough segment + 3
cinematic Seedance scenes + 1 hero still + N motion-graphics cards + 1 VO track), then prices
**bottom-up from real previews**:

- For each AI scene, run **`higgsfield generate cost <model> --prompt "<scene prompt>"`** →
  a **real per-scene cost estimate, no generation, no spend.** Sum these.
- ElevenLabs VO: estimate from character count × the model's per-char rate (a table the
  agent keeps; ElevenLabs has no free "cost preview" call, so this is an estimate).
- walk-agent, motion-graphics, video-stitch: **$0 marginal** (local compute / NVIDIA usage
  that isn't metered per-video here). Tag them as free so the brain doesn't waste budget
  reasoning on them.
- **`COGS = Σ scene costs + VO estimate`.** Customer **price = COGS / (1 − target_margin)**.
  E.g. COGS $80, target margin 60% → price ≈ **$200**. This number becomes the §A Payment
  Link amount. *The studio is visibly profitable, computed live.*

### (ii) Set per-job and per-scene budgets targeting a margin

After payment lands ($240 say), the brain sets:

- **`PRODUCTION_BUDGET = price × (1 − target_margin)`** — the hard ceiling for all variable
  spend on this job (e.g. $96). Everything beyond that eats margin → forbidden.
- **Per-scene allocations** summing to ≤ budget, with a small reserve for one retry. The
  brain allocates *more* to hero/establishing scenes, *less* to filler.

### (iii) Before each scene's spend — approve / downgrade / decline+escalate

For every paid generation, Nemotron runs this decision at runtime (not a hardcoded rule):

```
preview_cost = higgsfield generate cost <model> --prompt "<scene>"
remaining    = PRODUCTION_BUDGET − spent_so_far
IF preview_cost ≤ scene_allocation AND preview_cost ≤ remaining:
        APPROVE  → generate at the chosen model
ELIF a cheaper model clears the quality bar for this scene:
        DOWNGRADE → re-price with the cheaper model, then APPROVE
        (e.g. Seedance 2.0 → a lower tier; GPT Image 2 → Nano Banana flash for a non-text plate)
ELSE:
        DECLINE + ESCALATE → do not spend; surface "scene X needs $Y over budget,
        approve overage or cut the scene?" (in autonomous demo mode: auto-cut/auto-decline)
```

Nemotron makes the **judgment** ("is the cheaper model good enough for *this* scene?") — that
is the agentic decision the hackathon rewards, and it's why this isn't just an `if` statement.

### THE ENFORCEMENT CHOICE — two options, with a clear recommendation

The §iii logic above is the **brain**. The question is what *enforces* it — what physically
stops an over-budget spend. Two designs:

#### Option 1 — Internal budget ledger gating the API calls (simple)

A local ledger (`spent_so_far`, per-scene allocations). Before any Higgsfield/ElevenLabs
call, the producer-brain skill checks the ledger and **refuses to issue the CLI command** if
it would exceed budget.

- **Pro:** trivial to build, fully deterministic, no Stripe dependency, demoable in an hour.
- **Pro:** it's the *true* control surface — since Higgsfield/ElevenLabs bill their own
  accounts, the only real lever the agent has is *whether it issues the command*.
- **Con (fatal for this hackathon):** it's **the agent policing itself in its own code.** A
  Stripe judge sees a Python `if spent > budget: refuse`. There is no Stripe in the
  money-shot. It does not demonstrate "the money layer enforces the limit" — it demonstrates
  "the developer wrote a guard." Low credibility on the *Stripe* axis.

#### Option 2 — Stripe Issuing test-mode virtual card + `issuing_authorization.request` webhook (RECOMMENDED)

Provision a **Stripe Issuing virtual card in test mode** with `spending_controls` (a
`spending_limit` set to `PRODUCTION_BUDGET`, interval `per_authorization` or `all_time`).
Enable **real-time authorization decisioning**: every time the card is charged, Stripe fires
an **`issuing_authorization.request`** webhook to our listener, which must reply **approve**
or **decline within ~2 seconds**. Our listener replies with the producer brain's §iii verdict.

In test mode you create authorizations programmatically with the **test helper**
`POST /v1/test_helpers/issuing/authorizations` (simulate a card charge of $X). So the demo
flow is:

```
agent wants to spend $Z on a scene
  → agent simulates a card authorization for $Z on its Issuing card (test helper)
  → Stripe sends issuing_authorization.request to our webhook
  → webhook = producer brain: approve if within budget, DECLINE if over
  → Stripe records an APPROVED or DECLINED authorization (real Stripe object, visible in dashboard)
  → on APPROVE, agent proceeds to the real Higgsfield/ElevenLabs generation
  → on DECLINE, agent does NOT generate; escalates/cuts the scene
```

- **Pro:** the auto-decline is a **real Stripe authorization object** with `approved:false`,
  visible in the test dashboard. This is *Stripe's money layer* enforcing the limit, exactly
  the "agents that spend under real controls" story. Maximum credibility with Stripe judges.
- **Pro:** `spending_controls` is a genuine, documented Stripe feature — even the brain's
  ledger and the card's own `spending_limit` are belt-and-suspenders (the card declines even
  if the brain's code had a bug).
- **Con / honesty requirement:** the card authorization is a **proxy/voucher** for the
  Higgsfield/ElevenLabs spend, not the literal payment to them (their spend hits their own
  prepaid accounts). We must say this plainly (see §E). It is **test-mode theater that
  faithfully models the real architecture** — in a production version the agent would
  actually fund Higgsfield via a top-up charged to this very Issuing card, making the proxy
  real. For a 12-day hackathon demo, the simulated authorization is the right call.
- **Con:** Stripe Issuing test access must be enabled on the account (a checkbox in test
  mode; see §E). Slightly more setup than Option 1.

#### Recommendation: **Option 2 (Issuing card + real-time `issuing_authorization.request`
webhook), with Option 1's ledger kept underneath as a redundant guard.**

Rationale: this is a **Stripe** hackathon. The single most memorable, on-brand beat is
"Stripe itself declined the agent's over-budget spend, no human touched it." That requires a
real Stripe authorization decision — Option 2 is the only one that produces a real Stripe
`declined` object. Option 1 alone reduces the money layer to an internal `if`, which is the
opposite of the theme. Build Option 2 for the money-shot; keep the ledger (Option 1) wired in
as the brain's own first-line check so we're not relying on a webhook round-trip for routine
in-budget approvals and so the system degrades gracefully if the webhook is slow on stage.

**Reality tag (so we don't overclaim):** the EARN side and the Stripe authorization
decisions are **genuinely real Stripe behavior** (test mode == live behavior, no settlement).
The link between "Stripe declined the authorization" and "Higgsfield was not charged" is
**modeled, not physical** — the gate that actually prevents the Higgsfield spend is the
agent choosing not to issue the CLI command after seeing the decline. State this explicitly
in the demo narration. (This is Dennis's known failure mode — overclaiming — so the script
must own it in one honest sentence.)

---

## C. ORCHESTRATION — the `producer-brain` Hermes skill

A new Hermes skill, `producer-brain`, that orchestrates the existing skills under budget.
Nemotron makes every judgment call at runtime; the skill is the harness.

```
producer-brain(brief, customer_contact)
  │
  ├─ 1. PLAN        Nemotron decomposes brief → scene list (type, model, prompt, quality bar)
  ├─ 2. PRICE       for each AI scene: `higgsfield generate cost` (no spend) + VO estimate
  │                 → COGS → customer price = COGS/(1−margin)
  ├─ 3. EARN        Stripe Agent Toolkit: create product+price+payment link (TEST) → send to customer
  │                 ┌─ GATE: poll PaymentIntent until `paid` (webhook as slicker alt) ─┐
  │                 └─ no payment → no production. Hard stop. ──────────────────────────┘
  ├─ 4. PROVISION   create/refresh Issuing virtual card (TEST) with spending_limit = budget,
  │                 real-time auth on; budget = price×(1−margin); allocate per scene
  ├─ 5. PRODUCE     for each scene, in order:
  │        ├─ preview cost (higgsfield generate cost)
  │        ├─ DECISION (Nemotron): approve / downgrade-model / decline+escalate   ← §B-iii
  │        ├─ simulate Issuing authorization for the approved amount (test helper)
  │        │     └─ Stripe → issuing_authorization.request → our webhook → approve/DECLINE
  │        ├─ if APPROVED: run the right skill
  │        │     • walkthrough scene → walk-agent      (URL → 1080p MP4, NVIDIA Nemotron)
  │        │     • cinematic scene/plate → higgsfield-scene  (Seedance / GPT Image 2 …)  [PAID]
  │        │     • title/divider/lower-third/callout → motion-graphics  (Remotion, FREE)
  │        ├─ if DECLINED: skip/cut scene, log overage, continue (or escalate to human)
  │        └─ update ledger (spent_so_far)
  ├─ 6. VOICEOVER   ElevenLabs VO for the script  [PAID — same decision gate as a scene]
  ├─ 7. STITCH      video-stitch: probe → normalize → concat in order → mux VO/music → verify  (FREE)
  └─ 8. DELIVER     final MP4 + a P&L receipt: price, COGS, per-scene spend, declines, margin
```

Key orchestration properties:

- **Nemotron is the decision-maker at steps 1, 2, 5.** Pricing, scene planning, and the
  per-scene approve/downgrade/decline judgment are LLM calls (`hermes chat -Q`), not static
  rules. Use Nemotron 3 Ultra for planning/pricing; the cheaper `nemotron-3-super-120b` for
  the high-frequency per-scene gate.
- **Free skills never touch the budget machinery** — motion-graphics and video-stitch are
  tagged `$0` and run freely; only Higgsfield and ElevenLabs calls pass through the Stripe
  authorization gate.
- **The P&L receipt (step 8)** is a presentation asset: a one-screen ledger showing the
  studio made money, with the declined line item visible. Great for the demo tweet.

---

## D. DEMO MONEY-SHOT — the auto-decline beat

The exact on-screen sequence (the single most important 15 seconds of the submission):

1. **On screen:** the producer brain has a $96 production budget; $88 already spent across
   the walkthrough + two cinematic scenes (ledger visible, margin bar shrinking).
2. The agent reaches the **final hero scene**. It runs
   `higgsfield generate cost seedance_2_0 --prompt "…"` → preview says **$14**.
3. Nemotron's gate: `$14 > remaining $8`. It first **tries to downgrade** the model to clear
   the budget — and (scripted for the demo) decides the cheaper model can't hold the hero
   shot's quality bar. So it proceeds to attempt the spend at full price to show the control
   fire.
4. The agent **simulates the $14 Issuing authorization** on its Stripe card (test helper).
5. **Stripe fires `issuing_authorization.request`** → our webhook (the producer brain)
   evaluates against the live budget and **replies `decline`**. (Even the card's own
   `spending_limit` would decline it independently — show both.)
6. **On screen, no human present:** the terminal prints
   `Stripe authorization DECLINED — $14 exceeds remaining budget $8. Scene cut. No spend.`
   Cut to the **Stripe test dashboard** showing the **`Declined` authorization** object
   (real Stripe record). Cut to the **NVIDIA**-driven agent log: it did **not** call
   Higgsfield; it cut the scene and proceeded to stitch.
7. **Payoff line (honest):** "No human approved or denied this. The agent hit its own budget,
   and Stripe's money layer declined the charge — in test mode, modeling exactly how it would
   gate a real Higgsfield top-up in production." Then it delivers the finished, profitable
   video.

The money-shot = **a real Stripe `declined` authorization, triggered autonomously by the
agent's own budget, with the finished video as proof the studio still shipped at a profit.**

---

## E. PREREQUISITES Dennis must provide + minimal setup

**Honesty banner for the whole project (bake into README + demo narration):**
> Stripe is in **test mode**. The customer payment (earn) and every authorization decision
> (spend) are **real Stripe behavior** — test mode is byte-for-byte the live API minus
> settlement. The one **modeled** link is that a declined Issuing authorization stands in for
> "Higgsfield/ElevenLabs was not charged" — those vendors bill their own accounts, so the
> agent enforces the decline by **not issuing the generate command**. The Stripe card models
> a production top-up flow. We do not claim Stripe physically moved Higgsfield's money.

**What Dennis must provide (the only real blockers):**

1. **A Stripe account + test API key.** Free, no business details needed for test mode. Get
   the **test secret key** (`sk_test_…`) from Dashboard → Developers → API keys (toggle
   "Test mode" on). Restricted key (`rk_test_…`) scoped to PaymentLinks + Issuing is the
   safer alternative.
2. **Enable Stripe Issuing in test mode** on that account (Dashboard → Issuing → "Get
   started"; test mode requires no real underwriting). Needed for the §B/§D money-shot. If
   Issuing test access turns out to be gated on the account, **fall back to §B Option 1's
   ledger for the gate and still use the Agent Toolkit for the earn side** — the earn loop
   alone is a complete, real Stripe story.
3. **(optional but recommended) the `stripe` CLI** — `brew install stripe`, then
   `stripe login` (test mode) for `stripe listen --forward-to localhost:<port>` to drive the
   webhook locally without a public tunnel. Not strictly required if §A uses polling, but it
   makes the §D webhook demo turnkey.

**What is already real and needs nothing:** Higgsfield CLI + device-login token; ElevenLabs
key in `~/.hermes/.env`; walk-agent / motion-graphics / video-stitch skills; Hermes on
Nemotron via NVIDIA. (Note: confirm Higgsfield account has **prepaid credits** so the real
in-budget generations in the demo actually run — that's a Higgsfield account state, not a
Stripe one.)

**Minimal setup steps (once Dennis hands over the test key):**

1. Put `STRIPE_SECRET_KEY=sk_test_…` (or the restricted `rk_test_…`) in **`~/.hermes/.env`**
   (Hermes reads `.env`, not shell env — established gotcha). Verify presence by length, never
   print the value. Do not put it in `~/.zshrc` (one-off, project-scoped).
2. Enable Issuing in the test dashboard; create one test cardholder + one virtual card via
   the API (programmatically, inside the skill, with `spending_controls`).
3. `stripe listen --forward-to localhost:<port>` (or wire the webhook to the polling
   fallback). Point `issuing_authorization.request` and `checkout.session.completed` at the
   local handler.
4. Build the `producer-brain` skill harness around the existing skills (separate task — **not
   in scope here**; this is the design only).

---

## Recommendation summary

- **Stripe setup status:** **NOT set up.** No CLI, no config dir, no key anywhere. The only
  `STRIPE` string on the machine is Hermes's own secret-redaction regex in `redact.py`. A
  Stripe test account + `sk_test_`/`rk_test_` key is a real prerequisite Dennis must supply.
- **Recommended budget enforcement:** **Stripe Issuing test-mode virtual card with
  `spending_controls` + a real-time `issuing_authorization.request` webhook** (Option 2),
  with the internal ledger (Option 1) kept underneath as a redundant first-line guard. It is
  the only design that yields a **real Stripe `declined` authorization** for the autonomous
  money-shot — far more credible to Stripe judges in ~12 days than an internal `if`. Fall
  back to the ledger only if Issuing test access is unexpectedly gated.
- **Earn side:** Stripe Agent Toolkit Payment Link (test mode), payment-landing gates
  production; poll for `paid` (robust) with webhook as the slicker alternative.
- **The one honesty caveat to narrate:** the declined Stripe authorization is a faithful
  *model* of the Higgsfield/ElevenLabs spend, not the literal payment to them — test-mode
  theater that mirrors the real production architecture. Say it in one sentence; don't
  overclaim.
