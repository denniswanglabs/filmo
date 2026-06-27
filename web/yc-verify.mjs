// Task 7 — regenerate the Y Combinator video through the LIVE worker (now running the
// content-quality pipeline) and ASSERT the fixes. $0: super-free + mock. Pulls props,
// checks no repeated subtitle / no feature-card bullets / no nav labels, prints scene
// copy, downloads the mp4, then deletes its own test row.
import { readFileSync, writeFileSync } from 'node:fs'
import { createClient, createAdminClient } from '@insforge/sdk'

const env = {}
for (const l of readFileSync(new URL('./.env.local', import.meta.url), 'utf8').split('\n')) {
  const m = l.match(/^([A-Z0-9_]+)=(.*)$/); if (m) env[m[1]] = m[2].trim()
}
const log = (...a) => console.log(new Date().toISOString().slice(11, 19), ...a)
const anon = createClient({ baseUrl: env.NEXT_PUBLIC_INSFORGE_URL, anonKey: env.NEXT_PUBLIC_INSFORGE_ANON_KEY })
const db = createAdminClient({ baseUrl: env.INSFORGE_URL, apiKey: env.INSFORGE_API_KEY })

const si = await anon.auth.signInWithPassword({ email: env.NEXT_PUBLIC_DEMO_EMAIL, password: env.NEXT_PUBLIC_DEMO_PASSWORD })
if (si.error) { log('FAIL signin', JSON.stringify(si.error)); process.exit(1) }
const cu = await anon.auth.getCurrentUser()
const userId = cu?.data?.user?.id || cu?.data?.id || si?.data?.user?.id
if (!userId) { log('FAIL no userId'); process.exit(1) }

const url = 'https://www.ycombinator.com'
const runKey = `yc-verify-${Date.now()}`
const ins = await db.database.from('runs').insert([{
  user_id: userId, run_key: runKey, brand: 'www.ycombinator.com', company_url: url,
  goal: 'A 30-second brand explainer', emphasis: null, quality: 'standard', brain: 'super-free', mode: 'mock', status: 'queued',
}]).select()
if (ins.error) { log('FAIL runs.insert', JSON.stringify(ins.error)); process.exit(1) }
const runId = ins.data[0].id
const params = { company_url: url, goal: 'A 30-second brand explainer', emphasis: '', quality: 'standard', brain: 'super-free', mode: 'mock', run_key: runKey, duration: 30 }
const ji = await db.database.from('jobs').insert([{ run_id: runId, status: 'queued', params }])
if (ji.error) { log('FAIL jobs.insert', JSON.stringify(ji.error)); process.exit(1) }
log(`QUEUED YC run ${runId} (${runKey}) brain=super-free mode=mock`)

const TERMINAL = new Set(['delivered', 'completed_with_warnings', 'failed', 'aborted'])
const deadline = Date.now() + 12 * 60 * 1000
let last = '', row
while (Date.now() < deadline) {
  await new Promise((r) => setTimeout(r, 12000))
  const q = await db.database.from('runs').select('status, phase, final_url, props').eq('id', runId)
  if (q.error) { log('poll error', JSON.stringify(q.error)); continue }
  row = q.data?.[0]; if (!row) continue
  const sig = `${row.status}/${row.phase || '-'}`
  if (sig !== last) { log('  ->', sig); last = sig }
  if (TERMINAL.has(row.status)) break
}
if (!row || !TERMINAL.has(row.status)) { log('TIMEOUT lastStatus=', row?.status); process.exit(2) }
if (row.status === 'failed' || row.status === 'aborted') { log('WORKER FAILED', row.status, row.phase); process.exit(3) }

// ---- assertions on the delivered props ----
const p = (row.props_edited && row.props_edited.scenes) ? row.props_edited : row.props
const scenes = p?.scenes || []
const TEXT_KEYS = ['title', 'subtitle', 'kicker', 'eyebrow', 'heading', 'headline', 'caption', 'statement', 'overlayTitle', 'punchWord', 'supporting']
const NAV = ['knowledge & news', "in founders' words", 'in founders’ words', 'be in the room with']
const norm = (s) => (s || '').toLowerCase().replace(/\s+/g, ' ').trim()

const subtitles = {}
let bulletsFound = []
let navFound = []
console.log('\n========== YC scenes (on-screen copy) ==========')
for (let i = 0; i < scenes.length; i++) {
  const d = scenes[i].data || {}
  const onscreen = {}
  for (const k of TEXT_KEYS) if (d[k]) onscreen[k] = d[k]
  if (Array.isArray(d.bullets) && d.bullets.length) { onscreen.bullets = d.bullets; bulletsFound.push({ scene: i, bullets: d.bullets }) }
  console.log(`scene ${i} [${scenes[i].archetype}]: ${JSON.stringify(onscreen)}`)
  if (d.subtitle && norm(d.subtitle)) { const key = norm(d.subtitle); (subtitles[key] ||= []).push(i) }
  for (const k of TEXT_KEYS) if (d[k] && NAV.includes(norm(d[k]))) navFound.push({ scene: i, key: k, val: d[k] })
  if (Array.isArray(d.bullets)) for (const b of d.bullets) if (NAV.includes(norm(b))) navFound.push({ scene: i, key: 'bullet', val: b })
}
const repeatedSubs = Object.entries(subtitles).filter(([, v]) => v.length > 1)
console.log('\n========== VERDICT ==========')
const repeatOk = repeatedSubs.length === 0
const bulletsOk = bulletsFound.length === 0
const navOk = navFound.length === 0
log(`repeated subtitle across scenes: ${repeatOk ? 'NONE ✓' : 'FOUND ✗ ' + JSON.stringify(repeatedSubs)}`)
log(`feature-card bullets present:    ${bulletsOk ? 'NONE ✓' : 'FOUND ✗ ' + JSON.stringify(bulletsFound)}`)
log(`nav/section labels on-screen:    ${navOk ? 'NONE ✓' : 'FOUND ✗ ' + JSON.stringify(navFound)}`)

if (row.final_url) {
  try { const r = await fetch(row.final_url); const buf = Buffer.from(await r.arrayBuffer()); writeFileSync('/tmp/yc-verify.mp4', buf); log(`downloaded /tmp/yc-verify.mp4 ${r.status} bytes=${buf.length}`) } catch (e) { log('mp4 fetch err', String(e)) }
}
const del = await db.database.from('runs').delete().eq('id', runId)
log('cleanup:', del.error ? JSON.stringify(del.error) : 'ok')
const allOk = repeatOk && bulletsOk && navOk
log(`\nYC-VERIFY ${allOk ? 'PASS — content-quality fixes confirmed on the live worker' : 'FAIL — see ✗ above'}`)
process.exit(allOk ? 0 : 4)
