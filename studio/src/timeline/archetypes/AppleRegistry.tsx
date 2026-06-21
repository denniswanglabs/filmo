// APPLE-REGISTRY archetype — the "Registry" beat (data / catalog / entities).
// Maps a scene role: the PRODUCT-SURFACE / "everything connected" beat. An
// iOS segmented control slides its pill to the selected segment, then a grid
// of TYPE-CODED entity cards deals in one per cue, each colored by its
// `entity.type` via `data.entityColors` (falls back to theme.accent). The
// `selected` card gets an ACTIVE badge + a soft type-colored glow.
//
// Apple iOS motion only: cubic ease-out arrivals, NO springs (per
// feedback_apple_screenshot_animation). Palette + per-type colors come from
// props so the style-fill engine recolors per brand.
//
// Reveals fire on the scene's CUE frames (relative to scene in_frame):
//   heading-in -> heading + segmented control, pill -> pill slides to segment,
//   card-1..card-6 -> each entity card deals in.
import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";
import type { Cue, SceneData, Theme } from "../types";
import { appleRise, breathDrift, EASE_OUT_QUART, alphaHex } from "../motion";

const cueAt = (cues: Cue[], label: string, fallback: number) =>
  cues.find((c) => c.label === label)?.at_frame ?? fallback;

const typeColor = (
  theme: Theme,
  colors: Record<string, string> | undefined,
  type?: string
) => (type && colors && colors[type]) || theme.accent;

