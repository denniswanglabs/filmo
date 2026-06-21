# Curated Design Library — Walk Studio inspiration corpus

> The catalog of Dennis's curated, PUBLISHED video designs the Walk Studio agent
> should draw inspiration from when producing a customer's video. "Curated" =
> the pieces Dennis actually selected and shipped onto his public studio site —
> not internal experiments.

Built: 2026-06-21 (research subagent, Hermes hackathon). Read-only research.

---

## STEP 1 — Where the curated set lives

**The curated set is the `films[]` array on the Luceo Studio website.**

- **Website (source of truth):** https://luceostudio.com — the public studio brand.
  The curated list is hard-coded in the repo at
  `~/Desktop/Projects/Luceo/luceo-site/src/data/films.ts` (`films: Film[]`).
  `films.test.ts` hard-asserts the film count + order, so this array is the
  authoritative, intentionally-curated set. The live page renders two sections:
  **Client Work** (paid) and **Concept Films** (spec pieces), plus a Walk Agent
  "Also Building" founder section (not a film).
- **YouTube mirror:** https://www.youtube.com/@luceo-studio
  (channel `UC3K9B7mewAFcUm7wayT-fRg`). Every film in `films.ts` carries a
  `youtubeUrl`; the published YouTube cut is the canonical render and the
  720p loops on the site are pulled from it via yt-dlp into
  `luceo-site/public/video/<slug>-launch-720.mp4`.
- **NOT the curated set:** the personal portfolio at
  `~/Desktop/Projects/Personal/dennis-portfolio/` (that showcases Walk/Beside/
  Ashlar *products*, deliberately kept off luceostudio.com to separate personal
  vs studio brand). It is not a video catalog.

**Curated set = 12 films** (verified against `films.ts`, 2026-06-21):

### Client Work (paid)
1. Cumie  2. Orinovate

### Concept Films (spec)
3. Webduino  4. TapPay  5. Hotcake  6. JGB Property  7. Smartbase
8. Kuli  9. Trayd  10. Benchling  11. NanoClaw  12. iKala Kolr

---

## Published-on-website ⇄ local source repo map

| # | Film (site) | YouTube id | Local source repo (absolute) | Rendered ref (local) | Build tool | Style family |
|---|---|---|---|---|---|---|
| 1 | Cumie | `4zVHsR7HVSc` | `~/Desktop/Projects/Demos/cumie-promo/` (+ siblings a–d, hub :3007) | `out/cumie-promo-4k.mp4`, `out/cumie-promo.mp4` | Remotion | Vertical kinetic glass (9:16, violet/pink) |
| 2 | Orinovate | `FNXrDx8v42I` | `~/Desktop/Projects/Orinovate/orinovate-video/` (zh hub :3002) | `~/Desktop/orinovate-kinetic-light-4K.mp4` (kinetic-light sibling) | Remotion | **Orinovate kinetic-light** |
| 3 | Webduino | `IerYuQewe24` | `~/Desktop/Projects/Demos/webduino-promo/` | `out/webduino-promo.mp4` | Remotion | Kinetic-light (amber/navy) |
| 4 | TapPay | `TCqd_-HQWDY` | `~/Desktop/Projects/Demos/tappay-promo/` (:3009) | `renders/tappay-zelios-v4.mp4` (Zelios) + Orinovate-style zh cut | Remotion | Zelios (Lovio) + kinetic-light |
| 5 | Hotcake | `BL8IVJ-f14Y` | `~/Desktop/Projects/Demos/hotcake-promo/` | `out/hotcake-promo-4k.mp4` | Remotion | Kinetic-light (9 scenes) |
| 6 | JGB Property | `OKW6xlPMrpo` | `~/Desktop/Projects/Demos/jgb-promo/` | `out/jgb-promo-v6.mp4` (also v3–v5, v3-vo) | Remotion + Higgsfield plates | Zelios-arc (cold-open→reveal→montage→CTA) |
| 7 | Smartbase | `yRmhOeCaa4Y` | **`~/Desktop/Projects/Demos/smartbase-promo-hyperframes/`** (HF is the deliverable) + `smartbase-promo/` (Remotion, stills only) | `smartbase-promo-hyperframes/renders/smartbase-promo-4k-v2.mp4` | **HyperFrames** (HTML) | Kinetic-light |
| 8 | Kuli | `nxFYamrhC5o` | `~/Desktop/Projects/Demos/kuli-promo/` | `out/kuli-promo.mp4` | Remotion | Kinetic-light (violet, 5 scenes) |
| 9 | Trayd | `w-YUqHcC9vU` | `~/Desktop/Projects/Demos/trayd-promo/` | `out/trayd-promo.mp4` | Remotion | **Apple-style** (navy/lime) |
| 10 | Benchling | `HLzd5XL3Ocs` | `~/Desktop/Projects/Demos/benchling-promo/` | `out/benchling-promo-4k.mp4` | Remotion | **Apple-style** (navy/coral) |
| 11 | NanoClaw | `QFcblqVfGyU` | **UNCONFIRMED** — no clearly-named promo repo in `Demos/`. Thumbnail exists at `Demos/luceo-thumbnails/src/thumbnails/NanoClawThumbnail.tsx` (light-gray canvas, navy + teal, serif "NanoClaw" wordmark, "agents that *collaborate*"). NOT the same as `alai-promo` (that is the getalai.com slide product). | — (YouTube is source of truth) | Remotion (assumed) | Light editorial / kinetic-light |
| 12 | iKala Kolr | `gLConMB0-vI` | `~/Desktop/Projects/iKala/ikala-video/` (:3006) | `out/ikala-kolr-v1.mp4` | Remotion | **Orinovate kinetic-light** (indigo/violet) |

