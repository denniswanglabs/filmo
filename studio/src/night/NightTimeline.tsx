// Engineered Night timeline — ONE tall world, ZERO hard cuts (spec §5.1).
//
// Accepts the exact TimelineData contract the classic Timeline gets. Scenes become
// vertically stacked full-frame sections on one blueprint surface; the camera
// glides between section anchors so every transition is a move, not a cut. Each
// glide ENDS at the scene's in_frame — the camera arrives exactly when the VO
// beat begins, preserving the pipeline's VO-driven timing.
import React from "react";
import { AbsoluteFill, Audio, Sequence, interpolate, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import type { Scene, TimelineData } from "../timeline/types";
import { ensureNightFonts } from "./fonts";
import { nightTokens, type NightTokens } from "./theme";
import { NightStage, WorldSurface, FRAME_W } from "./Stage";
import { NightHero, type NightHeroData } from "./NightHero";
import {
  NightClose,
  NightCredibility,
  NightEcosystem,
  NightLadder,
  NightPanel,
  NightQuote,
  NightTerminal,
} from "./NightSections";
import { GLIDE_EASE, snapToBeat, type BeatGrid } from "./motion";

// Sections are TIGHTER than the viewport so neighbors peek at the frame edges —
// the film reads as one continuous tall page, and mid-glide never crosses a void.
const SECTION_H = 860;
const GLIDE_S = 0.95; // 0.8–1.4s band (spec §6)
// v2 camera: the film NEVER holds still — during each beat the camera crawls
// through ±DRIFT_PX around the section anchor, then the boundary glide eases into
// the next beat's crawl. One continuous path, no stationary frame (spec §6).
const DRIFT_PX = 24;
// The world's grid moves a touch slower than the content — subtle depth parallax
// that makes the surface feel explored rather than slid.
const GRID_PARALLAX = 0.92;

const resolveAsset = (path: string): string =>
  path.startsWith("http") || path.startsWith("/") ? path : staticFile(path);

// Music behavior mirrors the classic Timeline's constants (duck under VO,
// fade in at the start, tail fade outlasting the visual close).
const BGM_DUCKED = 0.16;
const BGM_OPEN = 0.45;
const BGM_FADE_IN = 18;
const BGM_TAIL_FADE = 45;

/** v2 camera path: a single continuous piecewise curve through the section
 *  anchors. During beat i the camera CRAWLS linearly from (anchor−DRIFT) to
 *  (anchor+DRIFT) across the hold; in the last GLIDE_S of the beat it eases the
 *  remaining distance to the next beat's (anchor−DRIFT), landing exactly at the
 *  next scene's in_frame. The camera is in motion on every frame of the film. */
function worldY(frame: number, scenes: Scene[], fps: number): number {
  if (!scenes.length) return 0;
  const glideFrames = Math.round(GLIDE_S * fps);
  const anchor = (i: number) => i * SECTION_H;
  const n = scenes.length;

  for (let i = 0; i < n; i++) {
    const start = scenes[i].in_frame;
    const end = i + 1 < n ? scenes[i + 1].in_frame : scenes[i].out_frame;
    if (frame >= end && i + 1 < n) continue;
    const isLast = i + 1 >= n;
    const glideStart = isLast ? end : Math.max(start, end - glideFrames);
    if (frame <= glideStart) {
      // Crawl phase: linear drift across the hold.
      const span = Math.max(1, glideStart - start);
      const p = Math.min(1, Math.max(0, (frame - start) / span));
      return anchor(i) - DRIFT_PX + 2 * DRIFT_PX * p;
    }
    // Glide phase: ease from (anchor+DRIFT) into the next beat's crawl start.
    const p = interpolate(frame, [glideStart, end], [0, 1], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
      easing: GLIDE_EASE,
    });
    return anchor(i) + DRIFT_PX + (anchor(i + 1) - DRIFT_PX - (anchor(i) + DRIFT_PX)) * p;
  }
  return anchor(n - 1) + DRIFT_PX;
}

const NightSection: React.FC<{
  t: NightTokens;
  scene: Scene;
  frame: number;
  fps: number;
  wordmark: string;
  logoSrc?: string;
  index?: number;
}> = ({ t, scene, frame, fps, wordmark, logoSrc, index }) => {
  const local = Math.max(0, frame - scene.in_frame);
  const hold = Math.max(1, scene.out_frame - scene.in_frame);
  const kind = String(scene.archetype);
  const data = (scene.data ?? {}) as Record<string, unknown>;
  switch (kind) {
    case "night-hero":
      return <NightHero t={t} frame={local} fps={fps} data={data as unknown as NightHeroData} />;
    case "night-panel":
      return <NightPanel t={t} frame={local} fps={fps} data={data} />;
    case "night-quote":
      return <NightQuote t={t} frame={local} fps={fps} data={data} />;
    case "night-credibility":
      return <NightCredibility t={t} frame={local} fps={fps} data={data} holdFrames={hold} />;
    case "night-terminal":
      return <NightTerminal t={t} frame={local} fps={fps} data={data} />;
    case "night-ladder":
      return <NightLadder t={t} frame={local} fps={fps} data={data} wordmark={wordmark} index={index} holdFrames={hold} />;
    case "night-ecosystem":
      return <NightEcosystem t={t} frame={local} fps={fps} data={data} />;
    case "night-close":
      return (
        <NightClose
          t={t}
          frame={local}
          fps={fps}
          data={{ wordmark, logoSrc, ...(data as object) }}
        />
      );
    default:
      return <NightLadder t={t} frame={local} fps={fps} data={data} />;
  }
};

