# DEMO-BEAT-SHEET.md — the 8-beat recordable scaffold for the submission video

_Read-only scaffold, 2026-06-20. For Dennis to record. Deadline: EOD Tue 2026-06-30._

This is the shot-by-shot recording plan for the **1–3 min submission demo video** — the #1
win-mover per `WINNING-STRATEGY.md` §(g). The beat order follows §(c) exactly: cold-open money
line → agent wakes → Nemotron PLANs → PRICE + pay-gate → auto-decline money-shot → agent writes
Remotion → NemoClaw walkthrough → finished video → P&L close.

Target runtime: **~2:15–2:45** (upper bound of the 1–3 min window; verify exact bounds — Tier 0 V2).

**Every claim below is ground-truthed against the real artifacts:**
- the dashboard UI (`dashboard/{index.html,app.js}`) — the exact views/labels you screen-record;
- the real Hermes-driven run (`evidence/hermes-driven-run/transcript.md`, session `20260620_000754_46aa2a`);
- the money-shot ledger (`runs/demo-3-decline/ledger.json`);
- the finished cut (`runs/demo-1-approve/final.mp4`, 32.3s, 1080p, audio-on — the strongest delivered video).

---

## THE SINGLE HONESTY RULE THAT DECIDES THE ENTRY (read before recording)

Stripe is a **judge**. The committed money-shot ledger (`runs/demo-3-decline/ledger.json`) carries
`"simulated": true`, `"id": "iauth_sim_50127164"`, `"decline_reason": "spending_controls"`,
`"approved": false`. **That is the agent's own budget governor producing a faithful Issuing-shaped
authorization object — NOT Stripe's native card network declining a live charge.**

- ✅ SAY: "the agent's budget governor declines the over-budget scene," "it models the Stripe
  Issuing decline," "approved = false, no human in the loop."
- ❌ NEVER SAY: "Stripe declined the charge," "the card was declined by Stripe," "a real payment failed."
- The on-screen **TEST MODE** and **(simulated)** badges are assets, not weaknesses — every reviewer
  praised them. Keep them visible. They read as credible.
- This rule is overridden ONLY if R1 is closed live (real `stripe listen` webhook → a real declined
  authorization object on screen). See ASSETS STILL NEEDED. Until then, narrate the governor, not Stripe.

The same discipline applies to the **earn / pay-gate** beat: the pay-gate badge literally says
"TEST MODE · sandbox Stripe · test card 4242…". Narrate it as a **real Stripe test-mode Checkout**
(true) — not as a real customer paying real money.

---

## COLD-OPEN HOOK (the first 5–8s — non-negotiable)

Open on the money line over the live build console. **NOT** "hi, this is our entry," no logo card first.
First frame = the agent doing a human's job.

> **"This is an AI agent running a video-production company. It just quoted a customer, charged
> them, wrote the video itself — and refused to overspend doing it. Watch."**

