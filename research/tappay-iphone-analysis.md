# TapPay promo — device-mockup ("iPhone") analysis + how to port to Filmo

_Investigated 2026-06-25. Read-only inspection of `/Users/dennis/Desktop/Projects/Demos/tappay-promo/`. Grounded in code + 3 stills extracted from the shipped render `renders/tappay-zelios-v4.mp4` (1920×1080, 30fps, 1500f = 50s) + the source photo asset._

---

## TL;DR — there are TWO different "phone" techniques, and the one Dennis loved is the photo-composite one

| | **A. Orinovate-style `IPhoneTapScene`** | **B. Zelios-style `Z5_Montage` Beat 1 "TAP-TO-PAY"** ← _the premium one_ |
|---|---|---|
| Comp | `TapPayPromo` | `TapPayZelios` (the shipped 50s) |
| Phone frame | **Pure CSS/divs** (rounded-rect, dynamic-island div, box-shadow) | **A REAL PHOTOGRAPH** of a hand holding an iPhone (`hands_tap.jpg`) |
| Screen content | Remotion-built UI, flat (no perspective) | Remotion-built UI **perspective-mapped onto the real screen** via CSS `matrix3d` homography |
| Reads as | Clean but flat / "device illustration" | Photoreal product shot — this is what avoids the "SVG iPhone = cartoonish" trap (per `feedback_iphone_svg_insufficient.md`) |

**The frame Dennis loved is Technique B.** It does NOT draw a phone at all — it takes a real stock photo of someone tapping an iPhone on a card terminal and projects a live Remotion payment-success UI onto the actual lit screen, tracking the photo's perspective, with a subtle handheld wobble so photo + UI move as one rigid unit. That's why it looks premium and not like a wireframe.

---

## Evidence (stills read from `tappay-zelios-v4.mp4`)

- **28.20s** (abs frame ~846): real photo, iPhone screen still near-blank lavender/white (UI not yet drawn). You can see it's unmistakably a real hand + real device + real card terminal on a dark counter.
- **29.20s** (abs ~876): the composited UI is locked onto the screen — TapPay TapMark glyph, "NT$540", a circular progress/success ring — all tilted to match the phone's perspective in the photo.
- **30.40s** (abs ~912): success check resolved inside the ring with a cyan sonar ripple, "已完成" (completed) under the amount. The UI sits flush on the glass, tracking the slight handheld motion.

Source asset confirmed: `public/zelios/bg/hands_tap.jpg` (1920×1080) is a real photo of a hand holding an iPhone with a deliberately blank screen over an NFC terminal — i.e. a "screen-ready" plate chosen precisely so a UI can be comped in.

---

## Exact files

### Technique B — the premium photo-composite (PORT THIS)
**`src/zelios/scenes/Z5_Montage.tsx`** — Beat 1 "TAP-TO-PAY", scene-local frames 0–95 (absolute 840–935 in the 1500f comp).

1. **Phone "frame" = a real photo.** `<Img src={staticFile('zelios/bg/hands_tap.jpg')}>` rendered full-frame `objectFit:cover`, with a gentle warm grade `filter:'brightness(1.03) saturate(0.95)'`. No drawn bezel anywhere.

2. **Inner screen content = Remotion UI mapped onto the screen via a CSS `matrix3d` homography.** This is the load-bearing trick. The four corners of the phone's lit screen were hand-measured in the 1920×1080 photo:
   ```js
   const SCREEN_QUAD = [[779,397],[966,284],[1368,582],[1193,697]]; // TL,TR,BR,BL of the lit screen
   const UI_W = 375, UI_H = 667;  // design the UI as a normal upright iPhone-portrait rect
   const QUAD_BLEED = 1.045;       // expand ~4.5% about centroid so no lit edge peeks
   ```
   A general 4-point homography (`matrix3dToQuad(w,h,dstQuad)`, lines ~47–90) computes the CSS `matrix3d(...)` that maps the upright `375×667` UI rect onto the measured screen quad. The UI div is authored flat/upright, then `transformOrigin:'0 0'; transform: SCREEN_MATRIX`. Everything inside it (logo, amount text, success ring, ripple SVG) inherits the perspective for free. This homography math is self-contained and copy-pasteable.

