import { createClient, createAdminClient } from '@insforge/sdk'

// Keep-alive fetch for the browser client. The web app talks to InsForge in Singapore
// from (often) EU clients, so a COLD connection pays ~0.8s of TLS+handshake latency per
// call; reusing a warm connection drops that to ~0.28s (measured). Browsers already pool
// same-origin keep-alive connections by default, so the repeated 3s run-page poll mostly
// benefits automatically — but we set `keepalive: true` explicitly to (a) state the intent
// and (b) let an in-flight read survive a navigation/unload. NOTE: `keepalive` requests
// cap their BODY at 64KB in browsers; our reads are GETs (no body) and the heaviest write
// elsewhere is small, so the cap is irrelevant here. We delegate to the real fetch and only
// add the flag — the SDK still injects its own AbortController `signal`, so the 8s timeout
// and retry behavior are unchanged.
const keepAliveFetch: typeof fetch = (input, init) =>
  (globalThis.fetch as typeof fetch)(input, { ...init, keepalive: true })

// ───────────── Body-based refresh-token grant (the always-signed-out-after-paying fix) ─────────────
// ROOT CAUSE (verified live 2026-07-02): access tokens live 15 min (not configurable — the
// admin auth-config API exposes no TTL), the pay flow always crosses 15 min, and web-mode
// refresh needs the httpOnly cookie on the INSFORGE (third-party) domain + a CSRF nonce baked
// into it — a cross-site fetch never carries that cookie (SameSite / Safari ITP), so refresh
// failed EVERY time and the reconcile erased the session. Deterministic logout for every payer.
//
// THE FIX (proven against the live server via the demo account before this was written):
// InsForge's own endpoints return the refresh token IN THE RESPONSE BODY when the request
// carries `?client_type=mobile` (login/register/oauth-exchange), and `/api/auth/refresh
// ?client_type=mobile` accepts `{refreshToken}` in the body — no cookie, no CSRF. The SDK
// (1.4.x) ALREADY prefers this body mode automatically whenever its http layer holds a
// refreshToken (dist refreshAccessToken: `this.refreshToken ? "/api/auth/refresh?client_type
// =mobile" : ...`), and stores/rotates it from every auth response. The ONLY missing pieces:
// (1) the browser's grant calls go out as client_type=web, so no body refreshToken is ever
// GRANTED, and (2) the SDK holds it in memory only, so it dies on reload. This wrapper fixes
// (1) by appending client_type=mobile to the three GRANT endpoints, and captures every
// refreshToken that flows back (grants AND rotations) into localStorage for (2) — rehydrate
// re-seeds it. Trade-off (accepted for the hackathon): a refresh token in localStorage is
// XSS-readable; the gold-standard first-party-cookie proxy lives on branch auth-ssr-firstparty.
const AUTH_GRANT_PATHS = ['/api/auth/sessions', '/api/auth/users', '/api/auth/oauth/exchange']

const authAwareFetch: typeof fetch = async (input, init) => {
  let target: RequestInfo | URL = input
  let urlStr: string | null = null
  try {
    urlStr =
      typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url
    const u = new URL(urlStr)
    const method = (
      init?.method ?? (typeof input === 'object' && 'method' in input ? input.method : 'GET')
    ).toUpperCase()
    // Exact-path match (NOT prefix): /api/auth/sessions/current (getCurrentUser GET) must
    // stay untouched — only the POST grant endpoints get the mobile client_type.
    if (
      method === 'POST' &&
      AUTH_GRANT_PATHS.some((p) => u.pathname === p || u.pathname.endsWith(p)) &&
      !u.searchParams.has('client_type')
    ) {
      u.searchParams.set('client_type', 'mobile')
      target = u.toString()
    }
  } catch {
    /* malformed URL — pass through untouched */
  }

  const res = await (globalThis.fetch as typeof fetch)(target as RequestInfo, {
    ...init,
    keepalive: true,
  })

  // Capture any refreshToken flowing back from an auth endpoint (initial grant on
  // login/register/oauth-exchange + every rotation from /api/auth/refresh). Best-effort:
  // a capture failure must never break the request itself.
  try {
    if (urlStr && res.ok) {
      const u = new URL(typeof target === 'string' ? target : urlStr)
      if (u.pathname.startsWith('/api/auth/') && u.pathname !== '/api/auth/logout') {
        const body = (await res
          .clone()
          .json()
          .catch(() => null)) as { refreshToken?: unknown } | null
        if (body && typeof body.refreshToken === 'string' && body.refreshToken) {
          mergeStoredRefreshToken(body.refreshToken)
        }
      }
    }
  } catch {
    /* never let capture interfere */
  }
  return res
}

