'use client'
// ═══════════════════════ /overview — THE SIGNED-IN HOME ══════════════════════
//
// Where a signed-in visitor lands. Before this route existed, `/` sent them
// straight into their most recent film — which answered "what was I last doing"
// and nothing else. This answers the question they actually arrive with: what do
// I have, and what should I do next.
//
// FOUR THINGS ABOUT IT ARE LOAD-BEARING.
//
// 1. EVERY CARD IS CHECKABLE. The "For you" column proposes things derived from
//    rows this account owns — pages Filmo read, recordings it kept, notes given
//    to the director, builds that failed. Nothing is inferred from a live look
//    at a customer's site, because we cannot know a page changed without
//    checking, and checking on page load is not something a home page gets to
//    do. The derivations live in the OVERVIEW block of app/actions.ts; this file
//    renders them and adds no claim of its own.
//
// 2. AN EMPTY ACCOUNT IS A FIRST-CLASS STATE, NOT AN ERROR. A brand-new signup
//    reaches this page with no runs, no events and no assets. It gets zeroes on
//    the strip and an invitation in the column — never a failure, and never a
//    redirect, because a redirect out of an empty home is how you build a loop
//    out of an account with nothing in it.
//
// 3. IT IS A FIXED SHELL, PORTALLED. `app/template.tsx` wraps every route in a
//    framer-motion div; a `position:fixed` child of a transformed ancestor is
//    positioned against that ancestor rather than the viewport. Workspace solves
//    this by rendering into document.body and so does this — same reason, same
//    shape, and the body then never scrolls, at any width.
//
// 4. SIGNED OUT, IT ASKS — IT DOES NOT BOUNCE. Every read here is owner-scoped
//    server-side, so a stale token surfaces the sign-in gate rather than an
//    empty page pretending the account is new.
import { useCallback, useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import Link from 'next/link'
import { useAuth } from '../../lib/auth'
import { ensureFreshAccessToken } from '../../lib/insforge'
import {
  getOverviewStats, getSuggestions, listMyRuns,
  type OverviewStats, type Suggestion,
} from '../actions'
import type { Run } from '../../lib/types'
import FeedbackModal from '../runs/[id]/FeedbackModal'
import OverviewRail from '../components/overview/OverviewRail'
import StatStrip from '../components/overview/StatStrip'
import SuggestionCards from '../components/overview/SuggestionCards'
import RecentFilmos from '../components/overview/RecentFilmos'
import FilmoLoader, { GROUND_STUDIO } from '../components/FilmoLoader'

// The operator account. Four other copies of this string exist (actions.ts,
// Brand.tsx, FloatingNav.tsx, AccountMenu.tsx) and only the SERVER's is a
// boundary — this copy decides one thing: which word the greeting prints.
const OWNER_EMAIL = 'denniswanglabs@gmail.com'

// ── AN EMAIL NEVER REACHES THE SCREEN ───────────────────────────────────────
// Same rule and same order of preference as AccountMenu and the landing nav:
// the operator shows a first name so a screen-recording never exposes the
// handle, everyone else shows a real name when we have one and the local-part
// when we don't. The @domain has no path here.
function displayName(user: { email?: string; [k: string]: unknown }): string {
  if ((user.email || '').toLowerCase() === OWNER_EMAIL) return 'Dennis'
  const meta = user.user_metadata as Record<string, unknown> | undefined
  const name =
    (user.name as string)
    || (user.full_name as string)
    || (meta?.full_name as string)
    || (meta?.name as string)
  if (typeof name === 'string' && name.trim()) return name.trim().split(/\s+/)[0]
  const email = user.email || ''
  return email.split('@')[0] || ''
}

// Time of day is the READER's, never the server's — this is only ever called
// from a branch that renders after mount, so it is the browser's clock that
// decides whether it is evening.
function greeting(): string {
  const h = new Date().getHours()
  if (h < 5) return 'Still up'
  if (h < 12) return 'Good morning'
  if (h < 18) return 'Good afternoon'
  return 'Good evening'
}

export default function OverviewPage() {
  const { user, loading, getToken } = useAuth()
  const [mounted, setMounted] = useState(false)
  const [stats, setStats] = useState<OverviewStats | null>(null)
  const [suggestions, setSuggestions] = useState<Suggestion[] | null>(null)
  const [runs, setRuns] = useState<Run[] | null>(null)
  const [authError, setAuthError] = useState(false)
  // A read that failed is not an account that is empty. This flag exists so the
  // page can say so plainly instead of rendering three convincing zeroes.
  const [readFailed, setReadFailed] = useState(false)
  const [fbOpen, setFbOpen] = useState(false)

  useEffect(() => setMounted(true), [])

  const load = useCallback(async () => {
    setReadFailed(false)
    // Three independent owner-scoped reads, in parallel: the strip, the
    // cards, and the same run list /videos shows.
    const read = async () => {
      const token = await getToken()
      const [statsRes, sugRes, runsRes] = await Promise.all([
        getOverviewStats(token),
        getSuggestions(token),
        listMyRuns(token),
      ])
      return { statsRes, sugRes, runsRes }
    }
    const deniedIn = (r: Awaited<ReturnType<typeof read>>) =>
      'authError' in r.statsRes || 'authError' in r.sugRes || 'authError' in r.runsRes
    try {
      let r = await read()
      // ONE STALE 401 IS NOT A SIGNOUT. The reproduced false-logout class
      // (2026-07-20): the access token expires mid-session, the reads carry the
      // dead bearer, verifyUser answers a clean 401 each — while a perfectly
      // valid refresh token sits in localStorage. So before the gate is even
      // considered: force ONE refresh (the server outranks the client's clock)
      // and retry the reads ONCE on the fresh token. The invariant this
      // establishes: a user holding a valid refresh token never sees the
      // sign-in gate — they see their data, or a "try again", never the door.
      if (deniedIn(r)) {
        const freshness = await ensureFreshAccessToken({ force: true })
        if (freshness === 'ok') r = await read()
        if (deniedIn(r)) {
          if (freshness === 'unavailable') {
            // The auth service itself was unreachable: the session is UNKNOWN,
            // not dead. That is a blip with a retry button, never the gate.
            setReadFailed(true)
            return
          }
          // Definitive: the refresh credential is gone/revoked ('signed-out'),
          // or a token minted seconds ago was still rejected. The gate is honest.
          setAuthError(true)
          return
        }
      }
      if ('authError' in r.statsRes || 'authError' in r.sugRes || 'authError' in r.runsRes) {
        return // unreachable after the block above; narrows the types below
      }
      setAuthError(false)
      setStats(r.statsRes.stats)
      setSuggestions(r.sugRes.suggestions)
      setRuns(r.runsRes.runs)
    } catch {
      // verifyUser THROWS (rather than returning null) when the auth service is
      // unreachable, precisely so a brownout cannot read as "signed out". Say
      // it is a blip and offer the retry.
      setReadFailed(true)
    }
  }, [getToken])

  // KEYED ON THE USER'S ID, NEVER THE USER OBJECT — see the full note in
  // /videos. This page pays the most for the difference: `load` fires THREE
  // server actions, and Next.js serializes server actions globally, so one
  // redundant re-run costs three more queued round trips (measured: 6 actions
  // for a single visit).
  const userId = user?.id
  useEffect(() => { if (userId) void load() }, [userId, load])

  // Pre-mount there is no document.body to portal into, so this branch is
  // unavoidable — but it used to render NOTHING, which meant the server sent an
  // empty document for /overview and the route's loading.tsx handed over to a
  // blank page. It hands over to the same boot screen instead, on the same
  // ground, so the wait is continuous. (Server and first client render agree
  // here — `mounted` is false in both — so there is no hydration mismatch.)
  if (!mounted) return <FilmoLoader ground={GROUND_STUDIO} />



  const name = user ? displayName(user) : ''
  const hasWork = (runs?.length ?? 0) > 0

  let body: React.ReactNode
  if (loading) {
    body = <FilmoLoader ground={GROUND_STUDIO} fit="block" />
  } else if (!user || authError) {
    // No redirect. A signed-out visitor who typed this URL gets the door, not a
    // bounce — and an account with nothing in it can never loop if nothing moves.
    body = (
      <div className="ov-gate">
        <b>Sign in to see your overview</b>
        <span>Your filmos, and everything Filmo made them from, live in your account.</span>
        <Link className="ov-gatebtn" href="/login">Sign in</Link>
      </div>
    )
  } else if (readFailed) {
    body = (
      <div className="ov-gate">
        <b>That didn&rsquo;t load</b>
        <span>
          The studio couldn&rsquo;t be reached just now. Nothing is lost — your
          filmos are where you left them.
        </span>
        <button className="ov-gatebtn" onClick={() => void load()}>Try again</button>
      </div>
    )
  } else {
    body = (
      <>
        <StatStrip stats={stats} />
        <div className="ov-cols">
          <SuggestionCards
            suggestions={suggestions}
            getToken={getToken}
            hasWork={hasWork}
          />
          <RecentFilmos runs={runs} />
        </div>
      </>
    )
  }

  return createPortal(
    <div className="ov-root">
      <OverviewRail getToken={getToken} onFeedback={() => setFbOpen(true)} />

      <main className="ov-stage">
        <div className="ov-inner">
          <header className="ov-head">
            <h1 className="ov-greet">
              {greeting()}{name ? `, ${name}` : ''}
            </h1>
            <p className="ov-lede">
              Everything below is read off your own filmos — what Filmo opened,
              recorded and cut. Nothing here is a guess about your site.
            </p>
          </header>
          {body}
        </div>
      </main>

      {/* Context is what turns "this is broken" into something someone can go
          and look at: the route they were standing on when it felt wrong. */}
      <FeedbackModal
        open={fbOpen}
        onClose={() => setFbOpen(false)}
        getToken={getToken}
        context="/overview"
      />

      <style>{`
        .ov-root { position:fixed; inset:0; display:flex; background:#F1F1EF;
          color:#1B1B1A; font:14px/1.5 Inter,-apple-system,sans-serif; z-index:50; }
        /* The stage scrolls, the shell does not — so the BODY never scrolls in
           either direction, at 1440 or at 390. */
        .ov-stage { flex:1 1 0; min-width:0; min-height:0; overflow-y:auto;
          overflow-x:hidden; }
        .ov-inner { max-width:1120px; margin:0 auto; padding:38px 32px 56px; }
        .ov-head { margin-bottom:26px; }
        .ov-greet { margin:0; font-size:32px; font-weight:600;
          letter-spacing:-.025em; line-height:1.15; color:#1B1B1A; }
        .ov-lede { margin:9px 0 0; max-width:56ch; font-size:14.5px;
          line-height:1.55; color:#8A8A86; }
        /* Two columns above 1040px, one below. minmax(0,…) on the first track
           is what stops a long title from widening the grid past the viewport
           and handing the body a horizontal scrollbar. */
        .ov-cols { margin-top:26px; display:grid; gap:28px;
          grid-template-columns:minmax(0, 1fr); align-items:start; }
        @media (min-width:1040px) {
          .ov-cols { grid-template-columns:minmax(0, 1fr) 320px; gap:32px; } }
        @media (max-width:760px) {
          .ov-inner { padding:26px 18px 44px; }
          .ov-greet { font-size:26px; }
          .ov-lede { font-size:13.5px; } }
        .ov-quiet { margin:0; font-size:13.5px; color:#B6B6B2; }
        .ov-gate { background:#fff; border:1px solid #E6E6E3; border-radius:14px;
          padding:26px; display:flex; flex-direction:column; gap:7px;
          align-items:flex-start; max-width:520px; }
        .ov-gate b { font-size:16px; font-weight:650; }
        .ov-gate span { font-size:13.5px; line-height:1.55; color:#6E6E6A; }
        .ov-gatebtn { margin-top:10px; display:inline-flex; align-items:center;
          justify-content:center; border:1px solid #1B1B1A; background:#1B1B1A;
          color:#fff; border-radius:99px; padding:9px 20px;
          font:13px/1 Inter,-apple-system,sans-serif; cursor:pointer;
          text-decoration:none; }
        .ov-gatebtn:hover { background:#000; border-color:#000; }
        .ov-gatebtn:focus-visible { outline:2px solid #3B82F6; outline-offset:3px; }
      `}</style>
    </div>,
    document.body,
  )
}