Note on caption files: films with `.en.vtt` (Orinovate, Kuli, Trayd, Benchling, NanoClaw, iKala) ship burned/sidecar captions — relevant if the agent reuses the caption pipeline.

---

## STEP 2 — Style profiles

There are really **three reusable style FAMILIES** plus a couple of one-offs.
Every piece shares the same craft DNA: brand colors pulled live from the target
site (style = genre, palette = brand), native SVG/CSS UI (never screenshots),
Remotion (one HyperFrames exception), kinetic typography, scene files + a
brand-pulled `theme.ts`, music with fade-in/out and VO-dependent ducking.

### A. Orinovate kinetic-light  ★ flagship template
- **Source repo:** `~/Desktop/Projects/Orinovate/orinovate-kinetic-light/`
  (canonical), siblings: `orinovate-video/`, `orinovate-video-zh/` (hub :3002).
- **Rendered ref:** `~/Desktop/orinovate-kinetic-light-4K.mp4`.
- **Memory:** `feedback_orinovate_kinetic_light_style.md` (full spec).
- **Genre/aesthetic:** crisp white-background editorial; fast but readable;
  product UI rebuilt natively so it holds at 4K. The approved "customer intro"
  default.
- **Palette:** bg near-white `#f8fafc` + faint fractalNoise grain (opacity 0.035);
  navy text `#0f172a`; accent blue; product-green for success; muted grays.
  (Adapts per brand: Webduino amber `#F0B834`/navy `#1A3A6B`; iKala indigo
  `#1e1b4b`/violet `#7c3aed`/magenta `#d946ef`.)
- **Typography:** Noto Sans TC; hero titles 120–220pt weight 900, letterSpacing
  −4 to −10; accent color on the punch word/number; no trailing periods on
  display text.
- **Motion vocab:** spring entrances (damping 14–22, stiffness 120–200); eased
  cubic for layout/camera lerps; "tail animation" — every scene keeps a slow
  pulse/breath/sweep after its main reveal so held frames never freeze;
  card-deal-in stagger; instant-quote trope (6f progress fill + check cascade).
- **Pacing:** 58–60s @ 30fps, 8 scenes, 4–11s each, one hero statement + one UI
  element per scene.
- **Best-fit brands:** any SaaS/product walkthrough or onboarding intro with a
  dashboard UI; B2B / Taiwan businesses; manufacturing, KOL, education, salon.
- **Used by:** Orinovate, iKala, Webduino, Hotcake, Kuli, Smartbase(HF),
  TapPay(zh cut).

