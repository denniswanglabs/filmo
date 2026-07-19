// Filmo CURATED claimer — runs on the Hetzner VM host.
//
// Polls InsForge `jobs` (atomic claim_next_job), runs the CURATED python
// build_runner.py pipeline (real screenshots via Playwright .venv-capture + real
// logos via _sanitize_logo_svg + the curated pattern library) as a subprocess,
// streams its ledger events into `run_events`, uploads the finished MP4 +
// per-scene assets to the walk-videos bucket, and marks the run delivered with a
// `hetzner-curated` producer tag.
//
// This is the proven Railway `worker/run.js` produce+ship path (build_runner is
// untouched), with two host-side additions:
//   1. An SSRF guard (refuse private/internal/metadata target URLs BEFORE any
//      egress) — ported from the previous VM worker.js.
//   2. A `hetzner-curated` producer tag so a delivered run is provably from the VM:
//      - jobs.claimed_by  = WORKER_ID (`hetzner-curated-<host>-<pid>`)
//      - runs.props.producer = 'hetzner-curated' (the `producer` column does not
//        exist in this schema; props is a jsonb that the editor already reads)
//      - a `run_events` line  "Produced on Hetzner VM (producer=hetzner-curated)."
//
// VO: ElevenLabs is the DEFAULT. We set WS_VO_PROVIDER=elevenlabs so align_vo.py
// tries ElevenLabs first and AUTOMATICALLY falls back to the free edge-tts +
// whisper path on any ElevenLabs failure (401 / quota_exceeded / no key), so a
// render never fails on VO. vo_alignment.json records which engine actually ran.
//
// Run:
//   export $(cat /root/.insforge-key)            # INSFORGE_API_KEY=ik_...
//   export INSFORGE_URL=https://jd3mdkqr.ap-southeast.insforge.app
//   export $(cat /root/.orkey)                   # OPENROUTER_API_KEY=...
//   node curated-claimer.js                      # daemon: claim oldest queued job in a loop
//   node curated-claimer.js --once <run_key>     # process ONE specific run_key (test, no claim)
//   node curated-claimer.js --url <URL>          # enqueue a test job for URL + process it
import { createAdminClient } from '@insforge/sdk'
import { spawn } from 'node:child_process'
import { readFileSync, writeFileSync, existsSync, readdirSync, mkdirSync } from 'node:fs'
import { join } from 'node:path'
import { hostname } from 'node:os'
import dns from 'node:dns/promises'
import net from 'node:net'
import { fileURLToPath } from 'node:url'

const BASE_URL = process.env.INSFORGE_URL || 'https://jd3mdkqr.ap-southeast.insforge.app'
const API_KEY = process.env.INSFORGE_API_KEY
const BUCKET = process.env.WALK_BUCKET || 'walk-videos'
const PIPELINE_DIR = process.env.PIPELINE_DIR || '/root/filmo-pipeline'
const PYTHON_BIN = process.env.PYTHON_BIN || '/root/filmo-venv/bin/python'
const POLL_MS = Number(process.env.POLL_MS || 4000)
const LEDGER_POLL_MS = Number(process.env.LEDGER_POLL_MS || 2000)
const PRODUCER = process.env.PRODUCER || 'hetzner-curated'
const WORKER_ID = process.env.WORKER_ID || `${PRODUCER}-${hostname()}-${process.pid}`
const RENDER_TIMEOUT_MS = Number(process.env.RENDER_TIMEOUT_MS || 1500000) // 25 min ceiling

// ── M2 Phase C: reversible Hermes-mode cutover ──────────────────────────────
// CLAIMER_MODE selects how the produce step runs:
//   'direct' (DEFAULT, SAFE LIVE PATH): the deterministic build_runner.py render
//            below — unchanged. This is what the live filmo-claimer daemon runs.
//   'hermes': the produce step is CONDUCTED by the Hermes agent inside the
//            NemoClaw sandbox (it drives the 5 filmo-host MCP tools end-to-end:
//            conversion_read -> plan -> price -> gate -> produce_and_ship, which
//            captures, renders, and uploads -> final_url). We parse the
//            `Shipped: <final_url>` line and mark the run delivered with
//            producer=hetzner-hermes. On ANY Hermes failure/timeout we FALL BACK
//            to the deterministic build_runner path, so a render NEVER fails.
const CLAIMER_MODE = (process.env.CLAIMER_MODE || 'direct').trim().toLowerCase()
const HERMES_PRODUCER = process.env.HERMES_PRODUCER || 'hetzner-hermes'
const HERMES_SANDBOX = process.env.HERMES_SANDBOX || 'filmo'
// Single-conduct skill (the auto path / legacy single atomic conduct): runs all
// five tools read->plan->price->gate->produce in one shot.
const HERMES_SKILL = process.env.HERMES_SKILL || 'filmo-producer'
// ── Option A: SPLIT conduct skills ──────────────────────────────────────────
// The split lets us PARK at a REAL Stripe payment between the price and the
// produce. Two scoped skills replace the single filmo-producer conduct for the
// human-pay path (and, by default, the auto path too — see runHermesConduct below):
//   HERMES_PLAN_SKILL    -> conversion_read, plan, price ONLY; prints
//                           "Planned: plan_id=<id> price_cents=<n> (<N> scenes)."
//   HERMES_PRODUCE_SKILL -> produce_and_ship ONLY, reusing the cached plan_id;
//                           prints "Shipped: <url> (<N> scenes)."
// Both are ADDITIVE — filmo-producer is left intact as a fallback. Reversibility:
// set HERMES_SPLIT=false (env) to use the old single atomic conduct everywhere.
const HERMES_PLAN_SKILL = process.env.HERMES_PLAN_SKILL || 'filmo-plan'
const HERMES_PRODUCE_SKILL = process.env.HERMES_PRODUCE_SKILL || 'filmo-produce'
const HERMES_SPLIT = String(process.env.HERMES_SPLIT ?? 'true').trim().toLowerCase() !== 'false'
const HERMES_BUDGET_CENTS = Number(process.env.HERMES_BUDGET_CENTS || 5000)
const HERMES_TIMEOUT_S = Number(process.env.HERMES_TIMEOUT_S || 1200) // nemoclaw exec --timeout (20min: slowest brand = stripe.com, ~12min render + a long InsForge-brownout upload tail was exceeding the old 900s and falling to recovery)
const PLAN_ATTEMPTS = Number(process.env.PLAN_ATTEMPTS || 3) // claimer-level retries of read->plan->price on a transient model/stream blip
const PLAN_RETRY_DELAY_MS = Number(process.env.PLAN_RETRY_DELAY_MS || 4000)
const NEMOCLAW_BIN = process.env.NEMOCLAW_BIN || 'nemoclaw'

// ── Pre-conduct Stripe TEST payment gate (human-pays) ───────────────────────
// When a claimed job has pay_mode==='human' AND payments are required, the customer
// must pay a REAL Stripe TEST Checkout (4242 card) BEFORE we conduct. TEST-mode only;
// gate.py reuses stripe_earn._assert_test_key (refuses live/missing keys, asserts
// livemode==false). Charge the price the conduct would charge: HERMES_PRICE_CAP_CENTS
// ($10) — every conduct price is capped to it and the gate always proceeds, so the cap
// IS the honest quote. REVERSIBILITY: set PAYMENTS_REQUIRED=false (env) to bypass the
// gate entirely (instant auto-proceed) without touching code or the website.
const PAYMENTS_REQUIRED = String(process.env.PAYMENTS_REQUIRED ?? 'true').trim().toLowerCase() !== 'false'
const GATE_PRICE_CENTS = Number(process.env.HERMES_PRICE_CAP_CENTS || 1000)
const GATE_CURRENCY = process.env.GATE_CURRENCY || 'usd'
const PAYMENT_TIMEOUT_MS = Number(process.env.PAYMENT_TIMEOUT_MS || 15 * 60 * 1000) // mirror build_runner 15 min
const PAYMENT_POLL_MS = Number(process.env.PAYMENT_POLL_MS || 2500)                 // mirror build_runner 2.5s
// Public base for the success/cancel return (the live run page). Env-driven.
const FILMO_PUBLIC_BASE = (process.env.FILMO_PUBLIC_BASE || 'https://filmostudio.vercel.app').replace(/\/+$/, '')
// Public site base used in the "video ready" delivery EMAIL link (where the customer
// watches / edits / downloads). The marketing domain, NOT the Vercel deploy host used
// for Stripe returns above. Env-overridable. The email links to <base>/runs/<runId>.
const FILMO_SITE_BASE = (process.env.FILMO_SITE_BASE || 'https://filmo.dev').replace(/\/+$/, '')
// AgentMail transactional-email sender (best-effort, see notifyVideoReady). The API key
// is loaded by systemd from /root/.agentmail-key (EnvironmentFile); absent key -> the
// notify step logs + skips, never failing or delaying a delivery.
const AGENTMAIL_API_KEY = process.env.AGENTMAIL_API_KEY
const AGENTMAIL_INBOX = process.env.AGENTMAIL_INBOX || 'filmo@agentmail.to'
// gate.py sits beside this ESM file; resolve it via import.meta (no __dirname in ESM).
const GATE_PY = process.env.GATE_PY || fileURLToPath(new URL('./gate.py', import.meta.url))
// The produce toolserver, invoked as a SHORT-LIVED CLI (NOT the running MCP server) to
// reconstruct a recovered run's rich editor props + heal its per-scene assets — see
// healRecoveredRun. It lives in PIPELINE_DIR (its runs/<plan_id>/props.json is the
// render source), not beside this ESM file, so resolve it from PIPELINE_DIR.
const TOOLSERVER_PY = process.env.TOOLSERVER_PY || join(PIPELINE_DIR, 'mcp_toolserver.py')
const HEAL_TIMEOUT_MS = Number(process.env.HEAL_TIMEOUT_MS || 180000)

if (!BASE_URL || !API_KEY) { console.error('FATAL: INSFORGE_URL / INSFORGE_API_KEY required (export $(cat /root/.insforge-key))'); process.exit(1) }
const db = createAdminClient({ baseUrl: BASE_URL, apiKey: API_KEY })

const log = (...a) => console.log(new Date().toISOString(), ...a)
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

// ── InsForge resilience: bounded fast-timeout + retry around EVERY InsForge call ──
// A single blocked InsForge call (a 30s gateway timeout on runs.update, or a hung
// storage upload) must NEVER freeze the single-threaded worker — that wedge cost us
// a live conduct. Every InsForge db/storage call below is wrapped in `ifCall`, which:
//   1. Races each attempt against IF_TIMEOUT_MS (default 10s) — the SDK's thenable
//      query builders have no AbortController, so a Promise.race timeout is the only
//      universal bound. The underlying request may keep running in the background,
//      but the WORKER stops waiting at 10s and moves on (the loop never blocks).
//   2. Retries IF_ATTEMPTS times (default 4) with 500ms→1s→2s backoff on a returned
//      `{error}` OR a thrown error OR a timeout — so a transient blip self-heals.
//   3. Caps TOTAL time at ~IF_TIMEOUT_MS*attempts + backoff (~40s+3.5s), then returns
//      cleanly. It NEVER hangs and NEVER throws: it returns the SDK's own
//      `{ data, error }` shape (with a synthetic timeout error on exhaustion), so the
//      existing `const { data, error } = await db…` destructuring at every call site
//      keeps working unchanged. Tune via env: IF_TIMEOUT_MS / IF_ATTEMPTS / IF_BACKOFF_MS.
const IF_TIMEOUT_MS = Number(process.env.IF_TIMEOUT_MS || 10000)
const IF_ATTEMPTS = Number(process.env.IF_ATTEMPTS || 4)
const IF_BACKOFF_MS = Number(process.env.IF_BACKOFF_MS || 500)

class IfTimeout extends Error {}

// Race a thenable op against a per-attempt timeout. Resolves the op's value, or
// rejects with IfTimeout once ms elapses (the op keeps running but is abandoned).
function withTimeout(op, ms, label) {
  return new Promise((resolve, reject) => {
    let settled = false
    const t = setTimeout(() => {
      if (settled) return
      settled = true
      reject(new IfTimeout(`InsForge ${label} timed out after ${ms}ms`))
    }, ms)
    Promise.resolve(op()).then(
      (v) => { if (settled) return; settled = true; clearTimeout(t); resolve(v) },
      (e) => { if (settled) return; settled = true; clearTimeout(t); reject(e) },
    )
  })
}

