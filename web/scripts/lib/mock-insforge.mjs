// ─────────────────────────────────────────────────────────────────────────────
// mock-insforge.mjs — an ephemeral, in-memory stand-in for the InsForge backend,
// good enough to boot the real Filmo web app and the real @insforge/sdk against.
//
// It is NOT a general InsForge emulator. It speaks exactly the slice of the wire
// protocol the app exercises on the signed-in journeys (see signed-in-smoke.mjs):
//   • Auth: PKCE code exchange, session verify, refresh-with-rotation, password
//     login/signup, logout, public-config.
//   • Data: the PostgREST records API for runs/jobs/credit_ledger/run_events/
//     agent_events/developers — enough filtering (eq/neq/gt/gte/lt/lte/in/order/
//     limit) + insert-returning to absorb createBuild's writes and answer the
//     owner-scoped reads.
//
// It mints its OWN fake JWTs (unsigned-payload style: real base64url header +
// payload with a real `exp`/`sub`, a throwaway signature the mock never checks
// cryptographically). NO SECRET is read, stored, or emitted anywhere.
//
// The mock is also the harness's source of truth: it records every request and
// every write, and exposes them under /__mock/* so a check can assert "exactly
// one refresh POST" or "createBuild inserted a runs row" against server-side
// fact rather than a flaky client probe.
// ─────────────────────────────────────────────────────────────────────────────
import http from 'node:http'
import { randomUUID, randomBytes } from 'node:crypto'

const b64url = (buf) =>
  Buffer.from(buf).toString('base64').replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')

// A JWT the app can decode: header + payload carry a real `exp`/`sub`/`email`,
// the signature is random (the mock validates by looking the token up, never by
// verifying a signature — there is no key anywhere).
function mintJwt({ sub, email, ttlSec }) {
  const now = Math.floor(Date.now() / 1000)
  const header = b64url(JSON.stringify({ alg: 'HS256', typ: 'JWT' }))
  const payload = b64url(
    JSON.stringify({ sub, email, role: 'authenticated', iat: now, exp: now + ttlSec }),
  )
  return `${header}.${payload}.${b64url(randomBytes(24))}`
}

function decodeJwt(token) {
  try {
    const part = token.split('.')[1]
    let s = part.replace(/-/g, '+').replace(/_/g, '/')
    while (s.length % 4) s += '='
    return JSON.parse(Buffer.from(s, 'base64').toString('utf8'))
  } catch {
    return null
  }
}

// Deterministic user id per email — so a session minted for a given email always
// names the same owner, and reads seeded for that id line up with it.
const USER_IDS = new Map()
function userIdFor(email) {
  if (!USER_IDS.has(email)) USER_IDS.set(email, randomUUID())
  return USER_IDS.get(email)
}

