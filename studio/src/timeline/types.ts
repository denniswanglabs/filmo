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
  | "apple-statement" // big editorial wordmark with subtle breath drift
  // A REAL website screenshot (headless-browser capture) shown inside a
  // brand-tinted browser card with the Apple shrink/zoom arrival. Mode-
  // INDEPENDENT: rendered in both mock + real builds (screenshots are $0).
  | "apple-screenshot"
  // A produced walkthrough MP4 (Walk Agent capture) played INSIDE the branded
  // studio composition, so the clip inherits Walk Studio overlays + per-scene VO
  // placement. The clip fills a brand-tinted frame with a kinetic wordmark/title
  // bar; its own audio is muted by default (the scene VO owns the audio).
  | "walkthrough-player";

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

  // explainer-card RICH TREATMENT fields (feature-card-richness spec).
  // `treatment` selects one of the layout variants. ABSENT / unknown → the
  // existing card renders exactly as before (backward-compat guaranteed).
  // Degrade: split-mosaic/logo-wall w/o featureEntities, split-stat/icon-stat/
  // big-number w/o stat, or feature-list w/o entities+subtitle → archetype drops
  // to the centered, full-width "icon-headline".
  // DORMANT: big-number / logo-wall / feature-list render + validate but NO
  // selection logic emits them yet (the orchestrator wires selection later).
  treatment?:
    | "icon-stat"
    | "split-mosaic"
    | "split-stat"
    | "icon-headline"
    | "big-number"
    | "logo-wall"
    | "feature-list";
  // Curated icon name rendered as inline SVG inside the card tile.
  // Set: rocket, spark, shield, chart, users, bolt, globe, dollar, layers,
  //      sparkles, target, clock. Unknown / missing → falls back to "spark".
  icon?: string;
  // A REAL (never invented) stat shown in icon-stat / split-stat treatments.
  stat?: { value: string; label: string };
  // REAL named entities (companies / people / labels) for the split-mosaic
  // treatment tile grid (up to 6). Named separately from `entities` which is
  // the apple-registry object array — these are plain strings.
  featureEntities?: string[];
  // OPTIONAL real brand logos for the split-mosaic / logo-wall tiles, index-
  // aligned with `featureEntities`. Each is a self-contained data URI
  // ("data:image/png;base64,…") staged at BUILD time (no render-time network).
  // An empty string / missing entry = no logo found -> the tile falls back to
  // the entity name/initial. NEVER invented — only real fetched marks.
  entityLogos?: string[];

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

  // apple-screenshot fields. A REAL captured website screenshot shown inside a
  // brand-tinted browser card with the Apple shrink/zoom arrival.
  //   imageSrc: public-relative (staticFile-resolved) or absolute/remote path to
  //             the captured PNG (style_fill stages it into studio/public/).
  //   frame:    "browser" (mac browser chrome + address bar) or "none" (bare card).
  //   caption:  optional URL shown in the browser address bar (e.g. the captured URL).
  //   headline: optional grounded value-prop line (a short headline about WHAT the
  //             screenshot shows) rendered as prominent on-screen text above the card,
  //             so the proof beat communicates rather than being a bare image. Filled
  //             by style_fill from the scene's narrated VO beat (NEVER the URL).
  imageSrc?: string;
  // "browser" = mac browser chrome + address bar (web product; the Stripe default),
  // "phone"   = portrait PhoneFrame device chrome (mobile/app product; reuses the
  //             SAME archetype with a portrait capture), "none" = bare card.
  frame?: "browser" | "phone" | "none";
  caption?: string;
  headline?: string;

  // --- apple-screenshot v2 "split" layout (spec §2). ALL optional; absent =
  //     byte-identical to the pre-overhaul centered behavior. ---
  // Layout axis: "split" = text-left / screenshot-right (the new default the
  // archetype opts into); "centered" = the original centered-text-above-card path.
  // When ABSENT the archetype keeps its current default (no schema migration).
  layout?: "split" | "centered";
  // The muted supporting sentence under the headline in the left column.
  supporting?: string;
  // The headline↔UI tie target: a rect in card-LOCAL normalized coords (0..1).
  // The archetype draws a highlight-box over it (and optionally a cursor + zoom)
  // timed to the headline punch word. ABSENT = no box/cursor/zoom (plain shot).
  focus?: { x: number; y: number; w: number; h: number; label?: string };
  // Optional cursor path in card-LOCAL normalized coords (0..1); `click` emits a
  // ripple at that keyframe. ABSENT = no cursor.
  cursorPath?: Array<{ at: number; x: number; y: number; click?: boolean }>;
  // Optional zoom-punch target (card-local normalized 0..1) + push scale. ABSENT
  // = no zoom.
  zoomTo?: { x: number; y: number; scale: number };

  // walkthrough-player fields. A produced walkthrough MP4 played inside a
  // brand-tinted frame with a kinetic overlay title bar.
  //   videoSrc:     public-relative (staticFile-resolved) or absolute/remote path
  //                 to the produced clip (style_fill stages it into studio/public/).
  //   videoFit:     "contain" (letterbox, never crop — default for UI walkthroughs)
  //                 or "cover" (fill the frame, may crop edges).
  //   overlayTitle: the brand wordmark / emphasis shown in the kinetic title bar
  //                 over the clip (accent underline reveals on the scene's cues).
  //   muteClip:     mute the clip's own audio (default true — the scene VO owns it).
  videoSrc?: string;
  videoFit?: "contain" | "cover";
  overlayTitle?: string;
  muteClip?: boolean;
  // OPTIONAL proof KPI for the walkthrough device-hero (R4). A short stat string
  // like "$1T+ processed" / "99.999% uptime" / "millions of businesses". The
  // archetype parses a number out of it, rolls it up, and floats a glass chip
  // over the held clip (the TapPay approve-chip analog). ABSENT or number-less
  // => no chip (never invents a stat). Falls back to a number in overlayTitle.
  kpi?: string;

  // OPTIONAL geometry overrides written by the visual editor. Each key maps to a
  // single hardcoded geometry literal inside an archetype (font size, box width,
  // border radius, etc.). When `geo` is ABSENT (every production run today),
  // archetypes fall back to their original literal so output is byte-identical.
  // Keys are archetype-scoped (see each archetype for the exact key set):
  //   hero-title:       titleFontSize, subtitleFontSize, kickerFontSize, plateW,
  //                     plateH, plateOffsetX, plateOffsetY
  //   apple-hero:       titleFontSize, subtitleFontSize
  //   apple-screenshot: cardW, cardRadius, shotH, cardOffsetX, cardOffsetY
  //   apple-statement:  statementFontSize
  // Offsets default to 0 and font/size keys default to the archetype literal, so
  // an absent `geo` (every production run today) renders byte-identical.
  geo?: Record<string, number>;
}

