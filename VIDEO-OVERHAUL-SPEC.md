# Walk Studio — Video Overhaul Build Spec (Phase 0 keystone)

Goal: bring Walk Studio's rendered videos to the bar of Dennis's **Orinovate
`kinetic-light`** and **TapPay** promos — Luceo-grade motion graphics, a coherent
story, the **text-left / screenshot-right** format where the headline and the
screenshot reinforce each other, real brand logos, and background music.

**Perfect ONE brand first: Stripe.** Then generalize. Every literal in this spec
(copy, hexes, URLs) is a Stripe-tuned default; the implementation must keep them
data-driven (theme + scene data) so a second brand only changes data, not code.

This spec is grounded in frames pulled from the real renders:
- Orinovate: `/Users/dennis/Desktop/Projects/Orinovate/orinovate-video-zh/out/orinovate-kinetic-light-1080p.mp4`
- TapPay: stills in `/Users/dennis/Desktop/Projects/Demos/tappay-promo/out/stills/` + `IPhoneTapScene.tsx`

All canvas math is **1920×1080 @ 30fps** (matches both references and current Walk
Studio). Frames below are at 30fps.

---

## 0. What the references actually look like (grounding)

From the frames I read, every winning beat shares ONE layout DNA:

- **Text block pinned LEFT** (~`left: 80–120px`), vertically centered-ish, never
  centered over the UI. A small **tracked uppercase eyebrow** (`STEP 2 / 客製化成型`,
  `加值服務 · IPHONE 卡緊收`, `商家後台`) sits above…
