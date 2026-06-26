'use client'

// TRIAL — pinned scroll-intro hero (isolated at /trial; does not touch the live landing).
//  • Title starts HUGE + centered, then as you scroll the hero is PINNED (the page
//    doesn't move) while the title shrinks + lands in its final top-left slot and the
//    composer + the right-side "URL → film" visual reveal in. After ~1 viewport of
//    scroll the pin releases and the page scrolls normally.
//  • The big title's ENTRANCE uses the fancycomponents "Vertical Cut Reveal" pick.
//  • Reduced-motion: renders the settled hero in normal flow, no pin, no scrub.

import { useLayoutEffect, useRef, useState } from 'react'
import { motion, useScroll, useTransform, useReducedMotion } from 'framer-motion'
import VerticalCutReveal from '../components/fancy/VerticalCutReveal'

const TITLE = 'Your AI Product\nLaunch Producer'

// ───────────────────────── Right side: URL → film (looping) ─────────────────────────
function FilmTransform() {
  return (
    <div className="ft mx-auto w-full max-w-md">
      <div className="ft-card relative aspect-[4/3] w-full overflow-hidden rounded-2xl border border-[#D4E2FB] bg-white shadow-[0_30px_80px_-40px_rgba(30,58,120,0.35)]">
        {/* chrome bar */}
        <div className="flex items-center gap-2 border-b border-[#EAF1FF] bg-[#F7F9FC] px-3 py-2">
          <span className="h-2.5 w-2.5 rounded-full bg-[#CFE0FB]" />
          <span className="h-2.5 w-2.5 rounded-full bg-[#CFE0FB]" />
          <span className="h-2.5 w-2.5 rounded-full bg-[#CFE0FB]" />
          <span className="ml-2 inline-flex items-center rounded-md bg-white px-2 py-0.5 text-[10px] font-semibold text-[#5A6472] ring-1 ring-[#EAF1FF]">
            https://acme.com
          </span>
        </div>
        {/* stage: website layer + film layer crossfade */}
        <div className="relative h-full w-full">
          {/* WEBSITE layer */}
          <div className="ft-web absolute inset-0 p-4">
            <div className="mb-3 h-4 w-1/2 rounded bg-[#DCE9FF]" />
            <div className="mb-2 h-2.5 w-3/4 rounded bg-[#EAF1FF]" />
            <div className="mb-4 h-2.5 w-2/3 rounded bg-[#EAF1FF]" />
            <div className="grid grid-cols-3 gap-2">
              <div className="h-12 rounded-lg bg-[#3B82F6]/20" />
              <div className="h-12 rounded-lg bg-[#EAF1FF]" />
              <div className="h-12 rounded-lg bg-[#EAF1FF]" />
            </div>
          </div>
          {/* FILM layer */}
          <div className="ft-film absolute inset-0 grid place-items-center bg-[#0B0F1A]">
            <div aria-hidden className="absolute inset-x-0 top-0 flex justify-between px-2 py-1.5">
              {Array.from({ length: 9 }).map((_, i) => (
                <span key={i} className="h-2 w-2 rounded-[3px] bg-white/12" />
              ))}
            </div>
            <div aria-hidden className="absolute inset-x-0 bottom-0 flex justify-between px-2 py-1.5">
              {Array.from({ length: 9 }).map((_, i) => (
                <span key={i} className="h-2 w-2 rounded-[3px] bg-white/12" />
              ))}
            </div>
            <span className="grid h-14 w-14 place-items-center rounded-full bg-[#3B82F6] shadow-[0_8px_30px_-6px_rgba(59,130,246,0.7)]">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="white" aria-hidden>
                <path d="M8 5v14l11-7z" />
              </svg>
            </span>
            <div className="absolute bottom-7 left-6 right-6 h-1 overflow-hidden rounded-full bg-white/15">
              <span className="ft-scrub block h-full w-1/3 rounded-full bg-[#60A5FA]" />
            </div>
          </div>
          {/* blue scan line sweeping during the morph */}
          <span aria-hidden className="ft-scan absolute inset-x-0 h-[3px] bg-gradient-to-r from-transparent via-[#3B82F6] to-transparent" />
        </div>
      </div>
      <p className="mt-4 text-center text-sm font-medium text-[#5A6472]">
        Your site, read and reshot as a launch film.
      </p>

      <style jsx>{`
        /* ~6s loop: website holds, scan sweeps, film holds, scan sweeps back. */
        .ft-web {
          animation: ft-web 6s ease-in-out infinite;
        }
        .ft-film {
          opacity: 0;
          animation: ft-film 6s ease-in-out infinite;
        }
        .ft-scan {
          top: -10%;
          opacity: 0;
          animation: ft-scan 6s ease-in-out infinite;
        }
        .ft-scrub {
          animation: ft-scrub 2.4s ease-in-out infinite;
        }
        @keyframes ft-web {
          0%, 38% { opacity: 1; }
          50%, 88% { opacity: 0; }
          100% { opacity: 1; }
        }
        @keyframes ft-film {
          0%, 38% { opacity: 0; }
          50%, 88% { opacity: 1; }
          100% { opacity: 0; }
        }
        @keyframes ft-scan {
          0%, 36% { top: -10%; opacity: 0; }
          44% { opacity: 1; }
          50% { top: 100%; opacity: 0.2; }
          52%, 86% { top: 100%; opacity: 0; }
          92% { top: -10%; opacity: 1; }
          100% { top: -10%; opacity: 0; }
        }
        @keyframes ft-scrub {
          0% { transform: translateX(0); }
          100% { transform: translateX(200%); }
        }
        @media (prefers-reduced-motion: reduce) {
          .ft-web, .ft-film, .ft-scan, .ft-scrub { animation: none !important; }
          .ft-film { opacity: 1; }
          .ft-web { opacity: 0; }
        }
      `}</style>
    </div>
  )
}

