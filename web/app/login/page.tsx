'use client'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { insforge } from '../../lib/insforge'
import { useAuth } from '../../lib/auth'
import { Wordmark } from '../components/Brand'

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
      if (error) throw new Error(error.message || 'Sign in failed')
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

  return (
    <main className="surface-dots flex min-h-screen items-center justify-center px-5 py-16">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex justify-center">
          <Wordmark className="text-xl" />
        </div>

        <div className="rounded-2xl border border-black/5 bg-white p-7 shadow-[0_12px_40px_-12px_rgba(20,23,28,0.18)]">
          {needsCode ? (
            <form onSubmit={onVerify} className="space-y-4">
              <div>
                <h1 className="text-lg font-semibold text-ink">Check your email</h1>
                <p className="mt-1 text-sm text-slate-500">
                  Enter the 6-digit code we sent to {email}.
                </p>
              </div>
              <input
                inputMode="numeric"
                autoFocus
                value={code}
                onChange={(e) => setCode(e.target.value)}
                placeholder="123456"
                className="w-full rounded-lg border border-black/10 px-3 py-2.5 text-center text-lg tracking-[0.3em] outline-none focus:border-amber"
              />
              {error && <p className="text-sm text-red-600">{error}</p>}
              <button
                disabled={busy}
                className="w-full rounded-lg bg-amber py-2.5 font-medium text-white transition hover:opacity-90 disabled:opacity-50"
              >
                {busy ? 'Verifying…' : 'Verify & continue'}
              </button>
            </form>
          ) : (
            <form onSubmit={onSubmit} className="space-y-4">
              <div>
                <h1 className="text-lg font-semibold text-ink">
                  {mode === 'signin' ? 'Sign in' : 'Create your account'}
                </h1>
                <p className="mt-1 text-sm text-slate-500">
                  {mode === 'signin'
                    ? 'Welcome back to Walk Studio.'
                    : 'Start turning URLs into finished videos.'}
                </p>
              </div>

              <button
                type="button"
                onClick={() => void signInWithGoogle(window.location.origin + '/')}
                className="flex w-full items-center justify-center gap-3 rounded-lg border border-black/10 bg-white py-2.5 font-medium text-ink transition hover:bg-black/[0.02]"
              >
                <svg className="h-5 w-5 shrink-0" viewBox="0 0 18 18" aria-hidden>
                  <path fill="#4285F4" d="M17.64 9.2c0-.64-.06-1.25-.16-1.84H9v3.48h4.84a4.14 4.14 0 0 1-1.8 2.72v2.26h2.92c1.7-1.57 2.68-3.88 2.68-6.62z" />
                  <path fill="#34A853" d="M9 18c2.43 0 4.47-.8 5.96-2.18l-2.92-2.26c-.81.54-1.84.86-3.04.86-2.34 0-4.32-1.58-5.03-3.7H.96v2.33A9 9 0 0 0 9 18z" />
                  <path fill="#FBBC05" d="M3.97 10.72a5.4 5.4 0 0 1 0-3.44V4.95H.96a9 9 0 0 0 0 8.1l3.01-2.33z" />
                  <path fill="#EA4335" d="M9 3.58c1.32 0 2.5.46 3.44 1.35l2.58-2.58C13.47.9 11.43 0 9 0A9 9 0 0 0 .96 4.95l3.01 2.33C4.68 5.16 6.66 3.58 9 3.58z" />
                </svg>
                Continue with Google
              </button>

              <div className="flex items-center gap-3 py-1">
                <div className="h-px flex-1 bg-black/5" />
                <span className="text-xs uppercase tracking-wide text-slate-400">or</span>
                <div className="h-px flex-1 bg-black/5" />
              </div>

              {mode === 'signup' && (
                <Field
                  label="Name"
                  value={name}
                  onChange={setName}
                  type="text"
                  placeholder="Ada Lovelace"
                  optional
                />
              )}
              <Field
                label="Email"
                value={email}
                onChange={setEmail}
                type="email"
                placeholder="you@company.com"
                autoFocus
                required
              />
              <Field
                label="Password"
                value={password}
                onChange={setPassword}
                type="password"
                placeholder="••••••••"
                required
              />

              {error && <p className="text-sm text-red-600">{error}</p>}

              <button
                disabled={busy}
                className="w-full rounded-lg bg-amber py-2.5 font-medium text-white transition hover:opacity-90 disabled:opacity-50"
              >
                {busy
                  ? 'Working…'
                  : mode === 'signin'
                    ? 'Sign in'
                    : 'Create account'}
              </button>
            </form>
          )}
        </div>

        {!needsCode && (
          <p className="mt-5 text-center text-sm text-slate-500">
            {mode === 'signin' ? "Don't have an account?" : 'Already have an account?'}{' '}
            <button
              onClick={() => {
                setMode(mode === 'signin' ? 'signup' : 'signin')
                setError(null)
              }}
              className="font-medium text-amber hover:underline"
            >
              {mode === 'signin' ? 'Sign up' : 'Sign in'}
            </button>
          </p>
        )}
      </div>
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
}: {
  label: string
  value: string
  onChange: (v: string) => void
  type: string
  placeholder?: string
  required?: boolean
  optional?: boolean
  autoFocus?: boolean
}) {
  return (
    <label className="block">
      <span className="mb-1.5 flex items-center gap-1.5 text-sm font-medium text-ink">
        {label}
        {optional && <span className="text-xs font-normal text-slate-400">optional</span>}
      </span>
      <input
        type={type}
        value={value}
        required={required}
        autoFocus={autoFocus}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-lg border border-black/10 px-3 py-2.5 outline-none transition focus:border-amber"
      />
    </label>
  )
}
