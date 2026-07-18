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
  kind: "headline" | "sub" | "stat" | "video" | "cta" | "wordmark" | "graphic";
  x: number; // world coords (element center X)
  y: number;
  w?: number;
  at: number; // frame the entrance chord starts
  dir?: "left" | "right" | "top" | "bottom";
  text?: string;
  accentWord?: string;
  size?: number;
  value?: string;
  label?: string;
  videoSrc?: string;
  logoSrc?: string;
  motif?: "house" | "chat" | "tag" | "globe" | "card";
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

/** Domain-themed line-art beat for stops that don't earn a second screen
 *  recording (Dennis 2026-07-18: "if there is no need to be another screen
 *  recording, use more motion graphics"). Strokes draw on over ~55f in
 *  staggered groups (deliberate tier), accent details pop with a small
 *  overshoot (confirmation tier), then the whole motif floats gently. */
const MOTIF_PATHS: Record<string, { groups: string[][]; pops: { d?: string; cx?: number; cy?: number; r?: number; rect?: [number, number, number, number, number] }[] }> = {
  house: {
    groups: [
      ["M 90 262 L 320 92 L 550 262"], // roof
      ["M 140 262 L 140 452 L 500 452 L 500 262", "M 60 452 L 580 452"], // body + ground
      ["M 180 306 h 84 v 70 h -84 Z"], // window
    ],
    pops: [{ rect: [292, 340, 80, 112, 10] }], // door, accent
  },
  chat: {
    groups: [
      ["M 128 128 h 224 a 28 28 0 0 1 28 28 v 84 a 28 28 0 0 1 -28 28 h -152 l -44 40 v -40 h -28 a 28 28 0 0 1 -28 -28 v -84 a 28 28 0 0 1 28 -28 Z"],
      ["M 288 288 h 224 a 28 28 0 0 1 28 28 v 84 a 28 28 0 0 1 -28 28 h -28 v 40 l -44 -40 h -152 a 28 28 0 0 1 -28 -28 v -84 a 28 28 0 0 1 28 -28 Z"],
    ],
    pops: [
      { cx: 356, cy: 358, r: 12 }, { cx: 400, cy: 358, r: 12 }, { cx: 444, cy: 358, r: 12 },
    ],
  },
  tag: {
    groups: [
      ["M 190 120 L 350 120 L 480 250 a 24 24 0 0 1 0 34 L 344 420 a 24 24 0 0 1 -34 0 L 180 290 L 180 130 a 10 10 0 0 1 10 -10 Z"],
      ["M 250 60 C 250 100 236 110 232 140"], // string
    ],
    pops: [{ cx: 246, cy: 186, r: 22 }],
  },
  globe: {
    groups: [
      ["M 320 96 a 176 176 0 1 0 0.01 0 Z"],
      ["M 320 96 a 88 176 0 1 0 0.01 0 Z", "M 152 214 h 336", "M 152 330 h 336"],
    ],
    pops: [{ cx: 396, cy: 190, r: 18 }],
  },
  card: {
    groups: [
      ["M 120 130 h 400 a 24 24 0 0 1 24 24 v 240 a 24 24 0 0 1 -24 24 h -400 a 24 24 0 0 1 -24 -24 v -240 a 24 24 0 0 1 24 -24 Z", "M 96 196 h 448"],
      ["M 150 244 h 220", "M 150 292 h 300"],
    ],
    pops: [{ rect: [150, 336, 132, 44, 22] }],
  },
};

const MotionGraphic: React.FC<{ el: WalkrecElement; t: WalkrecProps["theme"]; frame: number }> = ({ el, t, frame }) => {
  const local = frame - el.at;
  const motif = MOTIF_PATHS[el.motif || "card"] || MOTIF_PATHS.card;
  const drawP = (gi: number) =>
    interpolate(local, [gi * 10, gi * 10 + 55], [1, 0], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
      easing: VEVARA_STEP,
    });
  const popStart = motif.groups.length * 10 + 40;
  const popP = (pi: number) =>
    interpolate(local, [popStart + pi * 5, popStart + pi * 5 + 10], [0, 1], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
      easing: Easing.out(Easing.back(2)),
    });
  const float = local > popStart + 20 ? 6 * Math.sin((2 * Math.PI * (local - popStart - 20)) / 150) : 0;
  return (
    <svg viewBox="0 0 640 520" style={{ width: "100%", display: "block", transform: `translateY(${float}px)` }}>
      {motif.groups.map((paths, gi) =>
        paths.map((d, pi) => (
          <path
            key={`${gi}-${pi}`}
            d={d}
            pathLength={1}
            fill="none"
            stroke={t.ink}
            strokeWidth={9}
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeDasharray={1}
            strokeDashoffset={drawP(gi)}
          />
        )),
      )}
      {motif.pops.map((p, pi) => {
        const s = popP(pi);
        if (s <= 0) return null;
        const common = { fill: t.accent, opacity: Math.min(1, s) };
        if (p.rect) {
          const [x, y, w, h, r] = p.rect;
          return <rect key={pi} x={x} y={y} width={w} height={h} rx={r} {...common}
            transform={`translate(${x + w / 2} ${y + h / 2}) scale(${s}) translate(${-(x + w / 2)} ${-(y + h / 2)})`} />;
        }
        return <circle key={pi} cx={p.cx} cy={p.cy} r={(p.r || 12) * s} {...common} />;
      })}
    </svg>
  );
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
        <div style={{ ...base, fontFamily: t.fontDisplay, fontSize: el.size ?? 92, fontWeight: 700, letterSpacing: "-0.025em", lineHeight: 1.12, color: t.ink }}>
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
    case "graphic":
      return (
        <div style={{ ...base, width: el.w ?? 760 }}>
          <MotionGraphic el={el} t={t} frame={frame} />
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
