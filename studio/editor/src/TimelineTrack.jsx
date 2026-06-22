// The iMovie-style bottom TIMELINE: a horizontal track of the video's scenes as
// CLIP blocks. Each clip's width is proportional to its duration. Click a clip to
// select it (drives the inspector + seeks the Player to its in_frame). A live
// playhead tracks the Player's current frame, and a subtle time ruler runs above.
//
// Premium / Hera: heavily rounded clips, soft shadows, accent ring + glow on the
// selected clip, smooth hover lift. NO emojis — archetype glyphs are SVG.
import React, { useMemo } from "react";
import { Thumbnail } from "@remotion/player";
import { Timeline as TimelineComp } from "../../src/timeline/Timeline";
import { Icon } from "./ui.jsx";

const PRETTY = (a) => (a || "scene").replace(/-/g, " ");

// A small SVG glyph per archetype family so each clip reads at a glance.
function ClipGlyph({ archetype }) {
  const a = archetype || "";
  if (a.includes("screenshot") || a.includes("walkthrough") || a.includes("player"))
    return <Icon.film style={{ width: 13, height: 13 }} />;
  if (a.includes("hero") || a.includes("title") || a.includes("statement"))
    return <Icon.type style={{ width: 13, height: 13 }} />;
  if (a.includes("card") || a.includes("entit") || a.includes("list"))
    return <Icon.list style={{ width: 13, height: 13 }} />;
  return <Icon.film style={{ width: 13, height: 13 }} />;
}

