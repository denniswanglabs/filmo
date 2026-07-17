# Engineered Night — Development Pass (v3)

**Date:** 2026-07-17 · **Owner:** pipeline · **Trigger:** Dennis's verdict after the
8-brain bake-off: *"all of the models produce roughly the same things — the main
problem is probably the templates. The reference offered more variety of animations
and was more creative."*

The 8-way model test proved the model is not the creativity lever: eight brains fed
the same engine produced eight films with the same skeleton. The remaining distance
to the hand-built reference (`insforge-launch-32s-v3-REMUSIC-v5`) is **engine
choreography**, in four measurable gaps.

## The four gaps (from frame-level comparison)

1. **Co-visible density** — reference frames stack stat + label + chip row + a peek
   of the next section; ours render one element centered on a dark field.
2. **Within-beat development** — reference sections develop across their hold
   (ladders build while the header persists, toggles flip mid-beat, terminal output
   appears after commands); ours do entrance → hold → glide.
3. **Motion vocabulary width** — reference: pops, underline draws, count-ups,
   dim/undim, staggered arrivals. Ours: word-cascade, type-on, big-number pop.
4. **Musical quantization** — reference arrivals land on the bed's onsets; ours fire
   at scene boundaries wherever the beat happens to be.

Plus one **feeding defect** that masquerades as an engine problem: chip ladders
almost always render in fallback statement mode because `featureEntities` is rarely
populated — the richest archetypes starve for structured material.

## Stages

### A — Camera-distance dim/undim (density + the reference's undim vocabulary)
`NightTimeline.tsx`: per-section focus = distance from camera center; section
opacity `0.30 + 0.70 * focus`. Neighbors peek deliberately at ~30% and undim as the
camera glides in. One curve, zero new props.

### B — Beat grid + quantization
`night_music.py` `build_bed` returns `{ok, first_beat_s, spb_s}` derived from the
bed's measured 99.4 BPM through the exact trim/atempo applied. `build_runner`
patches `props.theme.musicMeta = {spbFrames, phaseFrames}`. `NightTimeline` snaps
pop-SFX times (and sections' *internal* element arrivals — never the VO-locked
`in_frame`) to the nearest beat within ±4 frames.

### C — Within-beat development (per archetype)
- **credibility**: value **counts up** (numeric part animated ~0.7s, prefix/suffix
  static, formatting preserved — display-only, never new facts), label + underline
  after.
- **terminal**: after each typed command completes, a muted `✓ done` tick line
  (mechanical UI chrome, not a brand claim); toggle flip unchanged.
- **ladder (chips)**: header persists; after the last chip lands, the active
  highlight **sweeps** across the chips once and settles on `activeIndex`;
  secondary row after.
- **ladder (statement)**: word cascade + a grounded **support line** arriving at
  ~55% of the hold + underline draw under the accent word.
- **panel**: browser frame arrives first, shot fades in inside it (two-stage);
  caption delayed; push-in unchanged.
- **hero**: fix the `real / estate` line-break bug — split lines at the word
  boundary that minimizes line-length variance instead of the word-count midpoint.
- **entrance variants**: add `rise` (y-14 + fade) alongside `pop` in `motion.ts`;
  sections alternate deterministically by index.

### D — Feed the rich archetypes (honesty-safe harvest)
`style_fill.py`: `build_props` stashes `brand["_plan_design_brief"]`. Night ladder
chips harvest priority: `data.featureEntities` → `brand.features[].title` (real
page harvest, UI-label filtered) → `design_brief.story_shape.features` →
`steps[].title`. All sources are already-guarded real material; empty → statement
mode as today. Statement `support` comes from real scene sub-text only.

### E — Fixture + tests
Fixture exercises: count-up, terminal ticks, chip sweep, support lines, musicMeta.
Python tests: balanced hero split; chips harvest priority; beat-grid math;
credibility count-up parser on `$1.9tn / 99.999% / 135+ / €99.99`.

### F — Verify + ship
1. Fixture render → contact sheet → density check (≥2 visible elements at mid-hold
   on ladder/credibility/terminal beats).
2. Pipeline renders (stripe + homefeed) → contact sheets.
3. Full test suite → commit → `railway up` → hosted verification build → deliver.

## Explicitly out of scope (separate pending decisions)
- VO-grounding honesty guard (fabrication set) — awaiting go-ahead.
- Accent extraction fix (invented hash-green) — awaiting direction pick.
- Default brain switch — awaiting decision.

## Acceptance
- Mid-hold frames carry ≥2 co-visible elements on rich beats.
- Element arrivals span ≥60% of each hold (no frozen frames after entrance).
- SFX/inner arrivals within ±4 frames of the beat grid.
- Chips fire on stripe + homefeed via the harvest chain.
- All tests green; hosted Night build delivers with zero legacy fallback.
