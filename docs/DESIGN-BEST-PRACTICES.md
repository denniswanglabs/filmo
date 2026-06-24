# Walk Studio — Design Best-Practices Reference

_Last updated 2026-06-25. The bar every UI surface and every produced video must clear._

This is a **checkable** standard, not a mood board. Every rule has a number, a ratio, a
frame count, or a cubic-bezier. A builder or a judge should be able to hold a screen or a
video frame up to it and say pass / fail. Where a rule maps to a token already in the
codebase (`dashboard/styles.css`, the Remotion themes), the token name is given so you
change one place, not fifty.

## Two surfaces, two palettes — do not confuse them

Walk Studio has **two** visual products and they are deliberately different:

| Surface | Theme | Source of truth | Accent |
|---|---|---|---|
| **Producer Console** (the hosted dashboard) | **Light**, paper-cool, editorial | `dashboard/styles.css` `:root` | coral `#D6351C` |
| **Produced video output** (the ~30s promos) | **Dark or brand-driven** | Remotion `theme.ts` per style | brand's real colors |

> The product UI is light. The videos are not. A reviewer who pastes "dark theme" rules
> onto the console, or "white-bg" rules onto a JGB-cinematic render, is reviewing the wrong
> surface. Always name which surface you are judging first.

The console's locked token system (read these as the canonical values):

```
--bg     #F4F5F7   page canvas      --ink    #14171C   primary text  (AAA on white)
--bg-1   #FFFFFF   card surface      --ink-2  #3D4654   secondary text
--bg-2   #F7F8FA   recessed well     --ink-3  #6B7686   tertiary / labels
--bg-3   #EEF0F4   deepest recess    --ink-4  #98A1B0   placeholder / ticks
--line   #E4E7EC   hairline          --amber  #D6351C   PRIMARY ACCENT (coral)
--line-2 #D5DAE2   control outline   --pos    #0E9F6E   approve / profit (green)
--video-bg #0C0E12 video chrome      --neg    #C01A2B   DECLINE only (deep crimson)
fonts: --mono "Hanken Grotesk"  ·  --serif "Newsreader"  ·  --code ui-monospace
radii: --r-ctl 11px · --r-card 15px · --r-pill 999px
ease:  --ease-rise cubic-bezier(.2,.7,.2,1) · --ease-spring cubic-bezier(.34,1.4,.64,1)
```

---

# PART A — UI/UX (the Producer Console)

## A1. Visual hierarchy & the 5-second read

