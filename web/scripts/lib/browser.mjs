// ─────────────────────────────────────────────────────────────────────────────
// browser.mjs — a tiny Chrome DevTools Protocol driver, zero npm dependencies.
//
// Why not Playwright: no `playwright`/`playwright-core` package is installed
// anywhere on this machine (checked), and pulling one in would add a network
// install to a harness meant to run before a deploy. Chromium itself IS already
// cached (Playwright's own `chrome-headless-shell`), and Node 22 ships a global
// `WebSocket` — so we launch that cached binary with `--remote-debugging-port`
// and speak CDP over the built-in WebSocket. That is the whole dependency story.
//
// It exposes just enough: seed storage before load (addInitScript), navigate,
// evaluate expressions, poll for a condition, fill a React-controlled input, and
// click. Everything the checks need, nothing they don't.
// ─────────────────────────────────────────────────────────────────────────────
import { spawn } from 'node:child_process'
import { readFileSync, existsSync, mkdtempSync, rmSync, readdirSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { setTimeout as sleep } from 'node:timers/promises'

// Highest-versioned cached chrome-headless-shell (falls back to full Chromium).
function findChromiumBinary() {
  const cache = join(process.env.HOME || '', 'Library/Caches/ms-playwright')
  const candidates = []
  if (existsSync(cache)) {
    for (const dir of readdirSync(cache)) {
      const shell = join(cache, dir, 'chrome-headless-shell-mac-arm64', 'chrome-headless-shell')
      if (existsSync(shell)) candidates.push({ dir, bin: shell, kind: 'shell' })
      const full = join(cache, dir, 'chrome-mac-arm64', 'Google Chrome for Testing.app',
        'Contents/MacOS/Google Chrome for Testing')
      if (existsSync(full)) candidates.push({ dir, bin: full, kind: 'full' })
    }
  }
  if (!candidates.length) throw new Error('No cached Chromium found under ~/Library/Caches/ms-playwright')
  // Prefer chrome-headless-shell, then the newest version number.
  candidates.sort((a, b) => {
    if (a.kind !== b.kind) return a.kind === 'shell' ? -1 : 1
    return (parseInt(b.dir.replace(/\D/g, ''), 10) || 0) - (parseInt(a.dir.replace(/\D/g, ''), 10) || 0)
  })
  return candidates[0].bin
}

export async function launchBrowser() {
  const bin = findChromiumBinary()
  const userDataDir = mkdtempSync(join(tmpdir(), 'filmo-smoke-chrome-'))
  const proc = spawn(bin, [
    '--headless=new',
    '--disable-gpu',
    '--no-first-run',
    '--no-default-browser-check',
    '--disable-dev-shm-usage',
    '--remote-debugging-port=0',
    `--user-data-dir=${userDataDir}`,
    'about:blank',
  ], { stdio: ['ignore', 'ignore', 'pipe'] })

  // The chosen port is written to <user-data-dir>/DevToolsActivePort (line 1).
  const portFile = join(userDataDir, 'DevToolsActivePort')
  let port = null
  for (let i = 0; i < 100; i++) {
    if (existsSync(portFile)) {
      const l = readFileSync(portFile, 'utf8').split('\n')[0].trim()
      if (l) { port = l; break }
    }
    await sleep(100)
  }
  if (!port) throw new Error('Chromium did not expose a DevTools port')

  const ver = await fetchJson(`http://127.0.0.1:${port}/json/version`)
  const cdp = await connectCdp(ver.webSocketDebuggerUrl)

  // One tab, attached flat so every command/event carries its sessionId.
  const { targetId } = await cdp.send('Target.createTarget', { url: 'about:blank' })
  const { sessionId } = await cdp.send('Target.attachToTarget', { targetId, flatten: true })
  await cdp.send('Page.enable', {}, sessionId)
  await cdp.send('Runtime.enable', {}, sessionId)

  const page = makePage(cdp, sessionId)

  return {
    page,
    close: async () => {
      try { await cdp.send('Target.closeTarget', { targetId }) } catch { /* ignore */ }
      cdp.close()
      try { proc.kill('SIGKILL') } catch { /* ignore */ }
      try { rmSync(userDataDir, { recursive: true, force: true }) } catch { /* ignore */ }
    },
  }
}

function makePage(cdp, sessionId) {
  const send = (method, params) => cdp.send(method, params, sessionId)

  async function evaluate(expression) {
    const { result, exceptionDetails } = await send('Runtime.evaluate', {
      expression: `(() => { ${expression} })()`,
      awaitPromise: true,
      returnByValue: true,
    })
    if (exceptionDetails) {
      throw new Error(
        'evaluate failed: ' +
          (exceptionDetails.exception?.description || exceptionDetails.text || 'unknown'),
      )
    }
    return result?.value
  }

  return {
    evaluate,

    // Runs before any page script on the NEXT (and every) navigation — the CDP
    // equivalent of Playwright's addInitScript. Used to plant a signed-in session
    // in localStorage before lib/auth.tsx reads it.
    async addInitScript(source) {
      await send('Page.addScriptToEvaluateOnNewDocument', { source })
    },

    async goto(url, { timeout = 45000 } = {}) {
      await send('Page.navigate', { url })
      // Wait for the document to finish, then for React to have mounted something.
      await this.waitFor('return document.readyState === "complete"', { timeout })
    },

    // Poll an expression (its `return` value coerced to boolean) until truthy.
    async waitFor(expression, { timeout = 15000, interval = 150 } = {}) {
      const deadline = Date.now() + timeout
      let last
      for (;;) {
        try {
          last = await evaluate(expression)
          if (last) return last
        } catch (e) {
          last = e.message
        }
        if (Date.now() > deadline) {
          throw new Error(`waitFor timed out after ${timeout}ms (last: ${JSON.stringify(last)})`)
        }
        await sleep(interval)
      }
    },

    pathname() {
      return evaluate('return location.pathname + location.search')
    },

    bodyText() {
      return evaluate('return document.body ? document.body.innerText : ""')
    },

    // Fill a React-controlled <input>: React tracks the value via a native
    // setter, so assigning .value directly is ignored — we call the prototype
    // setter and dispatch a bubbling `input` event, which is what syncs state.
    async fillInput(selector, value) {
      return evaluate(`
        const el = document.querySelector(${JSON.stringify(selector)});
        if (!el) throw new Error('no element ' + ${JSON.stringify(selector)});
        const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
        setter.call(el, ${JSON.stringify(value)});
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
        return true;
      `)
    },

    async click(selector) {
      return evaluate(`
        const el = document.querySelector(${JSON.stringify(selector)});
        if (!el) throw new Error('no element ' + ${JSON.stringify(selector)});
        el.click();
        return true;
      `)
    },

    // Click the first element whose trimmed text matches — for buttons the app
    // labels by their words ("Sign out") rather than a stable selector.
    async clickByText(selector, text) {
      return evaluate(`
        const els = [...document.querySelectorAll(${JSON.stringify(selector)})];
        const el = els.find(e => (e.textContent || '').trim() === ${JSON.stringify(text)});
        if (!el) throw new Error('no ' + ${JSON.stringify(selector)} + ' with text ' + ${JSON.stringify(text)});
        el.click();
        return true;
      `)
    },

    storage(area, key) {
      return evaluate(`return window.${area}.getItem(${JSON.stringify(key)});`)
    },
  }
}

// ── Minimal CDP-over-WebSocket transport ──────────────────────────────────────
async function connectCdp(wsUrl) {
  const ws = new WebSocket(wsUrl)
  await new Promise((resolve, reject) => {
    ws.addEventListener('open', resolve, { once: true })
    ws.addEventListener('error', reject, { once: true })
  })
  let nextId = 1
  const pending = new Map()
  ws.addEventListener('message', (ev) => {
    let msg
    try { msg = JSON.parse(ev.data) } catch { return }
    if (msg.id && pending.has(msg.id)) {
      const { resolve, reject } = pending.get(msg.id)
      pending.delete(msg.id)
      if (msg.error) reject(new Error(`CDP ${msg.error.message || JSON.stringify(msg.error)}`))
      else resolve(msg.result)
    }
  })
  return {
    send(method, params = {}, sessionId) {
      const id = nextId++
      const payload = { id, method, params }
      if (sessionId) payload.sessionId = sessionId
      return new Promise((resolve, reject) => {
        pending.set(id, { resolve, reject })
        ws.send(JSON.stringify(payload))
        setTimeout(() => {
          if (pending.has(id)) {
            pending.delete(id)
            reject(new Error(`CDP ${method} timed out`))
          }
        }, 30000)
      })
    },
    close() { try { ws.close() } catch { /* ignore */ } },
  }
}

async function fetchJson(url) {
  const res = await fetch(url)
  return res.json()
}
