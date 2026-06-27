// HUMAN-PAY smoke test against the LIVE deployed stack (InsForge + Railway worker).
// Queues a super-free / mock build of stripe.com EXACTLY like e2e-smoke BUT with
// pay_mode='human' so the pipeline's _payment_gate creates a REAL Stripe TEST
// checkout session and parks the run at phase 'awaiting_payment'. We assert the
// run parks there with a valid, reachable checkout_url, then delete our own row.
// $0: mock render (no real render); Stripe TEST mode (we never submit a payment).
import { readFileSync } from 'node:fs'
import { createClient, createAdminClient } from '@insforge/sdk'

// --- load .env.local ---
const env = {}
for (const line of readFileSync(new URL('./.env.local', import.meta.url), 'utf8').split('\n')) {
  const m = line.match(/^([A-Z0-9_]+)=(.*)$/)
  if (m) env[m[1]] = m[2].trim()
}
const log = (...a) => console.log(new Date().toISOString().slice(11, 19), ...a)

const anon = createClient({ baseUrl: env.NEXT_PUBLIC_INSFORGE_URL, anonKey: env.NEXT_PUBLIC_INSFORGE_ANON_KEY })
const db = createAdminClient({ baseUrl: env.INSFORGE_URL, apiKey: env.INSFORGE_API_KEY })

// --- 1. sign in as the demo user to get a valid owner user_id (FK) ---
const si = await anon.auth.signInWithPassword({ email: env.NEXT_PUBLIC_DEMO_EMAIL, password: env.NEXT_PUBLIC_DEMO_PASSWORD })
if (si.error) { log('PAY-SMOKE FAIL signin', JSON.stringify(si.error)); process.exit(1) }
const cu = await anon.auth.getCurrentUser()
const userId = cu?.data?.user?.id || cu?.data?.id || si?.data?.user?.id
if (!userId) { log('PAY-SMOKE FAIL no userId', JSON.stringify(cu?.data)); process.exit(1) }
log('signed in demo user', userId)