3. **Rigid-group wobble** (`BeatTapToPay`, lines ~204–292): the photo AND the mapped UI sit inside ONE `<AbsoluteFill>` that gets a shared handheld transform so they never separate:
   ```js
   const settle = interpolate(local,[0,22],[1.045,1.015],{easing:EASE_OUT}); // cut-in settle, scale stays >1 so wobble never exposes the frame edge
   const wx = Math.sin(local*0.21)*2.4 + Math.sin(local*0.067+2)*1.2;        // 2–3px x wobble
   const wy = Math.cos(local*0.17)*2.0;                                       // y wobble
   const wr = Math.sin(local*0.05+1)*0.2;                                     // tiny rot
   // applied: transform: `translate(${wx}px,${wy}px) rotate(${wr}deg) scale(${settle})`
   ```

4. **The on-screen UI animation** (all keyed off `local`, fps from `useVideoConfig`):
   - TapMark logo fades in `local [6,14]`.
   - `SuccessRing` (lines ~105–154): SVG circle stroke-dash draw `local [34,50]` + check-path draw `local [46,58]`, popped in with `springAt(local,fps,34,SPRING_POP)`. The pop is beat-locked to abs 874 (a downbeat where `success.wav` fires).
   - `ScreenRipple` (lines ~164–202): a single cyan sonar ring-arc, `r = 8 + 157*p`, quick flash-in then linear decay `opacity = 0.9*clamp01(p*7)*(1-p)`, drawn INSIDE the mapped UI div so the homography scales it to the screen.
   - Amount "NT$540" springs in `springAt(local,fps,26,SPRING_SNAPPY)`; "已完成" at frame 34.

### Technique A — the pure-CSS device frame (reference only, NOT the premium look)
- **`src/components/PhoneFrame.tsx`** — a self-contained div-based iPhone: outer `borderRadius`, `padding` as the bezel, white screen child, an absolutely-positioned black Dynamic-Island pill, and a layered `boxShadow` (`0 60px 140px` ambient + `0 24px 48px` contact + `inset 0 0 0 2px rgba(255,255,255,0.08)` rim highlight). Aspect 2.06 (19.5:9). Crisp at 4K, but flat — no perspective, no glare, reads as a clean device illustration.
- **`src/scenes/IPhoneTapScene.tsx`** — uses `PhoneFrame` tilted (`rotate(-8deg)`) with a spring entrance (`spring(damping:16,stiffness:110)`, scale 0.85→1, rotate 10→-8), a flat tap-to-pay UI inside (NFC ring, NT$175, approval pill), plus a separate contactless **credit-card div** that flies in from upper-right and "taps" the phone top — pure CSS gradients, no asset. NFC waves are expanding bordered circles.
- _Uncertain:_ there is no full Orinovate render saved in `renders/` or `out/`, so Technique A was analyzed from code only — I could not extract a still of it to view. The shipped/loved video is the Zelios one (Technique B).

---

## What makes Technique B read PREMIUM vs a cheap mockup

1. **A real photograph supplies all the hard-to-fake cues** — real glass reflections, real bezel, real hand, real depth-of-field bokeh, real lighting on a real counter. No drawn bezel can match this; this is the direct answer to `feedback_iphone_svg_insufficient.md` ("SVG iPhone reads wireframe").
2. **Perspective-correct UI.** The UI is not pasted flat — the `matrix3d` homography makes it sit ON the angled glass, so text/ring foreshorten correctly. A flat overlay would instantly read as fake.
3. **Rigid handheld wobble.** Photo + UI move together (2–3px sine wobble, slight rot), so the screen never looks like a static sticker; `settle` scale stays >1 so the wobble never exposes a frame edge.
4. **Beat-locked motion.** Ring pop / ripple / amount land on musical downbeats with `success.wav`, so the payment "completes" on the beat — feels designed, not generic.
5. **The UI itself is alive** — stroke-dash ring draw, check-path draw, sonar ripple, spring-in amount — a still screenshot would feel dead.

---

## Assets the TapPay version depends on (paths to reuse)

