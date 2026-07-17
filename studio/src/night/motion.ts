// Engineered Night motion vocabulary (spec §6) — the measured atoms, expressed as
// pure frame math so every render is deterministic.
//
//   pop        the atomic appearance: scale 0.92→1.0 + fade, 180–260ms, cubic ease-out
//   ladder     successive pops spaced 0.28–0.30s (musical half-beats at ~100 BPM)
//   glide      camera moves 0.8–1.4s, strong ease-in-out, one axis dominant
//   microDrift ≤1% scale breath during holds so no frame is frozen
import type { CSSProperties } from "react";
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

// --- Development-pass vocabulary (docs/night-development-pass.md §C) ---------

export interface RiseState extends PopState {
  y: number;
}

/** Second entrance atom: fade + a 14px upward settle (no scale). Sections
 *  alternate pop/rise deterministically so consecutive beats don't rhyme. */
export function rise(frame: number, start: number, fps: number, ms: number = 260): RiseState {
  const dur = Math.max(2, Math.round((ms / 1000) * fps));
  const t = interpolate(frame, [start, start + dur], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: POP_EASE,
  });
  return { opacity: t, scale: 1, y: 14 * (1 - t) };
}

export const riseStyle = (r: RiseState): CSSProperties => ({
  opacity: r.opacity,
  transform: `translateY(${r.y}px)`,
});

/** Count-up progress for a credibility value: 0→1 over `ms`, ease-out, starting
 *  at `start`. The caller formats the number; this is timing only. */
export function countUp(frame: number, start: number, fps: number, ms: number = 700): number {
  const dur = Math.max(2, Math.round((ms / 1000) * fps));
  return interpolate(frame, [start, start + dur], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: POP_EASE,
  });
}

export interface BeatGrid {
  /** Frames from timeline 0 to the first musical beat. */
  phaseFrames: number;
  /** Frames per beat after the per-run trim/atempo mapping. */
  spbFrames: number;
}

/** Snap a frame to the nearest musical beat when one is within `tolerance`
 *  frames; otherwise return the frame unchanged (VO sync always outranks the
 *  grid). No grid -> unchanged. */
export function snapToBeat(frame: number, grid: BeatGrid | undefined, tolerance: number = 4): number {
  if (!grid || !(grid.spbFrames > 1)) return frame;
  const n = Math.round((frame - grid.phaseFrames) / grid.spbFrames);
  const beat = grid.phaseFrames + n * grid.spbFrames;
  return Math.abs(beat - frame) <= tolerance ? Math.max(0, Math.round(beat)) : frame;
}
