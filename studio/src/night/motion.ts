// Engineered Night motion vocabulary (spec §6) — the measured atoms, expressed as
// pure frame math so every render is deterministic.
//
//   pop        the atomic appearance: scale 0.92→1.0 + fade, 180–260ms, cubic ease-out
//   ladder     successive pops spaced 0.28–0.30s (musical half-beats at ~100 BPM)
//   glide      camera moves 0.8–1.4s, strong ease-in-out, one axis dominant
//   microDrift ≤1% scale breath during holds so no frame is frozen
import { Easing, interpolate } from "remotion";

export const POP_MS_DEFAULT = 220;
export const LADDER_SPACING_S = 0.29;
export const GLIDE_EASE = Easing.bezier(0.65, 0, 0.35, 1);
const POP_EASE = Easing.out(Easing.cubic);

export interface PopState {
  opacity: number;
  scale: number;
}

/** Appearance pop. `start` is the local frame the element begins arriving. */
export function pop(frame: number, start: number, fps: number, ms: number = POP_MS_DEFAULT): PopState {
  const dur = Math.max(2, Math.round((ms / 1000) * fps));
  const t = interpolate(frame, [start, start + dur], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: POP_EASE,
  });
  return { opacity: t, scale: 0.92 + 0.08 * t };
}

/** Frame offset for the i-th rung of a chip/icon ladder. */
export function ladderStart(i: number, fps: number, spacingS: number = LADDER_SPACING_S): number {
  return Math.round(i * spacingS * fps);
}

/** ≤1% scale breath during holds — the camera (and held elements) never freeze. */
export function microDrift(frame: number, fps: number, amount: number = 0.006): number {
  return 1 + amount * Math.sin((frame / fps) * Math.PI * 0.45);
}

/** Typed-line reveal for the terminal: returns how many characters of `text`
 *  are visible at `frame` when the line starts typing at `start`. */
export function typedChars(frame: number, start: number, fps: number, text: string, cps: number = 34): number {
  if (frame <= start) return 0;
  return Math.min(text.length, Math.floor(((frame - start) / fps) * cps));
}

/** Camera glide between two values (one axis), 0.8–1.4s with the strong ease. */
export function glide(
  frame: number,
  start: number,
  fps: number,
  from: number,
  to: number,
  durationS: number = 1.1,
): number {
  const dur = Math.max(4, Math.round(durationS * fps));
  return interpolate(frame, [start, start + dur], [from, to], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: GLIDE_EASE,
  });
}
