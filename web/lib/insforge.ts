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
export const insforge = createClient({
  baseUrl: process.env.NEXT_PUBLIC_INSFORGE_URL!,
  anonKey: process.env.NEXT_PUBLIC_INSFORGE_ANON_KEY!,
  fetch: keepAliveFetch,
  timeout: 8000,
  retryCount: 3,
  retryDelay: 400,
})

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
        // 401/403 = the token is genuinely rejected → null now (don't retry, don't
        // mask a real auth failure). Any other error (408 timeout / 5xx / network) is
        // transient → retry a few times before giving up.
        if (status === 401 || status === 403 || attempt >= 3) return null
      } else {
        const u = (data?.user ?? null) as { id?: string; email?: string } | null
        return u?.id ? { id: u.id, email: u.email } : null
      }
    } catch (e) {
      // Thrown (rather than returned) errors: same treatment. A thrown 401/403 is a
      // real rejection; anything else is transient and worth a retry.
      const status = (e as { statusCode?: number })?.statusCode
      if (status === 401 || status === 403 || attempt >= 3) return null
    }
    await new Promise((r) => setTimeout(r, 400 * (attempt + 1)))
  }
}