- **A huge two-line display headline** where the *key noun* is in the **brand
  accent** and the rest is near-black. (Orinovate: gray→blue `多種材料 / 快速篩選`;
  TapPay: `每筆`accent`交易 都看得見`, `用 `accent`iPhone` 卡緊收`).
- **The product UI floats RIGHT** as a single **glass/white card with a soft long
  shadow**, slightly inset from the right edge. It is NOT full-bleed — it reads as a
  *floating object* on a near-white textured page.
- The headline **names the thing the UI shows**: "多種材料快速篩選" sits next to the
  material-filter panel; "每筆交易都看得見" sits next to the dashboard. Text and UI are
  one sentence.
- **Bookends** (open + close) are **centered**: a wordmark on near-white with a
  faint radial bloom (TapPay `01-intro`), and a CTA wordmark card at the end.
- **Background is near-white** (`#f6f7f9` Orinovate / warm cream TapPay), with very
  faint brand-tinted radial blooms — never flat.
- The TapPay **iPhone scene** = the device-animation Dennis loves: phone springs up
  from lower-right (rotate `10°→-8°`, scale `0.85→1`), a card flies in from upper-right
  and *taps* the top, NFC rings ripple out, an "approved" chip springs in. This is the
  **device-as-hero** motion; the web analog is an animated **browser frame** doing the
  same arrival + a live cursor + element highlight.

The current Walk Studio `apple-screenshot` archetype is **centered text ABOVE a
browser card** — it is close but WRONG axis. The overhaul re-lays it out to
text-left / card-right and adds the motion layer below.

---

## 1. Motion vocabulary (build into `studio/src/timeline/motion.ts`)

A named, reusable, **deterministic** (frame-derived, no `Math.random`/`Date`) set.
Naming follows the existing `reveal` / `appleRise` style. Timings are defaults the
archetypes pass cue frames into. All easings already partly exist in `motion.ts`
(`EASE_OUT_QUART`, `easeOutCubic`, `breathDrift`, `tailPulse`) — REUSE them.

| Name | What it does | Timing / easing | Source |
|---|---|---|---|
| **word-rise** | line fades + rises `dy→0`, opacity `0→1` | `dur≈18f`, `EASE_OUT_QUART` | exists as `reveal`/`appleRise`; standardize the name |
| **line-stagger** | multi-line headline, each line offset | `stagger 16–18f` | exists as `stagedLine` |
| **accent-pop** | the punch noun snaps to brand accent + soft glow, then `tailPulse` | pop over `8f`, glow `0.28α` | exists in `HeroTitle`/`CardUi` |
| **eyebrow-track** | tracked uppercase kicker fades in first | `at≈4f`, `dur 12f`, letter-spacing `0.18em` | `AppleScreenshot` badge |
| **card-deal-in** | the floating UI card arrives: opacity `0→1` (`14f`), **scale `1.06→1.00`** (cubic, NO overshoot), top-down `clipPath inset(100%→0)` reveal over `30f` | `easeOutCubic` + `EASE_OUT_QUART` | exists in `AppleScreenshot` (`ARRIVE=30`) |
| **frame-rise** *(NEW)* | the **browser chrome frame** itself springs up from `+48px` & `scale 0.92→1` with a slight `rotateX(6deg→0)` tilt-settle (the web analog of TapPay's phone-rise) | spring `damping 16, stiffness 110`; `28f` | port from `IPhoneTapScene` phoneSpring |
| **cursor-move** *(NEW)* | an arrow cursor springs between keyframes in card-local coords; emits a **click ripple** (radius `6→60`, opacity `0.65→0`) over `18f` on `click` frames | spring `damping 14, stiffness 110, mass 0.6` | port `orinovate .../walkthrough/ui/Cursor.tsx` |
| **highlight-box** *(NEW)* | a rounded accent ring + tint draws ON over a named UI rect inside the card: stroke dash-in or opacity `0→1` over `14f`, holds, fades; pairs with the headline noun | `EASE_OUT_QUART` | new; mirrors Cursor ripple color |
| **zoom-punch** *(NEW)* | a Ken-Burns / CameraRig push toward a focus rect: `scale 1→1.18` toward `focusOn(x,y)` over `24f`, hold, ease back | `EASE_IN_OUT_CUBIC` | port `orinovate .../walkthrough/ui/CameraRig.tsx` (`focusOn`) |
| **parallax-drift** | settled card + bg blooms drift `±2.5px` on a slow sine so held frames never freeze | `breathDrift`, `period 110` | exists |
| **nfc-ripple** *(device only)* | concentric accent rings scale `0→2.0` & fade, staggered `6f` | from `IPhoneTapScene` waveScale/waveOp | port for any "tap/confirm" beat |
| **approve-chip** | a success chip springs in `scale 0.6→1` (`damping 11, stiffness 200`) with a check | exists in `IPhoneTapScene` | port |
| **whip-transition** *(NEW)* | scene-to-scene: outgoing exits with a fast `translateX(-60px)+blur(6px)` over `8f` while incoming `word-rise`s; OR a clean cross-fade (`12f`) for calm cuts. Default: cross-fade; whip only on the Hook→What cut. | `EASE_IN_OUT_CUBIC` | new; lives in Timeline seam |
| **counter-roll** | a number ("20,000+", "$31,895") counts up from 0 with `EASE_OUT_QUART` over `26f` | new helper `rollNumber(frame,at,to,dur)` | TapPay proof stat |
| **bg-bloom-drift** | the two brand-tinted radial blooms ease position on a very slow sine so the near-white bg breathes | sine `period 300` | exists pattern in `AppleScreenshot` mesh |

**Helpers to ADD to `motion.ts`:**
```
frameRise(frame, at, fps)            -> { opacity, transform } (spring up + scale + tilt-settle)
cursorAt(frame, keyframes, fps)      -> { x, y, ripples[] }    (card-local cursor pos + ripples)
highlightBox(frame, at, holdEnd)     -> { opacity }            (ring draw-on / hold / out)
zoomPunch(frame, at, focus, scale)   -> { transform }          (CameraRig-style push)
rollNumber(frame, at, to, dur)       -> number                 (counter-roll)
nfcRipple(frame, at, i)              -> { scale, opacity }     (device tap)
```
All clamp via the existing `interpClamp`/`ease`; all are pure functions of `frame`.

---

## 2. The text-left / screenshot-right archetype (`apple-screenshot` v2)

**Rename intent, keep the archetype key `apple-screenshot`** so `Timeline.tsx`,
`style_fill`, `build_timeline` keep wiring it without a schema migration. Add a
`data.layout?: "split" | "centered"` flag (default `"split"`) so the new format is
opt-in-by-default but old behavior is still reachable.

### Layout (split mode)
```
┌──────────────────────────────────────────────────────────┐
│  [ 02 · HOW IT WORKS ]            ╭───────────────────────╮│
│                                   │ ● ● ●  dashboard.strip ││   <- frame-rise
│  Accept payments                  │┌─────────────────────┐││
│  in a single                      ││  REAL STRIPE        │││
│  integration.                     ││  SCREENSHOT (cover, │││   <- card-deal-in
│  ── accent underline ──           ││  object top)        │││
│                                   ││   [highlight-box]   │││   <- highlight + cursor
│  one line of supporting copy      │└─────────────────────┘││
│                                   ╰───────────────────────╯│
│  LEFT ~38% width, left:96px       RIGHT ~58%, right:64px    │
└──────────────────────────────────────────────────────────┘
```
- **Left column** (`width ~640px`, `left: 96px`, vertically centered):
  - `eyebrow-track` kicker: `NN · LABEL` (act badge folded into the eyebrow here,
    not top-left) — fontSize 22, accent, `0.18em`, mono.
  - Headline: 2–3 lines, `splitToLines`, `line-stagger`. fontSize ~76, weight 700,
    `lineHeight 1.08`, color `theme.text`; the **punch noun** in `theme.accent`
    (`accent-pop`). Below it a short **accent underline bar** that wipes in
    (`width 0→120px`).
  - Supporting line (the existing `caption`/`headline` split): one muted sentence,
    `word-rise` after the headline. fontSize 28, `theme.textMuted`.
- **Right column** (the floating UI card):
  - The **browser frame** = the existing mac chrome (3 brand-tinted dots + address
    pill with the real captured host, e.g. `dashboard.stripe.com`). The whole card
    does **frame-rise** (spring up + scale `0.92→1` + `rotateX` tilt-settle) THEN the
    screenshot inside does **card-deal-in** (clip-mask reveal). Card `width ~1080`,
    `borderRadius 18`, the existing 3-layer long shadow.
  - **Highlight + cursor mechanism (the headline↔UI tie):** `data.focus` describes a
    rect in card-local %, e.g. `{ x:0.62, y:0.30, w:0.30, h:0.14, label:"Payments" }`.
    The archetype draws a **highlight-box** over that rect timed to the headline punch
    word's cue, and (optionally) a **cursor-move** that travels to the rect center and
    clicks (ripple) right as the box appears. Optionally a **zoom-punch** pushes the
    card toward that rect so the named element fills more of the frame. This is what
    makes "Accept payments **in one integration**" literally point at the Payments
    nav/element in the Stripe shot.
  - `data.focus` is OPTIONAL: when absent, no box/cursor/zoom — byte-identical to a
    plain shot. `style_fill` populates it (best-effort) from the captured DOM rects
    (see §6 task `focus-grounding`); a missing rect just degrades to no-highlight.

### New `SceneData` fields (extend `types.ts`)
```ts
layout?: "split" | "centered";          // default "split"
supporting?: string;                     // the muted left-column sentence
focus?: { x:number; y:number; w:number; h:number; label?:string };  // card-local % rect
cursorPath?: Array<{ at:number; x:number; y:number; click?:boolean }>; // card-local %
zoomTo?: { x:number; y:number; scale:number };  // optional zoom-punch target
```
New `Cue` labels the archetype reads: `eyebrow-in`, `headline-in`, `frame-in`,
`shot-in`, `highlight-in`, `cursor-go`, `supporting-in`. All fall back to scene-length-
scaled defaults exactly like `HeroTitle` does today (must survive short scenes).

### Device variant
For mobile/app products, reuse the SAME archetype with `data.frame: "phone"` →
render the `PhoneFrame` (port `tappay-promo/src/components/PhoneFrame.tsx`) instead
of browser chrome, and the screenshot is a portrait capture. Stripe is web-first so
the **browser** frame is the Stripe default; keep `phone` available for generality.

---

## 3. Per-scene treatment — the Stripe story arc

Arc: **Hook → What it is → How it works (screenshot beats) → Proof → CTA.**
Total target ~32–40s. This mirrors the TapPay contact-sheet arc exactly. Every
content scene gets the new motion layer; bookends stay centered.

Stripe brand facts to use (real, public): accent **`#635BFF`** (Stripe purple), ink
`#0A2540`, near-white bg `#F6F9FC`, wordmark "Stripe", tagline family "Financial
infrastructure for the internet" / "Payments infrastructure for the internet".
Real surfaces to capture: `https://stripe.com` (home), `https://stripe.com/payments`,
`https://dashboard.stripe.com` (or the Stripe Dashboard marketing page if login-gated:
`https://stripe.com/dashboard`), `https://stripe.com/pricing`.

| # | Scene | Archetype | Content (Stripe) | Motion |
|---|---|---|---|---|
| 1 | **Hook (cold open)** | `hero-title` / `apple-statement` (centered bookend) | Wordmark "Stripe" + accent block, faint purple radial bloom; subtitle "Payments infrastructure for the internet." | wordmark `word-rise` + `accent-pop` on the logo block; `bg-bloom-drift`; held with `parallax-drift`. ~3s |
| 2 | **What it is** | `apple-statement` (centered) OR `card-ui` | Big editorial line: "One integration. **Every payment.**" `accent` on "Every payment." Optional 3 mini stat chips (135+ currencies, 99.999% uptime, millions of businesses). | `line-stagger`, `accent-pop`, chips `card-deal-in` staggered; `counter-roll` on any number. ~4s |
| 3 | **How it works — Payments** | `apple-screenshot` **split** | Eyebrow `01 · ACCEPT`; headline "Accept **payments** in a single integration"; supporting "Cards, wallets, and 100+ methods through one API."; **shot** = `stripe.com/payments`; `focus` = the payment-methods/checkout element; cursor moves to it. | `frame-rise`→`card-deal-in`→`highlight-box` on "payments" cue + `cursor-move`; optional `zoom-punch`. ~5s |
| 4 | **How it works — Dashboard** | `apple-screenshot` **split** | Eyebrow `02 · SEE EVERYTHING`; headline "Every transaction, **in one place**"; supporting "Real-time revenue, payouts, and disputes."; **shot** = dashboard; `focus` = the revenue/metrics card. | same chain; `highlight-box` on the metrics card; `counter-roll` can overlay a KPI. ~5s |
| 5 | **How it works — Build/Pricing** | `apple-screenshot` **split** | Eyebrow `03 · BUILD`; headline "Go live with **a few lines of code**"; supporting "Clear, usage-based pricing — no setup fees."; **shot** = `stripe.com/pricing` or a docs/code surface; `focus` = the pricing/code block. | same chain; if a code surface, a subtle type-on caret instead of cursor. ~5s |
| 6 | **Proof / walkthrough** | `walkthrough-player` (if a Walk Agent clip exists) ELSE `card-ui` proof | "Trusted by millions of businesses" + proof stat "**$1T+** processed" / logo strip (Amazon, Shopify, Google — only if truly verifiable, else neutral "millions of businesses"). | `counter-roll` on the big stat; logo chips `card-deal-in`; `zoom-punch` on the stat. ~5s |
| 7 | **CTA (close bookend)** | `hero-title` (centered) | Wordmark "Stripe" lockup + CTA "Start now → stripe.com"; the brand promise/slogan lands HERE (per `feedback_slogan_lands_on_cta`). | wordmark `word-rise`, CTA button `accent-pop`, gentle `bg-bloom-drift`; audio + visual fade (audio outlasts). ~4s |

Pacing budget (per `reference_video_pacing_budgets`): no scene > 9s, 3–6 beats/scene,
no held beat > 40f without motion (the `parallax-drift` + held glow covers this).
`whip-transition` ONLY on the Hook(2)→How(3) cut; cross-fade elsewhere.

---

## 4. Logo fetch + placement, and music

### Logo (real Stripe logo, not the derived wordmark)
Today `brand_extract._wordmark_svg` **derives** an SVG from the brand NAME (honest,
but generic). Upgrade path (data-only, no fabrication):
1. **Capture during the existing Playwright pass** (`capture_screenshots.py`). While
   the page is open, also pull, in priority order:
   - the inline `<svg>` of the site logo (querySelector for header `a[href="/"] svg`,
     `[class*="Logo"] svg`), serialize `outerHTML`;
   - else `<link rel="icon"|"apple-touch-icon"|"mask-icon">` href → download the asset;
   - else `og:image` (`meta[property="og:image"]`).
   Save to `runs/<id>/brand/logo.svg` (or `.png`) + record the source in the manifest.
2. For Stripe specifically the high-confidence real asset is the favicon /
   `apple-touch-icon` at `https://stripe.com` and the og:image; the wordmark is the
   word "Stripe" set in their purple — the derived wordmark with accent `#635BFF` is an
   acceptable, honest fallback if SVG scrape fails.
3. `style_fill` stages the captured logo into `studio/public/brand/` and the theme
   gets `theme.logoSrc?: string`. Bookend archetypes (`hero-title`) render
   `theme.logoSrc` as an `<Img>` when present, else fall back to `wordmark_svg`/text.
   **Never** invent a logo; degrade to the wordmark.

### Music — RECOMMENDATION: `tappay-promo/public/music.mp3`
Path: `/Users/dennis/Desktop/Projects/Demos/tappay-promo/public/music.mp3` (51.5s).
Why it fits Stripe: it scores a **fintech / payments / Taiwan SDK** promo in the
same kinetic-light genre we are copying — confident, modern, clean, not dramatic — and
at **51.5s** it covers the full ~32–40s arc without a loop seam (the 30–33s tracks at
alai/cluely/webduino would need a loop). It is the closest stylistic + duration match
to a premium fintech piece in Dennis's owned, attribution-free Pixabay set.
- **Mix:** stage to `studio/public/music.mp3`; add ONE `<Audio loop volume={...}>` in
  `Timeline.tsx` UNDER the VO. Per `feedback_bgm_level_depends_on_vo`: BGM **0.16**
  ducked while VO plays, **0.45** in VO gaps (intro sting + CTA tail). Implement a
  frame-windowed volume: full-ish under the silent bookends, ducked under narrated
  scenes. Audio fade-out **outlasts** the visual fade by ~15f (`feedback_audio_outlasts_visual_fade`).
- Fallback if Dennis prefers a different cut: `kuli-promo/public/music.mp3` (116s,
  also calm/modern) — but tappay is the recommendation.

---

## 5. Judge rubric (orchestrator scores each Stripe render 1–5 per dimension)

Anchor: **5 = indistinguishable in craft from the Orinovate/TapPay reference frames
in §0; 3 = competent but flat; 1 = the pre-overhaul centered-card look.** Score from
tiled stills + a watch of the MP4.

| # | Dimension | 1 | 3 | 5 |
|---|---|---|---|---|
| 1 | **Layout fidelity** (text-left/UI-right) | centered text over card | split but cramped/misaligned | clean left column + floating right card, matches §0 spacing |
| 2 | **Headline↔UI coherence** | headline unrelated to shot | headline near right topic | headline punch word literally highlighted/zoomed on the named UI element |
| 3 | **Motion quality** | static fades only | entrances present, no held life | frame-rise + card-deal-in + cursor/highlight + parallax-drift; nothing freezes |
| 4 | **Kinetic typography** | one weight, no accent | accent present, no stagger | line-stagger + accent-pop + underline wipe, reads like Orinovate |
| 5 | **Brand truth** (Stripe) | wrong/again-generic palette | accent right, logo derived | real Stripe purple `#635BFF`, real logo asset, real captured surfaces |
| 6 | **Story arc** | scenes feel random | arc present, weak bookends | Hook→What→How→Proof→CTA with centered bookends + slogan on CTA |
| 7 | **Pacing** | scenes drag / cut early | mostly ok | every scene 3–9s, 3–6 beats, whip only on the one cut |
| 8 | **Audio mix** | no music / clashing | music present, not ducked | BGM ducked 0.16 under VO, 0.45 in gaps, audio outlasts visual fade |
| 9 | **Polish** (shadows/bg/blooms) | flat white bg, hard card | soft shadow | textured near-white + drifting brand blooms + 3-layer card shadow |

**Gate to "ship Stripe":** total ≥ 36/45 AND no dimension < 3 AND dims 1, 2, 3 each ≥ 4.

---

## 6. Build task breakdown (Phase 1 fan-out — minimal conflict)

Independent units. The only shared file is `motion.ts` (helpers) and `types.ts`
(fields) — land those FIRST (Task A) so the rest don't conflict.

- **Task A — motion + types foundation** *(do first; everyone depends on it)*
  Files: `studio/src/timeline/motion.ts`, `studio/src/timeline/types.ts`.
  Add the new helpers from §1 (`frameRise`, `cursorAt`, `highlightBox`, `zoomPunch`,
  `rollNumber`, `nfcRipple`) and the new `SceneData` fields from §2. Back up both
  (`.pre-overhaul.bak`). No visual change yet; existing archetypes still compile.

- **Task B — `apple-screenshot` v2 (split layout + tie mechanism)** *(the keystone)*
  File: `studio/src/timeline/archetypes/AppleScreenshot.tsx` (back up
  `.pre-overhaul.bak`). Implement §2: split layout, `frame-rise`, left kinetic
  headline w/ accent-pop + underline, `highlight-box`, embedded `cursor-move`,
  optional `zoom-punch`. Keep `layout:"centered"` path = current behavior. Self-
  contained; depends only on Task A.

- **Task C — port Cursor + CameraRig as shared card-local primitives**
  New files: `studio/src/timeline/ui/Cursor.tsx`, `studio/src/timeline/ui/CameraRig.tsx`
  (ported from `orinovate-video-zh/src/walkthrough/ui/`). Card-local coords (% of card),
  consumed by Task B. Can land in parallel with B if B stubs the import.

- **Task D — bookends + logo plumbing**
  Files: `studio/src/timeline/archetypes/HeroTitle.tsx`,
  `studio/src/timeline/archetypes/AppleStatement.tsx`, `types.ts` (`theme.logoSrc`),
  `Timeline.tsx`. Render real `theme.logoSrc` `<Img>` in bookends with wordmark
  fallback; ensure CTA slogan placement. Depends on Task A.

- **Task E — music bed in Timeline**
  File: `studio/src/timeline/Timeline.tsx` (back up). Add the looped, frame-windowed
  ducked `<Audio>` per §4. Stage `tappay-promo/public/music.mp3` → `studio/public/music.mp3`.
  Independent.

- **Task F — Stripe logo + DOM-rect capture in the pipeline**
  Files: `capture_screenshots.py` (logo + per-target element rects → manifest),
  `brand_extract.py` (consume captured logo over derived wordmark),
  `style_fill.py` (stage logo into `studio/public/brand/`, populate `data.focus`
  from captured rects, set `theme.logoSrc`). Backend-only; parallel with all UI tasks.

- **Task G — Stripe story plan + scene data**
  Files: the planner path (`plan_job.py` / `planner-prompt.md` / a Stripe fixture
  `studio/src/timeline/fixtures/`). Encode the §3 arc as the Stripe plan: 7 scenes,
  the right archetypes, copy, cues, `focus` rects, music on. This is what the
  orchestrator renders to score against the §5 rubric.

- **Task H — integration render + tiled-stills verify**
  Orchestrator-run (NOT a subagent): render the Stripe timeline `--concurrency=8`,
  tile stills, score against §5, loop fixes back into B/D/G. Per project rules, verify
  via tiled stills BEFORE any full MP4.

**Conflict map:** A blocks B/D/E/G. B and C touch the screenshot path (C is new files,
low conflict). D and E both touch `Timeline.tsx` — sequence D then E, or have one
agent own `Timeline.tsx` for both. F and G are backend/data, independent of UI.

---

### Appendix — exact reference values lifted from the sources
- Card-deal-in: `ARRIVE=30f`, `scale 1.06→1.00` cubic, opacity `0→1` over `14f`,
  `clipPath inset(100%→0)` over `30f` (from current `AppleScreenshot.tsx`).
- Phone/frame-rise spring: `spring({damping:16, stiffness:110})`, `scale 0.85→1`,
  `rotate 10°→-8°`, opacity over `14→36f` (from `IPhoneTapScene.tsx`).
- Cursor spring: `{damping:14, stiffness:110, mass:0.6}`, click ripple `r 6→60`,
  `op 0.65→0` over `18f` (from Orinovate `Cursor.tsx`).
- CameraRig `focusOn(wx,wy,scale)`: target point → screen center at zoom
  (from Orinovate `CameraRig.tsx`); for card-local, scale is relative to card box.
- Title spring (kinetic-light): `{damping:16, stiffness:150}`, line-stagger `16–18f`
  (from `HeroTitle.tsx` / Orinovate IntroScene).
- Palette tokens already shaped in `types.ts` `Theme`; Stripe values: accent
  `#635BFF`, ink `#0A2540`, bg `#F6F9FC`.
