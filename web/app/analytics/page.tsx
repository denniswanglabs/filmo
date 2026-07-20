'use client'
// ═══════════════════ /analytics — THE BUSINESS, ON THE STUDIO GROUND ═════════
//
// This page used to wear the old white chrome: `TopBar` from components/Brand,
// reading "Analytics · Dennis · Sign out" over a white page, with amber buttons
// and a "← Back to Filmo" link doing the work a navigation should do. It now
// wears the same shell as the Overview — studio ground, white cards, #E6E6E3
// hairlines, the rail — because a signed-in surface that looks like a different
// product depending on which link you pressed is the bug, not the chrome.
//
// WHAT DID NOT CHANGE, DELIBERATELY. Every number, and the model behind it. The
// COGS constants, `voCharsFor` / `tokenUsdFor` / `cogsCentsFor`, the `metrics`
// memo and the branch order below are the code that was here before, moved
// rather than rewritten. This was a rebuild of the chrome and the layout; if a
// figure reads differently it is a bug in this rewrite, not a new opinion about
// the business.
//
// FOUR THINGS ABOUT IT ARE LOAD-BEARING.
//
// 1. THE OWNER GATE IS UNTOUCHED, AND IT IS STILL NOT THE BOUNDARY. `OWNER_EMAIL`
//    below decides what to RENDER. The boundary is server-side in `readAnalytics`
//    (verifyUser → owner check → admin client), so a tampered client gets
//    `authorized:false` and zero rows. Both gates are kept: the client one so a
//    non-owner never even issues the read, the server one because it is the only
//    one that counts.
//
// 2. THE RAIL LIGHTS NOTHING HERE. Analytics is owner-only and therefore not one
//    of the rail's entries — the rail is EVERY user's navigation (see the TWIN
//    note at the top of OverviewRail). `current="none"` is passed explicitly:
//    omitting it defaults to 'overview', and the rail would then claim you are
//    standing somewhere you are not.
//
// 3. IT IS A FIXED SHELL, PORTALLED. `app/template.tsx` wraps every route in a
//    framer-motion div, and a position:fixed child of a TRANSFORMED ancestor is
//    positioned against that ancestor rather than the viewport. Rendering into
//    document.body is what makes `inset:0` mean the screen — same reason, same
//    shape as overview/page.tsx and LibraryShell. The body then never scrolls,
//    at 1440 or at 390; the stage does, and the one genuinely wide thing on the
//    page (the per-video table) scrolls inside its own box.
//
// 4. WHOEVER RENDERS THE RAIL OWNS THE FEEDBACK SHEET. The rail's account circle
//    is the way IN to feedback; the sheet has to belong to a surface that
//    outlives the click, and on this route that surface is this file.
import { useEffect, useState, useMemo } from 'react'
import { createPortal } from 'react-dom'
import Link from 'next/link'
import { useAuth } from '../../lib/auth'
import { StatusChip } from '../components/Brand'
import FilmoLoader, { GROUND_STUDIO } from '../components/FilmoLoader'
import OverviewRail from '../components/overview/OverviewRail'
import FeedbackModal from '../runs/[id]/FeedbackModal'
import { readAnalytics, type AnalyticsRunRow } from '../actions'
import { formatCents, formatCentsPrecise } from '../../lib/types'

// Owner-only business analytics. The page renders nothing sensitive on its own — the
// real gate is server-side in readAnalytics (admin client bypasses RLS, so the owner
// check happens there after verifying the token). This client gate is the UX skin;
// even a tampered client gets `authorized: false` + zero rows from the server.
const OWNER_EMAIL = 'denniswanglabs@gmail.com'

// ── THE RAIL LIGHTS NOTHING ON THIS ROUTE ───────────────────────────────────
// `current` selects which rail entry is lit. Analytics is not an entry and must
// never become one, so none of them may light. The rail lights an entry by
// `current === entry`, so a value outside the union lights none and sets no
// aria-current — the honest answer to "where am I" on a route the rail does not
// name. Leaving the prop OFF would default it to 'overview', and the rail would
// then claim you were standing somewhere you are not, which is the exact failure
// the `current` prop was added to fix.
//
// `RailEntry` now carries a real 'none' member, so the page declares what it
// means instead of casting around a type that could not say it.

// Delivered-ish = the run shipped a video (mirrors lib/types DELIVERED_STATUSES).
const DELIVERED = new Set(['delivered', 'completed_with_warnings'])

