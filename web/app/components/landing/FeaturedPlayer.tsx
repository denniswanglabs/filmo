'use client'

// Featured "watch it" player — a single hero cut (stripe.mp4) that autoplays
// muted + looping, with a launch-video TIMELINE below it: a row of chapter pills
// (Intro · Hook · Feature · Proof · Close), a playhead line that tracks the
// video's currentTime, a decorative waveform strip, and a "Tap for sound" toggle.
//
// Our take vs. Hera's onboarding frame: white + light-blue surface, our blue
// (#3B82F6) active pill instead of red, a different beat set, and a glass frame.
// Reduced-motion safe: when the user opts out we don't autoplay or raf-animate;
// the playhead snaps to the static first chapter and the video stays paused on
// its poster until the visitor presses play via the sound toggle.

import { useEffect, useRef, useState } from 'react'
import { useReducedMotion } from 'framer-motion'

// Launch-video beats. Each pill owns a proportional slice of the timeline; the
// active pill is whichever slice the playhead is currently inside.
const CHAPTERS = ['Intro', 'Hook', 'Feature', 'Proof', 'Close'] as const

// Decorative waveform — a fixed set of bar heights (0..1). Static + deterministic
// so SSR and client render identically. Drawn as an inline SVG strip.
const WAVE = [
  0.3, 0.55, 0.42, 0.7, 0.5, 0.85, 0.62, 0.4, 0.74, 0.5, 0.92, 0.66, 0.48, 0.8,
  0.58, 0.38, 0.7, 0.52, 0.88, 0.6, 0.44, 0.76, 0.54, 0.34, 0.68, 0.5, 0.82,
  0.6, 0.46, 0.72, 0.56, 0.4, 0.78, 0.52, 0.9, 0.64, 0.42, 0.7, 0.5, 0.6,
]

