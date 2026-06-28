// E2E smoke test against the LIVE deployed stack (InsForge + Railway worker).
// Queues a super-free / mock build of stripe.com exactly like createBuild(), polls
// the run to terminal, verifies the delivered mp4, then deletes its own test row.
// $0: mock mode => Stripe simulated; super-free => free Nemotron. No paid calls.
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
if (si.error) { log('E2E FAILED signin', JSON.stringify(si.error)); process.exit(1) }
const cu = await anon.auth.getCurrentUser()
const userId = cu?.data?.user?.id || cu?.data?.id || si?.data?.user?.id
if (!userId) { log('E2E FAILED no userId', JSON.stringify(cu?.data)); process.exit(1) }
log('signed in demo user', userId)

// --- 2. queue the build (mirror createBuild) ---
const url = 'https://stripe.com'
const runKey = `e2e-smoke-${Date.now()}`
const goal = 'A 30-second brand explainer'
const brand = url.replace(/^https?:\/\//, '').replace(/\/.*$/, '')
const ins = await db.database.from('runs').insert([{
  user_id: userId, run_key: runKey, brand, company_url: url,
  goal, emphasis: null, quality: 'standard', brain: 'super-free', mode: 'mock', status: 'queued',
}]).select()
if (ins.error) { log('E2E FAILED runs.insert', JSON.stringify(ins.error)); process.exit(1) }
const runId = ins.data[0].id
const params = { company_url: url, goal, emphasis: '', quality: 'standard', brain: 'super-free', mode: 'mock', run_key: runKey, duration: 30 }
const ji = await db.database.from('jobs').insert([{ run_id: runId, status: 'queued', params }])
if (ji.error) { log('E2E FAILED jobs.insert', JSON.stringify(ji.error)); process.exit(1) }
log(`E2E QUEUED run ${runId} (${runKey}) brain=super-free mode=mock`)

// --- 3. poll to terminal ---
const TERMINAL = new Set(['delivered', 'completed_with_warnings', 'failed', 'aborted'])
const deadline = Date.now() + 12 * 60 * 1000
let last = ''
let row
while (Date.now() < deadline) {
  await new Promise((r) => setTimeout(r, 12000))
  const q = await db.database.from('runs').select('status, phase, final_url, selection').eq('id', runId)
  if (q.error) { log('poll error', JSON.stringify(q.error)); continue }
  row = q.data?.[0]
  if (!row) continue
  const sig = `${row.status}/${row.phase || '-'}`
  if (sig !== last) { log('  ->', sig, row.final_url ? '(final_url set)' : ''); last = sig }
  if (TERMINAL.has(row.status)) break
}

// --- 4. verdict + verify mp4 ---
if (!row || !TERMINAL.has(row.status)) { log('E2E TIMEOUT (worker did not finish in 12m) lastStatus=', row?.status); process.exit(2) }
if (row.status === 'failed' || row.status === 'aborted') { log('E2E WORKER FAILED status=', row.status, 'phase=', row.phase); process.exit(3) }

let mp4ok = false
if (row.final_url) {
  try {
    log(`final_url: ${row.final_url}`)
    const r = await fetch(row.final_url)
    const buf = Buffer.from(await r.arrayBuffer())
    const { writeFileSync } = await import('node:fs')
    writeFileSync('/tmp/verify-unified.mp4', buf)
    mp4ok = r.ok && buf.length > 100000
    log(`downloaded /tmp/verify-unified.mp4: ${r.status} bytes=${buf.length}`)
  } catch (e) { log('final_url fetch err', String(e)) }
}
log('selection(Nemotron telemetry):', JSON.stringify(row.selection))

// --- 5. cleanup our own test row (cascade removes job + events) ---
const del = await db.database.from('runs').delete().eq('id', runId)
log('cleanup delete e2e run:', del.error ? JSON.stringify(del.error) : 'ok')

if (row.status.startsWith('delivered') || row.status === 'completed_with_warnings') {
  log(`E2E PASS — worker delivered a video (status=${row.status}, mp4ok=${mp4ok})`)
  process.exit(mp4ok ? 0 : 4)
}
log('E2E UNEXPECTED status', row.status); process.exit(5)
