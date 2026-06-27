# Filmo Curated Pattern Library + Lookbook — Design

**Date:** 2026-06-27 · **Target:** Hermes × NVIDIA × Stripe hackathon (Filmo, due 2026-06-30) · **Status:** approved design, pre-implementation

## 1. Goal & thesis

Filmo's differentiator is **taste as an anti-slop moat** (the Ploy / Bryant-Chou thesis): generic AI video tools let the model improvise every layout, which is where slop comes from. Filmo instead has a **hand-curated library of designer-quality scene patterns**; the AI only decides *which* pattern fits each piece of content and fills it with **verified** data. The curation is the moat — and because it's distilled from a real studio's (Luceo Studio's) Remotion films, it is uncopyable.

This spec covers the hackathon-scoped slice: formalize + expand the pattern library, harvest patterns from Dennis's real Luceo Studio Remotion videos, make the assembler pick from the library legibly + honestly, and make the curation **visible** on the landing page alongside the Luceo Studio films.

**Success criteria (judge-facing):**
1. A URL in → a video whose every scene is a recognizable, designer-quality pattern (no improvised/empty layouts).
2. The landing page shows the **Pattern Lookbook** + the **Luceo Studio films it's distilled from**, with the "curated, not improvised" story legible.
3. The pipeline can name, per scene, *which* curated pattern it used and *why* (legibility = proof the curation is real).
4. Honesty preserved end-to-end: a pattern is only used when the **real** data it needs exists; never fabricate to fit a pattern.

**Non-goals (explicit):** rebuilding the treatment system; runtime feeding of whole videos to the brain; porting every Luceo video; >~4 new patterns; live Remotion players in the Lookbook if stills suffice; the broader Luceo Lookbook product infra (`Tooling/luceo-lookbook`, a separate project this can later fold into).

## 2. Architecture — one catalog, two consumers

A single **pattern catalog** is the source of truth. Two consumers read it, guaranteeing the visible lookbook never drifts from what the engine actually renders:

```
                 ┌──────────────────────────┐
                 │  pattern catalog (SoT)    │
                 │  patterns.catalog.json    │  id, name, purpose,
                 │  + per-pattern archetype  │  whenToUse, dataContract,
                 └─────────┬───────────┬─────┘  exampleProps, harvestedFrom?
                           │           │
              ┌────────────▼──┐   ┌────▼─────────────────┐
              │ THE ASSEMBLER │   │ THE LANDING LOOKBOOK  │
              │ style_fill    │   │ web landing section   │
              │ pattern pick  │   │ renders the catalog   │
              │ (honesty-     │   │ + Luceo films         │
              │  guarded)     │   │                       │
              └───────────────┘   └──────────────────────┘
```

- **Catalog** = `studio/src/timeline/patterns.catalog.json` (machine-readable registry) — the seed of truth both for selection rules and for the lookbook display. Each entry: `id`, `name`, `purpose`, `whenToUse` (human + rule hints), `dataContract` (which `scene.data` fields it needs), `exampleProps` (a self-contained sample for the lookbook), optional `harvestedFrom` (the Luceo video it was lifted from — provenance for the pitch). The catalog must be readable from BOTH the `studio/` (render) and `web/` (landing) projects — co-locate + sync it the same way the two `ExplainerCard.tsx` copies are kept in lockstep (one canonical file, mirrored into `web/`), so there is one logical source of truth.
- **Assembler** = the existing `style_fill.py:_assign_treatment_from_filled_copy`, upgraded to be catalog-driven (§5).
- **Lookbook** = a landing section that imports the catalog + renders each pattern's `exampleProps` through the real archetype (§6).

## 3. The pattern catalog (registry)

