# Hera (real app) → Hermes Producer Console: Visual & Motion Learnings

_Read-only study of the **logged-in** app at `app.hera.video`, 2026-06-20, via Chrome MCP. No
edits were made to Hera (no projects/content created, no forms submitted, $0). No edits were made
to our code. Scope: extract the **visual system + motion craft + polish** that makes Hera read
"premium," and map it onto OUR dashboard (`dashboard/{index.html,app.js,styles.css}`) so the
Producer Console **stands out for hackathon judges**._

This is the high-quality follow-up the earlier `HERA-LEARNINGS.md` §6 explicitly asked for: that
study was public-surface-only and could not see the real app. Everything below was observed live in
the editor, the Brief view, the Export flow, and the rendered motion played frame-by-frame.

**Important framing (house rules):** "X style" = motion craft + hierarchy, NOT palette. Hera is a
**light** app on a near-white base (`#F9F9F9`) with a single **coral** accent (`#FA4E3E`). Our
console is the opposite — dark graphite (`#0B0E14`) with an **amber** accent (`#F5A623`), red
reserved only for declines, mono+serif type. We borrow Hera's *moves*, never its colors. Hera's
whole system is structurally "one confident accent over a neutral base," which is exactly our
amber-over-graphite — so the hierarchy and motion port cleanly without touching our palette. A
parallel agent is currently decluttering our IA (collapsing panels, run-delete, one-primary-focus-
per-state); this doc deliberately sits the polish layer ON TOP of that, and does not re-do it.

---

## 0. The one-line takeaway

**Hera looks premium because it commits to one accent, one idea per moment, generous breathing
room, and a small library of named, channel-specific motion presets — and it earns its
"polished" read in the hold, not the entrance.** Our console already shares the bones (single
accent, disciplined type, the `rise` stagger). The judge-impressing delta is: (1) make ONE hero
moment per state genuinely large and confident, (2) replace our single `cubic-bezier` rise with a
2-3 preset motion vocabulary, and (3) keep something alive during every "wait" instead of three
static spinners.

---

## 1. What makes Hera look good (concrete, observed)

### 1.1 Tech under the hood (corrects the prior study's inference)
DevTools peek of the live preview: **0 `<canvas>`, 0 `<video>`, 53 `<svg>`, no Lottie / GSAP /
Remotion / Three / Pixi scripts.** The renderer is **DOM + SVG + CSS/WAAPI animation**, not WebGL
and not Lottie playback. (Prior `HERA-LEARNINGS.md` §2 guessed Canvas/WebGL/Lottie at "HIGH
inference" — it's actually DOM/SVG/CSS, the closest possible cousin to our own React-DOM/Remotion
approach.) For our dashboard this matters because it means **everything they do is reproducible in
plain CSS** — there is no special renderer to envy.

### 1.2 The visual system
- **Base + one accent.** Near-white `#F9F9F9` canvas, near-black text, **a single coral accent
  `#FA4E3E`** carrying every primary action (Export, Create Video, active scene chips, selected
  toggles — observed 22× on one screen). No competing colors. This is the same discipline our
  `--amber` single-accent system already has.
- **Radius rhythm: a deliberate 3-tier scale.** `8px` for small controls/inputs (27×), `20px` for
  content cards/panels (12×), `9999px` (pill) for chips and segmented toggles (12×). Consistent,
  intentional, never mixed at random.
- **Type: bold sans for impact, huge.** The home hero "Hi Wang, what are we creating today?" is a
  ~56px bold sans, centered, with enormous vertical breathing room. In the rendered videos the
  headline type is a heavy near-black sans set very large in the frame.
- **One idea per moment + an accent phrase.** Every rendered scene is "near-black setup text +
  exactly ONE phrase in the accent color" (e.g. "Every customer call, **handled by AI.**" / "The #1
  AI voice platform **for voice agents**"). The accent always carries the payload. Generous negative
  space; never more than one focal idea on screen.
- **Soft depth, not heavy shadow.** Cards use low, diffuse shadows and 1px hairline borders; depth
  is felt, not loud. One dark charcoal CTA card is used as the closing contrast beat in an otherwise
  light video — a single intentional inversion for emphasis.

### 1.3 The motion craft (watched frame-by-frame — the part the prior study couldn't see)
- **Word-by-word staggered build.** Headlines don't appear at once. Caught mid-entrance, "The #1 AI"
  was solid, "voice" mid-opacity, "platform" faded + offset + slightly blurred — i.e. each word
  eases in on a short opacity+position(+blur) ramp, ~80-120ms apart. This is the single most
  "motion-graphics, not slides" move they make.
- **The accent clause lands second.** The setup text builds, then the accent-colored phrase resolves
  in as its own beat — a tiny two-stage reveal that creates a "punchline" rhythm.
