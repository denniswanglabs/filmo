# Naming + Logo exploration — the video-production agent

> **DECISION (UPDATED 2026-06-26): the product is now `Filmo`, live at https://filmostudio.vercel.app.** (Earlier name `Walk Studio`, picked 2026-06-20, has been retired.) Mark: `branding/logo-walkstudio-{light,dark}.svg` (filenames kept for now; re-skin later). Use the `Filmo` wordmark across the dashboard header + the submission video. The rest of this doc below is the original 2026-06-20 naming exploration, preserved as historical record — names like "Walk Studio" / "Walkwright" / "Showrunner" in the tables below are the original shortlist, not the final pick.

_Overnight branding exploration, 2026-06-20. **These are OPTIONS for Dennis to pick — nothing is
finalized.** No code/dashboard/protected runs were touched; only this file + `branding/*.svg` were
created. $0, no paid APIs._

## What this product is (the brief the names have to carry)
An all-in-one AI video-production **agent**: give it a company URL + a goal, and a Hermes/Nemotron
agent **plans** a promo + walkthrough, **prices** it, **takes payment**, **auto-declines** over-budget
spend, **writes its own Remotion**, **produces** in a sandbox, and **ships** a finished on-brand video.
The thesis from `STRATEGY.md`: _"a video-production **company** in a box — a P&L on camera."_ It is a
maker and an operator, not a filter or a template. The walkthrough step is powered by Dennis's **Walk
Agent / Walk Ultra**, which is why a Walk-lineage name is on the table.

