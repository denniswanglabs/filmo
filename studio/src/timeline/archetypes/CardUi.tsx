// CARD-UI archetype — ported from Orinovate kinetic-light ReviewApproveScene
// (Act 2). A big accent-split heading on the left, then a 2x2 grid of cards
// that DEAL IN with a staggered rise (card-deal-in). The accent card keeps a
// slow glow/scale "tail pulse" through the hold so the held frames stay alive.
//
// Reveals fire on the scene's CUE frames (relative to scene in_frame):
//   heading-in -> heading, card-1..card-4 -> each card's deal-in.
import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";
import type { Cue, SceneData, Theme } from "../types";
import { ease, reveal, alphaHex, actNum, actLabel } from "../motion";

const cueAt = (cues: Cue[], label: string, fallback: number) =>
  cues.find((c) => c.label === label)?.at_frame ?? fallback;

const splitAccent = (heading: string, accent?: string) => {
  if (!accent || !heading.includes(accent)) return { pre: heading, hit: "" };
  const i = heading.indexOf(accent);
  return { pre: heading.slice(0, i), hit: heading.slice(i) };
};

export const CardUi: React.FC<{
  data: SceneData;
  cues: Cue[];
  theme: Theme;
  durationInFrames: number;
  // 1-based act index among content-beat scenes (-1 = no badge)
  actIndex?: number;
  // OPTIONAL: scene id, threaded from Timeline for click-to-select addressing.
  sceneId?: string;
}> = ({ data, cues, theme, durationInFrames, actIndex = -1, sceneId }) => {
  const frame = useCurrentFrame();

  const headingAt = cueAt(cues, "heading-in", 6);
  const cards = data.cards ?? [];
  const cardAt = (i: number) => cueAt(cues, `card-${i + 1}`, headingAt + 20 + i * 22);

  const headStyle = reveal(frame, headingAt, 18, 16);
  const chapOpacity = ease(frame, headingAt, headingAt + 12, 0, 1);

  // Accent card tail pulse (ReviewApproveScene.accentShipPulse) — a slow scale
  // breath through the held tail so the highlighted card never freezes.
  const accentStart = cardAt(0) + 40;
  const accentPulse =
    1 +
    Math.sin((frame - accentStart) * 0.12) *
      0.035 *
      ease(frame, accentStart, accentStart + 14, 0, 1);

  const exitFade = ease(frame, durationInFrames - 12, durationInFrames, 1, 0);
  const { pre, hit } = splitAccent(data.heading ?? "", data.headingAccent);

  // Act badge: replaces the hardcoded "Capabilities" chapter label.
  // When actIndex > 0, render "NN — LABEL"; otherwise fall back to "Capabilities".
  const badgeLabel = actIndex > 0 ? actLabel(data.kicker ?? data.heading) : "";
  const badgeText =
    actIndex > 0
      ? `${actNum(actIndex)}${badgeLabel ? ` — ${badgeLabel}` : ""}`
      : "Capabilities";

  return (
    <AbsoluteFill
      style={{
        backgroundColor: theme.bg,
        fontFamily: theme.fontPrimary,
        opacity: exitFade,
      }}
    >
      {/* Chapter / act badge eyebrow (kinetic-light top-left) */}
      <div
        style={{
          position: "absolute",
          left: 96,
          top: 96,
          opacity: chapOpacity,
          fontSize: actIndex > 0 ? 22 : 26,
          fontWeight: actIndex > 0 ? 700 : 500,
          letterSpacing: actIndex > 0 ? "0.18em" : 6,
          textTransform: "uppercase",
          color: theme.accent,
          fontFamily: theme.fontMono,
        }}
      >
        {badgeText}
      </div>

      {/* Big accent-split heading */}
      <div
        data-scene-id={sceneId}
        data-field="heading"
        style={{
          position: "absolute",
          left: 96,
          top: 150,
          ...headStyle,
          fontSize: 116,
          fontWeight: 900,
          letterSpacing: -4,
          lineHeight: 1.0,
          color: theme.text,
        }}
      >
        {pre}
        {hit && <span style={{ color: theme.accent }}>{hit}</span>}
      </div>

      {/* 2x2 card grid — each card deals in on its cue frame */}
      <div
        data-scene-id={sceneId}
        data-field="cards"
        style={{
          position: "absolute",
          left: 96,
          right: 96,
          top: 340,
          bottom: 96,
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gridTemplateRows: "1fr 1fr",
          gap: 28,
        }}
      >
        {cards.slice(0, 4).map((card, i) => {
          const at = cardAt(i);
          const r = reveal(frame, at, 26, 16);
          const isAccent = !!card.accent;
          const scale = isAccent ? accentPulse : 1;
          const glow = isAccent
            ? `0 0 ${48 * accentPulse}px ${theme.accent}${alphaHex(0.28 * accentPulse)}`
            : "none";
          return (
            <div
              key={card.label}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 28,
                padding: "36px 44px",
                background: isAccent ? theme.bgCardRaised : theme.bgCard,
                border: `1px solid ${isAccent ? theme.accent + "55" : theme.border}`,
                borderRadius: 20,
                boxShadow: glow,
                opacity: r.opacity,
                transform: `${r.transform} scale(${scale})`,
              }}
            >
              {/* numbered badge (NO emoji) */}
              <div
                style={{
                  flex: "0 0 64px",
                  width: 64,
                  height: 64,
                  borderRadius: 16,
                  background: isAccent ? theme.accent : theme.bgCardRaised,
                  border: `1px solid ${isAccent ? theme.accent : theme.border}`,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontSize: 30,
                  fontWeight: 800,
                  color: isAccent ? "#ffffff" : theme.textDim,
                  fontFamily: theme.fontMono,
                }}
              >
                {i + 1}
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div
                  style={{
                    fontSize: 44,
                    fontWeight: 700,
                    color: isAccent ? theme.text : theme.textMuted,
                    letterSpacing: -0.6,
                    marginBottom: 8,
                  }}
                >
                  {card.label}
                </div>
                {card.sub && (
                  <div style={{ fontSize: 22, color: theme.textDim, lineHeight: 1.4 }}>
                    {card.sub}
                  </div>
                )}
              </div>
              {card.value && (
                <div
                  style={{
                    fontSize: 72,
                    fontWeight: 900,
                    color: theme.accent,
                    fontFamily: theme.fontMono,
                    letterSpacing: -3,
                    textShadow: isAccent ? `0 0 28px ${theme.accent}66` : "none",
                  }}
                >
                  {card.value}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};