- **A named, channel-organized preset vocabulary** (their "Animate" panel, full list):
  - BASIC: Appear · Fade in
  - MASK: Mask in ↑ · Mask in ↓ (clip/wipe reveal)
  - SLIDE: Slide in ↑ · ↓ · ← · →
  - SCALE: Shrink in · Grow in
  - BLUR: Blur in · **Blur and Slide** (a compound, two-channel preset)

  They expose **named presets, not bezier handles** — curated, single-purpose, grouped by the
  channel each animates (opacity / position / scale / blur / mask), plus compounds. This is exactly
  the Zelios/Jitter "named motion vocabulary" model in Dennis's memory, and it validates
  `HERA-LEARNINGS.md` L5.
- **Progress as colored fill.** The timeline scene chips fill left-to-right with the accent as
  playback advances (active region colored, future region gray), and a vertical playhead sweeps a
  fine frame-tick ruler beneath. Smooth fill, never a jump.
- **"Snappy and punchy" vs "Swift and fluid"** is a binary *Rhythm* toggle in the Brief — pacing is
  surfaced as a two-option choice, not a slider. (Selected = "Snappy and punchy", coral.)

### 1.4 The micro-interactions / polish that read as "premium"
- **Progressive disclosure on hover.** The home action cards reveal a chevron `›` and lift slightly
  only on hover; the featured card **autoplays a video preview on hover** (with a mute toggle
  appearing top-right) and its circular `›` gains a fill ring. Affordances are hidden until wanted.
- **Rotating ghost-text prompts.** The editor's chat placeholder cycles ("Change the font colour to
  dark grey (#A9A9A9)" → "Make this Nintendo style" → "Recolour this…") to teach the interaction
  without a tutorial.
- **Context-swapping toolbar.** With nothing selected, the canvas shows a minimal play toolbar
  (select, comment, music, aspect, reset, magic-wand, reaction faces). Select an element and a full
  Figma-like property bar drops in (font dropdown, color, B/I/U, align, gradient, 3D, **Animate**) —
  density appears only when it's relevant.
- **Canvas controls tucked to the right edge.** Layers / fit / zoom +/− live as a tiny vertical
  rail on the canvas's right edge, out of the way until needed.
- **Compact popovers, one primary action.** Export is a small anchored popover (no scrim): two radio
  groups (Resolution 360/720/1080/4k with 4k gated; Format MP4/WebM), a "Remove watermark" upsell,
  and one coral **Export video** button. Clean hierarchy, single CTA.
- **The Brief = an editable plan before producing.** "Enter your website" + an explicit **"Extract
  style"** action; a **Story** column of editable scene rows (each with asset/Figma/edit icons and
  `+ Section ⌘Enter`); a Style column with Colors as three named swatches (**Background / Text /
  Accent**), a Font preview, the Rhythm toggle, and Additional Notes. One top-right **Create Video**
  CTA. This is the review-and-approve-the-plan beat done well.

### Honest counterweight
Hera's *bespoke* art-direction ceiling is lower than its template polish (a hands-on reviewer found
prompt-to-edit unreliable, output "volume over distinctiveness"). We don't need their ceiling — we
need their **polish floor** and **hierarchy discipline**, applied to a console Dennis art-directs by
hand. Our edit-bay/trading-desk aesthetic is already MORE distinctive than Hera's clean-SaaS look;
the goal is to make it as *confident and polished*, not to make it look like Hera.

---

## 2. Top dashboard-applicable learnings (mapped to our files)

Each is **Hera does X → apply to our dashboard by Y (file/element)**. All sit on top of the
declutter pass and respect house rules (no emoji; amber accent, mono+serif; red = declines only).
Ordered by judge-impact-per-hour.

### D1 — One large, confident HERO moment per state (the "premium" anchor)
**Hera does:** every screen has exactly one dominant focal element (the 56px home hero; the single
huge headline per rendered scene; the 58px price-equivalent), surrounded by air. Nothing competes.
**Apply to:** `styles.css` + `app.js` render functions. The declutter pass establishes one-focus-
per-state; this makes that focus *big and confident*. Per state, pick the ONE hero and scale it up
with breathing room:
- **delivered** → the video (`.delivered-hero .dh-video`) is already the hero; ensure nothing above
  it competes. Currently `.margin-fig` is 64px and `.pg-price` 58px — bigger than anything about the
  video itself (UX-IMPROVEMENTS §8.5). Demote those on the delivered view so the *video + "Your
  <brand> promo is ready"* title is unambiguously the largest element.
- **awaiting_payment** → the price (`.pg-price`, already 58px) is the right hero; give it more air
  and let the side panel recede.
