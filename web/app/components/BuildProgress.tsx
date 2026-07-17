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
  // Reading now has a REAL backend phase ('analyzing'): the OPTION-A split runs a
  // dedicated read->plan->price pass FIRST, so the Reading stage reflects genuine
  // state instead of being purely implicit. ('reading' kept as an alias.)
  { label: 'Reading the site', phases: ['analyzing', 'reading'] },
  { label: 'Planning', phases: ['planning'] },
  // 'awaiting_payment' is NO LONGER mapped onto Pricing's phases. In the OPTION-A
  // flow read/plan/price genuinely complete BEFORE the pay prompt, so a parked run
  // must show Reading+Planning+Pricing DONE and Pricing as the reached milestone —
  // handled explicitly in activeStageIndex (NOT by listing awaiting_payment here,
  // which would mis-mark the Pricing row's own done/active state).
  { label: 'Pricing', phases: ['pricing', 'earning'] },
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
  // OPTION A: parked awaiting payment. Read/plan/price already ran, so anchor on
  // the Pricing milestone (index 2): Reading + Planning show DONE, Pricing is the
  // current/reached stage, Producing+ stay pending until payment clears. This is
  // HONEST now that the plan pass runs before the gate (the old flow paid first).
  if (p === 'awaiting_payment') return 2
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
  filmo: 'bg-amber/10 text-amber',
  stripe: 'bg-indigo-50 text-indigo-600',
}

// Legacy runs carry hermes/nemotron actors from the retired conduct era — they
// render as FILMO so old run pages match the current brand voice.
const LEGACY_ACTOR_DISPLAY: Record<string, string> = {
  hermes: 'filmo',
  nemotron: 'filmo',
}

function ActorBadge({ actor }: { actor: string }) {
  const display = LEGACY_ACTOR_DISPLAY[actor] ?? actor
  const style = ACTOR_STYLES[display] || 'bg-slate-100 text-slate-500'
  return (
    <span
      className={`mt-0.5 shrink-0 rounded px-1.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide ${style}`}
    >
      {display}
    </span>
  )
}

