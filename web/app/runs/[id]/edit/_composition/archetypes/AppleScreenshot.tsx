// APPLE-SCREENSHOT archetype (v2) — a REAL captured website screenshot shown
// inside a brand-tinted browser card. Two layouts:
//
//   "split"    (the v2 default, spec §2): text-LEFT / screenshot-RIGHT. A tracked
//              eyebrow + a large 2-line kinetic headline (punch noun in accent) +
//              an optional supporting line sit in a left column; the screenshot is
//              a soft-shadow glass card inside an animated browser frame on the
//              right. The card enters with `frameRise`, the shot does a top-down
//              `card-deal-in` clip reveal, and the headline TIES to the UI it names
//              via an optional highlight-box over `data.focus`, a cursor moved via
//              `data.cursorPath`, and an optional `zoomPunch(data.zoomTo)`.
//   "centered" (the pre-overhaul path): centered headline ABOVE a centered card.
//
// BACKWARD COMPATIBILITY: when `data.layout`/`data.focus`/`data.cursorPath` are all
// ABSENT, this renders the original centered-card path BYTE-IDENTICAL — same DOM,
// same motion, same geometry (see `CenteredScreenshot`, lifted verbatim from the
// pre-overhaul archetype). `data.layout:"split"` opts into the new format.
//
// Mode-INDEPENDENT by construction: this renders the real captured PNG in BOTH
// mock + real builds (screenshots are $0 deterministic), so a mock Standard
// build still shows the real site in a clean white studio card — sidestepping
// the real-mode orange-overlay coupling for screenshots.
//
// Motion: Apple cubic-ease arrivals for the shot reveal (NO overshoot, per
// feedback_apple_screenshot_animation); the FRAME itself uses the Foundation's
// `frameRise` spring (the web analog of TapPay's phone-rise). Palette from
// props.theme so style-fill recolors the frame per brand.
import React from "react";
import { AbsoluteFill, Img, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import type { Cue, SceneData, Theme } from "../types";
import {
  appleRise,
  breathDrift,
  EASE_OUT_QUART,
  easeOutCubic,
  actNum,
  actLabel,
  alphaHex,
  frameRise,
  cursorAt,
  highlightBox,
  zoomPunch,
  monoFrames,
  type CursorKeyframe,
} from "../motion";

const cueAt = (cues: Cue[], label: string, fallback: number) =>
  cues.find((c) => c.label === label)?.at_frame ?? fallback;

// Trim a captured URL/caption down to a host + path for the address pill.
const toAddr = (raw: string): string => {
  try {
    if (raw.startsWith("http")) return new URL(raw).host + new URL(raw).pathname.replace(/\/$/, "");
  } catch {
    /* fall through */
  }
  return raw;
};

type ScreenshotProps = {
  data: SceneData;
  cues: Cue[];
  theme: Theme;
  durationInFrames: number;
  resolveSrc: (path: string) => string;
  actIndex?: number;
  sceneId?: string;
};

export const AppleScreenshot: React.FC<ScreenshotProps> = (props) => {
  // Layout selection. The v2 default is "split". Explicit "centered" (or — for
  // strict backward compatibility — an ABSENT layout WITH no split-only fields)
  // falls back to the original centered render so old props stay byte-identical.
  const { data } = props;
  const hasSplitData = data.focus != null || data.cursorPath != null || data.zoomTo != null || data.supporting != null;
  const layout = data.layout ?? (hasSplitData ? "split" : "centered");
  return layout === "split" ? <SplitScreenshot {...props} /> : <CenteredScreenshot {...props} />;
};

// ===========================================================================
// STATS CARD — the text-only motion-graphic case (no real screenshot).
// The `motion-graphic-stats` scene maps onto this archetype but has an EMPTY
// imageSrc; its content IS the headline + supporting stats. We render a clean,
// centered, animated stat card on the light stage (NO empty browser frame) so
// the credibility proof actually shows. Fixes the blank-stats regression the
// screenshot overlay-removal introduced.
// ===========================================================================
const StatsCard: React.FC<{
  data: SceneData;
  cues: Cue[];
  theme: Theme;
  durationInFrames: number;
  actIndex?: number;
  sceneId?: string;
}> = ({ data, theme, durationInFrames }) => {
  const frame = useCurrentFrame();
  const accent = (theme as { accent?: string }).accent ?? "#3B82F6";
  const headline = (data.headline ?? data.title ?? "").trim() || theme.wordmark || "";
  const support = (data.supporting ?? "").trim();
  const punch = ((data as { punchWord?: string }).punchWord ?? "").trim();

  const fadeIn = (at: number, d = 14) =>
    interpolate(frame, [at, at + d], [0, 1], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
      easing: EASE_OUT_QUART,
    });
  const riseIn = (at: number, d = 14, dist = 28) =>
    interpolate(frame, [at, at + d], [dist, 0], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
      easing: EASE_OUT_QUART,
    });
  const exit = interpolate(frame, [durationInFrames - 16, durationInFrames], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const headlineNodes = (() => {
    const i = punch ? headline.toLowerCase().indexOf(punch.toLowerCase()) : -1;
    if (i < 0) return <span style={{ color: "#0E1320" }}>{headline}</span>;
    return (
      <>
        <span style={{ color: "#0E1320" }}>{headline.slice(0, i)}</span>
        <span style={{ color: accent }}>{headline.slice(i, i + punch.length)}</span>
        <span style={{ color: "#0E1320" }}>{headline.slice(i + punch.length)}</span>
      </>
    );
  })();

  return (
    <AbsoluteFill
      style={{ alignItems: "center", justifyContent: "center", padding: 140, opacity: exit }}
    >
      <div style={{ textAlign: "center", maxWidth: 1500 }}>
        <div
          style={{
            opacity: fadeIn(10, 18),
            transform: `translateY(${riseIn(10, 18)}px)`,
            fontSize: 138,
            lineHeight: 1.02,
            fontWeight: 700,
            letterSpacing: -3,
          }}
        >
          {headlineNodes}
        </div>
        {support ? (
          <div
            style={{
              opacity: fadeIn(36),
              transform: `translateY(${riseIn(36)}px)`,
              color: "#5A6472",
              fontSize: 54,
              fontWeight: 500,
              marginTop: 40,
            }}
          >
            {support}
          </div>
        ) : null}
      </div>
    </AbsoluteFill>
  );
};

