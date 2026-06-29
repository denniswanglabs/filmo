'use client'

import { useRef } from 'react'
import { Reveal, RevealGroup, RevealItem, SlidingPanel } from './Motion'
import FeaturedPlayer from './FeaturedPlayer'
import PoweredBy from './PoweredBy'

interface Card {
  slug: string
  src: string
  poster: string
  brand: string
  sourceUrl: string
  descriptor: string
}

const BRAND: Record<string, { logo: string; tint: string }> = {
  'Y Combinator': { logo: '/examples/logos/ycombinator.svg', tint: '#FFF4EE' },
  Linear: { logo: '/examples/logos/linear.svg', tint: '#F2F3FD' },
  Stripe: { logo: '/examples/logos/stripe.svg', tint: '#F2F1FF' },
}

const CARDS: readonly Card[] = [
  {
    slug: 'ycombinator-wide',
    src: '/examples/ycombinator.mp4',
    poster: '/examples/ycombinator.jpg',
    brand: 'Y Combinator',
    sourceUrl: 'https://www.ycombinator.com',
    descriptor: 'A launch story for YC, read from the live site.',
  },
  {
    slug: 'linear-wide',
    src: '/examples/linear.mp4',
    poster: '/examples/linear.jpg',
    brand: 'Linear',
    sourceUrl: 'https://linear.app',
    descriptor: 'Build-velocity teaser grounded in the real UI.',
  },
  {
    slug: 'stripe-wide',
    src: '/examples/stripe.mp4',
    poster: '/examples/stripe.jpg',
    brand: 'Stripe',
    sourceUrl: 'https://stripe.com',
    descriptor: 'A payments story, planned and produced on autopilot.',
  },
]

function GalleryCard({ card }: { card: Card }) {
  const videoRef = useRef<HTMLVideoElement>(null)

  function play() {
    const el = videoRef.current
    if (!el) return
    void el.play().catch(() => {})
  }

  function reset() {
    const el = videoRef.current
    if (!el) return
    el.pause()
    el.currentTime = 0
  }

  function remix() {
    if (typeof window === 'undefined') return
    window.dispatchEvent(
      new CustomEvent('filmo:seed-composer', { detail: { url: card.sourceUrl } }),
    )
  }

  function watch() {
    if (typeof window === 'undefined') return
    window.open(card.src, '_blank', 'noopener,noreferrer')
  }

  const brand = BRAND[card.brand]

  return (
    <figure
      onMouseEnter={play}
      onMouseLeave={reset}
      className="group relative block aspect-video w-full overflow-hidden bg-white"
    >
      <div
        aria-hidden="true"
        className="absolute inset-0 grid place-items-center"
        style={{ backgroundColor: brand?.tint ?? '#F6F8FC' }}
      >
        {brand && (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={brand.logo}
            alt=""
            className="w-[40%] max-w-[160px] object-contain opacity-90"
          />
        )}
      </div>

      <video
        ref={videoRef}
        src={card.src}
        poster={card.poster}
        muted
        loop
        playsInline
        preload="none"
        className="absolute inset-0 h-full w-full bg-[#F5F8FF] object-cover opacity-0 transition-opacity duration-500 group-hover:opacity-100"
      />

      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-x-0 bottom-0 h-1/2 bg-gradient-to-t from-[#0E1320]/55 via-[#0E1320]/10 to-transparent opacity-0 transition-opacity duration-500 group-hover:opacity-100"
      />

      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 grid place-items-center transition-opacity duration-300 group-hover:opacity-0"
      >
        <span className="grid h-14 w-14 place-items-center rounded-full bg-white/80 ring-1 ring-[#3B82F6]/40 backdrop-blur-sm">
          <svg viewBox="0 0 24 24" className="h-6 w-6 translate-x-[1px]" aria-hidden="true">
            <path d="M8 5.5 L18 12 L8 18.5 Z" fill="#3B82F6" />
          </svg>
        </span>
      </div>

      <figcaption className="absolute inset-x-0 bottom-0 flex items-end justify-between gap-3 p-4 sm:p-5">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-[#0E1320] transition-colors duration-500 group-hover:text-white group-hover:drop-shadow-sm sm:text-base">
            {card.brand}
          </p>
          <p className="mt-0.5 truncate text-xs text-[#5A6472] transition-colors duration-500 group-hover:text-white/80 sm:text-sm">
            {card.descriptor}
          </p>
        </div>
        <button
          type="button"
          onClick={remix}
          aria-label={`Remix the ${card.brand} cut — pre-fill the composer with ${card.sourceUrl}`}
          className="pointer-events-auto shrink-0 translate-y-2 rounded-full bg-white/90 px-3 py-1 text-xs font-medium text-[#3B82F6] opacity-0 shadow-sm backdrop-blur-sm transition-all duration-300 hover:bg-white focus-visible:translate-y-0 focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#3B82F6] group-hover:translate-y-0 group-hover:opacity-100"
        >
          Remix
        </button>
      </figcaption>

      <button
        type="button"
        onClick={watch}
        aria-label={`Watch the ${card.brand} cut`}
        className="pointer-events-auto absolute right-4 top-4 inline-flex items-center gap-1 rounded-full bg-white/85 px-2.5 py-1 text-[11px] font-medium text-[#0E1320] opacity-0 shadow-sm backdrop-blur-sm transition-opacity duration-300 hover:bg-white focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#3B82F6] group-hover:opacity-100"
      >
        <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-[#3B82F6]" />
        Watch
      </button>
    </figure>
  )
}

export default function Examples() {
  return (
    <SlidingPanel id="examples" className="panel panel--stage px-5 py-20 sm:py-24">
      <div className="mx-auto max-w-5xl">
        <Reveal className="mx-auto max-w-xl text-center">
          <span className="eyebrow">Proof gallery</span>
          <h2 className="section-title mt-4">Explore what it&rsquo;s made.</h2>
          <p className="section-lede mx-auto max-w-lg">
            Real cuts the pipeline produced end to end — read, planned, priced, and shipped.
            Press play below, or hover any card to watch it move.
          </p>
        </Reveal>

        <Reveal className="mt-8 flex justify-center">
          <PoweredBy compact />
        </Reveal>

        <Reveal className="mt-12">
          <FeaturedPlayer />
        </Reveal>

        <RevealGroup className="mt-8 grid grid-cols-1 gap-0 overflow-hidden rounded-2xl border border-[#D4E2FB] shadow-[0_30px_80px_-40px_rgba(30,58,120,0.32)] sm:rounded-3xl md:grid-cols-3">
          {CARDS.map((card, i) => (
            <RevealItem key={card.slug} index={i} className="block">
              <GalleryCard card={card} />
            </RevealItem>
          ))}
        </RevealGroup>
      </div>
    </SlidingPanel>
  )
}
