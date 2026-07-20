'use client'

import { useRouter } from 'next/navigation'
import { Reveal } from './Motion'

// Closing band: a light-blue panel that drives the visitor to the composer.
// Lives on /how-it-works, so the CTA leaves this page for it. The composer is
// the studio's now, not the landing's — `/?new=1` asks `/` for that surface
// specifically, which resolves to the sign-in gate when signed out and to the
// "New film" stage when signed in. (Bare `/` would open their most recent film,
// and `/#start` was the retired landing's composer anchor.)
export default function ClosingCTA() {
  const router = useRouter()

  function jumpToComposer() {
    router.push('/?new=1')
  }

  return (
    <section className="panel panel--lit px-5 py-20 sm:py-24">
      {/* Blue glass top edge — our signature on the rounded panel lip. */}
      <span aria-hidden="true" className="panel__edge" />
      <div className="mx-auto max-w-5xl">
        <Reveal className="stage-aura overflow-hidden rounded-2xl border border-amber-line bg-amber-soft px-6 py-14 text-center shadow-[0_30px_80px_-34px_rgba(59,130,246,0.35)] sm:px-12 sm:py-16">
          <span className="inline-block rounded-full border border-amber-line bg-white px-3 py-1 text-xs font-medium uppercase tracking-[0.1em] text-[#2563EB]">
            Your launch is one link away
          </span>
          <h2 className="section-title mx-auto mt-4 max-w-xl">
            Paste your URL. Get the video that sells it.
          </h2>
          <p className="section-lede mx-auto max-w-xl">
            Filmo reads your product, plans the cut, prices the job, and ships a finished MP4.
          </p>
          <button
            type="button"
            onClick={jumpToComposer}
            className="mt-8 rounded-xl bg-amber px-6 py-3 font-semibold text-white shadow-[0_10px_30px_-10px_rgba(59,130,246,0.6)] transition hover:opacity-90 active:scale-[0.99] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber/40 focus-visible:ring-offset-2"
          >
            Start with your URL
          </button>
        </Reveal>
      </div>
    </section>
  )
}