**Current dashboard identity (from `HERA-DASHBOARD-UIUX.md` + `dashboard/styles.css`):** light /
near-white canvas (`#F4F5F7` page, `#FFFFFF` cards), a single confident **coral** accent `#D6351C`
(deeper than Hera's `#FA4E3E` so it stays AA-legible), a lighter coral `#F26B52` for soft accents,
and a true **decline red** kept cooler/deeper than the coral. Mono + serif type pairing. No emoji.
(Note: "HERA" in the repo's filenames is the _external_ app `app.hera.video` that was studied for UI
craft — it is **not** a candidate name for our product. Our product is still effectively codenamed
"Hermes," which is the runtime, not a sellable brand.)

The Walk mark we're echoing (`promo-agent/docs/walkthrough-logo.svg`) is dead simple: a **click-cursor
glyph + a heavy sans wordmark with tight tracking**. Every concept below keeps that DNA — a simple
geometric glyph + a confident sans wordmark — so the new mark reads as a sibling of Walk.

---

## 1. Name shortlist (~8)

### Direction A — Walk-lineage (honors Walk Agent's role)

| Name | One-line rationale | Vibe | Collision risk (reasoned, unverified) |
|---|---|---|---|
| **Walkwright** ⭐ | "Walk" + **-wright** (a maker: playwright, shipwright, wheelwright). Literally "one who makes the walk," but expands to "a wright that makes finished work." Says **autonomy + craft** — a maker, not a tool. | Crafted, confident, a little literary; ownable. | Low. Coined compound; `walkwright.com`/`@walkwright` likely open. Distinct from "Wainwright." |
| **Walk Studio** | The safest, most literal read. Honors Walk; "Studio" states the "agency/company in a box" plainly. | Plain, trustworthy, agency. | Med-high. "Walk Studio" is a common generic phrase (fitness/dance/dev studios); exact `.com` likely taken. Defensible as a product name under the Walk family, weak as a standalone trademark. |
| **Walkshow** | Walk + **show** (the thing it produces). Compact, punchy, two strong syllables. | Energetic, product-y. | Med. Coined; `.com` plausibly gettable. Slightly opaque on first read. |
| **Walk Reel** | Walk + **reel** (the deliverable). Names the output, not the act. | Filmic, tight. | Med. "Reel" is heavily used; exact `.com` likely taken, handle crowded. |
| **Walkframe** | Walk + **frame** (a film frame). Suggests the walkthrough becoming finished footage. | Sturdy, technical. | Low-med. Coined; reasonably ownable. Reads slightly tool-ish vs studio-ish. |

### Direction B — fresh (the product essence: an agent that runs a studio — produces, prices, ships)

| Name | One-line rationale | Vibe | Collision risk (reasoned, unverified) |
|---|---|---|---|
| **Showrunner** ⭐ | A showrunner **runs the entire production AND the business** — the creative calls and the budget calls. It is the single most accurate word for "a video company that runs itself" + the P&L-on-camera thesis. | Authoritative, industry-literate, premium. | Med. Real TV term, so `showrunner.com` is likely taken and the bare word is hard to trademark broadly — but **"Showrunner AI" / `showrunner.studio` / `getshowrunner.com`** are strong, ownable lockups. (An unrelated "Showrunner" AI-TV product has existed; ours is B2B video-ops, a different lane — worth a quick check before committing.) |
| **Greenlight** | The agent **greenlights** (or declines) each scene against budget — the literal money-shot. Names the autonomous-decision beat that wins the Stripe axis. | Decisive, business-y, confident. | Med-high. Common word; `greenlight.com` taken, many SaaS uses. `greenlight.studio` / "Greenlight AI" possible but crowded. |
| **Daily** (as in "the dailies") | Film "dailies" = the footage you review each day. Short, warm, premium, easy to say. | Minimal, editorial, calm. | High. Extremely common word/brand (Robinhood's "Daily," many apps). Hard to own. Included for tone reference, not recommended. |

---

## Top recommendation (2–3)

1. **Walkwright** ⭐ (Walk-lineage pick) — the **best of both worlds**: it keeps the literal Walk
   lineage Dennis leans toward, _and_ the "-wright" suffix encodes the exact thing that makes this
   product special — it's an autonomous **maker** that produces a finished artifact, not a tool you
   operate. It's a coined compound, so it's ownable (clean `.com`/handle odds) and trademarkable in a
   way "Walk Studio" is not. Distinctive, a little premium, sits next to "Walk" as an obvious sibling.

2. **Showrunner** ⭐ (fresh pick) — if Dennis is open to leaving the Walk name behind for the product,
   this is the sharpest articulation of the thesis. A showrunner is precisely "the person who runs the
   whole show and owns the P&L," which is the demo's entire pitch. Premium and self-explanatory to any
   judge. Caveat: needs a lockup (`Showrunner Studio` / `getshowrunner`) because the bare word is a
   common industry term and an unrelated AI-TV "Showrunner" exists — worth a 2-minute name check
   before locking.

3. **Walk Studio** (safe fallback) — if Dennis wants zero risk and maximum legibility under the Walk
   umbrella. Reads instantly as "the Walk family's studio product." Weakest as a defensible standalone
   trademark, strongest as a clear product label.

**If I had to pick one for the hackathon demo:** **Walkwright** — it honors the lineage Dennis named,
it's ownable, and the "-wright = maker" story lands the autonomy thesis in a single word that a judge
gets instantly. **Showrunner** is the pick if the goal is a standalone brand beyond the Walk family.

---

## 2. Logo concepts (SVG) — one-line each

All marks: **simple geometric glyph in a rounded "app chip" + heavy sans wordmark**, echoing the Walk
cursor mark. Each ships a **light** and a **dark** variant, sized to sit in the dashboard header
(viewBox ~520–560 × 120; the chip is ~72–84px square = header-row height). Coral `#D6351C` on light /
`#FF6A4F` on dark; ink `#16181D` / paper `#F4F5F7`. Fonts degrade gracefully to system sans/mono.

- **`logo-walkwright-{light,dark}.svg`** — the **Walk click-cursor** with a small **play-triangle**
  emitting from its tip (the cursor "walks" a UI → a video ships). Wordmark splits **`Walk`** (coral,
  the parent) + **`wright`** (ink) so the lineage is visible in the type itself.
- **`logo-walkstudio-{light,dark}.svg`** — the Walk cursor framed inside a **film frame** (rounded
  square with sprocket notches = a studio/production). Heavy **`Walk`** + a spaced **mono `STUDIO`**
  caption underneath for the agency read.
- **`logo-showrunner-{light,dark}.svg`** — **three accelerating chevrons** that resolve into a solid
  **play triangle**: "press play and run the whole production forward." The two trailing chevrons fade
  (the queue of scenes behind the shipped head). Wordmark splits **`Show`** (ink) + **`runner`**
  (coral) to stress the _run / operate_ half of the word — i.e. the P&L, not just the show.

Rendered + XML-validated; both trios verified on their correct backgrounds (light-on-paper,
dark-on-graphite) — see `branding/`.

---

## 3. Why the recommended name + mark fit the positioning

The product's whole pitch is **"a video-production company that runs itself"** — it doesn't just
animate text, it _decides, prices, charges, governs, and ships_. A generic "AI video" name (Reel,
Clip, Frame) describes the **output** and undersells the autonomy. **Walkwright** and **Showrunner**
both name the **operator**: a _wright_ is a maker who delivers finished goods; a _showrunner_ runs the
whole production and owns the budget. That's the exact gap between this and a template tool — and it's
the gap the hackathon is judged on (usefulness/viability = "it runs a real, profitable operation").

The **mark** carries it the same way Walk's does — one confident glyph that _is the verb_:
- Walkwright's **cursor → play-triangle** = "navigate a product, ship a video" in one shape.
- Showrunner's **chevrons → play head** = "run the pipeline, press play on the company."

Both lean on the existing **single-coral-over-neutral** discipline the dashboard already commits to
(per `HERA-DASHBOARD-UIUX.md`: one accent, one idea per moment), so the mark drops into the current
light/coral header with zero palette change and reads as premium, not "AI-generated."

---

## 4. (Bonus) Animated logo-reveal concept — one paragraph

**"The cursor that ships a video" (Walkwright) / "Press play on the company" (Showrunner).** On a
near-white field, the **glyph draws itself first**: for Walkwright, the click-cursor strokes on
(path-length dash from tip to tail, ~0.5s, a confident `cubic-bezier(.2,.7,.2,1)` ease), holds a beat,
then the **play-triangle pops from its tip** with a small spring as a single coral accent lands —
echoing Hera's "the accent clause lands second" two-stage rhythm. For Showrunner, the three chevrons
**stagger in left-to-right ~90ms apart** (the pipeline filling), then the solid play head **snaps in**
on the last beat. As the glyph settles, the **wordmark builds in by word/segment** — `Walk` then
`wright` (or `Show` then `runner`) — with the coral half resolving _last_ so the accent carries the
punchline, then the whole lockup nudges up ~6px and rests. ~1.6–2.0s total, CSS-only (dash-offset +
opacity + transform + one spring keyframe); trivially portable to Remotion (`interpolate` +
`spring`) for the submission video's title card or the dashboard's first-load splash. No emoji,
no glow gimmicks — it earns "polished" in the hold, not the entrance.

---

## Files
- `branding/logo-walkwright-light.svg`, `branding/logo-walkwright-dark.svg`
- `branding/logo-walkstudio-light.svg`, `branding/logo-walkstudio-dark.svg`
- `branding/logo-showrunner-light.svg`, `branding/logo-showrunner-dark.svg`

_Collision/trademark notes above are **reasoned, not verified** (no web access used). Before locking a
name, do a 5-minute pass: domain availability, the `@handle` on X/IG, a USPTO/`namechk` glance, and
specifically check the unrelated "Showrunner" AI product if that name wins._