// ── COGS model (tunable rates) ───────────────────────────────────────────────
// We COMPUTE a real per-video COGS here instead of trusting runs.cogs_cents — every run
// today records cogs_cents = NULL. COGS has TWO real lines, both per-run-aware:
//   (1) ElevenLabs voiceover — billed per character; the dominant cost.
//   (2) Nemotron tokens — REAL OpenRouter spend, NOT zero. The planner (and on the
//       Hermes path, the Conversion Read too) run on Nemotron via OpenRouter. Pricier
//       550B (`ultra-paid`) runs cost more than free 120B (`super-free`) runs, so the
//       token line is keyed on each run's brain + its actual recorded usage.cost.
//
// ── (1) ElevenLabs VO ──
// ElevenLabs effective price (≈ the plan's $/char). MAIN cost driver.
const ELEVENLABS_USD_PER_1K_CHARS = 0.22
// VO characters ≈ video duration × speaking rate. ~14 chars/sec is a natural pace.
const VO_CHARS_PER_SECOND = 14
// Fallback VO length when a run didn't store its duration (≈ a typical ~30s VO).
const DEFAULT_VO_CHARS = 450

// ── (2) Nemotron token COGS ──
// PREFERRED: the ACTUAL OpenRouter spend the pipeline stamps at
// runs.selection.planner_usage.cost (e.g. $0.0047 for a 550B plan call). The plan call's
// cost is recorded; the Conversion Read + design_brief calls (also Nemotron) are NOT
// persisted, so we gross the recorded plan cost up by this factor to cover them. Mirrors
// the worker's own model (agent-host/vm/mcp_toolserver.py `_real_token_cogs_cents`: real
// plan usage.cost + a ~0.6× Read/brief estimate → ×1.6 total).
const READ_BRIEF_GROSS_UP = 1.6

// FALLBACK (run on a paid brain but usage.cost not recorded): estimate from the brain's
// OpenRouter list rate × a conservative tokens/video estimate. Rates are USD per 1M tokens,
// verified against OpenRouter (2026-06-29) and matching brain.py:
//   ultra-paid  = nvidia/nemotron-3-ultra-550b-a55b : $0.50 in / $2.20 out per 1M
//   super-paid  = nvidia/nemotron-3-super-120b-a12b : $0.09 in / $0.45 out per 1M (≈OR $0.085/$0.40)
//   super-free  = nvidia/nemotron-3-super-120b-a12b:free : $0 / $0 (free tier — genuinely ~$0)
const BRAIN_RATE_USD_PER_1M: Record<string, { input: number; output: number }> = {
  'ultra-paid': { input: 0.5, output: 2.2 },
  'super-paid': { input: 0.09, output: 0.45 },
  'super-free': { input: 0, output: 0 },
}
// Conservative tokens/video for the estimate fallback (≈ the actuals observed: ~6.3k prompt
// + ~0.75k completion per plan call). Grossed up the same ×1.6 for the Read/brief calls.
const EST_PROMPT_TOKENS_PER_VIDEO = 6300
const EST_COMPLETION_TOKENS_PER_VIDEO = 750

// Estimated VO character count for a run — exact-ish from stored duration, else default.
function voCharsFor(row: AnalyticsRunRow): number {
  if (row.vo_seconds && row.vo_seconds > 0) return Math.round(row.vo_seconds * VO_CHARS_PER_SECOND)
  return DEFAULT_VO_CHARS
}

// Per-run Nemotron token COGS in USD. ACTUAL recorded spend when present (×gross-up for the
// un-persisted Read/brief calls); else a labeled estimate from the run's brain rate.
// super-free (120B free tier) → $0, truthfully.
function tokenUsdFor(row: AnalyticsRunRow): number {
  if (row.planner_cost_usd != null && row.planner_cost_usd >= 0) {
    return row.planner_cost_usd * READ_BRIEF_GROSS_UP
  }
  const rate = BRAIN_RATE_USD_PER_1M[(row.brain || 'super-free').toLowerCase()] ?? {
    input: 0,
    output: 0,
  }
  const est =
    (EST_PROMPT_TOKENS_PER_VIDEO / 1_000_000) * rate.input +
    (EST_COMPLETION_TOKENS_PER_VIDEO / 1_000_000) * rate.output
  return est * READ_BRIEF_GROSS_UP
}

