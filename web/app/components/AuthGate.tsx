'use client'
import { useEffect, useState } from 'react'
import { insforge } from '../../lib/insforge'
import { useAuth } from '../../lib/auth'
import { Wordmark } from './Brand'

interface AuthUser {
  id: string
  email?: string
  [k: string]: unknown
}

/**
 * The sign-in gate that appears the moment a logged-out visitor tries to Build.
 * Leads with Google; the composer they just filled stays visible behind it.
 *
 *  - Google  → full-page OAuth redirect; the caller stashes the pending build first,
 *              and the home page auto-resumes it on return.
 *  - Email   → inline sign-in/up (no redirect); on success `onSignedIn(user)` fires so
 *              the build can run immediately.
 *  - Demo    → one-tap shared account (only when configured).
 */
export function AuthGate({
  open,
  onClose,
  onSignedIn,
  onBeforeRedirect,
}: {
  open: boolean
  onClose: () => void
  onSignedIn: (user: AuthUser) => void
  /** Called right before a redirecting provider (Google) navigates away. */
  onBeforeRedirect: () => void
}) {
  const { signInWithGoogle } = useAuth()
  const [showEmail, setShowEmail] = useState(false)
  const [mode, setMode] = useState<'signin' | 'signup'>('signin')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState<null | 'google' | 'email'>(null)
  const [error, setError] = useState<string | null>(null)
  // Google-only accounts have no password in InsForge and there is no reset flow, so a
  // failed password sign-in nudges toward Google. (Provider isn't knowable client-side,
  // so the hint shows on every credentials failure by design.)
  const [showGoogleHint, setShowGoogleHint] = useState(false)

  // Reset transient state whenever the gate is reopened.
  useEffect(() => {
    if (open) {
      setError(null)
      setShowGoogleHint(false)
      setBusy(null)
    }
  }, [open])

  // Close on Escape.
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open) return null

  async function google() {
    setError(null)
    setShowGoogleHint(false)
    setBusy('google')
    try {
      onBeforeRedirect()
      await signInWithGoogle()
      // Browser navigates away; nothing after this runs.
    } catch (err) {
      setBusy(null)
      setError(err instanceof Error ? err.message : 'Could not start Google sign-in')
    }
  }

  async function emailSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setShowGoogleHint(false)
    setBusy('email')
    try {
      if (mode === 'signup') {
        const { data, error } = await insforge.auth.signUp({
          email,
          password,
          name: email.split('@')[0],
        })
        if (error) throw new Error(error.message || 'Sign up failed')
        if (data?.requireEmailVerification) {
          throw new Error('Check your email to verify, then sign in.')
        }
      } else {
        const { error } = await insforge.auth.signInWithPassword({ email, password })
        if (error) {
          setShowGoogleHint(true)
          throw new Error(error.message || 'Sign in failed')
        }
      }
      const { data } = await insforge.auth.getCurrentUser()
      const u = (data?.user as AuthUser) ?? null
      if (!u) throw new Error('Sign in failed')
      onSignedIn(u)
    } catch (err) {
      setBusy(null)
      setError(err instanceof Error ? err.message : 'Sign in failed')
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="authgate-title"
    >
      {/* Scrim */}
      <button
        aria-label="Close"
        onClick={onClose}
        className="absolute inset-0 cursor-default bg-ink/40 backdrop-blur-sm"
      />

      {/* Card */}
      <div className="relative w-full max-w-sm rounded-2xl border border-black/5 bg-white p-7 shadow-[0_24px_70px_-24px_rgba(20,23,28,0.45)]">
        <button
          onClick={onClose}
          aria-label="Close"
          className="absolute right-4 top-4 grid h-7 w-7 place-items-center rounded-full text-slate-400 transition hover:bg-black/[0.04] hover:text-ink"
        >
          <svg viewBox="0 0 20 20" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.8">
            <path d="M5 5l10 10M15 5L5 15" strokeLinecap="round" />
          </svg>
        </button>

        <div className="mb-5 flex justify-center">
          <Wordmark className="text-lg" />
        </div>

        <h2 id="authgate-title" className="text-center text-lg font-semibold text-ink">
          Sign in to start your build
        </h2>
        <p className="mx-auto mt-1.5 max-w-[19rem] text-center text-sm text-slate-500">
          Your prompt is ready. Sign in and Filmo picks up right where you left off.
        </p>
        <p className="mx-auto mt-3 max-w-[19rem] rounded-lg bg-amber/[0.07] px-3 py-2 text-center text-xs leading-relaxed text-slate-600">
          Filmo is in <span className="font-semibold text-ink">beta</span> — each account gets{' '}
          <span className="font-semibold text-ink">3 free videos a day</span>.
        </p>

        {/* Google — the hero */}
        <button
          onClick={google}
          disabled={!!busy}
          className="mt-6 flex w-full items-center justify-center gap-3 rounded-xl border border-black/10 bg-white py-3 font-medium text-ink transition hover:bg-black/[0.02] disabled:opacity-50"
        >
          <GoogleG />
          {busy === 'google' ? 'Redirecting to Google…' : 'Continue with Google'}
        </button>

        {error && (
          <div className="mt-4 text-center">
            <p className="text-sm text-red-600">{error}</p>
            {showGoogleHint && (
              <p className="mt-1.5 text-xs text-slate-500">
                Signed up with Google? Use Continue with Google above.
              </p>
            )}
          </div>
        )}

        {/* Email fallback */}
        {!showEmail ? (
          <button
            onClick={() => {
              setShowEmail(true)
              setError(null)
            }}
            disabled={!!busy}
            className="mt-3 w-full text-center text-sm text-slate-500 transition hover:text-ink disabled:opacity-50"
          >
            Use email instead
          </button>
        ) : (
          <form onSubmit={emailSubmit} className="mt-5 space-y-3">
            <div className="flex items-center gap-3">
              <div className="h-px flex-1 bg-black/5" />
              <span className="text-xs uppercase tracking-wide text-slate-400">or</span>
              <div className="h-px flex-1 bg-black/5" />
            </div>
            <input
              type="email"
              required
              autoFocus
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@company.com"
              className="w-full rounded-lg border border-black/10 px-3 py-2.5 outline-none transition focus:border-amber"
            />
            <input
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              className="w-full rounded-lg border border-black/10 px-3 py-2.5 outline-none transition focus:border-amber"
            />
            <button
              disabled={!!busy}
              className="w-full rounded-lg bg-amber py-2.5 font-medium text-white transition hover:opacity-90 disabled:opacity-50"
            >
              {busy === 'email'
                ? 'Working…'
                : mode === 'signin'
                  ? 'Sign in & build'
                  : 'Create account & build'}
            </button>
            <p className="text-center text-sm text-slate-500">
              {mode === 'signin' ? 'New here?' : 'Already have an account?'}{' '}
              <button
                type="button"
                onClick={() => {
                  setMode(mode === 'signin' ? 'signup' : 'signin')
                  setError(null)
                }}
                className="font-medium text-amber hover:underline"
              >
                {mode === 'signin' ? 'Create account' : 'Sign in'}
              </button>
            </p>
          </form>
        )}

      </div>
    </div>
  )
}

function GoogleG() {
  return (
    <svg className="h-5 w-5 shrink-0" viewBox="0 0 18 18" aria-hidden>
      <path
        fill="#4285F4"
        d="M17.64 9.2c0-.64-.06-1.25-.16-1.84H9v3.48h4.84a4.14 4.14 0 0 1-1.8 2.72v2.26h2.92c1.7-1.57 2.68-3.88 2.68-6.62z"
      />
      <path
        fill="#34A853"
        d="M9 18c2.43 0 4.47-.8 5.96-2.18l-2.92-2.26c-.81.54-1.84.86-3.04.86-2.34 0-4.32-1.58-5.03-3.7H.96v2.33A9 9 0 0 0 9 18z"
      />
      <path
        fill="#FBBC05"
        d="M3.97 10.72a5.4 5.4 0 0 1 0-3.44V4.95H.96a9 9 0 0 0 0 8.1l3.01-2.33z"
      />
      <path
        fill="#EA4335"
        d="M9 3.58c1.32 0 2.5.46 3.44 1.35l2.58-2.58C13.47.9 11.43 0 9 0A9 9 0 0 0 .96 4.95l3.01 2.33C4.68 5.16 6.66 3.58 9 3.58z"
      />
    </svg>
  )
}