(Cut on "Watch." straight into Beat 1's wake. This line doubles as the tweet copy — see end.)

---

## THE 8 BEATS

### BEAT 1 — HOOK + THE AGENT WAKES · ~0:00–0:12 (~12s)

**On-screen action:** The Producer Console (`http://localhost:3030`, dark theme, amber accent).
Open on the idle hero: the word-by-word build "An agent that produces, prices, and **ships a video.**"
(`index.html` line 70). Then a real `hermes chat` session kicking off — the actual terminal launch
from the proof run, or its verbose log scrolling:
```
hermes chat -v --yolo --max-turns 40 -s producer-brain -q "<brief>"
model=nvidia/nemotron-3-super-120b-a12b   provider=nvidia
```
On-screen lower-third tag: **"Hermes agent · Nemotron brain."**

**Capture notes:** Two layers to choose from — (a) screen-record the terminal `hermes chat` startup
(grounds "real agent runtime," our hard-won proof), then (b) cut to the console idle hero. Recommended:
1–2s of the terminal showing `model=nvidia/nemotron-3-super-120b-a12b provider=nvidia` (the FREE-model
proof, `transcript.md` lines 19–22), then push into the browser console. Cut on the cold-open "Watch."

**VO:** (cold-open line lands over the terminal/console) … then:
> "It runs on the Hermes agent runtime — reasoning on NVIDIA's free, open Nemotron model. No human is
> driving this."

**Timing:** ~12s (the cold-open line is ~7s; the wake/tag is ~5s).

---

### BEAT 2 — PLAN (Nemotron writes the script) · ~0:12–0:35 (~23s)

**On-screen action:** A live build is started — paste a company URL + goal into the **NEW BUILD** bar
(`index.html` lines 44–56) and hit Build. The console enters `phase=="planning"` and the **Script panel**
types out (rAF-typed, `app.js` `liveScript`/`initLiveScript`): the **VO narration** in the serif "VO ·
Voiceover narration" card AND the ordered **Shot list** ("Shot list · N scenes") with each scene's
type + producing model + duration. This is Nemotron authoring a site-specific storyboard from the URL.
Real plan reference (`transcript.md` step 2 / `runs/demo-1-approve`): 5 scenes —
`title-open · cine-establish [seedance_2_0] · walkthrough · cine-hero [gpt_image_2] · title-close`.

**Capture notes:** Record the Script panel typing live (don't pre-skip it — the typing IS the "agent
writing the script" moment). The phase-track chips at the top sweep amber left-to-right (`liveHeader`).
Caption overlay: **"NVIDIA Nemotron-3-Super-120B — free, open."** Cut once the shot list is fully
populated. If the live planner is slow on camera, pre-stage a planned run and scrub the Script panel.

**VO:**
> "Give it a company URL and a goal. Nemotron plans the whole shoot — it writes the voiceover, then a
> shot list: an opening title, a cinematic establishing shot, a product walkthrough, a hero plate, a
> close. A real storyboard, built from the site — not a template."

**Timing:** ~23s. (The visible decision-maker — NVIDIA axis.)

---

### BEAT 3 — PRICE + THE PAY-GATE (the agent gets PAID first) · ~0:35–0:55 (~20s)

**On-screen action:** The build advances to `phase=="awaiting_payment"`. The **pay-gate card**
(`app.js` `payGate`) appears: a big amber price (e.g. **$0.92** / **$1.05** — from the real ledgers),
the "to produce · <brand> promo video" line, and the honest badge **"TEST MODE · sandbox Stripe · no
real charge · test card 4242 4242 4242 4242."** Beside it the economics summary (`livePnl(l, true)`):
**"You pay $X · Agent budget $Y · Auto-declines over $Y."** A **"Pay $X to produce"** button opens the
real `cs_test_` Stripe Checkout in a new tab. On payment → green "payment received — starting
production…" and the build resumes.

**Capture notes:** This is the EARN proof. Best version: a committed ledger that contains a real
`cs_test_` session id and `payment_status: "paid"` (see ASSETS STILL NEEDED — needs Dennis to pay the
test checkout once, card 4242, $0 real money). If that's captured, show the actual Checkout page
opening + the green confirmation. Fallback if not paid live: show the pay-gate card with the real
`cs_test_…` session id in the side panel + the TEST-MODE badge, and narrate the test Checkout honestly.
The "Auto-declines over $Y" cell visually pre-arms Beat 4 — point to it.

**VO:**
> "Before it spends a cent, the agent prices the job for margin and charges the customer — a real
> Stripe test-mode checkout. It gets paid first. And it sets itself a hard production budget: spend
> past it, and it auto-declines."

**Timing:** ~20s. (Stripe earn axis. The "Auto-declines over $Y" line sets up the money-shot.)

---

### BEAT 4 — THE MONEY-SHOT · AUTO-DECLINE · ~0:55–1:18 (~23s) — THE CENTERPIECE

**On-screen action:** Production runs; scenes pop up in the storyboard (`liveStoryboard`:
queued → working → done). Then the over-budget scene hits the budget gate and is **CUT**. Open the
**Budget gate · timeline** view (`app.js` `gate`/`gateRow`) on the canonical money-shot run
(`runs/demo-3-decline`): the filmstrip shows the declined clip with the scissors icon in **red** (the
only place red appears), and the gate row reads:
- scene **`hero-still`** · brief "Elaborate hero plate…" · model `gpt_image_2`
- **would cost $0.60 · CUT** · pill: **decline**
- the authorization line: **"Stripe authorization DECLINED · iauth_sim_50127164 · approved=false"**
And the P&L side card: **"The budget gate auto-declined 1 scene and saved $0.60 of overage — no human
in the loop."** The margin holds green at **67.4%** (above the 60% target).

**Capture notes:** SLOW DOWN here — this beat out-differentiates HermesCo, give it room. Push in on the
red scissors + the `approved=false` authorization row. Hold on "saved $0.60 of overage — no human in
the loop." The numbers are exact, from `runs/demo-3-decline/ledger.json` (`would_have_cost_cents: 60`,
`overage_avoided_cents: 60`, `margin: 0.6739`, `decline_reason: "spending_controls"`,
`simulated: true`). **Honesty: this is the simulated/modeled decline — narrate the governor, see top rule.**

**VO:**
> "Here's the part no template can do. A hero scene would cost sixty cents and blow the budget. So the
> agent's budget governor declines it — models the Stripe Issuing decline, approved equals false, on
> its own. It saves the overage, protects its margin, and ships anyway. An agent that refuses to lose
> money."

**Timing:** ~23s. (Viability axis — the rarest, most "agentic-commerce" beat. Let it land.)

---

### BEAT 5 — THE AGENT WRITES REMOTION · ~1:18–1:38 (~20s)

**On-screen action:** Open the **Studio** view (`app.js` `studio`/`typeCode`): a real Remotion `.tsx`
component types out, line-numbered, syntax-highlighted (the tokenizer colors `interpolate`, `spring`,
`import`, etc.), with the render-state going **"writing… → rendered · <ms>ms"** and the rendered clip
playing in the PREVIEW · Remotion pane. Tabs across the top are the authored scenes (e.g. `title-open.tsx`,
`title-close.tsx` with their archetype labels). The code is genuinely the agent's generated component
(`remotion_codegen.py`), replayed.

**Capture notes:** Record the code typing to the "rendered · Xms" flip, then the preview clip playing.
Pick the title scene with the cleanest motion. This is unique vs JSON-deliverable competitors — feature
it. Don't let the typing run too long; ~6–8s of typing then the render flip is enough.

**VO:**
> "And it isn't filling in a template. For every title and motion-graphics scene, the agent writes the
> Remotion code itself — real React, it compiles, it renders. The agent is doing the creative work."

**Timing:** ~20s. (Unique-vs-JSON differentiator.)

---

### BEAT 6 — PRODUCE IN A NEMOCLAW SANDBOX (the walkthrough) · ~1:38–1:55 (~17s)

**On-screen action:** The walkthrough scene. In the **Source media** view (`app.js` `sourceMedia`) or
the live agent pane (`liveAgent` — a faux browser chrome bar with the company URL + "live" dot and the
walkthrough clip playing), show the product walkthrough captured by an agent inside a NemoClaw sandbox.
Reference clip: `runs/demo-1-approve/clips/03_walkthrough.mp4` (real `walk-agent` source per the ledger).

**Capture notes:** ⚠️ Quality risk — see ASSETS STILL NEEDED (R5). The existing walkthrough clip was
captured under the BEAM viewport bug (`WALKTHROUGH-INVOCATION-FIX.md`): 1280×720 frames rendered into a
1440×900 `cover` box → ~80px clipped each side (the Stripe wordmark loses "Strip"). On a full-bleed cut
this reads as "B-grade internal tooling." If a framing-fixed re-capture isn't ready, keep this beat
SHORT, frame the clip inside the dashboard's browser chrome (not full-bleed), and lean the VO on the
"secure sandbox" point rather than dwelling on the footage.

**VO:**
> "The walkthrough — actually clicking through the product — is captured by an agent running inside a
> secure NemoClaw sandbox, on NVIDIA's stack."

**Timing:** ~17s. (NemoClaw axis. Keep tight if the framing fix isn't in.)

---

### BEAT 7 — THE FINISHED VIDEO · ~1:55–2:25 (~30s)

**On-screen action:** The **delivered hero** (`app.js` `deliveredHero`): the headline builds
"Your **<brand>** promo is **ready**", a **DELIVERED** badge, the final cut playing full-bleed with
**audio on**, a real **Download MP4** link + **Copy link** share button, and the meta line
("final.mp4 · 32s · clips · audio on · …"). Then play the actual film with sound.

**Capture notes:** Use **`runs/demo-1-approve/final.mp4`** — 32.3s, 1080p, audio-on, carries real
Seedance + GPT Image 2 + walkthrough footage (verified). This is the payoff: let 20–30s of the real
film breathe, full-bleed, with its audio bed. **Do NOT use `runs/build-orinovate-edf804`** as the
finished video — it's `status: failed`, 14s, NO audio track (verified via ffprobe). If a re-rendered
Orinovate (or other) hero cut with audio lands, prefer the freshest delivered, audio-on run.

**VO:** (mostly let the film + its music/VO carry; one line up front)
> "And it ships a finished, on-brand video — promo and walkthrough, scored, graded, delivered. The kind
> of thing a business pays an agency two thousand dollars for."
> *(then drop VO and let the film play with its own audio for ~15–20s)*

**Timing:** ~30s. (Usefulness + presentation payoff. The longest single beat by design.)

---

### BEAT 8 — THE P&L CLOSE · ~2:25–2:42 (~17s)

**On-screen action:** Land on the **Profit & loss** receipt (`app.js` `pl`): "PRODUCTION P&L · PRICE
CHARGED $X · COGS SPENT $Y · GROSS PROFIT $Z" and the **NET MARGIN** card (e.g. **60.0%** on the
hermes-driven run, or **67.4%** on demo-3-decline) above the target, with the "auto-declined 1 scene ·
saved $0.60 · no human in the loop" note. Hold on the margin figure as the closing frame.

**Capture notes:** Use the P&L from the run you've been following. The clean thesis numbers from the
real Hermes-driven run: **price 80¢ · COGS 32¢ · gross profit 48¢ · margin 60.0% · declines 0**
(`transcript.md` line 123). For the decline story, demo-3's **price 92¢ · COGS 30¢ · profit 62¢ ·
margin 67.4% · 1 cut** is the stronger close. End on the thesis line, then the title card.

**VO:**
> "Price, eighty cents. Cost, thirty-two. Sixty percent margin, zero budget overruns. An agent that
> earns, spends within its limits, and ships — a company in a box."

**Timing:** ~17s. End on the thesis + a title card (see tweet copy).

---

## TITLE-CARD / TWEET COPY (tag @NousResearch)

> **A Hermes agent on NVIDIA Nemotron runs a whole video-production company — it quotes a customer,
> charges them on @stripe, declines its own over-budget spend to protect margin, writes the Remotion
> itself, and ships a finished video. A profitable P&L, live, on the open stack. cc @NousResearch
> #HermesHackathon**

(End-card text variant, shorter: "An agent that earns, spends within its limits, and ships. A company
in a box. — built on Hermes · Nemotron · Stripe · @NousResearch")

---

## ASSETS STILL NEEDED (flagged by beat)

Ordered by how much each gates the cut. Items 1–2 are the real risks; 3 is a bonus that upgrades a beat
from "honest fallback" to "knockout."

1. **[BEAT 6/7 — quality risk R5] A framing-fixed walkthrough clip (free, ~3–5 min run).** The current
   walkthrough footage (`runs/demo-1-approve/clips/03_walkthrough.mp4` and any new walk-agent capture)
   is clipped ~80px/side by the BEAM viewport bug (`WALKTHROUGH-INVOCATION-FIX.md`). Fix is scoped + free
   in the sibling `walk-ultra/` repo (set BEAM scout viewport to 1440×900, OR `objectFit: contain` in
   `Explainer.tsx`, OR `BEAM=0` in `tutorial-maker.sh`), then re-capture once. Until then: keep Beat 6
   short and frame the clip inside the browser chrome, not full-bleed. **This is the single biggest
   quality lift for the cut.**

2. **[BEAT 3 — earn proof] A committed ledger with a real `cs_test_` paid session.** Today every
   committed `earn` block is `dev_mode` / unpaid; no ledger shows `payment_status: "paid"` with a real
   `cs_test_…` id (orinovate's real run failed before payment; demo runs are mock). To make Beat 3 fully
   real, Dennis pays ONE test checkout in the browser (card 4242, $0 real money) so a committed ledger
   carries the paid session. Stripe IS already configured (`acct_1TTyp9Aj3uJtl67R`) — this is just one
   click-through, not setup. **Honest fallback exists** (show the pay-gate card + real `cs_test_` session
   id + TEST-MODE badge), so this is a "make it real" upgrade, not a blocker.

3. **[BEAT 4 — bonus, upgrades the money-shot] A REAL declined Issuing authorization object on camera.**
   Closing R1 turns Beat 4 from the modeled/simulated decline (which we narrate honestly as the budget
   governor) into a real declined-authorization object — a knockout. Needs the interactive step:
   `stripe login` (CLI is installed) → `python3 stripe_webhook.py` (port 4242) → `stripe listen
   --forward-to localhost:4242/webhook --events issuing_authorization.request` → a `--stripe-live` run
   whose over-budget scene declines via the brain's webhook verdict (`webhook_declined`). Per
   `STRIPE-SETUP.md` this is a ~5-min morning step. **If NOT done, do NOT narrate the sim as a real Stripe
   decline — narrate the governor (see the top honesty rule). This is the one item that can disqualify us
   if mishandled.**

4. **[BEAT 7 — preferred] A fresh delivered, audio-on hero cut in the target brand (optional).**
   `runs/demo-1-approve/final.mp4` (32.3s, audio-on, real footage) is a solid finished-video asset today.
   If Dennis wants the finished video to match the same brand he runs live in Beats 2–6, a fresh
   delivered run (mode real, audio on, framing fix applied) would tie the cut together. Not a blocker —
   demo-1 works.

5. **[BEAT 1 — nice-to-have] A clean screen-recording of the `hermes chat` terminal launch** showing
   `model=nvidia/nemotron-3-super-120b-a12b provider=nvidia` (the FREE-model proof). The proof run's
   `session-raw.log` exists; a fresh 2–3s terminal capture reads better on camera than scrolling a log.

### Leak/rehearsal check before recording (cheap, from WINNING-STRATEGY Tier-1 #6 / R6)
Rehearse the exact click-path so the live console never surfaces on camera: raw Python tracebacks,
literal `stripe login` strings, `PRODUCER_SIMULATE_PAID`, `"MONEY-SHOT:"` labels, or a served `build.log`.
Don't HTTP-serve project source if screen-sharing the browser. Confirm the dashboard is on :3030 (it is)
and the run you're demoing is pre-loaded.