export async function startMockInsforge() {
  // ── State (all in-memory, reset by POST /__mock/reset) ──────────────────────
  const users = new Map() // userId -> { id, email }
  const validRefresh = new Map() // refreshToken -> userId  (rotated on every use)
  const tables = freshTables()
  let requestLog = [] // { ts, method, path, refreshTokenSeen? }

  function freshTables() {
    return {
      runs: [],
      jobs: [],
      credit_ledger: [],
      run_events: [],
      agent_events: [],
      developers: [],
    }
  }

  function registerSession(email, ttlSec) {
    const id = userIdFor(email)
    users.set(id, { id, email })
    const accessToken = mintJwt({ sub: id, email, ttlSec })
    const refreshToken = b64url(randomBytes(24))
    validRefresh.set(refreshToken, id)
    return { accessToken, refreshToken, user: { id, email } }
  }

  // Bearer -> the user it authenticates, or null (expired/unknown = 401).
  function userFromBearer(auth) {
    if (!auth) return null
    const m = /^Bearer\s+(.+)$/i.exec(auth)
    if (!m) return null
    const claims = decodeJwt(m[1])
    if (!claims?.sub || !claims.exp) return null
    if (claims.exp <= Math.floor(Date.now() / 1000)) return null // expired → 401
    return users.get(claims.sub) || null
  }

  // ── PostgREST-ish filtering ────────────────────────────────────────────────
  const OPS = {
    eq: (a, b) => String(a) === b,
    neq: (a, b) => String(a) !== b,
    gt: (a, b) => a > castNum(b, a),
    gte: (a, b) => a >= castNum(b, a),
    lt: (a, b) => a < castNum(b, a),
    lte: (a, b) => a <= castNum(b, a),
    in: (a, b) => parseInList(b).includes(String(a)),
    is: (a, b) => (b === 'null' ? a == null : String(a) === b),
    like: (a, b) => new RegExp('^' + b.replace(/[.*+?^${}()|[\]\\]/g, '\\$&').replace(/%/g, '.*') + '$').test(String(a)),
  }
  const castNum = (b, a) => (typeof a === 'number' && b !== '' && !Number.isNaN(Number(b)) ? Number(b) : b)
  const parseInList = (v) => v.replace(/^\(/, '').replace(/\)$/, '').split(',').map((s) => s.replace(/^"|"$/g, ''))

  function queryTable(table, searchParams) {
    let rows = (tables[table] || []).slice()
    let order = null
    let limit = null
    for (const [key, raw] of searchParams.entries()) {
      if (key === 'select' || key === 'offset' || key === 'on_conflict') continue
      if (key === 'order') {
        const [col, dir] = raw.split('.')
        order = { col, asc: dir !== 'desc' }
        continue
      }
      if (key === 'limit') {
        limit = parseInt(raw, 10)
        continue
      }
      // column filter: value is "op.operand"
      const dot = raw.indexOf('.')
      if (dot < 0) continue
      const op = raw.slice(0, dot)
      const operand = raw.slice(dot + 1)
      const fn = OPS[op]
      if (!fn) continue
      rows = rows.filter((r) => fn(r[key], operand))
    }
    if (order) {
      rows.sort((a, b) => {
        const av = a[order.col]
        const bv = b[order.col]
        if (av === bv) return 0
        const cmp = av > bv ? 1 : -1
        return order.asc ? cmp : -cmp
      })
    }
    if (limit != null) rows = rows.slice(0, limit)
    return rows
  }

  // ── HTTP ────────────────────────────────────────────────────────────────────
  const server = http.createServer(async (req, res) => {
    const origin = req.headers.origin || '*'
    const cors = {
      'Access-Control-Allow-Origin': origin,
      'Access-Control-Allow-Credentials': 'true',
      'Access-Control-Allow-Methods': 'GET,POST,PATCH,DELETE,OPTIONS',
      'Access-Control-Allow-Headers':
        req.headers['access-control-request-headers'] ||
        'authorization,content-type,x-csrf-token,prefer,accept,accept-profile,content-profile,apikey,x-api-key,x-client-info',
      'Access-Control-Expose-Headers': 'content-range',
      Vary: 'Origin',
    }
    if (req.method === 'OPTIONS') {
      res.writeHead(204, cors)
      res.end()
      return
    }

    const url = new URL(req.url, 'http://localhost')
    const path = url.pathname
    const body = await readBody(req)

    const send = (status, payload, extra = {}) => {
      const json = payload === undefined ? '' : JSON.stringify(payload)
      res.writeHead(status, {
        'Content-Type': 'application/json',
        ...cors,
        ...extra,
      })
      res.end(json)
    }

    // Record every InsForge-facing request (skip the mock's own control plane).
    if (!path.startsWith('/__mock/')) {
      const entry = { ts: Date.now(), method: req.method, path }
      if (path === '/api/auth/refresh') entry.refreshToken = body?.refreshToken || null
      requestLog.push(entry)
    }

    try {
      // ── Control plane ────────────────────────────────────────────────────────
      if (path === '/__mock/reset' && req.method === 'POST') {
        Object.assign(tables, freshTables())
        validRefresh.clear()
        requestLog = []
        return send(200, { ok: true })
      }
      if (path === '/__mock/session' && req.method === 'POST') {
        const email = body?.email || 'smoke.user@filmo.test'
        const ttlSec = Number.isFinite(body?.ttlSec) ? body.ttlSec : 900
        return send(200, registerSession(email, ttlSec))
      }
      if (path === '/__mock/seed' && req.method === 'POST') {
        // Append fixture rows to a table: { table, rows: [...] }
        const t = body?.table
        if (!t || !tables[t]) return send(400, { error: 'unknown table' })
        for (const row of body.rows || []) {
          tables[t].push({ id: randomUUID(), created_at: new Date().toISOString(), ...row })
        }
        return send(200, { ok: true, count: (body.rows || []).length })
      }
      if (path === '/__mock/requests' && req.method === 'GET') {
        const mFilter = url.searchParams.get('method')
        const pFilter = url.searchParams.get('path')
        const matches = requestLog.filter(
          (e) => (!mFilter || e.method === mFilter) && (!pFilter || e.path === pFilter),
        )
        return send(200, { count: matches.length, requests: matches })
      }
      if (path === '/__mock/writes' && req.method === 'GET') {
        const t = url.searchParams.get('table')
        return send(200, { rows: t ? tables[t] || [] : tables })
      }
      if (path === '/__mock/state' && req.method === 'GET') {
        return send(200, {
          users: [...users.values()],
          validRefreshCount: validRefresh.size,
          tables: Object.fromEntries(Object.entries(tables).map(([k, v]) => [k, v.length])),
          requestCount: requestLog.length,
        })
      }

      // ── Auth ──────────────────────────────────────────────────────────────────
      if (path === '/api/auth/public-config') return send(200, { requireEmailVerification: false })

      if (path === '/api/auth/oauth/google' || path.startsWith('/api/auth/oauth/custom/')) {
        // signInWithOAuth GET — returns the URL the browser would be sent to.
        return send(200, { authUrl: `${origin}/?insforge_code=TEST` })
      }

      if (path === '/api/auth/oauth/exchange' && req.method === 'POST') {
        // PKCE exchange: the mock does not check the verifier — any code returns a
        // session for the deterministic smoke user (mirrors a successful Google return).
        if (!body?.code) return send(400, apiErr(400, 'missing code'))
        return send(200, registerSession(SMOKE_EMAIL, 900))
      }

      if (path === '/api/auth/sessions' && req.method === 'POST') {
        // Password sign-in. Any credentials succeed as the email supplied.
        const email = body?.email || SMOKE_EMAIL
        return send(200, registerSession(email, 900))
      }
      if (path === '/api/auth/users' && req.method === 'POST') {
        const email = body?.email || SMOKE_EMAIL
        return send(200, registerSession(email, 900))
      }

      if (path === '/api/auth/sessions/current' && req.method === 'GET') {
        const user = userFromBearer(req.headers.authorization)
        if (!user) return send(401, apiErr(401, 'invalid or expired token'))
        return send(200, { user })
      }

      if (path === '/api/auth/refresh' && req.method === 'POST') {
        const rt = body?.refreshToken
        // Body-mode refresh WITH ROTATION. A valid token is consumed and replaced;
        // presenting an already-rotated (or unknown) token is a real 401. This is
        // what makes the single-flight belt meaningful: two racing refreshes with
        // the same token → the second one 401s.
        if (!rt || !validRefresh.has(rt)) return send(401, apiErr(401, 'invalid refresh token'))
        const userId = validRefresh.get(rt)
        validRefresh.delete(rt)
        const user = users.get(userId)
        const accessToken = mintJwt({ sub: userId, email: user.email, ttlSec: 900 })
        const newRefresh = b64url(randomBytes(24))
        validRefresh.set(newRefresh, userId)
        return send(200, { accessToken, refreshToken: newRefresh, user })
      }

      if (path === '/api/auth/logout' && req.method === 'POST') return send(200, {})

      // ── Data (PostgREST records + rpc) ─────────────────────────────────────────
      const rec = /^\/api\/database\/records\/([a-zA-Z0-9_]+)$/.exec(path)
      if (rec) {
        const table = rec[1]
        if (!(table in tables)) tables[table] = []
        if (req.method === 'GET') {
          return send(200, queryTable(table, url.searchParams))
        }
        if (req.method === 'POST') {
          const incoming = Array.isArray(body) ? body : [body]
          const inserted = incoming.map((row) => ({
            id: randomUUID(),
            created_at: new Date().toISOString(),
            ...row,
          }))
          tables[table].push(...inserted)
          // Always answer with the representation array; callers that didn't ask
          // for it ignore the body, and createBuild's runs.insert().select() needs it.
          return send(201, inserted, { 'Content-Range': `0-${inserted.length - 1}/*` })
        }
        if (req.method === 'PATCH') {
          const updates = body || {}
          const hits = queryTable(table, url.searchParams)
          for (const r of hits) Object.assign(r, updates)
          return send(200, hits)
        }
        if (req.method === 'DELETE') {
          const hits = new Set(queryTable(table, url.searchParams))
          tables[table] = tables[table].filter((r) => !hits.has(r))
          return send(200, [...hits])
        }
      }
      const rpc = /^\/api\/database\/rpc\/([a-zA-Z0-9_]+)$/.exec(path)
      if (rpc) return send(200, [])

      // Anything else the app touches that we didn't model: answer empty-OK rather
      // than erroring, so an unmodelled read never masquerades as an auth failure.
      return send(200, [])
    } catch (err) {
      return send(500, apiErr(500, `mock error: ${err?.message || err}`))
    }
  })

  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve))
  const port = server.address().port
  const baseUrl = `http://127.0.0.1:${port}`
  return {
    url: baseUrl,
    port,
    close: () => new Promise((r) => server.close(r)),
  }
}

// The InsForgeError shape the SDK parses (parseResponse reads `.error` +
// `.statusCode`); anything without an `error` key becomes a generic REQUEST_FAILED.
function apiErr(status, message) {
  return { error: message, message, statusCode: status }
}

export const SMOKE_EMAIL = 'smoke.user@filmo.test'

function readBody(req) {
  return new Promise((resolve) => {
    if (req.method === 'GET' || req.method === 'HEAD' || req.method === 'OPTIONS') return resolve(null)
    const chunks = []
    req.on('data', (c) => chunks.push(c))
    req.on('end', () => {
      const raw = Buffer.concat(chunks).toString('utf8')
      if (!raw) return resolve(null)
      try {
        resolve(JSON.parse(raw))
      } catch {
        resolve(raw)
      }
    })
    req.on('error', () => resolve(null))
  })
}
