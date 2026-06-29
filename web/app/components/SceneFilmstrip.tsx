'use client'
import { useMemo, useState } from 'react'
import type { Run, RunEvent } from '../../lib/types'

/**
 * Live scene-production filmstrip — the demo showpiece.
 *
 * Renders a strip of scene cards that animate pending → rendering → done with the
 * real per-scene thumbnails the agent produces, driven by the FILMSTRIP contract
 * the pipeline already ships (see agent-host/vm/mcp_toolserver.py):
 *
 *   - runs.props.scenes       = [{index,type,label,headline}]  (durable: planned scenes)
 *   - runs.props.scene_thumbs = {"0":"<url>", ...}             (durable: index→thumbnail)
 *   - run_events level="storyboard"  payload {event,count,scenes:[...]}  (live: the plan)
 *   - run_events level="scene_done"  payload {index,...,thumbnail_url,status:"done"} (live)
 *   - msg = "<human text> ::FILMSTRIP:: <json>" — split on the literal sentinel.
 *
 * We JOIN on the 0-based scene `index` (NOT type — storyboard `type` is the plan
 * type, scene_done `type` is the rendered archetype). The "rendering" card has no
 * explicit start event, so we infer it: the FIRST not-yet-done card after the done
 * run — exactly one card pulses at a time.
 *
 * Durable props are the floor (so a freshly-loaded or delivered run shows the strip
 * immediately); live events layer on top so updates land without waiting for a poll
 * to re-read props. On-brand with the light Filmo theme — no emojis, SVG marks only.
 */

const FILMSTRIP_MARK = ' ::FILMSTRIP:: '

type PlannedScene = {
  index: number
  type: string
  label: string
  headline: string
}

type SceneState = 'pending' | 'rendering' | 'done'

type FilmstripCard = PlannedScene & {
  state: SceneState
  thumbnailUrl: string | null
}

// ---- contract parsing -------------------------------------------------------

function parseFilmstripTail(msg: string): unknown | null {
  const i = msg.indexOf(FILMSTRIP_MARK)
  if (i === -1) return null
  const tail = msg.slice(i + FILMSTRIP_MARK.length)
  try {
    return JSON.parse(tail)
  } catch {
    return null
  }
}

function asPlannedScene(raw: unknown): PlannedScene | null {
  if (!raw || typeof raw !== 'object') return null
  const r = raw as Record<string, unknown>
  if (typeof r.index !== 'number') return null
  return {
    index: r.index,
    type: typeof r.type === 'string' ? r.type : '',
    label: typeof r.label === 'string' && r.label ? r.label : 'Scene',
    headline: typeof r.headline === 'string' ? r.headline : '',
  }
}

function readProps(run: Run): {
  scenes: PlannedScene[]
  thumbs: Record<number, string>
} {
  const props = (run.props ?? {}) as Record<string, unknown>
  const scenes: PlannedScene[] = []
  if (Array.isArray(props.scenes)) {
    for (const s of props.scenes) {
      const p = asPlannedScene(s)
      if (p) scenes.push(p)
    }
  }
  const thumbs: Record<number, string> = {}
  const st = props.scene_thumbs
  if (st && typeof st === 'object') {
    for (const [k, v] of Object.entries(st as Record<string, unknown>)) {
      const idx = Number(k)
      if (Number.isInteger(idx) && typeof v === 'string' && v) thumbs[idx] = v
    }
  }
  return { scenes, thumbs }
}

// Build the card list from durable props (floor) + live events (overlay).
function buildCards(run: Run, events: RunEvent[]): FilmstripCard[] {
  const { scenes: propScenes, thumbs: propThumbs } = readProps(run)

  // Index → planned scene. Start from durable props, then let a live storyboard
  // event fill in / correct it (the plan can refine between the props write and
  // the storyboard event, e.g. headline wording).
  const planned = new Map<number, PlannedScene>()
  for (const s of propScenes) planned.set(s.index, s)

  // Index → done thumbnail. Durable map first; live scene_done events override
  // (and add scenes done since the last props read). thumbnail_url may be null —
  // we still record that the scene is DONE.
  const thumbs = new Map<number, string>()
  for (const [idx, url] of Object.entries(propThumbs)) thumbs.set(Number(idx), url)
  const doneIdx = new Set<number>(thumbs.keys())

  for (const e of events) {
    if (e.level !== 'storyboard' && e.level !== 'scene_done') continue
    const payload = parseFilmstripTail(e.msg)
    if (!payload || typeof payload !== 'object') continue
    const p = payload as Record<string, unknown>

    if (e.level === 'storyboard' && Array.isArray(p.scenes)) {
      for (const raw of p.scenes) {
        const ps = asPlannedScene(raw)
        if (ps) planned.set(ps.index, ps)
      }
    } else if (e.level === 'scene_done' && typeof p.index === 'number') {
      const idx = p.index
      doneIdx.add(idx)
      if (typeof p.thumbnail_url === 'string' && p.thumbnail_url) {
        thumbs.set(idx, p.thumbnail_url)
      }
      // A scene_done can arrive for an index the plan list missed — backfill a
      // minimal planned entry from the event so the card still renders.
      if (!planned.has(idx)) {
        const ps = asPlannedScene(p)
        if (ps) planned.set(idx, ps)
      }
    }
  }

  if (planned.size === 0) return []

  const indices = [...planned.keys()].sort((a, b) => a - b)

  // The "rendering" card: there's no explicit scene_start event, so infer it as
  // the FIRST not-yet-done card. Exactly one card renders at a time; once every
  // card is done, none render (delivered).
  const firstNotDone = indices.find((i) => !doneIdx.has(i))
  const isLive = run.status === 'running' || run.status === 'queued'

  return indices.map((i) => {
    const base = planned.get(i)!
    const done = doneIdx.has(i)
    // Only show a pulsing "rendering" card while the run is still live. On a
    // delivered run every card should read done/pending statically.
    const rendering = !done && i === firstNotDone && isLive
    const state: SceneState = done ? 'done' : rendering ? 'rendering' : 'pending'
    return { ...base, state, thumbnailUrl: thumbs.get(i) ?? null }
  })
}

