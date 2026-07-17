// Engineered Night type system — Manrope (display) + Inter (body), loaded from
// local woff2 in studio/public/fonts (self-contained; no node_modules dependency,
// identical in dev, CI, and the Railway image). Spec §4.
import { continueRender, delayRender, staticFile } from "remotion";

const FACES: Array<[family: string, file: string, weight: string]> = [
  ["Manrope", "fonts/manrope-500.woff2", "500"],
  ["Manrope", "fonts/manrope-600.woff2", "600"],
  ["Manrope", "fonts/manrope-700.woff2", "700"],
  ["Inter", "fonts/inter-400.woff2", "400"],
  ["Inter", "fonts/inter-500.woff2", "500"],
  ["Inter", "fonts/inter-600.woff2", "600"],
];

let loaded = false;

/** Load the Night faces once per page; render is delayed until they resolve so
 *  headlines never rasterize in a fallback font. Safe to call from every Night
 *  component — subsequent calls are no-ops. */
export function ensureNightFonts(): void {
  if (loaded || typeof document === "undefined") return;
  loaded = true;
  const handle = delayRender("night-fonts");
  Promise.all(
    FACES.map(([family, file, weight]) => {
      const face = new FontFace(
        family,
        `url(${staticFile(file)}) format('woff2')`,
        { weight, style: "normal" },
      );
      return face.load().then((f) => document.fonts.add(f));
    }),
  )
    .catch(() => {
      /* a failed face falls back to the stack below — never block the render */
    })
    .finally(() => continueRender(handle));
}

export const NIGHT_DISPLAY = `Manrope, Inter, -apple-system, sans-serif`;
export const NIGHT_BODY = `Inter, -apple-system, sans-serif`;
export const NIGHT_MONO = `"SF Mono", "JetBrains Mono", Menlo, Consolas, monospace`;
