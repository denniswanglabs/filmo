// Timeline data loader. The bundled fixture is the standalone default (so the
// studio + the render-smoke work without the Python pipeline). At render time
// the orchestrator overrides it via Remotion inputProps (`--props=<json>` or
// `--props=<file>.json`), which Remotion shallow-merges over defaultProps.
import fixture from "./fixtures/timeline.fixture.json";
import type { TimelineData } from "./types";

export const fixtureTimeline = fixture as TimelineData;

// calculateMetadata reads the (possibly overridden) props so the composition's
// duration + fps come straight from timeline.json — the picture follows the VO.
// Signature matches Remotion's CalculateMetadataFunction (takes the full
// options object; we only need `props`).
export const timelineMetadata = ({ props }: { props: TimelineData }) => ({
  durationInFrames: Math.max(1, props.total_frames ?? fixtureTimeline.total_frames),
  fps: props.fps ?? fixtureTimeline.fps,
  width: 1920,
  height: 1080,
});
