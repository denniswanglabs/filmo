'use client'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '../lib/auth'
import { OAUTH_RETURN } from '../lib/insforge'
import { createBuild, listMyRuns } from './actions'
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
  // A build that failed on its way in has to say so somewhere, and the landing
  // has no composer to say it in — so it is carried onto the studio surface.
  const [notice, setNotice] = useState<string | null>(null)
  // ── THE LANDING CTA'S STATE (Ploy-style, 2026-07-20) ────────────────────────
  // firstTime = never signed in here AND signed out now → "Log in" + "Start free".
  // Anyone else → "Enter the studio". This is CLIENT chrome: the durable
  // `filmo_has_signed_in` flag (written in lib/auth.tsx, and it OUTLIVES sign-out
  // — the session key does not, which is the whole reason it, not the session, is
  // the signal) is unreadable on the server, so the read runs after hydrate and
  // the CTA settles then. It is deliberately NOT wired to the pre-paint BOOT_PROBE
  // (which keys on the session for the signed-in cover) — a late-settling button
  // is invisible; a late-settling cover is the flash this file exists to kill.
  const [ctaFirstTime, setCtaFirstTime] = useState(false)

  // The stamp lives on <html>, outside React's tree, so React will not clean it
  // up on unmount. Leaving it set would hide the landing on a later client
  // navigation back to `/`.
  useEffect(() => clearBootStamp, [])

  // WHICH CTA THE LANDING SHOWS. Read the durable flag after hydrate; a signed-in
  // visitor is never "first time" whatever the flag says (belt and braces — the
  // flag is written for them anyway). A failed read (private mode) leaves the
  // safe default, "Enter the studio", which routes correctly for everyone.
  useEffect(() => {
    if (user) {
      setCtaFirstTime(false)
      return
    }
    let seen = false
    try {
      seen = localStorage.getItem('filmo_has_signed_in') === '1'
    } catch {
      /* private mode — treat as returning; the CTA still works signed out */
      seen = true
    }
    setCtaFirstTime(!seen)
  }, [user])

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
          // The session died under the resume. The URL is the one thing that can
          // be lost here, so re-stash it (it was consumed on the way in) and send
          // the reader to the one sign-in surface; /login's stash-aware subtitle
          // says it is waiting, and `/`'s resume decision fires it after they sign
          // in. The boot cover stays up through the replace — no flash to the door.
          writePendingBuild(p)
          router.replace('/login')
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
        // 401/403, not a brownout). The one resume outcome that needs a fresh
        // sign-in: keep the URL for the round-trip and send them to /login (which
        // now IS the sign-in surface — the modal is retired).
        if ('authError' in res) {
          writePendingBuild(p)
          router.replace('/login')
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

      // 0. A FAILED OAUTH RETURN → the door, wearing the failure. Google bounced
      //    the reader back with no session; instead of the retired modal
      //    reopening over the landing, forward to /login?retry=1, which shows the
      //    same honest red sentence ("nothing was saved. Try again."). The stash,
      //    if any, is deliberately LEFT for /login to advertise and `/` to resume
      //    after a successful retry — so this outranks the stash cleanup below.
      //    `user` is null on a failed return (auth.tsx: oauthReturnFailed + no
      //    session), so a SUCCESSFUL return never lands here.
      if (oauthReturnFailed && !user) {
        router.replace('/login?retry=1')
        return
      }

      // 1. A URL typed elsewhere and interrupted by the Google round-trip
      //    outranks everything else: it is the only thing on this page that can
      //    be lost, and it is lost silently.
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

      // 1.5 OAUTH RETURN, SIGNED IN, NOTHING TO RESUME → INTO THE STUDIO.
      //     This reader is mid-journey, not visiting: they clicked "Enter the
      //     studio", which is the click that sent them to Google, and Google has
      //     just handed them back here signed in. The resume path above already
      //     took anyone with a stashed build; reaching this line with a `user`
      //     means there is nothing to pick up — so carry them the rest of the way
      //     to /overview instead of depositing them on the marketing page to
      //     press the same button again (Dennis, 2026-07-20: "i arrive at the
      //     landing page having signed in… i have to click on enter the studio
      //     again"). /overview is the empty-account-safe destination enterStudio
      //     also uses; the boot cover stays up through the client replace.
      //
      //     Two gates, both load-bearing:
      //       • OAUTH_RETURN — only the return HOP continues inward. A plain
      //         signed-in visit to `/` (no `insforge_code` in the URL) is not a
      //         journey and still gets the landing, per Dennis's standing rule
      //         ("no signed in still go through the landing page").
      //       • user — SUCCESS only. A FAILED return resolves `user = null`
      //         (auth.tsx sets oauthReturnFailed + no session), so this cannot
      //         fire on it; that path was already caught by step 0 above and
      //         forwarded to /login?retry=1 (5c74691's red sentence, now on the
      //         door), never reaching here.
      if (OAUTH_RETURN && user) {
        setBooting(true)
        router.replace('/overview')
        return
      }

      // 2. `?new=1` SIGNED OUT → THE DOOR. Someone who pressed a Build/Start
      //    button elsewhere in the app arrives here with `?new=1`. Signed out,
      //    the honest next step is the one sign-in surface — send them straight
      //    to /login rather than dropping them at the top of a marketing page
      //    with no sign that their click did anything. Routed BEFORE showLanding
      //    so the marketing page never flashes on the way to the door.
      if (fresh && !user && !landing) {
        setBooting(true)
        router.replace('/login')
        return
      }

      // 3. EVERYONE ELSE GETS THE LANDING. `/` is the front door, not a router
      //    (Dennis, 2026-07-19: "no signed in still go through the landing
      //    page"). It used to bounce a signed-in visitor straight into the
      //    studio, which meant the one person who most needed to see the front
      //    door — its owner — was the only one who never did. A signed-in
      //    visitor with no stash lands here too; entering the studio is now
      //    something you DO, via the state-aware CTA below, not something that
      //    happens to you. No auth-shaped navigation fires on a plain load, so
      //    there is no ordering hazard against the OAuth exchange above and
      //    nothing for a stale optimistic session to get wrong.
      showLanding()
    })()
  }, [loading, user, oauthReturnFailed, runBuild, showLanding, router])

  // The landing's CTAs. Sign-in no longer happens HERE — every signed-out door
  // goes to /login, the single sign-in surface (the modal is retired). Signed in,
  // "Enter the studio" resolves the destination the same way it always did.
  function onEnterStudio() {
    if (user) {
      void enterStudio()
      return
    }
    router.push('/login')
  }
  // The first-run pair (shown only when signed out AND never signed in here).
  // "Start free" carries the create-account intent — /login opens on its signup
  // state — while "Log in" lands on the default sign-in state.
  function onLogIn() {
    router.push('/login')
  }
  function onStartFree() {
    router.push('/login?signup=1')
  }

  return (
    <>
      <script dangerouslySetInnerHTML={{ __html: BOOT_PROBE }} />
      <BootScreen on={booting} />

      {view === 'landing' ? (
        <PloyLanding
          firstTime={ctaFirstTime}
          onEnter={onEnterStudio}
          onLogIn={onLogIn}
          onStartFree={onStartFree}
        />
      ) : null}
      {view === 'studio-entry' ? <StudioEntry getToken={getToken} notice={notice} /> : null}
    </>
  )
}
