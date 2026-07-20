'use client'
// ═══════════════════════ /login — THE DOOR ═══════════════════════════════════
//
// This page used to sit on a dotted white field with `Wordmark` above an amber
// card. It now sits on the studio's daylight (#F1F1EF) with the canonical mark
// set exactly as `landing2/BootScreen` sets it — 50px mark, 38px word, 11px gap,
// -.022em — because the very next screen a successful sign-in produces IS that
// boot screen. Setting the lockup identically makes the hand-off a dissolve
// rather than a resize, which is the same argument BootScreen itself makes for
// choosing the studio ground over the landing's night.
//
// IT DOES NOT GET THE RAIL, AND THAT IS THE POINT. The rail is the product's
// navigation — Overview, Filmos, Assets, your account. Every one of those is a
// place inside a session that does not exist yet. A 72px column of destinations
// nobody can reach is furniture for a room you have not entered, so the door
// gets the brand and the form and nothing else.
//
// EVERY BEHAVIOUR HERE IS THE ONE THAT WAS HERE BEFORE. The already-signed-in
// redirect, the Google path, password sign-in and sign-up, the failed-password
// nudge toward Google, and the e-mail verification fallback are unchanged — only
// their surface is new. The single addition is that a visitor we already believe
// is signed in now sees the loader instead of a sign-in form that is about to
// vanish underneath them.
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { insforge } from '../../lib/insforge'
import { useAuth } from '../../lib/auth'
import FilmoMark from '../components/landing2/FilmoMark'
import FilmoLoader, { GROUND_STUDIO } from '../components/FilmoLoader'

type Mode = 'signin' | 'signup'

