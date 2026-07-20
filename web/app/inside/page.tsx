'use client'
// ═══════════════ /inside — DEVELOPER MODE, ON THE STUDIO GROUND ══════════════
//
// This page used to wear the old white chrome: `TopBar` from components/Brand
// over a dotted white ground, an amber "Developer mode" pill and amber buttons.
// It now wears the same shell as /analytics — studio ground, one white card,
// #E6E6E3 hairlines, the rail — because an operator surface that looks like a
// different product depending on which link you pressed is the bug, not the
// chrome. /analytics made that call first; this page follows it.
//
// WHAT DID NOT CHANGE, DELIBERATELY: every behaviour of the pairing flow.
// The `?key=` capture (and the immediate strip of the key from the address
// bar), the sessionStorage stash across the Google round-trip, the auto-pair
// once auth resolves, and the signed-out submit that stashes → signs in →
// resumes at `?resume=1`. This was a reskin of the chrome; if pairing behaves
// differently it is a bug in this rewrite, not a new opinion about pairing.
//
// THE RAIL LIGHTS NOTHING HERE. Developer mode is owner/judge-facing and
// deliberately not one of the rail's entries — same reasoning, and same
// `current="none"`, as /analytics (see the note there and the 'none' member's
// own comment in OverviewRail).
//
// FIXED SHELL, PORTALLED — same reason as /analytics, /new and LibraryShell:
// app/template.tsx wraps every route in a framer-motion transform, and a
// position:fixed child of a transformed ancestor is positioned against that
// ancestor rather than the viewport. Rendering into document.body is what makes
// `inset:0` mean the screen; the stage scrolls, the body never does.
import { Suspense, useCallback, useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import { createPortal } from 'react-dom'
import { useSearchParams } from 'next/navigation'
import { useAuth } from '../../lib/auth'
import OverviewRail from '../components/overview/OverviewRail'
import FeedbackModal from '../runs/[id]/FeedbackModal'
import FilmoLoader, { GROUND_STUDIO } from '../components/FilmoLoader'
import { pairDeveloper } from '../actions'
import { FEATURED_RUN_ID } from '../../lib/featured-run'

// The dev-mode key is stashed across the Google OAuth round-trip so a `?key=` link
// works even for a logged-out judge: stash → sign in → return → auto-pair. Mirrors
// the composer's PENDING_KEY auto-resume in app/page.tsx.
const PENDING_DEV_KEY = 'ws_pending_dev_key'

type Status = 'idle' | 'pairing' | 'ok' | 'rejected' | 'signin'

// The pairing card and nothing else — the shell around it (rail, ground,
// feedback sheet) belongs to the page component below, so this inner component
// is exactly the part `useSearchParams` forces behind a Suspense boundary.
function InsideInner() {
  const search = useSearchParams()
  const { user, loading, signInWithGoogle, getToken } = useAuth()

  const [key, setKey] = useState('')
  const [status, setStatus] = useState<Status>('idle')
  const [error, setError] = useState<string | null>(null)
  const autoRan = useRef(false)

  // Run the server-side validation + pairing for the signed-in user.
  const pair = useCallback(
    async (rawKey: string) => {
      const k = rawKey.trim()
      if (!k) return
      setStatus('pairing')
      setError(null)
      try {
        const accessToken = await getToken()
        if (!accessToken) {
          setStatus('rejected')
          setError('Please sign in first, then enter your key.')
          return
        }
        const { ok } = await pairDeveloper({ key: k, accessToken })
        if (ok) {
          setStatus('ok')
          try {
            sessionStorage.removeItem(PENDING_DEV_KEY)
          } catch {
            /* ignore */
          }
        } else {
          setStatus('rejected')
          setError('That key was not accepted.')
        }
      } catch {
        setStatus('rejected')
        setError('Could not reach the pairing service. Try again.')
      }
    },
    [getToken],
  )

  // Capture a `?key=` from the URL into the field (so the form reflects a shared link),
  // then strip it from the address bar so the secret isn't left sitting in history.
  useEffect(() => {
    const urlKey = search.get('key')
    if (urlKey && !key) {
      setKey(urlKey)
      // Clean the URL (drop ?key=) without a navigation.
      if (typeof window !== 'undefined') {
        const u = new URL(window.location.href)
        u.searchParams.delete('key')
        window.history.replaceState({}, '', u.pathname + (u.search ? u.search : '') + u.hash)
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search])

  // Auto-pair once auth resolves: a `?key=` (in field) or a stashed key + signed-in user
  // → pair immediately. Covers both the resume-from-OAuth path and the direct-link path.
  useEffect(() => {
    if (loading || autoRan.current) return

    // The key may live in the field (from ?key=) or in sessionStorage (from the OAuth round-trip).
    let candidate = key
    if (!candidate) {
      try {
        candidate = sessionStorage.getItem(PENDING_DEV_KEY) || ''
      } catch {
        /* ignore */
      }
      if (candidate) setKey(candidate)
    }
    if (!candidate) return

    autoRan.current = true
    if (user) {
      void pair(candidate)
    }
    // If not signed in, we wait for an explicit "Pair" click (or a resume=1 return) so we
    // don't redirect a judge unexpectedly on first paint.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading, user, key])

  function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    const k = key.trim()
    if (!k) return
    if (user) {
      void pair(k)
      return
    }
    // Logged out: stash the key and route through Google sign-in, returning to ?resume=1.
    try {
      sessionStorage.setItem(PENDING_DEV_KEY, k)
    } catch {
      /* sessionStorage unavailable — the return just won't auto-resume */
    }
    setStatus('signin')
    const dest =
      (typeof window !== 'undefined' ? window.location.origin : '') + '/inside?resume=1'
    void signInWithGoogle(dest)
  }

  return (
    <div className="in-card">
      <span className="in-pill">
        <i aria-hidden />
        Developer mode
      </span>
      <h1 className="in-h1">See the machinery</h1>
      <p className="in-lede">
        Enter your developer key to unlock the inside view — the Conversion Read scores,
        the Stripe checkout gate (with the autonomous self-decline path also built in),
        the host-side real-site capture, and the live P&amp;L behind a build. Pairing
        sticks to your account, so you only do this once.
      </p>

      {status === 'ok' ? (
        <div className="in-ok">
          <b>Developer mode is on for this account.</b>
          <span>
            Open the featured canonical run, or append a run id to <code>/inside/</code>.
          </span>
          <Link href={`/inside/${FEATURED_RUN_ID}`} className="in-primary in-primary-link">
            View the featured run
          </Link>
        </div>
      ) : (
        <form onSubmit={onSubmit} className="in-form">
          <label className="in-label">
            <span>Developer key</span>
            <input
              value={key}
              onChange={(e) => setKey(e.target.value)}
              type="password"
              autoComplete="off"
              placeholder="Paste your key"
              className="in-input"
            />
          </label>

          {error && (
            <p className="in-error" role="alert">
              {error}
            </p>
          )}
          {status === 'signin' && (
            <p className="in-note">Redirecting to Google — your key is saved…</p>
          )}

          <button disabled={status === 'pairing' || !key.trim()} className="in-primary">
            {status === 'pairing'
              ? 'Pairing…'
              : user
                ? 'Unlock developer mode'
                : 'Sign in with Google & unlock'}
          </button>

          {!user && !loading && (
            <p className="in-fine">
              You&rsquo;ll sign in with Google to bind the key to your account — your key is
              saved.
            </p>
          )}
        </form>
      )}
    </div>
  )
}

export default function InsidePage() {
  const { getToken } = useAuth()
  const [mounted, setMounted] = useState(false)
  // Whoever renders the rail owns the feedback sheet — the account circle is the
  // way in, the sheet belongs to the surface that outlives the click.
  const [fbOpen, setFbOpen] = useState(false)

  useEffect(() => setMounted(true), [])

  // Pre-mount there is no document.body to portal into; the boot screen on the
  // destination's own ground keeps the wait continuous (same as /new).
  if (!mounted) return <FilmoLoader ground={GROUND_STUDIO} />

  return createPortal(
    <div className="in-root">
      <OverviewRail current="none" getToken={getToken} onFeedback={() => setFbOpen(true)} />

      <main className="in-stage">
        <div className="in-inner">
          {/* useSearchParams() requires a Suspense boundary under the App Router. */}
          <Suspense fallback={<FilmoLoader ground={GROUND_STUDIO} fit="block" />}>
            <InsideInner />
          </Suspense>

          <Link href="/" className="in-back">
            Back to Filmo
          </Link>
        </div>
      </main>

      <FeedbackModal
        open={fbOpen}
        onClose={() => setFbOpen(false)}
        getToken={getToken}
        context="/inside"
      />

      <style>{`
        .in-root { position:fixed; inset:0; display:flex; background:#F1F1EF;
          color:#1B1B1A; font:14px/1.5 Inter,-apple-system,sans-serif; z-index:50; }
        .in-stage { flex:1 1 0; min-width:0; min-height:0; overflow-y:auto;
          overflow-x:hidden; display:flex; }
        .in-inner { margin:auto; width:100%; max-width:560px;
          padding:48px 24px 56px; display:flex; flex-direction:column; }

        /* One white card on the studio ground — the same surface grammar as
           /analytics' cards and /login's form card. */
        .in-card { background:#fff; border:1px solid #E6E6E3; border-radius:16px;
          padding:28px 26px;
          box-shadow:0 1px 2px rgba(27,27,26,.04), 0 24px 48px -32px rgba(27,27,26,.28); }

        /* The same pill shape /analytics uses for "Stripe test-mode": a fact
           about everything below it, stated beside the title, in the accent. */
        .in-pill { display:inline-flex; align-items:center; gap:6px;
          background:#EAF1FF; border:1px solid #C9D9F8; border-radius:99px;
          padding:4px 11px; font-size:12px; font-weight:600; color:#1D4ED8; }
        .in-pill i { width:6px; height:6px; border-radius:50%; background:#3B82F6; }

        .in-h1 { margin:14px 0 0; font-size:22px; font-weight:650;
          letter-spacing:-.018em; color:#1B1B1A; }
        .in-lede { margin:8px 0 0; font-size:13.5px; line-height:1.6; color:#8A8A86; }

        .in-form { margin-top:20px; display:flex; flex-direction:column; gap:14px; }
        .in-label { display:block; }
        .in-label span { display:block; margin-bottom:6px; font-size:13px;
          font-weight:600; color:#1B1B1A; }
        .in-input { width:100%; background:#fff; border:1px solid #E6E6E3;
          border-radius:10px; padding:10px 12px;
          font:13.5px/1.4 ui-monospace,SFMono-Regular,Menlo,monospace; color:#1B1B1A;
          outline:none; transition:border-color .15s, box-shadow .15s; }
        .in-input::placeholder { color:#B6B6B2;
          font-family:Inter,-apple-system,sans-serif; }
        .in-input:hover { border-color:#C9C9C4; }
        .in-input:focus-visible { border-color:#3B82F6;
          box-shadow:0 0 0 3px rgba(59,130,246,.18); }

        /* The product's primary control: the black pill /login and /analytics
           already use. Amber was the old chrome's accent; it does not follow. */
        .in-primary { width:100%; border:1px solid #1B1B1A; background:#1B1B1A;
          color:#fff; border-radius:10px; padding:11px 16px; cursor:pointer;
          font:600 14px/1.2 Inter,-apple-system,sans-serif;
          transition:background-color .15s, border-color .15s, opacity .15s; }
        .in-primary:hover:not(:disabled) { background:#000; border-color:#000; }
        .in-primary:focus-visible { outline:2px solid #3B82F6; outline-offset:2px; }
        .in-primary:disabled { opacity:.55; cursor:default; }
        .in-primary-link { display:flex; align-items:center; justify-content:center;
          width:auto; text-decoration:none; margin-top:14px; }

        .in-ok { margin-top:20px; border:1px solid #E6E6E3; border-radius:12px;
          background:#FAFAF8; padding:16px 18px; display:flex;
          flex-direction:column; gap:5px; }
        .in-ok b { font-size:14.5px; font-weight:650; color:#1B1B1A; }
        .in-ok span { font-size:13px; line-height:1.55; color:#8A8A86; }
        .in-ok code { font:12px/1 ui-monospace,SFMono-Regular,Menlo,monospace;
          background:#F1F1EF; border-radius:4px; padding:2px 5px; color:#6E6E6A; }

        /* #DC2626 is the app's existing "something went wrong" ink. */
        .in-error { margin:0; font-size:13px; line-height:1.5; color:#DC2626; }
        .in-note { margin:0; font-size:13px; color:#8A8A86; }
        .in-fine { margin:0; text-align:center; font-size:12px; line-height:1.5;
          color:#B6B6B2; }

        .in-back { margin:18px auto 0; font-size:13px; color:#8A8A86;
          text-decoration:none; border-radius:4px; }
        .in-back:hover { color:#1B1B1A; }
        .in-back:focus-visible { outline:2px solid #3B82F6; outline-offset:3px;
          color:#1B1B1A; }

        @media (max-width:760px) {
          .in-inner { padding:32px 16px 44px; }
          .in-card { padding:22px 18px; } }
        @media (prefers-reduced-motion:reduce) {
          .in-input, .in-primary { transition:none; } }
      `}</style>
    </div>,
    document.body,
  )
}