export const AppleRegistry: React.FC<{
  data: SceneData;
  cues: Cue[];
  theme: Theme;
  durationInFrames: number;
}> = ({ data, cues, theme, durationInFrames }) => {
  const frame = useCurrentFrame();

  const headingAt = cueAt(cues, "heading-in", 8);
  const pillAt = cueAt(cues, "pill", headingAt + 14);

  const segments = data.segments ?? ["All"];
  const selectedSeg = Math.min(data.selectedSegment ?? 0, segments.length - 1);
  const entities = (data.entities ?? []).slice(0, 6);
  const selected = data.selected ?? -1;

  const head = appleRise(frame, headingAt, 18, 18);

  // Segmented control geometry (iOS picker). The pill slides from segment 0 to
  // the selected segment with ease-out-quart (no overshoot).
  const SEG_W = 200;
  const SEG_PAD = 6;
  const pillP = interpolate(frame, [pillAt, pillAt + 22], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: EASE_OUT_QUART,
  });
  const pillX = SEG_PAD + pillP * selectedSeg * SEG_W;
  const segOpacity = appleRise(frame, headingAt, 12, 16).opacity;

  // each card deals in on its own cue (card-1..card-6); fallback staggers.
  const cardAt = (i: number) => cueAt(cues, `card-${i + 1}`, pillAt + 16 + i * 12);

  // breath drift on the whole grid once settled, keeps the hold alive.
  const lastCardAt = entities.length ? cardAt(entities.length - 1) : headingAt;
  const breath = breathDrift(frame, lastCardAt + 30, 1.6, 110);

  const exitFade = interpolate(frame, [durationInFrames - 14, durationInFrames], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: EASE_OUT_QUART,
  });

  return (
    <AbsoluteFill
      style={{
        backgroundColor: theme.bg,
        fontFamily: theme.fontPrimary,
        opacity: exitFade,
      }}
    >
      {/* soft mesh so glass cards read */}
      <AbsoluteFill
        style={{
          background: `
            radial-gradient(ellipse 900px 700px at 18% 22%, ${theme.navy}16 0%, transparent 60%),
            radial-gradient(ellipse 900px 700px at 84% 80%, ${theme.accent}14 0%, transparent 60%),
            ${theme.bg}
          `,
        }}
      />

      {/* Heading */}
      <div
        style={{
          position: "absolute",
          left: 0,
          right: 0,
          top: 110,
          textAlign: "center",
          opacity: head.opacity,
          transform: head.transform,
          fontSize: 64,
          fontWeight: 700,
          letterSpacing: "-0.025em",
          color: theme.text,
        }}
      >
        {data.heading}
      </div>

      {/* Segmented control */}
      <div
        style={{
          position: "absolute",
          left: "50%",
          top: 212,
          transform: "translateX(-50%)",
          opacity: segOpacity,
          display: "flex",
          padding: SEG_PAD,
          borderRadius: 999,
          backgroundColor: theme.bgCardRaised,
          border: `1px solid ${theme.border}`,
          boxShadow: "inset 0 1px 0 rgba(255,255,255,0.8)",
        }}
      >
        {/* sliding pill (positioned within this absolute container) */}
        <div
          style={{
            position: "absolute",
            left: pillX,
            top: SEG_PAD,
            width: SEG_W,
            height: 52,
            borderRadius: 999,
            backgroundColor: theme.accent,
            boxShadow: `0 4px 16px ${theme.accent}55, inset 0 1px 0 rgba(255,255,255,0.4)`,
          }}
        />
        {segments.map((seg, i) => (
          <div
            key={seg}
            style={{
              position: "relative",
              width: SEG_W,
              height: 52,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: 24,
              fontWeight: 600,
              letterSpacing: "-0.01em",
              color: i === selectedSeg && pillP > 0.5 ? "#ffffff" : theme.textMuted,
              zIndex: 1,
            }}
          >
            {seg}
          </div>
        ))}
      </div>

      {/* Type-coded entity grid (3 x 2) */}
      <div
        style={{
          position: "absolute",
          left: 120,
          right: 120,
          top: 320,
          bottom: 96,
          display: "grid",
          gridTemplateColumns: "1fr 1fr 1fr",
          gridTemplateRows: "1fr 1fr",
          gap: 28,
          transform: `translateY(${breath}px)`,
        }}
      >
        {entities.map((e, i) => {
          const at = cardAt(i);
          const r = appleRise(frame, at, 36, 22);
          const color = typeColor(theme, data.entityColors, e.type);
          const isSel = i === selected;
          const selGlow = isSel
            ? interpolate(frame, [at + 10, at + 30], [0, 1], {
                extrapolateLeft: "clamp",
                extrapolateRight: "clamp",
                easing: EASE_OUT_QUART,
              })
            : 0;
          return (
            <div
              key={e.code}
              style={{
                position: "relative",
                opacity: r.opacity,
                transform: r.transform,
                borderRadius: 22,
                padding: 28,
                backgroundColor: theme.bgCard,
                border: isSel ? `1.5px solid ${color}` : `1px solid ${theme.border}`,
                boxShadow: isSel
                  ? [
                      `0 24px 60px ${color}${alphaHex(0.28 * selGlow)}`,
                      `0 0 0 5px ${color}${alphaHex(0.1 * selGlow)}`,
                      "inset 0 1px 0 rgba(255,255,255,0.9)",
                    ].join(", ")
                  : ["0 12px 32px rgba(15,35,56,0.06)", "inset 0 1px 0 rgba(255,255,255,0.9)"].join(", "),
                display: "flex",
                flexDirection: "column",
                justifyContent: "space-between",
              }}
            >
              {/* top: type glyph (lettered, NO emoji) + code chip */}
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <div
                  style={{
                    width: 44,
                    height: 44,
                    borderRadius: 12,
                    backgroundColor: color,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    color: "#ffffff",
                    fontSize: 18,
                    fontWeight: 800,
                    fontFamily: theme.fontMono,
                    textTransform: "uppercase",
                  }}
                >
                  {(e.type ?? e.code).slice(0, 2)}
                </div>
                <div
                  style={{
                    fontSize: 16,
                    fontFamily: theme.fontMono,
                    color: theme.textDim,
                    padding: "4px 12px",
                    borderRadius: 999,
                    backgroundColor: theme.bgCardRaised,
                    letterSpacing: "0.04em",
                  }}
                >
                  {e.code}
                </div>
              </div>

              {/* middle: name + meta */}
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                <div
                  style={{
                    fontSize: 30,
                    fontWeight: 700,
                    color: theme.text,
                    letterSpacing: "-0.02em",
                    lineHeight: 1.1,
                  }}
                >
                  {e.name}
                </div>
                {e.meta && (
                  <div style={{ fontSize: 18, color: theme.textDim, fontWeight: 500 }}>{e.meta}</div>
                )}
              </div>

              {/* bottom: type label */}
              <div style={{ fontSize: 18, fontWeight: 600, color }}>
                {(e.type ?? "entity").replace(/^\w/, (c) => c.toUpperCase())}
              </div>

              {isSel && (
                <div
                  style={{
                    position: "absolute",
                    top: -1,
                    right: -1,
                    padding: "5px 12px",
                    fontSize: 13,
                    fontWeight: 800,
                    color: "#ffffff",
                    backgroundColor: color,
                    borderRadius: "0 22px 0 14px",
                    letterSpacing: "0.06em",
                    opacity: selGlow,
                  }}
                >
                  ACTIVE
                </div>
              )}
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};
