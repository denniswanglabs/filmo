// APPLE-STATEMENT archetype — the big editorial statement beat. Maps a scene
// role: the THESIS / value-statement / CTA-lead-in beat. A large multi-line
// editorial wordmark slides up line-by-line behind a clip mask (Apple keynote
// title), one chosen line drawn in the brand accent, then the settled
// statement keeps a subtle breath drift so the held frames never freeze. An
// optional small muted footnote settles underneath.
//
// Apple iOS motion only: cubic ease-out arrivals, NO springs, NO overshoot
// (per feedback_apple_screenshot_animation). Palette from props.theme so the
// style-fill engine recolors per brand.
//
// Reveals fire on the scene's CUE frames (relative to scene in_frame):
//   line-1..line-N -> each statement line slides up, footnote-in -> footnote.
import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";
import type { Cue, SceneData, Theme } from "../types";
import { appleMaskRise, appleRise, breathDrift, EASE_OUT_QUART } from "../motion";

const cueAt = (cues: Cue[], label: string, fallback: number) =>
  cues.find((c) => c.label === label)?.at_frame ?? fallback;

export const AppleStatement: React.FC<{
  data: SceneData;
  cues: Cue[];
  theme: Theme;
  durationInFrames: number;
  // OPTIONAL: scene id, threaded from Timeline for click-to-select addressing.
  sceneId?: string;
}> = ({ data, cues, theme, durationInFrames, sceneId }) => {
  const frame = useCurrentFrame();

  // OPTIONAL geometry overrides (data.geo). `data.geo?.KEY ?? LITERAL` so when geo
  // is absent (every production run) the original literal is used and output is
  // byte-identical. The visual editor writes these keys.
  const geo = data.geo;
  const statementFontSize = geo?.statementFontSize ?? 116;

  // accept either `lines` (multi-line) or a single `statement`.
  const lines = data.lines ?? (data.statement ? [data.statement] : []);
  const accentLine = data.accentLine ?? -1;

  // each line slides up on its own cue (line-1..line-N); fallback staggers.
  const lineAt = (i: number) => cueAt(cues, `line-${i + 1}`, 8 + i * 16);
  const lastLineAt = lines.length ? lineAt(lines.length - 1) : 8;
  const footAt = cueAt(cues, "footnote-in", lastLineAt + 24);

  const foot = appleRise(frame, footAt, 18, 20);

  // breath drift on the settled statement (PATTERNS "breath drift", tiny).
  const breath = breathDrift(frame, lastLineAt + 26, 3, 100);

  // soft radial glow that swells under the statement after it lands.
  const glow = interpolate(
    frame,
    [lineAt(0), lineAt(0) + 40, durationInFrames - 1],
    [0.6, 1.05, 0.9],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  const exitFade = interpolate(frame, [durationInFrames - 14, durationInFrames], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: EASE_OUT_QUART,
  });

  return (
    <AbsoluteFill
      style={{
        backgroundColor: theme.bg,
        fontFamily: theme.fontDisplay,
        opacity: exitFade,
      }}
    >
      {/* soft brand-accent radial glow behind the statement */}
      <div
        style={{
          position: "absolute",
          top: "50%",
          left: "50%",
          width: 1300,
          height: 760,
          transform: `translate(-50%, -50%) scale(${glow})`,
          background: `radial-gradient(ellipse, ${theme.accent}1a 0%, ${theme.accent}00 64%)`,
        }}
      />

      <AbsoluteFill
        style={{
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: 6,
          transform: `translateY(${breath}px)`,
        }}
      >
        {/* Statement plate — the multi-line editorial wordmark. Wrapped in a
            selectable container so a click on any line selects the statement text. */}
        <div
          data-scene-id={sceneId}
          data-field="statement"
          style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 6 }}
        >
          {lines.map((line, i) => {
            const m = appleMaskRise(frame, lineAt(i), 56, 28);
            const isAccent = i === accentLine;
            return (
              <div
                key={i}
                style={{
                  opacity: m.opacity,
                  clipPath: m.clipPath,
                  transform: m.transform,
                  fontSize: statementFontSize,
                  fontWeight: 700,
                  letterSpacing: "-0.03em",
                  lineHeight: 1.04,
                  textAlign: "center",
                  maxWidth: 1600,
                  color: isAccent ? theme.accent : theme.text,
                }}
              >
                {line}
              </div>
            );
          })}
        </div>

        {data.footnote && (
          <div
            data-scene-id={sceneId}
            data-field="footnote"
            style={{
              opacity: foot.opacity,
              transform: foot.transform,
              marginTop: 36,
              fontSize: 28,
              fontWeight: 500,
              letterSpacing: "0.04em",
              color: theme.textDim,
              fontFamily: theme.fontMono,
            }}
          >
            {data.footnote}
          </div>
        )}
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
