import React from "react";
import { Composition } from "remotion";
// `active` is the component the producer agent just wrote for THIS scene.
// remotion_codegen.py overwrites src/generated/active.tsx before each render,
// so the registered "Scene" composition always renders the agent's latest code.
import { Active, activeMeta } from "./generated/active";
// VO-driven timeline composition (Phase 1, module 3) — renders a whole video
// FROM timeline.json. Registered ALONGSIDE "Scene" under a separate id so the
// existing single-Scene path + its tests stay green.
import { Timeline } from "./timeline/Timeline";
import { fixtureTimeline, timelineMetadata } from "./timeline/data";
// Engineered Night (dark one-world style) — dev/stills composition for the
// Stage-2 aesthetic checkpoint; the full NightTimeline registers once assembled.
import { NightHeroDemo } from "./night/NightHeroDemo";
import { NightTimeline } from "./night/NightTimeline";
import { nightFixture, nightMetadata } from "./night/fixture";

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="Scene"
        component={Active}
        durationInFrames={activeMeta.durationInFrames}
        fps={activeMeta.fps}
        width={activeMeta.width}
        height={activeMeta.height}
      />
      <Composition
        id="Timeline"
        component={Timeline}
        defaultProps={fixtureTimeline}
        calculateMetadata={timelineMetadata}
      />
      <Composition
        id="NightTimeline"
        component={NightTimeline}
        defaultProps={nightFixture}
        calculateMetadata={nightMetadata}
        width={1920}
        height={1080}
      />
      <Composition
        id="NightHeroDemo"
        component={NightHeroDemo}
        defaultProps={{ brand: "insforge" }}
        durationInFrames={150}
        fps={30}
        width={1920}
        height={1080}
      />
    </>
  );
};
