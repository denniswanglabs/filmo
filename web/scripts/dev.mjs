#!/usr/bin/env node
/**
 * Filmo safe dev launcher — permanent localhost reliability.
 *
 * Root causes this addresses:
 * 1. Stale Next/Node on :3000 (browser hits broken server; new dev lands on :3001)
 * 2. Corrupt `.next` after bad HMR → 500, vendor-chunks ENOENT, webpack `.call` errors
 * 3. Stale webpack cache in `.next/cache` → SegmentViewNode manifest / chunk mismatches
 *
 * Usage:
 *   npm run dev         — safe start (free ports, clear webpack cache, auto-repair corrupt .next)
 *   npm run dev:clean   — also delete the entire `.next` directory first
 */
import { spawn, execSync } from 'node:child_process'
import { existsSync, readFileSync, rmSync, statSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { setTimeout as sleep } from 'node:timers/promises'

const webRoot = join(dirname(fileURLToPath(import.meta.url)), '..')
const nextDir = join(webRoot, '.next')
const port = process.env.PORT || '3000'
const extraPorts = ['3001']
const forceClean = process.argv.includes('--clean')

/** Kill node/next listeners on dev ports (macOS / Linux). */
function freePort(p) {
  if (process.platform === 'win32') return
  try {
    const pids = execSync(`lsof -tiTCP:${p} -sTCP:LISTEN 2>/dev/null || true`, {
      encoding: 'utf8',
    }).trim()
    if (!pids) return

    for (const pid of pids.split(/\s+/).filter(Boolean)) {
      let cmd = ''
      try {
        cmd = execSync(`ps -p ${pid} -o command= 2>/dev/null`, { encoding: 'utf8' }).trim()
      } catch {
        continue
      }
      if (/next|node/i.test(cmd)) {
        console.log(`[filmo-dev] stopping stale listener on :${p} (pid ${pid})`)
        try {
          process.kill(Number(pid), 'SIGKILL')
        } catch {
          /* already gone */
        }
      }
    }
  } catch {
    /* lsof unavailable */
  }
}

/** Detect a half-written `.next` that causes vendor-chunks / webpack `.call` crashes. */
function isNextCorrupt() {
  if (!existsSync(nextDir)) return false

  const vendorNext = join(nextDir, 'server/vendor-chunks/next.js')
  const pageJs = join(nextDir, 'server/app/page.js')

  // Classic ENOENT: compiled page references vendor-chunks/next but the file is missing.
  if (existsSync(pageJs) && !existsSync(vendorNext)) {
    try {
      const src = readFileSync(pageJs, 'utf8')
      if (src.includes('vendor-chunks/next')) return true
    } catch {
      return true
    }
  }

  // Zero-byte vendor chunk from interrupted write.
  if (existsSync(vendorNext)) {
    try {
      if (statSync(vendorNext).size === 0) return true
    } catch {
      return true
    }
  }

  return false
}

function clearWebpackCache() {
  const cacheDir = join(nextDir, 'cache')
  if (!existsSync(cacheDir)) return
  console.log('[filmo-dev] clearing .next/cache (stale HMR / webpack chunks)')
  rmSync(cacheDir, { recursive: true, force: true })
}

function wipeNext() {
  if (!existsSync(nextDir)) return
  console.log('[filmo-dev] removing .next (corrupt or --clean)')
  rmSync(nextDir, { recursive: true, force: true })
}

async function main() {
  for (const p of [port, ...extraPorts]) freePort(p)
  await sleep(300)

  if (forceClean || isNextCorrupt()) {
    wipeNext()
  } else {
    clearWebpackCache()
  }

  const nextBin = join(webRoot, 'node_modules', '.bin', 'next')
  const child = spawn(nextBin, ['dev', '-p', port], {
    cwd: webRoot,
    stdio: 'inherit',
    env: {
      ...process.env,
      NEXT_TELEMETRY_DISABLED: '1',
    },
  })

  child.on('exit', (code, signal) => {
    if (signal) process.kill(process.pid, signal)
    process.exit(code ?? 0)
  })
}

main().catch((err) => {
  console.error('[filmo-dev] failed to start:', err)
  process.exit(1)
})
