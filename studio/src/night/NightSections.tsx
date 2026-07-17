// Engineered Night sections (spec §5) — every beat of the film beyond the hero.
// Each component receives the scene-local frame (0 at camera arrival) and reads
// ONLY real data stamped by the pipeline: captured screenshots, page quotes,
// real stats, real feature copy. No invented content lives here.
import React from "react";
import { Img, staticFile } from "remotion";
import { NIGHT_TYPE, type NightTokens } from "./theme";
import { countUp, ladderStart, microDrift, pop, rise, riseStyle, typedChars } from "./motion";
import { Chip, Eyebrow, popStyle } from "./ui";
import { CONTENT_W } from "./Stage";

const resolveAsset = (path: string): string =>
  path.startsWith("http") || path.startsWith("/") ? path : staticFile(path);

const Section: React.FC<{
  children: React.ReactNode;
  frame: number;
  fps: number;
  t?: NightTokens;
  wordmark?: string;
  index?: number;
}> = ({ children, frame, fps, t, wordmark, index }) => (
  <div
    style={{
      position: "absolute",
      inset: 0,
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
    }}
  >
    {/* Structural header (reference grammar): the film's wordmark + a muted
        section index pin every beat to the one engineered surface. */}
    {t && wordmark ? (
      <div
        style={{
          position: "absolute",
          top: 54,
          left: 0,
          right: 0,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          gap: 14,
          opacity: pop(frame, 4, fps).opacity * 0.85,
          fontFamily: t.fontBody,
          fontSize: 11,
          fontWeight: 600,
          letterSpacing: "0.22em",
          color: t.inkDim,
        }}
      >
        <span>{wordmark.toUpperCase()}</span>
        {typeof index === "number" ? (
          <>
            <span style={{ width: 26, height: 1, background: t.panelLine }} />
            <span style={{ color: t.accent, opacity: 0.75 }}>
              {String(index + 1).padStart(2, "0")}
            </span>
          </>
        ) : null}
      </div>
    ) : null}
    <div
      style={{
        width: CONTENT_W,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: 30,
        transform: `scale(${microDrift(frame, fps)})`,
      }}
    >
      {children}
    </div>
  </div>
);

/** The grounding beat: the captured homepage framed as a surface in the world. */
export const NightPanel: React.FC<{
  t: NightTokens;
  frame: number;
  fps: number;
  data: { imageSrc?: string; caption?: string };
}> = ({ t, frame, fps, data }) => {
  const p = pop(frame, Math.round(0.15 * fps), fps, 260);
  // §C two-stage arrival: the browser frame lands first, THEN the captured page
  // fades in inside it — the panel reads as a surface receiving content.
  const shotIn = pop(frame, Math.round(0.5 * fps), fps, 300);
  // Slow push-in over the hold so the shot never freezes.
  const push = 1 + Math.min(0.05, (frame / fps) * 0.009);
  return (
    <Section frame={frame} fps={fps}>
      {data.caption ? (
        <div style={riseStyle(rise(frame, Math.round(0.9 * fps), fps))}>
          <Eyebrow t={t}>{data.caption}</Eyebrow>
        </div>
      ) : null}
      <div
        style={{
          ...popStyle(p),
          width: 1180,
          borderRadius: 18,
          border: `1px solid ${t.panelLine}`,
          background: t.panel,
          padding: 10,
          boxShadow: "0 60px 140px -60px rgba(0,0,0,0.9)",
          overflow: "hidden",
        }}
      >
        <div style={{ display: "flex", gap: 7, padding: "4px 6px 10px" }}>
          {[0, 1, 2].map((i) => (
            <div key={i} style={{ width: 10, height: 10, borderRadius: 5, background: "rgba(255,255,255,0.16)" }} />
          ))}
        </div>
        <div style={{ borderRadius: 10, overflow: "hidden" }}>
          {data.imageSrc ? (
            <Img
              src={resolveAsset(data.imageSrc)}
              style={{
                width: "100%",
                display: "block",
                opacity: shotIn.opacity,
                transform: `scale(${push})`,
                transformOrigin: "50% 20%",
              }}
            />
          ) : (
            <div style={{ height: 560, background: "#0B0B0B" }} />
          )}
        </div>
      </div>
    </Section>
  );
};

