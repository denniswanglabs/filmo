'use client'

// THE showpiece (Hera's "moving windows"): columns of rounded video cards that
// drift vertically at DIFFERENT rates as you scroll. Filled with the REAL Luceo
// films (duplicated so each column reads full), hover-to-play, on the dark stage.
//
// Motion contract (same as the rest of the landing):
//  - transform/opacity only (GPU-composited, 60fps target)
//  - gated on prefers-reduced-motion + client-mount, so SSR renders the rest
//    state and there's never a hydration mismatch. Reduced motion = static grid.

import {
  motion,
  useReducedMotion,
  useScroll,
  useTransform,
  type MotionValue,
} from 'framer-motion'
import { useEffect, useRef, useState } from 'react'
import { Reveal } from './Motion'

interface Film {
  slug: string
  src: string
  poster: string
  title: string
  descriptor: string
}

// Real Luceo launch films (mirrors LuceoShowcase). These are Luceo's films —
// the credibility behind Filmo's engine — not Walk Studio customers.
const FILMS: readonly Film[] = [
  {
    slug: 'smartbase',
    src: '/luceo/smartbase-launch-720.mp4',
    poster: '/luceo/smartbase-thumbnail.jpg',
    title: 'Smartbase',
    descriptor: 'Manufacturing AI launch',
  },
  {
    slug: 'kuli',
    src: '/luceo/kuli-launch-720.mp4',
    poster: '/luceo/kuli-thumbnail.jpg',
    title: 'Kuli',
    descriptor: 'AI-native influencer marketing',
  },
  {
    slug: 'benchling',
    src: '/luceo/benchling-launch-720.mp4',
    poster: '/luceo/benchling-thumbnail.jpg',
    title: 'Benchling',
    descriptor: 'AI-native R&D cloud',
  },
  {
    slug: 'hero-loop',
    src: '/luceo/hero-loop-720.mp4',
    poster: '/luceo/hero-loop-poster.jpg',
    title: 'Studio reel',
    descriptor: 'Kinetic typography cut',
  },
]

function useMounted() {
  const [mounted, setMounted] = useState(false)
  useEffect(() => setMounted(true), [])
  return mounted
}

