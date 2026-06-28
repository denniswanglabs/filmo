// Filmo Hermes worker — runs on the VM host.
//
// Turns an InsForge `jobs` row into a finished video via the Hermes-in-NemoClaw
// path:  Hermes (sandbox) produces the plan  ->  style_fill.py renders on the host
// ->  the MP4 is uploaded to the walk-videos bucket  ->  the runs row is marked
// delivered with a final_url.
//
// InsForge integration (createAdminClient, putObject, syncEvents, setRun,
// readProps, the supervise/claim loop) is reused verbatim from the deployed
// Railway worker (worker/run.js). Only processJob differs: instead of spawning
// build_runner.py it invokes Hermes for the plan and then style_fill.py to render.
//
// Run modes:
//   Test (safe — never claims real jobs):
//     export $(cat /root/.insforge-key); export INSFORGE_URL=https://jd3mdkqr.ap-southeast.insforge.app
//     node worker.js --once <run_key>          # process ONE specific run_key
//     node worker.js --enqueue-and-run         # enqueue a fresh stripe test job + process it
//     node worker.js --url <URL>               # enqueue a test job for ANY url + process it
//   Daemon (live wiring — claims oldest queued job in a loop):
//     node worker.js                           # or:  node worker.js --daemon
import { createAdminClient } from '@insforge/sdk'
import { spawn, execFileSync } from 'node:child_process'
import { readFileSync, writeFileSync, existsSync, mkdirSync } from 'node:fs'
import { join } from 'node:path'
import { hostname } from 'node:os'
import dns from 'node:dns/promises'
import net from 'node:net'

const BASE_URL = process.env.INSFORGE_URL || 'https://jd3mdkqr.ap-southeast.insforge.app'
const API_KEY = process.env.INSFORGE_API_KEY
const BUCKET = process.env.WALK_BUCKET || 'walk-videos'
const PIPELINE_DIR = process.env.PIPELINE_DIR || '/root/filmo-pipeline'
const PYTHON_BIN = process.env.PYTHON_BIN || '/root/filmo-venv/bin/python'
const STYLE = process.env.STYLE || 'orinovate-kinetic-light'
const FPS = Number(process.env.FPS || 30)
const POLL_MS = Number(process.env.POLL_MS || 4000)
const WORKER_ID = process.env.WORKER_ID || `hermes-worker-${hostname()}-${process.pid}`
// Hermes (nemotron + web research via filmo-producer) runs ~25s when the sandbox
// is uncontended; a 3-min ceiling is generous headroom for a contended run.
const HERMES_TIMEOUT_MS = Number(process.env.HERMES_TIMEOUT_MS || 180000)
// Per-job dynamic egress policy file (rewritten before every read of a new host).
const DYNAMIC_POLICY_PATH = process.env.DYNAMIC_POLICY_PATH || '/root/filmo-sandbox/filmo-dynamic.yaml'
const HERMES_ATTEMPTS = Number(process.env.HERMES_ATTEMPTS || 2)
const RENDER_TIMEOUT_MS = Number(process.env.RENDER_TIMEOUT_MS || 900000)

if (!API_KEY) { console.error('FATAL: INSFORGE_API_KEY required (export $(cat /root/.insforge-key))'); process.exit(1) }
const db = createAdminClient({ baseUrl: BASE_URL, apiKey: API_KEY })

const log = (...a) => console.log(new Date().toISOString(), ...a)
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

// ── resilience: never let one stray rejection/exception kill the loop ──
process.on('unhandledRejection', (reason) => {
  try { log('!! unhandledRejection (kept alive)', String(reason && reason.stack || reason)) } catch {}
})
process.on('uncaughtException', (err) => {
  try { log('!! uncaughtException (kept alive)', String(err && err.stack || err)) } catch {}
})

// ───────────────────────────── SSRF guard (Node) ────────────────────────────
// SECURITY CRITICAL. Mirrors the proven python guard in extract_brand_theme.py.
// Parse the host; resolve EVERY A/AAAA record; reject if ANY address is private/
// loopback/link-local/reserved/multicast/unspecified — i.e. 10/8, 172.16/12,
// 192.168/16, 127/8, 169.254/16 (incl. 169.254.169.254 metadata), ::1, fc00::/7,
// fe80::/10, IPv4-mapped-IPv6, and the literal `localhost`. Throws on any unsafe
// or unresolvable host so the caller can fail the job BEFORE any egress/Hermes.
const BLOCKED_HOSTNAMES = new Set([
  'localhost', 'localhost.localdomain', 'ip6-localhost', 'ip6-loopback',
])

