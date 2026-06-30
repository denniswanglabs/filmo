'use client'
import { Suspense, useCallback, useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'
import { useAuth } from '../../lib/auth'
import { TopBar } from '../components/Brand'
import { pairDeveloper } from '../actions'
import { FEATURED_RUN_ID } from '../../lib/featured-run'

// The dev-mode key is stashed across the Google OAuth round-trip so a `?key=` link
// works even for a logged-out judge: stash → sign in → return → auto-pair. Mirrors
// the composer's PENDING_KEY auto-resume in app/page.tsx.
const PENDING_DEV_KEY = 'ws_pending_dev_key'

type Status = 'idle' | 'pairing' | 'ok' | 'rejected' | 'signin'

function InsideInner() {
  const router = useRouter()
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
    <>
      <TopBar />
      <main className="surface-dots mx-auto flex min-h-[calc(100vh-3.5rem)] max-w-lg flex-col justify-center px-5 py-16">
        <div className="rounded-2xl border border-black/5 bg-white p-7 shadow-[0_12px_40px_-12px_rgba(20,23,28,0.18)]">
          <span className="inline-block rounded-full border border-amber/30 bg-amber/10 px-2.5 py-1 text-xs font-medium text-amber">
            Developer mode
          </span>
          <h1 className="mt-4 text-2xl font-semibold tracking-tight text-ink">
            See the machinery
          </h1>
          <p className="mt-2 text-sm leading-relaxed text-slate-500">
            Enter your developer key to unlock the inside view — the Conversion Read scores,
            the Stripe checkout gate (with the autonomous self-decline path also built in),
            the host-side real-site capture, and the live P&amp;L behind a build. Pairing
            sticks to your account, so you only do this once.
          </p>

          {status === 'ok' ? (
            <div className="mt-6 rounded-xl border border-nemo/30 bg-nemo/[0.06] p-5">
              <p className="font-medium text-ink">Developer mode is on for this account.</p>
              <p className="mt-1 text-sm text-slate-500">
                Open the featured canonical run, or append a run id to{' '}
                <code className="rounded bg-black/5 px-1 py-0.5 text-xs">/inside/</code>.
              </p>
              <Link
                href={`/inside/${FEATURED_RUN_ID}`}
                className="mt-4 inline-flex items-center justify-center rounded-lg bg-amber px-4 py-2.5 font-medium text-white transition hover:opacity-90"
              >
                View the featured run
              </Link>
            </div>
          ) : (
            <form onSubmit={onSubmit} className="mt-6 space-y-4">
              <label className="block">
                <span className="mb-1.5 block text-sm font-medium text-ink">Developer key</span>
                <input
                  value={key}
                  onChange={(e) => setKey(e.target.value)}
                  type="password"
                  autoComplete="off"
                  placeholder="Paste your key"
                  className="w-full rounded-lg border border-black/10 px-3 py-2.5 font-mono text-sm outline-none transition focus:border-amber"
                />
              </label>

              {error && <p className="text-sm text-red-600">{error}</p>}
              {status === 'signin' && (
                <p className="text-sm text-slate-500">Redirecting to Google — your key is saved…</p>
              )}

              <button
                disabled={status === 'pairing' || !key.trim()}
                className="w-full rounded-lg bg-amber py-2.5 font-medium text-white transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
              >
                {status === 'pairing'
                  ? 'Pairing…'
                  : user
                    ? 'Unlock developer mode'
                    : 'Sign in with Google & unlock'}
              </button>

              {!user && !loading && (
                <p className="text-center text-xs text-slate-400">
                  You&rsquo;ll sign in with Google to bind the key to your account — your key is saved.
                </p>
              )}
            </form>
          )}
        </div>

        <Link href="/" className="mt-6 text-center text-sm text-slate-400 transition hover:text-ink">
          ← Back to Filmo
        </Link>
      </main>
    </>
  )
}

export default function InsidePage() {
  // useSearchParams() requires a Suspense boundary under the App Router.
  return (
    <Suspense fallback={<div className="flex min-h-screen items-center justify-center text-slate-400">Loading…</div>}>
      <InsideInner />
    </Suspense>
  )
}