/** One hover-to-play 16:9 card — dark glass tile that "pops" off the stage. */
function ColumnCard({ film }: { film: Film }) {
  const videoRef = useRef<HTMLVideoElement>(null)

  function play() {
    void videoRef.current?.play().catch(() => {
      /* autoplay edge — leave on poster */
    })
  }
  function reset() {
    const el = videoRef.current
    if (!el) return
    el.pause()
    el.currentTime = 0
  }

  return (
    <figure
      onMouseEnter={play}
      onMouseLeave={reset}
      className="group relative overflow-hidden rounded-2xl border border-white/10 bg-white/[0.04] shadow-[0_24px_60px_-24px_rgba(0,0,0,0.85)] ring-1 ring-inset ring-white/5 transition hover:border-white/20"
    >
      <video
        ref={videoRef}
        src={film.src}
        poster={film.poster}
        muted
        loop
        playsInline
        preload="none"
        className="aspect-video w-full bg-black object-cover"
      />
      {/* Play affordance — fades out on hover. */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 grid place-items-center transition-opacity duration-300 group-hover:opacity-0"
      >
        <span className="grid h-11 w-11 place-items-center rounded-full bg-white/15 ring-1 ring-white/40 backdrop-blur-sm">
          <svg viewBox="0 0 24 24" className="h-4 w-4 translate-x-[1px]" aria-hidden="true">
            <path d="M8 5.5 L18 12 L8 18.5 Z" fill="#FFFFFF" fillOpacity="0.95" />
          </svg>
        </span>
      </div>
      {/* Bottom label gradient. */}
      <figcaption className="pointer-events-none absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/70 to-transparent px-3.5 pb-3 pt-8">
        <p className="text-sm font-semibold text-white">{film.title}</p>
        <p className="text-xs text-slate-300">{film.descriptor}</p>
      </figcaption>
    </figure>
  )
}

/** A single drifting column. `y` is provided by the parent (scroll-mapped). */
function DriftColumn({
  films,
  y,
  className = '',
}: {
  films: readonly Film[]
  y: MotionValue<number> | number
  className?: string
}) {
  return (
    <motion.div
      style={{ y, willChange: 'transform' }}
      className={`flex w-full min-w-0 flex-col gap-5 ${className}`}
    >
      {films.map((film, i) => (
        <ColumnCard key={`${film.slug}-${i}`} film={film} />
      ))}
    </motion.div>
  )
}

// Build a full column from the films, offset so columns don't show the same
// film side-by-side, and duplicated so the column reads long enough to drift.
function columnFilms(offset: number): Film[] {
  const rotated = [...FILMS.slice(offset), ...FILMS.slice(0, offset)]
  return [...rotated, ...rotated]
}

export default function ParallaxColumns() {
  const reduced = useReducedMotion()
  const mounted = useMounted()
  const enabled = mounted && !reduced

  const ref = useRef<HTMLDivElement>(null)
  const { scrollYProgress } = useScroll({
    target: ref,
    offset: ['start end', 'end start'],
  })

  // Each column drifts a different distance/direction across the section's span.
  const yA = useTransform(scrollYProgress, [0, 1], [60, -120])
  const yB = useTransform(scrollYProgress, [0, 1], [-90, 90])
  const yC = useTransform(scrollYProgress, [0, 1], [40, -160])

  const colA = columnFilms(0)
  const colB = columnFilms(1)
  const colC = columnFilms(2)

  // Pinned-CTA action: smooth-scroll to the full Luceo examples section (#examples).
  function jumpToExamples() {
    if (typeof document === 'undefined') return
    document.getElementById('examples')?.scrollIntoView({ behavior: 'smooth' })
  }

  return (
    <section
      ref={ref}
      className="panel panel--dark relative px-5 py-24 sm:py-28"
    >
      {/* Blue glass top edge — our signature on the rounded panel lip. */}
      <span aria-hidden="true" className="panel__edge" />
      {/* Header */}
      <Reveal className="relative z-10 mx-auto mb-14 max-w-xl text-center">
        <span className="inline-block rounded-full border border-amber/30 bg-amber/10 px-3 py-1 text-xs font-medium text-[#6F9BFF]">
          Example outputs
        </span>
        <h2 className="mt-4 text-3xl font-semibold tracking-tight text-[#F2F4F7] sm:text-4xl">
          A gallery that moves like the films do.
        </h2>
        <p className="mx-auto mt-3 text-slate-400">
          Real launch films, drifting on the stage. Hover any card to watch it play.
        </p>
      </Reveal>

      {/* Stage: the columns clip themselves (inner overflow-hidden); the CTA is a
          sticky-centered sibling that PINS to the viewport center while the
          columns drift past it (Hera's centered "Browse templates" affordance,
          in our copy). The section root is NOT overflow-hidden so sticky works. */}
      <div className="relative mx-auto max-w-5xl">
        {/* Drifting columns. Fade-masked top & bottom so they bleed into the stage. */}
        <div className="mask-fade-y relative grid max-h-[78vh] grid-cols-2 gap-5 overflow-hidden lg:grid-cols-3">
          {enabled ? (
            <>
              <DriftColumn films={colA} y={yA} />
              <DriftColumn films={colB} y={yB} />
              <DriftColumn films={colC} y={yC} className="hidden lg:flex" />
            </>
          ) : (
            // Reduced motion / SSR: a calm static grid of the four films, no drift.
            <>
              <DriftColumn films={FILMS.slice(0, 2)} y={0} />
              <DriftColumn films={FILMS.slice(2, 4)} y={0} />
              <DriftColumn films={[FILMS[0], FILMS[3]]} y={0} className="hidden lg:flex" />
            </>
          )}
        </div>

        {/* Pinned center CTA. Lives in the stage so its sticky span is the column
            scroll; pointer-events:none lets hover reach the cards behind it, and
            the pill itself re-enables clicks. Smooth-scrolls to #examples. */}
        <div className="pointer-events-none absolute inset-0 z-20 flex justify-center">
          <div className="sticky top-1/2 -translate-y-1/2">
            <button
              type="button"
              onClick={jumpToExamples}
              className="pointer-events-auto inline-flex items-center gap-2 rounded-full border border-[#0052FF]/40 bg-[#0b0c0e]/75 px-5 py-2.5 text-sm font-medium text-slate-100 shadow-[0_12px_40px_-16px_rgba(0,82,255,0.6)] backdrop-blur-xl transition hover:border-[#0052FF]/70 hover:bg-[#0b0c0e]/90"
            >
              See every example
              <svg
                viewBox="0 0 24 24"
                className="h-3.5 w-3.5"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <path d="M5 12h14" />
                <path d="M13 6l6 6-6 6" />
              </svg>
            </button>
          </div>
        </div>
      </div>
    </section>
  )
}
