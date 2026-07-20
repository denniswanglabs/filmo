'use client'
import { useEffect } from 'react'

// ── `?look=` IS A STICKY PRODUCT SWITCH, NOT LANDING DECORATION ─────────────
// Arriving with `/?look=walkrec` selects the agent-toured film pipeline, and
// the choice STICKS: every later plain visit keeps it, until `/?look=classic`
// explicitly switches back (which sticks the same way). The reader is
// `NewFilmComposer.stickyLook()`.
//
// This used to be an effect inside the old landing's page component, which made
// it the ONLY writer of `filmo-look` in the repo — so replacing that landing
// would have made every `?look=` URL silently inert, with no error and no
// visible symptom beyond films quietly coming back from the wrong pipeline.
// It lives in the root layout now, so the switch works from ANY entry URL
// rather than only from the front door.
//
// Storing 'classic' matters even though stickyLook() deliberately declines to
// restore it: writing it is what OVERWRITES a stored 'walkrec' and hands the
// decision back to the server default. Dropping the write would make the switch
// one-way.
const LOOKS = new Set(['walkrec', 'classic', 'engineered-night'])

export default function StickyLookParam() {
  useEffect(() => {
    try {
      const q = new URLSearchParams(window.location.search).get('look')
      if (q && LOOKS.has(q)) localStorage.setItem('filmo-look', q)
    } catch {
      /* private mode / no storage — the server default decides, as it should */
    }
  }, [])
  return null
}
