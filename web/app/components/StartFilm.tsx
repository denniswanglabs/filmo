'use client'
// ═════════════════════ START A FILM, AND GO THERE ════════════════════════════
//
// THE DEFECT THIS EXISTS TO KILL. Pressing send used to change nothing. The
// composer stayed on screen, the input kept its text, and the only evidence
// that the click had landed was twelve grey pixels of "Starting the filmo…"
// under the box. Then, between three and four and a half seconds later
// (measured, `/new`, warm connection), the studio arrived. Dennis, 2026-07-19:
// "when i ran stripe, it took a while before it jumped to this page, and i
// simply thought that it was broken."
//
// He is describing the correct conclusion. A button that does not visibly do
// anything IS broken, whatever the network is doing behind it. The wait is not
// the defect — the film takes minutes and everyone knows it. The defect is
// being left standing on the screen you just left.
//
// ── WHY THE COVER GOES UP BEFORE THE NETWORK, NOT AFTER ─────────────────────
// The obvious fix is "make createBuild fast enough that the wait stops
// mattering". It cannot be made fast enough, and it is worth writing down why
// so nobody tries again: before a run id can exist, the server must (1) verify
// the caller's token against InsForge, (2) check the rate limit, (3) check the
// credit balance, and only then (4) insert the run. Steps 2 and 3 now run
// concurrently (see actions.ts), but 1 → gates → 4 is three sequential round
// trips to Singapore that no amount of tuning removes: ~930ms on a warm
// connection, ~2.4s on a cold one, more on a phone. Every one of those trips is
// load-bearing — identity cannot be inferred, and a gate that runs after the
// insert is not a gate.
//
// So the id is genuinely not available in "immediately", and the transition
// cannot be allowed to wait for it. It waits for the CLICK instead.
//
// ── WHY THIS COVERS IN PLACE RATHER THAN NAVIGATING TO A PLACEHOLDER ────────
// The other way to leave the composer at once is to navigate somewhere — a
// `/runs/pending` shell — and swap the real id in when it lands. That buys a
// correct URL about three seconds earlier and costs three things: a route that
// matches `/runs/[id]` and has to be special-cased out of it, a history entry
// to clean up, and a failure path where the reader is already standing on a run
// that turns out not to exist. This raises a full-screen cover instead, from
// the door the reader is standing in, so:
//   • no fabricated id ever reaches the URL, the history, or the run page;
//   • a failure lowers the cover back onto the door that made the call, WITH
//     its message — there is no state in which a loader spins forever;
//   • the destination's own `runs/[id]/loading.tsx` renders the SAME
//     `FilmoLoader` on the SAME ground, so the cover does not blink on the way
//     out. Click to studio is one continuous branded screen.
// The reader cannot perceive the URL lag; they can perceive all three costs.
//
// ── AND WHY THERE IS EXACTLY ONE OF THESE ───────────────────────────────────
// Three surfaces start a film: the studio composer (`/new`, `/?new=1` via
// StudioEntry, and the studio's own "New filmo" tab — all one component), the
// Overview's suggestion cards, and the landing's resume of a URL stashed before
// sign-in. They used to carry three private copies of the same forty lines:
// validate, get a token, call createBuild, special-case `limit`, catch the
// opaque throw, push. Three copies of `stickyLook()`. Three copies of
// BUILD_DEFAULTS, each with a comment warning that the other two existed.
//
// A copy is not a style problem here, it is a product one: two doors that
// disagree about a single createBuild parameter turn one URL into two different
// films with no visible cause and nobody to blame. So the parameters, the
// wording, the stash, the cover and the navigation all live here, once, and a
// door contributes only the thing that is genuinely its own — how it asks for a
// sign-in, and where it puts the sentence when the answer is no.
import { useCallback, useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { useRouter } from 'next/navigation'
import { createBuild } from '../actions'
import FilmoLoader, { GROUND_STUDIO } from './FilmoLoader'
import { isValidBuildUrl, writePendingBuild } from '../../lib/pending-build'

// ── THE PARAMETERS, PINNED ONCE ─────────────────────────────────────────────
//   brain    'ultra-paid'  the paid flagship (CLAUDE.md: paid Nemotron, so a
//                          free-tier 429 can never decide a user's film). NOTE
//                          createBuild's own fallback for an absent brain is
//                          'super-free' — omitting it silently downgrades.
//   mode     'mock'        real Remotion cards, $0 third-party spend.
//   payMode  'auto'        payments are dormant for the open beta.
export const BUILD_DEFAULTS = {
  brain: 'ultra-paid',
  mode: 'mock' as const,
  payMode: 'auto' as const,
}

// ── A SURFACE MAKES ITS OWN KIND OF FILM ────────────────────────────────────
// createBuild's rule is that a bare submit yields walkrec for the operator and
// classic for everyone else. That rule is right for the LANDING, where the
// visitor has expressed no preference and the server picks. It is wrong for
// every door that lives INSIDE the studio: the rail, the thread, the beat board
// and the director all belong to the walkrec pipeline, so a non-owner pressing
// send there would get a classic run — a completely different page — and be
// navigated out of the room they were standing in with nothing on screen
// explaining why. A sticky 'engineered-night' still wins: that is a visitor
// asking for a specific look, which outranks a surface's default.
export const STUDIO_LOOK = 'walkrec' as const

/**
 * The sticky look the landing writes when someone arrives with `?look=…`.
 * A stored 'classic' is deliberately NOT restored, because the landing does not
 * restore it either and the server's default is what should decide. Mirroring
 * the quirk is what keeps the doors identical; "fixing" it on one side is what
 * makes them differ.
 */
export function stickyLook(): 'walkrec' | 'engineered-night' | undefined {
  try {
    const saved = localStorage.getItem('filmo-look')
    if (saved === 'walkrec' || saved === 'engineered-night') return saved
  } catch {
    /* private mode — the server default decides */
  }
  return undefined
}

/** Typing "acme.com" is the same intent as typing "https://acme.com". Fill in
 *  the scheme rather than failing a URL the user got right. */
export function normalizeUrl(raw: string): string {
  const t = (raw || '').trim()
  if (!t) return ''
  return /^https?:\/\//i.test(t) ? t : `https://${t}`
}

// ── THE SENTENCES, ALSO ONCE ────────────────────────────────────────────────
// THREE genuinely different conditions, and the difference matters to the reader:
//   • "you are not signed in"            (no token at all)
//   • "you looked signed in and the      (a token the SERVER verified and
//      server disagreed"                  rejected — a real 401/403)
//   • "the backend blinked; nothing      (a timeout / InsForge brownout /
//      started, try again"                unexpected 500 between click and run)
// They used to be worded several slightly different ways across three files, and
// — worse — the third collapsed into the second: a transient backend hiccup told
// a still-signed-in reader their session had expired and put the sign-in sheet in
// front of them. That is the defect this file now exists (also) to kill.
export const NEEDS_SIGN_IN =
  'Sign in to start filming — your link is saved.'
export const SESSION_REJECTED =
  'Your session expired — sign in again to start the filmo.'
// THE INVARIANT, IN ONE SENTENCE. The session is fine — so this must never read
// as "signed out" and never raise a gate. NOTHING was started, and that is not a
// hope: the run row is written LAST, after identity and both gates, so a failure
// anywhere before it leaves nothing half-made. The URL never leaves the box, so
// the retry is a single keystroke. createBuild classifies the server-visible
// failures into { unavailable } and the hook's catch classifies the one it can't
// see (the server action's own transport failing) the same way — both land here.
export const BUILD_UNAVAILABLE =
  "That didn't go through — nothing was started. Try again."
export const BAD_URL = 'Enter a valid website URL.'

/**
 * Stash a URL to be resumed by `/` after the Google round-trip, with exactly
 * the parameters `startFilm` would have used.
 *
 * Signing in with Google navigates the WHOLE BROWSER away and always returns to
 * `/` — AuthGate calls signInWithGoogle() with no redirectTo — so no door can
 * resume its own build; the landing does it, by reading this stash on mount.
 * `startFilm` calls this on every refusal, so a gate is never opened over an
 * un-stashed URL. It is exported for the one case that leaves: a reader who
 * EDITS the box while the sign-in sheet is open, whose newer URL would
 * otherwise be thrown away in favour of the one that failed.
 *
 * Silently ignores a URL that could never build — a stash of `{url:''}` is the
 * classic cause of an empty auto-fire on the OAuth return.
 */
export function stashPendingFilm(rawUrl: string): void {
  const url = normalizeUrl(rawUrl)
  if (!isValidBuildUrl(url)) return
  writePendingBuild({
    url,
    brain: BUILD_DEFAULTS.brain,
    look: stickyLook() || STUDIO_LOOK,
    // Pinned false by the module on read AND write: stashes written before
    // payments were switched off carry true and would resurrect the checkout
    // gate on resume.
    requirePay: false,
  })
}

/** Why `startFilm` could not start a film. The door decides what to DO about
 *  it; the wording is already decided here. */
export type FilmStartRefusal = {
  /** 'sign-in'      the reader has to authenticate — doors with a gate open it.
   *  'limit'        a real, structured answer from the server (a cap): the credit
   *                 allowance, or the short-window build throttle.
   *  'unavailable'  the backend blinked and nothing was started. Retryable words,
   *                 the URL is kept, and NO door opens a sign-in gate over it — a
   *                 still-valid session is never sent to sign in because of a blip.
   *  'invalid'      the URL was never going to work.
   *
   *  A door's ONLY branch is `kind === 'sign-in'` → open the gate; every other
   *  kind is just a sentence it shows. So a door needs no change to honour a new
   *  kind — 'unavailable' shows its words and, correctly, never gates. */
  kind: 'sign-in' | 'limit' | 'unavailable' | 'invalid'
  message: string
  /** The normalized URL, for a door that wants to say it back. */
  url: string
}

// ═══════════════════════════ THE ARRIVAL STATE ═══════════════════════════════
// The branded loader, on the studio's ground, over everything.
//
// GROUND. `GROUND_STUDIO` is `#F1F1EF` — `.wk-root`, `.ov-root`, `.nw-root` and
// `runs/[id]/loading.tsx` all sit on it. Handing this a white or a night ground
// would turn the hand-off into a flash; matching it makes the whole wait one
// screen that dissolves into the studio.
//
// PORTALLED, DELIBERATELY. `app/template.tsx` wraps every route in a
// framer-motion div that animates `y`, and a transformed ancestor positions its
// fixed descendants against ITSELF rather than the viewport — the same contract
// note Workspace, /new and /overview all carry. Worse here than elsewhere:
// `/new` renders its whole shell through a portal, so the motion div wrapping
// that route has no height at all, and a cover left inside it would collapse to
// nothing. Rendering into document.body is what makes `inset:0` mean the
// screen.
//
// NO COPY ON IT. `FilmoLoader`'s own contract — the mark, the word, and nothing
// else, because at this moment the app genuinely knows nothing yet and anything
// more would be an invention. It is honest about the one thing it could get
// wrong: it does not name a phase, because no phase has begun. The words go to
// the screen reader, where a live region is the right place for them.
export function FilmStartCover({ on }: { on: boolean }) {
  // No document.body to portal into before mount, and the server has no body
  // either. The cover is only ever raised by a click, which cannot happen
  // before hydration, so nothing is lost by rendering nothing until then.
  const [mounted, setMounted] = useState(false)
  useEffect(() => setMounted(true), [])
  if (!mounted) return null

  return createPortal(
    <div className={'sf-cover' + (on ? ' on' : '')}>
      <FilmoLoader ground={GROUND_STUDIO} label="Starting your film" />
      <style>{`
        /* Above every fixed shell in the product: .nw-root is z-index 50,
           .wk-root and .fl-studioentry are unindexed fixed layers. Matches the
           landing's own cover (.fl-boot, z-index 999) so the two never fight. */
        .sf-cover { position:fixed; inset:0; z-index:999; background:${GROUND_STUDIO};
          opacity:0; visibility:hidden;
          transition:opacity .22s ease, visibility .22s; }
        .sf-cover.on { opacity:1; visibility:visible; }
        @media (prefers-reduced-motion:reduce) { .sf-cover { transition:none; } }
      `}</style>
    </div>,
    document.body,
  )
}

// ═════════════════════════════ THE ONE FUNCTION ══════════════════════════════
/**
 * "Start a film and go there." Every door calls this and nothing else.
 *
 * Returns `cover` as a ready-made element rather than asking each caller to
 * render `<FilmStartCover on={starting} />` itself: a door that drops one line
 * from its JSX is a door that silently goes back to doing nothing on click,
 * which is the exact defect this file exists to prevent.
 */
export function useStartFilm({
  getToken,
  onRefused,
}: {
  getToken: () => Promise<string | null>
  /** The one thing a door owns. A surface with a sign-in gate opens it on
   *  `kind === 'sign-in'`; a surface without one just says the sentence. */
  onRefused: (refusal: FilmStartRefusal) => void
}) {
  const router = useRouter()
  const [starting, setStarting] = useState(false)

  const startFilm = useCallback(
    async (rawUrl: string): Promise<void> => {
      const url = normalizeUrl(rawUrl)
      // createBuild THROWS on a bad URL, and a thrown server action surfaces in
      // production as the opaque "Server Components render … digest" 500 — so
      // the message the reader would see is no message at all. Check here, once,
      // for every door.
      if (!isValidBuildUrl(url)) {
        onRefused({ kind: 'invalid', message: BAD_URL, url })
        return
      }

      // ── THE WHOLE POINT OF THIS FILE ──────────────────────────────────────
      // Before the token, before the server, before anything that can be slow:
      // the screen changes. Everything below this line may take seconds and the
      // reader is already watching the studio's ground.
      setStarting(true)

      const look = stickyLook() || STUDIO_LOOK
      // A typed URL must survive sign-in — see stashPendingFilm. It happens on
      // BOTH refusal paths and in every door. (It used to happen in one of the
      // three, which is why a suggestion card that met a dead session lost the
      // reader's intent outright.)
      const stash = () => stashPendingFilm(url)

      try {
        const accessToken = await getToken()
        // NO TOKEN IS NOT A NO-OP. createBuild needs one and throws without it,
        // so the honest response to a session that has quietly expired under a
        // still-signed-in-looking UI is to ask for a sign-in — never to swallow
        // the click and leave the reader tapping a button that does nothing.
        if (!accessToken) {
          setStarting(false)
          stash()
          onRefused({ kind: 'sign-in', message: NEEDS_SIGN_IN, url })
          return
        }

        const res = await createBuild({ accessToken, url, look, ...BUILD_DEFAULTS })

        // createBuild answers with a DISCRIMINATED refusal rather than throwing,
        // because a thrown server action is the opaque "Server Components render …
        // digest" 500 on the client — its real reason is unreadable here, so the
        // classification has to arrive as a value. Three shapes, three honest doors.

        // authError — the server VERIFIED the token and rejected it: a real 401/403,
        // NOT a brownout (verifyUser returns null only on a genuine rejection and
        // THROWS on an unreachable auth service — see lib/insforge). This is the one
        // failure that has actually earned the sign-in sheet, so it opens the gate,
        // keeps the URL for after the Google round-trip, and says the same "expired"
        // sentence as before. It is the ONLY non-'sign-in'-token path that gates.
        if ('authError' in res) {
          setStarting(false)
          stash()
          onRefused({ kind: 'sign-in', message: SESSION_REJECTED, url })
          return
        }

        // limit — a cap the server chose to report (the credit allowance, or the
        // short-window build throttle). A real answer, not a broken session: say it
        // and stop, and do NOT open a sign-in gate over it.
        if ('limit' in res) {
          setStarting(false)
          onRefused({ kind: 'limit', message: res.message, url })
          return
        }

        // unavailable — the backend blinked (timeout / InsForge unreachable /
        // unexpected 500) and NOTHING was started. The session is fine, so the one
        // thing this must never do is send a signed-in reader to sign in again.
        // Lower the cover onto retryable words with the URL still in the box; there
        // is no round-trip to survive, so — unlike the two gate paths — it does not
        // stash.
        if ('unavailable' in res) {
          setStarting(false)
          onRefused({ kind: 'unavailable', message: BUILD_UNAVAILABLE, url })
          return
        }

        // Leave the cover UP through the navigation. The client transition
        // keeps this route mounted until the run page is ready, and that page's
        // loading.tsx is the same loader on the same ground, so the reader sees
        // one screen from the click to the studio rather than three.
        router.push(`/runs/${res.runId}`)
      } catch {
        // THE LAST UNKNOWN. createBuild now classifies every failure it can SEE into
        // one of the shapes above, so the only throw that still reaches here is the
        // one it cannot return through: the server action's own transport failing —
        // the browser never reached Vercel, or Vercel died mid-call — which IS,
        // definitionally, the backend blinking. So the conservative reading of an
        // unknown throw is 'unavailable', NEVER 'sign-in': a valid session must not
        // be told to re-authenticate because the wire hiccuped. This used to say
        // "your session expired" and raise the gate on exactly this hiccup — the
        // mislabel this fix removes. Nothing was started, so the cover is lowered
        // (a cover that outlives its build is a spinner that never ends), the words
        // are the same retryable ones, and the URL stays in the box for one-key retry.
        setStarting(false)
        onRefused({ kind: 'unavailable', message: BUILD_UNAVAILABLE, url })
      }
    },
    [getToken, onRefused, router],
  )

  return { startFilm, starting, cover: <FilmStartCover on={starting} /> }
}
