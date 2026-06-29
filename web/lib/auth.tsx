'use client'
import { createContext, useContext, useEffect, useState, useCallback } from 'react'
import { insforge } from './insforge'

interface AuthUser {
  id: string
  email?: string
  [k: string]: unknown
}

interface AuthState {
  user: AuthUser | null
  loading: boolean
  /** True when a shared demo account is configured (NEXT_PUBLIC_DEMO_*). */
  demoAvailable: boolean
  /** Re-read the session; returns the current user (or null). */
  refresh: () => Promise<AuthUser | null>
  /**
   * The current access token (a signed JWT) for authenticating server actions.
   * Server actions verify it against InsForge — passing the token, not a user id,
   * is what makes them tamper-proof. Returns null when signed out.
   */
  getToken: () => Promise<string | null>
  signOut: () => Promise<void>
  /** Redirect to Google. The browser leaves the page and returns to `redirectTo`. */
  signInWithGoogle: (redirectTo?: string) => Promise<void>
  /** One-tap sign-in with the shared demo account (no redirect). */
  signInDemo: () => Promise<{ user?: AuthUser; error?: string }>
}

const DEMO_EMAIL = process.env.NEXT_PUBLIC_DEMO_EMAIL
const DEMO_PASSWORD = process.env.NEXT_PUBLIC_DEMO_PASSWORD

const AuthContext = createContext<AuthState>({
  user: null,
  loading: true,
  demoAvailable: false,
  refresh: async () => null,
  getToken: async () => null,
  signOut: async () => {},
  signInWithGoogle: async () => {},
  signInDemo: async () => ({ error: 'not ready' }),
})

// Read the current access token from the InsForge client. The SDK exposes it on the
// auth object / its token manager; we probe the known shapes defensively so a minor
// SDK version bump can't silently break auth.
async function readAccessToken(): Promise<string | null> {
  const a = insforge.auth as unknown as {
    getAccessToken?: () => string | null
    getSession?: () => { accessToken?: string } | null
    tokenManager?: { getAccessToken?: () => string | null; getSession?: () => { accessToken?: string } | null }
  }
  const probe = () =>
    a.getAccessToken?.() ??
    a.getSession?.()?.accessToken ??
    a.tokenManager?.getAccessToken?.() ??
    a.tokenManager?.getSession?.()?.accessToken ??
    null
  let t = probe()
  if (t) return t
  // Token not populated yet (e.g. right after an OAuth return) — force a session read.
  try {
    await insforge.auth.getCurrentUser()
  } catch {
    /* ignore — fall through */
  }
  t = probe()
  return t ?? null
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async (): Promise<AuthUser | null> => {
    const { data, error } = await insforge.auth.getCurrentUser()
    const u = error ? null : ((data?.user as AuthUser) ?? null)
    setUser(u)
    setLoading(false)
    return u
  }, [])

  const getToken = useCallback(async () => readAccessToken(), [])

  const signOut = useCallback(async () => {
    await insforge.auth.signOut()
    setUser(null)
  }, [])

  const signInWithGoogle = useCallback(async (redirectTo?: string) => {
    const dest =
      redirectTo ?? (typeof window !== 'undefined' ? window.location.origin + '/' : '/')
    // SPA flow: the SDK builds the PKCE challenge and redirects the browser to Google.
    // On return to `dest`, the SDK auto-exchanges `insforge_code` for a session.
    await insforge.auth.signInWithOAuth('google', {
      redirectTo: dest,
      additionalParams: { prompt: 'select_account' },
    })
  }, [])

  const signInDemo = useCallback(async (): Promise<{ user?: AuthUser; error?: string }> => {
    if (!DEMO_EMAIL || !DEMO_PASSWORD) return { error: 'Demo account not configured' }
    const r = await insforge.auth.signInWithPassword({ email: DEMO_EMAIL, password: DEMO_PASSWORD })
    if (r.error) return { error: r.error.message || 'Demo sign-in failed' }
    const u = await refresh()
    return u ? { user: u } : { error: 'Demo sign-in failed' }
  }, [refresh])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      // If we just came back from an OAuth redirect, the SDK constructor kicked off the
      // `insforge_code` exchange. Wait for it to finish so getCurrentUser sees the session.
      const pending = (insforge.auth as unknown as { authCallbackHandled?: Promise<unknown> })
        .authCallbackHandled
      if (pending) {
        try {
          await pending
        } catch {
          /* exchange failures are non-fatal; we fall through to getCurrentUser */
        }
      }
      // Resolve the session WITH RETRY. getCurrentUser hits InsForge over the network,
      // and InsForge has intermittent multi-second timeouts — a single failed call would
      // FALSE-LOGOUT a signed-in user (e.g. right after returning from Stripe checkout,
      // the exact symptom we hit). A genuine "signed out" returns a fast 401 (don't retry
      // that); a timeout / 5xx / network error is transient → retry a few times with
      // backoff before giving up, so a DB blip can't strand a valid session at the gate.
      let u: AuthUser | null = null
      for (let attempt = 0; ; attempt++) {
        const { data, error } = await insforge.auth.getCurrentUser()
        if (cancelled) return
        if (!error) {
          u = (data?.user as AuthUser) ?? null
          break
        }
        const status = (error as { statusCode?: number })?.statusCode
        if (status === 401 || attempt >= 3) break
        await new Promise((r) => setTimeout(r, 700 * (attempt + 1)))
      }
      if (cancelled) return
      setUser(u)
      setLoading(false)
    })()
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        demoAvailable: !!(DEMO_EMAIL && DEMO_PASSWORD),
        refresh,
        getToken,
        signOut,
        signInWithGoogle,
        signInDemo,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  return useContext(AuthContext)
}
