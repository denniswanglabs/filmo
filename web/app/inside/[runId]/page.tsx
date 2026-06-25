'use client'
import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import { useParams, useRouter } from 'next/navigation'
import { useAuth } from '../../../lib/auth'
import { TopBar, StatusChip } from '../../components/Brand'
import { isDeveloper, readInsideRun } from '../../actions'
import { formatCents, formatMargin } from '../../../lib/types'
import {
  FEATURED_RUN,
  FEATURED_RUN_ID,
  type ConversionRead,
  type StripeDecline,
  type FeaturedRun,
} from '../../../lib/featured-run'

type Gate = 'checking' | 'denied' | 'ok'

// The shape /inside renders: a unified view assembled either from the baked fixture
// or from a live InsForge run (best-effort — live runs may not carry a Conversion Read).
interface InsideView {
  id: string
  brand: string
  company_url: string
  goal: string
  quality: string
  status: string
  price_cents: number | null
  cogs_cents: number | null
  margin: number | null
  overage_avoided_cents: number | null
  gross_profit_cents: number | null
  conversion_read: ConversionRead | null
  decline: StripeDecline | null
  nemoclaw_image: string | null
}

function fromFeatured(f: FeaturedRun): InsideView {
  return {
    id: f.id,
    brand: f.brand,
    company_url: f.company_url,
    goal: f.goal,
    quality: f.quality,
    status: f.status,
    price_cents: f.price_cents,
    cogs_cents: f.cogs_cents,
    margin: f.margin,
    overage_avoided_cents: f.overage_avoided_cents,
    gross_profit_cents: f.gross_profit_cents,
    conversion_read: f.conversion_read,
    decline: f.decline,
    nemoclaw_image: f.nemoclaw_image,
  }
}

function fromLiveRun(run: Record<string, unknown>): InsideView {
  const num = (v: unknown) => (typeof v === 'number' ? v : null)
  const str = (v: unknown) => (typeof v === 'string' ? v : '')
  return {
    id: str(run.id),
    brand: str(run.brand) || str(run.company_url),
    company_url: str(run.company_url),
    goal: str(run.goal) || 'Brand video',
    quality: str(run.quality) || 'standard',
    status: str(run.status) || 'queued',
    price_cents: num(run.price_cents),
    cogs_cents: num(run.cogs_cents),
    margin: num(run.margin),
    // Live runs don't carry these derived fields on the row yet → "n/a", never invented.
    overage_avoided_cents: null,
    gross_profit_cents: null,
    conversion_read: null,
    decline: null,
    nemoclaw_image: null,
  }
}

export default function InsideRunPage() {
  const params = useParams<{ runId: string }>()
  const runId = params?.runId
  const router = useRouter()
  const { user, loading } = useAuth()

  const [gate, setGate] = useState<Gate>('checking')
  const [view, setView] = useState<InsideView | null>(null)
  const [notFound, setNotFound] = useState(false)

  const load = useCallback(async () => {
    if (!runId) return
    if (runId === FEATURED_RUN_ID) {
      setView(fromFeatured(FEATURED_RUN))
      return
    }
    const res = await readInsideRun(runId)
    if (!res) {
      setNotFound(true)
      return
    }
    setView(fromLiveRun(res.run))
  }, [runId])

  // Gate on the developer flag once auth resolves. Non-developers bounce to /inside.
  useEffect(() => {
    if (loading) return
    let cancelled = false
    ;(async () => {
      if (!user) {
        if (!cancelled) {
          setGate('denied')
          router.replace('/inside')
        }
        return
      }
      const dev = await isDeveloper(user.id)
      if (cancelled) return
      if (!dev) {
        setGate('denied')
        router.replace('/inside')
        return
      }
      setGate('ok')
      void load()
    })()
    return () => {
      cancelled = true
    }
  }, [loading, user, router, load])

  if (loading || gate === 'checking') {
    return <div className="flex min-h-screen items-center justify-center text-slate-400">Loading…</div>
  }
  if (gate === 'denied') {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-3 px-5 text-center text-slate-500">
        <p>Developer mode required to view the inside of a run.</p>
        <Link href="/inside" className="font-medium text-amber hover:underline">
          Enter your developer key →
        </Link>
      </div>
    )
  }

  return (
    <>
      <TopBar />
      <main className="mx-auto max-w-3xl px-5 pb-24 pt-8">
        <Link href="/inside" className="text-sm text-slate-400 transition hover:text-ink">
          ← Developer mode
        </Link>

        {notFound ? (
          <p className="mt-10 text-slate-500">This run could not be found.</p>
        ) : !view ? (
          <p className="mt-10 text-slate-400">Loading the inside view…</p>
        ) : (
          <div className="mt-5 space-y-8">
            {/* Header */}
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="rounded-full border border-amber/30 bg-amber/10 px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-amber">
                    Inside
                  </span>
                  {view.id === FEATURED_RUN_ID && (
                    <span className="rounded-full border border-nemo/30 bg-nemo/10 px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-nemo">
                      Featured
                    </span>
                  )}
                </div>
                <h1 className="mt-2 truncate text-2xl font-semibold tracking-tight text-ink">
                  {view.brand}
                </h1>
                <p className="mt-1 text-slate-500">{view.goal}</p>
              </div>
              <StatusChip status={view.status} />
            </div>

            {/* Conversion Read */}
            <ConversionReadPanel read={view.conversion_read} />

            {/* Stripe decline (the money-shot) */}
            <DeclinePanel decline={view.decline} />

            {/* NemoClaw in-sandbox capture */}
            <NemoclawPanel src={view.nemoclaw_image} />

            {/* P&L */}
            <PnlPanel view={view} />
          </div>
        )}
      </main>
    </>
  )
}

