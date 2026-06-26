// Shared kinetic-light motion vocabulary, ported from the Orinovate
// kinetic-light scenes (IntroScene / HookScene / ReviewApproveScene). Every
// value is frame-derived and deterministic — NO Math.random / Date — so renders
// are reproducible.
import { Easing, interpolate, spring } from "remotion";

// Clamped linear ease between two frames (the kinetic-light default).
export const ease = (frame: number, a: number, b: number, from: number, to: number) =>
  interpolate(frame, [a, Math.max(a + 1, b)], [from, to], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

// Force an input-frame keyframe array to be strictly monotonically increasing.
// Cue frames + scene-length-derived offsets can collide on short scenes; this
// keeps interpolate() valid (>= +1 between every stop) without dropping beats.
export const monoFrames = (frames: number[]) => {
  const out = [...frames];
  for (let i = 1; i < out.length; i++) {
    if (out[i] <= out[i - 1]) out[i] = out[i - 1] + 1;
  }
  return out;
};

// interpolate with the input keyframes auto-corrected to be monotonic + clamped.
export const interpClamp = (frame: number, frames: number[], values: number[]) =>
  interpolate(frame, monoFrames(frames), values, {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

// A reveal that fades + rises from `dy`px over `dur` frames, starting at `at`.
// `at` is the cue frame (relative to the scene). Returns inline style fragments.
export const reveal = (frame: number, at: number, dy = 18, dur = 16) => ({
  opacity: ease(frame, at, at + dur, 0, 1),
  transform: `translateY(${ease(frame, at, at + dur, dy, 0)}px)`,
});

// The "tail animation": a slow multi-keyframe pulse so a HELD element never
// freezes after its entrance (mirrors HookScene's secGlow / ReviewApprove's
// accentShipPulse). Cycles gently around 1.0 across the held tail.
export const tailPulse = (frame: number, start: number, end: number, amp = 0.03) => {
  const span = Math.max(1, end - start);
  // four soft beats across the tail
  const t = (frame - start) / span;
  return 1 + Math.sin(t * Math.PI * 8) * amp * ease(frame, start, start + 12, 0, 1);
};

// A held-element glow that pulses through the tail (HookScene.secGlow shape).
export const tailGlow = (frame: number, start: number, end: number) => {
  const span = Math.max(1, end - start);
  const t = (frame - start) / span;
  return 0.55 + 0.3 * (0.5 + 0.5 * Math.sin(t * Math.PI * 6)) * ease(frame, start, start + 14, 0, 1);
};

// Hex accent + 2-digit alpha (0..1 -> "00".."ff"), for textShadow glow strings.
export const alphaHex = (a: number) =>
  Math.round(Math.max(0, Math.min(1, a)) * 255)
    .toString(16)
    .padStart(2, "0");

// ---------------------------------------------------------------------------
// Apple-style motion vocabulary (iOS cubic-ease curves — NOT springs).
// PATTERNS.md "iOS motion curves": ease-out-quart for arrivals, a steeper
// curve for transitions. Per feedback_apple_screenshot_animation the
// shrink/arrival uses CUBIC EASE-OUT with NO overshoot.
// ---------------------------------------------------------------------------

// Apple ease-out-quart — the keynote arrival curve (text, cards settling).
export const EASE_OUT_QUART = Easing.bezier(0.22, 1, 0.36, 1);
// Steeper cubic for continuous translations / camera-style moves.
export const EASE_IN_OUT_CUBIC = Easing.bezier(0.65, 0, 0.35, 1);
// Pure cubic ease-out (1 - (1-t)^3) — the screenshot-shrink curve, no overshoot.
export const easeOutCubic = (t: number) => 1 - Math.pow(1 - Math.max(0, Math.min(1, t)), 3);

// An Apple arrival: fade + slide-up from `dy`px over `dur` frames at `at`,
// using ease-out-quart (NOT the linear kinetic-light `reveal`). Returns inline
// style fragments. This is the Apple analog of motion.reveal().
export const appleRise = (frame: number, at: number, dy = 36, dur = 24) => {
  const p = interpolate(frame, [at, at + dur], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: EASE_OUT_QUART,
  });
  return { opacity: p, transform: `translateY(${(1 - p) * dy}px)`, p };
};

// Slide-up title with clip mask (PATTERNS "slide-up title with mask"): the
// bottom-revealed keynote title. Returns clipPath + translateY + opacity.
export const appleMaskRise = (frame: number, at: number, dy = 48, dur = 26) => {
  const p = interpolate(frame, [at, at + dur], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: EASE_OUT_QUART,
  });
  return {
    opacity: p,
    clipPath: `inset(0 0 ${(1 - p) * 100}% 0)`,
    transform: `translateY(${(1 - p) * dy}px)`,
    p,
  };
};

// Breath drift (PATTERNS "breath drift"): the tiny ±amp px oscillation that
// keeps a settled Apple composition alive. Starts at `settle`, deterministic.
export const breathDrift = (frame: number, settle: number, amp = 2, period = 90) =>
  frame > settle ? Math.sin(((frame - settle) / period) * Math.PI * 2) * amp : 0;

// ---------------------------------------------------------------------------
// Staged line-by-line / word-by-word reveal helpers (D2 pacing — R4)
// ---------------------------------------------------------------------------

// Split a title string into display lines for staged reveals.
// Respects explicit "\n" breaks first; otherwise splits on word boundaries
// targeting ~maxCharsPerLine characters per line (max 3 lines).
// Short titles (≤ maxCharsPerLine chars, ≤ 3 words) return as a single line.
export const splitToLines = (text: string, maxCharsPerLine = 22): string[] => {
  const trimmed = (text ?? "").trim();
  if (!trimmed) return [];
  // Explicit newlines win.
  if (trimmed.includes("\n")) return trimmed.split("\n").map((l) => l.trim()).filter(Boolean).slice(0, 3);
  const words = trimmed.split(/\s+/);
  // Short text or few words → single line.
  if (words.length <= 3 || trimmed.length <= maxCharsPerLine) return [trimmed];
  // Split into 2 lines at the word closest to 50% of total chars.
  const half = Math.ceil(trimmed.length / 2);
  let acc = 0;
  let splitAt = Math.floor(words.length / 2);
  for (let i = 0; i < words.length - 1; i++) {
    acc += words[i].length + 1;
    if (acc >= half) { splitAt = i + 1; break; }
  }
  const lineA = words.slice(0, splitAt).join(" ");
  const lineB = words.slice(splitAt).join(" ");
  // If lineB is long, try to split it again (max 3 lines total).
  if (lineB.length > maxCharsPerLine + 8) {
    const sub = lineB.split(/\s+/);
    const subSplit = Math.ceil(sub.length / 2);
    return [lineA, sub.slice(0, subSplit).join(" "), sub.slice(subSplit).join(" ")];
  }
  return [lineA, lineB];
};

// Per-line staged reveal:
//   - before its turn: pending (dim color, fully transparent → still present at 0.18 opacity)
//   - arriving: fades + rises from dy px over dur frames
//   - active: full opacity/color
// Returns { opacity, transform, colorProgress } for the given line index.
// colorProgress 0 = pending dim, 1 = active bright.
//
// stagger: frames between each line's start (default 16f = ~0.53s at 30fps)
// startFrame: when line 0 begins to arrive
export const stagedLine = (
  frame: number,
  lineIndex: number,
  startFrame: number,
  stagger = 16,
  dy = 28,
  dur = 18
) => {
  const lineStart = startFrame + lineIndex * stagger;
  const opacity = ease(frame, lineStart, lineStart + dur, 0, 1);
  const yOffset = ease(frame, lineStart, lineStart + dur, dy, 0);
  // color: arrives → bright; pending (not yet arrived) → dim (0.28 opacity on the text color)
  // We express this as a 0→1 progress the caller uses to lerp color.
  const colorP = ease(frame, lineStart, lineStart + dur, 0, 1);
  return { opacity, transform: `translateY(${yOffset}px)`, colorP };
};

// ---------------------------------------------------------------------------
// Act badge helpers
// ---------------------------------------------------------------------------

// Format a 1-based act index as a zero-padded two-digit string: 1 -> "01", 12 -> "12".
export const actNum = (index: number) => String(Math.max(1, index)).padStart(2, "0");

// Derive a SHORT LABEL (≤2 words, all-caps) from a kicker string.
// e.g. "PRODUCT WALKTHROUGH DEMO" -> "PRODUCT WALKTHROUGH"
export const actLabel = (kicker?: string): string => {
  const raw = (kicker ?? "").trim().toUpperCase();
  if (!raw) return "";
  return raw.split(/\s+/).slice(0, 2).join(" ");
};

// ===========================================================================
// Overhaul motion vocabulary (spec §1). Ported, frame-derived, deterministic.
// REUSES ease / interpClamp / easeOutCubic / EASE_OUT_QUART / EASE_IN_OUT_CUBIC
// / breathDrift above — these add ONLY the named primitives the spec lists as
// gaps. Every helper is a pure function of `frame` (springs are seeded from
// frame + fps), so renders stay reproducible.
// ===========================================================================

// frame-rise (NEW) — the web analog of TapPay's phone-rise, retargeted for a
// browser/UI card. The card springs up from `+dy`px, scales `scaleFrom→1`, and
// settles a small `rotateX` tilt back to flat. Ported spring config from
// IPhoneTapScene.phoneSpring ({damping:16, stiffness:110}); opacity fades over
// `fadeDur` like the reference's [at, at+22] window. Defaults match the spec
// (scale 0.92→1, dy 48, rotateX 6°→0, ~28f settle).
//   frame, at: scene-local cue frame + start; fps: spring seed (from useVideoConfig).
export const frameRise = (
  frame: number,
  at: number,
  fps: number,
  opts: { dy?: number; scaleFrom?: number; tilt?: number; fadeDur?: number } = {}
) => {
  const { dy = 48, scaleFrom = 0.92, tilt = 6, fadeDur = 22 } = opts;
  const s = spring({ frame: frame - at, fps, config: { damping: 16, stiffness: 110 } });
  const opacity = ease(frame, at, at + fadeDur, 0, 1);
  const ty = interpolate(s, [0, 1], [dy, 0]);
  const scale = interpolate(s, [0, 1], [scaleFrom, 1]);
  const rx = interpolate(s, [0, 1], [tilt, 0]);
  return {
    opacity,
    s,
    transform: `perspective(1600px) translateY(${ty}px) rotateX(${rx}deg) scale(${scale})`,
  };
};

// cursor-move (NEW) — port of Orinovate Cursor.tsx. Springs an arrow cursor
// through `keyframes` (card-LOCAL coords; the archetype decides px vs %), and
// emits click ripples (r 6→60, opacity 0.65→0 over 18f) for any keyframe with
// `click` within the last 18 frames. Spring config + ripple curve lifted exactly
// ({damping:14, stiffness:110, mass:0.6}). Returns position + active ripples so
// the caller renders the cursor glyph + ripple <circle>s however it likes.
export type CursorKeyframe = { at: number; x: number; y: number; click?: boolean };
export const cursorAt = (
  frame: number,
  keyframes: CursorKeyframe[],
  fps: number
): { x: number; y: number; ripples: Array<{ at: number; x: number; y: number; r: number; opacity: number }> } => {
  if (!keyframes || keyframes.length === 0) return { x: 0, y: 0, ripples: [] };
  const first = keyframes[0];
  const last = keyframes[keyframes.length - 1];
  let prev = first;
  let next = last;
  for (let i = 0; i < keyframes.length - 1; i++) {
    if (frame >= keyframes[i].at && frame <= keyframes[i + 1].at) {
      prev = keyframes[i];
      next = keyframes[i + 1];
      break;
    }
  }
  if (frame <= first.at) {
    prev = first;
    next = first;
  } else if (frame >= last.at) {
    prev = last;
    next = last;
  }
  const span = Math.max(1, next.at - prev.at);
  const t = (frame - prev.at) / span;
  const eased = spring({ frame: t * fps * 0.6, fps, config: { damping: 14, stiffness: 110, mass: 0.6 } });
  const x = interpolate(eased, [0, 1], [prev.x, next.x]);
  const y = interpolate(eased, [0, 1], [prev.y, next.y]);
  const ripples = keyframes
    .filter((k) => k.click && frame >= k.at && frame < k.at + 18)
    .map((k) => {
      const p = (frame - k.at) / 18;
      return {
        at: k.at,
        x: k.x,
        y: k.y,
        r: interpolate(p, [0, 1], [6, 60]),
        opacity: interpolate(p, [0, 1], [0.65, 0]),
      };
    });
  return { x, y, ripples };
};

// highlight-box (NEW) — a rounded accent ring + tint draws ON over a named UI
// rect: opacity 0→1 over `dur` (EASE_OUT_QUART), HOLDS until `holdEnd`, then
// fades out over `dur`. Pairs with the headline punch noun. Returns the box
// opacity (the archetype owns the rect geometry + stroke/tint styling).
export const highlightBox = (frame: number, at: number, holdEnd: number, dur = 14) => {
  const inP = interpolate(frame, [at, at + dur], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: EASE_OUT_QUART,
  });
  const outP = interpolate(frame, [holdEnd, holdEnd + dur], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: EASE_OUT_QUART,
  });
  return { opacity: Math.min(inP, outP) };
};