// ===========================================================================
// SPLIT layout (v2 keystone) — text-LEFT / screenshot-RIGHT.
// ===========================================================================
const SplitScreenshot: React.FC<ScreenshotProps> = ({
  data,
  cues,
  theme,
  durationInFrames,
  resolveSrc,
  actIndex = -1,
  sceneId,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const showChrome = (data.frame ?? "browser") !== "none";
  const src = data.imageSrc ? resolveSrc(data.imageSrc) : "";

  // HAS-A-REAL-SCREENSHOT signal. `data.imageSrc` is the staged capture path for a
  // real screenshot scene (e.g. "shot-<run>-screenshot-home.png"); style_fill leaves
  // it EMPTY ("") — or pops it entirely — for a text-only motion-graphic/stats scene
  // that maps onto this same `apple-screenshot` archetype (its content IS the headline
  // + supporting stats, not a captured image). The overlay-removal Dennis asked for
  // applies ONLY to the real-screenshot case (show the clean captured shot, no text).
  // For the text-only stats case the overlay is the WHOLE content, so we KEEP it and
  // render a clean centered motion-graphic stat card instead (no blank frame).
  const hasRealScreenshot = src.trim() !== "";
  if (!hasRealScreenshot) {
    return (
      <StatsCard
        data={data}
        cues={cues}
        theme={theme}
        durationInFrames={durationInFrames}
        actIndex={actIndex}
        sceneId={sceneId}
      />
    );
  }

  // Layout geometry. Left column is fixed-width, vertically centered; the card
  // floats right, inset from the right edge. All overridable via data.geo with a
  // literal fallback (absent geo => these literals).
  // Geometry. With the text overlay removed the card is CENTERED + enlarged so
  // the captured screenshot is the hero. cardW/shotH default up from the old
  // split sizes (1010x620) to a near-full-frame studio card (1620x820) that
  // still leaves a tasteful margin on the 1920x1080 stage. leftX/leftColW/
  // cardRight are retained (unused by the centered layout) so data.geo overrides
  // stay backward-compatible.
  const geo = data.geo;
  const leftX = geo?.leftX ?? 110;
  const leftColW = geo?.leftColW ?? 660;
  const cardW = geo?.cardW ?? 1620;
  const cardRadius = geo?.cardRadius ?? 18;
  const shotH = geo?.shotH ?? 820;
  const cardRight = geo?.cardRight ?? 64;
  const cardOffsetX = geo?.cardOffsetX ?? 0;
  const cardOffsetY = geo?.cardOffsetY ?? 0;

  // --- Cue timeline (all fall back to scene-length-scaled defaults so SHORT
  //     scenes still land every beat; mirrors HeroTitle's short-scene guard). ---
  const eyebrowAt = cueAt(cues, "eyebrow-in", Math.min(4, Math.round(durationInFrames * 0.04)));
  const headlineAt = cueAt(cues, "headline-in", Math.min(18, Math.round(durationInFrames * 0.12)));
  const frameAt = cueAt(cues, "frame-in", headlineAt + 6);
  const shotAt = cueAt(cues, "shot-in", frameAt + 12);
  // The punch / supporting / highlight / cursor all key off the shot landing.
  const supportingAt = cueAt(cues, "supporting-in", headlineAt + 30);
  const highlightAt = cueAt(cues, "highlight-in", shotAt + 18);
  const cursorAtCue = cueAt(cues, "cursor-go", highlightAt - 6);
  // Punch glow fires ~with the highlight so the accent word + the named UI light up together.
  const punchAt = Math.max(headlineAt + 14, highlightAt - 4);

  // ---- Left column: eyebrow + headline + underline + supporting -------------
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

  // Eyebrow text: "NN · LABEL" (act badge folded into the eyebrow, per spec). When
  // there is no act index, fall back to the kicker label alone.
  const eyebrowLabel = actLabel(data.kicker);
  const eyebrowText =
    actIndex > 0
      ? `${actNum(actIndex)}${eyebrowLabel ? ` · ${eyebrowLabel}` : ""}`
      : eyebrowLabel;

  // Headline split into lines with the punch noun isolated for the accent-pop.
  // Reuses the title text; never empty (falls back to wordmark like the bookends).
  const headlineText = (data.headline ?? data.title ?? "").trim() || theme.wordmark || "";
  const headlineLines = headlineText.includes("\n")
    ? headlineText.split("\n").map((l) => l.trim()).filter(Boolean).slice(0, 3)
    : splitHeadline(headlineText);

  // line-stagger: each line fades + rises, offset 16f.
  const LINE_STAGGER = geo?.lineStagger ?? 16;
  const LINE_DUR = 18;

  // accent-pop glow on the punch noun (HeroTitle.punchGlow shape): pops on punchAt,
  // soft tail pulse so the held word breathes.
  // SHORT-SCENE GUARD: the glow keyframes mix a cue-derived `punchAt` (+14/+40
  // pop+tail) with scene-length tail stops (`durationInFrames-18`, `durationInFrames`).
  // On a SHORT screenshot scene — a stripe.com proof beat narrated in ~2-3s lands
  // `durationInFrames` ≈ 60-100 — the third stop `punchAt+40` overtakes the fourth
  // `durationInFrames-18`, so the raw inputRange descends (e.g. [44,58,84,78,96]) and
  // interpolate() throws "inputRange must be strictly monotonically increasing",
  // crashing the Hermes render into the slow build_runner fallback. `monoFrames`
  // forces each stop > the previous (clamp to prev+1) so the range is GUARANTEED
  // strictly increasing. It is a NO-OP on the normal (long) scene where the stops
  // are already ascending, so the visual is byte-identical there.
  const punchGlow = interpolate(
    frame,
    monoFrames([punchAt, punchAt + 14, punchAt + 40, durationInFrames - 18, durationInFrames]),
    [0, 1, 0.6, 0.85, 0.5],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  // accent underline wipe (width 0 -> 120) under the headline.
  const underlineW = interpolate(frame, [punchAt, punchAt + 18], [0, 120], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: EASE_OUT_QUART,
  });

  const supporting = (data.supporting ?? "").trim();
  const supportingMotion = appleRise(frame, supportingAt, 18, 18);

  // ---- Right column: frame-rise + card-deal-in ------------------------------
  const rise = frameRise(frame, frameAt, fps);
  // card-deal-in: opacity over 14f + top-down clip reveal over 30f (appendix vals).
  const ARRIVE = 30;
  const shotOpacity = interpolate(frame, [shotAt, shotAt + 14], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: EASE_OUT_QUART,
  });
  const maskReveal = interpolate(frame, [shotAt, shotAt + ARRIVE], [100, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: EASE_OUT_QUART,
  });
  // shot settle scale 1.06 -> 1.00 (cubic, no overshoot) — matches centered path.
  const shotScale = 1.06 - 0.06 * easeOutCubic((frame - shotAt) / ARRIVE);

  // breath drift on the settled card so held frames never freeze.
  const breath = breathDrift(frame, shotAt + ARRIVE + 6, 2.5, 110);

  // exit fade (whole scene).
  const exitFade = interpolate(frame, [durationInFrames - 14, durationInFrames], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: EASE_OUT_QUART,
  });

  // ---- Tie mechanism: highlight-box / cursor / zoom-punch (all OPTIONAL) -----
  // The screenshot viewport (the inner window the PNG fills) is the coordinate box
  // for the focus rect + cursor + zoom. Card-local NORMALIZED 0..1 (spec contract).
  const shotW = cardW; // the window is full card width
  const focus = data.focus;
  // OVERLAY-REMOVAL (Dennis): the clean captured screenshot is the hero — do NOT draw
  // a synthetic highlight ring/tint over it. (focus stays referenced for layout/zoom math.)
  const SHOW_FOCUS_RING = false;
  // highlight holds from highlightAt until ~the end of the held tail, then fades.
  const highlightHoldEnd = Math.max(highlightAt + 24, durationInFrames - 28);
  const hl = focus ? highlightBox(frame, highlightAt, highlightHoldEnd) : { opacity: 0 };

  // zoom-punch pushes the shot CONTENT toward the focus point (transformOrigin 0 0).
  const zoomTarget = data.zoomTo ?? (focus ? { x: focus.x + focus.w / 2, y: focus.y + focus.h / 2, scale: 1.14 } : null);
  const zoom = zoomTarget
    ? zoomPunch(
        frame,
        highlightAt,
        { x: zoomTarget.x, y: zoomTarget.y },
        zoomTarget.scale,
        { dur: 24, holdEnd: highlightHoldEnd, boxW: shotW, boxH: shotH }
      )
    : { transform: "translate(0px,0px) scale(1)", scale: 1, p: 0 };

  // #6 SLOW KEN-BURNS (2026-07-02): mirror of the studio archetype — a plain homepage
  // shot (no focus / zoom-punch) freezes after the settle; a gentle continuous push
  // (1.0 -> 1.045 from settle to scene end) keeps the long hold alive. Skipped when a
  // zoom-punch is active. Keep in sync with studio/src/timeline/archetypes/AppleScreenshot.tsx.
  const kenBurns = zoomTarget
    ? 1
    : interpolate(frame, [shotAt + ARRIVE, durationInFrames], [1, 1.045], {
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
        easing: EASE_OUT_QUART,
      });

  // cursor path (card-local normalized -> px in the shot window). Default: travel
  // to the focus center and click, if a focus exists and no explicit path given.
  const cursorPath: CursorKeyframe[] | null =
    data.cursorPath != null
      ? data.cursorPath
      : focus
      ? [
          { at: 0, x: 0.12, y: 0.85 },
          { at: cursorAtCue - frameAt, x: focus.x + focus.w / 2, y: focus.y + focus.h / 2, click: true },
        ]
      : null;
  // CURSOR DISABLED on screenshot scenes (user explicitly disliked the moving
  // cursor + click ripples). Force `cursor` to null so the guarded render block
  // below ({cursor && ...}) never draws CursorGlyph or the ripples. The cursorPath
  // computation above is left intact (harmless, no render) so re-enabling is a
  // one-line revert. WalkthroughPlayer keeps its own cursor — unaffected.
  // Typed as the union (not the literal `null`) so the dead `{cursor && ...}`
  // render block below still type-checks against the cursor shape. Using a const
  // initialized to `null` would narrow `cursor` to `never` inside the guard.
  const cursorEnabled = false;
  const cursor: ReturnType<typeof cursorAt> | null = cursorEnabled
    ? cursorAt(frame, cursorPath ?? [], fps)
    : null;
  void cursorPath; // intentionally unused now that the cursor is disabled

  // TEXT OVERLAY DISABLED (user request): the eyebrow/headline/underline/supporting
  // bindings below are computed but no longer rendered (the left column was removed).
  // Reference them so they stay valid + lint-clean; a one-line revert re-renders them.
  void [eyebrowOpacity, eyebrowY, eyebrowText, headlineLines, LINE_STAGGER, LINE_DUR,
    punchGlow, underlineW, supporting, supportingMotion, leftX, leftColW, cardRight];

  const addr = toAddr(data.caption ?? "");

  return (
    <AbsoluteFill style={{ backgroundColor: theme.bg, fontFamily: theme.fontDisplay, opacity: exitFade }}>
      {/* soft brand mesh — drifting blooms so the near-white page breathes. */}
      <AbsoluteFill
        style={{
          background: `
            radial-gradient(ellipse 1100px 780px at ${22 + breath * 0.4}% 24%, ${theme.navy}1c 0%, transparent 60%),
            radial-gradient(ellipse 1000px 760px at ${80 - breath * 0.4}% 82%, ${theme.accent}18 0%, transparent 60%),
            ${theme.bg}
          `,
        }}
      />

      {/* TEXT OVERLAY REMOVED (user request): the eyebrow + kinetic headline +
          underline + supporting LEFT COLUMN that used to sit beside the screenshot
          is gone. The captured screenshot now fills the frame as the hero. The
          eyebrow/headline/underline/supporting motion values above are left intact
          (harmless, no render) so re-enabling is a localized revert; `void` below
          silences unused-binding lint without deleting the computations. */}

      {/* CENTERED browser card — the screenshot is now the sole subject and is
          centered + enlarged to read prominently without the text panel. The card
          still frame-rises (spring up + scale + tilt-settle); the shot inside does
          card-deal-in. */}
      <div
        style={{
          position: "absolute",
          left: "50%",
          top: "50%",
          transform: `translate(calc(-50% + ${cardOffsetX}px), calc(-50% + ${breath + cardOffsetY}px))`,
        }}
      >
        <div
          data-scene-id={sceneId}
          data-field="card"
          style={{
            opacity: rise.opacity,
            transform: rise.transform,
            transformOrigin: "center center",
            width: cardW,
            borderRadius: cardRadius,
            overflow: "hidden",
            backgroundColor: theme.bgCardRaised,
            border: `1px solid ${theme.border}`,
            boxShadow: [
              "0 48px 130px rgba(15,35,56,0.24)",
              "0 10px 30px rgba(15,35,56,0.13)",
              "inset 0 1px 0 rgba(255,255,255,0.9)",
            ].join(", "),
          }}
        >
          {showChrome && <BrowserChrome theme={theme} addr={addr} />}

          {/* the screenshot window — the coordinate box for highlight/cursor/zoom. */}
          <div
            style={{
              position: "relative",
              width: "100%",
              height: shotH,
              overflow: "hidden",
              backgroundColor: theme.bgCard,
              clipPath: `inset(${maskReveal}% 0 0 0)`,
            }}
          >
            {/* zoomable content layer (PNG + highlight + cursor move together so the
                named element stays under the highlight as the camera pushes in). */}
            <div
              style={{
                position: "absolute",
                inset: 0,
                opacity: shotOpacity,
                transform: `${zoom.transform} scale(${shotScale * kenBurns})`,
                transformOrigin: "0 0",
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

              {/* highlight-box over data.focus (card-local % of the shot window).
                  A clean accent ring + faint tint — NO text caption. The headline
                  in the left column already NAMES the element; the ring just points
                  at it (spec §2 "a rounded accent ring + tint draws ON over a named
                  UI rect"). `focus.label` is the captured DOM text used only to PICK
                  the rect upstream in style_fill (_focus_for_headline) — it is debug
                  metadata and must never render on the shot (R2: it was being plastered
                  over the screenshot as an ugly monospace caption, the coherence killer). */}
              {SHOW_FOCUS_RING && focus && hl.opacity > 0.001 && (
                <div
                  style={{
                    position: "absolute",
                    left: `${focus.x * 100}%`,
                    top: `${focus.y * 100}%`,
                    width: `${focus.w * 100}%`,
                    height: `${focus.h * 100}%`,
                    borderRadius: 12,
                    border: `3px solid ${theme.accent}`,
                    backgroundColor: `${theme.accent}1f`,
                    boxShadow: `0 0 0 6px ${theme.accent}22, 0 0 28px ${theme.accent}55`,
                    opacity: hl.opacity,
                  }}
                />
              )}

              {/* cursor + click ripples (card-local px inside the shot window) */}
              {cursor && (
                <>
                  {cursor.ripples.map((rp, i) => (
                    <div
                      key={`rip-${i}`}
                      style={{
                        position: "absolute",
                        left: rp.x,
                        top: rp.y,
                        width: rp.r * 2,
                        height: rp.r * 2,
                        marginLeft: -rp.r,
                        marginTop: -rp.r,
                        borderRadius: "50%",
                        border: `2px solid ${theme.accent}`,
                        opacity: rp.opacity,
                      }}
                    />
                  ))}
                  <CursorGlyph x={cursor.x} y={cursor.y} color={theme.text} />
                </>
              )}
            </div>
          </div>
        </div>
      </div>
    </AbsoluteFill>
  );
};

// A minimal arrow cursor glyph (card-local px coords). SVG, no emoji.
const CursorGlyph: React.FC<{ x: number; y: number; color: string }> = ({ x, y, color }) => (
  <svg
    width={28}
    height={28}
    viewBox="0 0 28 28"
    style={{ position: "absolute", left: x, top: y, filter: "drop-shadow(0 2px 4px rgba(0,0,0,0.35))" }}
  >
    <path d="M3 2 L3 22 L9 16 L13 25 L17 23 L13 14 L21 14 Z" fill="#ffffff" stroke={color} strokeWidth={1.4} />
  </svg>
);

// Shared mac browser chrome bar (brand-tinted dots + address pill). Used by both
// layouts so the frame is visually identical regardless of axis.
const BrowserChrome: React.FC<{ theme: Theme; addr: string }> = ({ theme, addr }) => (
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
        <div key={i} style={{ width: 13, height: 13, borderRadius: "50%", backgroundColor: c, opacity: 0.85 }} />
      ))}
    </div>
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
);

