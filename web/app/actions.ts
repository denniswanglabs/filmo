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