// zoom-punch (NEW) — Ken-Burns / CameraRig-style push toward a focus point
// inside a box. `focus` is in NORMALIZED card coords (0..1); the push scales the
// content `1→scale` and translates so the focus point stays toward center, then
// (optionally) eases back after `holdEnd`. Eases with EASE_IN_OUT_CUBIC (24f in
// per spec). Returns a CSS transform string applied to the card content layer
// (transformOrigin should be "0 0" / top-left so the % math is exact).
export const zoomPunch = (
  frame: number,
  at: number,
  focus: { x: number; y: number },
  scale = 1.18,
  opts: { dur?: number; holdEnd?: number; boxW?: number; boxH?: number } = {}
) => {
  const { dur = 24, holdEnd, boxW = 1, boxH = 1 } = opts;
  const inP = interpolate(frame, [at, at + dur], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: EASE_IN_OUT_CUBIC,
  });
  const outP =
    holdEnd != null
      ? interpolate(frame, [holdEnd, holdEnd + dur], [1, 0], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
          easing: EASE_IN_OUT_CUBIC,
        })
      : 1;
  const p = Math.min(inP, outP);
  const s = 1 + (scale - 1) * p;
  // Keep the focus point fixed under the scale (transformOrigin top-left):
  // translate so focus*box stays put as everything scales up around it.
  const tx = (1 - s) * focus.x * boxW;
  const ty = (1 - s) * focus.y * boxH;
  return { transform: `translate(${tx}px, ${ty}px) scale(${s})`, scale: s, p };
};