// Split a headline into display lines balanced near the midpoint (the split layout
// wants a tall multi-line block, distinct from the body splitToLines heuristic).
// ROBUSTNESS: at 76px in the ~660px left column a line holds ~HEADLINE_MAX_CHARS.
// style_fill clamps the screenshot headline to ~38 chars upstream, but a DENSE
// planner can author a longer explicit data.headline; cap each line and overflow to
// a 3rd line (never beyond) so a long headline NEVER spills out of the column.
const HEADLINE_MAX_CHARS = 18;
const splitHeadline = (text: string): string[] => {
  const t = (text ?? "").trim();
  if (!t) return [];
  const words = t.split(/\s+/);
  if (words.length <= 1) return [t];
  // Greedy word-wrap into lines of <= HEADLINE_MAX_CHARS, then BALANCE: aim for 2
  // lines when it fits, allow a 3rd, hard-cap at 3 (the layout's vertical budget).
  // First try the original midpoint 2-way split; keep it only if both lines fit.
  const half = t.length / 2;
  let acc = 0;
  let splitAt = Math.floor(words.length / 2);
  for (let i = 0; i < words.length - 1; i++) {
    acc += words[i].length + 1;
    if (acc >= half) { splitAt = i + 1; break; }
  }
  const a = words.slice(0, splitAt).join(" ");
  const b = words.slice(splitAt).join(" ");
  if (a.length <= HEADLINE_MAX_CHARS && b.length <= HEADLINE_MAX_CHARS) return [a, b];
  // A line overflows — greedy-wrap the whole headline so no line exceeds the cap.
  const lines: string[] = [];
  let cur = "";
  for (const w of words) {
    const next = cur ? cur + " " + w : w;
    if (next.length > HEADLINE_MAX_CHARS && cur) {
      lines.push(cur);
      cur = w;
    } else {
      cur = next;
    }
  }
  if (cur) lines.push(cur);
  // Hard-cap at 3 lines: fold any overflow into the 3rd so it never spills the box.
  if (lines.length > 3) {
    return [lines[0], lines[1], lines.slice(2).join(" ")];
  }
  return lines;
};

