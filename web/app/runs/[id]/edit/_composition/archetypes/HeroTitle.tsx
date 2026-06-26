// HERO-TITLE archetype — ported from Orinovate kinetic-light IntroScene +
// HookScene. A centered lockup: a kicker eyebrow rises, the title springs in
// (damping 16), the punch word lands in the brand accent with a glow, and a
// subtitle settles under it. A slow breath + glow "tail animation" keeps the
// held frames alive so the scene never freezes on the hold.
//
// Reveals fire on the scene's CUE frames (relative to scene in_frame):
//   kicker-in -> kicker, title-in -> title, punch -> accent glow on punchWord,
//   subtitle-in -> subtitle.
import React from "react";
import { AbsoluteFill, Img, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import type { Cue, SceneData, Theme } from "../types";
import { ease, alphaHex, interpClamp, splitToLines, stagedLine, breathDrift } from "../motion";

const cueAt = (cues: Cue[], label: string, fallback: number) =>
  cues.find((c) => c.label === label)?.at_frame ?? fallback;

// Resolve a public-relative path under public/ via staticFile; pass absolute /
// remote (http or leading-slash) paths through untouched. Mirrors Timeline's
// resolveAsset so the captured brand logo (theme.logoSrc, staged into
// studio/public/brand/ by style_fill) renders as an <Img>. ABSENT logoSrc =>
// the bookend degrades to the wordmark text (never invents a logo).
// When a `resolve` (the Timeline assetBaseUrl seam) is passed, public-relative
// names resolve against the hosted bucket so the editor preview shows the real
// logo too (matches how screenshots/VO/music/walkthrough already resolve).
const resolveLogo = (path: string, resolve?: (p: string) => string): string =>
  path.startsWith("http") || path.startsWith("/")
    ? path
    : resolve
      ? resolve(path)
      : staticFile(path);

// Heuristic: is this hero acting as the CLOSING / CTA bookend? The CTA beat is
// where the brand promise + call-to-action land (feedback_slogan_lands_on_cta).
// Detected WITHOUT a schema change: a kicker that reads as a close/CTA, or a
// subtitle that carries a CTA signal (an arrow, a URL, or "start"/"get"). When
// false the hero is the OPENING bookend and the subtitle stays a plain tagline.
const isCtaBeat = (data: SceneData): boolean => {
  const k = (data.kicker ?? "").toLowerCase();
  const s = (data.subtitle ?? "").toLowerCase();
  if (/(get started|start now|sign ?up|close|cta|try|join)/.test(k)) return true;
  if (/→|->|https?:\/\/|www\.|\.com|\.io|\.ai|start now|get started/.test(s)) return true;
  return false;
};

// Split a title around its punch word so the punch word can be accent-colored.
const splitPunch = (title: string, punch?: string) => {
  if (!punch || !title.includes(punch)) return { pre: title, hit: "", post: "" };
  const i = title.indexOf(punch);
  return { pre: title.slice(0, i), hit: punch, post: title.slice(i + punch.length) };
};

export const HeroTitle: React.FC<{
  data: SceneData;
  cues: Cue[];
  theme: Theme;
  durationInFrames: number;
  // OPTIONAL: scene id, threaded from Timeline for click-to-select addressing.
  sceneId?: string;
  // OPTIONAL: the Timeline assetBaseUrl seam, so the brand logo resolves from the
  // hosted bucket in the editor preview (absent in the studio render → staticFile).
  resolveSrc?: (path: string) => string;
}> = ({ data, cues, theme, durationInFrames, sceneId, resolveSrc }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // OPTIONAL geometry overrides (data.geo). Each reads `data.geo?.KEY ?? LITERAL`
  // so when geo is absent (every production run) the original literal is used and
  // output is byte-identical. The visual editor writes these keys.
  const geo = data.geo;
  const plateW = geo?.plateW ?? 1200;
  const plateH = geo?.plateH ?? 720;
  // Plate position nudge (px from center). Absent -> 0,0 so output is identical.
  const plateOffsetX = geo?.plateOffsetX ?? 0;
  const plateOffsetY = geo?.plateOffsetY ?? 0;
  const kickerFontSize = geo?.kickerFontSize ?? 26;
  const titleFontSize = geo?.titleFontSize ?? 132;
  const subtitleFontSize = geo?.subtitleFontSize ?? 34;

  // Fallback cue frames must fit SHORT scenes (a 31-frame title beat can't wait
  // for a hard-coded 36-frame title-in or the title never appears — the
  // blank-scenes fix). Scale the entrance to the scene length so the title +
  // subtitle always land with time to read on the hold.
  const titleFallback = Math.min(36, Math.round(durationInFrames * 0.22));
  const kickerAt = cueAt(cues, "kicker-in", Math.min(6, Math.round(durationInFrames * 0.05)));
  const titleAt = cueAt(cues, "title-in", titleFallback);
  const punchAt = cueAt(cues, "punch", titleAt + Math.round((durationInFrames - titleAt) * 0.4));
  const subAt = cueAt(cues, "subtitle-in", titleAt + Math.min(20, Math.round((durationInFrames - titleAt) * 0.35)));

  // HARD never-empty guard (blank-scenes fix): an empty title falls back to the
  // brand wordmark so the hero ALWAYS shows legible content, never a bare glow.
  const titleText = (data.title ?? "").trim() || theme.wordmark || "";

  // Title staged reveal: split into lines, each line fades+rises in sequence.
  // The first line fires on titleAt; subsequent lines stagger by 18f.
  const TITLE_STAGGER = 18;
  const TITLE_DUR = 18;
  const titleLines = splitToLines(titleText, 20);
  // Scale: springs in on the first line's arrival (kinetic-light damping 16).
  const titleSpring = spring({
    frame: frame - titleAt,
    fps,
    config: { damping: 16, stiffness: 150, mass: 0.8 },
  });
  const titleScale = interpolate(titleSpring, [0, 0.7, 1], [0.9, 1.04, 1]);
  // Overall container opacity: starts fading in at titleAt (first line).
  const titleOpacity = ease(frame, titleAt, titleAt + 16, 0, 1);

  // Punch word: accent glow that pops on the punch cue, then a slow tail pulse
  // (HookScene.secGlow shape) so the held word keeps breathing.
  const punchGlow = interpClamp(
    frame,
    [punchAt, punchAt + 14, punchAt + 40, durationInFrames - 18, durationInFrames],
    [0, 1, 0.55, 0.85, 0.5]
  );

  // Soft radial glow behind the lockup (IntroScene glowPulse) + whole-lockup
  // breath after assembly — the tail animation that prevents a frozen hold.
  const breathe = interpClamp(
    frame,
    [subAt + 14, subAt + 44, durationInFrames - 1],
    [1, 1.015, 1.0]
  );
  const glowPulse = interpClamp(
    frame,
    [titleAt, titleAt + 40, durationInFrames - 1],
    [0.8, 1.2, 0.95]
  );

  // Exit drift over the last 12 frames so scenes hand off cleanly.
  const exitFade = ease(frame, durationInFrames - 12, durationInFrames, 1, 0.0);
  const exitShift = ease(frame, durationInFrames - 12, durationInFrames, 0, -20);

  const kickerOpacity = ease(frame, kickerAt, kickerAt + 14, 0, 1);
  const kickerY = ease(frame, kickerAt, kickerAt + 14, 14, 0);
  const subOpacity = ease(frame, subAt, subAt + 16, 0, 1);
  const subY = ease(frame, subAt, subAt + 16, 14, 0);

  // --- Logo (spec §4) -------------------------------------------------------
  // The hero is a BOOKEND, so it shows the real captured logo prominently when
  // present, else the wordmark text. The logo lockup rises with the kicker.
  const logoSrc = (theme.logoSrc ?? "").trim();
  const hasLogo = logoSrc.length > 0;
  // Persistent corner mark: a small brand mark anchored bottom-right on every
  // scene per the spec. Graceful when there is no logo AND no wordmark.
  const cornerMark = hasLogo ? logoSrc : "";
  const cornerWordmark = (theme.wordmark ?? "").trim();
  const cornerOpacity = ease(frame, kickerAt + 6, kickerAt + 22, 0, 0.7);
  const cornerDrift = breathDrift(frame, kickerAt + 30, 1.5, 130);

  // --- CTA bookend (spec §3 scene 7, feedback_slogan_lands_on_cta) ----------
  // On the closing/CTA hero, render the subtitle as an accent CTA pill that
  // pops in (the slogan/brand-promise lands HERE, not on the opening hero).
  const cta = isCtaBeat(data);
  const ctaSpring = spring({
    frame: frame - subAt,
    fps,
    config: { damping: 14, stiffness: 170, mass: 0.7 },
  });
  const ctaScale = interpolate(ctaSpring, [0, 0.7, 1], [0.7, 1.04, 1]);
  const ctaGlow = interpClamp(
    frame,
    [subAt, subAt + 16, subAt + 44, durationInFrames - 14, durationInFrames],
    [0, 1, 0.6, 0.85, 0.55]
  );

  return (
    <AbsoluteFill
      style={{
        backgroundColor: theme.bg,
        fontFamily: theme.fontDisplay,
        opacity: exitFade,
        transform: `translateY(${exitShift}px)`,
      }}
    >
      {/* Soft brand-navy radial glow behind the lockup */}
      <div
        data-scene-id={sceneId}
        data-field="plate"
        style={{
          position: "absolute",
          top: "50%",
          left: "50%",
          width: plateW,
          height: plateH,
          transform: `translate(calc(-50% + ${plateOffsetX}px), calc(-50% + ${plateOffsetY}px)) scale(${glowPulse})`,
          background: `radial-gradient(ellipse, ${theme.navy}22 0%, ${theme.navy}00 65%)`,
        }}
      />
      <div
        style={{
          position: "absolute",
          inset: 0,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: 26,
          transform: `scale(${breathe})`,
        }}
      >
        {/* Brand lockup — the real captured logo (theme.logoSrc) when present,
            else the wordmark text. Rises with the kicker. Hidden when the title
            already IS the wordmark and there is no real logo, so it isn't shown
            twice (the never-empty fallback case). */}
        {hasLogo ? (
          <div
            data-scene-id={sceneId}
            data-field="logo"
            style={{
              opacity: kickerOpacity,
              transform: `translateY(${kickerY}px)`,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              height: 72,
            }}
          >
            <Img
              src={resolveLogo(logoSrc, resolveSrc)}
              style={{ height: "100%", width: "auto", objectFit: "contain", display: "block" }}
            />
          </div>
        ) : theme.wordmark && theme.wordmark.trim() !== titleText.trim() ? (
          <div
            data-scene-id={sceneId}
            data-field="logo"
            style={{
              opacity: kickerOpacity,
              fontSize: 46,
              fontWeight: 600,
              letterSpacing: -1,
              color: theme.navy,
            }}
          >
            {theme.wordmark}
          </div>
        ) : null}

        {/* Kicker eyebrow */}
        <div
          style={{
            opacity: kickerOpacity,
            transform: `translateY(${kickerY}px)`,
            fontSize: kickerFontSize,
            fontWeight: 600,
            letterSpacing: 6,
            textTransform: "uppercase",
            color: theme.textDim,
            fontFamily: theme.fontMono,
          }}
        >
          {data.kicker}
        </div>

        {/* Title — staged line-by-line reveal with two-tone active/pending treatment.
            Each line fades+rises in sequence. Lines not yet active render dimmed;
            the arriving line brightens to full text color. Single-line titles fall
            through with the original spring scale behavior. */}
        <div
          data-scene-id={sceneId}
          data-field="title"
          style={{
            transform: `scale(${titleScale})`,
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            gap: 4,
          }}
        >
          {titleLines.map((line, li) => {
            const sl = stagedLine(frame, li, titleAt, TITLE_STAGGER, 36, TITLE_DUR);
            // Two-tone: pending lines dim to textDim, active/arrived lines are full text.
            const lineColor = sl.colorP > 0.5 ? theme.text : theme.textDim;
            // Accent punch word only on the line that contains punchWord.
            const { pre, hit, post } = splitPunch(line, data.punchWord);
            return (
              <div
                key={li}
                style={{
                  opacity: sl.opacity,
                  transform: sl.transform,
                  fontSize: titleFontSize,
                  fontWeight: 900,
                  letterSpacing: -4,
                  lineHeight: 1.02,
                  color: lineColor,
                  textAlign: "center",
                  maxWidth: 1500,
                  transition: "color 0s", // color is frame-driven, not CSS transition
                }}
              >
                {pre}
                {hit && (
                  <span
                    style={{
                      color: theme.accent,
                      textShadow: `0 0 ${48 * punchGlow}px ${theme.accent}${alphaHex(punchGlow * 0.7)}`,
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

        {/* Accent underline rule — always visible on any background (light or dark).
            Slides in with the title so the brand color is never absent, even when
            there is no punchWord to anchor the accent glow. Width pulses gently on
            the breath so it stays alive on the hold. */}
        <div
          style={{
            opacity: titleOpacity,
            width: interpolate(breathe, [1, 1.015], [96, 108]),
            height: 4,
            borderRadius: 2,
            backgroundColor: theme.accent,
            boxShadow: `0 0 ${16 * punchGlow}px ${theme.accent}88`,
          }}
        />

        {/* Subtitle — on the CLOSING/CTA hero it lands as an accent CTA pill
            (the brand promise / call-to-action; feedback_slogan_lands_on_cta),
            with a spring pop + held accent glow. On the opening hero it stays a
            plain muted tagline. */}
        {data.subtitle ? (
          cta ? (
            <div
              data-scene-id={sceneId}
              data-field="subtitle"
              style={{
                opacity: subOpacity,
                transform: `scale(${ctaScale})`,
                marginTop: 8,
                padding: "18px 40px",
                borderRadius: 999,
                backgroundColor: theme.accent,
                color: "#ffffff",
                fontSize: Math.round(subtitleFontSize * 0.92),
                fontWeight: 700,
                letterSpacing: "-0.01em",
                textAlign: "center",
                boxShadow: `0 10px 36px ${theme.accent}${alphaHex(0.45 * ctaGlow)}, inset 0 1px 0 rgba(255,255,255,0.35)`,
              }}
            >
              {data.subtitle}
            </div>
          ) : (
            <div
              data-scene-id={sceneId}
              data-field="subtitle"
              style={{
                opacity: subOpacity,
                transform: `translateY(${subY}px)`,
                fontSize: subtitleFontSize,
                fontWeight: 400,
                color: theme.textMuted,
                maxWidth: 1100,
                textAlign: "center",
              }}
            >
              {data.subtitle}
            </div>
          )
        ) : null}
      </div>

      {/* Persistent corner brand mark (spec §4) — bottom-right, small + low-key,
          on every scene. Real logo <Img> when present, else the wordmark text;
          renders nothing when neither exists (graceful). */}
      {(cornerMark || cornerWordmark) && (
        <div
          data-scene-id={sceneId}
          data-field="cornerMark"
          style={{
            position: "absolute",
            right: 56,
            bottom: 44,
            opacity: cornerOpacity,
            transform: `translateY(${cornerDrift}px)`,
            display: "flex",
            alignItems: "center",
            height: 34,
            pointerEvents: "none",
          }}
        >
          {cornerMark ? (
            <Img
              src={resolveLogo(cornerMark, resolveSrc)}
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