/** Pull-quote in Night type — the (sentence-trimmed) real testimonial.
 *  The quote develops over the WHOLE beat (pacing budget: no long static hold):
 *  it reveals in three phrase chunks that pace the narration, each chunk popping
 *  and brightening from muted to ink as the read reaches it; the attribution and
 *  its accent underline land late. `holdFrames` scales the reveal to the beat. */
export const NightQuote: React.FC<{
  t: NightTokens;
  frame: number;
  fps: number;
  data: { quote?: string; quoteAttribution?: string; holdFrames?: number };
}> = ({ t, frame, fps, data }) => {
  const quote = data.quote ?? "";
  const words = quote.split(/\s+/).filter(Boolean);
  const third = Math.ceil(words.length / 3);
  const chunks = [
    words.slice(0, third).join(" "),
    words.slice(third, 2 * third).join(" "),
    words.slice(2 * third).join(" "),
  ].filter(Boolean);
  const hold = data.holdFrames ?? Math.round(10 * fps);
  // Chunks arrive across the first ~70% of the beat; attribution in the last ~25%.
  const chunkStart = (i: number) => Math.round(0.3 * fps + (i * 0.7 * hold) / Math.max(1, chunks.length));
  const whoStart = Math.round(hold * 0.78);
  const mark = pop(frame, 2, fps);
  const underline = Math.min(1, Math.max(0, (frame - whoStart) / (0.5 * fps)));
  return (
    <Section frame={frame} fps={fps}>
      <div style={{ ...popStyle(mark), fontFamily: t.fontDisplay, fontSize: 120, lineHeight: 0.6, color: t.accent, fontWeight: 700 }}>
        &ldquo;
      </div>
      <div
        style={{
          fontFamily: t.fontDisplay,
          fontSize: 44,
          fontWeight: 600,
          letterSpacing: "-0.02em",
          lineHeight: 1.34,
          maxWidth: 1040,
          textAlign: "center",
        }}
      >
        {chunks.map((chunk, i) => {
          const p = pop(frame, chunkStart(i), fps, 260);
          // The chunk being read is ink; earlier chunks settle to muted.
          const isCurrent = i === chunks.length - 1
            ? frame >= chunkStart(i)
            : frame >= chunkStart(i) && frame < chunkStart(i + 1);
          return (
            <span
              key={i}
              style={{
                opacity: p.opacity,
                color: isCurrent ? t.ink : t.inkMuted,
                transition: "none",
              }}
            >
              {chunk}{" "}
            </span>
          );
        })}
      </div>
      {data.quoteAttribution ? (
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 12 }}>
          <div style={{ width: 150 * underline, height: 3, borderRadius: 2, background: t.accent }} />
          <div
            style={{
              ...popStyle(pop(frame, whoStart, fps)),
              fontFamily: t.fontBody,
              fontSize: NIGHT_TYPE.label,
              fontWeight: 500,
              color: t.inkMuted,
            }}
          >
            — {data.quoteAttribution}
          </div>
        </div>
      ) : null}
    </Section>
  );
};

/** Split a stat value into prefix / numeric part / suffix so the NUMBER can
 *  count up while the currency sign and unit stay put. "$1.9tn" -> ["$", "1.9",
 *  "tn"]; "99.999%" -> ["", "99.999", "%"]; non-numeric values -> no animation. */
export function splitStatValue(value: string): { prefix: string; num: number | null; decimals: number; grouped: boolean; suffix: string } {
  const m = /^([^0-9]*)(\d[\d,]*(?:\.\d+)?)(.*)$/.exec(value.trim());
  if (!m) return { prefix: "", num: null, decimals: 0, grouped: false, suffix: "" };
  const raw = m[2];
  const grouped = raw.includes(",");
  const num = parseFloat(raw.replace(/,/g, ""));
  const decimals = raw.includes(".") ? raw.split(".")[1].length : 0;
  if (!isFinite(num)) return { prefix: "", num: null, decimals: 0, grouped: false, suffix: "" };
  return { prefix: m[1], num, decimals, grouped, suffix: m[3] };
}

