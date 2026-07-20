'use client'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '../lib/auth'
import { createBuild, listMyRuns } from './actions'
import { AuthGate } from './components/AuthGate'
import PloyLanding from './components/landing2/PloyLanding'
import BootScreen from './components/landing2/BootScreen'
import StudioEntry from './components/landing2/StudioEntry'
import {
  clearPendingBuild,
  isValidBuildUrl,
  readPendingBuild,
  writePendingBuild,
  type PendingBuild,
} from '../lib/pending-build'

/* ───────────────────────────────────────────────────────────────────────────
   `/` IS A DOOR, NOT A PAGE.

   The studio is the product; the landing is the front door. So this route
   resolves to one of three things and renders exactly one of them:

     signed out ................ the landing
     signed in, has films ...... their most recent film, in the studio
     signed in, no films ....... the studio's own "New film" surface, in place

   Three things about that are load-bearing enough to state out loud:

   1. NO HTTP REDIRECT IS INVOLVED, ANYWHERE. The session lives in
      origin-scoped localStorage (`insforge.ts`), which no server and no
      middleware can read — a redirect decided on the server would fire for
      nobody. Every hand-off here is a client `router.replace`, which also
      means there is no status code to get wrong: a 301/308 would be cached by
      the browser permanently and rolling the deploy back would NOT free the
      people who had already hit it. There is no way to make that mistake from
      here, and that is deliberate.

   2. THE ZERO-FILM ACCOUNT IS RENDERED, NOT SENT. The studio has no route of
      its own — it is `runs/[id]` with a walkrec run — so a brand-new signup
      has no id to be sent to. Redirecting them anywhere would either invent an
      id (greeting a first-time user with "This run could not be found") or
      bounce them back here forever. So `/` becomes the empty studio for that
      account. An account with nothing in it cannot loop if nothing moves.

   3. THE REDIRECT IS GATED ON A SERVER-VERIFIED SESSION, NOT ON `user`.
      `lib/auth.tsx` paints `user` optimistically from localStorage and drops
      `loading` before anything is validated. Trusting that would take a
      returning visitor whose session actually died, redirect them into the
      studio on the strength of a stale cache, bounce them to "please sign in",
      and — because every later visit to `/` repeats the trick — never let them
      reach the marketing page again. So the optimistic user only decides
      whether it is WORTH ASKING; `listMyRuns` (whose `verifyUser` runs on the
      server) decides the answer, and its `authError` sends them to the
      landing. Anything that isn't a definitive yes fails open to the landing.
   ─────────────────────────────────────────────────────────────────────────── */

// The landing is the DEFAULT, and it is what the server renders for everyone —
// it has to be. The server cannot read the session, so if this started as a
// "deciding" blank, every anonymous visitor and every crawler would get an
// empty document and wait for JS to fill it. The signed-in visitor is handled
// the other way round: the markup ships, and the pre-paint stamp hides it.
type View = 'landing' | 'studio-entry'

// `?landing=1` — always show the marketing page, even signed in. Without an
// escape hatch a signed-in visitor (Dennis included) literally cannot look at
// the landing, and every in-app link back to it becomes a teleport into the
// studio. `?new=1` — go straight to the composer instead of the last film,
// which is what "Build" means from anywhere else in the app.
function readIntent(): { landing: boolean; fresh: boolean } {
  try {
    const q = new URLSearchParams(window.location.search)
    return { landing: q.get('landing') === '1', fresh: q.get('new') === '1' }
  } catch {
    return { landing: false, fresh: false }
  }
}