The console's job is to make a complex agent run legible at a glance: someone lands on a
run and must understand _what the agent is doing and whether it's making money_ in **5
seconds**. That is the same 5-second-clarity test landing pages use — apply it to every
view. ([CXL](https://cxl.com/blog/how-to-build-a-high-converting-landing-page/))

Rules:
- **One primary object per view.** The cockpit's primary object is the live storyboard +
  P&L ticker; everything else (rail, log) is secondary. If two things compete for "biggest
  + boldest," you have no hierarchy.
- **F-pattern placement.** Eyes scan top-left → top-right → down-left. Put the most
  important number (margin / phase) **top-left**, secondary KPIs top-right, the activity
  log down the left, supporting breakdowns right. ([Improvado](https://improvado.io/blog/dashboard-design-guide))
- **3 levels of text weight, max, per card.** Title (`--ink`, 600), value, caption
  (`--ink-3`). The token ramp `--ink → --ink-2 → --ink-3 → --ink-4` _is_ the hierarchy —
  use the ramp, don't invent greys.
- **Working-memory cap: 5–9 elements per zone; never >12 KPIs in view.** Dashboards over
  12 KPIs show a ~40% engagement drop. ([Brand.dev](https://www.brand.dev/blog/dashboard-design-best-practices))
- **Size ratio for emphasis ≥ 1.5×.** A "primary" number must be at least 1.5× the body
  size or it doesn't read as primary (the console hero greet is `clamp(36px,5vw,50px)` vs
  13px body — a deliberate ~3× jump).

## A2. Type scale & pairing

- **Use a fixed modular scale, not arbitrary px.** Major-Third (1.25) or Minor-Third
  (1.2) keeps hierarchy harmonious. The console's effective ramp:
  `11 → 12 → 13(body) → 16 → 20 → ~32 → 50`. Stay on the ramp. ([DesignSystems.com](https://www.designsystems.com/space-grids-and-layouts/))
- **Body 13px / line-height 1.35–1.5.** Console body is 13px @ 1.35 for dense UI; long-form
  reading text gets 1.5–1.6. Never set body below 12px.
- **Pairing = one workhorse sans + one accent serif.** Hanken Grotesk (`--mono`, the UI
  workhorse — note: despite the name it is sans) + Newsreader (`--serif`, for the hero
  greeting and editorial moments). Two families, clear roles. Don't add a third.
- **Letter-spacing by size:** tighten display (`-1px` at 50px), open small uppercase labels
  (`+1.5px` to `+1.6px` at 9.5–11px). The console already does both — match it.
- **Line length 45–75 characters** for any paragraph. Past ~80 chars reading speed drops.
  ([NN/g](https://www.nngroup.com/articles/legibility-readability-comprehension/))

## A3. Spacing & rhythm — 8pt grid

- **Everything is a multiple of 4, default 8.** Spacing scale: `4, 8, 12, 16, 24, 32, 48`.
  Use 4 only for tight intra-component gaps. Most padding/margin is 8/16/24. ([Rejuvenate](https://www.rejuvenate.digital/news/designing-rhythm-power-8pt-grid-ui-design))
- **Internal ≤ external.** The space _around_ a group must be ≥ the space _inside_ it, or
  groups bleed together. A card's outer margin (e.g. 24) ≥ its inner padding (e.g. 16). ([Cieden](https://cieden.com/book/sub-atomic/spacing/spacing-best-practices))
- **Radius ladder, three rungs:** controls `--r-ctl 11px`, cards `--r-card 15px`, pills
  `--r-pill 999px`. Nothing in between. A button inside a card uses 11 inside 15 — child
  radius < parent radius always (or the corners look wrong).
- **8pt frees you from the 13px-vs-15px debate** — that's the point. Narrow choices, spend
  the saved decisions on hierarchy.

## A4. Color & contrast (WCAG)

Targets, non-negotiable on the console:
- **Body text ≥ 4.5:1 (AA), aim 7:1 (AAA).** `--ink #14171C` on `#FFFFFF` ≈ 16:1 — AAA,
  good. Don't drop body text below `--ink-2 #3D4654` (still ~9:1). `--ink-3` and `--ink-4`
  are **labels/placeholders only**, never body copy. ([W3C WCAG 2.2](https://www.w3.org/TR/WCAG22/))
- **Large text (≥24px, or ≥19px bold) ≥ 3:1 (AA).** ([Make Things Accessible](https://www.makethingsaccessible.com/guides/contrast-requirements-for-wcag-2-2-level-aa/))
- **UI components & graphics ≥ 3:1** — borders, input outlines, chart strokes, focus rings,
  icons. `--line-2 #D5DAE2` on white is borderline (~1.3:1) so it is decorative only;
  any **functional** control outline must hit 3:1. ([Deque](https://dequeuniversity.com/rules/axe/4.8/color-contrast))
- **Text on the coral fill:** `--on-accent #FFFFFF` on `--amber #D6351C` ≈ 4.6:1 — passes AA
  for normal text (it's deliberately deepened to clear it). Don't lighten the coral without
  re-checking.
- **Never carry meaning by color alone.** Approve/decline must also differ by icon, label,
  or position — colorblind users and grayscale screenshots must still parse it.
- **Status semantics, locked:** green `--pos` = approve/profit, crimson `--neg` = **decline
  only**. Coral `--amber` is brand/primary-action, _not_ "error." Keep these disjoint.

## A5. Microinteractions & state feedback

- **Every interactive element has 5 states:** default, hover, active/pressed, focus-visible,
  disabled. Missing any one is a bug.
- **Focus ring is mandatory and visible.** `--focus-ring 0 0 0 3px rgba(214,53,28,.22)` —
  3px, hugs the edge, ≥3:1 against the background. Never `outline:none` without a replacement.
- **Feedback within 100ms.** A click must show _something_ (press, ripple, spinner) inside
  100ms or it feels broken — that's the human "instantaneous" threshold.
- **Transition durations:** micro/hover **120–150ms**, standard state change **200–250ms**,
  layout/disclosure **≤300ms**. The console uses `.12s` for color/border, `.15–.22s` for
  transform/layout — match those. ([Material](https://m1.material.io/motion/duration-easing.html))
- **Tap-feedback shape matches the control:** pill ring on wide buttons, circle on icon
  chips. A generic circle on a wide button overflows — banned (codebase lesson).
- **Loading → revert pattern for actions:** tap → loading ~1.5s → revert to default state →
  next action. The revert _is_ the "done" beat; don't leave a button stuck in loading.

## A6. Loading, empty, and error states — design all three

A view is not done until empty/loading/error are designed. Defaults:
- **Empty state = the onboarding moment.** Open on the empty/upload state, hold ~1s, then
  drop the first content in (~1s, delayed spring so the hold reads). One sentence of what
  goes here + one primary action. Never a blank panel.
- **Loading:** skeletons that match final layout (not spinners) for content; a determinate
  bar or phase-chip for known-length work (the console's `planning→pricing→producing→
  delivered` phase chips are the model). The live ledger polls ~1s — show motion so it
  reads as alive (the `--rec-dot` pulse @ 2.4s).
- **Error:** say what failed, why, and the one next action. Use crimson `--neg` text
  (`--neg-2 #B42318` for AAA on white), never just a red border. A declined budget-gate
  scene is an _expected_ state, not an error — style it as a decision (the money-shot),
  distinct from a crash.

## A7. Dashboard / data-viz patterns (the cockpit + P&L)

- **KPI cards = big bold number + tiny context.** Each metric card: the value (large),
  a label, and one comparison/trend (delta, sparkline). The P&L ticker is exactly this —
  price, budget, margin, each with its sign and direction. ([DataCamp](https://www.datacamp.com/tutorial/dashboard-design-tutorial))
- **Match chart to task:** bar = compare, line = trend over time, the 6-dimension
  Conversion Read = a **radar/spider or a labeled bar set**, never a pie (pies fail at >5
  slices and at comparison). Six labeled bars with a shared 0–100 axis beat a radar for
  _legibility_; use radar only if the shape itself is the message.
- **Sort by meaning, not alphabet.** Rank the 6 Conversion-Read dimensions worst-first (or
  best-first) so the eye lands on the diagnosis, not the spelling.
- **One accent, grey everything else.** In a chart, color only the series that carries the
  point (coral for the focus metric, green/crimson for pass/fail); everything else is
  `--ink-3`/`--line`. Color is a spotlight, not decoration.
- **Direct-label over legends** where space allows — a legend forces a saccade-and-match;
  a label on the line doesn't.

## A8. Conversion-oriented design (the marketing site + because the product diagnoses it)

Walk Studio's product literally scores conversion on 6 dimensions — so its own surfaces
must be exemplary. The checklist the Conversion Read should itself reward:
- **5-second clarity:** a first-time visitor can state _what it does and for whom_ after 5s.
  Headline answers "what's in it for me," not a clever pun. ([Lovable](https://lovable.dev/guides/landing-page-best-practices-convert))
- **Outcome-led, not feature-led.** "Turn any URL into a narrated product promo in minutes"
  beats "AI video pipeline with VO alignment." Quantify when you can ("47% in 60 days"
  pattern). ([FormAssembly](https://www.formassembly.com/blog/20-converting-landing-pages/))
- **Single primary CTA, repeated.** One action (Build / Try it), echoed in hero, mid-page
  after proof, and at the end. Competing CTAs split intent and cost conversions. ([InvokeMedia](https://invokemedia.co.uk/designing-focused-landing-pages-with-one-cta-boost-your-conversions))
- **Proof reduces risk:** real logos, a real produced video, a real P&L. Place proof right
  after the value prop and again before the final CTA (19–34% lift when positioned well).
- **Above the fold = headline + subhead + value + CTA**, nothing else fighting for the eye.
- **Brand promise lands on the CTA, not the landing.** The wordmark is earned by the
  landing; the slogan is earned by the CTA. A slogan on the landing reads as decoration
  (codebase lesson).

## A9. Glassmorphism (when, and how, on textured surfaces)

The "lovio glass" card recipe — use only where there's a textured/photographic backdrop
behind it (e.g. JGB-cinematic plates), never on the flat light console:
backdrop blur + low-opacity white fill + a bright 1px border + an inset top highlight.
On the flat console, fake depth with the shadow ladder instead:
`--card-shadow: 0 1px 2px rgba(20,23,28,.05), 0 8px 24px rgba(20,23,28,.05)` — a tight
contact shadow + a soft ambient one. Two-layer shadows read real; one-layer reads flat.

## A10. No emojis, ever

No emojis in UI chrome or video frames. Use numbered/letter badges or SVG icons. (Standing
rule.) Icons must clear the 3:1 non-text contrast bar like any other UI graphic.

---

# PART B — Motion graphics & video (the produced promos)

The competitor ships glossy AI-generated cinematic film. **Our edge is grounded, polished,
_legible_ real-product video** — screen-capture walkthroughs + kinetic title cards +
narration, rendered deterministically in Remotion. Legibility is the whole moat. Every rule
below protects it. All frame counts assume **30fps** unless noted; double for 60fps.

## B1. Timing & pacing budgets (the hard caps)

- **Reading time = words ÷ ~3 per second + 0.5s buffer.** On-screen text reads at ~180–220
  wpm on paper but **~110–125 wpm on screen** — budget for the screen number. Practical:
  `seconds = (characters ÷ 12) + 0.5`, round up to the nearest 0.25s. A 7-word line needs
  **1.8–2.5s** minimum on screen. ([envato/kinetic](https://elements.envato.com/learn/fast-typography-templates), [NN/g](https://www.nngroup.com/articles/legibility-readability-comprehension/))
- **Minimum on-screen for any readable text: 2s (60 frames).** Sub-second text = unreadable
  decoration. A single word can flash shorter only if it's also spoken in the VO.
- **Pacing budgets (Dennis's locked rules — keep them):**
  - **No scene > 9 seconds** (270f). Long scenes lose attention.
  - **No beat > 40 frames without motion** (~1.3s). Something must move/reveal/settle on a
    static frame within 40f or it reads as frozen.
  - **3–6 beats per scene.** Fewer = static; more = frantic.
- **Cut cadence: one visual change every 2–4s.** Each cut resets the attention span. Vary
  shot scale (close UI detail ↔ full screen) so cuts feel intentional, not metronomic.
  ([OpusClip](https://www.opus.pro/blog/youtube-shorts-hook-formulas))

## B2. Easing — never linear, curve per move

Linear motion reads robotic. Pick the curve by what the element is doing. ([Material](https://m1.material.io/motion/duration-easing.html), [animations.dev](https://animations.dev/learn/animation-theory/the-easing-blueprint))

| Move | Curve | cubic-bezier | Notes |
|---|---|---|---|
| Enter (on-screen) | **ease-out** (decelerate) | `(.2,.7,.2,1)` = `--ease-rise` | full speed in, settle. ~60% of all motion. |
| Exit (off-screen) | **ease-in** (accelerate) | `(.4,0,1,1)` | leaves fast, don't decelerate off-screen |
| Move A→B (both on-screen) | **ease-in-out / standard** | `(.4,0,.2,1)` | Material standard curve |
| Hero / money beat | **spring, slight overshoot** | `(.34,1.4,.64,1)` = `--ease-spring` | the P&L pop, a scene-card land |

- **Workhorse is ease-out** — reliable, invisible, correct. When unsure, use `--ease-rise`.
- **Springs only on emphasis** (a reveal that should feel physical). Overshoot magnitude
  small: the `1.4` control overshoots ~15–20%, not a cartoon bounce.
- **In Remotion:** `interpolate(frame,[in,out],[0,1],{easing:Easing.bezier(.2,.7,.2,1)})`
  for ease-out; `spring({fps,frame,config:{damping:14,stiffness:120}})` for the overshoot
  beats. Always pass `extrapolateLeft/Right:'clamp'` so values don't run past their range.

## B3. The 12 principles, applied to kinetic UI

Only the ones that earn their keep on product video: ([IxDF](https://ixdf.org/literature/article/ui-animation-how-to-apply-disney-s-12-principles-of-animation-to-ui-design))
- **Squash & stretch (subtle):** a card scales 0.98→1.0 on land to feel tactile. Keep ≤2%
  on UI — more looks like jelly.
- **Anticipation:** a 2–4f dip/glow before a big reveal primes the eye. A cursor moving
  _toward_ a button before the click reads as intent.
- **Staging:** dim/blur the backdrop so the eye lands where you point. One focal point per
  frame. The agent-browser pane should spotlight the clicked element, not the whole page.
- **Follow-through / overshoot:** elements pass their resting point ~15% then settle —
  that's the `--ease-spring`. Apply to hero text and the money-shot, not to body rows.
- **Slow in / slow out:** = easing. Covered in B2. Never start or stop at full velocity.
- **Secondary action:** a subtle parallax or a shadow that grows as a card rises — adds life
  without stealing focus. Keep it under the primary motion's volume.

## B4. Kinetic typography legibility (the moat)

- **Animate ≤ 3 properties at once per unit.** Position + scale + opacity is the ceiling;
  add a 4th and comprehension drops. ([envato](https://elements.envato.com/learn/fast-typography-templates))
- **Don't animate _during_ the read.** Motion finishes, _then_ the eye reads. Reveal the
  word (≤300ms), hold it still for its full reading budget (B1), then exit. Text that's
  still moving when the viewer tries to read it is the #1 legibility killer.
- **Reveal style:** prefer **fade-out → snap-reveal with a spring** over character-cycling
  / matrix glitch — glitch reads cliché (especially in CJK). (codebase lesson)
- **Displacement ≤ ~20px/frame @30fps** or motion feels "fast" and smears. ([envato](https://elements.envato.com/learn/fast-typography-templates))
- **Type for motion:** sans-serif, regular width (not condensed), generous size. Serifs and
  condensed faces smear in motion. (For Walk Studio video, the brand's display sans; the
  console's Newsreader serif stays in the _UI_, not in fast kinetic type.)
- **One idea per card.** A kinetic title card carries one phrase, not a paragraph. If it
  takes >2.5s to read, it's two cards.

## B5. Enter / emphasis / exit hierarchy

Give each element a clear lifecycle and don't blend them:
- **Enter:** ease-out, from slightly down/scaled-down + transparent → rest. ~12–20f (0.4–0.7s).
- **Emphasis** (while on screen): a pulse, glow, color shift, or a `--ease-spring` pop on
  the beat the VO stresses the word. Reserve for the _one_ thing that matters in the scene.
- **Exit:** ease-in, faster than the enter (~8–12f), often just opacity + small drift, or a
  hard cut. Don't make exits ceremonial — they steal time from the next beat.
- **Stagger groups:** when N items enter, stagger by **2–4f each** (not all at once, not
  >5f or it drags). Caps the group reveal at ~0.5s for legibility.

## B6. Scene transitions — cut is the default

- **Hard cut = default.** It's the clearest, fastest, most "real-product" transition. Use it
  for ~90% of cuts. ([Quora/editing](https://www.quora.com/When-should-you-make-a-hard-cut-and-when-a-soft-crossfade-when-video-editing))
- **Crossfade / dissolve (8–15f)** only to signal _time passing, a mood shift, or a
  connection_ between two shots. Never as a generic "I don't know how to cut" default.
- **Wipes: avoid** in product video — they read as dated/PowerPoint. (One exception: a
  deliberate branded wipe matched to a UI swipe gesture.)
- **Match-cut / UI-continuity cut:** cut on a shared shape or motion (a clicked button →
  the screen it opens) — this is the grounded-product signature; lean into it.
- **J-cut / L-cut for VO:** let the next scene's VO start ~6–12f _before_ its visual
  (J-cut), or let the prior VO trail ~6–12f _over_ the new visual (L-cut). This is what
  makes narration feel woven in rather than slide-after-slide. ([Epidemic Sound](https://www.epidemicsound.com/blog/j-cuts-and-l-cuts/))

## B7. Audio-visual sync (VO-driven timeline)

This is Walk Studio's architecture — the picture is **slaved to a word-aligned VO** so it
cannot drift (`align_vo.py` → `build_timeline.py` → `<Timeline>`). Mixing rules:
- **Reveals fire on word cues, not on the clock.** A scene's key word's `at_frame` from
  `vo_alignment.json` is when its emphasis beat lands. Land copy reveals on the stressed
  syllable.
- **Music ducking under VO:** music sits at **~-18 to -25 dB** under speech, VO is the
  loudest element. ([CyberLink](https://www.cyberlink.com/learning/powerdirector-video-editing-software/824/using-audio-ducking-to-balance-voice-overs-and-background-music))
- **Walk Studio loudness recipe (locked):** solo BGM ≈ **0.85**; BGM under VO ≈ **0.45
  ducked to 0.16** while words play, back up in the gaps. Recalibrate whenever you toggle
  VO on/off — the level depends on whether VO is present. (codebase lesson)
- **Duck has a ramp:** fade music down ~6–10f _before_ the VO word, back up ~10–15f after —
  no instant gain jumps (they pop).
- **Audio outlasts the visual fade.** On the outro: visual fades to black first, audio keeps
  fading ~15f _over_ black. Cutting audio with the picture feels abrupt. (codebase lesson)

## B8. Hook & retention structure (~30s promo)

50–60% of drop-off happens in the **first 3 seconds**; ~65% who clear 3s reach 10s.
([VirVid](https://virvid.ai/blog/first-3-seconds-hook-faceless-shorts-2026), [OpusClip](https://www.opus.pro/blog/ideal-youtube-shorts-length-format-retention))
- **Hook in 0–3s (deliver by ~2.5s).** Lead with the payoff or the sharpest claim, not a
  logo-ident crawl. The brand wordmark can wait — the hook can't.
- **Structure for ~30s:** Hook (0–3s) → Build/escalate (3s–~80%) → Payoff (last 15–25%) →
  CTA (last 3–5s). ([OpusClip](https://www.opus.pro/blog/youtube-shorts-hook-formulas))
- **CTA = one action, 3–5 words, on screen,** placed _after_ the payoff. The brand promise
  lands here (mirrors A8: slogan on the CTA, not the open).
- **A new visual every 2–4s** keeps retention — covered in B1, restated because it's the
  single biggest retention lever.
- **Open on empty/upload state → drop-in** for AI-tool reveals: show the blank state, hold
  ~1s, then the agent fills it. The contrast _is_ the hook. (codebase lesson)

## B9. Readability-in-motion & safe areas

- **Text contrast in video ≥ 4.5:1 against the _busiest_ frame it sits over**, not the
  average. Over screen-capture or photographic plates, add a scrim/blur pad behind text.
  Dark video chrome is `--video-bg #0C0E12`. ([W3C WCAG 2.2](https://www.w3.org/TR/WCAG22/))
- **Safe areas:** keep titles/CTA inside the **action-safe** region (≈5% inset all sides).
  For **vertical 1080×1920**, reserve the **top ~12%** for the notch + YouTube chrome —
  bake `TOP_SAFE_PX` into the theme; never put a reveal there. (codebase lesson)
- **Don't put readable text over high-motion video.** If the background is moving fast,
  freeze/slow it or darken it under the text. Two competing motions = neither reads.
- **Caption from the same alignment** (`vo_alignment.json`) so captions are frame-accurate
  to the VO, not eyeballed.

## B10. Determinism (Remotion discipline)

- **No `Math.random()`, no `Date.now()`, no un-seeded values** in a composition — every
  frame must be a pure function of `frame`. Re-renders must be byte-identical or the
  "fixes land in new builds, not old final.mp4" rule bites you.
- **Pin the run:** a `final.mp4` is frozen at render-time code. A fix only appears in a NEW
  build — verify against the run-id, never assume an old render reflects current code.
  (codebase lesson)
- **Judge the whole video, not one frame.** Verify a render via a ffmpeg contact sheet read
  scene-by-scene against the budgets above — cherry-picking one nice frame is how the
  "disconnect" happened. (codebase lesson)
- **Rebuild UI as native SVG/React, never paste raster screenshots** of UI into a comp —
  except the _real product screen-capture_, which is the intentional grounded footage and
  the whole point. (Distinguish: chrome/diagrams = native; the captured product = real.)

---

# Quick-check scorecards

**UI surface passes if:** one primary object · F-pattern KPI placement · ≤12 KPIs · 3 text
weights · 8pt spacing · radius ladder 11/15/999 · body ≥4.5:1 (aim 7:1) · UI strokes ≥3:1 ·
visible focus ring · all 5 control states · empty/loading/error all designed · meaning never
by color alone · no emojis.

**Video passes if:** hook lands ≤3s · readable text ≥2s (60f) · no scene >9s · no static
beat >40f · cut every 2–4s · ≤3 animated props/unit · no animation during the read · curves
not linear (ease-out default, spring on emphasis only) · cuts default, dissolve only for
time/mood · VO is loudest, music ducked to ~0.16 under words · audio outlasts visual fade ·
text ≥4.5:1 over its busiest frame · safe-area + vertical top-12% respected · deterministic
(pure-of-frame) · judged whole via contact sheet.

---

## Sources

UI/UX: [DesignSystems.com — space, grids, layouts](https://www.designsystems.com/space-grids-and-layouts/) ·
[8pt grid (Rejuvenate)](https://www.rejuvenate.digital/news/designing-rhythm-power-8pt-grid-ui-design) ·
[Spacing best practices (Cieden)](https://cieden.com/book/sub-atomic/spacing/spacing-best-practices) ·
[WCAG 2.2 (W3C)](https://www.w3.org/TR/WCAG22/) ·
[WCAG 2.2 AA contrast (Make Things Accessible)](https://www.makethingsaccessible.com/guides/contrast-requirements-for-wcag-2-2-level-aa/) ·
[Color contrast (Deque axe)](https://dequeuniversity.com/rules/axe/4.8/color-contrast) ·
[Dark theme (Material)](https://m2.material.io/design/color/dark-theme.html) ·
[Dashboard design (Improvado)](https://improvado.io/blog/dashboard-design-guide) ·
[Dashboard best practices (Brand.dev)](https://www.brand.dev/blog/dashboard-design-best-practices) ·
[Dashboard design (DataCamp)](https://www.datacamp.com/tutorial/dashboard-design-tutorial) ·
[Legibility/readability (NN/g)](https://www.nngroup.com/articles/legibility-readability-comprehension/) ·
[Landing page best practices (Lovable)](https://lovable.dev/guides/landing-page-best-practices-convert) ·
[High-converting landing pages (CXL)](https://cxl.com/blog/how-to-build-a-high-converting-landing-page/) ·
[Converting landing pages (FormAssembly)](https://www.formassembly.com/blog/20-converting-landing-pages/) ·
[Single-CTA pages (InvokeMedia)](https://invokemedia.co.uk/designing-focused-landing-pages-with-one-cta-boost-your-conversions)

Motion/video: [Duration & easing (Material)](https://m1.material.io/motion/duration-easing.html) ·
[Easing blueprint (animations.dev)](https://animations.dev/learn/animation-theory/the-easing-blueprint) ·
[12 principles for UI (IxDF)](https://ixdf.org/literature/article/ui-animation-how-to-apply-disney-s-12-principles-of-animation-to-ui-design) ·
[Kinetic typography templates (envato)](https://elements.envato.com/learn/fast-typography-templates) ·
[3-second hook (VirVid)](https://virvid.ai/blog/first-3-seconds-hook-faceless-shorts-2026) ·
[Shorts hook formulas (OpusClip)](https://www.opus.pro/blog/youtube-shorts-hook-formulas) ·
[Shorts length/retention (OpusClip)](https://www.opus.pro/blog/ideal-youtube-shorts-length-format-retention) ·
[J-cuts & L-cuts (Epidemic Sound)](https://www.epidemicsound.com/blog/j-cuts-and-l-cuts/) ·
[Audio ducking (CyberLink)](https://www.cyberlink.com/learning/powerdirector-video-editing-software/824/using-audio-ducking-to-balance-voice-overs-and-background-music)

Internal source-of-truth: `dashboard/styles.css` `:root` (token system) ·
`docs/2026-06-19-live-build-console-design.md` (console spec) ·
`docs/2026-06-21-vo-driven-style-engine-design.md` (VO-driven timeline + style-fill).
