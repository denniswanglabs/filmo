'use server'
import { adminClient, verifyUser } from '../lib/insforge'

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
  // Opt-in HUMAN payment: 'auto' (default) lets the worker auto-resolve payment
  // (PRODUCER_SIMULATE_PAID); 'human' creates a REAL Stripe TEST checkout the user
  // must pay (test card 4242) before the build proceeds. Only the payment becomes
  // real — the render stays $0 mock.
  payMode?: 'auto' | 'human'
}) {
  // Identity comes from the verified token, NEVER from the client. The owner of the
  // build is whoever the token belongs to.
  const me = await verifyUser(input.accessToken)
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

  // Beta cap: every account EXCEPT the owner gets a TOTAL of N videos (lifetime, not
  // per-day) while Filmo is in beta — this protects the Nemotron/ElevenLabs budget from a
  // stranger draining it. Identity is the server-verified token (never the client) and the
  // admin count bypasses RLS, so it can't be gamed. The owner is exempt. We RETURN a
  // structured { limit } (not throw) so the UI shows the friendly message inline rather than
  // the opaque "Server Components render" server-action error.
  const BETA_VIDEO_LIMIT = 3
  if ((me.email || '').toLowerCase() !== OWNER_EMAIL) {
    const { data: mine } = await db.database
      .from('runs')
      .select('id')
      .eq('user_id', me.id)
    if (mine && mine.length >= BETA_VIDEO_LIMIT) {
      return {
        limit: true as const,
        message: `You've used all ${BETA_VIDEO_LIMIT} of your beta videos. Filmo is in beta — each account gets ${BETA_VIDEO_LIMIT} videos. Thanks for trying it!`,
      }
    }
  }

  // Whitelist every client-supplied param (never forward raw — the worker trusts these).
  // Single coherent tier: every video is produced the same way. `quality` is pinned to
  // 'standard' (kept only to satisfy the existing runs/jobs schema + worker param contract).
  const quality = 'standard' as const
  const brain = input.brain && ALLOWED_BRAINS.has(input.brain) ? input.brain : 'super-free'
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
      }])
      .select(),
  )
  if (runErr) throw new Error('runs.insert: ' + JSON.stringify(runErr))
  const runId = runs![0].id

  const params = { company_url: rawUrl, goal, emphasis: input.emphasis || '', quality, brain, mode, pay_mode: payMode, run_key: runKey, duration: 30 }
  const { error: jobErr } = await withRetry(() =>
    db.database.from('jobs').insert([{ run_id: runId, status: 'queued', params }]),
  )
  if (jobErr) throw new Error('jobs.insert: ' + JSON.stringify(jobErr))

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
