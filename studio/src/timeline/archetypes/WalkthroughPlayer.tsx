// WALKTHROUGH-PLAYER archetype — a produced walkthrough MP4 (Walk Agent capture)
// played INSIDE the branded studio composition. Maps a scene role: the "here is
// the actual guided walkthrough" beat. The clip plays inside a brand-tinted frame
// (the same studio card language as apple-screenshot) with a kinetic title bar
// over the top — the brand wordmark / emphasis (`overlayTitle`) with an accent
// underline that sweeps in on the scene's cue frames, exactly like the cards.
//
// The clip's OWN audio is muted by default (`muteClip`, default true): the scene
// VO owns the audio (the Timeline places a per-scene <Audio> at this scene's
// in_frame). So the produced clip inherits Walk Studio's branding + VO placement
// instead of carrying its own baked-in narration.
//
// INTEGRATION NOTE (LOOP-STATE P2): for the cleanest branding, consume the RAW
// 60fps base.mp4 (pre-overlay) from the walkthrough capture — not the finished
// "Canonical Explainer" (which bakes in its own cursor ring + step bar + banner).
// This archetype then adds OUR overlay. style_fill decides which clip to point at.
//
// Reveals fire on the scene's CUE frames (relative to scene in_frame):
//   card-in  -> the video frame arrives (Apple shrink/zoom settle, NO overshoot),
//   title-in -> the overlay title bar slides in,
//   accent   -> the brand accent underline sweeps in under the title.
// Sensible fallback cue frames keep it animating even when a scene has no cues.
import React from "react";
import {
  AbsoluteFill,
  OffthreadVideo,
  interpolate,
  useCurrentFrame,
} from "remotion";
import type { Cue, SceneData, Theme } from "../types";
import { appleRise, breathDrift, EASE_OUT_QUART, easeOutCubic, alphaHex, actNum, actLabel } from "../motion";