// Chat avatar for the build conversation. `user` = the person who requested the
// build; `agent` = the Filmo producer agent (soft blue blob mark, no emoji).
function ChatAvatar({ who }: { who: 'user' | 'agent' }) {
  if (who === 'user') {
    return (
      <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border border-slate-200 bg-slate-50 text-slate-400">
        <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" aria-hidden>
          <circle cx="12" cy="8" r="3.4" stroke="currentColor" strokeWidth="1.7" />
          <path d="M5.5 19.5a6.5 6.5 0 0113 0" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
        </svg>
      </span>
    )
  }
  return (
    <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border border-[#3B82F6]/35 bg-[#3B82F6]/10">
      <svg viewBox="14 13 56 56" className="h-4 w-4" aria-hidden>
        <path fillRule="evenodd" fill="#3B82F6" d="M42 17 C56 15 67 27 65 41 C63 55 52 67 38 65 C25 63 16 51 19 37 C21 25 30 19 42 17 Z M47 28.5 A8.5 8.5 0 1 1 47 45.5 A8.5 8.5 0 1 1 47 28.5 Z" />
      </svg>
    </span>
  )
}

// The build activity log as a CHAT thread. First bubble = the user's prompt (the
// run's goal + emphasis); subsequent bubbles = the agent's steps (run_events, in
// chronological order). Mirrors the editor chat-panel vocabulary so the build and
// the edit loop feel like one continuous conversation.
function BuildChat({ run, events }: { run: Run; events: RunEvent[] }) {
  // Chronological (oldest first) so the thread reads top-to-bottom like a chat.
  // Hide internal infrastructure diagnostics (actor 'system', e.g. the asset verify-and-heal
  // probe) from the live feed — they're ops/log noise, not the user-facing production story.
  const ordered = [...events].filter((e) => e.actor !== 'system').sort((a, b) => a.seq - b.seq)
  const newestSeq = ordered.length ? ordered[ordered.length - 1].seq : -1

  // The user's opening request, assembled from the run's own fields.
  const prompt =
    (run.goal || 'A brand video') +
    (run.emphasis ? ` — emphasis: ${run.emphasis}` : '') +
    (run.company_url ? `\n${run.company_url}` : '')

  return (
    <div className="max-h-80 space-y-3 overflow-y-auto overscroll-contain pr-1">
      {/* User prompt bubble (right-aligned, blue) */}
      <div className="flex flex-row-reverse items-start gap-2.5">
        <ChatAvatar who="user" />
        <div className="max-w-[82%] whitespace-pre-wrap rounded-2xl rounded-tr-sm bg-[#3B82F6] px-3.5 py-2 text-sm text-white shadow-sm">
          {prompt}
        </div>
      </div>

      {ordered.length === 0 ? (
        <div className="flex items-start gap-2.5">
          <ChatAvatar who="agent" />
          <div className="max-w-[82%] rounded-2xl rounded-tl-sm border border-black/5 bg-white px-3.5 py-2 text-sm text-slate-500 shadow-sm">
            Warming up — I&apos;ll start reading your product in a moment.
          </div>
        </div>
      ) : (
        ordered.map((e) => {
          const isNewest = e.seq === newestSeq
          return (
            <div key={e.id} className="flex items-start gap-2.5">
              <ChatAvatar who="agent" />
              <div
                className={`max-w-[82%] rounded-2xl rounded-tl-sm border px-3.5 py-2 text-sm text-ink shadow-sm transition ${
                  isNewest ? 'border-amber/30 bg-amber/[0.06]' : 'border-black/5 bg-white'
                }`}
              >
                <div className="mb-1 flex items-center gap-2">
                  <ActorBadge actor={e.actor} />
                  <span className="text-[11px] text-slate-300">
                    {new Date(e.created_at).toLocaleTimeString([], {
                      hour: '2-digit',
                      minute: '2-digit',
                      second: '2-digit',
                    })}
                  </span>
                </div>
                {e.msg}
              </div>
            </div>
          )
        })
      )}
    </div>
  )
}

// Pay affordance — shown only when the human-pays flow has parked the build at
// 'awaiting_payment' AND a Stripe TEST checkout URL is on the run. Redirects THIS
// tab to Stripe's hosted test checkout (same-tab); once the human pays (test card
// 4242), Stripe's success_url returns to this run page and the pipeline's payment
// gate resolves so the build continues.
//
// Auth across the round-trip: the InsForge SDK keeps the session token IN MEMORY only
// (it dies on any full reload, incl. this Stripe return) — durability comes from the
// httpOnly refresh cookie PLUS a `{accessToken,user}` copy we persist in localStorage
// (see lib/insforge.ts persistSession + lib/auth.tsx rehydrate-on-load). localStorage is
// origin-scoped and survives the cross-origin redirect, a reload, AND a new tab, so the
// user stays signed in on return regardless of same-tab vs new-tab. Same-tab is still the
// nicer UX, so we keep it. Landing tokens: white surface, ink #0E1320, blue accent
// (#3B82F6). No emojis — SVG lock mark only.
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

      {/* SAME-TAB redirect (NOT target="_blank"). Session durability across the
          Stripe round-trip is handled by localStorage persistence + rehydrate-on-load
          (lib/insforge.ts / lib/auth.tsx), so the user stays signed in on return in
          either a same tab or a new tab. We keep same-tab purely for the cleaner UX;
          Stripe's success_url returns here. */}
      <a
        href={run.checkout_url ?? '#'}
        className="mt-4 flex w-full items-center justify-center gap-2 rounded-xl bg-[#3B82F6] py-3 font-semibold text-white shadow-[0_10px_30px_-10px_rgba(59,130,246,0.6)] transition hover:bg-[#2f6fe0]"
      >
        Pay {price}
        <span className="text-xs font-normal text-white/80">— test card 4242·4242·4242·4242</span>
      </a>

      <p className="mx-auto mt-2.5 max-w-md text-center text-[11px] leading-relaxed text-[#5A6472]">
        Filmo is in beta, so this is a Stripe test checkout — you won&rsquo;t actually be charged.
        Use test card <span className="font-medium text-[#0E1320]">4242 4242 4242 4242</span> with
        any future expiry, any CVC, and any name and email. You&rsquo;ll return here automatically
        after paying.
      </p>
    </div>
  )
}

