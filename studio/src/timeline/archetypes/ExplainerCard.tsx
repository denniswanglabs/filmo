// EXPLAINER-CARD archetype — the never-blank designed card for a CINEMATIC /
// walkthrough / demo beat that gets NO real footage on a $0 / standard run.
// Instead of a flat solid color (the old synth_clip blank), it SHOWS the narrated
// point as on-brand kinetic motion-graphics: a navy left rail (Orinovate sidebar
// motif), a kicker eyebrow, a word-rise title with a blue underline sweep, a
// subtitle, and staggered bullet reveals — each bullet a numbered badge (NO emoji)
// + a capability line parsed from the VO/brief.
//
// Reuses the kinetic-light motion vocabulary (motion.ts) so it matches HeroTitle /
// CardUi exactly. Reveals fire on the scene's CUE frames (relative to in_frame):
//   title-in -> title, subtitle-in -> subtitle, point-1..point-N -> each bullet.
// Sensible fallback cue frames keep it animating even when a scene has no cues.
import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import type { Cue, SceneData, Theme } from "../types";
import { ease, reveal, interpClamp, alphaHex } from "../motion";

const cueAt = (cues: Cue[], label: string, fallback: number) =>
  cues.find((c) => c.label === label)?.at_frame ?? fallback;

export const ExplainerCard: React.FC<{
  data: SceneData;
  cues: Cue[];
  theme: Theme;
  durationInFrames: number;
}> = ({ data, cues, theme, durationInFrames }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const kickerAt = cueAt(cues, "kicker-in", 4);
  const titleAt = cueAt(cues, "title-in", 14);
  const subAt = cueAt(cues, "subtitle-in", titleAt + 18);
  const bullets = (data.bullets ?? []).slice(0, 4);
  // Bullets stagger after the subtitle; prefer explicit point-N cues when present.
  const bulletAt = (i: number) =>
    cueAt(cues, `point-${i + 1}`, subAt + 16 + i * 16);

  // Left navy rail slides up as the scene opens (Orinovate sidebar motif).
  const railGrow = ease(frame, 0, 18, 0, 1);

  // Title word-rises with a spring (kinetic-light damping 16) + a blue underline
  // that sweeps in just after the title settles.
  const titleSpring = spring({
    frame: frame - titleAt,
    fps,
    config: { damping: 16, stiffness: 150, mass: 0.8 },
  });
  const titleY = interpolate(titleSpring, [0, 1], [42, 0]);
  const titleOpacity = ease(frame, titleAt, titleAt + 16, 0, 1);
  const underline = ease(frame, titleAt + 12, titleAt + 34, 0, 1);

  // Subtitle settle.
  const subOpacity = ease(frame, subAt, subAt + 16, 0, 1);
  const subY = ease(frame, subAt, subAt + 16, 14, 0);

  // Soft accent glow behind the lockup keeps the held frames alive (tail pulse).
  const glowPulse = interpClamp(
    frame,
    [titleAt, titleAt + 40, durationInFrames - 1],
    [0.85, 1.1, 0.95]
  );

  // Clean exit so scenes hand off without a freeze.
  const exitFade = ease(frame, durationInFrames - 12, durationInFrames, 1, 0);
  const exitShift = ease(frame, durationInFrames - 12, durationInFrames, 0, -18);

  return (
    <AbsoluteFill
      style={{
        backgroundColor: theme.bg,
        fontFamily: theme.fontDisplay,
        opacity: exitFade,
        transform: `translateY(${exitShift}px)`,
      }}
    >
      {/* Soft brand-accent radial glow behind the content */}
      <div
        style={{
          position: "absolute",
          top: "44%",
          left: "46%",
          width: 1100,
          height: 680,
          transform: `translate(-50%, -50%) scale(${glowPulse})`,
          background: `radial-gradient(ellipse, ${theme.accent}14 0%, ${theme.accent}00 65%)`,
        }}
      />

      {/* Navy left rail (Orinovate sidebar motif) */}
      <div
        style={{
          position: "absolute",
          left: 0,
          top: 0,
          bottom: 0,
          width: 14,
          transformOrigin: "top",
          transform: `scaleY(${railGrow})`,
          background: `linear-gradient(${theme.navy}, ${theme.navyBright})`,
        }}
      />

      <div
        style={{
          position: "absolute",
          left: 140,
          right: 120,
          top: 150,
          bottom: 120,
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          gap: 22,
        }}
      >
        {/* Kicker eyebrow + wordmark */}
        <div
          style={{
            display: "flex",
            alignItems: "baseline",
            gap: 22,
            opacity: ease(frame, kickerAt, kickerAt + 14, 0, 1),
            transform: `translateY(${ease(frame, kickerAt, kickerAt + 14, 12, 0)}px)`,
          }}
        >
          <span
            style={{
              fontSize: 24,
              fontWeight: 700,
              letterSpacing: 6,
              textTransform: "uppercase",
              color: theme.accent,
              fontFamily: theme.fontMono,
            }}
          >
            {data.kicker || theme.wordmark}
          </span>
          {data.kicker ? (
            <span style={{ fontSize: 22, fontWeight: 600, color: theme.navy }}>
              {theme.wordmark}
            </span>
          ) : null}
        </div>

        {/* Title with a blue underline sweep */}
        <div style={{ position: "relative", display: "inline-block" }}>
          <div
            style={{
              opacity: titleOpacity,
              transform: `translateY(${titleY}px)`,
              fontSize: 96,
              fontWeight: 900,
              letterSpacing: -3,
              lineHeight: 1.04,
              color: theme.text,
              maxWidth: 1500,
            }}
          >
            {data.title}
          </div>
          <div
            style={{
              marginTop: 14,
              height: 8,
              width: `${Math.round(underline * 360)}px`,
              borderRadius: 6,
              background: theme.accent,
              boxShadow: `0 0 24px ${theme.accent}${alphaHex(0.45 * underline)}`,
            }}
          />
        </div>

        {/* Subtitle */}
        {data.subtitle ? (
          <div
            style={{
              opacity: subOpacity,
              transform: `translateY(${subY}px)`,
              fontSize: 32,
              fontWeight: 400,
              color: theme.textMuted,
              maxWidth: 1200,
            }}
          >
            {data.subtitle}
          </div>
        ) : null}

        {/* Staggered capability bullets — numbered badges (NO emoji) */}
        {bullets.length > 0 ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 18, marginTop: 12 }}>
            {bullets.map((b, i) => {
              const at = bulletAt(i);
              const r = reveal(frame, at, 22, 16);
              return (
                <div
                  key={`${i}-${b}`}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 24,
                    opacity: r.opacity,
                    transform: r.transform,
                  }}
                >
                  <div
                    style={{
                      flex: "0 0 52px",
                      width: 52,
                      height: 52,
                      borderRadius: 14,
                      background: theme.navy,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      fontSize: 24,
                      fontWeight: 800,
                      color: "#ffffff",
                      fontFamily: theme.fontMono,
                    }}
                  >
                    {i + 1}
                  </div>
                  <div
                    style={{
                      fontSize: 38,
                      fontWeight: 600,
                      color: theme.text,
                      letterSpacing: -0.4,
                    }}
                  >
                    {b}
                  </div>
                </div>
              );
            })}
          </div>
        ) : null}
      </div>
    </AbsoluteFill>
  );
};
