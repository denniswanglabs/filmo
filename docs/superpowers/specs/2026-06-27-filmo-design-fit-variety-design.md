# Filmo Design-Fit Variety — Design Spec (2026-06-27)

## Goal
Make Filmo choose **which designs/patterns a given company's video uses**, so different companies get visibly different — and *appropriate* — videos ("not all videos look the same"). Selection model (approved):
- **Content-fit is primary** — the design follows the company's REAL story.
- **Brand-vibe** chooses the style layer (opening style, motion intensity, accent boldness).
- **hash(host)** only breaks ties when 2+ options fit equally.

This is the anti-slop moat: a video's design is a *function of the company's real material*, never forced or fabricated. All selection runs on **Nemotron Ultra 550B** (`ultra-paid`) — paid is approved.

## Five units (clear boundaries)

### Unit 1 — The Design Brief (brain: Nemotron 550B Conversion Read)
Extend the Conversion Read output with a structured, honesty-guarded brief. Lives on the plan/conversion_read; threaded to the planner + `style_fill`.
- `story_shape`: only what is CORROBORATED in the real scraped/known content (never invented):
  - `stats: [{value,label}]`, `customers: [name]`, `process_steps: [{title,body}]`, `contrast: {before,after}`, `testimonial: {quote,who}`, `scored_results: [{name,score}]`, `corpus: {count,label}`, `has_screenshot: bool`, `hero_metric: {value,label}`.
- `brand_vibe`: `{ label: "enterprise"|"startup-bold"|"consumer-playful"|"technical-precise", motion: "calm"|"energetic" }`.
- HONESTY: each field present ONLY if real. The 550B must leave a field empty rather than guess. This reuses the existing enrich/honesty discipline (`enrich_brand_knowledge`, the corroboration guards).

### Unit 2 — Content-fit router (harness: `plan_job` / `style_fill`)
Each beat selects the pattern whose raw material exists in `story_shape`:
- `process_steps` (>=3) → **process-pipeline**; `corpus` (real count) → **scan-grid**; `scored_results` (>=2) → **scorecard-rings**; `testimonial` → **pull-quote**; `contrast` → **comparison-columns**; `stats` (>=3) → **metric-row**; `stats` (1) → **split-stat**; `customers` (>=3) → **split-mosaic**/**logo-wall**; else honest floor → **icon-headline**. No material → not chosen. This EXTENDS the existing data-driven `_assign_treatment_from_filled_copy`, not replaces it. All existing honesty guards stay.

### Unit 3 — Vibe style-selector
`brand_vibe` drives the style choices content-fit leaves open:
- Opening: `startup-bold`/`consumer-playful` or `motion: energetic` → **kinetic-badge opening** (existing kinetic-statement + brandBadge); `enterprise`/`technical-precise` + `calm` → current **clean wordmark** opening.
- (Phase 2) accent boldness + motion intensity params.

### Unit 4 — New pattern archetypes (from Dennis's Luceo films)
Each a self-contained `ExplainerCard` treatment in BOTH copies + types + Timeline route (only if not reusing `explainer-card`) + catalog entry (`harvestedFrom` set) + Lookbook still. Priorities + data contracts (from the scouts):
- **process-pipeline** (smartbase `StepsOverviewScene.tsx:24-250`): `data.steps:[{badge,title,body}]` (3-4), optional `eyebrow`/`headline`. Horizontal numbered cards + animated connector arrows drawing L→R.
- **scan-grid** (kuli `VideoCollage.tsx:59-362`): reuses `featureEntities[]`/`entityLogos[]` + `stat{value,label}` (the corpus counter) + optional `tilePills[]`. Accent scanline sweeps the grid, tiles glow row-by-row, live "N/Total" counter.
- **brand-resolve** (cluely `Scene7.tsx:51-316`) — Phase 2 outro: `{wordmark/logoSrc, tagline, cta, url}`. Wordmark assemble + bloom + tagline + CTA chip. NEW archetype (new `BrandResolve.tsx` both copies + `Archetype` union + Timeline branch + `BOOKEND_ARCHETYPES` + `_shape_brand_resolve`).
- (Phase 2) **equation-payoff** (smartbase `HookScene.tsx`), **scorecard-rings** (kuli `CreatorResults.tsx:545-967`).

### Unit 5 — Tie-break hash(host)
Deterministic `variant = int(hashlib.sha1((host+"|open").encode()).hexdigest(),16) % N`. Use `hashlib` (NOT `hash()` — salted per-process, breaks worker determinism). Seed `brand["host"]` → fallback `name`/`wordmark`. Only used when vibe doesn't decide.

## Integration seam (from recon)
ONE spot decides archetype with `brand`/`theme`/`host` in scope: **`style_fill.build_props`**, after `archetype = style.archetype_for(plan_scene)` (~`style_fill.py:3912`), written at `:3950`. Compute the per-brand variants once at the top of `build_props` (~`:3886`).
- **Opening kinetic-badge variant = ZERO new archetype**: when `archetype==ARCH_HERO` AND `idx==0` AND not closing AND (vibe-bold OR tie-break==1): derive opening copy via `_grounded_headline(...)`, set `d["treatment"]="kinetic-statement"`, `d["brandBadge"]=True`, `d["lines"]=_split_statement_lines(title)`, `d["emphasisWord"]=<content word>`, then override `archetype=ARCH_EXPLAINER`. The kinetic-statement opt-in + verbatim guards already exist (`style_fill.py:2388-2434`); `brandBadge` renders in studio `ExplainerCard.tsx:1547`.
- **PARITY FIX (required):** web-editor `ExplainerCard.tsx` is missing the `brandBadge` block — port it from studio so the editor preview matches the render.
- New archetypes (process-pipeline/scan-grid/brand-resolve) route via the same seam.

## Honesty (non-negotiable)
Every pattern fires ONLY on real corroborated data. The Design Brief leaves fields empty when unsure; the router degrades to the honest floor (icon-headline). Never fabricate a stat, step, quote, score, or customer. Carries forward the existing corroboration guards.

## Phasing
- **Phase 1 (visible variety fast):** Unit 1 (Design Brief: story_shape + vibe) · Unit 3 opening variant (vibe-driven kinetic-badge + logo) · Unit 4 `process-pipeline` + `scan-grid` · Unit 2 routing for those · Unit 5 tie-break · web `brandBadge` parity fix. **Test hosted across ~4 diverse brands** (a steps/ops tool, a stat+customer SaaS, an AI-corpus tool, an enterprise) → confirm they look genuinely DIFFERENT + each appropriate + honest. Deploy worker + (lookbook) web.
- **Phase 2:** brand-resolve outro, equation-payoff, scorecard-rings, accent/motion vibe params.

## Testing
- Unit tests (`tests/test_patterns.py`): Design-Brief parse + router selection per story_shape (incl. empty→floor); new-pattern selection + honesty (no data→not selected).
- Render-verify each new archetype (contact sheet read, taste-gated).
- Hosted gens across 4 diverse brands → variety + fit + no regression + no fabrication. 78-test `test_style_fill` regression stays green throughout.
- All on Ultra 550B.

## Risks
- The brain emitting `story_shape` could over-claim (fabrication) → mitigate with the existing corroboration guard + "leave empty when unsure" prompt + a verbatim/real-data check in the router.
- Routing could starve good existing patterns → the router PREFERS richer fits but always falls through to today's behavior; verify no regression on stat/customer brands.
- Two ExplainerCard copies + new archetypes = drift risk → keep byte-identical (the established rule).