// ---- icons ------------------------------------------------------------------

function ClockIcon() {
  return (
    <svg viewBox="0 0 20 20" className="h-3.5 w-3.5" aria-hidden>
      <circle cx="10" cy="10" r="7" fill="none" stroke="currentColor" strokeWidth="1.6" />
      <path d="M10 6v4l2.5 2" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function CheckIcon() {
  return (
    <svg viewBox="0 0 20 20" className="h-3.5 w-3.5" aria-hidden>
      <path d="M5 10.5l3 3 7-7" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function SpinnerIcon({ className = 'h-3.5 w-3.5' }: { className?: string }) {
  return (
    <svg viewBox="0 0 20 20" className={`${className} animate-spin`} aria-hidden>
      <circle cx="10" cy="10" r="7" fill="none" stroke="currentColor" strokeOpacity="0.25" strokeWidth="2.4" />
      <path d="M10 3a7 7 0 0 1 7 7" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" />
    </svg>
  )
}

// A faint scene-type glyph shown behind a pending/rendering preview so the card
// reads as a real shot-in-waiting (never an empty void).
function SceneGlyph({ type }: { type: string }) {
  const t = (type || '').toLowerCase()
  if (t.includes('title')) {
    return (
      <svg viewBox="0 0 48 48" className="h-9 w-9" aria-hidden>
        <path d="M12 18h24M12 26h16" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" />
      </svg>
    )
  }
  if (t.includes('screenshot') || t.includes('walkthrough')) {
    return (
      <svg viewBox="0 0 48 48" className="h-9 w-9" aria-hidden>
        <rect x="9" y="11" width="30" height="22" rx="2.4" fill="none" stroke="currentColor" strokeWidth="2.2" />
        <path d="M9 17h30" stroke="currentColor" strokeWidth="2.2" />
        <circle cx="13" cy="14" r="1" fill="currentColor" />
      </svg>
    )
  }
  // motion_graphic / stat / mosaic / default
  return (
    <svg viewBox="0 0 48 48" className="h-9 w-9" aria-hidden>
      <rect x="10" y="10" width="28" height="28" rx="2.6" fill="none" stroke="currentColor" strokeWidth="2.2" />
      <path d="M16 30l5-7 4 4 7-10" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

// ---- card -------------------------------------------------------------------

function pad2(n: number): string {
  return String(n + 1).padStart(2, '0')
}

function SceneCard({ card }: { card: FilmstripCard }) {
  const { state, label, headline, thumbnailUrl, index, type } = card

  const ring =
    state === 'rendering'
      ? 'border-2 border-amber shadow-[0_0_0_3px_rgba(59,130,246,0.12)]'
      : state === 'done'
        ? 'border border-nemo/30'
        : 'border border-black/5'

  return (
    <div
      className={`flex w-[180px] shrink-0 flex-col overflow-hidden rounded-xl bg-white transition sm:w-auto ${ring}`}
      title={headline || label}
    >
      {/* 16:9 preview area */}
      <div className="relative aspect-video w-full overflow-hidden bg-slate-50">
        {state === 'done' && thumbnailUrl ? (
          // Real per-scene thumbnail. Plain <img> (the InsForge URL 302-redirects
          // to a presigned object; native <img> follows it). Established pattern
          // here — next/image is avoided for remote/redirecting sources.
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={thumbnailUrl}
            alt={`Scene ${pad2(index)} — ${label}`}
            loading="lazy"
            className="h-full w-full object-cover"
          />
        ) : state === 'rendering' ? (
          <>
            {/* pulsing skeleton */}
            <div className="absolute inset-0 animate-pulse bg-gradient-to-br from-amber/10 via-slate-100 to-amber/5" />
            <div className="absolute inset-0 flex items-center justify-center text-amber/40">
              <SceneGlyph type={type} />
            </div>
            <div className="absolute right-2 top-2 flex h-6 w-6 items-center justify-center rounded-full bg-white/90 text-amber shadow-sm">
              <SpinnerIcon className="h-3 w-3" />
            </div>
          </>
        ) : (
          // pending (or done with a null thumbnail) — dim ghost glyph
          <div className="absolute inset-0 flex items-center justify-center text-slate-300">
            <SceneGlyph type={type} />
          </div>
        )}
      </div>

      {/* footer: NN · label · state icon */}
      <div className="flex items-center gap-1.5 px-2.5 py-2">
        <span className="font-mono text-[11px] tabular-nums text-slate-400">{pad2(index)}</span>
        <span className="truncate text-xs font-medium text-ink">{label}</span>
        <span
          className={`ml-auto shrink-0 ${
            state === 'done' ? 'text-nemo' : state === 'rendering' ? 'text-amber' : 'text-slate-300'
          }`}
          aria-label={state}
        >
          {state === 'done' ? <CheckIcon /> : state === 'rendering' ? <SpinnerIcon /> : <ClockIcon />}
        </span>
      </div>
    </div>
  )
}

// ---- filmstrip --------------------------------------------------------------

export default function SceneFilmstrip({
  run,
  events,
}: {
  run: Run
  events: RunEvent[]
}) {
  const cards = useMemo(() => buildCards(run, events), [run, events])

  // Lightbox for a clicked done thumbnail (review a finished scene full-size).
  const [zoom, setZoom] = useState<FilmstripCard | null>(null)

  if (cards.length === 0) return null

  const total = cards.length
  const doneCount = cards.filter((c) => c.state === 'done').length
  const allDone = doneCount === total
  const pct = total > 0 ? Math.round((doneCount / total) * 100) : 0

  return (
    <section className="mt-6 overflow-hidden rounded-2xl border border-black/5 bg-white shadow-sm">
      {/* header */}
      <div className="flex flex-wrap items-center justify-between gap-2 px-5 pt-5">
        <div className="flex items-center gap-2.5">
          {allDone ? (
            <span className="flex h-6 w-6 items-center justify-center rounded-full bg-nemo/10 text-nemo">
              <CheckIcon />
            </span>
          ) : (
            <span className="text-amber">
              <SpinnerIcon className="h-4 w-4" />
            </span>
          )}
          <h3 className="font-medium text-ink">
            {allDone ? 'Your scenes' : 'Producing your video'}
          </h3>
        </div>
        <span className="rounded-full bg-slate-50 px-2.5 py-1 text-xs font-medium tabular-nums text-slate-500">
          {allDone ? `${total} scenes` : `Scene ${Math.min(doneCount + 1, total)} of ${total}`}
        </span>
      </div>

      {/* thin progress bar */}
      <div className="mt-3 px-5">
        <div className="h-1 w-full overflow-hidden rounded-full bg-amber/10">
          <div
            className="h-full rounded-full bg-amber transition-[width] duration-500 ease-out"
            style={{ width: `${pct}%` }}
          />
        </div>
      </div>

      {/* filmstrip — horizontal scroll on mobile, responsive grid above sm */}
      <div className="mt-4 px-5 pb-5">
        <div className="flex gap-3 overflow-x-auto pb-1 [scrollbar-width:thin] sm:grid sm:grid-cols-3 sm:overflow-visible lg:grid-cols-4">
          {cards.map((c) =>
            c.state === 'done' && c.thumbnailUrl ? (
              <button
                key={c.index}
                type="button"
                onClick={() => setZoom(c)}
                className="cursor-zoom-in text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-amber/40 sm:contents"
              >
                <SceneCard card={c} />
              </button>
            ) : (
              <SceneCard key={c.index} card={c} />
            )
          )}
        </div>
      </div>

      {/* lightbox */}
      {zoom && zoom.thumbnailUrl ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-6"
          onClick={() => setZoom(null)}
          role="dialog"
          aria-modal="true"
        >
          <div className="max-w-3xl" onClick={(e) => e.stopPropagation()}>
            <div className="overflow-hidden rounded-2xl border border-white/10 bg-black shadow-2xl">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={zoom.thumbnailUrl}
                alt={`Scene ${pad2(zoom.index)} — ${zoom.label}`}
                className="aspect-video w-full object-contain"
              />
            </div>
            <div className="mt-2 flex items-center justify-between gap-3 text-sm text-white/80">
              <span>
                <span className="font-mono tabular-nums text-white/50">{pad2(zoom.index)}</span>{' '}
                <span className="font-medium text-white">{zoom.label}</span>
                {zoom.headline ? <span className="text-white/60"> · {zoom.headline}</span> : null}
              </span>
              <button
                type="button"
                onClick={() => setZoom(null)}
                className="rounded-lg border border-white/20 px-3 py-1 text-white/80 transition hover:bg-white/10"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </section>
  )
}
