import { NextRequest, NextResponse } from 'next/server'

// ─────────────────── Canonical-domain redirect (filmo.dev) ───────────────────
// WHY (2026-07-02): sessions live in ORIGIN-SCOPED localStorage. The app is reachable on
// two origins (filmo.dev + filmostudio.vercel.app), so a user who signs in on one and gets
// navigated to the other (the Stripe success_url did exactly this) lands on an origin with
// EMPTY storage → hard signed-out, votes lost mid-payment. One canonical origin makes that
// class of bug impossible: anyone arriving on the legacy vercel.app host is 308'd to
// filmo.dev with path + query preserved (run links, ?paid=1 returns, everything survives).
//
// Scope guard: ONLY the exact legacy public host redirects. Deployment-preview hosts
// (filmostudio-<hash>-….vercel.app), localhost, and filmo.dev itself pass through untouched
// — previews must stay directly viewable and this must never loop.
const LEGACY_HOSTS = new Set(['filmostudio.vercel.app', 'www.filmo.dev'])
const CANONICAL_ORIGIN = 'https://filmo.dev'

export function middleware(req: NextRequest) {
  const host = req.headers.get('host')?.toLowerCase() ?? ''
  if (LEGACY_HOSTS.has(host)) {
    const url = new URL(req.nextUrl.pathname + req.nextUrl.search, CANONICAL_ORIGIN)
    return NextResponse.redirect(url, 308)
  }
  return NextResponse.next()
}

// Skip static assets — only page/API navigations need canonicalizing.
export const config = {
  matcher: ['/((?!_next/static|_next/image|favicon.ico).*)'],
}
