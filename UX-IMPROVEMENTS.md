# UX Improvements — Hermes Producer Console

_Read-only product/UX review, 2026-06-19. Scope: the end-to-end user experience of the
all-in-one video producer — the input step, the "watch it build" arc, trust, the pay moment,
the payoff, control, edge states, polish, and cohesion. Infra/security/reliability/perf are
explicitly out of scope (covered in `PRODUCTION-READINESS-REVIEW.md`); a handful of items below
touch the same code as that review but are flagged here only for their **felt experience**, not
their engineering. Files reviewed: `dashboard/{index.html,app.js,styles.css,serve.py}`,
`build_runner.py`, `ledger.py`, `plan_job.py`, and the seven existing run ledgers._

**The honest one-line read:** this is a beautiful, legible *receipt viewer* with a genuinely
striking live-build moment — but as a *product* the loop is open at both ends. A first-timer
doesn't know what they'll get or what it costs before starting, and at the end there is no way to
actually take the video (no download/share/deliver). The thing it sells — "an all-in-one producer
that ships you a finished video" — stops one click short of shipping. And the on-screen price
($0.92–$1.30) silently undercuts the "real agency made it" story it works so hard to tell.

Severity legend: **HIGH** (breaks the core promise or first impression) · **MEDIUM** (real
friction/confusion) · **LOW** (polish).

---

## 1. First-run / onboarding & the input step

### 1.1 A newcomer cannot tell what this is or what they'll get before committing — HIGH
On load, `init()` auto-selects a finished run (`app.js:29`, prefers a decline run) and drops the
user straight into a dense P&L receipt for *someone else's* job. The NEW BUILD bar
(`index.html:40-48`) is a 304px column with two thin inputs and a Build button — there is **no
headline, no one-line "paste a URL, we plan + price + produce a promo + walkthrough", no example,
no sample of the output**. The empty stage says only "Select a job from the ledger."
(`index.html:61`), which assumes you already have jobs and know what a "job" is here. A
first-timer's first screen should explain the product in one sentence and show what a finished
result looks like.
- **Fix:** when there are no *user* builds yet (or on first load), make the stage a short hero:
  product name + one-line value prop + "Paste a company URL to start" pointing at the bar + a
  looping thumbnail of a finished `final.mp4`. Keep auto-selecting a demo, but frame it as
  "Example build" not as the user's own.

