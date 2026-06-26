'use client'
import { useEffect, useState } from 'react'
import { formatCents, type Run, type RunEvent } from '../../lib/types'

/**
 * Live "the agent is building" view for a non-terminal run.
 *
 * Replaces the old static RunningPanel. Conveys continuous progress so nobody
 * thinks a ~6 min run has stalled:
 *  - a stage tracker derived from run.phase (completed / active / pending),
 *  - a prominent live activity feed (the real Hermes / Nemotron stream),
 *  - an elapsed timer + animated shimmer for reassurance.
 *
 * On-brand with the light Filmo theme. No emojis — SVG marks only.
 */

// Pipeline stages in display order. `phases` lists every backend phase string
// (from orchestrator.py / build_runner.py set_phase calls) that maps to it.
const STAGES: { label: string; phases: string[] }[] = [
  { label: 'Reading the site', phases: [] }, // implicit pre-planning step
  { label: 'Planning', phases: ['planning'] },
  { label: 'Pricing', phases: ['pricing', 'earning', 'awaiting_payment'] },
  { label: 'Producing scenes', phases: ['producing'] },
  { label: 'Voiceover', phases: ['voiceover'] },
  { label: 'Stitching', phases: ['stitching'] },
  { label: 'Delivering', phases: ['delivered'] },
]

// Resolve the active stage index from run.phase. Anything we don't recognize
// (e.g. a brand-new run with no phase yet) sits at the first stage.
function activeStageIndex(phase: string | null): number {
  if (!phase) return 0
  const p = phase.toLowerCase()
  for (let i = STAGES.length - 1; i >= 0; i--) {
    if (STAGES[i].phases.includes(p)) return i
  }
  // Unknown phase string (payment_timeout, etc.) — keep the tracker honest by
  // anchoring on the last recognized milestone rather than jumping around.
  return 0
}

