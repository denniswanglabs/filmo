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
  motif?: "house" | "chat" | "tag" | "globe" | "card" | "request-table" | "context-cards" | "chat-exchange" | "price-card" | "check-list" | "chip-sweep" | "stat-pop" | "kinetic-line";
  lines?: string[]; // verbatim site strings the vignette renders as content
  chips?: string[]; // short real labels for the chip sweep
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

/** Concept vignettes (Dennis 2026-07-18: "there should be infographics or
 *  animations of clients requiring a property and a preferred time, maybe like
 *  a table" — enact the title, don't just iconify it). Honest by construction:
 *  only the stop's own words and abstract bars — no invented names, prices,
 *  or dates. Motion: entrances on the fitted curve, sibling stagger 8f,
 *  detail pops confirmation-tier with overshoot, ambient float after. */
const vinP = (local: number, at: number, dur = 14) =>
  interpolate(local, [at, at + dur], [0, 1], {
    extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: VEVARA_STEP,
  });
const vinPop = (local: number, at: number, dur = 10) =>
  interpolate(local, [at, at + dur], [0, 1], {
    extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.out(Easing.back(2)),
  });
const vinFloat = (local: number, after: number) =>
  local > after ? 5 * Math.sin((2 * Math.PI * (local - after)) / 160) : 0;

const Bar: React.FC<{ w: number; h?: number; o?: number; color: string }> = ({ w, h = 12, o = 0.16, color }) => (
  <div style={{ width: w, height: h, borderRadius: h / 2, background: color, opacity: o }} />
);

const ClockGlyph: React.FC<{ color: string }> = ({ color }) => (
  <svg viewBox="0 0 24 24" style={{ width: 16, height: 16, display: "block" }}>
    <circle cx="12" cy="12" r="9" fill="none" stroke={color} strokeWidth="2.4" />
    <path d="M 12 7 v 5 l 3.4 2" fill="none" stroke={color} strokeWidth="2.4" strokeLinecap="round" />
  </svg>
);

const HouseGlyph: React.FC<{ color: string; size?: number }> = ({ color, size = 40 }) => (
  <svg viewBox="0 0 64 52" style={{ width: size, height: (size * 52) / 64, display: "block" }}>
    <path d="M 6 26 L 32 6 L 58 26 M 14 24 v 22 h 36 v -22" fill="none" stroke={color} strokeWidth="4.4" strokeLinecap="round" strokeLinejoin="round" />
    <path d="M 27 46 v -12 h 10 v 12" fill="none" stroke={color} strokeWidth="4.4" strokeLinejoin="round" />
  </svg>
);

/** Rows of incoming requests: real site strings as the request lines, with a
 *  time-flavored site label in the chip when the site offers one. */