// Bounded retry wrapper for an InsForge `{data,error}` thenable. NEVER hangs (each
// attempt is timeout-bounded) and NEVER throws (returns {data,error}). On a returned
// error / thrown error / timeout it retries with backoff up to IF_ATTEMPTS, then
// returns the last {data,error} (synthesizing an error on a final timeout).
async function ifCall(label, op, { attempts = IF_ATTEMPTS, timeoutMs = IF_TIMEOUT_MS, baseDelayMs = IF_BACKOFF_MS } = {}) {
  let last = { data: null, error: { message: `InsForge ${label}: no attempt ran` } }
  for (let i = 0; i < attempts; i++) {
    try {
      const res = await withTimeout(op, timeoutMs, label)
      if (res && !res.error) return res
      last = res || { data: null, error: { message: `InsForge ${label}: empty result` } }
    } catch (e) {
      const timedOut = e instanceof IfTimeout
      last = { data: null, error: { message: String((e && e.message) || e), timeout: timedOut } }
    }
    if (i < attempts - 1) {
      log(`  ~ InsForge ${label} attempt ${i + 1}/${attempts} failed (${(last.error && last.error.message) || 'err'}); retrying`)
      await sleep(baseDelayMs * 2 ** i) // 500, 1000, 2000…
    }
  }
  log(`  ! InsForge ${label} exhausted after ${attempts} attempts: ${(last.error && last.error.message) || 'unknown'}`)
  return last
}

// ── resilience: never let one stray rejection/exception kill the poll loop ──
process.on('unhandledRejection', (reason) => {
  try { log('!! unhandledRejection (kept alive)', String(reason && reason.stack || reason)) } catch {}
})
process.on('uncaughtException', (err) => {
  try { log('!! uncaughtException (kept alive)', String(err && err.stack || err)) } catch {}
})

// ───────────────────────────── SSRF guard (Node) ────────────────────────────
// Parse the host; resolve EVERY A/AAAA record; reject if ANY address is private/
// loopback/link-local/reserved/multicast/unspecified — 10/8, 172.16/12,
// 192.168/16, 127/8, 169.254/16 (incl. 169.254.169.254 metadata), ::1, fc00::/7,
// fe80::/10, IPv4-mapped-IPv6, and the literal `localhost`. Throws on any unsafe
// or unresolvable host so the caller fails the job BEFORE any egress/build.
const BLOCKED_HOSTNAMES = new Set(['localhost', 'localhost.localdomain', 'ip6-localhost', 'ip6-loopback'])

function ipBytes(ip) {
  if (net.isIPv4(ip)) return ip.split('.').map((o) => Number(o))
  if (net.isIPv6(ip)) {
    let s = ip.split('%')[0]
    let v4tail = null
    const lastColon = s.lastIndexOf(':')
    if (s.slice(lastColon + 1).includes('.')) { v4tail = s.slice(lastColon + 1); s = s.slice(0, lastColon + 1) + '0:0' }
    const halves = s.split('::')
    const head = halves[0] ? halves[0].split(':') : []
    const tail = halves.length > 1 && halves[1] ? halves[1].split(':') : []
    const missing = 8 - head.length - tail.length
    const groups = [...head, ...Array(Math.max(0, missing)).fill('0'), ...tail]
    const bytes = []
    for (const g of groups) { const n = parseInt(g || '0', 16); bytes.push((n >> 8) & 0xff, n & 0xff) }
    if (v4tail) { bytes.splice(12, 4, ...v4tail.split('.').map((o) => Number(o))) }
    return bytes.length === 16 ? bytes : null
  }
  return null
}

function isBlockedIp(ipStr) {
  const ip = (ipStr || '').split('%')[0]
  const b = ipBytes(ip)
  if (!b) return true
  if (b.length === 4) {
    const [a, c] = b
    if (a === 10) return true
    if (a === 172 && c >= 16 && c <= 31) return true
    if (a === 192 && c === 168) return true
    if (a === 127) return true
    if (a === 169 && c === 254) return true
    if (a === 100 && c >= 64 && c <= 127) return true
    if (a === 0) return true
    if (a >= 224) return true
    return false
  }
  const allZero = b.every((x) => x === 0)
  if (allZero) return true
  if (b.slice(0, 15).every((x) => x === 0) && b[15] === 1) return true
  if (b[0] === 0xff) return true
  if (b[0] === 0xfe && (b[1] & 0xc0) === 0x80) return true
  if ((b[0] & 0xfe) === 0xfc) return true
  const first10Zero = b.slice(0, 10).every((x) => x === 0)
  if (first10Zero && b[10] === 0xff && b[11] === 0xff) return isBlockedIp(b.slice(12).join('.'))
  if (first10Zero && b[10] === 0 && b[11] === 0) return isBlockedIp(b.slice(12).join('.'))
  if (ip === 'fd00:ec2::254') return true
  return false
}

