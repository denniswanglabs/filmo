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
import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";
import type { Cue, SceneData, Theme } from "../types";
import {
  appleMaskRise,
  appleRise,
  breathDrift,
  EASE_IN_OUT_CUBIC,
  EASE_OUT_QUART,
  alphaHex,
} from "../motion";

const cueAt = (cues: Cue[], label: string, fallback: number) =>
  cues.find((c) => c.label === label)?.at_frame ?? fallback;

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
}> = ({ data, cues, theme, durationInFrames }) => {
  const frame = useCurrentFrame();

  const kickerAt = cueAt(cues, "kicker-in", 8);
  const titleAt = cueAt(cues, "title-in", 30);
  const punchAt = cueAt(cues, "punch", titleAt + 18);
  const productAt = cueAt(cues, "product-in", titleAt + 30);
  const subAt = cueAt(cues, "subtitle-in", productAt + 22);

  const kicker = appleRise(frame, kickerAt, 20, 18);
  const title = appleMaskRise(frame, titleAt, 56, 28);
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

  const { pre, hit, post } = splitPunch(data.title ?? "", data.punchWord);

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
        {/* Wordmark */}
        <div
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

        {/* Kicker eyebrow */}
        <div
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

        {/* Title — slide-up with clip mask (the Apple keynote title) */}
        <div
          style={{
            opacity: title.opacity,
            clipPath: title.clipPath,
            transform: title.transform,
            fontSize: 140,
            fontWeight: 700,
            letterSpacing: "-0.03em",
            lineHeight: 1.02,
            color: theme.text,
            textAlign: "center",
            maxWidth: 1500,
          }}
        >
          {pre}
          {hit && (
            <span
              style={{
                // ease the punch word from base text color into the brand accent
                color: punchP > 0.5 ? theme.accent : theme.text,
                textShadow: `0 0 ${36 * punchP}px ${theme.accent}${alphaHex(punchP * 0.45)}`,
              }}
            >
              {hit}
            </span>
          )}
          {post}
        </div>

        {/* Glass product plate with edge-light sweep */}
        {data.product && (
          <div
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

        {/* Subtitle */}
        <div
          style={{
            opacity: sub.opacity,
            transform: sub.transform,
            fontSize: 32,
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
    </AbsoluteFill>
  );
};
