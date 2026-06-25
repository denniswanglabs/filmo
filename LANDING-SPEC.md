# Walk Studio — Landing Page Spec (the contract)

A **product launch video generator** landing page, structured like Hera
(hera.video) but in **Walk Studio's own brand**. Hera gives us the SECTION FLOW;
the palette/voice are Walk Studio's. The wedge vs Hera: Walk Studio is **grounded**
— you give it a real product URL, it *reads the actual product and diagnoses how it
converts* before it animates anything.

This file is the single source of truth. Every section component must obey the
Design System below and use the EXACT copy provided. Do not invent claims, stats,
customer names, testimonials, or logos.

---

## Page flow (top → bottom)

1. **Nav** — existing `TopBar` (orchestrator). Not your job.
2. **Hero with composer** — orchestrator-built (the real prompt box lives here). Not your job.
3. **TrustBar** — the real tech stack the product runs on.
4. **HowItWorks** — 4 numbered steps (the real pipeline).
5. **Differentiators** — feature grid: why this beats a random-pixel generator.
6. **UseCases** — the launch formats it produces.
7. **Showcase** — example output cards (by format, not by client).
8. **ClosingCTA** — "Ready to launch?" → scrolls to the hero composer.
9. **SiteFooter** — wordmark + minimal real links.

---

## Design System (LOCKED — every section matches this)

**Theme:** light. Alternate section backgrounds between white (`bg-white`) and a
faint tint (`bg-[#F7F8FA]`) so sections read as distinct bands.

**Color tokens** (Tailwind, already configured in `tailwind.config.ts`):
- `ink` = `#14171C` — primary text / headings
- `amber` = `#D6351C` — PRIMARY ACCENT (coral): eyebrows, primary CTAs, numbered badges, highlights
- `nemo` = `#76B900` — secondary accent (NVIDIA green): use sparingly for "positive/delivered" cues
- Muted text: `text-slate-500` (body), `text-slate-400` (captions)
- Hairlines: `border-black/5` (default), `border-black/10` (interactive)

**Type:** body/headings use the inherited sans (Hanken Grotesk / system). Headings
`font-semibold tracking-tight`. No serif needed.

**Section wrapper:** `<section className="px-5 py-20 sm:py-24">` with inner
`<div className="mx-auto max-w-5xl">`. Text-only blocks may use `max-w-3xl`.

**Section header pattern (centered):**
```
<eyebrow pill>  →  <h2 text-3xl sm:text-4xl font-semibold tracking-tight text-ink>  →  <p text-slate-500 max-w-xl mx-auto>
```

**Eyebrow pill:**
`inline-block rounded-full border border-amber/20 bg-amber/5 px-3 py-1 text-xs font-medium text-amber`

**Card recipe (the house card — match the composer card):**
`rounded-2xl border border-black/5 bg-white p-6 shadow-[0_18px_50px_-20px_rgba(20,23,28,0.25)]`
Lighter sub-card: `rounded-xl border border-black/5 bg-white p-5`.

**Numbered step badge:**
`grid h-9 w-9 place-items-center rounded-full bg-amber/10 text-sm font-semibold text-amber`

**Primary button:** `rounded-xl bg-amber px-6 py-3 font-semibold text-white transition hover:opacity-90`
**Secondary button:** `rounded-xl border border-black/10 px-6 py-3 font-medium text-ink transition hover:bg-black/[0.02]`

**Icons:** inline SVG ONLY (`viewBox="0 0 24 24"`, `fill="none"`, `stroke="currentColor"`, `strokeWidth="1.8"`, `strokeLinecap="round"`, `strokeLinejoin="round"`). NO EMOJI anywhere. No raster images.

**Motion:** keep it subtle/optional. A gentle `transition` on hover for cards
(`hover:shadow-sm` / `hover:border-black/10`) is enough. No autoplay video, no heavy JS.

---

## Component contract (every agent)

- One file, at the path assigned to you, under `web/app/components/landing/`.
- **Default export** a React component named as assigned. TypeScript (`.tsx`).
- **Server component by default** (NO `'use client'`) — these are static. Only add
  `'use client'` if you genuinely need an event handler; the ClosingCTA is the one
  likely exception (smooth-scroll click).
- Tailwind classes only, using the tokens above. No new CSS files, no new deps.
- Self-contained: if you need an icon, inline the SVG in the same file.
- Must compile under Next 15 + React 19 + Tailwind 3.4 + `tsconfig` strict. No `any`.
- Width: the component renders its own full-width `<section>`; the page stacks them.
- Keep it tasteful and restrained — Dennis is meticulous about UI. Match the
  existing composer/run-page styling (house card, hairlines, generous spacing).

---

## EXACT COPY (use verbatim; do not embellish)

### TrustBar  → `web/app/components/landing/TrustBar.tsx`
A slim band (tint or white) with a small left/centered label and the real stack.
- Label: `Grounded in your real product — and built on a serious stack`
- Three inline items, each a small SVG glyph (abstract — a chip, a card, a globe/cursor) + label:
  - `NVIDIA Nemotron` — sub: `reads & plans`
  - `Stripe` — sub: `prices & bills, autonomously`
  - `Real-site capture` — sub: `your actual UI, not stock`
Render as a single horizontal row (wraps on mobile), muted, understated. No fake
partner logos — use simple abstract SVG glyphs you draw inline.