const VignetteRequestTable: React.FC<{ el: WalkrecElement; t: WalkrecProps["theme"] }> = ({ el, t }) => {
  const frame = useCurrentFrame();
  const local = frame - el.at;
  const lines = el.lines || [];
  const chipLine = lines.find((l) => /time|date|viewing|visit|when|schedule/i.test(l));
  const rowLines = lines.filter((l) => l !== chipLine);
  const rows = [0, 1, 2];
  return (
    <div style={{ background: t.card, borderRadius: 36, padding: "34px 38px", minWidth: 640, boxShadow: "0 40px 90px -36px rgba(15,20,40,0.28)", transform: `translateY(${vinFloat(local, 70)}px)` }}>
      <div style={{ display: "flex", alignItems: "center", gap: 14, marginBottom: 24, opacity: vinP(local, 0) }}>
        <HouseGlyph color={t.accent} size={34} />
        <div style={{ fontFamily: t.fontBody, fontSize: 19, fontWeight: 700, color: t.ink, opacity: 0.8, textAlign: "left" }}>{el.text}</div>
      </div>
      {rows.map((r) => {
        const p = vinP(local, 10 + r * 8, 16);
        const chip = vinPop(local, 34 + r * 8);
        const line = rowLines[r];
        const initial = (line || el.text || "A")[0].toUpperCase();
        return (
          <div key={r} style={{ display: "flex", alignItems: "center", gap: 18, padding: "16px 18px", borderRadius: 20, background: `${t.ink}0D`, marginBottom: 14, opacity: p, transform: `translateY(${24 * (1 - p)}px)` }}>
            <div style={{ width: 52, height: 52, borderRadius: 26, background: `${t.accent}26`, color: t.accent, fontFamily: t.fontDisplay, fontWeight: 700, fontSize: 24, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
              {initial}
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 9, flex: 1, minWidth: 0 }}>
              {line ? (
                <div style={{ fontFamily: t.fontBody, fontSize: 21, fontWeight: 600, color: t.ink, textAlign: "left", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{line}</div>
              ) : (
                <Bar w={200 - r * 26} h={13} o={0.3} color={t.ink} />
              )}
              <Bar w={132} h={10} color={t.ink} />
            </div>
            {chip > 0 ? (
              <div style={{ display: "flex", alignItems: "center", gap: 9, padding: "10px 16px", borderRadius: 999, background: `${t.accent}16`, border: `2px solid ${t.accent}55`, transform: `scale(${chip})`, flexShrink: 0 }}>
                <ClockGlyph color={t.accent} />
                {chipLine ? (
                  <span style={{ fontFamily: t.fontBody, fontSize: 16, fontWeight: 700, color: t.accent, whiteSpace: "nowrap" }}>{chipLine}</span>
                ) : (
                  <Bar w={44} h={11} o={0.85} color={t.accent} />
                )}
              </div>
            ) : null}
          </div>
        );
      })}
    </div>
  );
};

/** Property cards gaining context chips; the middle one gets the accent ring. */
const VignetteContextCards: React.FC<{ el: WalkrecElement; t: WalkrecProps["theme"] }> = ({ el, t }) => {
  const frame = useCurrentFrame();
  const local = frame - el.at;
  const ring = vinPop(local, 62, 12);
  return (
    <div style={{ display: "flex", gap: 22, transform: `translateY(${vinFloat(local, 84)}px)` }}>
      {[0, 1, 2].map((c) => {
        const p = vinP(local, c * 9, 16);
        const highlighted = c === 1;
        return (
          <div key={c} style={{ width: 224, borderRadius: 28, background: t.card, boxShadow: "0 34px 70px -30px rgba(15,20,40,0.26)", overflow: "hidden", opacity: p, transform: `translateY(${30 * (1 - p)}px) scale(${highlighted ? 1 + 0.05 * ring : 1})`, outline: highlighted && ring > 0 ? `4px solid ${t.accent}` : "none", outlineOffset: -2 }}>
            <div style={{ height: 118, background: `linear-gradient(135deg, ${t.accent}30, ${t.accent}0C)`, display: "flex", alignItems: "center", justifyContent: "center" }}>
              <HouseGlyph color={t.accent} size={46} />
            </div>
            <div style={{ padding: "18px 18px 20px", display: "flex", flexDirection: "column", gap: 10 }}>
              {(el.lines || [])[c] ? (
                <div style={{ fontFamily: t.fontBody, fontSize: 17, fontWeight: 600, color: t.ink, textAlign: "left", lineHeight: 1.3, minHeight: 44 }}>{(el.lines || [])[c]}</div>
              ) : (
                <>
                  <Bar w={150 - c * 14} h={13} o={0.32} color={t.ink} />
                  <Bar w={104} h={11} color={t.ink} />
                </>
              )}
              <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
                {[0, 1].map((k) => {
                  const chip = vinPop(local, 30 + c * 9 + k * 5);
                  return chip > 0 ? (
                    <div key={k} style={{ display: "flex", alignItems: "center", gap: 6, padding: "7px 12px", borderRadius: 999, background: `${t.ink}12`, transform: `scale(${chip})` }}>
                      <div style={{ width: 10, height: 10, borderRadius: 5, background: t.accent, opacity: 0.75 }} />
                      <Bar w={34} h={9} o={0.34} color={t.ink} />
                    </div>
                  ) : null;
                })}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
};

/** A chat exchange: typing dots resolve to bars; a home card lands in-thread. */
const VignetteChat: React.FC<{ el: WalkrecElement; t: WalkrecProps["theme"] }> = ({ el, t }) => {
  const frame = useCurrentFrame();
  const local = frame - el.at;
  const pL = vinP(local, 0, 16);
  const pR = vinP(local, 26, 16);
  const dotsDone = local > 52;
  const pCard = vinPop(local, 60, 14);
  const dot = (i: number) => 0.35 + 0.65 * Math.abs(Math.sin((Math.PI * (local - i * 4)) / 24));
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18, width: 620, transform: `translateY(${vinFloat(local, 86)}px)` }}>
      <div style={{ alignSelf: "flex-start", maxWidth: 440, padding: "20px 24px", borderRadius: "26px 26px 26px 8px", background: t.card, boxShadow: "0 26px 60px -28px rgba(15,20,40,0.24)", opacity: pL, transform: `translateY(${20 * (1 - pL)}px)` }}>
        <div style={{ fontFamily: t.fontBody, fontSize: 20, fontWeight: 600, color: t.ink, textAlign: "left", lineHeight: 1.4 }}>{el.text}</div>
      </div>
      <div style={{ alignSelf: "flex-end", maxWidth: 440, padding: "18px 24px", borderRadius: "26px 26px 8px 26px", background: t.accent, boxShadow: "0 26px 60px -28px rgba(15,20,40,0.3)", opacity: pR, transform: `translateY(${20 * (1 - pR)}px)` }}>
        {!dotsDone ? (
          <div style={{ display: "flex", gap: 8, padding: "4px 2px" }}>
            {[0, 1, 2].map((i) => (
              <div key={i} style={{ width: 11, height: 11, borderRadius: 6, background: "#FFFFFF", opacity: dot(i) }} />
            ))}
          </div>
        ) : (el.lines || [])[0] ? (
          <div style={{ fontFamily: t.fontBody, fontSize: 20, fontWeight: 600, color: "#FFFFFF", textAlign: "left", lineHeight: 1.4 }}>{(el.lines || [])[0]}</div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 9 }}>
            <Bar w={236} h={12} o={0.92} color="#FFFFFF" />
            <Bar w={150} h={12} o={0.6} color="#FFFFFF" />
          </div>
        )}
      </div>
      {pCard > 0 ? (
        <div style={{ alignSelf: "flex-end", display: "flex", alignItems: "center", gap: 16, padding: "16px 22px", borderRadius: 22, background: t.card, boxShadow: "0 30px 64px -28px rgba(15,20,40,0.26)", transform: `scale(${pCard})`, transformOrigin: "bottom right" }}>
          <div style={{ width: 84, height: 62, borderRadius: 14, background: `linear-gradient(135deg, ${t.accent}30, ${t.accent}0C)`, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
            <HouseGlyph color={t.accent} size={34} />
          </div>
          {(el.lines || [])[1] ? (
            <div style={{ fontFamily: t.fontBody, fontSize: 17, fontWeight: 600, color: t.ink, textAlign: "left", maxWidth: 240 }}>{(el.lines || [])[1]}</div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              <Bar w={130} h={12} o={0.32} color={t.ink} />
              <Bar w={88} h={10} color={t.ink} />
            </div>
          )}
        </div>
      ) : null}
    </div>
  );
};

/** Real pricing, big: the currency line as the hero figure, remaining site
 *  lines as checked rows. Everything shown is verbatim from the site. */
const VignettePriceCard: React.FC<{ el: WalkrecElement; t: WalkrecProps["theme"] }> = ({ el, t }) => {
  const frame = useCurrentFrame();
  const local = frame - el.at;
  const lines = el.lines || [];
  // The RECURRING price is the real offer; a bare figure may be the
  // crossed-out original — emphasizing it would misrepresent the price.
  const price =
    lines.find((l) => /[€$£¥]\s?\d[\d.,]*\s*\/\s*(year|month|mo|yr|wk|week)/i.test(l)) ||
    lines.find((l) => /[€$£¥]\s?\d|\d+[.,]\d{2}/.test(l));
  // Rows carry benefits/labels — a bare leftover price (the crossed-out
  // original) must not render as a checked benefit.
  const rest = lines.filter((l) => l !== price && !/^[€$£¥]\s?\d[\d.,]*$/.test(l.trim()));
  const pPrice = vinPop(local, 24, 14);
  return (
    <div style={{ background: t.card, borderRadius: 36, padding: "40px 48px", minWidth: 560, boxShadow: "0 40px 90px -36px rgba(15,20,40,0.28)", transform: `translateY(${vinFloat(local, 84)}px)` }}>
      <div style={{ fontFamily: t.fontBody, fontSize: 18, fontWeight: 700, letterSpacing: "0.08em", color: t.ink, opacity: 0.55 * vinP(local, 0), textAlign: "left" }}>
        {(el.text || "").toUpperCase()}
      </div>
      {price ? (
        <div style={{ fontFamily: t.fontDisplay, fontSize: 84, fontWeight: 700, letterSpacing: "-0.02em", color: t.accent, textAlign: "left", margin: "14px 0 6px", opacity: Math.min(1, pPrice), transform: `scale(${0.8 + 0.2 * pPrice})`, transformOrigin: "left center" }}>
          {price}
        </div>
      ) : null}
      <div style={{ marginTop: 18, display: "flex", flexDirection: "column", gap: 14 }}>
        {rest.slice(0, 3).map((l, i) => {
          const p = vinP(local, 44 + i * 8, 14);
          return (
            <div key={i} style={{ display: "flex", alignItems: "center", gap: 14, opacity: p, transform: `translateY(${16 * (1 - p)}px)` }}>
              <svg viewBox="0 0 24 24" style={{ width: 24, height: 24, flexShrink: 0 }}>
                <circle cx="12" cy="12" r="11" fill={`${t.accent}26`} />
                <path d="M 7 12.5 l 3.2 3.2 L 17 9" fill="none" stroke={t.accent} strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              <div style={{ fontFamily: t.fontBody, fontSize: 21, fontWeight: 600, color: t.ink, textAlign: "left" }}>{l}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

/** Night's chip sweep, walkrec-grounded: real short labels cascade in BIG. */
const VignetteChipSweep: React.FC<{ el: WalkrecElement; t: WalkrecProps["theme"] }> = ({ el, t }) => {
  const frame = useCurrentFrame();
  const local = frame - el.at;
  const chips = (el.chips || []).slice(0, 10);
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 18, justifyContent: "center", width: 980, transform: `translateY(${vinFloat(local, chips.length * 6 + 40)}px)` }}>
      {chips.map((c, i) => {
        const p = vinP(local, i * 6, 16);
        const hot = i % 4 === 1; // a few chips carry the accent
        return (
          <div key={i} style={{
            padding: "18px 30px", borderRadius: 999,
            background: hot ? `${t.accent}1F` : t.card,
            border: `2.5px solid ${hot ? t.accent : `${t.ink}22`}`,
            color: hot ? t.accent : t.ink,
            fontFamily: t.fontBody, fontSize: 27, fontWeight: 700,
            boxShadow: "0 22px 48px -24px rgba(15,20,40,0.25)",
            opacity: p, transform: `translateY(${26 * (1 - p)}px)`,
            filter: p < 0.97 ? `blur(${8 * (1 - p)}px)` : undefined,
          }}>
            {c}
          </div>
        );
      })}
    </div>
  );
};

/** Credibility number counting up to the REAL figure from the site line. */
const VignetteStatPop: React.FC<{ el: WalkrecElement; t: WalkrecProps["theme"] }> = ({ el, t }) => {
  const frame = useCurrentFrame();
  const local = frame - el.at;
  const line = (el.lines || []).find((l) => /\d/.test(l)) || el.text || "";
  const m = line.match(/([$€£]?)(\d+(?:[.,]\d+)?)([kKmM%+]*)/);
  const target = m ? parseFloat(m[2].replace(",", ".")) : 0;
  const decimals = m && m[2].includes(".") ? m[2].split(".")[1].length : 0;
  const p = interpolate(local, [8, 52], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: VEVARA_STEP });
  const shown = (target * p).toFixed(decimals);
  const label = m ? (line.slice(0, m.index) + line.slice((m.index || 0) + m[0].length)).trim() : line;
  return (
    <div style={{ transform: `translateY(${vinFloat(local, 70)}px)` }}>
      <div style={{ fontFamily: t.fontDisplay, fontSize: 168, fontWeight: 700, letterSpacing: "-0.03em", color: t.ink, lineHeight: 1 }}>
        {m ? `${m[1]}${shown}${m[3]}` : ""}
      </div>
      <div style={{ width: 150, height: 5, borderRadius: 3, background: t.accent, margin: "24px auto 18px", transform: `scaleX(${vinP(local, 40, 16)})` }} />
      <div style={{ fontFamily: t.fontBody, fontSize: 27, fontWeight: 600, color: t.inkMuted, opacity: vinP(local, 46, 14) }}>{label}</div>
    </div>
  );
};

/** Kinetic statement: the site's own line, word-by-word rise + deblur. */
const VignetteKineticLine: React.FC<{ el: WalkrecElement; t: WalkrecProps["theme"] }> = ({ el, t }) => {
  const frame = useCurrentFrame();
  const local = frame - el.at;
  const words = (el.text || "").split(/\s+/);
  const accentIdx = words.reduce((bi, w, i) => (w.length > words[bi].length ? i : bi), 0);
  return (
    <div style={{ width: 1100, fontFamily: t.fontDisplay, fontSize: 84, fontWeight: 700, letterSpacing: "-0.025em", lineHeight: 1.15, transform: `translateY(${vinFloat(local, words.length * 6 + 40)}px)` }}>
      {words.map((w, i) => {
        const p = vinP(local, i * 6, 18);
        return (
          <span key={i} style={{
            display: "inline-block", marginRight: "0.28em",
            color: i === accentIdx ? t.accent : t.ink,
            opacity: p, transform: `translateY(${34 * (1 - p)}px)`,
            filter: p < 0.97 ? `blur(${10 * (1 - p)}px)` : undefined,
          }}>
            {w}
          </span>
        );
      })}
    </div>
  );
};

const VIGNETTES: Record<string, React.FC<{ el: WalkrecElement; t: WalkrecProps["theme"] }>> = {
  "request-table": VignetteRequestTable,
  "context-cards": VignetteContextCards,
  "chat-exchange": VignetteChat,
  "price-card": VignettePriceCard,
  "check-list": VignettePriceCard,
  "chip-sweep": VignetteChipSweep,
  "stat-pop": VignetteStatPop,
  "kinetic-line": VignetteKineticLine,
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
    case "graphic": {
      const Vignette = el.motif ? VIGNETTES[el.motif] : undefined;
      return (
        <div style={{ ...base, width: el.w ?? 760 }}>
          {/* Inner scale keeps vignette layouts authored at comfortable px
              while filling the frame (Dennis: content must come BIG). */}
          <div style={{ transform: "scale(1.3)", transformOrigin: "center" }}>
            {Vignette ? <Vignette el={el} t={t} /> : <MotionGraphic el={el} t={t} frame={frame} />}
          </div>
        </div>
      );
    }
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
