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
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import type { Cue, SceneData, Theme } from "../types";
import { ease, alphaHex, interpClamp, splitToLines, stagedLine } from "../motion";

const cueAt = (cues: Cue[], label: string, fallback: number) =>
  cues.find((c) => c.label === label)?.at_frame ?? fallback;

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
}> = ({ data, cues, theme, durationInFrames, sceneId }) => {
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
        {/* Wordmark — hidden when the title already IS the wordmark (the
            never-empty fallback case) so it isn't shown twice. */}
        {theme.wordmark && theme.wordmark.trim() !== titleText.trim() ? (
          <div
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

        {/* Subtitle */}
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
      </div>
    </AbsoluteFill>
  );
};