// ── PRE-PAINT COVER ─────────────────────────────────────────────────────────
// `/` is server-rendered as the landing for EVERYONE — it has to be, because
// the session lives in localStorage and no server can read it. So without a
// signal that runs before the first paint, a visitor who is already signed in
// watches the marketing page paint and hydrate before it disappears, which is
// the entire complaint this work exists to answer.
//
// This script runs ahead of the landing markup and, when it has reason to think
// the visitor is signed in, injects a stylesheet that hides the landing and
// raises the boot cover. React removes that stylesheet by id the moment it
// learns otherwise.
//
// It injects a <style> rather than stamping an attribute on <html> DELIBERATELY.
// The obvious version — `documentElement.setAttribute(...)` — works, but React
// then finds an attribute on the root that the server never rendered and logs a
// hydration mismatch on every signed-in load; `suppressHydrationWarning` does
// not cover the App Router's root element (verified, Next 15 / React 19). A node
// React never rendered has nothing to reconcile, so there is no mismatch to
// suppress. The rules are !important because BootScreen's own <style> lives in
// the body and would otherwise win on document order.
//
// ⚠ `insforge_session_v1` is `SESSION_KEY` in `lib/insforge.ts`, duplicated here
// because this has to be a literal inside a script that runs before any module
// loads. If that key moves, this degrades to a landing flash for signed-in
// users — not a break, but fix it here too.
const BOOT_STYLE_ID = 'filmo-boot-cover'
const BOOT_PROBE = `try{var q=location.search;if(q.indexOf('landing=1')<0&&(localStorage.getItem('insforge_session_v1')||q.indexOf('insforge_code')>-1)){var s=document.createElement('style');s.id='${BOOT_STYLE_ID}';s.textContent='[data-filmo-landing]{visibility:hidden!important}.fl-boot{opacity:1!important;visibility:visible!important}';document.head.appendChild(s)}}catch(e){}`

function clearBootStamp() {
  try {
    document.getElementById(BOOT_STYLE_ID)?.remove()
  } catch {
    /* ignore */
  }
}

