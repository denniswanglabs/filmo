// R2-VISUAL — Luceo-light theme normalizer (spec §0/§3 light treatment).
//
// WHY THIS EXISTS: the R1 render came out dark navy. The pipeline (style_fill)
// emits an INVERTED theme for Stripe — bg `#0A2540` (ink-as-page), text `#FFFFFF`,
// navy `#80E9FF` (cyan) — so every archetype paints a dark page even though the
// canonical Orinovate/TapPay bar is a near-white `#F6F9FC` page with dark ink.
//
// Rather than rely on the python pipeline emitting a light theme (R2-CONTENT's
// domain), we normalize the theme ONCE at the timeline seam (Timeline.tsx) before
// it flows to any archetype. Every archetype reads `theme.bg`/`theme.text`/etc.,
// so fixing the tokens here fixes ALL scenes' background, ink, cards, and blooms
// in one place — the light/dark treatment, nothing else.
//
// BACKWARD-COMPATIBLE: a theme that is ALREADY light (light `bg`) passes through
// untouched; only a dark-`bg` theme is remapped. The brand `accent` is ALWAYS
// preserved (coral/Stripe-purple stays). Pure function of the input theme.

import type { Theme } from "./types";

// Canonical Luceo-light palette (Stripe-tuned defaults; spec §3 §0). These are the
// neutral page/ink/card tokens; the brand `accent` is taken from the incoming theme
// and never overwritten.
const LIGHT = {
  bg: "#F6F9FC", // near-white page
  bgCard: "#FFFFFF", // chrome bar / address-pill surface (reads as white card on the page)
  bgCardRaised: "#FFFFFF", // the floating screenshot/glass card surface
  text: "#0A2540", // dark ink for headlines
  textMuted: "#3D4A5C", // supporting copy
  textDim: "#6B7589", // captions / address text / placeholders
  border: "#E5E9F0", // light hairline
};

// A hex (#rgb / #rrggbb) is "dark" when its perceived luminance is low. Used to
// decide whether the incoming theme is inverted (dark page) and needs remapping.
const luminance = (hex: string): number => {
  const h = (hex || "").trim().replace(/^#/, "");
  if (h.length !== 3 && h.length !== 6) return 1; // unknown → treat as light (no remap)
  const full = h.length === 3 ? h.split("").map((c) => c + c).join("") : h;
  const r = parseInt(full.slice(0, 2), 16);
  const g = parseInt(full.slice(2, 4), 16);
  const b = parseInt(full.slice(4, 6), 16);
  if ([r, g, b].some((v) => Number.isNaN(v))) return 1;
  // Rec. 601 perceived luminance, 0..255.
  return 0.299 * r + 0.587 * g + 0.114 * b;
};

const isDark = (hex: string): boolean => luminance(hex) < 110;

// True when a token is the SAME color as the (dark) page bg — the pipeline often
// sets bgCard === bg on a dark theme, which must become a light card, not stay bg.
const sameColor = (a: string, b: string): boolean =>
  (a || "").trim().toLowerCase().replace(/^#/, "") ===
  (b || "").trim().toLowerCase().replace(/^#/, "");

// Normalize a theme to the Luceo-light treatment. If the page bg is already light,
// the theme is returned UNCHANGED (backward-compatible). If it is dark/inverted,
// neutral tokens are remapped to LIGHT while the brand accent + fonts + wordmark +
// logoSrc + music are preserved.
//
// `navy`/`navyBright`/`ok` are the bloom + browser-chrome-dot tints. On a remapped
// light page we re-derive them from the brand accent (and a calm steel-blue) so the
// page breathes with brand-tinted blooms instead of the pipeline's cyan `#80E9FF`,
// which reads wrong on near-white and clashes with Stripe purple.
export const lightenTheme = (theme: Theme): Theme => {
  if (!isDark(theme.bg)) return theme; // already light → leave as-is

  const accent = theme.accent || "#635BFF";
  // Bloom/chrome tints: brand accent + a calm steel-blue secondary. Kept distinct
  // from `accent` so the three chrome dots aren't identical, but on-brand.
  const tintSecondary = "#9DA8C0"; // soft steel-blue (neutral, reads on near-white)

  return {
    ...theme,
    bg: LIGHT.bg,
    bgCard: LIGHT.bgCard,
    // If the pipeline left the raised card light, keep its choice; else force white.
    bgCardRaised: isDark(theme.bgCardRaised) ? LIGHT.bgCardRaised : theme.bgCardRaised,
    text: LIGHT.text,
    textMuted: LIGHT.textMuted,
    textDim: LIGHT.textDim,
    border: LIGHT.border,
    // bloom + chrome-dot tints re-derived from the brand accent (drop the cyan).
    navy: sameColor(theme.navy, theme.bg) || isDark(theme.navy) ? accent : theme.navy,
    navyBright: tintSecondary,
    ok: accent,
    // accent, fonts, wordmark, logoSrc, music: preserved untouched.
  };
};