// Per-scene VO audio. The picture is stretched so each scene HOLDS for its
// planned duration (>= its voice), so a single continuous track from frame 0 would
// no longer land each beat on its scene. Instead each voiced scene carries its own
// per-beat file, rendered at the scene's in_frame. `src` is a public-relative path
// (staticFile-resolved) or an absolute/remote path.
export interface SceneAudio {
  src: string;
}

export interface Scene {
  id: string;
  archetype: Archetype;
  in_frame: number;
  out_frame: number;
  cues: Cue[];
  data: SceneData;
  // Optional per-scene VO (per-beat file). When present on ANY scene the Timeline
  // places these per-scene instead of the single continuous top-level audio_path.
  audio?: SceneAudio;
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
  // OPTIONAL real brand logo asset (spec §4). A public-relative path
  // (staticFile-resolved) or absolute/remote URL staged by style_fill into
  // studio/public/brand/. Bookend archetypes render this as an <Img> when
  // present, else fall back to wordmark_svg/text. NEVER invented — ABSENT here
  // means "no captured logo", and bookends degrade to the wordmark.
  logoSrc?: string;
  // OPTIONAL background-music track (spec §4). A public-relative path
  // (staticFile-resolved) or absolute/remote URL staged into studio/public/.
  // When present, Timeline adds ONE looped, ducked <Audio> under the VO; ABSENT
  // = no music track (current behavior). May also be supplied at the top level
  // as `music_path` (theme.music wins if both are set).
  music?: string;
}

// Index signature so TimelineData satisfies Remotion's `Record<string, unknown>`
// Props constraint on <Composition> (lets inference accept it without a Zod schema).
export interface TimelineData {
  fps: number;
  total_frames: number;
  audio_path: string;
  // OPTIONAL background-music track (spec §4), a top-level alternative to
  // theme.music. A public-relative (staticFile-resolved) or absolute/remote
  // path staged into studio/public/. ABSENT = no music (current behavior).
  // If both are set, theme.music wins.
  music_path?: string;
  lang: string;
  theme: Theme;
  scenes: Scene[];
  [key: string]: unknown;
}