export default function Home() {
  const router = useRouter()
  const { user, loading, getToken } = useAuth()

  const [view, setView] = useState<View>('landing')
  const [booting, setBooting] = useState(false)
  const [gateOpen, setGateOpen] = useState(false)
  // A build that failed on its way in has to say so somewhere, and the landing
  // has no composer to say it in — so it is carried onto the studio surface.
  const [notice, setNotice] = useState<string | null>(null)

  // The stamp lives on <html>, outside React's tree, so React will not clean it
  // up on unmount. Leaving it set would hide the landing on a later client
  // navigation back to `/`.
  useEffect(() => clearBootStamp, [])

  const showLanding = useCallback(() => {
    clearBootStamp()
    setBooting(false)
    setView('landing')
  }, [])

  // Kick off a build and navigate to its run. Identity travels as the verified
  // access token (the server derives the owner from it), never a client-set id.
  // Every parameter is pinned to the same value the studio's own composer pins,
  // because two doors that disagree about one of them make two different films
  // from the same URL. `brain` especially: createBuild's fallback for an absent
  // brain is 'super-free', so omitting it silently downgrades the paid flagship.
  const runBuild = useCallback(
    async (p: PendingBuild) => {
      setBooting(true)
      try {
        const accessToken = await getToken()
        if (!accessToken) {
          writePendingBuild(p)
          setBooting(false)
          setNotice('Sign in again to start the film — your link is saved.')
          setGateOpen(true)
          setView('studio-entry')
          clearBootStamp()
          return
        }
        const res = await createBuild({
          accessToken,
          url: p.url.trim(),
          brain: p.brain,
          look:
            p.look === 'walkrec'
              ? 'walkrec'
              : p.look === 'engineered-night'
                ? 'engineered-night'
                : p.look === 'classic'
                  ? 'classic'
                  : undefined,
          mode: 'mock',
          payMode: p.requirePay ? 'human' : 'auto',
        })
        // The beta cap answers with a structured { limit } rather than a run. It
        // is a real answer, not a broken session — say it and stop.
        if ('limit' in res) {
          setNotice(res.message)
          setBooting(false)
          setView('studio-entry')
          clearBootStamp()
          return
        }
        // Leave the cover up: the client transition keeps this route mounted
        // until the run page is ready, so the wait reads as one beat.
        router.push(`/runs/${res.runId}`)
      } catch {
        // A thrown server action is OPAQUE in production (the "Server Components
        // render … digest" 500), so its real message is unreadable. The dominant
        // cause is a stale token — the UI looks signed in because the session was
        // restored optimistically, but the server's verifyUser rejected it. Put
        // the URL back so signing in a second time doesn't cost it.
        writePendingBuild(p)
        setBooting(false)
        setNotice('Your session expired — sign in again to start the film.')
        setGateOpen(true)
        setView('studio-entry')
        clearBootStamp()
      }
    },
    [getToken, router],
  )

  // Resolve where a signed-in visitor belongs. Returns only when it has decided
  // to render something here; otherwise it has already started a navigation.
  const enterStudio = useCallback(async () => {
    setBooting(true)
    const { fresh } = readIntent()
    let token: string | null = null
    try {
      token = await getToken()
    } catch {
      /* fall through — listMyRuns treats an empty token as unauthenticated */
    }
    let runs: Array<{ id: string; film_mode?: string | null }> = []
    try {
      const res = await listMyRuns(token || '')
      // THE DEFINITIVE ANSWER. verifyUser ran on the server; a rejection here
      // means the optimistically-painted session is genuinely dead, so the
      // honest destination is the front door, not a studio they can't load.
      if ('authError' in res) {
        showLanding()
        return
      }
      runs = res.runs
    } catch {
      // Network/server blip. Fail OPEN to the landing rather than stranding
      // them on a cover that never lifts; "Enter the studio" retries.
      showLanding()
      return
    }
    if (!fresh && runs.length) {
      // The studio proper is a walkrec run, so prefer the most recent one of
      // those; otherwise the most recent film of any kind is still their work.
      // `listMyRuns` already orders newest-first.
      const target = runs.find((r) => r.film_mode === 'walkrec') ?? runs[0]
      router.replace(`/runs/${target.id}`)
      return
    }
    clearBootStamp()
    setBooting(false)
    setView('studio-entry')
  }, [getToken, router, showLanding])

  // ── The one decision, made once, after auth resolves ──────────────────────
  const decidedRef = useRef(false)
  useEffect(() => {
    if (loading || decidedRef.current) return
    decidedRef.current = true
    void (async () => {
      const { landing, fresh } = readIntent()

      // 1. A URL typed elsewhere and interrupted by the Google round-trip
      //    outranks everything: it is the only thing on this page that can be
      //    lost, and it is lost silently.
      const pending = readPendingBuild()
      if (pending && isValidBuildUrl(pending.url)) {
        if (user) {
          clearPendingBuild()
          await runBuild(pending)
          return
        }
        // Came back signed OUT (sign-in cancelled or failed). KEEP the stash —
        // unlike the old landing there is no composer to restore it into, so
        // consuming it here would destroy the URL with nothing to show for it.
        // It resumes on the next return instead.
      } else if (pending) {
        // Unreadable or empty: it can never be acted on, and leaving it would
        // re-check it on every visit forever.
        clearPendingBuild()
      }

      // 2. The escape hatch, and everyone we have no reason to think is signed in.
      if (landing || !user) {
        showLanding()
        // `?new=1` is someone who pressed a Build/Start button elsewhere in the
        // app. Signed out, the honest next step is the sign-in gate over the
        // landing rather than dropping them at the top of a marketing page with
        // no sign that their click did anything.
        if (fresh && !user && !landing) setGateOpen(true)
        return
      }

      // 3. Optimistically signed in — worth asking the server about.
      await enterStudio()
    })()
  }, [loading, user, runBuild, enterStudio, showLanding])

  // The landing's CTA. Signed out, this is where sign-in begins; the Google
  // path returns to `/` and the decision above takes it from there.
  function onEnterStudio() {
    if (user) {
      void enterStudio()
      return
    }
    setGateOpen(true)
  }

  return (
    <>
      <script dangerouslySetInnerHTML={{ __html: BOOT_PROBE }} />
      <BootScreen on={booting} />

      {view === 'landing' ? <PloyLanding onEnterStudio={onEnterStudio} /> : null}
      {view === 'studio-entry' ? <StudioEntry getToken={getToken} notice={notice} /> : null}

      <AuthGate
        open={gateOpen}
        onClose={() => setGateOpen(false)}
        // Nothing to stash: this door has no composer. Deliberately does NOT
        // clear an existing stash either — a URL typed in the studio and
        // interrupted here should still resume when Google returns.
        onBeforeRedirect={() => {}}
        onSignedIn={() => {
          setGateOpen(false)
          setNotice(null)
          void enterStudio()
        }}
      />
    </>
  )
}
