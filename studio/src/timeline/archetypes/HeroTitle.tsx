// HERO-TITLE archetype — ported from Orinovate kinetic-light IntroScene +
// HookScene. A centered lockup: a kicker eyebrow rises, the title springs in
// (damping 16), the punch word lands in the brand accent with a glow, and a
// subtitle settles under it. A slow breath + glow "tail animation" keeps the
// held frames alive so the scene never freezes on the hold.
//
// Reveals fire on the scene's CUE frames (relative to scene in_frame):
//   kicker-in -> kicker, title-in -> title, punch -> accent glow on punchWord,
//   subtitle-in -> subtitle.
import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import type { Cue, SceneData, Theme } from "../types";
import { ease, alphaHex, interpClamp } from "../motion";

const cueAt = (cues: Cue[], label: string, fallback: number) =>
  cues.find((c) => c.label === label)?.at_frame ?? fallback;

// Split a title around its punch word so the punch word can be accent-colored.
const splitPunch = (title: string, punch?: string) => {
  if (!punch || !title.includes(punch)) return { pre: title, hit: "", post: "" };
  const i = title.indexOf(punch);
  return { pre: title.slice(0, i), hit: punch, post: title.slice(i + punch.length) };
};

export const HeroTitle: React.FC<{
  data: SceneData;
  cues: Cue[];
  theme: Theme;
  durationInFrames: number;
}> = ({ data, cues, theme, durationInFrames }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const kickerAt = cueAt(cues, "kicker-in", 6);
  const titleAt = cueAt(cues, "title-in", 36);
  const punchAt = cueAt(cues, "punch", titleAt + 24);
  const subAt = cueAt(cues, "subtitle-in", punchAt + 20);

  // Title springs in (kinetic-light damping 16) — rise + slight scale overshoot.
  const titleSpring = spring({
    frame: frame - titleAt,
    fps,
    config: { damping: 16, stiffness: 150, mass: 0.8 },
  });
  const titleY = interpolate(titleSpring, [0, 1], [40, 0]);
  const titleScale = interpolate(titleSpring, [0, 0.7, 1], [0.9, 1.04, 1]);
  const titleOpacity = ease(frame, titleAt, titleAt + 16, 0, 1);

  // Punch word: accent glow that pops on the punch cue, then a slow tail pulse
  // (HookScene.secGlow shape) so the held word keeps breathing.
  const punchGlow = interpClamp(
    frame,
    [punchAt, punchAt + 14, punchAt + 40, durationInFrames - 18, durationInFrames],
    [0, 1, 0.55, 0.85, 0.5]
  );

  // Soft radial glow behind the lockup (IntroScene glowPulse) + whole-lockup
  // breath after assembly — the tail animation that prevents a frozen hold.
  const breathe = interpClamp(
    frame,
    [subAt + 14, subAt + 44, durationInFrames - 1],
    [1, 1.015, 1.0]
  );
  const glowPulse = interpClamp(
    frame,
    [titleAt, titleAt + 40, durationInFrames - 1],
    [0.8, 1.2, 0.95]
  );

  // Exit drift over the last 12 frames so scenes hand off cleanly.
  const exitFade = ease(frame, durationInFrames - 12, durationInFrames, 1, 0.0);
  const exitShift = ease(frame, durationInFrames - 12, durationInFrames, 0, -20);

  const kickerOpacity = ease(frame, kickerAt, kickerAt + 14, 0, 1);
  const kickerY = ease(frame, kickerAt, kickerAt + 14, 14, 0);
  const subOpacity = ease(frame, subAt, subAt + 16, 0, 1);
  const subY = ease(frame, subAt, subAt + 16, 14, 0);

  const { pre, hit, post } = splitPunch(data.title ?? "", data.punchWord);

  return (
    <AbsoluteFill
      style={{
        backgroundColor: theme.bg,
        fontFamily: theme.fontDisplay,
        opacity: exitFade,
        transform: `translateY(${exitShift}px)`,
      }}
    >
      {/* Soft brand-navy radial glow behind the lockup */}
      <div
        style={{
          position: "absolute",
          top: "50%",
          left: "50%",
          width: 1200,
          height: 720,
          transform: `translate(-50%, -50%) scale(${glowPulse})`,
          background: `radial-gradient(ellipse, ${theme.navy}22 0%, ${theme.navy}00 65%)`,
        }}
      />
      <div
        style={{
          position: "absolute",
          inset: 0,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: 26,
          transform: `scale(${breathe})`,
        }}
      >
        {/* Wordmark */}
        <div
          style={{
            opacity: kickerOpacity,
            fontSize: 46,
            fontWeight: 600,
            letterSpacing: -1,
            color: theme.navy,
          }}
        >
          {theme.wordmark}
        </div>

        {/* Kicker eyebrow */}
        <div
          style={{
            opacity: kickerOpacity,
            transform: `translateY(${kickerY}px)`,
            fontSize: 26,
            fontWeight: 600,
            letterSpacing: 6,
            textTransform: "uppercase",
            color: theme.textDim,
            fontFamily: theme.fontMono,
          }}
        >
          {data.kicker}
        </div>

        {/* Title with accent punch word */}
        <div
          style={{
            opacity: titleOpacity,
            transform: `translateY(${titleY}px) scale(${titleScale})`,
            fontSize: 132,
            fontWeight: 900,
            letterSpacing: -4,
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
                color: theme.accent,
                textShadow: `0 0 ${48 * punchGlow}px ${theme.accent}${alphaHex(punchGlow * 0.7)}`,
              }}
            >
              {hit}
            </span>
          )}
          {post}
        </div>

        {/* Subtitle */}
        <div
          style={{
            opacity: subOpacity,
            transform: `translateY(${subY}px)`,
            fontSize: 34,
            fontWeight: 400,
            color: theme.textMuted,
            maxWidth: 1100,
            textAlign: "center",
          }}
        >
          {data.subtitle}
        </div>
      </div>
    </AbsoluteFill>
  );
};
