// /how-it-works — a focused, scannable explainer (not the whole marketing story).
// Three tight beats: the hero header, the numbered how-it-works steps (the point),
// and ONE condensed "why Filmo" credibility block — then the closing CTA. The
// heavier showpieces (TrustBar, ParallaxColumns, UseCases) live on the landing /
// remain available as shared components; they're just not stacked here anymore.

import FloatingNav from '../components/landing/FloatingNav'
import HowItWorks from '../components/landing/HowItWorks'
import Differentiators from '../components/landing/Differentiators'
import ClosingCTA from '../components/landing/ClosingCTA'
import SiteFooter from '../components/landing/SiteFooter'

export const metadata = {
  title: 'How it works — Filmo',
  description:
    'How Filmo turns a URL into a finished launch video: it reads your product on NVIDIA Nemotron, plans the cut, fills your real facts into a curated library of designer-made motion patterns, and renders a real MP4 with Remotion.',
}

export default function HowItWorksPage() {
  return (
    <div className="landing-dark min-h-screen">
      <FloatingNav />

      {/* Page header — clears the floating nav and introduces the explainer. */}
      <header className="surface-dots-dark relative overflow-hidden border-b border-[#D4E2FB]/60">
        <div aria-hidden="true" className="stage-aura pointer-events-none absolute inset-0 z-0" />
        <div className="relative z-10 mx-auto max-w-3xl px-5 pb-16 pt-28 text-center sm:pt-36">
          <span className="eyebrow">How it works</span>
          <h1 className="section-title mt-4 sm:text-5xl sm:leading-[1.08]">
            From a link to a launch video.
          </h1>
          <p className="section-lede mx-auto max-w-xl text-lg">
            Paste your URL. Filmo reads your product on NVIDIA Nemotron, plans the cut, fills your
            real facts into a curated library of designer-made patterns, and renders a finished MP4.
          </p>
        </div>
      </header>

      {/* The point: the numbered pipeline steps. Badge suppressed — the page
          header above already shows the "How it works" pill. */}
      <HowItWorks showBadge={false} />
      {/* ONE credibility beat — why Filmo, not a random-pixel generator. */}
      <Differentiators />
      <ClosingCTA />
      <SiteFooter />
    </div>
  )
}
