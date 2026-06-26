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
import { lightenTheme } from "./theme-light";

// build_timeline.py emits cue at_frame as ABSOLUTE timeline frames (clamped into
// [in_frame, out_frame]). Inside a <Sequence from={in_frame}>, useCurrentFrame()
// is scene-LOCAL (0-based), so rebase cues to scene-relative once at this seam.
// The archetypes therefore only ever see scene-relative cue frames.
const rebaseCues = (cues: Cue[], inFrame: number): Cue[] =>
  (cues ?? []).map((c) => ({ ...c, at_frame: Math.max(0, c.at_frame - inFrame) }));

// Resolve a public-relative path. Absolute/remote (http or leading-slash) paths
// pass through untouched. For a public-relative name we either (a) prepend the
// hosted `assetBaseUrl` (the InsForge `walk-videos` bucket / CDN base the editor
// passes in inputProps) when present, or (b) fall back to Remotion's staticFile
// (the studio render path). This is the ONE seam where the hosted editor swaps
// the render-time public/ for bucket URLs without rewriting every props path.
// Shared by <Audio> and the apple-screenshot <Img>.
const makeResolveAsset =
  (assetBaseUrl?: string) =>
  (path: string): string => {
    if (!path) return path;
    if (path.startsWith("http") || path.startsWith("/")) return path;
    if (assetBaseUrl) {
      const baseTrimmed = assetBaseUrl.replace(/\/+$/, "");
      const rel = path.replace(/^\/+/, "");
      return `${baseTrimmed}/${rel}`;
    }
    return staticFile(path);
  };

// Background-music duck levels (spec §4 + feedback_bgm_level_depends_on_vo).
const BGM_DUCKED = 0.16; // under VO
const BGM_OPEN = 0.45; // in VO gaps (intro sting + CTA tail)
const BGM_FADE_IN = 18; // frames to ramp the bed up at the very start
// Per feedback_audio_outlasts_visual_fade: the audio fade-out OUTLASTS the
// visual fade. The visual close fades over the CTA bookend; the music keeps
// fading ~15f longer, so we start the audio fade EARLY and let it run to the end.
const BGM_TAIL_FADE = 45; // frames over which the bed fades out at the end (~15f past a 30f visual fade)

// Build the frame→volume callback for the looped background-music bed. Ducks to
// BGM_DUCKED whenever a VO beat is playing, opens to BGM_OPEN in the gaps
// (silent bookends), ramps in at the start, and fades out at the end so the
// audio outlasts the visual fade. VO windows are derived from the scenes:
//   - per-scene VO mode: a scene is "narrated" iff it carries scene.audio?.src.
//   - single continuous VO mode: every NON-bookend scene is treated as narrated;
//     bookends (intro/CTA) are the gaps.
// Pure function of frame → deterministic.
const makeMusicVolume = (
  scenes: Scene[],
  totalFrames: number,
  hasPerSceneAudio: boolean,
  hasContinuousVo: boolean,
  // Editor music-level multiplier (0..1.5). Default 1 keeps the ducked/open curve
  // exactly as the pipeline emits it; the editor's Music control scales it.
  level = 1
) => {
  const voWindows: Array<[number, number]> = scenes
    .filter((s) =>
      hasPerSceneAudio
        ? Boolean(s.audio?.src)
        : hasContinuousVo && !BOOKEND_ARCHETYPES.has(s.archetype)
    )
    .map((s) => [s.in_frame, Math.max(s.in_frame + 1, s.out_frame)] as [number, number]);

  const fadeOutStart = Math.max(0, totalFrames - BGM_TAIL_FADE);

  return (frame: number): number => {
    const inVo = voWindows.some(([a, b]) => frame >= a && frame < b);
    const target = inVo ? BGM_DUCKED : BGM_OPEN;
    // start ramp-in
    const rampIn = Math.min(1, Math.max(0, frame / BGM_FADE_IN));
    // tail fade-out (outlasts the visual fade)
    const tail =
      frame >= fadeOutStart
        ? Math.max(0, 1 - (frame - fadeOutStart) / Math.max(1, BGM_TAIL_FADE))
        : 1;
    return target * rampIn * tail * level;
  };
};

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

