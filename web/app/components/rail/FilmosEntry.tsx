'use client'
// ── THE FILMOS ENTRY — LIBRARY DOOR AND LIVE-FILM INDICATOR IN ONE ──────────
// This is the rail's Filmos entry, and it now does two jobs that used to be two
// separate rail slots. It is the way to /videos (every filmo you have made), and
// it also carries the state of the films that are happening RIGHT NOW — the pulse
// while one is filming, a count when two are, a ready mark when one has landed and
// not been opened. Those live states used to live in a sibling slot of their own
// (the old LiveFilmEntry) and, inside the studio, in a third place again (the Film
// tab). Three entries for one idea — "your films" — is three things that can
// disagree, and the rail had exactly that drift history. So the current film, the
// other running films, and the library are now ONE entry (Dennis, 2026-07-20: a
// current run "doesn't need a designated film button, it can be integrated into
// the filmo button"). The film you are watching is reached by being IN the studio;
// every other film, live or finished, is reached through here.
//
// ── WHY IT IS ONE FILE AND NOT TWO ──────────────────────────────────────────
// The rail is rendered by two components — OverviewRail (off a run) and Workspace
// (the studio) — and the TWIN note at the top of each records what happens when
// they are kept in sync by hand: they drifted once on the ENTRY LIST, and a later
// mechanical diff found the Overview glyph had been drawn from two different SVG
// paths that looked identical and had already diverged in source. This entry
// carries state, motion and four visual conditions, so it is written ONCE and
// imported by both. There is no second copy to keep honest.
//
// It is also SELF-CONTAINED, which is a harder constraint than it sounds and the
// reason it fetches its own state: every page that renders a rail (/overview,
// /videos, /assets, /new, /analytics, plus the studio) gets this entry, and if it
// needed a prop then every one of those pages would have to be edited to add it.
// It takes `getToken`, which both rails already hold, plus two presentation flags
// the host rail sets (`lit`, `bar`) and — inside the studio only — the id of the
// run being viewed, so its own live state decorates this entry and it is not then
// announced back as unopened news the moment you walk out.
//
// ── WHAT IT IS ALLOWED TO CLAIM ─────────────────────────────────────────────
// MOTION MEANS WORK — the same rule the studio's tail blob obeys. The badge
// animates only while a run is genuinely alive, and liveness is derived from the
// run's STATUS *and* the age of its last event (see getLiveFilms), never from a
// completion event that may never fire. A run that has gone quiet well past any
// phase it could plausibly be in shows a STILL mark, because a moving dot on a
// wedged run is a lie about work being done.
// Everything on this entry is a row that exists: how many films are open, and
// which of four states each is in. No queue position it did not read, no phase
// label that may have rotted, and nothing from inside the operator's machinery.
import { useCallback, useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import { getLiveFilms, type LiveFilm } from '../../actions'

// ── HOW OFTEN IT ASKS ───────────────────────────────────────────────────────
// 15s, and only while a film is actually in flight. The number is chosen against
// what it is watching rather than by feel: a film takes ~10 minutes and changes
// visible state every ~1-3 minutes, so 15s is roughly a tenth of the shortest
// thing it could miss — the entry is never meaningfully behind, and a delivery
// becomes a ready mark within a quarter of a minute. It is also 10x slower than
// the studio's own 1.5s event poll, which is the right ratio: that page IS the run
// and is redrawing a thread, this is one glyph on the chrome.
const POLL_MS = 15_000

// ── SEEN, KEPT IN THE BROWSER ───────────────────────────────────────────────
// Dennis's rule: a delivered film's ready mark STAYS until he has actually opened
// it — nothing finishes without him noticing. That needs somewhere to record
// "opened", and the choice is deliberately localStorage rather than a column: it
// is a per-person UI nicety, it is worthless to the pipeline, and a schema
// migration to hold it would be a permanent cost for a temporary mark. No existing
// column means "the owner looked at this" (runs has status/phase/updated_at, all
// written BY the worker), so using one would mean overloading a field the worker
// owns — the kind of shortcut that turns into a bug the first time the worker
// writes it for its own reasons.
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

// ── THE FILMOS GLYPH ────────────────────────────────────────────────────────
// A FILM STRIP — the library's own icon, identical to the one this entry wore
// before it absorbed the live states, and identical in both rails. The entry's
// silhouette never changes and only a small corner BADGE comes and goes as films
// move through their life, so the state is legible without the rail jumping or an
// icon swapping under the reader's eye. Inline, viewBox "0 0 24 24", strokeWidth
// 2, fill none, exactly like every other glyph on this rail.
function FilmStrip() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden>
      <rect x="3" y="5" width="18" height="14" rx="2" stroke="currentColor" strokeWidth="2" fill="none" />
      <path d="M7.5 5v14M16.5 5v14M3 12h4.5M16.5 12H21" stroke="currentColor" strokeWidth="2" fill="none" />
    </svg>
  )
}

