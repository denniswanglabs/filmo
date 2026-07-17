// Engineered Night demo fixture — the guards-run insforge.dev film (run
// e2e-guards-1784266469617) re-expressed in the Night style. Every asset and
// every line is REAL pipeline output from that run: the captured homepage, the
// per-scene ElevenLabs/edge VO beats, the music bed, the sentence-trimmed
// testimonial, the 12.3k stat, the four page features. CLI lines are real
// @insforge/cli commands. Nothing invented.
import type { TimelineData } from "../timeline/types";

const FPS = 30;

export const nightFixture: TimelineData = {
  fps: FPS,
  total_frames: 1401,
  audio_path: "",
  lang: "en",
  theme: {
    bg: "#000000",
    bgCard: "#161616",
    bgCardRaised: "#1D1D1D",
    navy: "#0A0A0A",
    navyBright: "#161616",
    accent: "#6EE7B7",
    ok: "#22C55E",
    text: "#FFFFFF",
    textMuted: "rgba(255,255,255,0.62)",
    textDim: "rgba(255,255,255,0.38)",
    border: "rgba(255,255,255,0.08)",
    fontPrimary: "Inter, sans-serif",
    fontMono: '"SF Mono", Menlo, monospace',
    fontDisplay: "Manrope, sans-serif",
    wordmark: "INSFORGE",
    logoSrc: "night-demo/brand-logo.ico",
    music: "night-demo/music.mp3",
    // Development pass §B: the bed's measured 99.4 BPM as a frame grid
    // (60/99.4 s per beat @ 30fps), phase 0 — exercises SFX quantization.
    musicMeta: { spbFrames: 18.11, phaseFrames: 0 },
  },
  scenes: [
    {
      id: "open-title",
      archetype: "night-hero" as never,
      in_frame: 0,
      out_frame: 156,
      cues: [],
      audio: { src: "night-demo/vo-open-title.mp3" },
      data: {
        eyebrow: "Backed by Y Combinator",
        lines: [
          [{ text: "Ship " }, { text: "production-ready", accent: true }],
          [{ text: "backends in minutes" }],
        ],
        sub: "Model gateway, compute, deployment, database, auth, and more — every service built for agents.",
        ctaPrimary: "Start Building Today",
        ctaSecondary: "Read Docs",
      } as never,
    },
    {
      id: "shot-homepage",
      archetype: "night-panel" as never,
      in_frame: 156,
      out_frame: 336,
      cues: [],
      audio: { src: "night-demo/vo-shot-homepage.mp3" },
      data: {
        imageSrc: "night-demo/shot-shot-homepage.png",
        caption: "insforge.dev — captured live",
      } as never,
    },
    {
      id: "mg-ship-faster",
      archetype: "night-quote" as never,
      in_frame: 336,
      out_frame: 741,
      cues: [],
      audio: { src: "night-demo/vo-mg-ship-faster.mp3" },
      data: {
        quote:
          "One platform gave me auth, AI model access, embeddings, real-time, file storage and PostgreSQL — everything Drexii needed to connect 11 tools and 50+ actions in one AI agent.",
        quoteAttribution: "Davidson @AwokoyaD",
        holdFrames: 405,
      } as never,
    },
    {
      id: "mg-production-ready",
      archetype: "night-credibility" as never,
      in_frame: 741,
      out_frame: 891,
      cues: [],
      audio: { src: "night-demo/vo-mg-production-ready.mp3" },
      data: {
        eyebrow: "Open source",
        stat: {
          value: "12.3k",
          label: "GitHub stars — model gateway, compute, deployment, database, auth, and more",
        },
      } as never,
    },
    {
      id: "mg-safe-agents",
      archetype: "night-terminal" as never,
      in_frame: 891,
      out_frame: 1086,
      cues: [],
      audio: { src: "night-demo/vo-mg-safe-agents.mp3" },
      data: {
        title: "Safe for agents to operate",
        toggle: { left: "Human", right: "Agent" },
        lines: [
          'npx @insforge/cli metadata --json',
          'npx @insforge/cli db query "SELECT status FROM runs"',
        ],
        status: "sandboxed execution · audit trail written · instant rollback ready",
      } as never,
    },
    {
      id: "mg-changelog",
      archetype: "night-ladder" as never,
      in_frame: 1086,
      out_frame: 1251,
      cues: [],
      audio: { src: "night-demo/vo-mg-changelog.mp3" },
      data: {
        headline: "Live changelog ships versioned updates continuously",
        chips: ["Ship Faster", "Everything for Production", "Safe for Agents", "Changelog"],
        secondary: ["Sites", "Custom Compute", "Vector", "Analytics", "Messaging"],
        activeIndex: 3,
      } as never,
    },
    {
      id: "close-cta",
      archetype: "night-close" as never,
      in_frame: 1251,
      out_frame: 1401,
      cues: [],
      audio: { src: "night-demo/vo-close-cta.mp3" },
      data: {
        tagline: "Start building at insforge.dev today",
        accentWord: "insforge.dev today",
        chip: "Built for agents",
        terminalLines: [
          'npx @insforge/cli metadata --json',
          'npx @insforge/cli db query "SELECT status FROM runs"',
        ],
      } as never,
    },
  ],
};

export const nightMetadata = ({ props }: { props: TimelineData }) => ({
  durationInFrames: props.total_frames,
  fps: props.fps,
});