### B. Zelios / Lovio (aurora + glass + kinetic type)
- **Source repos:** `~/Desktop/Projects/Demos/lovio-fable5/` (:3021, the
  benchmark); applied in `tappay-promo/src/zelios/` (TapPayZelios),
  `cluely-promo-zelios/` (:3022), `jgb-promo/` (Zelios six-act arc).
- **Rendered refs:** `lovio-fable5/renders/lovio-fable5.mp4` +
  `…-nosource.mp4`; `tappay-promo/renders/tappay-zelios-v4.mp4`;
  `cluely-promo-zelios/out/already-right-zelios-v2-master.mp4`;
  `jgb-promo/out/jgb-promo-v6.mp4`.
- **Memory:** `feedback_zelios_style_spec.md`, `reference_zelios_animation_vocab.md`,
  `feedback_glassmorphic_panel_recipe.md`, `project_lovio_fable5.md`,
  `reference_zelios_video_skill.md` (also packaged as the
  `zelios-style-product-video` skill).
- **Genre/aesthetic:** dark, cinematic, premium. Aurora radial gradients
  (mixBlendMode screen + blur) under frosted-glass UI panels; six-act narrative
  (cold open → problem hook → transformation word → product reveal → feature
  montage → CTA + logo). Has a LIGHT variant of the same genre (cluely-zelios,
  tappay-zelios v4) when the brand is light.
- **Palette (default, override per brand):** deep night `#050814`, deep blue
  `#0B1E52`, royal `#1E3AFF`, ice `#9EC2FF`, violet `#7A5BFF`; spring-green
  `#00C767` for feature callouts.
- **Glass recipe (the "lovio glass" card):** `backdrop-filter: blur(18px)` +
  `rgba(255,255,255,0.22)` fill + `rgba(255,255,255,0.35)` 1px border +
  two-part shadow (`0 30px 80px rgba(15,30,60,0.18)` lift + `inset 0 1px 0
  rgba(255,255,255,0.5)` sheen). Needs a textured backdrop to blur over.
- **Typography:** Inter bold 120–220px hero words; gradient text fills
  (white→blue); `serif-accent-swap` (one keyword → blue italic serif).
- **Motion vocab (named, from the taxonomy):** `word-rise-blur`,
  `serif-accent-swap`, `card-deal-in`, `screen-zoom-handoff` (the move Dennis
  loved — hero revealed as a device screen via continuous camera pull-back),
  `3d-tilt-settle`, `whip-cut`, `whiteout`/`radial-bloom-swell`,
  `icon-bloom` + `bg-recede`. Spring scale/translate, beat-locked cuts.
- **Pacing:** 50–55s @ 30fps, ~20 scenes of 1–4s, lots of momentum, no cut > ~4s.
- **Best-fit brands:** premium / consumer-facing SaaS, launch films, anything
  that wants to feel high-end and cinematic; payments, AI products.

### C. Apple-style (Product Love Letter)
- **Source repos:** `~/Desktop/Projects/Demos/apple-style-demo/` (the living
  pattern library — read its `PATTERNS.md` first); applied in `benchling-promo/`,
  `trayd-promo/`.
- **Rendered refs:** `benchling-promo/out/benchling-promo-4k.mp4`,
  `trayd-promo/out/trayd-promo.mp4`.
- **Memory:** `project_apple_style_demo.md`, `project_benchling_video.md`,
  `project_trayd_video.md`. Pattern catalog: `apple-style-demo/PATTERNS.md`.
- **Genre/aesthetic:** ~30s silent vignette; restrained, product-as-hero, white
  mesh + brand accent; liquid glass, segmented controls, shape morphs, edge
  light sweeps; alternating navy/light sections.
- **Palette (per brand):** Benchling = white-mesh + navy `#1A2847` + coral
  `#FF6B5C`; Trayd = navy `#0B2747` + lime `#E9FF9A` + off-white `#F7F9FC`.
- **Typography:** SF Pro / Geist; large editorial wordmarks; type-coded entity
  colors for data grids.
- **Motion vocab:** Apple iOS motion curves (cubic ease, NOT spring on screenshot
  shrink), slide-up titles, word stagger, shape morph, edge light sweep, breath
  drift, scene zoom-outs. Reusable "Notebook + Instrument" split + "Registry"
  grid patterns.
