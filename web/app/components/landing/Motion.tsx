'use client'

// Scroll-driven motion helpers for the landing page — Hera-inspired: smooth
// ease-out reveals, calm depth/parallax, NO bounce. Transform/opacity only, so
// the browser can composite them on the GPU (60fps target). Every effect is
// gated on `prefers-reduced-motion`: when the user opts out we render the plain
// rest state with no transforms at all.
//
// SSR contract: the server always renders the rest state (visible, untransformed).
// On the client we only switch motion ON after mount, so the first client paint
// matches the server HTML and there is never a hydration mismatch. framer-motion
// then drives the entrance/parallax from there.

import {
  motion,
  useReducedMotion,
  useScroll,
  useSpring,
  useTransform,
  type MotionValue,
} from 'framer-motion'
import { useEffect, useRef, useState, type ReactNode } from 'react'

/** True only after the component has mounted on the client. */
function useMounted(): boolean {
  const [mounted, setMounted] = useState(false)
  useEffect(() => setMounted(true), [])
  return mounted
}

/** Whether motion is allowed: mounted on the client AND not reduced-motion. */
function useMotionEnabled(): boolean {
  const mounted = useMounted()
  const reduced = useReducedMotion()
  return mounted && !reduced
}

const EASE_OUT = [0.22, 1, 0.36, 1] as const

// ---------------------------------------------------------------------------
// Reveal — fade + rise as the element scrolls into view (once).
// ---------------------------------------------------------------------------
interface RevealProps {
  children: ReactNode
  /** vertical offset (px) the element rises from. Default 24. */
  y?: number
  /** entrance duration (s). Default 0.5. */
  duration?: number
  /** delay before the entrance starts (s). Default 0. */
  delay?: number
  className?: string
  /** render as this element. Default 'div'. */
  as?: 'div' | 'section' | 'li' | 'ul' | 'ol' | 'figure'
}

