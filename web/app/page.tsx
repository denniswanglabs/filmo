'use client'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '../lib/auth'
import { createBuild, listMyRuns } from './actions'
import { AuthGate } from './components/AuthGate'
import PloyLanding from './components/landing2/PloyLanding'
import BootScreen from './components/landing2/BootScreen'
import StudioEntry from './components/landing2/StudioEntry'
import { BUILD_DEFAULTS, BUILD_UNAVAILABLE } from './components/StartFilm'
import {
  clearPendingBuild,
  isValidBuildUrl,
  readPendingBuild,
  writePendingBuild,
  type PendingBuild,
} from '../lib/pending-build'

/* ───────────────────────────────────────────────────────────────────────────
   `/` IS A DOOR, NOT A PAGE.

   The studio is the product; the landing is the front door. So `/` RENDERS the
   landing for everyone, signed in or not (see step 2 of the decision below),
   and hands anyone onward only when they ask it to:

     on load, anybody .................... the landing
     the CTA, signed in .................. their Overview (`/overview`)
     the CTA, signed in, with `?new=1` ... the studio's "New filmo" surface, here
     a URL stashed before sign-in ........ straight into that build

   Three things about the hand-off are load-bearing enough to state out loud:

   1. NO HTTP REDIRECT IS INVOLVED, ANYWHERE. The session lives in
      origin-scoped localStorage (`insforge.ts`), which no server and no
      middleware can read — a redirect decided on the server would fire for
      nobody. Every hand-off here is a client `router.replace`, which also
      means there is no status code to get wrong: a 301/308 would be cached by
      the browser permanently and rolling the deploy back would NOT free the
      people who had already hit it. There is no way to make that mistake from
      here, and that is deliberate.

   2. THE DESTINATION IS A ROUTE THAT EXISTS FOR AN EMPTY ACCOUNT. The CTA used
      to send a signed-in visitor to their most recent run, and that is exactly
      why a brand-new signup could not be sent anywhere: the studio has no route
      of its own — it is `runs/[id]` — so handing an account with no runs to it
      would either invent an id (greeting a first-time user with "This run could
      not be found") or bounce them back here forever. `/overview` is the route
      that was missing. It renders zeroes and an invitation for an account with
      nothing in it, and it never redirects anyone anywhere, so there is nothing
      for an empty account to loop against. `?new=1` still lands on the composer
      here, which is what "Build" means from everywhere else in the app.

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
  const { user, loading, getToken, oauthReturnFailed } = useAuth()

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

  // A FAILED OAUTH RETURN REOPENS THE GATE, NAMED (2026-07-20 outage). Google
  // bounced the reader back here and the exchange produced no session; without
  // this, they land on an ordinary signed-out landing with no sign anything
  // went wrong — "it threw me back to the landing page" — and their next click
  // reopens the gate as if the first attempt never happened. The gate reopens
  // ITSELF instead, wearing the failure, so retry is one click and the reader
  // knows the product saw it too.
  useEffect(() => {
    if (oauthReturnFailed && !loading && !user) setGateOpen(true)
  }, [oauthReturnFailed, loading, user])

  const showLanding = useCallback(() => {
    clearBootStamp()
    setBooting(false)
    setView('landing')
  }, [])

  // RESUME a build that was interrupted by the Google round-trip. This is not a
  // composer — there is no input on this page — so it does not go through
  // `useStartFilm` (components/StartFilm.tsx) the way the three composing doors
  // do. It does not need to: it already answers the click instantly (the boot
  // cover goes up on the line below, before the token fetch), and it is called
  // from the OAuth-return decision effect rather than from a button.
  //
  // It cannot disagree with those doors about a parameter either, which is the
  // thing that actually matters. `stashPendingFilm` is the ONLY writer of this
  // stash, and it writes BUILD_DEFAULTS.brain and `stickyLook() || STUDIO_LOOK`
  // — so `p.brain` and `p.look` below ARE the shared values, arriving through
  // sessionStorage instead of through a function call. `requirePay` is pinned
  // false on read and write, so payMode is always the shared 'auto'. `mode` was
  // the one value still written out twice; it is imported now, so there is no
  // literal left here that could drift from the composer's.
  //
  // Identity travels as the verified access token (the server derives the owner
  // from it), never a client-set id.
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
          mode: BUILD_DEFAULTS.mode,
          payMode: p.requirePay ? 'human' : 'auto',
        })
        // createBuild classifies its own failures now (mirrors the composing
        // doors' useStartFilm in components/StartFilm.tsx), so this resume path
        // reads the SAME four shapes rather than treating every non-run as a run.

        // authError — the server VERIFIED the token and rejected it (a real
        // 401/403, not a brownout). The one case that earns the sign-in sheet:
        // keep the URL for the round-trip and open the gate.
        if ('authError' in res) {
          writePendingBuild(p)
          setBooting(false)
          setNotice('Sign in again to start the film — your link is saved.')
          setGateOpen(true)
          setView('studio-entry')
          clearBootStamp()
          return
        }
        // limit — the credit cap or the short-window throttle. A real answer, not
        // a broken session — say it and stop.
        if ('limit' in res) {
          setNotice(res.message)
          setBooting(false)
          setView('studio-entry')
          clearBootStamp()
          return
        }
        // unavailable — the backend blinked and nothing was started. The session
        // is fine, so this must NOT raise the sign-in gate: say the retryable line
        // and keep the URL stashed so a second attempt is one tap.
        if ('unavailable' in res) {
          writePendingBuild(p)
          setBooting(false)
          setNotice(BUILD_UNAVAILABLE)
          setView('studio-entry')
          clearBootStamp()
          return
        }
        // Leave the cover up: the client transition keeps this route mounted
        // until the run page is ready, so the wait reads as one beat.
        router.push(`/runs/${res.runId}`)
      } catch {
        // createBuild now returns every failure it can SEE, so the only throw that
        // reaches here is the server action's own transport failing — the backend
        // blinking, not an auth verdict. This used to say "your session expired"
        // and raise the gate on exactly that hiccup; it must not. Nothing was
        // started, so keep the URL and offer a retry — never a sign-in gate over a
        // still-valid session.
        writePendingBuild(p)
        setBooting(false)
        setNotice(BUILD_UNAVAILABLE)
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
    try {
      // The list itself is no longer what decides the destination — /overview
      // is the destination for every signed-in visitor, empty account or not.
      // This call stays because its ANSWER is what makes the redirect safe:
      // `listMyRuns` runs verifyUser on the server, so it is the only thing on
      // this page that can tell a live session from an optimistically-painted
      // dead one.
      const res = await listMyRuns(token || '')
      // THE DEFINITIVE ANSWER. verifyUser ran on the server; a rejection here
      // means the optimistically-painted session is genuinely dead, so the
      // honest destination is the front door, not a studio they can't load.
      if ('authError' in res) {
        showLanding()
        return
      }
    } catch {
      // Network/server blip. Fail OPEN to the landing rather than stranding
      // them on a cover that never lifts; "Enter the studio" retries.
      showLanding()
      return
    }
    if (!fresh) {
      router.replace('/overview')
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

      // 2. EVERYONE GETS THE LANDING. `/` is the front door, not a router
      //    (Dennis, 2026-07-19: "no signed in still go through the landing
      //    page"). It used to bounce a signed-in visitor straight into the
      //    studio, which meant the one person who most needed to see the front
      //    door — the person who owns it — was the only one who never did. A
      //    landing nobody on the team ever looks at is a landing that rots.
      //    Entering the studio is now something you DO, via the CTA below,
      //    rather than something that happens to you.
      //
      //    This also deletes the entire redirect: no auth-shaped navigation
      //    fires on load at all, so there is no ordering hazard against the
      //    OAuth exchange above, no flash-then-bounce, and nothing for a stale
      //    optimistic session to get wrong. The only auto-navigation left is
      //    step 1, which is a URL the user typed and would otherwise lose.
      showLanding()
      // `?new=1` is someone who pressed a Build/Start button elsewhere in the
      // app. Signed out, the honest next step is the sign-in gate over the
      // landing rather than dropping them at the top of a marketing page with
      // no sign that their click did anything.
      if (fresh && !user && !landing) setGateOpen(true)
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
        notice={
          oauthReturnFailed && !user
            ? 'That sign-in didn’t complete — nothing was saved. Try again.'
            : undefined
        }
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