- **Pacing:** 30s @ 30fps, ~5 scenes of 4–7s. Silent (music only).
- **Best-fit brands:** cold-outreach samples, life-sciences / biotech, vertical
  SaaS with rich dashboard UIs; "premium but quiet" pitches.

### D. Vertical kinetic glass (Cumie) — specialized one-off-ish
- **Source repo:** `~/Desktop/Projects/Demos/cumie-promo/` (hub :3007 + siblings
  a–d). **Memory:** `project_cumie_video.md`.
- **Genre:** 9:16 vertical, 1080×1920, 28.5s, violet/pink, zh-TC; cosmic-aurora /
  glass chat-bubble UI; reserve top 12% safe area.
- **Best-fit:** consumer mobile apps, social-first vertical reels.

### E. JGB — Zelios six-act + Higgsfield live-action plates
- A Zelios-arc piece that composites Higgsfield-generated b-roll
  (`jgb-promo/higgsfield/clips/*.mp4`) under the native UI. Best-fit: real-estate
  / lifestyle brands wanting cinematic establishing shots. Heavier (paid
  Higgsfield assets) — less deterministic to reproduce.

---

## STEP 3 — Parameterizability assessment

**What every repo already has going for it:** brand-pulled `theme.ts` (the one
file that holds all palette/typography tokens), discrete scene files, a fixed
arc, native-SVG UI, deterministic Remotion render. The `theme.ts` indirection is
exactly the seam an agent fills: swap tokens + copy + UI data, keep motion.

**Ranking — gorgeous × parameterizable × reliable-to-render-deterministically:**

| Rank | Style | Gorgeous | Parameterizable | Deterministic render | Notes |
|---|---|---|---|---|---|
| 1 | **Orinovate kinetic-light** | High | **Highest** | **Highest** (pure Remotion, no external assets) | 8-scene arc maps cleanly to any product walkthrough; proven re-skinned 5× (Webduino/iKala/Hotcake/Kuli/TapPay) by editing theme + scene data only. The template. |
| 2 | **Apple-style** | High | High | High (pure Remotion, silent) | Backed by `PATTERNS.md` — composable named patterns, not bespoke scenes. 30s is cheap to render. Proven re-skinned (Benchling→Trayd). |
| 3 | **Zelios / Lovio** | **Highest** | Medium | Medium | Most beautiful, packaged as a SKILL (`zelios-style-product-video`). But the most gorgeous builds use Higgsfield/Gemini plates (paid, non-deterministic). The CODE-ONLY Zelios (SVG aurora + glass, no source pixels — see lovio-fable5 v2) IS deterministic; wire THAT variant. |
| 4 | Vertical kinetic glass (Cumie) | High | Medium | High | Specialized to 9:16 consumer apps; narrower fit but the only vertical template. |
| 5 | JGB six-act + Higgsfield | High | Low | **Low** (depends on paid generated clips) | Beautiful but least reproducible cold; deprioritize for v1. |

---

## Recommendation — wire these into the agent first

1. **Orinovate kinetic-light** — the single best template: gorgeous, most
   re-skinned, 100% deterministic Remotion. Default for any B2B/SaaS walkthrough.
2. **Apple-style** — second template, backed by `PATTERNS.md` as composable
   parts; cheap 30s silent render; ideal for "premium quiet" outreach.
3. **Zelios (code-only variant)** — the show-stopper look, already a skill; wire
   the no-source-pixels SVG-aurora+glass build for determinism, gate the
   Higgsfield-plate version behind an explicit "spend money" flag.
4. *(optional)* **Cumie vertical** — when the customer wants a 9:16 social reel.
5. *(skip for v1)* JGB / Higgsfield-plate styles — non-deterministic, paid.

**Agent integration seam:** for each chosen style, the fillable surface is
`src/theme.ts` (palette + fonts) + per-scene copy/UI-data + the brand wordmark
SVG. Keep the motion code frozen. Pull the customer's real palette/copy from
their site first (style = genre, palette = brand), then re-skin the template —
exactly Dennis's established manual workflow.
