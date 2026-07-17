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
// the film reads as one continuous engineered surface, and mid-glide never
// crosses a void.
const SECTION_H = 860;
// v4: the world is TWO-dimensional. Consecutive beats alternate DOWN then RIGHT
// (the reference's camera grammar — "sometimes it's going down, sometimes right").
// The horizontal step is slightly tighter than the frame so the next column's
// rail peeks in during the glide.
const H_STEP = 1800;
const GLIDE_S = 0.95; // 0.8–1.4s band (spec §6)
// v2 camera: the film NEVER holds still — during each beat the camera crawls
// through ±DRIFT_PX around the section anchor (along its ARRIVAL axis), then the
// boundary glide eases into the next beat's crawl. One continuous path.
const DRIFT_PX = 24;
// The world's grid moves a touch slower than the content — subtle depth parallax
// that makes the surface feel explored rather than slid.
const GRID_PARALLAX = 0.92;

interface WorldPoint {
  x: number;
  y: number;
}

/** v4 layout: anchor positions on the 2D surface. Step i -> i+1 moves DOWN when
 *  i is even, RIGHT when i is odd — down, right, down, right… deterministic for
 *  every run, so the camera grammar (not the brand) owns the rhythm. */
export function worldLayout(count: number): WorldPoint[] {
  const pos: WorldPoint[] = [{ x: 0, y: 0 }];
  for (let i = 1; i < count; i++) {
    const prev = pos[i - 1];
    if ((i - 1) % 2 === 0) pos.push({ x: prev.x, y: prev.y + SECTION_H });
    else pos.push({ x: prev.x + H_STEP, y: prev.y });
  }
  return pos;
}

/** Axis the camera ARRIVES on at beat i (the crawl drifts along this axis). */
const arrivalAxis = (i: number): "x" | "y" => (i === 0 ? "y" : (i - 1) % 2 === 0 ? "y" : "x");

const resolveAsset = (path: string): string =>
  path.startsWith("http") || path.startsWith("/") ? path : staticFile(path);

// Music behavior mirrors the classic Timeline's constants (duck under VO,
// fade in at the start, tail fade outlasting the visual close).
const BGM_DUCKED = 0.16;
const BGM_OPEN = 0.45;
const BGM_FADE_IN = 18;
const BGM_TAIL_FADE = 45;

/** v4 camera path: a single continuous piecewise curve through the 2D anchors.
 *  During beat i the camera CRAWLS linearly through ±DRIFT along its ARRIVAL
 *  axis; in the last GLIDE_S of the beat it eases (one dominant axis per move,
 *  spec §6) into the next beat's crawl start, landing exactly at the next
 *  scene's in_frame. The camera is in motion on every frame of the film. */