// Split a line around its punch word so the punch word can be accent-colored.
const splitPunch = (line: string, punch?: string) => {
  if (!punch || !line.includes(punch)) return { pre: line, hit: "", post: "" };
  const i = line.indexOf(punch);
  return { pre: line.slice(0, i), hit: punch, post: line.slice(i + punch.length) };
};

// ===========================================================================
// CENTERED layout — lifted VERBATIM from the pre-overhaul archetype so old props
// (no layout / focus / cursorPath / supporting) render BYTE-IDENTICAL.
// ===========================================================================
const CenteredScreenshot: React.FC<ScreenshotProps> = ({
  data,
  cues,
  theme,
  durationInFrames,
  resolveSrc,
  actIndex = -1,
  sceneId,
}) => {
  const frame = useCurrentFrame();

  const showChrome = (data.frame ?? "browser") !== "none";
  const src = data.imageSrc ? resolveSrc(data.imageSrc) : "";

  const geo = data.geo;
  const cardW = geo?.cardW ?? 1380;
  const cardRadius = geo?.cardRadius ?? 18;
  const shotH = geo?.shotH ?? 712;
  const cardOffsetX = geo?.cardOffsetX ?? 0;
  const cardOffsetY = geo?.cardOffsetY ?? 0;

  const cardAt = cueAt(cues, "card-in", 8);
  const captionAt = cueAt(cues, "caption-in", cardAt + 30);
  const headlineAt = Math.max(cardAt + 4, captionAt - 18);

  const ARRIVE = 30;
  const tRaw = (frame - cardAt) / ARRIVE;
  const t = easeOutCubic(tRaw);
  const scale = 1.06 - 0.06 * t;
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

  const headline = (data.headline ?? "").trim();
  const headlineKicker = headline ? actLabel(data.kicker) : "";

  const breath = breathDrift(frame, cardAt + ARRIVE + 6, 2.5, 110);

  const exitFade = interpolate(frame, [durationInFrames - 14, durationInFrames], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: EASE_OUT_QUART,
  });

  const addr = toAddr(data.caption ?? "");

  const badgeLabel = actIndex > 0 ? actLabel(data.kicker) : "";
  const badgeText = actIndex > 0 ? `${actNum(actIndex)}${badgeLabel ? ` — ${badgeLabel}` : ""}` : "";
  const badgeOpacity =
    actIndex > 0
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
          {showChrome && <BrowserChrome theme={theme} addr={addr} />}

          <div
            style={{
              position: "relative",
              width: "100%",
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
                  // R5 (Shopify bug #3) — anchor TOP-LEFT, not top-center. A wide
                  // capture under objectFit:cover that is wider than the card window
                  // gets cropped left+right equally with "top center", clipping the
                  // left-edge wordmark/first nav column (the brand-truth miss). Browser
                  // captures always put the logo + primary nav at the top-LEFT, so
                  // anchoring there keeps the brand mark in frame and crops the (usually
                  // emptier) right margin instead.
                  objectPosition: "top left",
                  display: "block",
                }}
              />
            ) : (
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