// Browser/user client — anon key, RLS-scoped. Safe to use in client components.
//
// timeout/retry rationale (verified against @insforge/sdk 1.4.2 dist/index.mjs):
//   • timeout (default 30000) aborts a slow request via AbortController and throws
//     InsForgeError(408, REQUEST_TIMEOUT). IMPORTANT: a timeout is thrown IMMEDIATELY
//     and is NOT covered by the SDK's own retryCount (the SDK only retries network
//     errors + 5xx, never 4xx and never its own timeout). We drop it to 8s so a stuck
//     InsForge call fails fast instead of hanging the UI for 30s. Our callers that
//     need to survive the blip retry the 408 themselves (auth.tsx getCurrentUser loop,
//     run page poll) — a 408 is non-401, so it never reads as a real logout / error.
//   • retryCount (default 3) + retryDelay still recover transient 5xx/network errors
//     under the 8s ceiling; bumped retryDelay down a touch so a couple of retries can
//     still fit. 401 is never retried, so a genuine signed-out state still resolves fast.
// ── ARE WE MID-OAUTH-EXCHANGE? MUST BE READ BEFORE createClient ─────────────
// The SDK's Auth constructor runs `detectAuthCallback()` at construction time —
// it reads `insforge_code` off the query string and STRIPS it with
// history.replaceState BEFORE awaiting the exchange. So by the time any other
// module imports this one, the evidence that we are returning from Google is
// already gone from the URL. ES import hoisting guarantees this file evaluates
// before auth.tsx, which is exactly why the flag has to be captured HERE, on
// the line above the client, and cannot be recomputed later.
//
// Consumers use it to hold off on trusting the optimistic localStorage session:
// during an OAuth return the cached session belongs to whoever was signed in
// BEFORE, which is not necessarily who is signing in now — signInWithGoogle
// sends `prompt: 'select_account'`, so switching accounts is an invited action,
// not an edge case.
export const OAUTH_RETURN =
  typeof window !== 'undefined'
  && new URLSearchParams(window.location.search).has('insforge_code')

export const insforge = createClient({
  baseUrl: process.env.NEXT_PUBLIC_INSFORGE_URL!,
  anonKey: process.env.NEXT_PUBLIC_INSFORGE_ANON_KEY!,
  // authAwareFetch = keepAliveFetch behavior + the body-refresh-token grant/capture layer
  // (see the block above). keepAliveFetch itself remains for reference/reuse.
  fetch: authAwareFetch,
  timeout: 8000,
  retryCount: 3,
  retryDelay: 400,
})
void keepAliveFetch // retained intentionally (documents the base behavior authAwareFetch wraps)

// ─────────────────── Durable session persistence (localStorage) ───────────────────
// ROOT CAUSE this fixes (verified against @insforge/sdk 1.4.2 source, not guessed):
// the SDK's TokenManager is MEMORY-ONLY ("Memory-only token storage", dist/index.mjs
// TokenManager class ~L214-281; the access token + user live in `this.accessToken` /
// `this.user` and are NEVER written to any persistent store). The ONLY thing the SDK
// persists across a full page reload is the **httpOnly `insforge_refresh_token` cookie**
// (`SameSite=None; Secure; Path=/api/auth`), which on reload `getCurrentUser()` trades
// for a new session via `POST /api/auth/refresh` (dist/index.mjs `getCurrentUser`
// ~L1224-1238 → `refreshSession`). That refresh REQUIRES an `X-CSRF-Token` header that
// hash-matches the `csrfNonce` baked into the refresh-cookie JWT; the SDK reads that CSRF
// value from the `insforge_csrf_token` cookie, which it writes itself via `document.cookie`
// as **`SameSite=Lax`** (`setCsrfToken` ~L203-208). Empirically (curl + live browser):
// refresh with cookie + matching CSRF → 200; with a missing/mismatched CSRF → **403 →
// signed out**. So the whole "stay signed in across pay→return" path hangs on a fragile
// Lax-CSRF + cross-site-refresh round-trip after the Stripe redirect. There is NO SDK
// option to persist the session (InsForgeConfig in types-Dk-44JJf.d.ts has no
// storage/persistSession; auth options are only `detectOAuthCallback`), and the refresh
// token is httpOnly so we CANNOT store it ourselves.
//
// What we CAN do — and what makes the session survive a reload / new tab / the cross-origin
// Stripe round-trip deterministically — is persist the JS-accessible `{ accessToken, user }`
// in **localStorage** (origin-scoped, NOT SameSite-gated, survives the redirect-and-back) and
// re-seed it into the SDK on load. The access token is a 15-min JWT (measured) — far longer
// than a checkout — so the restored token authenticates the post-payment page immediately,
// with the httpOnly refresh cookie still there as the longer-term backstop. We never weaken
// auth: a restored token that's actually expired/revoked still 401s server-side, and we always
// reconcile against `getCurrentUser()` (which refreshes) and clear the cache on a real signout.
const SESSION_KEY = 'insforge_session_v1'

