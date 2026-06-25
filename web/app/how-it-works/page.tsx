// /how-it-works — the marketing + explainer story, moved off the minimal landing.
// Renders the same sections (the Conversion Read explainer, how-it-works steps,
// differentiators, use cases, parallax columns, closing CTA) on the white +
// light-blue stage, with the floating nav and footer. Nothing was lost — it just
// lives here now. The landing stays video-forward.

import FloatingNav from '../components/landing/FloatingNav'
import TrustBar from '../components/landing/TrustBar'
import HowItWorks from '../components/landing/HowItWorks'
import Differentiators from '../components/landing/Differentiators'
import ParallaxColumns from '../components/landing/ParallaxColumns'
import UseCases from '../components/landing/UseCases'
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

      {/* The full explainer + marketing story, moved off the landing. */}
      <TrustBar />
      <HowItWorks />
      <Differentiators />
      {/* THE showpiece: parallax drifting columns of the real Luceo films. */}
      <ParallaxColumns />
      <UseCases />
      <ClosingCTA />
      <SiteFooter />
    </div>
  )
}