/** Format a count-up sample exactly like the target's own notation (same decimal
 *  places, same digit grouping) — display math only, never a new fact. */
export function formatStatNumber(n: number, decimals: number, grouped: boolean): string {
  const fixed = n.toFixed(decimals);
  if (!grouped) return fixed;
  const [int, frac] = fixed.split(".");
  const g = int.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  return frac ? `${g}.${frac}` : g;
}

/** Credibility beat: badge + one strong stat, given air (spec §5.5).
 *  Development pass §C: the numeric part COUNTS UP to the real value over ~0.7s
 *  (formatting preserved), the label rises in after, the underline draws last —
 *  the beat develops instead of landing all at once. */
export const NightCredibility: React.FC<{
  t: NightTokens;
  frame: number;
  fps: number;
  data: { eyebrow?: string; stat?: { value?: string; label?: string } };
  holdFrames?: number;
}> = ({ t, frame, fps, data }) => {
  const value = data.stat?.value ?? "";
  const label = data.stat?.label ?? "";
  const badge = pop(frame, 2, fps);
  const numStart = Math.round(0.28 * fps);
  const num = pop(frame, numStart, fps, 260);
  const parts = splitStatValue(value);
  const progress = countUp(frame, numStart, fps, 700);
  const shown = parts.num === null
    ? value
    : `${parts.prefix}${formatStatNumber(parts.num * progress, parts.decimals, parts.grouped)}${parts.suffix}`;
  const under = Math.min(1, Math.max(0, (frame - 1.05 * fps) / (0.5 * fps)));
  return (
    <Section frame={frame} fps={fps}>
      {data.eyebrow ? (
        <div style={popStyle(badge)}>
          <Chip t={t} active>
            {data.eyebrow}
          </Chip>
        </div>
      ) : null}
      <div
        style={{
          ...popStyle(num),
          fontFamily: t.fontDisplay,
          fontSize: 200,
          fontWeight: 700,
          letterSpacing: "-0.03em",
          lineHeight: 1,
          color: t.ink,
          fontVariantNumeric: "tabular-nums",
        }}
      >
        {shown}
      </div>
      <div style={{ width: 180 * under, height: 4, borderRadius: 2, background: t.accent }} />
      <div
        style={{
          ...riseStyle(rise(frame, Math.round(0.8 * fps), fps)),
          fontFamily: t.fontBody,
          fontSize: NIGHT_TYPE.lede,
          color: t.inkMuted,
          maxWidth: 720,
          textAlign: "center",
        }}
      >
        {label}
      </div>
    </Section>
  );
};

/** HUMAN/AGENT-style toggle chip pair — the active side flips mid-beat. */
const ToggleChips: React.FC<{
  t: NightTokens;
  frame: number;
  fps: number;
  left: string;
  right: string;
  flipAt: number;
}> = ({ t, frame, fps, left, right, flipAt }) => {
  const entered = pop(frame, Math.round(0.3 * fps), fps);
  const rightActive = frame >= flipAt;
  const flip = pop(frame, flipAt, fps);
  return (
    <div style={{ ...popStyle(entered), display: "flex", gap: 8 }}>
      <Chip t={t} active={!rightActive}>{left}</Chip>
      <div style={rightActive ? popStyle(flip) : undefined}>
        <Chip t={t} active={rightActive}>{right}</Chip>
      </div>
    </div>
  );
};

