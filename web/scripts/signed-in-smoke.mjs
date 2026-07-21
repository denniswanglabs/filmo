#!/usr/bin/env node
// ═════════════════════════════════════════════════════════════════════════════
// signed-in-smoke.mjs — the signed-in smoke harness for the Filmo web app.
//
// WHAT IT COVERS
//   The signed-in journeys that shipped broken this week — the ones a build
//   passes tsc and unit tests but still gets wrong, because they only fail in a
//   real browser holding a real session. Six checks, each a PASS/FAIL line:
//     1. OAuth return   — /?insforge_code=TEST → PKCE exchange → session written →
//                          signed-in paint → no stash → lands /overview.
//     2. Stash resume   — a pending build stashed before sign-in → signed-in
//                          arrival on / → createBuild fires → router lands on the run.
//     3. Composer submit — type a URL on /new → submit → run created → /runs/<id>.
//     4. False-logout belt — access token expired mid-session, refresh token still
//                          valid → visit /videos → EXACTLY ONE refresh POST, and
//                          NO sign-in gate (the invariant the belt exists to hold).
//     5. Sign-out       — session cleared, pending stash cleared, lands /login.
//     6. /login post-auth — signed in with no stash → /overview; with a stash →
//                          resume onto the run.
//
//   None of it touches the real InsForge or the real worker: a zero-dependency
//   mock InsForge (scripts/lib/mock-insforge.mjs) scripts the auth surface and
//   absorbs runs/jobs writes, minting its OWN fake JWTs. No secret is read or
//   printed anywhere. The app is the REAL Next.js app, booted in an isolated
//   sandbox (its own .next, a mock-pointed .env.local) so it never touches a
//   running dev server or the repo's build. The browser is the already-cached
//   Chromium driven over CDP (no Playwright install; see scripts/lib/browser.mjs).
//
// HOW TO RUN
//   node web/scripts/signed-in-smoke.mjs
//   Exit code 0 = all pass; non-zero = at least one FAIL (CI-gateable). ~<3 min.
//
// CATCH-PROOF (does the harness actually catch a regression?)
//   SMOKE_SABOTAGE=false-logout node web/scripts/signed-in-smoke.mjs
//   injects a known regression into the SANDBOX COPY ONLY (never the repo) and
//   check 4 flips to FAIL with a pointed message. Off by default.
//
// HOW TO ADD A CHECK
//   Append to CHECKS below: give it a name and an async (ctx) => void that throws
//   on failure. `ctx` provides: page (the CDP driver), app/mock URLs, and helpers
//   mintSession({email,ttlSec}), seed({local,session}), gotoAndSettle(url),
//   resetMock(), seedRows(table,rows), refreshCount(), writes(table), assert().
//   Reset the mock first, seed the storage the flow needs, drive, then assert
//   against the DOM and the mock's server-side request/write log.
// ═════════════════════════════════════════════════════════════════════════════
import { startMockInsforge } from './lib/mock-insforge.mjs'
import { startApp } from './lib/app.mjs'
import { launchBrowser } from './lib/browser.mjs'

const t0 = Date.now()
const log = (...a) => console.log(...a)

