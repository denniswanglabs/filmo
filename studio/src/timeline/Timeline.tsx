// The <Timeline> composition body. VO-driven:
//   - ONE <Audio src={audio_path}> spans the whole voiceover.
//   - ONE <Sequence from={in_frame} durationInFrames={out-in}> per scene.
//   - Each scene renders its archetype; reveals fire on the scene's cue frames
//     (at_frame is relative to the scene, which is exactly the local frame a
//     <Sequence> child sees via useCurrentFrame).
//
// Data selection: props passed via Remotion inputProps (`--props=<json>` from
// build_timeline.py / the orchestrator) win; otherwise the bundled fixture is
// used so the studio + smoke render work standalone.
import React from "react";
import { AbsoluteFill, Audio, Sequence, staticFile } from "remotion";
import type { Cue, Scene, TimelineData } from "./types";
import { HeroTitle } from "./archetypes/HeroTitle";
import { CardUi } from "./archetypes/CardUi";
import { ExplainerCard } from "./archetypes/ExplainerCard";
import { AppleHero } from "./archetypes/AppleHero";
import { AppleRegistry } from "./archetypes/AppleRegistry";
import { AppleStatement } from "./archetypes/AppleStatement";
import { AppleScreenshot } from "./archetypes/AppleScreenshot";
import { WalkthroughPlayer } from "./archetypes/WalkthroughPlayer";

// build_timeline.py emits cue at_frame as ABSOLUTE timeline frames (clamped into
// [in_frame, out_frame]). Inside a <Sequence from={in_frame}>, useCurrentFrame()
// is scene-LOCAL (0-based), so rebase cues to scene-relative once at this seam.
// The archetypes therefore only ever see scene-relative cue frames.
const rebaseCues = (cues: Cue[], inFrame: number): Cue[] =>
  (cues ?? []).map((c) => ({ ...c, at_frame: Math.max(0, c.at_frame - inFrame) }));

// Resolve a public-relative path under public/ via staticFile; pass absolute/remote
// (http or leading-slash) paths through untouched. Shared by <Audio> and the
// apple-screenshot <Img> (both staged into public/ by style_fill).
const resolveAsset = (path: string): string =>
  path.startsWith("http") || path.startsWith("/") ? path : staticFile(path);

// Archetypes that are opening/closing bookends — they do NOT receive an act badge.
// hero-title: the opening and CTA-close title beats.
// apple-statement: the editorial thesis / CTA-lead-in beat.
const BOOKEND_ARCHETYPES = new Set(["hero-title", "apple-statement"]);

// Compute act index (1-based) for each scene: count only non-bookend scenes in
// timeline order. Returns -1 for bookend scenes (badge not shown).
const computeActIndices = (scenes: Scene[]): number[] => {
  let counter = 0;
  return scenes.map((s) => (BOOKEND_ARCHETYPES.has(s.archetype) ? -1 : ++counter));
};

const SceneBody: React.FC<{ scene: Scene; theme: TimelineData["theme"]; actIndex: number }> = ({
  scene,
  theme,
  actIndex,
}) => {
  const dur = scene.out_frame - scene.in_frame;
  const cues = rebaseCues(scene.cues, scene.in_frame);
  if (scene.archetype === "card-ui") {
    return <CardUi data={scene.data} cues={cues} theme={theme} durationInFrames={dur} actIndex={actIndex} sceneId={scene.id} />;
  }
  if (scene.archetype === "explainer-card") {
    return <ExplainerCard data={scene.data} cues={cues} theme={theme} durationInFrames={dur} actIndex={actIndex} sceneId={scene.id} />;
  }
  if (scene.archetype === "apple-hero") {
    return <AppleHero data={scene.data} cues={cues} theme={theme} durationInFrames={dur} actIndex={actIndex} sceneId={scene.id} />;
  }
  if (scene.archetype === "apple-registry") {
    return <AppleRegistry data={scene.data} cues={cues} theme={theme} durationInFrames={dur} actIndex={actIndex} sceneId={scene.id} />;
  }
  if (scene.archetype === "apple-statement") {
    return <AppleStatement data={scene.data} cues={cues} theme={theme} durationInFrames={dur} sceneId={scene.id} />;
  }
  if (scene.archetype === "apple-screenshot") {
    return (
      <AppleScreenshot
        data={scene.data}
        cues={cues}
        theme={theme}
        durationInFrames={dur}
        resolveSrc={resolveAsset}
        actIndex={actIndex}
        sceneId={scene.id}
      />
    );
  }
  if (scene.archetype === "walkthrough-player") {
    return (
      <WalkthroughPlayer
        data={scene.data}
        cues={cues}
        theme={theme}
        durationInFrames={dur}
        resolveSrc={resolveAsset}
        actIndex={actIndex}
        sceneId={scene.id}
      />
    );
  }
  // default + "hero-title" — no act badge on bookends
  return <HeroTitle data={scene.data} cues={cues} theme={theme} durationInFrames={dur} sceneId={scene.id} />;
};

export const Timeline: React.FC<TimelineData> = (props) => {
  const { audio_path, theme, scenes } = props;
  // Per-scene VO: scenes are stretched to hold their planned duration, so each
  // beat must start at its OWN scene's in_frame (a single continuous track from
  // frame 0 would drift). When ANY scene carries per-scene audio, place those
  // per-scene; otherwise fall back to the single continuous top-level track.
  const hasPerSceneAudio = scenes.some((s) => s.audio?.src);
  // Assign 1-based act indices to content-beat scenes; bookends get -1.
  const actIndices = computeActIndices(scenes);

  return (
    <AbsoluteFill style={{ backgroundColor: theme.bg }}>
      {!hasPerSceneAudio && audio_path ? <Audio src={resolveAsset(audio_path)} /> : null}
      {scenes.map((scene, i) => (
        <Sequence
          key={scene.id}
          from={scene.in_frame}
          durationInFrames={Math.max(1, scene.out_frame - scene.in_frame)}
          name={`${scene.id} (${scene.archetype})`}
        >
          {/* Per-scene VO starts at the scene's in_frame (local frame 0). */}
          {hasPerSceneAudio && scene.audio?.src ? (
            <Audio src={resolveAsset(scene.audio.src)} />
          ) : null}
          <SceneBody scene={scene} theme={theme} actIndex={actIndices[i]} />
        </Sequence>
      ))}
    </AbsoluteFill>
  );
};
