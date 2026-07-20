'use client'
// ═══════════════════════ /new — THE COMPOSER, AS A PLACE ═════════════════════
//
// "New filmo" on the rail used to link to `/?new=1` — the marketing landing,
// which then lays the composer over itself. That works, and it answers the wrong
// question: a reader who pressed a NAVIGATION entry arrived at the front door,
// with no rail beside them and no way back to Overview / Filmos / Assets without
// abandoning what they came to do. Dennis, 2026-07-19: "when i click on 'new
// filmo' in the studio, i want you to take me directly to the chatbox, and not
// the landing page. when i get to the chatbox, i still want access to the
// overview, filmos and assets, so i can flip back and forth."
//
// So the composer gets a real ROUTE, on the studio's ground, with the product's
// own rail beside it. Flipping to the Overview and back is then not a feature
// this page has to build — it is the rail, unchanged, doing the single job it
// exists for.
//
// ── `/?new=1` IS NOT REPLACED ───────────────────────────────────────────────
// It is still what "Build" means from the landing and from every empty-state CTA
// (`readIntent` in app/page.tsx documents it), and it still renders StudioEntry:
// the composer WITHOUT a rail, because a visitor who has never signed in has no
// overview, no filmos and no assets to flip between. Two destinations for two
// audiences — and ONE composer between them, see below. A destination was added
// here; none was taken away.
//
// ── ONE COMPOSER, IMPORTED ──────────────────────────────────────────────────
// `NewFilmComposer` is imported, never copied. Its own header says what a copy
// costs: two composers that disagree about a single createBuild parameter make
// two different films from the same URL, with no visible cause and nobody to
// blame. This route contributes CHROME and nothing else — it passes the composer
// no build parameter at all, so there is no value here that could drift from the
// landing's.
//
// ── SIGNED OUT, IT STILL COMPOSES ───────────────────────────────────────────
// /overview, /videos and /assets show a sign-in gate instead of their content,
// because their content IS owner-scoped data and there is nothing honest to draw
// without it. This page has no such content: it is one input box. The composer
// already owns the signed-out path end to end — it stashes the typed URL, opens
// the product's real sign-in gate, and the landing resumes the build when Google
// returns — so gating in front of it would remove the one screen built to
// survive that round-trip, and would cost the reader the URL they came to type.
//
// ── FIXED SHELL, PORTALLED ──────────────────────────────────────────────────
// Same reason as /overview and LibraryShell: `app/template.tsx` wraps every route
// in a framer-motion div, and a position:fixed child of a TRANSFORMED ancestor is
// positioned against that ancestor rather than the viewport. Rendering into
// document.body is what makes `inset:0` mean the screen — and the body then never
// scrolls, at 1440 or at 390.
import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { useAuth } from '../../lib/auth'
import OverviewRail from '../components/overview/OverviewRail'
import NewFilmComposer from '../runs/[id]/NewFilmComposer'
import FeedbackModal from '../runs/[id]/FeedbackModal'
import FilmoLoader, { GROUND_STUDIO } from '../components/FilmoLoader'

export default function NewFilmoPage() {
  const { getToken } = useAuth()
  const [mounted, setMounted] = useState(false)
  // WHOEVER RENDERS THE RAIL OWNS THE FEEDBACK SHEET (LibraryShell's rule): the
  // rail's account circle is the way IN, but the sheet has to belong to a
  // surface that outlives the click.
  const [fbOpen, setFbOpen] = useState(false)

  useEffect(() => setMounted(true), [])

  // Pre-mount there is no document.body to portal into. Rendering NOTHING here
  // would mean the server sends an empty document for /new and the route's
  // loading.tsx hands over to a blank page; the boot screen on the same ground
  // makes the wait continuous instead. Server and first client render agree
  // (`mounted` is false in both), so there is no hydration mismatch.
  if (!mounted) return <FilmoLoader ground={GROUND_STUDIO} />

  return createPortal(
    <div className="nw-root">
      <OverviewRail
        current="new"
        getToken={getToken}
        onFeedback={() => setFbOpen(true)}
      />

      {/* The composer owns the whole stage and draws no chrome of its own —
          `.nf-stage` is already `flex:1 1 0`, so it takes what the rail leaves
          exactly as it does inside the studio. */}
      <NewFilmComposer getToken={getToken} />

      {/* "This is broken" is only actionable if it says where the reader was
          standing. */}
      <FeedbackModal
        open={fbOpen}
        onClose={() => setFbOpen(false)}
        getToken={getToken}
        context="/new"
      />

      <style>{`
        /* Same ground and same shape as Workspace's .wk-root and the Overview's
           .ov-root — this is the studio, in its empty state, and it may not read
           as a different product from the rooms one rail-click away. */
        .nw-root { position:fixed; inset:0; display:flex; background:#F1F1EF;
          color:#1B1B1A; font:14px/1.5 Inter,-apple-system,sans-serif; z-index:50; }
      `}</style>
    </div>,
    document.body,
  )
}
