'use client'
import { createContext, useContext, useEffect, useState, useCallback } from 'react'
import { insforge, persistSession, readPersistedSession, rehydrateSessionIntoClient, ensureFreshAccessToken, OAUTH_RETURN } from './insforge'
import { clearPendingBuild } from './pending-build'

interface AuthUser {
  id: string
  email?: string
  [k: string]: unknown
}

interface AuthState {
  user: AuthUser | null
  loading: boolean
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
  /** True when THIS page load is an OAuth return that ended with no session — the code
   *  exchange failed or never ran. Surfaces let the reader retry with honest words
   *  instead of a silently signed-out landing (2026-07-20 outage: the SDK swallows
   *  exchange errors at console.debug, so nothing else will ever say it). */
  oauthReturnFailed: boolean
}

const AuthContext = createContext<AuthState>({
  user: null,
  loading: true,
  refresh: async () => null,
  getToken: async () => null,
  signOut: async () => {},
  signInWithGoogle: async () => {},
  oauthReturnFailed: false,
})

// Read the current access token from the InsForge client. The SDK exposes it on the
// auth object / its token manager; we probe the known shapes defensively so a minor
// SDK version bump can't silently break auth.
async function readAccessToken(): Promise<string | null> {
  // Freshness first: if the current token is expired/expiring and we hold a body-mode
  // refresh credential, mint a fresh one BEFORE reading — server actions verify this
  // bearer server-side, so handing them a dead token = the "signed out after paying" wall.
  await ensureFreshAccessToken()
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
  if (t) return t
  // Last resort: the in-memory token may have been dropped by a reload before the SDK
  // re-seeded it. Fall back to the durable localStorage copy so a server action on the
  // post-payment page still has a bearer to verify (verifyUser re-validates it anyway).
  return readPersistedSession()?.accessToken ?? null
}