// refreshToken (optional): the body-mode refresh credential captured by authAwareFetch.
// It outlives the 15-min access token, so persistSession CARRIES IT OVER when a caller
// writes a session without one — only an explicit persistSession(null) (sign-out) clears it.
type PersistedSession = { accessToken: string; user: AuthLikeUser; refreshToken?: string }
type AuthLikeUser = { id: string; email?: string; [k: string]: unknown }

function ls(): Storage | null {
  // SSR-safe: no window/localStorage on the server, and a privacy-mode browser can throw
  // on access — never let storage access break auth.
  try {
    if (typeof window === 'undefined' || !window.localStorage) return null
    return window.localStorage
  } catch {
    return null
  }
}

// UNVALIDATED read of whatever is stored — used internally so a refreshToken captured
// BEFORE the full {accessToken,user} lands (the grant response arrives mid-login, ahead
// of the resolve that persists the session) is never lost to validation.
function readRawStored(): Partial<PersistedSession> | null {
  const store = ls()
  if (!store) return null
  try {
    const raw = store.getItem(SESSION_KEY)
    return raw ? (JSON.parse(raw) as Partial<PersistedSession>) : null
  } catch {
    return null
  }
}

/** Merge a freshly captured refresh token into storage without touching the rest. */
function mergeStoredRefreshToken(refreshToken: string): void {
  const store = ls()
  if (!store) return
  try {
    const raw = readRawStored() ?? {}
    store.setItem(SESSION_KEY, JSON.stringify({ ...raw, refreshToken }))
  } catch {
    /* quota / privacy mode — non-fatal */
  }
}

/** Persist (or clear, when session is null) the JS-readable session for cross-reload restore. */
export function persistSession(session: PersistedSession | null): void {
  const store = ls()
  if (!store) return
  try {
    if (session && session.accessToken && session.user?.id) {
      // Carry the stored refreshToken forward when the caller didn't supply one —
      // persistAfterResolve only knows {accessToken,user}; dropping the refresh
      // credential here would undo the whole stay-signed-in fix.
      const refreshToken = session.refreshToken ?? readRawStored()?.refreshToken
      store.setItem(SESSION_KEY, JSON.stringify(refreshToken ? { ...session, refreshToken } : session))
    } else {
      store.removeItem(SESSION_KEY)
    }
  } catch {
    /* quota / privacy mode — non-fatal */
  }
}