// Format a frame count as m:ss (for the ruler ticks).
const fmtTime = (frame, fps) => {
  const s = frame / fps;
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${String(sec).padStart(2, "0")}`;
};

const sceneLabel = (s) =>
  (
    s.data?.title ||
    s.data?.statement ||
    s.data?.overlayTitle ||
    s.data?.heading ||
    s.data?.caption ||
    PRETTY(s.archetype)
  ).slice(0, 48);

export function TimelineTrack({ props, activeIdx, onSelect, currentFrame, total, fps }) {
  const scenes = props?.scenes || [];
  const inputProps = useMemo(() => props || {}, [props]);

  // The track maps frame-space -> px using flex (the container is full-width); we
  // give each clip a flex-basis proportional to its duration so widths sum to 100%.
  // To position the live playhead and render absolute clips we need pixel math, so
  // we measure the track and lay clips out in a relative coordinate system using %.
  const totalDur = Math.max(1, total || 1);

  // Ruler ticks: ~6 evenly spaced markers across the whole duration.
  const ticks = useMemo(() => {
    const n = 6;
    const out = [];
    for (let i = 0; i <= n; i++) out.push((totalDur / n) * i);
    return out;
  }, [totalDur]);

  const playheadPct = Math.max(0, Math.min(100, (currentFrame / totalDur) * 100));

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8, width: "100%" }}>
      {/* ---- time ruler ---- */}
      <div style={{ position: "relative", height: 16, marginLeft: 2, marginRight: 2 }}>
        {ticks.map((f, i) => {
          const pct = (f / totalDur) * 100;
          return (
            <div
              key={i}
              style={{
                position: "absolute",
                left: `${pct}%`,
                top: 0,
                transform: i === 0 ? "none" : i === ticks.length - 1 ? "translateX(-100%)" : "translateX(-50%)",
                display: "flex",
                flexDirection: "column",
                alignItems: i === 0 ? "flex-start" : i === ticks.length - 1 ? "flex-end" : "center",
              }}
            >
              <span
                style={{
                  fontSize: 9.5,
                  fontFamily: "var(--code)",
                  color: "var(--dim)",
                  fontVariantNumeric: "tabular-nums",
                  letterSpacing: 0.2,
                }}
              >
                {fmtTime(f, fps)}
              </span>
            </div>
          );
        })}
      </div>

      {/* ---- the clip track: an off-white recessed well (part of the light
             chrome), framed by a hairline with a faint inset so it reads as a
             track the white clip cards sit inside ---- */}
      <div
        style={{
          position: "relative",
          height: 78,
          borderRadius: 13,
          background: "var(--rail)",
          border: "1px solid var(--line)",
          boxShadow: "inset 0 1px 0 rgba(255,255,255,.6), inset 0 2px 8px -6px rgba(20,23,28,.10)",
          padding: 6,
        }}
      >
        <div style={{ position: "relative", width: "100%", height: "100%" }}>
          {/* clips laid out by % of total duration (resolved to px via a ref-free %) */}
          {scenes.map((s, i) => {
            const start = s.in_frame || 0;
            const dur = Math.max(1, (s.out_frame || 0) - start);
            const xPct = (start / totalDur) * 100;
            const wPct = (dur / totalDur) * 100;
            return (
              <PctClip
                key={s.id || i}
                xPct={xPct}
                wPct={wPct}
                scene={s}
                idx={i}
                active={i === activeIdx}
                fps={fps}
                total={totalDur}
                inputProps={inputProps}
                onSelect={onSelect}
              />
            );
          })}

          {/* ---- live playhead ---- */}
          <div
            style={{
              position: "absolute",
              left: `${playheadPct}%`,
              top: -7,
              bottom: -7,
              width: 2,
              background: "var(--accent)",
              boxShadow: "0 0 10px 1px var(--accent-glow-strong)",
              pointerEvents: "none",
              zIndex: 6,
              borderRadius: 2,
            }}
          >
            <span
              style={{
                position: "absolute",
                top: -4,
                left: "50%",
                transform: "translateX(-50%)",
                width: 10,
                height: 10,
                borderRadius: "50%",
                background: "var(--accent)",
                boxShadow: "0 0 8px 1px var(--accent-glow-strong)",
              }}
            />
          </div>
        </div>
      </div>
    </div>
  );
}

// A clip positioned by percentage of the track width (so it scales with the
// container). It re-uses the absolute <Clip> renderer by translating % into a
// nested 100%-relative box.
function PctClip({ xPct, wPct, scene, idx, active, fps, total, inputProps, onSelect }) {
  const [hover, setHover] = React.useState(false);
  const dur = Math.max(0, (scene.out_frame || 0) - (scene.in_frame || 0));
  const wide = wPct > 10; // heuristics on % since we don't measure px
  const showThumb = wPct > 7;
  const showMeta = wPct > 13;
  // Clips with a thumbnail get a dark scrim over imagery → light text rides on it.
  // Narrow placeholder clips are light cards on the off-white well → dark ink reads.
  const onDark = showThumb;

  return (
    <button
      onClick={() => onSelect(idx)}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      title={sceneLabel(scene)}
      style={{
        position: "absolute",
        left: `calc(${xPct}% + 3px)`,
        top: 0,
        width: `calc(${wPct}% - 6px)`,
        height: "100%",
        padding: 0,
        border: "none",
        background: "transparent",
        cursor: "pointer",
        textAlign: "left",
        transition: "transform .18s var(--ease)",
        transform: hover && !active ? "translateY(-2px)" : "none",
        zIndex: active ? 3 : hover ? 2 : 1,
      }}
    >
      <div
        style={{
          position: "relative",
          width: "100%",
          height: "100%",
          borderRadius: 13,
          overflow: "hidden",
          background: "var(--clip)",
          border: "1px solid " + (active ? "var(--accent-line)" : hover ? "var(--line-2)" : "var(--line)"),
          boxShadow: active
            ? "0 0 0 1px var(--accent-line), 0 6px 16px rgba(214,53,28,.20)"
            : hover
            ? "0 2px 6px rgba(20,23,28,.08), 0 14px 30px rgba(20,23,28,.10)"
            : "0 1px 2px rgba(20,23,28,.05), 0 6px 16px rgba(20,23,28,.07)",
          transition: "box-shadow .18s var(--ease), border-color .18s var(--ease), background .18s var(--ease)",
        }}
      >
        {showThumb ? (
          <div style={{ position: "absolute", inset: 0, overflow: "hidden", background: "#000" }}>
            <Thumbnail
              component={TimelineComp}
              inputProps={inputProps}
              durationInFrames={Math.max(1, total)}
              frameToDisplay={Math.min(total - 1, (scene.in_frame || 0) + 3)}
              fps={fps}
              compositionWidth={1920}
              compositionHeight={1080}
              style={{ width: "100%", height: "100%", objectFit: "cover" }}
              acknowledgeRemotionLicense
            />
          </div>
        ) : (
          <div
            style={{
              position: "absolute",
              inset: 0,
              background: active
                ? "linear-gradient(160deg, var(--accent-tint-2), var(--accent-tint))"
                : "linear-gradient(160deg, var(--clip-2), var(--clip))",
            }}
          />
        )}

        {/* gradient scrim for legibility — only over thumbnail imagery, so the
            footer labels read as light text on the darkened bottom edge */}
        {showThumb ? (
          <div
            style={{
              position: "absolute",
              inset: 0,
              background:
                "linear-gradient(180deg, rgba(8,10,17,.05) 35%, rgba(8,10,17,.5) 72%, rgba(8,10,17,.9) 100%)",
              pointerEvents: "none",
            }}
          />
        ) : null}

        {/* index chip */}
        <span
          style={{
            position: "absolute",
            top: 6,
            left: 6,
            fontSize: 9.5,
            fontWeight: 800,
            color: active ? "var(--accent-ink)" : onDark ? "#cfd8e6" : "var(--muted)",
            background: active ? "var(--accent)" : onDark ? "rgba(10,13,23,.72)" : "var(--bg-2)",
            backdropFilter: "blur(6px)",
            WebkitBackdropFilter: "blur(6px)",
            border: "1px solid " + (active ? "transparent" : onDark ? "rgba(255,255,255,.12)" : "var(--line)"),
            borderRadius: 7,
            padding: "1px 5.5px",
            fontVariantNumeric: "tabular-nums",
            letterSpacing: 0.3,
            zIndex: 2,
          }}
        >
          {String(idx + 1).padStart(2, "0")}
        </span>

        {/* label footer */}
        <div
          style={{
            position: "absolute",
            left: 0,
            right: 0,
            bottom: 0,
            padding: wide ? "6px 8px 7px" : "5px 6px",
            display: "flex",
            flexDirection: "column",
            gap: 2,
            minWidth: 0,
            zIndex: 2,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 5, minWidth: 0 }}>
            <span style={{ color: active ? "var(--accent)" : onDark ? "#aeb8ca" : "var(--muted)", flex: "0 0 auto", display: "flex" }}>
              <ClipGlyph archetype={scene.archetype} />
            </span>
            <span
              style={{
                fontSize: 11,
                fontWeight: 600,
                color: onDark ? (active ? "#fff" : "#dde3ee") : active ? "var(--accent-deep)" : "var(--text)",
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
                minWidth: 0,
                textShadow: onDark ? "0 1px 3px rgba(0,0,0,.7)" : "none",
              }}
            >
              {showMeta ? sceneLabel(scene) : PRETTY(scene.archetype)}
            </span>
          </div>
          {showMeta ? (
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 7,
                fontSize: 9,
                fontFamily: "var(--code)",
                color: onDark ? (active ? "var(--accent-soft)" : "#9aa6b8") : active ? "var(--accent)" : "var(--dim)",
                letterSpacing: 0.2,
                textShadow: onDark ? "0 1px 2px rgba(0,0,0,.7)" : "none",
              }}
            >
              <span style={{ textTransform: "uppercase" }}>{PRETTY(scene.archetype)}</span>
              <span style={{ fontVariantNumeric: "tabular-nums" }}>{dur}f</span>
            </div>
          ) : null}
        </div>
      </div>
    </button>
  );
}