/** The proof moment: a terminal panel with typed lines (spec §5.3). */
export const NightTerminal: React.FC<{
  t: NightTokens;
  frame: number;
  fps: number;
  data: { title?: string; lines?: string[]; status?: string; toggle?: { left: string; right: string } };
}> = ({ t, frame, fps, data }) => {
  const lines = data.lines ?? [];
  const panel = pop(frame, Math.round(0.12 * fps), fps, 260);
  const lineStart = (i: number) => Math.round(0.55 * fps) + Math.round(i * 0.52 * fps);
  const allDone = lineStart(lines.length - 1) + Math.round(0.6 * fps);
  const status = pop(frame, allDone, fps);
  const cursorOn = Math.floor(frame / (fps * 0.4)) % 2 === 0;
  return (
    <Section frame={frame} fps={fps}>
      {data.title ? (
        <div style={popStyle(pop(frame, 2, fps))}>
          <Eyebrow t={t} accent>
            {data.title}
          </Eyebrow>
        </div>
      ) : null}
      {data.toggle ? (
        <ToggleChips
          t={t}
          frame={frame}
          fps={fps}
          left={data.toggle.left}
          right={data.toggle.right}
          flipAt={allDone + Math.round(0.4 * fps)}
        />
      ) : null}
      <div
        style={{
          ...popStyle(panel),
          width: 1000,
          borderRadius: 16,
          border: `1px solid ${t.panelLine}`,
          background: t.panel,
          padding: "26px 34px 30px",
          boxShadow: "0 60px 140px -60px rgba(0,0,0,0.9)",
          fontFamily: t.fontMono,
          fontSize: NIGHT_TYPE.mono,
          lineHeight: 1.9,
          textAlign: "left",
        }}
      >
        {lines.map((line, i) => {
          const chars = typedChars(frame, lineStart(i), fps, line);
          if (chars <= 0) return <div key={i} style={{ minHeight: 38 }} />;
          const active = chars < line.length;
          // §C development: once the command finishes typing, a dim exit-status
          // tick fades in at the end of the line — mechanical UI chrome (never a
          // brand claim), so the panel keeps living between commands.
          const doneAt = lineStart(i) + Math.ceil((line.length / 34) * fps) + Math.round(0.25 * fps);
          const tick = pop(frame, doneAt, fps);
          return (
            <div key={i} style={{ color: t.inkMuted, whiteSpace: "pre" }}>
              <span style={{ color: t.accent }}>{"❯ "}</span>
              <span style={{ color: t.ink }}>{line.slice(0, chars)}</span>
              {active && cursorOn ? <span style={{ color: t.accent }}>▍</span> : null}
              {!active ? (
                <span style={{ opacity: tick.opacity * 0.7, color: t.accent }}>{"  ✓"}</span>
              ) : null}
            </div>
          );
        })}
        {data.status ? (
          <div style={{ ...popStyle(status), marginTop: 10, color: t.accent, fontSize: NIGHT_TYPE.label }}>
            {data.status}
          </div>
        ) : null}
      </div>
    </Section>
  );
};

/** Capability section: headline + a ladder of chips popping in sequence.
 *  Development pass §C: after the last chip lands the ACTIVE highlight sweeps
 *  across the row once and settles on `activeIndex`; statement mode gains a
 *  grounded support line (~55% of the hold) + an accent underline draw — the
 *  beat keeps developing across its whole hold. */