const DIM_LABELS: Record<string, string> = {
  promise: 'Promise',
  outcome: 'Outcome',
  proof: 'Proof',
  show: 'Show',
  specificity: 'Specificity',
  cta: 'CTA',
}

function ScoreBadge({ score }: { score: number }) {
  // 0-5 → red (low) / slate (mid) / green (high). No emojis — colored numeric badge.
  const tone =
    score <= 1
      ? 'bg-red-50 text-red-600 border-red-200'
      : score <= 3
        ? 'bg-amber/10 text-amber border-amber/30'
        : 'bg-nemo/10 text-nemo border-nemo/30'
  return (
    <span className={`shrink-0 rounded-md border px-2 py-0.5 text-sm font-semibold tabular-nums ${tone}`}>
      {score}/5
    </span>
  )
}

function Section({
  title,
  children,
  right,
}: {
  title: string
  children: React.ReactNode
  right?: React.ReactNode
}) {
  return (
    <section>
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-400">{title}</h2>
        {right}
      </div>
      {children}
    </section>
  )
}

function ConversionReadPanel({ read }: { read: ConversionRead | null }) {
  if (!read) {
    return (
      <Section title="Conversion Read">
        <p className="rounded-xl border border-dashed border-black/10 px-4 py-6 text-sm text-slate-400">
          n/a — this run predates the Conversion Read stage.
        </p>
      </Section>
    )
  }
  return (
    <Section
      title="Conversion Read"
      right={
        read.degraded ? (
          <span className="text-xs font-medium text-amber">best-effort (degraded)</span>
        ) : (
          <span className="text-xs font-medium text-nemo">Nemotron — full read</span>
        )
      }
    >
      <div className="rounded-2xl border border-black/5 bg-white p-5">
        <p className="text-[15px] leading-relaxed text-ink">{read.verdict}</p>

        <div className="mt-5 space-y-3">
          {read.dimensions.map((d) => (
            <div key={d.key} className="rounded-xl border border-black/5 bg-white px-4 py-3">
              <div className="flex items-center justify-between gap-3">
                <span className="text-sm font-semibold text-ink">{DIM_LABELS[d.key] || d.key}</span>
                <ScoreBadge score={d.score} />
              </div>
              <p className="mt-2 text-sm text-slate-600">{d.finding}</p>
              <p className="mt-2 text-xs italic text-slate-400">“{d.evidence}”</p>
              <p className="mt-2 text-sm text-ink">
                <span className="font-medium text-amber">Fix:</span> {d.fix}
              </p>
            </div>
          ))}
        </div>

        {/* Priority fixes */}
        <div className="mt-5">
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
            Priority fixes
          </h3>
          <ol className="space-y-2">
            {read.priority_fixes.map((p) => (
              <li
                key={p.rank}
                className="flex items-start gap-3 rounded-lg border border-black/5 bg-white px-3.5 py-2.5"
              >
                <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-amber text-xs font-semibold text-white">
                  {p.rank}
                </span>
                <div className="min-w-0">
                  <p className="text-sm text-ink">{p.fix}</p>
                  <p className="mt-0.5 text-xs text-slate-400">maps to: {p.maps_to}</p>
                </div>
              </li>
            ))}
          </ol>
        </div>

        {/* Headline fix — the line that opens the video */}
        <div className="mt-5 rounded-xl border border-nemo/20 bg-nemo/[0.05] px-4 py-3">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Headline fix — opens the video
          </p>
          <p className="mt-1 text-[15px] font-medium text-ink">“{read.headline_fix}”</p>
        </div>
      </div>
    </Section>
  )
}

