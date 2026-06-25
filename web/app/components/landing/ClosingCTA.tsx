'use client'

import { Reveal } from './Motion'

// Closing band: a coral-tinted panel that drives the visitor back to the hero
// composer. The CTA smooth-scrolls to #start and focuses the URL field, guarded
// so server rendering never touches the DOM.
export default function ClosingCTA() {
  function jumpToComposer() {
    if (typeof document === 'undefined') return
    document.getElementById('start')?.scrollIntoView({ behavior: 'smooth' })
    document.getElementById('hero-url')?.focus()
  }

  return (
    <section className="px-5 py-20 sm:py-24">
      <div className="mx-auto max-w-5xl">
        <Reveal className="overflow-hidden rounded-2xl border border-amber/15 bg-amber/5 px-6 py-14 text-center shadow-[0_18px_50px_-20px_rgba(20,23,28,0.25)] sm:px-12 sm:py-16">
          <span className="inline-block rounded-full border border-amber/20 bg-amber/10 px-3 py-1 text-xs font-medium text-amber">
            Your launch is one link away
          </span>
          <h2 className="mx-auto mt-4 max-w-xl text-3xl font-semibold tracking-tight text-ink sm:text-4xl">
            Paste your URL. Get the video that sells it.
          </h2>
          <p className="mx-auto mt-3 max-w-xl text-slate-500">
            Filmo reads your product, plans the cut, prices the job, and ships a finished MP4.
          </p>
          <button
            type="button"
            onClick={jumpToComposer}
            className="mt-8 rounded-xl bg-amber px-6 py-3 font-semibold text-white transition hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber/40 focus-visible:ring-offset-2"
          >
            Start with your URL
          </button>
        </Reveal>
      </div>
    </section>
  )
}
