'use server'
import { adminClient, verifyUser } from '../lib/insforge'
import { isDelivered } from '../lib/types'
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
}): Promise<
  | { runId: string; runKey: string }
  | { limit: true; message: string }
  | { unavailable: true; message: string }
  | { authError: true }
> {
  // ── THE ACTION BOUNDARY ─────────────────────────────────────────────────────
  // Every failure this function can SEE is classified into ONE of four honest
  // shapes, and none of them is an opaque throw. The reason is the build-start
  // invariant, stated in components/StartFilm.tsx and enforced here at its source:
  // a signed-in reader is NEVER told to sign in because the backend blinked. So the
  // only failure that yields the sign-in door is the auth VERDICT (verifyUser
  // returns null — a real 401/403); every OTHER failure — a timeout, an InsForge
  // brownout, a retried-then-failed insert, an unexpected error — is caught by the
  // boundary at the bottom and returned as { unavailable }, retryable, never auth.
  // (A thrown server action is also the production "Server Components render …
  // digest" 500 on the client, so returning instead of throwing hands the caller a
  // clean, legible answer rather than an opaque error it has to guess at.)
  try {
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
    // A NULL from verifyUser is a VERDICT, not a blip: it returns null ONLY on a
    // genuine 401/403 (or an absent/garbage token) and THROWS on an unreachable
    // auth service (see lib/insforge — that throw is caught below as { unavailable }).
    // So !me is the one failure that has truly earned the sign-in door — return it
    // as a distinct, structured refusal the client gates on WITHOUT reading an
    // opaque throw, and which is unmistakably NOT the transient-blip path.
    if (!me) return { authError: true as const }

    // Validate the URL is a real http(s) address (defense-in-depth; the worker also
    // SSRF-guards the fetch, but reject obvious garbage before we enqueue + spend).
    const rawUrl = (input.url || '').trim()
    if (!/^https?:\/\/[^\s]+\.[^\s]+/i.test(rawUrl)) throw new Error('Enter a valid website URL.')

    const db = adminClient()

    // ── THE TWO GATES RUN CONCURRENTLY ──────────────────────────────────────────
    // Nothing stands between the caller and a run id except identity and these two
    // gates, and every one of them is a round trip to InsForge in Singapore
    // (~310ms warm, ~1.4s on a cold connection — measured). They used to run one
    // after the other for no reason other than the order they were written in:
    // the rate-limit read and the credit read take the same already-verified
    // user id, touch different tables, and neither one's answer changes the
    // other's question. Run together they cost ONE trip instead of two, which is
    // a third off everything that happens before the run row exists.
    //
    // They must both still finish BEFORE the insert. A gate evaluated after the
    // row is written is not a gate — it is a report on a build that already
    // started — so no amount of "move the slow part later" applies to these two.
    // (The reason this is only a third and not the whole wait, and why the UI
    // therefore cannot be allowed to wait on it at all, is written up in
    // components/StartFilm.tsx.)
    const windowStart = new Date(Date.now() - 10 * 60_000).toISOString()
    const isOwner = (me.email || '').toLowerCase() === OWNER_EMAIL
    const [recentRes, bal] = await Promise.all([
      db.database
        .from('runs')
        .select('id')
        .eq('user_id', me.id)
        .gte('created_at', windowStart),
      // The owner is exempt from the credit cap, so their balance is never read.
      isOwner ? Promise.resolve(null) : creditBalances(db, me.id),
    ])

    // Rate limit: cap builds per user per window so a scripted loop can't drain the
    // Nemotron/render budget. Time-based + status-agnostic (stuck rows never wedge it).
    // A throttle is not a broken session, so it RETURNS a structured { limit } (the
    // same channel as the credit caps) rather than throwing: the client says the
    // "give it a minute" line inline and — critically — never raises a sign-in gate
    // over it, which the opaque throw used to make it do.
    const recent = recentRes.data as { id: string }[] | null
    if (recent && recent.length >= 10) {
      return {
        limit: true as const,
        message: 'Too many builds in a short window — give it a minute and try again.',
      }
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
    if (bal) {
      // CREDITS (beta): costs and caps are the constants above — never restate
      // them here, or the comment rots the moment they move. Balance is the SUM
      // of an append-only ledger (spends negative; failed builds refunded by the
      // worker), so failed attempts do not consume the allowance. Server-side,
      // admin client — can't be gamed. `bal` is null for exactly one reason: the
      // owner is exempt, so the read above was never issued.
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

    // ── THE WRITE ORDER IS AN INVARIANT: runs → jobs → charge, all awaited ───────
    // Both enqueue inserts retry on a transient InsForge error so a one-off blip
    // doesn't surface as a failed build (see withRetry). A retried-then-failed
    // insert throws, and that throw is the boundary's job: the caller gets
    // { unavailable } (retryable) and, because the run row is written FIRST and the
    // charge LAST, a failure here means nothing the reader would be billed for.
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
    //
    // STAYS AFTER THE JOBS INSERT, AND STAYS AWAITED. Both are tempting to move:
    // running it concurrently with the enqueue would save a round trip, and
    // firing it off unawaited would save one more. Neither is safe. The order is
    // an invariant — a jobs.insert failure throws above, so a reader is never
    // charged for a build that was never enqueued — and a serverless function may
    // be killed the moment it responds, so an unawaited write is a write that
    // sometimes does not happen. Charging "sometimes" is the same as not charging.
    // The wait these two cost is paid behind the arrival cover, not in front of
    // the reader (components/StartFilm.tsx).
    if (!isOwner) {
      // The charge is the DATA BEHIND THE CAP: creditBalances sums this table, so a
      // charge that silently fails makes the daily/lifetime caps fiction for that
      // build. The build itself must still proceed (the run is already enqueued —
      // failing the caller here would charge them a confusing error instead of a
      // film), but the failure can never be invisible: log it with enough identity
      // to reconcile the ledger by hand. It does NOT throw — the build is real, so
      // it must not be reported to the reader as unavailable.
      const { error: chargeErr } = await withRetry(() => db.database.from('credit_ledger').insert([{
        user_id: me.id, delta: -VIDEO_CREDIT_COST, reason: 'video', run_id: runId,
      }]))
      if (chargeErr) {
        console.error(
          `[credits] video charge FAILED for run ${runId} (user ${me.id}): ` +
          `${JSON.stringify(chargeErr)} — ledger is now missing a -${VIDEO_CREDIT_COST} spend row`,
        )
      }
    }

    return { runId, runKey }
  } catch (err) {
    // THE BOUNDARY. Everything the function could SEE that is not the auth verdict
    // or a cap above funnels here: verifyUser throwing on an unreachable auth
    // service, a retried-then-failed runs/jobs insert, an unexpected error. NONE of
    // them becomes an auth signal — that is the whole point. They become one
    // structured { unavailable }: retryable, and (because the run row is the LAST
    // thing gated, written only after identity and both caps) genuinely "nothing was
    // started". The real reason is logged here for the operator; the client owns the
    // one honest sentence it shows the reader (components/StartFilm.tsx).
    console.error(
      '[createBuild] unavailable —',
      err instanceof Error ? err.message : String(err),
    )
    return {
      unavailable: true as const,
      message: 'The build service is briefly unavailable — nothing was started.',
    }
  }
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
  /** runs.film_mode: 'walkrec' ships music-only BY DESIGN (no ElevenLabs VO ever ran),
   *  so the page must not cost a voiceover onto it. null/'classic' = the VO pipeline. */
  film_mode: string | null
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
      'id, created_at, brand, company_url, status, price_cents, cogs_cents, final_url, brain, props, selection, film_mode',
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
      film_mode: typeof row.film_mode === 'string' && row.film_mode ? row.film_mode : null,
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
  const web3 = process.env.FEEDBACK_ACCESS_KEY || ''
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
    // WEB3FORMS. A form-relay service: you give it an email, it gives you an
    // access key, and it mails you whatever you POST. No domain to verify, no
    // DNS, and the access key is designed to be public — it can only ever send
    // to the address it was issued for, so it is not a credential in the way an
    // API key is. That makes it the cheapest honest path to a real inbox.
    //
    // ⚠ IT RETURNS HTTP 200 ON FAILURE. A rejected submission is
    // `200 {"success": false, "message": "..."}`, so trusting `r.ok` here would
    // mark the row notified and swear an email went out that never did — the
    // exact class of lie we spent the day removing. Parse the body.
    if (web3) {
      const r = await fetch('https://api.web3forms.com/submit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify({
          access_key: web3,
          subject: 'Filmo feedback',
          from_name: 'Filmo',
          message: body,
        }),
      })
      if (!r.ok) return false
      const out = await r.json().catch(() => null) as { success?: boolean } | null
      return out?.success === true
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
  /** THE BROWSER ALREADY DELIVERED THIS. Web3Forms — the relay Dennis chose —
   *  refuses server-side calls on its free tier ("Use our API in client side…
   *  Pro plan is required"), and its access key is public BY DESIGN for exactly
   *  that reason: it can only ever mail the address it was issued for. So the
   *  browser posts the note and reports back here, and this only records what
   *  actually happened. It is a claim about the past, never a request — the
   *  server never marks a row notified on the strength of hope. */
  clientNotified?: boolean
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
  const notified = input.clientNotified === true
    ? true
    : await notifyFeedback(
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

// ═══════════════════════ OVERVIEW — the signed-in home ═══════════════════════
//
// THE GOVERNING RULE OF EVERYTHING BELOW: every number on the strip and every
// claim on a card is a COUNT OF ROWS THAT EXIST. Nothing here is estimated,
// extrapolated, or inferred from a live look at a customer's site.
//
// That rule is not fastidiousness. A card that says "your pricing page changed"
// without having checked is the same defect as a reviewer that passes a film it
// never watched — it just wears a nicer coat. So: if a fact cannot be derived
// from a row we already hold, the card that would have carried it is not
// rendered, and the strip drops the half of a stat it cannot measure rather
// than filling it in. Fewer, true things.
//
// Two reads, both owner-scoped through `verifyUser` like every other action in
// this file. The admin client bypasses RLS, so `.eq('user_id', me.id)` IS the
// security boundary (same rule as listMyRuns / listAssets):
//   getOverviewStats → the thin strip along the top
//   getSuggestions   → the "For you" cards
//
// Credits are deliberately absent from both: they live in the account circle
// (AccountMenu → getCredits), and a number that means "what you have left to
// spend" does not belong in a row of numbers that mean "what you have made".

// How far back the Overview looks. Both reads are bounded so a heavy account
// can never turn the home page into a full-table scan. Today the largest
// account holds ~100 runs, so this window is the entire history for everyone;
// if that stops being true the stats become a floor rather than a total, which
// is why the window is stated here rather than buried in a query.
const OVERVIEW_RUN_LIMIT = 400
// `agent_events` are fetched in batches of run ids, because a `.in()` carrying
// 400 uuids is a query string nobody should build.
//
// ★ MEASURED, NOT CHOSEN BY FEEL. Each id costs ~43 bytes once quoted and
// URL-encoded, and the gateway in front of InsForge drops a request line past
// ~4KB. It does not drop it loudly: the SDK hands back `{ data: null }`, which
// reads exactly like "this account has no events". Raising this to 100 (≈4.3KB)
// was tried and turned a real account's 66 pages read and 228 assets into
// zeroes with no error anywhere — a strip full of confident, wrong numbers.
// 50 ids ≈ 2.2KB, half the ceiling. Do not raise it without measuring the
// encoded length, and read the throw in overviewEvents before you do.
const OVERVIEW_ID_BATCH = 50
const OVERVIEW_EVENTS_PER_BATCH = 1500

interface OverviewRunRow {
  id: string
  brand: string | null
  company_url: string | null
  status: string
  film_mode: string | null
  created_at: string
  final_url: string | null
  /** `props.total_frames` / `props.fps`, pulled as jsonb sub-paths so the whole
   *  (large) props blob never crosses the wire. Null when the run stored no
   *  frame count — see `measuredSeconds`. */
  total_frames: number | null
  fps: number | null
}

interface OverviewEventRow {
  run_id: string
  seq: number
  kind: string
  title: string
  detail: string
  artifact_url: string
}

/** Every run this user owns, newest first. `.eq('user_id')` is the boundary.
 *  Throws on a failed read for the same reason overviewEvents does: an account
 *  whose runs could not be read is not an account with no runs, and only one of
 *  those two is safe to render. An EMPTY array is a real answer and passes
 *  through — that is a brand-new signup, and the Overview has a page for it. */
async function overviewRuns(
  db: ReturnType<typeof adminClient>,
  userId: string,
): Promise<OverviewRunRow[]> {
  const { data, error } = await db.database
    .from('runs')
    .select(
      'id, brand, company_url, status, film_mode, created_at, final_url,'
      + ' total_frames:props->total_frames, fps:props->fps',
    )
    .eq('user_id', userId)
    .order('created_at', { ascending: false })
    .limit(OVERVIEW_RUN_LIMIT)
  if (error || data == null) {
    throw new Error('overview: runs read failed — refusing to report an empty account')
  }
  // The SDK types a select carrying an ALIASED jsonb sub-path
  // (`total_frames:props->total_frames`) as GenericStringError[], because its
  // generated row types only know real columns. The rows are real; the type is
  // the one thing that isn't, so it goes through `unknown` and every field is
  // narrowed by hand below.
  const rows = (data as unknown as Record<string, unknown>[]) ?? []
  const num = (v: unknown): number | null =>
    typeof v === 'number' && isFinite(v) ? v : null
  return rows.map((r) => ({
    id: String(r.id),
    brand: (r.brand as string | null) ?? null,
    company_url: (r.company_url as string | null) ?? null,
    status: String(r.status ?? ''),
    film_mode: (r.film_mode as string | null) ?? null,
    created_at: String(r.created_at ?? ''),
    final_url: (r.final_url as string | null) ?? null,
    total_frames: num(r.total_frames),
    fps: num(r.fps),
  }))
}

/** The named event kinds for these runs, in seq order, batched by run id.
 *
 *  ── A FAILED READ IS NOT AN EMPTY ONE ──────────────────────────────────────
 *  THROWS rather than returning what it managed to collect. Every caller below
 *  turns these rows into a number or a claim, and both of those degrade the
 *  same silent way when a batch quietly comes back empty: the strip prints
 *  zeroes it presents as counts, and the cards announce that pages were never
 *  filmed because the evidence that they were is missing. A read that did not
 *  happen must be indistinguishable from a read that failed — which means it
 *  has to stop here. The Overview catches this and offers a retry; that is the
 *  honest answer, and an unreadable page is a better outcome than a confident
 *  wrong one. */
async function overviewEvents(
  db: ReturnType<typeof adminClient>,
  runIds: string[],
  kinds: string[],
): Promise<OverviewEventRow[]> {
  const out: OverviewEventRow[] = []
  for (let i = 0; i < runIds.length; i += OVERVIEW_ID_BATCH) {
    const batch = runIds.slice(i, i + OVERVIEW_ID_BATCH)
    if (!batch.length) continue
    const { data, error } = await db.database
      .from('agent_events')
      .select('run_id, seq, kind, title, detail, artifact_url')
      .in('run_id', batch)
      .in('kind', kinds)
      .order('seq', { ascending: true })
      .limit(OVERVIEW_EVENTS_PER_BATCH)
    // `data == null` with no error is the shape an over-long request line comes
    // back as (see OVERVIEW_ID_BATCH), so absence is checked as well as error.
    if (error || data == null) {
      throw new Error('overview: agent_events read failed — refusing to report partial counts')
    }
    for (const e of (data as OverviewEventRow[])) out.push(e)
  }
  return out
}

/** Group events by run, each list ordered by seq (the order the studio wrote them). */
function eventsByRun(events: OverviewEventRow[]): Map<string, OverviewEventRow[]> {
  const m = new Map<string, OverviewEventRow[]>()
  for (const e of events) {
    const list = m.get(e.run_id)
    if (list) list.push(e)
    else m.set(e.run_id, [e])
  }
  for (const list of m.values()) list.sort((a, b) => a.seq - b.seq)
  return m
}

// ── MEASURED, NEVER ESTIMATED ───────────────────────────────────────────────
// A film's length is stored in exactly two places, and both are written FROM
// THE RENDERED ARTIFACT rather than from the plan:
//   walkrec → the run's LAST `assemble.film` event, whose detail the pipeline
//             stamps off the finished file ("53.1s"). Last, not first: a
//             director re-cut emits a second one, and the newest is the film
//             that actually shipped.
//   classic → props.total_frames / props.fps, the frames actually rendered.
// There is no `duration` column, and no third source. A delivered run carrying
// neither is UNMEASURED: it contributes zero seconds and is excluded from
// `filmSecondsMeasuredOf`, so the strip can say how many films it measured
// instead of quietly under-reporting a total it presents as complete.
const FILM_SECONDS_RE = /^\s*([0-9]+(?:\.[0-9]+)?)\s*s\s*$/

function measuredSeconds(run: OverviewRunRow, events: OverviewEventRow[]): number | null {
  for (let i = events.length - 1; i >= 0; i--) {
    if (events[i].kind !== 'assemble.film') continue
    const m = FILM_SECONDS_RE.exec(events[i].detail || '')
    if (m) return parseFloat(m[1])
    break
  }
  const { total_frames: frames, fps } = run
  if (frames && fps && fps > 0 && frames > 0) return frames / fps
  return null
}

export interface OverviewStats {
  /** Runs that shipped a film (isDelivered — the app's shared definition). */
  filmos: number
  /** Sum of the MEASURED lengths of those films, in seconds. */
  filmSeconds: number
  /** How many of `filmos` had a stored length. When it is below `filmos` the
   *  strip says so, because "51 minutes" over 88 films of which 86 were
   *  measured is a different sentence from "51 minutes". */
  filmSecondsMeasuredOf: number
  /** Distinct pages Filmo read, counted once per (run, page): the same page
   *  read twice inside one run is one page, read twice across two filmos is
   *  two. Only the agent pipeline records reads, so a library of classic-only
   *  films honestly reports zero. */
  pagesRead: number
  /** Recordings KEPT (`film.shot`) — the library's own definition of a
   *  recording (ASSET_OF_KIND maps film.shot → 'recording'), so this number and
   *  the Recordings filter on /assets can never disagree. */
  recordings: number
  /** Everything in the assets library, counted the way the library counts it. */
  assets: number
}

export type OverviewStatsResult = { authError: true } | { stats: OverviewStats }

// The assets library shows the 40 most recent runs (listAssets), so the strip
// counts exactly that window. A strip reading 250 over a library holding 96
// would be a number the user has no way to check — and a number nobody can
// check is indistinguishable from one that is wrong.
const ASSET_RUN_WINDOW = 40

export async function getOverviewStats(
  accessToken: string | null | undefined,
): Promise<OverviewStatsResult> {
  const me = await verifyUser(accessToken)
  if (!me) return { authError: true }
  const db = adminClient()
  const runs = await overviewRuns(db, me.id)
  const empty: OverviewStats = {
    filmos: 0, filmSeconds: 0, filmSecondsMeasuredOf: 0,
    pagesRead: 0, recordings: 0, assets: 0,
  }
  if (!runs.length) return { stats: empty }

  // ASSET_OF_KIND is the library's definition of what counts as an asset;
  // re-deriving it here is how the two surfaces would drift apart.
  const assetKinds = Object.keys(ASSET_OF_KIND)
  const kinds = Array.from(new Set([...assetKinds, 'assemble.film']))
  const events = await overviewEvents(db, runs.map((r) => r.id), kinds)
  const byRun = eventsByRun(events)

  const assetWindow = new Set(runs.slice(0, ASSET_RUN_WINDOW).map((r) => r.id))
  const pages = new Set<string>()
  let filmos = 0
  let filmSeconds = 0
  let measured = 0
  let recordings = 0
  // One film per run that has a delivery receipt — listAssets' `film` row.
  let assets = runs.filter((r) => assetWindow.has(r.id) && r.final_url).length

  for (const r of runs) {
    const es = byRun.get(r.id) ?? []
    if (isDelivered(r.status)) {
      filmos++
      const secs = measuredSeconds(r, es)
      if (secs != null) { filmSeconds += secs; measured++ }
    }
    for (const e of es) {
      if (e.kind === 'read.page') pages.add(`${r.id}\n${e.title}`)
      if (e.kind === 'film.shot') recordings++
      // ASSET_OF_KIND — not merely "has an artifact". `assemble.film` is
      // fetched here for the length above and carries an artifact of its own,
      // and counting it would put 17 things on the strip that the library does
      // not hold. The kind map is the definition; membership in it is the test.
      if (assetWindow.has(r.id) && e.artifact_url && ASSET_OF_KIND[e.kind]) assets++
    }
  }

  return {
    stats: {
      filmos,
      filmSeconds: Math.round(filmSeconds),
      filmSecondsMeasuredOf: measured,
      pagesRead: pages.size,
      recordings,
      assets,
    },
  }
}

// ─────────────────────────── "For you" — the cards ───────────────────────────
// Five card kinds, each derived from rows this account owns. At most one card
// per kind (the strongest instance) and never two cards proposing the same
// action, so the column reads as five different reasons rather than the same
// site five times. Everything a card asserts is in the query above it.

export type SuggestionAction =
  | { type: 'build'; url: string; label: string }
  | { type: 'open'; runId: string; label: string }

export type SuggestionKind =
  | 'in-flight'
  | 'unfilmed-page'
  | 'no-notes'
  | 'stranded-failure'
  | 'most-filmed'

export interface Suggestion {
  id: string
  kind: SuggestionKind
  title: string
  /** One sentence of plain explanation. Never carries a date — see `at`. */
  detail: string
  /** The rows it came from, in the user's words ("5 pages read, 2 kept"). */
  evidence: string
  /** ISO timestamp of the row the card is about, or '' when it isn't about one
   *  moment. Dates are NOT baked into the copy: a date formatted on the server
   *  is the server's day, not the reader's, and a card that is off by one is a
   *  card that is wrong. The client formats this in the reader's own zone. */
  at: string
  action: SuggestionAction
}

export type SuggestionsResult = { authError: true } | { suggestions: Suggestion[] }

const SUGGESTION_CAP = 5

/** Bare host, lowercased, `www.` dropped — the identity of a site across runs. */
function siteHost(url: string | null | undefined): string {
  const raw = (url || '').trim()
  if (!raw) return ''
  try {
    return new URL(/^https?:\/\//i.test(raw) ? raw : `https://${raw}`)
      .hostname.toLowerCase().replace(/^www\./, '')
  } catch {
    return ''
  }
}

// A site worth proposing has to be a site. The runs table also holds the
// pipeline's own SSRF self-tests and reserved addresses (169.254.169.254,
// *.example) — real rows, but proposing "film 169.254.169.254 again" is how a
// grounded card still ends up looking stupid.
function isProposableHost(host: string): boolean {
  if (!host || !host.includes('.')) return false
  if (/^[0-9.]+$/.test(host)) return false // bare IPv4
  if (/(^|\.)(example|invalid|test|local|localhost)$/.test(host)) return false
  return true
}

/** Scheme+host lowercased, trailing slash dropped — so two spellings of one
 *  page do not read as two pages. */
function normalizePageUrl(raw: string): string {
  const t = (raw || '').trim()
  if (!t) return ''
  try {
    const u = new URL(t)
    u.hash = ''
    const path = u.pathname.replace(/\/+$/, '')
    return `${u.protocol}//${u.host.toLowerCase()}${path}${u.search}`
  } catch {
    return ''
  }
}

/** The page a `read.page` event is about. Titles are either an absolute URL
 *  ("Read https://insforge.dev") or a site-relative path ("Read /pricing"). */
function readPageUrl(title: string, companyUrl: string | null): string {
  const m = (title || '').replace(/^Read\s+/i, '').trim()
  if (!m) return ''
  if (/^https?:\/\//i.test(m)) return normalizePageUrl(m)
  if (!companyUrl) return ''
  try {
    return normalizePageUrl(new URL(m, companyUrl).toString())
  } catch {
    return ''
  }
}

/** The page a `film.recording` event is about: its detail reads "Gliding
 *  through <url>", which is the ONLY place a recording states its page. */
function recordingPageUrl(detail: string): string {
  const m = /https?:\/\/\S+/.exec(detail || '')
  return m ? normalizePageUrl(m[0]) : ''
}

/** The pages that produced a KEPT recording, or null when the run's events do
 *  not support the question. The pipeline emits `film.recording` (the attempt,
 *  carrying the page) and then either `film.shot` (kept) or `decide.guard`
 *  (dropped) for that same stop, so a kept shot's page is its nearest preceding
 *  recording. If any kept shot has no resolvable page ahead of it, the pairing
 *  is incomplete and we return null rather than a set with holes in it — a
 *  missing page here would show up as a confident "you never filmed this" about
 *  a page that is in the film. */
function keptPages(events: OverviewEventRow[]): Set<string> | null {
  const kept = new Set<string>()
  let pending = ''
  for (const e of events) {
    if (e.kind === 'film.recording') {
      pending = recordingPageUrl(e.detail)
    } else if (e.kind === 'film.shot') {
      if (!pending) return null
      kept.add(pending)
    }
  }
  return kept
}

const listPhrase = (items: string[]): string =>
  items.length <= 1 ? (items[0] || '')
    : `${items.slice(0, -1).join(', ')} and ${items[items.length - 1]}`

/** The path a reader recognises: "/pricing", or "the homepage" for the root. */
function pageLabel(pageUrl: string): string {
  try {
    const p = new URL(pageUrl).pathname.replace(/\/+$/, '')
    return p ? p : 'the homepage'
  } catch {
    return pageUrl
  }
}

export async function getSuggestions(
  accessToken: string | null | undefined,
): Promise<SuggestionsResult> {
  const me = await verifyUser(accessToken)
  if (!me) return { authError: true }
  const db = adminClient()
  const runs = await overviewRuns(db, me.id)
  if (!runs.length) return { suggestions: [] }

  const events = await overviewEvents(db, runs.map((r) => r.id),
    ['read.page', 'film.recording', 'film.shot', 'chat.user'])
  const byRun = eventsByRun(events)
  const nameOf = (r: OverviewRunRow) =>
    siteHost(r.company_url) || r.brand || 'this site'

  const out: Suggestion[] = []
  // Two cards must never propose the same click. A site that is at once the
  // most-filmed, the one with a stranded failure and the one with unfilmed
  // pages would otherwise fill the whole column with one URL.
  const claimed = new Set<string>()
  /** Adds the card unless something already proposes that exact click.
   *  Returns whether it landed, so a kind with several candidates can move on
   *  to its next-best one rather than dropping out of the column entirely. */
  const push = (s: Suggestion): boolean => {
    const key = s.action.type === 'build' ? `b:${normalizePageUrl(s.action.url)}`
      : `o:${s.action.runId}`
    if (claimed.has(key)) return false
    claimed.add(key)
    out.push(s)
    return true
  }

  // 1 ─ IN FLIGHT. Derived from: runs.status ∈ {queued, running}. The most
  //     useful thing on the page when it applies, because it is the only card
  //     about work that is happening rather than work that has finished.
  const flying = runs.find((r) => r.status === 'queued' || r.status === 'running')
  if (flying) {
    push({
      id: `in-flight-${flying.id}`,
      kind: 'in-flight',
      title: `${nameOf(flying)} is in the studio`,
      detail: flying.status === 'running'
        ? 'Filmo is working on this one now — the workspace shows what it is doing as it does it.'
        : 'This one is queued. It starts as soon as the studio finishes what is in front of it.',
      evidence: `run ${flying.status}`,
      at: flying.created_at,
      action: { type: 'open', runId: flying.id, label: 'Open the workspace' },
    })
  }

  // 2 ─ READ BUT NEVER FILMED. Derived from: `read.page` rows for a DELIVERED
  //     run, minus the pages behind that run's kept `film.shot` rows. Both
  //     halves are rows; the subtraction is the whole claim. Runs whose events
  //     cannot answer the question (no recordings at all, or a kept shot with
  //     no page ahead of it) are skipped rather than guessed at.
  for (const r of runs) {
    if (!isDelivered(r.status)) continue
    const es = byRun.get(r.id) ?? []
    const kept = keptPages(es)
    if (!kept || kept.size === 0) continue
    const read: string[] = []
    for (const e of es) {
      if (e.kind !== 'read.page') continue
      const u = readPageUrl(e.title, r.company_url)
      if (u && !read.includes(u)) read.push(u)
    }
    const unfilmed = read.filter((u) => !kept.has(u))
    if (!unfilmed.length) continue
    const labels = unfilmed.slice(0, 3).map(pageLabel)
    push({
      id: `unfilmed-${r.id}`,
      kind: 'unfilmed-page',
      title: unfilmed.length === 1
        ? `One page of ${nameOf(r)} never made the film`
        : `${unfilmed.length} pages of ${nameOf(r)} never made the film`,
      // Says what happened and what the button does — never what the next film
      // will contain. Whether a new run keeps a recording of that page is the
      // recorder's call at the time, and this card does not get to promise it.
      detail: `Filmo read ${listPhrase(labels)}${unfilmed.length > labels.length ? ' and more' : ''}`
        + `, and kept no recording from ${unfilmed.length === 1 ? 'it' : 'them'}.`
        + ` Point a filmo straight at ${labels[0]} to make it the page the film opens on.`,
      evidence: `${read.length} pages read · ${kept.size} recordings kept`,
      at: r.created_at,
      action: { type: 'build', url: unfilmed[0], label: 'Film that page' },
    })
    break
  }

  // 3 ─ SHIPPED WITHOUT A NOTE. Derived from: a delivered walkrec run with
  //     zero `chat.user` rows — nobody ever told the director to change
  //     anything. Restricted to walkrec because that is the only pipeline with
  //     a director to talk to.
  const unnoted = runs.find((r) =>
    r.film_mode === 'walkrec' && isDelivered(r.status)
    && !(byRun.get(r.id) ?? []).some((e) => e.kind === 'chat.user'))
  if (unnoted) {
    push({
      id: `no-notes-${unnoted.id}`,
      kind: 'no-notes',
      title: `You shipped ${nameOf(unnoted)} without a note`,
      detail: 'This filmo went out exactly as the director cut it. Open it and'
        + ' say what you would change — a note re-cuts the film.',
      evidence: 'delivered, no director notes',
      at: unnoted.created_at,
      action: { type: 'open', runId: unnoted.id, label: 'Open and give a note' },
    })
  }

  // 4 ─ A FAILURE NOTHING FOLLOWED. Derived from: a run with status 'failed'
  //     for which no delivered run of the same host exists with a LATER
  //     created_at. Both sides are row comparisons; nothing is inferred about
  //     why it failed.
  const stranded = runs.find((r) => {
    if (r.status !== 'failed') return false
    const host = siteHost(r.company_url)
    if (!isProposableHost(host)) return false
    return !runs.some((o) =>
      isDelivered(o.status) && siteHost(o.company_url) === host
      && o.created_at > r.created_at)
  })
  if (stranded && stranded.company_url) {
    push({
      id: `stranded-${stranded.id}`,
      kind: 'stranded-failure',
      title: `${nameOf(stranded)} never finished`,
      detail: `That build failed, and no filmo of ${nameOf(stranded)} has landed since.`
        + ' Most failures are a bad moment rather than a bad site — run it again.',
      evidence: 'run failed',
      at: stranded.created_at,
      action: { type: 'build', url: stranded.company_url, label: 'Try it again' },
    })
  }

  // 5 ─ THE SITE YOU COME BACK TO. Derived from: a count of delivered runs
  //     grouped by host. Says only how many times it was filmed and when the
  //     newest cut is — never that the site has changed, which would need a
  //     crawl we have not done.
  const tally = new Map<string, { count: number; newest: OverviewRunRow }>()
  for (const r of runs) {
    if (!isDelivered(r.status)) continue
    const host = siteHost(r.company_url)
    if (!isProposableHost(host)) continue
    const cur = tally.get(host)
    // runs is newest-first, so the first row seen for a host IS its newest.
    if (cur) cur.count++
    else tally.set(host, { count: 1, newest: r })
  }
  // Most-filmed first, then the next one down. The top site is often already
  // spoken for by an earlier card (a stranded failure on the same host), and
  // dropping the whole kind because its FIRST candidate was taken would spend
  // a slot on nothing.
  const ranked = Array.from(tally.entries())
    .filter(([, v]) => v.count >= 2)
    .sort((a, b) => b[1].count - a[1].count)
  for (const [host, v] of ranked) {
    if (!v.newest.company_url) continue
    const landed = push({
      id: `most-filmed-${host}`,
      kind: 'most-filmed',
      title: `You've filmed ${host} ${v.count} times`,
      // NO SUPERLATIVE. This card falls through to the next-ranked site when
      // the top one is already claimed above, so "the site you come back to
      // most" would be false exactly when the fallback fires. The count in the
      // title is the fact; the sentence only has to be true of any repeat.
      detail: 'You keep coming back to this one. Every filmo is cut from'
        + ' whatever the site says on the day it is read.',
      evidence: `newest of ${v.count} delivered filmos`,
      at: v.newest.created_at,
      action: { type: 'build', url: v.newest.company_url, label: 'Film it again' },
    })
    if (landed) break
  }

  return { suggestions: out.slice(0, SUGGESTION_CAP) }
}

// ═══════════════════ THE RAIL'S LIVE-FILM ENTRY ═══════════════════
//
// Feeds components/rail/LiveFilmEntry — the one entry that follows the reader
// off the studio so a running film stays visible on Overview, Filmos and
// Assets. It answers exactly one question, "which of my films are open or just
// finished, and is anything actually happening to them", and it is allowed to
// answer only from rows that exist.
//
// ── LIVENESS IS STATUS *AND* A HEARTBEAT ───────────────────────────────────
// A terminal event is not a reliable signal — the sink browns out, a worker
// dies mid-render, and the row that would have said "done" never lands. The
// studio already learned this (its `working` flag ends on a terminal STATUS
// precisely because "a sink brownout used to leave it spinning forever on a
// finished film"). So a run counts as LIVE only when its status is non-terminal
// AND something has happened to it recently. A run that has gone quiet is
// reported STALLED and the entry stops animating: a moving dot on a wedged run
// is a claim that work is being done, and it would be false.
//
// ── WHERE THE HEARTBEAT COMES FROM, AND WHY IT IS TWO TABLES ────────────────
// NOT `runs.updated_at`, and NOT `runs.phase`. Measured on a run that was live
// while this was written: updated_at was stamped 2 seconds after created_at and
// then sat still for 12 minutes while the film rendered, and phase still read
// 'planning' when agent_events was on 'assemble.render'. Both move at creation
// and again at the terminal write; neither tracks the middle. Keying staleness
// on updated_at would park every healthy run about thirty seconds in.
//
// The pulse is the run's own event stream — and the two pipelines write to
// DIFFERENT tables. Measured over the last 60 runs: all 45 `classic` runs have
// zero agent_events and write run_events; all 15 `walkrec` runs write
// agent_events. They are disjoint, so reading only agent_events (the obvious
// choice, because that is what the walkrec studio polls) would report every
// classic run as stalled from the moment it started. `film_mode` picks the
// table. If a third pipeline is ever added, it belongs in RAIL_BEAT_TABLE.
const RAIL_BEAT_TABLE = (filmMode: string | null): 'agent_events' | 'run_events' =>
  filmMode === 'walkrec' ? 'agent_events' : 'run_events'

// ── HOW LONG SILENCE IS ALLOWED TO LAST ─────────────────────────────────────
// 20 minutes, and the number is measured rather than felt. Across the whole
// event history (~4,100 gaps between consecutive events):
//   · walkrec (agent_events): p95 185s, p99 274s
//   · classic (run_events):   p95 105s, p99 305s
// so this is roughly 4x the p99 of both and a healthy run does not come close
// to tripping it. Going the other way, a delivered film's whole wall-clock life
// is p90 1,629s / max 1,871s — so a run silent for 20 minutes has been quiet
// for longer than most complete films take, and 20 minutes is still short
// enough that it parks WELL before a healthy film of the same age would have
// finished.
// The evidence that this is the right side of the line: in the entire history
// exactly ONE agent_events gap ever exceeded it (1,155s, at assemble.render) —
// and that run's status is `failed`. The one time the walkrec pipeline went
// that quiet, it really was dying. Two classic runs did exceed it and go on to
// deliver (1,304s and 1,042s, both single retrying steps), so this will
// occasionally render a live classic run as stalled. That is the direction to
// err in: showing a still dot on a working run understates, showing a moving
// dot on a dead one lies.
const RAIL_STALE_AFTER_MS = 20 * 60_000

// ── HOW LONG A FINISH STAYS NEWS ────────────────────────────────────────────
// A delivered film keeps its entry until it is opened, which is Dennis's rule —
// nothing finishes without him noticing. But "until opened" cannot mean
// forever: this account holds 173 delivered runs, and without a bound the rail
// would announce every film ever made as unopened news. A day is the bound. Past
// it, a film is not news, it is library, and the Filmos entry two rows up is
// already where library lives.
const RAIL_NEWS_WINDOW_MS = 24 * 60 * 60_000

// The rail looks at this account's most recent runs only. Anything open is by
// definition recent, and a small fixed window keeps this the cheapest read in
// the app — one narrow query, indexed the same way listMyRuns already is.
const RAIL_RUN_WINDOW = 12
// Newest heartbeats across the (few) open runs. Comfortably more than enough to
// contain the newest row for each: only a handful of runs can be open at once,
// and a run whose beat is not in this window has been out-emitted by its
// siblings for long enough that it is stale anyway.
const RAIL_BEAT_ROWS = 60

// Same three words the run page and the studio already treat as terminal.
// `completed_with_warnings` ships a film, so it is an end, not a middle.
const RAIL_TERMINAL = new Set(['delivered', 'completed_with_warnings', 'failed'])

/** live    — non-terminal, and something happened recently. The dot moves.
 *  stalled — non-terminal, but silent past RAIL_STALE_AFTER_MS. Still, not gone.
 *  ready   — finished with a film to watch.
 *  stopped — finished with nothing to watch (failed, or delivered with no
 *            final_url, which the run page already calls out as an upload that
 *            never landed). Never dressed as "ready". */
export type LiveFilmState = 'live' | 'stalled' | 'ready' | 'stopped'

export interface LiveFilm {
  id: string
  /** The customer's own site, for the tooltip and the screen-reader name. The
   *  ONLY run-derived string that reaches the rail: no brain, no model, no
   *  price, no phase, no finish_reason. */
  label: string
  state: LiveFilmState
}

/** `unavailable` is a real member and not laziness. Every other outcome here is
 *  a claim about the account's films, and a failed read is not one — rendering
 *  it as `{ films: [] }` would tell a reader with a film in the studio that
 *  nothing is running. The client keeps its last good answer instead. (Same
 *  rule the Overview's reads state at length: a read that did not happen must
 *  be indistinguishable from a read that failed.) */
export type LiveFilmsResult =
  | { authError: true }
  | { unavailable: true }
  | { films: LiveFilm[] }

/** Newest event time per run id, in ms. Returns null if the read FAILED — the
 *  caller must not turn our own blindness into a stalled dot. */
async function railHeartbeats(
  db: ReturnType<typeof adminClient>,
  table: 'agent_events' | 'run_events',
  runIds: string[],
): Promise<Map<string, number> | null> {
  const out = new Map<string, number>()
  if (!runIds.length) return out
  const { data, error } = await db.database
    .from(table)
    .select('run_id, created_at')
    .in('run_id', runIds)
    .order('created_at', { ascending: false })
    .limit(RAIL_BEAT_ROWS)
  if (error || data == null) return null
  for (const row of (data as { run_id: string; created_at: string }[])) {
    const t = Date.parse(row.created_at)
    if (!isFinite(t)) continue
    const cur = out.get(row.run_id)
    if (cur == null || t > cur) out.set(row.run_id, t)
  }
  return out
}

export async function getLiveFilms(
  accessToken: string | null | undefined,
): Promise<LiveFilmsResult> {
  const me = await verifyUser(accessToken)
  if (!me) return { authError: true }
  const db = adminClient()

  // `.eq('user_id')` IS the boundary — the admin client bypasses RLS, exactly
  // as in listMyRuns / listAssets / the Overview reads.
  const { data, error } = await db.database
    .from('runs')
    .select('id, brand, company_url, status, film_mode, final_url, created_at, updated_at')
    .eq('user_id', me.id)
    .order('created_at', { ascending: false })
    .limit(RAIL_RUN_WINDOW)
  if (error || data == null) return { unavailable: true }

  const rows = (data as {
    id: string; brand: string | null; company_url: string | null
    status: string; film_mode: string | null; final_url: string | null
    created_at: string; updated_at: string | null
  }[])

  const open = rows.filter((r) => !RAIL_TERMINAL.has(r.status))
  // Only the OPEN runs need a heartbeat — a finished run's state is settled by
  // its status, so nothing is spent asking when it last spoke. When nothing is
  // open this is the whole cost of the call: one query.
  let beats = new Map<string, number>()
  if (open.length) {
    const walkrec = open.filter((r) => RAIL_BEAT_TABLE(r.film_mode) === 'agent_events')
    const classic = open.filter((r) => RAIL_BEAT_TABLE(r.film_mode) === 'run_events')
    const [a, b] = await Promise.all([
      railHeartbeats(db, 'agent_events', walkrec.map((r) => r.id)),
      railHeartbeats(db, 'run_events', classic.map((r) => r.id)),
    ])
    if (a == null || b == null) return { unavailable: true }
    beats = new Map([...a, ...b])
  }

  const now = Date.now()
  const films: LiveFilm[] = []
  for (const r of rows) {
    const label = siteHost(r.company_url) || r.brand || 'Your film'

    if (RAIL_TERMINAL.has(r.status)) {
      // Terminal: the run row's own last write is when it ended.
      const endedAt = Date.parse(r.updated_at || r.created_at)
      if (!isFinite(endedAt) || now - endedAt > RAIL_NEWS_WINDOW_MS) continue
      // A film to watch, or not. `delivered` without a final_url is the upload
      // that never completed — the run page says so in as many words, and it is
      // not something to hang a ready mark on.
      const watchable = isDelivered(r.status) && !!r.final_url
      films.push({ id: r.id, label, state: watchable ? 'ready' : 'stopped' })
      continue
    }

    // Open: the newest of everything that could mark activity. created_at is in
    // here so a just-enqueued run with no events yet reads as fresh rather than
    // as instantly silent, and updated_at because it is stamped at the claim.
    // Neither is trusted to track the MIDDLE of a run — that is the heartbeat's
    // job — but both are real activity when they are the newest thing there is.
    const marks = [
      Date.parse(r.created_at),
      r.updated_at ? Date.parse(r.updated_at) : NaN,
      beats.get(r.id) ?? NaN,
    ].filter((t) => isFinite(t))
    const last = marks.length ? Math.max(...marks) : 0
    films.push({
      id: r.id, label,
      state: now - last <= RAIL_STALE_AFTER_MS ? 'live' : 'stalled',
    })
  }

  return { films }
}