// Poll the server-side demand signal so the "demand is high" note only shows when
// a real global backlog exists. Defaults to FALSE (normal) until the first fetch
// resolves, so we never claim high demand without evidence. Server route is the
// only place that can see other users' jobs (client SDK is RLS-scoped to self).
function useHighDemand(enabled: boolean): boolean {
  const [highDemand, setHighDemand] = useState(false)
  useEffect(() => {
    if (!enabled) {
      setHighDemand(false)
      return
    }
    let cancelled = false
    const check = async () => {
      try {
        const res = await fetch('/api/demand', { cache: 'no-store' })
        if (!res.ok) return
        const json = (await res.json()) as { highDemand?: boolean }
        if (!cancelled) setHighDemand(!!json.highDemand)
      } catch {
        // Fail safe: leave highDemand as-is (defaults false) — never over-claim.
      }
    }
    void check()
    const t = setInterval(check, 15000)
    return () => {
      cancelled = true
      clearInterval(t)
    }
  }, [enabled])
  return highDemand
}

export default function BuildProgress({ run, events }: { run: Run; events: RunEvent[] }) {
  const isQueued = run.status === 'queued'
  const elapsed = useElapsed(run.created_at)
  const active = activeStageIndex(run.phase)

  // Most-recent activity first; the newest line gets a highlight so motion reads.
  // Show the FULL history (scrollable) so nothing scrolls out of reach on a long run.
  const recent = [...events].filter((e) => e.actor !== 'system').sort((a, b) => b.seq - a.seq)

  // Human-pays flow: the build is parked awaiting a real Stripe TEST payment.
  const awaitingPayment = run.phase === 'awaiting_payment' && !!run.checkout_url
  // Parked awaiting payment but the checkout URL hasn't landed yet (still being created,
  // or creation failed). Show an honest interim state instead of the bare build tracker,
  // so the user isn't stranded with no Pay button. If creation truly failed, the worker
  // fails the run and the run page shows the error.
  const preparingCheckout = run.phase === 'awaiting_payment' && !run.checkout_url

  // Only consult the demand signal while we'd actually show the line (a live,
  // non-payment producing build) — no point polling otherwise.
  const showsExpectationLine = !isQueued && !awaitingPayment && !preparingCheckout
  const highDemand = useHighDemand(showsExpectationLine)

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
            : 'This can take several minutes — Filmo reads your site, plans the cut, and produces every scene. Please be patient; your video appears here automatically the moment it’s ready.'}
        </p>

        {/* Concurrent-load expectation setter — the VM renders sequentially, so under
            demand a build can sit in the queue. The "demand is high / in the queue"
            framing is shown ONLY when the server-side demand signal confirms a real
            global backlog (≥2 genuinely-active jobs); otherwise a neutral
            "Producing your video…" line that makes no queue claim. */}
        {showsExpectationLine && (
          <p className="mt-1.5 text-xs text-slate-400">
            {highDemand
              ? "Hang tight — demand is high, so your video is in the queue. Rendering usually takes a few minutes, and it'll appear here automatically the moment it's ready."
              : "Producing your video — this usually takes a few minutes, and it'll appear here automatically the moment it's ready."}
          </p>
        )}

        {/* Pay CTA — only when the human-pays flow parked the build awaiting a real
            Stripe TEST payment. Prominent, above the stage tracker. */}
        {awaitingPayment && <PayPanel run={run} />}
        {preparingCheckout && (
          <div className="mt-5 flex items-center gap-3 rounded-xl border border-[#3B82F6]/30 bg-[#F8FAFF] px-5 py-4 ring-1 ring-inset ring-[#EAF1FF]">
            <span className="text-[#3B82F6]"><Spinner /></span>
            <p className="text-sm text-[#0E1320]">
              Preparing your secure checkout… the Pay button will appear here in a moment.
            </p>
          </div>
        )}

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

        {/* Live activity — rendered as a CHAT conversation (same vocabulary as the
            editor's chat panel): the user's prompt is the first bubble, the agent's
            steps are assistant messages flowing below. Reuses run_events as-is. */}
        <div className="mt-6 border-t border-black/5 pt-5">
          <div className="mb-3 flex items-center justify-between">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-400">Conversation</h3>
            <span className="text-[11px] text-slate-300">
              {recent.length > 0 ? `${recent.length} steps · live` : 'updates every few seconds'}
            </span>
          </div>
          <BuildChat run={run} events={events} />
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