export default function FeaturedPlayer() {
  const reduced = useReducedMotion()
  const videoRef = useRef<HTMLVideoElement>(null)
  const rafRef = useRef<number | null>(null)

  // 0..1 position of the playhead across the whole timeline.
  const [progress, setProgress] = useState(0)
  const [muted, setMuted] = useState(true)

  // Drive the playhead from the video clock via requestAnimationFrame (smoother
  // than `timeupdate`, which only fires ~4x/s). Skipped under reduced motion.
  useEffect(() => {
    if (reduced) return
    const el = videoRef.current
    if (!el) return

    const tick = () => {
      const d = el.duration
      if (d && Number.isFinite(d) && d > 0) {
        setProgress(Math.min(1, el.currentTime / d))
      }
      rafRef.current = requestAnimationFrame(tick)
    }
    rafRef.current = requestAnimationFrame(tick)
    return () => {
      if (rafRef.current != null) cancelAnimationFrame(rafRef.current)
    }
  }, [reduced])

  // Autoplay the muted loop once mounted (motion on). Reduced motion: stay on
  // the poster until the visitor opts in via the sound toggle.
  useEffect(() => {
    if (reduced) return
    const el = videoRef.current
    if (!el) return
    void el.play().catch(() => {
      /* autoplay blocked — poster stays; sound toggle will start it */
    })
  }, [reduced])

  // Which chapter slice the playhead sits in (0..CHAPTERS.length-1).
  const activeIndex = Math.min(CHAPTERS.length - 1, Math.floor(progress * CHAPTERS.length))

  function toggleSound() {
    const el = videoRef.current
    if (!el) return
    const next = !muted
    setMuted(next)
    el.muted = next
    if (!next) {
      // Unmuting implies the visitor wants to watch — make sure it's playing.
      void el.play().catch(() => {})
    }
  }

  return (
    <div className="mx-auto max-w-3xl">
      {/* Glass frame around the featured cut. */}
      <div className="relative overflow-hidden rounded-3xl border border-[#D4E2FB] bg-white p-2.5 shadow-[0_40px_100px_-40px_rgba(30,58,120,0.35)] ring-1 ring-inset ring-[#EAF1FF]">
        <div className="relative overflow-hidden rounded-2xl bg-[#F5F8FF]">
          <video
            ref={videoRef}
            src="/examples/stripe.mp4"
            poster="/examples/stripe.jpg"
            muted={muted}
            loop
            playsInline
            preload="metadata"
            className="aspect-video w-full object-cover"
          />

          {/* "Tap for sound" toggle, bottom-right over the frame. */}
          <button
            type="button"
            onClick={toggleSound}
            className="absolute bottom-3 right-3 inline-flex items-center gap-1.5 rounded-full border border-white/70 bg-white/80 px-3 py-1.5 text-xs font-medium text-[#0E1320] shadow-sm backdrop-blur-md transition hover:bg-white"
          >
            <span
              aria-hidden="true"
              className={`grid h-4 w-4 place-items-center rounded-full ${
                muted ? 'bg-[#3B82F6]/15 text-[#3B82F6]' : 'bg-[#3B82F6] text-white'
              }`}
            >
              <svg viewBox="0 0 24 24" className="h-2.5 w-2.5" fill="currentColor" aria-hidden="true">
                <path d="M4 9 H8 L13 5 V19 L8 15 H4 Z" />
                {muted ? (
                  <path d="M16 9 L21 14 M21 9 L16 14" stroke="currentColor" strokeWidth="2" strokeLinecap="round" fill="none" />
                ) : (
                  <path d="M16 8 Q19 12 16 16" stroke="currentColor" strokeWidth="2" strokeLinecap="round" fill="none" />
                )}
              </svg>
            </span>
            {muted ? 'Tap for sound' : 'Sound on'}
          </button>
        </div>

        {/* TIMELINE ----------------------------------------------------------- */}
        <div className="px-2.5 pb-1.5 pt-4 sm:px-3">
          {/* Chapter pills */}
          <div className="flex flex-wrap items-center gap-1.5">
            {CHAPTERS.map((label, i) => {
              const active = i === activeIndex
              const past = i < activeIndex
              return (
                <span
                  key={label}
                  className={`rounded-full px-3 py-1 text-xs font-medium transition-colors duration-200 ${
                    active
                      ? 'bg-[#3B82F6] text-white shadow-[0_6px_16px_-6px_rgba(59,130,246,0.7)]'
                      : past
                        ? 'bg-[#E8F0FF] text-[#2563EB]'
                        : 'bg-[#F2F6FF] text-[#9AA6B8]'
                  }`}
                >
                  {label}
                </span>
              )
            })}
            <span className="ml-auto font-mono text-[11px] tabular-nums text-[#9AA6B8]">
              {String(activeIndex + 1).padStart(2, '0')} / {String(CHAPTERS.length).padStart(2, '0')}
            </span>
          </div>

          {/* Playhead track + moving line */}
          <div className="relative mt-3 h-1.5 w-full overflow-hidden rounded-full bg-[#EAF1FF]">
            <div
              className="absolute inset-y-0 left-0 rounded-full bg-gradient-to-r from-[#7DAEFB] to-[#3B82F6]"
              style={{ width: `${Math.max(0, Math.min(100, progress * 100))}%` }}
            />
          </div>
          {/* Playhead knob */}
          <div className="relative h-0">
            <span
              aria-hidden="true"
              className="absolute -top-[7px] z-10 h-2.5 w-2.5 -translate-x-1/2 rounded-full border-2 border-white bg-[#3B82F6] shadow-[0_2px_8px_rgba(59,130,246,0.6)]"
              style={{ left: `${Math.max(0, Math.min(100, progress * 100))}%` }}
            />
          </div>

          {/* Waveform strip (decorative). */}
          <svg
            viewBox="0 0 400 28"
            preserveAspectRatio="none"
            className="mt-3 h-7 w-full"
            aria-hidden="true"
          >
            {WAVE.map((h, i) => {
              const x = (i / WAVE.length) * 400
              const barH = 4 + h * 20
              const lit = i / WAVE.length <= progress
              return (
                <rect
                  key={i}
                  x={x}
                  y={(28 - barH) / 2}
                  width={400 / WAVE.length - 2.5}
                  height={barH}
                  rx={1.5}
                  fill={lit ? '#3B82F6' : '#D4E2FB'}
                  fillOpacity={lit ? 0.85 : 0.7}
                />
              )
            })}
          </svg>
        </div>
      </div>
    </div>
  )
}
