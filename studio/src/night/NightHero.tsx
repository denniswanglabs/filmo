// Engineered Night hero (spec §5.2): eyebrow → stacked two-line headline with the
// key phrase carrying the accent → corner brackets drawing in around it → CTA pair.
// Pure frame math; every entrance is the spec's pop atom.
import React from "react";
import { NIGHT_TYPE, type NightTokens } from "./theme";
import { ladderStart, microDrift, pop } from "./motion";
import { CornerBrackets, CtaPair, Eyebrow, popStyle } from "./ui";

export interface HeroPart {
  text: string;
  accent?: boolean;
}

export interface NightHeroData {
  eyebrow?: string;
  /** Headline as lines of parts; parts marked accent render in the brand accent. */
  lines: HeroPart[][];
  sub?: string;
  ctaPrimary?: string;
  ctaSecondary?: string;
}

export const NightHero: React.FC<{
  t: NightTokens;
  frame: number;
  fps: number;
  data: NightHeroData;
}> = ({ t, frame, fps, data }) => {
  const drift = microDrift(frame, fps);
  const eyebrowPop = pop(frame, Math.round(0.1 * fps), fps);
  const bracketProgress = Math.min(1, Math.max(0, (frame - Math.round(0.25 * fps)) / (0.55 * fps)));
  const ctaStart = Math.round(1.35 * fps);
  const BOX_W = 1060;
  const BOX_H = 460;

  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <div
        style={{
          position: "relative",
          width: BOX_W,
          minHeight: BOX_H,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: 28,
          transform: `scale(${drift})`,
        }}
      >
        <CornerBrackets t={t} width={BOX_W} height={BOX_H} progress={bracketProgress} />
        {data.eyebrow ? (
          <div style={popStyle(eyebrowPop)}>
            <Eyebrow t={t} accent>
              {data.eyebrow}
            </Eyebrow>
          </div>
        ) : null}
        <div style={{ textAlign: "center" }}>
          {data.lines.map((parts, li) => {
            const p = pop(frame, Math.round(0.3 * fps) + ladderStart(li, fps), fps, 260);
            return (
              <div
                key={li}
                style={{
                  ...popStyle(p),
                  fontFamily: t.fontDisplay,
                  fontSize: NIGHT_TYPE.display,
                  fontWeight: 700,
                  letterSpacing: "-0.025em",
                  lineHeight: 1.12,
                  color: t.ink,
                }}
              >
                {parts.map((part, pi) => (
                  <span key={pi} style={part.accent ? { color: t.accent } : undefined}>
                    {part.text}
                  </span>
                ))}
              </div>
            );
          })}
        </div>
        {data.sub ? (
          <div
            style={{
              ...popStyle(pop(frame, Math.round(0.95 * fps), fps)),
              fontFamily: t.fontBody,
              fontSize: NIGHT_TYPE.lede,
              fontWeight: 400,
              color: t.inkMuted,
              maxWidth: 760,
              textAlign: "center",
              lineHeight: 1.5,
            }}
          >
            {data.sub}
          </div>
        ) : null}
        {data.ctaPrimary ? (
          <div style={{ marginTop: 6 }}>
            <CtaPair
              t={t}
              primary={data.ctaPrimary}
              secondary={data.ctaSecondary}
              frame={frame}
              start={ctaStart}
              fps={fps}
            />
          </div>
        ) : null}
      </div>
    </div>
  );
};