/** The ready mark, drawn small enough to live inside the badge: the work is over
 *  and waiting for you. A check, never a dot — a dot would read as "still going". */
function CheckMini() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden className="railfilm-checkmini">
      <path d="m6 12.5 3.5 3.5 8-8" stroke="currentColor" strokeWidth="3" fill="none"
        strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

export default function FilmosEntry({ getToken, lit, bar, currentRunId }: {
  /** Both rails already hold this; it is the only thing the live poll needs. */
  getToken: () => Promise<string | null>
  /** Is this the entry the reader is standing on? Lights it and sets aria-current.
   *  Off a run it means "on /videos"; inside the studio it is always true, because
   *  the film you are watching IS a filmo and this entry is where it lives now. */
  lit: boolean
  /** Draw the studio's accent bar when lit. The two rails mark the current entry
   *  differently — the studio pins an accent bar to the rail edge, the overview
   *  only darkens the ink — so which of the two to use is the host rail's call,
   *  not this entry's. Off-run rails pass it false (or omit it). */
  bar?: boolean
  /** ── THE STUDIO'S OWN RUN ─────────────────────────────────────────────────
   *  Inside /runs/[id] this entry represents the film you are viewing as well as
   *  any others, so — unlike the old sibling slot — the current run is INCLUDED
   *  in the live decoration: its pulse is this entry's pulse. What the id still
   *  buys is the acknowledgement: standing in the studio watching a film land IS
   *  opening it, so when this run finishes it must not then be announced back to
   *  you as unopened news the moment you walk out to the Overview. */
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
  //   · It never blocks first paint. This runs in an effect and the entry
  //     renders its resting shape immediately, so the rail is on screen before
  //     the first request leaves.
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
    // look once leaves the entry unable to say anything until the tab is
    // focused — so a window restored in the background pops its badge in late
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

  // ── WHAT THE BADGE SPEAKS FOR ───────────────────────────────────────────
  // Open films always count; finished ones count only until they have been
  // opened, then they fall to the library and stop being news. The run being
  // viewed is NOT excluded — inside the studio its live state is exactly what
  // should make this entry pulse. `films` may still be null (no answer yet),
  // in which case there is simply no decoration and the entry rests.
  const visible = (films ?? []).filter((f) => {
    if (isOpen(f.state)) return true
    return !seen.has(f.id)
  })
  const count = visible.length
  const anyWorking = visible.some((f) => f.state === 'live')
  const anyOpen = visible.some((f) => isOpen(f.state))
  const anyReady = visible.some((f) => f.state === 'ready')
  // Blue is for something that wants you; grey is for something at rest. A
  // stalled run is grey for the same reason its dot does not move — nothing is
  // being produced, and the entry must not imply otherwise.
  const alert = anyWorking || (anyReady && !anyOpen)

  // ── THE BADGE ───────────────────────────────────────────────────────────
  // One small mark in the corner of the film strip, and it is the ONLY thing
  // that changes as films come and go — a number when several are in play, a
  // check when one is ready to watch, a plain dot for a single film that is
  // filming or has gone quiet. `live` pulses; nothing else does.
  const badgeKind = !count ? 'none'
    : count >= 2 ? 'count'
      : anyReady && !anyWorking ? 'ready'
        : 'dot'
  const badgeTone = anyWorking ? 'live' : alert ? 'ready' : 'quiet'

  // What a screen reader (and the tooltip) get. It names the destination — this
  // is a link to the library — and, when something is happening, what. The count
  // and states are rows that exist; nothing here is invented.
  const speak = !count ? 'Filmos — every film you have made'
    : count >= 2 ? (anyWorking
      ? `Filmos — ${count} films in the studio now`
      : anyReady ? `Filmos — ${count} films, some ready to watch`
        : `Filmos — ${count} films`)
      : anyWorking ? 'Filmos — a film is filming now'
        : anyReady ? 'Filmos — a film is ready to watch'
          : anyOpen ? 'Filmos — a film is in the studio'
            : 'Filmos — every film you have made'

  return (
    <Link
      className={'railfilm' + (lit ? ' on' : '') + (bar ? ' railfilm--bar' : '')
        + (!lit && alert ? ' railfilm--alert' : '')}
      href="/videos"
      title={speak}
      aria-label={speak}
      aria-current={lit ? 'page' : undefined}
    >
      <span className="railfilm-mark">
        <FilmStrip />
        {badgeKind !== 'none' ? (
          <span className={'railfilm-badge railfilm-badge--' + badgeKind
            + ' railfilm-tone--' + badgeTone}>
            {badgeKind === 'count' ? (count > 9 ? '9+' : count)
              : badgeKind === 'ready' ? <CheckMini />
                : null}
          </span>
        ) : null}
      </span>
      <i>Filmos</i>

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
        .railfilm { position:relative; display:flex; flex-direction:column;
          align-items:center; gap:4px; background:none; border:none;
          text-decoration:none; font:inherit; cursor:pointer; color:#8A8A86; }
        .railfilm svg { width:22px; height:22px; display:block; }
        .railfilm i { font-style:normal; font-size:10px; text-align:center;
          white-space:nowrap; }
        /* Resting and hover mirror the rail's own greys. */
        .railfilm:hover { color:#1B1B1A; }
        /* Something is happening or waiting, and this is not where you are
           standing — take the rail's accent so it reads across the chrome. */
        .railfilm--alert { color:#3B82F6; }
        .railfilm--alert:hover { color:#2563EB; }
        /* YOU ARE STANDING HERE. Ink darkens like every other lit entry; the
           accent BAR is drawn only when the host rail asked for it (the studio),
           because the overview marks its current entry with ink alone. */
        .railfilm.on { color:#1B1B1A; }
        .railfilm--bar.on::before { content:''; position:absolute;
          left:calc(50% - 35.5px); top:50%; transform:translateY(-50%);
          width:3px; height:26px; border-radius:0 3px 3px 0; background:#3B82F6; }
        /* FOCUS MUST BE SEEN. The rail is chrome-less by design, which is a
           look and not a licence — same ring, same offset and same radius as
           .ovrail-ic and .wk-ic, so a keyboard crossing the rail never meets a
           control that forgot. */
        .railfilm:focus-visible { outline:2px solid #3B82F6; outline-offset:4px;
          border-radius:8px; color:#1B1B1A; }

        /* The badge lives INSIDE the glyph's fixed 22px box, so no state can
           move the rail or its neighbours. */
        .railfilm-mark { position:relative; display:block; width:22px;
          height:22px; }
        /* Base: a small dot, top-right, hugging the film strip's corner. It
           grows only rightward for a number, so the rail geometry is fixed. */
        .railfilm-badge { position:absolute; top:-5px; left:12px; box-sizing:border-box;
          min-width:11px; height:11px; border-radius:99px; display:flex;
          align-items:center; justify-content:center;
          box-shadow:0 0 0 2px #F1F1EF; }
        .railfilm-badge--count { top:-6px; min-width:15px; height:15px;
          padding:0 4px; font-size:9.5px; font-weight:700; line-height:1;
          letter-spacing:0; color:#fff; }
        .railfilm-badge--ready { width:15px; height:15px; top:-6px; }
        .railfilm-checkmini { width:11px !important; height:11px !important;
          color:#fff; }
        /* Tone carries the same blue/grey meaning the whole entry does; the
           badge keeps it even when the entry is lit (dark ink) so an in-studio
           film still shows blue that it is live. */
        .railfilm-tone--live { background:#3B82F6; color:#fff;
          animation:railfilmpulse 1.6s ease-in-out infinite; }
        .railfilm-tone--ready { background:#3B82F6; color:#fff; }
        .railfilm-tone--quiet { background:#8A8A86; color:#fff; }

        /* MOTION MEANS WORK. Only a live badge animates, and only opacity —
           nothing here reflows or repaints its neighbours. */
        @keyframes railfilmpulse { 0%,100% { opacity:1 } 50% { opacity:.3 } }
        /* Asked for no motion: the pulse goes and the badge stays, so the state
           still reads. The colour was always what carried it — the animation
           only ever drew the eye. */
        @media (prefers-reduced-motion: reduce) {
          .railfilm-tone--live { animation:none; }
        }

        /* Matches OverviewRail's narrow-viewport rule so the entry shrinks with
           the rail it is in. Scoped to :not(.railfilm--bar) — i.e. the overview
           rail only — because that rail shrinks to 56px at this width while the
           studio's (.wk-iconrail, which passes bar) stays 72px at every width; a
           blanket shrink would render the studio's Filmos glyph 2px smaller than
           its .wk-ic siblings. */
        @media (max-width:760px) {
          .railfilm:not(.railfilm--bar) svg { width:20px; height:20px; }
          .railfilm:not(.railfilm--bar) .railfilm-mark { width:20px; height:20px; }
          .railfilm:not(.railfilm--bar) i { font-size:9px; } }
      `}</style>
    </Link>
  )
}
