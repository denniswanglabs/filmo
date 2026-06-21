// Shared kinetic-light motion vocabulary, ported from the Orinovate
// kinetic-light scenes (IntroScene / HookScene / ReviewApproveScene). Every
// value is frame-derived and deterministic — NO Math.random / Date — so renders
// are reproducible.
import { Easing, interpolate } from "remotion";

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
