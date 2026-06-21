# Hera → Hermes: Motion-Craft Learnings

_Read-only research + proposal, 2026-06-20. No code was changed. Scope: study **Hera**
(hera.video / app.hera.video) — an AI motion-graphics app — and map its motion craft and product
ideas onto our agent's video-generation surfaces (`remotion_codegen.py`, the dashboard, the agent
loop). This document **proposes**; it does not implement. Dennis picks what to apply._

Sources are public only — `app.hera.video` is auth-gated, so the app's internals were inferred from
the marketing site, Product Hunt, and hands-on third-party reviews. Confidence is flagged per claim.
A logged-in walkthrough would materially sharpen §2 and §3 (see §6).

---

## 0. The strategic punchline (read this first)

**Hera and Hermes already share the same core thesis, and that is the win, not a gap to close.**
Hera's entire pitch is: *"not a video generator — code-based animations where every parameter can be
fine-tuned"* (Product Hunt, ChatGate; **CONFIRMED** — their explicit positioning). That is exactly
what `remotion_codegen.py` does: the agent writes real, deterministic, editable TSX instead of
hallucinating pixels. **We don't need to copy Hera's architecture — we already have the better version
of it for a hackathon (the agent authors the code live, on camera).** What we should borrow is Hera's
*motion-craft polish* and a couple of product ideas, applied surgically to the scenes that currently
hold our cut at "B+" (per `VIDEO-GENERATION-REVIEW.md` §4).

The trap to avoid: a coherence review already warned that over-polishing the tool competes with the
#1 priority — *making the Hermes agent visibly drive the run* (submission due 2026-06-30). So every
learning below is flagged **GENERATION-QUALITY** (improves the produced video → directly helps win) vs
**PURE POLISH** (nice, but pulls effort from the agent-on-camera story), with an honest effort/ROI read.

---

## 1. What Hera does exceptionally well

**Motion craft (their output):**
- **Code-based, parameter-editable motion** — animations are structured layers (CSS/JS/JSON), not
  rendered pixels, so easing, timing, delays, colors, motion paths are all tweakable after generation.
  This is the source of their polish: clean vector type, no garble, crisp at 4K. (**CONFIRMED**.)
- **Animated data-viz as a first-class citizen** — rising line charts with dots and fade-in labels,
  animated bar/pie charts, maps, infographics. A reviewer specifically built "a rising line chart with
  dots and fade-in labels" and it worked. (**CONFIRMED** — repeated across reviews.)
- **Kinetic typography + lower-thirds + logo reveals** as named, repeatable formats. (**CONFIRMED**.)
- **Brand consistency baked in** — Brand Kits (colors, fonts, logo) auto-applied across every template
  so output is on-brand by default, with a "design agent" that auto-adapts elements to the brand.
  (**CONFIRMED**.)
- **Transparent/alpha export (MOV + Lottie)** so a motion graphic can be composited *over* other
  footage as an overlay, not just delivered as a standalone clip. (**CONFIRMED** — reviewer tested
  transparent MOV "composited cleanly").

**Product / UX:**
- **Text-prompt → several animated variations in ~5-10s**, with a **real-time preview** that reflects
  color/timing tweaks "almost instantly" — no long render wait. (**CONFIRMED**.)
- **Timeline editor + layers** for sequencing/timing on top of the prompt flow (a familiar NLE mental
  model), plus a **100+ remixable template library** keyed by format (logo, chart, social, lower-third).
  (**CONFIRMED**.)
- **Fast, structured-communication use cases**: product-launch video, animated chart, UI explainer,
  social cutdown, sales recap — i.e. exactly the "agency promo + explainer" lane Hermes targets.
- **Speed-as-the-headline**: "5-hour projects into 5-minute tasks", "polished promo in ~15 min".

