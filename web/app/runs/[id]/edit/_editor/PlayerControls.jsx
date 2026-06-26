// Playback controls that sit under the preview canvas: a big round play/pause
// button (Hera gradient + glow), a back-to-start button, the live scrub/seek bar
// bound to the Player's current frame, and a tabular time readout.
//
// State is driven by the Player ref's events (play/pause/frameupdate/seeked) so the
// controls stay in lockstep with the video — including when the timeline clips seek it.
import React, { useEffect, useState } from "react";
import { Icon } from "./ui.jsx";

const fmt = (frame, fps) => {
  const s = Math.max(0, frame) / fps;
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  const cs = Math.floor((s * 100) % 100);
  return `${m}:${String(sec).padStart(2, "0")}.${String(cs).padStart(2, "0")}`;
};

export function PlayerControls({ playerRef, frame, setFrame, total, fps }) {
  const [playing, setPlaying] = useState(false);

  // Subscribe to the player so controls reflect real playback state.
  useEffect(() => {
    const pl = playerRef.current;
    if (!pl) return;
    const onPlay = () => setPlaying(true);
    const onPause = () => setPlaying(false);
    const onFrame = (e) => setFrame(e.detail.frame);
    const onSeek = (e) => setFrame(e.detail.frame);
    pl.addEventListener("play", onPlay);
    pl.addEventListener("pause", onPause);
    pl.addEventListener("ended", onPause);
    pl.addEventListener("frameupdate", onFrame);
    pl.addEventListener("seeked", onSeek);
    return () => {
      pl.removeEventListener("play", onPlay);
      pl.removeEventListener("pause", onPause);
      pl.removeEventListener("ended", onPause);
      pl.removeEventListener("frameupdate", onFrame);
      pl.removeEventListener("seeked", onSeek);
    };
    // re-bind whenever the player instance changes (run reload)
  }, [playerRef, setFrame, total]);

  const toggle = () => {
    const pl = playerRef.current;
    if (!pl) return;
    pl.isPlaying() ? pl.pause() : pl.play();
  };
  const toStart = () => {
    const pl = playerRef.current;
    if (!pl) return;
    pl.pause();
    pl.seekTo(0);
    setFrame(0);
  };
  const onScrub = (e) => {
    const f = Number(e.target.value);
    const pl = playerRef.current;
    if (pl) pl.seekTo(f);
    setFrame(f);
  };

  const pct = total > 1 ? (frame / (total - 1)) * 100 : 0;

  const roundBtn = (primary) => ({
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    flex: "0 0 auto",
    border: primary ? "none" : "1px solid var(--glass-edge)",
    cursor: "pointer",
    transition: "transform .12s var(--ease), box-shadow .16s var(--ease), background .16s var(--ease)",
  });

  return (
    <div
      className="ws-glass"
      style={{
        display: "flex",
        alignItems: "center",
        gap: 14,
        padding: "10px 16px",
        borderRadius: "var(--r-pill)",
      }}
    >
      {/* back to start */}
      <button
        onClick={toStart}
        title="Back to start"
        style={{
          ...roundBtn(false),
          width: 34,
          height: 34,
          borderRadius: "50%",
          background: "var(--glass-2)",
          color: "var(--text-2)",
        }}
        onMouseEnter={(e) => (e.currentTarget.style.color = "var(--text)")}
        onMouseLeave={(e) => (e.currentTarget.style.color = "var(--text-2)")}
      >
        <Icon.rewind />
      </button>

      {/* play / pause — the hero control */}
      <button
        onClick={toggle}
        title={playing ? "Pause" : "Play"}
        style={{
          ...roundBtn(true),
          width: 46,
          height: 46,
          borderRadius: "50%",
          background: "var(--accent-grad)",
          color: "var(--accent-ink)",
          boxShadow: "0 1px 2px rgba(20,23,28,.18), 0 6px 16px rgba(59,130,246,.30), inset 0 1px 0 rgba(255,255,255,.25)",
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.transform = "scale(1.06)";
          e.currentTarget.style.boxShadow = "0 1px 2px rgba(20,23,28,.18), 0 10px 24px rgba(59,130,246,.36), inset 0 1px 0 rgba(255,255,255,.3)";
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.transform = "none";
          e.currentTarget.style.boxShadow = "0 1px 2px rgba(20,23,28,.18), 0 6px 16px rgba(59,130,246,.30), inset 0 1px 0 rgba(255,255,255,.25)";
        }}
      >
        {playing ? <Icon.pause /> : <Icon.play style={{ marginLeft: 2 }} />}
      </button>

      {/* current time */}
      <span
        style={{
          fontSize: 12,
          fontFamily: "var(--code)",
          color: "var(--text)",
          fontVariantNumeric: "tabular-nums",
          letterSpacing: 0.3,
          minWidth: 64,
        }}
      >
        {fmt(frame, fps)}
      </span>

      {/* scrub bar */}
      <input
        className="ws-scrub"
        type="range"
        min={0}
        max={Math.max(1, total - 1)}
        step={1}
        value={Math.min(frame, total - 1)}
        onChange={onScrub}
        style={{ "--pct": pct + "%", flex: 1 }}
      />

      {/* total duration */}
      <span
        style={{
          fontSize: 12,
          fontFamily: "var(--code)",
          color: "var(--muted)",
          fontVariantNumeric: "tabular-nums",
          letterSpacing: 0.3,
          minWidth: 64,
          textAlign: "right",
        }}
      >
        {fmt(total, fps)}
      </span>
    </div>
  );
}
