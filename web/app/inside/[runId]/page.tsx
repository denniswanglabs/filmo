'use client'
// ═══════════ /inside/[runId] — THE INSIDE OF ONE RUN, ON THE STUDIO GROUND ═══
//
// This page used to wear the old white chrome: `TopBar` from components/Brand
// over a bare white page. It now wears the /analytics shell — studio ground,
// white cards, #E6E6E3 hairlines, the rail with nothing lit — for the same
// reason /analytics does: an operator surface may not read as a different
// product from the rooms one rail-click away.
//
// WHAT DID NOT CHANGE, DELIBERATELY: the developer gate (isDeveloper →
// bounce to /inside), the featured-fixture vs live-run split, and every panel —
// Conversion Read, the Stripe decline, the NemoClaw capture, the P&L. Those
// panels are the CONTENT of this page, already drawn as white cards; only the
// chrome around them moved. If a number reads differently it is a bug in this
// rewrite, not a new opinion about the run.
import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import { createPortal } from 'react-dom'
import { useParams, useRouter } from 'next/navigation'
import { useAuth } from '../../../lib/auth'
import { StatusChip } from '../../components/Brand'
import OverviewRail from '../../components/overview/OverviewRail'
import FeedbackModal from '../../runs/[id]/FeedbackModal'
import FilmoLoader, { GROUND_STUDIO } from '../../components/FilmoLoader'
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
  const { user, loading, getToken } = useAuth()

  const [mounted, setMounted] = useState(false)
  const [fbOpen, setFbOpen] = useState(false)
  const [gate, setGate] = useState<Gate>('checking')
  const [view, setView] = useState<InsideView | null>(null)
  const [notFound, setNotFound] = useState(false)

  useEffect(() => setMounted(true), [])

  const load = useCallback(async () => {
    if (!runId) return
    if (runId === FEATURED_RUN_ID) {
      setView(fromFeatured(FEATURED_RUN))
      return
    }
    const accessToken = await getToken()
    const res = accessToken ? await readInsideRun({ runId, accessToken }) : null
    if (!res) {
      setNotFound(true)
      return
    }
    setView(fromLiveRun(res.run))
  }, [runId, getToken])

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
      const accessToken = await getToken()
      const dev = accessToken ? await isDeveloper(accessToken) : false
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
  }, [loading, user, router, load, getToken])

  // Auth resolving, the developer-mode check in flight, or no document yet to
  // portal into — the boot screen on the destination's own ground, a
  // continuation of this route's loading.tsx.
  if (loading || gate === 'checking' || !mounted) {
    return <FilmoLoader ground={GROUND_STUDIO} />
  }

  // ── WHAT GOES IN THE STAGE ──────────────────────────────────────────────────
  // The branch order is the one this page has always used: denied → not found →
  // still loading → the run. The shell (rail, ground, feedback sheet) sits
  // outside the branch, so even the denied flash keeps the product's navigation
  // while router.replace carries the reader back to /inside.
  let body: React.ReactNode

  if (gate === 'denied') {
    body = (
      <div className="ir-gate">
        <b>Developer mode required to view the inside of a run.</b>
        <Link href="/inside" className="ir-gatelink">
          Enter your developer key
        </Link>
      </div>
    )
  } else if (notFound) {
    body = (
      <div className="ir-gate">
        <b>This run could not be found.</b>
        <Link href="/inside" className="ir-gatelink">
          Back to developer mode
        </Link>
      </div>
    )
  } else if (!view) {
    body = <FilmoLoader ground={GROUND_STUDIO} fit="block" />
  } else {
    body = (
      <div className="space-y-8">
        {/* Header */}
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="ir-pill">
                <i aria-hidden />
                Inside
              </span>
              {view.id === FEATURED_RUN_ID && (
                <span className="ir-pill ir-pill-quiet">Featured</span>
              )}
            </div>
            <h1 className="ir-title mt-3 truncate">{view.brand}</h1>
            <p className="ir-goal mt-1">{view.goal}</p>
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
    )
  }

  return createPortal(
    <div className="ir-root">
      <OverviewRail current="none" getToken={getToken} onFeedback={() => setFbOpen(true)} />

      <main className="ir-stage">
        <div className="ir-inner">
          <Link href="/inside" className="ir-back">
            Developer mode
          </Link>
          <div className="mt-5">{body}</div>
        </div>
      </main>

      <FeedbackModal
        open={fbOpen}
        onClose={() => setFbOpen(false)}
        getToken={getToken}
        context={runId ? `/inside/${runId}` : '/inside'}
      />

      <style>{`
        .ir-root { position:fixed; inset:0; display:flex; background:#F1F1EF;
          color:#1B1B1A; font:14px/1.5 Inter,-apple-system,sans-serif; z-index:50; }
        .ir-stage { flex:1 1 0; min-width:0; min-height:0; overflow-y:auto;
          overflow-x:hidden; }
        .ir-inner { max-width:820px; margin:0 auto; padding:38px 32px 64px; }

        .ir-back { display:inline-flex; align-items:center; gap:6px;
          font-size:13px; color:#8A8A86; text-decoration:none; border-radius:4px; }
        .ir-back::before { content:'\\2190'; }
        .ir-back:hover { color:#1B1B1A; }
        .ir-back:focus-visible { outline:2px solid #3B82F6; outline-offset:3px;
          color:#1B1B1A; }

        .ir-pill { display:inline-flex; align-items:center; gap:6px;
          background:#EAF1FF; border:1px solid #C9D9F8; border-radius:99px;
          padding:4px 11px; font-size:12px; font-weight:600; color:#1D4ED8; }
        .ir-pill i { width:6px; height:6px; border-radius:50%; background:#3B82F6; }
        .ir-pill-quiet { background:#fff; border-color:#E6E6E3; color:#6E6E6A; }

        .ir-title { margin:0; font-size:28px; font-weight:600;
          letter-spacing:-.025em; line-height:1.15; color:#1B1B1A; }
        .ir-goal { margin:0; font-size:14.5px; color:#8A8A86; }

        .ir-gate { background:#fff; border:1px solid #E6E6E3; border-radius:14px;
          padding:26px; display:flex; flex-direction:column; gap:10px;
          align-items:flex-start; max-width:520px; }
        .ir-gate b { font-size:15px; font-weight:650; color:#1B1B1A; }
        .ir-gatelink { display:inline-flex; align-items:center; justify-content:center;
          border:1px solid #1B1B1A; background:#1B1B1A; color:#fff;
          border-radius:99px; padding:9px 20px;
          font:13px/1 Inter,-apple-system,sans-serif; text-decoration:none; }
        .ir-gatelink:hover { background:#000; border-color:#000; }
        .ir-gatelink:focus-visible { outline:2px solid #3B82F6; outline-offset:3px; }

        @media (max-width:760px) {
          .ir-inner { padding:26px 18px 48px; }
          .ir-title { font-size:23px; } }
      `}</style>
    </div>,
    document.body,
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
  // 0-5 → red (low) / blue (mid) / green (high). No emojis — colored numeric badge.
  const tone =
    score <= 1
      ? 'bg-red-50 text-red-600 border-red-200'
      : score <= 3
        ? 'bg-[#EAF1FF] text-[#1D4ED8] border-[#C9D9F8]'
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
        <h2 className="text-xs font-semibold uppercase tracking-[.08em] text-[#8A8A86]">{title}</h2>
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
        <p className="rounded-xl border border-dashed border-[#DDDDD9] bg-white px-4 py-6 text-sm text-[#8A8A86]">
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
          <span className="text-xs font-medium text-[#8A8A86]">best-effort (degraded)</span>
        ) : (
          <span className="text-xs font-medium text-nemo">Nemotron — full read</span>
        )
      }
    >
      <div className="rounded-2xl border border-[#E6E6E3] bg-white p-5">
        <p className="text-[15px] leading-relaxed text-ink">{read.verdict}</p>

        <div className="mt-5 space-y-3">
          {read.dimensions.map((d) => (
            <div key={d.key} className="rounded-xl border border-[#F1F1EF] bg-white px-4 py-3">
              <div className="flex items-center justify-between gap-3">
                <span className="text-sm font-semibold text-ink">{DIM_LABELS[d.key] || d.key}</span>
                <ScoreBadge score={d.score} />
              </div>
              <p className="mt-2 text-sm text-slate-600">{d.finding}</p>
              <p className="mt-2 text-xs italic text-slate-400">“{d.evidence}”</p>
              <p className="mt-2 text-sm text-ink">
                <span className="font-medium text-[#1D4ED8]">Fix:</span> {d.fix}
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
                className="flex items-start gap-3 rounded-lg border border-[#F1F1EF] bg-white px-3.5 py-2.5"
              >
                <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[#1B1B1A] text-xs font-semibold text-white">
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
        <div className="mt-5 rounded-xl border border-[#C9D9F8] bg-[#EAF1FF] px-4 py-3">
          <p className="text-xs font-semibold uppercase tracking-wide text-[#1D4ED8]">
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
        <p className="rounded-xl border border-dashed border-[#DDDDD9] bg-white px-4 py-6 text-sm text-[#8A8A86]">
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
        <figure className="overflow-hidden rounded-2xl border border-[#E6E6E3] bg-white shadow-sm">
          {/* Real in-sandbox capture PNG/JPG (downscaled). Native <img> is fine here. */}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={src} alt="NemoClaw in-sandbox capture of the target site" className="w-full" />
          <figcaption className="border-t border-[#F1F1EF] px-4 py-2.5 text-xs text-slate-400">
            Captured inside the NemoClaw / OpenShell sandbox — the agent reads any URL itself.
          </figcaption>
        </figure>
      ) : (
        <p className="rounded-xl border border-dashed border-[#DDDDD9] bg-white px-4 py-6 text-sm text-[#8A8A86]">
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
    <div className="rounded-xl border border-[#E6E6E3] bg-white px-3.5 py-3">
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
    <div className={`rounded-lg border px-3 py-2 ${red ? 'border-red-200 bg-white' : 'border-[#E6E6E3] bg-white'}`}>
      <p className={`text-[10px] font-medium uppercase tracking-wide ${red ? 'text-red-400' : 'text-slate-400'}`}>
        {label}
      </p>
      <p className={`mt-0.5 text-sm font-semibold ${red ? 'text-red-700' : 'text-ink'}`}>{value}</p>
    </div>
  )
}
