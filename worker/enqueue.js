// Test helper: enqueue a build the way the frontend will — create a `runs` row
// (status=queued) + a `jobs` row (status=queued) for the worker to claim.
// Run: node --env-file=.env enqueue.js   (override via ENQ_* env vars)
import { createAdminClient } from '@insforge/sdk'

const db = createAdminClient({ baseUrl: process.env.INSFORGE_URL, apiKey: process.env.INSFORGE_API_KEY })

const userId = process.env.ENQ_USER_ID || '90923fa8-41da-47f2-8d45-81a7dbd3405f' // keystone test user
const url = process.env.ENQ_URL || 'https://stripe.com'
const goal = process.env.ENQ_GOAL || 'A 30-second brand explainer'
const emphasis = process.env.ENQ_EMPHASIS || 'accept payments in one integration'
const quality = process.env.ENQ_QUALITY || 'standard'
const brain = process.env.ENQ_BRAIN || 'super-free'
const mode = process.env.ENQ_MODE || 'mock'
const runKey = process.env.ENQ_RUNKEY || `cloud-${Date.now()}`
const brand = (url.replace(/^https?:\/\//, '').replace(/\/.*$/, '')) || url

const { data: runRows, error: runErr } = await db.database.from('runs')
  .insert([{ user_id: userId, run_key: runKey, brand, company_url: url, goal, emphasis, quality, brain, mode, status: 'queued' }])
  .select()
if (runErr) { console.error('runs.insert', JSON.stringify(runErr)); process.exit(1) }
const runId = runRows[0].id

const params = { company_url: url, goal, emphasis, quality, brain, mode, run_key: runKey, duration: 30 }
const { error: jobErr } = await db.database.from('jobs').insert([{ run_id: runId, status: 'queued', params }])
if (jobErr) { console.error('jobs.insert', JSON.stringify(jobErr)); process.exit(1) }

console.log(`enqueued: run ${runKey} (${runId}) for ${url} [${mode}/${quality}/${brain}]`)
