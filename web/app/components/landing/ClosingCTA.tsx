'use client'

import { useRouter } from 'next/navigation'
import { Reveal } from './Motion'

// Closing band: a light-blue panel that drives the visitor to the hero composer.
// Lives on /how-it-works, so the CTA routes back to the landing's composer
// (/#start) rather than scrolling within this page.
export default function ClosingCTA() {
  const router = useRouter()

  function jumpToComposer() {
    router.push('/#start')
  }

  return (
    <section className="panel panel--lit px-5 py-20 sm:py-24">
      {/* Blue glass top edge — our signature on the rounded panel lip. */}
      <span aria-hidden="true" className="panel__edge" />
      <div className="mx-auto max-w-5xl">
        <Reveal className="stage-aura overflow-hidden rounded-2xl border border-amber-line bg-amber-soft px-6 py-14 text-center shadow-[0_30px_80px_-34px_rgba(59,130,246,0.35)] sm:px-12 sm:py-16">
          <span className="inline-block rounded-full border border-amber-line bg-white px-3 py-1 text-xs font-medium text-[#2563EB]">
            Your launch is one link away
          </span>
          <h2 className="mx-auto mt-4 max-w-xl text-3xl font-semibold tracking-tight text-[#0E1320] sm:text-4xl">
            Paste your URL. Get the video that sells it.
          </h2>
          <p className="mx-auto mt-3 max-w-xl text-[#5A6472]">
            Filmo reads your product, plans the cut, prices the job, and ships a finished MP4.
          </p>
          <button
            type="button"
            onClick={jumpToComposer}
            className="mt-8 rounded-xl bg-amber px-6 py-3 font-semibold text-white shadow-[0_10px_30px_-10px_rgba(59,130,246,0.6)] transition hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber/40 focus-visible:ring-offset-2"
          >
            Start with your URL
          </button>
        </Reveal>
      </div>
    </section>
  )
}
