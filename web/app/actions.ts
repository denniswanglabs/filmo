'use server'
import { adminClient } from '../lib/insforge'

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