function DeclinePanel({ decline }: { decline: StripeDecline | null }) {
  if (!decline) {
    return (
      <Section title="Autonomous Stripe decline">
        <p className="rounded-xl border border-dashed border-black/10 px-4 py-6 text-sm text-slate-400">
          n/a — no card decline recorded for this run.
        </p>
      </Section>
    )
  }
  return (
    <Section title="Autonomous Stripe decline">
      <div className="rounded-2xl border border-red-200 bg-red-50 p-5">
        <div className="flex items-center justify-between gap-3">
          <span className="rounded-md border border-red-200 bg-white px-2 py-0.5 text-xs font-semibold uppercase tracking-wide text-red-600">
            Declined
          </span>
          <span className="font-mono text-xs text-red-500">card •••• {decline.card_last4}</span>
        </div>
        <p className="mt-3 text-sm leading-relaxed text-red-800">{decline.event}</p>
        <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <MiniStat label="Scene" value={decline.scene_id} red />
          <MiniStat label="Planned" value={formatCents(decline.planned_cents)} red />
          <MiniStat label="Would-be cost" value={formatCents(decline.would_have_cost_cents)} red />
          <MiniStat label="Spent" value="$0.00" red />
        </div>
        <p className="mt-3 text-xs text-red-500">Reason: {decline.reason}</p>
        <p className="mt-1 font-mono text-[11px] text-red-400">{decline.card_id}</p>
      </div>
    </Section>
  )
}

function NemoclawPanel({ src }: { src: string | null }) {
  return (
    <Section title="NemoClaw in-sandbox capture">
      {src ? (
        <figure className="overflow-hidden rounded-2xl border border-black/5 bg-white shadow-sm">
          {/* Real in-sandbox capture PNG/JPG (downscaled). Native <img> is fine here. */}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={src} alt="NemoClaw in-sandbox capture of the target site" className="w-full" />
          <figcaption className="border-t border-black/5 px-4 py-2.5 text-xs text-slate-400">
            Captured inside the NemoClaw / OpenShell sandbox — the agent reads any URL itself.
          </figcaption>
        </figure>
      ) : (
        <p className="rounded-xl border border-dashed border-black/10 px-4 py-6 text-sm text-slate-400">
          n/a — no sandbox capture stored for this run.
        </p>
      )}
    </Section>
  )
}

function PnlPanel({ view }: { view: InsideView }) {
  return (
    <Section title="P&L">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <Stat label="Price" value={formatCents(view.price_cents)} />
        <Stat label="COGS spent" value={formatCents(view.cogs_cents)} />
        <Stat label="Margin" value={formatMargin(view.margin)} accent />
        <Stat
          label="Gross profit"
          value={view.gross_profit_cents != null ? formatCents(view.gross_profit_cents) : 'n/a'}
        />
        <Stat
          label="Overage avoided"
          value={
            view.overage_avoided_cents != null ? formatCents(view.overage_avoided_cents) : 'n/a'
          }
          accent
        />
        <Stat label="Quality" value={view.quality} capitalize />
      </div>
    </Section>
  )
}

function Stat({
  label,
  value,
  accent,
  capitalize,
}: {
  label: string
  value: string
  accent?: boolean
  capitalize?: boolean
}) {
  return (
    <div className="rounded-xl border border-black/5 bg-white px-3.5 py-3">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-400">{label}</p>
      <p
        className={`mt-1 text-lg font-semibold ${accent ? 'text-nemo' : 'text-ink'} ${
          capitalize ? 'capitalize' : ''
        }`}
      >
        {value}
      </p>
    </div>
  )
}

function MiniStat({ label, value, red }: { label: string; value: string; red?: boolean }) {
  return (
    <div className={`rounded-lg border px-3 py-2 ${red ? 'border-red-200 bg-white' : 'border-black/5 bg-white'}`}>
      <p className={`text-[10px] font-medium uppercase tracking-wide ${red ? 'text-red-400' : 'text-slate-400'}`}>
        {label}
      </p>
      <p className={`mt-0.5 text-sm font-semibold ${red ? 'text-red-700' : 'text-ink'}`}>{value}</p>
    </div>
  )
}
