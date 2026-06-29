// Live demand signal for the producing-phase copy.
//
// The run page shows a "demand is high, your video is in the queue" note while a
// build runs. That line must only appear when demand is GENUINELY high — otherwise
// it's misleading. This route returns a truthful, server-computed signal.
//
// Why server-side: the client InsForge SDK is RLS-scoped to the caller's own rows,
// so it cannot see OTHER users' jobs — it would always count ~1 (just this user's
// own build) and never detect a real backlog. The admin client (service role,
// INSFORGE_API_KEY) bypasses RLS to count globally-active jobs.
//
// "Active" = jobs the worker still owes work on RIGHT NOW:
//   • status = 'queued'  → waiting for a worker (genuine backlog) — always counts.
//   • status = 'claimed' AND created recently → a worker is actively building it.
// We DELIBERATELY ignore STALE claimed jobs (a crashed/abandoned claim that never
// reached done/failed sits 'claimed' forever — counting it would report "high
// demand" permanently, the exact falsehood we're removing). A real build finishes
// in ~6–9 min, so a claim older than the freshness window is treated as dead.
import { NextResponse } from 'next/server'
import { adminClient } from '../../../lib/insforge'

export const dynamic = 'force-dynamic'

// A claimed job older than this is almost certainly a dead claim (real builds take
// ~6–9 min). Generous enough to never drop a legitimately-slow live build.
const CLAIM_FRESH_MS = 30 * 60 * 1000
// ≥ this many genuinely-active jobs = "demand is high".
const HIGH_DEMAND_THRESHOLD = 2

export async function GET() {
  try {
    const db = adminClient()
    const { data, error } = await db.database
      .from('jobs')
      .select('id, status, created_at')
      .in('status', ['queued', 'claimed'])

    if (error || !Array.isArray(data)) {
      // Fail SAFE: if we can't compute the signal, report normal demand so we never
      // show the "demand is high" claim without evidence for it.
      return NextResponse.json(
        { active: 0, highDemand: false },
        { headers: { 'Cache-Control': 'no-store' } },
      )
    }

    const now = Date.now()
    const active = (data as { status?: string; created_at?: string }[]).filter((j) => {
      if (j.status === 'queued') return true
      if (j.status !== 'claimed') return false
      const t = j.created_at ? new Date(j.created_at).getTime() : NaN
      return Number.isFinite(t) && now - t <= CLAIM_FRESH_MS
    }).length

    return NextResponse.json(
      { active, highDemand: active >= HIGH_DEMAND_THRESHOLD },
      { headers: { 'Cache-Control': 'no-store' } },
    )
  } catch {
    return NextResponse.json(
      { active: 0, highDemand: false },
      { headers: { 'Cache-Control': 'no-store' } },
    )
  }
}
