'use client'
// ── THE FILM THAT IS HAPPENING ──────────────────────────────────────────────
// Filmo's most important fact is "a film is running right now", and until this
// existed the product forgot it the moment you left the studio: the Film tab
// lives inside /runs/[id], so navigating to Overview, Filmos or Assets made the
// running film invisible. This entry carries it everywhere the rail goes.
//
// ── WHY IT IS ONE FILE AND NOT TWO ──────────────────────────────────────────
// The rail is rendered by two components — OverviewRail (off a run) and
// Workspace (the studio) — and the TWIN note at the top of each records what
// happens when they are kept in sync by hand: they drifted once on the ENTRY
// LIST, and a later mechanical diff found the Overview glyph had been drawn
// from two different SVG paths that looked identical and had already diverged
// in source. So this entry is written ONCE and imported by both. There is no
// second copy to keep honest.
//
// It is also SELF-CONTAINED, which is a harder constraint than it sounds and
// the reason it fetches its own state: five pages render a rail
// (/overview, /videos, /assets, /new, /analytics, plus the studio), and if this
// needed a prop then every one of those pages would have to be edited to add
// it. It takes `getToken`, which both rails already hold, and nothing else.
//
// ── WHAT IT IS ALLOWED TO CLAIM ─────────────────────────────────────────────
// MOTION MEANS WORK — the same rule the studio's tail blob obeys. The dot
// animates only while the run is genuinely alive, and liveness is derived from
// the run's STATUS *and* the age of its last event (see getLiveFilms), never
// from a completion event that may never fire. A run that has gone quiet well
// past any phase it could plausibly be in renders STILL, because a moving dot
// on a wedged run is a lie about work being done.
// Everything on this entry is a row that exists: how many films are open, and
// which of four states each is in. No queue position it did not read, no phase
// label that may have rotted, and nothing from inside the operator's machinery.
import { useCallback, useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import { getLiveFilms, type LiveFilm } from '../../actions'

// ── HOW OFTEN IT ASKS ───────────────────────────────────────────────────────
// 15s, and only while a film is actually in flight. The number is chosen
// against what it is watching rather than by feel: a film takes ~10 minutes and
// changes visible state every ~1-3 minutes, so 15s is roughly a tenth of the
// shortest thing it could miss — the entry is never meaningfully behind, and a
// delivery becomes a ready mark within a quarter of a minute. It is also 10x
// slower than the studio's own 1.5s event poll, which is the right ratio: that
// page IS the run and is redrawing a thread, this is one glyph on the chrome.
const POLL_MS = 15_000

// ── SEEN, KEPT IN THE BROWSER ───────────────────────────────────────────────
// Dennis's rule: a delivered film's entry STAYS, as a quiet ready mark, until
// he has actually opened it — nothing finishes without him noticing. That needs
// somewhere to record "opened", and the choice is deliberately localStorage
// rather than a column: it is a per-person UI nicety, it is worthless to the
// pipeline, and a schema migration to hold it would be a permanent cost for a
// temporary mark. No existing column means "the owner looked at this" (runs has
// status/phase/updated_at, all written BY the worker), so using one would mean
// overloading a field the worker owns — the kind of shortcut that turns into a
// bug the first time the worker writes it for its own reasons.
const SEEN_KEY = 'filmo_rail_seen_v1'
// Bounded so a heavy account cannot grow this without limit. Newest kept.
const SEEN_CAP = 200

/** The acknowledged ids, or null when this browser has never written the key —
 *  which is the ONLY way to tell a fresh install from an account that has
 *  genuinely seen everything, and is what the first-run seed below hangs on. */
function readSeen(): string[] | null {
  try {
    const raw = window.localStorage.getItem(SEEN_KEY)
    if (raw == null) return null
    const parsed = JSON.parse(raw) as unknown
    return Array.isArray(parsed) ? parsed.filter((x): x is string => typeof x === 'string') : []
  } catch {
    // Unreadable or disabled storage: treat as "nothing acknowledged" rather
    // than as a fresh install, so a private-mode browser cannot loop through
    // the seeding branch on every mount.
    return []
  }
}

function writeSeen(ids: string[]): void {
  try {
    window.localStorage.setItem(SEEN_KEY, JSON.stringify(ids.slice(-SEEN_CAP)))
  } catch { /* storage full or blocked — the mark simply does not persist */ }
}

const isOpen = (s: LiveFilm['state']) => s === 'live' || s === 'stalled'

// ── THE GLYPHS ──────────────────────────────────────────────────────────────
// All three share the SAME ring, so the entry's silhouette never changes and
// only what sits inside it does — the state is legible without the entry
// jumping or resizing as a film moves through its life. Inline, viewBox
// "0 0 24 24", strokeWidth 2, fill none, exactly like every other glyph on this
// rail; the one filled element is the live core, which follows the precedent
// the Film tab's play triangle already set.

/** In flight. A FILLED core means the studio is working; a hollow one means the
 *  run is open but nothing is currently coming out of it. The fill — not the
 *  animation — is what carries "live", which is what lets the pulse be removed
 *  entirely for prefers-reduced-motion without the state becoming unreadable. */
function OpenGlyph({ working }: { working: boolean }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden>
      <circle cx="12" cy="12" r="8.5" stroke="currentColor" strokeWidth="2" fill="none" />
      {working ? (
        <circle className="railfilm-core" cx="12" cy="12" r="3.6" fill="currentColor" />
      ) : (
        <circle cx="12" cy="12" r="3.4" stroke="currentColor" strokeWidth="2" fill="none" />
      )}
    </svg>
  )
}

