// Dev/stills composition for the Engineered Night hero — the Stage-2 checkpoint.
// Two built-in brand fixtures prove the accent-as-slot rule: the reference-mint
// subject AND a non-mint brand render from the identical grammar.
import React from "react";
import { useCurrentFrame, useVideoConfig } from "remotion";
import { ensureNightFonts } from "./fonts";
import { nightTokens } from "./theme";
import { NightStage, WorldSurface, FRAME_W } from "./Stage";
import { NightHero, type NightHeroData } from "./NightHero";
import type { Theme } from "../timeline/types";

const BASE_THEME: Omit<Theme, "accent" | "wordmark"> = {
  bg: "#000000",
  bgCard: "#161616",
  bgCardRaised: "#1D1D1D",
  navy: "#0A0A0A",
  navyBright: "#161616",
  ok: "#22C55E",
  text: "#FFFFFF",
  textMuted: "rgba(255,255,255,0.62)",
  textDim: "rgba(255,255,255,0.38)",
  border: "rgba(255,255,255,0.08)",
  fontPrimary: "Inter, sans-serif",
  fontMono: '"SF Mono", Menlo, monospace',
  fontDisplay: "Manrope, sans-serif",
};

const FIXTURES: Record<string, { theme: Theme; hero: NightHeroData }> = {
  insforge: {
    theme: { ...BASE_THEME, accent: "#6EE7B7", wordmark: "INSFORGE" },
    hero: {
      eyebrow: "Backed by Y Combinator",
      lines: [
        [{ text: "Ship " }, { text: "production-ready", accent: true }],
        [{ text: "backends in minutes" }],
      ],
      sub: "Model gateway, compute, deployment, database, auth, and more — every service built for agents.",
      ctaPrimary: "Start Building Today",
      ctaSecondary: "Read Docs",
    },
  },
  stripe: {
    theme: { ...BASE_THEME, accent: "#635BFF", wordmark: "STRIPE" },
    hero: {
      eyebrow: "Financial infrastructure",
      lines: [
        [{ text: "Accept " }, { text: "payments", accent: true }],
        [{ text: "from anywhere" }],
      ],
      sub: "Online payments, billing, and financial infrastructure for the internet.",
      ctaPrimary: "Start now",
      ctaSecondary: "Contact sales",
    },
  },
};

export const NightHeroDemo: React.FC<{ brand?: string }> = ({ brand = "insforge" }) => {
  ensureNightFonts();
  const frame = useCurrentFrame();
  const { fps, height } = useVideoConfig();
  const fixture = FIXTURES[brand] ?? FIXTURES.insforge;
  const t = nightTokens(fixture.theme);
  return (
    <NightStage t={t}>
      <div style={{ position: "absolute", left: 0, top: 0, width: FRAME_W, height }}>
        <WorldSurface t={t} height={height} />
        <NightHero t={t} frame={frame} fps={fps} data={fixture.hero} />
      </div>
    </NightStage>
  );
};
