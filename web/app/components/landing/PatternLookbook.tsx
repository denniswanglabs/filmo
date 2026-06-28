'use client'

import { Reveal, RevealGroup, RevealItem } from './Motion'
import catalog from '../../_data/patterns.catalog.json'

interface Pattern {
  id: string
  name: string
  whenToUse: string
}

const PATTERNS: readonly Pattern[] = (catalog.patterns as Pattern[]).map((p) => ({
  id: p.id,
  name: p.name,
  whenToUse: p.whenToUse,
}))

const CORE_COUNT = 4
const CORE_PATTERNS = PATTERNS.slice(0, CORE_COUNT)
const MORE_PATTERNS = PATTERNS.slice(CORE_COUNT)

function PatternCard({ pattern }: { pattern: Pattern }) {
  return (
    <figure className="group overflow-hidden rounded-2xl border border-[#D4E2FB] bg-white shadow-[0_24px_60px_-34px_rgba(30,58,120,0.22)] ring-1 ring-inset ring-[#EAF1FF] transition hover:-translate-y-0.5 hover:border-[#B9D2F8] hover:shadow-[0_28px_70px_-34px_rgba(30,58,120,0.28)]">
      <div className="relative">
        <img
          src={`/lookbook/${pattern.id}.png`}
          alt={`${pattern.name} pattern example`}
          width={1200}
          height={675}
          loading="lazy"
          decoding="async"
          className="aspect-video w-full bg-[#F5F8FF] object-cover"
        />
      </div>
      <figcaption className="p-5 sm:p-6">
        <p className="font-semibold tracking-tight text-[#0E1320]">{pattern.name}</p>
        <p className="mt-1.5 text-sm leading-relaxed text-[#5A6472]">{pattern.whenToUse}</p>
      </figcaption>
    </figure>
  )
}

export default function PatternLookbook() {
  return (
    <section id="lookbook" className="panel panel--dotted scroll-mt-[120px] px-5 py-20 sm:py-24">
      <span aria-hidden="true" className="panel__edge" />
      <div className="mx-auto max-w-5xl">
        <Reveal className="mx-auto max-w-xl text-center">
          <span className="eyebrow">The curation</span>
          <h2 className="section-title mt-4">Curated, not improvised.</h2>
          <p className="section-lede mx-auto max-w-lg">
            Every Filmo video is assembled from a hand-curated library of
            designer-quality scene patterns &mdash; distilled from our own Luceo
            Studio launch films, below. The AI picks the right pattern for your
            real data; it never free-styles slop.
          </p>
          <p className="mt-3 text-sm font-medium tracking-wide text-[#3B82F6]">
            {PATTERNS.length} patterns · zero improvisation
          </p>
        </Reveal>

        <RevealGroup className="mt-12 grid gap-6 sm:grid-cols-2 lg:grid-cols-2">
          {CORE_PATTERNS.map((pattern, i) => (
            <RevealItem key={pattern.id} index={i}>
              <PatternCard pattern={pattern} />
            </RevealItem>
          ))}
        </RevealGroup>

        {MORE_PATTERNS.length > 0 && (
          <Reveal className="mt-10">
            <details className="group rounded-2xl border border-[#D4E2FB] bg-white/80 ring-1 ring-inset ring-[#EAF1FF]">
              <summary className="cursor-pointer list-none px-5 py-4 text-center text-sm font-semibold text-[#0E1320] marker:content-none sm:px-6">
                <span className="inline-flex items-center gap-2">
                  View all {PATTERNS.length} patterns
                  <svg
                    viewBox="0 0 24 24"
                    className="h-4 w-4 text-[#5A6472] transition group-open:rotate-180"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    aria-hidden="true"
                  >
                    <path d="M6 9 L12 15 L18 9" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </span>
              </summary>
              <div className="border-t border-[#EAF1FF] px-5 pb-6 pt-2 sm:px-6">
                <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
                  {MORE_PATTERNS.map((pattern) => (
                    <PatternCard key={pattern.id} pattern={pattern} />
                  ))}
                </div>
              </div>
            </details>
          </Reveal>
        )}
      </div>
    </section>
  )
}
