'use client'
import { useEffect, useState, useMemo } from 'react'
import Link from 'next/link'
import { useAuth } from '../../lib/auth'
import { TopBar, StatusChip } from '../components/Brand'
import { readAnalytics, type AnalyticsRunRow } from '../actions'
import { formatCents, formatCentsPrecise } from '../../lib/types'

// Owner-only business analytics. The page renders nothing sensitive on its own — the
// real gate is server-side in readAnalytics (admin client bypasses RLS, so the owner
// check happens there after verifying the token). This client gate is the UX skin;
// even a tampered client gets `authorized: false` + zero rows from the server.
const OWNER_EMAIL = 'denniswanglabs@gmail.com'

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
  const [data, setData] = useState<Loaded | null>(null)
  const [fetched, setFetched] = useState(false)

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

  // ── Render states ──
  if (loading || !fetched) {
    return (
      <>
        <TopBar />
        <div className="flex min-h-[60vh] items-center justify-center text-slate-400">
          Loading…
        </div>
      </>
    )
  }

  // Not authorized: either no session, not the owner client-side, or the server
  // refused. A clean, data-free denial — no numbers ever rendered.
  if (!user || !clientIsOwner || (data && !data.authorized)) {
    return (
      <>
        <TopBar />
        <main className="mx-auto flex min-h-[60vh] max-w-md flex-col items-center justify-center px-5 text-center">
          <div className="grid h-12 w-12 place-items-center rounded-full border border-black/10 bg-white text-slate-400">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <rect x="4" y="10" width="16" height="10" rx="2" stroke="currentColor" strokeWidth="1.8" />
              <path d="M8 10V7a4 4 0 0 1 8 0v3" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
            </svg>
          </div>
          <h1 className="mt-5 text-xl font-semibold text-ink">Not authorized</h1>
          <p className="mt-2 text-sm text-slate-500">
            This dashboard is restricted to the Filmo operator account.
          </p>
          <Link
            href="/"
            className="mt-6 inline-flex items-center justify-center rounded-lg bg-amber px-4 py-2 text-sm font-semibold text-white transition hover:opacity-90"
          >
            Back to Filmo
          </Link>
        </main>
      </>
    )
  }

  const m = metrics

  return (
    <>
      <TopBar />
      <main className="mx-auto max-w-5xl px-5 pb-24 pt-8">
        <Link href="/" className="text-sm text-slate-400 transition hover:text-ink">
          ← Back to Filmo
        </Link>

        <div className="mt-5 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight text-ink">Analytics</h1>
            <p className="mt-1 text-slate-500">The whole business, end to end.</p>
          </div>
          <span className="inline-flex items-center gap-1.5 rounded-full border border-amber/30 bg-amber-soft px-2.5 py-1 text-xs font-medium text-amber">
            <span className="h-1.5 w-1.5 rounded-full bg-amber" />
            Stripe test-mode
          </span>
        </div>

        {/* Top cards — revenue / COGS / profit / delivered */}
        <div className="mt-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
          <BigStat label="Total revenue" value={formatCents(m.revenue)} accent="blue" />
          <BigStat label="Total COGS" value={formatCentsPrecise(m.cogs)} />
          <BigStat label="Total profit" value={formatCentsPrecise(m.profit)} accent="green" />
          <BigStat label="Videos delivered" value={`${m.deliveredCount}`} sub={`of ${m.total} runs`} />
        </div>

        <p className="mt-2.5 text-xs leading-relaxed text-slate-400">
          COGS = real per-video voice (ElevenLabs) + Nemotron token cost — actual OpenRouter
          spend per run (550B runs cost more than free 120B); fixed infra not included.
        </p>

        {/* Secondary metrics */}
        <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <SmallStat label="Avg price" value={formatCents(m.avgPrice)} />
          <SmallStat
            label="Avg margin"
            value={m.avgMargin == null ? '--' : `${Math.round(m.avgMargin * 100)}%`}
          />
          <SmallStat label="Total runs" value={`${m.total}`} />
          <SmallStat
            label="Success rate"
            value={m.total ? `${Math.round((m.deliveredCount / m.total) * 100)}%` : '--'}
          />
        </div>

        {/* Revenue over time — lightweight inline-SVG cumulative chart */}
        <section className="mt-8">
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-400">
            Cumulative revenue
          </h2>
          <RevenueChart series={m.series} />
        </section>

        {/* Status + producer split */}
        <div className="mt-8 grid gap-3 sm:grid-cols-2">
          <BreakdownCard title="Runs by status">
            {Object.entries(m.byStatus)
              .sort((a, b) => b[1] - a[1])
              .map(([status, count]) => (
                <div key={status} className="flex items-center justify-between py-1.5">
                  <StatusChip status={status} />
                  <span className="text-sm font-semibold text-ink">{count}</span>
                </div>
              ))}
          </BreakdownCard>

          {m.producerTagged > 0 ? (
            <BreakdownCard
              title="Producer split"
              note={`${m.producerTagged} of ${m.total} runs tagged`}
            >
              {Object.entries(m.byProducer)
                .sort((a, b) => b[1] - a[1])
                .map(([producer, count]) => (
                  <div key={producer} className="flex items-center justify-between py-1.5">
                    <span className="font-mono text-xs text-slate-600">{producer}</span>
                    <span className="text-sm font-semibold text-ink">{count}</span>
                  </div>
                ))}
            </BreakdownCard>
          ) : (
            <BreakdownCard title="Producer split">
              <p className="py-2 text-sm text-slate-400">
                No runs tagged with a producer yet.
              </p>
            </BreakdownCard>
          )}
        </div>

        {/* Per-video table */}
        <section className="mt-8">
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-400">
            Per-video
          </h2>
          <div className="overflow-x-auto rounded-2xl border border-black/5 bg-white">
            <table className="w-full min-w-[680px] text-sm">
              <thead>
                <tr className="border-b border-black/5 text-left text-xs uppercase tracking-wide text-slate-400">
                  <th className="px-4 py-3 font-medium">Date</th>
                  <th className="px-4 py-3 font-medium">Brand</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                  <th className="px-4 py-3 text-right font-medium">Price</th>
                  <th className="px-4 py-3 text-right font-medium">COGS</th>
                  <th className="px-4 py-3 text-right font-medium">Profit</th>
                  <th className="px-4 py-3 font-medium">Video</th>
                </tr>
              </thead>
              <tbody>
                {(data?.rows ?? []).map((r) => {
                  const rowCogs = cogsCentsFor(r)
                  const profit = (r.price_cents || 0) - rowCogs
                  return (
                    <tr key={r.id} className="border-b border-black/[0.04] last:border-0">
                      <td className="whitespace-nowrap px-4 py-2.5 text-slate-500">
                        {new Date(r.created_at).toLocaleDateString([], {
                          month: 'short',
                          day: 'numeric',
                        })}
                      </td>
                      <td className="max-w-[180px] truncate px-4 py-2.5 font-medium text-ink">
                        <Link href={`/runs/${r.id}`} className="transition hover:text-amber">
                          {r.brand || r.company_url}
                        </Link>
                      </td>
                      <td className="px-4 py-2.5">
                        <StatusChip status={r.status} />
                      </td>
                      <td className="whitespace-nowrap px-4 py-2.5 text-right tabular-nums text-ink">
                        {formatCents(r.price_cents)}
                      </td>
                      <td className="whitespace-nowrap px-4 py-2.5 text-right tabular-nums text-slate-500">
                        {DELIVERED.has(r.status) ? formatCentsPrecise(rowCogs) : '--'}
                      </td>
                      <td className="whitespace-nowrap px-4 py-2.5 text-right tabular-nums font-medium text-nemo">
                        {r.price_cents == null ? '--' : formatCentsPrecise(profit)}
                      </td>
                      <td className="px-4 py-2.5">
                        {r.final_url ? (
                          <a
                            href={r.final_url}
                            target="_blank"
                            rel="noreferrer"
                            className="text-xs font-medium text-amber transition hover:underline"
                          >
                            View ↗
                          </a>
                        ) : (
                          <span className="text-xs text-slate-300">—</span>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </section>

        <p className="mt-5 text-xs leading-relaxed text-slate-400">
          Revenue reflects Stripe <span className="font-medium">test-mode</span> checkouts. COGS
          per delivered video = ElevenLabs voiceover ({ELEVENLABS_USD_PER_1K_CHARS.toFixed(2)}
          {' '}$/1k chars, the main driver) + <span className="font-medium">Nemotron token cost</span>.
          The token line is the <span className="font-medium">actual</span> OpenRouter spend
          recorded per run (planner <span className="font-mono">usage.cost</span>, grossed up
          {' '}{READ_BRIEF_GROSS_UP}× for the un-logged Conversion Read + design-brief calls);
          when a run didn&apos;t record it, it&apos;s estimated from the run&apos;s brain rate
          (550B <span className="font-mono">ultra-paid</span> ≈ $0.0075/video; free 120B
          {' '}<span className="font-mono">super-free</span> ≈ $0). VO length is exact when the
          render duration was stored, else inferred at ~{VO_CHARS_PER_SECOND} chars/sec.
          Profit = price − COGS.
        </p>
      </main>
    </>
  )
}

function BigStat({
  label,
  value,
  sub,
  accent,
}: {
  label: string
  value: string
  sub?: string
  accent?: 'blue' | 'green'
}) {
  const valueColor =
    accent === 'blue' ? 'text-amber' : accent === 'green' ? 'text-nemo' : 'text-ink'
  return (
    <div className="rounded-2xl border border-black/5 bg-white px-4 py-4">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-400">{label}</p>
      <p className={`mt-1.5 text-2xl font-semibold tracking-tight ${valueColor}`}>{value}</p>
      {sub ? <p className="mt-0.5 text-xs text-slate-400">{sub}</p> : null}
    </div>
  )
}

function SmallStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-black/5 bg-white px-3.5 py-3">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-400">{label}</p>
      <p className="mt-1 text-lg font-semibold text-ink">{value}</p>
    </div>
  )
}

function BreakdownCard({
  title,
  note,
  children,
}: {
  title: string
  note?: string
  children: React.ReactNode
}) {
  return (
    <div className="rounded-2xl border border-black/5 bg-white px-4 py-4">
      <div className="mb-2 flex items-baseline justify-between">
        <h3 className="text-sm font-semibold text-ink">{title}</h3>
        {note ? <span className="text-xs text-slate-400">{note}</span> : null}
      </div>
      <div className="divide-y divide-black/[0.04]">{children}</div>
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
    return (
      <div className="rounded-2xl border border-black/5 bg-white px-4 py-10 text-center text-sm text-slate-400">
        Not enough dated revenue yet to chart.
      </div>
    )
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
    <div className="rounded-2xl border border-black/5 bg-white p-4">
      <div className="mb-1 flex items-baseline justify-between">
        <span className="text-2xl font-semibold tracking-tight text-amber">
          {formatCents(last.cumulative)}
        </span>
        <span className="text-xs text-slate-400">
          {series[0].day} → {last.day}
        </span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="h-44 w-full" preserveAspectRatio="none">
        <defs>
          <linearGradient id="rev-fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#3B82F6" stopOpacity="0.18" />
            <stop offset="100%" stopColor="#3B82F6" stopOpacity="0" />
          </linearGradient>
        </defs>
        <path d={areaPath} fill="url(#rev-fill)" />
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
