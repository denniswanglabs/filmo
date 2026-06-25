'use client'

// "Built on Luceo Studio" attribution — REAL Luceo launch films. Replaces the
// abstract Showcase. Each card hover-plays a muted, looping 16:9 clip. Captions
// describe what each film SHOWS / its craft — these are Luceo's films, NOT Walk
// Studio customers.

import { useRef } from 'react'

interface Film {
  /** unique key */
  slug: string
  /** mp4 in /public/luceo */
  src: string
  /** poster jpg in /public/luceo */
  poster: string
  /** film title */
  title: string
  /** one-line descriptor (from Luceo's catalog) */
  descriptor: string
}

const FILMS: readonly Film[] = [
  {
    slug: 'smartbase',
    src: '/luceo/smartbase-launch-720.mp4',
    poster: '/luceo/smartbase-thumbnail.jpg',
    title: 'Smartbase',
    descriptor: 'Manufacturing AI — handwritten PO to ERP-ready row.',
  },
  {
    slug: 'kuli',
    src: '/luceo/kuli-launch-720.mp4',
    poster: '/luceo/kuli-thumbnail.jpg',
    title: 'Kuli',
    descriptor: 'AI-native influencer marketing — describe your ideal creator.',
  },
  {
    slug: 'benchling',
    src: '/luceo/benchling-launch-720.mp4',
    poster: '/luceo/benchling-thumbnail.jpg',
    title: 'Benchling',
    descriptor: 'AI-native R&D cloud for biotech.',
  },
  {
    slug: 'hero-loop',
    src: '/luceo/hero-loop-720.mp4',
    poster: '/luceo/hero-loop-poster.jpg',
    title: 'Studio reel',
    descriptor: 'The looping hero cut — kinetic typography and deliberate pacing.',
  },
]

/** A single film card: house card recipe wrapping a hover-to-play 16:9 video. */
function VideoCard({ film }: { film: Film }) {
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

  return (
    <figure
      onMouseEnter={play}
      onMouseLeave={reset}
      className="group overflow-hidden rounded-2xl border border-black/5 bg-white shadow-[0_18px_50px_-20px_rgba(20,23,28,0.25)] transition hover:border-black/10 hover:shadow-sm"
    >
      <div className="relative">
        <video
          ref={videoRef}
          src={film.src}
          poster={film.poster}
          muted
          loop
          playsInline
          preload="none"
          className="aspect-video w-full bg-ink object-cover"
        />
        {/* Play affordance — fades out on hover. */}
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 grid place-items-center transition-opacity duration-300 group-hover:opacity-0"
        >
          <span className="grid h-12 w-12 place-items-center rounded-full bg-white/20 ring-1 ring-white/50 backdrop-blur-sm">
            <svg viewBox="0 0 24 24" className="h-5 w-5 translate-x-[1px]" aria-hidden="true">
              <path d="M8 5.5 L18 12 L8 18.5 Z" fill="#FFFFFF" fillOpacity="0.95" />
            </svg>
          </span>
        </div>
      </div>
      <figcaption className="p-5">
        <p className="font-semibold text-ink">{film.title}</p>
        <p className="mt-1 text-sm text-slate-500">{film.descriptor}</p>
      </figcaption>
    </figure>
  )
}

export default function LuceoShowcase() {
  return (
    <section id="examples" className="bg-[#F7F8FA] px-5 py-20 sm:py-24">
      <div className="mx-auto max-w-5xl">
        {/* Section header */}
        <div className="mx-auto max-w-xl text-center">
          <span className="inline-block rounded-full border border-amber/20 bg-amber/5 px-3 py-1 text-xs font-medium text-amber">
            The taste behind the engine
          </span>
          <h2 className="mt-4 text-3xl font-semibold tracking-tight text-ink sm:text-4xl">
            Built on Luceo Studio&rsquo;s launch films.
          </h2>
          <p className="mx-auto mt-3 text-slate-500">
            Walk Studio takes its cues from the curated film library of Luceo Studio — a real
            launch-film studio. Every generated cut inherits that craft: deliberate pacing, kinetic
            typography, and a studio&rsquo;s eye for making a product feel inevitable.
          </p>
        </div>

        {/* Film cards */}
        <div className="mt-12 grid gap-6 sm:grid-cols-2 lg:grid-cols-2">
          {FILMS.map((film) => (
            <VideoCard key={film.slug} film={film} />
          ))}
        </div>

        {/* Attribution */}
        <p className="mt-10 text-center text-sm text-slate-500">
          <a
            href="https://www.youtube.com/@luceo-studio"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 font-medium text-amber hover:underline"
          >
            Films by Luceo Studio
            <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M7 17 L17 7" />
              <path d="M8 7 H17 V16" />
            </svg>
          </a>
        </p>
      </div>
    </section>
  )
}
