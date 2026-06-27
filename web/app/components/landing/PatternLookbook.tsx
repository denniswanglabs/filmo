'use client'

// The Pattern Lookbook — the curation moat made visible. Every Filmo video is
// assembled from a hand-curated library of designer-quality scene patterns,
// distilled from Luceo Studio's launch films (shown in the section directly
// below). This renders the catalog (the SAME patterns.catalog.json the Python
// assembler picks from) as a grid of real, rendered example tiles — proof the
// AI selects from a fixed set of beautiful layouts and never free-styles slop.
//
// Aesthetic + motion are kept in lockstep with LuceoShowcase: the same house
// card recipe (rounded-2xl, #D4E2FB border, soft navy shadow, inset ring), the
// same Reveal / RevealGroup / RevealItem / Parallax primitives, and the same
// blue-tinted eyebrow chip + section header.

import { Reveal, RevealGroup, RevealItem, Parallax } from './Motion'
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

/** A single pattern tile: house card recipe wrapping the 16:9 example still. */
function PatternCard({ pattern }: { pattern: Pattern }) {
  return (
    <figure className="group overflow-hidden rounded-2xl border border-[#D4E2FB] bg-white shadow-[0_24px_60px_-34px_rgba(30,58,120,0.22)] ring-1 ring-inset ring-[#EAF1FF] transition hover:border-[#B9D2F8]">
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
      <figcaption className="p-5">
        <p className="font-semibold text-[#0E1320]">{pattern.name}</p>
        <p className="mt-1 text-sm text-[#5A6472]">{pattern.whenToUse}</p>
      </figcaption>
    </figure>
  )
}

export default function PatternLookbook() {
  return (
    <section id="lookbook" className="panel panel--lit px-5 py-20 sm:py-24">
      {/* Blue glass top edge — our signature on the rounded panel lip. */}
      <span aria-hidden="true" className="panel__edge" />
      <div className="mx-auto max-w-5xl">
        {/* Section header */}
        <Reveal className="mx-auto max-w-xl text-center">
          <span className="inline-block rounded-full border border-amber-line bg-amber-soft px-3 py-1 text-xs font-medium text-[#2563EB]">
            The curation
          </span>
          <h2 className="mt-4 text-3xl font-semibold tracking-tight text-[#0E1320] sm:text-4xl">
            Curated, not improvised.
          </h2>
          <p className="mx-auto mt-3 text-[#5A6472]">
            Every Filmo video is assembled from a hand-curated library of
            designer-quality scene patterns &mdash; distilled from our own Luceo
            Studio launch films, below. The AI picks the right pattern for your
            real data; it never free-styles slop.
          </p>
        </Reveal>

        {/* Pattern cards — 3 cols desktop / 2 tablet / 1 mobile. */}
        <RevealGroup className="mt-12 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {PATTERNS.map((pattern, i) => (
            <RevealItem key={pattern.id} index={i}>
              <Parallax range={[10, -10]} scaleRange={[0.98, 1]}>
                <PatternCard pattern={pattern} />
              </Parallax>
            </RevealItem>
          ))}
        </RevealGroup>
      </div>
    </section>
  )
}
