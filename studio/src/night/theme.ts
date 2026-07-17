// Engineered Night tokens, derived from the SAME brand theme the classic Timeline
// receives. The stage is constant (black world, white ink); the ONLY brand-variable
// token is ACCENT — spec §3's "accent is a slot, not a color". Mint appears only
// when the subject brand's own accent is mint.
import type { Theme } from "../timeline/types";
import { NIGHT_BODY, NIGHT_DISPLAY, NIGHT_MONO } from "./fonts";

export interface NightTokens {
  stage: string;
  panel: string;
  panelLine: string;
  grid: string;
  ink: string;
  inkMuted: string;
  inkDim: string;
  accent: string;
  accentSoft: string; // ~10% fill for chips / highlight bands
  accentGlow: string; // ~20% for the atmospheric glow
  fontDisplay: string;
  fontBody: string;
  fontMono: string;
}

function hexToRgba(hex: string, alpha: number): string {
  const m = /^#?([0-9a-f]{6})$/i.exec((hex || "").trim());
  if (!m) return `rgba(255,255,255,${alpha})`;
  const n = parseInt(m[1], 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${alpha})`;
}

/** A stage-safe accent: on a black stage a near-black or muddy-dark brand accent
 *  disappears, so lift it to a floor of perceptual brightness while keeping hue. */
function stageSafeAccent(hex: string): string {
  const m = /^#?([0-9a-f]{6})$/i.exec((hex || "").trim());
  if (!m) return "#7DA7FF";
  const n = parseInt(m[1], 16);
  const r = (n >> 16) & 255;
  const g = (n >> 8) & 255;
  const b = n & 255;
  const lum = 0.2126 * r + 0.7152 * g + 0.0722 * b;
  if (lum >= 70) return `#${m[1]}`;
  // Blend toward white just enough to clear the floor (keeps the hue family).
  const t = Math.min(0.6, (70 - lum) / 255 + 0.25);
  const lift = (c: number) => Math.round(c + (255 - c) * t);
  return `rgb(${lift(r)},${lift(g)},${lift(b)})`;
}

export function nightTokens(theme: Theme): NightTokens {
  const accent = stageSafeAccent(theme.accent);
  return {
    stage: "#000000",
    panel: "#161616",
    panelLine: "rgba(255,255,255,0.08)",
    grid: "rgba(51,51,51,0.7)",
    ink: "#FFFFFF",
    inkMuted: "rgba(255,255,255,0.62)",
    inkDim: "rgba(255,255,255,0.38)",
    accent,
    accentSoft: accent.startsWith("#") ? hexToRgba(accent, 0.1) : accent.replace("rgb(", "rgba(").replace(")", ",0.1)"),
    accentGlow: accent.startsWith("#") ? hexToRgba(accent, 0.2) : accent.replace("rgb(", "rgba(").replace(")", ",0.2)"),
    fontDisplay: NIGHT_DISPLAY,
    fontBody: NIGHT_BODY,
    fontMono: theme.fontMono || NIGHT_MONO,
  };
}

// The type scale — exactly six sizes across the film (spec §4).
export const NIGHT_TYPE = {
  display: 96, // hero headline
  section: 64, // section headlines
  lede: 24, // supporting lines / quote body
  label: 16, // chips, CTA, attributions
  eyebrow: 12, // ALL-CAPS eyebrows
  mono: 20, // terminal lines
} as const;
