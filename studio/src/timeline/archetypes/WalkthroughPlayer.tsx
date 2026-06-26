// WALKTHROUGH-PLAYER archetype — a produced walkthrough MP4 (Walk Agent capture)
// played INSIDE the branded studio composition. Maps a scene role: the "here is
// the actual guided walkthrough" beat.
//
// The clip's OWN audio is muted by default (`muteClip`, default true): the scene
// VO owns the audio (the Timeline places a per-scene <Audio> at this scene's
// in_frame). So the produced clip inherits Walk Studio's branding + VO placement
// instead of carrying its own baked-in narration.
//
// DARKFIX (2026-06-23) — SPLIT retreatment so the walkthrough reads as an
// INTENTIONAL, LIGHT-framed, clearly-animated tour REGARDLESS of how dark the
// captured site is.
//
//   WHY: the R4 "device-hero" filled the frame with an 880px clip window at
//   cover-fit. On a LIGHT site (Stripe) that looked great. On a DARK site (e.g.
//   Linear / linear.app) the captured page is near-black, so the clip window
//   became a full-bleed black rectangle for ~1/3 of the video — jarring against
//   the polished LIGHT split scenes before it (Dennis: "looks broken").
//
//   FIX: adopt the SAME text-left / UI-right SPLIT DNA as the apple-screenshot
//   keystone. A clearly-LIGHT left column (tracked eyebrow + kinetic headline +
//   accent underline + supporting line) always reads on the near-white page, and
//   the walkthrough clip sits in a smaller, inset, browser-chrome DEVICE FRAME on
//   the RIGHT — so even a dark captured page sits inside a deliberate, light,
//   designed context, balanced exactly like the splits. The dark page no longer
//   fills the frame; it's a framed artifact the LIGHT page wraps.
//
//   The synthetic device-hero motion (R4) is PRESERVED but re-scoped to the
//   right-side clip window so it reads CLEARLY on a dark page: frame-rise arrival,
//   an auto Ken-Burns push, a guided cursor + click ripple, a highlight ring, and
//   an optional KPI counter-roll chip — all running with NO scene data (the
//   common $0-standard case, L6) and all OVERRIDABLE by explicit data.* fields.
//
// Reveals fire on the scene's CUE frames (relative to scene in_frame):
//   eyebrow-in -> the left eyebrow rises,
//   headline-in/title-in -> the headline lines stagger in,
//   frame-in/card-in -> the device frame arrives (frame-rise),
//   accent -> the brand accent underline sweeps in under the headline.
// Sensible fallback cue frames keep it animating even when a scene has no cues.
import React from "react";
import {
  AbsoluteFill,
  Img,
  OffthreadVideo,
  interpolate,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import type { Cue, SceneData, Theme } from "../types";
import {
  appleRise,
  breathDrift,
  EASE_OUT_QUART,
  alphaHex,
  actNum,
  actLabel,
  frameRise,
  cursorAt,
  highlightBox,
  zoomPunch,
  rollNumber,
  approveChip,
  tailGlow,
} from "../motion";

const cueAt = (cues: Cue[], label: string, fallback: number) =>
  cues.find((c) => c.label === label)?.at_frame ?? fallback;

// Resolve a public-relative logo path via staticFile; http/leading-slash pass
// through. ABSENT theme.logoSrc => corner mark degrades to the wordmark.
const resolveLogo = (path: string): string =>
  path.startsWith("http") || path.startsWith("/") ? path : staticFile(path);

// Parse a short numeric KPI out of a string for the counter-roll chip. Returns
// the prefix (e.g. "$"), the numeric target, and the suffix (e.g. "+", "M", "%")
// so the chip can roll the number while keeping the brand-true label intact.
// Returns null when no number is found (chip then shows nothing — never invents).
const parseKpi = (raw: string): { prefix: string; to: number; suffix: string; label: string } | null => {
  const m = raw.match(/([£$€]?)\s*([\d][\d,\.]*)\s*([%+]|[KMB]\+?|[a-z]+)?/i);
  if (!m) return null;
  const prefix = m[1] ?? "";
  const to = parseFloat(m[2].replace(/,/g, ""));
  if (!isFinite(to) || to <= 0) return null;
  const suffix = (m[3] ?? "").trim();
  // The label is the words AFTER the number (e.g. "businesses", "uptime").
  const after = raw.slice((m.index ?? 0) + m[0].length).trim();
  const label = after.replace(/^[\s·,—-]+/, "").slice(0, 28);
  return { prefix, to, suffix, label };
};

// Format a rolling number with thousands separators (integers) or one decimal
// (when the target is fractional, e.g. 99.9). Keeps the brand prefix/suffix.
const fmtKpi = (n: number, to: number, prefix: string, suffix: string): string => {
  const frac = !Number.isInteger(to);
  const v = frac ? n.toFixed(1) : Math.round(n).toLocaleString("en-US");
  return `${prefix}${v}${suffix ? suffix : ""}`;
};

// Derive a LEFT-column eyebrow + headline from the overlayTitle (which style_fill
// builds as "Brand — emphasis", e.g. "Stripe — accept payments in one
// integration"). The brand part feeds the eyebrow chrome; the emphasis is the
// kinetic headline. Honest: only ever SPLITS the real overlayTitle, never invents.
const splitOverlay = (raw: string, wordmark: string): { brand: string; headline: string } => {
  const t = (raw || "").trim();
  // Prefer an en-dash / em-dash / hyphen separator ("Brand — emphasis").
  const m = t.match(/^(.*?)\s*[—–-]\s*(.+)$/);
  if (m && m[1].trim() && m[2].trim()) {
    return { brand: m[1].trim(), headline: m[2].trim() };
  }
  // No separator: the whole thing is the headline; eyebrow falls to the wordmark.
  return { brand: (wordmark || "").trim(), headline: t || (wordmark || "").trim() };
};

// Capitalize the first letter of a display headline (the emphasis often arrives
// lower-case, e.g. "accept payments in one integration"). Never touches the rest.
const sentenceCase = (s: string): string =>
  s ? s.charAt(0).toUpperCase() + s.slice(1) : s;

// Split a headline into ~2 balanced display lines for the left column (mirrors the
// apple-screenshot split heuristic; the column holds ~18 chars/line at this size).
const splitHeadlineLines = (text: string, maxLines = 3): string[] => {
  const t = (text || "").trim();
  if (!t) return [];
  const words = t.split(/\s+/);
  if (words.length <= 2) return [t];
  // Greedy wrap near a target line length so a long emphasis breaks cleanly.
  const TARGET = Math.max(14, Math.ceil(t.length / Math.min(maxLines, 3)));
  const lines: string[] = [];
  let cur = "";
  for (const w of words) {
    const next = cur ? `${cur} ${w}` : w;
    if (next.length > TARGET && cur) {
      lines.push(cur);
      cur = w;
    } else {
      cur = next;
    }
    if (lines.length === maxLines - 1) {
      // last line takes the remainder
      const idx = words.indexOf(w);
      cur = words.slice(idx).join(" ");
      break;
    }
  }
  if (cur) lines.push(cur);
  return lines.slice(0, maxLines);
};

// Render a single headline line with the punch noun (if any) accent-popped.
const splitPunch = (line: string, punch?: string): { pre: string; hit: string; post: string } => {
  const p = (punch || "").trim();
  if (!p) return { pre: line, hit: "", post: "" };
  const i = line.toLowerCase().indexOf(p.toLowerCase());
  if (i < 0) return { pre: line, hit: "", post: "" };
  return { pre: line.slice(0, i), hit: line.slice(i, i + p.length), post: line.slice(i + p.length) };
};

// A web address for the device-frame chrome bar (the captured-page URL, when the
// caption carries one). Strips the scheme so it reads like a browser address.
const toAddr = (caption: string, fallback: string): string => {
  const c = (caption || "").trim();
  const base = c || fallback;
  return base.replace(/^https?:\/\//, "").replace(/\/$/, "");
};

export const WalkthroughPlayer: React.FC<{
  data: SceneData;
  cues: Cue[];
  theme: Theme;
  durationInFrames: number;
  // resolver injected by Timeline.tsx (same staticFile-or-passthrough helper as
  // audio + the apple-screenshot image).
  resolveSrc: (path: string) => string;
  // 1-based act index among content-beat scenes (-1 = no badge)
  actIndex?: number;
  // OPTIONAL: scene id, threaded from Timeline for click-to-select addressing.
  sceneId?: string;
}> = ({ data, cues, theme, durationInFrames, resolveSrc, actIndex = -1, sceneId }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const src = data.videoSrc ? resolveSrc(data.videoSrc) : "";
  // DARKFIX: the walkthrough clip defaults to COVER so the captured UI fills the
  // device-frame window (no dark letterbox wells inside the frame). An explicit
  // data.videoFit still wins (set "contain" for a clip you must not crop).
  // NOTE: style_fill sets "contain" by default; the frame is light-chromed so even
  // contain reads fine, but cover keeps the framed clip looking full.
  const fit = data.videoFit ?? "cover";
  // VO owns the audio: clips mute by default. Only an explicit false keeps sound.
  const muted = data.muteClip !== false;

  // ---- Left-column copy (derived from overlayTitle: "Brand — emphasis") -------
  const overlay = (data.overlayTitle ?? theme.wordmark ?? "").trim();
  const wordmark = (theme.wordmark ?? "").trim();
  const { brand, headline: rawHeadline } = splitOverlay(overlay, wordmark);
  const headlineText = sentenceCase(rawHeadline) || wordmark;
  const headlineLines = splitHeadlineLines(headlineText, 3);
  // Supporting line: an explicit caption is used as the device URL, so the muted
  // supporting line under the headline is the kicker (when distinct) else nothing.
  const kickerText = (data.kicker ?? "").trim();
  const supportingLine =
    kickerText && kickerText.toLowerCase() !== headlineText.toLowerCase() ? kickerText : "";

  // ---- Cue timeline (scene-length-scaled fallbacks so SHORT scenes still land) -
  const eyebrowAt = cueAt(cues, "eyebrow-in", Math.min(4, Math.round(durationInFrames * 0.04)));
  const headlineAt = cueAt(
    cues,
    "headline-in",
    cueAt(cues, "title-in", Math.min(16, Math.round(durationInFrames * 0.1)))
  );
  const cardAt = cueAt(cues, "frame-in", cueAt(cues, "card-in", headlineAt + 6));
  const accentAt = cueAt(cues, "accent", headlineAt + 26);

  // ---- LEFT column motion -----------------------------------------------------
  const eyebrowOpacity = interpolate(frame, [eyebrowAt, eyebrowAt + 12], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: EASE_OUT_QUART,
  });
  const eyebrowY = interpolate(frame, [eyebrowAt, eyebrowAt + 12], [10, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: EASE_OUT_QUART,
  });
  const LINE_STAGGER = 16;
  const LINE_DUR = 18;
  const punchAt = headlineAt + 14;
  const punchGlow = interpolate(
    frame,
    [punchAt, punchAt + 14, punchAt + 40, durationInFrames - 18, durationInFrames],
    [0, 1, 0.6, 0.85, 0.5],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );
  const underlineW = interpolate(frame, [accentAt, accentAt + 20], [0, 132], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: EASE_OUT_QUART,
  });
  const supportingMotion = appleRise(frame, headlineAt + 30, 18, 18);

  // ---- RIGHT column: device frame geometry (the split UI-right card) ----------
  // Mirrors the apple-screenshot split: a fixed left column + a right-inset card.
  // The card is generous (the walkthrough is the demo beat) but NOT full-bleed —
  // the left light column + page margins always frame it, so a dark page reads as
  // a deliberate framed artifact, never a black rectangle.
  const leftX = 110;
  const leftColW = 620;
  const CARD_W = 1010;
  const CARD_RIGHT = 70;
  const WIN_W = CARD_W;
  const WIN_H = 632; // clip window (matches the split shot footprint, ~16:10)

  const rise = frameRise(frame, cardAt, fps, { dy: 56, scaleFrom: 0.92, tilt: 6, fadeDur: 16 });
  const ARRIVE = 28;
  const maskReveal = interpolate(frame, [cardAt + 4, cardAt + 4 + ARRIVE], [100, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: EASE_OUT_QUART,
  });
  // breath drift keeps the settled card alive (tiny, deterministic).
  const breath = breathDrift(frame, cardAt + ARRIVE + 6, 2.5, 110);

  const exitFade = interpolate(frame, [durationInFrames - 14, durationInFrames], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: EASE_OUT_QUART,
  });

  // The motion layer starts AFTER the clip has revealed.
  const motionAt = cardAt + 4 + ARRIVE;
  const tailEnd = durationInFrames - 16;

  // Derived HOTSPOT (card-local normalized 0..1): where the cursor goes, the ring
  // draws, and the Ken-Burns pushes. data.focus center when given; else an
  // upper-center bias (where app UI action usually lives).
  const focus = data.focus;
  const hotspot = focus
    ? { x: focus.x + focus.w / 2, y: focus.y + focus.h / 2 }
    : { x: 0.6, y: 0.32 };

  // AUTO Ken-Burns zoom-drift — runs even with NO data so the held UI never freezes.
  const zTarget = data.zoomTo ?? { x: hotspot.x, y: hotspot.y, scale: 1.1 };
  const zoom = zoomPunch(frame, motionAt, zTarget, zTarget.scale ?? 1.1, {
    dur: 60,
    holdEnd: tailEnd,
    boxW: WIN_W,
    boxH: WIN_H,
  });

  // AUTO guided cursor — springs from lower-left toward the hotspot, clicks
  // (ripple), then drifts a touch. data.cursorPath (card-local %) overrides.
  const clickFrame = motionAt + 26;
  const autoPath = [
    { at: motionAt + 4, x: 0.2, y: 0.78 },
    { at: clickFrame, x: hotspot.x, y: hotspot.y, click: true },
    { at: clickFrame + 36, x: hotspot.x + 0.06, y: hotspot.y + 0.05 },
  ];
  const cursorKeys = (data.cursorPath && data.cursorPath.length
    ? data.cursorPath.map((k) => ({ at: motionAt + k.at, x: k.x, y: k.y, click: k.click }))
    : autoPath
  ).map((k) => ({ at: k.at, x: k.x * WIN_W, y: k.y * WIN_H, click: k.click }));
  const cursor = cursorAt(frame, cursorKeys, fps);
  // Cursor + click-ripple glyph is DISABLED — mirrors AppleScreenshot.tsx
  // (`const cursor = null;`). The arrow/ripple SVG reads as a literal mouse
  // pointer baked into the frame; the highlight ring below carries the focus.
  // Forcing opacity to 0 keeps the cursorAt/cursorKeys math (used by the ring
  // timing) intact while never rendering the pointer or ripples.
  const cursorOpacity = 0;

  // highlight ring at the hotspot, drawn on at the cursor click.
  const ringAt = clickFrame - 4;
  const hl = highlightBox(frame, ringAt, tailEnd, 14);
  const ringRect = focus ?? { x: hotspot.x - 0.14, y: hotspot.y - 0.07, w: 0.28, h: 0.14 };

  // KPI counter-roll chip — only when a real number exists (never invents).
  const kpiRaw = (data.kpi ?? "").trim();
  const kpi = kpiRaw ? parseKpi(kpiRaw) : null;
  const kpiAt = motionAt + 18;
  const kpiPop = approveChip(frame, kpiAt, fps);
  const kpiNow = kpi ? rollNumber(frame, kpiAt + 4, kpi.to, 44) : 0;
  const kpiGlow = tailGlow(frame, kpiAt + 10, tailEnd);

  // Persistent corner brand mark (spec §4): real logo when present, else wordmark.
  const logoSrc = (theme.logoSrc ?? "").trim();
  const cornerWordmark = (theme.wordmark ?? "").trim();
  const cornerOpacity = interpolate(frame, [cardAt, cardAt + 18], [0, 0.7], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: EASE_OUT_QUART,
  });

  // Eyebrow text: "NN · BRAND" (act badge folded in, like the screenshot split).
  const eyebrowLabel = actLabel(brand) || brand.toUpperCase();
  const eyebrowText =
    actIndex > 0
      ? `${actNum(actIndex)}${eyebrowLabel ? ` · ${eyebrowLabel}` : ""}`
      : eyebrowLabel;

  // Device-frame chrome address (captured URL when caption carries one).
  const addr = toAddr(data.caption ?? "", `${(wordmark || "app").toLowerCase()}.com`);

  return (
    <AbsoluteFill
      style={{
        backgroundColor: theme.bg,
        fontFamily: theme.fontDisplay,
        opacity: exitFade,
      }}
    >
      {/* soft brand mesh — drifting blooms so the near-white page breathes (same
          light page language as the apple-screenshot split). */}
      <AbsoluteFill
        style={{
          background: `
            radial-gradient(ellipse 1100px 780px at ${22 + breath * 0.4}% 24%, ${theme.navy}1c 0%, transparent 60%),
            radial-gradient(ellipse 1000px 760px at ${80 - breath * 0.4}% 82%, ${theme.accent}18 0%, transparent 60%),
            ${theme.bg}
          `,
        }}
      />

      {/* LEFT COLUMN — eyebrow + kinetic headline + accent underline + supporting.
          ALWAYS light + always visible, regardless of how dark the captured page
          on the right is. This is what makes the dark-site walkthrough read as a
          deliberate, light-framed tour instead of a black rectangle. */}
      <div
        style={{
          position: "absolute",
          left: leftX,
          top: 0,
          bottom: 0,
          width: leftColW,
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          gap: 22,
          zIndex: 3,
        }}
      >
        {eyebrowText && (
          <div
            data-scene-id={sceneId}
            data-field="kicker"
            style={{
              opacity: eyebrowOpacity,
              transform: `translateY(${eyebrowY}px)`,
              fontSize: 22,
              fontWeight: 700,
              letterSpacing: "0.18em",
              textTransform: "uppercase",
              color: theme.accent,
              fontFamily: theme.fontMono,
            }}
          >
            {eyebrowText}
          </div>
        )}

        {/* Headline — staggered lines, punch noun accent-popped. */}
        <div
          data-scene-id={sceneId}
          data-field="overlayTitle"
          style={{ display: "flex", flexDirection: "column", gap: 2 }}
        >
          {headlineLines.map((line, li) => {
            const lineStart = headlineAt + li * LINE_STAGGER;
            const lineOpacity = interpolate(frame, [lineStart, lineStart + LINE_DUR], [0, 1], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
              easing: EASE_OUT_QUART,
            });
            const lineY = interpolate(frame, [lineStart, lineStart + LINE_DUR], [28, 0], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
              easing: EASE_OUT_QUART,
            });
            const { pre, hit, post } = splitPunch(line, data.punchWord);
            return (
              <div
                key={li}
                style={{
                  opacity: lineOpacity,
                  transform: `translateY(${lineY}px)`,
                  fontSize: 64,
                  fontWeight: 700,
                  lineHeight: 1.08,
                  letterSpacing: "-0.02em",
                  color: theme.text,
                }}
              >
                {pre}
                {hit && (
                  <span
                    style={{
                      color: theme.accent,
                      textShadow: `0 0 ${44 * punchGlow}px ${theme.accent}${alphaHex(punchGlow * 0.7)}`,
                    }}
                  >
                    {hit}
                  </span>
                )}
                {post}
              </div>
            );
          })}
        </div>

        {/* accent underline wipe */}
        <div
          style={{
            width: underlineW,
            height: 5,
            borderRadius: 3,
            backgroundColor: theme.accent,
            boxShadow: `0 0 ${16 * Math.max(0.3, punchGlow)}px ${theme.accent}88`,
          }}
        />

        {/* supporting line (muted) — the kicker, when distinct from the headline. */}
        {supportingLine && (
          <div
            data-scene-id={sceneId}
            data-field="supporting"
            style={{
              opacity: supportingMotion.opacity,
              transform: supportingMotion.transform,
              fontSize: 26,
              fontWeight: 400,
              lineHeight: 1.4,
              maxWidth: leftColW - 30,
              color: theme.textMuted,
            }}
          >
            {supportingLine}
          </div>
        )}
      </div>

      {/* RIGHT COLUMN — the walkthrough clip inside a light browser-chrome device
          frame, inset from the right edge. frame-rise arrival; the synthetic
          device-hero motion plays over the held clip. */}
      <div
        style={{
          position: "absolute",
          right: CARD_RIGHT,
          top: 0,
          bottom: 0,
          display: "flex",
          alignItems: "center",
          transform: `translateY(${breath}px)`,
        }}
      >
        <div
          data-scene-id={sceneId}
          data-field="card"
          style={{
            opacity: rise.opacity,
            transform: rise.transform,
            transformOrigin: "center bottom",
            width: CARD_W,
            borderRadius: 18,
            overflow: "hidden",
            backgroundColor: theme.bgCardRaised,
            border: `1px solid ${theme.border}`,
            boxShadow: [
              "0 50px 140px rgba(15,35,56,0.26)",
              "0 12px 36px rgba(15,35,56,0.14)",
              "inset 0 1px 0 rgba(255,255,255,0.9)",
            ].join(", "),
          }}
        >
          {/* Light mac browser chrome — brand-tinted dots + address pill (the SAME
              chrome as the apple-screenshot split). A LIGHT bar is always on top,
              so even a dark captured page sits under a clearly light header. */}
          <div
            style={{
              height: 52,
              display: "flex",
              alignItems: "center",
              gap: 16,
              padding: "0 22px",
              backgroundColor: theme.bgCard,
              borderBottom: `1px solid ${theme.border}`,
            }}
          >
            <div style={{ display: "flex", gap: 9 }}>
              {[theme.navy, theme.accent, theme.navyBright].map((c, i) => (
                <div
                  key={i}
                  style={{ width: 13, height: 13, borderRadius: "50%", backgroundColor: c, opacity: 0.85 }}
                />
              ))}
            </div>
            <div
              data-scene-id={sceneId}
              data-field="caption"
              style={{
                flex: 1,
                height: 30,
                borderRadius: 8,
                backgroundColor: theme.bg,
                border: `1px solid ${theme.border}`,
                display: "flex",
                alignItems: "center",
                padding: "0 14px",
                fontSize: 18,
                fontFamily: theme.fontMono,
                letterSpacing: "0.01em",
                color: theme.textMuted,
                whiteSpace: "nowrap",
                overflow: "hidden",
                textOverflow: "ellipsis",
              }}
            >
              {addr}
            </div>
          </div>

          {/* the produced walkthrough clip, mask-revealed top-down as it arrives */}
          <div
            style={{
              position: "relative",
              width: "100%",
              height: WIN_H,
              overflow: "hidden",
              // light-treatment: the well reads as a light card surface for the
              // no-clip placeholder / any contain-fit clip (never a dark box).
              backgroundColor: theme.bgCard,
              clipPath: `inset(${maskReveal}% 0 0 0)`,
            }}
          >
            {/* zoom-punch layer — AUTO Ken-Burns push toward the hotspot so the
                held UI is always slowly moving. transformOrigin top-left so the
                normalized math is exact. */}
            <div
              style={{
                position: "absolute",
                inset: 0,
                transform: zoom.transform,
                transformOrigin: "0 0",
              }}
            >
              {src ? (
                <OffthreadVideo
                  src={src}
                  muted={muted}
                  style={{
                    width: "100%",
                    height: "100%",
                    objectFit: fit,
                    objectPosition: "center top",
                    display: "block",
                  }}
                />
              ) : (
                // never-blank floor: an on-brand placeholder if no clip is staged.
                <AbsoluteFill
                  style={{
                    alignItems: "center",
                    justifyContent: "center",
                    color: theme.textDim,
                    fontFamily: theme.fontMono,
                    fontSize: 26,
                    letterSpacing: "0.04em",
                  }}
                >
                  {headlineText || theme.wordmark}
                </AbsoluteFill>
              )}
            </div>

            {/* highlight-box — a rounded accent ring + tint draws ON at the hotspot,
                tied to the cursor click. Reads CLEARLY over a dark page. */}
            {hl.opacity > 0.001 && (
              <div
                data-scene-id={sceneId}
                data-field="focus"
                style={{
                  position: "absolute",
                  left: `${ringRect.x * 100}%`,
                  top: `${ringRect.y * 100}%`,
                  width: `${ringRect.w * 100}%`,
                  height: `${ringRect.h * 100}%`,
                  borderRadius: 14,
                  border: `2.5px solid ${theme.accent}`,
                  backgroundColor: `${theme.accent}${alphaHex(0.08 * hl.opacity)}`,
                  boxShadow: `0 0 0 4px ${theme.accent}${alphaHex(0.12 * hl.opacity)}, 0 0 30px ${theme.accent}${alphaHex(0.34 * hl.opacity)}`,
                  opacity: hl.opacity,
                  pointerEvents: "none",
                }}
              />
            )}

            {/* cursor-move — an arrow cursor springs to the hotspot and clicks
                (ripple). AUTO path when no data.cursorPath. */}
            <svg
              viewBox={`0 0 ${WIN_W} ${WIN_H}`}
              preserveAspectRatio="none"
              style={{
                position: "absolute",
                inset: 0,
                width: "100%",
                height: "100%",
                pointerEvents: "none",
                overflow: "visible",
                opacity: cursorOpacity,
              }}
            >
              {cursor.ripples.map((rp) => (
                <circle
                  key={rp.at}
                  cx={rp.x}
                  cy={rp.y}
                  r={rp.r}
                  fill="none"
                  stroke={theme.accent}
                  strokeWidth={3}
                  opacity={rp.opacity}
                />
              ))}
              <g transform={`translate(${cursor.x - 4} ${cursor.y - 2})`}>
                <path
                  d="M0 0 L0 34 L9 26 L14 38 L20 36 L15 24 L26 24 Z"
                  fill="#ffffff"
                  stroke={theme.text}
                  strokeWidth={1.6}
                  strokeLinejoin="round"
                />
              </g>
            </svg>

            {/* KPI counter-roll chip — only when a real number exists; never invents. */}
            {kpi && kpiPop.opacity > 0.001 && (
              <div
                data-scene-id={sceneId}
                data-field="kpi"
                style={{
                  position: "absolute",
                  left: 36,
                  bottom: 36,
                  display: "flex",
                  alignItems: "center",
                  gap: 14,
                  padding: "14px 20px",
                  borderRadius: 16,
                  backgroundColor: `${theme.bgCardRaised}f2`,
                  border: `1px solid ${theme.border}`,
                  boxShadow: `0 18px 50px rgba(15,35,56,0.22), 0 0 30px ${theme.accent}${alphaHex(0.18 * kpiGlow)}`,
                  opacity: kpiPop.opacity,
                  transform: kpiPop.transform,
                  transformOrigin: "left bottom",
                }}
              >
                <div
                  style={{
                    width: 10,
                    height: 10,
                    borderRadius: "50%",
                    backgroundColor: theme.accent,
                    boxShadow: `0 0 ${10 * kpiGlow}px ${theme.accent}`,
                  }}
                />
                <span
                  style={{
                    fontSize: 34,
                    fontWeight: 800,
                    letterSpacing: "-0.02em",
                    color: theme.text,
                    fontFamily: theme.fontMono,
                    fontVariantNumeric: "tabular-nums",
                  }}
                >
                  {fmtKpi(kpiNow, kpi.to, kpi.prefix, kpi.suffix)}
                </span>
                {kpi.label ? (
                  <span style={{ fontSize: 18, fontWeight: 500, color: theme.textMuted, maxWidth: 200 }}>
                    {kpi.label}
                  </span>
                ) : null}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Persistent corner brand mark (spec §4) — bottom-right, low-key. */}
      {(logoSrc || cornerWordmark) && (
        <div
          data-scene-id={sceneId}
          data-field="cornerMark"
          style={{
            position: "absolute",
            right: 56,
            bottom: 40,
            opacity: cornerOpacity,
            display: "flex",
            alignItems: "center",
            height: 30,
            pointerEvents: "none",
            zIndex: 4,
          }}
        >
          {logoSrc ? (
            <Img
              src={resolveLogo(logoSrc)}
              style={{ height: "100%", width: "auto", objectFit: "contain", display: "block", opacity: 0.9 }}
            />
          ) : (
            <span
              style={{
                fontSize: 22,
                fontWeight: 600,
                letterSpacing: "0.02em",
                color: theme.textDim,
                fontFamily: theme.fontDisplay,
              }}
            >
              {cornerWordmark}
            </span>
          )}
        </div>
      )}
    </AbsoluteFill>
  );
};
