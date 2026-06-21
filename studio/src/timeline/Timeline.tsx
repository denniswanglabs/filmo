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

// build_timeline.py emits cue at_frame as ABSOLUTE timeline frames (clamped into
// [in_frame, out_frame]). Inside a <Sequence from={in_frame}>, useCurrentFrame()
// is scene-LOCAL (0-based), so rebase cues to scene-relative once at this seam.
// The archetypes therefore only ever see scene-relative cue frames.
const rebaseCues = (cues: Cue[], inFrame: number): Cue[] =>
  (cues ?? []).map((c) => ({ ...c, at_frame: Math.max(0, c.at_frame - inFrame) }));

const SceneBody: React.FC<{ scene: Scene; theme: TimelineData["theme"] }> = ({ scene, theme }) => {
  const dur = scene.out_frame - scene.in_frame;
  const cues = rebaseCues(scene.cues, scene.in_frame);
  if (scene.archetype === "card-ui") {
    return <CardUi data={scene.data} cues={cues} theme={theme} durationInFrames={dur} />;
  }
  if (scene.archetype === "explainer-card") {
    return <ExplainerCard data={scene.data} cues={cues} theme={theme} durationInFrames={dur} />;
  }
  if (scene.archetype === "apple-hero") {
    return <AppleHero data={scene.data} cues={cues} theme={theme} durationInFrames={dur} />;
  }
  if (scene.archetype === "apple-registry") {
    return <AppleRegistry data={scene.data} cues={cues} theme={theme} durationInFrames={dur} />;
  }
  if (scene.archetype === "apple-statement") {
    return <AppleStatement data={scene.data} cues={cues} theme={theme} durationInFrames={dur} />;
  }
  // default + "hero-title"
  return <HeroTitle data={scene.data} cues={cues} theme={theme} durationInFrames={dur} />;
};

export const Timeline: React.FC<TimelineData> = (props) => {
  const { audio_path, theme, scenes } = props;
  // staticFile() resolves a path under public/. Allow absolute/remote paths too.
  const audioSrc =
    audio_path.startsWith("http") || audio_path.startsWith("/") ? audio_path : staticFile(audio_path);

  return (
    <AbsoluteFill style={{ backgroundColor: theme.bg }}>
      <Audio src={audioSrc} />
      {scenes.map((scene) => (
        <Sequence
          key={scene.id}
          from={scene.in_frame}
          durationInFrames={Math.max(1, scene.out_frame - scene.in_frame)}
          name={`${scene.id} (${scene.archetype})`}
        >
          <SceneBody scene={scene} theme={theme} />
        </Sequence>
      ))}
    </AbsoluteFill>
  );
};
