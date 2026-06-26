// APPLE-HERO archetype — product-as-hero. Maps a scene role: the OPENING /
// product-reveal beat. An Apple keynote lockup on a soft four-color mesh:
//   - a kicker eyebrow rises (ease-out-quart, NOT spring),
//   - the title slides up behind a clip mask (slide-up title with mask),
//   - the punch word lands in the brand accent,
//   - a glass "product plate" settles under it with an edge-light sweep,
//   - a subtitle settles, then the whole lockup keeps a subtle breath drift.
//
// Apple iOS motion only: cubic ease-out arrivals, NO springs, NO overshoot
// (per feedback_apple_screenshot_animation). Palette comes from props.theme so
// the style-fill engine can recolor it per brand (navy / lime / coral).
//
// Reveals fire on the scene's CUE frames (relative to scene in_frame):
//   kicker-in -> kicker, title-in -> title slide-up, punch -> accent word,
//   product-in -> glass product plate + edge sweep, subtitle-in -> subtitle.
import React from "react";
import { AbsoluteFill, Img, interpolate, staticFile, useCurrentFrame } from "remotion";
import type { Cue, SceneData, Theme } from "../types";
import {
  appleMaskRise,
  appleRise,
  breathDrift,
  EASE_IN_OUT_CUBIC,
  EASE_OUT_QUART,
  alphaHex,
  actNum,
  actLabel,
  splitToLines,
} from "../motion";

const cueAt = (cues: Cue[], label: string, fallback: number) =>
  cues.find((c) => c.label === label)?.at_frame ?? fallback;

// Resolve a public-relative logo path. http/leading-slash pass through. When a
// `resolve` (the Timeline assetBaseUrl seam) is passed, public-relative names
// resolve against the hosted bucket so the EDITOR PREVIEW shows the real logo
// (matches how screenshots/VO/music/walkthrough already resolve); absent it
// falls back to staticFile (the studio render path). ABSENT theme.logoSrc =>
// the lockup/corner mark degrades to wordmark.
const resolveLogo = (path: string, resolve?: (p: string) => string): string =>
  path.startsWith("http") || path.startsWith("/")
    ? path
    : resolve
      ? resolve(path)
      : staticFile(path);

// Split a title around its punch word so the punch word can be accent-colored.
const splitPunch = (title: string, punch?: string) => {
  if (!punch || !title.includes(punch)) return { pre: title, hit: "", post: "" };
  const i = title.indexOf(punch);
  return { pre: title.slice(0, i), hit: punch, post: title.slice(i + punch.length) };
};