/** Delivered and not yet opened. A check, not a dot — the work is over. */
function ReadyGlyph() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden>
      <circle cx="12" cy="12" r="8.5" stroke="currentColor" strokeWidth="2" fill="none" />
      <path d="m8.4 12.1 2.5 2.5 4.7-5" stroke="currentColor" strokeWidth="2" fill="none"
        strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

/** Over, with no film to watch. A bar rather than a cross or a warning triangle:
 *  it has to be TELLABLE from the check at 22px and it must not shout, because
 *  the rail is chrome and a failed build is already reported where it happened. */
function StoppedGlyph() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden>
      <circle cx="12" cy="12" r="8.5" stroke="currentColor" strokeWidth="2" fill="none" />
      <path d="M8.6 12h6.8" stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round" />
    </svg>
  )
}

export default function LiveFilmEntry({ getToken, currentRunId }: {
  /** Both rails already hold this; it is the only thing this entry needs. */
  getToken: () => Promise<string | null>
  /** ── THE STUDIO EDGE CASE ────────────────────────────────────────────────
   *  Inside /runs/[id] the rail ALREADY carries a Film tab for the run you are
   *  standing in, and two entries for one film is the twin-drift problem in
   *  miniature. Passing the run id here drops it from this entry, so the Film
   *  tab keeps the live indication for the film you are looking at and this
   *  entry only ever speaks for films you CANNOT currently see. A different run
   *  going in the background still appears, which is the whole point.
   *  It also acknowledges that run when it finishes: standing in the studio
   *  watching a film land IS opening it, so it must not then be announced back
   *  to you as unopened news the moment you walk out. */
  currentRunId?: string
}) {
  const [films, setFilms] = useState<LiveFilm[] | null>(null)
  const [seen, setSeen] = useState<Set<string>>(() => new Set())
  // The last good answer, so a failed read never clears the entry (see load()).
  const filmsRef = useRef<LiveFilm[] | null>(null)
  const seenRef = useRef<Set<string>>(new Set())
  const seeded = useRef(false)

  // Storage is read in an effect, never in a useState initializer: this renders
  // on the server too, and a first paint that depends on localStorage
  // hydrates into a mismatch.
  useEffect(() => {
    const stored = readSeen()
    if (stored) {
      const s = new Set(stored)
      seenRef.current = s
      setSeen(s)
      seeded.current = true
    }
  }, [])

  const ack = useCallback((id: string) => {
    if (!id || seenRef.current.has(id)) return
    const next = new Set(seenRef.current)
    next.add(id)
    seenRef.current = next
    setSeen(next)
    writeSeen(Array.from(next))
  }, [])

  /** Returns whether anything is still in flight — i.e. whether to keep asking. */
  const load = useCallback(async (): Promise<boolean> => {
    const stillOpen = () => (filmsRef.current ?? []).some((f) => isOpen(f.state))
    try {
      const res = await getLiveFilms((await getToken()) || '')
      // A READ THAT DID NOT HAPPEN IS NOT AN EMPTY ANSWER. Both of these leave
      // whatever we already had on screen: signing out is handled by the pages
      // themselves, and a server blip must never be rendered as "your film
      // finished" or "nothing is running" (the same rule the Overview's reads
      // state at length in actions.ts).
      if ('authError' in res || 'unavailable' in res) return stillOpen()

      // ── FIRST RUN ON THIS BROWSER SEEDS ITSELF ──────────────────────────
      // The seen-set did not exist before this feature did, so on a browser
      // that has never written it EVERY already-finished film would read as
      // unopened news — an account with a day of work behind it would light up
      // with a stack of "ready" marks for films watched hours ago. That is
      // fabricated news, which is the same defect as a fabricated number. A
      // browser meeting this for the first time therefore acknowledges
      // everything already finished and starts reporting from now on.
      if (!seeded.current) {
        seeded.current = true
        const already = res.films.filter((f) => !isOpen(f.state)).map((f) => f.id)
        const s = new Set(already)
        seenRef.current = s
        setSeen(s)
        writeSeen(already)
      }

      filmsRef.current = res.films
      setFilms(res.films)
      return res.films.some((f) => isOpen(f.state))
    } catch {
      return stillOpen()
    }
  }, [getToken])

  // ── THE POLL, AND WHEN IT STOPS ─────────────────────────────────────────
  // Three rules, all of them about not being the reason the app feels slow:
  //   · It never blocks first paint. This runs in an effect and the component
  //     renders NOTHING until an answer arrives, so the rail is on screen
  //     before the first request leaves.
  //   · It stops dead when nothing is in flight. Not a slower interval — no
  //     timer at all. An account with no running film costs exactly one query
  //     per mount and then nothing.
  //   · It stops while the tab is hidden and re-asks when it comes back, so a
  //     forgotten background tab is not quietly polling all afternoon.
  // Coming back into view re-arms it, which is also how a film started in
  // another tab is picked up despite the loop having stopped.
  useEffect(() => {
    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | null = null
    let busy = false

    const clear = () => {
      if (timer) { clearTimeout(timer); timer = null }
    }

    // `scheduled` is what separates the FIRST read from every repeat, and the
    // distinction matters: a hidden tab must not POLL, but refusing even to
    // look once leaves the rail unable to say anything until the tab is
    // focused — so a window restored in the background pops its entry in late
    // rather than being right the instant it is looked at. One small query on
    // mount is not the thing that makes an app feel slow; a timer running
    // behind a forgotten tab is, and that is what stays gated.
    const tick = async (scheduled: boolean) => {
      if (cancelled || busy) return
      if (scheduled && document.hidden) { clear(); return }
      busy = true
      let keepGoing = false
      try {
        keepGoing = await load()
      } finally {
        busy = false
      }
      if (cancelled) return
      clear()
      if (keepGoing && !document.hidden) timer = setTimeout(() => void tick(true), POLL_MS)
    }

    const onVisibility = () => {
      if (document.hidden) clear()
      else if (!timer && !busy) void tick(true)
    }

    void tick(false)
    document.addEventListener('visibilitychange', onVisibility)
    return () => {
      cancelled = true
      clear()
      document.removeEventListener('visibilitychange', onVisibility)
    }
  }, [load])

  // Standing in the studio while this run finishes IS opening it.
  useEffect(() => {
    if (!currentRunId || !films) return
    const here = films.find((f) => f.id === currentRunId)
    if (here && !isOpen(here.state)) ack(currentRunId)
  }, [currentRunId, films, ack])

  // Nothing is claimed until something is known — see the poll note above.
  if (!films) return null

  const visible = films.filter((f) => {
    // The run you are standing in is spoken for by the Film tab.
    if (currentRunId && f.id === currentRunId) return false
    if (isOpen(f.state)) return true
    // Finished: it stays until it has been opened, then it is gone.
    return !seen.has(f.id)
  })
  if (!visible.length) return null

  // ── ONE ENTRY, WHATEVER THE COUNT ───────────────────────────────────────
  // Dennis's call: two films running is ONE entry with a count, not two
  // entries. The rail's height is therefore fixed at any number of runs — the
  // badge is absolutely positioned inside the glyph's own 22px box, so going
  // from one film to nine changes the badge's width and nothing else.
  const count = visible.length
  // Newest first (the action orders by created_at desc), so this opens the
  // newest — which is the one just started, or the one just delivered.
  const target = visible[0]
  const anyWorking = visible.some((f) => f.state === 'live')
  const anyOpen = visible.some((f) => isOpen(f.state))
  const anyReady = visible.some((f) => f.state === 'ready')

  // The label names the STATE OF THE SET, and each of the three is true of
  // every film it covers. "In studio" is the product's own phrase for a film in
  // flight (the Overview's in-flight card says it too) and — this is the point
  // of choosing it — it stays true of a run that has gone quiet, which "Filming"
  // would not. A wedged film is still in the studio; it is just not moving.
  const label = anyOpen ? 'In studio' : anyReady ? 'Ready' : 'Stopped'
  // Blue is for something that wants you; grey is for something at rest. A
  // stalled run is grey for the same reason its core is hollow — nothing is
  // being produced, and the entry must not imply otherwise.
  const alert = anyWorking || (!anyOpen && anyReady)

  const glyph = anyOpen
    ? <OpenGlyph working={anyWorking} />
    : anyReady ? <ReadyGlyph /> : <StoppedGlyph />

  // What a screen reader (and the tooltip) get: which film, and what is true of
  // it. The site name is the run's own company_url host — a customer's site, not
  // anything from inside the operator's machinery.
  const one = target.label
  const speak = count > 1
    ? `${count} films — ${label.toLowerCase()}. Opens the newest, ${one}.`
    : anyWorking ? `${one} is filming now`
      : anyOpen ? `${one} is in the studio`
        : anyReady ? `${one} is ready to watch`
          : `${one} stopped before it finished`

  return (
    <Link
      className={'railfilm' + (alert ? ' railfilm--alert' : ' railfilm--quiet')}
      href={`/runs/${target.id}`}
      title={speak}
      aria-label={speak}
    >
      <span className="railfilm-mark">
        {glyph}
        {count > 1 ? (
          <span className="railfilm-badge">{count > 9 ? '9+' : count}</span>
        ) : null}
      </span>
      <i>{label}</i>

      <style>{`
        /* Every value here mirrors the rail it sits in (.ovrail-ic / .wk-ic)
           rather than inheriting from it, because this entry is rendered inside
           TWO different rails whose item classes are not the same. Owning them
           is what makes the component genuinely self-contained: one file to
           keep right, and it cannot half-inherit from one host and look wrong
           in the other.
           NB: no backticks in these comments — this is a template literal and
           one would terminate it. The studio's stylesheet learned that the
           expensive way and says so twice. */
        .railfilm { display:flex; flex-direction:column; align-items:center;
          gap:4px; background:none; border:none; text-decoration:none;
          font:inherit; cursor:pointer; }
        .railfilm svg { width:22px; height:22px; display:block; }
        .railfilm i { font-style:normal; font-size:10px; text-align:center;
          white-space:nowrap; }
        /* Something is happening, or something is waiting for you. */
        .railfilm--alert { color:#3B82F6; }
        .railfilm--alert:hover { color:#2563EB; }
        /* In flight but not moving, or over without a film. The rail's own
           resting grey — it is present, it is not asking for anything. */
        .railfilm--quiet { color:#8A8A86; }
        .railfilm--quiet:hover { color:#1B1B1A; }
        /* FOCUS MUST BE SEEN. The rail is chrome-less by design, which is a
           look and not a licence — same ring, same offset and same radius as
           .ovrail-ic and .wk-ic, so a keyboard crossing the rail never meets a
           control that forgot. */
        .railfilm:focus-visible { outline:2px solid #3B82F6; outline-offset:4px;
          border-radius:8px; }

        /* The badge lives INSIDE the glyph's fixed 22px box, so no count can
           move the rail or its neighbours. */
        .railfilm-mark { position:relative; display:block; width:22px;
          height:22px; }
        .railfilm-badge { position:absolute; top:-6px; left:13px;
          min-width:15px; height:15px; padding:0 4px; box-sizing:border-box;
          border-radius:99px; background:#3B82F6; color:#fff;
          font-size:9.5px; font-weight:700; line-height:15px; text-align:center;
          letter-spacing:0; }
        .railfilm--quiet .railfilm-badge { background:#8A8A86; }

        /* MOTION MEANS WORK. Only the live core animates, and only opacity —
           nothing here reflows or repaints its neighbours. */
        .railfilm-core { animation:railfilmpulse 1.6s ease-in-out infinite; }
        @keyframes railfilmpulse { 0%,100% { opacity:1 } 50% { opacity:.25 } }
        /* Asked for no motion: the pulse goes and the FILLED core stays, so the
           state still reads as live. The fill was always what carried it — the
           animation only ever drew the eye. */
        @media (prefers-reduced-motion: reduce) {
          .railfilm-core { animation:none; }
        }

        /* Matches OverviewRail's narrow-viewport rule so the entry shrinks with
           the rail it is in rather than becoming its widest item. */
        @media (max-width:760px) {
          .railfilm svg { width:20px; height:20px; }
          .railfilm-mark { width:20px; height:20px; }
          .railfilm i { font-size:9px; } }
      `}</style>
    </Link>
  )
}