export default function LoginPage() {
  const router = useRouter()
  const { user, loading, refresh, signInWithGoogle } = useAuth()
  const [mode, setMode] = useState<Mode>('signin')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // Google-only accounts have no password in InsForge (and no reset flow) — a failed
  // password sign-in nudges toward Google. Provider isn't knowable client-side.
  const [showGoogleHint, setShowGoogleHint] = useState(false)
  // Verification fallback (only used if the project still requires email verification)
  const [needsCode, setNeedsCode] = useState(false)
  const [code, setCode] = useState('')

  // Already signed in → go home.
  useEffect(() => {
    if (!loading && user) router.replace('/')
  }, [loading, user, router])

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setShowGoogleHint(false)
    setBusy(true)
    try {
      if (mode === 'signup') {
        const { data, error } = await insforge.auth.signUp({
          email,
          password,
          name: name || email.split('@')[0],
        })
        if (error) throw new Error(error.message || 'Sign up failed')
        if (data?.requireEmailVerification) {
          setNeedsCode(true)
          return
        }
        // Verification off → session is live.
        await refresh()
        router.replace('/')
        return
      }
      // sign in
      const { error } = await insforge.auth.signInWithPassword({ email, password })
      if (error) {
        setShowGoogleHint(true)
        throw new Error(error.message || 'Sign in failed')
      }
      await refresh()
      router.replace('/')
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  async function onVerify(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setShowGoogleHint(false)
    setBusy(true)
    try {
      const { error } = await insforge.auth.verifyEmail({ email, otp: code })
      if (error) throw new Error(error.message || 'Invalid or expired code')
      await refresh()
      router.replace('/')
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  // ── NOBODY IS SHOWN A DOOR THEY ARE ALREADY THROUGH ─────────────────────────
  // While the session is resolving, and for the frame between "there is a user"
  // and the redirect above actually landing, this is the loader rather than a
  // sign-in form. The redirect is unchanged; what changed is that it no longer
  // flashes a form at somebody who is signed in. Never a bare "Loading…".
  if (loading || user) {
    return (
      <FilmoLoader
        ground={GROUND_STUDIO}
        size="compact"
        label={user ? 'Signing you in' : 'Loading'}
      />
    )
  }

  return (
    <main className="lgn-root">
      <div className="lgn-col">
        {/* The mark and the word, set exactly as the boot screen sets them, so
            signing in dissolves into the studio instead of cutting to it. */}
        <div className="lgn-lockup">
          <FilmoMark />
          <span>Filmo</span>
        </div>

        <div className="lgn-card">
          {needsCode ? (
            <form onSubmit={onVerify} className="lgn-form">
              <div>
                <h1 className="lgn-h1">Check your email</h1>
                <p className="lgn-sub">Enter the 6-digit code we sent to {email}.</p>
              </div>
              <input
                inputMode="numeric"
                autoComplete="one-time-code"
                autoFocus
                value={code}
                onChange={(e) => setCode(e.target.value)}
                placeholder="123456"
                aria-label="Six-digit verification code"
                className="lgn-input lgn-code"
              />
              {error && <p className="lgn-error">{error}</p>}
              <button disabled={busy} className="lgn-primary">
                {busy ? 'Verifying…' : 'Verify & continue'}
              </button>
            </form>
          ) : (
            <form onSubmit={onSubmit} className="lgn-form">
              <div>
                <h1 className="lgn-h1">
                  {mode === 'signin' ? 'Sign in' : 'Create your account'}
                </h1>
                <p className="lgn-sub">
                  {mode === 'signin'
                    ? 'Welcome back to Filmo.'
                    : 'Start turning URLs into finished videos.'}
                </p>
              </div>

              <button
                type="button"
                onClick={() => void signInWithGoogle(window.location.origin + '/')}
                className="lgn-google"
              >
                {/* Google's own mark, in Google's own colours — a brand asset the
                    sign-in guidelines require verbatim, not decoration. */}
                <svg viewBox="0 0 18 18" aria-hidden>
                  <path fill="#4285F4" d="M17.64 9.2c0-.64-.06-1.25-.16-1.84H9v3.48h4.84a4.14 4.14 0 0 1-1.8 2.72v2.26h2.92c1.7-1.57 2.68-3.88 2.68-6.62z" />
                  <path fill="#34A853" d="M9 18c2.43 0 4.47-.8 5.96-2.18l-2.92-2.26c-.81.54-1.84.86-3.04.86-2.34 0-4.32-1.58-5.03-3.7H.96v2.33A9 9 0 0 0 9 18z" />
                  <path fill="#FBBC05" d="M3.97 10.72a5.4 5.4 0 0 1 0-3.44V4.95H.96a9 9 0 0 0 0 8.1l3.01-2.33z" />
                  <path fill="#EA4335" d="M9 3.58c1.32 0 2.5.46 3.44 1.35l2.58-2.58C13.47.9 11.43 0 9 0A9 9 0 0 0 .96 4.95l3.01 2.33C4.68 5.16 6.66 3.58 9 3.58z" />
                </svg>
                Continue with Google
              </button>

              <div className="lgn-or">
                <i />
                <span>or</span>
                <i />
              </div>

              {mode === 'signup' && (
                <Field
                  label="Name"
                  value={name}
                  onChange={setName}
                  type="text"
                  placeholder="Ada Lovelace"
                  autoComplete="name"
                  optional
                />
              )}
              <Field
                label="Email"
                value={email}
                onChange={setEmail}
                type="email"
                placeholder="you@company.com"
                autoComplete="email"
                autoFocus
                required
              />
              <Field
                label="Password"
                value={password}
                onChange={setPassword}
                type="password"
                placeholder="••••••••"
                autoComplete={mode === 'signin' ? 'current-password' : 'new-password'}
                required
              />

              {error && (
                <div>
                  <p className="lgn-error">{error}</p>
                  {showGoogleHint && (
                    <p className="lgn-hint">
                      Signed up with Google? Use Continue with Google above.
                    </p>
                  )}
                </div>
              )}

              <button disabled={busy} className="lgn-primary">
                {busy ? 'Working…' : mode === 'signin' ? 'Sign in' : 'Create account'}
              </button>
            </form>
          )}
        </div>

        {!needsCode && (
          <p className="lgn-switch">
            {mode === 'signin' ? "Don't have an account?" : 'Already have an account?'}{' '}
            <button
              type="button"
              onClick={() => {
                setMode(mode === 'signin' ? 'signup' : 'signin')
                setError(null)
              }}
            >
              {mode === 'signin' ? 'Sign up' : 'Sign in'}
            </button>
          </p>
        )}
      </div>

      <style>{`
        /* The studio's daylight, edge to edge. min-height rather than a fixed
           shell: this page has no rail to hold still, so it may simply scroll if
           a small screen needs it to — and it never scrolls SIDEWAYS, because
           nothing in the column has a width the viewport cannot give it. */
        .lgn-root { min-height:100vh; width:100%; display:flex;
          align-items:center; justify-content:center; padding:48px 20px;
          background:#F1F1EF; color:#1B1B1A;
          font:14px/1.5 Inter,-apple-system,sans-serif; overflow-x:hidden; }
        .lgn-col { width:100%; max-width:392px; }

        /* Byte-for-byte the boot screen's lockup (landing2/BootScreen .fl-bootmark),
           minus its breathing animation — the door is arrived at, not waited on. */
        .lgn-lockup { display:flex; align-items:center; justify-content:center;
          gap:11px; margin-bottom:26px;
          font:600 38px/1 Inter,ui-sans-serif,-apple-system,"Segoe UI",Roboto,sans-serif;
          letter-spacing:-.022em; color:#1B1B1A; }
        .lgn-lockup svg { width:50px; height:50px; flex:0 0 auto; }

        .lgn-card { background:#fff; border:1px solid #E6E6E3; border-radius:16px;
          padding:26px 24px;
          box-shadow:0 1px 2px rgba(27,27,26,.04), 0 24px 48px -32px rgba(27,27,26,.28); }
        .lgn-form { display:flex; flex-direction:column; gap:16px; }
        .lgn-h1 { margin:0; font-size:19px; font-weight:650;
          letter-spacing:-.018em; color:#1B1B1A; }
        .lgn-sub { margin:5px 0 0; font-size:13.5px; line-height:1.55;
          color:#8A8A86; }

        /* ── CONTROLS ────────────────────────────────────────────────────────
           Every one of them states its own focus. The surface is quiet by
           design; that is a look, not a licence (the same rule and the same
           #3B82F6 ring the rail and the account card carry). */
        .lgn-google { display:flex; align-items:center; justify-content:center;
          gap:10px; width:100%; background:#fff; border:1px solid #E6E6E3;
          border-radius:10px; padding:11px 14px; cursor:pointer;
          font:600 14px/1.2 Inter,-apple-system,sans-serif; color:#1B1B1A;
          transition:background-color .15s, border-color .15s; }
        .lgn-google svg { width:18px; height:18px; flex:0 0 auto; }
        .lgn-google:hover { background:#FAFAF8; border-color:#C9C9C4; }
        .lgn-google:focus-visible { outline:2px solid #3B82F6; outline-offset:2px; }

        .lgn-or { display:flex; align-items:center; gap:12px; }
        .lgn-or i { flex:1 1 auto; height:1px; background:#E6E6E3; }
        .lgn-or span { font-size:11px; font-weight:600; letter-spacing:.08em;
          text-transform:uppercase; color:#B6B6B2; }

        .lgn-label { display:block; }
        .lgn-labeltext { display:flex; align-items:baseline; gap:6px;
          margin-bottom:6px; font-size:13px; font-weight:600; color:#1B1B1A; }
        .lgn-optional { font-size:11.5px; font-weight:400; color:#B6B6B2; }
        .lgn-input { width:100%; background:#fff; border:1px solid #E6E6E3;
          border-radius:10px; padding:10px 12px;
          font:14px/1.4 Inter,-apple-system,sans-serif; color:#1B1B1A;
          outline:none; transition:border-color .15s, box-shadow .15s; }
        .lgn-input::placeholder { color:#B6B6B2; }
        .lgn-input:hover { border-color:#C9C9C4; }
        .lgn-input:focus-visible { border-color:#3B82F6;
          box-shadow:0 0 0 3px rgba(59,130,246,.18); }
        .lgn-code { text-align:center; font-size:19px; letter-spacing:.3em;
          padding:11px 12px; }

        .lgn-primary { width:100%; border:1px solid #1B1B1A; background:#1B1B1A;
          color:#fff; border-radius:10px; padding:11px 16px; cursor:pointer;
          font:600 14px/1.2 Inter,-apple-system,sans-serif;
          transition:background-color .15s, border-color .15s, opacity .15s; }
        .lgn-primary:hover:not(:disabled) { background:#000; border-color:#000; }
        .lgn-primary:focus-visible { outline:2px solid #3B82F6; outline-offset:2px; }
        .lgn-primary:disabled { opacity:.55; cursor:default; }

        /* #DC2626 is the app's existing "something went wrong" ink
           (SuggestionCards .ovsug-note.bad) — not a new colour. */
        .lgn-error { margin:0; font-size:13px; line-height:1.5; color:#DC2626; }
        .lgn-hint { margin:5px 0 0; font-size:12.5px; line-height:1.5;
          color:#8A8A86; }

        .lgn-switch { margin:18px 0 0; text-align:center; font-size:13.5px;
          color:#8A8A86; }
        .lgn-switch button { border:none; background:none; padding:0;
          cursor:pointer; font:600 13.5px/1.5 Inter,-apple-system,sans-serif;
          color:#1B1B1A; border-radius:4px; }
        .lgn-switch button:hover { color:#3B82F6; }
        .lgn-switch button:focus-visible { outline:2px solid #3B82F6;
          outline-offset:3px; color:#3B82F6; }

        /* A 390px screen keeps the whole lockup; it just stops spending 88px of
           its height on it. */
        @media (max-width:430px) {
          .lgn-root { padding:32px 16px; }
          .lgn-lockup { gap:9px; margin-bottom:22px; font-size:31px; }
          .lgn-lockup svg { width:41px; height:41px; }
          .lgn-card { padding:22px 18px; } }

        @media (prefers-reduced-motion:reduce) {
          .lgn-google, .lgn-primary, .lgn-input { transition:none; } }
      `}</style>
    </main>
  )
}

function Field({
  label,
  value,
  onChange,
  type,
  placeholder,
  required,
  optional,
  autoFocus,
  autoComplete,
}: {
  label: string
  value: string
  onChange: (v: string) => void
  type: string
  placeholder?: string
  required?: boolean
  optional?: boolean
  autoFocus?: boolean
  /** Handed to the browser's password manager. The user's own credential store
   *  filling its own fields is the only sanctioned path for a secret here. */
  autoComplete?: string
}) {
  return (
    <label className="lgn-label">
      <span className="lgn-labeltext">
        {label}
        {optional && <span className="lgn-optional">optional</span>}
      </span>
      <input
        className="lgn-input"
        type={type}
        value={value}
        required={required}
        autoFocus={autoFocus}
        autoComplete={autoComplete}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
      />
    </label>
  )
}