async function assertPublicUrl(rawUrl) {
  let u = String(rawUrl || '').trim()
  if (!u) throw new Error('empty URL')
  if (!/^https?:\/\//i.test(u)) u = 'https://' + u
  let parsed
  try { parsed = new URL(u) } catch (e) { throw new Error('unparseable URL: ' + String(e && e.message || e)) }
  if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') throw new Error('unsupported scheme: ' + parsed.protocol)
  const host = (parsed.hostname || '').replace(/^\[|\]$/g, '')
  if (!host) throw new Error('URL has no host')
  const low = host.toLowerCase().replace(/\.$/, '')
  if (BLOCKED_HOSTNAMES.has(low)) throw new Error(`blocked hostname: ${host}`)
  if (net.isIP(low)) {
    if (isBlockedIp(low)) throw new Error(`blocked IP literal: ${host}`)
    return { url: u, host: low }
  }
  let addrs
  try { addrs = await dns.lookup(low, { all: true }) }
  catch (e) { throw new Error(`could not resolve host ${host}: ${String(e && e.code || e)}`) }
  if (!addrs || !addrs.length) throw new Error(`host ${host} resolved to no addresses`)
  for (const a of addrs) {
    if (isBlockedIp(a.address)) throw new Error(`host ${host} resolves to a blocked address ${a.address}`)
  }
  return { url: u, host: low }
}

// ── actor classification: the product speaks as FILMO; only payment lines keep the
//    stripe tag (they surface solely on the dormant human-pay path). The old
//    hermes/nemotron actor labels retired with the Hermes conduct (2026-07-16). ──
const STRIPE_CUES = ['payment link', 'issuing', 'spending_limit', 'spending limit', 'authorization', 'authoriz', 'provision', 'earn', 'cardholder', 'virtual card', ' card ', 'charge', 'payout', 'checkout']
function classifyActor(msg) {
  const m = (msg || '').toLowerCase()
  if (STRIPE_CUES.some((c) => m.includes(c))) return 'stripe'
  return 'filmo'
}

// Payment THEATER lines from build_runner's simulated gate (PRODUCER_SIMULATE_PAID):
// with payments off, users never see a checkout, so narrating one is pure confusion.
// Filtered out of run_events whenever the job is not human-pay.
const PAYMENT_THEATER_CUES = ['payment gate', 'awaiting payment', 'customer paid', 'payment received', 'payment cleared', 'stripe test checkout', 'paymentintent', 'checkout.stripe.com', 'test card 4242', 'payment_timeout']
function isPaymentTheater(msg) {
  const m = (msg || '').toLowerCase()
  return PAYMENT_THEATER_CUES.some((c) => m.includes(c))
}

function readLedger(runKey) {
  const p = join(PIPELINE_DIR, 'runs', runKey, 'ledger.json')
  if (!existsSync(p)) return null
  try { return JSON.parse(readFileSync(p, 'utf8')) } catch { return null }
}

function readProps(runKey) {
  const p = join(PIPELINE_DIR, 'runs', runKey, 'props.json')
  if (!existsSync(p)) return null
  try { return JSON.parse(readFileSync(p, 'utf8')) } catch { return null }
}

async function syncEvents(runId, ledger, lastSeq, suppressPayments = false) {
  const events = (ledger && ledger.events) || []
  const fresh = events.filter((e) => (e.seq || 0) > lastSeq)
  if (!fresh.length) return lastSeq
  const rows = fresh
    .filter((e) => !(suppressPayments && isPaymentTheater(e.msg)))
    .map((e) => ({
      run_id: runId, seq: e.seq, level: e.level || 'info',
      actor: classifyActor(e.msg), msg: e.msg || '',
    }))
  if (!rows.length) return fresh.reduce((mx, e) => Math.max(mx, e.seq || 0), lastSeq)
  const { error } = await ifCall('run_events.insert', () => db.database.from('run_events').insert(rows))
  if (error) { log('  ! run_events.insert', JSON.stringify(error)); return lastSeq }
  return Math.max(lastSeq, ...fresh.map((e) => e.seq || 0))
}

function mapLedgerToRun(ledger) {
  const pnl = ledger.pnl || {}
  const pricing = ledger.pricing || {}
  const num = (...vals) => { for (const v of vals) if (typeof v === 'number') return v; return null }
  return {
    status: (ledger.status === 'completed_with_warnings' ? 'delivered' : ledger.status) || 'failed',
    phase: ledger.phase || null,
    price_cents: num(pnl.price_cents, pricing.price_cents, pnl.price, pricing.price),
    cogs_cents: num(pnl.cogs_cents, pnl.spent_cents, pricing.cogs_cents, pnl.cogs),
    margin: num(pnl.margin, pnl.net_margin),
    plan: ledger.plan || null,
    selection: ledger.selection || null,
    checkout_url: (ledger.earn || {}).checkout_url || null,
  }
}

// Idempotent upload: InsForge storage does NOT overwrite — remove the key first.
// Both the remove and the upload are bounded+retried (ifCall) so a hung storage
// call can never freeze the worker — this is the call that wedged a conduct for
// ~10min. TIMEOUT ASYMMETRY (Helsinki VM ↔ Singapore InsForge, ~140ms RTT,
// 1.3–3.8 MB/s upload): the remove is a tiny request (SHORT timeout, a 404 is
// fine); the UPLOAD moves multi-MB cross-region, so it gets a LONG per-attempt
// timeout (UPLOAD_TIMEOUT_MS, default 150s) — a short bound would ABORT a healthy
// large upload mid-flight. The SDK uses Node's undici fetch, which keep-alives /
// pools connections per origin by default, so steady-state calls reuse the warm
// connection (the ~0.8s cold-TLS penalty only hits the first call after restart).
const UPLOAD_TIMEOUT_MS = Number(process.env.UPLOAD_TIMEOUT_MS || 150000)
async function putObject(key, blob) {
  await ifCall(`storage.remove ${key}`, () => db.storage.from(BUCKET).remove([key]),
    { attempts: 2, timeoutMs: 8000 })
  const { data, error } = await ifCall(`storage.upload ${key}`, () => db.storage.from(BUCKET).upload(key, blob),
    { attempts: 3, timeoutMs: UPLOAD_TIMEOUT_MS })
  if (error) { log(`  ! storage.upload ${key}`, JSON.stringify(error)); return null }
  return data?.url || null
}

// InsForge gateway HARD-REJECTS bodies over ~20-30MB with HTTP 413 (deterministic,
// independent of timeout/plan). Guard at UPLOAD_MAX_BYTES (default 18MB, safely under
// the ceiling): a normal 30s 1080p render is ~5-7MB so this never trips in practice,
// but a long/4K cut could. Over the cap we DON'T attempt (a 413 would just fail) and
// signal the caller to keep the local file + mark the run retryable — never lose it.
const UPLOAD_MAX_BYTES = Number(process.env.UPLOAD_MAX_BYTES || 18 * 1024 * 1024)

async function uploadVideo(runKey, name = 'final.mp4') {
  const p = join(PIPELINE_DIR, 'runs', runKey, name)
  if (!existsSync(p)) return null
  const buf = readFileSync(p)
  if (buf.length > UPLOAD_MAX_BYTES) {
    log(`  ! ${name} is ${(buf.length / 1048576).toFixed(1)}MB > ${(UPLOAD_MAX_BYTES / 1048576).toFixed(0)}MB cap — skipping upload (would 413); video preserved at ${p}`)
    return null // caller treats null as upload-failed → keeps file, marks retryable
  }
  const blob = new Blob([buf], { type: 'video/mp4' })
  return putObject(`${runKey}/${name}`, blob)
}

// ── per-scene asset upload (so the editor preview shows REAL media) ────────────
const STUDIO_PUBLIC = join(PIPELINE_DIR, 'studio', 'public')
const CONTENT_TYPE = {
  '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp',
  '.svg': 'image/svg+xml', '.mp3': 'audio/mpeg', '.wav': 'audio/wav', '.m4a': 'audio/mp4',
  '.mp4': 'video/mp4', '.json': 'application/json',
}
const ctypeFor = (name) => CONTENT_TYPE['.' + (name.split('.').pop() || '').toLowerCase()] || 'application/octet-stream'

function stagedAssetNames(runKey) {
  if (!existsSync(STUDIO_PUBLIC)) return []
  try { return readdirSync(STUDIO_PUBLIC).filter((f) => f.includes(runKey)) } catch { return [] }
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

// ── per-scene thumbnails for the run page filmstrip ──
// The curated path historically produced "cards only" (no thumbs — the web's
// SceneFilmstrip reads a durable props.scene_thumbs {index: url} map that only the
// retired Hermes conduct used to fill). Extract one frame per scene from the
// rendered final.mp4 at each scene's midpoint, upload to <runKey>/thumb-<i>.jpg,
// and return the scene_thumbs map. Best-effort: any failure returns what we have.
async function stageSceneThumbs(runKey, props) {
  try {
    const scenes = props && Array.isArray(props.scenes) ? props.scenes : []
    const finalPath = join(PIPELINE_DIR, 'runs', runKey, 'final.mp4')
    if (!scenes.length || !existsSync(finalPath)) return null
    const fps = Number(props.fps) || 30
    const durs = scenes.map((s) => {
      const f = Number(s && s.durationInFrames)
      if (Number.isFinite(f) && f > 0) return f / fps
      const d = Number((s && s.duration_s) ?? (s && s.data && s.data.duration_s))
      return Number.isFinite(d) && d > 0 ? d : 6
    })
    const thumbs = {}
    let t = 0
    for (let i = 0; i < scenes.length; i++) {
      const mid = t + durs[i] / 2
      t += durs[i]
      const out = join(PIPELINE_DIR, 'runs', runKey, `thumb-${i}.jpg`)
      const ok = await new Promise((res) => {
        const c = spawn('ffmpeg', ['-y', '-ss', mid.toFixed(2), '-i', finalPath,
          '-frames:v', '1', '-vf', 'scale=480:-2', '-q:v', '4', out], { stdio: 'ignore' })
        c.on('error', () => res(false))
        c.on('close', (code) => res(code === 0 && existsSync(out)))
      })
      if (!ok) continue
      try {
        const url = await putObject(`${runKey}/thumb-${i}.jpg`,
          new Blob([readFileSync(out)], { type: 'image/jpeg' }))
        if (url) thumbs[String(i)] = url
      } catch (e) { log(`  ! thumb upload ${i}`, String(e)) }
    }
    const n = Object.keys(thumbs).length
    log(`  scene thumbs: ${n}/${scenes.length} staged`)
    return n ? thumbs : null
  } catch (e) {
    log('  ! stageSceneThumbs', String(e))
    return null
  }
}

// runs.update — THE call that wedged the worker (a 30s InsForge timeout right after
// "PAID … proceeding to conduct"). Now bounded+retried so it can never block >~40s.
async function setRun(runId, patch) {
  const { error } = await ifCall('runs.update', () => db.database.from('runs').update(patch).eq('id', runId))
  if (error) log('  ! runs.update', JSON.stringify(error))
}

// jobs.update — bounded+retried mirror of setRun. Marking a job done/failed must
// never block the loop; if it ultimately fails we log (the wall-clock guard in
// processJob still returns the loop to polling regardless).
async function setJob(jobId, patch) {
  const { error } = await ifCall('jobs.update', () => db.database.from('jobs').update(patch).eq('id', jobId))
  if (error) log('  ! jobs.update', JSON.stringify(error))
}

async function emit(runId, msg, actor = 'filmo', level = 'info') {
  if (!runId) return
  const seq = Date.now() % 1000000000
  const { error } = await ifCall('run_events.insert(emit)',
    () => db.database.from('run_events').insert([{ run_id: runId, seq, level, actor, msg }]))
  if (error) log('  ! emit', JSON.stringify(error))
}

// Stamp the producer onto the run's props (jsonb) — the schema has no `producer`
// column, so props.producer is the durable per-run producer tag the site can read.
function tagProducer(props) {
  const base = (props && typeof props === 'object') ? props : {}
  return { ...base, producer: PRODUCER, produced_on: 'hetzner-vm' }
}

// OPTION A: stamp the cached plan handle onto the run's props so the run carries the
// exact plan_id the produce pass will reuse (durable handle for debugging / audit /
// a re-ship). Merges into existing props (never clobbers other keys).
function tagPlanHandle(props, planId) {
  const base = (props && typeof props === 'object') ? props : {}
  return planId ? { ...base, plan_id: planId, plan_pass: 'hermes-split' } : base
}

// ─────────────────────── Hermes-mode conduct (Phase C / Option A) ─────────────
// Run a Hermes conduct in the NemoClaw sandbox with a given skill + prompt, and
// return the agent's raw final lines. The split (Option A) runs TWO conducts:
//   1. PLAN pass  (filmo-plan)    -> conversion_read, plan, price; prints
//      "Planned: plan_id=<id> price_cents=<n> (<N> scenes)." We park at a REAL
//      Stripe payment between this and the produce pass.
//   2. PRODUCE pass (filmo-produce) -> produce_and_ship ONLY, reusing the cached
//      plan_id; prints "Shipped: <url> (<N> scenes)." (NO re-read/re-plan/re-price.)
// runHermesSkill is the shared spawn+base64+capture plumbing; the two callers
// (runHermesPlan / runHermesProduce) own the per-pass prompt + output parsing.

// POSIX single-quote a string for safe embedding in `bash -lc '...'`.
function shquote(s) { return `'` + String(s).replace(/'/g, `'\\''`) + `'` }

// Spawn ONE `hermes chat -s <skill> -q <prompt>` conduct inside the sandbox and
// resolve { ok, code, raw } with the agent's tail output. NEVER throws — every
// failure is surfaced as { ok:false } so the caller can fall back deterministically.
// (This is the exact proven Phase B plumbing extracted from the old single conduct:
// base64 the whole inner script so the prompt survives every nested shell layer,
// /dev/null stdin so nemoclaw exec doesn't hang, per-job .hermes hygiene wipe.)
function runHermesSkill(skill, prompt) {
  return new Promise((resolve) => {
    // PER-JOB HYGIENE: wipe the agent's writable, job-carrying state in
    // /sandbox/.hermes BEFORE each conduct so one job cannot contaminate the next
    // (e.g. a prompt-injected job planting poisoned memory/session/db state). We
    // remove ONLY the mutable contamination surface — sessions, the session DB,
    // memories, logs, and caches — and PRESERVE config + credentials (.env,
    // config.yaml, auth.json, SOUL.md, bin/, skills/) so the conduct still runs.
    // NOTE: in the SPLIT flow the plan pass and the produce pass are SEPARATE
    // conducts; the cached plan lives in the PIPELINE (runs/<plan_id>/plan.json on
    // the toolserver host), NOT in /sandbox/.hermes, so wiping sandbox state
    // between the two passes does NOT lose the plan — the produce pass re-loads it
    // by plan_id via the MCP tool. The hygiene only resets the agent's own memory.
    const hygiene =
      `for d in sessions memories logs cache audio_cache image_cache; do ` +
      `rm -rf "/sandbox/.hermes/$d" 2>/dev/null; done; ` +
      `rm -f /sandbox/.hermes/state.db /sandbox/.hermes/.skills_prompt_snapshot.json 2>/dev/null; ` +
      `true\n`
    // Inner sandbox script: source the OpenRouter key, run hermes headless (-Q),
    // preload the scoped skill, print the agent's final lines. We pass the ENTIRE
    // inner script (prompt included) as a SINGLE base64 argv token and decode+run
    // it inside the sandbox — eliminating ALL nested-quote fragility across the
    // node->nemoclaw->openshell->bash layers (a mangled `-q` arg made hermes hang
    // on interactive input — the observed "session alive, zero MCP calls" wedge).
    const inner =
      `export HOME=/sandbox\n` +
      `set -a; [ -f /sandbox/.orkey ] && . /sandbox/.orkey; set +a\n` +
      `cd /sandbox\n` +
      hygiene +
      `hermes chat -Q -s ${skill} -q ${shquote(prompt)} 2>&1 | tail -60\n`
    const b64 = Buffer.from(inner, 'utf8').toString('base64')
    // nemoclaw exec uses its OWN --timeout bound (do NOT wrap in a host timeout).
    // The single-quoted b64 has no special chars, so this argv is quote-safe.
    const decodeCmd = `echo ${b64} | base64 -d | bash`
    const args = [HERMES_SANDBOX, 'exec', '--no-tty', '--timeout', String(HERMES_TIMEOUT_S),
                  '--', 'bash', '-c', decodeCmd]
    let out = ''
    let done = false
    // CRITICAL: stdin MUST be /dev/null ('ignore'). node's default spawn gives the
    // child an open stdin pipe; `nemoclaw exec` then waits on that stdin and hangs
    // forever (observed: session alive, zero MCP calls, never returns). Ignoring
    // stdin makes the exec return as it does from an interactive shell.
    const child = spawn(NEMOCLAW_BIN, args, { env: process.env, stdio: ['ignore', 'pipe', 'pipe'] })
    child.stdout.on('data', (d) => { out += d.toString(); try { process.stdout.write(`  [hermes:${skill}] ${d}`) } catch {} })
    child.stderr.on('data', (d) => { out += d.toString(); try { process.stderr.write(`  [hermes:${skill}!] ${d}`) } catch {} })
    child.on('error', (e) => { if (done) return; done = true; resolve({ ok: false, code: -1, error: 'spawn error: ' + String(e), raw: out }) })
    child.on('close', (code) => { if (done) return; done = true; resolve({ ok: code === 0, code, raw: out }) })
  })
}

// PLAN pass (Option A, half 1): conduct conversion_read -> plan -> price via the
// filmo-plan skill, parse the "Planned: plan_id=<id> price_cents=<n> (<N> scenes)."
// line. Returns { ok, planId, priceCents, sceneCount, raw } — NEVER throws.
function runHermesPlan(url, goal, runId) {
  // Scoped prompt: the filmo-plan skill enforces the 3-tool order + the parseable
  // final line, but we restate the scope in the prompt as belt-and-suspenders.
  const prompt =
    `Conduct ONLY the read->plan->price half of the curated Filmo pipeline for ` +
    `url=${url} with goal=${JSON.stringify(goal)}. ` +
    `Pass run_id=${runId} to EVERY tool so the live activity feed records each step. ` +
    `Call exactly three tools, once each, in order: conversion_read, plan, price. ` +
    `Do NOT call gate or produce_and_ship — production happens in a LATER pass ` +
    `after the customer pays. Pass the plan_id handle (not the full plan) from ` +
    `plan into price. ` +
    `End with EXACTLY this line: ` +
    `Planned: plan_id=<the plan_id> price_cents=<the integer price_cents> (<N> scenes).`
  return runHermesSkill(HERMES_PLAN_SKILL, prompt).then((res) => {
    const out = res.raw || ''
    // Parse "Planned: plan_id=<id> price_cents=<n> (N scenes)." (order/spacing tolerant).
    const planId = (out.match(/plan_id\s*[=:]\s*([A-Za-z0-9._-]+)/i) || [])[1] || null
    const priceM = out.match(/price_cents\s*[=:]\s*(\d+)/i)
    const priceCents = priceM ? Number(priceM[1]) : null
    const sceneM = out.match(/\((\d+)\s*scenes?\)/i)
    const sceneCount = sceneM ? Number(sceneM[1]) : null
    if (planId && priceCents != null && priceCents > 0) {
      return { ok: true, planId, priceCents, sceneCount, raw: out }
    }
    return { ok: false, error: `plan pass: no parseable Planned line (planId=${planId}, priceCents=${priceCents}, exit ${res.code})`, raw: out }
  })
}

// PRODUCE pass (Option A, half 2): conduct produce_and_ship ONLY via the
// filmo-produce skill, REUSING the cached plan_id (no re-read/re-plan/re-price).
// Parse the "Shipped: <url> (N scenes)." line. Returns { ok, finalUrl, sceneCount,
// raw } — NEVER throws.
function runHermesProduce(url, planId, runId) {
  const prompt =
    `Conduct ONLY the produce->ship half of the curated Filmo pipeline. The ` +
    `product was already read, planned, and priced, and the customer has PAID. ` +
    `Reuse the EXISTING plan via its handle: call produce_and_ship exactly once ` +
    `with url=${url}, plan_id=${planId}, and run_id=${runId}. ` +
    `Do NOT call conversion_read, plan, price, or gate — they already ran and the ` +
    `customer paid against that exact plan. ` +
    `End with the Shipped line containing the final_url.`
  return runHermesSkill(HERMES_PRODUCE_SKILL, prompt).then((res) => {
    const out = res.raw || ''
    const shipped = out.match(/Shipped:\s*(\S+)\s*(?:\((\d+)\s*scenes?\))?/i)
    if (shipped && /^https?:\/\//i.test(shipped[1])) {
      return { ok: true, finalUrl: shipped[1].replace(/[.,)]+$/, ''), sceneCount: shipped[2] ? Number(shipped[2]) : null, raw: out }
    }
    return { ok: false, error: `produce pass: no Shipped line (exit ${res.code})`, raw: out }
  })
}

// SINGLE atomic conduct (legacy / fallback / auto path when HERMES_SPLIT=false):
// the filmo-producer skill drives all five tools end-to-end in ONE conduct
// (conversion_read -> plan -> price -> gate -> produce_and_ship) and prints the
// Shipped line. Kept intact for reversibility — if the split is disabled this is
// the exact previous behaviour. Returns { ok, finalUrl, sceneCount, declined, raw }.
function runHermesConduct(url, goal, budgetCents, runId) {
  const prompt =
    `Conduct the curated Filmo pipeline end-to-end for url=${url} ` +
    `with goal=${JSON.stringify(goal)} and budget_cents=${budgetCents}. ` +
    `Pass run_id=${runId} to EVERY one of the five filmo-host MCP tools so the ` +
    `live activity feed records each step. ` +
    `Call the five tools exactly once each in order ` +
    `(conversion_read, plan, price, gate, produce_and_ship). Pass the plan_id ` +
    `handle (not the full plan) from plan into price and produce_and_ship. ` +
    `End with the Shipped line containing the final_url.`
  return runHermesSkill(HERMES_SKILL, prompt).then((res) => {
    const out = res.raw || ''
    const shipped = out.match(/Shipped:\s*(\S+)\s*(?:\((\d+)\s*scenes?\))?/i)
    const declined = /Gate declined/i.test(out)
    if (shipped && /^https?:\/\//i.test(shipped[1])) {
      return { ok: true, finalUrl: shipped[1].replace(/[.,)]+$/, ''), sceneCount: shipped[2] ? Number(shipped[2]) : null, raw: out }
    } else if (declined) {
      return { ok: false, declined: true, error: 'gate declined', raw: out }
    }
    return { ok: false, error: `no Shipped line (exit ${res.code})`, raw: out }
  })
}

// OPTION A robustness: recover an already-shipped video after a produce-pass that
// FAILED to print its Shipped line. The produce_and_ship MCP tool uploads the
// rendered video to walk-videos under `<plan_id>/video.mp4` BEFORE the agent emits
// its final reply — so if the agent stalls on the closing line (550B reply latency)
// and the conduct times out, the video is ALREADY in the bucket. We list the bucket
// for that object and return its public URL so the claimer can deliver the
// Hermes-produced video (producer=hetzner-hermes, REAL price preserved) WITHOUT a
// wasteful deterministic re-render that would also recompute (overwrite) the price.
// Returns { finalUrl, sceneCount } or null if nothing shipped. NEVER throws.
async function recoverByPrefix(prefix) {
  if (!prefix) return null
  const { data, error } = await ifCall(`storage.list(recover ${prefix})`,
    () => db.storage.from(BUCKET).list({ prefix: `${prefix}/`, limit: 200 }),
    { attempts: 2, timeoutMs: 10000 })
  if (error) { log(`  ! recover list ${prefix}`, JSON.stringify(error)); return null }
  const objs = (data && data.data) || data || []
  let finalUrl = null
  let sceneCount = 0
  for (const o of objs) {
    const key = o.key || o.name || ''
    if (key.endsWith('/video.mp4') || key === `${prefix}/video.mp4`) finalUrl = o.url || null
    if (/\/thumbs\/scene-\d+\.png$/.test(key)) sceneCount++
  }
  if (finalUrl && /^https?:\/\//i.test(finalUrl)) {
    return { finalUrl, sceneCount: sceneCount || null }
  }
  return null
}

// G5 DESYNC RECOVERY: unlike the Hermes recover (video.mp4 only), a desynced run
// may be a DETERMINISTIC build whose video landed as final.mp4 under the run_key
// prefix (e.g. web-...-c4bgo/final.mp4). Accept EITHER video.mp4 or final.mp4 under
// the run-UUID prefix OR the run_key prefix, so the reaper links a real shipped
// video instead of marking a deliverable run failed. Best-effort; NEVER throws.
async function recoverAnyVideo(runId, runKey) {
  for (const prefix of [runId, runKey]) {
    if (!prefix) continue
    const { data, error } = await ifCall(`storage.list(desync ${prefix})`,
      () => db.storage.from(BUCKET).list({ prefix: `${prefix}/`, limit: 200 }),
      { attempts: 2, timeoutMs: 10000 })
    if (error) continue
    const objs = (data && data.data) || data || []
    for (const o of objs) {
      const key = o.key || o.name || ''
      if ((key.endsWith('/video.mp4') || key.endsWith('/final.mp4')) && o.url && /^https?:\/\//i.test(o.url)) {
        return { finalUrl: o.url }
      }
    }
  }
  return null
}

// G2 FIX: the produce tool now uploads video.mp4 under the DB run UUID
// (<run_id>/video.mp4), NOT the url-slug plan_id — so conducts of the same site
// never overwrite each other. Recover therefore lists the per-run UUID prefix
// FIRST. We still fall back to the legacy slug prefix (<planId>/) so this also
// recovers a video shipped under the old scheme (e.g. a conduct mid-flight during
// the toolserver swap) — runId is preferred because it can never collide.
async function recoverShippedVideo(runId, planId) {
  // FRESHNESS-SAFE recover: ONLY the per-run UUID prefix. The video the produce
  // tool ships for THIS run lands at <run_id>/video.mp4 (G2: unique per run), so a
  // recovered runId object can only be THIS run's video. The legacy slug prefix
  // (planId, e.g. `stripe-com-mcp/`) is SHARED by every conduct of the same URL —
  // an ancient object left there was being re-delivered as a "fresh" paid video
  // (this silently re-shipped one Jun-30 stripe render for ~1.3 days). If nothing
  // fresh exists under runId (e.g. the render FAILED and produce uploaded nothing),
  // return null so the caller falls through to a FRESH deterministic re-render
  // (curated-claimer.js:1183) instead of shipping a stale slug object. planId is
  // retained in the signature for call-site compatibility but intentionally unused.
  if (runId) {
    const byRun = await recoverByPrefix(runId)
    if (byRun && byRun.finalUrl) return byRun
  }
  return null
}

// RECOVER-PATH REPAIR: when recoverShippedVideo delivers an already-shipped Hermes
// video, the rich render props live under runs/<planId>/props.json (the MCP produce
// tool's brand-derived render run_key) — which deliverHermesRun's readProps(jobRunKey)
// cannot see, so the run would be delivered with THIN props (editor shows 0 scenes +
// blank logo/screenshot/VO). Re-run the produce tool's OWN asset verify-and-heal +
// rich-props merge (mcp_toolserver.py --heal-recovered, a short-lived CLI process that
// does NOT touch the running MCP server) against that local render dir, so runs.props
// lands scenes[] and every editor asset resolves under the DB run_key namespace.
// Best-effort + bounded: NEVER throws and can never pin the worker. Returns the parsed
// summary (or { ok:false, ... }); deliverHermesRun then persists the now-rich props.
function healRecoveredRun(runId, planId) {
  return new Promise((resolve) => {
    if (!runId || !planId) { resolve({ ok: false, error: 'missing runId/planId' }); return }
    let out = '', err = '', done = false
    let timer = null
    const finish = (v) => { if (done) return; done = true; if (timer) clearTimeout(timer); resolve(v) }
    const child = spawn(PYTHON_BIN, [TOOLSERVER_PY, '--heal-recovered', String(runId), String(planId)],
      { cwd: PIPELINE_DIR, env: { ...process.env, PIPELINE_DIR, HOME: process.env.HOME || '/root' },
        stdio: ['ignore', 'pipe', 'pipe'] })
    timer = setTimeout(() => { try { child.kill('SIGKILL') } catch {}; finish({ ok: false, error: 'heal-recovered timeout' }) }, HEAL_TIMEOUT_MS)
    child.stdout.on('data', (d) => { out += d.toString() })
    child.stderr.on('data', (d) => { err += d.toString(); try { process.stderr.write(`  [heal!] ${d}`) } catch {} })
    child.on('error', (e) => finish({ ok: false, error: 'spawn: ' + String(e) }))
    child.on('close', (code) => {
      // The helper prints exactly one JSON summary line to stdout (_log -> stderr).
      let parsed = null
      for (const line of out.trim().split('\n').reverse()) { try { parsed = JSON.parse(line); break } catch {} }
      finish(parsed || { ok: code === 0, code, raw: (out || err).slice(-400) })
    })
  })
}

// ── Delivery email (AgentMail) ───────────────────────────────────────────────
// Resolve a run owner's email from their user_id via the InsForge admin auth API.
// VERIFIED working endpoint (2026-06-30, READ-ONLY against live InsForge):
//   GET <BASE_URL>/api/auth/users/<user_id>  (admin bearer) -> 200 { id, email, ... }
// (The DB has no public.users table, and /api/auth/users?id=eq.<uid> IGNORES the
// filter and lists ALL users — so we use the single-user path, which returns the
// email for exactly that id.) Best-effort: NEVER throws; returns a trimmed email
// string or null. Bounded so a hung request can't pin the worker.
async function lookupUserEmail(userId) {
  if (!userId || typeof userId !== 'string') return null
  if (!API_KEY) { log('  notify: no INSFORGE_API_KEY for user-email lookup; skipping'); return null }
  const url = `${BASE_URL.replace(/\/+$/, '')}/api/auth/users/${encodeURIComponent(userId)}`
  try {
    const ctrl = new AbortController()
    const t = setTimeout(() => { try { ctrl.abort() } catch {} }, 10000)
    let res
    try {
      res = await fetch(url, { headers: { Authorization: `Bearer ${API_KEY}` }, signal: ctrl.signal })
    } finally { clearTimeout(t) }
    if (!res.ok) { log(`  notify: user-email lookup ${userId} -> HTTP ${res.status}; skipping email`); return null }
    const j = await res.json().catch(() => null)
    const email = j && typeof j.email === 'string' ? j.email.trim() : null
    return email || null
  } catch (e) {
    log(`  notify: user-email lookup failed (${(e && e.message) || e}); skipping email`)
    return null
  }
}

// A pragmatic, deliverability-minded email sanity check (not RFC-perfect): one @, a
// dotted domain, no spaces. Filters obviously non-deliverable values so we don't fire
// the API at junk. (Synthetic test addresses like ...@walk.studio still pass shape —
// AgentMail's own bounce handling is the backstop; we only gate on STRUCTURE here.)
function looksLikeEmail(addr) {
  return typeof addr === 'string' && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(addr.trim())
}

// Best-effort "Your Filmo video is ready" email via AgentMail. NEVER throws. Logs a
// success line with the returned message_id, or the reason it skipped / failed. Does
// NOT block or delay the delivery (the caller already persisted the delivered state).
// Skips cleanly when AGENTMAIL_API_KEY or a valid userEmail is missing.
async function notifyVideoReady(runId, finalUrl, userEmail) {
  try {
    if (!AGENTMAIL_API_KEY) { log(`  notify: AGENTMAIL_API_KEY not set; skipping ready-email for run ${runId}`); return }
    if (!looksLikeEmail(userEmail)) { log(`  notify: no valid user email for run ${runId} (got ${JSON.stringify(userEmail)}); skipping`); return }
    const to = userEmail.trim()
    const runLink = `${FILMO_SITE_BASE}/runs/${encodeURIComponent(String(runId))}`
    const subject = '\u{1F3AC} Your Filmo video is ready'
    const preheader = 'Your launch video is rendered — watch, edit, or download it now.'
    const text = [
      'Your Filmo video is ready.',
      '',
      'We’ve finished producing your launch video. Watch, edit, or download it here:',
      runLink,
      '',
      '— Filmo',
    ].join('\n')
    const html = `<!doctype html><html><body style="margin:0;padding:0;background:#f6f7f9;">
<span style="display:none;max-height:0;overflow:hidden;opacity:0;">${preheader}</span>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f6f7f9;padding:32px 0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
<tr><td align="center">
<table role="presentation" width="480" cellpadding="0" cellspacing="0" style="max-width:480px;width:100%;background:#ffffff;border:1px solid #eceef1;border-radius:16px;overflow:hidden;">
<tr><td style="padding:32px 36px 0;">
<div style="font-size:20px;font-weight:700;letter-spacing:-0.01em;color:#0b0f1a;">Filmo</div>
</td></tr>
<tr><td style="padding:20px 36px 0;">
<div style="font-size:22px;line-height:1.3;font-weight:700;letter-spacing:-0.01em;color:#0b0f1a;">Your video is ready \u{1F3AC}</div>
<p style="margin:12px 0 0;font-size:15px;line-height:1.55;color:#475067;">We’ve finished producing your launch video. Watch it, fine-tune it in the editor, or download the final cut.</p>
</td></tr>
<tr><td style="padding:24px 36px 4px;">
<a href="${runLink}" style="display:inline-block;background:#3B82F6;color:#ffffff;text-decoration:none;font-size:15px;font-weight:600;padding:12px 22px;border-radius:10px;">Watch your video →</a>
</td></tr>
<tr><td style="padding:14px 36px 32px;">
<p style="margin:0;font-size:12px;line-height:1.5;color:#8a93a6;">Or paste this link into your browser:<br><a href="${runLink}" style="color:#3B82F6;text-decoration:none;word-break:break-all;">${runLink}</a></p>
</td></tr>
</table>
<div style="font-size:11px;color:#aab2c0;padding:18px 0 0;">Filmo — AI launch videos</div>
</td></tr>
</table>
</body></html>`

    const endpoint = `https://api.agentmail.to/v0/inboxes/${encodeURIComponent(AGENTMAIL_INBOX)}/messages/send`
    const ctrl = new AbortController()
    const t = setTimeout(() => { try { ctrl.abort() } catch {} }, 15000)
    let res
    try {
      res = await fetch(endpoint, {
        method: 'POST',
        headers: { Authorization: `Bearer ${AGENTMAIL_API_KEY}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ to, subject, html, text }),
        signal: ctrl.signal,
      })
    } finally { clearTimeout(t) }
    const bodyText = await res.text().catch(() => '')
    if (!res.ok) {
      log(`  notify: AgentMail send FAILED for run ${runId} -> HTTP ${res.status} ${bodyText.slice(0, 300)}`)
      return
    }
    let parsed = null; try { parsed = JSON.parse(bodyText) } catch {}
    const messageId = (parsed && parsed.message_id) || '(no message_id in 200 body)'
    log(`  notify: ready-email SENT for run ${runId} to ${to} [message_id=${messageId}]`)
  } catch (e) {
    // Absolutely never let a notification problem touch the delivery path.
    log(`  notify: ready-email errored for run ${runId} (${(e && e.message) || e}); ignored`)
  }
}

// Deliver a Hermes-produced run: stamp final_url + producer=hetzner-hermes,
// mark the job done, emit a producer line. Returns true on success.
//
// `planId` (optional): on the Hermes split path the render ran under run_key=<planId>,
// so the rich props.json lives at runs/<planId>/props.json — pass it so we source the
// rich props locally even when the JOB run_key dir is absent (the recover path).
async function deliverHermesRun(job, runId, runKey, finalUrl, sceneCount, t0, planId) {
  // Preserve any keys the MCP tools already wrote onto runs.props (the FILMSTRIP
  // scenes[] + scene_thumbs{} mirror is patched there mid-conduct). The Hermes
  // path's local runs/<runKey>/props.json may not exist (the render ran inside
  // the MCP tool under a different run_key), so DON'T start from the local file:
  // fetch the live runs.props column and merge the producer tags into it. This
  // keeps the durable, no-parse filmstrip source intact instead of clobbering it.
  let existingProps = {}
  // Also fetch the run's already-persisted price/cogs so we NEVER clobber the REAL
  // price the OPTION-A plan pass wrote (price_cents=<real>) with a null mapped value
  // when the local ledger lacks pnl (the Hermes render ran inside the MCP tool, not
  // via build_runner, so runs/<runKey>/ledger.json usually has no pricing).
  let curPrice = null, curCogs = null, curUserId = null
  const { data: cur } = await ifCall('runs.select(props,price)',
    () => db.database.from('runs').select('props, price_cents, cogs_cents, user_id').eq('id', runId).maybeSingle())
  if (cur && cur.props && typeof cur.props === 'object') existingProps = cur.props
  if (cur && typeof cur.price_cents === 'number') curPrice = cur.price_cents
  if (cur && typeof cur.cogs_cents === 'number') curCogs = cur.cogs_cents
  if (cur && typeof cur.user_id === 'string') curUserId = cur.user_id
  // On the Hermes path the render ran under run_key=<planId> (the MCP produce tool's
  // brand-derived run dir), so the rich props.json lives at runs/<planId>/props.json —
  // NOT runs/<jobRunKey>/ (which usually doesn't exist). Prefer it as the local rich
  // fallback; existingProps (freshly fetched — already enriched by the heal pass on the
  // recover path, or by the MCP tool mid-conduct on the success path) still wins for
  // shared keys, so we keep the healed full-URL asset refs. This is what makes a
  // RECOVERED run land rich instead of thin.
  const localProps = (planId && readProps(planId)) || readProps(runKey) || {}
  const props = { ...localProps, ...existingProps, producer: HERMES_PRODUCER, produced_on: 'hetzner-vm', conducted_by: 'hermes' }
  // The ledger may not exist (the render happened inside the MCP tool, not via
  // build_runner), so map conservatively and trust the agent's final_url.
  const ledger = readLedger(runKey) || {}
  const mapped = mapLedgerToRun(ledger)
  // Price/cogs: prefer the ledger value, else KEEP the already-persisted real value
  // (do not write null over the plan pass's real price).
  if (mapped.price_cents == null && curPrice != null) mapped.price_cents = curPrice
  if (mapped.cogs_cents == null && curCogs != null) mapped.cogs_cents = curCogs
  await setRun(runId, { ...mapped, status: 'delivered', phase: 'delivered', final_url: finalUrl, props })
  await setJob(job.id, { status: 'done' })
  // G4 FIX: setRun/setJob wrap ifCall and NEVER throw — on ultimate failure they
  // just log and return, so a transient InsForge outage at this exact instant would
  // leave a fully-produced video showing 'producing'/'running' forever with final_url
  // null and no retry. Re-read the row; if the flip didn't land, re-stamp the run
  // delivered with the KNOWN finalUrl and flag ship_retryable=true (mirroring the
  // deterministic upload-failed guard) so the reaper / a sweep can re-stamp it
  // instead of stranding it. Best-effort: never throws, never blocks the success path.
  try {
    const { data: chk } = await ifCall('runs.select(deliver-verify)',
      () => db.database.from('runs').select('status, final_url').eq('id', runId).maybeSingle())
    if (!chk || chk.status !== 'delivered' || !chk.final_url) {
      log(`  !! deliver flip did NOT land for run ${runKey} (status=${chk && chk.status}, final_url=${chk && chk.final_url ? 'set' : 'null'}); re-stamping with ship_retryable + known final_url`)
      await setRun(runId, { status: 'delivered', phase: 'delivered', final_url: finalUrl, props: { ...props, ship_retryable: true, recovered_final_url: finalUrl } })
      await setJob(job.id, { status: 'done' })
    }
  } catch (e) { log('  deliver-verify failed', String(e && e.message || e)) }
  // Best-effort "your video is ready" email. The deliver writes above are already
  // persisted; this lookup + send is fire-and-forget and NEVER blocks, delays, or
  // fails the delivery — notifyVideoReady swallows all errors internally and we still
  // await it (it self-bounds) so its success/failure log lands in order. A run with
  // no user_id (or a failed lookup) simply skips, logged.
  const notifyEmail = curUserId ? await lookupUserEmail(curUserId) : null
  await notifyVideoReady(runId, finalUrl, notifyEmail)
  const totalSec = ((Date.now() - t0) / 1000).toFixed(1)
  await emit(runId, `Conducted by Hermes on Hetzner VM (producer=${HERMES_PRODUCER})${sceneCount ? `, ${sceneCount} scenes` : ''}. ${totalSec}s total.`)
  log(`  DELIVERED run ${runKey} -> ${finalUrl}  [${totalSec}s, producer=${HERMES_PRODUCER}, conducted_by=hermes]`)
  return true
}

// ── Pre-conduct Stripe TEST payment gate helpers ────────────────────────────
// Run gate.py create/status as a subprocess; resolve its parsed JSON. NEVER throws.
// gate.py imports stripe_earn from PIPELINE_DIR and reads the TEST key from
// ~/.hermes/.env (so pass PIPELINE_DIR + HOME). It NEVER prints the key.
function runGatePy(args) {
  return new Promise((resolve) => {
    const child = spawn(PYTHON_BIN, [GATE_PY, ...args],
      { cwd: PIPELINE_DIR, env: { ...process.env, PIPELINE_DIR, HOME: process.env.HOME || '/root' },
        stdio: ['ignore', 'pipe', 'pipe'] })
    let out = '', err = ''
    child.stdout.on('data', (d) => { out += d.toString() })
    child.stderr.on('data', (d) => { err += d.toString() })
    child.on('error', (e) => resolve({ ok: false, error: 'spawn: ' + String(e) }))
    child.on('close', (code) => {
      const body = (out.trim() || err.trim())
      let parsed = null; try { parsed = JSON.parse(body) } catch {}
      if (code === 0 && parsed && !parsed.error) resolve({ ok: true, ...parsed })
      else resolve({ ok: false, error: (parsed && parsed.error) || `gate.py exit ${code}`, raw: body })
    })
  })
}

// Pre-conduct payment gate. Creates a Stripe TEST Checkout, parks the run at
// awaiting_payment with checkout_url + price (so the run page shows the Pay button),
// then polls get_session_status until 'paid' or timeout. Returns true when paid;
// false on create-failure / timeout (caller must NOT proceed to produce). On any
// non-paid outcome the run + job are left in a clean failed state.
//
// OPTION A: `realPriceCents` is the REAL price the plan pass computed (from the
// price tool, already capped at $10 server-side). We charge that — NOT the flat
// $10 cap. The GATE_PRICE_CENTS cap is kept as a defensive CEILING here:
// price = min(real, cap), so a parsing slip can never overcharge. A missing/
// non-positive real price falls back to the cap (the previous behaviour) so the
// gate still produces a valid Checkout rather than refusing a $0 session.
async function paymentGate(job, runId, runKey, safeUrl, realPriceCents) {
  const haveReal = Number.isInteger(realPriceCents) && realPriceCents > 0
  const priceCents = haveReal ? Math.min(realPriceCents, GATE_PRICE_CENTS) : GATE_PRICE_CENTS
  const brand = String(safeUrl || '').replace(/^https?:\/\//, '').replace(/^www\./, '').split('/')[0] || 'your product'
  const productName = `${brand} promo video`
  const successUrl = `${FILMO_PUBLIC_BASE}/runs/${runId}?paid=1`
  const cancelUrl = `${FILMO_PUBLIC_BASE}/runs/${runId}?cancelled=1`
  await emit(runId, `Payment gate: creating Stripe TEST checkout for $${(priceCents/100).toFixed(2)}\u2026`, 'stripe')
  const created = await runGatePy(['create', '--run-id', String(runId), '--amount-cents', String(priceCents),
    '--currency', GATE_CURRENCY, '--product-name', productName, '--success-url', successUrl, '--cancel-url', cancelUrl])
  if (!created.ok || !created.checkout_url) {
    await setRun(runId, { status: 'failed', phase: 'checkout_failed' })
    await setJob(job.id, { status: 'failed', error: 'checkout create failed: ' + (created.error || 'no url') })
    await emit(runId, `Could not create Stripe checkout (${created.error || 'no url'}).`, 'stripe', 'error')
    log(`  CHECKOUT FAILED run ${runKey}: ${created.error}`)
    return false
  }
  // Park the run so the run page's PayPanel renders: phase + checkout_url + price.
  await setRun(runId, { status: 'running', phase: 'awaiting_payment', price_cents: priceCents, checkout_url: created.checkout_url })
  await emit(runId, `Awaiting payment \u2014 Stripe TEST Checkout ${created.session_id} ($${(priceCents/100).toFixed(2)}). Pay with test card 4242.`, 'stripe')
  log(`  awaiting payment run ${runKey}: ${created.checkout_url} (livemode=${created.livemode})`)

  const deadline = Date.now() + PAYMENT_TIMEOUT_MS
  let lastStatus = created.payment_status || 'unpaid'
  for (;;) {
    const st = await runGatePy(['status', '--session', created.session_id])
    const status = (st.ok && st.payment_status) ? st.payment_status : lastStatus
    lastStatus = status
    if (status === 'paid' || status === 'no_payment_required') {
      // OPTION A: read/plan/price ALREADY ran (before this gate) \u2014 the next step is
      // production. Clear awaiting_payment by advancing straight to 'producing' so
      // the UI steps FORWARD (never back to Planning). The produce pass's
      // produce_and_ship tool also _set_phase("producing") at its start; setting it
      // here first avoids a flash of the old phase between paid and the conduct.
      await setRun(runId, { phase: 'producing' })
      await emit(runId, `Payment received ($${(priceCents/100).toFixed(2)}, test 4242). Releasing production.`, 'stripe')
      log(`  PAID run ${runKey} \u2014 proceeding to produce (plan already cached)`)
      return true
    }
    if (Date.now() >= deadline) {
      await setRun(runId, { status: 'failed', phase: 'payment_timeout' })
      await setJob(job.id, { status: 'failed', error: 'payment gate timed out (no payment received)' })
      await emit(runId, `Payment gate timed out after ${(PAYMENT_TIMEOUT_MS/60000)|0} min \u2014 no payment received; build cancelled.`, 'stripe', 'warn')
      log(`  PAYMENT TIMEOUT run ${runKey}`)
      return false
    }
    await sleep(PAYMENT_POLL_MS)
  }
}

// ───────────────────────── re-render (editor Export #87) ─────────────────────
// A `rerender` job re-renders the run's EDITED props (runs.props_edited, durable in
// InsForge) into a NEW edited.mp4. It SKIPS capture/plan/price/SSRF-gate (those ran
// for the original build) and NEVER calls assertPublicUrl. Ported from worker/run.js.
const STUDIO_DIR = join(PIPELINE_DIR, 'studio')

// Download every bucket object under <runKey>/ into studio/public/ so the render
// resolves the per-scene assets via staticFile. Skips final.mp4 / edited.mp4 / json.
async function downloadRunAssets(runKey) {
  if (!existsSync(STUDIO_PUBLIC)) mkdirSync(STUDIO_PUBLIC, { recursive: true })
  let objs = []
  {
    const { data, error } = await ifCall('storage.list',
      () => db.storage.from(BUCKET).list({ prefix: `${runKey}/`, limit: 200 }))
    if (error) { log('  ! list assets', JSON.stringify(error)); return 0 }
    objs = (data && data.data) || data || []
  }
  let ok = 0
  for (const o of objs) {
    const key = o.key || o.name
    if (!key) continue
    const base = key.split('/').pop()
    if (!base || base === 'final.mp4' || base === 'edited.mp4' || base.endsWith('.json')) continue
    try {
      const { data: blob, error } = await ifCall(`storage.download ${key}`,
        () => db.storage.from(BUCKET).download(key), { attempts: 3, timeoutMs: 120000 })
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
// Mirrors worker/run.js runRender (same remotion invocation + cwd + PATH).
function runRender(absPropsPath, outPath) {
  return new Promise((resolve) => {
    const env = {
      ...process.env,
      PATH: join(STUDIO_DIR, 'node_modules', '.bin') + (process.env.PATH ? ':' + process.env.PATH : ''),
    }
    const args = ['render', 'src/index.ts', 'Timeline', outPath,
      '--codec=h264', '--concurrency=50%', `--props=${absPropsPath}`]
    const child = spawn('remotion', args, { cwd: STUDIO_DIR, env })
    child.on('error', (e) => { log('  ! remotion spawn', String(e)); resolve(1) })
    child.stdout.on('data', (d) => { try { process.stdout.write(`  [rmx] ${d}`) } catch {} })
    child.stderr.on('data', (d) => { try { process.stderr.write(`  [rmx!] ${d}`) } catch {} })
    child.on('close', (c) => resolve(c))
  })
}

async function failRerenderJob(job, reason) {
  log(`  RERENDER FAILED ${job.id}: ${reason}`)
  await setJob(job.id, { status: 'failed', error: String(reason) })
}

async function processReRender(job) {
  const p = job.params || {}
  const runId = job.run_id
  const runKey = p.run_key || p.runKey
  log(`claimed RERENDER job ${job.id} -> run ${runKey}`)
  await setRun(runId, { phase: 'rerendering' })
  await emit(runId, 'Edit export: re-rendering your edited video…')

  // Pull the edited props (durable). Fall back to clean props if no edit was saved.
  const { data: run, error } = await ifCall('runs.select(rerender)',
    () => db.database.from('runs').select('props, props_edited').eq('id', runId).maybeSingle())
  if (error || !run) { log('  ! rerender: run not found', JSON.stringify(error)); await failRerenderJob(job, 'run not found'); await emit(runId, 'Re-render failed: run not found.', 'filmo', 'error'); return }
  const edited = run.props_edited && Array.isArray(run.props_edited.scenes) ? run.props_edited : run.props
  if (!edited || !Array.isArray(edited.scenes)) { await failRerenderJob(job, 'no edited props'); await emit(runId, 'Re-render failed: nothing to render.', 'filmo', 'error'); return }

  // Make a working copy; strip the hosted asset base so the render reads local
  // studio/public files via staticFile (we download the run's assets below).
  const props = structuredClone(edited)
  delete props.assetBaseUrl

  // Pull the run's per-scene assets back into studio/public for the render.
  await downloadRunAssets(runKey)

  const propsPath = join(PIPELINE_DIR, 'runs', runKey, 'props.edited.json')
  try {
    mkdirSync(join(PIPELINE_DIR, 'runs', runKey), { recursive: true })
    writeFileSync(propsPath, JSON.stringify(props, null, 2))
  } catch (e) { await failRerenderJob(job, 'write props: ' + e); await emit(runId, 'Re-render failed: could not stage props.', 'filmo', 'error'); return }

  const outPath = join(PIPELINE_DIR, 'runs', runKey, 'edited.mp4')
  await emit(runId, 'Rendering edited cut…')
  const code = await runRender(propsPath, outPath)
  if (code !== 0 || !existsSync(outPath)) { await failRerenderJob(job, `remotion exit ${code}`); await emit(runId, 'Re-render failed during rendering.', 'filmo', 'error'); return }

  const url = await uploadVideo(runKey, 'edited.mp4')
  await setRun(runId, { edited_url: url, phase: 'delivered', status: 'delivered' })
  await setJob(job.id, { status: 'done' })
  await emit(runId, 'Edited video ready.')
  log(`  RERENDER delivered run ${runKey} (${url ? 'uploaded' : 'NO video'})`)
}

async function processDirectorJob(job) {
  const p = job.params || {}
  const runKey = p.run_key || p.runKey
  // REPLICA AFFINITY: a director edit re-renders from the builder's working
  // files (stops.json + clips) which live on ONE replica's disk. If this
  // replica doesn't hold them, bounce the job back to the queue so the
  // sibling can claim it; after 3 bounces proceed anyway — director_job
  // answers gracefully when the files are truly gone.
  const bounces = Number(p._affinity || 0)
  if (!existsSync(join(PIPELINE_DIR, 'runs', String(runKey), 'stops.json'))
      && bounces < 3) {
    log(`director job ${job.id}: run files not on ${WORKER_ID} — bounce ${bounces + 1}/3`)
    await sleep(1500 + Math.floor(Math.random() * 2500))
    await setJob(job.id, {
      status: 'queued', claimed_at: null, claimed_by: null,
      params: { ...p, _affinity: bounces + 1 },
    })
    return
  }
  log(`director job ${job.id} -> run ${runKey}`)
  const code = await new Promise((resolve) => {
    const child = spawn(PYTHON_BIN,
      [join(PIPELINE_DIR, 'director_job.py'),
       '--run-key', String(runKey),
       '--run-id', String(job.run_id || ''),
       '--message', String(p.message || '')],
      { cwd: PIPELINE_DIR, env: process.env })
    child.stdout.on('data', (d) => { try { process.stdout.write(`  [dir] ${d}`) } catch {} })
    child.stderr.on('data', (d) => { try { process.stderr.write(`  [dir!] ${d}`) } catch {} })
    child.on('error', () => resolve(1))
    child.on('close', (c) => resolve(c ?? 1))
  })
  await setJob(job.id, code === 0 ? { status: 'done' }
    : { status: 'failed', error: `director exit ${code}` })
}

// ───────────────────────────── processJob ─────────────────────────────
async function processJob(job) {
  const p = job.params || {}
  const runId = job.run_id
  const runKey = p.run_key || p.runKey
  // #87 EXPORT FIX: a rerender job (editor Export) re-renders edited props only —
  // SKIP capture/plan/price AND the SSRF assertPublicUrl gate (those ran for the
  // original build). Must branch BEFORE the url read below.
  if (job.type === 'rerender' || p.from === 'props_edited') {
    return processReRender(job)
  }
  // Walkrec beta: director chat turns are jobs too — ONE python director
  // implementation; the reply + any re-render narrate via agent_events.
  if (job.type === 'director') {
    return processDirectorJob(job)
  }
  const url = p.company_url || p.url
  const t0 = Date.now()
  const activeProducer = CLAIMER_MODE === 'hermes' ? HERMES_PRODUCER : PRODUCER
  CURRENT_CLAIMED_JOB_ID = job.id
  log(`claimed job ${job.id} -> run ${runKey} (${url}) [mode=${CLAIMER_MODE}, producer=${activeProducer}]`)
  await setRun(runId, { status: 'running', phase: 'planning' })

  // 0) SECURITY: SSRF guard FIRST — refuse private/internal/metadata targets
  //    BEFORE any egress / pipeline subprocess is spawned.
  let safeUrl = url
  try {
    const safe = await assertPublicUrl(url)
    safeUrl = safe.url
    log(`  ssrf guard ok: ${safe.host} is public`)
  } catch (e) {
    const reason = 'unsafe url: ' + String(e && e.message || e)
    await setRun(runId, { status: 'failed', phase: 'blocked_url' })
    await setJob(job.id, { status: 'failed', error: reason })
    await emit(runId, reason, 'filmo', 'error')
    log(`  BLOCKED run ${runKey}: ${reason}`)
    return
  }

  // OPTION A flow: the payment gate now fires BETWEEN price and produce (inside the
  // split block below), so it parks with the REAL computed price + the already-built
  // plan. The gate fires only when PAYMENTS_REQUIRED (default true) AND
  // pay_mode==='human'; auto jobs and PAYMENTS_REQUIRED=false go straight through.
  // On create-fail / timeout the run is marked failed inside paymentGate and we
  // return (NEVER produce an unpaid job).
  //   `paidViaGate` lets the deterministic FALLBACK path below auto-resolve its own
  //   build_runner._payment_gate (PRODUCER_SIMULATE_PAID=1) so a fallback after a
  //   collected payment can NEVER charge a second time.
  let paidViaGate = false
  const payMode = (p.pay_mode || 'auto')

  // ── 0.5) HERMES MODE + OPTION A SPLIT ───────────────────────────────────────
  // The CONDUCT is split so payment is parked between PRICE and PRODUCE:
  //   read -> plan -> price  (PLAN pass, filmo-plan)
  //     -> [human-pay] park at awaiting_payment with the REAL price + the plan
  //     -> pay -> produce_and_ship (PRODUCE pass, filmo-produce, REUSES plan_id).
  // Hermes still conducts BOTH halves. On ANY failure of either pass we FALL BACK
  // to the deterministic build_runner path below (render NEVER fails). Reversibility:
  // HERMES_SPLIT=false keeps the old single atomic conduct (after a flat-cap gate).
  if (CLAIMER_MODE === 'hermes' && HERMES_SPLIT) {
    try {
      const goal = p.goal || 'A 30-second brand explainer'

      // (a) PLAN pass — read -> plan -> price. Set 'analyzing' so the Reading stage
      //     shows active while conversion_read runs; the plan tool then _set_phase
      //     'planning' and the price tool 'pricing', so the stepper advances HONESTLY
      //     (Reading/Planning/Pricing genuinely complete here, BEFORE any pay prompt).
      //     Yields a real price_cents + plan_id.
      await emit(runId, 'Conducting read -> plan -> price via Hermes agent (NemoClaw sandbox).')
      await setRun(runId, { phase: 'analyzing' })
      // A healthy 550B can still drop a plan pass via a transient stream truncation
      // ("Response payload is not completed"); the in-skill API retries share one
      // session, so they all hit the same blip. Re-run the WHOLE plan pass in a FRESH
      // nemoclaw exec (new session + upstream connection) up to PLAN_ATTEMPTS times - a
      // transient blip clears on a clean retry. The plan pass is read+plan+price ONLY
      // (no produce, no Stripe charge - the pay gate is AFTER), so a retry only
      // re-spends ~$0.01 of Nemotron tokens and can never double-charge. Only after all
      // attempts fail do we throw and fall back to the deterministic build_runner.
      let planRes = await runHermesPlan(safeUrl, goal, runId)
      for (let attempt = 2; (!planRes.ok || !planRes.planId || !(planRes.priceCents > 0)) && attempt <= PLAN_ATTEMPTS; attempt++) {
        log(`  ~ hermes PLAN pass attempt ${attempt - 1}/${PLAN_ATTEMPTS} failed (${planRes.error}); retrying in a fresh exec`)
        await emit(runId, `Plan hit a transient model error - retrying (attempt ${attempt}/${PLAN_ATTEMPTS})...`, 'filmo', 'warn')
        await sleep(PLAN_RETRY_DELAY_MS)
        planRes = await runHermesPlan(safeUrl, goal, runId)
      }
      if (!planRes.ok || !planRes.planId || !(planRes.priceCents > 0)) {
        log(`  ! hermes PLAN pass failed after ${PLAN_ATTEMPTS} attempts (${planRes.error}); falling back to deterministic build_runner`)
        await emit(runId, `Plan pass failed (${planRes.error || 'no plan'}); falling back to deterministic render.`, 'filmo', 'warn')
        throw new Error('plan pass failed: ' + (planRes.error || 'no plan'))
      }
      const planId = planRes.planId
      const realPriceCents = planRes.priceCents
      // Persist the plan handle + the real price onto the run so the gate (and the
      // run page) read the REAL computed price, not the flat cap.
      await setRun(runId, { phase: 'pricing', price_cents: realPriceCents, props: tagPlanHandle(readProps(runKey), planId) })
      log(`  PLAN pass ok: plan_id=${planId} price_cents=${realPriceCents} (${planRes.sceneCount ?? '?'} scenes)`)

      // (b) PAYMENT GATE (human-pays only) — park at awaiting_payment with the REAL
      //     price + the already-built plan. On create-fail / timeout the run is
      //     marked failed inside paymentGate; we return (NEVER produce an unpaid job).
      if (PAYMENTS_REQUIRED && payMode === 'human') {
        const paid = await paymentGate(job, runId, runKey, safeUrl, realPriceCents)
        if (!paid) return
        paidViaGate = true
      }

      // (c) PRODUCE pass — produce_and_ship ONLY, REUSING the cached plan_id (no
      //     re-read/re-plan/re-price, so no double charge and the customer gets the
      //     exact plan they paid for).
      await emit(runId, 'Payment cleared - producing the planned video via Hermes agent.')
      await setRun(runId, { phase: 'producing' })
      const prodRes = await runHermesProduce(safeUrl, planId, runId)
      if (prodRes.ok && prodRes.finalUrl) {
        await deliverHermesRun(job, runId, runKey, prodRes.finalUrl, prodRes.sceneCount ?? planRes.sceneCount, t0, planId)
        return
      }
      // ROBUSTNESS: the produce_and_ship tool uploads the video BEFORE the agent
      // emits its Shipped line. If the agent stalled on that line (550B reply
      // latency) and the conduct timed out, the video is ALREADY in the bucket —
      // recover it and deliver the Hermes-produced video (REAL price preserved)
      // instead of a wasteful deterministic re-render that recomputes the price.
      log(`  ! hermes PRODUCE pass failed (${prodRes.error}); checking if produce_and_ship already shipped…`)
      const recovered = await recoverShippedVideo(runId, planId)
      if (recovered && recovered.finalUrl) {
        log(`  RECOVERED already-shipped video for plan_id=${planId} -> ${recovered.finalUrl}`)
        // The recover path bypasses produce_and_ship's rich-props merge + per-scene
        // asset upload, so the editor would otherwise load THIN props (0 scenes, blank
        // assets). Reconstruct them from the local render dir (runs/<planId>) BEFORE
        // delivering: heal every editor asset under the DB run_key namespace + merge
        // scenes/theme/total_frames onto runs.props.
        const heal = await healRecoveredRun(runId, planId)
        log(`  heal-recovered ${heal && heal.ok ? 'ok' : 'FAILED'}: ${JSON.stringify((heal && (heal.asset_check || heal.error)) ?? heal)}`)
        await emit(runId, `Produce pass finished but did not echo the link; recovered the shipped video from storage.`, 'filmo', 'warn')
        await deliverHermesRun(job, runId, runKey, recovered.finalUrl, recovered.sceneCount ?? planRes.sceneCount, t0, planId)
        return
      }
      log(`  ! no shipped video found for plan_id=${planId}; falling back to deterministic build_runner`)
      await emit(runId, `Produce pass failed (${prodRes.error}); falling back to deterministic render.`, 'filmo', 'warn')
      // fall through to deterministic; paidViaGate (if set) prevents a 2nd charge.
    } catch (e) {
      log(`  ! hermes split mode threw (${String(e)}); falling back to deterministic build_runner`)
      await emit(runId, `Hermes conduct error; falling back to deterministic render.`, 'filmo', 'warn')
    }
    // fall through to the deterministic path (render NEVER fails)
  } else if (CLAIMER_MODE === 'hermes') {
    // ── LEGACY / REVERSIBLE single-conduct path (HERMES_SPLIT=false): flat-cap
    //    pre-conduct gate + ONE atomic conduct (read->plan->price->gate->produce).
    if (PAYMENTS_REQUIRED && payMode === 'human') {
      const paid = await paymentGate(job, runId, runKey, safeUrl) // flat cap (no real price yet)
      if (!paid) return
      paidViaGate = true
    }
    try {
      await emit(runId, 'Conducting produce step via Hermes agent (NemoClaw sandbox)…')
      await setRun(runId, { phase: 'hermes_conducting' })
      const goal = p.goal || 'A 30-second brand explainer'
      const res = await runHermesConduct(safeUrl, goal, HERMES_BUDGET_CENTS, runId)
      if (res.ok && res.finalUrl) {
        await deliverHermesRun(job, runId, runKey, res.finalUrl, res.sceneCount, t0)
        return
      }
      if (res.declined) {
        // The gate declined autonomously — a correct money outcome, not a render
        // failure. Mark the job failed with the decline reason; do NOT fall back.
        await setRun(runId, { status: 'failed', phase: 'gate_declined' })
        await setJob(job.id, { status: 'failed', error: 'hermes gate declined (over budget)' })
        await emit(runId, 'Hermes gate declined: price exceeds budget. No video produced.', 'filmo', 'warn')
        log(`  DECLINED run ${runKey} (hermes gate declined)`)
        return
      }
      log(`  ! hermes mode failed (${res.error}); falling back to deterministic build_runner`)
      await emit(runId, `Hermes conduct failed (${res.error}); falling back to deterministic render.`, 'filmo', 'warn')
    } catch (e) {
      log(`  ! hermes mode threw (${String(e)}); falling back to deterministic build_runner`)
      await emit(runId, `Hermes conduct error; falling back to deterministic render.`, 'filmo', 'warn')
    }
    // fall through to the deterministic path (render NEVER fails)
  }

  // DIRECT mode (CLAIMER_MODE !== 'hermes'): no conduct above ran, so the human-pay
  // gate must fire HERE (flat cap — the deterministic build_runner computes its own
  // price inside its own _payment_gate; this pre-gate only collects payment for the
  // human-pay path, mirroring the previous behaviour for non-hermes deployments).
  if (CLAIMER_MODE !== 'hermes' && PAYMENTS_REQUIRED && payMode === 'human' && !paidViaGate) {
    const paid = await paymentGate(job, runId, runKey, safeUrl)
    if (!paid) return
    paidViaGate = true
  }

  // 1) spawn the CURATED pipeline (build_runner.py --mode mock = real screenshots
  //    + real logos + curated pattern library; $0 free VO via edge-tts+whisper).
  const args = ['build_runner.py',
    '--url', url,
    '--goal', p.goal || 'A 30-second brand explainer',
    '--run-id', runKey,
    '--mode', p.mode || 'mock',
    '--quality', p.quality || 'standard',
    '--brain', p.brain || 'super-free',
    '--duration', String(p.duration || 30)]
  if (p.emphasis) args.push('--emphasis', p.emphasis)
  if (p.look === 'engineered-night' || p.look === 'walkrec') args.push('--look', p.look)
  // Walkrec beta: the pipeline's hosted event sink needs the runs.id UUID.
  try {
    const rdir = join(PIPELINE_DIR, 'runs', runKey)
    mkdirSync(rdir, { recursive: true })
    writeFileSync(join(rdir, 'insforge-run-id'), String(runId))
  } catch {}
  // ElevenLabs is the DEFAULT VO: set WS_VO_PROVIDER=elevenlabs so the pipeline
  // (align_vo.py) tries ElevenLabs FIRST. On ANY ElevenLabs failure (401 /
  // quota_exceeded / network / no key) align_vo AUTOMATICALLY falls back to the
  // free edge-tts + whisper path, so a render NEVER fails on VO. The resulting
  // run records vo_engine / vo_fallback / vo_fallback_reason in vo_alignment.json.
  const env = { ...process.env }
  env.WS_VO_PROVIDER = 'elevenlabs'
  // Auto-resolve the Stripe TEST payment gate for the mock demo (no human-pays).
  // Auto-resolve the deterministic-fallback payment gate when: the original build
  // was an auto/mock job (no human-pays), OR the pre-conduct gate ABOVE already
  // collected real payment (paidViaGate) \u2014 in the latter case the fallback must
  // NOT create a SECOND checkout, so we simulate-resolve it (zero double-charge).
  if ((p.mode || 'mock') === 'mock' && (p.pay_mode !== 'human' || paidViaGate)) env.PRODUCER_SIMULATE_PAID = '1'

  const child = spawn(PYTHON_BIN, args, { cwd: PIPELINE_DIR, env })
  child.on('error', (e) => log(`  ! spawn error ${runKey}`, String(e)))
  child.stdout.on('data', (d) => { try { process.stdout.write(`  [py] ${d}`) } catch {} })
  child.stderr.on('data', (d) => { try { process.stderr.write(`  [py!] ${d}`) } catch {} })

  // stream ledger events while the build runs. When the job is not human-pay,
  // the simulated gate's payment theater is suppressed end to end: no theater
  // events, no checkout_url on the run, no awaiting_payment flash on the page.
  const suppressPay = (p.pay_mode || 'auto') !== 'human'
  let lastSeq = 0
  let alive = true
  const streamer = (async () => {
    while (alive) {
      try {
        const led = readLedger(runKey)
        if (led) {
          lastSeq = await syncEvents(runId, led, lastSeq, suppressPay)
          if (led.phase) {
            const patch = { phase: led.phase }
            if (suppressPay && patch.phase === 'awaiting_payment') patch.phase = 'producing'
            const checkoutUrl = led.earn && led.earn.checkout_url
            if (checkoutUrl && !suppressPay) patch.checkout_url = checkoutUrl
            await setRun(runId, patch)
          }
        }
      } catch (e) { log('  ! streamer iter', String(e)) }
      await sleep(LEDGER_POLL_MS)
    }
  })()

  // hard render ceiling so a wedged build can't pin the daemon forever
  const renderTimer = setTimeout(() => { try { child.kill('SIGKILL') } catch {}; log('  ! render timeout (killed)') }, RENDER_TIMEOUT_MS)
  const code = await new Promise((res) => child.on('close', res))
  clearTimeout(renderTimer)
  alive = false
  await streamer

  const ledger = readLedger(runKey) || {}
  await syncEvents(runId, ledger, lastSeq, suppressPay)   // final flush
  const mapped = mapLedgerToRun(ledger)

  // WALKREC VERDICT: the classic ledger doesn't exist for walkrec builds
  // (the python pipeline narrates via agent_events instead), so the ledger
  // check above would fail every exit-0 walkrec run. Delivery receipt =
  // runs.final_url, PATCHed by the pipeline itself (strategy-flow upload,
  // no gateway body cap).
  if (p.look === 'walkrec') {
    const { data: fresh } = await ifCall('runs.select(walkrec-receipt)',
      () => db.database.from('runs').select('final_url').eq('id', runId).maybeSingle())
    const shippedUrl = fresh && fresh.final_url
    if (code === 0 && shippedUrl) {
      await setRun(runId, { status: 'delivered', phase: 'delivered' })
      await setJob(job.id, { status: 'done' })
      const totalSec = ((Date.now() - t0) / 1000).toFixed(1)
      log(`  DELIVERED walkrec run ${runKey} -> ${shippedUrl}  [${totalSec}s, claimed_by=${WORKER_ID}]`)
    } else {
      await setRun(runId, { status: 'failed', phase: 'failed' })
      await setJob(job.id, { status: 'failed', error: `walkrec exit ${code}, final_url ${shippedUrl ? 'set' : 'missing'}` })
      log(`  FAILED walkrec run ${runKey} (exit ${code}, final_url ${shippedUrl ? 'set' : 'missing'})`)
    }
    return
  }

  if (code === 0 && (mapped.status === 'delivered' || mapped.status === 'completed_with_warnings')) {
    // SHIP. uploadVideo -> putObject -> ifCall is BOUNDED (each attempt timeout-capped,
    // 3 attempts), so the mp4 upload can never hang the worker (this is the call that
    // pinned a conduct ~10min). The rendered mp4 lives at runs/<runKey>/final.mp4 and
    // is NEVER deleted here — so on an upload failure we mark the run RETRYABLE and
    // keep the file, instead of stranding a finished video.
    const finalUrl = await uploadVideo(runKey, 'final.mp4')
    const props = tagProducer(readProps(runKey))   // stamp producer into props jsonb
    await uploadRunAssets(runKey).catch((e) => log('  ! uploadRunAssets', String(e)))
    if (!finalUrl) {
      const localPath = join(PIPELINE_DIR, 'runs', runKey, 'final.mp4')
      const haveVideo = existsSync(localPath)
      // Mark FAILED-but-retryable: phase=upload_failed, ship_retryable=true, and the
      // on-disk path so the video can be re-shipped (it is NOT lost). The render
      // succeeded — only the InsForge upload didn't — so the file is the source of truth.
      const retryProps = { ...props, ship_retryable: haveVideo, local_video_path: haveVideo ? localPath : null }
      await setRun(runId, { ...mapped, status: 'failed', phase: 'upload_failed', final_url: null, props: retryProps })
      await setJob(job.id, { status: 'failed', error: `video upload failed (render OK; mp4 preserved at ${localPath} for re-ship)` })
      await emit(runId, `Render finished but the upload to storage failed after retries. Your video is safe on the worker and can be re-shipped (no re-render needed).`, 'filmo', 'warn')
      log(`  UPLOAD FAILED run ${runKey} (render ok, mp4 preserved at ${localPath}, ship_retryable=${haveVideo})`)
    } else {
      const sceneThumbs = await stageSceneThumbs(runKey, props)
      if (sceneThumbs) props.scene_thumbs = sceneThumbs
      await setRun(runId, { ...mapped, final_url: finalUrl, props })
      await setJob(job.id, { status: 'done' })
      const totalSec = ((Date.now() - t0) / 1000).toFixed(1)
      await emit(runId, `Produced by Filmo (${PRODUCER}). ${totalSec}s total.`)
      log(`  DELIVERED run ${runKey} -> ${finalUrl}  [${totalSec}s, producer=${PRODUCER}, claimed_by=${WORKER_ID}]`)
    }
  } else {
    await setRun(runId, { status: 'failed', phase: ledger.phase || 'failed' })
    await setJob(job.id, { status: 'failed', error: `exit ${code}, ledger ${mapped.status}` })
    log(`  FAILED run ${runKey} (exit ${code}, ledger ${mapped.status})`)
  }
}

// ── SAFE test path: process a SPECIFIC queued run_key without claim_next_job ──
async function processOne(runKey) {
  const { data: run, error: rErr } = await ifCall('runs.select(processOne)',
    () => db.database.from('runs').select('id, run_key, status').eq('run_key', runKey).maybeSingle())
  if (rErr || !run) { log(`processOne: run not found for run_key=${runKey}`, JSON.stringify(rErr)); return }
  const { data: jobs, error: jErr } = await ifCall('jobs.select(processOne)',
    () => db.database.from('jobs').select('*').eq('run_id', run.id).order('id', { ascending: true }))
  if (jErr) { log('processOne: jobs query error', JSON.stringify(jErr)); return }
  const job = (jobs || []).find((j) => j.status === 'queued' || j.status === 'claimed') || (jobs || [])[0]
  if (!job) { log(`processOne: no job for run_key=${runKey}`); return }
  await setJob(job.id, { status: 'claimed', claimed_by: WORKER_ID, claimed_at: new Date().toISOString() })
  return processJob({ ...job, status: 'claimed' })
}

// ── SAFE test enqueue: mirror the website's runs+jobs insert (enqueue.js) ──
async function enqueueTestJob(companyUrl = 'https://stripe.com') {
  const runKey = `cloud-${Date.now()}`
  const userId = process.env.ENQ_USER_ID || '90923fa8-41da-47f2-8d45-81a7dbd3405f'
  const host = String(companyUrl || '').replace(/^https?:\/\//, '').replace(/\/.*$/, '') || companyUrl
  const goal = process.env.ENQ_GOAL || 'A 30-second brand explainer'
  const emphasis = process.env.ENQ_EMPHASIS || 'accept payments in one integration'
  const runRow = { user_id: userId, run_key: runKey, brand: host, company_url: companyUrl, goal, emphasis, quality: 'standard', brain: 'super-free', mode: 'mock', status: 'queued' }
  const { data: runRows, error: runErr } = await ifCall('runs.insert(enqueue)',
    () => db.database.from('runs').insert([runRow]).select())
  if (runErr) { log('enqueue runs.insert', JSON.stringify(runErr)); process.exit(1) }
  const runId = runRows[0].id
  const params = { company_url: companyUrl, goal, emphasis, quality: 'standard', brain: 'super-free', mode: 'mock', run_key: runKey, duration: 30 }
  const { error: jobErr } = await ifCall('jobs.insert(enqueue)',
    () => db.database.from('jobs').insert([{ run_id: runId, status: 'queued', params }]))
  if (jobErr) { log('enqueue jobs.insert', JSON.stringify(jobErr)); process.exit(1) }
  log(`enqueued test job: run ${runKey} (${runId}) for ${companyUrl}`)
  return runKey
}

// Job wall-clock ceiling. The conduct is bounded by nemoclaw --timeout (20min) and
// the deterministic render by RENDER_TIMEOUT_MS (25min); this is a BELT-AND-SUSPENDERS
// outer bound so that even if some unforeseen await hangs (an InsForge path, a child
// that ignores its kill, etc.) the daemon ALWAYS returns to polling. Set above both
// inner ceilings so it only fires on a true wedge, never on a healthy long render.
const JOB_WALLCLOCK_MS = Number(process.env.JOB_WALLCLOCK_MS || 30 * 60 * 1000) // 30 min
// DEPLOY-SAFE CLAIMS (3x observed 2026-07-19): Railway sends SIGTERM before
// swapping containers, and a dying container can claim a job in its final
// seconds — orphaning it for STALE_CLAIM_MS. On SIGTERM, release THIS
// worker's in-flight claims back to 'queued' so the next container picks
// them up immediately.
let CURRENT_CLAIMED_JOB_ID = null
process.on('SIGTERM', async () => {
  try {
    if (CURRENT_CLAIMED_JOB_ID) {
      // Release ONLY a job that is still genuinely in flight — releasing a
      // finished job resurrects it on the next container (observed: a failed
      // walkrec job re-ran after a deploy because the claim var outlived
      // its job).
      const { data: j } = await ifCall('jobs.select(sigterm)',
        () => db.database.from('jobs').select('status').eq('id', CURRENT_CLAIMED_JOB_ID).maybeSingle())
      if (j && j.status === 'claimed') {
        await setJob(CURRENT_CLAIMED_JOB_ID,
          { status: 'queued', claimed_at: null, claimed_by: null })
        log(`SIGTERM: released claim on job ${CURRENT_CLAIMED_JOB_ID}`)
      } else {
        log(`SIGTERM: claim var held ${CURRENT_CLAIMED_JOB_ID} but status=${j && j.status} — not releasing`)
      }
    }
  } catch {}
  process.exit(0)
})

const STALE_CLAIM_MS = Number(process.env.STALE_CLAIM_MS || 35 * 60 * 1000) // a job 'claimed' longer than this by a non-current worker is a zombie
const STALE_SWEEP_INTERVAL_MS = Number(process.env.STALE_SWEEP_INTERVAL_MS || 2 * 60 * 1000)

// Run processJob bounded by the wall-clock ceiling. processJob still owns its own
// child kill + per-call ifCall bounds; this only guarantees the LOOP unblocks. The
// abandoned processJob (if any) keeps running in the background but cannot pin the
// poll loop — the next claim proceeds. NEVER throws.
async function runJobBounded(job) {
  let timer
  const guard = new Promise((resolve) => {
    timer = setTimeout(async () => {
      log(`  !! job wall-clock guard fired after ${(JOB_WALLCLOCK_MS / 60000) | 0}min (job ${job.id}); marking wedged + freeing the queue`)
      // CRITICAL: never leave the run a permanent zombie. Mark it terminal so the UI
      // stops spinning and claim_next_job/the reaper won't re-touch it. Best-effort.
      try {
        if (job.run_id) await setRun(job.run_id, { status: 'failed', phase: 'wedged' })
        await setJob(job.id, { status: 'failed', error: 'wall-clock wedge (>30min)' })
      } catch (e) { log('  wedge-mark failed', String(e && e.message || e)) }
      resolve('wallclock')
    }, JOB_WALLCLOCK_MS)
  })
  try {
    await Promise.race([
      processJob(job)
        .catch((e) => log('processJob threw', String(e && e.stack || e)))
        .finally(() => { CURRENT_CLAIMED_JOB_ID = null }),
      guard,
    ])
  } finally { clearTimeout(timer) }
}

// ───────────────────────────── daemon loop ─────────────────────────────
// Zombie reaper: a job left 'claimed' by a DEAD worker (restart / OOM / hang) is
// invisible to claim_next_job (which only picks 'queued') and strands its run as
// 'running' forever - a judge sees a permanent spinner. Periodically mark such stale
// claims (and their runs) failed so nothing is ever permanently stuck. Scoped to claims
// NOT held by THIS live worker and older than STALE_CLAIM_MS (> the 30-min wall-clock,
// so a healthy long job is never swept). Best-effort, bounded, never throws.
async function sweepStaleClaims() {
  try {
    const { data: claimed } = await ifCall('jobs.select(claimed)',
      () => db.database.from('jobs').select('id, run_id, claimed_by, claimed_at').eq('status', 'claimed'))
    const cutoffMs = Date.now() - STALE_CLAIM_MS
    const stale = (claimed || []).filter((j) =>
      j.claimed_by !== WORKER_ID && (!j.claimed_at || Date.parse(j.claimed_at) < cutoffMs))
    let n = 0
    for (const j of stale) {
      await setJob(j.id, { status: 'failed', error: `stale claim reaped (claimed_by=${j.claimed_by || 'null'})` })
      if (j.run_id) await setRun(j.run_id, { status: 'failed', phase: 'stale_reclaim' })
      n++
    }
    if (n) log(`  reaper: failed ${n} stale-claimed zombie job(s)`)
  } catch (e) { log('  reaper error', String(e && e.message || e)) }
  // G5 FIX: status/phase desync. A run can be left status='running' while its job is
  // already terminal (done/failed) — e.g. a partial/interleaved write, or a deliver
  // flip (G4) that landed the job but not the run. claim_next_job ignores it (it only
  // picks 'queued') so it spins forever in the UI. Reconcile: for each running run
  // whose job is done -> mark delivered if a final_url (or a recoverable video) exists,
  // else failed; whose job is failed -> mark failed. Best-effort, bounded, never throws.
  try {
    const { data: running } = await ifCall('runs.select(running-desync)',
      () => db.database.from('runs').select('id, run_key, final_url').eq('status', 'running'))
    if (running && running.length) {
      let r = 0
      for (const run of running) {
        const { data: jrows } = await ifCall('jobs.select(by-run)',
          () => db.database.from('jobs').select('status').eq('run_id', run.id))
        const jobStatuses = (jrows || []).map((x) => x.status)
        if (!jobStatuses.length) continue           // no job row -> leave for stale-claim / wall-clock paths
        if (jobStatuses.includes('queued') || jobStatuses.includes('claimed')) continue  // still live; skip
        const allDone = jobStatuses.every((st) => st === 'done')
        const anyFailed = jobStatuses.includes('failed')
        if (allDone) {
          let finalUrl = run.final_url || null
          if (!finalUrl) {
            // accept video.mp4 (Hermes, run-UUID key) OR final.mp4 (deterministic, run_key)
            const rec = await recoverAnyVideo(run.id, run.run_key)
            if (rec && rec.finalUrl) finalUrl = rec.finalUrl
          }
          if (finalUrl) {
            await setRun(run.id, { status: 'delivered', phase: 'delivered', final_url: finalUrl })
            log(`  reaper: reconciled desync run ${run.run_key} -> delivered (job done, final_url ${run.final_url ? 'present' : 'recovered'})`)
          } else {
            await setRun(run.id, { status: 'failed', phase: 'desync_no_video' })
            log(`  reaper: reconciled desync run ${run.run_key} -> failed (job done but no final_url/recoverable video)`)
          }
          r++
        } else if (anyFailed) {
          await setRun(run.id, { status: 'failed', phase: 'job_failed_desync' })
          log(`  reaper: reconciled desync run ${run.run_key} -> failed (job failed, run left running)`)
          r++
        }
      }
      if (r) log(`  reaper: reconciled ${r} status/phase desync run(s)`)
    }
  } catch (e) { log('  reaper desync error', String(e && e.message || e)) }
}

async function main() {
  log(`Filmo curated claimer up — ${WORKER_ID}`)
  log(`  insforge: ${BASE_URL}`)
  log(`  pipeline: ${PIPELINE_DIR}  (build_runner.py --mode mock, curated)`)
  log(`  mode: ${CLAIMER_MODE}${CLAIMER_MODE === 'hermes' ? ` (conduct via ${HERMES_SANDBOX}/${HERMES_SKILL}, fallback=direct)` : ' (deterministic build_runner)'}`)
  log(`  producer: ${CLAIMER_MODE === 'hermes' ? HERMES_PRODUCER : PRODUCER}`)
  log(`  resilience: InsForge calls bounded ${IF_TIMEOUT_MS}ms x${IF_ATTEMPTS}; job wall-clock ${(JOB_WALLCLOCK_MS / 60000) | 0}min`)
  let lastSweepMs = 0
  for (;;) {
    // Reaper pass (throttled): fail any job stuck 'claimed' by a dead worker so a
    // worker death/restart can never strand a run forever.
    const nowMs = Date.now()
    if (nowMs - lastSweepMs > STALE_SWEEP_INTERVAL_MS) { lastSweepMs = nowMs; await sweepStaleClaims() }
    let job = null
    // claim_next_job is the FIRST InsForge call each loop — bound it so a hung claim
    // can never freeze the daemon before it even has a job.
    const { data, error } = await ifCall('rpc.claim_next_job',
      () => db.database.rpc('claim_next_job', { p_worker: WORKER_ID }))
    if (error) log('claim error', JSON.stringify(error))
    else job = data

    if (job && job.id) {
      await runJobBounded(job)
    } else {
      log('poll: queue empty')
      try { await sleep(POLL_MS) } catch {}
    }
  }
}

async function supervise() {
  for (;;) {
    try { await main() }
    catch (e) { log('!! main() exited (restarting in 5s)', String(e && e.stack || e)); await sleep(5000) }
  }
}

// ───────────────────────────── entrypoint ─────────────────────
const argv = process.argv.slice(2)
;(async () => {
  if (argv[0] === '--once') {
    const rk = argv[1]
    if (!rk) { console.error('usage: node curated-claimer.js --once <run_key>'); process.exit(1) }
    await processOne(rk)
    process.exit(0)
  } else if (argv[0] === '--url') {
    const u = argv[1]
    if (!u) { console.error('usage: node curated-claimer.js --url <URL>'); process.exit(1) }
    const rk = await enqueueTestJob(u)
    await processOne(rk)
    process.exit(0)
  } else {
    supervise()
  }
})()