// ───────────────────────── simplified composer (visual only) ─────────────────────────
function TrialComposer() {
  return (
    <form
      onSubmit={(e) => e.preventDefault()}
      className="mt-6 rounded-2xl border border-[#D4E2FB] bg-white p-6 shadow-[0_30px_80px_-30px_rgba(30,58,120,0.22)] ring-1 ring-inset ring-[#EAF1FF]"
    >
      <span className="mb-1.5 block text-sm font-medium text-[#0E1320]">Website URL</span>
      <div className="flex items-center rounded-lg border border-[#D4E2FB] bg-[#F8FAFF]">
        <span className="select-none pl-3.5 pr-1 text-[#9AA6B8]">https://</span>
        <input
          placeholder="acme.com"
          className="w-full rounded-lg bg-transparent py-3 pr-3.5 text-[#0E1320] outline-none placeholder:text-[#9AA6B8]"
        />
      </div>
      <button className="mt-5 w-full rounded-xl bg-amber py-3 font-semibold text-white shadow-[0_10px_30px_-10px_rgba(59,130,246,0.6)] transition hover:opacity-90">
        Build
      </button>
    </form>
  )
}

function HeroContent({ titleNode, revealStyle }: { titleNode: React.ReactNode; revealStyle?: React.CSSProperties }) {
  return (
    <div className="mx-auto grid w-full max-w-6xl grid-cols-1 items-center gap-10 px-6 md:grid-cols-[1.05fr_0.95fr]">
      <div>
        {titleNode}
        <motion.div style={revealStyle as object}>
          <p className="mt-4 max-w-md text-lg text-[#5A6472]">
            Paste your URL. Filmo reads your real product, diagnoses how it converts, and ships a
            finished launch video — planned, priced, and produced on autopilot.
          </p>
          <TrialComposer />
        </motion.div>
      </div>
      <motion.div style={revealStyle as object}>
        <FilmTransform />
      </motion.div>
    </div>
  )
}

export default function TrialPage() {
  const reduced = useReducedMotion()
  const sectionRef = useRef<HTMLDivElement>(null)
  const slotRef = useRef<HTMLDivElement>(null)
  const [offset, setOffset] = useState({ x: 0, y: 0 })

  const { scrollYProgress } = useScroll({ target: sectionRef, offset: ['start start', 'end end'] })
  const scale = useTransform(scrollYProgress, [0, 0.42], [2.3, 1])
  const x = useTransform(scrollYProgress, [0, 0.42], [offset.x, 0])
  const y = useTransform(scrollYProgress, [0, 0.42], [offset.y, 0])
  const revealOpacity = useTransform(scrollYProgress, [0.26, 0.48], [0, 1])
  const revealY = useTransform(scrollYProgress, [0.26, 0.48], [28, 0])
  const revealScale = useTransform(scrollYProgress, [0.26, 0.48], [0.94, 1])

  // Measure the title's natural (settled) center, so the big state can be perfectly
  // centered in the viewport and land EXACTLY back in place.
  useLayoutEffect(() => {
    function measure() {
      const el = slotRef.current
      if (!el) return
      const r = el.getBoundingClientRect()
      setOffset({
        x: window.innerWidth / 2 - (r.left + r.width / 2),
        y: window.innerHeight / 2 - (r.top + r.height / 2),
      })
    }
    measure()
    window.addEventListener('resize', measure)
    return () => window.removeEventListener('resize', measure)
  }, [])

  const titleClass =
    'block max-w-[14ch] text-5xl font-semibold leading-[1.03] tracking-tight text-[#0E1320] sm:text-[3.75rem]'

  if (reduced) {
    return (
      <main className="landing-dark surface-dots-dark min-h-screen pt-28">
        <HeroContent
          titleNode={
            <h1 className={titleClass}>
              <VerticalCutReveal splitBy="lines" staggerDuration={0.12}>
                {TITLE}
              </VerticalCutReveal>
            </h1>
          }
        />
        <section className="mt-24 grid h-[60vh] place-items-center text-[#5A6472]">
          (next section — page scrolls normally)
        </section>
      </main>
    )
  }

  return (
    <main className="landing-dark">
      <section ref={sectionRef} className="surface-dots-dark relative h-[220vh]">
        <div className="sticky top-0 flex h-screen items-center overflow-hidden">
          <HeroContent
            titleNode={
              <div ref={slotRef} className="inline-block">
                <motion.h1
                  style={{ scale, x, y, transformOrigin: 'center center' }}
                  className={titleClass}
                >
                  <VerticalCutReveal splitBy="lines" staggerDuration={0.14} transition={{ type: 'spring', stiffness: 200, damping: 24 }}>
                    {TITLE}
                  </VerticalCutReveal>
                </motion.h1>
              </div>
            }
            revealStyle={{ opacity: revealOpacity, y: revealY, scale: revealScale } as unknown as React.CSSProperties}
          />
        </div>
      </section>

      {/* proof that the page scrolls normally after the pin releases */}
      <section className="grid h-screen place-items-center border-t border-[#D4E2FB]/60 bg-white text-[#5A6472]">
        <p className="text-lg">The rest of the page scrolls normally from here.</p>
      </section>
    </main>
  )
}
