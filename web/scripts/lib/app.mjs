// ─────────────────────────────────────────────────────────────────────────────
// app.mjs — boot the REAL Filmo web app against the mock, in total isolation.
//
// The hard rule (see the harness header): never touch a running dev server or the
// repo's own `.next`. So we build a throwaway sandbox — the web source rsync'd
// into an OS temp dir, with node_modules and public SYMLINKED (no multi-hundred-MB
// copy) — write it its own `.env.local` pointing at the mock, and run `next dev`
// there with its own cwd and therefore its own `.next`. Nothing under the repo is
// written, and we deliberately avoid ports 3000/3001 (the repo's dev launcher
// culls listeners there).
//
// The sandbox is the seam the catch-proof uses too: SMOKE_SABOTAGE patches a file
// IN THE SANDBOX ONLY, so a deliberately-broken run can never dirty the repo.
// ─────────────────────────────────────────────────────────────────────────────
import { spawn, execFileSync } from 'node:child_process'
import { mkdtempSync, symlinkSync, writeFileSync, rmSync, existsSync, readFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import net from 'node:net'
import { setTimeout as sleep } from 'node:timers/promises'

const WEB_ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..') // web/

function getFreePort() {
  return new Promise((resolve, reject) => {
    const srv = net.createServer()
    srv.on('error', reject)
    srv.listen(0, '127.0.0.1', () => {
      const p = srv.address().port
      srv.close(() => resolve(p))
    })
  })
}

// Copy the source (excluding the heavy/secret bits), symlink the rest.
function buildSandbox() {
  const dir = mkdtempSync(join(tmpdir(), 'filmo-smoke-app-'))
  execFileSync('rsync', [
    '-a',
    '--exclude', 'node_modules',
    '--exclude', '.next',
    '--exclude', 'public',
    '--exclude', '.git',
    '--exclude', '.vercel',
    '--exclude', '.env',
    '--exclude', '.env.local',
    '--exclude', '.env.*',
    '--exclude', '*.tsbuildinfo',
    WEB_ROOT + '/', dir + '/',
  ])
  symlinkSync(join(WEB_ROOT, 'node_modules'), join(dir, 'node_modules'))
  symlinkSync(join(WEB_ROOT, 'public'), join(dir, 'public'))
  return dir
}

// The mock-pointed env. No real secret is used — the mock validates by lookup,
// not by key, so these are arbitrary non-empty placeholders.
function writeEnv(dir, mockUrl) {
  const env = [
    `NEXT_PUBLIC_INSFORGE_URL=${mockUrl}`,
    `NEXT_PUBLIC_INSFORGE_ANON_KEY=smoke-anon-key`,
    `INSFORGE_URL=${mockUrl}`,
    `INSFORGE_API_KEY=smoke-admin-key`,
    `INSFORGE_BUCKET=walk-videos`,
    `DEV_MODE_KEY=smoke-dev-key`,
    `NEXT_PUBLIC_DEMO_EMAIL=smoke.user@filmo.test`,
    `NEXT_PUBLIC_DEMO_PASSWORD=smoke-pass`,
    '',
  ].join('\n')
  writeFileSync(join(dir, '.env.local'), env)
}

// SMOKE_SABOTAGE=<name> — inject a known regression into the SANDBOX COPY so the
// catch-proof can show the harness failing. Off by default; never writes the repo.
function applySabotage(dir, name) {
  const insforgePath = join(dir, 'lib', 'insforge.ts')
  const src = readFileSync(insforgePath, 'utf8')
  if (name === 'false-logout') {
    // Regress ensureFreshAccessToken to a PERMANENT NO-OP — the exact observable
    // behaviour of bug #1 documented in insforge.ts (the settled-flight trap: "one
    // getToken() while the token was fresh made this function a permanent no-op…
    // every server action 401'd, and /overview showed the sign-in gate to a user
    // whose refresh token sat valid the whole time"). With refresh never firing,
    // the /videos belt cannot recover an expired access token and the sign-in gate
    // appears — which is precisely what the belt check must catch.
    const anchor = '): Promise<FreshnessOutcome> {\n  // Join any in-progress flight.'
    if (!src.includes(anchor)) throw new Error('sabotage "false-logout" anchor not found in insforge.ts')
    const patched = src.replace(
      anchor,
      "): Promise<FreshnessOutcome> {\n  return 'ok' // SMOKE_SABOTAGE: choke point regressed to a no-op\n  // Join any in-progress flight.",
    )
    writeFileSync(insforgePath, patched)
    return
  }
  throw new Error(`unknown SMOKE_SABOTAGE: ${name}`)
}

export async function startApp({ mockUrl, log = () => {} }) {
  const dir = buildSandbox()
  writeEnv(dir, mockUrl)
  const sabotage = process.env.SMOKE_SABOTAGE
  if (sabotage) {
    applySabotage(dir, sabotage)
    log(`  !! SMOKE_SABOTAGE=${sabotage} applied to sandbox copy ONLY (repo untouched)`)
  }

  const port = await getFreePort()
  const nextBin = join(dir, 'node_modules', 'next', 'dist', 'bin', 'next')
  if (!existsSync(nextBin)) throw new Error(`next binary not found at ${nextBin}`)

  const proc = spawn(process.execPath, [nextBin, 'dev', '-p', String(port)], {
    cwd: dir,
    detached: true,
    env: {
      ...process.env,
      NODE_ENV: 'development',
      NEXT_TELEMETRY_DISABLED: '1',
      BROWSER: 'none',
      NEXT_PUBLIC_INSFORGE_URL: mockUrl,
      NEXT_PUBLIC_INSFORGE_ANON_KEY: 'smoke-anon-key',
      INSFORGE_URL: mockUrl,
      INSFORGE_API_KEY: 'smoke-admin-key',
      INSFORGE_BUCKET: 'walk-videos',
      DEV_MODE_KEY: 'smoke-dev-key',
    },
    stdio: ['ignore', 'pipe', 'pipe'],
  })
  let stderrTail = ''
  proc.stdout.on('data', (d) => { const s = d.toString(); if (/error|Error/.test(s)) log('  [next] ' + s.trim().slice(0, 200)) })
  proc.stderr.on('data', (d) => { stderrTail = (stderrTail + d.toString()).slice(-2000) })

  const baseUrl = `http://127.0.0.1:${port}`
  // Wait for the dev server to accept connections (the first hit compiles routes).
  const deadline = Date.now() + 90000
  let ready = false
  while (Date.now() < deadline) {
    if (proc.exitCode != null) throw new Error(`next dev exited early (${proc.exitCode}). stderr:\n${stderrTail}`)
    try {
      const res = await fetch(baseUrl + '/login', { signal: AbortSignal.timeout(4000) })
      if (res.status) { ready = true; break }
    } catch { /* not up yet */ }
    await sleep(500)
  }
  if (!ready) throw new Error(`next dev did not become ready in 90s. stderr:\n${stderrTail}`)

  return {
    url: baseUrl,
    port,
    dir,
    close: async () => {
      try { process.kill(-proc.pid, 'SIGKILL') } catch { try { proc.kill('SIGKILL') } catch { /* ignore */ } }
      await sleep(200)
      try { rmSync(dir, { recursive: true, force: true }) } catch { /* ignore */ }
    },
  }
}