### 1.2 The input gives no preview of duration, goal options, or price — HIGH
The bar collects only `url` and an optional `goal`. **Duration is invisible** — it is hardcoded
to 30s in `serve.py:119` and there is no field for it, yet the product copy ("30-second promo
plus a walkthrough") implies a choice. There is **no price estimate before Build**: the user
commits to an unknown spend and only sees the number after ~90s of planning, at the pay gate.
For an "all-in-one producer," the buyer wants to know "≈$X for a ≈30s promo + walkthrough"
*before* they click.
- **Fix:** add a duration selector (e.g. 15 / 30 / 60s chips) and a goal-style hint, and show a
  *ballpark* price range in the bar ("typical promo + walkthrough: $0.90–$1.40") so the user has a
  cost anchor before planning even starts. Even a static range beats zero.

### 1.3 Placeholder/affordance copy is thin and the goal field reads optional-but-load-bearing — MEDIUM
Placeholders are `"company URL…"` and `"goal (optional)…"` (`index.html:42-43`). The goal field
heavily shapes the walkthrough (`plan_job._template_plan` feeds `goal` into the walkthrough
brief), so "optional" undersells it. There's no example URL, no autofill, no "try Stripe / Linear /
Notion" chips even though the system has real palettes for exactly those brands.
- **Fix:** richer placeholders ("e.g. stripe.com" / "what should the walkthrough show? e.g. 'how
  to create an issue'"), and one-tap example chips for the brands with known palettes. Label the
  goal as "what to demo" rather than "optional."

### 1.4 No client-side validation feedback — MEDIUM
`startBuild()` (`app.js:357`) only checks the URL is non-empty and focuses the field silently if
not — no inline error, no message. A typo'd or non-URL string is `https://`-prepended in
`serve.py:115` and sent to the planner regardless; the user gets no "that doesn't look like a
URL" signal until (maybe) a failed build minutes later.
- **Fix:** lightweight inline validation (URL shape, helpful message), and disable Build until the
  field looks like a host.

---

## 2. The "watch it build" experience

### 2.1 The ~90s Nemotron planning wait is near-dead air — HIGH
This is the single biggest pacing gap. After Build, `renderLive` shows `liveHeader` + the agent
pane + an **empty** Script panel ("the agent is still writing the narration…" / "deciding the shot
list…", `app.js:505,514`) + an empty storyboard ("deciding the storyboard…", `app.js:595`). The
planner call can take up to 5 minutes (`validate_planner` `urlopen(timeout=300)`), and for most of
it the screen is three spinners and a static URL. The console's whole reason to exist is "watch the
agent build" — the very first phase is the longest and shows the least.
- **Fix:** narrate the planning phase actively. Stream interim events ("reading
  stripe.com…", "identifying brand palette…", "drafting 5 scenes…", "writing voiceover…") into the
  action feed during planning, even if some are scripted beats tied to elapsed time. Show a
  skeleton shot-list (5 placeholder rows pulsing) so the layout that's *about* to fill is visible.
  Add a subtle elapsed timer or progress hint so the wait feels bounded, not hung.

### 2.2 Two different "Script" panels appear, with confusingly near-identical labels — MEDIUM
During `awaiting_payment` the section reads "Script · the agent priced it before shooting"
(`app.js:425`); during production it reads "Script · the agent wrote it before shooting"
(`app.js:432`). Same panel, two subtly different captions a few seconds apart — the distinction
("priced" vs "wrote") is too fine to register and just reads as the UI flickering its own labels.
- **Fix:** one consistent caption for the Script panel across phases (e.g. "Script · what the agent
  decided before shooting"). Let the *phase track* carry the "now pricing / now producing" state,
  not the section label.

### 2.3 The "agent browser" pane is honest-but-underwhelming until a walkthrough exists — MEDIUM
`liveAgent` (`app.js:578`) renders a fake browser chrome with a red "live" dot and, when no
walkthrough clip exists yet, just the **last event string** centered in the frame
(`agent-think`). The chrome strongly implies a live browser session, but for most of the build
it's a single line of text under "live" — the gap between the framing and the content is felt.
- **Fix:** either lean into it as an honest "agent activity" pane (drop the browser chrome until a
  real walkthrough clip is streaming, show a richer live log there) or make the placeholder more
  alive (typing cursor, rotating "navigating… reading… capturing…" states). Don't promise a live
  browser the pane can't yet deliver.

### 2.4 The live P&L ticker only appears in the production view, not at the pay gate — MEDIUM
`livePnl` (`app.js:615`) renders Price / Spent / Budget left / Margin — but `renderLive` omits it
from the `awaiting_payment` branch (`app.js:422-430`). So at the exact moment the user is deciding
whether to pay, the margin/economics story (the product's whole thesis) is hidden; it only shows
*after* they've paid. The most persuasive panel is absent from the decision screen.
- **Fix:** show a compact economics summary on the pay gate ("you pay $X · agent's budget $Y ·
  it auto-declines anything over budget") so the value and the guardrail are visible *before*
  payment, not after.

### 2.5 Scene "pop-up" pacing depends on a hidden env var with no in-UI cue — LOW
Pacing is governed by `PRODUCER_PACE` (`build_runner.py:74`); the storyboard cards transition
queued→working→done. This is good, but there's no "now producing scene 2 of 5" counter anywhere —
the user can't tell how far through production they are at a glance.
- **Fix:** a small "N of M scenes" progress readout on the storyboard header.

---

## 3. Trust & transparency

### 3.1 The price ($0.92–$1.30) silently contradicts the "real agency" positioning — HIGH
Every run prices a finished promo + walkthrough at **92–130 cents** (`index.json`; pay gate renders
`cents(price)` → "$0.92"). The product's stated bar is "looks like a real agency made it," and the
P&L brags about "NET MARGIN 67%." A sub-dollar price for a 30s branded video is so far below any
real-world rate that it undercuts the credibility the rest of the UI is building — a viewer's
instinct is "this isn't real money / this is a toy." The number is technically honest (it's the
COGS-plus-margin of the *mock* cost stub) but as a *presented price* it damages trust.
- **Fix:** this is a positioning decision, not a code bug. Either (a) price in realistic dollars
  for the demo (a configurable price floor / a "list price $X" the margin is computed against), or
  (b) explicitly frame the cents figure as "marginal COGS-based price (demo economics)" so the
  viewer reads it as a unit-economics proof, not a retail price. Right now it's presented as a
  retail price and reads as fake.

### 3.2 "TEST MODE · sandbox Stripe" is well done — keep it, and extend the honesty pattern — LOW (strength)
The pay gate badge "TEST MODE · sandbox Stripe / no real charge · test card 4242…"
(`app.js:463-464`) and the `pg-note` explaining poll-based detection (`app.js:475`) are exactly
the right kind of honesty, and the decline note's `(simulated)` tag (`app.js:348`) matches the
data. Preserve this. The one place it's missing: the *mock* mode escape hatch produces a real video
with placeholder footage but the finished view doesn't loudly say "this is a $0 mock with
storyboard placeholders, not real footage" (see 5.4).

### 3.3 The decline "MONEY-SHOT" event copy is internal-jargon, leaks into the user log — MEDIUM
The run log surfaces raw event strings including `"MONEY-SHOT: Stripe declined authorization for
'hero-still' — $0.60 cut, no human"` (demo-3 seq 11). "MONEY-SHOT" is internal demo language —
it's the team's name for the beat, not something a customer should read in their own production
log. Same with `"PRODUCER_SIMULATE_PAID=1 — dev affordance…"` (`build_runner.py:167`) which would
appear verbatim in a user's feed in dev runs.
- **Fix:** keep two registers — internal event `level`s for styling, customer-facing `msg` copy
  that reads like a producer's note ("Skipped the hero plate — it would have pushed the budget
  over; the cut still delivers the story."). Never surface `PRODUCER_SIMULATE_PAID` / `dev
  affordance` text in the customer-visible feed.

### 3.4 What the customer is actually *buying* is never stated — MEDIUM
The pay gate sells a "<brand> promo video" for $X (`app.js:467`) but never says what that
includes: how long, how many scenes, that it's a promo *plus* a walkthrough, what resolution, what
deliverable format. The shot list is in a separate panel above; the pay card itself is just a big
number and a button.
- **Fix:** put a 1-line deliverable summary on the pay card ("~30s · 5 scenes · 1080p MP4 · promo +
  product walkthrough") so the price has something concrete attached to it.

---

## 4. The pay moment

### 4.1 Clicking Pay opens a new tab and the console gives a weak handoff — MEDIUM
`initPayGate` (`app.js:482`) does `window.open(url, "_blank")` and changes the status text to
"Checkout opened in a new tab — waiting for payment…". On a hackathon demo this is fine, but as a
product the handoff is fragile: if the popup is blocked, nothing happens and the only feedback is a
button that now looks `.opened` (dimmed) with no error. There's no "didn't open? click here" link,
no inline/embedded checkout option.
- **Fix:** detect a blocked popup (the `window.open` return value is null) and fall back to showing
  the checkout URL as a clickable link / "Open checkout" retry. Consider Stripe's embedded checkout
  so the user never leaves the console (much stronger "all-in-one" story).

### 4.2 There is no "cancel / I changed my mind" at the pay gate — HIGH (felt)
Once `awaiting_payment`, the only exits are: pay, or wait 15 minutes for `payment_timeout`
(`build_runner.py:50,192`). The console offers **no cancel button** at the pay gate (or anywhere
during a build). A user who pasted the wrong URL, or saw a plan they don't like, is stuck staring
at a pay card for 15 minutes with no way out except killing the server. This is the most jarring
"I am trapped in this flow" moment in the product.
- **Fix:** a "Cancel build" affordance on the pay gate and the live header that abandons the run
  (and ideally tells the backend to stop). Even a client-side "start over" that abandons the poll
  and clears the view would remove the trapped feeling. (The backend cancel is also noted in the
  production review §7.1; here it's the *felt* dead-end that matters.)

### 4.3 The wait-for-payment state is honest but static — LOW
While polling, the card shows an amber pulse dot + "waiting for payment…". Good. But if the user
closes the checkout tab without paying, the console has no idea — it keeps saying "waiting" until
the 15-min timeout. There's no "still waiting — finished in the other tab? it can take a few
seconds" reassurance, and no manual "I've paid, re-check now" button.
- **Fix:** after ~30s of waiting, soften the copy ("still waiting — payment can take a few seconds
  to confirm") and offer a manual re-check. On `payment_timeout`, render a clear recoverable state
  (see 7.x), not a dead `failed`.

### 4.4 The pay gate's `pg-nourl` "creating Checkout session…" can be a silent dead-end — MEDIUM
If `earn.checkout_url` is empty and not yet paid, the card shows a spinner "creating Checkout
session…" (`app.js:460`). But the session is created *before* the `awaiting_payment` ledger is
written (`build_runner.py:142-163`), so by the time this phase renders the URL should already
exist — meaning this spinner only appears if session creation *failed* and left no URL, in which
case it spins forever with no error. The user sees an eternal "creating session…".
- **Fix:** distinguish "no session yet" from "session creation failed"; if there's no URL after the
  awaiting_payment ledger is written, surface an actionable error, not an infinite spinner.

---

## 5. The payoff & delivery

### 5.1 There is NO way to download, share, or deliver the finished video — HIGH (this is the missing product spine)
The entire promise is "ship a finished video." At delivery the console shows the final cut in an
inline `<video controls>` (`viewer`, `app.js:320-326`) with a caption "final.mp4 · 26.8s · 4 clips ·
audio on" and the word "delivered." That's it. There is **no Download button, no copy-link, no
"send to customer," no "here's your file" moment** anywhere in `app.js` (confirmed: the only
"download/deliver" string is the literal word "delivered" in the caption). The product builds and
prices and produces a video — and then strands it inside a localhost video tag. The customer who
just "paid" cannot take their video.
- **Fix:** this is the highest-leverage product gap. Add a prominent **Download MP4** button (the
  file is already web-served at `/runs/<id>/final.mp4`), a **Copy share link**, and frame the
  delivery as an event ("Your video is ready" with the file front-and-center) rather than a quiet
  caption. For the "all-in-one producer" story, payment → gated download is the loop that closes
  it. The payoff currently has no payoff.

### 5.2 The delivery moment is anticlimactic relative to the build-up — HIGH
The live build has a dramatic arc (planning → pay → scenes popping → P&L ticking). Then
`finishBuild` (`app.js:407`) silently swaps the live view for the static post-hoc detail page —
the same dense receipt layout used for browsing old runs. There's no "done!" beat, no transition,
no celebration, no "here's what the agent made you." The emotional peak should be *delivery*; right
now delivery is the moment the UI gets *less* exciting (live energy → archival receipt).
- **Fix:** a dedicated delivered state: video hero at the top, "Your <brand> promo is ready" + the
  download/share actions + a collapsed "see how it was built (P&L, gate, code)" below. Make
  delivery feel like a reveal, not a context-switch into spreadsheet mode.

### 5.3 The final cut and the per-scene source media compete; the hero is buried — MEDIUM
In the post-hoc detail, "Final cut" is section 5 of 6 (`renderDetail` order, `app.js:96-101`),
below the P&L, the gate timeline, the Studio code view, and the source media grid. The thing the
customer actually wants — *their finished video* — is most of the way down the page. The receipt is
positioned as the headline; the deliverable is positioned as supporting evidence.
- **Fix:** for *delivered* runs, lead with the final cut. The P&L/gate/Studio are the "proof of
  craft" and belong below the video, not above it.

### 5.4 A silent video (declined VO) is delivered with no clear explanation — MEDIUM
demo-4 delivers `final.mp4` with `has_audio: false` because the voiceover was declined for being
over budget (`"VOICEOVER declined — 40c exceeds remaining 8c"`). The viewer caption says "audio
off" (`app.js:324`) — a tiny neutral note. A customer who paid for a promo and got a *silent* video
will be confused/upset, and "audio off" doesn't explain *why* or offer a remedy.
- **Fix:** when VO is declined, surface it as a prominent, explained state on the deliverable
  ("Narration was cut to stay on budget — add $X to include it?") rather than a quiet "audio off."
  This is also a control gap (see 6.x): the user should be able to top up to restore a cut element.

---

## 6. Control & iteration

### 6.1 No plan review/approval/edit before paying — HIGH
The flow is plan → price → **pay** → produce, with the storyboard shown read-only at the pay gate.
The user cannot edit the script, reorder/remove a scene, change a model, adjust the goal, or nudge
duration before committing money. For an "all-in-one producer" — and to feel in control of a
spend — a "review & approve the plan" checkpoint is the expected beat. Right now the agent decides
everything and the only human input is yes/no on payment.
- **Fix:** make the `awaiting_payment` Script panel lightly editable — at minimum let the user
  remove a scene, edit the VO text, and swap a scene's model — then re-price before they pay. Even
  an "I want changes" → re-plan affordance would transform this from "take it or leave it" into a
  collaboration.

### 6.2 No re-roll / regenerate of an individual scene — MEDIUM
If one scene comes out weak (the walkthrough is flagged as the flattest element in HANDOFF), there
is no per-scene "regenerate" or "try a different model" control in the delivered view. The user's
only recourse is to run the whole build again from scratch (new URL paste, new payment).
- **Fix:** a per-scene re-roll on the delivered storyboard/source-media cards (re-run that one
  scene, re-stitch). This is the difference between a producer *tool* and a one-shot generator.

### 6.3 No re-run / duplicate-with-tweaks from an existing run — LOW
Browsing an old run, there's no "build this again" or "use these settings for a new build" — the
user must re-type the URL and goal into the bar. The rail is read-only history.
- **Fix:** a "Rebuild / duplicate" action on each run card or in the detail header that pre-fills
  the build bar from that run's job.

### 6.4 No duration/budget/margin controls exposed at all — MEDIUM
`target_margin` (0.6) and `target_duration_s` (30) are hardcoded in `build_runner.run`
(`build_runner.py:71-72`) and never surfaced. A real buyer would want "make it shorter / cheaper /
higher-margin." The producer engine *supports* a target margin, but the UI gives no knob.
- **Fix:** expose duration (see 1.2) and at least a "draft / standard / premium" tier that maps to
  duration + budget, so the price is a lever the user can move, not a fixed output.

---

## 7. Error / edge / empty states

### 7.1 `payment_timeout` and `failed` collapse to the same bleak of a raw event string — HIGH
`liveFailed` (`app.js:630-634`) renders a red "FAILED" pill plus the *last raw event message*. For
a timeout that's "payment gate timed out after 15 min — no payment received; build cancelled"; for
a crash it's `"build failed: <exception str>"` (`build_runner.py:125`) — a Python exception leaked
to the customer. Neither offers a recovery path (retry, re-open checkout, start over). A timeout
isn't really a "failure" from the user's POV — they just didn't pay yet — but it's presented as a
hard red failure.
- **Fix:** separate the states. `payment_timeout` → a soft "Your checkout session expired — start
  again?" with a re-build button, not a red FAILED. `failed` → a friendly "Something went wrong
  producing your video — try again" with a retry, and never surface the raw exception string to the
  user (log it, show a clean message).

### 7.2 The no-runs-yet empty state is unwelcoming — MEDIUM
Covered in 1.1 from the onboarding angle; as an empty state, "Select a job from the ledger."
(`index.html:61`) with a generic card icon is the entire empty experience, and if
`/runs/index.json` fails to load the rail shows a raw "Could not load /runs/index.json — HTTP 500"
(`app.js:35`). Both are developer-facing, not user-facing.
- **Fix:** friendly empty state (1.1), and a friendly index-load error ("Couldn't reach the
  console — is the server running?") rather than the raw URL + HTTP code.

### 7.3 A transient ledger fetch failure shows "spinning up the agent…" indefinitely — MEDIUM
In `beginPoll`'s `tick`, a non-ok ledger fetch renders `liveStarting()` ("spinning up the agent…",
`app.js:392,626`). If the build process died before writing a ledger (the orchestrator import-error
case noted in the prod review), the user sees "spinning up the agent…" *forever* with no timeout
and no failure transition.
- **Fix:** a client-side watchdog — if the ledger hasn't appeared/advanced after N seconds, show a
  "this is taking longer than expected / the build may have failed — retry?" state instead of an
  eternal "spinning up."

### 7.4 The phase track silently doesn't render for older/edge ledgers — LOW
`liveHeader` builds the phase chips from `PHASES` and the ledger's `phase` (`app.js:564-575`).
demo-2/demo-4 have `phase: null`, so `PHASES.indexOf(null)` = -1 and **every chip renders as
"future"** (none "done", none "now"). These are post-hoc demos so it's mostly hidden, but any
ledger missing `phase` produces a phase track that looks stalled at the very start.
- **Fix:** default a missing/null phase to "delivered" for `status:"delivered"` ledgers so the
  track reads as complete, not stuck.

---

## 8. Visual & interaction polish

### 8.1 Strong, coherent visual language — preserve it — LOW (strength)
The edit-bay/trading-desk aesthetic (mono + serif, single amber accent, red reserved only for
declines, the receipt with perforated edges, the filmstrip gate timeline) is genuinely
distinctive and on-brief. The `rise` stagger animation on detail sections (`styles.css:140-144`),
the rAF-based time-correct typing (avoiding the setInterval throttle gotcha), and the no-emoji SVG
icon sprite are all well-executed. This is the product's biggest asset — don't dilute it.

### 8.2 Mobile/narrow collapses the rail entirely, stranding the build bar — MEDIUM
At `max-width: 940px` the rail (which *contains the NEW BUILD bar*) is `display: none`
(`styles.css:490-492`). So on a phone or narrow window the user **cannot start a build at all** —
the only entry point is hidden, and they can only view whatever run is already selected. The
two-up grids collapse nicely, but the primary action vanishes.
- **Fix:** on narrow viewports, hoist the build bar into the header or a top sheet so the core
  action survives; collapse only the *history* list, not the build entry.

### 8.3 Accessibility gaps: focus states, ARIA, color-only status — MEDIUM
- Run cards, studio tabs, the pay button, and the Build button are `<button>`s (good) but there's
  no visible focus ring styling beyond the default; keyboard users get little feedback. The
  live/connection dots and decline state are communicated largely by color (red/amber/green) with
  thin text backup — color-blind users lean on the small labels.
- The live region updates (action feed, phase track, status text) are not announced — a
  screen-reader user gets no "now producing scene 2" / "payment received" cues. No `aria-live` on
  the feed or status.
- **Fix:** explicit `:focus-visible` rings in the amber accent; `aria-live="polite"` on the action
  feed and pay status; pair every color-coded status with a text/icon token (the decline already
  has the cut icon — extend that discipline).

### 8.4 The Build button label flips "Build" → "starting…" but stays disabled through the whole build — LOW
`startBuild` sets the button to "starting…" and disabled (`app.js:365`), and it's only re-enabled
in `finishBuild` (`app.js:410`). So for the entire multi-minute build the bar's primary button sits
greyed at "starting…", which under-describes a long-running process and gives no sense that a build
is *in progress* (vs stuck starting).
- **Fix:** reflect live phase on the button or near the bar ("planning…", "awaiting payment",
  "producing 2/5…") so the bar's state tracks the build, and consider keeping it actionable as a
  Cancel (ties to 4.2).

### 8.5 Tiny tabular figures are great; the 64px margin number competes with the deliverable — LOW
The P&L `margin-fig` is 64px (`styles.css:192`) and the pay-gate price is 58px
(`styles.css:456`) — both are bigger than anything related to the *video itself*, reinforcing that
the UI treats the economics as the hero and the video as a footnote (see 5.3).
- **Fix:** rebalance type scale on the delivered view so the video/CTA is the largest element.

---

## 9. Cohesion as ONE product

### 9.1 It reads as two products bolted together: a live builder and a post-hoc receipt browser — HIGH
The live build view (`renderLive`: header, agent pane, script, storyboard, ticker) and the post-hoc
detail view (`renderDetail`: slate, P&L, gate, studio, source media, viewer, money log) are almost
entirely separate code paths and *visual layouts* sharing only section-label styling. When a build
finishes, the user is yanked from one design language into another (5.2). The "all-in-one" feeling
breaks at exactly the moment it should pay off — the live drama and the finished artifact live in
different rooms.
- **Fix:** unify the delivered state so the live storyboard *becomes* the finished gallery in
  place (cards fill with final clips, the ticker freezes into the P&L, the final cut rises to the
  top) rather than navigating to a different page. One continuous surface from paste to payoff.

### 9.2 Naming drift: "Producer Console" / "job ledger" / "takes" / "JOB LEDGER" vs the user's mental model — MEDIUM
The rail title is "JOB LEDGER" (`index.html:51`) with a count of "takes" (`app.js:49`), runs are
"jobs," the header says "PRODUCER CONSOLE." This is internal/film-production framing. A first-time
buyer thinks "my videos," "my projects" — not "takes" or "the ledger." The vocabulary is
atmospheric (and part of the charm) but it adds a translation step for a newcomer.
- **Fix:** keep the aesthetic flavor but make at least the primary nouns legible — "Your videos"
  or "Builds" for the rail, and reserve "ledger/takes" for the on-theme accents. The brand voice
  shouldn't cost comprehension at the top level.

### 9.3 The "all-in-one, no terminal" promise has visible seams — MEDIUM
The pay-gate note tells the user the webhook is "pending `stripe login`" and shows a literal
`<code>stripe login</code>` (`app.js:475`) — a setup command leaking into the customer UI. The
mock checkbox is labeled "mock (dev · $0)" — dev terminology in the primary action area. These are
honest dev affordances, but they puncture the "polished single product" surface for a first-time
viewer.
- **Fix:** move dev/diagnostic copy (webhook status, `stripe login`, "dev · $0") out of the
  primary customer surface into a collapsed "diagnostics" or behind a dev flag. The customer-facing
  console should never mention a CLI command it expects them not to run.

---

## TOP 7 UX WINS (ordered by impact-vs-effort)

1. **Add a Download / Share button on the finished video (§5.1).** HIGH impact, LOW effort — the
   file is already served at `/runs/<id>/final.mp4`; this is one button. It closes the core product
   loop ("ship a finished video") that is currently open. Nothing else matters as much.

2. **Make delivery a reveal, lead with the video (§5.2, §5.3, §9.1).** HIGH impact, MEDIUM effort —
   a dedicated delivered state with the final cut at the top, "Your <brand> promo is ready," and the
   download/share actions, with P&L/gate/code collapsed below as proof-of-craft. Turns the
   anticlimax into the payoff and unifies the live→done seam.

3. **Cover the planning dead-air + add a cancel (§2.1, §4.2, §8.4).** HIGH impact, MEDIUM effort —
   stream scripted planning events + a skeleton shot list during the ~90s wait, show "N of M"
   progress, and add a Cancel/Start-over so the user is never trapped (especially at the pay gate).
   Removes the two worst "is this hung?" moments.

4. **Fix the first-run screen: product framing + a price/duration anchor in the input (§1.1, §1.2,
   §1.3).** HIGH impact, MEDIUM effort — a one-line value prop + example chips + a duration selector
   + a ballpark price range so a newcomer knows what they're getting and what it costs *before* they
   commit. Currently they know neither.

5. **Resolve the sub-dollar price credibility problem (§3.1).** HIGH impact, LOW-MEDIUM effort
   (mostly a decision + a config) — either price the demo in realistic dollars or explicitly frame
   the cents figure as unit-economics, not a retail price. The current "$0.92 for an agency-grade
   promo" silently undermines the whole trust story.

6. **Add a plan-review/approve step before payment (§6.1).** HIGH impact, MEDIUM-HIGH effort — let
   the user edit the VO, drop/reorder a scene, or swap a model and re-price before paying. This is
   what makes it a *producer you direct* rather than a vending machine, and it's the strongest
   answer to "all-in-one."

7. **Clean up the leaks: internal jargon, dev copy, raw errors (§3.3, §7.1, §9.3).** MEDIUM impact,
   LOW effort — stop surfacing "MONEY-SHOT", `PRODUCER_SIMULATE_PAID`, `stripe login`, and raw
   Python exception strings in the customer-facing feed/error states; show clean producer-voice
   copy instead. Cheap polish that materially raises the "this is a finished product" read.

---

_Strengths to protect: the distinctive edit-bay visual language and the disciplined no-emoji SVG
system (§8.1); the honest TEST-MODE / simulated-decline transparency (§3.2); the genuinely
compelling "watch the agent write its own Remotion" Studio beat; and the rAF-correct typing that
survives background throttling. The work here is almost entirely about closing the product loop
(deliver the video), filling the pacing gaps, and giving the user a seat in the director's chair —
not about the craft of what's already on screen._