// ── The signed-in journeys, as checks ────────────────────────────────────────
const CHECKS = [
  {
    name: '1. OAuth return → session written → /overview',
    async run(ctx) {
      await ctx.resetMock()
      // A real Google return: the PKCE verifier is in sessionStorage (signInWithGoogle
      // stored it before the redirect), no session yet, and ?insforge_code in the URL.
      await ctx.seed({ session: { insforge_pkce_verifier: 'smoke-verifier' } })
      await ctx.gotoAndSettle('/?insforge_code=TEST')
      await ctx.page.waitFor("return location.pathname === '/overview'", { timeout: 30000 })
      // signed-in paint, not the gate
      const paint = await ctx.page.waitFor(
        "return !!document.querySelector('.ov-greet') && !/Sign in to see your overview/.test(document.body.innerText)",
        { timeout: 15000 },
      )
      ctx.assert(paint, 'overview signed-in paint (.ov-greet present, no gate)')
      const session = await ctx.page.storage('localStorage', 'insforge_session_v1')
      ctx.assert(session && JSON.parse(session).accessToken, 'insforge_session_v1 written with an accessToken')
      const exch = await ctx.get('/__mock/requests?method=POST&path=/api/auth/oauth/exchange')
      ctx.assert(exch.count === 1, `exactly one PKCE exchange POST (observed ${exch.count})`)
      return 'exchanged, session written, landed /overview'
    },
  },
  {
    name: '2. Stash resume → createBuild fires → /runs/<id>',
    async run(ctx) {
      await ctx.resetMock()
      const s = await ctx.mintSession({})
      await ctx.seed({
        local: sessionLocal(s),
        session: {
          ws_pending_build: JSON.stringify({
            url: 'https://stripe.com', brain: 'ultra-paid', look: 'walkrec', requirePay: false,
          }),
        },
      })
      await ctx.gotoAndSettle('/')
      await ctx.page.waitFor("return location.pathname.startsWith('/runs/')", { timeout: 30000 })
      const runs = await ctx.writes('runs')
      const jobs = await ctx.writes('jobs')
      ctx.assert(runs.length === 1, `createBuild inserted exactly one runs row (observed ${runs.length})`)
      ctx.assert(jobs.length === 1, `createBuild inserted exactly one jobs row (observed ${jobs.length})`)
      ctx.assert(runs[0].company_url === 'https://stripe.com', 'the run carries the stashed URL')
      const stash = await ctx.page.storage('sessionStorage', 'ws_pending_build')
      ctx.assert(!stash, 'pending stash consumed (cleared)')
      return `resumed build → ${await ctx.page.pathname()}`
    },
  },
  {
    name: '3. Composer submit (signed in) → run created',
    async run(ctx) {
      await ctx.resetMock()
      const s = await ctx.mintSession({})
      await ctx.seed({ local: sessionLocal(s) })
      await ctx.gotoAndSettle('/new')
      await ctx.page.waitFor("return !!document.querySelector('input[aria-label=\"Product URL\"]')", { timeout: 20000 })
      await ctx.page.fillInput('input[aria-label="Product URL"]', 'https://linear.app')
      await ctx.page.waitFor("return !document.querySelector('.nf-send').disabled", { timeout: 10000 })
      await ctx.page.click('.nf-send')
      await ctx.page.waitFor("return location.pathname.startsWith('/runs/')", { timeout: 30000 })
      const runs = await ctx.writes('runs')
      ctx.assert(runs.length === 1, `submit created exactly one run (observed ${runs.length})`)
      ctx.assert(runs[0].company_url === 'https://linear.app', 'the run carries the typed URL')
      return `typed → Enter → cover → ${await ctx.page.pathname()}`
    },
  },
  {
    name: '4. False-logout belt on /videos (one refresh, no gate)',
    async run(ctx) {
      await ctx.resetMock()
      // Access token already expired; refresh token still valid in localStorage.
      const s = await ctx.mintSession({ ttlSec: -60 })
      await ctx.seedRows('runs', [{
        user_id: s.user.id, brand: 'Belt Smoke', company_url: 'https://stripe.com',
        goal: 'A 30-second brand explainer', quality: 'standard', status: 'delivered',
        phase: 'done', price_cents: 0, margin: null, final_url: null, film_mode: 'classic',
      }])
      await ctx.seed({ local: sessionLocal(s) })
      await ctx.gotoAndSettle('/videos')
      // Wait for a TERMINAL state: the library grid, the empty state, or the gate.
      await ctx.page.waitFor(
        "return !!document.querySelector('.lib-grid, .lib-empty, .lib-gate')",
        { timeout: 30000 },
      )
      await sleep(600) // let any (buggy) late second refresh land before we count
      const gate = await ctx.page.evaluate("return /Sign in to see your filmos/.test(document.body.innerText)")
      ctx.assert(!gate, 'NO sign-in gate for a session holding a valid refresh token')
      const refresh = await ctx.refreshCount()
      ctx.assert(refresh === 1, `exactly one refresh POST (observed ${refresh})`)
      const rendered = await ctx.page.evaluate("return !!document.querySelector('.lib-grid, .lib-empty')")
      ctx.assert(rendered, 'the library rendered (not stuck on a loader)')
      return `1 refresh, no gate, library rendered`
    },
  },
  {
    name: '5. Sign-out → session + stash cleared → /login',
    async run(ctx) {
      await ctx.resetMock()
      const s = await ctx.mintSession({})
      await ctx.seed({
        local: sessionLocal(s),
        session: { ws_pending_build: JSON.stringify({ url: 'https://stripe.com', brain: 'ultra-paid', requirePay: false }) },
      })
      await ctx.gotoAndSettle('/overview')
      await ctx.page.waitFor("return !!document.querySelector('.wkacct-btn')", { timeout: 20000 })
      await ctx.page.click('.wkacct-btn')
      await ctx.page.waitFor("return !!document.querySelector('.wkacct-menu')", { timeout: 8000 })
      await ctx.page.clickByText('.wkacct-item', 'Sign out')
      await ctx.page.waitFor("return location.pathname === '/login'", { timeout: 20000 })
      const session = await ctx.page.storage('localStorage', 'insforge_session_v1')
      const stash = await ctx.page.storage('sessionStorage', 'ws_pending_build')
      ctx.assert(!session, 'insforge_session_v1 cleared on sign-out')
      ctx.assert(!stash, 'pending stash cleared on sign-out')
      const out = await ctx.get('/__mock/requests?method=POST&path=/api/auth/logout')
      ctx.assert(out.count >= 1, `logout POST sent (observed ${out.count})`)
      return 'session + stash cleared, landed /login'
    },
  },
  {
    name: '6. /login post-auth (no stash → /overview; stash → resume)',
    async run(ctx) {
      // 6a — no stash → /overview
      await ctx.resetMock()
      const s1 = await ctx.mintSession({})
      await ctx.seed({ local: sessionLocal(s1) })
      await ctx.gotoAndSettle('/login')
      await ctx.page.waitFor("return location.pathname === '/overview'", { timeout: 30000 })

      // 6b — with a stash → resume onto the run
      await ctx.resetMock()
      const s2 = await ctx.mintSession({})
      await ctx.seed({
        local: sessionLocal(s2),
        session: { ws_pending_build: JSON.stringify({ url: 'https://vercel.com', brain: 'ultra-paid', look: 'walkrec', requirePay: false }) },
      })
      await ctx.gotoAndSettle('/login')
      await ctx.page.waitFor("return location.pathname.startsWith('/runs/')", { timeout: 30000 })
      const runs = await ctx.writes('runs')
      ctx.assert(runs.length === 1 && runs[0].company_url === 'https://vercel.com', 'stash resumed into a created run')
      return 'no-stash → /overview; stash → resumed onto /runs/<id>'
    },
  },
]

