# Luceo Studio harvest — scout findings (2026-06-27)

Three read-only scouts distilled reusable SCENE patterns from Dennis's Luceo Studio Remotion films, to grow Filmo's curated pattern library. All proposals are honesty-compatible (literal real copy/data only) and brand-portable (theme tokens, no hardcoded hues).

## IMPLEMENTED
- **`kinetic-statement`** — harvested from `cluely-promo`. Word-by-word rise-blur editorial statement, one accent keyword + glow halo, optional highlighter sweep. The library's biggest gap (animated typography); all 3 scouts converged on this idea. Opt-in selection (`kind=="hook"` / planner emit) so it never disturbs existing icon-headline scenes.
  - Source: `Demos/cluely-promo/src/components/primitives.tsx:28-101` (KineticLines), `scenes/Scene2.tsx` (tilt-settle, emphasis halo ~108-124, highlighter ~126-137).

## BACKLOG (documented, not yet built — strong candidates for later)
- **`brand-resolve`** (cluely) — animated outro/sign-off: wordmark wipe-assemble + icon-bloom + staggered tagline + CTA chip, locks dead-still (good thumbnail freeze). Serves the "slogan lands on the CTA" principle. Deferred: overlaps the existing working outro/CTA scene (selection-conflict + regression risk); revisit as a deliberate upgrade to the final beat. Source: `cluely-promo/src/scenes/Scene7.tsx:51-316`, `primitives.tsx:310-329` (Wordmark), `components/fx.tsx:235-281` (CharReveal), `primitives.tsx:332-361` (Chip).
- **`statement-highlight`** (trayd) — single editorial sentence with one word marker-swept in accent. Mostly SUBSUMED by kinetic-statement's `underlineWord`; keep as a simpler static variant if ever wanted. Source: `Demos/trayd-promo/src/scenes/TheNumber.tsx:38-94`, footnote `:132-147`.
- **`count-up-metrics`** (trayd) — 3-4 KPI cards whose numbers animate counting up from 0 to real values (tabular-nums, decelerating ease). Overlaps existing `metric-row`; the count-up is the only new part → best folded into `metric-row` as an optional animated mode rather than a new pattern. Source: `Demos/trayd-promo/src/scenes/PayrollDashboard.tsx:244-263,436-485`, `CrewMobile.tsx:394-398`.
- **`relationship-graph`** (benchling) — staggered entity cards with animated SVG connecting edges ("everything connects / one source of truth"). Visually distinct + impressive, but niche (needs real related entities + edges) and complex. Revisit if a brand's story is genuinely a network/graph. Source: `Demos/benchling-promo/src/scenes/Registry.tsx` (grid `:76-99`, edges `:227-311`, card `:359-504`).
- **`kinetic-tagline`** (benchling) — two-line word-by-word Apple-style sign-off with optional footnote pill. Overlaps kinetic-statement (word cascade) + brand-resolve (sign-off); lower marginal value. Source: `Demos/benchling-promo/src/scenes/Close.tsx:41-185`.

## Rationale
The 11 pre-harvest patterns were mostly STATIC layouts. `kinetic-statement` adds the missing animated-typography dimension with the lowest risk (opt-in, zero assets, honest). The backlog is intentionally kept (not discarded): it is the literal "patterns distilled from our own designer-made films" story — the anti-slop moat.
