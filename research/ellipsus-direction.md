# Filmo landing — editorial redesign direction (inspired by ellipsus.com)

Captured live via Chrome MCP 2026-06-25. "Inspired, not cloned."

## What makes Ellipsus work (the parts we steal)
- **Type contrast is the whole identity.** Headlines: `Roslindale Display Narrow`, weight 300, 80–96px, high-contrast editorial serif, near-white `#FBFBF9` on dark. Body/UI: `Manrope` (clean geometric sans), warm ink `#282825`.
- **Dark cinematic hero**, warm charcoal (not blue-black), with a faint field of **dispersed floating letters** and a thin **hand-drawn line-art** motif (a paper plane).
- **Annotation marks as editing marks** — highlighter swipes + underlines on real manuscript text. This is the soul of the site.
- **Generous whitespace**, big editorial type scale, **alternating dark/light** sections, restrained color (one warm gradient on the product UI).

## The Filmo translation (why it's ours, not a copy)
Ellipsus annotates a **manuscript**. Filmo annotates a **product page** — that's literally the Conversion Read. So the editing-mark motif = our actual product. We keep Filmo's identity (one restrained **Coinbase blue `#0052FF`** accent) and translate writerly motifs to film: clapperboard/frame line-art instead of paper cranes; dispersed *subtitle words / letters* instead of manuscript letters.

## Tokens
- Display serif: **Fraunces** (variable, high-contrast — the free Roslindale analog), light/normal weights. next/font.
- Body/UI: **Manrope**. next/font. (No Inter/Roboto/Space Grotesk.)
- `--ink:#1C1C1A` · `--cream:#F4F2EC` · `--paper:#FBFBF9` · `--stage:#14130F` (warm charcoal) · `--filmo:#0052FF` (sole brand accent) · `--mark:#FFD964` (highlighter) · marks can also stroke in blue.
- Big editorial scale, tight headline leading, comfortable body leading, lots of negative space.

## Sections (reskin existing content; alternating dark/light)
1. **Hero (dark):** huge light-serif headline with ONE word annotated by a hand-drawn SVG mark (underline/circle); Manrope subhead; the **existing composer** (URL+goal+Build) restyled editorial — keep its handlers, auth-gate, sessionStorage prompt-stash + dev-mode flow intact. Faint dispersed-letters field + film line-art, reduced-motion safe.
2. **Conversion Read showcase:** an annotated "read" of a real product page — highlights/underlines diagnosing it (the manuscript-annotation translation). Powered-by note: Nous Hermes.
3. **How it works:** URL → read → plan → pay → produce → ship; editorial numbered steps, serif numerals, whitespace.
4. **Luceo film showcase:** keep the real films (hover-play), restyled as editorial frames (Ellipsus's device-mockup moment).
5. **Differentiators / use cases:** editorial.
6. **Trust bar:** Nous Hermes (Conversion Read) · NVIDIA Nemotron (planning) · Stripe (test mode) — honest.
7. **Closing CTA:** big serif statement; the brand slogan lands HERE (not the hero); CTA/composer repeat.
8. **Footer:** editorial; "Built for the Hermes Hackathon — Nous × NVIDIA × Stripe."

## Reusable pieces to build
- `AnnotationMark` SVG (rough hand-drawn underline / circle / highlight / bracket; draws in on scroll via stroke-dashoffset).
- Grain/noise overlay + subtle dispersed-letter field.
- Film line-art SVG (clapperboard / frame / play).

## Hard constraints
Keep composer + auth-gate + dev-mode + `/inside` working. No emojis (SVG/badges). Next 15 App Router + Tailwind 3.4 + framer-motion + next/font. Reduced-motion safe. Don't touch the Hermes pipeline or `/inside` routes. Build green; **preview deploy only** until Dennis approves.
