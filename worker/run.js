// Walk Studio cloud worker.
// Polls InsForge `jobs` (atomic claim_next_job), runs the EXISTING python
// build_runner.py pipeline as a subprocess, streams its ledger events into
// `run_events`, uploads the finished MP4 to the walk-videos bucket, and marks the
// run delivered. build_runner.py is untouched — this only orchestrates around it.
//
// Local run:  source ~/.zshrc && node --env-file=.env run.js
// Container:  Railway sets the env; CMD ["node","run.js"]
import { createAdminClient } from '@insforge/sdk'
import { spawn } from 'node:child_process'
import { readFileSync, existsSync } from 'node:fs'
import { join } from 'node:path'
import { hostname } from 'node:os'

const BASE_URL = process.env.INSFORGE_URL
const API_KEY = process.env.INSFORGE_API_KEY
const BUCKET = process.env.WALK_BUCKET || 'walk-videos'
// Where the python pipeline lives (the hermes-video-agent repo). In the container
// it's copied to /pipeline; locally it's the repo on disk.
const PIPELINE_DIR = process.env.PIPELINE_DIR ||
  join(process.env.HOME || '', 'Desktop/Projects/Hackathons/hermes-video-agent')
const PYTHON_BIN = process.env.PYTHON_BIN || 'python3'
const POLL_MS = Number(process.env.POLL_MS || 4000)
const LEDGER_POLL_MS = Number(process.env.LEDGER_POLL_MS || 2000)
const WORKER_ID = process.env.WORKER_ID || `worker-${hostname()}-${process.pid}`

if (!BASE_URL || !API_KEY) { console.error('FATAL: INSFORGE_URL / INSFORGE_API_KEY required'); process.exit(1) }
const db = createAdminClient({ baseUrl: BASE_URL, apiKey: API_KEY })

const log = (...a) => console.log(new Date().toISOString(), ...a)
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

// ── actor classification (mirrors activity.py): tag each ledger event line ──
const NEMOTRON_CUES = ['storyboard decided', 'planner', 'brain=', 'llm plan', 'nemotron', 'plan unavailable', 'falling back to deterministic', 're-planned']
const STRIPE_CUES = ['payment link', 'issuing', 'spending_limit', 'spending limit', 'authorization', 'authoriz', 'provision', 'earn', 'cardholder', 'virtual card', ' card ', 'charge', 'payout', 'checkout']
function classifyActor(msg) {
  const m = (msg || '').toLowerCase()
  if (NEMOTRON_CUES.some((c) => m.includes(c))) return 'nemotron'
  if (STRIPE_CUES.some((c) => m.includes(c))) return 'stripe'
  return 'hermes'
}

function readLedger(runKey) {
  const p = join(PIPELINE_DIR, 'runs', runKey, 'ledger.json')
  if (!existsSync(p)) return null
  try { return JSON.parse(readFileSync(p, 'utf8')) } catch { return null }
}

// Insert any events with seq > lastSeq; return the new high-water seq.
async function syncEvents(runId, ledger, lastSeq) {
  const events = (ledger && ledger.events) || []
  const fresh = events.filter((e) => (e.seq || 0) > lastSeq)
  if (!fresh.length) return lastSeq
  const rows = fresh.map((e) => ({
    run_id: runId, seq: e.seq, level: e.level || 'info',
    actor: classifyActor(e.msg), msg: e.msg || '',
  }))
  const { error } = await db.database.from('run_events').insert(rows)
  if (error) { log('  ! run_events.insert', JSON.stringify(error)); return lastSeq }
  return Math.max(lastSeq, ...fresh.map((e) => e.seq || 0))
}

// Pull the structured run fields out of the final ledger (defensive about location).
function mapLedgerToRun(ledger) {
  const pnl = ledger.pnl || {}
  const pricing = ledger.pricing || {}
  const num = (...vals) => { for (const v of vals) if (typeof v === 'number') return v; return null }
  return {
    status: ledger.status || 'failed',
    phase: ledger.phase || null,
    price_cents: num(pnl.price_cents, pricing.price_cents, pnl.price, pricing.price),
    cogs_cents: num(pnl.cogs_cents, pnl.spent_cents, pricing.cogs_cents, pnl.cogs),
    margin: num(pnl.margin, pnl.net_margin),
    plan: ledger.plan || null,
    selection: ledger.selection || null,
  }
}