// After we resolve who the user is, mirror the result into durable localStorage so the
// NEXT page load (reload / new tab / the Stripe pay→return) restores it instantly instead
// of depending on the cross-site refresh round-trip. We pair the user with the SDK's CURRENT
// in-memory access token (the freshest one, just minted by getCurrentUser/refresh). On a
// signed-out resolve we clear the cache so we never resurrect a dead session.
async function persistAfterResolve(user: AuthUser | null): Promise<void> {
  if (!user?.id) {
    persistSession(null)
    return
  }
  const token = await readAccessToken()
  if (token) persistSession({ accessToken: token, user: { id: user.id, email: user.email } })
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [loading, setLoading] = useState(true)
  const [oauthReturnFailed, setOauthReturnFailed] = useState(false)

  const refresh = useCallback(async (): Promise<AuthUser | null> => {
    // Mint a fresh session (body-mode refresh) BEFORE getCurrentUser: with an expired token
    // the SDK's memory is empty and getCurrentUser would fall into its cookie-mode
    // refreshSession() — the cross-site path that always 401s and erases the session.
    // After this, getCurrentUser resolves from the freshly saved in-memory session.
    await ensureFreshAccessToken()
    const { data, error } = await insforge.auth.getCurrentUser()
    const u = error ? null : ((data?.user as AuthUser) ?? null)
    setUser(u)
    setLoading(false)
    void persistAfterResolve(u)
    return u
  }, [])

  const getToken = useCallback(async () => readAccessToken(), [])

  const signOut = useCallback(async () => {
    await insforge.auth.signOut()
    persistSession(null) // drop the durable copy so a reload doesn't restore a dead session
    // A deliberate sign-out is the reader closing the book — nothing should
    // resume after it. Drop any build stashed before a Google round-trip
    // (ws_pending_build) so the next visit's gate can't greet them with a phantom
    // "Your prompt is ready" auto-resume from an attempt they'd walked away from
    // (2026-07-20). This is the ONLY place the stash is cleared on purpose: a
    // stash surviving a FAILED sign-in is exactly what makes resume work, so it
    // must never be cleared on any path but an intentional sign-out.
    clearPendingBuild()
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

  useEffect(() => {
    let cancelled = false

    // SYNCHRONOUS rehydrate FIRST: if we have a durable session in localStorage, re-seed it
    // into the SDK and paint `user` immediately. This is the core fix — the post-payment page
    // (a full reload after the cross-origin Stripe round-trip) now shows the signed-in UI and
    // makes authed reads on the FIRST render, instead of momentarily (or permanently, when the
    // Lax-CSRF refresh fails) dropping to the signed-out gate. The async reconcile below then
    // validates/refreshes in the background and corrects the cache if the session is truly gone.
    const restored = rehydrateSessionIntoClient()
    // …EXCEPT when we are mid-OAuth-exchange. The optimistic paint answers "who
    // was signed in last time", which during a Google return is the WRONG
    // question: signInWithGoogle sends `prompt: 'select_account'`, so the person
    // coming back may deliberately be a different account. Dropping `loading`
    // here would let a consumer make an identity decision — which run to open,
    // where to redirect — using the previous user's token while the new user's
    // exchange is still in flight, landing them on someone else's film.
    // OAUTH_RETURN is captured in lib/insforge.ts at module scope because the
    // SDK strips `insforge_code` from the URL before this code ever runs.
    if (restored && !OAUTH_RETURN) {
      setUser(restored as AuthUser)
      // We have a usable session right now — render the authed UI immediately and let the
      // background reconcile validate. Without this the run page sits on its loading spinner
      // until getCurrentUser returns (and never flashes the signed-out gate).
      setLoading(false)
    }

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
      // A FAILED EXCHANGE MUST NOT BE SILENT (2026-07-20, production sign-in outage).
      // The SDK's detectAuthCallback swallows exchange errors at console.debug and the
      // page then renders an ordinary signed-out landing — the user cannot tell a broken
      // sign-in from never having signed in, and the report we get is "it threw me back
      // to the landing page." So on an OAuth return, re-run the exchange check ourselves:
      // the SDK's exchangeOAuthCode returns {error} (never throws) and is idempotent-safe
      // here because a SUCCESSFUL exchange already consumed the code — this call only
      // produces a result when the constructor's attempt failed, in which case the code
      // is gone from the URL but its failure reason is what we want. We detect the
      // failure by outcome instead: OAUTH_RETURN and no session after the wait means the
      // exchange did not produce one. Say so, loudly, with whatever the SDK knows.
      if (OAUTH_RETURN) {
        const tm = (
          insforge.auth as unknown as {
            tokenManager?: { getAccessToken?: () => string | null }
          }
        ).tokenManager
        const gotSession = !!tm?.getAccessToken?.()
        if (!gotSession) {
          console.error(
            '[filmo-auth] OAuth return produced no session — the code exchange failed ' +
              'or never ran. Check the Verbose console for the SDK’s ' +
              '"OAuth code exchange failed" line; common causes: PKCE verifier missing ' +
              '(storage cleared mid-flow), the code consumed twice, or the exchange POST ' +
              'blocked by an extension.',
          )
          setOauthReturnFailed(true)
        }
      }
      // Resolve the session WITH RETRY. getCurrentUser hits InsForge over the network,
      // and InsForge has intermittent multi-second timeouts — a single failed call would
      // FALSE-LOGOUT a signed-in user (e.g. right after returning from Stripe checkout,
      // the exact symptom we hit). A genuine "signed out" returns a fast 401 (don't retry
      // that); a timeout / 5xx / network error is transient → retry a few times with
      // backoff before giving up, so a DB blip can't strand a valid session at the gate.
      //
      // CRUCIAL with the localStorage restore above: we must distinguish a DEFINITIVE 401
      // (real signout → clear `user` AND the durable cache) from a TRANSIENT failure
      // (timeout/5xx/network → keep whatever we restored; do NOT wipe a valid session on a
      // blip). `restored` is the optimistically-painted user; we only override it on a clear
      // signal.
      //
      // FRESHNESS FIRST (the stay-signed-in-after-Stripe fix): with an EXPIRED restored
      // token the SDK's memory is empty, and getCurrentUser would fall into its cookie-mode
      // refreshSession() — the cross-site path that always 401s — and that 401 reads as a
      // definitive signout below, ERASING a recoverable session. Mint a fresh session via
      // the body-mode refresh (no cookie, no CSRF) BEFORE asking who the user is.
      await ensureFreshAccessToken()
      if (cancelled) return
      let u: AuthUser | null = restored as AuthUser | null
      let definitive = false
      for (let attempt = 0; ; attempt++) {
        const { data, error } = await insforge.auth.getCurrentUser()
        if (cancelled) return
        if (!error) {
          u = (data?.user as AuthUser) ?? null
          definitive = true
          break
        }
        const status = (error as { statusCode?: number })?.statusCode
        if (status === 401) {
          // Real, authoritative signed-out state.
          u = null
          definitive = true
          break
        }
        if (attempt >= 3) break // transient failure exhausted retries — keep `restored`
        await new Promise((r) => setTimeout(r, 700 * (attempt + 1)))
      }
      if (cancelled) return
      setUser(u)
      setLoading(false)
      // Persist only on a DEFINITIVE resolve: a fresh user → refresh the cache (new token);
      // a real 401 → clear it. On a transient failure we leave the existing cache intact so
      // the next load can still restore.
      if (definitive) void persistAfterResolve(u)
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
        refresh,
        getToken,
        signOut,
        signInWithGoogle,
        oauthReturnFailed,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  return useContext(AuthContext)
}