function CheckMark() {
  return (
    <svg viewBox="0 0 20 20" className="h-3.5 w-3.5" aria-hidden>
      <path
        d="M5 10.5l3 3 7-7"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function Spinner() {
  return (
    <svg viewBox="0 0 20 20" className="h-3.5 w-3.5 animate-spin" aria-hidden>
      <circle cx="10" cy="10" r="7" fill="none" stroke="currentColor" strokeOpacity="0.25" strokeWidth="2.4" />
      <path
        d="M10 3a7 7 0 0 1 7 7"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.4"
        strokeLinecap="round"
      />
    </svg>
  )
}

function StageRow({
  label,
  state,
}: {
  label: string
  state: 'done' | 'active' | 'pending'
}) {
  const dot =
    state === 'done'
      ? 'bg-nemo text-white'
      : state === 'active'
        ? 'bg-amber text-white'
        : 'border border-slate-200 bg-white text-slate-300'
  const text =
    state === 'pending' ? 'text-slate-400' : state === 'active' ? 'text-ink font-medium' : 'text-slate-600'
  return (
    <li className="flex items-center gap-3">
      <span className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full ${dot}`}>
        {state === 'done' ? <CheckMark /> : state === 'active' ? <Spinner /> : null}
      </span>
      <span className={`text-sm ${text}`}>{label}</span>
      {state === 'active' && (
        <span className="ml-auto text-[11px] font-medium uppercase tracking-wide text-amber">Working</span>
      )}
    </li>
  )
}

function formatElapsed(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000))
  const m = Math.floor(total / 60)
  const s = total % 60
  return `${m}:${s.toString().padStart(2, '0')}`
}

function useElapsed(createdAt: string): string {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(t)
  }, [])
  const start = new Date(createdAt).getTime()
  if (Number.isNaN(start)) return '0:00'
  return formatElapsed(now - start)
}

const ACTOR_STYLES: Record<string, string> = {
  hermes: 'bg-amber/10 text-amber',
  nemotron: 'bg-nemo/10 text-nemo',
  stripe: 'bg-indigo-50 text-indigo-600',
}

function ActorBadge({ actor }: { actor: string }) {
  const style = ACTOR_STYLES[actor] || 'bg-slate-100 text-slate-500'
  return (
    <span
      className={`mt-0.5 shrink-0 rounded px-1.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide ${style}`}
    >
      {actor}
    </span>
  )
}

// Pay affordance — shown only when the human-pays flow has parked the build at
// 'awaiting_payment' AND a Stripe TEST checkout URL is on the run. Opens Stripe's
// hosted test checkout in a new tab; once the human pays (test card 4242), the
// pipeline's payment gate resolves and the build continues. The page already polls
// run status, so no extra polling is needed here. Landing tokens: white surface,
// ink #0E1320, blue accent (#3B82F6). No emojis — SVG lock mark only.
function PayPanel({ run }: { run: Run }) {
  const price = formatCents(run.price_cents)
  return (
    <div className="mt-5 rounded-xl border border-[#3B82F6]/30 bg-[#F8FAFF] p-5 ring-1 ring-inset ring-[#EAF1FF]">
      <div className="flex items-start gap-3">
        <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[#3B82F6]/10 text-[#3B82F6]">
          <svg viewBox="0 0 20 20" className="h-4 w-4" aria-hidden>
            <path
              d="M6 9V6.5a4 4 0 0 1 8 0V9"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.6"
              strokeLinecap="round"
            />
            <rect x="4.5" y="9" width="11" height="7.5" rx="1.6" fill="none" stroke="currentColor" strokeWidth="1.6" />
          </svg>
        </span>
        <div className="min-w-0">
          <p className="font-semibold text-[#0E1320]">Payment required to continue</p>
          <p className="mt-1 text-sm text-[#5A6472]">
            Your video is planned and priced. Complete checkout to release production — the build
            resumes automatically once payment clears.
          </p>
        </div>
      </div>

      <a
        href={run.checkout_url ?? '#'}
        target="_blank"
        rel="noreferrer"
        className="mt-4 flex w-full items-center justify-center gap-2 rounded-xl bg-[#3B82F6] py-3 font-semibold text-white shadow-[0_10px_30px_-10px_rgba(59,130,246,0.6)] transition hover:bg-[#2f6fe0]"
      >
        Pay {price}
        <span className="text-xs font-normal text-white/80">— test card 4242·4242·4242·4242</span>
      </a>

      <p className="mt-2.5 text-center text-[11px] text-[#5A6472]">
        Stripe test checkout — no real charge. Opens in a new tab.
      </p>
    </div>
  )
}

export default function BuildProgress({ run, events }: { run: Run; events: RunEvent[] }) {
  const isQueued = run.status === 'queued'
  const elapsed = useElapsed(run.created_at)
  const active = activeStageIndex(run.phase)

  // Most-recent activity first; the newest line gets a highlight so motion reads.
  const recent = [...events].sort((a, b) => b.seq - a.seq).slice(0, 6)

  // Human-pays flow: the build is parked awaiting a real Stripe TEST payment.
  const awaitingPayment = run.phase === 'awaiting_payment' && !!run.checkout_url

  return (
    <div className="mt-6 overflow-hidden rounded-2xl border border-black/5 bg-white shadow-sm">
      {/* Animated top progress bar — indeterminate shimmer that never sits still */}
      <div className="relative h-1 w-full overflow-hidden bg-amber/10">
        <div className="absolute inset-y-0 left-0 w-1/3 animate-[bp-slide_1.8s_ease-in-out_infinite] rounded-full bg-amber" />
      </div>

      <div className="px-5 py-6">
        {/* Header line: live pulse + headline + elapsed timer */}
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2.5">
            <span className="relative flex h-2.5 w-2.5">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-amber/50" />
              <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-amber" />
            </span>
            <p className="font-medium text-ink">
              {isQueued ? 'Queued — starting up' : 'Building your video'}
            </p>
          </div>
          <span className="rounded-full bg-slate-50 px-2.5 py-1 font-mono text-xs tabular-nums text-slate-500">
            {elapsed}
          </span>
        </div>

        <p className="mt-2 text-sm text-slate-500">
          {isQueued
            ? 'Reserved a worker — the agent will begin reading your product in a moment.'
            : 'This usually takes 1–3 minutes — the agent is reading your product, planning, and rendering.'}
        </p>

        {/* Pay CTA — only when the human-pays flow parked the build awaiting a real
            Stripe TEST payment. Prominent, above the stage tracker. */}
        {awaitingPayment && <PayPanel run={run} />}

        {/* Stage tracker */}
        <ol className="mt-5 space-y-2.5">
          {STAGES.map((stage, i) => (
            <StageRow
              key={stage.label}
              label={stage.label}
              state={isQueued ? 'pending' : i < active ? 'done' : i === active ? 'active' : 'pending'}
            />
          ))}
        </ol>

        {/* Live activity — surfaced inside the building view so the user sees motion */}
        <div className="mt-6 border-t border-black/5 pt-5">
          <div className="mb-2.5 flex items-center justify-between">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-400">Live activity</h3>
            <span className="text-[11px] text-slate-300">updates every few seconds</span>
          </div>
          {recent.length === 0 ? (
            <p className="text-sm text-slate-400">Warming up — first actions will appear here.</p>
          ) : (
            <ul className="space-y-1.5">
              {recent.map((e, i) => (
                <li
                  key={e.id}
                  className={`flex items-start gap-3 rounded-lg px-3 py-2 transition ${
                    i === 0 ? 'border border-amber/30 bg-amber/[0.06]' : 'border border-transparent'
                  }`}
                >
                  <ActorBadge actor={e.actor} />
                  <span className="flex-1 text-sm text-ink">{e.msg}</span>
                  <span className="shrink-0 text-xs text-slate-300">
                    {new Date(e.created_at).toLocaleTimeString([], {
                      hour: '2-digit',
                      minute: '2-digit',
                      second: '2-digit',
                    })}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {/* Keyframes for the indeterminate progress bar. Scoped via a unique name. */}
      <style jsx>{`
        @keyframes bp-slide {
          0% {
            transform: translateX(-110%);
          }
          100% {
            transform: translateX(410%);
          }
        }
      `}</style>
    </div>
  )
}
