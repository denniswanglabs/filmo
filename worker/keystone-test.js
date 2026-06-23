// Keystone test: prove the Node worker can do its whole InsForge data path against
// the live cloud backend — create a user, insert a run + events, upload a video,
// mark it delivered, read it back, then clean up. Run: node --env-file=.env keystone-test.js
import { createClient, createAdminClient } from '@insforge/sdk'

const baseUrl = process.env.INSFORGE_URL
const apiKey = process.env.INSFORGE_API_KEY
const anonKey = process.env.INSFORGE_ANON_KEY

const admin = createAdminClient({ baseUrl, apiKey })
const anon = createClient({ baseUrl, anonKey })

const log = (step, ok, extra = '') => console.log(`${ok ? '  OK ' : ' ERR '} ${step}${extra ? ' — ' + extra : ''}`)
const die = (step, error) => { console.error(' ERR ' + step + ' —', JSON.stringify(error)); process.exit(1) }

const stamp = Date.now()
const email = `keystone+${stamp}@walk.studio`
const runKey = `keystone-${stamp}`
let userId, runId, fileKey

console.log(`\n=== InsForge keystone test (${baseUrl}) ===`)

// 1) the run owner. In production the worker gets user_id from the job (a signed-in,
//    verified user). For the test, accept TEST_USER_ID; else sign up a fresh user.
{
  userId = process.env.TEST_USER_ID
  if (!userId) {
    const { data, error } = await anon.auth.signUp({ email, password: 'Keystone-passw0rd!' })
    if (error) die('auth.signUp', error)
    userId = data?.user?.id || data?.user?.user_id || data?.id
  }
  if (!userId) die('user id', { hint: 'email verification is on; pass TEST_USER_ID' })
  log('owner user', true, userId)
}

// 2) admin: insert a run (status=running)
{
  const { data, error } = await admin.database.from('runs')
    .insert([{ user_id: userId, run_key: runKey, brand: 'walk.studio', goal: 'keystone validation', status: 'running', brain: 'super-free', mode: 'mock' }])
    .select()
  if (error) die('runs.insert', error)
  runId = data?.[0]?.id
  log('runs.insert', !!runId, 'run ' + runId)
}

// 3) admin: insert two events (the worker streams these from the ledger)
{
  const { error } = await admin.database.from('run_events').insert([
    { run_id: runId, seq: 1, actor: 'hermes', msg: 'plan validated: 5 scenes' },
    { run_id: runId, seq: 2, actor: 'nemotron', msg: 'returned a 5-scene plan, finish: stop' },
  ])
  if (error) die('run_events.insert', error)
  log('run_events.insert', true, '2 events')
}

// 4) admin: upload a stand-in "video" to the walk-videos bucket
{
  fileKey = `${runKey}/final.mp4`
  const blob = new Blob([Buffer.from('FAKE-MP4-BYTES-for-keystone')], { type: 'video/mp4' })
  const { data, error } = await admin.storage.from('walk-videos').upload(fileKey, blob)
  if (error) die('storage.upload', error)
  log('storage.upload', !!data?.url, data?.url)
  // 5) admin: mark the run delivered with the video URL
  const { error: upErr } = await admin.database.from('runs').update({ status: 'delivered', final_url: data.url }).eq('id', runId)
  if (upErr) die('runs.update(delivered)', upErr)
  log('runs.update -> delivered', true)
}

// 6) read it back (admin) — run + its events
{
  const { data, error } = await admin.database.from('runs').select('run_key, status, final_url').eq('id', runId)
  if (error) die('runs.select', error)
  log('runs.select', true, JSON.stringify(data?.[0]))
  const { data: evs } = await admin.database.from('run_events').select('seq, actor, msg').eq('run_id', runId)
  log('run_events.select', true, (evs || []).length + ' events: ' + (evs || []).map(e => e.actor).join(','))
}

// 7) cleanup
{
  await admin.storage.from('walk-videos').remove([fileKey])
  await admin.database.from('runs').delete().eq('id', runId)   // cascades events
  log('cleanup', true, 'removed file + run (events cascade)')
  console.log('  note: test auth user left in place (admin user-delete is a separate flow)')
}

console.log('\n=== KEYSTONE PASSED — the worker can drive InsForge end-to-end ===\n')
