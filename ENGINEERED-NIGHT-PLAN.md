# Engineered Night — producible Filmo style (implementation plan)

Dennis's go: 2026-07-17 ("i want to be able to create that style of videos using filmo").
Spec: [docs/references/engineered-night-design-language.md](docs/references/engineered-night-design-language.md)
(his own design language, measured from `insforge-launch-32s-v3`).

## Shape of the change

- **Sibling composition, same contract.** `NightTimeline` (studio/src/night/) accepts the
  exact `TimelineData` props the classic `Timeline` gets. The pipeline stays byte-identical
  until the last mile: `style_fill` maps scenes to Night archetypes and `build_runner`
  renders composition `NightTimeline` when `job.style == "engineered-night"`.
- **One world, zero cuts.** Scenes become vertically stacked sections in one tall stage;
  the camera glides between section anchors at the scenes' existing `in_frame`s. VO-driven
  timing is preserved — the camera arrives when the narration does.
- **Accent is a slot** (spec §3): `theme.accent` from Filmo's existing brand extraction.
  Ink is white, stage is black, mint appears only when the subject is InsForge itself.
- **Default OFF.** `job.style` defaults to `classic`; the 14-pattern light catalog is
  untouched. Style select lives in the composer's Advanced panel.

## Scene-type mapping (classic → Night section)

| Plan scene / treatment        | Night section                                      |
|-------------------------------|----------------------------------------------------|
| title (open)                  | NightHero — eyebrow + 2-line headline (accent key phrase) + brackets + CTA pair |
| screenshot                    | NightPanel — the captured homepage framed as a surface inside the world (grounding beat stays) |
| motion_graphic · icon-headline / feature-list | NightLadder — headline + chips popping on half-beats |
| motion_graphic · split-stat   | NightCredibility — badge + stat line, given air     |
| motion_graphic · split-mosaic | NightEcosystem — entity tiles (real logos) popping as a family |
| motion_graphic · pull-quote   | NightQuote — the (sentence-trimmed) testimonial in Night type |
| motion_graphic · process-pipeline | NightTerminal — typed monospace lines as the proof moment |
| title (close)                 | NightClose — tagline (accent final word) → lockup + chip → stillness |

## Decisions (recommendation locked unless Dennis overrides)

1. **VO stays.** Filmo's product is a narrated explainer; the reference film is music-only.
   v1 keeps the VO-driven timeline (camera + pops land on narration boundaries) and adopts
   the spec's music grammar UNDER the VO (single build, climax on lockup, ducked per the
   with-VO levels rule). A music-only variant is a later dial, not v1.
2. **Beat-grid sync** (spec §6) applies to the SFX/music layer at the bed's measured BPM;
   visual entrances stay VO-anchored. Full musical quantization of visuals is post-v1.
3. **Fonts:** Manrope (display) + Inter (body) as local woff2 in `studio/public/fonts/`
   (self-contained, Docker-safe; no node_modules mutation).
4. **Stage gates:** stills → Dennis approves the look → sections → camera → pipeline →
   audio → tests → hosted e2e. No full MP4 until the stills pass (video-iteration rule).

## Acceptance (from spec §8)

Zero hard cuts (scene-detect < 0.28) · grid ≤7% luminance · accent ≤~8% frame area ·
Manrope/Inter only, ≤6 sizes · no beat static >40 frames · SFX end by T−1s, audio fade
outlasts visual.
