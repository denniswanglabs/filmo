// APPLE-SCREENSHOT archetype — a REAL captured website screenshot shown inside
// a brand-tinted browser card. Maps a scene role: the "here is the actual
// product / site" proof beat. The screenshot arrives with the Apple shrink/zoom
// (it starts slightly LARGE + soft, then settles to its resting size behind a
// clip mask), holds with a subtle breath drift, then exit-fades.
//
// Mode-INDEPENDENT by construction: this renders the real captured PNG in BOTH
// mock + real builds (screenshots are $0 deterministic), so a mock Standard
// build still shows the real site in a clean white studio card — sidestepping
// the real-mode orange-overlay coupling for screenshots.
//
// Apple iOS motion only: cubic ease-out arrivals, NO springs, NO overshoot
// (per feedback_apple_screenshot_animation — "cubic ease-out, NO spring").
// Palette from props.theme so style-fill recolors the frame per brand.
//
// Reveals fire on the scene's CUE frames (relative to scene in_frame):
//   card-in -> the browser card + screenshot arrive (shrink/zoom),
//   caption-in -> the muted caption settles underneath.
import React from "react";
import { AbsoluteFill, Img, interpolate, useCurrentFrame } from "remotion";
import type { Cue, SceneData, Theme } from "../types";
import { appleRise, breathDrift, EASE_OUT_QUART, easeOutCubic, actNum, actLabel } from "../motion";

const cueAt = (cues: Cue[], label: string, fallback: number) =>
  cues.find((c) => c.label === label)?.at_frame ?? fallback;

