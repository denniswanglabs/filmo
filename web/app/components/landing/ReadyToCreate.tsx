'use client'

// Closing CTA band — a full-width deep-navy stripe at the end of the page with a
// big "Ready to create?" and a blue-gradient "Start creating" button that scrolls
// to the composer (#start). Our take on Hera's dark closing band: deep navy
// (#0E1320) instead of black, a soft blue aura, a fine blue top edge, and a
// blue→bright-blue gradient button (NOT pink→orange).

import { Reveal, scrollToHeroComposer } from './Motion'

export default function ReadyToCreate() {
  // Smooth-scroll to the hero composer; falls back to the hash for reduced motion
  // / no-JS (the anchor href carries it too).
  function toComposer(e: React.MouseEvent<HTMLAnchorElement>) {
    if (document.getElementById('start')) {
      e.preventDefault()
      scrollToHeroComposer('smooth')
    }
  }

  return (
    <section className="relative overflow-hidden bg-[#0E1320] px-5 py-24 sm:py-28">
      {/* Fine blue top edge — echoes the panel lip on the dark band. */}
      <span
        aria-hidden="true"
        className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-[#3B82F6]/60 to-transparent"
      />
      {/* Soft blue aura behind the headline. */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute left-1/2 top-1/2 h-[420px] w-[680px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-[#3B82F6]/20 blur-[120px]"
      />

      <Reveal className="relative mx-auto max-w-2xl text-center">
          <span className="eyebrow eyebrow--dark">
            Your launch, on autopilot
          </span>
          <h2 className="mt-5 text-4xl font-semibold tracking-tight text-balance text-white sm:text-5xl">
            Ready to create?
          </h2>
          <p className="mx-auto mt-4 max-w-md text-pretty leading-relaxed text-[#AEB7C6]">
            Paste your URL and let Filmo read, plan, price, and produce a finished launch video.
          </p>

        <a
          href="/#start"
          onClick={toComposer}
          className="group mt-8 inline-flex items-center gap-2 rounded-full bg-gradient-to-r from-[#2563EB] to-[#5AA0FB] px-7 py-3.5 text-base font-semibold text-white shadow-[0_18px_50px_-16px_rgba(59,130,246,0.85)] transition hover:from-[#1D4FD8] hover:to-[#4E94F7] hover:shadow-[0_22px_60px_-16px_rgba(59,130,246,1)] active:scale-[0.99]"
        >
          Build
          <svg
            viewBox="0 0 24 24"
            className="h-4 w-4 transition-transform duration-300 group-hover:translate-x-0.5"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <path d="M5 12 H19" />
            <path d="M13 6 L19 12 L13 18" />
          </svg>
        </a>
      </Reveal>
    </section>
  )
}
