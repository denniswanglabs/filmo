// Walkrec v3 (PROTOTYPE, local-only) — the Vevara-grammar world film.
//
// One WORLD canvas painted in the BRAND'S OWN background color (Dennis
// 2026-07-18: "take the palette of the website and apply it as the background").
// Elements live in spatial clusters; a camera visits them as back-to-back
// MOMENTS with the fitted Vevara swift-S curve. Entrances are single chords
// (blur+slide+fade, zero stagger). Footage plays inside a rounded, bezel-less
// screenshot card (radius 44, soft shadow) — Vevara's frame grammar.
// Source of truth: vault Style-Specs/VEVARA-ANIMATION-TAXONOMY.md.
import React from "react";
import {
  AbsoluteFill,
  Audio,
  Easing,
  Img,
  OffthreadVideo,
  Sequence,
  interpolate,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

// The FITTED runtime curve (vevaraStep) — soft ~250ms attack, velocity peak
// ~27% in, long decel tail. NOT power4.out (that's only what the editor writes).
const VEVARA_STEP = Easing.bezier(0.35, 0.05, 0.3, 1);
const REFRAME_F = 66; // ≈2.2s camera thought, flagship cadence
const CHORD_F = 45; // element entrance chord

export interface WalkrecElement {
  id: string;
  kind: "headline" | "sub" | "stat" | "video" | "cta" | "wordmark";
  x: number; // world coords (element center X)
  y: number;
  w?: number;
  at: number; // frame the entrance chord starts
  dir?: "left" | "right" | "top" | "bottom";
  text?: string;
  accentWord?: string;
  value?: string;
  label?: string;
  videoSrc?: string;
  logoSrc?: string;
}

export interface WalkrecMoment {
  at: number; // frame the reframe starts
  x: number; // camera target (world center)
  y: number;
  scale: number;
}

export interface WalkrecProps {
  fps: number;
  total_frames: number;
  theme: {
    bg: string;
    ink: string;
    inkMuted: string;
    accent: string;
    card: string;
    fontDisplay: string;
    fontBody: string;
    wordmark: string;
    logoSrc?: string;
    music?: string;
  };
  elements: WalkrecElement[];
  moments: WalkrecMoment[];
}

const resolveAsset = (p: string): string =>
  p.startsWith("http") || p.startsWith("/") ? p : staticFile(p);

/** Camera pose at `frame`: tween INTO each moment over REFRAME_F with the
 *  swift-S curve, then hold until the next moment begins. */
function cameraPose(frame: number, moments: WalkrecMoment[]): WalkrecMoment {
  if (!moments.length) return { at: 0, x: 960, y: 540, scale: 1 };
  let pose = { ...moments[0] };
  for (let i = 1; i < moments.length; i++) {
    const m = moments[i];
    if (frame < m.at) break;
    const p = interpolate(frame, [m.at, m.at + REFRAME_F], [0, 1], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
      easing: VEVARA_STEP,
    });
    pose = {
      at: m.at,
      x: pose.x + (m.x - pose.x) * p,
      y: pose.y + (m.y - pose.y) * p,
      scale: pose.scale + (m.scale - pose.scale) * p,
    };
  }
  return pose;
}

/** The entrance chord: blur 20→0 + slide (±140/±100) + fade, one curve. */
function chord(frame: number, at: number) {
  const p = interpolate(frame, [at, at + CHORD_F], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: VEVARA_STEP,
  });
  return { p, opacity: p, blur: 20 * (1 - p) };
}

const slideOffset = (dir: WalkrecElement["dir"], p: number) => {
  const d = 1 - p;
  switch (dir) {
    case "left": return { dx: -140 * d, dy: 0 };
    case "right": return { dx: 140 * d, dy: 0 };
    case "top": return { dx: 0, dy: -100 * d };
    default: return { dx: 0, dy: 100 * d };
  }
};

