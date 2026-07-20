'use server'
import { adminClient, verifyUser } from '../lib/insforge'
import type { Run, RunEvent } from '../lib/types'

// The product owner — the ONLY account allowed to read the business-wide analytics
// (every run's revenue/COGS/profit). Matches the run page's OWNER_EMAIL gate, but
// here the gate is a real security boundary: the admin client below bypasses RLS, so
// the email check MUST happen server-side after verifying the token (never trust the
// client). Mirrors readInsideRun's developer gate.
const OWNER_EMAIL = 'denniswanglabs@gmail.com'

// Internal: is this ALREADY-VERIFIED user id a developer? (No token check — callers
// must have verified the token first.) Used to gate /inside reads + real-mode builds.
async function isDeveloperId(userId: string): Promise<boolean> {
  if (!userId) return false
  const db = adminClient()
  const { data } = await db.database
    .from('developers')
    .select('developer')
    .eq('user_id', userId)
    .maybeSingle()
  return !!(data && (data as { developer?: boolean }).developer)
}

const ALLOWED_BRAINS = new Set(['super-free', 'super-paid', 'ultra-paid'])

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))

// Retry a Supabase/InsForge call that returns `{ data, error }`. A transient
// InsForge blip (network/gateway hiccup) on the build-enqueue inserts otherwise
// surfaces to the user as a failed build; retrying with backoff (500ms→1s→2s)
// converts a blip into a build that's 1–2s slower but succeeds. The op is retried
// only on a returned `error` (or a thrown one) — a successful insert returns on the
// first attempt. attempts=3 → up to 3 tries total.
async function withRetry<T extends { data?: unknown; error: unknown }>(
  // The InsForge/Postgrest query builder is a *thenable*, not a real Promise, so
  // accept PromiseLike here and `await` it (await unwraps either).
  op: () => PromiseLike<T>,
  { attempts = 3, baseDelayMs = 500 }: { attempts?: number; baseDelayMs?: number } = {},
): Promise<T> {
  let last: T | undefined
  for (let i = 0; i < attempts; i++) {
    try {
      const res = await op()
      if (!res.error) return res
      last = res
    } catch (e) {
      last = { error: e } as T
    }
    if (i < attempts - 1) await sleep(baseDelayMs * 2 ** i) // 500, 1000, 2000…
  }
  return last as T
}

// ─────────────────────────── In-browser editor: save ───────────────────────────
// Persist the editor's edited props into runs.props_edited (a separate jsonb column
// from the clean, worker-generated `props`, so "revert to original" stays possible).
// Admin client bypasses RLS — but we derive the caller from a server-verified access
// token and check it owns the run before writing, so a user can only save edits to a
// run they own. The clean `props` column is never touched here.
export async function saveEditedProps(input: {
  runId: string
  accessToken: string
  props: unknown
}): Promise<{ ok: boolean; error?: string }> {
  if (!input.runId) return { ok: false, error: 'missing runId' }
  const me = await verifyUser(input.accessToken)
  if (!me) return { ok: false, error: 'not signed in' }
  if (input.props == null || typeof input.props !== 'object') {
    return { ok: false, error: 'invalid props' }
  }
  const db = adminClient()
  // Ownership check: the admin client ignores RLS, so verify the run belongs to the
  // SERVER-VERIFIED caller before writing (the passed token, not a client-set id).
  const { data: run, error: readErr } = await db.database
    .from('runs')
    .select('id, user_id')
    .eq('id', input.runId)
    .maybeSingle()
  if (readErr) return { ok: false, error: 'read: ' + JSON.stringify(readErr) }
  if (!run) return { ok: false, error: 'run not found' }
  if ((run as { user_id?: string }).user_id !== me.id) {
    return { ok: false, error: 'not the run owner' }
  }
  const { error } = await db.database
    .from('runs')
    .update({ props_edited: input.props })
    .eq('id', input.runId)
  if (error) return { ok: false, error: JSON.stringify(error) }
  return { ok: true }
}


// ─────────────────────────────── Credits (beta) ───────────────────────────────
// The ledger is append-only (spends negative, refunds positive, run_id links a
// spend to its build); balances are DERIVED, never stored.
// CREDITS ARE TOKENS. 1 credit = 35 tokens of model work, so the price of
// a thing is what it actually costs to think about:
//   a film  ≈ 22,400 tokens (plan ~9k + a critic that SEES 6 stills ~13k)
//           → 640 credits
//   an edit ≈  2,500 tokens (beats + events tail + the reply)
//           →  70 credits
// A day's 3,000 credits therefore buys 3 films AND 10 edits (2,620) with
// five more edits of headroom — the allowance Dennis specified, derived
// rather than guessed. Conversation and gate-declined edits stay free.
const VIDEO_CREDIT_COST = 640
const EDIT_CREDIT_COST = 70
const DAILY_CREDIT_CAP = 3000
const LIFETIME_CREDIT_CAP = 15000

async function creditBalances(db: ReturnType<typeof adminClient>, userId: string) {
  const { data: rows } = await db.database
    .from('credit_ledger')
    .select('delta, created_at')
    .eq('user_id', userId)
  const all = (rows as { delta: number; created_at: string }[]) || []
  const dayStart = Date.now() - 24 * 60 * 60_000
  const sum = (xs: number[]) => xs.reduce((a, b) => a + b, 0)
  // "Used" is net spend (refunds net out), floored at 0.
  const lifetimeUsed = Math.max(0, -sum(all.map((r) => r.delta)))
  const dailyUsed = Math.max(0, -sum(
    all.filter((r) => Date.parse(r.created_at) >= dayStart).map((r) => r.delta)))
  return { dailyUsed, lifetimeUsed }
}

