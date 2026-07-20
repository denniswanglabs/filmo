'use client'
// Walkrec beta workspace — the Ploy-shaped page: ONE white canvas in browser
// chrome where everything happens (page reads, the live recording, the beats,
// the film), and ONE timeline rail on the left merging conversation + work
// updates chronologically. Direct React port of the validated local viewer;
// same event contract, agent_events + storage instead of localhost.
import { useCallback, useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { getAgentRun, listMyRuns, sendDirectorMessage, type AgentEvent } from '../../actions'
// ONE status chip for the whole product: the Builds tiles wear the same chip as
// the /videos cards, so a status can never mean two different things in two
// places (STATUS_STYLES/STATUS_LABELS stay the single source of truth).
import { StatusChip } from '../../components/Brand'
import NewFilmComposer from './NewFilmComposer'
import FeedbackModal from './FeedbackModal'

const VERBS: Record<string, string> = {
  read: 'Scouting', decide: 'Framing', film: 'Rolling',
  design: 'Cutting', assemble: 'Printing', review: 'Grading',
}
function md(text: string) {
  // Ploy-grammar light markdown: **bold leads**, keep everything else plain.
  const esc = text.replace(/&/g, '&amp;').replace(/</g, '&lt;')
  return esc.replace(/\*\*(.+?)\*\*/g, '<b>$1</b>')
}

// A KIND THIS SET DOESN'T KNOW RENDERS AS NOTHING. The thread is allow-listed,
// which is right — a new internal event should not leak into a customer's
// timeline unreviewed — but it means a genuinely customer-facing outcome that
// nobody adds here is emitted, stored, polled, and then silently dropped on the
// floor. `review.reject` is the reviewer's honest verdict when a finding
// survives its re-cut, and it is exactly as customer-visible as `review.pass`;
// it sits beside it, and like it renders as a work receipt rather than prose.
const THREAD_KINDS = new Set([
  'run.start', 'read.page', 'read.quotes', 'decide.plan', 'decide.guard',
  'film.recording', 'film.shot', 'film.failed', 'design.beat', 'review.lint',
  'review.finding', 'review.pass', 'review.reject', 'review.apply', 'review.done',
  'assemble.film', 'run.error', 'chat.user', 'chat.director', 'say.step',
])

// VOICE: the agent SPEAKS in prose (always visible, full sentences) and
// leaves work RECEIPTS (collapsed, verb + result). A thread of nothing but
// receipts reads as a log; a thread of nothing but prose hides the work.
const PROSE_KINDS = new Set(['chat.director', 'say.step'])

// ── A LIBRARY ROW MUST DISCRIMINATE ─────────────────────────────────────────
// Presence of a label is not the same as usefulness of a label. Thirteen of a
// user's fourteen films can be the same brand, and a bucket-per-day stamp
// ("Updated today") collapses every one of them onto the same two strings —
// the row renders and is still unfindable. Every field a Builds tile carries is
// therefore chosen to VARY between neighbouring rows: a precise age, the
// pipeline that made it, its measured length, its status. `relativeAge` is the
// same clock the /videos cards use, so one film reads the same in both places.
function relativeAge(ts: number): string {
  const mins = Math.round((Date.now() - ts * 1000) / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.round(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  const days = Math.round(hrs / 24)
  if (days < 7) return `${days}d ago`
  return new Date(ts * 1000).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

// Same words the /videos cards use for the two pipelines.
const filmModeLabel = (mode: string) =>
  mode === 'walkrec' ? 'Agent tour' : 'Brand explainer'

// The film's own measured length, read off the tile's metadata load — never a
// guess. Unknown/streaming durations return '' and the row simply omits the
// field rather than printing a made-up number.
function runtime(secs: number | undefined): string {
  if (!secs || !isFinite(secs) || secs <= 0) return ''
  const s = Math.round(secs)
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, '0')}s`
}

// ── FILMO'S OWN MARK ────────────────────────────────────────────────────────
// The canonical path lives here ONCE so no surface can drift into an
// approximation of it, and so nothing run-derived has a way into the chrome
// that wears it.
function FilmoMark({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="14 13 56 56" aria-hidden>
      <path fillRule="evenodd" fill="#3B82F6"
        d="M42 17 C56 15 67 27 65 41 C63 55 52 67 38 65 C25 63 16 51 19 37 C21 25 30 19 42 17 Z M47 28.5 A8.5 8.5 0 1 1 47 45.5 A8.5 8.5 0 1 1 47 28.5 Z" />
    </svg>
  )
}

// ── POSTER INVARIANT ────────────────────────────────────────────────────────
// A film on this surface NEVER occupies the layout as an empty box. Every
// <video> here is rendered through this ONE component, and both of its props
// are required, so no caller can add a film without saying what frame it opens
// on: it hangs the still the run already produced (beat 1's frame — same-origin
// proxied like every other artifact) on the element, and decides the fallback
// from what the video is FOR. A tile is a thumbnail nobody plays, so a missing
// still is covered by seeking the file to 2s; a player is meant to be watched
// from the beginning, so it never carries a fragment that would skip the
// film's opening — a second of black beats starting the film two seconds in.
function FilmVideo({ src, poster, role, controls, videoRef, onTimeUpdate, onLoadedMetadata }: {
  src: string
  /** A still already produced for this film, or '' when none is in hand. */
  poster: string
  role: 'player' | 'tile'
  controls?: boolean
  videoRef?: React.Ref<HTMLVideoElement>
  onTimeUpdate?: React.ReactEventHandler<HTMLVideoElement>
  onLoadedMetadata?: React.ReactEventHandler<HTMLVideoElement>
}) {
  return (
    <video
      ref={videoRef}
      src={!poster && role === 'tile' ? `${src}#t=2` : src}
      poster={poster || undefined}
      preload="metadata"
      muted
      playsInline
      controls={controls}
      onTimeUpdate={onTimeUpdate}
      onLoadedMetadata={onLoadedMetadata}
    />
  )
}

type LocalMsg = { ts: number; kind: 'user' | 'dir'; text: string }

// ── THE RAIL SWITCHES SURFACES; IT DOES NOT LEAVE ───────────────────────────
// Every destination on the icon rail is one of these, and they are all rendered
// by this component — so no rail entry can be a link out of the studio. It used
// to have one: `Builds` was <a href="/">, which walked the user out of the app
// they were working in and dropped them on the marketing landing, mid-film.
// A studio surface is now a value, not a URL, and the type is what enforces it.
//   'film'   the run this workspace is about.
//   'builds' the library — every film this account has finished.
//   'new'    the composer. Takes the whole stage: the rail is fixed furniture,
//            the room you're standing in is what changes.
// Feedback is deliberately NOT here. It is an ACT, not a place — it opens over
// whatever you were looking at and gives it back when you're done.
type Surface = 'film' | 'builds' | 'new'

function reduce(evts: AgentEvent[]) {
  const S = {
    pages: [] as AgentEvent[], plan: [] as string[], beats: [] as AgentEvent[],
    review: [] as AgentEvent[], film: '', filmSeq: 0, phase: 'read',
    roundResetAt: 0,
    status: '', lastTitle: '', site: '', done: false, logo: '', poster: '',
    // A VERDICT IS NOT A COUNT. `review` collects the events that entitle this
    // surface to say the film passed — but `review.done` lands in it whatever
    // the reviewer concluded, so once the reviewer could genuinely FAIL, a
    // length check alone would stamp "review passed" on a film it had just
    // rejected. The reject is tracked on its own, and it is what the label
    // reads from; presence of a review is not evidence of a good one.
    rejected: false,
  }
  for (const e of evts) {
    const k = e.kind
    if (k === 'run.start') {
      // Titles: "Opening https://x" (hosted) or "... for https://x" (local).
      const m = e.title.match(/(https?:\/\/\S+)/)
      if (m) S.site = m[1]
      S.done = false
    }
    if (!S.site && k === 'read.page') {
      const m = e.title.match(/(https?:\/\/\S+)/)
      if (m) S.site = m[1]
    }
    if (k === 'read.page') { S.pages.push(e); S.phase = 'read' }
    if (k === 'brand.logo' && e.artifact_url) S.logo = e.artifact_url
    if (k === 'decide.plan') { S.plan = e.detail.split('\n'); S.phase = 'decide' }
    if (k.startsWith('film.')) S.phase = 'film'
    if (k === 'assemble.render') { S.roundResetAt = e.seq }
    if (k === 'design.beat' && e.artifact_url) {
      // A new render round replaces the WHOLE beat set — without this, a
      // dropped beat's stale segment survives at the strip's tail.
      if (S.roundResetAt && e.seq > S.roundResetAt
          && S.beats.some((b) => b.seq <= S.roundResetAt)) {
        S.beats = S.beats.filter((b) => b.seq > S.roundResetAt)
      }
      // A review round re-emits its beats — REPLACE by beat index (the
      // title carries "Beat N:") so the timeline strip never shows a
      // mixed set of superseded and current beats.
      const m = e.title.match(/^Beat (\d+):/)
      const idx = m ? parseInt(m[1], 10) : S.beats.length + 1
      const at = S.beats.findIndex((b) => (b.title.match(/^Beat (\d+):/) || [])[1] === String(idx))
      if (at >= 0) S.beats[at] = e
      else S.beats.push(e)
      S.phase = 'design'
    }
    if (k === 'assemble.render') S.phase = 'assemble'
    if (k.startsWith('review.')) S.phase = 'review'
    if (k === 'assemble.film') { S.film = e.artifact_url; S.filmSeq = e.seq }
    if (k === 'review.pass' || k === 'review.done') S.review.push(e)
    if (k === 'review.reject') S.rejected = true
    if (k === 'run.done') { S.phase = 'done'; S.status = 'finished'; S.done = true }
    if (k === 'run.error') { S.phase = 'done'; S.status = 'failed'; S.done = true }
    S.lastTitle = e.title
  }
  // The film's own opening frame. Beat 1's still IS the poster for the film it
  // opens; any still we hold is better than a black box, so fall back to the
  // earliest one rather than leaving the player bare.
  const opener = S.beats.find((b) => /^Beat 1\b/.test(b.title)) || S.beats[0]
  S.poster = opener?.artifact_url || ''
  return S
}

// ── ONE WORKSPACE, ONE RUN ──────────────────────────────────────────────────
// Everything below this line — the event log, the reduced phase, the poll
// cursor, the film URL, the library, the thread — describes ONE run, and the
// only thing that says which run is `runKey`. Until now nothing could change it
// mid-life: the library's tiles are plain <a href> tags, so opening another
// film was a full page load and the whole component was rebuilt from nothing.
// The composer added the first CLIENT-side route between two runs
// (router.push('/runs/…')), and a client route keeps the instance alive: the
// poll would re-aim at the new run while the previous run's events, poster and
// beat board stayed on screen underneath, appending rather than replacing.
//
// The fix is identity, not cleanup. A reset effect would have to list every
// piece of state and would rot the day someone adds a useState and forgets;
// keying on the run makes React tear the instance down and build a new one, so
// state that belongs to a run cannot outlive it BY CONSTRUCTION. New state can
// be added below freely — it inherits the guarantee.
export default function Workspace(props: {
  runKey: string; getToken: () => Promise<string | null>
}) {
  return <WorkspaceRun key={props.runKey} {...props} />
}

function WorkspaceRun({ runKey, getToken }: {
  runKey: string; getToken: () => Promise<string | null>
}) {
  const [evts, setEvts] = useState<AgentEvent[]>([])
  const [liveUrl, setLiveUrl] = useState('')
  const [liveFresh, setLiveFresh] = useState(false)
  const [liveTick, setLiveTick] = useState(0)
  const [queueAhead, setQueueAhead] = useState<number | null>(null)
  const [filmUrl, setFilmUrl] = useState('')
  const [runStatus, setRunStatus] = useState('')
  const [localMsgs, setLocalMsgs] = useState<LocalMsg[]>([])
  const [input, setInput] = useState('')
  const [pinned, setPinned] = useState<AgentEvent | null>(null)
  const [tab, setTab] = useState<Surface>('film')
  // Feedback is an act, not a surface: it opens OVER whatever the rail is
  // showing and hands that view back untouched when it closes, so reporting a
  // broken screen never costs you the screen you were reporting.
  const [fbOpen, setFbOpen] = useState(false)
  // The films this account has already produced — the library behind the
  // Builds tab. Loaded once, lazily, when the tab is first opened. Every field
  // here is one the row renders; a library row that carries only the brand is
  // unfindable once the same brand has been filmed a dozen times.
  const [library, setLibrary] = useState<{
    id: string; brand: string; url: string; ts: number; status: string; mode: string
  }[] | null>(null)
  // Measured film lengths, keyed by run id — read off each tile's own metadata
  // load (the tiles already fetch it to paint a frame), so the most
  // discriminating field on the row costs no extra request and no server field.
  const [durations, setDurations] = useState<Record<string, number>>({})
  const [openWork, setOpenWork] = useState<Record<number, boolean>>({})
  const [pending, setPending] = useState(false)
  // ── UNKNOWN IS NOT "STARTING" ──────────────────────────────────────────────
  // Has the server told us anything about this run yet? Every element that
  // asserts run state (the status pill, the canvas, the thread's tail step and
  // its timer, the run header's sub) hangs off this ONE flag. Without it the
  // surface defaulted to a confident, specific optimism — a film delivered
  // long ago opened as "starting · Warming up…" under a counting-up phase
  // timer, because "no state" and "just started" were the same value. They are
  // not: a run whose status has not loaded is UNKNOWN, and the honest render
  // of unknown is a neutral skeleton that claims nothing.
  const [hydrated, setHydrated] = useState(false)
  const phaseStart = useRef(Date.now())
  const lastPhase = useRef('')
  const threadRef = useRef<HTMLDivElement>(null)
  const videoRef = useRef<HTMLVideoElement>(null)
  const [playT, setPlayT] = useState(0)
  const evtsRef = useRef<AgentEvent[]>([])
  // FULL-SCREEN SURFACE CONTRACT: the page template wraps content in a
  // framer-motion fade with a transform — a transformed ancestor hijacks
  // position:fixed and inherits its opacity. The workspace therefore
  // PORTALS to document.body, outside any page-transition wrapper.
  const [mounted, setMounted] = useState(false)
  useEffect(() => { setMounted(true) }, [])

  const S = reduce(evts)

  // Event poll (1.5s) — the same contract as the local viewer.
  useEffect(() => {
    let stop = false
    const tick = async () => {
      if (stop) return
      try {
        const after = evtsRef.current.length
          ? evtsRef.current[evtsRef.current.length - 1].seq : -1
        // Rows whose artifact hasn't attached yet (insert-first sink):
        // ask the server to re-read them until the PATCH lands.
        const pendingArtifacts = evtsRef.current
          .filter((e) => !e.artifact_url && (
            e.kind === 'design.beat' || e.kind === 'assemble.film'
            || e.kind === 'read.page' || e.kind === 'brand.logo'
            || e.kind === 'film.shot' || e.kind === 'review.done'))
          .map((e) => e.seq)
        const res = await getAgentRun(runKey, after, (await getToken()) || '',
          pendingArtifacts)
        if (!('error' in res)) {
          let next = evtsRef.current
          if (res.refreshed && res.refreshed.length) {
            const bySeq = new Map(res.refreshed.map((e) => [e.seq, e]))
            next = next.map((e) => bySeq.get(e.seq) || e)
          }
          if (res.events.length) next = [...next, ...res.events]
          if (next !== evtsRef.current) {
            evtsRef.current = next
            setEvts(next)
          }
          if (typeof res.queueAhead === 'number') setQueueAhead(res.queueAhead)
          else if (res.events.length) setQueueAhead(null)
          if (res.filmUrl) setFilmUrl(res.filmUrl)
          const st = (res.run as { status?: string } | undefined)?.status
          if (st) setRunStatus(st)
          // Real state has arrived — and only now may this page describe the
          // run. Set on ANY successful read (a run with zero events is still a
          // known run); a failed read leaves us honestly in the dark.
          setHydrated(true)
        }
      } catch { /* transient */ }
      setTimeout(tick, 1500)
    }
    tick()
    return () => { stop = true }
  }, [runKey, getToken])

  useEffect(() => {
    if (tab !== 'builds' || library !== null) return
    let stop = false
    ;(async () => {
      try {
        const res = await listMyRuns((await getToken()) || '')
        if (stop || 'authError' in res) return
        setLibrary(res.runs
          .filter((r) => r.final_url)
          .map((r) => ({
            id: r.id,
            brand: r.brand || r.company_url || 'Launch film',
            url: r.final_url as string,
            ts: Date.parse(r.created_at) / 1000,
            status: r.status,
            mode: r.film_mode || '',
          })))
      } catch { /* transient */ }
    })()
    return () => { stop = true }
  }, [tab, library, getToken])

  // Live viewport probe (~1s): the frame URL 404s via the proxy when stale.
  useEffect(() => {
    let stop = false
    const probe = async () => {
      if (stop) return
      try {
        const res = await getAgentRun(runKey, 1e9, (await getToken()) || '')
        if (!('error' in res)) setLiveUrl(res.liveUrl)
      } catch { /* once */ }
    }
    probe()
    const iv = setInterval(() => setLiveTick((t) => t + 1), 1200)
    return () => { stop = true; clearInterval(iv) }
  }, [runKey, getToken])

  useEffect(() => {
    // The phase clock starts when there IS a phase. Before hydration `S.phase`
    // is only a default, and starting the timer against it charged the wait
    // for the first poll to the studio's work ("Scouting… 8s" on a film that
    // finished half an hour ago).
    if (!hydrated) return
    if (S.phase !== lastPhase.current) {
      lastPhase.current = S.phase
      phaseStart.current = Date.now()
    }
  })
  // The thread stays pinned to its tail. `tab` is a dependency because the
  // composer surface unmounts the rail entirely: on the way back the thread is
  // a fresh element scrolled to the top, and without a re-pin the user returns
  // to the beginning of a conversation they had already read to the end.
  useEffect(() => {
    const el = threadRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [evts.length, localMsgs.length, tab])

  const send = useCallback(async () => {
    const text = input.trim()
    if (!text) return
    setInput('')
    setLocalMsgs((m) => [...m, { ts: Date.now() / 1000, kind: 'user', text }])
    setPending(true)
    const res = await sendDirectorMessage(runKey, text, (await getToken()) || '')
    if ('error' in res) {
      // An out-of-credits refusal explains itself; anything else is a blip.
      const msg = ('message' in res && res.message)
        ? res.message
        : 'That did not go through — try again.'
      setPending(false)
      setLocalMsgs((m) => [...m, { ts: Date.now() / 1000, kind: 'dir', text: msg }])
    }
  }, [input, runKey, getToken])

  // Merge thread items chronologically; server chat events replace local echoes.
  const items: Array<
    | { ts: number; type: 'user' | 'dir'; text: string }
    | { ts: number; type: 'work'; e: AgentEvent }
  > = []
  let sawDirectorReply = false
  for (const e of evts) {
    if (!THREAD_KINDS.has(e.kind)) continue
    if (e.kind === 'chat.user') items.push({ ts: e.ts, type: 'user', text: e.title })
    else if (PROSE_KINDS.has(e.kind)) {
      items.push({ ts: e.ts, type: 'dir', text: e.title })
      if (e.kind === 'chat.director') sawDirectorReply = true
    } else items.push({ ts: e.ts, type: 'work', e })
  }
  useEffect(() => {
    if (pending && sawDirectorReply) setPending(false)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [evts.length])
  for (const m of localMsgs) {
    const dupe = evts.some((e) =>
      (e.kind === 'chat.user' || e.kind === 'chat.director')
      && e.title === m.text && Math.abs(e.ts - m.ts) < 60)
    if (!dupe) items.push({ ts: m.ts, type: m.kind, text: m.text })
  }
  items.sort((a, b) => a.ts - b.ts)

  // MOTION MEANS WORK: the mark moves only while the studio is actually
  // doing something. A terminal run row ends it even if the terminal EVENT
  // never arrived (a sink brownout used to leave it spinning forever on a
  // finished film).
  // `working` also carries the unknown-vs-starting rule: an un-hydrated run is
  // not working, because nothing is known to be happening. That one word
  // switches off the phase verb, the counting timer, the recording dot and the
  // live probe until the studio has actually reported in.
  const TERMINAL = ['delivered', 'failed', 'completed_with_warnings']
  const working = hydrated && !S.done && !TERMINAL.includes(runStatus)
  const host = (S.site || '').replace(/^https?:\/\//, '').split('/')[0]
  const brandTitle = host
    ? host.split('.')[0].charAt(0).toUpperCase()
      + host.split('.')[0].slice(1) + ' launch film'
    : 'Launch film'
  const verb = VERBS[S.phase] || 'Working'
  const elapsed = Math.round((Date.now() - phaseStart.current) / 1000)

  // ── ABSENCE MUST NOT PRODUCE A URL ─────────────────────────────────────────
  // `${liveUrl}&t=${tick}` on an empty liveUrl yields the RELATIVE reference
  // `&t=0`, which the browser resolves against /runs/ — and the app answers
  // that path with its own HTML, 200. A missing frame therefore looked like a
  // loaded one all the way down: no 404, no console error, an <img> quietly
  // decoding a web page. The concatenation now happens in exactly ONE place
  // and yields null when there is nothing to point at, so every consumer is
  // forced to branch and the empty case cannot reach an <img> at all.
  const liveFrame = liveUrl ? `${liveUrl}&t=${liveTick}` : null

  // The ONE screen's content.
  let screen: React.ReactNode = null
  let pill = ''
  const lastPage = S.pages[S.pages.length - 1]
  if (tab === 'builds') {
    screen = library === null ? (
      <div className="wk-text"><div className="big">Loading your films…</div></div>
    ) : library.length === 0 ? (
      <div className="wk-text">
        <div className="big">No finished films yet</div>
        <div className="small">Every film you produce lands here.</div>
      </div>
    ) : (
      <div className="wk-library">
        {library.map((f) => (
          <a key={f.id} className="wk-filmcard" href={`/runs/${f.id}`}>
            <div className="prev">
              {/* No still is in hand for a library row: the beat frames live
                  in each run's own event stream, and the list read returns run
                  rows only. The #t=2 fallback covers it. */}
              <FilmVideo src={f.url} poster="" role="tile"
                onLoadedMetadata={(ev) => {
                  const d = (ev.target as HTMLVideoElement).duration
                  setDurations((m) => (m[f.id] === d ? m : { ...m, [f.id]: d }))
                }} />
            </div>
            <div className="meta">
              <div className="head">
                <div className="name" title={f.brand}>{f.brand}</div>
                <StatusChip status={f.status} />
              </div>
              {/* The discriminating line: which pipeline made it, how long it
                  runs, and how long ago — three fields that differ between two
                  films of the same brand made on the same day. Unknown length
                  drops out of the line rather than printing a placeholder. */}
              <div className="sub">
                {[filmModeLabel(f.mode), runtime(durations[f.id]), relativeAge(f.ts)]
                  .filter(Boolean).join(' · ')}
              </div>
              <div className="open">Open film</div>
            </div>
          </a>
        ))}
      </div>
    )
    pill = library ? `${library.length} film${library.length === 1 ? '' : 's'} produced` : 'films'
  } else if (!hydrated) {
    // Nothing is known about this run yet: a neutral placeholder, no phase, no
    // copy to read, no timer — and no motion, because on this surface motion
    // means work and no work is known to be happening.
    screen = <div className="wk-skeleton" aria-hidden />
    pill = ''
  } else if (pinned) {
    screen = <img src={pinned.artifact_url} alt="" />
    pill = pinned.title
  } else if (liveFrame && liveFresh && working) {
    screen = <img src={liveFrame} alt="" />
    pill = `Recording ${S.site || ''}`
  } else if (evts.length === 0 && working) {
    // Queue truth: the run is CONFIRMED live (hydrated, non-terminal) and has
    // simply not emitted yet — so say where in the line it sits. Reachable only
    // after hydration, which is what keeps a finished film out of this branch.
    screen = (
      <div className="wk-text">
        <div className="big">
          {queueAhead === null ? 'Warming up…'
            : queueAhead === 0 ? 'Up next'
              : `In line at the studio`}
        </div>
        <div className="small">
          {queueAhead === null
            ? 'Connecting to the studio.'
            : queueAhead === 0
              ? 'The studio is opening your site now.'
              : `${queueAhead} build${queueAhead === 1 ? '' : 's'} ahead of you — the studio films one at a time.`}
        </div>
      </div>
    )
    // The pill echoes what the server said — the queue position it returned, or
    // failing that the run's own status word. Never a word this page made up.
    pill = queueAhead && queueAhead > 0 ? `queued · ${queueAhead} ahead`
      : queueAhead === 0 ? 'up next' : runStatus
  } else if (S.phase === 'read') {
    screen = lastPage?.artifact_url ? <img src={lastPage.artifact_url} alt="" /> : null
    pill = lastPage ? lastPage.title.replace('Read ', '') : (S.site || 'opening…')
  } else if (S.phase === 'decide') {
    screen = (
      <div className="wk-text">
        <div className="big">{S.plan.map((p, i) => <div key={i}>{p}</div>)}</div>
        <div className="small">The moments a customer cares about — the site's own words.</div>
      </div>
    )
    pill = S.site
  } else if (S.phase === 'film') {
    screen = <div className="wk-text"><div className="big">{S.lastTitle}</div></div>
    pill = S.site
  } else if (['design', 'assemble', 'review'].includes(S.phase)) {
    screen = S.beats.length ? (
      <div className="wk-grid">
        {S.beats.map((b) => (
          <div key={b.seq} className="beat"><img src={b.artifact_url} alt="" /></div>
        ))}
      </div>
    ) : (
      <div className="wk-text">
        <div className="big">Printing the film</div>
        <div className="small">The beat board fills in as scenes land.</div>
      </div>
    )
    pill = S.phase === 'review' ? 'Grading — story and coherence' : 'Cutting — beat by beat'
  } else {
    if (!S.film && filmUrl) S.film = filmUrl
    if (S.film) {
      const starts = S.beats.map((b) => {
        const m = b.detail.match(/· ([\d.]+)s/)
        return m ? parseFloat(m[1]) : NaN
      })
      const seekable = starts.some((s) => !isNaN(s))
      let active = -1
      if (seekable) {
        for (let i = 0; i < starts.length; i++) {
          if (!isNaN(starts[i]) && playT >= starts[i]) active = i
        }
      }
      screen = (
        <div className="wk-playerwrap">
          <FilmVideo src={S.film} poster={S.poster} role="player" controls videoRef={videoRef}
            onTimeUpdate={(ev) => setPlayT((ev.target as HTMLVideoElement).currentTime)} />
          {S.beats.length ? (
            <div className="wk-timeline">
              {S.beats.map((b, i) => (
                <div key={b.seq}
                  className={'seg' + (i === active ? ' on' : '')}
                  title={b.detail}
                  onClick={() => {
                    const v = videoRef.current
                    if (v && !isNaN(starts[i])) { v.currentTime = starts[i]; v.play() }
                  }}>
                  <img src={b.artifact_url} alt="" />
                  <span>{b.title.replace(/^Beat \d+:\s*/, '').split(' (')[0]}</span>
                </div>
              ))}
            </div>
          ) : null}
        </div>
      )
    } else {
      screen = <div className="wk-text"><div className="big">{S.status === 'failed' ? 'The run failed.' : 'Finished.'}</div></div>
    }
    pill = S.film
      ? `film · ${S.rejected ? 'review rejected'
        : S.review.length ? 'review passed' : 'final'}`
      : ''
  }

  // Live-frame freshness: try turning it on whenever working (img onError flips off).
  useEffect(() => {
    // The probe below owns liveFresh; the tick only advances the counter.
  }, [liveTick, working, liveUrl])

  if (!mounted) return null
  return createPortal(
    <div className="wk-root">
      <div className="wk-iconrail">
        {/* ── PRODUCT CHROME WEARS THE PRODUCT'S MARK ────────────────────────
            This rail is Filmo's own global navigation (Builds / Film / Films),
            and the slot above it is the conventional "whose app is this"
            position. It used to hold the CUSTOMER's logo, which badged Filmo
            as whoever it happened to be filming. Whatever brand a run is
            about, this is always Filmo — and because the mark comes from
            FilmoMark rather than run state, nothing run-derived can reach it.
            The mark appears here exactly once; the run's own brand lives in
            the run header below, beside the film's title. */}
        <div className="wk-brand" title="Filmo">
          <FilmoMark />
        </div>
        {/* Making a film is the primary act, so it sits directly under the
            mark where the hand already is — the position Ploy gives its own
            new-thread button. */}
        <button className={'wk-ic' + (tab === 'new' ? ' on' : '')} onClick={() => setTab('new')} title="Start a new film">
          <svg viewBox="0 0 24 24"><path d="M12 5v14M5 12h14" stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round"/></svg>
          <i>New film</i>
        </button>
        {/* ONE NAME PER THING. `Builds` and `Films` were two rail entries for
            one idea — the work this account has produced — and they disagreed
            about what it was: Builds left the app for the marketing landing,
            Films showed the library that actually answers the question. The
            library keeps its grid (it is still a wall of finished films) and
            takes the name; the link, and the second entry, are gone. */}
        <button className={'wk-ic' + (tab === 'builds' ? ' on' : '')} onClick={() => setTab('builds')} title="Films you've made">
          <svg viewBox="0 0 24 24"><rect x="3" y="4" width="8" height="7" rx="1.5" stroke="currentColor" strokeWidth="2" fill="none"/><rect x="13" y="4" width="8" height="7" rx="1.5" stroke="currentColor" strokeWidth="2" fill="none"/><rect x="3" y="13" width="8" height="7" rx="1.5" stroke="currentColor" strokeWidth="2" fill="none"/><rect x="13" y="13" width="8" height="7" rx="1.5" stroke="currentColor" strokeWidth="2" fill="none"/></svg>
          <i>Builds</i>
        </button>
        <button className={'wk-ic' + (tab === 'film' ? ' on' : '')} onClick={() => setTab('film')} title="This film">
          <svg viewBox="0 0 24 24"><rect x="3" y="5" width="18" height="14" rx="2.5" stroke="currentColor" strokeWidth="2" fill="none"/><path d="M10 9.5v5l4.5-2.5z" fill="currentColor"/></svg>
          <i>Film</i>
        </button>
        <div className="wk-railspace" />
        {/* Bottom of the rail, below the fold of the work: reaching a human is
            always available and never in the way. Not a surface — it opens
            over the room and gives it back. */}
        <button className="wk-ic" onClick={() => setFbOpen(true)} title="Send feedback">
          <svg viewBox="0 0 24 24"><rect x="2.5" y="5" width="19" height="14" rx="2.5" stroke="currentColor" strokeWidth="2" fill="none"/><path d="M3.5 7l8.5 6 8.5-6" stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round"/></svg>
          <i>Feedback</i>
        </button>
      </div>
      {/* ── THE ROOM CHANGES, THE RAIL DOESN'T ────────────────────────────
          Starting a film is not a different page, it is this room in its empty
          state — so the composer replaces the STAGE (the thread and the
          canvas) and the rail stays exactly where it was. The run keeps
          polling underneath while you type: coming back to Film shows the film
          where it actually is now, not where it was when you left it. */}
      {tab === 'new' ? <NewFilmComposer getToken={getToken} /> : (
      <>
      <div className="wk-rail">
        <div className="wk-railhead" title={S.site || undefined}>
          {/* THE RUN's identity — the only place a customer's brand appears in
              this chrome. Still by default: this mark is identity, not
              activity; the tail blob (wk-tailblob) is the thing that moves
              while the studio is working. No logo captured yet → no icon, and
              the title carries the brand on its own. */}
          {S.logo ? <img className="wk-runlogo" src={S.logo} alt="" /> : null}
          <div>
            <h1>{brandTitle} <span className="wk-betachip">beta</span></h1>
            {/* Says nothing until it knows something; then it reports the same
                truth `working` is derived from, so the header can't call a
                delivered run "live" just because its run.done event was lost. */}
            <div className="sub">
              {!hydrated ? '' : working ? 'live' : (S.status || runStatus || 'finished')}
            </div>
          </div>
        </div>
        <div className="wk-thread" ref={threadRef}>
          {items.map((it, i) => {
            if (it.type !== 'work') {
              return it.type === 'user'
                ? <div key={i} className={'t-user' + (pending && i === items.length - 1 ? ' dim' : '')}>{it.text}</div>
                : <div key={i} className="t-dir"
                    dangerouslySetInnerHTML={{ __html: md(it.text) }} />
            }
            const e = it.e
            const thumb = e.artifact_url && !e.artifact_url.includes('.mp4')
            const open = !!openWork[e.seq]
            return (
              <div key={i} className="t-work">
                <button className="t-chev" onClick={() =>
                  setOpenWork((o) => ({ ...o, [e.seq]: !o[e.seq] }))}>
                  <svg viewBox="0 0 16 16" style={{ transform: open ? 'rotate(90deg)' : 'none' }}>
                    <path d="M6 4l4 4-4 4" stroke="currentColor" strokeWidth="1.8" fill="none" strokeLinecap="round"/>
                  </svg>
                </button>
                <div className="t-workbody">
                  <div className="t-workline" onClick={() =>
                    setOpenWork((o) => ({ ...o, [e.seq]: !o[e.seq] }))}>
                    <b>{e.title}</b>
                  </div>
                  {open ? (
                    <div className="t-workdetail">
                      {e.detail ? <div>{e.detail}</div> : null}
                      {thumb ? (
                        <img src={e.artifact_url} alt=""
                          onClick={() => { setPinned(e); setTimeout(() => setPinned(null), 8000) }} />
                      ) : null}
                    </div>
                  ) : null}
                </div>
              </div>
            )
          })}
          {working || pending ? (
            <div className="t-verb">
              <span className="wk-tailblob" />
              {pending ? 'Thinking…' : `${verb}… ${elapsed}s`}
            </div>
          ) : items.length ? (
            <div className="t-verb rest">
              <span className="wk-tailblob still" />
              {S.status === 'failed' ? 'Stopped' : 'Finished'}
            </div>
          ) : null}
        </div>
        <div className="wk-inputrow">
          <div className="wk-inputbox">
            <input value={input} placeholder="Tell the director what to change…"
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') send() }} />
            <button onClick={send} aria-label="Send">↑</button>
          </div>
        </div>
      </div>
      <div className="wk-canvaswrap">
        <div className="wk-canvas">
          <div className="wk-chrome">
            <div className="dots"><i /><i /><i /></div>
            <div className="wk-tabs">
              <button className={tab === 'film' ? 'on' : ''} onClick={() => setTab('film')}>Film</button>
              <button className={tab === 'builds' ? 'on' : ''} onClick={() => setTab('builds')}>Builds</button>
            </div>
            <div className="wk-urlpill" title={S.site}>{host || '…'}</div>
            {pill ? <div className="wk-statuschip">{pill}</div> : null}
            {liveFresh && working ? <div className="rec" /> : null}
            {working && liveFrame ? (
              <img className="wk-liveprobe" src={liveFrame}
                onLoad={() => setLiveFresh(true)}
                onError={() => setLiveFresh(false)} alt="" />
            ) : null}
          </div>
          <div className="wk-screen">{screen}</div>
        </div>
      </div>
      </>
      )}

      {/* Context is what turns "this is broken" into something someone can go
          and look at: the route, the run this workspace is polling, and which
          surface was on screen when it felt wrong. */}
      <FeedbackModal
        open={fbOpen}
        onClose={() => setFbOpen(false)}
        getToken={getToken}
        context={`${window.location.pathname} · run_key=${runKey} · surface=${tab}`}
      />

      <style>{`
        .wk-root { position:fixed; inset:0; display:flex; background:#F1F1EF;
          color:#1B1B1A; font:14px/1.5 Inter,-apple-system,sans-serif; z-index:50; }
        .wk-iconrail { flex:0 0 72px; display:flex; flex-direction:column;
          align-items:center; gap:18px; padding:16px 0; border-right:1px solid #E6E6E3; }
        /* Filmo's mark sits plain on the ground — the same presentation the
           boot screen and the landing use. No tile, and no customer logo. */
        .wk-brand { width:40px; height:40px; display:flex; align-items:center;
          justify-content:center; }
        .wk-brand svg { width:34px; height:34px; display:block; }
        .wk-ic { display:flex; flex-direction:column; align-items:center; gap:4px;
          color:#8A8A86; background:none; border:none; cursor:pointer;
          text-decoration:none; font:inherit; }
        .wk-ic svg { width:22px; height:22px; }
        .wk-ic i { font-style:normal; font-size:10px; }
        .wk-ic.on, .wk-ic:hover { color:#1B1B1A; }
        /* Pushes Feedback to the foot of the rail: always reachable, never in
           the way of the work above it. */
        .wk-railspace { flex:1 1 auto; }
        /* ── FOCUS MUST BE SEEN ──────────────────────────────────────────────
           Every control on this surface is deliberately chrome-less — no
           border, no background, and in the text fields no outline either. That
           is a look, not a licence: a control a mouse can find and a keyboard
           cannot is simply broken for whoever is using the keyboard. So each
           one states its own focus, and the ones that suppress the ring hand
           the job to the box around them (:focus-within) rather than dropping
           it. Anything added to this rail or these inputs inherits the rule. */
        .wk-ic:focus-visible { color:#1B1B1A; outline:2px solid #3B82F6;
          outline-offset:4px; border-radius:8px; }
        .wk-tailblob { display:inline-block; width:26px; height:26px;
          position:relative; flex-shrink:0; vertical-align:-7px;
          background:radial-gradient(circle at 32% 30%, #7FB0FF, #3B82F6 58%, #1D4ED8);
          border-radius:44% 56% 52% 48% / 50% 46% 54% 50%;
          animation:wkmorph 2.4s ease-in-out infinite; }
        /* AT REST: perfectly round and still. Motion is the only signal. */
        .wk-tailblob.still { animation:none; border-radius:50%; }
        .wk-tabs { display:flex; gap:2px; background:#F1F1EF; border-radius:8px;
          padding:2px; }
        .wk-tabs button { border:none; background:none; font:12px Inter,sans-serif;
          padding:4px 12px; border-radius:6px; color:#8A8A86; cursor:pointer; }
        .wk-tabs button.on { background:#fff; color:#1B1B1A;
          box-shadow:0 1px 2px rgba(0,0,0,0.06); }
        .t-verb.rest { color:#B6B6B2; }
        .t-user.dim { opacity:0.45; }
        .t-chev { border:none; background:none; padding:2px; cursor:pointer;
          color:#B6B6B2; flex-shrink:0; }
        .t-chev svg { width:14px; height:14px; transition:transform 0.15s; }
        .t-workbody { min-width:0; }
        .t-workline { cursor:pointer; }
        .t-workdetail { margin-top:6px; color:#8A8A86; }
        .t-workdetail img { width:150px; border-radius:8px; margin-top:6px;
          border:1px solid #E6E6E3; cursor:pointer; display:block; }
        .wk-rail { flex:0 0 380px; display:flex; flex-direction:column;
          border-right:1px solid #E6E6E3; }
        .wk-railhead { flex:0 0 62px; display:flex; align-items:center; gap:12px;
          padding:0 20px; }
        .wk-railhead h1 { font-size:14.5px; font-weight:700; margin:0; }
        .wk-railhead .sub { color:#8A8A86; font-size:12px; min-height:16px; }
        /* The customer's mark, kept in a dark tile so transparent logos stay
           legible. Run identity, not product identity. */
        .wk-runlogo { width:32px; height:32px; border-radius:10px;
          flex-shrink:0; object-fit:cover; background:#1B1B1A; display:block;
          box-shadow:0 2px 8px rgba(0,0,0,0.12); }
        @keyframes wkmorph {
          0%,100% { border-radius:58% 42% 55% 45% / 48% 60% 40% 52%; transform:scale(1); }
          33% { border-radius:42% 58% 38% 62% / 60% 42% 58% 40%; transform:scale(0.92); }
          66% { border-radius:52% 48% 62% 38% / 40% 55% 45% 60%; transform:scale(1.05); } }
        @keyframes wkspin { to { transform:rotate(360deg); } }
        @keyframes wkhole {
          0% { border-radius:52% 48% 50% 50% / 48% 52% 48% 52%;
               transform:translate(0,0) scale(1); }
          33% { border-radius:46% 54% 58% 42% / 54% 46% 52% 48%;
                transform:translate(-34%,30%) scale(0.9); }
          66% { border-radius:55% 45% 47% 53% / 45% 55% 50% 50%;
                transform:translate(-58%,-8%) scale(1.08); }
          100% { border-radius:52% 48% 50% 50% / 48% 52% 48% 52%;
                 transform:translate(0,0) scale(1); } }
        .wk-thread { flex:1; min-height:0; overflow-y:auto; padding:6px 20px 12px;
          display:flex; flex-direction:column; gap:12px; }
        .t-user { background:#fff; border:1px solid #E6E6E3; border-radius:12px;
          padding:10px 14px; font-size:13.5px; box-shadow:0 1px 2px rgba(0,0,0,0.03); }
        .t-dir { font-size:13.5px; line-height:1.55; }
        .t-work { color:#8A8A86; font-size:12.5px; display:flex; gap:8px;
          align-items:flex-start; }
        .t-work b { color:#6E6E6A; font-weight:600; }
        .t-work img { width:52px; border-radius:6px; border:1px solid #E6E6E3;
          cursor:pointer; flex-shrink:0; }
        .t-verb { color:#8A8A86; font-size:12.5px; display:flex; align-items:center;
          gap:8px; }
        .dotp { width:7px; height:7px; border-radius:4px; background:#3B82F6;
          animation:wkpulse 1.2s infinite; }
        @keyframes wkpulse { 0%,100%{opacity:1} 50%{opacity:0.25} }
        .wk-inputrow { flex:0 0 auto; padding:14px 20px 18px; }
        .wk-inputbox { display:flex; gap:8px; background:#fff;
          border:1px solid #E6E6E3; border-radius:14px; padding:10px 12px;
          box-shadow:0 1px 3px rgba(0,0,0,0.04); }
        .wk-inputbox:focus-within { border-color:#C9D9F8;
          box-shadow:0 1px 3px rgba(0,0,0,0.04), 0 0 0 3px rgba(59,130,246,0.12); }
        .wk-inputbox input { flex:1; border:none; outline:none;
          font:13.5px Inter,sans-serif; background:transparent; }
        .wk-inputbox button { border:none; background:#1B1B1A; color:#fff;
          width:34px; height:34px; border-radius:17px; cursor:pointer;
          font-size:15px; }
        .wk-inputbox button:focus-visible { outline:2px solid #3B82F6;
          outline-offset:3px; }
        .wk-canvaswrap { flex:1 1 0; min-width:0; min-height:0; display:flex;
          align-items:stretch; justify-content:center; padding:18px; }
        .wk-canvas { flex:1; min-width:0; min-height:0; max-width:1240px;
          background:#fff; border-radius:16px; display:flex; flex-direction:column;
          overflow:hidden; box-shadow:0 1px 2px rgba(0,0,0,0.04),
          0 24px 70px -30px rgba(0,0,0,0.18); }
        .wk-chrome { flex:0 0 44px; display:flex; align-items:center; gap:14px;
          padding:0 16px; border-bottom:1px solid #E6E6E3; }
        .wk-chrome .dots { display:flex; gap:6px; }
        .wk-chrome .dots i { width:10px; height:10px; border-radius:5px;
          background:#E4E4E1; }
        .wk-urlpill { flex:1; max-width:520px; margin:0 auto;
          background:#F5F5F3; border-radius:8px; padding:5px 14px;
          text-align:center; color:#6E6E6A; font-size:12.5px;
          white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
        .wk-statuschip { flex:0 0 auto; background:#F5F5F3; border-radius:99px;
          padding:4px 12px; color:#8A8A86; font-size:11.5px;
          white-space:nowrap; max-width:240px; overflow:hidden;
          text-overflow:ellipsis; }
        .wk-chrome .rec { width:8px; height:8px; border-radius:4px;
          background:#EF4444; animation:wkpulse 1.1s infinite; }
        .wk-screen { flex:1; min-height:0; display:flex; align-items:center;
          justify-content:center; background:#FAFAF8; }
        .wk-screen img, .wk-screen video { max-width:100%; max-height:100%;
          display:block; }
        .wk-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:14px;
          width:100%; height:100%; padding:18px; grid-auto-rows:1fr; }
        .wk-grid .beat { border-radius:10px; overflow:hidden; min-height:0;
          background:#0B0B09;
          border:1px solid #E6E6E3; background:#fff; }
        .wk-grid .beat img { width:100%; height:100%; object-fit:contain; }
        /* A ROW IS SIZED BY ITS CONTENT; THE LIST SCROLLS, ROWS NEVER SHRINK.
           This grid has a definite height (100% of the canvas), and auto rows
           in a definite-height grid are free to compress below their content —
           which they did: rows collapsed from 331px to 187px, so every card's
           label block was pushed past the card's own overflow:hidden edge and
           clipped. The labels were in the DOM, laid out, visibility:visible,
           and invisible on screen — a measurement of the markup said the row
           was fine while the screen showed a black rectangle. max-content
           takes the squeeze away at its source: rows take the height their
           content needs, and the overflow becomes what it should always have
           been, a scroll. */
        .wk-library { display:grid; grid-template-columns:repeat(auto-fill, minmax(260px, 1fr));
          gap:18px; width:100%; height:100%; padding:22px; overflow-y:auto;
          align-content:start; grid-auto-rows:max-content; }
        .wk-filmcard { display:flex; flex-direction:column; border-radius:14px;
          overflow:hidden; background:#fff; border:1px solid #E6E6E3;
          text-decoration:none; color:inherit; transition:border-color .15s; }
        .wk-filmcard:hover { border-color:#C9C9C4; }
        /* Neither half of a tile may be squeezed out by the other: the frame
           keeps its ratio and the labels keep their height, whatever the grid
           row does. A row that renders its picture but not its name is the
           same failure as a row with no name at all. */
        .wk-filmcard .prev { aspect-ratio:16/9; background:#0B0B09;
          flex:0 0 auto; }
        .wk-filmcard .prev video { width:100%; height:100%; object-fit:cover;
          display:block; }
        .wk-filmcard .meta { padding:14px 16px 16px; flex:0 0 auto; }
        .wk-filmcard .head { display:flex; align-items:flex-start;
          justify-content:space-between; gap:10px; }
        .wk-filmcard .name { font-size:15px; font-weight:650; color:#1B1B1A;
          min-width:0; white-space:nowrap; overflow:hidden;
          text-overflow:ellipsis; }
        .wk-filmcard .sub { font-size:12.5px; color:#8A8A86; margin-top:3px; }
        .wk-filmcard .open { margin-top:12px; text-align:center; font-size:13px;
          padding:7px 0; border:1px solid #E6E6E3; border-radius:99px;
          color:#1B1B1A; }
        .wk-filmcard:hover .open { background:#F5F5F3; }
        .wk-liveprobe { position:absolute; width:1px; height:1px;
          opacity:0; pointer-events:none; }
        .wk-betachip { display:inline-block; vertical-align:3px;
          margin-left:8px; padding:1px 8px; border-radius:99px;
          font-size:10px; font-weight:700; letter-spacing:.08em;
          text-transform:uppercase; color:#3B82F6; background:#EAF1FF; }
        .wk-playerwrap { width:100%; height:100%; display:flex;
          flex-direction:column; gap:10px; padding:14px; min-height:0; }
        .wk-playerwrap video { flex:1; min-height:0; width:100%;
          background:#000; border-radius:10px; object-fit:contain; }
        .wk-timeline { flex:0 0 84px; display:flex; gap:6px; }
        .wk-timeline .seg { flex:1; min-width:0; border-radius:8px;
          overflow:hidden; border:2px solid #E6E6E3; cursor:pointer;
          position:relative; background:#fff; }
        .wk-timeline .seg.on { border-color:#3B82F6; }
        .wk-timeline .seg img { width:100%; height:100%; object-fit:cover; }
        .wk-timeline .seg span { position:absolute; left:0; right:0; bottom:0;
          font-size:9.5px; padding:2px 6px; color:#fff;
          background:linear-gradient(transparent, rgba(0,0,0,0.65));
          white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
        /* The un-hydrated canvas: neutral, still and silent. It asserts no
           phase and carries no copy or timer, because nothing is known yet —
           and it does not animate, because motion here means work. */
        .wk-skeleton { width:min(84%, 880px); aspect-ratio:16/9;
          border-radius:12px; background:#F1F1EF; border:1px solid #E9E9E6; }
        .wk-text { max-width:640px; text-align:center; padding:30px; }
        .wk-text .big { font-size:22px; font-weight:650; line-height:1.4; }
        .wk-text .small { color:#8A8A86; margin-top:10px; font-size:13.5px; }
      `}</style>
    </div>,
    document.body,
  )
}
