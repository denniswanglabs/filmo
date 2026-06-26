'use server'
import { adminClient } from '../lib/insforge'

// ─────────────────────────── In-browser editor: save ───────────────────────────
// Persist the editor's edited props into runs.props_edited (a separate jsonb column
// from the clean, worker-generated `props`, so "revert to original" stays possible).
// Admin client bypasses RLS — but we scope the write to a single run id (and require
// a signed-in owner via `userId`, verified against the row) so a user can only save
// edits to a run they own. The clean `props` column is never touched here.
export async function saveEditedProps(input: {
  runId: string
  userId: string
  props: unknown
}): Promise<{ ok: boolean; error?: string }> {
  if (!input.runId || !input.userId) return { ok: false, error: 'missing runId/userId' }
  if (input.props == null || typeof input.props !== 'object') {
    return { ok: false, error: 'invalid props' }
  }
  const db = adminClient()
  // Ownership check: the admin client ignores RLS, so verify the run belongs to the
  // caller before writing (defense-in-depth — the page already RLS-loads the run).
  const { data: run, error: readErr } = await db.database
    .from('runs')
    .select('id, user_id')
    .eq('id', input.runId)
    .maybeSingle()
  if (readErr) return { ok: false, error: 'read: ' + JSON.stringify(readErr) }
  if (!run) return { ok: false, error: 'run not found' }
  if ((run as { user_id?: string }).user_id !== input.userId) {
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
  userId: string
  url: string
  goal?: string
  emphasis?: string
  quality?: 'standard' | 'premium'
  brain?: string
  mode?: 'mock' | 'real'
}) {
  const db = adminClient()
  const runKey = `web-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
  const brand = input.url.replace(/^https?:\/\//, '').replace(/\/.*$/, '')
  const quality = input.quality || 'standard'
  const brain = input.brain || 'super-free'
  const mode = input.mode || 'mock'
  const goal = input.goal || 'A 30-second brand explainer'

  const { data: runs, error: runErr } = await db.database
    .from('runs')
    .insert([{
      user_id: input.userId, run_key: runKey, brand, company_url: input.url,
      goal, emphasis: input.emphasis || null, quality, brain, mode, status: 'queued',
    }])
    .select()
  if (runErr) throw new Error('runs.insert: ' + JSON.stringify(runErr))
  const runId = runs![0].id

  const params = { company_url: input.url, goal, emphasis: input.emphasis || '', quality, brain, mode, run_key: runKey, duration: 30 }
  const { error: jobErr } = await db.database.from('jobs').insert([{ run_id: runId, status: 'queued', params }])
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
  userId: string
}): Promise<{ ok: boolean; error?: string }> {
  if (!input.runId || !input.userId) return { ok: false, error: 'missing runId/userId' }
  const db = adminClient()
  const { data: run, error: readErr } = await db.database
    .from('runs')
    .select('id, user_id, run_key, props, props_edited')
    .eq('id', input.runId)
    .maybeSingle()
  if (readErr) return { ok: false, error: 'read: ' + JSON.stringify(readErr) }
  if (!run) return { ok: false, error: 'run not found' }
  const r = run as { user_id?: string; run_key?: string; props?: unknown; props_edited?: unknown }
  if (r.user_id !== input.userId) return { ok: false, error: 'not the run owner' }
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
export async function pairDeveloper(input: { key: string; userId: string }): Promise<{ ok: boolean }> {
  const expected = process.env.DEV_MODE_KEY
  // Reject if the server has no key configured, or the supplied key doesn't match.
  // Constant-ish compare; we intentionally do not branch-log the comparison.
  if (!expected || !input.key || input.key !== expected) return { ok: false }
  if (!input.userId) return { ok: false }

  const db = adminClient()
  // Upsert-by-hand (read → insert-or-noop) so re-pairing is safe and we never throw on
  // a duplicate. The admin key bypasses RLS, so this writes for any signed-in account.
  const { data: existing } = await db.database
    .from('developers')
    .select('user_id')
    .eq('user_id', input.userId)
    .maybeSingle()

  if (!existing) {
    const { error } = await db.database
      .from('developers')
      .insert([{ user_id: input.userId, developer: true, source: 'dev_mode_key' }])
    if (error) throw new Error('developers.insert: ' + JSON.stringify(error))
  }
  return { ok: true }
}

/** Read back the developer flag for a user. Used to gate /inside/[runId]. */
export async function isDeveloper(userId: string | null | undefined): Promise<boolean> {
  if (!userId) return false
  const db = adminClient()
  const { data } = await db.database
    .from('developers')
    .select('developer')
    .eq('user_id', userId)
    .maybeSingle()
  return !!(data && (data as { developer?: boolean }).developer)
}

/**
 * Admin-client fetch of a run + its run_events, so a developer can view ANY run
 * (including the canonical featured run they don't own). Returns null if not found.
 * Bypasses RLS by design — only reachable behind the isDeveloper() gate in /inside.
 */
export async function readInsideRun(runId: string): Promise<{
  run: Record<string, unknown>
  events: Record<string, unknown>[]
} | null> {
  if (!runId) return null
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
