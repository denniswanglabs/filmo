// Lightweight checker for an in-flight YC run: polls ONLY status/phase (no heavy props
// blob), then fetches props ONCE at terminal and asserts the content-quality fixes.
import { readFileSync, writeFileSync } from 'node:fs'
import { createAdminClient } from '@insforge/sdk'
const env = {}
for (const l of readFileSync(new URL('./.env.local', import.meta.url), 'utf8').split('\n')) {
  const m = l.match(/^([A-Z0-9_]+)=(.*)$/); if (m) env[m[1]] = m[2].trim()
}
const log = (...a) => console.log(new Date().toISOString().slice(11, 19), ...a)
const db = createAdminClient({ baseUrl: env.INSFORGE_URL, apiKey: env.INSFORGE_API_KEY })
const RUN_ID = process.argv[2] || '35728d92-94cd-43eb-96ba-c86eddc1a333'

const TERMINAL = new Set(['delivered', 'completed_with_warnings', 'failed', 'aborted'])
const deadline = Date.now() + 14 * 60 * 1000
let last = '', status = null
while (Date.now() < deadline) {
  await new Promise((r) => setTimeout(r, 15000))
  try {
    const q = await db.database.from('runs').select('status, phase').eq('id', RUN_ID)
    const row = q.data?.[0]; if (!row) { log('(no row yet)'); continue }
    const sig = `${row.status}/${row.phase || '-'}`
    if (sig !== last) { log('  ->', sig); last = sig }
    status = row.status
    if (TERMINAL.has(status)) break
  } catch (e) { log('  (poll timeout, retrying)') }
}
if (!TERMINAL.has(status)) { log('YC-CHECK TIMEOUT lastStatus=', status); process.exit(2) }
if (status === 'failed' || status === 'aborted') { log('YC-CHECK WORKER FAILED', status); process.exit(3) }

// fetch props ONCE now that it's terminal
let p = null, final_url = null
for (let i = 0; i < 5; i++) {
  try { const q = await db.database.from('runs').select('props, props_edited, final_url').eq('id', RUN_ID); const row = q.data?.[0]; p = (row.props_edited && row.props_edited.scenes) ? row.props_edited : row.props; final_url = row.final_url; break } catch { log('  (props fetch retry)'); await new Promise(r => setTimeout(r, 5000)) }
}
const scenes = p?.scenes || []
const TEXT_KEYS = ['title', 'subtitle', 'kicker', 'eyebrow', 'heading', 'headline', 'caption', 'statement', 'overlayTitle', 'punchWord', 'supporting']
const NAV = ['knowledge & news', "in founders' words", 'in founders’ words', 'be in the room with']
const norm = (s) => (s || '').toLowerCase().replace(/\s+/g, ' ').trim()
const subtitles = {}; let bulletsFound = []; let navFound = []
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
const repeatOk = repeatedSubs.length === 0, bulletsOk = bulletsFound.length === 0, navOk = navFound.length === 0
console.log('\n========== VERDICT ==========')
log(`repeated subtitle across scenes: ${repeatOk ? 'NONE ✓' : 'FOUND ✗ ' + JSON.stringify(repeatedSubs)}`)
log(`feature-card bullets present:    ${bulletsOk ? 'NONE ✓' : 'FOUND ✗ ' + JSON.stringify(bulletsFound)}`)
log(`nav/section labels on-screen:    ${navOk ? 'NONE ✓' : 'FOUND ✗ ' + JSON.stringify(navFound)}`)
if (final_url) { try { const r = await fetch(final_url); const buf = Buffer.from(await r.arrayBuffer()); writeFileSync('/tmp/yc-verify.mp4', buf); log(`downloaded /tmp/yc-verify.mp4 ${r.status} bytes=${buf.length}`) } catch (e) { log('mp4 err', String(e)) } }
const del = await db.database.from('runs').delete().eq('id', RUN_ID)
log('cleanup:', del.error ? JSON.stringify(del.error) : 'ok')
const allOk = repeatOk && bulletsOk && navOk
log(`\nYC-CHECK ${allOk ? 'PASS — content-quality fixes confirmed on the live worker' : 'FAIL — see ✗'}`)
process.exit(allOk ? 0 : 4)