export function Reveal({
  children,
  y = 24,
  duration = 0.5,
  delay = 0,
  className,
  as = 'div',
}: RevealProps) {
  const enabled = useMotionEnabled()
  const MotionTag = motion[as]

  if (!enabled) {
    const Tag = as
    return <Tag className={className}>{children}</Tag>
  }

  return (
    <MotionTag
      className={className}
      initial={{ opacity: 0, y }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-80px' }}
      transition={{ duration, delay, ease: EASE_OUT }}
      style={{ willChange: 'transform, opacity' }}
    >
      {children}
    </MotionTag>
  )
}

// ---------------------------------------------------------------------------
// RevealGroup / RevealItem — staggered children. Wrap a list of RevealItem
// children in a RevealGroup; the group orchestrates the stagger via variants.
// ---------------------------------------------------------------------------
interface RevealGroupProps {
  children: ReactNode
  /** delay between each child (s). Default 0.08. */
  stagger?: number
  /** delay before the first child (s). Default 0. */
  delayChildren?: number
  className?: string
  as?: 'div' | 'ul' | 'ol' | 'section'
}

const groupVariants = (stagger: number, delayChildren: number) => ({
  hidden: {},
  show: {
    transition: { staggerChildren: stagger, delayChildren },
  },
})

const itemVariants = (y: number, duration: number) => ({
  hidden: { opacity: 0, y },
  show: {
    opacity: 1,
    y: 0,
    transition: { duration, ease: EASE_OUT },
  },
})

export function RevealGroup({
  children,
  stagger = 0.08,
  delayChildren = 0,
  className,
  as = 'div',
}: RevealGroupProps) {
  const enabled = useMotionEnabled()
  const MotionTag = motion[as]

  if (!enabled) {
    const Tag = as
    return <Tag className={className}>{children}</Tag>
  }

  return (
    <MotionTag
      className={className}
      variants={groupVariants(stagger, delayChildren)}
      initial="hidden"
      whileInView="show"
      viewport={{ once: true, margin: '-80px' }}
    >
      {children}
    </MotionTag>
  )
}

interface RevealItemProps {
  children: ReactNode
  y?: number
  duration?: number
  className?: string
  as?: 'div' | 'li' | 'figure'
}

export function RevealItem({
  children,
  y = 24,
  duration = 0.5,
  className,
  as = 'div',
}: RevealItemProps) {
  const enabled = useMotionEnabled()
  const MotionTag = motion[as]

  if (!enabled) {
    const Tag = as
    return <Tag className={className}>{children}</Tag>
  }

  return (
    <MotionTag
      className={className}
      variants={itemVariants(y, duration)}
      style={{ willChange: 'transform, opacity' }}
    >
      {children}
    </MotionTag>
  )
}

// ---------------------------------------------------------------------------
// Parallax — translate a wrapped element on scroll. Tracks the element's own
// progress through the viewport and maps it to a small y range. Use for subtle
// depth on real content (a few px) — keep `range` small and tasteful.
// ---------------------------------------------------------------------------
interface ParallaxProps {
  children: ReactNode
  /** [from, to] y translation in px across the element's scroll span. */
  range?: [number, number]
  /** small scale drift, [from, to]. Default no scale. */
  scaleRange?: [number, number]
  className?: string
}

export function Parallax({
  children,
  range = [24, -24],
  scaleRange,
  className,
}: ParallaxProps) {
  const enabled = useMotionEnabled()
  const ref = useRef<HTMLDivElement>(null)
  const { scrollYProgress } = useScroll({
    target: ref,
    offset: ['start end', 'end start'],
  })
  const y = useTransform(scrollYProgress, [0, 1], range)
  const scale = useTransform(
    scrollYProgress,
    [0, 0.5, 1],
    scaleRange ? [scaleRange[0], scaleRange[1], scaleRange[0]] : [1, 1, 1],
  )

  if (!enabled) {
    return (
      <div ref={ref} className={className}>
        {children}
      </div>
    )
  }

  return (
    <motion.div
      ref={ref}
      className={className}
      style={{ y, scale, willChange: 'transform' }}
    >
      {children}
    </motion.div>
  )
}

// ---------------------------------------------------------------------------
// ParallaxWindows — decorative, abstract "product window" cards (pure SVG, no
// raster, no emoji) that drift at different rates as the page scrolls. They sit
// BEHIND content (low z, pointer-events:none) and evoke Hera's floating product
// windows + depth. Driven by the page's overall scroll progress.
// ---------------------------------------------------------------------------

/** A single abstract UI window drawn in inline SVG — tuned for the DARK stage:
 *  faint light-glass body + brighter Coinbase-blue accents that read on charcoal. */
function WindowCard({
  variant,
}: {
  variant: 'dashboard' | 'chart' | 'list'
}) {
  return (
    <svg viewBox="0 0 220 150" className="h-full w-full" aria-hidden="true">
      <defs>
        <linearGradient id={`win-${variant}`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#FFFFFF" stopOpacity="0.06" />
          <stop offset="100%" stopColor="#FFFFFF" stopOpacity="0.015" />
        </linearGradient>
      </defs>
      {/* window body */}
      <rect
        x="1"
        y="1"
        width="218"
        height="148"
        rx="14"
        fill={`url(#win-${variant})`}
        stroke="#FFFFFF"
        strokeOpacity="0.10"
        strokeWidth="1"
      />
      {/* title bar */}
      <rect x="1" y="1" width="218" height="26" rx="14" fill="#FFFFFF" fillOpacity="0.04" />
      <circle cx="18" cy="14" r="3" fill="#0052FF" fillOpacity="0.7" />
      <circle cx="30" cy="14" r="3" fill="#FFFFFF" fillOpacity="0.18" />
      <circle cx="42" cy="14" r="3" fill="#FFFFFF" fillOpacity="0.18" />

      {variant === 'dashboard' && (
        <>
          <rect x="16" y="40" width="56" height="32" rx="6" fill="#0052FF" fillOpacity="0.30" />
          <rect x="82" y="40" width="56" height="32" rx="6" fill="#FFFFFF" fillOpacity="0.06" />
          <rect x="148" y="40" width="56" height="32" rx="6" fill="#FFFFFF" fillOpacity="0.06" />
          <rect x="16" y="84" width="120" height="14" rx="5" fill="#FFFFFF" fillOpacity="0.07" />
          <rect x="16" y="106" width="92" height="14" rx="5" fill="#FFFFFF" fillOpacity="0.05" />
          <rect x="148" y="84" width="56" height="36" rx="6" fill="#0052FF" fillOpacity="0.30" />
        </>
      )}
      {variant === 'chart' && (
        <>
          <line x1="20" y1="64" x2="204" y2="64" stroke="#FFFFFF" strokeOpacity="0.07" strokeWidth="1" />
          <line x1="20" y1="92" x2="204" y2="92" stroke="#FFFFFF" strokeOpacity="0.07" strokeWidth="1" />
          <path
            d="M 24 112 L 64 96 L 104 102 L 144 70 L 184 48"
            fill="none"
            stroke="#0052FF"
            strokeOpacity="0.85"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          <circle cx="184" cy="48" r="3.5" fill="#0052FF" fillOpacity="1" />
        </>
      )}
      {variant === 'list' && (
        <>
          <rect x="16" y="40" width="14" height="14" rx="4" fill="#0052FF" fillOpacity="0.45" />
          <rect x="38" y="42" width="120" height="10" rx="5" fill="#FFFFFF" fillOpacity="0.07" />
          <rect x="16" y="66" width="14" height="14" rx="4" fill="#0052FF" fillOpacity="0.45" />
          <rect x="38" y="68" width="150" height="10" rx="5" fill="#FFFFFF" fillOpacity="0.07" />
          <rect x="16" y="92" width="14" height="14" rx="4" fill="#0052FF" fillOpacity="0.45" />
          <rect x="38" y="94" width="100" height="10" rx="5" fill="#FFFFFF" fillOpacity="0.07" />
        </>
      )}
    </svg>
  )
}

interface FloatingWindowProps {
  variant: 'dashboard' | 'chart' | 'list'
  /** y drift across the scroll span, in px. */
  yRange: [number, number]
  /** absolute-positioning utility classes (top/left/right + width). */
  position: string
  /** static rotation, deg. */
  rotate?: number
  scrollYProgress: MotionValue<number>
}

function FloatingWindow({
  variant,
  yRange,
  position,
  rotate = 0,
  scrollYProgress,
}: FloatingWindowProps) {
  const y = useTransform(scrollYProgress, [0, 1], yRange)
  return (
    <motion.div
      className={`absolute ${position}`}
      style={{ y, rotate, willChange: 'transform' }}
      aria-hidden="true"
    >
      <WindowCard variant={variant} />
    </motion.div>
  )
}

// ---------------------------------------------------------------------------
// SlidingPanel — a full-bleed, rounded-top surface that slides up and OVERLAPS
// the section above it as it enters the viewport (Hera's stacking transform,
// Filmo's character). The overlap itself is pure CSS layout (`.panel`, set by
// the caller); this component adds the *motion*: the panel lifts a few px and
// fades in as it crosses into view, so the cover reads as a deliberate slide.
// Transform/opacity only. Reduced motion / SSR render the rest state (already
// stacked via CSS) with no transforms.
// ---------------------------------------------------------------------------
interface SlidingPanelProps {
  children: ReactNode
  /** classes for the <section> (surface + .panel + spacing). */
  className?: string
  /** anchor id passed through to the section. */
  id?: string
  /** how far (px) the panel rises as it slides in. Default 40. */
  lift?: number
  /** show the blue glass top edge. Default true. */
  edge?: boolean
}

export function SlidingPanel({
  children,
  className = '',
  id,
  lift = 40,
  edge = true,
}: SlidingPanelProps) {
  const enabled = useMotionEnabled()
  const ref = useRef<HTMLElement>(null)
  // Track the panel's entrance: from just-below-the-fold until its top reaches
  // the top of the viewport. We only use the entering half for the slide.
  const { scrollYProgress } = useScroll({
    target: ref,
    offset: ['start end', 'start start'],
  })
  const yRaw = useTransform(scrollYProgress, [0, 1], [lift, 0])
  const opacityRaw = useTransform(scrollYProgress, [0, 0.6], [0.55, 1])
  // Spring-smooth the slide so it settles (our easing, not a hard scrub).
  const y = useSpring(yRaw, { stiffness: 120, damping: 26, mass: 0.4 })

  if (!enabled) {
    return (
      <section ref={ref} id={id} className={className}>
        {edge && <span aria-hidden="true" className="panel__edge" />}
        {children}
      </section>
    )
  }

  return (
    <motion.section
      ref={ref}
      id={id}
      className={className}
      style={{ y, opacity: opacityRaw, willChange: 'transform, opacity' }}
    >
      {edge && <span aria-hidden="true" className="panel__edge" />}
      {children}
    </motion.section>
  )
}

// ---------------------------------------------------------------------------
// ScrubbedHero — scroll-scrubbed pinned hero. The child (the real composer
// card + headline) is pinned via position:sticky inside a tall stage, and
// scrubs in (scale + lift) then SETTLES as you scroll the first viewport.
// The composer stays fully functional — this only wraps it in a transform.
// Reduced motion / SSR: the stage collapses to auto height (CSS) and the child
// renders untransformed in normal flow.
//
// Usage:
//   <ScrubbedHero>
//     <form>…the real composer…</form>
//   </ScrubbedHero>
// ---------------------------------------------------------------------------
interface ScrubbedHeroProps {
  children: ReactNode
  /** classes for the sticky inner wrapper (where content centers). */
  className?: string
}

export function ScrubbedHero({ children, className = '' }: ScrubbedHeroProps) {
  const enabled = useMotionEnabled()
  const ref = useRef<HTMLDivElement>(null)
  // Progress across the tall stage: 0 at entry, 1 when the stage is scrolled out.
  const { scrollYProgress } = useScroll({
    target: ref,
    offset: ['start start', 'end start'],
  })
  // Scrub IN over the first ~35% (scale up + rise + fade), then hold settled.
  const scaleRaw = useTransform(scrollYProgress, [0, 0.35], [0.92, 1])
  const yRaw = useTransform(scrollYProgress, [0, 0.35], [48, 0])
  const opacityRaw = useTransform(scrollYProgress, [0, 0.12], [0.4, 1])
  const scale = useSpring(scaleRaw, { stiffness: 140, damping: 28, mass: 0.4 })
  const y = useSpring(yRaw, { stiffness: 140, damping: 28, mass: 0.4 })

  if (!enabled) {
    // No pin, no transform — content sits in normal flow.
    return <div className={className}>{children}</div>
  }

  return (
    <div ref={ref} className="hero-scrub-stage">
      <div className="sticky top-0 flex min-h-screen items-center justify-center">
        <motion.div
          className={className}
          style={{ scale, y, opacity: opacityRaw, willChange: 'transform, opacity' }}
        >
          {children}
        </motion.div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// PinnedCenter — pins a centered element (e.g. an "Examples" CTA) while the
// surrounding content drifts past it. Pure position:sticky; no transforms, so
// it works identically with reduced motion. Place it as a sibling overlay
// inside a tall `relative` section; it sticks to the vertical center of the
// viewport for the section's scroll span.
// ---------------------------------------------------------------------------
interface PinnedCenterProps {
  children: ReactNode
  className?: string
}

export function PinnedCenter({ children, className = '' }: PinnedCenterProps) {
  return (
    <div
      className={`pointer-events-none sticky top-1/2 z-20 flex -translate-y-1/2 justify-center ${className}`}
    >
      {children}
    </div>
  )
}

/**
 * A decorative parallax layer of floating window cards. Place it as the first
 * child of a `relative` container (and give the real content `relative z-10` so
 * it stays on top). The layer fills the container at z-0, sits above the
 * container's own CSS background but behind raised content, and never intercepts
 * pointer events. Renders an empty anchor when motion is disabled — so reduced
 * motion / SSR get no windows and no hydration mismatch.
 */
export function ParallaxWindows() {
  const enabled = useMotionEnabled()
  const ref = useRef<HTMLDivElement>(null)
  const { scrollYProgress } = useScroll({
    target: ref,
    offset: ['start end', 'end start'],
  })

  // Always render the anchor div so useScroll has a target; the windows only
  // appear once motion is enabled (mounted + not reduced-motion). The anchor is
  // empty on the server, so there's no hydration mismatch.
  return (
    <div
      ref={ref}
      aria-hidden="true"
      className="pointer-events-none absolute inset-0 z-0 overflow-hidden"
    >
      {enabled && (
        <>
          <FloatingWindow
            variant="dashboard"
            position="-left-16 top-[8%] w-[230px] opacity-70 sm:left-[2%] sm:w-[260px]"
            yRange={[40, -40]}
            rotate={-4}
            scrollYProgress={scrollYProgress}
          />
          <FloatingWindow
            variant="chart"
            position="-right-12 top-[30%] w-[200px] opacity-60 sm:right-[3%] sm:w-[230px]"
            yRange={[-30, 30]}
            rotate={5}
            scrollYProgress={scrollYProgress}
          />
          <FloatingWindow
            variant="list"
            position="left-[6%] bottom-[10%] hidden w-[210px] opacity-50 lg:block"
            yRange={[24, -24]}
            rotate={3}
            scrollYProgress={scrollYProgress}
          />
        </>
      )}
    </div>
  )
}