async function uploadVideo(runKey, runId) {
  const p = join(PIPELINE_DIR, 'runs', runKey, 'final.mp4')
  if (!existsSync(p)) return null
  const buf = readFileSync(p)
  const blob = new Blob([buf], { type: 'video/mp4' })
  const { data, error } = await db.storage.from(BUCKET).upload(`${runKey}/final.mp4`, blob)
  if (error) { log('  ! storage.upload', JSON.stringify(error)); return null }
  return data?.url || null
}

async function setRun(runId, patch) {
  const { error } = await db.database.from('runs').update(patch).eq('id', runId)
  if (error) log('  ! runs.update', JSON.stringify(error))
}

async function processJob(job) {
  const p = job.params || {}
  const runId = job.run_id
  const runKey = p.run_key || p.runKey
  log(`claimed job ${job.id} -> run ${runKey} (${p.company_url || p.url})`)
  await setRun(runId, { status: 'running', phase: 'planning' })

  // spawn the existing pipeline
  const args = ['build_runner.py',
    '--url', p.company_url || p.url,
    '--goal', p.goal || 'A 30-second brand explainer',
    '--run-id', runKey,
    '--mode', p.mode || 'mock',
    '--quality', p.quality || 'standard',
    '--brain', p.brain || 'super-free',
    '--duration', String(p.duration || 30)]
  if (p.emphasis) args.push('--emphasis', p.emphasis)
  const env = { ...process.env }
  if ((p.mode || 'mock') === 'mock') env.PRODUCER_SIMULATE_PAID = '1'

  const child = spawn(PYTHON_BIN, args, { cwd: PIPELINE_DIR, env })
  child.stdout.on('data', (d) => process.stdout.write(`  [py] ${d}`))
  child.stderr.on('data', (d) => process.stderr.write(`  [py!] ${d}`))

  // stream ledger events while the build runs
  let lastSeq = 0
  let alive = true
  const streamer = (async () => {
    while (alive) {
      const led = readLedger(runKey)
      if (led) { lastSeq = await syncEvents(runId, led, lastSeq); if (led.phase) await setRun(runId, { phase: led.phase }) }
      await sleep(LEDGER_POLL_MS)
    }
  })()

  const code = await new Promise((res) => child.on('close', res))
  alive = false
  await streamer

  const ledger = readLedger(runKey) || {}
  await syncEvents(runId, ledger, lastSeq)   // final flush
  const mapped = mapLedgerToRun(ledger)

  if (code === 0 && mapped.status === 'delivered') {
    const url = await uploadVideo(runKey, runId)
    await setRun(runId, { ...mapped, final_url: url })
    await db.database.from('jobs').update({ status: 'done' }).eq('id', job.id)
    log(`  delivered run ${runKey} (${url ? 'video uploaded' : 'NO video'})`)
  } else {
    await setRun(runId, { status: 'failed', phase: ledger.phase || 'failed' })
    await db.database.from('jobs').update({ status: 'failed', error: `exit ${code}, ledger ${mapped.status}` }).eq('id', job.id)
    log(`  FAILED run ${runKey} (exit ${code}, ledger ${mapped.status})`)
  }
}

async function main() {
  log(`Walk Studio worker up — ${WORKER_ID}`)
  log(`  insforge: ${BASE_URL}`)
  log(`  pipeline: ${PIPELINE_DIR}`)
  for (;;) {
    let job = null
    try {
      const { data, error } = await db.database.rpc('claim_next_job', { p_worker: WORKER_ID })
      if (error) log('claim error', JSON.stringify(error))
      else job = data
    } catch (e) { log('claim threw', String(e)) }

    if (job && job.id) {
      try { await processJob(job) } catch (e) { log('processJob threw', String(e)) }
    } else {
      await sleep(POLL_MS)
    }
  }
}

main()