/** Ploy-style credit card data for the signed-in user. Owner gets unlimited. */
export async function getCredits(accessToken: string): Promise<{
  dailyUsed: number; dailyCap: number
  lifetimeUsed: number; lifetimeCap: number
  videoCost: number; editCost: number; unlimited: boolean
} | { error: 'not-signed-in' }> {
  const me = await verifyUser(accessToken)
  if (!me) return { error: 'not-signed-in' as const }
  const unlimited = (me.email || '').toLowerCase() === OWNER_EMAIL
  const db = adminClient()
  const bal = unlimited ? { dailyUsed: 0, lifetimeUsed: 0 }
    : await creditBalances(db, me.id)
  return {
    dailyUsed: bal.dailyUsed, dailyCap: DAILY_CREDIT_CAP,
    lifetimeUsed: bal.lifetimeUsed, lifetimeCap: LIFETIME_CREDIT_CAP,
    videoCost: VIDEO_CREDIT_COST, editCost: EDIT_CREDIT_COST, unlimited,
  }
}

// Create a build the way the worker expects: a `runs` row (status=queued) + a `jobs`
// row (status=queued). The Railway worker's claim_next_job picks it up. user_id comes
// from the signed-in user (the run owner). Returns the new run id + key.
export async function createBuild(input: {
  accessToken: string
  url: string
  goal?: string
  emphasis?: string
  brain?: string
  mode?: 'mock' | 'real'
  /** Visual style family. 'engineered-night' renders the dark one-world style;
      anything else (or absent) is the classic light look. */
  look?: 'classic' | 'engineered-night' | 'walkrec'
  // Opt-in HUMAN payment: 'auto' (default) lets the worker auto-resolve payment
  // (PRODUCER_SIMULATE_PAID); 'human' creates a REAL Stripe TEST checkout the user
  // must pay (test card 4242) before the build proceeds. Only the payment becomes
  // real — the render stays $0 mock.
  payMode?: 'auto' | 'human'
}): Promise<{ runId: string; runKey: string } | { limit: true; message: string }> {
  // Identity comes from the verified token, NEVER from the client. The owner of the
  // build is whoever the token belongs to.
  const me = await verifyUser(input.accessToken)
  // The operator defaults to the walkrec pipeline (Dennis 2026-07-19: "I want
  // to use the new one"): a plain submit with no explicit mode upgrades to
  // walkrec for the owner account only — public beta users keep classic
  // unless they carry the ?look=walkrec flag. /?look=classic stays an
  // explicit escape (the client sends it through as-is).
  let look = input.look
  if (me && (me.email || '').toLowerCase() === OWNER_EMAIL && !look) {
    look = 'walkrec'
  }
  if (!me) throw new Error('Please sign in to start a build.')

  // Validate the URL is a real http(s) address (defense-in-depth; the worker also
  // SSRF-guards the fetch, but reject obvious garbage before we enqueue + spend).
  const rawUrl = (input.url || '').trim()
  if (!/^https?:\/\/[^\s]+\.[^\s]+/i.test(rawUrl)) throw new Error('Enter a valid website URL.')

  const db = adminClient()

  // Rate limit: cap builds per user per window so a scripted loop can't drain the
  // Nemotron/render budget. Time-based + status-agnostic (stuck rows never wedge it).
  const windowStart = new Date(Date.now() - 10 * 60_000).toISOString()
  const { data: recent } = await db.database
    .from('runs')
    .select('id')
    .eq('user_id', me.id)
    .gte('created_at', windowStart)
  if (recent && recent.length >= 10) {
    throw new Error('Too many builds in a short window — give it a minute and try again.')
  }

  // Beta cap: every account EXCEPT the owner gets N videos per rolling 24h DAY while
  // Filmo is in beta — protects the Nemotron/ElevenLabs budget from a stranger draining
  // it, while letting people come back tomorrow. Identity is the server-verified token
  // (never the client) and the admin count bypasses RLS, so it can't be gamed. The owner
  // is exempt. We RETURN a structured { limit } (not throw) so the UI shows the friendly
  // message inline rather than the opaque "Server Components render" server-action error.
  // FREE INDEFINITELY; THE CREDIT CAP IS THE ONLY LIMIT (Dennis, 2026-07-19).
  // There was a hard date here — builds paused for every non-owner after
  // 2026-07-22 — which is a time bomb, not a policy: nothing would look wrong
  // until the morning the product silently stopped accepting work. The daily
  // and lifetime caps below already protect the model budget, continuously and
  // without a cliff, so the date bought nothing that the caps don't. Do not
  // reintroduce a wall-clock expiry; if the free tier ever ends, that is a
  // deliberate product decision that ships with its own messaging.
  if ((me.email || '').toLowerCase() !== OWNER_EMAIL) {
    // CREDITS (beta): costs and caps are the constants above — never restate
    // them here, or the comment rots the moment they move. Balance is the SUM
    // of an append-only ledger (spends negative; failed builds refunded by the
    // worker), so failed attempts do not consume the allowance. Server-side,
    // admin client — can't be gamed.
    const bal = await creditBalances(db, me.id)
    if (bal.dailyUsed + VIDEO_CREDIT_COST > DAILY_CREDIT_CAP) {
      return {
        limit: true as const,
        message: `You've used today's ${DAILY_CREDIT_CAP.toLocaleString()} credits. They refresh tomorrow morning — see you then.`,
      }
    }
    if (bal.lifetimeUsed + VIDEO_CREDIT_COST > LIFETIME_CREDIT_CAP) {
      return {
        limit: true as const,
        message: `You've reached the beta's ${LIFETIME_CREDIT_CAP}-credit allowance. Paid credits are coming — thanks for filming with us!`,
      }
    }
  }

  // Whitelist every client-supplied param (never forward raw — the worker trusts these).
  // Single coherent tier: every video is produced the same way. `quality` is pinned to
  // 'standard' (kept only to satisfy the existing runs/jobs schema + worker param contract).
  const quality = 'standard' as const
  const brain = input.brain && ALLOWED_BRAINS.has(input.brain) ? input.brain : 'super-free'
  const lookFinal: 'classic' | 'engineered-night' | 'walkrec' =
    look === 'walkrec' ? 'walkrec'
    : look === 'engineered-night' ? 'engineered-night' : 'classic'
  const mode: 'mock' | 'real' = input.mode === 'real' ? 'real' : 'mock'
  let payMode: 'auto' | 'human' = input.payMode === 'human' ? 'human' : 'auto'

  // COST GUARD: 'real' mode spends real third-party COGS (Higgsfield/ElevenLabs). Never
  // let it run for free — force a real (test) Stripe checkout unless the caller is an
  // operator/developer account. Demo/normal users always run $0 mock anyway.
  if (mode === 'real' && payMode !== 'human') {
    const dev = await isDeveloperId(me.id)
    if (!dev) payMode = 'human'
  }

  const runKey = `web-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
  const brand = rawUrl.replace(/^https?:\/\//, '').replace(/\/.*$/, '')
  const goal = input.goal || 'A 30-second brand explainer'

  // Both enqueue inserts retry on a transient InsForge error so a one-off blip
  // doesn't surface as a failed build (see withRetry).
  const { data: runs, error: runErr } = await withRetry(() =>
    db.database
      .from('runs')
      .insert([{
        user_id: me.id, run_key: runKey, brand, company_url: rawUrl,
        goal, emphasis: input.emphasis || null, quality, brain, mode, status: 'queued',
        // Walkrec beta: free (price 0), narrated via agent_events, Sonnet-planned.
        film_mode: lookFinal === 'walkrec' ? 'walkrec' : 'classic',
        ...(lookFinal === 'walkrec' ? { price_cents: 0 } : {}),
      }])
      .select(),
  )
  if (runErr) throw new Error('runs.insert: ' + JSON.stringify(runErr))
  const runId = runs![0].id

  const params = { company_url: rawUrl, goal, emphasis: input.emphasis || '', quality, brain, mode, look: lookFinal, pay_mode: payMode, run_key: runKey, duration: 30 }
  const { error: jobErr } = await withRetry(() =>
    db.database.from('jobs').insert([{ run_id: runId, status: 'queued', params }]),
  )
  if (jobErr) throw new Error('jobs.insert: ' + JSON.stringify(jobErr))

  // Charge the video at creation (owner exempt). The worker refunds this row
  // if the build fails, so failed attempts never consume the allowance. The
  // partial unique index (run_id, reason) makes the charge idempotent.
  if ((me.email || '').toLowerCase() !== OWNER_EMAIL) {
    await withRetry(() => db.database.from('credit_ledger').insert([{
      user_id: me.id, delta: -VIDEO_CREDIT_COST, reason: 'video', run_id: runId,
    }]))
  }

  return { runId, runKey }
}

// ─────────────────────── Editor: Export → re-render job ───────────────────────
// Enqueue a `rerender` job: the worker re-renders the run's saved props_edited into
// a NEW video (runs.edited_url) without re-running capture/plan/price. Mirrors
// createBuild's insert shape, but reuses the EXISTING run row (no new run) and tags
// the job type 'rerender'. Ownership is verified against the run before enqueueing.
export async function requestReRender(input: {
  runId: string
  accessToken: string
}): Promise<{ ok: boolean; error?: string }> {
  if (!input.runId) return { ok: false, error: 'missing runId' }
  const me = await verifyUser(input.accessToken)
  if (!me) return { ok: false, error: 'not signed in' }
  const db = adminClient()
  const { data: run, error: readErr } = await db.database
    .from('runs')
    .select('id, user_id, run_key, props, props_edited')
    .eq('id', input.runId)
    .maybeSingle()
  if (readErr) return { ok: false, error: 'read: ' + JSON.stringify(readErr) }
  if (!run) return { ok: false, error: 'run not found' }
  const r = run as { user_id?: string; run_key?: string; props?: unknown; props_edited?: unknown }
  if (r.user_id !== me.id) return { ok: false, error: 'not the run owner' }
  // Need SOMETHING to render: a saved edit, or the clean props as a fallback.
  const hasProps =
    (r.props_edited && typeof r.props_edited === 'object') ||
    (r.props && typeof r.props === 'object')
  if (!hasProps) return { ok: false, error: 'no props to re-render' }

  // Avoid stacking duplicate pending rerender jobs for the same run.
  const { data: pending } = await db.database
    .from('jobs')
    .select('id, status, type')
    .eq('run_id', input.runId)
    .eq('type', 'rerender')
    .in('status', ['queued', 'claimed'])
  if (pending && pending.length > 0) {
    return { ok: true } // a rerender is already in flight; treat as success (idempotent)
  }

  const params = { run_key: r.run_key, from: 'props_edited' }
  const { error: jobErr } = await db.database
    .from('jobs')
    .insert([{ run_id: input.runId, type: 'rerender', status: 'queued', params }])
  if (jobErr) return { ok: false, error: 'jobs.insert: ' + JSON.stringify(jobErr) }
  // Clear the previous edited_url so the run page shows "rendering" until the new one lands.
  await db.database.from('runs').update({ edited_url: null }).eq('id', input.runId)
  return { ok: true }
}

// ─────────────────────────────── Developer mode ───────────────────────────────
// Key-gated "see the machinery" access for hackathon judges. A signed-in account
// pairs a secret DEV_MODE_KEY (validated SERVER-SIDE only) and gets a row in the
// `developers` table — `developer = true` unlocks /inside/[runId] forever for that
// account. The key never leaves the server: it is compared to process.env.DEV_MODE_KEY
// and is NEVER returned, logged, or shipped to the browser.

/**
 * Validate a dev-mode key (server-only) and, on match, set the developer flag for the
 * given signed-in user. Idempotent: re-pairing the same account is a no-op success.
 * Returns only `{ ok }` — never the key or the env value.
 */
export async function pairDeveloper(input: { key: string; accessToken: string }): Promise<{ ok: boolean }> {
  const expected = process.env.DEV_MODE_KEY
  // Reject if the server has no key configured, or the supplied key doesn't match.
  // Constant-ish compare; we intentionally do not branch-log the comparison.
  if (!expected || !input.key || input.key !== expected) return { ok: false }
  // Only the SERVER-VERIFIED caller can grant THEMSELVES developer — never an arbitrary id.
  const me = await verifyUser(input.accessToken)
  if (!me) return { ok: false }

  const db = adminClient()
  // Upsert-by-hand (read → insert-or-noop) so re-pairing is safe and we never throw on
  // a duplicate.
  const { data: existing } = await db.database
    .from('developers')
    .select('user_id')
    .eq('user_id', me.id)
    .maybeSingle()

  if (!existing) {
    const { error } = await db.database
      .from('developers')
      .insert([{ user_id: me.id, developer: true, source: 'dev_mode_key' }])
    if (error) throw new Error('developers.insert: ' + JSON.stringify(error))
  }
  return { ok: true }
}

/** Is the SERVER-VERIFIED caller a developer? Used to gate /inside/[runId]. */
export async function isDeveloper(accessToken: string | null | undefined): Promise<boolean> {
  const me = await verifyUser(accessToken)
  if (!me) return false
  return isDeveloperId(me.id)
}

/**
 * Admin-client fetch of a run + its run_events, so a developer can view ANY run
 * (including the canonical featured run they don't own). Returns null if not found
 * OR if the caller isn't a verified developer. Bypasses RLS by design — so it MUST
 * server-side gate on isDeveloper (the client gate alone is not a security boundary).
 */
export async function readInsideRun(input: { runId: string; accessToken: string }): Promise<{
  run: Record<string, unknown>
  events: Record<string, unknown>[]
} | null> {
  const runId = input?.runId
  if (!runId) return null
  // Server-side authorization: only a verified developer may read arbitrary runs.
  const me = await verifyUser(input.accessToken)
  if (!me || !(await isDeveloperId(me.id))) return null
  const db = adminClient()
  const { data: run } = await db.database
    .from('runs')
    .select()
    .eq('id', runId)
    .maybeSingle()
  if (!run) return null

  const { data: events } = await db.database
    .from('run_events')
    .select()
    .eq('run_id', runId)
    .order('seq', { ascending: true })

  return {
    run: run as Record<string, unknown>,
    events: (events as Record<string, unknown>[]) ?? [],
  }
}

// ───────────────────────── Run page: server-side owner read ─────────────────────────
// AUTHORITATIVE run read for the run page + editor, done SERVER-SIDE via the admin
// (service-key) client so it NEVER depends on the freshness of the browser's RLS token.
//
// ROOT CAUSE this fixes: the run page used to read `runs`/`run_events`/`jobs` directly
// from the browser via the anon (RLS-scoped) client. The session JWT is a ~15-min token
// rehydrated from localStorage; when a user opens an EMAILED /runs/<id> link in a cold tab
// long after that token expired, the RLS read returned EMPTY (no error) and the page lied
// "This run could not be found." Moving the read here removes the token-freshness coupling:
// we verify the token server-side (a stale token → authError, NOT notFound), then admin-read
// the run owner-scoped. The admin client bypasses RLS, so the owner gate below is a REAL
// security boundary (mirrors readAnalytics/readInsideRun): only the run's owner — or the
// system owner (OWNER_EMAIL, who may view any run, matching the analytics gate) — gets data;
// any other verified user is told notFound (privacy: they can't enumerate others' runs).

// Discriminated result. The page maps: notFound → "could not be found"; authError → the
// re-auth ("Sign in again") branch (an expired token now prompts re-auth instead of lying);
// { run, events, rerenderInFlight } → render as today.
export type RunForViewerResult =
  | { authError: true }
  | { notFound: true }
  | { run: Run; events: RunEvent[]; rerenderInFlight: boolean }


// Media playback boundary: storage objects serve `binary/octet-stream` (the
// platform drops upload MIMEs), which Chrome's <video> refuses to sniff — so
// any URL the app will PLAY is rewritten through /api/media, which stamps the
// real MIME from the extension and forwards Range. Same-origin relative URL,
// safe for <video src>.
function proxyPlayableUrl(u: string | null | undefined): string | null {
  if (!u || typeof u !== 'string') return u ?? null
  try {
    const parsed = new URL(u)
    if (!parsed.pathname.includes('/api/storage/buckets/')) return u
  } catch {
    return u
  }
  return `/api/media?u=${encodeURIComponent(u)}`
}

export async function getRunForViewer(input: {
  runId: string
  accessToken: string | null | undefined
  // Terminal watch tick: the run page already has the (heavy) props loaded and only
  // polls to catch a rerender's edited_url. When true we skip re-pulling run_events
  // (frozen once terminal) — mirroring the page's old client-side terminal regime that
  // avoided re-fetching the feed every 3s. The run row itself is always returned in full
  // (the admin path doesn't pay the EU→Singapore anon-client heavy-blob penalty the same
  // way, and the page merges it the same either way).
  terminalWatch?: boolean
}): Promise<RunForViewerResult> {
  if (!input.runId) return { notFound: true }
  // 1) Verify the caller server-side. A stale/expired token → authError (the page sends
  //    this to the re-auth branch), NEVER a false notFound.
  const me = await verifyUser(input.accessToken)
  if (!me) return { authError: true }

  const db = adminClient()
  // 2) Admin-read the run by id (bypasses RLS).
  const { data: runRow } = await db.database
    .from('runs')
    .select()
    .eq('id', input.runId)
    .maybeSingle()
  if (!runRow) return { notFound: true }
  const run = runRow as Run

  // 3) Owner gate (the real security boundary now that RLS is bypassed): only the run's
  //    owner, or the system owner, may view it. Anyone else → notFound (don't reveal it
  //    exists). Matches readAnalytics' OWNER_EMAIL gate for the system-owner exception.
  const isSystemOwner = (me.email || '').toLowerCase() === OWNER_EMAIL
  if (run.user_id !== me.id && !isSystemOwner) return { notFound: true }

  // 4) Events feed (ordered by seq asc), same as the page derived it. Skipped on a
  //    terminal-watch tick (the feed is frozen once terminal — see input.terminalWatch).
  let events: RunEvent[] = []
  if (!input.terminalWatch) {
    const { data: ev } = await db.database
      .from('run_events')
      .select()
      .eq('run_id', input.runId)
      .order('seq', { ascending: true })
    events = (ev as RunEvent[]) ?? []
  }

  // 5) Rerender-in-flight: an editor Export enqueues a `rerender` job AFTER delivery, so
  //    the page keeps polling while one is queued/claimed (to catch edited_url). Derived
  //    the SAME way the page did client-side.
  const rerenderInFlight = await isRerenderInFlight(db, input.runId)

  const playableRun = {
    ...run,
    final_url: proxyPlayableUrl(run.final_url),
    edited_url: proxyPlayableUrl(run.edited_url),
  } as Run

  return { run: playableRun, events, rerenderInFlight }
}

// Shared: is a rerender job for this run queued or claimed? (Matches the run page's old
// client check + requestReRender's dedupe.) Takes the already-built admin client so the
// owner-gated caller doesn't spin up a second one.
async function isRerenderInFlight(
  db: ReturnType<typeof adminClient>,
  runId: string,
): Promise<boolean> {
  const { data: jobs } = await db.database
    .from('jobs')
    .select('id, type, status')
    .eq('run_id', runId)
    .eq('type', 'rerender')
    .in('status', ['queued', 'claimed'])
  return !!(jobs && jobs.length > 0)
}

// ───────────────────────── /videos: server-side owner list ─────────────────────────
// AUTHORITATIVE list of the signed-in user's own runs for the "Your Videos" page, read
// SERVER-SIDE via the admin (service-key) client so it NEVER depends on the freshness of
// the browser's RLS token. SAME bug/fix as the run page (getRunForViewer): the /videos
// page used to read `runs` directly from the browser via the anon (RLS-scoped) client, so
// a stale/expired ~15-min session token (e.g. after a Stripe-payment redirect logged the
// tab out) returned EMPTY with no error — the user saw a misleading "No builds yet" empty
// list instead of their videos. We verify the token server-side (stale → authError, which
// the page routes to the "sign in" gate, NOT a false empty), then admin-read that user's
// runs owner-scoped. The admin client bypasses RLS, and the `.eq('user_id', me.id)` filter
// IS the owner boundary (a verified user can only ever list their own runs).
export type MyRunsResult = { authError: true } | { runs: Run[] }

export async function listMyRuns(accessToken: string | null | undefined): Promise<MyRunsResult> {
  // 1) Verify the caller server-side. A stale/expired token → authError (the page shows
  //    the sign-in gate), NEVER a false-empty list.
  const me = await verifyUser(accessToken)
  if (!me) return { authError: true }

  // 2) Admin-read this user's runs, owner-scoped. Same columns + ordering + limit the
  //    page used client-side, so the rendered list is byte-for-byte what it showed before.
  const db = adminClient()
  const { data } = await db.database
    .from('runs')
    .select(
      'id, brand, company_url, goal, quality, status, phase, price_cents, margin, final_url, created_at, film_mode',
    )
    .eq('user_id', me.id)
    .order('created_at', { ascending: false })
    .limit(20)
  return { runs: (data as Run[]) ?? [] }
}

// ───────────────────────────────── Assets library ─────────────────────────────
// Everything Filmo has taken from a customer's site or made from it, in one
// place. This is the provenance ledger made browsable: every page it read,
// every mark it captured, every second it recorded, every scene it cut. All
// of it already exists as agent_events artifacts + runs.final_url — the
// library is a VIEW, never a second copy.
export type AssetKind = 'film' | 'recording' | 'capture' | 'mark' | 'scene'

export interface AssetRow {
  id: string
  kind: AssetKind
  name: string
  url: string
  runId: string
  brand: string
  ts: number
  video: boolean
}

const ASSET_OF_KIND: Record<string, AssetKind> = {
  'read.page': 'capture',
  'brand.logo': 'mark',
  'film.shot': 'recording',
  'design.beat': 'scene',
}

/** Strip the event's verb so the asset reads as a thing, not a log line. */
function assetName(kind: string, title: string): string {
  const t = (title || '').trim()
  if (kind === 'read.page') {
    const m = t.replace(/^Read\s+/i, '')
    try {
      return m.startsWith('http') ? new URL(m).pathname || '/' : m
    } catch { return m }
  }
  if (kind === 'film.shot') return t.replace(/^Shot kept:\s*/i, '')
  if (kind === 'design.beat') return t.replace(/\s*\(.*\)$/, '').replace(/:/, ' —')
  if (kind === 'brand.logo') return 'Brand mark'
  return t
}

export async function listAssets(accessToken: string | null | undefined): Promise<
  { authError: true } | { assets: AssetRow[] }
> {
  const me = await verifyUser(accessToken)
  if (!me) return { authError: true }
  const db = adminClient()
  const { data: runRows } = await db.database
    .from('runs')
    .select('id, brand, company_url, final_url, created_at')
    .eq('user_id', me.id)
    .order('created_at', { ascending: false })
    .limit(40)
  const runs = (runRows as {
    id: string; brand: string | null; company_url: string | null
    final_url: string | null; created_at: string
  }[]) || []
  if (!runs.length) return { assets: [] }
  const byId = new Map(runs.map((r) => [r.id, r]))

  const { data: evtRows } = await db.database
    .from('agent_events')
    .select('run_id, seq, ts, kind, title, artifact_url')
    .in('run_id', runs.map((r) => r.id))
    .in('kind', Object.keys(ASSET_OF_KIND))
    .neq('artifact_url', '')
    .order('ts', { ascending: false })
    .limit(600)

  const assets: AssetRow[] = []
  for (const r of runs) {
    if (!r.final_url) continue
    assets.push({
      id: `film-${r.id}`, kind: 'film',
      name: `${r.brand || r.company_url || 'Launch'} film`,
      url: proxyPlayableUrl(r.final_url) || '',
      runId: r.id, brand: r.brand || r.company_url || '',
      ts: Date.parse(r.created_at) / 1000, video: true,
    })
  }
  for (const e of ((evtRows as {
    run_id: string; seq: number; ts: number; kind: string
    title: string; artifact_url: string
  }[]) || [])) {
    const run = byId.get(e.run_id)
    if (!run) continue
    assets.push({
      id: `${e.run_id}-${e.seq}`, kind: ASSET_OF_KIND[e.kind],
      name: assetName(e.kind, e.title),
      url: `/api/agent-artifact?u=${encodeURIComponent(e.artifact_url)}`,
      runId: e.run_id, brand: run.brand || run.company_url || '',
      ts: e.ts, video: /\.mp4(\?|$)/i.test(e.artifact_url),
    })
  }
  assets.sort((a, b) => b.ts - a.ts)
  return { assets }
}

// ─────────────────────────────── Owner analytics ───────────────────────────────
// The business-wide P&L: EVERY run's revenue / COGS / profit, plus splits. Admin
// client bypasses RLS, so this is owner-only — the gate is a real security boundary,
// not a cosmetic one. We verify the token server-side and require the verified email
// to equal OWNER_EMAIL before reading a single row. A non-owner gets `authorized:
// false` and NO data. (runs.cogs_cents is NULL on every run today, so the page does NOT
// trust it — it recomputes COGS from ElevenLabs VO + REAL Nemotron token spend, reading
// the per-run `brain` rate and `selection.planner_usage.cost` we surface below.)

export interface AnalyticsRunRow {
  id: string
  created_at: string
  brand: string | null
  company_url: string
  status: string
  price_cents: number | null
  cogs_cents: number | null
  final_url: string | null
  /** Pulled out of props.producer when set (e.g. 'hetzner-hermes' / 'hetzner-curated'). */
  producer: string | null
  /** Real rendered video duration in seconds, derived from props.total_frames / props.fps
   *  when both are present (else null). Used to estimate VO cost (ElevenLabs is billed per
   *  character; characters ≈ duration × speaking rate). Exact for runs that stored frames. */
  vo_seconds: number | null
  /** The Nemotron BRAIN this run planned on (runs.brain column): 'ultra-paid' = 550B
   *  (`nvidia/nemotron-3-ultra-550b-a55b`, the pricier flagship used on the Hermes path),
   *  'super-free'/'super-paid' = 120B. Drives the per-run token-COGS rate (550B costs more). */
  brain: string | null
  /** REAL OpenRouter spend (USD) for this run's PLANNER call, read from
   *  runs.selection.planner_usage.cost — the exact prompt+completion cost OpenRouter billed
   *  (e.g. 0.0047 for a 550B plan). null when not recorded (older/free runs). The page uses
   *  this ACTUAL when present; otherwise it estimates from the brain + storyboard size. */
  planner_cost_usd: number | null
}

export interface AnalyticsPayload {
  authorized: boolean
  rows: AnalyticsRunRow[]
}

export async function readAnalytics(
  accessToken: string | null | undefined,
): Promise<AnalyticsPayload> {
  // 1) Verify the caller server-side (token → authoritative identity).
  const me = await verifyUser(accessToken)
  // 2) Owner-only. A non-owner never reaches the admin query → no data is exposed.
  if (!me || (me.email || '').toLowerCase() !== OWNER_EMAIL) {
    return { authorized: false, rows: [] }
  }

  const db = adminClient()
  // Whole-business read: all runs, newest first. We only select the economics columns
  // (no plan/props_edited blobs) so the payload stays light. `props` → producer + duration;
  // `brain` → the per-run token-COGS rate; `selection` → the REAL planner OpenRouter spend.
  const { data, error } = await db.database
    .from('runs')
    .select(
      'id, created_at, brand, company_url, status, price_cents, cogs_cents, final_url, brain, props, selection',
    )
    .order('created_at', { ascending: false })
  if (error) return { authorized: true, rows: [] }

  const rows: AnalyticsRunRow[] = (data ?? []).map((r) => {
    const row = r as Record<string, unknown>
    const props = (row.props && typeof row.props === 'object' ? row.props : {}) as Record<
      string,
      unknown
    >
    let producer: string | null = null
    const p = props.producer
    if (typeof p === 'string' && p) producer = p

    // Real video duration → drives the VO-cost estimate. Stored as total_frames / fps
    // on produced runs; null when either is missing (the page then uses a default).
    const fps = typeof props.fps === 'number' ? props.fps : null
    const totalFrames = typeof props.total_frames === 'number' ? props.total_frames : null
    const voSeconds = fps && fps > 0 && totalFrames && totalFrames > 0 ? totalFrames / fps : null

    // REAL planner token spend (USD). The pipeline stamps the exact OpenRouter cost at
    // runs.selection.planner_usage.cost (older runs also mirror it under props.selection).
    // We surface it as an ACTUAL so the page's token-COGS is real, not estimated, when present.
    const selection = (row.selection && typeof row.selection === 'object'
      ? row.selection
      : props.selection && typeof props.selection === 'object'
        ? props.selection
        : {}) as Record<string, unknown>
    const usage = (selection.planner_usage && typeof selection.planner_usage === 'object'
      ? selection.planner_usage
      : {}) as Record<string, unknown>
    const plannerCostUsd = typeof usage.cost === 'number' && usage.cost >= 0 ? usage.cost : null

    return {
      id: String(row.id),
      created_at: String(row.created_at),
      brand: (row.brand as string | null) ?? null,
      company_url: String(row.company_url ?? ''),
      status: String(row.status ?? ''),
      price_cents: (row.price_cents as number | null) ?? null,
      cogs_cents: (row.cogs_cents as number | null) ?? null,
      final_url: (row.final_url as string | null) ?? null,
      producer,
      vo_seconds: voSeconds,
      brain: typeof row.brain === 'string' && row.brain ? row.brain : null,
      planner_cost_usd: plannerCostUsd,
    }
  })
  return { authorized: true, rows }
}


// ---- Walkrec beta: the agent activity stream + director chat ----------------

export type AgentEvent = {
  seq: number; ts: number; kind: string; title: string; detail: string;
  artifact_url: string
}

async function ownedRun(runKey: string, accessToken: string) {
  const me = await verifyUser(accessToken)
  if (!me) return null
  const db = adminClient()
  const { data } = await db.database
    .from('runs').select('*').eq('run_key', runKey).limit(1)
  const run = (data && data[0]) as Run | undefined
  if (!run || (run as { user_id?: string }).user_id !== me.id) return null
  return { me, db, run: run as Run & { id: string; film_mode?: string } }
}

/** The walkrec workspace poll: run row + agent events after `after`.
 *  artifact_url is rewritten to the same-origin proxy so private storage
 *  objects render in the browser. */
export async function getAgentRun(
  runKey: string, after: number, accessToken: string,
  refreshSeqs?: number[],
) {
  const ctx = await ownedRun(runKey, accessToken)
  if (!ctx) return { error: 'not-found' as const }
  const { db, run } = ctx
  const { data: evts } = await db.database
    .from('agent_events')
    .select('seq,ts,kind,title,detail,artifact_url')
    .eq('run_id', run.id)
    .gt('seq', after)
    .order('seq', { ascending: true })
    .limit(400)
  const proxied = (rows: AgentEvent[] | null | undefined) =>
    (rows || []).map((e) => ({
      ...e,
      artifact_url: e.artifact_url
        ? `/api/agent-artifact?u=${encodeURIComponent(e.artifact_url)}`
        : '',
    }))
  const events = proxied(evts as AgentEvent[])
  // ARTIFACTS ATTACH BY PATCH after their row lands (insert-first sink), so
  // an incremental seq cursor never sees them. The client sends the seqs it
  // holds with empty artifacts; rows whose artifact has since attached come
  // back for upsert.
  let refreshed: AgentEvent[] = []
  if (refreshSeqs && refreshSeqs.length) {
    const { data: re } = await db.database
      .from('agent_events')
      .select('seq,ts,kind,title,detail,artifact_url')
      .eq('run_id', run.id)
      .in('seq', refreshSeqs.slice(0, 40))
      .neq('artifact_url', '')
    refreshed = proxied(re as AgentEvent[])
  }
  const liveUrl = `/api/agent-artifact?u=${encodeURIComponent(
    `${(process.env.INSFORGE_URL || process.env.NEXT_PUBLIC_INSFORGE_URL || '').replace(/\/$/, '')}`
    + `/api/storage/buckets/${process.env.INSFORGE_BUCKET || 'walk-videos'}`
    + `/objects/agent/${run.id}/live.jpg`)}`
  // Queue truth (F8): before any event arrives, the only honest thing the
  // workspace can say is where this build sits in line. One studio worker
  // builds one film at a time, so ahead = queued build jobs older than ours
  // + any currently-claimed build.
  let queueAhead: number | null = null
  if (after < 0 && events.length === 0) {
    const { data: ourJob } = await db.database
      .from('jobs').select('id, created_at, status')
      .eq('run_id', run.id).eq('type', 'build')
      .order('created_at', { ascending: true }).limit(1)
    const mine = ourJob && (ourJob[0] as
      { created_at: string; status: string } | undefined)
    if (mine && (mine.status === 'queued' || mine.status === 'claimed')) {
      const { data: others } = await db.database
        .from('jobs').select('id, status, created_at')
        .eq('type', 'build').in('status', ['queued', 'claimed'])
      const rows = (others as
        { id: string; status: string; created_at: string }[]) || []
      queueAhead = mine.status === 'claimed' ? 0 : rows.filter((j) =>
        j.status === 'claimed'
        || (j.status === 'queued' && j.created_at < mine.created_at)).length
    }
  }
  // The delivery receipt is always current on the run row — the done-state
  // film falls back to it when assemble.film's artifact hasn't attached yet.
  const filmUrl = proxyPlayableUrl(
    (run as { final_url?: string | null }).final_url) || ''
  return { run, events, refreshed, runId: run.id, liveUrl, queueAhead, filmUrl }
}

/** One director chat turn: log the user message as an agent event and enqueue
 *  a director job — the worker's python director replies via chat.director
 *  events (ONE director implementation, no TS drift). */
export async function sendDirectorMessage(
  runKey: string, message: string, accessToken: string,
) {
  // Distinguish "your session died" from "this run isn't yours" — the
  // generic failure told Dennis to retry something that could never work.
  const me = await verifyUser(accessToken)
  if (!me) {
    return {
      error: 'auth' as const,
      message: 'Your session expired — sign in again and your note will send.',
    }
  }
  const ctx = await ownedRun(runKey, accessToken)
  if (!ctx) return { error: 'not-found' as const }
  const { db, run } = ctx
  const text = String(message || '').slice(0, 2000)
  if (!text.trim()) return { error: 'empty' as const }
  // An edit that lands re-renders the film, so it must fit inside the
  // allowance. Checked before enqueueing; the worker charges only if the
  // gates actually apply the change.
  if ((ctx.me.email || '').toLowerCase() !== OWNER_EMAIL) {
    const bal = await creditBalances(db, ctx.me.id)
    if (bal.dailyUsed + EDIT_CREDIT_COST > DAILY_CREDIT_CAP
        || bal.lifetimeUsed + EDIT_CREDIT_COST > LIFETIME_CREDIT_CAP) {
      return {
        error: 'no-credits' as const,
        message: `An edit costs ${EDIT_CREDIT_COST} credits and you're out for now — credits refresh through the day.`,
      }
    }
  }
  const { data: maxRow } = await db.database
    .from('agent_events').select('seq').eq('run_id', run.id)
    .order('seq', { ascending: false }).limit(1)
  const seq = ((maxRow && maxRow[0] && (maxRow[0] as { seq: number }).seq) || 0) + 1
  await withRetry(() => db.database.from('agent_events').insert([{
    run_id: run.id, seq, ts: Date.now() / 1000, kind: 'chat.user',
    title: text, detail: '', artifact_url: '',
  }]))
  const { error: jobErr } = await withRetry(() =>
    db.database.from('jobs').insert([{
      run_id: run.id, status: 'queued', type: 'director',
      params: { run_key: runKey, message: text, look: 'walkrec' },
    }]))
  if (jobErr) return { error: 'enqueue-failed' as const }
  return { ok: true as const, seq }
}

// ─────────────────────────────── Feedback ───────────────────────────────
// DURABILITY BEFORE DELIVERY. A note is STORED first and notified second, so
// what someone took the trouble to write survives a mail provider that is
// rate-limited, misconfigured, or simply not wired yet. Nothing about sending
// mail is a precondition for accepting it — `notified` on the row records
// whether it actually reached an inbox, so a later digest can sweep up
// everything that didn't rather than re-sending blindly.
const FEEDBACK_MAX = 5000

/** Best-effort notification. Returns whether an inbox actually received it.
 *  Never throws and never blocks acceptance — a false here means the note is
 *  safely in the table waiting to be swept, not that it was lost. */
async function notifyFeedback(body: string): Promise<boolean> {
  const resend = process.env.RESEND_API_KEY || ''
  const hook = process.env.FEEDBACK_WEBHOOK_URL || ''
  try {
    if (resend) {
      const r = await fetch('https://api.resend.com/emails', {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${resend}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          from: process.env.FEEDBACK_FROM || 'Filmo <onboarding@resend.dev>',
          to: [OWNER_EMAIL],
          subject: 'Filmo feedback',
          text: body,
        }),
      })
      return r.ok
    }
    if (hook) {
      const r = await fetch(hook, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ to: OWNER_EMAIL, subject: 'Filmo feedback', text: body }),
      })
      return r.ok
    }
  } catch { /* the row is already safe; delivery is the only thing that failed */ }
  return false
}

