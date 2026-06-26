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
    'How Filmo turns a URL into a finished launch video: it reads your product, runs a Conversion Read, plans the cut, prices the job, and ships a real MP4.',
}

export default function HowItWorksPage() {
  return (
    <div className="landing-dark min-h-screen">
      <FloatingNav />

      {/* Page header — clears the floating nav and introduces the explainer. */}
      <header className="surface-dots-dark relative overflow-hidden border-b border-[#D4E2FB]/60">
        <div aria-hidden="true" className="stage-aura pointer-events-none absolute inset-0 z-0" />
        <div className="relative z-10 mx-auto max-w-3xl px-5 pb-16 pt-28 text-center sm:pt-36">
          <span className="inline-block rounded-full border border-amber-line bg-amber-soft px-3 py-1 text-xs font-medium text-[#2563EB]">
            How it works
          </span>
          <h1 className="mt-4 text-4xl font-semibold tracking-tight text-[#0E1320] sm:text-5xl">
            From a link to a launch video.
          </h1>
          <p className="mx-auto mt-4 max-w-xl text-lg text-[#5A6472]">
            Paste your URL and Filmo reads your real product, diagnoses how it converts,
            plans the cut, prices the job, and ships a finished MP4 — on autopilot.
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