// Big-endian byte array of an IPv4/IPv6 address (4 or 16 bytes), or null.
function ipBytes(ip) {
  if (net.isIPv4(ip)) return ip.split('.').map((o) => Number(o))
  if (net.isIPv6(ip)) {
    // Expand "::" and any embedded IPv4 tail, return 16 bytes.
    let s = ip.split('%')[0] // strip zone id (fe80::1%eth0)
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

// True when the IP string falls in any private / loopback / link-local /
// reserved / multicast / unspecified / metadata range we must never reach.
function isBlockedIp(ipStr) {
  const ip = (ipStr || '').split('%')[0]
  const b = ipBytes(ip)
  if (!b) return true // un-parseable -> refuse rather than risk it
  if (b.length === 4) {
    const [a, c] = b
    if (a === 10) return true                                  // 10/8
    if (a === 172 && c >= 16 && c <= 31) return true           // 172.16/12
    if (a === 192 && c === 168) return true                    // 192.168/16
    if (a === 127) return true                                 // 127/8 loopback
    if (a === 169 && c === 254) return true                    // 169.254/16 link-local (incl. metadata 169.254.169.254)
    if (a === 100 && c >= 64 && c <= 127) return true          // 100.64/10 CGNAT (reserved)
    if (a === 0) return true                                   // 0.0.0.0/8 unspecified/this-network
    if (a >= 224) return true                                  // 224/4 multicast + 240/4 reserved
    return false
  }
  // IPv6 (16 bytes)
  const allZero = b.every((x) => x === 0)
  if (allZero) return true                                     // :: unspecified
  if (b.slice(0, 15).every((x) => x === 0) && b[15] === 1) return true // ::1 loopback
  if (b[0] === 0xff) return true                               // ff00::/8 multicast
  if (b[0] === 0xfe && (b[1] & 0xc0) === 0x80) return true     // fe80::/10 link-local
  if ((b[0] & 0xfe) === 0xfc) return true                      // fc00::/7 unique-local (ULA)
  // IPv4-mapped (::ffff:a.b.c.d) and IPv4-compatible — unwrap and recheck.
  const first10Zero = b.slice(0, 10).every((x) => x === 0)
  if (first10Zero && b[10] === 0xff && b[11] === 0xff) return isBlockedIp(b.slice(12).join('.'))
  if (first10Zero && b[10] === 0 && b[11] === 0) return isBlockedIp(b.slice(12).join('.')) // ::a.b.c.d compat
  if (ip === 'fd00:ec2::254') return true                      // explicit cloud metadata (belt-and-suspenders)
  return false
}

// Normalize a URL and REJECT private/internal/metadata targets. Returns
// { url, host } on success; throws Error on any unsafe/unresolvable host.
async function assertPublicUrl(rawUrl) {
  let u = String(rawUrl || '').trim()
  if (!u) throw new Error('empty URL')
  if (!/^https?:\/\//i.test(u)) u = 'https://' + u
  let parsed
  try { parsed = new URL(u) } catch (e) { throw new Error('unparseable URL: ' + String(e && e.message || e)) }
  if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') throw new Error('unsupported scheme: ' + parsed.protocol)
  const host = (parsed.hostname || '').replace(/^\[|\]$/g, '') // strip [..] from IPv6 literals
  if (!host) throw new Error('URL has no host')
  const low = host.toLowerCase().replace(/\.$/, '')
  if (BLOCKED_HOSTNAMES.has(low)) throw new Error(`blocked hostname: ${host}`)
  // Host is itself an IP literal -> check directly, no DNS.
  if (net.isIP(low)) {
    if (isBlockedIp(low)) throw new Error(`blocked IP literal: ${host}`)
    return { url: u, host: low }
  }
  // Resolve ALL A/AAAA records; reject if ANY is internal (defends against a
  // name that resolves to a mix of public + private addresses / DNS rebinding).
  let addrs
  try { addrs = await dns.lookup(low, { all: true }) }
  catch (e) { throw new Error(`could not resolve host ${host}: ${String(e && e.code || e)}`) }
  if (!addrs || !addrs.length) throw new Error(`host ${host} resolved to no addresses`)
  for (const a of addrs) {
    if (isBlockedIp(a.address)) throw new Error(`host ${host} resolves to a blocked address ${a.address}`)
  }
  return { url: u, host: low }
}

// ───────────────────────────── dynamic egress ───────────────────────────────
// Allowlist a single (already-SSRF-vetted) host for the sandbox by writing a
// `filmo-dynamic` preset and applying it with `nemoclaw filmo policy-add`. A
// fresh sandbox exec picks the new endpoint up. policy-add is PROVEN to work.
async function ensureEgress(host) {
  const yaml = [
    'preset:',
    '  name: filmo-dynamic',
    '  description: "Per-job target host (rewritten per build)"',
    'network_policies:',
    '  filmo-dynamic:',
    '    name: filmo-dynamic',
    '    endpoints:',
    `      - { host: ${host}, port: 443, access: full }`,
    `      - { host: www.${host}, port: 443, access: full }`,
    '    binaries:',
    '      - { path: "/**" }',
    '',
  ].join('\n')
  try { mkdirSync(join(DYNAMIC_POLICY_PATH, '..'), { recursive: true }) } catch {}
  writeFileSync(DYNAMIC_POLICY_PATH, yaml)
  log(`  egress: wrote policy for ${host} -> ${DYNAMIC_POLICY_PATH}`)
  await new Promise((resolve) => {
    const cmd = `source /root/.nemoclaw-env; export PATH=$HOME/.local/bin:/usr/local/bin:$PATH; ` +
      `nemoclaw filmo policy-add filmo-dynamic --from-file ${DYNAMIC_POLICY_PATH} --yes`
    const child = spawn('bash', ['-lc', cmd], { env: { ...process.env, HOME: '/root' }, stdio: ['ignore', 'pipe', 'pipe'] })
    let out = ''
    child.stdout.on('data', (d) => { out += String(d) })
    child.stderr.on('data', (d) => { out += String(d) })
    const t = setTimeout(() => { try { child.kill('SIGKILL') } catch {}; resolve() }, 60000)
    child.on('error', (e) => { clearTimeout(t); log('  ! policy-add spawn', String(e)); resolve() })
    child.on('close', () => { clearTimeout(t); log(`  egress: policy-add applied for ${host}`, out.trim().slice(-200)); resolve() })
  })
}

// ───────────────────────────── InsForge helpers (reused) ─────────────────────
async function setRun(runId, patch) {
  const { error } = await db.database.from('runs').update(patch).eq('id', runId)
  if (error) log('  ! runs.update', JSON.stringify(error))
}

// Some delivery-metadata columns (notably `producer`) may not exist in the
// `runs` schema. Try the full patch; on an unknown-column / schema error, drop
// optional keys ONE AT A TIME (re-trying after each removal) so columns that DO
// exist (e.g. price_cents, margin, quality) still persist and only the genuinely
// missing column is dropped. `optional` lists keys that are safe to strip, tried
// in order. Returns the keys actually dropped (for a one-line "column missing"
// note). Drops the named optional column if its presence is what fails the write.
async function setRunWithOptional(runId, patch, optional = []) {
  const isSchemaErr = (error) => {
    const msg = JSON.stringify(error).toLowerCase()
    return /column|schema|unknown|does not exist|undefined|unprocessable|400|422|pgrst/.test(msg)
  }
  let attempt = { ...patch }
  const dropped = []
  const droppable = optional.filter((k) => k in patch)
  for (let i = 0; i <= droppable.length; i++) {
    const { error } = await db.database.from('runs').update(attempt).eq('id', runId)
    if (!error) {
      if (dropped.length) log(`  note: runs column(s) missing, delivered without [${dropped.join(', ')}]`)
      return dropped
    }
    if (!isSchemaErr(error) || i === droppable.length) { log('  ! runs.update', JSON.stringify(error)); return dropped }
    // Drop the next optional key and retry. (We can't tell from the error WHICH
    // column is missing, so we peel optional keys off in order until it lands.)
    const k = droppable[i]
    delete attempt[k]
    dropped.push(k)
  }
  return dropped
}

// Append a single run_event (best-effort; never throws into the caller).
let _seq = 1
async function emit(runId, msg, actor = 'hermes', level = 'info') {
  if (!runId) return
  try {
    const seq = Date.now() % 1000000000 + (_seq++)
    await db.database.from('run_events').insert([{ run_id: runId, seq, level, actor, msg }])
  } catch (e) { log('  ! emit', String(e)) }
}

// Render-ready props.json the editor loads; persisted onto the run row.
function readProps(runKey) {
  const p = join(PIPELINE_DIR, 'runs', runKey, 'props.json')
  if (!existsSync(p)) return null
  try { return JSON.parse(readFileSync(p, 'utf8')) } catch { return null }
}

// Idempotent upload: InsForge storage does NOT overwrite — remove the key first.
async function putObject(key, blob) {
  try { await db.storage.from(BUCKET).remove([key]) } catch {}
  const { data, error } = await db.storage.from(BUCKET).upload(key, blob)
  if (error) { log(`  ! storage.upload ${key}`, JSON.stringify(error)); return null }
  return data?.url || null
}

// Upload runs/<runKey>/<name> to <runKey>/final.mp4 in the bucket.
async function uploadVideo(runKey, localName = 'video.mp4', destName = 'final.mp4') {
  const p = join(PIPELINE_DIR, 'runs', runKey, localName)
  if (!existsSync(p)) { log(`  ! uploadVideo: missing ${p}`); return null }
  const blob = new Blob([readFileSync(p)], { type: 'video/mp4' })
  return putObject(`${runKey}/${destName}`, blob)
}

// ───────────────────────────── Hermes (sandbox) ─────────────────────────────
// Invoke Hermes in the `filmo` NemoClaw sandbox to produce the render-ready plan.
// nemoclaw exec rejects newline argv, so the inner script is base64'd. nemoclaw
// exec returns a SPURIOUS non-zero exit even on success, so we validate the
// captured stdout parses as JSON with a `scenes` array instead of trusting code.
function hermesPlan(url) {
  return new Promise((resolve) => {
    // The filmo-producer skill writes /sandbox/plan.canonical.json, but its format is
    // inconsistent — sometimes strict JSON, sometimes a Python-repr dict
    // (single quotes, True/False/None). Normalize it to strict JSON inside the
    // sandbox via ast.literal_eval -> json.dumps so the worker always receives
    // parseable JSON. Emit a sentinel so we can isolate the plan from skill noise.
    const inner = [
      'export HOME=/sandbox',
      'export $(cat /sandbox/.orkey)',
      'cd /sandbox',
      'rm -f /sandbox/plan.canonical.json',
      `hermes chat -q "Produce a render-ready launch video plan for the product at ${url}" -Q -s filmo-producer >/dev/null 2>&1`,
      'echo "<<<PLAN_JSON>>>"',
      `python3 -c 'import ast,json,sys
raw=open("/sandbox/plan.canonical.json").read()
try: d=json.loads(raw)
except Exception: d=ast.literal_eval(raw)
# filmo-producer wraps the plan as [plan_dict, pricing_command]; unwrap to the dict.
if isinstance(d,list):
    d=next((x for x in d if isinstance(x,dict) and "scenes" in x), d[0] if d else {})
print(json.dumps(d))'`,
    ].join('\n')
    const b64 = Buffer.from(inner, 'utf8').toString('base64')
    // Match the proven standalone invocation: a plain foreground child with stdin
    // closed (EOF) so the nemoclaw exec channel terminates when hermes exits — the
    // `exec`+detached variant kept the openshell channel open and the pipe never
    // closed, hanging the worker until timeout. No `exec`; stdin = 'ignore' (EOF).
    const cmd = `source /root/.nemoclaw-env; export PATH=$HOME/.local/bin:/usr/local/bin:$PATH; ` +
      `nemoclaw filmo exec --no-tty -- bash -lc 'echo ${b64} | base64 -d | bash'`
    const child = spawn('bash', ['-lc', cmd], { env: { ...process.env, HOME: '/root' }, stdio: ['ignore', 'pipe', 'pipe'] })
    let out = '', err = '', timedOut = false
    const timer = setTimeout(() => {
      timedOut = true
      try { child.kill('SIGKILL') } catch {}
      // Reap any orphaned sandbox exec the SIGKILL didn't reach (openshell detaches).
      // NOTE: this pkill pattern is BROAD — it kills EVERY `nemoclaw filmo exec`.
      // Safe only because this is a single-daemon host (one worker, sole sandbox
      // user). Do NOT enable concurrent workers without narrowing this match.
      try { spawn('bash', ['-lc', 'pkill -9 -f "nemoclaw filmo exec" 2>/dev/null || true']) } catch {}
      log('  ! hermes timeout (killed)')
    }, HERMES_TIMEOUT_MS)
    let settled = false
    const finish = (plan) => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      resolve(plan)
    }
    const tryParse = () => {
      const marker = out.lastIndexOf('<<<PLAN_JSON>>>')
      if (marker < 0) return null
      const tail = out.slice(marker + '<<<PLAN_JSON>>>'.length)
      const plan = extractJson(tail)
      return (plan && Array.isArray(plan.scenes) && plan.scenes.length) ? plan : null
    }
    // Resolve-on-sentinel: as soon as a complete plan appears after the sentinel,
    // accept it and tear the child down — don't depend on the exec pipe closing
    // (the openshell channel can linger open after hermes already exited).
    let settleTimer = null
    child.stdout.on('data', (d) => {
      out += String(d)
      if (settled) return
      if (tryParse() && !settleTimer) {
        settleTimer = setTimeout(() => {
          const plan = tryParse()
          if (plan) {
            try { child.kill('SIGKILL') } catch {}
            try { spawn('bash', ['-lc', 'pkill -9 -f "nemoclaw filmo exec" 2>/dev/null || true']) } catch {}
            log('  hermes plan captured (resolve-on-sentinel)')
            finish(plan)
          }
        }, 1500)
      }
    })
    child.stderr.on('data', (d) => { err += String(d) })
    child.on('error', (e) => { log('  ! hermes spawn', String(e)); finish(null) })
    child.on('close', () => {
      if (settled) return
      if (timedOut) { log('  ! hermes plan: timed out'); return finish(null) }
      const plan = tryParse() || extractJson(out)
      if (!plan || !Array.isArray(plan.scenes) || !plan.scenes.length) {
        log('  ! hermes plan invalid; stdout tail:', out.slice(-400), '| stderr tail:', err.slice(-300))
        return finish(null)
      }
      finish(plan)
    })
  })
}

// Self-safe orphan clear: the `exec` form is mandatory — a plain `pkill -f
// filmo-producer` self-kills its own wrapper (exit 255). Runs INSIDE the sandbox.
function clearOrphans() {
  return new Promise((resolve) => {
    const cmd = `source /root/.nemoclaw-env; export PATH=$HOME/.local/bin:/usr/local/bin:$PATH; ` +
      `nemoclaw filmo exec --no-tty -- bash -lc 'exec pkill -9 -f filmo-producer'`
    const child = spawn('bash', ['-lc', cmd], { env: { ...process.env, HOME: '/root' }, stdio: ['ignore', 'ignore', 'ignore'] })
    const t = setTimeout(() => { try { child.kill('SIGKILL') } catch {}; resolve() }, 30000)
    child.on('error', () => { clearTimeout(t); resolve() })
    child.on('close', () => { clearTimeout(t); resolve() })
  })
}

// Hermes is the slowest, flakiest stage (sandbox contention can return a null
// plan). Retry up to HERMES_ATTEMPTS times; between attempts clear orphaned
// filmo-producer procs (self-safe `exec pkill`) + brief settle. Returns the
// first valid plan, or null after all attempts.
async function hermesPlanWithRetry(url) {
  for (let attempt = 1; attempt <= HERMES_ATTEMPTS; attempt++) {
    const plan = await hermesPlan(url)
    if (plan) { if (attempt > 1) log(`  hermes plan ok on attempt ${attempt}/${HERMES_ATTEMPTS}`); return plan }
    if (attempt < HERMES_ATTEMPTS) {
      log(`  ! hermes plan null (attempt ${attempt}/${HERMES_ATTEMPTS}); clearing orphans + retrying`)
      await clearOrphans()
      await sleep(3000)
    }
  }
  return null
}

// Pull the first complete top-level JSON object out of a noisy stdout blob.
function extractJson(s) {
  const start = s.indexOf('{')
  if (start < 0) return null
  let depth = 0, inStr = false, esc = false
  for (let i = start; i < s.length; i++) {
    const c = s[i]
    if (inStr) {
      if (esc) esc = false
      else if (c === '\\') esc = true
      else if (c === '"') inStr = false
    } else if (c === '"') inStr = true
    else if (c === '{') depth++
    else if (c === '}') { depth--; if (depth === 0) { try { return JSON.parse(s.slice(start, i + 1)) } catch { return null } } }
  }
  return null
}

// ───────────────────────────── brand theme ─────────────────────────────
// Resolve a render-ready brand_theme.json for the company URL. Order:
//   1) A CURATED hand-authored fixture (e.g. stripe-brand-theme.json) for a
//      known brand — used only for the curated `stripe.com` case.
//   2) REAL extraction via extract_brand_theme.py (live fetch -> real name /
//      tagline / accent / features). This is a strict improvement over the
//      placeholder. Note: the extractor's OWN output path is
//      branding/<host>-brand-theme.json, so we DON'T short-circuit on that file
//      existing (it may be a stale extraction) — we always re-extract fresh.
//   3) On ANY extractor error (nonzero/throw), fall back to the placeholder so
//      the render never lacks a theme.
function brandingDir() { return join(PIPELINE_DIR, 'branding') }

// Write the original neutral placeholder theme (the previous behavior). Kept as
// the guaranteed fallback when live extraction fails. Returns the abs out path.
function writePlaceholderTheme(host) {
  const name = host.replace(/\.[a-z]+$/i, '').replace(/[-_]/g, ' ').replace(/\b\w/g, (m) => m.toUpperCase()) || host
  const stripeShape = join(brandingDir(), 'stripe-brand-theme.json')
  let base = {}
  try { base = JSON.parse(readFileSync(stripeShape, 'utf8')) } catch { base = {} }
  const theme = {
    ...base,
    _comment: `Auto-generated default brand_theme for ${host} (neutral palette; generic features).`,
    brand: name,
    wordmark: name,
    tagline: `${name}`,
    palette: {
      bg: '#ffffff', bgCard: '#ffffff', bgCardRaised: '#f5f7fa',
      navy: '#1a1a2e', navyBright: '#3a3a5c', accent: '#4f46e5',
      ok: '#16a34a', text: '#111827', textMuted: '#4b5563', textDim: '#9ca3af',
      border: '#e5e7eb',
    },
    fonts: {
      fontPrimary: 'Inter, system-ui, -apple-system, sans-serif',
      fontMono: 'ui-monospace, SFMono-Regular, Menlo, monospace',
      fontDisplay: 'Inter, system-ui, sans-serif',
    },
    features: [
      { label: 'Product', value: 'New', sub: 'Built for you', accent: true },
      { label: 'Fast', sub: 'Ships in minutes' },
      { label: 'Simple', sub: 'One integration' },
      { label: 'Reliable', sub: 'Production ready' },
    ],
    cta_url: host,
  }
  const outPath = join(brandingDir(), `${host}-brand-theme.json`)
  try { writeFileSync(outPath, JSON.stringify(theme, null, 2)) } catch (e) { log('  ! write brand theme', String(e)) }
  log(`  brand theme: WROTE placeholder ${outPath}`)
  return outPath
}

function resolveBrandTheme(companyUrl) {
  const host = String(companyUrl || '').replace(/^https?:\/\//, '').replace(/\/.*$/, '').replace(/^www\./, '') || 'brand'
  const dir = brandingDir()
  const outPath = join(dir, `${host}-brand-theme.json`)

  // 1) Curated fixture for known brands ONLY (not the extractor's own
  //    <host>-brand-theme.json output, which may be a stale extraction).
  if (host === 'stripe.com') {
    const curated = join(dir, 'stripe-brand-theme.json')
    if (existsSync(curated)) { log(`  brand theme: curated fixture ${curated}`); return { themePath: curated, host } }
  }

  // 2) REAL extraction (live fetch, SSRF-guarded inside the python). On success
  //    it overwrites <host>-brand-theme.json with the brand's real accent/copy.
  try {
    execFileSync(PYTHON_BIN, [join(PIPELINE_DIR, 'extract_brand_theme.py'), '--url', companyUrl, '--out', outPath],
      { timeout: 60000, stdio: ['ignore', 'pipe', 'pipe'] })
    if (existsSync(outPath)) {
      let accent = ''
      try { accent = (JSON.parse(readFileSync(outPath, 'utf8')).palette || {}).accent || '' } catch {}
      log(`  brand theme: EXTRACTED real theme ${outPath} (accent ${accent})`)
      return { themePath: outPath, host }
    }
    log('  ! brand extract produced no file; falling back to placeholder')
  } catch (e) {
    const msg = String((e && (e.stderr ? e.stderr.toString() : '') ) || (e && e.message) || e).trim().slice(-300)
    log('  ! brand extract failed; falling back to placeholder:', msg)
  }

  // 3) Fallback placeholder so the render never lacks a theme.
  return { themePath: writePlaceholderTheme(host), host }
}

// ───────────────────────────── render (host) ─────────────────────────────
// style_fill.py --plan ... --brand ... --style ... --out runs/<runKey> --render
// Writes runs/<runKey>/video.mp4. Multi-minute; needs ElevenLabs for VO synth.
function render(runKey, planPath, brandPath) {
  return new Promise((resolve) => {
    const outDir = `runs/${runKey}`
    const args = ['style_fill.py',
      '--plan', `${outDir}/plan.json`,
      '--brand', brandPath,
      '--style', STYLE,
      '--out', outDir,
      '--fps', String(FPS),
      '--render']
    // ElevenLabs VO + key.
    let el = {}
    try { for (const line of readFileSync('/root/.el-key', 'utf8').split('\n')) { const [k, ...v] = line.split('='); if (k.trim()) el[k.trim()] = v.join('=').trim() } } catch {}
    const env = { ...process.env, ...el, WS_VO_PROVIDER: 'elevenlabs' }
    const child = spawn(PYTHON_BIN, args, { cwd: PIPELINE_DIR, env })
    const timer = setTimeout(() => { try { child.kill('SIGKILL') } catch {} ; log('  ! render timeout') }, RENDER_TIMEOUT_MS)
    child.stdout.on('data', (d) => { try { process.stdout.write(`  [render] ${d}`) } catch {} })
    child.stderr.on('data', (d) => { try { process.stderr.write(`  [render!] ${d}`) } catch {} })
    child.on('error', (e) => { clearTimeout(timer); log('  ! render spawn', String(e)); resolve(1) })
    child.on('close', (c) => { clearTimeout(timer); resolve(c) })
  })
}

// ───────────────────────────── processJob (Hermes path) ─────────────────────
async function processJob(job) {
  const p = job.params || {}
  const runId = job.run_id
  const runKey = p.run_key || p.runKey
  const url = p.company_url || p.url
  const t0 = Date.now()
  log(`processing job ${job.id} -> run ${runKey} (${url})`)
  await setRun(runId, { status: 'running', phase: 'planning' })

  // 0) SECURITY: SSRF guard FIRST — refuse private/internal/metadata targets
  //    BEFORE any egress policy is written or any Hermes/sandbox exec spawned.
  //    THEN allowlist the (vetted) host for the sandbox. Order is load-bearing:
  //    guard -> allowlist -> read.
  let safeHost
  try {
    const safe = await assertPublicUrl(url)
    safeHost = safe.host
  } catch (e) {
    const reason = 'unsafe url: ' + String(e && e.message || e)
    await setRun(runId, { status: 'failed', phase: 'blocked_url' })
    await db.database.from('jobs').update({ status: 'failed', error: reason }).eq('id', job.id)
    await emit(runId, reason, 'hermes', 'error')
    log(`  BLOCKED run ${runKey}: ${reason}`)
    return
  }
  log(`  ssrf guard ok: ${safeHost} is public`)
  await emit(runId, `Target ${safeHost} verified public; opening egress…`, 'hermes')
  await ensureEgress(safeHost)
  await emit(runId, `Invoking Hermes to plan the launch video for ${url}…`, 'hermes')

  // 1) Hermes plan (sandbox) — retried up to HERMES_ATTEMPTS times.
  const tHermes = Date.now()
  const plan = await hermesPlanWithRetry(url)
  if (!plan) {
    await setRun(runId, { status: 'failed', phase: 'planning_failed' })
    await db.database.from('jobs').update({ status: 'failed', error: 'hermes plan invalid/empty' }).eq('id', job.id)
    await emit(runId, 'Hermes planning failed.', 'hermes', 'error')
    log(`  FAILED run ${runKey} (hermes plan)`)
    return
  }
  const hermesSec = ((Date.now() - tHermes) / 1000).toFixed(1)
  log(`  hermes plan ok: ${plan.scenes.length} scenes (${hermesSec}s)`)
  await emit(runId, `Hermes plan ready: ${plan.scenes.length} scenes.`, 'nemotron')

  // 2) Write plan to runs/<runKey>/plan.json.
  const runDir = join(PIPELINE_DIR, 'runs', runKey)
  try { mkdirSync(runDir, { recursive: true }) } catch {}
  const planPath = join(runDir, 'plan.json')
  try { writeFileSync(planPath, JSON.stringify(plan, null, 2)) } catch (e) {
    await db.database.from('jobs').update({ status: 'failed', error: 'write plan: ' + e }).eq('id', job.id); return
  }

  // 3) Brand theme.
  const { themePath } = resolveBrandTheme(url)

  // 4) Render (detached spawn; multi-minute).
  await setRun(runId, { phase: 'rendering' })
  await emit(runId, 'Rendering on the host (style_fill + ElevenLabs VO)…', 'hermes')
  const tRender = Date.now()
  const code = await render(runKey, planPath, themePath)
  const renderSec = ((Date.now() - tRender) / 1000).toFixed(1)
  const videoPath = join(runDir, 'video.mp4')
  if (code !== 0 || !existsSync(videoPath)) {
    await setRun(runId, { status: 'failed', phase: 'render_failed' })
    await db.database.from('jobs').update({ status: 'failed', error: `render exit ${code}` }).eq('id', job.id)
    await emit(runId, `Render failed (exit ${code}).`, 'hermes', 'error')
    log(`  FAILED run ${runKey} (render exit ${code})`)
    return
  }
  log(`  render ok: ${videoPath} (${renderSec}s)`)

  // 5) Upload + deliver.
  await emit(runId, 'Uploading the finished MP4…', 'hermes')
  const url2 = await uploadVideo(runKey, 'video.mp4', 'final.mp4')
  const props = readProps(runKey)
  if (!url2) {
    await setRun(runId, { status: 'failed', phase: 'upload_failed', final_url: null, props })
    await db.database.from('jobs').update({ status: 'failed', error: 'video upload failed' }).eq('id', job.id)
    log(`  FAILED run ${runKey} (upload failed)`)
    return
  }
  // B4: persist price + margin from the plan; B1: tag the producer; B5: this is
  //     the agent path (Ultra + ElevenLabs) so mark quality premium. `producer`
  //     may not exist in the schema — setRunWithOptional strips it on a schema
  //     error and still lands the core delivery patch (non-fatal).
  const priceCents = Math.max(500, 250 * plan.scenes.length)
  const margin = 0.6
  const dropped = await setRunWithOptional(runId, {
    status: 'delivered', phase: 'delivered', final_url: url2, props,
    producer: 'hermes', price_cents: priceCents, margin, quality: 'premium',
  }, ['producer', 'price_cents', 'margin', 'quality'])
  await db.database.from('jobs').update({ status: 'done' }).eq('id', job.id)
  const totalSec = ((Date.now() - t0) / 1000).toFixed(1)
  await emit(runId, `Delivered. ${totalSec}s total (Hermes ${hermesSec}s + render ${renderSec}s).`, 'hermes')
  log(`  DELIVERED run ${runKey} -> ${url2}  [hermes ${hermesSec}s + render ${renderSec}s = ${totalSec}s total]` +
      ` | producer=hermes price_cents=${priceCents} margin=${margin}` +
      (dropped.length ? ` (dropped missing cols: ${dropped.join(',')})` : ''))
  return { runKey, final_url: url2, hermesSec, renderSec, totalSec, priceCents, margin, droppedCols: dropped }
}

// ───────────────────────────── processOne (SAFE test path) ───────────────────
// Fetch a SPECIFIC queued run/job by run_key and process it. Does NOT call
// claim_next_job (which would grab a real user job).
async function processOne(runKey) {
  const { data: run, error: rErr } = await db.database.from('runs').select('id, run_key, status').eq('run_key', runKey).maybeSingle()
  if (rErr || !run) { log(`processOne: run not found for run_key=${runKey}`, JSON.stringify(rErr)); return null }
  const { data: jobs, error: jErr } = await db.database.from('jobs').select('*').eq('run_id', run.id).order('id', { ascending: true })
  if (jErr) { log('processOne: jobs query error', JSON.stringify(jErr)); return null }
  const job = (jobs || []).find((j) => j.status === 'queued' || j.status === 'claimed') || (jobs || [])[0]
  if (!job) { log(`processOne: no job for run_key=${runKey}`); return null }
  // Mark claimed so it reflects the real lifecycle (without touching other rows).
  try { await db.database.from('jobs').update({ status: 'claimed' }).eq('id', job.id) } catch {}
  return processJob(job)
}

// ───────────────────────────── enqueue (SAFE test job) ───────────────────────
// Enqueue a hermes-test run/job for `companyUrl` (defaults to stripe). The brand
// is derived from the host. The SSRF guard in processJob still vets the url at
// run time — enqueueing an unsafe url is fine; it fails cleanly when processed.
async function enqueueTestJob(companyUrl = 'https://stripe.com') {
  const runKey = `hermes-test-${Date.now()}`
  const userId = '90923fa8-41da-47f2-8d45-81a7dbd3405f'
  const host = String(companyUrl || '').replace(/^https?:\/\//, '').replace(/\/.*$/, '').replace(/^www\./, '') || companyUrl
  const goal = 'A 30-second brand explainer'
  const emphasis = 'what makes the product worth trying'
  const runRow = {
    user_id: userId, run_key: runKey, brand: host, company_url: companyUrl,
    goal, emphasis, quality: 'standard', brain: 'super-free', mode: 'mock', status: 'queued',
  }
  const { data: runRows, error: runErr } = await db.database.from('runs').insert([runRow]).select()
  if (runErr) { log('enqueue runs.insert', JSON.stringify(runErr)); process.exit(1) }
  const runId = runRows[0].id
  const params = { company_url: companyUrl, goal, emphasis, quality: 'standard', brain: 'super-free', mode: 'mock', run_key: runKey, duration: 30 }
  const { error: jobErr } = await db.database.from('jobs').insert([{ run_id: runId, status: 'queued', params }])
  if (jobErr) { log('enqueue jobs.insert', JSON.stringify(jobErr)); process.exit(1) }
  log(`enqueued test job: run ${runKey} (${runId}) for ${companyUrl}`)
  return runKey
}

// ───────────────────────────── daemon loop (live wiring) ─────────────────────
// Built for later live wiring — NOT started by the test paths.
async function daemon() {
  log(`Hermes worker daemon up — ${WORKER_ID}`)
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
async function supervise() {
  for (;;) {
    try { await daemon() }
    catch (e) { log('!! daemon() exited (restarting in 5s)', String(e && e.stack || e)); await sleep(5000) }
  }
}

// ───────────────────────────── entrypoint ─────────────────────
const argv = process.argv.slice(2)
;(async () => {
  if (argv[0] === '--once') {
    const rk = argv[1]
    if (!rk) { console.error('usage: node worker.js --once <run_key>'); process.exit(1) }
    const res = await processOne(rk)
    log('RESULT', JSON.stringify(res))
    process.exit(res && res.final_url ? 0 : 1)
  } else if (argv[0] === '--enqueue-and-run') {
    const rk = await enqueueTestJob()
    const res = await processOne(rk)
    log('RESULT', JSON.stringify(res))
    process.exit(res && res.final_url ? 0 : 1)
  } else if (argv[0] === '--url') {
    const u = argv[1]
    if (!u) { console.error('usage: node worker.js --url <URL>'); process.exit(1) }
    const rk = await enqueueTestJob(u)
    const res = await processOne(rk)
    log('RESULT', JSON.stringify(res))
    // exit 0 only on a delivered MP4; blocked/failed jobs exit 1.
    process.exit(res && res.final_url ? 0 : 1)
  } else {
    // default / --daemon: live claim loop
    supervise()
  }
})()