export const AppleScreenshot: React.FC<{
  data: SceneData;
  cues: Cue[];
  theme: Theme;
  durationInFrames: number;
  // resolver injected by Timeline.tsx (same staticFile-or-passthrough helper as audio)
  resolveSrc: (path: string) => string;
  // 1-based act index among content-beat scenes (-1 = no badge)
  actIndex?: number;
  // OPTIONAL: scene id, threaded from Timeline for click-to-select addressing.
  sceneId?: string;
}> = ({ data, cues, theme, durationInFrames, resolveSrc, actIndex = -1, sceneId }) => {
  const frame = useCurrentFrame();

  const showChrome = (data.frame ?? "browser") !== "none";
  const src = data.imageSrc ? resolveSrc(data.imageSrc) : "";

  // OPTIONAL geometry overrides (data.geo). `data.geo?.KEY ?? LITERAL` so when geo
  // is absent (every production run) the original literal is used and output is
  // byte-identical. The visual editor writes these keys.
  const geo = data.geo;
  const cardW = geo?.cardW ?? 1380;
  const cardRadius = geo?.cardRadius ?? 18;
  const shotH = geo?.shotH ?? 712;
  // Card position nudge (px). Absent -> 0,0 so output is byte-identical.
  const cardOffsetX = geo?.cardOffsetX ?? 0;
  const cardOffsetY = geo?.cardOffsetY ?? 0;

  const cardAt = cueAt(cues, "card-in", 8);
  const captionAt = cueAt(cues, "caption-in", cardAt + 30);
  // The grounded value-prop headline rises just BEFORE the card settles, so the
  // viewer reads WHAT the screenshot proves as the shot arrives. Anchored a few
  // frames after the card starts; falls back ahead of the caption cue.
  const headlineAt = Math.max(cardAt + 4, captionAt - 18);

  // Apple shrink/zoom arrival (feedback_apple_screenshot_animation): the card
  // starts slightly LARGER + soft and settles to 1.0 with cubic ease-out (NO
  // overshoot), revealed behind a top-down clip mask. Opacity eases in alongside.
  const ARRIVE = 30;
  const tRaw = (frame - cardAt) / ARRIVE;
  const t = easeOutCubic(tRaw); // 0..1, clamped inside easeOutCubic
  const scale = 1.06 - 0.06 * t; // 1.06 -> 1.00 (shrink, no overshoot)
  const cardOpacity = interpolate(frame, [cardAt, cardAt + 14], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: EASE_OUT_QUART,
  });
  const maskReveal = interpolate(frame, [cardAt, cardAt + ARRIVE], [100, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: EASE_OUT_QUART,
  });

  const caption = appleRise(frame, captionAt, 18, 18);
  const headlineMotion = appleRise(frame, headlineAt, 22, 20);

  // The on-screen headline: a grounded value-prop line ABOUT what the screenshot
  // shows (filled by style_fill from the narrated VO beat). Distinct from `caption`
  // (the URL in the address bar) so there is no duplication. Empty -> nothing renders
  // and the layout is unchanged (backward-compatible with pre-headline props).
  const headline = (data.headline ?? "").trim();
  // The accent kicker over the headline reuses the act label when present, else a
  // neutral eyebrow; it only shows when a headline exists.
  const headlineKicker = headline ? actLabel(data.kicker) : "";

  // breath drift keeps the settled card alive (tiny, deterministic).
  const breath = breathDrift(frame, cardAt + ARRIVE + 6, 2.5, 110);

  const exitFade = interpolate(frame, [durationInFrames - 14, durationInFrames], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: EASE_OUT_QUART,
  });

  // browser address-bar text: the captured caption/url, trimmed to a host.
  const addr = (() => {
    const raw = data.caption ?? "";
    try {
      if (raw.startsWith("http")) return new URL(raw).host + new URL(raw).pathname.replace(/\/$/, "");
    } catch {
      /* fall through */
    }
    return raw;
  })();

  // Act badge: "NN — LABEL" in the top-left, accent color, tracked all-caps.
  // Fades in with the card arrival; -1 actIndex = bookend, skip.
  const badgeLabel = actIndex > 0 ? actLabel(data.kicker) : "";
  const badgeText = actIndex > 0 ? `${actNum(actIndex)}${badgeLabel ? ` — ${badgeLabel}` : ""}` : "";
  const badgeOpacity = actIndex > 0
    ? interpolate(frame, [cardAt, cardAt + 14], [0, 1], {
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
        easing: EASE_OUT_QUART,
      })
    : 0;

  return (
    <AbsoluteFill
      style={{
        backgroundColor: theme.bg,
        fontFamily: theme.fontDisplay,
        opacity: exitFade,
      }}
    >
      {/* soft brand mesh so the floating card has something to sit on */}
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
          gap: 28,
          transform: `translateY(${breath}px)`,
        }}
      >
        {/* Grounded value-prop headline ABOVE the card — the proof beat says WHAT the
            screenshot shows, not just an image. Only renders when style_fill filled a
            real headline (empty -> the layout collapses to the original card-only). */}
        {headline && (
          <div
            data-scene-id={sceneId}
            data-field="headline"
            style={{
              opacity: headlineMotion.opacity,
              transform: headlineMotion.transform,
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              gap: 12,
              maxWidth: 1180,
              textAlign: "center",
              marginBottom: 4,
            }}
          >
            {headlineKicker && (
              <div
                style={{
                  fontSize: 20,
                  fontWeight: 700,
                  letterSpacing: "0.18em",
                  textTransform: "uppercase",
                  color: theme.accent,
                  fontFamily: theme.fontMono,
                }}
              >
                {headlineKicker}
              </div>
            )}
            <div
              style={{
                fontSize: 46,
                lineHeight: 1.12,
                fontWeight: 600,
                letterSpacing: "-0.01em",
                color: theme.text,
                fontFamily: theme.fontDisplay,
              }}
            >
              {headline}
            </div>
          </div>
        )}

        {/* The browser card — brand-tinted chrome around the real screenshot. */}
        <div
          data-scene-id={sceneId}
          data-field="card"
          style={{
            opacity: cardOpacity,
            transform: `translate(${cardOffsetX}px, ${cardOffsetY}px) scale(${scale})`,
            transformOrigin: "center center",
            width: cardW,
            borderRadius: cardRadius,
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
          {/* mac browser chrome bar (brand-tinted), optional */}
          {showChrome && (
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
              {/* three traffic-light dots, tinted from the brand (NOT macOS rgb) */}
              <div style={{ display: "flex", gap: 9 }}>
                {[theme.navy, theme.accent, theme.navyBright].map((c, i) => (
                  <div
                    key={i}
                    style={{
                      width: 13,
                      height: 13,
                      borderRadius: "50%",
                      backgroundColor: c,
                      opacity: 0.85,
                    }}
                  />
                ))}
              </div>
              {/* address pill */}
              <div
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
          )}

          {/* the REAL screenshot, mask-revealed top-down as it arrives */}
          <div
            style={{
              position: "relative",
              width: "100%",
              // fixed 16:9-ish window so the card is a stable size; the PNG fills
              // it from the top (object-position top) so the hero/nav reads.
              height: shotH,
              overflow: "hidden",
              backgroundColor: theme.bgCard,
              clipPath: `inset(${maskReveal}% 0 0 0)`,
            }}
          >
            {src ? (
              <Img
                src={src}
                style={{
                  width: "100%",
                  height: "100%",
                  objectFit: "cover",
                  objectPosition: "top center",
                  display: "block",
                }}
              />
            ) : (
              // never-blank floor: a synth-ish placeholder if no image staged.
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
                {data.caption || theme.wordmark}
              </AbsoluteFill>
            )}
          </div>
        </div>

        {/* caption under the card — the captured URL (muted). Click-to-select via
            data-field="caption" so it stays addressable by the visual editor. */}
        {data.caption && (
          <div
            data-scene-id={sceneId}
            data-field="caption"
            style={{
              opacity: caption.opacity,
              transform: caption.transform,
              fontSize: 26,
              fontWeight: 500,
              letterSpacing: "0.02em",
              color: theme.textMuted,
              fontFamily: theme.fontMono,
            }}
          >
            {data.caption}
          </div>
        )}
      </AbsoluteFill>

      {/* Numbered act badge — top-left eyebrow: "NN — LABEL".
          Rendered LAST (highest z-order) so it paints over the mesh + card. */}
      {actIndex > 0 && (
        <div
          style={{
            position: "absolute",
            left: 60,
            top: 52,
            opacity: badgeOpacity,
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