**Honest counterweight (so we don't over-index):** a hands-on reviewer found prompt-to-edit
**unreliable** ("zoom and highlight" prompts had "no impact"; had to fall back to an "Enhance"
button) and judged the output "volume over distinctiveness… not the best choice for a competitive
space requiring standout graphics." (**CONFIRMED** — Hamza Iqbal / Medium.) Translation: their
*template polish is high, their bespoke-art-direction ceiling is lower*. For a hackathon submission
video — a bespoke, art-directed piece Dennis cuts by hand — we want their polish floor, not their
prompt-it-and-ship ceiling.

---

## 2. How they (apparently) built it

| Claim | Confidence | Basis |
|---|---|---|
| Code-based motion graphics, not pixel video-gen | **CONFIRMED** | Their own headline positioning (Product Hunt, ChatGate, blog) |
| Output is structured editable layers (CSS / JS / JSON) | **HIGH inference** | ChatGate "editable code layers (CSS/JavaScript/JSON)"; not from Hera's own docs |
| Lottie JSON is one export target | **HIGH inference** | Multiple secondary sources; consistent with "transparent overlay" claim |
| Web-runtime renderer (browser-rendered animation, real-time preview) | **HIGH inference** | "instant preview", CSS/JS layers, browser-class export all point to a DOM/Canvas/WebGL web renderer |
| AI generates the animation spec, then a deterministic engine renders it | **HIGH inference** | "several variations in seconds" + "every parameter editable after" = LLM emits a structured scene/animation spec, engine renders it (same shape as our codegen→Remotion split) |
| Easing/timing/delay are exposed numeric params | **CONFIRMED** | "adjust easing, timings, delays, transitions"; "fine-grain control" |
| Brand Kit = stored colors/fonts/logo applied via the engine's theming | **CONFIRMED** | Marketing + reviews |
| 4K MP4 / GIF / transparent MOV export | **CONFIRMED** | Review tested transparent MOV |
| Founders: Peter (Economics Explained, 100M+ views) + Chia (built Vyond Studio, 20k+ businesses) | **CONFIRMED** | Product Hunt |

**Net read:** Hera is, architecturally, a hosted, brand-kit-aware, template-library version of *our*
`remotion_codegen → studio render` split, with a web-runtime renderer (likely DOM/Canvas + Lottie
export) instead of Remotion, and an AI layer that emits an editable animation spec. We are not behind
them on the core idea. We are behind them on **(a) motion-craft polish of the authored scenes,
(b) data-viz/kinetic-type variety, and (c) brand-font/logo fidelity** — all things our own
`VIDEO-GENERATION-REVIEW.md` §4 already flagged independently.

---

## 3. Concrete, prioritized learnings → mapped to our files

Each is written as **Hera does X → apply to [file] by doing Y**, with a win-alignment flag and an
honest effort/ROI read against the June 30 deadline.

### L1 — Brand fonts + brand logo, not Helvetica wordmarks
**Hera does:** Brand Kit auto-applies the brand's real fonts and logo to every template; output reads
*as that brand*.
**Apply to `remotion_codegen.py`:** the header hardcodes `fontFamily: "Helvetica, Arial, sans-serif"`
in all four templates (lines ~117/149/184/209), and the "logo" is the brand name set in Helvetica.
Add a `font` field to `BRAND_PALETTES` (e.g. Stripe→sohne/Inter, Linear→Inter Display, Notion→Inter,
Vercel→Geist/Inter) and load it via Remotion `@remotion/google-fonts` or a bundled `loadFont`; inject
`${FONT}` into the header. For the open/close card, drop in the brand's real SVG logo lockup (fetch
favicon/SVG once at plan time) instead of set type.
**Win flag: GENERATION-QUALITY (high).** This is the single most "this is a template" tell in the
authored scenes, and it's the same call as `VIDEO-GENERATION-REVIEW.md` §4 + Top-Win #6.
**Effort/ROI:** Font swap is ~1-2h and high-visibility. Per-brand SVG-logo fetch+lockup is ~half a day
(network fetch, sizing, fallback) — do the font now; logo lockup only if time allows.