export const NightLadder: React.FC<{
  t: NightTokens;
  frame: number;
  fps: number;
  data: { headline?: string; chips?: string[]; secondary?: string[]; activeIndex?: number; support?: string };
  wordmark?: string;
  index?: number;
  holdFrames?: number;
}> = ({ t, frame, fps, data, wordmark, index, holdFrames }) => {
  const chips = data.chips ?? [];
  const secondary = data.secondary ?? [];
  const head = pop(frame, 2, fps, 260);
  const base = Math.round(0.5 * fps);
  const secondaryStart = base + ladderStart(chips.length, fps) + Math.round(0.2 * fps);
  const hold = holdFrames ?? Math.round(4 * fps);
  // §C sweep: once every chip is in, the highlight scans the row (one chip per
  // 0.45s) and settles on the shaped activeIndex.
  const sweepStart = base + ladderStart(chips.length - 1, fps) + Math.round(0.5 * fps);
  const sweepStep = Math.round(0.45 * fps);
  let activeIdx = data.activeIndex ?? 0;
  if (chips.length > 1 && frame >= sweepStart) {
    const k = Math.floor((frame - sweepStart) / sweepStep);
    activeIdx = k < chips.length ? k : (data.activeIndex ?? 0);
  } else if (chips.length > 1) {
    activeIdx = -1; // nothing highlighted until the sweep begins
  }
  // Statement mode (no chips to ladder): the headline IS the beat — set it big,
  // accent its strongest word, and let the words pop in as a group sequence.
  const statement = chips.length === 0;
  const words = String(data.headline ?? "").split(/\s+/).filter(Boolean);
  const accentWord = words.reduce((a, b) =>
    (b.replace(/[.,!?]/g, "").length > a.replace(/[.,!?]/g, "").length ? b : a), "");
  const supportStart = Math.round(hold * 0.55);
  const underlineP = Math.min(1, Math.max(0, (frame - hold * 0.7) / (0.5 * fps)));
  return (
    <Section frame={frame} fps={fps} t={t} wordmark={wordmark} index={index}>
      {statement ? (
        <div
          style={{
            fontFamily: t.fontDisplay,
            fontSize: 84,
            fontWeight: 700,
            letterSpacing: "-0.025em",
            lineHeight: 1.12,
            maxWidth: 1150,
            textAlign: "center",
          }}
        >
          {words.map((w, i) => {
            const p = pop(frame, Math.round(0.12 * fps) + Math.round(i * 0.055 * fps), fps);
            const isAccent = w === accentWord && w.replace(/[.,!?]/g, "").length >= 6;
            return (
              <span key={i} style={{ opacity: p.opacity, color: isAccent ? t.accent : t.ink }}>
                {w}{" "}
              </span>
            );
          })}
        </div>
      ) : (
      <div
        style={{
          ...popStyle(head),
          fontFamily: t.fontDisplay,
          fontSize: NIGHT_TYPE.section,
          fontWeight: 700,
          letterSpacing: "-0.02em",
          lineHeight: 1.15,
          color: t.ink,
          maxWidth: 980,
          textAlign: "center",
        }}
      >
        {data.headline}
      </div>
      )}
      {statement && underlineP > 0 ? (
        <div style={{ width: 170 * underlineP, height: 4, borderRadius: 2, background: t.accent, marginTop: -6 }} />
      ) : null}
      {statement && data.support ? (
        <div
          style={{
            ...riseStyle(rise(frame, supportStart, fps)),
            fontFamily: t.fontBody,
            fontSize: NIGHT_TYPE.lede,
            color: t.inkMuted,
            maxWidth: 860,
            textAlign: "center",
            lineHeight: 1.5,
          }}
        >
          {data.support}
        </div>
      ) : null}
      <div style={{ display: "flex", gap: 14, flexWrap: "wrap", justifyContent: "center", maxWidth: 1000 }}>
        {chips.map((c, i) => (
          <div key={i} style={popStyle(pop(frame, base + ladderStart(i, fps), fps))}>
            <Chip t={t} active={i === activeIdx}>
              {c}
            </Chip>
          </div>
        ))}
      </div>
      {secondary.length ? (
        // Second tier (the reference's "Sites · Custom Compute · …" row): quieter
        // real product surfaces, one muted line under the chip ladder.
        <div
          style={{
            ...popStyle(pop(frame, secondaryStart, fps)),
            fontFamily: t.fontBody,
            fontSize: NIGHT_TYPE.label,
            fontWeight: 500,
            color: t.inkDim,
            letterSpacing: "0.02em",
          }}
        >
          {secondary.join("  ·  ")}
        </div>
      ) : null}
    </Section>
  );
};