**Seed (already built — document, don't rebuild):** the 7 existing treatments — `split-stat`, `split-mosaic`, `big-number`, `icon-stat`, `icon-headline`, `logo-wall`, `feature-list`. Each gets a catalog entry with its `whenToUse` + a curated `exampleProps`. (`logo-wall`/`feature-list` are currently render-valid but unselected; the catalog promotes them into the selectable set.)

**Catalog entry shape:**
```json
{
  "id": "split-stat",
  "name": "Split Stat",
  "purpose": "One hero number, text-left / number+bars-right.",
  "whenToUse": "Scene's filled title carries exactly one real impressive number.",
  "dataContract": ["title", "stat.value", "stat.label"],
  "exampleProps": { "treatment": "split-stat", "title": "Companies funded", "stat": { "value": "5,000+", "label": "" }, "...": "..." },
  "harvestedFrom": null
}
```

## 4. New patterns (~4 high-taste additions)

Each = a Remotion archetype (BOTH `studio/.../ExplainerCard.tsx` and `web/.../_composition/archetypes/ExplainerCard.tsx`, kept in sync), a `types.ts` data contract addition (both copies), a `whenToUse` rule, and a catalog entry. All honesty-guarded.

1. **comparison-columns** — two-column "the old way vs Filmo" / before-after. Data: `compare: { leftTitle, leftItems[], rightTitle, rightItems[] }`. Used when the brand copy frames a contrast. Honesty: both sides from real copy/known facts.
2. **metric-row** — a horizontal strip of 3–4 small stats. Data: `metrics: [{value,label}]` (reuses the enrich's stats). Used when a beat has ≥3 real numbers (an alternative to one split-stat). Honesty: every metric a real mined/enriched number.
3. **pull-quote** — large editorial testimonial + attribution. Data: `quote`, `quoteAttribution`. Used ONLY when a real quote/testimonial exists in the source. Honesty: never invent a quote.
4. **device-frame** — a product screenshot in a clean phone/browser frame. Data: reuses the existing site-capture `imageSrc`. Used for a "see the product" beat. Honesty: real captured screenshot only.

(Final set confirmable at build; these 4 maximize variety + reuse existing data — `metric-row` and `device-frame` need no new capture.)

## 5. Assembly — AI picks from the library, honesty-guarded, legible

Upgrade `_assign_treatment_from_filled_copy` to be **catalog-driven**:
- It already re-derives the treatment from the FILLED copy (the correct, post-fill point). Extend it to evaluate each scene against the catalog's `whenToUse` rules and pick the best-fit pattern.
- **Nemotron may propose** a pattern (the planner can emit a `treatment` hint); the deterministic pass **validates** it against the real filled data and overrides if the data isn't there (same override mechanism as today). The brain proposes; the honesty guard disposes.
- **Legibility:** record `data.patternReason` (e.g. "split-mosaic: 6 real named entities") per scene. Surfaced in logs + available to the demo/UI to prove "curated, not improvised."
- **Honesty (unchanged, central):** a pattern is selected only when its `dataContract` is satisfied by REAL data; otherwise degrade to the honest floor (`icon-headline`). Never fabricate data to unlock a fancier pattern.

## 6. The visible Lookbook + Luceo Studio — together on the landing

The landing already has `LuceoShowcase.tsx`, `Examples.tsx`, `FeaturedPlayer.tsx`, `Showcase.tsx`. Add ONE new section pairing the two halves of the moat:

- **Pattern Lookbook (new):** a `PatternLookbook.tsx` landing section that imports `patterns.catalog.json` and renders each pattern's `exampleProps` through the real archetype as a **high-quality still** (live mini-player only if time permits), each labeled with its name + "when we use it." Headline: *"Every Filmo video is assembled from this hand-curated library — never improvised."*
- **Luceo Studio films (extend existing):** the adjacent `LuceoShowcase`/`FeaturedPlayer` shows the real Luceo Studio films, framed as the provenance: *"Distilled from Luceo Studio's real work — here are the films the library came from."*
- The two sit together as one landing beat ("Curated, not improvised — and here's the proof"), tying the pattern library to the human portfolio.

## 7. Luceo Studio harvest (offline curation)

The mechanism that gets Dennis's taste into the library — an **offline harvest**, not runtime:
- **Source set (~2–4 strongest, confirm at build):** `Demos/lovio-fable5` (Zelios aurora/glass), a `Demos/apple-style-demo` piece (Apple-minimal), `Projects/Orinovate/orinovate-video` (kinetic-light). All are Remotion `.tsx` — readable source, not pixels.
- **Process:** parallel subagents read each project's scene/layout/motion source → distill the most reusable, beautiful **layout + motion patterns** → propose them as candidate catalog patterns (data contract + archetype sketch + the source it came from). Dennis/curation pass selects which 1–3 to actually port into the Filmo archetype format.
- **Output:** the ported patterns join the catalog with `harvestedFrom` set (provenance for the pitch). This is repeatable as Dennis makes more films.
- **Honesty/scope:** harvest *layout/motion craft* (palette-agnostic), not brand-specific content. Time-box to a few patterns; the existing 7 + 4 new already carry the library.

## 8. Narrative / pitch

- Landing "Curated, not improvised" section (§6) + a one-liner on the moat.
- Pitch talking points: the AI-slop problem; curation = the moat (Ploy thesis); the library is distilled from a real studio's films (uncopyable); per-scene legibility proves it; honesty guard means we never fake data to look good.

## 9. Build order (milestones)

1. **Catalog SoT** — write `patterns.catalog.json` for the 7 existing patterns (+ promote logo-wall/feature-list into selection). No behavior change yet; assembler reads catalog metadata.
2. **Assembler catalog-driven + legible** — `_assign_treatment_from_filled_copy` evaluates `whenToUse`, records `patternReason`. Verify on the existing brand sweep (no regression vs current treatments).
3. **New patterns** — add the ~4 archetypes (both ExplainerCard copies + both types.ts), data contracts, whenToUse, catalog entries, honesty guards. Verify each renders + selects on a real brand.
4. **Landing Lookbook + Luceo pairing** — `PatternLookbook.tsx` (stills from `exampleProps`) beside the existing Luceo showcase; the "curated, not improvised" copy. Deploy to Vercel.
5. **Luceo harvest** — subagents distill patterns from the source set; port 1–3 into the catalog with `harvestedFrom`.
6. **Pitch polish** — narrative copy, per-scene legibility surfaced, a clean demo URL.

Each milestone is independently shippable; if time runs short, milestones 1–4 alone deliver the moat (5 enriches it, 6 sells it).

## 10. Risks & mitigations

- **Drift between studio + web archetype copies** → both edited in lockstep (established pattern); catalog is shared SoT.
- **Honesty regressions** when adding patterns that "want" data → every new pattern degrades to `icon-headline` when its `dataContract` isn't met by real data; verify on the unknown-brand cases (Orinovate/TapPay) that they don't fabricate.
- **Harvest over-runs the clock** → it's milestone 5 (after the shippable core); strictly time-boxed to a few patterns.
- **Lookbook stills look static** → acceptable for v1; live mini-players only if milestones 1–5 land early.
- **Scope creep into the full Luceo Lookbook product** → explicitly out of scope; this slice is foldable into it later but does not depend on it.
