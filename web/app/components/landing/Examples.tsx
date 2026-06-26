'use client'

// "Explore what it's made." — the proof gallery: a featured "watch it" player up
// top, then a uniform, tightly packed wall of equal-size tiles (no gaps). Each
// tile hover-plays a muted, looping cut (onMouseEnter → play, onMouseLeave →
// pause + reset to the poster). The three real produced cuts are reused across
// six identical-size tiles — 3 across on desktop, 2 on mobile.
//
// Light editorial style on the white + light-blue stage; our blue (#3B82F6)
// accents, soft light-blue shadows, and a hover "remix" affordance — varied from
// Hera's "Explore and remix" so it reads as Filmo, not a clone.

import { useRef } from 'react'
import { Reveal, RevealGroup, RevealItem } from './Motion'
import FeaturedPlayer from './FeaturedPlayer'

interface Card {
  /** unique key */
  slug: string
  /** mp4 in /public/examples */
  src: string
  /** poster jpg in /public/examples */
  poster: string
  /** brand the cut was made for */
  brand: string
  /** the real source URL this cut was read from — seeds the composer on "Remix" */
  sourceUrl: string
  /** one-line descriptor */
  descriptor: string
  /** grid placement — varies the masonry rhythm */
  span: string
  /** card height tier (drives the varied wall) */
  height: string
}

// Resting-state brand logos (Simple Icons, CC0) keyed by brand. The logo is the
// poster at rest; the video fades in over it on hover. `tint` is a very subtle
// brand-tinted wash behind the mark so the white tiles don't read flat.
const BRAND: Record<string, { logo: string; tint: string }> = {
  Notion: { logo: '/examples/logos/notion.svg', tint: '#F6F8FC' },
  Linear: { logo: '/examples/logos/linear.svg', tint: '#F2F3FD' },
  Stripe: { logo: '/examples/logos/stripe.svg', tint: '#F2F1FF' },
}

// Six tiles drawn from the three real cuts — all identical size in a packed wall.
const CARDS: readonly Card[] = [
  {
    slug: 'notion-tall',
    src: '/examples/notion.mp4',
    poster: '/examples/notion.jpg',
    brand: 'Notion',
    sourceUrl: 'https://notion.so',
    descriptor: 'Activity-demo launch cut, read from the live product.',
    span: 'sm:col-span-3',
    height: 'h-[260px] sm:h-[420px]',
  },
  {
    slug: 'linear-wide',
    src: '/examples/linear.mp4',
    poster: '/examples/linear.jpg',
    brand: 'Linear',
    sourceUrl: 'https://linear.app',
    descriptor: 'Build-velocity teaser grounded in the real UI.',
    span: 'sm:col-span-3',
    height: 'h-[200px] sm:h-[200px]',
  },
  {
    slug: 'stripe-wide',
    src: '/examples/stripe.mp4',
    poster: '/examples/stripe.jpg',
    brand: 'Stripe',
    sourceUrl: 'https://stripe.com',
    descriptor: 'A payments story, planned and produced on autopilot.',
    span: 'sm:col-span-3',
    height: 'h-[200px] sm:h-[200px]',
  },
  {
    slug: 'notion-square',
    src: '/examples/notion.mp4',
    poster: '/examples/notion.jpg',
    brand: 'Notion',
    sourceUrl: 'https://notion.so',
    descriptor: 'A waitlist teaser scored to a beat.',
    span: 'sm:col-span-2',
    height: 'h-[220px] sm:h-[300px]',
  },
  {
    slug: 'stripe-square',
    src: '/examples/stripe.mp4',
    poster: '/examples/stripe.jpg',
    brand: 'Stripe',
    sourceUrl: 'https://stripe.com',
    descriptor: 'A 30-second hero loop for the launch page.',
    span: 'sm:col-span-2',
    height: 'h-[220px] sm:h-[300px]',
  },
  {
    slug: 'linear-square',
    src: '/examples/linear.mp4',
    poster: '/examples/linear.jpg',
    brand: 'Linear',
    sourceUrl: 'https://linear.app',
    descriptor: 'A Product Hunt cut built to win the day.',
    span: 'sm:col-span-2',
    height: 'h-[220px] sm:h-[300px]',
  },
]