const El: React.FC<{ el: WalkrecElement; t: WalkrecProps["theme"]; frame: number; fps: number }> = ({
  el, t, frame, fps,
}) => {
  const c = chord(frame, el.at);
  if (c.p <= 0) return null;
  const { dx, dy } = slideOffset(el.dir, c.p);
  const base: React.CSSProperties = {
    position: "absolute",
    left: el.x,
    top: el.y,
    transform: `translate(-50%, -50%) translate(${dx}px, ${dy}px)`,
    opacity: c.opacity,
    filter: c.blur > 0.4 ? `blur(${c.blur.toFixed(1)}px)` : undefined,
    width: el.w,
    textAlign: "center",
  };
  switch (el.kind) {
    case "headline": {
      const words = (el.text || "").split(/\s+/);
      return (
        <div style={{ ...base, fontFamily: t.fontDisplay, fontSize: 92, fontWeight: 700, letterSpacing: "-0.025em", lineHeight: 1.12, color: t.ink }}>
          {words.map((w, i) => (
            <span key={i} style={{ color: el.accentWord && w.toLowerCase().startsWith(el.accentWord.toLowerCase()) ? t.accent : t.ink }}>
              {w}{" "}
            </span>
          ))}
        </div>
      );
    }
    case "sub":
      return (
        <div style={{ ...base, fontFamily: t.fontBody, fontSize: 30, fontWeight: 400, color: t.inkMuted, lineHeight: 1.5 }}>
          {el.text}
        </div>
      );
    case "stat":
      return (
        <div style={{ ...base }}>
          <div style={{ fontFamily: t.fontDisplay, fontSize: 170, fontWeight: 700, letterSpacing: "-0.03em", color: t.ink, lineHeight: 1 }}>
            {el.value}
          </div>
          <div style={{ width: 150, height: 5, borderRadius: 3, background: t.accent, margin: "22px auto 18px" }} />
          <div style={{ fontFamily: t.fontBody, fontSize: 27, color: t.inkMuted }}>{el.label}</div>
        </div>
      );
    case "video":
      return (
        <div
          style={{
            ...base,
            width: el.w ?? 1240,
            borderRadius: 44,
            overflow: "hidden",
            boxShadow: "0 60px 120px -40px rgba(15,20,40,0.35)",
            background: t.card,
          }}
        >
          {el.videoSrc ? (
            <Sequence from={el.at} layout="none">
              <OffthreadVideo src={resolveAsset(el.videoSrc)} muted style={{ width: "100%", display: "block" }} />
            </Sequence>
          ) : null}
        </div>
      );
    case "cta":
      return (
        <div style={{ ...base }}>
          {el.logoSrc ? (
            <Img src={resolveAsset(el.logoSrc)} style={{ width: 84, height: 84, objectFit: "contain", borderRadius: 20, margin: "0 auto 26px", display: "block" }} />
          ) : null}
          <div style={{ fontFamily: t.fontDisplay, fontSize: 76, fontWeight: 700, letterSpacing: "-0.02em", color: t.ink }}>
            {el.text}
          </div>
          <div
            style={{
              display: "inline-block",
              marginTop: 30,
              padding: "20px 44px",
              borderRadius: 999,
              background: t.accent,
              color: "#FFFFFF",
              fontFamily: t.fontBody,
              fontSize: 26,
              fontWeight: 600,
            }}
          >
            {el.value || "Get started"}
          </div>
        </div>
      );
    case "wordmark":
      return (
        <div style={{ ...base, fontFamily: t.fontBody, fontSize: 15, fontWeight: 600, letterSpacing: "0.24em", color: t.inkMuted }}>
          {(el.text || t.wordmark).toUpperCase()}
        </div>
      );
    default:
      return null;
  }
};

export const WalkrecWorld: React.FC<WalkrecProps> = (props) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const { theme: t, elements, moments, total_frames } = props;
  const cam = cameraPose(frame, moments);
  const s = cam.scale;

  return (
    <AbsoluteFill style={{ backgroundColor: t.bg, overflow: "hidden" }}>
      {/* Soft brand-accent atmosphere on the LIGHT world (felt, not seen). */}
      <div
        style={{
          position: "absolute",
          width: 1500,
          height: 1500,
          right: -420,
          top: -560,
          background: `radial-gradient(circle at center, ${t.accent}22 0%, transparent 62%)`,
        }}
      />
      <div
        style={{
          position: "absolute",
          left: 0,
          top: 0,
          transform: `translate(${960 - cam.x * s}px, ${540 - cam.y * s}px) scale(${s})`,
          transformOrigin: "0 0",
          willChange: "transform",
        }}
      >
        {elements.map((el) => (
          <El key={el.id} el={el} t={t} frame={frame} fps={fps} />
        ))}
      </div>
      {t.music ? (
        <Audio
          src={resolveAsset(t.music)}
          volume={(f) =>
            interpolate(f, [0, 20, total_frames - 45, total_frames - 1], [0, 0.4, 0.4, 0], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
            })
          }
        />
      ) : null}
    </AbsoluteFill>
  );
};

export const walkrecMetadata = ({ props }: { props: WalkrecProps }) => ({
  durationInFrames: props.total_frames,
  fps: props.fps,
});