// Real per-video COGS in CENTS: ElevenLabs (chars × rate) + Nemotron token cost. Only
// delivered videos incur production cost — a queued/failed run that never rendered cost ~nothing.
function cogsCentsFor(row: AnalyticsRunRow): number {
  if (!DELIVERED.has(row.status)) return 0
  const elevenUsd = (voCharsFor(row) / 1000) * ELEVENLABS_USD_PER_1K_CHARS
  return (elevenUsd + tokenUsdFor(row)) * 100
}

type Loaded = { authorized: boolean; rows: AnalyticsRunRow[] }

export default function AnalyticsPage() {
  const { user, loading, getToken } = useAuth()
  const [mounted, setMounted] = useState(false)
  const [data, setData] = useState<Loaded | null>(null)
  const [fetched, setFetched] = useState(false)
  const [fbOpen, setFbOpen] = useState(false)

  useEffect(() => setMounted(true), [])

  // Client-side owner check — purely for the UX (deciding whether to even call the
  // server / what to render). NOT a security boundary.
  const clientIsOwner =
    typeof user?.email === 'string' && user.email.toLowerCase() === OWNER_EMAIL

  useEffect(() => {
    if (loading) return
    // No user, or not the owner client-side → don't even hit the server; show denied.
    if (!user || !clientIsOwner) {
      setFetched(true)
      return
    }
    let cancelled = false
    ;(async () => {
      const token = await getToken()
      const res = await readAnalytics(token)
      if (!cancelled) {
        setData(res)
        setFetched(true)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [loading, user, clientIsOwner, getToken])

  // ── Derived metrics (all computed from the server-returned rows) ──
  const metrics = useMemo(() => {
    const rows = data?.rows ?? []
    const revenue = rows.reduce((a, r) => a + (r.price_cents || 0), 0)
    // Real, recomputed COGS (ElevenLabs VO + token), summed over delivered videos —
    // NOT the stored r.cogs_cents (null/0 on every run today).
    const cogs = rows.reduce((a, r) => a + cogsCentsFor(r), 0)
    const profit = revenue - cogs

    const delivered = rows.filter((r) => DELIVERED.has(r.status))
    const deliveredCount = delivered.length

    // Avg price across PRICED runs only (price_cents != null) so unpriced/queued runs
    // don't drag the average to zero.
    const priced = rows.filter((r) => r.price_cents != null)
    const avgPrice = priced.length
      ? Math.round(priced.reduce((a, r) => a + (r.price_cents || 0), 0) / priced.length)
      : null

    // Avg margin = profit / revenue across the whole book (a single blended margin is
    // more honest than averaging per-run margins, esp. with COGS mostly 0 today).
    const avgMargin = revenue > 0 ? profit / revenue : null

    // Counts by status.
    const byStatus: Record<string, number> = {}
    for (const r of rows) byStatus[r.status] = (byStatus[r.status] || 0) + 1

    // Counts by producer (props.producer) — only where tagged. Skip the whole block if
    // nothing is tagged (most runs predate the producer tag).
    const byProducer: Record<string, number> = {}
    let producerTagged = 0
    for (const r of rows) {
      if (r.producer) {
        byProducer[r.producer] = (byProducer[r.producer] || 0) + 1
        producerTagged++
      }
    }

    // Cumulative revenue per day (for the chart). Group priced runs by YYYY-MM-DD.
    const perDay = new Map<string, number>()
    for (const r of rows) {
      if (!r.price_cents) continue
      const day = r.created_at.slice(0, 10)
      perDay.set(day, (perDay.get(day) || 0) + r.price_cents)
    }
    const days = [...perDay.keys()].sort()
    let running = 0
    const series = days.map((d) => {
      running += perDay.get(d) || 0
      return { day: d, dayRevenue: perDay.get(d) || 0, cumulative: running }
    })

    return {
      revenue,
      cogs,
      profit,
      deliveredCount,
      total: rows.length,
      avgPrice,
      avgMargin,
      byStatus,
      byProducer,
      producerTagged,
      series,
    }
  }, [data])

  // The portal has nowhere to go until there is a document. `app/analytics/loading.tsx`
  // covers the gap before this paints.
  if (!mounted) return null

  // ── WHAT GOES IN THE STAGE ────────────────────────────────────────────────
  // The branch ORDER here is the one this page has always used, kept exactly:
  // resolving → the owner whose session died → everyone else who may not look →
  // the dashboard. The shell (rail, ground, feedback sheet) sits OUTSIDE the
  // branch, so a denied visitor still gets the product's navigation rather than
  // a bare page — the same call the Overview makes for its own sign-in gate.
  let body: React.ReactNode

  if (loading || !fetched) {
    // Never a bare "Loading…". `fit="block"` fills the stage rather than the
    // viewport, because the rail beside it is already on screen and correct.
    body = <FilmoLoader ground={GROUND_STUDIO} fit="block" label="Loading analytics" />
  } else if (clientIsOwner && data && !data.authorized) {
    // The OWNER with an expired session lands here: the client recognizes the owner
    // email (optimistic restore) but the server returned authorized:false because
    // verifyUser couldn't verify the stale token. Show a re-auth prompt — not a flat
    // "not authorized" — so the operator can actually recover instead of being confused.
    body = (
      <div className="an-gate">
        <b>Your session expired</b>
        <span>Sign in again to view your analytics.</span>
        <Link className="an-gatebtn" href="/login">Sign in again</Link>
      </div>
    )
  } else if (!user || !clientIsOwner || (data && !data.authorized)) {
    // Not authorized: either no session, not the owner client-side, or the server
    // refused. A clean, data-free denial — no numbers ever rendered.
    body = (
      <div className="an-gate">
        <span className="an-gateicon" aria-hidden>
          <svg viewBox="0 0 24 24" fill="none">
            <rect x="4" y="10" width="16" height="10" rx="2" stroke="currentColor" strokeWidth="2" />
            <path d="M8 10V7a4 4 0 0 1 8 0v3" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
          </svg>
        </span>
        <b>Not authorized</b>
        <span>This dashboard is restricted to the Filmo operator account.</span>
        {/* `/` and not `/overview`: this branch also catches a SIGNED-OUT
            visitor, and the Overview would hand them a second gate. The home
            route already sends a signed-in reader on to their overview, so one
            destination is correct for everybody who can land here. */}
        <Link className="an-gatebtn" href="/">Back to Filmo</Link>
      </div>
    )
  } else {
    const m = metrics
    body = (
      <>
        {/* The four headline figures. One hairline grid rather than four floating
            cards — the same shape the Overview's stat strip uses, for the same
            reason: these are one readout, not four unrelated ones. */}
        <div className="an-strip">
          <Figure label="Total revenue" value={formatCents(m.revenue)} />
          <Figure label="Total COGS" value={formatCentsPrecise(m.cogs)} />
          <Figure label="Total profit" value={formatCentsPrecise(m.profit)} negative={m.profit < 0} />
          <Figure
            label="Videos delivered"
            value={`${m.deliveredCount}`}
            sub={`of ${m.total} runs`}
          />
        </div>

        <p className="an-note">
          COGS = real per-video voice (ElevenLabs) + Nemotron token cost — actual OpenRouter
          spend per run (550B runs cost more than free 120B); fixed infra not included.
        </p>

        {/* Secondary metrics */}
        <div className="an-sub">
          <Small label="Avg price" value={formatCents(m.avgPrice)} />
          <Small
            label="Avg margin"
            value={m.avgMargin == null ? '--' : `${Math.round(m.avgMargin * 100)}%`}
          />
          <Small label="Total runs" value={`${m.total}`} />
          <Small
            label="Success rate"
            value={m.total ? `${Math.round((m.deliveredCount / m.total) * 100)}%` : '--'}
          />
        </div>

        {/* Revenue over time — lightweight inline-SVG cumulative chart */}
        <section className="an-section">
          <h2 className="an-h2">Cumulative revenue</h2>
          <RevenueChart series={m.series} />
        </section>

        {/* Status + producer split */}
        <div className="an-split">
          <Breakdown title="Runs by status">
            {Object.entries(m.byStatus)
              .sort((a, b) => b[1] - a[1])
              .map(([status, count]) => (
                <div className="an-row" key={status}>
                  <StatusChip status={status} />
                  <span className="an-rowval">{count}</span>
                </div>
              ))}
          </Breakdown>

          {m.producerTagged > 0 ? (
            <Breakdown title="Producer split" note={`${m.producerTagged} of ${m.total} runs tagged`}>
              {Object.entries(m.byProducer)
                .sort((a, b) => b[1] - a[1])
                .map(([producer, count]) => (
                  <div className="an-row" key={producer}>
                    <span className="an-mono">{producer}</span>
                    <span className="an-rowval">{count}</span>
                  </div>
                ))}
            </Breakdown>
          ) : (
            <Breakdown title="Producer split">
              <p className="an-quiet">No runs tagged with a producer yet.</p>
            </Breakdown>
          )}
        </div>

        {/* Per-video table. The ONE genuinely wide thing on the page, so it
            scrolls inside its own box — the body never scrolls sideways. */}
        <section className="an-section">
          <h2 className="an-h2">Per-video</h2>
          <div className="an-tablewrap">
            <table className="an-table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Brand</th>
                  <th>Status</th>
                  <th className="r">Price</th>
                  <th className="r">COGS</th>
                  <th className="r">Profit</th>
                  <th>Video</th>
                </tr>
              </thead>
              <tbody>
                {(data?.rows ?? []).map((r) => {
                  const rowCogs = cogsCentsFor(r)
                  const profit = (r.price_cents || 0) - rowCogs
                  return (
                    <tr key={r.id}>
                      <td className="an-dim nowrap">
                        {new Date(r.created_at).toLocaleDateString([], {
                          month: 'short',
                          day: 'numeric',
                        })}
                      </td>
                      <td className="an-brand">
                        <Link href={`/runs/${r.id}`}>{r.brand || r.company_url}</Link>
                      </td>
                      <td>
                        <StatusChip status={r.status} />
                      </td>
                      <td className="r num nowrap">{formatCents(r.price_cents)}</td>
                      <td className="r num nowrap an-dim">
                        {DELIVERED.has(r.status) ? formatCentsPrecise(rowCogs) : '--'}
                      </td>
                      <td
                        className={
                          'r num nowrap an-profit' +
                          (r.price_cents != null && profit < 0 ? ' bad' : '')
                        }
                      >
                        {r.price_cents == null ? '--' : formatCentsPrecise(profit)}
                      </td>
                      <td>
                        {r.final_url ? (
                          <a className="an-view" href={r.final_url} target="_blank" rel="noreferrer">
                            View
                            <svg viewBox="0 0 24 24" aria-hidden>
                              <path d="M14 5h5v5M19 5l-8 8" stroke="currentColor" strokeWidth="2"
                                fill="none" strokeLinecap="round" strokeLinejoin="round" />
                              <path d="M18 14.5V18a1.5 1.5 0 0 1-1.5 1.5h-10A1.5 1.5 0 0 1 5 18V8a1.5 1.5 0 0 1 1.5-1.5H10"
                                stroke="currentColor" strokeWidth="2" fill="none"
                                strokeLinecap="round" strokeLinejoin="round" />
                            </svg>
                          </a>
                        ) : (
                          <span className="an-none">—</span>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </section>

        <p className="an-method">
          Revenue reflects Stripe <b>test-mode</b> checkouts. COGS per delivered video =
          ElevenLabs voiceover ({ELEVENLABS_USD_PER_1K_CHARS.toFixed(2)} $/1k chars, the main
          driver) + <b>Nemotron token cost</b>. The token line is the <b>actual</b> OpenRouter
          spend recorded per run (planner <code>usage.cost</code>, grossed up{' '}
          {READ_BRIEF_GROSS_UP}× for the un-logged Conversion Read + design-brief calls); when a
          run didn&rsquo;t record it, it&rsquo;s estimated from the run&rsquo;s brain rate (550B{' '}
          <code>ultra-paid</code> ≈ $0.0075/video; free 120B <code>super-free</code> ≈ $0). VO
          length is exact when the render duration was stored, else inferred at ~
          {VO_CHARS_PER_SECOND} chars/sec. Profit = price − COGS.
        </p>
      </>
    )
  }

  return createPortal(
    <div className="an-root">
      <OverviewRail
        current="none"
        getToken={getToken}
        onFeedback={() => setFbOpen(true)}
      />

      <main className="an-stage">
        <div className="an-inner">
          <header className="an-head">
            <div className="an-headrow">
              <h1 className="an-title">Analytics</h1>
              <span className="an-testmode">
                <i aria-hidden />
                Stripe test-mode
              </span>
            </div>
            <p className="an-lede">
              Every run this account has made, priced and costed. The revenue is what Stripe
              actually took; the cost of each video is recomputed here from what that run
              really spent, never read off a stored total.
            </p>
          </header>
          {body}
        </div>
      </main>

      <FeedbackModal
        open={fbOpen}
        onClose={() => setFbOpen(false)}
        getToken={getToken}
        context="/analytics"
      />

      <style>{`
        .an-root { position:fixed; inset:0; display:flex; background:#F1F1EF;
          color:#1B1B1A; font:14px/1.5 Inter,-apple-system,sans-serif; z-index:50; }
        /* The stage scrolls, the shell does not — so the BODY never scrolls in
           either direction, at 1440 or at 390. */
        .an-stage { flex:1 1 0; min-width:0; min-height:0; overflow-y:auto;
          overflow-x:hidden; }
        .an-inner { max-width:1120px; margin:0 auto; padding:38px 32px 56px; }

        .an-head { margin-bottom:26px; }
        .an-headrow { display:flex; align-items:center; gap:14px; flex-wrap:wrap; }
        .an-title { margin:0; font-size:32px; font-weight:600;
          letter-spacing:-.025em; line-height:1.15; color:#1B1B1A; }
        .an-lede { margin:9px 0 0; max-width:62ch; font-size:14.5px;
          line-height:1.55; color:#8A8A86; }
        /* Test-mode is a fact about every number below it, so it sits beside the
           title rather than in a footnote nobody scrolls to. */
        .an-testmode { display:inline-flex; align-items:center; gap:6px;
          background:#EAF1FF; border:1px solid #C9D9F8; border-radius:99px;
          padding:4px 11px; font-size:12px; font-weight:600; color:#1D4ED8; }
        .an-testmode i { width:6px; height:6px; border-radius:50%;
          background:#3B82F6; }

        /* ── THE HEADLINE FIGURES ────────────────────────────────────────────
           One hairline grid, the Overview's stat-strip shape: 1px gaps over a
           #E6E6E3 field, so the separators ARE the background and no cell owns
           a border that can disagree with its neighbour's. */
        .an-strip { display:grid; grid-template-columns:repeat(4, minmax(0, 1fr));
          gap:1px; background:#E6E6E3; border:1px solid #E6E6E3;
          border-radius:14px; overflow:hidden; }
        .an-cell { background:#fff; padding:16px 18px; min-width:0; }
        .an-cell-label { font-size:12px; font-weight:600; letter-spacing:.06em;
          text-transform:uppercase; color:#8A8A86; }
        .an-cell-value { margin-top:6px; font-size:26px; font-weight:650;
          letter-spacing:-.02em; line-height:1.1; color:#1B1B1A;
          font-variant-numeric:tabular-nums; }
        /* Money that has gone the wrong way is the one figure allowed a colour.
           #DC2626 is the app's existing "bad" ink (SuggestionCards .ovsug-note). */
        .an-cell-value.bad { color:#DC2626; }
        .an-cell-sub { margin-top:2px; font-size:12.5px; color:#8A8A86; }

        .an-note { margin:10px 0 0; font-size:12px; line-height:1.55;
          color:#B6B6B2; max-width:78ch; }

        .an-sub { margin-top:14px; display:grid;
          grid-template-columns:repeat(4, minmax(0, 1fr)); gap:12px; }
        .an-small { background:#fff; border:1px solid #E6E6E3; border-radius:12px;
          padding:12px 14px; min-width:0; }
        .an-small-label { font-size:11.5px; font-weight:600; letter-spacing:.06em;
          text-transform:uppercase; color:#8A8A86; }
        .an-small-value { margin-top:4px; font-size:18px; font-weight:650;
          letter-spacing:-.015em; color:#1B1B1A;
          font-variant-numeric:tabular-nums; }

        .an-section { margin-top:32px; }
        .an-h2 { margin:0 0 12px; font-size:12px; font-weight:600;
          letter-spacing:.08em; text-transform:uppercase; color:#8A8A86; }

        /* ── THE CHART ───────────────────────────────────────────────────────── */
        .an-chart { background:#fff; border:1px solid #E6E6E3; border-radius:14px;
          padding:16px; }
        .an-charthead { display:flex; align-items:baseline;
          justify-content:space-between; gap:12px; margin-bottom:6px;
          flex-wrap:wrap; }
        .an-charttotal { font-size:26px; font-weight:650; letter-spacing:-.02em;
          color:#1B1B1A; font-variant-numeric:tabular-nums; }
        .an-chartrange { font-size:12.5px; color:#8A8A86;
          font-variant-numeric:tabular-nums; }
        .an-chart svg { display:block; width:100%; height:176px; }
        .an-chartempty { background:#fff; border:1px dashed #DDDDD9;
          border-radius:14px; padding:34px 22px; text-align:center;
          font-size:13.5px; color:#8A8A86; }

        /* ── BREAKDOWNS ──────────────────────────────────────────────────────── */
        .an-split { margin-top:32px; display:grid;
          grid-template-columns:repeat(2, minmax(0, 1fr)); gap:14px; }
        .an-card { background:#fff; border:1px solid #E6E6E3; border-radius:14px;
          padding:16px 18px; min-width:0; }
        .an-cardhead { display:flex; align-items:baseline;
          justify-content:space-between; gap:10px; margin-bottom:6px; }
        .an-cardhead h3 { margin:0; font-size:14.5px; font-weight:650;
          color:#1B1B1A; }
        .an-cardnote { font-size:12px; color:#8A8A86; }
        .an-row { display:flex; align-items:center; justify-content:space-between;
          gap:12px; padding:7px 0; border-top:1px solid #F1F1EF; }
        .an-row:first-child { border-top:0; }
        .an-rowval { font-size:14px; font-weight:650; color:#1B1B1A;
          font-variant-numeric:tabular-nums; }
        .an-mono { font:12px/1.4 ui-monospace,SFMono-Regular,Menlo,monospace;
          color:#6E6E6A; overflow:hidden; text-overflow:ellipsis;
          white-space:nowrap; min-width:0; }
        .an-quiet { margin:0; padding:7px 0; font-size:13.5px; color:#8A8A86; }

        /* ── THE PER-VIDEO TABLE ─────────────────────────────────────────────
           overflow-x:auto here and a min-width on the table itself: seven
           columns cannot fit a 390px screen, and the choice is between the BOX
           scrolling and the BODY scrolling. It is always the box. */
        .an-tablewrap { background:#fff; border:1px solid #E6E6E3;
          border-radius:14px; overflow-x:auto; }
        .an-table { width:100%; min-width:680px; border-collapse:collapse;
          font-size:13.5px; }
        .an-table th { text-align:left; padding:11px 16px; font-size:11.5px;
          font-weight:600; letter-spacing:.06em; text-transform:uppercase;
          color:#8A8A86; border-bottom:1px solid #E6E6E3; white-space:nowrap; }
        .an-table td { padding:10px 16px; border-bottom:1px solid #F1F1EF;
          vertical-align:middle; }
        .an-table tr:last-child td { border-bottom:0; }
        .an-table .r { text-align:right; }
        .an-table .num { font-variant-numeric:tabular-nums; }
        .an-table .nowrap { white-space:nowrap; }
        .an-dim { color:#8A8A86; }
        .an-brand { max-width:200px; overflow:hidden; text-overflow:ellipsis;
          white-space:nowrap; font-weight:600; }
        .an-brand a { color:#1B1B1A; text-decoration:none; border-radius:4px; }
        .an-brand a:hover { color:#3B82F6; }
        .an-brand a:focus-visible { outline:2px solid #3B82F6; outline-offset:2px;
          color:#3B82F6; }
        .an-profit { font-weight:600; color:#1B1B1A; }
        .an-profit.bad { color:#DC2626; }
        .an-view { display:inline-flex; align-items:center; gap:5px;
          font-size:12.5px; font-weight:600; color:#3B82F6; text-decoration:none;
          border-radius:4px; white-space:nowrap; }
        .an-view svg { width:13px; height:13px; }
        .an-view:hover { text-decoration:underline; }
        .an-view:focus-visible { outline:2px solid #3B82F6; outline-offset:2px; }
        .an-none { color:#B6B6B2; }

        .an-method { margin:18px 0 0; font-size:12px; line-height:1.6;
          color:#B6B6B2; max-width:86ch; }
        .an-method b { font-weight:650; color:#8A8A86; }
        .an-method code { font:11.5px/1 ui-monospace,SFMono-Regular,Menlo,monospace;
          color:#8A8A86; }

        /* ── THE GATES ───────────────────────────────────────────────────────
           Signed out, not the owner, and the owner's dead session all land
           here. None of them is an empty dashboard and none may be dressed as
           one — no figure is ever rendered on these branches. */
        .an-gate { background:#fff; border:1px solid #E6E6E3; border-radius:14px;
          padding:26px; display:flex; flex-direction:column; gap:7px;
          align-items:flex-start; max-width:520px; }
        .an-gate b { font-size:16px; font-weight:650; }
        .an-gate span { font-size:13.5px; line-height:1.55; color:#6E6E6A; }
        .an-gateicon { display:grid; place-items:center; width:44px; height:44px;
          border-radius:50%; background:#F1F1EF; color:#8A8A86; margin-bottom:6px; }
        .an-gateicon svg { width:22px; height:22px; }
        .an-gatebtn { margin-top:10px; display:inline-flex; align-items:center;
          justify-content:center; border:1px solid #1B1B1A; background:#1B1B1A;
          color:#fff; border-radius:99px; padding:9px 20px;
          font:13px/1 Inter,-apple-system,sans-serif; cursor:pointer;
          text-decoration:none; }
        .an-gatebtn:hover { background:#000; border-color:#000; }
        .an-gatebtn:focus-visible { outline:2px solid #3B82F6; outline-offset:3px; }

        /* ── NARROW ──────────────────────────────────────────────────────────
           Four columns of currency cannot be read at 390px, so they stack.
           Nothing is dropped and nothing shrinks below reading size. */
        @media (max-width:980px) {
          .an-strip { grid-template-columns:repeat(2, minmax(0, 1fr)); }
          .an-split { grid-template-columns:minmax(0, 1fr); } }
        @media (max-width:760px) {
          .an-inner { padding:26px 18px 44px; }
          .an-title { font-size:26px; }
          .an-lede { font-size:13.5px; }
          .an-sub { grid-template-columns:repeat(2, minmax(0, 1fr)); } }
        @media (max-width:620px) {
          .an-strip { grid-template-columns:minmax(0, 1fr); }
          .an-cell { padding:13px 16px; }
          .an-cell-value { font-size:22px; }
          .an-charttotal { font-size:22px; } }
      `}</style>
    </div>,
    document.body,
  )
}

// A headline figure. Every value carries the same ink; only a NEGATIVE profit is
// allowed a colour, because it is the one figure whose sign changes what it means.
function Figure({
  label,
  value,
  sub,
  negative,
}: {
  label: string
  value: string
  sub?: string
  negative?: boolean
}) {
  return (
    <div className="an-cell">
      <div className="an-cell-label">{label}</div>
      <div className={'an-cell-value' + (negative ? ' bad' : '')}>{value}</div>
      {sub ? <div className="an-cell-sub">{sub}</div> : null}
    </div>
  )
}

function Small({ label, value }: { label: string; value: string }) {
  return (
    <div className="an-small">
      <div className="an-small-label">{label}</div>
      <div className="an-small-value">{value}</div>
    </div>
  )
}

function Breakdown({
  title,
  note,
  children,
}: {
  title: string
  note?: string
  children: React.ReactNode
}) {
  return (
    <div className="an-card">
      <div className="an-cardhead">
        <h3>{title}</h3>
        {note ? <span className="an-cardnote">{note}</span> : null}
      </div>
      {children}
    </div>
  )
}

// Lightweight cumulative-revenue chart — pure inline SVG, no chart lib. Renders a
// filled area + line over the per-day cumulative series, with the latest total called
// out. Degrades to a friendly empty state with 0/1 priced days.
function RevenueChart({
  series,
}: {
  series: { day: string; dayRevenue: number; cumulative: number }[]
}) {
  if (series.length < 2) {
    return <div className="an-chartempty">Not enough dated revenue yet to chart.</div>
  }

  const W = 720
  const H = 200
  const padX = 8
  const padY = 16
  const max = Math.max(...series.map((s) => s.cumulative), 1)
  const n = series.length
  const x = (i: number) => padX + (i / (n - 1)) * (W - padX * 2)
  const y = (v: number) => H - padY - (v / max) * (H - padY * 2)

  const linePts = series.map((s, i) => `${x(i)},${y(s.cumulative)}`).join(' ')
  const areaPath =
    `M ${x(0)},${H - padY} ` +
    series.map((s, i) => `L ${x(i)},${y(s.cumulative)}`).join(' ') +
    ` L ${x(n - 1)},${H - padY} Z`

  const last = series[n - 1]

  return (
    <div className="an-chart">
      <div className="an-charthead">
        <span className="an-charttotal">{formatCents(last.cumulative)}</span>
        <span className="an-chartrange">
          {series[0].day} → {last.day}
        </span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" aria-hidden>
        <defs>
          <linearGradient id="an-rev-fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#3B82F6" stopOpacity="0.16" />
            <stop offset="100%" stopColor="#3B82F6" stopOpacity="0" />
          </linearGradient>
        </defs>
        <path d={areaPath} fill="url(#an-rev-fill)" />
        <polyline
          points={linePts}
          fill="none"
          stroke="#3B82F6"
          strokeWidth="2.5"
          strokeLinejoin="round"
          strokeLinecap="round"
          vectorEffect="non-scaling-stroke"
        />
        <circle cx={x(n - 1)} cy={y(last.cumulative)} r="3.5" fill="#3B82F6" />
      </svg>
    </div>
  )
}