export const AppleHero: React.FC<{
  data: SceneData;
  cues: Cue[];
  theme: Theme;
  durationInFrames: number;
  // 1-based act index among content-beat scenes (-1 = no badge)
  actIndex?: number;
  // OPTIONAL: scene id, threaded from Timeline for click-to-select addressing.
  sceneId?: string;
  // OPTIONAL: the Timeline assetBaseUrl seam, so the brand logo resolves from the
  // hosted bucket in the editor preview (absent in the studio render → staticFile).
  resolveSrc?: (path: string) => string;
}> = ({ data, cues, theme, durationInFrames, actIndex = -1, sceneId, resolveSrc }) => {
  const frame = useCurrentFrame();

  // OPTIONAL geometry overrides (data.geo). `data.geo?.KEY ?? LITERAL` so when geo
  // is absent (every production run) the original literal is used and output is
  // byte-identical. The visual editor writes these keys.
  const geo = data.geo;
  const titleFontSize = geo?.titleFontSize ?? 140;
  const subtitleFontSize = geo?.subtitleFontSize ?? 32;

  const kickerAt = cueAt(cues, "kicker-in", 8);
  const titleAt = cueAt(cues, "title-in", 30);
  const punchAt = cueAt(cues, "punch", titleAt + 18);
  const productAt = cueAt(cues, "product-in", titleAt + 30);
  const subAt = cueAt(cues, "subtitle-in", productAt + 22);

  const kicker = appleRise(frame, kickerAt, 20, 18);
  // Title staged reveal: split into display lines; each line slides up in sequence.
  // AppleHero uses appleMaskRise (clip-mask + ease-out-quart) per the Apple pattern.
  const TITLE_STAGGER = 18;
  const titleTextRaw = (data.title ?? "").trim();
  const titleLines = splitToLines(titleTextRaw, 18);
  const sub = appleRise(frame, subAt, 24, 22);

  // Accent punch word: fades to its accent color on the punch cue (cubic).
  const punchP = interpolate(frame, [punchAt, punchAt + 16], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: EASE_OUT_QUART,
  });

  // Glass product plate: arrives (ease-out-quart) on product-in.
  const plate = appleRise(frame, productAt, 40, 26);
  // Edge-light sweep: a specular conic gradient that travels around the plate
  // once after it lands (PATTERNS "edge light sweep"). ~90f single rotation.
  const sweepAngle = interpolate(frame, [productAt + 6, productAt + 96], [0, 360], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: EASE_IN_OUT_CUBIC,
  });

  // Breath drift on the settled lockup (tiny, keeps the hold alive).
  const breath = breathDrift(frame, subAt + 22, 2.5, 100);

  // Clean exit drift over the last 14 frames so scenes hand off.
  const exitFade = interpolate(frame, [durationInFrames - 14, durationInFrames], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: EASE_IN_OUT_CUBIC,
  });

  // Act badge label from kicker (≤2 words, all-caps).
  const badgeLabel = actIndex > 0 ? actLabel(data.kicker) : "";
  const badgeText = actIndex > 0 ? `${actNum(actIndex)}${badgeLabel ? ` — ${badgeLabel}` : ""}` : "";

  return (
    <AbsoluteFill
      style={{
        backgroundColor: theme.bg,
        fontFamily: theme.fontDisplay,
        opacity: exitFade,
      }}
    >
      {/* Apple four-color mesh — gives the glass plate something to refract.
          Tints are derived from the brand theme so it recolors per brand. */}
      <AbsoluteFill
        style={{
          background: `
            radial-gradient(ellipse 900px 680px at 22% 24%, ${theme.navy}1f 0%, transparent 58%),
            radial-gradient(ellipse 1000px 760px at 80% 78%, ${theme.accent}1a 0%, transparent 58%),
            radial-gradient(ellipse 680px 560px at 88% 18%, ${theme.navyBright}14 0%, transparent 60%),
            ${theme.bg}
          `,
        }}
      />

      <AbsoluteFill
        style={{
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: 30,
          transform: `translateY(${breath}px)`,
        }}
      >
        {/* Brand lockup — real captured logo (theme.logoSrc) when present, else
            the wordmark text. Rises with the kicker. */}
        {(theme.logoSrc ?? "").trim() ? (
          <div
            data-scene-id={sceneId}
            data-field="logo"
            style={{
              opacity: kicker.opacity,
              transform: kicker.transform,
              height: 60,
              display: "flex",
              alignItems: "center",
            }}
          >
            <Img
              src={resolveLogo((theme.logoSrc ?? "").trim(), resolveSrc)}
              style={{ height: "100%", width: "auto", objectFit: "contain", display: "block" }}
            />
          </div>
        ) : (
          <div
            data-scene-id={sceneId}
            data-field="logo"
            style={{
              opacity: kicker.opacity,
              fontSize: 40,
              fontWeight: 600,
              letterSpacing: "-0.02em",
              color: theme.navy,
            }}
          >
            {theme.wordmark}
          </div>
        )}

        {/* Kicker eyebrow */}
        <div
          data-scene-id={sceneId}
          data-field="kicker"
          style={{
            opacity: kicker.opacity,
            transform: kicker.transform,
            fontSize: 24,
            fontWeight: 600,
            letterSpacing: "0.32em",
            textTransform: "uppercase",
            color: theme.textDim,
            fontFamily: theme.fontMono,
          }}
        >
          {data.kicker}
        </div>

        {/* Title — staged line-by-line reveal (D2 pacing — R4).
            Each line uses appleMaskRise (clip mask + ease-out-quart) staggered by
            18f. Two-tone: pending lines render at textDim; active/arrived lines at
            full text color. Punch word gets accent color on its line. */}
        <div
          data-scene-id={sceneId}
          data-field="title"
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            gap: 2,
          }}
        >
          {titleLines.map((line, li) => {
            const lineStart = titleAt + li * TITLE_STAGGER;
            const m = appleMaskRise(frame, lineStart, 56, 28);
            // Two-tone: colorP < 0.5 → pending (textDim), ≥ 0.5 → active (text).
            const lineColor = m.p > 0.5 ? theme.text : theme.textDim;
            const { pre, hit, post } = splitPunch(line, data.punchWord);
            return (
              <div
                key={li}
                style={{
                  opacity: m.opacity,
                  clipPath: m.clipPath,
                  transform: m.transform,
                  fontSize: titleFontSize,
                  fontWeight: 700,
                  letterSpacing: "-0.03em",
                  lineHeight: 1.02,
                  color: lineColor,
                  textAlign: "center",
                  maxWidth: 1500,
                }}
              >
                {pre}
                {hit && (
                  <span
                    style={{
                      color: punchP > 0.5 ? theme.accent : theme.text,
                      textShadow: `0 0 ${36 * punchP}px ${theme.accent}${alphaHex(punchP * 0.45)}`,
                    }}
                  >
                    {hit}
                  </span>
                )}
                {post}
              </div>
            );
          })}
        </div>

        {/* Glass product plate with edge-light sweep */}
        {data.product && (
          <div
            data-scene-id={sceneId}
            data-field="product"
            style={{
              opacity: plate.opacity,
              transform: plate.transform,
              position: "relative",
              marginTop: 8,
              padding: "20px 44px",
              borderRadius: 22,
              backgroundColor: `${theme.bgCardRaised}`,
              border: `1px solid ${theme.border}`,
              boxShadow: [
                "0 22px 60px rgba(15,35,56,0.10)",
                "inset 0 1px 0 rgba(255,255,255,0.9)",
                "inset 0 -1px 0 rgba(0,0,0,0.04)",
              ].join(", "),
              fontSize: 30,
              fontWeight: 600,
              letterSpacing: "-0.015em",
              color: theme.text,
              overflow: "hidden",
            }}
          >
            {/* edge-light sweep overlay */}
            <div
              style={{
                position: "absolute",
                inset: 0,
                borderRadius: 22,
                background: `conic-gradient(from ${sweepAngle}deg at 50% 50%,
                  transparent 0%, transparent 42%,
                  ${theme.accent}cc 50%,
                  transparent 58%, transparent 100%)`,
                mixBlendMode: "overlay",
                pointerEvents: "none",
              }}
            />
            <span style={{ position: "relative" }}>{data.product}</span>
          </div>
        )}

        {/* Accent underline rule — always visible on any background (light or dark).
            Appears after the last title line arrives (fires at punchAt). Width eases
            so it reads as part of the settled lockup. */}
        <div
          style={{
            opacity: interpolate(frame, [punchAt, punchAt + 16], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: EASE_OUT_QUART }),
            width: interpolate(punchP, [0, 1], [80, 100]),
            height: 4,
            borderRadius: 2,
            backgroundColor: theme.accent,
            boxShadow: `0 0 ${14 * punchP}px ${theme.accent}88`,
            marginTop: -8,
          }}
        />

        {/* Subtitle */}
        <div
          data-scene-id={sceneId}
          data-field="subtitle"
          style={{
            opacity: sub.opacity,
            transform: sub.transform,
            fontSize: subtitleFontSize,
            fontWeight: 400,
            color: theme.textMuted,
            maxWidth: 1100,
            textAlign: "center",
            letterSpacing: "-0.01em",
          }}
        >
          {data.subtitle}
        </div>
      </AbsoluteFill>

      {/* Numbered act badge — top-left eyebrow: "NN — LABEL".
          Rendered LAST (highest z-order) so it paints over the mesh + lockup. */}
      {actIndex > 0 && (
        <div
          style={{
            position: "absolute",
            left: 60,
            top: 52,
            opacity: kicker.opacity,
            fontSize: 22,
            fontWeight: 700,
            letterSpacing: "0.18em",
            textTransform: "uppercase",
            color: theme.accent,
            fontFamily: theme.fontMono,
          }}
        >
          {badgeText}
        </div>
      )}
    </AbsoluteFill>
  );
};