export const NightTimeline: React.FC<TimelineData> = (props) => {
  ensureNightFonts();
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const { scenes, total_frames, audio_path, music_path } = props;
  const t = nightTokens(props.theme);
  const worldH = Math.max(1, scenes.length) * SECTION_H;
  const y = worldY(frame, scenes, fps);

  const hasPerSceneAudio = scenes.some((s) => s.audio?.src);
  const music = props.theme.music || music_path;
  // §B beat grid (frames) from the per-run bed mapping; undefined -> no snapping.
  const grid: BeatGrid | undefined = props.theme.musicMeta;
  // §A camera-distance focus: how centered section i is in the viewport RIGHT NOW.
  // 1 at dead center, falling to 0 one full section away. Sections dim to a 30%
  // peek and UNDIM as the camera glides in — the reference's dim/undim vocabulary.
  const focusOf = (i: number): number => {
    const center = i * SECTION_H + SECTION_H / 2;
    const viewCenter = y + 540; // camera viewport middle in world coords
    return Math.max(0, 1 - Math.abs(center - viewCenter) / SECTION_H);
  };

  return (
    <NightStage t={t}>
      {/* The blueprint surface rides a hair behind the content (depth parallax). */}
      <div
        style={{
          position: "absolute",
          left: 0,
          top: 0,
          width: FRAME_W,
          height: worldH,
          transform: `translateY(${-y * GRID_PARALLAX}px)`,
          willChange: "transform",
        }}
      >
        <WorldSurface t={t} height={worldH} />
      </div>
      {/* The world — every beat translates as one surface. */}
      <div
        style={{
          position: "absolute",
          left: 0,
          top: 0,
          width: FRAME_W,
          height: worldH,
          transform: `translateY(${-y}px)`,
          willChange: "transform",
        }}
      >
        {scenes.map((scene, i) => {
          const focus = focusOf(i);
          return (
            <div
              key={scene.id}
              style={{
                position: "absolute",
                left: 0,
                top: i * SECTION_H,
                width: FRAME_W,
                height: SECTION_H,
                // §A dim/undim: the focused section is full ink; neighbors peek
                // at ~30% and brighten as the camera arrives. Smoothstep keeps
                // the transition part of the glide, not a separate event.
                opacity: 0.3 + 0.7 * (focus * focus * (3 - 2 * focus)),
              }}
            >
              <NightSection
                t={t}
                scene={scene}
                frame={frame}
                fps={fps}
                wordmark={props.theme.wordmark}
                logoSrc={props.theme.logoSrc}
                index={i}
              />
            </div>
          );
        })}
      </div>

      {/* Audio: per-scene VO beats at each scene's in_frame (pipeline convention),
          else the single continuous track. Music ducks under VO and its fade
          outlasts the visual close. */}
      {hasPerSceneAudio
        ? scenes
            .filter((s) => s.audio?.src)
            .map((s) => (
              <Sequence key={`vo-${s.id}`} from={s.in_frame} durationInFrames={s.out_frame - s.in_frame}>
                <Audio src={resolveAsset(s.audio!.src)} />
              </Sequence>
            ))
        : audio_path
          ? <Audio src={resolveAsset(audio_path)} />
          : null}
      {/* Pop family (spec §7): two level-matched samples alternating, marking
          section arrivals and ladder/tile rungs. SFX end by T−1s; the music's
          fade owns the final second. */}
      {scenes.map((scene, i) => {
        const pops: Array<{ at: number; key: string }> = [];
        if (i > 0) pops.push({ at: scene.in_frame, key: `arrive-${scene.id}` });
        const kind = String(scene.archetype);
        const data = (scene.data ?? {}) as { chips?: unknown[]; entities?: unknown[] };
        const rungs = kind === "night-ladder" ? (data.chips?.length ?? 0)
          : kind === "night-ecosystem" ? (data.entities?.length ?? 0) : 0;
        for (let r = 0; r < rungs; r++) {
          pops.push({ at: scene.in_frame + Math.round(0.5 * fps) + Math.round(r * 0.29 * fps), key: `rung-${scene.id}-${r}` });
        }
        // §B: each pop lands ON the nearest musical beat when one is close
        // (±4 frames); VO-locked arrivals that sit off-grid stay put.
        return pops
          .map((p) => ({ ...p, at: snapToBeat(p.at, grid) }))
          .filter((p) => p.at < total_frames - fps)
          .map((p, j) => (
            <Sequence key={p.key} from={p.at} durationInFrames={Math.round(0.7 * fps)}>
              <Audio src={staticFile((i + j) % 2 === 0 ? "night-sfx/pop-a.mp3" : "night-sfx/pop-b.mp3")} volume={0.5} />
            </Sequence>
          ));
      })}
      {music ? (
        <Audio
          src={resolveAsset(music)}
          volume={(f) =>
            interpolate(
              f,
              [0, BGM_FADE_IN, total_frames - BGM_TAIL_FADE, total_frames - 1],
              [0, hasPerSceneAudio ? BGM_DUCKED : BGM_OPEN, BGM_DUCKED, 0],
              { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
            )
          }
        />
      ) : null}
    </NightStage>
  );
};
