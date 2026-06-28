'use client'

// "Built on Luceo Studio" attribution — REAL Luceo launch films. Replaces the
// abstract Showcase. Each card hover-plays a muted, looping 16:9 clip. Captions
// describe what each film SHOWS / its craft — these are Luceo's films, NOT Walk
// Studio customers.

import { useRef } from 'react'
import { Reveal, RevealGroup, RevealItem, SlidingPanel } from './Motion'

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
      className="group overflow-hidden rounded-2xl border border-[#D4E2FB] bg-white shadow-[0_24px_60px_-34px_rgba(30,58,120,0.22)] ring-1 ring-inset ring-[#EAF1FF] transition hover:-translate-y-0.5 hover:border-[#B9D2F8] hover:shadow-[0_28px_70px_-34px_rgba(30,58,120,0.28)]"
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
          className="aspect-video w-full bg-[#F5F8FF] object-cover"
        />
        {/* Play affordance — fades out on hover. */}
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 grid place-items-center transition-opacity duration-300 group-hover:opacity-0"
        >
          <span className="grid h-12 w-12 place-items-center rounded-full bg-white/70 ring-1 ring-[#3B82F6]/40 backdrop-blur-sm">
            <svg viewBox="0 0 24 24" className="h-5 w-5 translate-x-[1px]" aria-hidden="true">
              <path d="M8 5.5 L18 12 L8 18.5 Z" fill="#3B82F6" fillOpacity="1" />
            </svg>
          </span>
        </div>
      </div>
      <figcaption className="p-5 sm:p-6">
        <p className="font-semibold tracking-tight text-[#0E1320]">{film.title}</p>
        <p className="mt-1.5 text-sm leading-relaxed text-[#5A6472]">{film.descriptor}</p>
      </figcaption>
    </figure>
  )
}

export default function LuceoShowcase() {
  return (
    <SlidingPanel id="luceo" className="panel panel--stage px-5 py-20 sm:py-24">
      <div className="mx-auto max-w-5xl">
        {/* Section header */}
        <Reveal className="mx-auto max-w-xl text-center">
          <span className="eyebrow">The taste behind the engine</span>
          <h2 className="section-title mt-4">
            Built on Luceo Studio&rsquo;s launch films.
          </h2>
          <p className="section-lede mx-auto max-w-lg">
            Filmo takes its cues from the curated film library of Luceo Studio — a real
            launch-film studio. Every generated cut inherits that craft: deliberate pacing, kinetic
            typography, and a studio&rsquo;s eye for making a product feel inevitable.
          </p>
        </Reveal>

        {/* Film cards */}
        <RevealGroup className="mt-12 grid gap-6 sm:grid-cols-2 lg:grid-cols-2">
          {FILMS.map((film, i) => (
            <RevealItem key={film.slug} index={i}>
              <VideoCard film={film} />
            </RevealItem>
          ))}
        </RevealGroup>

        {/* Attribution */}
        <p className="mt-10 text-center text-sm text-[#5A6472]">
          <a
            href="https://luceostudio.com"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 font-medium text-[#2563EB] hover:underline"
          >
            Films by Luceo Studio
            <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M7 17 L17 7" />
              <path d="M8 7 H17 V16" />
            </svg>
          </a>
        </p>
      </div>
    </SlidingPanel>
  )
}