/** Take a note from inside the studio. Signed-out senders are accepted — we
 *  would rather hear it anonymously than refuse it. */
export async function sendFeedback(input: {
  message: string
  accessToken?: string | null
  /** Where they were standing: a run id, a route. Makes a vague note actionable. */
  context?: string
}): Promise<{ ok: true; notified: boolean } | { ok: false; message: string }> {
  const message = (input.message || '').trim()
  if (!message) {
    return { ok: false as const, message: 'Write a line first and I’ll pass it on.' }
  }
  if (message.length > FEEDBACK_MAX) {
    return {
      ok: false as const,
      message: `That’s longer than ${FEEDBACK_MAX.toLocaleString()} characters — trim it and send again.`,
    }
  }
  const me = input.accessToken ? await verifyUser(input.accessToken) : null
  const db = adminClient()

  // 1) STORE. If this fails there is nothing to be optimistic about, so it is
  //    the only step that can reject the note.
  const { data, error } = await withRetry(() =>
    db.database.from('feedback').insert([{
      user_id: me?.id ?? null,
      email: me?.email ?? '',
      message,
      context: (input.context || '').slice(0, 300),
    }]).select('id'),
  )
  if (error) {
    return {
      ok: false as const,
      message: 'That didn’t save — try again in a moment.',
    }
  }

  // 2) NOTIFY. Best-effort, and its failure is invisible to the sender: from
  //    their side the note landed, because it did.
  const notified = await notifyFeedback(
    [
      `From: ${me?.email || 'anonymous'}`,
      input.context ? `Context: ${input.context}` : '',
      '',
      message,
    ].filter(Boolean).join('\n'),
  )
  const row = (data as { id: string }[] | null)?.[0]
  if (notified && row?.id) {
    await db.database.from('feedback').update({ notified: true }).eq('id', row.id)
  }
  return { ok: true as const, notified }
}