- **empty/first-run** → `.hero-title` is the hero; it's good — keep it the single large object.
**Why it impresses judges:** confident scale + whitespace is the fastest visual signal of "designed,
not assembled." Effort: ~2-3h (type-scale rebalance per state). High.

### D2 — Replace the single `rise` with a 2-3 preset motion vocabulary
**Hera does:** named, channel-specific entrance presets (Fade / Slide↑ / Blur-and-Slide / Grow),
varied by element role, with a word-by-word stagger on headlines.
**Apply to:** `styles.css` (currently ONE move: `@keyframes rise` = translateY(10px)+opacity on
`.detail > *`, with nth-child delays). Add a tiny vocabulary of 2-3 keyframes and assign them by
element role instead of using `rise` for everything:
- a **blur-and-rise** for hero text (`filter: blur(6px)→0` + translateY) — their signature look, one
  extra property on the existing rise;
- a **scale/grow-in** (0.96→1) for the price figure and the delivered badge — gives the money moment
  a confident "pop";
- keep plain `rise` for list rows / receipt lines.
Use a slightly springier curve than the current `cubic-bezier(.2,.7,.2,1)` on the hero only (a small
overshoot, e.g. `cubic-bezier(.34,1.4,.64,1)`) so the focal element feels alive, not slid.
**Why:** turns "everything fades up identically" into a small designed motion language — visible
within the first second a judge watches. Effort: ~2-3h. High.

### D3 — Word-by-word build on the ONE hero line per state
**Hera does:** headlines build word-by-word (~80-120ms stagger), and the accent clause lands as a
second beat.
**Apply to:** `app.js` where the hero line renders per state — the empty-state `.hero-title`, the
live `.live-goal`, the delivered `.dh-title`, the pay `.pg-for-v`. Wrap the hero string's words in
spans and stagger their entrance (reuse the D2 blur-rise with per-word `animation-delay`). Critically,
**set the key word/clause in `--amber`** and let it resolve last — this is the "accent carries the
payload" move, and it's already our house pattern (amber-on-serif goals). One small render helper +
CSS; apply to the single hero line only, never to body copy.
**Why:** it's the single most "motion-graphics, not a static page" signal, and it reinforces our own
product story (the agent authoring kinetic type). Effort: ~2-3h. High.

### D4 — Keep something alive during every wait (kill the dead-air)
**Hera does:** progress reads as a smooth accent fill across scene chips + a sweeping playhead;
nothing on screen is ever fully static during activity.
**Apply to:** `app.js` live states + `styles.css`. UX-IMPROVEMENTS §2.1 flags the ~90s planning
phase as near-dead air (three spinners). Borrow Hera's "colored progress as motion":
- make the `.ph-track` phase chips fill/advance with an animated amber sweep as phases progress
  (the active `.ph-chip.now` already glows — add a left-to-right fill transition between chips);
- give the storyboard `.sb-card.s-queued` a slow shimmer (a low-opacity amber gradient sweep) so the
  "about to fill" layout looks alive, not greyed;
- add an "N of M scenes" readout (§2.5) so progress feels bounded.
This is pure CSS + a counter — no new architecture. **Why:** the live build is the centerpiece of
the submission demo; a judge watching the wait should never wonder "is it stuck?" Effort: ~3-4h.
High (and directly serves the demo).

### D5 — Context-swapping density (minimal by default, rich on demand)
**Hera does:** a minimal toolbar until you select something, then a full property bar drops in;
canvas controls hide on the right edge; hover reveals affordances.
**Apply to:** this is the polish-layer rationale for the declutter pass already underway. Where the
declutter agent collapses panels, make the *expand* a smooth reveal rather than a hard toggle (a
height/opacity transition on the collapsed `.panel`/`.studio` bodies). Add **hover-revealed
affordances** in the spirit of Hera: the run-delete control (being added) should appear on
`.run-card:hover` (fade in, not always-on), matching their progressive-disclosure feel. Keep our
amber `:hover` border (already present) — just extend the pattern to the new controls.
**Why:** "shows me what I need, when I need it" is a core premium signal and complements the
declutter without re-doing it. Effort: ~2-3h. Medium-high.

### D6 — A named pacing/tier toggle instead of a hidden env var
**Hera does:** "Swift and fluid / Snappy and punchy" Rhythm toggle in the Brief — pacing as a named
binary, not a slider or hidden setting.
**Apply to:** `index.html` build-bar + `serve.py`/`build_runner.py` (currently `PRODUCER_PACE` /
`target_duration_s` are hidden env vars — UX-IMPROVEMENTS §2.5, §6.4). Add a small pill segmented
control to the NEW BUILD bar (a "draft / standard / premium" or "fast / cinematic" two-three-option
chip, styled like `.ph-chip` pills) that maps to duration+pace. Gives the user a visible lever and
makes the bar feel considered, not bare. (Coordinate with the declutter agent — this adds one
control to the build-bar.)
**Why:** cheap, high-perceived-control, and matches a real gap. Effort: ~2h (UI) + wiring. Medium.

