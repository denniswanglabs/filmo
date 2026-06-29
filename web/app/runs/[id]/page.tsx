'use client'
import { useEffect, useState, useCallback, useRef } from 'react'
import Link from 'next/link'
import { useParams } from 'next/navigation'
import { insforge, resilientRead } from '../../../lib/insforge'
import { useAuth } from '../../../lib/auth'
import { TopBar, StatusChip } from '../../components/Brand'
import BuildProgress from '../../components/BuildProgress'
import SceneFilmstrip from '../../components/SceneFilmstrip'
import {
  formatCents,
  DELIVERED_STATUSES,
  type Run,
  type RunEvent,
} from '../../../lib/types'

// Terminal states stop the 3s poll loop. `completed_with_warnings` is delivered-ish
// (the run shipped a video but isolated one or more scene failures) — it must be
// terminal too, or polling never stops and the live tracker spins forever.
const TERMINAL = new Set(['delivered', 'completed_with_warnings', 'failed'])


export default function RunPage() {
  const params = useParams<{ id: string }>()
  const runId = params?.id
  const { user, loading } = useAuth()

  const [run, setRun] = useState<Run | null>(null)
  const [events, setEvents] = useState<RunEvent[]>([])
  const [notFound, setNotFound] = useState(false)
  const stopped = useRef(false)

  const poll = useCallback(async () => {
    if (!runId) return
    // Retry a transient InsForge blip (8s-timeout 408 / 5xx / network) inside a single
    // poll tick so a stuck call doesn't drop a cycle. A real 4xx returns immediately.
    const { data, error } = await resilientRead(() =>
      insforge.database.from('runs').select().eq('id', runId).maybeSingle(),
    )
    // Transient error → keep the last good state and let the next 3s tick retry; never
    // blank the view or flip a delivered run to an error on a network hiccup.
    if (error) return
    if (!data) {
      // Empty result. Only declare "not found" when we have NOTHING loaded yet — once a
      // run is on screen (esp. a delivered video), a transient empty/RLS race must never
      // erase it to "could not be found". A real deletion is vanishingly rare here.
      setRun((prev) => {
        if (!prev) setNotFound(true)
        return prev
      })
      return
    }
    const r = data as Run
    setRun(r)

    const { data: ev } = await resilientRead(() =>
      insforge.database
        .from('run_events')
        .select()
        .eq('run_id', runId)
        .order('seq', { ascending: true }),
    )
    if (ev) setEvents(ev as RunEvent[])

    // A terminal build normally stops polling — but an editor Export enqueues a
    // `rerender` job that produces runs.edited_url AFTER the run is already
    // 'delivered'. So keep polling while a rerender is queued/claimed, so the new
    // "Edited" cut appears without a manual refresh.
    let rerenderInFlight = false
    if (TERMINAL.has(r.status)) {
      const { data: jobs } = await resilientRead(() =>
        insforge.database
          .from('jobs')
          .select('id, type, status')
          .eq('run_id', runId)
          .eq('type', 'rerender')
          .in('status', ['queued', 'claimed']),
      )
      rerenderInFlight = !!(jobs && jobs.length > 0)
    }
    stopped.current = TERMINAL.has(r.status) && !rerenderInFlight
  }, [runId])

  useEffect(() => {
    if (loading || !user || !runId) return
    stopped.current = false
    void poll()
    const t = setInterval(() => {
      if (stopped.current) return
      void poll()
    }, 3000)
    return () => clearInterval(t)
  }, [loading, user, runId, poll])

  if (loading) {
    return <div className="flex min-h-screen items-center justify-center text-slate-400">Loading…</div>
  }

  // Logged-out gate. The run fetch is RLS-scoped to the signed-in owner, so when
  // there's no session the poll never runs (it bails on !user) and the view would
  // otherwise sit on "Loading run…" forever. Mirror the editor's sign-in gate —
  // a short message + a link to /login — instead of a dead spinner.
  if (!user) {
    return (
      <>
        <TopBar />
        <main className="mx-auto max-w-3xl px-5 pb-24 pt-8">
          <Link href="/" className="text-sm text-slate-400 transition hover:text-ink">
            ← All builds
          </Link>
          <div className="mt-10">
            <p className="text-slate-500">Please sign in to view this video.</p>
            <Link
              href="/login"
              className="mt-4 inline-flex items-center justify-center rounded-lg bg-[#3B82F6] px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-[#2f6fe0]"
            >
              Sign in
            </Link>
          </div>
        </main>
      </>
    )
  }

  return (
    <>
      <TopBar />
      <main className="mx-auto max-w-3xl px-5 pb-24 pt-8">
        <Link href="/" className="text-sm text-slate-400 transition hover:text-ink">
          ← All builds
        </Link>

        {notFound ? (
          <p className="mt-10 text-slate-500">This run could not be found.</p>
        ) : !run ? (
          <p className="mt-10 text-slate-400">Loading run…</p>
        ) : (
          <div className="mt-5">
            {/* Header */}
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <h1 className="truncate text-2xl font-semibold tracking-tight text-ink">
                  {run.brand || run.company_url}
                </h1>
                <p className="mt-1 text-slate-500">{run.goal || 'Brand video'}</p>
              </div>
              <StatusChip status={run.status} />
            </div>

            {/* Sponsor credit chip. HONEST: only claim Hermes when this run was
                actually Hermes-conducted (props.producer === 'hetzner-hermes').
                The deterministic fallback ('hetzner-curated') and any
                unknown/missing producer get a neutral "Produced by Filmo". */}
            <CreditBadge producer={readProducer(run.props)} />

            {/* Live / delivered surface */}
            {DELIVERED_STATUSES.has(run.status) && run.final_url ? (
              <>
                {/* The video shipped, but the orchestrator isolated one or more scene
                    failures. Surface it as a non-blocking note — the video below is real. */}
                {run.status === 'completed_with_warnings' ? (
                  <div className="mt-6 flex items-start gap-2.5 rounded-xl border border-amber/30 bg-amber/[0.06] px-4 py-3">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true" className="mt-0.5 shrink-0 text-amber">
                      <path d="M12 9v4m0 4h.01M10.3 3.86l-8 13.86A2 2 0 004 21h16a2 2 0 001.7-3.28l-8-13.86a2 2 0 00-3.4 0z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                    <p className="text-sm text-ink">
                      <span className="font-semibold">Completed with warnings.</span>{' '}
                      Your video shipped, but one or more scenes were skipped during production.
                    </p>
                  </div>
                ) : null}

                {/* Edited cut (from an editor Export → re-render), shown FIRST when present */}
                {run.edited_url ? (
                  <div className="mt-6">
                    <div className="mb-2 flex items-center gap-2">
                      <span className="rounded-md bg-[#3B82F6]/10 px-2 py-0.5 text-xs font-semibold uppercase tracking-wide text-[#3B82F6]">
                        Edited
                      </span>
                      <span className="text-xs text-slate-400">Your re-rendered cut</span>
                    </div>
                    <div className="overflow-hidden rounded-2xl border border-[#3B82F6]/20 bg-black shadow-lg">
                      <video
                        key={run.edited_url}
                        controls
                        playsInline
                        src={run.edited_url}
                        className="aspect-video w-full bg-black"
                      />
                    </div>
                  </div>
                ) : null}

                <div className="mt-6">
                  {run.edited_url ? (
                    <div className="mb-2 flex items-center gap-2">
                      <span className="rounded-md bg-slate-100 px-2 py-0.5 text-xs font-semibold uppercase tracking-wide text-slate-500">
                        Original
                      </span>
                      <span className="text-xs text-slate-400">The first delivered cut</span>
                    </div>
                  ) : null}
                  <div className="overflow-hidden rounded-2xl border border-black/5 bg-black shadow-lg">
                    <video
                      key={run.final_url}
                      controls
                      playsInline
                      src={run.final_url}
                      className="aspect-video w-full bg-black"
                    />
                  </div>
                </div>

                {/* The full delivered filmstrip — every scene's real thumbnail,
                    rendered from props.scene_thumbs so a finished run still shows
                    the scene-by-scene breakdown beneath the player. */}
                <SceneFilmstrip run={run} events={events} />

                <div className="mt-3 flex justify-end gap-2.5">
                  <a
                    href={`/api/runs/${runId}/download`}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-black/10 bg-white px-4 py-2 text-sm font-semibold text-ink shadow-sm transition hover:bg-black/[0.03]"
                  >
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                      <path d="M12 4v11m0 0l-4-4m4 4l4-4M5 19h14" stroke="currentColor" strokeWidth="2.1" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                    Download
                  </a>
                  <Link
                    href={`/runs/${runId}/edit`}
                    className="inline-flex items-center gap-1.5 rounded-lg bg-[#3B82F6] px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-[#2f6fe0]"
                  >
                    Edit video
                  </Link>
                </div>
              </>
            ) : DELIVERED_STATUSES.has(run.status) && !run.final_url ? (
              // Delivered-ish but no video URL = the render finished but the upload didn't
              // land. Don't show the live "Producing" tracker forever — surface it
              // honestly with a way to retry.
              <div className="mt-6 rounded-2xl border border-amber/30 bg-amber/[0.06] px-5 py-8 text-center">
                <p className="font-medium text-ink">The video finished, but the upload didn’t complete.</p>
                <p className="mt-1 text-sm text-slate-500">
                  This is usually a transient storage hiccup. Starting a fresh build almost always fixes it.
                </p>
                <Link
                  href="/"
                  className="mt-4 inline-flex items-center justify-center rounded-lg bg-amber px-4 py-2 text-sm font-semibold text-white transition hover:opacity-90"
                >
                  Start a new build
                </Link>
              </div>
            ) : run.status === 'failed' ? (
              <div className="mt-6 rounded-2xl border border-red-100 bg-red-50 px-5 py-8 text-center">
                <p className="font-medium text-red-700">This build failed.</p>
                {run.phase && <p className="mt-1 text-sm text-red-500">Last phase: {run.phase}</p>}
              </div>
            ) : (
              <>
                {/* Live scene-production filmstrip — the headline of a producing run.
                    Consumes the FILMSTRIP contract (props.scenes / props.scene_thumbs +
                    storyboard/scene_done run_events). Renders nothing until the agent
                    has decided the storyboard, so an early run shows just BuildProgress. */}
                <SceneFilmstrip run={run} events={events} />
                <BuildProgress run={run} events={events} />
              </>
            )}

            {/* Price — the single customer-facing fact on the delivered view. Quality,
                COGS and Margin were removed here; the owner's full P&L lives on Analytics. */}
            <div className="mt-6 max-w-[220px]">
              <Stat label="Price" value={formatCents(run.price_cents)} />
            </div>

            {/* Activity feed — full log. Only shown once the run reaches a terminal
                state; during a build the live feed in BuildProgress covers this, so
                we don't double-render two activity lists. */}
            {TERMINAL.has(run.status) && (
              <section className="mt-8">
                <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-400">
                  Activity
                </h2>
                {events.length === 0 ? (
                  <p className="text-sm text-slate-400">No events yet.</p>
                ) : (
                  <ul className="space-y-1.5">
                    {events.map((e) => (
                      <li
                        key={e.id}
                        className="flex items-start gap-3 rounded-lg border border-black/5 bg-white px-3.5 py-2.5"
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
              </section>
            )}
          </div>
        )}
      </main>
    </>
  )
}

// Pull the producer tag out of the run's props blob. Returns the raw string when
// present (e.g. 'hetzner-hermes' / 'hetzner-curated') or null. The badge decides
// what to claim — this only reads.
function readProducer(props: unknown): string | null {
  if (!props || typeof props !== 'object') return null
  const p = (props as Record<string, unknown>).producer
  return typeof p === 'string' && p ? p : null
}

// A small, honest sponsor-credit chip shown near the run header. We ONLY claim
// "Conducted by Hermes" when the run genuinely ran through the Hermes harness
// ('hetzner-hermes'). The deterministic curated fallback ('hetzner-curated') and
// any unknown/missing producer fall back to a neutral "Produced by Filmo" — no
// Hermes claim, no Nemotron claim. The Nemotron tier (120B/550B) is deliberately
// not stated. Stripe is intentionally omitted (not wired into the live flow yet).
function CreditBadge({ producer }: { producer: string | null }) {
  const isHermes = producer === 'hetzner-hermes'
  return (
    <div className="mt-3">
      <span className="inline-flex max-w-full flex-wrap items-center gap-x-1.5 gap-y-1 rounded-full border border-black/5 bg-white px-3 py-1 text-[11px] font-medium text-slate-500 shadow-sm">
        <svg
          width="12"
          height="12"
          viewBox="0 0 24 24"
          fill="none"
          aria-hidden="true"
          className={`shrink-0 ${isHermes ? 'text-amber' : 'text-slate-400'}`}
        >
          <path
            d="M12 2l2.4 5.5L20 8.2l-4 4 1 5.8-5-2.9-5 2.9 1-5.8-4-4 5.6-.7L12 2z"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinejoin="round"
          />
        </svg>
        {isHermes ? (
          <>
            <span className="text-ink">Conducted by Hermes</span>
            <span aria-hidden="true" className="text-slate-300">·</span>
            <span>NVIDIA Nemotron</span>
            <span aria-hidden="true" className="text-slate-300">·</span>
            <span>sealed in NemoClaw</span>
          </>
        ) : (
          <span className="text-ink">Produced by Filmo</span>
        )}
      </span>
    </div>
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