const cueAt = (cues: Cue[], label: string, fallback: number) =>
  cues.find((c) => c.label === label)?.at_frame ?? fallback;

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

  const src = data.videoSrc ? resolveSrc(data.videoSrc) : "";
  const fit = data.videoFit ?? "contain";
  // VO owns the audio: clips mute by default. Only an explicit false keeps sound.
  const muted = data.muteClip !== false;
  const title = (data.overlayTitle ?? theme.wordmark ?? "").trim();

  const cardAt = cueAt(cues, "card-in", 6);
  const titleAt = cueAt(cues, "title-in", cardAt + 10);
  const accentAt = cueAt(cues, "accent", titleAt + 8);

  // Apple shrink/zoom arrival (mirrors apple-screenshot): the frame starts
  // slightly LARGER + soft and settles to 1.0 with cubic ease-out (NO overshoot),
  // revealed behind a top-down clip mask. Opacity eases in alongside.
  const ARRIVE = 26;
  const t = easeOutCubic((frame - cardAt) / ARRIVE);
  const scale = 1.05 - 0.05 * t; // 1.05 -> 1.00 (shrink, no overshoot)
  const cardOpacity = interpolate(frame, [cardAt, cardAt + 12], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: EASE_OUT_QUART,
  });
  const maskReveal = interpolate(frame, [cardAt, cardAt + ARRIVE], [100, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: EASE_OUT_QUART,
  });

  // Title bar slides in (Apple rise), then a brand accent underline sweeps in
  // under it on the `accent` cue — the SAME cue-driven underline the cards use.
  const titleRise = appleRise(frame, titleAt, 16, 18);
  const underline = interpolate(frame, [accentAt, accentAt + 22], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: EASE_OUT_QUART,
  });

  // breath drift keeps the settled frame alive (tiny, deterministic).
  const breath = breathDrift(frame, cardAt + ARRIVE + 6, 2.5, 120);

  const exitFade = interpolate(frame, [durationInFrames - 14, durationInFrames], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: EASE_OUT_QUART,
  });

  // Act badge label from kicker (≤2 words, all-caps); fall back to overlayTitle.
  const badgeSource = (data.kicker ?? data.overlayTitle ?? "").trim();
  const badgeLabel = actIndex > 0 ? actLabel(badgeSource) : "";
  const badgeText = actIndex > 0 ? `${actNum(actIndex)}${badgeLabel ? ` — ${badgeLabel}` : ""}` : "";

  return (
    <AbsoluteFill
      style={{
        backgroundColor: theme.bg,
        fontFamily: theme.fontDisplay,
        opacity: exitFade,
      }}
    >
      {/* soft brand mesh so the floating frame has something to sit on */}
      <AbsoluteFill
        style={{
          background: `
            radial-gradient(ellipse 1000px 720px at 26% 22%, ${theme.navy}1c 0%, transparent 60%),
            radial-gradient(ellipse 1000px 760px at 78% 80%, ${theme.accent}16 0%, transparent 60%),
            ${theme.bg}
          `,
        }}
      />

      <AbsoluteFill
        style={{
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          transform: `translateY(${breath}px)`,
        }}
      >
        {/* The brand-tinted video frame — studio card chrome around the clip. */}
        <div
          data-scene-id={sceneId}
          data-field="card"
          style={{
            opacity: cardOpacity,
            transform: `scale(${scale})`,
            transformOrigin: "center center",
            width: 1420,
            borderRadius: 18,
            overflow: "hidden",
            backgroundColor: theme.bgCardRaised,
            border: `1px solid ${theme.border}`,
            boxShadow: [
              "0 40px 120px rgba(15,35,56,0.22)",
              "0 8px 28px rgba(15,35,56,0.12)",
              "inset 0 1px 0 rgba(255,255,255,0.9)",
            ].join(", "),
          }}
        >
          {/* Kinetic title bar — brand wordmark / emphasis over the clip. */}
          <div
            style={{
              height: 64,
              display: "flex",
              flexDirection: "column",
              justifyContent: "center",
              gap: 8,
              padding: "0 26px",
              backgroundColor: theme.bgCard,
              borderBottom: `1px solid ${theme.border}`,
            }}
          >
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 16,
                opacity: titleRise.opacity,
                transform: titleRise.transform,
              }}
            >
              {/* brand accent dot (NOT macOS traffic lights) */}
              <div
                style={{
                  width: 12,
                  height: 12,
                  borderRadius: "50%",
                  backgroundColor: theme.accent,
                  boxShadow: `0 0 14px ${theme.accent}aa`,
                }}
              />
              <span
                data-scene-id={sceneId}
                data-field="overlayTitle"
                style={{
                  fontSize: 26,
                  fontWeight: 700,
                  letterSpacing: "-0.01em",
                  color: theme.text,
                }}
              >
                {title}
              </span>
            </div>
            {/* accent underline sweeps in on the `accent` cue (same as the cards) */}
            <div
              style={{
                marginLeft: 28,
                height: 4,
                width: `${Math.round(underline * 220)}px`,
                borderRadius: 4,
                background: theme.accent,
                boxShadow: `0 0 16px ${theme.accent}${alphaHex(0.4 * underline)}`,
              }}
            />
          </div>

          {/* the produced walkthrough clip, mask-revealed top-down as it arrives */}
          <div
            style={{
              position: "relative",
              width: "100%",
              // fixed 16:9 window so the frame is a stable size; videoFit decides
              // whether the clip letterboxes (contain) or fills + crops (cover).
              height: 738,
              overflow: "hidden",
              backgroundColor: "#000000",
              clipPath: `inset(${maskReveal}% 0 0 0)`,
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
                  objectPosition: "center",
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
                {title || theme.wordmark}
              </AbsoluteFill>
            )}
          </div>
        </div>

        {/* optional muted caption under the frame */}
        {data.caption ? (
          <div
            data-scene-id={sceneId}
            data-field="caption"
            style={{
              marginTop: 26,
              opacity: titleRise.opacity,
              transform: titleRise.transform,
              fontSize: 26,
              fontWeight: 500,
              letterSpacing: "0.02em",
              color: theme.textMuted,
              fontFamily: theme.fontMono,
            }}
          >
            {data.caption}
          </div>
        ) : null}
      </AbsoluteFill>

      {/* Numbered act badge — top-left eyebrow: "NN — LABEL".
          Rendered LAST (highest z-order) so it paints over the mesh + frame. */}
      {actIndex > 0 && (
        <div
          style={{
            position: "absolute",
            left: 60,
            top: 52,
            opacity: titleRise.opacity,
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
    </AbsoluteFill>
  );
};
