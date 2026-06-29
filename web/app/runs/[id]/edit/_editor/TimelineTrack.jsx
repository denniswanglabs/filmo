// The iMovie-style bottom TIMELINE: a horizontal track of the video's scenes as
// CLIP blocks. Each clip's width is proportional to its duration. Click a clip to
// select it (drives the inspector + seeks the Player to its in_frame). A live
// playhead tracks the Player's current frame, and a subtle time ruler runs above.
//
// Premium / Hera: heavily rounded clips, soft shadows, accent ring + glow on the
// selected clip, smooth hover lift. The blocks are solid blue with a centered
// "Scene N" label — they deliberately do NOT render scene screenshots.
"use client";
import React, { useCallback, useMemo, useRef } from "react";

const clampN = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

const PRETTY = (a) => (a || "scene").replace(/-/g, " ");

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

export function TimelineTrack({ props, activeIdx, onSelect, onSeek, currentFrame, total, fps }) {
  const scenes = props?.scenes || [];

  // The inner clip-coordinate box (the `position:relative` div the clips + playhead
  // are laid out inside). We measure it so a pointer X anywhere on the track maps to
  // a frame. Click-anywhere jumps the playhead; press-and-drag scrubs live.
  const laneRef = useRef(null);
  const draggingRef = useRef(false);

  const totalDurForSeek = Math.max(1, total || 1);
  const frameFromClientX = useCallback(
    (clientX) => {
      const lane = laneRef.current;
      if (!lane) return null;
      const r = lane.getBoundingClientRect();
      if (r.width <= 0) return null;
      const ratio = clampN((clientX - r.left) / r.width, 0, 1);
      return clampN(Math.round(ratio * (totalDurForSeek - 1)), 0, totalDurForSeek - 1);
    },
    [totalDurForSeek]
  );

  // Arm a live scrub: seek to the pointer's frame now, then bind window-level
  // pointermove/up so the drag keeps scrubbing even as the pointer leaves the track
  // or crosses clips/handles. Shared by BOTH entry points — pressing the track
  // background AND grabbing the playhead knob — so they scrub identically.
  const startScrub = useCallback(
    (e) => {
      if (!onSeek) return;
      // Only the primary (left) button starts a scrub.
      if (e.button != null && e.button !== 0) return;
      const f = frameFromClientX(e.clientX);
      if (f == null) return;
      e.preventDefault();
      // Keep receiving moves even if the finger/cursor slips off the tiny handle.
      try {
        e.currentTarget.setPointerCapture?.(e.pointerId);
      } catch {}
      draggingRef.current = true;
      onSeek(f);
      const onMove = (ev) => {
        if (!draggingRef.current) return;
        const nf = frameFromClientX(ev.clientX);
        if (nf != null) onSeek(nf);
      };
      const onUp = () => {
        draggingRef.current = false;
        window.removeEventListener("pointermove", onMove, true);
        window.removeEventListener("pointerup", onUp, true);
      };
      window.addEventListener("pointermove", onMove, true);
      window.addEventListener("pointerup", onUp, true);
    },
    [onSeek, frameFromClientX]
  );

  // Press on the track background → start a scrub. (Clip buttons stop their own
  // pointerdown from reaching here, so clicking a clip still selects its scene
  // rather than starting a scrub.)
  const onTrackPointerDown = startScrub;
  // Grabbing the playhead knob → start the SAME scrub. stopPropagation so the press
  // doesn't ALSO fire the track-background handler (it would be redundant, but keep
  // a single drag session). The knob seeks-to-cursor on grab like the track does;
  // since the knob already sits at the playhead, that's a no-op jump, then drag.
  const onPlayheadPointerDown = useCallback(
    (e) => {
      e.stopPropagation();
      startScrub(e);
    },
    [startScrub]
  );

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
        <div
          ref={laneRef}
          className="ws-timeline-lane"
          onPointerDown={onTrackPointerDown}
          style={{ position: "relative", width: "100%", height: "100%", cursor: onSeek ? "ew-resize" : "default" }}
        >
          {/* transparent seek surface — fills the whole lane BEHIND the clips so a
              press anywhere on the track (incl. the gaps between/around clips) maps
              to a frame. Clips sit at z-index >= 1 and intercept their own clicks to
              SELECT a scene; this surface (z-index 0) only catches background presses
              and the window listeners handle dragging across the clips. */}
          <div style={{ position: "absolute", inset: 0, zIndex: 0 }} aria-hidden="true" />

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
                onSelect={onSelect}
              />
            );
          })}

          {/* ---- live playhead + GRABBABLE knob ----
                 The vertical line stays pointer-transparent (so it never blocks a
                 click meant for a clip beneath it); the KNOB at its top is a real
                 grab target (pointerEvents:auto, cursor:ew-resize) that starts a
                 live scrub on pointerdown via onPlayheadPointerDown. */}
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
            {/* The grab handle: a rounded knob with a downward nub that reads as a
                draggable playhead head. Sits above the track, hangs over the line. */}
            <div
              onPointerDown={onSeek ? onPlayheadPointerDown : undefined}
              title="Drag to scrub"
              role="slider"
              aria-label="Scrub playhead"
              aria-valuemin={0}
              aria-valuemax={totalDur}
              aria-valuenow={Math.round(currentFrame)}
              style={{
                position: "absolute",
                top: -13,
                left: "50%",
                transform: "translateX(-50%)",
                width: 18,
                height: 18,
                borderRadius: "50%",
                background: "var(--accent)",
                border: "2px solid #fff",
                boxShadow: "0 1px 3px rgba(20,23,28,.30), 0 0 10px 1px var(--accent-glow-strong)",
                cursor: onSeek ? "ew-resize" : "default",
                pointerEvents: onSeek ? "auto" : "none",
                // touch-action:none so a finger drag scrubs instead of scrolling the page.
                touchAction: "none",
                zIndex: 1,
              }}
            >
              {/* a tiny triangle nub pointing down into the track, so the knob
                  reads as a playhead head rather than a stray dot */}
              <span
                style={{
                  position: "absolute",
                  bottom: -4,
                  left: "50%",
                  transform: "translateX(-50%) rotate(45deg)",
                  width: 7,
                  height: 7,
                  background: "var(--accent)",
                  borderRight: "2px solid #fff",
                  borderBottom: "2px solid #fff",
                  pointerEvents: "none",
                }}
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// A clip positioned by percentage of the track width (so it scales with the
// container). Per the editor spec, the timeline blocks are SOLID BLUE cards with
// a centered "Scene N" label — they deliberately do NOT render the scene's
// screenshot/thumbnail. The blue pops against the neutral-white editor chrome and
// keeps the timeline reading as an at-a-glance scene order. Selection (accent ring
// + lift) and hover behavior are preserved.
//
// Blue scale for the blocks (kept self-contained here so it stays blue even after
// the surrounding chrome was neutralized to the landing palette):
const CLIP_BLUE = "#3B82F6";        // base block fill (Filmo blue)
const CLIP_BLUE_DEEP = "#2563EB";   // gradient bottom / active block
const CLIP_BLUE_SOFT = "#60A5FA";   // gradient top on the active/hover block

