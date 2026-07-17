// Engineered Night shared UI atoms (spec §2, §4): eyebrow grammar, chips,
// corner brackets, CTA pair. Every color routes through NightTokens — the accent
// is semantic only (active chip, filled CTA, keyword) and never decoration.
import React from "react";
import { interpolate, Easing } from "remotion";
import { NIGHT_TYPE, type NightTokens } from "./theme";
import { pop, type PopState } from "./motion";

export const popStyle = (p: PopState): React.CSSProperties => ({
  opacity: p.opacity,
  transform: `scale(${p.scale})`,
});

export const Eyebrow: React.FC<{
  t: NightTokens;
  accent?: boolean;
  children: React.ReactNode;
  style?: React.CSSProperties;
}> = ({ t, accent = false, children, style }) => (
  <div
    style={{
      fontFamily: t.fontBody,
      fontSize: NIGHT_TYPE.eyebrow,
      fontWeight: 600,
      letterSpacing: "0.10em",
      textTransform: "uppercase",
      color: accent ? t.accent : t.inkDim,
      ...style,
    }}
  >
    {children}
  </div>
);

export const Chip: React.FC<{
  t: NightTokens;
  active?: boolean;
  children: React.ReactNode;
  style?: React.CSSProperties;
}> = ({ t, active = false, children, style }) => (
  <div
    style={{
      display: "inline-flex",
      alignItems: "center",
      padding: "10px 18px",
      borderRadius: 999,
      border: `1px solid ${active ? t.accent : t.panelLine}`,
      background: active ? t.accentSoft : t.panel,
      color: active ? t.ink : t.inkMuted,
      fontFamily: t.fontBody,
      fontSize: NIGHT_TYPE.label,
      fontWeight: 500,
      whiteSpace: "nowrap",
      ...style,
    }}
  >
    {children}
  </div>
);

/** Four thin L-brackets drawing in around the hero (spec §2). `progress` 0→1. */
export const CornerBrackets: React.FC<{
  t: NightTokens;
  width: number;
  height: number;
  progress: number;
  arm?: number;
}> = ({ t, width, height, progress, arm = 56 }) => {
  const p = interpolate(progress, [0, 1], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.cubic),
  });
  const a = arm * p;
  const stroke = "rgba(255,255,255,0.85)";
  const sw = 2;
  const corners: Array<[number, number, 1 | -1, 1 | -1]> = [
    [0, 0, 1, 1],
    [width, 0, -1, 1],
    [0, height, 1, -1],
    [width, height, -1, -1],
  ];
  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      style={{ position: "absolute", inset: 0, overflow: "visible" }}
    >
      {corners.map(([x, y, dx, dy], i) => (
        <path
          key={i}
          d={`M ${x + dx * a} ${y} L ${x} ${y} L ${x} ${y + dy * a}`}
          stroke={stroke}
          strokeWidth={sw}
          fill="none"
          opacity={p}
        />
      ))}
    </svg>
  );
};

export const CtaPair: React.FC<{
  t: NightTokens;
  primary: string;
  secondary?: string;
  frame: number;
  start: number;
  fps: number;
}> = ({ t, primary, secondary, frame, start, fps }) => {
  const p1 = pop(frame, start, fps);
  const p2 = pop(frame, start + Math.round(0.12 * fps), fps);
  const base: React.CSSProperties = {
    fontFamily: t.fontBody,
    fontSize: NIGHT_TYPE.label,
    fontWeight: 600,
    padding: "16px 30px",
    borderRadius: 12,
    whiteSpace: "nowrap",
  };
  return (
    <div style={{ display: "flex", gap: 16, justifyContent: "center" }}>
      <div style={{ ...base, ...popStyle(p1), background: t.accent, color: "#0A0A0A" }}>{primary}</div>
      {secondary ? (
        <div
          style={{
            ...base,
            ...popStyle(p2),
            border: `1px solid ${t.panelLine}`,
            background: "rgba(255,255,255,0.04)",
            color: t.ink,
          }}
        >
          {secondary}
        </div>
      ) : null}
    </div>
  );
};
