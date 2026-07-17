# Filmo Style — "Engineered Night"
### Producible style spec (from Dennis's own InsForge launch film, `insforge-launch-32s-v3`)

**Provenance:** Dennis's own design language, measured from his InsForge launch
film. In Filmo this is a PRODUCIBLE STYLE: the render implements this grammar
fresh in `studio/src/night/`, and §3's accent-as-slot rule maps 1:1 onto
Filmo's brand extraction — ACCENT = the target brand's extracted accent, ink
stays white, the reference's mint stays out unless the subject IS InsForge.

---

## 1. Identity

A single engineered world at night. The film is not a slideshow — it is one
tall, coherent product surface explored by a gliding camera. Every element that
appears *earns* its entrance; nothing is decorative. The mood is precise,
premium, dark, and quietly confident: blueprint meets keynote.

## 2. Stage system

- **Canvas:** pure black `#000000`. Panels/cards: `#161616`, 1px borders at
  ~`rgba(255,255,255,0.08)`.
- **Blueprint grid:** 40px grid lines at `rgba(51,51,51,0.7)`, with vertical
  rails bounding a 1280px content column. The grid is felt, not seen —
  ≤7% luminance over black.
- **Dual atmospheric glow:** one radial glow tinted with the ACCENT at ~20%
  opacity (one side), one white at ~10% (other side). Static, enormous, soft.
- **Corner brackets** frame the hero moment — four thin L-brackets that draw in
  around the headline, camera-locked.

## 3. Palette rule (strict)

- Ink: `#FFFFFF`. Muted ink: white at 55–65%.
- **ACCENT is a slot, not a color.** It is derived from the film's *subject*
  (the product being launched) — its brand accent, sampled from its real
  surfaces. The reference's mint `#6EE7B7` is the reference subject's brand and
  is **prohibited** here.
- Soft accent fill: ACCENT at 10% for chip fills and highlight bands.
- Semantic use only: accent = the subject's voice (headline keyword, active
  chip, CTA, live badge). Never decoration, never more than ~8% of the frame.

## 4. Type system

- **Display: Manrope** (500/600/700). Headlines at −2% to −3% tracking,
  110–115% leading, set in two lines with the key phrase carrying the accent.
- **Body/labels: Inter** (400/500/600).
- **Eyebrow grammar:** 11–12px, ALL-CAPS, +8–12% tracking, muted or accent —
  e.g. `BACKED BY …`, section labels.
- **Chips:** 11–12px Inter 500 in bordered pills, `#161616` fill or soft-accent
  fill for the active one.
- ≤6 sizes total across the film.

## 5. Composition grammar

1. **One world, no hard cuts.** The film is a single tall page; the camera
   glides and zooms between sections. Transitions are camera moves and morphs —
   scene detection across the reference finds *zero* cuts.
2. **Hero:** stacked headline + eyebrow + corner brackets; CTA pair appears
   beneath (filled + ghost).
3. **Proof moment:** a terminal/console panel with typed lines appearing —
   monospace, prompt glyphs, a status line. The technical heartbeat of the film.
4. **Capability section:** a headline plus a *ladder* of feature chips that pop
   in sequence.
5. **Credibility beat:** badge + stat line (the reference's "backed by / stars"
   shape) — one strong appearance, given air.
6. **Ecosystem row:** small icon tiles popping in as a family.
7. **Close:** tagline line where the final word carries the accent → brand
   lockup resolve with a chip ("Built for …" shape) → stillness.

## 6. Motion vocabulary (measured from the reference)

- **The atomic move is the appearance pop:** scale 0.92→1.0 + fade, 180–260ms,
  ease-out (cubic). Elements arrive as objects, not fades-in-place.
- **Chip/icon ladders:** successive pops spaced 0.28–0.30s (musical half-beats
  at ~100 BPM). Never simultaneous, never slower than 0.35s apart.
- **Camera glides:** 0.8–1.4s, strong ease-in-out, one axis dominant per move.
  The camera *breathes* — micro-drift (≤1% scale) during holds so no frame is
  frozen.
- **Typed lines** in the proof panel appear line-by-line, 0.4–0.6s apart.
- **Pacing budgets (hard):** no scene beat static for >40 frames; every scene
  develops over its full duration; 12–16 meaningful shots/actions per 32–45s
  film; 3–6 active elements per beat.
- **Sync rule:** every appearance lands on the soundtrack's beat grid (or
  half-beat), verified against the music's measured BPM — not approximated.

## 7. Audio grammar

- **Music:** one continuous build → single climax landing exactly on the brand
  lockup resolve; a breath/dropout ~0.5s before the climax. No flat loops.
- **SFX:** a single pop family (two level-matched samples, alternating) marks
  appearances only — the agent panel, chips, badges, stat, icons, tagline
  keyword, lockup. No whooshes-by-default; the music's own risers carry moves.
- SFX end by T−1s; the music's fade owns the final second. Audio fade outlasts
  the visual fade.

## 8. Acceptance criteria

- Zero hard cuts (scene-detect score < 0.28 across the whole film).
- Appearance beats measurably on the beat grid (±2 frames).
- Grid ≤7% luminance; accent ≤~8% of frame area; no reference brand content
  (name, mint hue, logo, stats) anywhere.
- Type: Manrope/Inter only, ≤6 sizes, headline tracking −2% or tighter.
- Every scene passes the pacing budgets in §6.
