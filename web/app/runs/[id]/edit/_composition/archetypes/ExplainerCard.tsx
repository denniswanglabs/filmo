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
//
// RICH TREATMENTS (feature-card-richness spec): switch on data.treatment:
//   "icon-stat"     — centered: kicker · SVG icon tile · headline · stat row
//   "split-mosaic"  — 2-col: text left + dark entity-tile grid right
//   "split-stat"    — 2-col: text left + light stat panel right (rising bars)
//   "icon-headline" — centered, FULL-WIDTH: kicker · SVG icon · headline (FALLBACK)
//   "big-number"    — full-bleed: kicker · HUGE stat.value · label · title line
//   "logo-wall"     — centered header + a fuller branded-chip grid of entities
//   "feature-list"  — title + a clean vertical "what you get" check-row list
//   absent/unknown  — ORIGINAL card (backward-compat, byte-identical behavior)
//
// NOTE (DORMANT): big-number / logo-wall / feature-list RENDER + are registered
// in the treatment union + Python validation, but NO selection logic emits them
// yet (the orchestrator wires selection later, one at a time, measured). Today
// nothing sets data.treatment to these, so behavior is unchanged.
//
// DEGRADE-TO-CENTER GUARD (kills the right-side white-space bug): the two-column
// + data-driven treatments require their data. When "split-mosaic"/"logo-wall"
// has no featureEntities, "split-stat"/"icon-stat"/"big-number" has no stat, or
// "feature-list" has neither entities nor a subtitle, we DROP to the centered
// full-width "icon-headline" fallback instead of rendering a blank / ghosted /
// empty layout. The fallback is symmetric + centered so it FILLS WIDTH.
import React from "react";
import { AbsoluteFill, Img, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import type { Cue, SceneData, Theme } from "../types";
import { ease, reveal, interpClamp, alphaHex, actNum, actLabel, splitToLines, stagedLine } from "../motion";

const cueAt = (cues: Cue[], label: string, fallback: number) =>
  cues.find((c) => c.label === label)?.at_frame ?? fallback;

// Resolve a public-relative logo path. http/leading-slash pass through. When a
// `resolve` (the Timeline assetBaseUrl seam) is passed, public-relative names
// resolve against the hosted bucket so the EDITOR PREVIEW shows the real logo
// (matches how screenshots/VO/music/walkthrough already resolve); absent it
// falls back to staticFile (the studio render path). ABSENT theme.logoSrc =>
// corner mark degrades to the wordmark.
const resolveLogo = (path: string, resolve?: (p: string) => string): string =>
  path.startsWith("http") || path.startsWith("/") || path.startsWith("data:")
    ? path
    : resolve
      ? resolve(path)
      : staticFile(path);

// Persistent corner brand mark (spec §4) — bottom-right, low-key. Real logo
// <Img> when present, else wordmark text; nothing when neither exists.
const CornerMark: React.FC<{
  theme: Theme;
  opacity: number;
  sceneId?: string;
  resolveSrc?: (p: string) => string;
}> = ({ theme, opacity, sceneId, resolveSrc }) => {
  const logoSrc = (theme.logoSrc ?? "").trim();
  const wordmark = (theme.wordmark ?? "").trim();
  if (!logoSrc && !wordmark) return null;
  return (
    <div
      data-scene-id={sceneId}
      data-field="cornerMark"
      style={{
        position: "absolute",
        right: 56,
        bottom: 40,
        opacity,
        display: "flex",
        alignItems: "center",
        height: 30,
        pointerEvents: "none",
      }}
    >
      {logoSrc ? (
        <Img
          src={resolveLogo(logoSrc, resolveSrc)}
          style={{ height: "100%", width: "auto", objectFit: "contain", display: "block", opacity: 0.9 }}
        />
      ) : (
        <span
          style={{
            fontSize: 20,
            fontWeight: 600,
            letterSpacing: "0.02em",
            color: theme.textDim,
            fontFamily: theme.fontDisplay,
          }}
        >
          {wordmark}
        </span>
      )}
    </div>
  );
};

// ---------------------------------------------------------------------------
// Icon set — inline SVG paths for curated icon names. Stroke style, 24px
// viewBox, ACCENT color for stroke. Unknown / missing → "spark" (never a
// broken / empty icon slot).
// ---------------------------------------------------------------------------
const ACCENT = "#3B82F6";

type IconName =
  | "rocket" | "spark" | "shield" | "chart" | "users" | "bolt"
  | "globe" | "dollar" | "layers" | "sparkles" | "target" | "clock";

const ICON_PATHS: Record<IconName, React.ReactNode> = {
  rocket: (
    <>
      <path d="M12 2C12 2 7 7 7 14l5 5 5-5c0-7-5-12-5-12z" stroke={ACCENT} strokeWidth="2" fill="none" strokeLinejoin="round"/>
      <circle cx="12" cy="13" r="2" stroke={ACCENT} strokeWidth="2" fill="none"/>
      <path d="M9 19l-2 3M15 19l2 3" stroke={ACCENT} strokeWidth="1.5" strokeLinecap="round"/>
    </>
  ),
  spark: (
    <>
      <path d="M12 2l2.5 7H22l-6.5 4.5 2.5 7L12 17l-6 3.5 2.5-7L2 9h7.5z" stroke={ACCENT} strokeWidth="2" fill="none" strokeLinejoin="round"/>
    </>
  ),
  shield: (
    <>
      <path d="M12 3L4 7v5c0 4.4 3.4 8.5 8 9.5 4.6-1 8-5.1 8-9.5V7l-8-4z" stroke={ACCENT} strokeWidth="2" fill="none" strokeLinejoin="round"/>
      <path d="M9 12l2 2 4-4" stroke={ACCENT} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
    </>
  ),
  chart: (
    <>
      <rect x="3" y="14" width="4" height="7" rx="1" stroke={ACCENT} strokeWidth="2" fill="none"/>
      <rect x="10" y="9" width="4" height="12" rx="1" stroke={ACCENT} strokeWidth="2" fill="none"/>
      <rect x="17" y="4" width="4" height="17" rx="1" stroke={ACCENT} strokeWidth="2" fill="none"/>
    </>
  ),
  users: (
    <>
      <circle cx="9" cy="8" r="3" stroke={ACCENT} strokeWidth="2" fill="none"/>
      <path d="M3 20c0-3.3 2.7-6 6-6s6 2.7 6 6" stroke={ACCENT} strokeWidth="2" fill="none" strokeLinecap="round"/>
      <circle cx="17" cy="8" r="2.5" stroke={ACCENT} strokeWidth="1.5" fill="none"/>
      <path d="M21 20c0-2.8-1.8-5.2-4.3-6" stroke={ACCENT} strokeWidth="1.5" fill="none" strokeLinecap="round"/>
    </>
  ),
  bolt: (
    <>
      <path d="M13 2L4 14h8l-1 8 9-12h-8l1-8z" stroke={ACCENT} strokeWidth="2" fill="none" strokeLinejoin="round"/>
    </>
  ),
  globe: (
    <>
      <circle cx="12" cy="12" r="9" stroke={ACCENT} strokeWidth="2" fill="none"/>
      <ellipse cx="12" cy="12" rx="4" ry="9" stroke={ACCENT} strokeWidth="1.5" fill="none"/>
      <path d="M3 12h18" stroke={ACCENT} strokeWidth="1.5"/>
      <path d="M3 8h18M3 16h18" stroke={ACCENT} strokeWidth="1" opacity="0.5"/>
    </>
  ),
  dollar: (
    <>
      <circle cx="12" cy="12" r="9" stroke={ACCENT} strokeWidth="2" fill="none"/>
      <path d="M12 7v10M9.5 9.5c0-1.4 1.1-2.5 2.5-2.5s2.5 1.1 2.5 2.5S13.4 14 12 14s-2.5 1.1-2.5 2.5S10.6 19 12 19" stroke={ACCENT} strokeWidth="1.5" fill="none" strokeLinecap="round"/>
    </>
  ),
  layers: (
    <>
      <path d="M2 12l10 6 10-6" stroke={ACCENT} strokeWidth="2" fill="none" strokeLinejoin="round"/>
      <path d="M2 17l10 6 10-6" stroke={ACCENT} strokeWidth="1.5" fill="none" strokeLinejoin="round" opacity="0.6"/>
      <path d="M12 2L2 7l10 5 10-5-10-5z" stroke={ACCENT} strokeWidth="2" fill="none" strokeLinejoin="round"/>
    </>
  ),
  sparkles: (
    <>
      <path d="M12 2l1.5 4.5L18 8l-4.5 1.5L12 14l-1.5-4.5L6 8l4.5-1.5z" stroke={ACCENT} strokeWidth="1.5" fill="none" strokeLinejoin="round"/>
      <path d="M19 14l.8 2.2L22 17l-2.2.8L19 20l-.8-2.2L16 17l2.2-.8z" stroke={ACCENT} strokeWidth="1.5" fill="none" strokeLinejoin="round"/>
      <path d="M5 16l.6 1.4L7 18l-1.4.6L5 20l-.6-1.4L3 18l1.4-.6z" stroke={ACCENT} strokeWidth="1.5" fill="none" strokeLinejoin="round"/>
    </>
  ),
  target: (
    <>
      <circle cx="12" cy="12" r="9" stroke={ACCENT} strokeWidth="2" fill="none"/>
      <circle cx="12" cy="12" r="5" stroke={ACCENT} strokeWidth="1.5" fill="none"/>
      <circle cx="12" cy="12" r="2" stroke={ACCENT} strokeWidth="1.5" fill="none"/>
    </>
  ),
  clock: (
    <>
      <circle cx="12" cy="12" r="9" stroke={ACCENT} strokeWidth="2" fill="none"/>
      <path d="M12 7v5l3.5 3.5" stroke={ACCENT} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
    </>
  ),
};

// Curated-icons-only resolver: unknown / missing → "spark" default glyph, so an
// icon-stat / icon-headline scene never renders a broken / empty icon slot.
function iconPath(name: string | undefined): React.ReactNode {
  const key = (name ?? "spark") as IconName;
  return ICON_PATHS[key] ?? ICON_PATHS["spark"];
}

// Renders an SVG icon in a rounded #EAF2FF tile with a 1px #BFD8FF border (~84px).
const IconTile: React.FC<{ name: string | undefined; size?: number }> = ({ name, size = 84 }) => (
  <div
    style={{
      width: size,
      height: size,
      borderRadius: 20,
      background: "#EAF2FF",
      border: "1px solid #BFD8FF",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      flexShrink: 0,
    }}
  >
    <svg
      width={44}
      height={44}
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      {iconPath(name)}
    </svg>
  </div>
);

// Returns true when a string looks like a person name (single or two capitalized
// words, no punctuation like .com / Inc / & which indicate companies).
function looksLikePerson(s: string): boolean {
  return /^[A-Z][a-z]+(?: [A-Z][a-z]+)?$/.test(s.trim());
}

// ---------------------------------------------------------------------------
// Shared sub-components
// ---------------------------------------------------------------------------

const KickerRow: React.FC<{
  data: SceneData;
  theme: Theme;
  style?: React.CSSProperties;
  sceneId?: string;
}> = ({ data, theme, style, sceneId }) => (
  <div
    data-scene-id={sceneId}
    data-field="kicker"
    style={{
      display: "flex",
      alignItems: "baseline",
      gap: 22,
      ...style,
    }}
  >
    <span
      style={{
        fontSize: 24,
        fontWeight: 700,
        letterSpacing: 6,
        textTransform: "uppercase" as const,
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
);

const TitleBlock: React.FC<{
  titleText: string;
  titleLines: string[];
  frame: number;
  fps: number;
  titleAt: number;
  titleOpacity: number;
  titleContainerY: number;
  underline: number;
  theme: Theme;
  fontSize?: number;
  centered?: boolean;
  sceneId?: string;
}> = ({
  titleText,
  titleLines,
  frame,
  fps,
  titleAt,
  titleOpacity,
  titleContainerY,
  underline,
  theme,
  fontSize = 96,
  centered = false,
  sceneId,
}) => {
  const TITLE_STAGGER = 16;
  const TITLE_DUR = 16;
  return (
    <div
      data-scene-id={sceneId}
      data-field="title"
      style={{
        position: "relative",
        display: centered ? "flex" : "inline-block",
        flexDirection: centered ? "column" : undefined,
        alignItems: centered ? "center" : undefined,
        textAlign: centered ? "center" : undefined,
        opacity: titleOpacity,
        transform: `translateY(${titleContainerY}px)`,
      }}
    >
      {titleLines.map((line, li) => {
        const sl = stagedLine(frame, li, titleAt, TITLE_STAGGER, 28, TITLE_DUR);
        const lineColor = sl.colorP > 0.5 ? theme.text : theme.textDim;
        return (
          <div
            key={li}
            style={{
              opacity: sl.opacity,
              transform: sl.transform,
              fontSize,
              fontWeight: 900,
              letterSpacing: -3,
              lineHeight: 1.04,
              color: lineColor,
              maxWidth: 1500,
            }}
          >
            {line}
          </div>
        );
      })}
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
  );
};

// ---------------------------------------------------------------------------
// TREATMENT A — icon-stat (centered)
// ---------------------------------------------------------------------------
const TreatmentIconStat: React.FC<{
  data: SceneData;
  theme: Theme;
  frame: number;
  fps: number;
  cues: Cue[];
  kickerAt: number;
  titleAt: number;
  titleOpacity: number;
  titleContainerY: number;
  underline: number;
  titleText: string;
  titleLines: string[];
  sceneId?: string;
}> = ({
  data, theme, frame, fps, cues, kickerAt, titleAt,
  titleOpacity, titleContainerY, underline, titleText, titleLines, sceneId,
}) => {
  const iconAt = titleAt - 8 < kickerAt ? kickerAt + 6 : titleAt - 8;
  const statAt = cueAt(cues, "subtitle-in", titleAt + 20);
  const iconOpacity = ease(frame, iconAt, iconAt + 14, 0, 1);
  const iconY = ease(frame, iconAt, iconAt + 14, 16, 0);
  const statOpacity = ease(frame, statAt, statAt + 16, 0, 1);
  const statY = ease(frame, statAt, statAt + 16, 14, 0);
  const statValue = data.stat?.value ?? "";
  const statLabel = data.stat?.label ?? "";

  return (
    <div
      style={{
        position: "absolute",
        left: 120,
        right: 120,
        top: 100,
        bottom: 80,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: 28,
        textAlign: "center",
      }}
    >
      <KickerRow
        data={data}
        theme={theme}
        style={{
          opacity: ease(frame, kickerAt, kickerAt + 14, 0, 1),
          transform: `translateY(${ease(frame, kickerAt, kickerAt + 14, 12, 0)}px)`,
          justifyContent: "center",
        }}
        sceneId={sceneId}
      />
      <div style={{ opacity: iconOpacity, transform: `translateY(${iconY}px)` }}>
        <IconTile name={data.icon} size={84} />
      </div>
      <TitleBlock
        titleText={titleText}
        titleLines={titleLines}
        frame={frame}
        fps={fps}
        titleAt={titleAt}
        titleOpacity={titleOpacity}
        titleContainerY={titleContainerY}
        underline={underline}
        theme={theme}
        fontSize={72}
        centered
        sceneId={sceneId}
      />
      {statValue ? (
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            gap: 6,
            opacity: statOpacity,
            transform: `translateY(${statY}px)`,
          }}
        >
          <span style={{ fontSize: 64, fontWeight: 900, color: theme.accent, letterSpacing: -2, lineHeight: 1, fontFamily: theme.fontDisplay }}>
            {statValue}
          </span>
          {statLabel ? (
            <span style={{ fontSize: 26, fontWeight: 400, color: theme.textMuted, letterSpacing: 0.2 }}>
              {statLabel}
            </span>
          ) : null}
        </div>
      ) : null}
    </div>
  );
};

// ---------------------------------------------------------------------------
// TREATMENT B — split-mosaic (text left + entity grid right)
// ---------------------------------------------------------------------------
const TreatmentSplitMosaic: React.FC<{
  data: SceneData;
  theme: Theme;
  frame: number;
  fps: number;
  cues: Cue[];
  kickerAt: number;
  titleAt: number;
  subAt: number;
  titleOpacity: number;
  titleContainerY: number;
  underline: number;
  subOpacity: number;
  subY: number;
  titleText: string;
  titleLines: string[];
  subText: string;
  sceneId?: string;
  resolveSrc?: (p: string) => string;
}> = ({
  data, theme, frame, fps, cues, kickerAt, titleAt, subAt,
  titleOpacity, titleContainerY, underline, subOpacity, subY,
  titleText, titleLines, subText, sceneId, resolveSrc,
}) => {
  // Caller guarantees a non-empty grid (degrade guard runs before mount).
  const entities = (data.featureEntities ?? []).slice(0, 6);
  const gridAt = cueAt(cues, "subtitle-in", subAt + 4);

  return (
    <div
      style={{
        position: "absolute",
        left: 140,
        right: 60,
        top: 120,
        bottom: 100,
        display: "grid",
        gridTemplateColumns: "1.05fr 0.95fr",
        gap: 48,
        alignItems: "center",
      }}
    >
      <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
        <KickerRow
          data={data}
          theme={theme}
          style={{
            opacity: ease(frame, kickerAt, kickerAt + 14, 0, 1),
            transform: `translateY(${ease(frame, kickerAt, kickerAt + 14, 12, 0)}px)`,
          }}
          sceneId={sceneId}
        />
        <TitleBlock
          titleText={titleText}
          titleLines={titleLines}
          frame={frame}
          fps={fps}
          titleAt={titleAt}
          titleOpacity={titleOpacity}
          titleContainerY={titleContainerY}
          underline={underline}
          theme={theme}
          fontSize={72}
          sceneId={sceneId}
        />
        {subText ? (
          <div
            data-scene-id={sceneId}
            data-field="subtitle"
            style={{ opacity: subOpacity, transform: `translateY(${subY}px)`, fontSize: 28, fontWeight: 400, color: theme.textMuted, maxWidth: 680 }}
          >
            {subText}
          </div>
        ) : null}
      </div>

      <div
        style={{
          background: theme.bg,
          borderRadius: 24,
          padding: 28,
          display: "grid",
          gridTemplateColumns: "repeat(3, 1fr)",
          gap: 14,
          alignContent: "center",
          minHeight: 280,
          border: `1px solid ${theme.border}`,
        }}
      >
        {entities.map((entity, i) => {
          const tileAt = gridAt + i * 10;
          const tileOpacity = ease(frame, tileAt, tileAt + 14, 0, 1);
          const tileY = ease(frame, tileAt, tileAt + 14, 12, 0);
          const logo = (data.entityLogos ?? [])[i];
          return (
            <div
              key={`${i}-${entity}`}
              style={{
                opacity: tileOpacity,
                transform: `translateY(${tileY}px)`,
                background: theme.bgCard,
                borderRadius: 12,
                border: `1px solid ${theme.border}`,
                boxShadow: "0 2px 10px rgba(20,40,80,0.06)",
                padding: "14px 10px",
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "center",
                gap: 8,
                minHeight: 84,
              }}
            >
              {logo ? (
                <Img
                  src={resolveLogo(logo, resolveSrc)}
                  style={{ width: 42, height: 42, objectFit: "contain", borderRadius: 8 }}
                />
              ) : (
                <div
                  style={{
                    width: 38,
                    height: 38,
                    borderRadius: 10,
                    background: theme.accent,
                    color: "#FFFFFF",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontSize: 17,
                    fontWeight: 800,
                    fontFamily: theme.fontDisplay,
                    flexShrink: 0,
                  }}
                >
                  {(entity || "?").trim().charAt(0).toUpperCase()}
                </div>
              )}
              <span
                style={{
                  fontSize: 13,
                  fontWeight: 600,
                  color: theme.text,
                  textAlign: "center",
                  lineHeight: 1.3,
                  letterSpacing: 0.2,
                  fontFamily: theme.fontDisplay,
                }}
              >
                {entity}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// TREATMENT C — split-stat (text left + stat panel right with rising bars)
// ---------------------------------------------------------------------------
const TreatmentSplitStat: React.FC<{
  data: SceneData;
  theme: Theme;
  frame: number;
  fps: number;
  cues: Cue[];
  kickerAt: number;
  titleAt: number;
  subAt: number;
  titleOpacity: number;
  titleContainerY: number;
  underline: number;
  subOpacity: number;
  subY: number;
  titleText: string;
  titleLines: string[];
  subText: string;
  sceneId?: string;
}> = ({
  data, theme, frame, fps, cues, kickerAt, titleAt, subAt,
  titleOpacity, titleContainerY, underline, subOpacity, subY,
  titleText, titleLines, subText, sceneId,
}) => {
  const statAt = cueAt(cues, "subtitle-in", subAt + 4);
  const statOpacity = ease(frame, statAt, statAt + 20, 0, 1);
  const statY = ease(frame, statAt, statAt + 20, 20, 0);
  // Caller guarantees a non-empty stat value (degrade guard runs before mount).
  const statValue = data.stat?.value ?? "";
  const statLabel = data.stat?.label ?? "";
  const BAR_HEIGHTS = [30, 48, 62, 80, 100];
  const BAR_BASE = 120;

  return (
    <div
      style={{
        position: "absolute",
        left: 140,
        right: 60,
        top: 120,
        bottom: 100,
        display: "grid",
        gridTemplateColumns: "1fr 1fr",
        gap: 48,
        alignItems: "center",
      }}
    >
      <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
        <KickerRow
          data={data}
          theme={theme}
          style={{
            opacity: ease(frame, kickerAt, kickerAt + 14, 0, 1),
            transform: `translateY(${ease(frame, kickerAt, kickerAt + 14, 12, 0)}px)`,
          }}
          sceneId={sceneId}
        />
        <TitleBlock
          titleText={titleText}
          titleLines={titleLines}
          frame={frame}
          fps={fps}
          titleAt={titleAt}
          titleOpacity={titleOpacity}
          titleContainerY={titleContainerY}
          underline={underline}
          theme={theme}
          fontSize={72}
          sceneId={sceneId}
        />
        {subText ? (
          <div
            data-scene-id={sceneId}
            data-field="subtitle"
            style={{ opacity: subOpacity, transform: `translateY(${subY}px)`, fontSize: 28, fontWeight: 400, color: theme.textMuted, maxWidth: 680 }}
          >
            {subText}
          </div>
        ) : null}
      </div>

      <div
        style={{
          background: "#EAF2FF",
          borderRadius: 24,
          padding: "40px 44px",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: 16,
          opacity: statOpacity,
          transform: `translateY(${statY}px)`,
          minHeight: 280,
        }}
      >
        {statValue ? (
          <span style={{ fontSize: 120, fontWeight: 900, color: theme.accent, letterSpacing: -4, lineHeight: 1, fontFamily: theme.fontDisplay, textAlign: "center" }}>
            {statValue}
          </span>
        ) : null}
        {statLabel ? (
          <span style={{ fontSize: 26, fontWeight: 600, color: "#1A3A5C", letterSpacing: 0.3, textAlign: "center" }}>
            {statLabel}
          </span>
        ) : null}
        <div style={{ display: "flex", alignItems: "flex-end", gap: 10, height: BAR_BASE, marginTop: 16 }}>
          {BAR_HEIGHTS.map((hPct, i) => {
            const barAt = statAt + 8 + i * 6;
            const barGrow = ease(frame, barAt, barAt + 20, 0, 1);
            const barH = (hPct / 100) * BAR_BASE;
            const barOpacity = 0.4 + (hPct / 100) * 0.6;
            return (
              <div
                key={i}
                style={{ width: 18, height: barH * barGrow, borderRadius: 5, background: theme.accent, opacity: barOpacity }}
              />
            );
          })}
        </div>
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// TREATMENT — metric-row (text left + a strip of 3-4 small real stats right)
// Sibling of split-stat. THEME-TOKEN ONLY (adapts per brand — light/orange on
// YC, etc.). The right panel is a horizontal flex row of up to 4 stat cards;
// each card staggers in. Caller guarantees >= 3 validated numeric metrics.
// ---------------------------------------------------------------------------
const TreatmentMetricRow: React.FC<{
  data: SceneData;
  theme: Theme;
  frame: number;
  fps: number;
  cues: Cue[];
  kickerAt: number;
  titleAt: number;
  subAt: number;
  titleOpacity: number;
  titleContainerY: number;
  underline: number;
  subOpacity: number;
  subY: number;
  titleText: string;
  titleLines: string[];
  subText: string;
  sceneId?: string;
}> = ({
  data, theme, frame, fps, cues, kickerAt, titleAt, subAt,
  titleOpacity, titleContainerY, underline, subOpacity, subY,
  titleText, titleLines, subText, sceneId,
}) => {
  const statAt = cueAt(cues, "subtitle-in", subAt + 4);
  // Caller guarantees a non-empty validated metric list (selection guard runs first).
  const metrics = (data.metrics ?? []).slice(0, 4);

  return (
    <div
      style={{
        position: "absolute",
        left: 140,
        right: 60,
        top: 120,
        bottom: 100,
        display: "grid",
        gridTemplateColumns: "0.92fr 1.08fr",
        gap: 48,
        alignItems: "center",
      }}
    >
      <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
        <KickerRow
          data={data}
          theme={theme}
          style={{
            opacity: ease(frame, kickerAt, kickerAt + 14, 0, 1),
            transform: `translateY(${ease(frame, kickerAt, kickerAt + 14, 12, 0)}px)`,
          }}
          sceneId={sceneId}
        />
        <TitleBlock
          titleText={titleText}
          titleLines={titleLines}
          frame={frame}
          fps={fps}
          titleAt={titleAt}
          titleOpacity={titleOpacity}
          titleContainerY={titleContainerY}
          underline={underline}
          theme={theme}
          fontSize={72}
          sceneId={sceneId}
        />
        {subText ? (
          <div
            data-scene-id={sceneId}
            data-field="subtitle"
            style={{ opacity: subOpacity, transform: `translateY(${subY}px)`, fontSize: 28, fontWeight: 400, color: theme.textMuted, maxWidth: 680 }}
          >
            {subText}
          </div>
        ) : null}
      </div>

      <div
        style={{
          display: "flex",
          flexDirection: "row",
          gap: 16,
          alignItems: "stretch",
          justifyContent: "flex-end",
        }}
      >
        {metrics.map((metric, i) => {
          const cardAt = statAt + i * 6;
          const cardOpacity = ease(frame, cardAt, cardAt + 14, 0, 1);
          const cardY = ease(frame, cardAt, cardAt + 14, 18, 0);
          return (
            <div
              key={`${i}-${metric.value}`}
              style={{
                opacity: cardOpacity,
                transform: `translateY(${cardY}px)`,
                background: theme.bgCard,
                borderRadius: 16,
                border: `1px solid ${theme.border}`,
                boxShadow: "0 6px 24px rgba(20,40,80,0.07)",
                padding: "26px 18px",
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "center",
                gap: 8,
                flex: 1,
                minWidth: 0,
                minHeight: 168,
              }}
            >
              <span
                style={{
                  fontSize: 54,
                  fontWeight: 900,
                  color: theme.accent,
                  letterSpacing: -2.5,
                  lineHeight: 1,
                  fontFamily: theme.fontDisplay,
                  textAlign: "center",
                }}
              >
                {metric.value}
              </span>
              {metric.label ? (
                <span
                  style={{
                    fontSize: 16,
                    fontWeight: 600,
                    color: theme.textMuted,
                    letterSpacing: 0.4,
                    textTransform: "uppercase",
                    textAlign: "center",
                    lineHeight: 1.3,
                    fontFamily: theme.fontDisplay,
                  }}
                >
                  {metric.label}
                </span>
              ) : null}
            </div>
          );
        })}
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// TREATMENT — comparison-columns (a two-column contrast). LEFT = the muted "old
// way" (de-emphasized: textMuted rows with a dash marker). RIGHT = the accented
// "with Filmo" way (emphasized: full-text rows with an accent checkmark). A
// centered title block sits above; a subtle theme.border divider separates the
// columns. THEME-TOKEN ONLY so it reads clean on any brand. Caller guarantees a
// `compare` with >=2 items per side (selection guard runs first). No remote
// assets — identical JSX in studio + web.
// ---------------------------------------------------------------------------
const TreatmentComparisonColumns: React.FC<{
  data: SceneData;
  theme: Theme;
  frame: number;
  fps: number;
  cues: Cue[];
  kickerAt: number;
  titleAt: number;
  subAt: number;
  titleOpacity: number;
  titleContainerY: number;
  underline: number;
  titleText: string;
  titleLines: string[];
  sceneId?: string;
}> = ({
  data, theme, frame, fps, cues, kickerAt, titleAt, subAt,
  titleOpacity, titleContainerY, underline, titleText, titleLines, sceneId,
}) => {
  const compare = data.compare ?? { leftTitle: "", leftItems: [], rightTitle: "", rightItems: [] };
  const leftItems = (compare.leftItems ?? []).map((s) => (s ?? "").trim()).filter(Boolean).slice(0, 5);
  const rightItems = (compare.rightItems ?? []).map((s) => (s ?? "").trim()).filter(Boolean).slice(0, 5);
  const rowsAt = cueAt(cues, "subtitle-in", subAt + 4);

  const ColumnHeader: React.FC<{ label: string; opacity: number; accent: boolean }> = ({
    label, opacity, accent,
  }) => (
    <div
      style={{
        opacity,
        fontSize: 22,
        fontWeight: 800,
        letterSpacing: 3,
        textTransform: "uppercase",
        color: accent ? theme.accent : theme.textMuted,
        fontFamily: theme.fontMono,
        paddingBottom: 4,
      }}
    >
      {label}
    </div>
  );

  const Row: React.FC<{ text: string; i: number; accent: boolean }> = ({ text, i, accent }) => {
    const rowAt = rowsAt + i * 8;
    const rowOpacity = ease(frame, rowAt, rowAt + 16, 0, 1);
    const rowX = ease(frame, rowAt, rowAt + 16, accent ? 18 : -18, 0);
    return (
      <div
        style={{
          opacity: rowOpacity,
          transform: `translateX(${rowX}px)`,
          display: "flex",
          alignItems: "center",
          gap: 18,
        }}
      >
        <div
          style={{
            flex: "0 0 36px",
            width: 36,
            height: 36,
            borderRadius: accent ? 10 : 18,
            background: accent ? `${theme.accent}${alphaHex(0.12)}` : "transparent",
            border: `1px solid ${accent ? `${theme.accent}${alphaHex(0.45)}` : theme.border}`,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          {accent ? (
            <svg width={20} height={20} viewBox="0 0 24 24" fill="none">
              <path d="M5 12.5l4 4 10-10" stroke={theme.accent} strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          ) : (
            <svg width={20} height={20} viewBox="0 0 24 24" fill="none">
              <path d="M6 12h12" stroke={theme.textMuted} strokeWidth="2.4" strokeLinecap="round" />
            </svg>
          )}
        </div>
        <span
          style={{
            fontSize: 30,
            fontWeight: accent ? 600 : 400,
            color: accent ? theme.text : theme.textMuted,
            letterSpacing: -0.3,
            lineHeight: 1.25,
            fontFamily: theme.fontDisplay,
          }}
        >
          {text}
        </span>
      </div>
    );
  };

  return (
    <div
      style={{
        position: "absolute",
        left: 140,
        right: 140,
        top: 110,
        bottom: 96,
        display: "flex",
        flexDirection: "column",
        justifyContent: "center",
        gap: 44,
      }}
    >
      <div style={{ display: "flex", flexDirection: "column", gap: 16, alignItems: "center", textAlign: "center" }}>
        <KickerRow
          data={data}
          theme={theme}
          style={{
            justifyContent: "center",
            opacity: ease(frame, kickerAt, kickerAt + 14, 0, 1),
            transform: `translateY(${ease(frame, kickerAt, kickerAt + 14, 12, 0)}px)`,
          }}
          sceneId={sceneId}
        />
        <TitleBlock
          titleText={titleText}
          titleLines={titleLines}
          frame={frame}
          fps={fps}
          titleAt={titleAt}
          titleOpacity={titleOpacity}
          titleContainerY={titleContainerY}
          underline={underline}
          theme={theme}
          fontSize={56}
          sceneId={sceneId}
        />
      </div>

      <div
        data-scene-id={sceneId}
        data-field="compare"
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1px 1fr",
          gap: 56,
          alignItems: "start",
        }}
      >
        <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
          <ColumnHeader
            label={compare.leftTitle || "Before"}
            opacity={ease(frame, rowsAt - 6, rowsAt + 8, 0, 1)}
            accent={false}
          />
          {leftItems.map((text, i) => (
            <Row key={`l-${i}-${text}`} text={text} i={i} accent={false} />
          ))}
        </div>

        <div
          style={{
            width: 1,
            alignSelf: "stretch",
            background: theme.border,
            opacity: ease(frame, rowsAt, rowsAt + 20, 0, 1),
          }}
        />

        <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
          <ColumnHeader
            label={compare.rightTitle || "With Filmo"}
            opacity={ease(frame, rowsAt - 6, rowsAt + 8, 0, 1)}
            accent
          />
          {rightItems.map((text, i) => (
            <Row key={`r-${i}-${text}`} text={text} i={i} accent />
          ))}
        </div>
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// TREATMENT — device-frame (text left + a REAL product screenshot in a clean
// browser frame, right). Sibling of split-stat. THEME-TOKEN ONLY so the frame
// chrome reads clean on any brand (white/orange YC, etc.). The frame is a
// rounded card: a top bar with 3 small dots, then the screenshot filling the
// body. Caller guarantees a non-empty real `imageSrc` (selection guard first).
// WEB EDITOR: resolves the screenshot via resolveLogo(imageSrc, resolveSrc) so the
// preview pulls the hosted capture (matches split-mosaic logo resolution).
// ---------------------------------------------------------------------------
const TreatmentDeviceFrame: React.FC<{
  data: SceneData;
  theme: Theme;
  frame: number;
  fps: number;
  cues: Cue[];
  kickerAt: number;
  titleAt: number;
  subAt: number;
  titleOpacity: number;
  titleContainerY: number;
  underline: number;
  subOpacity: number;
  subY: number;
  titleText: string;
  titleLines: string[];
  subText: string;
  sceneId?: string;
  resolveSrc?: (p: string) => string;
}> = ({
  data, theme, frame, fps, cues, kickerAt, titleAt, subAt,
  titleOpacity, titleContainerY, underline, subOpacity, subY,
  titleText, titleLines, subText, sceneId, resolveSrc,
}) => {
  const shotAt = cueAt(cues, "subtitle-in", subAt + 4);
  const shotOpacity = ease(frame, shotAt, shotAt + 20, 0, 1);
  const shotY = ease(frame, shotAt, shotAt + 20, 24, 0);
  const shotScale = ease(frame, shotAt, shotAt + 24, 0.96, 1);
  // Caller guarantees a non-empty captured screenshot path (selection guard runs first).
  const imageSrc = (data.imageSrc ?? "").trim();
  const src = resolveLogo(imageSrc, resolveSrc);

  return (
    <div
      style={{
        position: "absolute",
        left: 140,
        right: 60,
        top: 120,
        bottom: 100,
        display: "grid",
        gridTemplateColumns: "0.82fr 1.18fr",
        gap: 48,
        alignItems: "center",
      }}
    >
      <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
        <KickerRow
          data={data}
          theme={theme}
          style={{
            opacity: ease(frame, kickerAt, kickerAt + 14, 0, 1),
            transform: `translateY(${ease(frame, kickerAt, kickerAt + 14, 12, 0)}px)`,
          }}
          sceneId={sceneId}
        />
        <TitleBlock
          titleText={titleText}
          titleLines={titleLines}
          frame={frame}
          fps={fps}
          titleAt={titleAt}
          titleOpacity={titleOpacity}
          titleContainerY={titleContainerY}
          underline={underline}
          theme={theme}
          fontSize={72}
          sceneId={sceneId}
        />
        {subText ? (
          <div
            data-scene-id={sceneId}
            data-field="subtitle"
            style={{ opacity: subOpacity, transform: `translateY(${subY}px)`, fontSize: 28, fontWeight: 400, color: theme.textMuted, maxWidth: 680 }}
          >
            {subText}
          </div>
        ) : null}
      </div>

      <div
        style={{
          opacity: shotOpacity,
          transform: `translateY(${shotY}px) scale(${shotScale})`,
          transformOrigin: "center",
          background: theme.bgCard,
          borderRadius: 18,
          border: `1px solid ${theme.border}`,
          boxShadow: "0 24px 64px rgba(20,40,80,0.16), 0 4px 14px rgba(20,40,80,0.08)",
          overflow: "hidden",
          display: "flex",
          flexDirection: "column",
          maxHeight: "100%",
        }}
      >
        {/* Browser chrome bar: 3 dots, left-aligned. */}
        <div
          style={{
            height: 40,
            display: "flex",
            alignItems: "center",
            gap: 9,
            padding: "0 18px",
            background: theme.bgCard,
            borderBottom: `1px solid ${theme.border}`,
            flexShrink: 0,
          }}
        >
          {[0, 1, 2].map((i) => (
            <div
              key={i}
              style={{
                width: 12,
                height: 12,
                borderRadius: "50%",
                background: theme.border,
                border: `1px solid ${theme.textMuted}`,
                opacity: 0.55,
              }}
            />
          ))}
          <div
            style={{
              flex: 1,
              marginLeft: 12,
              height: 22,
              borderRadius: 7,
              background: theme.bg,
              border: `1px solid ${theme.border}`,
            }}
          />
        </div>
        {/* Screenshot body. */}
        <div style={{ background: theme.bg, display: "flex", minHeight: 0 }}>
          <Img
            src={src}
            style={{ width: "100%", height: "auto", display: "block", objectFit: "cover", objectPosition: "top" }}
          />
        </div>
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// TREATMENT D — icon-headline (centered, FULL-WIDTH) — THE FALLBACK
//
// This is also the degrade target for the two-column treatments. It is a
// symmetric, centered, full-width composition: the container is inset by the
// SAME amount left/right (120/120) and the content is centered both axes, so it
// fills the stage with no right-side white space.
// ---------------------------------------------------------------------------
const TreatmentIconHeadline: React.FC<{
  data: SceneData;
  theme: Theme;
  frame: number;
  fps: number;
  cues: Cue[];
  kickerAt: number;
  titleAt: number;
  subAt: number;
  titleOpacity: number;
  titleContainerY: number;
  underline: number;
  subOpacity: number;
  subY: number;
  titleText: string;
  titleLines: string[];
  subText: string;
  sceneId?: string;
}> = ({
  data, theme, frame, fps, kickerAt, titleAt,
  titleOpacity, titleContainerY, underline, subOpacity, subY,
  titleText, titleLines, subText, sceneId,
}) => {
  const iconAt = titleAt - 8 < kickerAt ? kickerAt + 6 : titleAt - 8;
  const iconOpacity = ease(frame, iconAt, iconAt + 14, 0, 1);
  const iconY = ease(frame, iconAt, iconAt + 14, 16, 0);

  return (
    <div
      style={{
        position: "absolute",
        left: 120,
        right: 120,
        top: 100,
        bottom: 80,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: 28,
        textAlign: "center",
      }}
    >
      <KickerRow
        data={data}
        theme={theme}
        style={{
          opacity: ease(frame, kickerAt, kickerAt + 14, 0, 1),
          transform: `translateY(${ease(frame, kickerAt, kickerAt + 14, 12, 0)}px)`,
          justifyContent: "center",
        }}
        sceneId={sceneId}
      />
      <div style={{ opacity: iconOpacity, transform: `translateY(${iconY}px)` }}>
        <IconTile name={data.icon} size={84} />
      </div>
      <TitleBlock
        titleText={titleText}
        titleLines={titleLines}
        frame={frame}
        fps={fps}
        titleAt={titleAt}
        titleOpacity={titleOpacity}
        titleContainerY={titleContainerY}
        underline={underline}
        theme={theme}
        fontSize={72}
        centered
        sceneId={sceneId}
      />
      {/* Optional centered supporting line — keeps the centered block from
          reading thin when the scene happens to carry a subtitle. */}
      {subText ? (
        <div
          data-scene-id={sceneId}
          data-field="subtitle"
          style={{
            opacity: subOpacity,
            transform: `translateY(${subY}px)`,
            fontSize: 30,
            fontWeight: 400,
            color: theme.textMuted,
            maxWidth: 1100,
            textAlign: "center",
          }}
        >
          {subText}
        </div>
      ) : null}
    </div>
  );
};

// ---------------------------------------------------------------------------
// TREATMENT E — big-number (ONE dominant stat, full-bleed)
//
// For scenes whose PUNCH is the number (e.g. "$800B+"). Renders the kicker, then
// a HUGE stat.value as the hero element (clamped 120-200px), the stat.label
// beneath, and the `title` as a supporting line under that. Centered + symmetric
// so it FILLS WIDTH (no right-side white space). Requires a real stat — the
// degrade guard drops to "icon-headline" when no stat.
// ---------------------------------------------------------------------------
const TreatmentBigNumber: React.FC<{
  data: SceneData;
  theme: Theme;
  frame: number;
  fps: number;
  cues: Cue[];
  kickerAt: number;
  titleAt: number;
  underline: number;
  titleText: string;
  sceneId?: string;
}> = ({ data, theme, frame, fps, cues, kickerAt, titleAt, underline, titleText, sceneId }) => {
  const statAt = titleAt - 6 < kickerAt ? kickerAt + 8 : titleAt - 6;
  const labelAt = cueAt(cues, "subtitle-in", statAt + 14);
  const titleLineAt = labelAt + 10;
  // Hero number springs up with the kinetic-light damping; supporting lines ease.
  const statSpring = spring({
    frame: frame - statAt,
    fps,
    config: { damping: 16, stiffness: 150, mass: 0.8 },
  });
  const statOpacity = ease(frame, statAt, statAt + 16, 0, 1);
  const statY = interpolate(statSpring, [0, 1], [40, 0]);
  const statScale = interpolate(statSpring, [0, 1], [0.86, 1]);
  const labelOpacity = ease(frame, labelAt, labelAt + 16, 0, 1);
  const labelY = ease(frame, labelAt, labelAt + 16, 14, 0);
  const titleOpacity = ease(frame, titleLineAt, titleLineAt + 16, 0, 1);
  const titleY = ease(frame, titleLineAt, titleLineAt + 16, 16, 0);
  const statValue = data.stat?.value ?? "";
  const statLabel = data.stat?.label ?? "";

  return (
    <div
      style={{
        position: "absolute",
        left: 120,
        right: 120,
        top: 100,
        bottom: 80,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: 18,
        textAlign: "center",
      }}
    >
      <KickerRow
        data={data}
        theme={theme}
        style={{
          opacity: ease(frame, kickerAt, kickerAt + 14, 0, 1),
          transform: `translateY(${ease(frame, kickerAt, kickerAt + 14, 12, 0)}px)`,
          justifyContent: "center",
        }}
        sceneId={sceneId}
      />
      <div
        data-scene-id={sceneId}
        data-field="stat"
        style={{
          opacity: statOpacity,
          transform: `translateY(${statY}px) scale(${statScale})`,
          fontSize: "clamp(120px, 18vw, 200px)",
          fontWeight: 900,
          letterSpacing: -8,
          lineHeight: 0.95,
          color: theme.accent,
          fontFamily: theme.fontDisplay,
          textShadow: `0 0 60px ${theme.accent}${alphaHex(0.28)}`,
        }}
      >
        {statValue}
      </div>
      {statLabel ? (
        <div
          style={{
            opacity: labelOpacity,
            transform: `translateY(${labelY}px)`,
            fontSize: 32,
            fontWeight: 600,
            color: theme.textMuted,
            letterSpacing: 0.4,
            maxWidth: 1100,
          }}
        >
          {statLabel}
        </div>
      ) : null}
      <div
        style={{
          marginTop: 10,
          height: 6,
          width: `${Math.round(underline * 300)}px`,
          borderRadius: 6,
          background: theme.accent,
          boxShadow: `0 0 24px ${theme.accent}${alphaHex(0.45 * underline)}`,
        }}
      />
      {titleText ? (
        <div
          data-scene-id={sceneId}
          data-field="title"
          style={{
            opacity: titleOpacity,
            transform: `translateY(${titleY}px)`,
            fontSize: 40,
            fontWeight: 700,
            color: theme.text,
            letterSpacing: -1,
            lineHeight: 1.15,
            maxWidth: 1200,
          }}
        >
          {titleText}
        </div>
      ) : null}
    </div>
  );
};

// ---------------------------------------------------------------------------
// TREATMENT F — logo-wall (centered header + a fuller branded-chip grid)
//
// For "backed by / integrates with / trusted by" scenes. Renders the `title` as
// a centered header above a prominent grid of featureEntities (4-8) drawn as
// branded chips/tiles (bigger + more of them than split-mosaic's right column).
// Requires entities — the degrade guard drops to "icon-headline" when none.
// ---------------------------------------------------------------------------
const TreatmentLogoWall: React.FC<{
  data: SceneData;
  theme: Theme;
  frame: number;
  fps: number;
  cues: Cue[];
  kickerAt: number;
  titleAt: number;
  subAt: number;
  titleOpacity: number;
  titleContainerY: number;
  underline: number;
  titleText: string;
  titleLines: string[];
  sceneId?: string;
}> = ({
  data, theme, frame, fps, cues, kickerAt, titleAt, subAt,
  titleOpacity, titleContainerY, underline, titleText, titleLines, sceneId,
}) => {
  // Caller guarantees a non-empty grid (degrade guard runs before mount).
  const entities = (data.featureEntities ?? []).slice(0, 8);
  const wallAt = cueAt(cues, "subtitle-in", subAt + 4);
  // 4 -> 2 cols, 5-6 -> 3 cols, 7-8 -> 4 cols (keeps tiles big + rows balanced).
  const cols = entities.length <= 4 ? 2 : entities.length <= 6 ? 3 : 4;

  return (
    <div
      style={{
        position: "absolute",
        left: 120,
        right: 120,
        top: 100,
        bottom: 80,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: 40,
        textAlign: "center",
      }}
    >
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 18 }}>
        <KickerRow
          data={data}
          theme={theme}
          style={{
            opacity: ease(frame, kickerAt, kickerAt + 14, 0, 1),
            transform: `translateY(${ease(frame, kickerAt, kickerAt + 14, 12, 0)}px)`,
            justifyContent: "center",
          }}
          sceneId={sceneId}
        />
        <TitleBlock
          titleText={titleText}
          titleLines={titleLines}
          frame={frame}
          fps={fps}
          titleAt={titleAt}
          titleOpacity={titleOpacity}
          titleContainerY={titleContainerY}
          underline={underline}
          theme={theme}
          fontSize={64}
          centered
          sceneId={sceneId}
        />
      </div>

      <div
        data-scene-id={sceneId}
        data-field="featureEntities"
        style={{
          display: "grid",
          gridTemplateColumns: `repeat(${cols}, 1fr)`,
          gap: 22,
          width: "100%",
          maxWidth: 1480,
        }}
      >
        {entities.map((entity, i) => {
          const tileAt = wallAt + i * 8;
          const tileOpacity = ease(frame, tileAt, tileAt + 14, 0, 1);
          const tileY = ease(frame, tileAt, tileAt + 14, 16, 0);
          const isPerson = looksLikePerson(entity);
          return (
            <div
              key={`${i}-${entity}`}
              style={{
                opacity: tileOpacity,
                transform: `translateY(${tileY}px)`,
                background: "#FFFFFF",
                borderRadius: 18,
                border: "1px solid #D6E4FF",
                boxShadow: `0 8px 28px ${theme.accent}${alphaHex(0.08)}`,
                padding: "26px 22px",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: 14,
                minHeight: 96,
              }}
            >
              <div
                style={{
                  width: 40,
                  height: 40,
                  borderRadius: isPerson ? "50%" : 11,
                  background: "#EAF2FF",
                  border: "1px solid #BFD8FF",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  flexShrink: 0,
                }}
              >
                {isPerson ? (
                  <svg width={22} height={22} viewBox="0 0 24 24" fill="none">
                    <circle cx="12" cy="8" r="4" stroke={theme.accent} strokeWidth="1.6" fill="none" />
                    <path d="M4 20c0-4.4 3.6-8 8-8s8 3.6 8 8" stroke={theme.accent} strokeWidth="1.6" fill="none" strokeLinecap="round" />
                  </svg>
                ) : (
                  <span
                    style={{
                      fontSize: 20,
                      fontWeight: 800,
                      color: theme.accent,
                      fontFamily: theme.fontDisplay,
                      lineHeight: 1,
                    }}
                  >
                    {(entity.trim()[0] || "•").toUpperCase()}
                  </span>
                )}
              </div>
              <span
                style={{
                  fontSize: 24,
                  fontWeight: 700,
                  color: theme.navy,
                  letterSpacing: -0.3,
                  lineHeight: 1.2,
                  fontFamily: theme.fontDisplay,
                  textAlign: "left",
                }}
              >
                {entity}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// TREATMENT G — feature-list (title + a clean vertical "what you get" list)
//
// Rows built from featureEntities (each a check/dot + label) OR, when no
// entities, the `subtitle` split into 2-3 bullet rows. A crisp left-aligned
// card. Always has SOMETHING to list (entities or subtitle clauses) — when the
// caller has neither, the row source falls back to a single title row so it is
// never empty (the degrade guard upstream prefers the centered fallback anyway).
// ---------------------------------------------------------------------------
const TreatmentFeatureList: React.FC<{
  data: SceneData;
  theme: Theme;
  frame: number;
  fps: number;
  cues: Cue[];
  kickerAt: number;
  titleAt: number;
  subAt: number;
  titleOpacity: number;
  titleContainerY: number;
  underline: number;
  titleText: string;
  titleLines: string[];
  subText: string;
  sceneId?: string;
}> = ({
  data, theme, frame, fps, cues, kickerAt, titleAt, subAt,
  titleOpacity, titleContainerY, underline, titleText, titleLines, subText, sceneId,
}) => {
  const ents = (data.featureEntities ?? []).map((e) => (e ?? "").trim()).filter(Boolean);
  // Row source: real entities win; else split the subtitle into 2-3 clauses; else
  // fall back to the single title so the list is never empty.
  let rows: string[];
  if (ents.length > 0) {
    rows = ents.slice(0, 5);
  } else {
    const clauses = subText
      .split(/[.;—–\n]|,\s+(?=[A-Z])/)
      .map((c) => c.trim())
      .filter((c) => c.split(/\s+/).length >= 2);
    rows = clauses.length >= 2 ? clauses.slice(0, 3) : (subText ? [subText] : [titleText]);
  }
  const listAt = cueAt(cues, "subtitle-in", subAt + 4);

  return (
    <div
      style={{
        position: "absolute",
        left: 140,
        right: 140,
        top: 120,
        bottom: 100,
        display: "flex",
        flexDirection: "column",
        justifyContent: "center",
        gap: 32,
      }}
    >
      <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
        <KickerRow
          data={data}
          theme={theme}
          style={{
            opacity: ease(frame, kickerAt, kickerAt + 14, 0, 1),
            transform: `translateY(${ease(frame, kickerAt, kickerAt + 14, 12, 0)}px)`,
          }}
          sceneId={sceneId}
        />
        <TitleBlock
          titleText={titleText}
          titleLines={titleLines}
          frame={frame}
          fps={fps}
          titleAt={titleAt}
          titleOpacity={titleOpacity}
          titleContainerY={titleContainerY}
          underline={underline}
          theme={theme}
          fontSize={68}
          sceneId={sceneId}
        />
      </div>

      <div
        data-scene-id={sceneId}
        data-field="featureEntities"
        style={{ display: "flex", flexDirection: "column", gap: 18, maxWidth: 1280 }}
      >
        {rows.map((row, i) => {
          const rowAt = listAt + i * 10;
          const rowOpacity = ease(frame, rowAt, rowAt + 16, 0, 1);
          const rowX = ease(frame, rowAt, rowAt + 16, -20, 0);
          return (
            <div
              key={`${i}-${row}`}
              style={{
                opacity: rowOpacity,
                transform: `translateX(${rowX}px)`,
                display: "flex",
                alignItems: "center",
                gap: 22,
                background: "#FFFFFF",
                borderRadius: 16,
                border: "1px solid #E2EBF8",
                boxShadow: `0 6px 22px ${theme.accent}${alphaHex(0.06)}`,
                padding: "20px 26px",
              }}
            >
              <div
                style={{
                  flex: "0 0 44px",
                  width: 44,
                  height: 44,
                  borderRadius: 12,
                  background: "#EAF2FF",
                  border: "1px solid #BFD8FF",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                <svg width={24} height={24} viewBox="0 0 24 24" fill="none">
                  <path d="M5 12.5l4 4 10-10" stroke={theme.accent} strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </div>
              <span
                style={{
                  fontSize: 32,
                  fontWeight: 600,
                  color: theme.text,
                  letterSpacing: -0.4,
                  lineHeight: 1.2,
                  fontFamily: theme.fontDisplay,
                }}
              >
                {row}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Main ExplainerCard export
// ---------------------------------------------------------------------------
export const ExplainerCard: React.FC<{
  data: SceneData;
  cues: Cue[];
  theme: Theme;
  durationInFrames: number;
  // 1-based act index among content-beat scenes (-1 = no badge)
  actIndex?: number;
  // OPTIONAL: scene id, threaded from Timeline for click-to-select addressing.
  sceneId?: string;
  // OPTIONAL: the Timeline assetBaseUrl seam, so the brand logo resolves from the
  // hosted bucket in the editor preview (absent in the studio render → staticFile).
  resolveSrc?: (path: string) => string;
}> = ({ data, cues, theme, durationInFrames, actIndex = -1, sceneId, resolveSrc }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const kickerAt = cueAt(cues, "kicker-in", 4);
  const titleAt = cueAt(cues, "title-in", 14);
  const subAt = cueAt(cues, "subtitle-in", titleAt + 18);
  const bullets = (data.bullets ?? []).slice(0, 4);

  // HARD never-empty guard (blank-scenes fix): if the upstream copy is empty,
  // render an on-brand fallback (wordmark + tagline) so the scene ALWAYS shows
  // legible content — never just the background + a faint glow. The fallback
  // title is the brand wordmark; the subtitle is the threaded subtitle/tagline.
  const titleText = (data.title ?? "").trim() || theme.wordmark || "";
  const subText = (data.subtitle ?? "").trim();
  // Bullets stagger after the subtitle; prefer explicit point-N cues when present.
  const bulletAt = (i: number) =>
    cueAt(cues, `point-${i + 1}`, subAt + 16 + i * 16);

  // Left navy rail slides up as the scene opens (Orinovate sidebar motif).
  const railGrow = ease(frame, 0, 18, 0, 1);

  // Title staged line-by-line reveal (D2 pacing — R4): each line fades+rises in
  // sequence; pending lines render at textDim, active/arrived lines at full text.
  const TITLE_STAGGER = 16;
  const TITLE_DUR = 16;
  const titleLines = splitToLines(titleText, 24);
  // Spring on the outer wrapper (kinetic-light damping 16) fires on titleAt.
  const titleSpring = spring({
    frame: frame - titleAt,
    fps,
    config: { damping: 16, stiffness: 150, mass: 0.8 },
  });
  const titleContainerY = interpolate(titleSpring, [0, 1], [20, 0]);
  const titleOpacity = ease(frame, titleAt, titleAt + 16, 0, 1);
  // Underline sweeps in after the last line settles.
  const lastLineStart = titleAt + (Math.max(1, titleLines.length) - 1) * TITLE_STAGGER;
  const underline = ease(frame, lastLineStart + 12, lastLineStart + 34, 0, 1);

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

  // Act badge label: derives from kicker if present (≤2 words, all-caps).
  const badgeLabel = actIndex > 0 ? actLabel(data.kicker) : "";
  const badgeText = actIndex > 0 ? `${actNum(actIndex)}${badgeLabel ? ` — ${badgeLabel}` : ""}` : "";

  // -------------------------------------------------------------------------
  // TREATMENT RESOLUTION + DEGRADE-TO-CENTER GUARD.
  // ABSENT / unknown treatment → render the ORIGINAL card (backward compat).
  // For the data-driven treatments, if the required right-column data is
  // missing we DROP to "icon-headline" (centered, full-width) so we never
  // render a blank / ghosted right half (the white-space bug).
  // -------------------------------------------------------------------------
  const hasEntities = (data.featureEntities ?? []).filter((e) => (e ?? "").trim()).length > 0;
  const hasStat = !!(data.stat?.value ?? "").trim();
  const hasShot = !!(data.imageSrc ?? "").trim();
  // comparison-columns needs >=2 real items on BOTH sides (never a lopsided contrast).
  const hasCompare =
    (data.compare?.leftItems ?? []).filter((s) => (s ?? "").trim()).length >= 2 &&
    (data.compare?.rightItems ?? []).filter((s) => (s ?? "").trim()).length >= 2;

  let treatment = data.treatment;
  if ((treatment === "split-mosaic" || treatment === "logo-wall") && !hasEntities) treatment = "icon-headline";
  else if ((treatment === "split-stat" || treatment === "icon-stat" || treatment === "big-number") && !hasStat) treatment = "icon-headline";
  // feature-list needs SOMETHING to list — entities or a subtitle to split into
  // rows. With neither, drop to the centered fallback (never an empty list card).
  else if (treatment === "feature-list" && !hasEntities && !subText.trim()) treatment = "icon-headline";
  // device-frame needs a real captured screenshot — with none, drop to the
  // centered fallback (never an empty browser frame).
  else if (treatment === "device-frame" && !hasShot) treatment = "icon-headline";
  // comparison-columns needs a real two-sided contrast — without it, drop to the
  // centered fallback (never a half-empty comparison).
  else if (treatment === "comparison-columns" && !hasCompare) treatment = "icon-headline";

  return (
    <AbsoluteFill
      style={{
        backgroundColor: theme.bg,
        fontFamily: theme.fontDisplay,
        opacity: exitFade,
        transform: `translateY(${exitShift}px)`,
      }}
    >
      {/* Numbered act badge — top-left eyebrow: "NN — LABEL" */}
      {actIndex > 0 && (
        <div
          style={{
            position: "absolute",
            left: 140,
            top: 52,
            opacity: ease(frame, kickerAt, kickerAt + 14, 0, 1),
            fontSize: 22,
            fontWeight: 700,
            letterSpacing: "0.18em",
            textTransform: "uppercase",
            color: theme.accent,
            fontFamily: theme.fontMono,
          }}
        >
          {badgeText}
        </div>
      )}

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

      {/* ------------------------------------------------------------------ */}
      {/* TREATMENT SWITCH                                                    */}
      {/* ------------------------------------------------------------------ */}
      {treatment === "icon-stat" ? (
        <TreatmentIconStat
          data={data}
          theme={theme}
          frame={frame}
          fps={fps}
          cues={cues}
          kickerAt={kickerAt}
          titleAt={titleAt}
          titleOpacity={titleOpacity}
          titleContainerY={titleContainerY}
          underline={underline}
          titleText={titleText}
          titleLines={titleLines}
          sceneId={sceneId}
        />
      ) : treatment === "split-mosaic" ? (
        <TreatmentSplitMosaic
          data={data}
          theme={theme}
          frame={frame}
          fps={fps}
          cues={cues}
          kickerAt={kickerAt}
          titleAt={titleAt}
          subAt={subAt}
          titleOpacity={titleOpacity}
          titleContainerY={titleContainerY}
          underline={underline}
          subOpacity={subOpacity}
          subY={subY}
          titleText={titleText}
          titleLines={titleLines}
          subText={subText}
          sceneId={sceneId}
          resolveSrc={resolveSrc}
        />
      ) : treatment === "split-stat" ? (
        <TreatmentSplitStat
          data={data}
          theme={theme}
          frame={frame}
          fps={fps}
          cues={cues}
          kickerAt={kickerAt}
          titleAt={titleAt}
          subAt={subAt}
          titleOpacity={titleOpacity}
          titleContainerY={titleContainerY}
          underline={underline}
          subOpacity={subOpacity}
          subY={subY}
          titleText={titleText}
          titleLines={titleLines}
          subText={subText}
          sceneId={sceneId}
        />
      ) : treatment === "metric-row" ? (
        <TreatmentMetricRow
          data={data}
          theme={theme}
          frame={frame}
          fps={fps}
          cues={cues}
          kickerAt={kickerAt}
          titleAt={titleAt}
          subAt={subAt}
          titleOpacity={titleOpacity}
          titleContainerY={titleContainerY}
          underline={underline}
          subOpacity={subOpacity}
          subY={subY}
          titleText={titleText}
          titleLines={titleLines}
          subText={subText}
          sceneId={sceneId}
        />
      ) : treatment === "device-frame" ? (
        <TreatmentDeviceFrame
          data={data}
          theme={theme}
          frame={frame}
          fps={fps}
          cues={cues}
          kickerAt={kickerAt}
          titleAt={titleAt}
          subAt={subAt}
          titleOpacity={titleOpacity}
          titleContainerY={titleContainerY}
          underline={underline}
          subOpacity={subOpacity}
          subY={subY}
          titleText={titleText}
          titleLines={titleLines}
          subText={subText}
          sceneId={sceneId}
          resolveSrc={resolveSrc}
        />
      ) : treatment === "comparison-columns" ? (
        <TreatmentComparisonColumns
          data={data}
          theme={theme}
          frame={frame}
          fps={fps}
          cues={cues}
          kickerAt={kickerAt}
          titleAt={titleAt}
          subAt={subAt}
          titleOpacity={titleOpacity}
          titleContainerY={titleContainerY}
          underline={underline}
          titleText={titleText}
          titleLines={titleLines}
          sceneId={sceneId}
        />
      ) : treatment === "icon-headline" ? (
        <TreatmentIconHeadline
          data={data}
          theme={theme}
          frame={frame}
          fps={fps}
          cues={cues}
          kickerAt={kickerAt}
          titleAt={titleAt}
          subAt={subAt}
          titleOpacity={titleOpacity}
          titleContainerY={titleContainerY}
          underline={underline}
          subOpacity={subOpacity}
          subY={subY}
          titleText={titleText}
          titleLines={titleLines}
          subText={subText}
          sceneId={sceneId}
        />
      ) : treatment === "big-number" ? (
        <TreatmentBigNumber
          data={data}
          theme={theme}
          frame={frame}
          fps={fps}
          cues={cues}
          kickerAt={kickerAt}
          titleAt={titleAt}
          underline={underline}
          titleText={titleText}
          sceneId={sceneId}
        />
      ) : treatment === "logo-wall" ? (
        <TreatmentLogoWall
          data={data}
          theme={theme}
          frame={frame}
          fps={fps}
          cues={cues}
          kickerAt={kickerAt}
          titleAt={titleAt}
          subAt={subAt}
          titleOpacity={titleOpacity}
          titleContainerY={titleContainerY}
          underline={underline}
          titleText={titleText}
          titleLines={titleLines}
          sceneId={sceneId}
        />
      ) : treatment === "feature-list" ? (
        <TreatmentFeatureList
          data={data}
          theme={theme}
          frame={frame}
          fps={fps}
          cues={cues}
          kickerAt={kickerAt}
          titleAt={titleAt}
          subAt={subAt}
          titleOpacity={titleOpacity}
          titleContainerY={titleContainerY}
          underline={underline}
          titleText={titleText}
          titleLines={titleLines}
          subText={subText}
          sceneId={sceneId}
        />
      ) : (
        /* ---------------------------------------------------------------- */
        /* ORIGINAL card — ABSENT/unknown treatment. Byte-identical behavior */
        /* ---------------------------------------------------------------- */
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
            data-scene-id={sceneId}
            data-field="kicker"
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

          {/* Title — staged line-by-line reveal with two-tone active/pending treatment.
              Each line fades+rises in sequence (16f stagger). The outer wrapper
              keeps the kinetic-light spring for the whole title block. */}
          <div
            data-scene-id={sceneId}
            data-field="title"
            style={{
              position: "relative",
              display: "inline-block",
              opacity: titleOpacity,
              transform: `translateY(${titleContainerY}px)`,
            }}
          >
            {titleLines.map((line, li) => {
              const sl = stagedLine(frame, li, titleAt, TITLE_STAGGER, 28, TITLE_DUR);
              const lineColor = sl.colorP > 0.5 ? theme.text : theme.textDim;
              return (
                <div
                  key={li}
                  style={{
                    opacity: sl.opacity,
                    transform: sl.transform,
                    fontSize: 96,
                    fontWeight: 900,
                    letterSpacing: -3,
                    lineHeight: 1.04,
                    color: lineColor,
                    maxWidth: 1500,
                  }}
                >
                  {line}
                </div>
              );
            })}
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
          {subText ? (
            <div
              data-scene-id={sceneId}
              data-field="subtitle"
              style={{
                opacity: subOpacity,
                transform: `translateY(${subY}px)`,
                fontSize: 32,
                fontWeight: 400,
                color: theme.textMuted,
                maxWidth: 1200,
              }}
            >
              {subText}
            </div>
          ) : null}

          {/* Staggered capability bullets — numbered badges (NO emoji) */}
          {bullets.length > 0 ? (
            <div data-scene-id={sceneId} data-field="bullets" style={{ display: "flex", flexDirection: "column", gap: 18, marginTop: 12 }}>
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
      )}

      <CornerMark theme={theme} opacity={ease(frame, kickerAt + 6, kickerAt + 22, 0, 0.65)} sceneId={sceneId} resolveSrc={resolveSrc} />
    </AbsoluteFill>
  );
};