// counter-roll — a number counts up from `0` (or `from`) to `to` over `dur`,
// EASE_OUT_QUART. Returns the raw number; the caller formats ($, commas, +).
export const rollNumber = (frame: number, at: number, to: number, dur = 26, from = 0): number => {
  const p = interpolate(frame, [at, at + dur], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: EASE_OUT_QUART,
  });
  return from + (to - from) * p;
};

// nfc-ripple (device only) — concentric accent rings scale 0→2.0 & fade,
// staggered 6f per ring index `i`. Curves lifted from IPhoneTapScene
// waveScale/waveOp. Returns { scale, opacity } for ring `i`.
export const nfcRipple = (frame: number, at: number, i: number) => {
  const base = at + i * 6;
  const scale = interpolate(frame, [base, base + 24, base + 54], [0, 1.4, 2.0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const opacity = interpolate(frame, [base, base + 14, base + 44], [0, 0.9, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return { scale, opacity };
};

// approve-chip — a success chip springs in scale 0.6→1 ({damping:11,
// stiffness:200}) with a fade. Ported from IPhoneTapScene approveSpring.
export const approveChip = (frame: number, at: number, fps: number) => {
  const s = spring({ frame: frame - at, fps, config: { damping: 11, stiffness: 200 } });
  return {
    opacity: ease(frame, at, at + 25, 0, 1),
    transform: `scale(${interpolate(s, [0, 1], [0.6, 1])})`,
  };
};