### L2 — Keep one element in continuous motion through the hold (no dead slides)
**Hera does:** its animations *read as motion graphics*, not slides — there's continuous secondary
motion, not a 1s entrance then a frozen frame.
**Apply to `remotion_codegen.py`:** every template animates in over ~1s (spring + linear `ease`) then
**holds a static frame** for the remaining 2-4s (`VIDEO-GENERATION-REVIEW.md` §4 "still frame after a
~1s entrance"). Add a cheap continuous driver to each archetype: a slow background gradient drift
(`backgroundPosition` interpolated over the full duration), a low-opacity drifting brand glyph, the
accent rule with a subtle shimmer, or a 1.0→1.03 ambient scale on the whole composition. One extra
`interpolate` keyed to `frame` over `[0, durationInFrames]` per template.
**Win flag: GENERATION-QUALITY (high).** Turns "good slides" into "title sequence" — the §7 art-
direction gap.
**Effort/ROI:** ~2-3h for all three archetypes. Very high ROI; the difference is immediately visible.

### L3 — Animated background texture (the difference between a slide and a title card)
**Hera does:** polished, layered backgrounds (gradients, depth), not flat color fields.
**Apply to `remotion_codegen.py`:** the cards are ~70% flat color with text in one corner
(`VIDEO-GENERATION-REVIEW.md` §4 "vast dead negative space"). Add a reusable animated-background
block to `_HEADER`: a large soft radial/linear gradient using `${ACCENT}`/`${ACCENT2}` at low opacity,
optionally a faint grain overlay (CSS `backgroundImage` data-URI noise) and one drifting blurred blob.
Keep it subtle and brand-colored.
**Win flag: GENERATION-QUALITY (medium-high).** Pairs with L2.
**Effort/ROI:** ~2-3h. High ROI, low risk (purely additive, can't break compile).

### L4 — Animated data-viz / stat card as a fourth archetype
**Hera does:** animated charts are a flagship feature — rising line chart, dots, fade-in labels;
animated bars/pies; the most "produced-looking" thing they make.
**Apply to `remotion_codegen.py` + the planner:** today `motion_graphic` collapses to the `divider`
archetype (number badge + hairline + one line — `VIDEO-GENERATION-REVIEW.md` §4 "thin variety"). Add a
**`stat`/`chart` archetype**: a count-up number (interpolated 0→value), a bar/line that grows with a
spring, fade-in labels staggered by index. Have the planner optionally emit a `metric` (`{label,
value, unit}`) on a motion-graphic scene so the agent can drop a real proof-point beat ("99.99% uptime",
"2M+ developers"). This is also a *demo-able agent capability* ("the agent decided to add a stat beat").
**Win flag: GENERATION-QUALITY (high) AND demo-narrative.** Directly fills the §10 "data viz / animated
stat cards" gap and gives the agent a visibly smarter authoring choice on camera.
**Effort/ROI:** ~half a day (new template + small planner-schema field + `_copy_from_brief` branch).
High ROI — it's both better video *and* a better agent story. Strongest candidate after L1/L2.

### L5 — Richer, varied motion vocabulary (stagger-by-letter, overshoot, blur-in)
**Hera does:** kinetic typography with per-element timing/easing; varied entrances, not one move.
**Apply to `remotion_codegen.py`:** every scene uses the same rise/sweep/pop with one spring config and
linear `ease` (`VIDEO-GENERATION-REVIEW.md` §4 "one spring + linear ease"). Borrow from the Zelios/Jitter
animation vocab already in memory: a word-by-word or letter-by-letter staggered title build (map over
split text with per-index `ease` delays), an overshoot spring (`damping` ~12-18) on the badge/logo, a
blur-in (`filter: blur()` interpolated to 0) on the title. Pick a different entrance per archetype so
two scenes don't feel identical.
**Win flag: GENERATION-QUALITY (medium).** Adds craft variety; less visible per-unit than L1-L4.
**Effort/ROI:** ~3-4h. Medium ROI — do the staggered title build (cheap, high payoff) and skip the
rest under time pressure.

### L6 — Varied, intentional transitions (not one uniform dissolve)
**Hera does:** named transitions between scenes as a designed choice.
**Apply to `finish_cut.py`:** every cut is the same 0.45s `xfade=fade` ("slideshow", not "edit" —
`VIDEO-GENERATION-REVIEW.md` §6). Vary transition by boundary type: hard cut into the cinematic
(energy), dissolve out of it, dip-to-brand-color between acts. A small `transition_for(prev_type,
next_type)` lookup.
**Win flag: PURE POLISH (low-medium).** Real but subtle; not where the demo is won.
**Effort/ROI:** ~2-3h in ffmpeg, fiddly to get right. Low priority before the deadline.

### L7 — Real-time preview / "watch it render" feel in the dashboard
**Hera does:** instant preview; tweaks reflect "almost instantly" — the app *feels* live and fast.
**Apply to `dashboard/`:** the Producer Console already has good live motion (cubic-bezier `rise`
stagger, `pulse`/`blink` cursor, rAF-typed code) — this is genuinely close to Hera's feel already.
The cheap borrow: when a scene finishes rendering, **show the actual generated clip frame popping into
the storyboard tile** with the same `rise` stagger (a "preview just rendered" beat), reinforcing the
agent-is-producing story. Don't rebuild the timeline as an editor — that's scope we don't need.
**Win flag: GENERATION-QUALITY-adjacent / demo-narrative (medium).** Helps the *submission video's*
centerpiece (agent building live), not the produced promo itself.
**Effort/ROI:** ~2-4h if thumbnails aren't already wired per-scene. Medium ROI for the demo; verify
it isn't already done before spending time.

### L8 — Alpha/overlay output as a capability the agent can use internally
**Hera does:** transparent MOV/Lottie export so motion graphics composite over footage.
**Apply to the agent loop / `finish_cut.py`:** the real value here isn't an export *format* for the
user — it's that **authored Remotion scenes could be rendered with alpha and composited as
lower-thirds/callouts over the walkthrough and cinematic**, which `VIDEO-GENERATION-REVIEW.md` §3/§10
flags as missing (brand-styled lower-thirds over the walkthrough; on-screen text over the cinematic to
fix the GPT-Image-2 garble). Render a small Remotion "callout" comp with `--codec=prores -pix_fmt
yuva444p10le` (alpha) and `ffmpeg overlay` it onto the screen-capture/cinematic clips.
**Win flag: GENERATION-QUALITY (medium-high).** Fixes two named §3/§10 gaps at once (callouts +
cinematic text), and shows the agent doing real compositing.
**Effort/ROI:** ~half a day (alpha render path + overlay filter). Good ROI but more moving parts than
L1-L4; second tier.

---

## 4. Win-alignment summary (effort/ROI before June 30)

| # | Learning | File | Win flag | Effort | ROI |
|---|---|---|---|---|---|
| L1 | Brand font (+ logo) | `remotion_codegen.py` | **GEN-QUALITY** | font ~1-2h / logo ~½d | **Very high** (font) |
| L2 | Continuous motion on hold | `remotion_codegen.py` | **GEN-QUALITY** | ~2-3h | **Very high** |
| L3 | Animated bg texture | `remotion_codegen.py` | **GEN-QUALITY** | ~2-3h | High |
| L4 | Stat/chart archetype | `remotion_codegen.py` + planner | **GEN-QUALITY + demo** | ~½d | **High** |
| L5 | Varied motion vocab | `remotion_codegen.py` | GEN-QUALITY | ~3-4h | Medium |
| L6 | Varied transitions | `finish_cut.py` | PURE POLISH | ~2-3h | Low |
| L7 | Live "preview rendered" beat | `dashboard/` | demo-narrative | ~2-4h | Medium |
| L8 | Alpha overlay → callouts | agent / `finish_cut.py` | GEN-QUALITY | ~½d | Med-high |

**Do-now shortlist (best video-per-hour, all aligned with winning):** L2 + L3 + L1(font) together are a
single ~1-day art-direction pass on `remotion_codegen.py` that converts the templated title cards from
"good slides" to "title sequence" — the exact §4/§7 gap. L4 is the strongest single *new* feature
because it improves the video **and** the agent-decision story. Defer L5/L6/L7/L8 unless the cut is
locked early.

**The over-polish guardrail (honor it):** none of L1-L8 should come before the submission demo itself
(the agent visibly driving the pay-gate + auto-decline + live-codegen run — HANDOFF NEXT #5). If
forced to choose, ship the agent-on-camera story first; apply the L2+L3+L1 art-direction pass to the
hero cut only if there's a clear day to spare.

---

## 5. The single highest-ROI thing to adopt

**The L2+L3+L1(font) art-direction pass on `remotion_codegen.py`** — one focused day that gives the
three authored archetypes (1) a brand webfont, (2) a subtle animated brand-colored background, and
(3) one element in continuous slow motion through the hold. It is purely additive (can't break the
compile-and-render path), it directly closes the §4/§7 "good slides, not a title sequence" gap that is
explicitly holding the cut at B+, and it's the cheapest way to make the agent's *own authored output*
look like Hera-grade motion graphics rather than templates. If only one thing ships, ship this.

If a *second* thing ships, make it **L4 (the stat/chart archetype)** — it's the one item that improves
the produced video and gives the Hermes agent a visibly smarter authoring decision to show on camera,
so it pays into both the quality axis and the win-the-hackathon axis.

---

## 6. What a logged-in walkthrough would add (and what I couldn't see)

`app.hera.video` is auth-gated; all of the above is from the public marketing surface + third-party
reviews, so the §2 "how they built it" rows marked **HIGH inference** are educated guesses, not
confirmed. A 15-minute logged-in pass (Dennis + Chrome MCP) would materially sharpen this proposal by
letting me see things the marketing copy can't show:

- **The actual easing/timing UI** — are easings named presets, bezier handles, or numeric fields? This
  tells us how granular to make our own params (relevant to L5).
- **The real motion feel** — frame-step a generated title/chart to read their default spring stiffness,
  stagger intervals, blur-in usage, and secondary motion. This would let L2/L5 *match a known-good
  reference* instead of guessing.
- **Their data-viz defaults** — exact chart entrance choreography (do bars grow then labels fade, what
  delays?), which is the spec we'd want to mirror for L4.
- **Brand Kit application** — how font/logo/color propagate, and whether they do logo lockups (informs
  the L1 logo half).
- **Transition catalog** — the named set, to pick the 2-3 worth porting in L6.
- **DevTools network/DOM peek** — would confirm/deny the CSS-JS-JSON/Lottie/WebGL inference in §2 (e.g.
  a `.lottie`/`lottie-web` asset, a `<canvas>`, or DOM-animated nodes in the preview).

None of this changes the *recommendations* (L1-L4 stand on our own review's findings), but it would
upgrade the §2 confidence flags and give L2/L4/L5 concrete reference numbers to copy instead of
reasonable defaults.

---

## Sources
- Product Hunt — Hera: Your AI Motion Designer: https://www.producthunt.com/products/hera-6
- ChatGate — Hera: Code-Based AI Motion Graphics in Seconds: https://chatgate.ai/post/hera-ai-motion-designer
- websites2know — Hera.video Review 2025: https://websites2know.com/hera-video-review/
- Medium (Data Science Collective) — Hera: Build Motion Graphics with AI: https://medium.com/data-science-collective/hera-build-motion-graphics-with-ai-ffee1fac66c7
- Medium (Hamza Iqbal) — I tried Hera AI (hands-on review): https://medium.com/@hamzaiqbal1327/i-tried-hera-ai-to-create-motion-graphics-worth-it-or-not-1a62db566151
- MOGE — Hera Video product profile: https://moge.ai/product/hera-video
- Tech Pilot — Hera AI Motion Graphics: https://techpilot.ai/tools/hera-video-ai-motion-graphics/
- Hera blog — Hera vs After Effects: https://hera.video/blog/hera-vs-after-effects-creators-dont-need-pro-animation

_Internal cross-refs: `VIDEO-GENERATION-REVIEW.md` §4 (templated authored scenes), §7 (art-direction
gap), §10 (missing data-viz / logo / lower-thirds), Top-Win #6; `remotion_codegen.py` (the four
templates + `BRAND_PALETTES`); `dashboard/styles.css` (existing live motion); `HANDOFF.md` NEXT #5
(the submission demo is the priority)._