### HowItWorks  → `web/app/components/landing/HowItWorks.tsx`
- Eyebrow: `How it works`
- H2: `From a link to a launch video.`
- Subhead: `No brief, no timeline, no editor. Paste your URL and Walk Studio does the rest.`
- 4 steps (numbered badges 1–4), each a card with a title + one-line body:
  1. **Read your page** — `Walk Studio opens your real product and runs a Conversion Read — scoring promise, proof, specificity, and CTA.`
  2. **Plan the cut** — `Nemotron turns that diagnosis into a scene-by-scene launch storyboard, fixing what the page failed to say.`
  3. **Price & produce** — `It prices the job, captures your live UI, and animates structured, fully editable scenes.`
  4. **Ship the MP4** — `You get a finished 1080p video — ready for Product Hunt, X, or your hero section.`
Layout: a 4-up grid on desktop (`sm:grid-cols-2 lg:grid-cols-4`), stacked on mobile.

### Differentiators  → `web/app/components/landing/Differentiators.tsx`
- Eyebrow: `Why Walk Studio`
- H2: `Not another random-pixel generator.`
- Subhead: `Most AI video tools hallucinate footage. Walk Studio is grounded in your actual product — so the video is true, on-brand, and editable.`
- 6 feature cards (3-up grid `sm:grid-cols-2 lg:grid-cols-3`), each: inline SVG icon + title + 1–2 line body:
  1. **Grounded in your product** — `It reads your real page and captures your real UI. The result looks like you, not like stock AI footage.`
  2. **The Conversion Read** — `Before it animates, it diagnoses how your page fails to convert — and writes the video to fix it.`
  3. **Structured, editable scenes** — `Every scene is real layout with readable text you can still change — not a one-shot you can't touch.`
  4. **Prices & bills itself** — `The agent quotes the job and charges through Stripe autonomously — and declines its own over-budget spend.`
  5. **Ships a real MP4** — `A finished 1080p/AAC file, not a preview. Drop it straight onto Product Hunt or your hero section.`
  6. **Built on NVIDIA Nemotron** — `One planner reasons over the whole storyboard, so the cut is coherent end to end.`

### UseCases  → `web/app/components/landing/UseCases.tsx`
- Eyebrow: `What you can ship`
- H2: `One link. Every launch asset.`
- Subhead: `The same grounded engine, pointed at whatever you're launching.`
- 6 items as compact cards or chips (2-up/3-up grid), each title + one short line:
  - **Product Hunt launch** — `A scroll-stopping cut built to win the day.`
  - **Waitlist teaser** — `Tease the promise before you've shipped.`
  - **Feature announcement** — `Make a new feature feel inevitable.`
  - **Investor update** — `Show traction in 30 seconds.`
  - **Social cutdowns** — `Vertical and square edits for X, LinkedIn, IG.`
  - **Landing-page hero** — `The loop that lives at the top of your site.`

### Showcase  → `web/app/components/landing/Showcase.tsx`
- Eyebrow: `Example outputs`
- H2: `What comes out the other side.`
- Subhead: `Finished, editable launch videos — generated from a single URL.`
- 3 example cards in a grid (`sm:grid-cols-3`). Each card = a 16:9 "video poster"
  you DRAW with inline SVG (tasteful abstract: a soft gradient field + a simple UI
  motif like a window bar, a play triangle in a translucent circle, a duration chip
  `0:30`). Below the poster: a format label + one-line caption. Use these three —
  they are FORMATS, not real clients:
  1. `SaaS dashboard launch` — `Promise → product reveal → proof → CTA.`
  2. `AI feature reveal` — `The old way, then the one-line magic.`
  3. `Mobile app teaser` — `Screens in motion, scored to a beat.`
  The poster is a pure-SVG mock — NO real screenshots, NO emoji, NO real brand names.

### ClosingCTA  → `web/app/components/landing/ClosingCTA.tsx`  (`'use client'` OK)
- A centered, high-contrast closing band (use the house card or a coral-tinted panel).
- Eyebrow: `Your launch is one link away`
- H2: `Paste your URL. Get the video that sells it.`
- Subhead: `Walk Studio reads your product, plans the cut, prices the job, and ships a finished MP4.`
- One primary button: label `Start with your URL`. On click, smooth-scroll to the
  hero: `document.getElementById('start')?.scrollIntoView({ behavior: 'smooth' })`
  then focus the URL field if present (`document.getElementById('hero-url')?.focus()`).
  Wrap in a guard so SSR is safe.

### SiteFooter  → `web/app/components/landing/SiteFooter.tsx`
- A slim footer (tint background, hairline top border).
- Left: the wordmark (import `Wordmark` from `../Brand` — it exists) + a one-line
  tagline: `URL in, finished launch video out.`
- Right: three text anchors only (real, in-page): `How it works` → `#how`,
  `Examples` → `#examples`, `Sign in` → `/login`.
- Bottom line: `© 2026 Walk Studio` (small, muted). No fake social links, no fake
  pages. Keep it minimal and honest.

---

## Section anchor ids (orchestrator wires these on the page; FYI for links)
- Hero composer: `#start` (URL input id `hero-url`)
- HowItWorks: wrap its `<section id="how">`
- Showcase: wrap its `<section id="examples">`

Each agent: put the matching `id` on your section's root where noted (HowItWorks →
`id="how"`, Showcase → `id="examples"`). Others need no id.
