'use client'

import { useRef, useState } from 'react'

// The big autoplaying hero/demo video — a real Filmo-produced launch cut (Stripe).
// Browsers only autoplay muted, so it starts muted + looping; a clear overlaid
// control lets visitors unmute to hear the voiceover.
export default function HeroDemoVideo() {
  const videoRef = useRef<HTMLVideoElement>(null)
  const [muted, setMuted] = useState(true)

  function toggleSound() {
    const v = videoRef.current
    if (!v) return
    const next = !v.muted
    v.muted = next
    // A user gesture lets us (re)start playback with sound on some browsers.
    if (!next) void v.play().catch(() => {})
    setMuted(next)
  }

  return (
    <figure className="mx-auto mt-10 w-full max-w-3xl sm:mt-12">
      <div className="group relative overflow-hidden rounded-2xl border border-[#D4E2FB] bg-white shadow-[0_40px_120px_-40px_rgba(30,58,120,0.32)] ring-1 ring-inset ring-[#EAF1FF] sm:rounded-3xl">
        <video
          ref={videoRef}
          className="block aspect-video w-full bg-white"
          src="/hero-demo.mp4"
          poster="/hero-demo-poster.jpg"
          autoPlay
          muted
          loop
          playsInline
          preload="metadata"
        />

        {/* Tap-to-unmute control — overlaid bottom-right, clearly labeled. */}
        <button
          type="button"
          onClick={toggleSound}
          aria-pressed={!muted}
          aria-label={muted ? 'Unmute — tap for sound' : 'Mute video'}
          className="absolute bottom-3 right-3 inline-flex items-center gap-2 rounded-full border border-white/60 bg-[#0E1320]/70 px-3.5 py-2 text-sm font-medium text-white shadow-lg backdrop-blur transition hover:bg-[#0E1320]/85 active:scale-[0.97] sm:bottom-4 sm:right-4"
        >
          {muted ? (
            // Muted speaker (with an X)
            <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
              <path d="M4 9v6h4l5 4V5L8 9H4Z" strokeLinejoin="round" />
              <path d="M17 9l4 4M21 9l-4 4" strokeLinecap="round" />
            </svg>
          ) : (
            // Speaker with sound waves
            <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
              <path d="M4 9v6h4l5 4V5L8 9H4Z" strokeLinejoin="round" />
              <path d="M16.5 8.5a5 5 0 0 1 0 7M19 6a8.5 8.5 0 0 1 0 12" strokeLinecap="round" />
            </svg>
          )}
          <span className="whitespace-nowrap">{muted ? 'Tap for sound' : 'Sound on'}</span>
        </button>
      </div>
      <figcaption className="mt-3 text-center text-sm text-[#8A94A6]">
        A real launch video Filmo produced — Stripe, end to end.
      </figcaption>
    </figure>
  )
}
