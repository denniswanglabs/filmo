'use client'

// Route-entry transition. App Router re-mounts template.tsx on every navigation,
// so wrapping children in a framer-motion fade + small rise gives every page
// (including /how-it-works) a subtle, snappy ease-in instead of a hard cut.
// Kept deliberately fast (~280ms, ~6px) so it reads as polish, not a delay.
//
// SSR contract: never paint opacity:0 in the server HTML. If JS fails to load
// (corrupt .next / webpack `.call` errors), an initial hidden state leaves a
// permanently blank page. Motion only runs after mount + when reduced-motion is off.

import { motion, useReducedMotion } from 'framer-motion'
import { useEffect, useState } from 'react'

export default function Template({ children }: { children: React.ReactNode }) {
  const [mounted, setMounted] = useState(false)
  const reduced = useReducedMotion()
  useEffect(() => setMounted(true), [])

  if (!mounted || reduced) {
    return <>{children}</>
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.28, ease: [0.16, 1, 0.3, 1] }}
    >
      {children}
    </motion.div>
  )
}