function worldPos(frame: number, scenes: Scene[], fps: number, layout: WorldPoint[]): WorldPoint {
  if (!scenes.length) return { x: 0, y: 0 };
  const glideFrames = Math.round(GLIDE_S * fps);
  const n = scenes.length;

  const crawlPoint = (i: number, p: number): WorldPoint => {
    const a = layout[i];
    const d = -DRIFT_PX + 2 * DRIFT_PX * p;
    return arrivalAxis(i) === "y" ? { x: a.x, y: a.y + d } : { x: a.x + d, y: a.y };
  };

  for (let i = 0; i < n; i++) {
    const start = scenes[i].in_frame;
    const end = i + 1 < n ? scenes[i + 1].in_frame : scenes[i].out_frame;
    if (frame >= end && i + 1 < n) continue;
    const isLast = i + 1 >= n;
    const glideStart = isLast ? end : Math.max(start, end - glideFrames);
    if (frame <= glideStart) {
      // Crawl phase: linear drift across the hold, along the arrival axis.
      const span = Math.max(1, glideStart - start);
      return crawlPoint(i, Math.min(1, Math.max(0, (frame - start) / span)));
    }
    // Glide phase: ease from the crawl's end into the NEXT beat's crawl start.
    const from = crawlPoint(i, 1);
    const to = crawlPoint(i + 1, 0);
    const p = interpolate(frame, [glideStart, end], [0, 1], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
      easing: GLIDE_EASE,
    });
    return { x: from.x + (to.x - from.x) * p, y: from.y + (to.y - from.y) * p };
  }
  return crawlPoint(n - 1, 1);
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
      return <NightPanel t={t} frame={local} fps={fps} data={data} wordmark={wordmark} index={index} />;
    case "night-quote":
      return <NightQuote t={t} frame={local} fps={fps} data={data} wordmark={wordmark} index={index} logoSrc={logoSrc} />;
    case "night-credibility":
      return <NightCredibility t={t} frame={local} fps={fps} data={data} holdFrames={hold} wordmark={wordmark} index={index} />;
    case "night-terminal":
      return <NightTerminal t={t} frame={local} fps={fps} data={data} wordmark={wordmark} index={index} />;
    case "night-ladder":
      return <NightLadder t={t} frame={local} fps={fps} data={data} wordmark={wordmark} index={index} holdFrames={hold} />;
    case "night-ecosystem":
      return <NightEcosystem t={t} frame={local} fps={fps} data={data} wordmark={wordmark} index={index} />;
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
  const layout = worldLayout(Math.max(1, scenes.length));
  const worldW = Math.max(...layout.map((p) => p.x)) + FRAME_W;
  const worldH = Math.max(...layout.map((p) => p.y)) + SECTION_H + 220;
  const cam = worldPos(frame, scenes, fps, layout);

  const hasPerSceneAudio = scenes.some((s) => s.audio?.src);
  const music = props.theme.music || music_path;
  // §B beat grid (frames) from the per-run bed mapping; undefined -> no snapping.
  const grid: BeatGrid | undefined = props.theme.musicMeta;
  // §A camera-distance focus in 2D: per-axis distance normalized by the step
  // size, max-metric so a horizontal neighbor dims exactly like a vertical one.
  // Sections dim to a 30% peek and UNDIM as the camera glides in.
  const focusOf = (i: number): number => {
    const c = layout[i];
    const dx = Math.abs(c.x + FRAME_W / 2 - (cam.x + FRAME_W / 2)) / H_STEP;
    const dy = Math.abs(c.y + SECTION_H / 2 - (cam.y + SECTION_H / 2)) / SECTION_H;
    return Math.max(0, 1 - Math.max(dx, dy));
  };

  return (
    <NightStage t={t}>
      {/* The blueprint surface rides a hair behind the content (depth parallax). */}
      <div
        style={{
          position: "absolute",
          left: 0,
          top: 0,
          width: worldW,
          height: worldH,
          transform: `translate(${-cam.x * GRID_PARALLAX}px, ${-cam.y * GRID_PARALLAX}px)`,
          willChange: "transform",
        }}
      >
        <WorldSurface t={t} width={worldW} height={worldH} />
      </div>
      {/* The world — every beat translates as one surface. */}
      <div
        style={{
          position: "absolute",
          left: 0,
          top: 0,
          width: worldW,
          height: worldH,
          transform: `translate(${-cam.x}px, ${-cam.y}px)`,
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
                left: layout[i].x,
                top: layout[i].y,
                width: FRAME_W,
                height: SECTION_H,
                // §A dim/undim: the focused section is full ink; neighbors peek
                // at ~30% and brighten as the camera arrives. Smoothstep keeps
                // the transition part of the glide, not a separate event.
                opacity: 0.3 + 0.7 * (focus * focus * (3 - 2 * focus)),
              }}
            >
              {/* Per-cell rails bound each beat's content column — with the 2D
                  layout the rails travel with the cell instead of the world. */}
              <div style={{ position: "absolute", left: (FRAME_W - 1280) / 2, top: 0, bottom: 0, width: 1, background: "rgba(255,255,255,0.10)" }} />
              <div style={{ position: "absolute", right: (FRAME_W - 1280) / 2, top: 0, bottom: 0, width: 1, background: "rgba(255,255,255,0.10)" }} />
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