// --- 2. queue the build (mirror e2e-smoke) WITH human-pay turned on ---
const url = 'https://stripe.com'
const runKey = `pay-smoke-${Date.now()}`
const goal = 'A 30-second brand explainer'
const brand = url.replace(/^https?:\/\//, '').replace(/\/.*$/, '')
const ins = await db.database.from('runs').insert([{
  user_id: userId, run_key: runKey, brand, company_url: url,
  goal, emphasis: null, quality: 'standard', brain: 'super-free', mode: 'mock', status: 'queued',
}]).select()
if (ins.error) { log('PAY-SMOKE FAIL runs.insert', JSON.stringify(ins.error)); process.exit(1) }
const runId = ins.data[0].id
const params = { company_url: url, goal, emphasis: '', quality: 'standard', brain: 'super-free', mode: 'mock', run_key: runKey, duration: 30, pay_mode: 'human' }
const ji = await db.database.from('jobs').insert([{ run_id: runId, status: 'queued', params }])
if (ji.error) {
  log('PAY-SMOKE FAIL jobs.insert', JSON.stringify(ji.error))
  await db.database.from('runs').delete().eq('id', runId)
  process.exit(1)
}
log(`PAY-SMOKE QUEUED run ${runId} (${runKey}) brain=super-free mode=mock pay_mode=human`)

// helper: delete our own run row, log result
async function cleanup() {
  const del = await db.database.from('runs').delete().eq('id', runId)
  log('cleanup delete pay-smoke run:', del.error ? JSON.stringify(del.error) : 'ok')
}

// --- 3. poll runs for awaiting_payment + checkout_url, up to a 10-MINUTE deadline ---
const FAIL_TERMINAL = new Set(['failed', 'aborted'])
const PASS_TERMINAL = new Set(['delivered', 'completed_with_warnings']) // sailing here w/o gate = BUG
const deadline = Date.now() + 10 * 60 * 1000
let last = ''
const phaseSeq = []
let row
let parked = false
while (Date.now() < deadline) {
  await new Promise((r) => setTimeout(r, 12000))
  const q = await db.database.from('runs').select('status, phase, checkout_url').eq('id', runId)
  if (q.error) { log('poll error', JSON.stringify(q.error)); continue }
  row = q.data?.[0]
  if (!row) continue
  const sig = `${row.status}/${row.phase || '-'}`
  if (sig !== last) {
    log('  ->', sig, row.checkout_url ? '(checkout_url set)' : '')
    last = sig
    phaseSeq.push(sig)
  }
  if (row.phase === 'awaiting_payment' && typeof row.checkout_url === 'string' && row.checkout_url.length > 0) {
    parked = true
    break
  }
  if (FAIL_TERMINAL.has(row.status)) break
  // If the run reaches a delivered state WITHOUT ever parking, that's the pay_mode bug.
  if (PASS_TERMINAL.has(row.status)) break
}

log('observed phase sequence:', phaseSeq.join(' | '))

// --- 4. verdict ---
function fail(reason) {
  log(`PAY-SMOKE FAIL ${reason}`)
  return reason
}

if (!parked) {
  let reason
  if (!row) reason = 'no run row returned during polling'
  else if (FAIL_TERMINAL.has(row.status)) reason = `worker FAILED status=${row.status} phase=${row.phase} (never reached awaiting_payment)`
  else if (PASS_TERMINAL.has(row.status)) reason = `run sailed to terminal status=${row.status} phase=${row.phase} WITHOUT ever parking at awaiting_payment — pay_mode NOT honored (REAL BUG)`
  else reason = `TIMEOUT after 10m — reached status=${row.status} phase=${row.phase}, never parked at awaiting_payment`
  fail(reason)
  await cleanup()
  process.exit(2)
}

// parked at awaiting_payment with a checkout_url — validate it's a real Stripe TEST checkout
const checkoutUrl = row.checkout_url
log('parked at awaiting_payment. checkout_url:', checkoutUrl)

let host = ''
try { host = new URL(checkoutUrl).host } catch (e) { /* handled below */ }
const validHost = host === 'checkout.stripe.com' || host === 'buy.stripe.com'
// Stripe TEST sessions carry a 'cs_test_' session id (in the URL or its path/query).
const hasTestMarker = /cs_test_|test/i.test(checkoutUrl)

if (!validHost) {
  fail(`checkout host not a Stripe checkout domain (host=${host || 'unparseable'})`)
  await cleanup()
  process.exit(3)
}
if (!hasTestMarker) {
  // Not a hard fail by itself, but the brief requires a test marker — treat as FAIL to be safe.
  fail(`checkout_url lacks a TEST marker (cs_test_/test) — not provably a Stripe TEST checkout: ${checkoutUrl}`)
  await cleanup()
  process.exit(3)
}

// fetch the checkout page (do NOT submit anything) and confirm HTTP 200
let httpOk = false
let httpStatus = 0
try {
  const r = await fetch(checkoutUrl, { redirect: 'follow' })
  httpStatus = r.status
  httpOk = r.ok
  log(`checkout fetch: HTTP ${r.status} (final url host=${(() => { try { return new URL(r.url).host } catch { return '?' } })()})`)
} catch (e) {
  log('checkout fetch err', String(e))
}

// --- 5. cleanup our own test row (parked unpaid => safe + correct to delete) ---
await cleanup()

if (httpOk) {
  log(`PAY-SMOKE PASS — payment gate created a valid Stripe TEST checkout (host=${host}, HTTP ${httpStatus}) and run parked at awaiting_payment`)
  process.exit(0)
}
fail(`checkout_url unreachable (HTTP ${httpStatus || 'no response'}) — host=${host}, url=${checkoutUrl}`)
process.exit(4)