/** Read the persisted session (or null). */
export function readPersistedSession(): PersistedSession | null {
  const store = ls()
  if (!store) return null
  try {
    const raw = store.getItem(SESSION_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as PersistedSession
    if (parsed?.accessToken && parsed?.user?.id) return parsed
    return null
  } catch {
    return null
  }
}

// Reach the SDK's (private at the type level, present at runtime) TokenManager so we can
// re-seed a FULL session — both the access token AND the user — which is what makes the
// SDK's own `getCurrentUser()` short-circuit from memory (`tokenManager.getSession()` only
// returns non-null when BOTH are set). We probe defensively (mirrors auth.tsx's existing
// token-probe style) so an SDK version bump can't hard-break this; if the internal shape
// changes we still fall back to the public `setAccessToken`, so authed reads keep working.
type TokenManagerLike = {
  saveSession?: (s: { accessToken: string; user: AuthLikeUser }) => void
  setAccessToken?: (t: string) => void
}
function reachTokenManager(): TokenManagerLike | null {
  const probe = insforge as unknown as {
    tokenManager?: TokenManagerLike
    auth?: { tokenManager?: TokenManagerLike }
    getHttpClient?: () => { tokenManager?: TokenManagerLike }
  }
  return (
    probe.tokenManager ??
    probe.auth?.tokenManager ??
    probe.getHttpClient?.().tokenManager ??
    null
  )
}

/**
 * Re-seed a persisted session into the live SDK client so authed requests + getToken work
 * IMMEDIATELY on this page load, without waiting on (or depending on) the cross-site refresh
 * round-trip. Sets the HTTP bearer via the public `setAccessToken`, and (best-effort) writes
 * the full {accessToken,user} into the TokenManager so `getCurrentUser()` resolves from memory.
 * Returns the restored user (or null).
 */
// Seconds until a JWT expires (negative = already expired; null = undecodable).
function jwtSecondsLeft(token: string): number | null {
  try {
    let b64 = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')
    // atob REQUIRES padded base64 in some engines — re-pad or a valid token reads as null.
    while (b64.length % 4 !== 0) b64 += '='
    const payload = JSON.parse(atob(b64)) as { exp?: number }
    if (typeof payload.exp !== 'number') return null
    return Math.floor(payload.exp - Date.now() / 1000)
  } catch {
    return null
  }
}

// Best-effort: hand the SDK's http layer the body-mode refresh credential. Once set, the
// SDK's own refreshAccessToken uses `/api/auth/refresh?client_type=mobile` + body — no
// cookie, no CSRF (verified in dist 1.4.x). Probed defensively like reachTokenManager.
function seedRefreshTokenIntoClient(refreshToken: string): void {
  try {
    const probe = insforge as unknown as {
      auth?: { http?: { setRefreshToken?: (t: string) => void } }
      getHttpClient?: () => { setRefreshToken?: (t: string) => void }
    }
    probe.auth?.http?.setRefreshToken?.(refreshToken)
    probe.getHttpClient?.()?.setRefreshToken?.(refreshToken)
  } catch {
    /* ignore — ensureFreshAccessToken re-seeds before refreshing anyway */
  }
}

export function rehydrateSessionIntoClient(): AuthLikeUser | null {
  const session = readPersistedSession()
  if (!session) return null

  // Seed the refresh credential FIRST — it's what makes everything below recoverable.
  if (session.refreshToken) seedRefreshTokenIntoClient(session.refreshToken)

  // EXPIRED (or about-to-expire) access token: do NOT seed it into the SDK's session
  // memory. getCurrentUser() short-circuits from memory (dist: `tokenManager.getSession()`
  // → cached user, NO network), so seeding a dead token would freeze the client on it
  // forever. Left empty, getCurrentUser() falls through to the SDK's own refreshSession()
  // — body-mode now, thanks to the seed above — which mints a fresh session and saves it.
  // We still return the user so the UI paints signed-in instantly; if the refresh truly
  // fails (revoked), the async reconcile resolves signed-out exactly as before.
  const secondsLeft = jwtSecondsLeft(session.accessToken)
  if (secondsLeft !== null && secondsLeft <= 60 && session.refreshToken) {
    return session.user
  }

  try {
    ;(insforge as unknown as { setAccessToken?: (t: string) => void }).setAccessToken?.(
      session.accessToken,
    )
  } catch {
    /* ignore */
  }
  const tm = reachTokenManager()
  try {
    if (tm?.saveSession) tm.saveSession({ accessToken: session.accessToken, user: session.user })
    else tm?.setAccessToken?.(session.accessToken)
  } catch {
    /* ignore — bearer is already set above, reads still authenticate */
  }
  return session.user
}

// ───────────── Access-token freshness guard (single choke point for getToken) ─────────────
// getCurrentUser() never re-validates a session it has in memory, and server actions verify
// whatever bearer getToken hands them — so WITHOUT this, an expired in-memory token would sit
// there 401-ing every server action until sign-out. Called by auth.tsx's readAccessToken
// before every token read: if the current token is inside its last 60s (or gone) and we hold
// a refresh credential, run the SDK's public refreshSession() (body-mode) and persist the
// result. Single-flight so the 3s run-page poll can't stampede parallel refreshes.
let freshnessFlight: Promise<void> | null = null
export async function ensureFreshAccessToken(): Promise<void> {
  if (freshnessFlight) return freshnessFlight
  freshnessFlight = (async () => {
    try {
      const stored = readRawStored()
      const refreshToken = stored?.refreshToken
      if (!refreshToken) return // nothing to refresh with — legacy session, behave as before

      const tm = reachTokenManager() as { getAccessToken?: () => string | null } | null
      const current = tm?.getAccessToken?.() ?? stored?.accessToken ?? null
      const secondsLeft = current ? jwtSecondsLeft(current) : -1
      if (secondsLeft !== null && secondsLeft > 60) return // still fresh — no-op

      seedRefreshTokenIntoClient(refreshToken)
      // CRITICAL: use http.refreshAndSaveSession(), NOT auth.refreshSession(). The public
      // refreshSession() in browser mode posts NO body (dist: `void 0`) — pure cookie mode,
      // it never reads the seeded refreshToken (verified: it 401'd in the first local test).
      // refreshAndSaveSession → refreshAccessToken DOES body-mode when http.refreshToken is
      // set, then saves {accessToken,user} into the TokenManager and rotates. authAwareFetch
      // persists any rotated refreshToken from the response.
      const http = (
        insforge as unknown as {
          http?: { refreshAndSaveSession?: () => Promise<unknown> }
          auth?: { http?: { refreshAndSaveSession?: () => Promise<unknown> } }
        }
      )
      const refresher =
        http.http?.refreshAndSaveSession?.bind(http.http) ??
        http.auth?.http?.refreshAndSaveSession?.bind(http.auth.http)
      if (!refresher) return
      await refresher()

      // Persist the freshened access token so reloads + getToken fallbacks see it.
      const freshToken = (reachTokenManager() as { getAccessToken?: () => string | null } | null)
        ?.getAccessToken?.()
      const user = stored?.user
      if (freshToken && user?.id) {
        persistSession({ accessToken: freshToken, user: user as AuthLikeUser })
      }
    } catch {
      /* best-effort — callers fall back to whatever token exists; verifyUser re-validates */
    } finally {
      freshnessFlight = null
    }
  })()
  return freshnessFlight
}

// ───────────────────────── Transient-read resilience ─────────────────────────
// Wrap a `{ data, error }` SDK read so a TRANSIENT failure (the 8s timeout 408, a
// 5xx, or a network blip — exactly the InsForge intermittent-timeout symptom that
// false-logged-out users tonight) is retried a few times before the caller sees it,
// instead of hard-failing a one-shot load. A genuine 4xx (401/403/404/422 — auth or
// a real "not found") is returned IMMEDIATELY so we never mask a real signed-out
// state or paper over a real not-found. Preserves the `{ data, error }` shape, so a
// caller that does `if (error) return` / `if (!error) setX()` behaves identically on
// success and on a real 4xx — it just gets a recovered result across an InsForge blip.
// The SDK's query builders are *thenables* (PostgrestBuilder), not real Promises, and
// every read resolves to a `{ data, error }` envelope where `error` (when present) is
// an InsForgeError carrying a numeric `statusCode`. We accept any thenable of that
// envelope shape and normalize so callers keep destructuring `{ data, error }`.
type ReadResult<T> = { data: T; error: { statusCode?: number } | null }
export async function resilientRead<R extends { data: unknown; error: unknown }>(
  read: () => PromiseLike<R>,
  { attempts = 3, baseDelayMs = 400 }: { attempts?: number; baseDelayMs?: number } = {},
): Promise<{ data: R['data']; error: R['error'] }> {
  const statusOf = (err: unknown): number | undefined =>
    err && typeof err === 'object' ? (err as { statusCode?: number }).statusCode : undefined
  let last: { data: R['data']; error: R['error'] } = {
    data: null as R['data'],
    error: { statusCode: 0 } as R['error'],
  }
  for (let i = 0; ; i++) {
    try {
      const res = await read()
      const status = statusOf(res.error)
      // Success, or a genuine client error (4xx) → return as-is, don't retry.
      if (!res.error || (typeof status === 'number' && status >= 400 && status < 500)) {
        return res
      }
      last = res // transient (408/5xx/network status 0) → fall through to retry
    } catch (e) {
      // A thrown error: treat a thrown 4xx as terminal, everything else as transient.
      const status = statusOf(e)
      if (typeof status === 'number' && status >= 400 && status < 500) {
        return { data: null as R['data'], error: { statusCode: status } as R['error'] }
      }
      last = { data: null as R['data'], error: { statusCode: status ?? 0 } as R['error'] }
    }
    if (i >= attempts) return last
    await new Promise((r) => setTimeout(r, baseDelayMs * (i + 1)))
  }
}

// Server-only admin client — full access, bypasses RLS. ONLY call inside server
// actions / route handlers (the INSFORGE_API_KEY is never exposed to the browser).
export function adminClient() {
  return createAdminClient({
    baseUrl: process.env.INSFORGE_URL!,
    apiKey: process.env.INSFORGE_API_KEY!,
    // Admin reads are heavier (e.g. runs ⨝ auth.users) and run server-side where a
    // longer wait is acceptable — keep a roomier 15s ceiling (still half the 30s
    // default) so legit slow joins don't 408, while the SDK retries 5xx/network.
    timeout: 15000,
    retryCount: 3,
    retryDelay: 500,
  })
}

// ─────────────────────────── Server-side identity ───────────────────────────
// Verify a client-supplied access token against InsForge and return the AUTHORITATIVE
// user. The token is a signed JWT; passing it as `accessToken` puts the client in
// server mode so `getCurrentUser()` makes a network call to /api/auth/sessions/current
// that validates it server-side. This is the ONLY trustworthy identity source in a
// server action — NEVER trust a client-supplied user id (the admin client bypasses
// RLS, so a forged id would be a cross-tenant write / auth bypass). Returns null when
// the token is absent, malformed, or rejected.
export async function verifyUser(
  accessToken: string | null | undefined,
): Promise<{ id: string; email?: string } | null> {
  if (!accessToken || typeof accessToken !== 'string') return null
  const client = createClient({
    baseUrl: process.env.INSFORGE_URL || process.env.NEXT_PUBLIC_INSFORGE_URL!,
    anonKey: process.env.NEXT_PUBLIC_INSFORGE_ANON_KEY!,
    accessToken, // → server mode → getCurrentUser() verifies via network
    // Short-lived client used inside a server action on the post-payment critical
    // path. 8s timeout so a slow InsForge call fails fast (SDK throws 408, not a 30s
    // hang that could blow the action's own time budget). The SDK retries 5xx/network
    // internally; we additionally retry the 408 timeout ourselves below, because a
    // transient blip here would FALSE-REJECT a valid token (read as "not signed in")
    // and strand a paying user. A genuine bad/expired token returns a fast 401 — never
    // retried, so this still rejects forged/expired tokens immediately.
    timeout: 8000,
    retryCount: 3,
    retryDelay: 400,
  })
  for (let attempt = 0; ; attempt++) {
    try {
      const { data, error } = await client.auth.getCurrentUser()
      if (error) {
        const status = (error as { statusCode?: number })?.statusCode
        // 401/403 = the token is genuinely rejected → null now (→ authError, "sign in").
        // Any other error (408 timeout / 5xx / network) is transient: retry, then THROW —
        // never return null — so a brownout can't false-reject a VALID token and strand a
        // signed-in / paying user behind a "session expired" wall (a null here reads as
        // authError). A throw is caught upstream as a transient blip that keeps retrying.
        if (status === 401 || status === 403) return null
        if (attempt >= 3) throw new Error('verifyUser: auth service unreachable (transient)')
      } else {
        const u = (data?.user ?? null) as { id?: string; email?: string } | null
        return u?.id ? { id: u.id, email: u.email } : null
      }
    } catch (e) {
      // Thrown (rather than returned) errors: same treatment. A thrown 401/403 is a
      // real rejection (→ null); anything else is transient → retry, then re-throw.
      const status = (e as { statusCode?: number })?.statusCode
      if (status === 401 || status === 403) return null
      if (attempt >= 3) throw new Error('verifyUser: auth service unreachable (transient)')
    }
    await new Promise((r) => setTimeout(r, 400 * (attempt + 1)))
  }
}
