// Engineered Night stage system (spec §2).
//
//   NightStage    viewport-locked atmosphere: pure black canvas + the two enormous
//                 static glows (accent ~20% one side, white ~10% the other) + a
//                 soft vignette. The camera never moves these.
//   WorldSurface  the tall product surface the camera glides across: blueprint
//                 grid (40px, felt-not-seen) + vertical rails bounding the
//                 1280px content column.
import React from "react";
import { AbsoluteFill } from "remotion";
import type { NightTokens } from "./theme";

export const CONTENT_W = 1280;
export const FRAME_W = 1920;
const RAIL_X = (FRAME_W - CONTENT_W) / 2; // 320

export const NightStage: React.FC<{
  t: NightTokens;
  children?: React.ReactNode;
}> = ({ t, children }) => {
  return (
    <AbsoluteFill style={{ backgroundColor: t.stage, overflow: "hidden" }}>
      {/* Dual atmospheric glow — static, enormous, soft. */}
      <div
        style={{
          position: "absolute",
          width: 1600,
          height: 1600,
          right: -520,
          top: -640,
          background: `radial-gradient(circle at center, ${t.accentGlow} 0%, transparent 62%)`,
          filter: "blur(8px)",
        }}
      />
      <div
        style={{
          position: "absolute",
          width: 1400,
          height: 1400,
          left: -560,
          bottom: -700,
          background: `radial-gradient(circle at center, rgba(255,255,255,0.10) 0%, transparent 60%)`,
        }}
      />
      {children}
      {/* Soft vignette keeps edges quiet regardless of world content. */}
      <AbsoluteFill
        style={{
          pointerEvents: "none",
          background:
            "radial-gradient(ellipse at center, transparent 58%, rgba(0,0,0,0.42) 100%)",
        }}
      />
    </AbsoluteFill>
  );
};

export const WorldSurface: React.FC<{
  t: NightTokens;
  height: number;
  /** v4: the world is 2D — the surface spans the full layout width. Defaults to
   *  one frame for callers that still render a single column. */
  width?: number;
  children?: React.ReactNode;
}> = ({ t, height, width = FRAME_W, children }) => {
  // 1px grid lines every 40px, both axes — drawn at the spec color but only 1px
  // wide, so over black the field reads ≤7% luminance ("felt, not seen").
  // Rails moved into each section CELL (NightTimeline) so they travel with the
  // beat in the 2D layout instead of striping the whole world.
  const line = t.grid;
  return (
    <div
      style={{
        position: "absolute",
        left: 0,
        top: 0,
        width,
        height,
        backgroundImage: `repeating-linear-gradient(0deg, ${line} 0 1px, transparent 1px 40px), repeating-linear-gradient(90deg, ${line} 0 1px, transparent 1px 40px)`,
        backgroundSize: "40px 40px, 40px 40px",
      }}
    >
      {children}
    </div>
  );
};