| Asset | Path | Role |
|---|---|---|
| **Hand-tap iPhone photo (the "frame")** | `/Users/dennis/Desktop/Projects/Demos/tappay-promo/public/zelios/bg/hands_tap.jpg` (1920×1080) | The real device plate. Screen is deliberately blank → ready for UI comp. **Reusable as-is** for any "tap to pay / hold the phone" beat. |
| Other Zelios bg plates | `public/zelios/bg/{cafe_counter,taipei_bokeh,taipei_day,light_wash,light_streaks}.jpg` | Backdrops for other beats; not phone-specific. |
| SFX | `public/zelios/sfx/{tap,success,impact,whoosh_hi,whoosh_lo,riser}.wav` | `success.wav` is what the ring pop beat-locks to. |
| Fonts | `public/zelios/fonts/*.woff2` (Inter, Poppins, Noto Sans TC, JetBrains Mono) | |

There is **no PNG/3D phone-frame asset and no 3D model** — Technique A draws the frame in CSS; Technique B uses the photo. The only "device frame" asset that exists is the photo.

---

## How to port to Filmo

**Key context:** Filmo's studio (`/Users/dennis/Desktop/Projects/Hackathons/hermes-video-agent/studio/`) ALREADY has a device-mockup archetype: `src/timeline/archetypes/AppleScreenshot.tsx`. Its own header comment even says the browser frame "uses the Foundation's `frameRise` spring (the web analog of TapPay's phone-rise)." So the work is mostly **extend the existing pattern**, not build from zero.

### What Filmo already does (browser/desktop — its primary case)
`AppleScreenshot.tsx` puts a captured PNG inside a brand-tinted **browser card**:
- `BrowserChrome` component (lines ~519–558): 52px bar, three brand-tinted dots, an address pill from `toAddr(data.caption)`.
- Card frame: `frameRise(frame, frameAt, fps)` spring (scale + rise + tilt-settle) — Filmo's analog of TapPay's phone spring.
- Screenshot drop-in: `<Img>` in a clipped window, `clipPath: inset(${maskReveal}% 0 0 0)` top-down reveal over 30f + `shotScale 1.06→1.00` (cubic, NO overshoot, per `feedback_apple_screenshot_animation`) + 14f opacity fade.
- Tie mechanics already present: `highlightBox` (accent ring over `data.focus` normalized rect), `cursorAt` (animated cursor + click ripples via `data.cursorPath`), `zoomPunch` (push toward focus). Premium shadow stack: `0 48px 130px` ambient + `0 10px 30px` contact + `inset 0 1px 0 rgba(255,255,255,0.9)` top highlight. `breathDrift` keeps held frames alive.

This is already a solid browser mockup. The two upgrades worth porting from TapPay are **(1) the photo-composite device option** and **(2) richer "alive" detail**.

### Recipe 1 (highest value, lowest effort): drop a captured product screenshot INTO Filmo's browser frame
This is essentially done. To wire a screenshot in:
```ts
// SceneData fields AppleScreenshot already consumes:
{
  archetype: "screenshot",
  layout: "split",            // text-left / browser-right (or "centered")
  imageSrc: "shots/foo.png",  // resolved via resolveSrc -> staticFile under studio/public/
  caption: "https://foo.com", // becomes the address-bar pill
  headline: "...", punchWord: "...", supporting: "...",
  focus: { x, y, w, h, label }, // OPTIONAL: normalized 0..1 highlight rect over a named UI element
  cursorPath: [ {at, x, y, click} ], // OPTIONAL normalized cursor move
  zoomTo: { x, y, scale },      // OPTIONAL camera push toward the element
  geo: { cardW, shotH, cardRadius, ... } // OPTIONAL overrides
}
```
The capture pipeline already exists (the `website-to-hyperframes` / hyperframes-capture path + `feedback_brand_chrome_mcp`). Just feed the PNG path as `imageSrc`. **No new code needed for the basic browser-mockup-with-screenshot case.**

To make the browser frame read MORE premium (cheap wins, borrow from TapPay's `PhoneFrame` shadow recipe and the success-ring liveliness):
- Add a faint **screen glare** overlay on the shot window: an absolutely-positioned div with `background: linear-gradient(115deg, rgba(255,255,255,0.10) 0%, transparent 35%)` and a slow `breathDrift`-driven x shift — sells "real glass."
- Keep the existing 3-layer shadow; optionally add a soft floor reflection (a vertically-flipped, low-opacity, gradient-masked copy of the card) for the desktop case.

### Recipe 2 (the TapPay "wow" — photo-composite device): add a `PhotoDevice` archetype/variant
For a real-device beat (e.g. "open this on your phone", a mobile product shot, a tap-to-pay/checkout moment), replicate Technique B as a NEW archetype, e.g. `src/timeline/archetypes/PhotoDevice.tsx`:

1. **Get a screen-ready device photo.** Either reuse `hands_tap.jpg` directly, or generate one (Higgsfield / stock) with a deliberately blank/lit screen at a clean angle. Drop it in `studio/public/devices/`.
2. **Measure the screen quad once.** Open the photo, read the 4 corner pixel coords of the lit screen (TL, TR, BR, BL). Store as scene data: `data.screenQuad: [[x,y]×4]` plus the photo's native `[w,h]`.
3. **Copy the homography helpers verbatim** from `Z5_Montage.tsx` lines ~47–90 (`adj3`, `mul3`, `mulV3`, `basisToPoints`, `matrix3dToQuad`, `bleedQuad`) into Filmo's `src/timeline/motion.ts` — they're framework-agnostic pure functions. Compute `SCREEN_MATRIX = matrix3dToQuad(UI_W, UI_H, bleedQuad(quad, 1.045))`.
4. **Render the device:** full-frame `<Img src={resolveSrc(data.imageSrc)}>` with a gentle grade.
5. **Composite the content** — and here's the Filmo adaptation: Filmo mostly does BROWSER UI, so the "UI" mapped onto the screen can be either (a) a Remotion-built mini-UI (like TapPay's payment card), or (b) **a captured screenshot** `<Img>` of the mobile/responsive site — same `imageSrc` plumbing as `AppleScreenshot`, just sized `UI_W×UI_H` and placed in the `matrix3d`-transformed div instead of a flat browser card. Use `objectFit:cover`, `objectPosition:'top left'`.
6. **Wrap photo + mapped UI in ONE `<AbsoluteFill>`** and apply the rigid wobble + `settle` (copy `BeatTapToPay`'s `wx/wy/wr/settle` block) so they track as one unit. Keep `scale ≥ ~1.015` so the wobble never reveals an edge.
7. **Reuse Filmo's existing motion + tie mechanics** for entry (`frameRise`/`appleRise`), `breathDrift` on hold, exit fade, and — if you want the named-element highlight — `highlightBox`/`cursorAt` placed INSIDE the mapped UI div (it inherits the perspective automatically, exactly like TapPay's `ScreenRipple`).

### Browser-window adaptation note (Filmo's actual default)
Since Filmo is desktop/browser-first, **Recipe 1 is the default** and Recipe 2 is the occasional "real-feel" beat. The homography trick (Recipe 2) also generalizes to a tilted/3D browser window: instead of a real photo, you can `matrix3d`-map the browser card itself onto an arbitrary quad to get an angled "floating browser in space" look — but that's a stylistic upgrade, not required. For most browser product UI, the existing flat `AppleScreenshot` split card + the glare/reflection polish from Recipe 1 is the right call; reach for the photo-composite only when you specifically want the photoreal "device in a real environment" wow that Dennis loved.

### Files to touch in Filmo for the port
- `studio/src/timeline/motion.ts` — add the 6 homography helpers (pure functions, lift verbatim from `Z5_Montage.tsx`).
- `studio/src/timeline/archetypes/PhotoDevice.tsx` — new archetype for Recipe 2 (model on `BeatTapToPay` + reuse `frameRise`/`breathDrift`/`highlightBox`/`cursorAt`).
- `studio/src/timeline/archetypes/AppleScreenshot.tsx` — optional polish (screen glare overlay, floor reflection) for Recipe 1.
- `studio/public/devices/` — drop the screen-ready device photo (reuse TapPay's `hands_tap.jpg` to start).
- Register the new archetype wherever Filmo maps `archetype` → component (the same place `AppleScreenshot` is registered), and add the `screenQuad` field to `SceneData` types.

---

## One-line recommendation
The look Dennis loved = **real device photo + a Remotion (or screenshot) UI perspective-mapped onto the real screen via a CSS `matrix3d` homography, wobbled as one rigid group, with beat-locked on-screen animation.** Filmo already has the browser-card half of this (`AppleScreenshot.tsx`); port the homography helpers + a `PhotoDevice` archetype to get the photoreal device beat, and reuse `hands_tap.jpg` as the first plate.
