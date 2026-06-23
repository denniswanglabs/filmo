'use client'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { insforge } from '../../lib/insforge'
import { useAuth } from '../../lib/auth'
import { Wordmark } from '../components/Brand'

type Mode = 'signin' | 'signup'

export default function LoginPage() {
  const router = useRouter()
  const { user, loading, refresh } = useAuth()
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