const SceneBody: React.FC<{
  scene: Scene;
  theme: TimelineData["theme"];
  actIndex: number;
  resolveAsset: (path: string) => string;
}> = ({ scene, theme, actIndex, resolveAsset }) => {
  const dur = scene.out_frame - scene.in_frame;
  const cues = rebaseCues(scene.cues, scene.in_frame);
  if (scene.archetype === "card-ui") {
    return <CardUi data={scene.data} cues={cues} theme={theme} durationInFrames={dur} actIndex={actIndex} sceneId={scene.id} resolveSrc={resolveAsset} />;
  }
  if (scene.archetype === "explainer-card") {
    return <ExplainerCard data={scene.data} cues={cues} theme={theme} durationInFrames={dur} actIndex={actIndex} sceneId={scene.id} resolveSrc={resolveAsset} />;
  }
  if (scene.archetype === "apple-hero") {
    return <AppleHero data={scene.data} cues={cues} theme={theme} durationInFrames={dur} actIndex={actIndex} sceneId={scene.id} resolveSrc={resolveAsset} />;
  }
  if (scene.archetype === "apple-registry") {
    return <AppleRegistry data={scene.data} cues={cues} theme={theme} durationInFrames={dur} actIndex={actIndex} sceneId={scene.id} resolveSrc={resolveAsset} />;
  }
  if (scene.archetype === "apple-statement") {
    return <AppleStatement data={scene.data} cues={cues} theme={theme} durationInFrames={dur} sceneId={scene.id} resolveSrc={resolveAsset} />;
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
  return <HeroTitle data={scene.data} cues={cues} theme={theme} durationInFrames={dur} sceneId={scene.id} resolveSrc={resolveAsset} />;
};

export const Timeline: React.FC<TimelineData> = (props) => {
  const { audio_path, scenes, total_frames, music_path } = props;
  // R2-VISUAL: normalize the brand theme to the canonical Luceo-light treatment
  // (near-white page + dark ink + light cards, brand accent preserved) ONCE at the
  // seam, so the light/dark treatment is correct regardless of what the pipeline
  // emits. Already-light themes pass through unchanged (backward-compatible). Every
  // archetype reads tokens off this `theme`, so this fixes all scenes' bg/ink/cards.
  const theme = lightenTheme(props.theme);
  // Hosted-editor asset seam: when inputProps carry an `assetBaseUrl` (the
  // InsForge `walk-videos` bucket / CDN base), public-relative asset names in
  // props resolve against it; otherwise this falls back to Remotion's staticFile
  // (the studio render path). Absolute/remote paths always pass through.
  const resolveAsset = makeResolveAsset(
    typeof props.assetBaseUrl === "string" ? props.assetBaseUrl : undefined
  );
  // Per-scene VO: scenes are stretched to hold their planned duration, so each
  // beat must start at its OWN scene's in_frame (a single continuous track from
  // frame 0 would drift). When ANY scene carries per-scene audio, place those
  // per-scene; otherwise fall back to the single continuous top-level track.
  const hasPerSceneAudio = scenes.some((s) => s.audio?.src);
  const hasContinuousVo = !hasPerSceneAudio && Boolean(audio_path);
  // Assign 1-based act indices to content-beat scenes; bookends get -1.
  const actIndices = computeActIndices(scenes);

  // Background-music bed (spec §4). theme.music wins over the top-level
  // music_path; absent → no music track (current behavior, default-safe). The
  // F agent populates these. The bed is ONE looped <Audio> UNDER the VO, ducked
  // to BGM_DUCKED while a VO beat plays and opened to BGM_OPEN in the gaps.
  const musicSrc = theme.music ?? music_path;
  const lastOut = scenes.reduce((m, s) => Math.max(m, s.out_frame), 0);
  const musicTotal = Math.max(total_frames ?? 0, lastOut, 1);
  // Editor music-level: props.music_level (0 = mute … 1.5 = louder). Undefined → 1.
  const musicLevel =
    typeof (props as { music_level?: number }).music_level === "number"
      ? (props as { music_level?: number }).music_level!
      : 1;
  const musicVolume = makeMusicVolume(scenes, musicTotal, hasPerSceneAudio, hasContinuousVo, musicLevel);

  return (
    <AbsoluteFill style={{ backgroundColor: theme.bg }}>
      {!hasPerSceneAudio && audio_path ? <Audio src={resolveAsset(audio_path)} /> : null}
      {musicSrc ? (
        <Audio src={resolveAsset(musicSrc)} loop volume={musicVolume} />
      ) : null}
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
          <SceneBody scene={scene} theme={theme} actIndex={actIndices[i]} resolveAsset={resolveAsset} />
        </Sequence>
      ))}
    </AbsoluteFill>
  );
};