/** Ecosystem row: small tiles popping in as a family (real entities only). */
export const NightEcosystem: React.FC<{
  t: NightTokens;
  frame: number;
  fps: number;
  data: { headline?: string; entities?: string[]; logos?: string[] };
}> = ({ t, frame, fps, data }) => {
  const entities = data.entities ?? [];
  const base = Math.round(0.45 * fps);
  return (
    <Section frame={frame} fps={fps}>
      {data.headline ? (
        <div style={popStyle(pop(frame, 2, fps, 260))}>
          <Eyebrow t={t}>{data.headline}</Eyebrow>
        </div>
      ) : null}
      <div style={{ display: "flex", gap: 18, justifyContent: "center" }}>
        {entities.map((name, i) => {
          const logo = data.logos?.[i];
          return (
            <div
              key={i}
              style={{
                ...popStyle(pop(frame, base + ladderStart(i, fps), fps)),
                width: 150,
                height: 120,
                borderRadius: 16,
                border: `1px solid ${t.panelLine}`,
                background: t.panel,
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "center",
                gap: 10,
              }}
            >
              {logo ? (
                <Img src={resolveAsset(logo)} style={{ width: 40, height: 40, objectFit: "contain" }} />
              ) : (
                <div
                  style={{
                    width: 40,
                    height: 40,
                    borderRadius: 12,
                    background: t.accentSoft,
                    color: t.accent,
                    display: "grid",
                    placeItems: "center",
                    fontFamily: t.fontDisplay,
                    fontWeight: 700,
                    fontSize: 20,
                  }}
                >
                  {name.slice(0, 1).toUpperCase()}
                </div>
              )}
              <div style={{ fontFamily: t.fontBody, fontSize: 14, fontWeight: 500, color: t.inkMuted }}>{name}</div>
            </div>
          );
        })}
      </div>
    </Section>
  );
};

/** Close: tagline (accent final word) → brand lockup + chip → stillness (spec §5.7). */
export const NightClose: React.FC<{
  t: NightTokens;
  frame: number;
  fps: number;
  data: {
    tagline?: string;
    accentWord?: string;
    chip?: string;
    wordmark?: string;
    logoSrc?: string;
    /** Recurring-motif bookend: the film's terminal returns, small and muted,
        under the lockup (the reference closes exactly this way). */
    terminalLines?: string[];
  };
}> = ({ t, frame, fps, data }) => {
  const tagline = data.tagline ?? "";
  const accentWord = data.accentWord ?? "";
  const pre = accentWord && tagline.endsWith(accentWord)
    ? tagline.slice(0, tagline.length - accentWord.length)
    : tagline;
  const tag = pop(frame, Math.round(0.1 * fps), fps, 260);
  const lockup = pop(frame, Math.round(1.0 * fps), fps, 260);
  const chip = pop(frame, Math.round(1.5 * fps), fps);
  return (
    <Section frame={frame} fps={fps}>
      <div
        style={{
          ...popStyle(tag),
          fontFamily: t.fontDisplay,
          fontSize: NIGHT_TYPE.section,
          fontWeight: 700,
          letterSpacing: "-0.02em",
          color: t.ink,
          textAlign: "center",
          maxWidth: 1000,
          lineHeight: 1.18,
        }}
      >
        {pre}
        {accentWord ? <span style={{ color: t.accent }}>{accentWord}</span> : null}
      </div>
      <div style={{ ...popStyle(lockup), display: "flex", alignItems: "center", gap: 18, marginTop: 14 }}>
        {data.logoSrc ? (
          <Img src={resolveAsset(data.logoSrc)} style={{ width: 54, height: 54, objectFit: "contain", borderRadius: 12 }} />
        ) : null}
        <div
          style={{
            fontFamily: t.fontDisplay,
            fontWeight: 700,
            fontSize: 40,
            letterSpacing: "0.22em",
            color: t.ink,
          }}
        >
          {data.wordmark}
        </div>
      </div>
      {data.chip ? (
        <div style={popStyle(chip)}>
          <Chip t={t}>{data.chip}</Chip>
        </div>
      ) : null}
      {data.terminalLines?.length ? (
        <div
          style={{
            ...popStyle(pop(frame, Math.round(1.9 * fps), fps, 260)),
            marginTop: 18,
            width: 640,
            borderRadius: 12,
            border: `1px solid ${t.panelLine}`,
            background: t.panel,
            padding: "16px 22px",
            fontFamily: t.fontMono,
            fontSize: 15,
            lineHeight: 1.8,
            textAlign: "left",
            opacity: 0.9,
          }}
        >
          {data.terminalLines.map((line, i) => {
            const chars = typedChars(frame, Math.round((2.1 + i * 0.35) * fps), fps, line, 46);
            return (
              <div key={i} style={{ whiteSpace: "pre", color: t.inkMuted }}>
                <span style={{ color: t.accent }}>{"❯ "}</span>
                {line.slice(0, chars)}
              </div>
            );
          })}
        </div>
      ) : null}
    </Section>
  );
};
