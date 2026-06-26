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
import { readFileSync, writeFileSync, existsSync, readdirSync, mkdirSync } from 'node:fs'
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

// ── resilience: never let one stray rejection/exception kill the poll loop ──
// A fire-and-forget rejection (e.g. inside the ledger streamer or a child-process
// stream handler) terminates Node by default since v15. Log it and keep running;
// the main loop will pick up the next job on its next tick.
process.on('unhandledRejection', (reason) => {
  try { log('!! unhandledRejection (kept alive)', String(reason && reason.stack || reason)) } catch {}
})
process.on('uncaughtException', (err) => {
  try { log('!! uncaughtException (kept alive)', String(err && err.stack || err)) } catch {}
})

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

// The render-ready props.json (fps, scenes[], theme, audio_path, …) the in-browser
// editor loads. Persisted onto the run row so the editor never needs disk access.
function readProps(runKey) {
  const p = join(PIPELINE_DIR, 'runs', runKey, 'props.json')
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

// Idempotent upload: InsForge storage does NOT overwrite — a second upload of the
// same key lands as "name (1).ext", which would break the exact-filename asset
// resolution the editor depends on. So remove any existing object at the key first.
async function putObject(key, blob) {
  try { await db.storage.from(BUCKET).remove([key]) } catch {}
  const { data, error } = await db.storage.from(BUCKET).upload(key, blob)
  if (error) { log(`  ! storage.upload ${key}`, JSON.stringify(error)); return null }
  return data?.url || null
}

async function uploadVideo(runKey, runId, name = 'final.mp4') {
  const p = join(PIPELINE_DIR, 'runs', runKey, name)
  if (!existsSync(p)) return null
  const blob = new Blob([readFileSync(p)], { type: 'video/mp4' })
  return putObject(`${runKey}/${name}`, blob)
}

// ── per-scene asset upload (so the editor preview shows REAL media) ────────────
// The render stages every asset props.json references (screenshots, per-scene VO,
// the music bed, the walkthrough mp4, the brand logo) into studio/public/ under
// FLAT filenames that exactly match the relative strings inside props.json. The
// editor's <Player> resolves those relative names against `assetBaseUrl` =
// .../buckets/walk-videos/objects/<run_key>. So uploading studio/public/*<runKey>*
// to <runKey>/<filename> makes every preview asset resolve. final.mp4 is uploaded
// separately (uploadVideo); we never clobber it here.
const STUDIO_PUBLIC = join(PIPELINE_DIR, 'studio', 'public')
const CONTENT_TYPE = {
  '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp',
  '.svg': 'image/svg+xml', '.mp3': 'audio/mpeg', '.wav': 'audio/wav', '.m4a': 'audio/mp4',
  '.mp4': 'video/mp4', '.json': 'application/json',
}
const ctypeFor = (name) => CONTENT_TYPE['.' + (name.split('.').pop() || '').toLowerCase()] || 'application/octet-stream'

// Every studio/public file whose name contains the runKey == this run's staged
// assets (style_fill names them shot-<runKey>-*, vo-<runKey>*, music-<runKey>.mp3,
// walk-<runKey>-*, brand-logo-<runKey>.svg). Returns the list of uploaded names.
function stagedAssetNames(runKey) {
  if (!existsSync(STUDIO_PUBLIC)) return []
  try {
    return readdirSync(STUDIO_PUBLIC).filter((f) => f.includes(runKey))
  } catch { return [] }
}

async function uploadRunAssets(runKey) {
  const names = stagedAssetNames(runKey)
  let ok = 0
  for (const name of names) {
    try {
      const blob = new Blob([readFileSync(join(STUDIO_PUBLIC, name))], { type: ctypeFor(name) })
      const url = await putObject(`${runKey}/${name}`, blob)
      if (url) ok++
    } catch (e) { log(`  ! asset read ${name}`, String(e)) }
  }
  log(`  staged ${ok}/${names.length} per-scene assets to ${runKey}/`)
  return ok
}

async function setRun(runId, patch) {
  const { error } = await db.database.from('runs').update(patch).eq('id', runId)
  if (error) log('  ! runs.update', JSON.stringify(error))
}

// ───────────────────────────── re-render (editor Export) ─────────────────────
// A `rerender` job re-renders the run's EDITED props into a NEW mp4. It SKIPS
// capture/plan/price (those already ran for the original build). The editor's
// edited props live in runs.props_edited (durable in InsForge). The assets those
// props reference were uploaded to <runKey>/ by uploadRunAssets, so we pull them
// back down into studio/public/ and render against staticFile (assetBaseUrl is
// stripped so the render reads local files, not the hosted bucket URL).

const STUDIO_DIR = join(PIPELINE_DIR, 'studio')

// Append a run_event so the rerender shows up in the run page's activity feed.
async function emit(runId, msg, actor = 'hermes', level = 'info') {
  try {
    // seq: monotonic-ish; large base so it sorts after the original build's events.
    const seq = 100000 + Math.floor((Date.now() / 1000) % 100000)
    await db.database.from('run_events').insert([{ run_id: runId, seq, level, actor, msg }])
  } catch (e) { log('  ! emit', String(e)) }
}

// Download every bucket object under <runKey>/ into studio/public/ so the render
// resolves the per-scene assets via staticFile. Skips final.mp4 / edited.mp4
// (renders, not inputs). Returns count downloaded.
async function downloadRunAssets(runKey) {
  if (!existsSync(STUDIO_PUBLIC)) mkdirSync(STUDIO_PUBLIC, { recursive: true })
  let objs = []
  try {
    const { data } = await db.storage.from(BUCKET).list({ prefix: `${runKey}/`, limit: 200 })
    objs = (data && data.data) || data || []
  } catch (e) { log('  ! list assets', String(e)); return 0 }
  let ok = 0
  for (const o of objs) {
    const key = o.key || o.name
    if (!key) continue
    const base = key.split('/').pop()
    if (!base || base === 'final.mp4' || base === 'edited.mp4' || base.endsWith('.json')) continue
    try {
      const { data: blob, error } = await db.storage.from(BUCKET).download(key)
      if (error || !blob) { log(`  ! download ${key}`, JSON.stringify(error)); continue }
      const buf = Buffer.from(await blob.arrayBuffer())
      writeFileSync(join(STUDIO_PUBLIC, base), buf)
      ok++
    } catch (e) { log(`  ! download ${key}`, String(e)) }
  }
  log(`  pulled ${ok}/${objs.length} assets into studio/public for ${runKey}`)
  return ok
}

// Render the Timeline composition with the given abs props path into outPath.
// Mirrors build_runner._run_vo_engine's exact remotion invocation + cwd + PATH.
function runRender(absPropsPath, outPath) {
  return new Promise((resolve) => {
    const env = {
      ...process.env,
      PATH: join(STUDIO_DIR, 'node_modules', '.bin') + (process.env.PATH ? ':' + process.env.PATH : ''),
    }
    const args = ['render', 'src/index.ts', 'Timeline', outPath,
      '--codec=h264', '--concurrency=8', `--props=${absPropsPath}`]
    const child = spawn('remotion', args, { cwd: STUDIO_DIR, env })
    child.on('error', (e) => { log('  ! remotion spawn', String(e)); resolve(1) })
    child.stdout.on('data', (d) => { try { process.stdout.write(`  [rmx] ${d}`) } catch {} })
    child.stderr.on('data', (d) => { try { process.stderr.write(`  [rmx!] ${d}`) } catch {} })
    child.on('close', (c) => resolve(c))
  })
}

// VO-regen (ElevenLabs/edge-tts) for a rerender whose VO text changed. Reuses the
// pipeline's style_fill.run_pipeline(do_align=True) via a tiny python -c, which
// re-synthesizes VO + re-times scenes + rebuilds props.json from the run's
// plan.json. REQUIRES the run dir (plan.json + brand_theme.json) to exist on THIS
// container — i.e. the rerender lands on the same container that built the run.
// Returns the path to the regenerated props.json, or null if it could not run.
function regenVoAndProps(runKey, beats) {
  return new Promise((resolve) => {
    const runDir = join(PIPELINE_DIR, 'runs', runKey)
    const planPath = join(runDir, 'plan.json')
    const brandPath = join(runDir, 'brand_theme.json')
    if (!existsSync(planPath)) { log('  rerender VO: no plan.json on this container — cannot re-synthesize'); return resolve(null) }
    // Overlay the edited beat texts onto plan.json, then run the align+props pipeline.
    let plan
    try { plan = JSON.parse(readFileSync(planPath, 'utf8')) } catch (e) { log('  ! read plan', String(e)); return resolve(null) }
    const byId = new Map((beats || []).map((b) => [b.scene_id, b.text]))
    const vo = (plan.voiceover && plan.voiceover.beats) || []
    let changed = 0
    for (const b of vo) { if (byId.has(b.scene_id) && byId.get(b.scene_id) !== b.text) { b.text = byId.get(b.scene_id); changed++ } }
    if (!changed) { log('  rerender VO: no beat text actually differs — skipping re-synth'); return resolve(null) }
    try { writeFileSync(planPath, JSON.stringify(plan, null, 2)) } catch (e) { log('  ! write plan', String(e)); return resolve(null) }
    const py = `import json,sys,style_fill\nres=style_fill.run_pipeline(${JSON.stringify(planPath)}, ${JSON.stringify(brandPath)}, "${process.env.VO_ENGINE_STYLE || 'orinovate-kinetic-light'}", ${JSON.stringify(runDir)}, fps=30, do_align=True, do_render=False)\nprint(res["props_path"])\n`
    const child = spawn(PYTHON_BIN, ['-c', py], { cwd: PIPELINE_DIR, env: { ...process.env } })
    let out = ''
    child.stdout.on('data', (d) => { out += String(d); try { process.stdout.write(`  [vo] ${d}`) } catch {} })
    child.stderr.on('data', (d) => { try { process.stderr.write(`  [vo!] ${d}`) } catch {} })
    child.on('error', (e) => { log('  ! vo regen spawn', String(e)); resolve(null) })
    child.on('close', (c) => {
      if (c !== 0) { log(`  rerender VO regen exited ${c}`); return resolve(null) }
      const propsPath = out.trim().split('\n').filter(Boolean).pop()
      resolve(propsPath && existsSync(propsPath) ? propsPath : null)
    })
  })
}

async function processReRender(job) {
  const p = job.params || {}
  const runId = job.run_id
  const runKey = p.run_key || p.runKey
  log(`claimed RERENDER job ${job.id} -> run ${runKey}`)
  await setRun(runId, { phase: 'rerendering' })
  await emit(runId, 'Edit export: re-rendering your edited video…', 'hermes')

  // Pull the edited props (durable). Fall back to clean props if no edit was saved.
  const { data: run, error } = await db.database.from('runs')
    .select('props, props_edited').eq('id', runId).maybeSingle()
  if (error || !run) { log('  ! rerender: run not found', JSON.stringify(error)); await failJob(job, 'run not found'); return }
  const edited = run.props_edited && Array.isArray(run.props_edited.scenes) ? run.props_edited : run.props
  if (!edited || !Array.isArray(edited.scenes)) { await failJob(job, 'no edited props'); await emit(runId, 'Re-render failed: nothing to render.', 'hermes', 'error'); return }

  // Make a working copy; strip the hosted asset base so the render reads local
  // studio/public files via staticFile (we download the run's assets below).
  const props = structuredClone(edited)
  delete props.assetBaseUrl

  // Pull the run's per-scene assets back into studio/public for the render.
  await downloadRunAssets(runKey)

  // If the editor carried changed VO copy (props.voiceover.beats[]), re-synthesize
  // it + re-time + rebuild props. Only possible on the build container (needs the
  // run dir). On success we render the REGENERATED props (which point at fresh,
  // re-timed audio); otherwise we render the edited props as-is (text/layout edits
  // still apply; VO stays the original).
  let absProps
  const beats = props.voiceover && Array.isArray(props.voiceover.beats) ? props.voiceover.beats : null
  if (beats && props.voiceover.dirty) {
    await emit(runId, 'Voiceover changed — re-synthesizing narration…', 'hermes')
    const regen = await regenVoAndProps(runKey, beats)
    if (regen) {
      absProps = regen
      await emit(runId, 'Voiceover re-synthesized and re-timed.', 'hermes')
    } else {
      await emit(runId, 'VO re-synthesis unavailable on this worker — rendering with the original narration.', 'hermes', 'warn')
    }
  }
  if (!absProps) {
    const propsPath = join(PIPELINE_DIR, 'runs', runKey, 'props.edited.json')
    try {
      mkdirSync(join(PIPELINE_DIR, 'runs', runKey), { recursive: true })
      writeFileSync(propsPath, JSON.stringify(props, null, 2))
    } catch (e) { await failJob(job, 'write props: ' + e); return }
    absProps = propsPath
  }

  const outPath = join(PIPELINE_DIR, 'runs', runKey, 'edited.mp4')
  await emit(runId, 'Rendering edited cut…', 'hermes')
  const code = await runRender(absProps, outPath)
  if (code !== 0 || !existsSync(outPath)) { await failJob(job, `remotion exit ${code}`); await emit(runId, 'Re-render failed during rendering.', 'hermes', 'error'); return }

  const url = await uploadVideo(runKey, runId, 'edited.mp4')
  await setRun(runId, { edited_url: url, phase: 'delivered' })
  await db.database.from('jobs').update({ status: 'done' }).eq('id', job.id)
  await emit(runId, 'Edited video ready.', 'hermes')
  log(`  RERENDER delivered run ${runKey} (${url ? 'uploaded' : 'NO video'})`)
}

async function failJob(job, reason) {
  log(`  RERENDER FAILED ${job.id}: ${reason}`)
  try { await db.database.from('jobs').update({ status: 'failed', error: String(reason) }).eq('id', job.id) } catch {}
}

async function processJob(job) {
  const p = job.params || {}
  const runId = job.run_id
  const runKey = p.run_key || p.runKey
  // Branch on job type: a `rerender` job re-renders the edited props (Export from
  // the editor) and never re-runs capture/plan/price. Default 'build' = full pipeline.
  if (job.type === 'rerender' || p.from === 'props_edited') {
    return processReRender(job)
  }
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
  child.on('error', (e) => log(`  ! spawn error ${runKey}`, String(e)))
  child.stdout.on('data', (d) => { try { process.stdout.write(`  [py] ${d}`) } catch {} })
  child.stderr.on('data', (d) => { try { process.stderr.write(`  [py!] ${d}`) } catch {} })

  // stream ledger events while the build runs. Guard each iteration so a transient
  // ledger/db error logs and retries instead of rejecting and killing the process.
  let lastSeq = 0
  let alive = true
  const streamer = (async () => {
    while (alive) {
      try {
        const led = readLedger(runKey)
        if (led) { lastSeq = await syncEvents(runId, led, lastSeq); if (led.phase) await setRun(runId, { phase: led.phase }) }
      } catch (e) { log('  ! streamer iter', String(e)) }
      await sleep(LEDGER_POLL_MS)
    }
  })()

  const code = await new Promise((res) => child.on('close', res))
  alive = false
  await streamer

  const ledger = readLedger(runKey) || {}
  await syncEvents(runId, ledger, lastSeq)   // final flush
  const mapped = mapLedgerToRun(ledger)

  if (code === 0 && (mapped.status === 'delivered' || mapped.status === 'completed_with_warnings')) {
    const url = await uploadVideo(runKey, runId)
    const props = readProps(runKey)   // render-ready props.json for the editor (null if missing)
    // Upload the per-scene staged assets (screenshots/VO/music/walkthrough/logo) so
    // the in-browser editor preview resolves REAL media, not just text/layout.
    await uploadRunAssets(runKey).catch((e) => log('  ! uploadRunAssets', String(e)))
    await setRun(runId, { ...mapped, final_url: url, props })
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
      try { await sleep(POLL_MS) } catch {}
    }
  }
}

// Keep the worker alive even if main() somehow rejects: log and restart the loop
// after a short backoff rather than letting the process exit silently.
async function supervise() {
  for (;;) {
    try {
      await main()
    } catch (e) {
      log('!! main() exited (restarting in 5s)', String(e && e.stack || e))
      await sleep(5000)
    }
  }
}
supervise()
