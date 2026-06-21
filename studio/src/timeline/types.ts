// Data contract consumed by the <Timeline> composition.
//
// timeline.json (produced by build_timeline.py) is the SHAPE the orchestrator
// passes via `--props=<json>`. We DEVELOP against a bundled fixture so this
// composition does not depend on the other agent's module landing first.
//
// The composition is VO-driven: ONE <Audio> spans the whole voiceover and one
// <Sequence from={in_frame} durationInFrames={out_frame-in_frame}> renders each
// scene. Inside a scene, designed reveals fire on the scene's cue frames
// (at_frame, which build_timeline emits relative to the scene's in_frame).

export type Archetype =
  // Orinovate kinetic-light archetypes
  | "hero-title"
  | "card-ui"
  // The never-blank designed card for a cinematic/walkthrough/demo beat that gets
  // no real footage on a $0/standard run — shows the narrated point as kinetic
  // motion-graphics (navy rail, word-rise title, blue underline, numbered bullets).
  | "explainer-card"
  // Apple-style archetypes (cubic-ease iOS motion, per-brand palette)
  | "apple-hero" // product-as-hero, slide-up title, edge-light sweep
  | "apple-registry" // segmented control + type-coded entity grid
  | "apple-statement"; // big editorial wordmark with subtle breath drift

export interface Cue {
  // A named reveal point. `word` is the spoken word it is anchored to (for
  // provenance / debugging); `at_frame` is when the reveal fires. As emitted by
  // build_timeline.py it is an ABSOLUTE timeline frame (clamped within the
  // scene's [in_frame, out_frame]); Timeline.tsx rebases it to scene-relative
  // before handing it to an archetype (a <Sequence> child sees local frames).
  label: string;
  word: string;
  at_frame: number;
}

// Per-scene filled content + the brand theme. The motion is owned by the
// archetype component; the agent only fills copy / ui-data / cues.
export interface SceneData {
  // hero-title fields
  kicker?: string;
  title?: string;
  // the single word in `title` that gets the accent color + glow punch.
  punchWord?: string;
  subtitle?: string;
  // card-ui fields
  heading?: string;
  headingAccent?: string; // accent-colored leading fragment of the heading
  cards?: Array<{ label: string; value?: string; sub?: string; accent?: boolean }>;

  // explainer-card fields. Reuses kicker / title / subtitle above. `bullets` are
  // short capability lines (parsed from the VO/brief) revealed as numbered badges.
  bullets?: string[];

  // apple-hero fields (product-as-hero lockup)
  // reuses kicker / title / punchWord / subtitle above. `product` is an
  // optional short product/feature name shown on the hero "product" plate.
  product?: string;

  // apple-registry fields. A segmented control across the top, then a
  // type-coded grid of entities (each entity's `type` selects a color from
  // `entityColors`). `selected` is the index that gets the ACTIVE highlight.
  segments?: string[]; // segmented-control labels (e.g. ["All","Plasmids","Runs"])
  selectedSegment?: number; // which segment the sliding pill lands on
  entities?: Array<{ code: string; name: string; meta?: string; type?: string }>;
  // maps an entity.type -> hex color (type-coded). Falls back to theme accent.
  entityColors?: Record<string, string>;
  selected?: number; // index of the entity that gets the ACTIVE badge/glow

  // apple-statement fields. A big editorial wordmark / statement that settles
  // in with a slide-up mask then keeps a subtle breath drift. `lines` is the
  // statement broken into lines; `accentLine` is the line index drawn in accent.
  statement?: string; // single-line statement (alternative to `lines`)
  lines?: string[]; // multi-line editorial statement
  accentLine?: number; // index of the line drawn in the brand accent color
  footnote?: string; // small muted footnote / attribution under the statement
}

export interface Scene {
  id: string;
  archetype: Archetype;
  in_frame: number;
  out_frame: number;
  cues: Cue[];
  data: SceneData;
}

export interface Theme {
  // kinetic-light palette tokens (ported from Orinovate kinetic-light theme.ts)
  bg: string;
  bgCard: string;
  bgCardRaised: string;
  navy: string;
  navyBright: string;
  accent: string;
  ok: string;
  text: string;
  textMuted: string;
  textDim: string;
  border: string;
  fontPrimary: string;
  fontMono: string;
  fontDisplay: string;
  // brand wordmark shown in the hero lockup.
  wordmark: string;
}

// Index signature so TimelineData satisfies Remotion's `Record<string, unknown>`
// Props constraint on <Composition> (lets inference accept it without a Zod schema).
export interface TimelineData {
  fps: number;
  total_frames: number;
  audio_path: string;
  lang: string;
  theme: Theme;
  scenes: Scene[];
  [key: string]: unknown;
}