/** A single masonry card: hover-to-play cover video + brand label + remix hint. */
function GalleryCard({ card }: { card: Card }) {
  const videoRef = useRef<HTMLVideoElement>(null)

  function play() {
    const el = videoRef.current
    if (!el) return
    void el.play().catch(() => {
      /* autoplay/permission edge — leave on poster */
    })
  }

  function reset() {
    const el = videoRef.current
    if (!el) return
    el.pause()
    el.currentTime = 0
  }

  // "Remix" — seed the landing composer with this cut's real source URL and bring
  // it into view/focus. Mirrors FloatingNav.jumpToComposer (scroll #start + focus
  // #hero-url); the URL is lifted into the composer's React state via a window
  // CustomEvent that page.tsx listens for (avoids DOM-pasting a controlled input).
  function remix() {
    if (typeof window === 'undefined') return
    window.dispatchEvent(
      new CustomEvent('filmo:seed-composer', { detail: { url: card.sourceUrl } }),
    )
  }

  // "Watch" — open this cut's mp4 in a new tab so a visitor can play it full-size.
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
      {/* Resting state: brand logo centered on a clean, faintly brand-tinted tile. */}
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

      {/* Hover state: the video fades in OVER the logo and plays. */}
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

      {/* Readability scrim along the bottom for the label — only over the playing video. */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-x-0 bottom-0 h-1/2 bg-gradient-to-t from-[#0E1320]/55 via-[#0E1320]/10 to-transparent opacity-0 transition-opacity duration-500 group-hover:opacity-100"
      />

      {/* Center play chip — fades out on hover. */}
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

      {/* Brand label — bottom-left, always visible. Dark over the resting logo
          tile, switches to white once the video fades in on hover. */}
      <figcaption className="absolute inset-x-0 bottom-0 flex items-end justify-between gap-3 p-4 sm:p-5">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-[#0E1320] transition-colors duration-500 group-hover:text-white group-hover:drop-shadow-sm sm:text-base">
            {card.brand}
          </p>
          <p className="mt-0.5 truncate text-xs text-[#5A6472] transition-colors duration-500 group-hover:text-white/80 sm:text-sm">
            {card.descriptor}
          </p>
        </div>
        {/* "Remix" affordance — slides up on hover. Seeds the composer with this
            cut's source URL. */}
        <button
          type="button"
          onClick={remix}
          aria-label={`Remix the ${card.brand} cut — pre-fill the composer with ${card.sourceUrl}`}
          className="pointer-events-auto shrink-0 translate-y-2 rounded-full bg-white/90 px-3 py-1 text-xs font-medium text-[#2563EB] opacity-0 shadow-sm backdrop-blur-sm transition-all duration-300 hover:bg-white focus-visible:translate-y-0 focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#3B82F6] group-hover:translate-y-0 group-hover:opacity-100"
        >
          Remix
        </button>
      </figcaption>

      {/* Top-right "watch" chip — appears on hover. Opens this cut's mp4 full-size. */}
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
    <section id="examples" className="panel panel--lit px-5 py-20 sm:py-24">
      {/* Blue glass top edge — our signature on the rounded panel lip. */}
      <span aria-hidden="true" className="panel__edge" />
      <div className="mx-auto max-w-5xl">
        {/* Section header */}
        <Reveal className="mx-auto max-w-xl text-center">
          <span className="inline-block rounded-full border border-amber-line bg-amber-soft px-3 py-1 text-xs font-medium text-[#2563EB]">
            Explore &amp; remix
          </span>
          <h2 className="mt-4 text-3xl font-semibold tracking-tight text-[#0E1320] sm:text-4xl">
            Explore what it&rsquo;s made.
          </h2>
          <p className="mx-auto mt-3 text-[#5A6472]">
            Real cuts the pipeline produced end to end — read, planned, priced, and shipped.
            Press play below, or hover any card to watch it move.
          </p>
        </Reveal>

        {/* Featured "watch it" player with a moving timeline. */}
        <Reveal className="mt-12">
          <FeaturedPlayer />
        </Reveal>

        {/* Uniform packed wall — equal-size tiles, flush (no gaps). */}
        <RevealGroup className="mt-8 grid grid-cols-2 gap-0 overflow-hidden rounded-3xl border border-[#D4E2FB] shadow-[0_30px_80px_-40px_rgba(30,58,120,0.32)] sm:grid-cols-3">
          {CARDS.map((card) => (
            <RevealItem key={card.slug} className="block">
              <GalleryCard card={card} />
            </RevealItem>
          ))}
        </RevealGroup>
      </div>
    </section>
  )
}
