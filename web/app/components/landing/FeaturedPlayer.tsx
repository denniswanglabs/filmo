'use client'

import { useEffect, useRef, useState } from 'react'
import { useReducedMotion } from 'framer-motion'

const POSTER = '/hero-demo-poster.jpg'

export default function FeaturedPlayer() {
  const reduced = useReducedMotion()
  const videoRef = useRef<HTMLVideoElement>(null)

  const [muted, setMuted] = useState(true)
  const [playing, setPlaying] = useState(false)

  useEffect(() => {
    if (reduced) return
    const el = videoRef.current
    if (!el) return

    const onPlaying = () => setPlaying(true)
    el.addEventListener('playing', onPlaying)

    void el.play()
      .then(() => setPlaying(true))
      .catch(() => {
        /* autoplay blocked — poster + play chip stay up */
      })

    return () => el.removeEventListener('playing', onPlaying)
  }, [reduced])

  function startPlayback() {
    const el = videoRef.current
    if (!el) return
    void el.play()
      .then(() => setPlaying(true))
      .catch(() => {})
  }

  function toggleSound() {
    const el = videoRef.current
    if (!el) return
    const next = !muted
    setMuted(next)
    el.muted = next
    if (!next) {
      void el.play()
        .then(() => setPlaying(true))
        .catch(() => {})
    }
  }

  const showPoster = !playing

  return (
    <div className="w-full">
      <div className="relative overflow-hidden rounded-3xl border border-[#D4E2FB] bg-white p-2.5 shadow-[0_40px_100px_-40px_rgba(30,58,120,0.35)] ring-1 ring-inset ring-[#EAF1FF]">
        <div className="relative aspect-video w-full overflow-hidden rounded-2xl bg-[#0B0F1A]">
          <img
            src={POSTER}
            alt=""
            className={`absolute inset-0 h-full w-full object-cover transition-opacity duration-500 ${
              showPoster ? 'opacity-100' : 'opacity-0'
            }`}
          />

          <video
            ref={videoRef}
            src="/hero-demo.mp4"
            poster={POSTER}
            autoPlay
            muted={muted}
            loop
            playsInline
            preload="metadata"
            className={`absolute inset-0 h-full w-full object-cover transition-opacity duration-500 ${
              showPoster ? 'opacity-0' : 'opacity-100'
            }`}
          />

          {showPoster && (
            <>
              <div
                aria-hidden="true"
                className="pointer-events-none absolute inset-0 bg-gradient-to-t from-[#0E1320]/50 via-transparent to-[#0E1320]/10"
              />
              <button
                type="button"
                onClick={startPlayback}
                aria-label="Play the featured launch cut Filmo produced"
                className="absolute inset-0 grid place-items-center"
              >
                <span className="grid h-16 w-16 place-items-center rounded-full bg-white/90 shadow-lg ring-1 ring-[#3B82F6]/40 backdrop-blur-sm transition hover:scale-105">
                  <svg viewBox="0 0 24 24" className="h-7 w-7 translate-x-[2px]" aria-hidden="true">
                    <path d="M8 5.5 L18 12 L8 18.5 Z" fill="#3B82F6" />
                  </svg>
                </span>
              </button>
            </>
          )}

          <button
            type="button"
            onClick={toggleSound}
            className="absolute bottom-3 right-3 z-10 inline-flex items-center gap-1.5 rounded-full border border-white/70 bg-white/80 px-3 py-1.5 text-xs font-medium text-[#0E1320] shadow-sm backdrop-blur-md transition hover:bg-white"
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
      </div>
    </div>
  )
}