function PctClip({ xPct, wPct, scene, idx, active, onSelect }) {
  const [hover, setHover] = React.useState(false);
  const wide = wPct > 9; // enough room for the longer "Scene NN" label form

  return (
    <button
      onClick={() => onSelect(idx)}
      // Swallow pointerdown so pressing a clip SELECTS the scene (via onClick) instead
      // of starting a timeline scrub on the seek surface behind it.
      onPointerDown={(e) => e.stopPropagation()}
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
          // SOLID BLUE block. Active/hover lift to the brighter blue; resting
          // blocks sit a touch deeper so the selected one reads as "lit".
          background:
            active || hover
              ? `linear-gradient(160deg, ${CLIP_BLUE_SOFT}, ${CLIP_BLUE})`
              : `linear-gradient(160deg, ${CLIP_BLUE}, ${CLIP_BLUE_DEEP})`,
          border: "1px solid " + (active ? "rgba(255,255,255,.9)" : "rgba(255,255,255,.18)"),
          boxShadow: active
            ? `0 0 0 2px ${CLIP_BLUE_DEEP}, 0 6px 16px rgba(59,130,246,.35)`
            : hover
            ? "0 2px 6px rgba(20,23,28,.10), 0 14px 30px rgba(30,58,120,.18)"
            : "0 1px 2px rgba(20,23,28,.06), 0 6px 16px rgba(30,58,120,.12)",
          transition: "box-shadow .18s var(--ease), border-color .18s var(--ease), background .18s var(--ease)",
        }}
      >
        {/* subtle top sheen so the flat blue block has a little depth */}
        <div
          style={{
            position: "absolute",
            inset: 0,
            background: "linear-gradient(180deg, rgba(255,255,255,.16) 0%, rgba(255,255,255,0) 42%)",
            pointerEvents: "none",
          }}
        />

        {/* index chip (kept, top-left) — white-on-translucent so it reads on blue */}
        <span
          style={{
            position: "absolute",
            top: 6,
            left: 6,
            fontSize: 9.5,
            fontWeight: 800,
            color: "#fff",
            background: "rgba(255,255,255,.18)",
            border: "1px solid rgba(255,255,255,.28)",
            borderRadius: 7,
            padding: "1px 5.5px",
            fontVariantNumeric: "tabular-nums",
            letterSpacing: 0.3,
            zIndex: 2,
          }}
        >
          {String(idx + 1).padStart(2, "0")}
        </span>

        {/* CENTERED "Scene N" label — the only text on the block, vertically and
            horizontally centered. White ink rides on the blue fill. */}
        <div
          style={{
            position: "absolute",
            inset: 0,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: "0 8px",
            zIndex: 1,
          }}
        >
          <span
            style={{
              fontSize: wide ? 13 : 11,
              fontWeight: 700,
              color: "#fff",
              letterSpacing: 0.2,
              textAlign: "center",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
              maxWidth: "100%",
              textShadow: "0 1px 2px rgba(8,10,17,.35)",
            }}
          >
            {wide ? `Scene ${idx + 1}` : idx + 1}
          </span>
        </div>
      </div>
    </button>
  );
}