// ── Runner ────────────────────────────────────────────────────────────────────
async function main() {
  if (process.env.SMOKE_SABOTAGE) {
    log(`\n  ⚠ SMOKE_SABOTAGE=${process.env.SMOKE_SABOTAGE} — this run is a CATCH-PROOF; expect a FAIL. Never set in CI.\n`)
  }
  log('booting mock InsForge…')
  const mock = await startMockInsforge()
  log(`  mock at ${mock.url}`)
  log('booting the app (isolated next dev sandbox)…')
  const app = await startApp({ mockUrl: mock.url, log })
  log(`  app at ${app.url}`)
  log('warming routes…')
  await Promise.all(['/', '/overview', '/videos', '/new', '/login', '/runs/warm']
    .map((p) => fetch(app.url + p).catch(() => {})))
  log('launching Chromium (CDP)…')
  const browser = await launchBrowser()

  // Establish the invariant: we sit on the app origin with a live document, so
  // each check can prime storage (clear + set) before navigating to its target.
  await browser.page.goto(app.url + '/login')

  const ctx = makeCtx({ page: browser.page, app, mock })

  const results = []
  for (const check of CHECKS) {
    const started = Date.now()
    try {
      const detail = await check.run(ctx)
      results.push({ name: check.name, pass: true, detail })
      log(`PASS  ${check.name}\n        → ${detail}  (${((Date.now() - started) / 1000).toFixed(1)}s)`)
    } catch (err) {
      results.push({ name: check.name, pass: false, detail: err.message })
      log(`FAIL  ${check.name}\n        → ${err.message}  (${((Date.now() - started) / 1000).toFixed(1)}s)`)
    }
  }

  await browser.close()
  await app.close()
  await mock.close()

  const passed = results.filter((r) => r.pass).length
  const secs = ((Date.now() - t0) / 1000).toFixed(1)
  log(`\n${passed}/${results.length} checks passed in ${secs}s`)
  process.exit(passed === results.length ? 0 : 1)
}

// ── Check context / helpers ───────────────────────────────────────────────────
function makeCtx({ page, app, mock }) {
  const post = async (path, body) => {
    const res = await fetch(mock.url + path, {
      method: 'POST', headers: { 'content-type': 'application/json' },
      body: body ? JSON.stringify(body) : undefined,
    })
    return res.json()
  }
  const get = async (path) => (await fetch(mock.url + path)).json()
  return {
    page, app, mock, get,
    assert(cond, label) { if (!cond) throw new Error(`expected: ${label}`) },
    resetMock: () => post('/__mock/reset'),
    mintSession: ({ email, ttlSec } = {}) => post('/__mock/session', { email, ttlSec }),
    seedRows: (table, rows) => post('/__mock/seed', { table, rows }),
    writes: async (table) => (await get(`/__mock/writes?table=${table}`)).rows,
    refreshCount: async () => (await get('/__mock/requests?method=POST&path=/api/auth/refresh')).count,
    // Prime storage on the current (app-origin) document, then it's the caller's
    // job to navigate — the fresh load reads exactly what we planted.
    async seed({ local = {}, session = {} } = {}) {
      const sets = [
        'localStorage.clear(); sessionStorage.clear();',
        ...Object.entries(local).map(([k, v]) => `localStorage.setItem(${JSON.stringify(k)}, ${JSON.stringify(v)});`),
        ...Object.entries(session).map(([k, v]) => `sessionStorage.setItem(${JSON.stringify(k)}, ${JSON.stringify(v)});`),
        'return true;',
      ].join('\n')
      await page.evaluate(sets)
    },
    async gotoAndSettle(path) {
      await page.goto(app.url + path)
    },
  }
}

// A signed-in localStorage seed: the durable session + the "has ever signed in"
// flag a returning visitor carries.
function sessionLocal(s) {
  return {
    insforge_session_v1: JSON.stringify({ accessToken: s.accessToken, user: s.user, refreshToken: s.refreshToken }),
    filmo_has_signed_in: '1',
  }
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

main().catch((err) => {
  console.error('\nHARNESS ERROR:', err?.stack || err)
  process.exit(2)
})