### D7 — Compact, single-primary-action popovers + radius rhythm
**Hera does:** the Export popover is small, anchored, scrim-less, with grouped radios and exactly one
coral CTA; a consistent 8 / 20 / pill radius scale everywhere.
**Apply to:** `styles.css` radius tokens + any of our menus. We already have a strong radius set
(5-14px); formalize a **3-tier scale** (small controls ~6-8px, cards ~10-12px, pills 999px) and
apply it consistently — our `.build-go` (6px), `.run-card` (7px), `.ph-chip` (999px) are close;
audit for one-offs. If/when the declutter pass adds menus (e.g. run-delete confirm, a build-options
menu), make them compact anchored popovers with one amber primary action, not modals.
**Why:** consistency of radius + "one primary action per surface" is a quiet but strong polish
signal. Effort: ~1-2h. Medium.

---

## 3. The single highest-impact "stand out for the judges" move

**D2 + D3 together: a small motion vocabulary with a word-by-word, accent-lands-last build on the
ONE hero line of each state.**

Rationale: a judge forms the "is this polished?" judgment in the first 1-2 seconds of seeing a
screen, and that judgment is driven almost entirely by *how the focal element arrives*. Right now
every section uses the same `translateY+fade` rise — competent but uniform. Hera's entire premium
read comes from headlines that **build word-by-word, with the key idea resolving in the accent color
as a second beat.** We already own the ingredients: a single accent (amber), serif hero type, the
`rise` keyframe, and the house pattern of "accent carries the payload." Adding a blur-and-rise
keyframe + a per-word stagger helper + setting the key clause in `--amber` is ~half a day, purely
additive (can't break anything), touches only the hero line per state, and converts our "clean
receipt viewer" into something that reads as *authored motion* — the exact signal that wins a design-
judged hackathon. It also reinforces the product narrative (an agent that authors kinetic
typography), so the polish pays into the story, not away from it.

If only a second thing ships: **D4 (kill the planning dead-air with animated progress)**, because the
live-build is the demo's centerpiece and "never looks stuck" is the difference between an
impressive live run and an awkward one in front of judges.

---

## 4. Strengths to PROTECT (don't let polish dilute these)

- The edit-bay/trading-desk identity (mono+serif, single amber, red-only-declines, perforated
  receipt, filmstrip gate timeline) is **more distinctive than Hera's clean SaaS look** — it's our
  biggest asset. Make it as confident as Hera, not like Hera.
- The no-emoji SVG icon sprite, the rAF-correct typing, and the existing `rise` stagger are
  well-executed — D1-D3 extend them, they don't replace them.
- Do NOT flip the palette to light/coral, do NOT add a second accent, do NOT introduce emoji. House
  rules + the no-unilateral-aesthetic-flips rule stand.

---

## Appendix — concrete numbers observed (for reference when implementing)
- Hera accent: `#FA4E3E` (rgb 250,78,62). Base: `#F9F9F9`. (Ours stays amber `#F5A623` / graphite.)
- Radius scale: 8px (controls) / 20px (cards) / 9999px (pills).
- Home hero: ~56px bold sans, centered, heavy vertical air.
- Word stagger: ~80-120ms between words; headline = setup (near-black) + one accent clause landing
  second.
- Animate presets: Appear, Fade in, Mask in ↑/↓, Slide in ↑/↓/←/→, Shrink in, Grow in, Blur in,
  Blur and Slide. (Named presets, grouped by channel; no bezier UI.)
- Renderer: DOM + SVG + CSS/WAAPI (0 canvas, 0 video, 53 svg, no Lottie/GSAP/Remotion in the page).
- Rhythm toggle: "Swift and fluid" / "Snappy and punchy" (binary, not a slider).
- Export popover: Resolution 360/720/1080/4k(gated), Format MP4/WebM, Remove-watermark upsell, one
  coral CTA, no scrim.

_Cross-refs: `HERA-LEARNINGS.md` (the public-only predecessor — §6 asked for exactly this logged-in
pass; §2 inference re: renderer is corrected here to DOM/SVG/CSS); `UX-IMPROVEMENTS.md` §2.1 (dead
air → D4), §6.1/§6.4 (plan review + pacing → D6), §8.5 (type-scale balance → D1), §8.1 (protect the
identity → §4 here). Our files: `dashboard/styles.css` (`@keyframes rise`, `.hero-title`,
`.pg-price`, `.margin-fig`, `.ph-track`, `.sb-card`), `dashboard/app.js` (per-state render fns),
`dashboard/index.html` (build-bar)._
