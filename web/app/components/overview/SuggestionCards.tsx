'use client'
// ── "FOR YOU" — PROPOSALS, EACH ONE CHECKABLE ───────────────────────────────
// Every card here was derived from rows this account owns (see the OVERVIEW
// block in app/actions.ts, which is where the claims are made and where they
// have to stay true). This file's whole job is to render them without adding a
// single assertion of its own: it never infers, never rounds a count, and never
// writes a sentence the server did not derive. The one thing it does add is the
// TIME, because a date is the one fact the server cannot state correctly — a
// timestamp formatted on the server is the server's day, not the reader's.
import { useCallback, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { createBuild, type Suggestion, type SuggestionKind } from '../../actions'
import { isValidBuildUrl } from '../../../lib/pending-build'

// ── STARTING A FILMO FROM A CARD ────────────────────────────────────────────
// A card's action button is a THIRD door into the same factory: the landing's
// resume path (app/page.tsx → runBuild) and the studio's composer
// (runs/[id]/NewFilmComposer.tsx → BUILD_DEFAULTS + STUDIO_LOOK) are the other
// two. If the three disagree about a single createBuild parameter then one URL,
// started from three places, makes three different films and none of them is
// wrong — a defect with no visible cause and nobody to blame. Every value below
// is therefore pinned to exactly what the composer pins, and the composer is the
// source of truth: if it moves, this moves with it.
//   brain   'ultra-paid'  the paid flagship. createBuild's fallback for an
//                         absent brain is 'super-free', so omitting it would
//                         silently downgrade the film.
//   mode    'mock'        real Remotion cards, $0 third-party spend.
//   payMode 'auto'        payments are dormant for the open beta.
//   look    the sticky look, else 'walkrec' — the studio's own pipeline. A card
//           that quietly started a classic run would land the reader in a
//           different room than the one they pressed the button in.
const BUILD_DEFAULTS = { brain: 'ultra-paid', mode: 'mock' as const, payMode: 'auto' as const }

/** The sticky look the landing writes when someone arrives with `?look=…`.
 *  Read with the composer's exact rule — a stored 'classic' is deliberately NOT
 *  restored, because neither other door restores it and the server's default is
 *  what should decide. Mirroring the quirk is what keeps the doors identical. */
function stickyLook(): 'walkrec' | 'engineered-night' | undefined {
  try {
    const saved = localStorage.getItem('filmo-look')
    if (saved === 'walkrec' || saved === 'engineered-night') return saved
  } catch { /* private mode — the server default decides */ }
  return undefined
}

// The same clock the /videos cards and the studio's library use, so one filmo
// never reads as two different ages in two places.
function relativeTime(iso: string): string {
  const then = Date.parse(iso)
  if (!then) return ''
  const mins = Math.round((Date.now() - then) / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.round(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  const days = Math.round(hrs / 24)
  if (days < 7) return `${days}d ago`
  return new Date(then).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

// One icon per reason, drawn in the rail's hand: 24-box, 2px stroke, no fill.
// No emoji anywhere in this product.
function KindIcon({ kind }: { kind: SuggestionKind }) {
  const s = { stroke: 'currentColor', strokeWidth: 2, fill: 'none' } as const
  if (kind === 'in-flight') {
    return (
      <svg viewBox="0 0 24 24" aria-hidden>
        <circle cx="12" cy="12" r="8.5" {...s} />
        <circle cx="12" cy="12" r="3.2" fill="currentColor" />
      </svg>
    )
  }
  if (kind === 'unfilmed-page') {
    return (
      <svg viewBox="0 0 24 24" aria-hidden>
        <path d="M6 3.5h7l5 5V20a1.5 1.5 0 0 1-1.5 1.5h-10A1.5 1.5 0 0 1 5 20V5a1.5 1.5 0 0 1 1-1.5z"
          {...s} strokeLinejoin="round" />
        <path d="M13 3.5V9h5" {...s} strokeLinejoin="round" />
        <path d="M8.5 13.5h7M8.5 17h4" {...s} strokeLinecap="round" />
      </svg>
    )
  }
  if (kind === 'no-notes') {
    return (
      <svg viewBox="0 0 24 24" aria-hidden>
        <path d="M4 6.5A2.5 2.5 0 0 1 6.5 4h11A2.5 2.5 0 0 1 20 6.5v7a2.5 2.5 0 0 1-2.5 2.5H10l-4.5 4v-4A1.5 1.5 0 0 1 4 14.5z"
          {...s} strokeLinejoin="round" />
      </svg>
    )
  }
  if (kind === 'stranded-failure') {
    return (
      <svg viewBox="0 0 24 24" aria-hidden>
        <path d="M20 12a8 8 0 1 1-2.6-5.9" {...s} strokeLinecap="round" />
        <path d="M20 4v5h-5" {...s} strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    )
  }
  return (
    <svg viewBox="0 0 24 24" aria-hidden>
      <path d="M12 3.5 21 8l-9 4.5L3 8z" {...s} strokeLinejoin="round" />
      <path d="M3 12.5 12 17l9-4.5M3 17 12 21.5 21 17" {...s} strokeLinejoin="round" />
    </svg>
  )
}

function Card({ s, getToken }: {
  s: Suggestion
  getToken: () => Promise<string | null>
}) {
  const router = useRouter()
  const [busy, setBusy] = useState(false)
  // ONE line under the action carries everything this card has to say back, and
  // its tone says which kind of thing it is (same rule as the composer's hint).
  const [note, setNote] = useState<{ text: string; bad?: boolean } | null>(null)

  const run = useCallback(async () => {
    if (s.action.type !== 'build') return
    const url = s.action.url
    // createBuild THROWS on a bad URL, and a thrown server action is an opaque
    // digest 500 in production — so the message the reader would see is no
    // message at all. Both other doors check first; so does this one.
    if (!isValidBuildUrl(url)) {
      setNote({ text: 'That page no longer looks like a valid address.', bad: true })
      return
    }
    setNote(null)
    setBusy(true)
    try {
      const accessToken = await getToken()
      if (!accessToken) {
        setBusy(false)
        setNote({ text: 'Your session expired — sign in again to start it.', bad: true })
        return
      }
      const res = await createBuild({
        accessToken,
        url,
        look: stickyLook() || 'walkrec',
        ...BUILD_DEFAULTS,
      })
      // The credit cap answers with a structured { limit } rather than a run.
      // It is a real answer, not a broken session — say it and stop.
      if ('limit' in res) {
        setBusy(false)
        setNote({ text: res.message, bad: true })
        return
      }
      router.push(`/runs/${res.runId}`)
    } catch {
      setBusy(false)
      setNote({ text: 'Your session expired — sign in again to start it.', bad: true })
    }
  }, [s.action, getToken, router])

  const age = s.at ? relativeTime(s.at) : ''

  return (
    <li className="ovsug-card">
      <div className="ovsug-top">
        <span className="ovsug-icon" aria-hidden><KindIcon kind={s.kind} /></span>
        <div className="ovsug-body">
          <h3 className="ovsug-title">{s.title}</h3>
          <p className="ovsug-detail">{s.detail}</p>
          {/* WHERE IT CAME FROM, ON THE CARD. A proposal a reader cannot trace
              back to their own work is indistinguishable from one we made up. */}
          <p className="ovsug-evidence">
            {s.evidence}{age ? ` · ${age}` : ''}
          </p>
        </div>
      </div>
      <div className="ovsug-actions">
        {s.action.type === 'open' ? (
          <Link className="ovsug-btn" href={`/runs/${s.action.runId}`}>
            {s.action.label}
          </Link>
        ) : (
          <button className="ovsug-btn" onClick={() => void run()} disabled={busy}>
            {busy ? 'Starting…' : s.action.label}
          </button>
        )}
        <span className={'ovsug-note' + (note?.bad ? ' bad' : '')} role="status">
          {note?.text || ''}
        </span>
      </div>
    </li>
  )
}

export default function SuggestionCards({ suggestions, getToken, hasWork }: {
  /** null = not read yet. [] = read, and there is genuinely nothing to say. */
  suggestions: Suggestion[] | null
  getToken: () => Promise<string | null>
  /** Whether this account has started anything at all (any run, delivered or
   *  not). An empty column means two very different things on either side of
   *  that line, and telling a brand-new account "nothing to propose" would be
   *  answering a question it never asked. */
  hasWork: boolean
}) {
  return (
    <section className="ovsug" aria-labelledby="ovsug-h">
      <h2 className="ovsug-h" id="ovsug-h">For you</h2>

      {suggestions == null ? (
        <ul className="ovsug-list">
          <li className="ovsug-card ovsug-skel" aria-hidden><span /><span /></li>
          <li className="ovsug-card ovsug-skel" aria-hidden><span /><span /></li>
        </ul>
      ) : suggestions.length ? (
        <ul className="ovsug-list">
          {suggestions.map((s) => <Card key={s.id} s={s} getToken={getToken} />)}
        </ul>
      ) : (
        <div className="ovsug-empty">
          {hasWork ? (
            <>
              <b>Nothing to propose right now.</b>
              <span>
                Suggestions are read off your own filmos — the pages Filmo
                opened, the footage it kept, the notes you gave the director.
                Make another and this column fills itself in.
              </span>
            </>
          ) : (
            <>
              <b>Your first filmo starts with a URL.</b>
              <span>
                Give Filmo a product address and it reads the site the way a
                first-time visitor would, records the pages that carry the
                argument, and cuts you a film from what it actually found.
              </span>
              <Link className="ovsug-btn ovsug-cta" href="/new">New filmo</Link>
            </>
          )}
        </div>
      )}

      <style>{`
        .ovsug { min-width:0; }
        .ovsug-h { margin:0 0 12px; font-size:12px; font-weight:600;
          letter-spacing:.08em; text-transform:uppercase; color:#8A8A86; }
        .ovsug-list { list-style:none; margin:0; padding:0; display:flex;
          flex-direction:column; gap:12px; }
        .ovsug-card { background:#fff; border:1px solid #E6E6E3;
          border-radius:14px; padding:16px 18px;
          box-shadow:0 1px 2px rgba(0,0,0,.03); }
        .ovsug-top { display:flex; gap:13px; align-items:flex-start; }
        .ovsug-icon { flex:0 0 auto; width:34px; height:34px; border-radius:10px;
          display:flex; align-items:center; justify-content:center;
          background:#EAF1FF; color:#3B82F6; }
        .ovsug-icon svg { width:19px; height:19px; }
        .ovsug-body { min-width:0; }
        .ovsug-title { margin:0; font-size:15px; font-weight:650; line-height:1.35;
          color:#1B1B1A; }
        .ovsug-detail { margin:5px 0 0; font-size:13.5px; line-height:1.55;
          color:#6E6E6A; }
        .ovsug-evidence { margin:8px 0 0; font-size:11.5px; color:#B6B6B2; }
        .ovsug-actions { display:flex; align-items:center; gap:12px;
          margin:13px 0 0 47px; flex-wrap:wrap; }
        .ovsug-btn { display:inline-flex; align-items:center; justify-content:center;
          border:1px solid #E6E6E3; background:#fff; border-radius:99px;
          padding:7px 16px; font:13px/1 Inter,-apple-system,sans-serif;
          color:#1B1B1A; cursor:pointer; text-decoration:none;
          transition:background-color .15s, border-color .15s; }
        .ovsug-btn:hover:not(:disabled) { background:#F5F5F3; border-color:#C9C9C4; }
        .ovsug-btn:disabled { opacity:.5; cursor:default; }
        .ovsug-btn:focus-visible { outline:2px solid #3B82F6; outline-offset:3px; }
        .ovsug-note { font-size:11.5px; color:#B6B6B2; min-width:0; }
        .ovsug-note.bad { color:#DC2626; }
        .ovsug-empty { background:#fff; border:1px dashed #DDDDD9;
          border-radius:14px; padding:22px; display:flex; flex-direction:column;
          gap:7px; align-items:flex-start; }
        .ovsug-empty b { font-size:15px; font-weight:650; color:#1B1B1A; }
        .ovsug-empty span { font-size:13.5px; line-height:1.55; color:#6E6E6A;
          max-width:52ch; }
        .ovsug-cta { margin-top:8px; background:#1B1B1A; border-color:#1B1B1A;
          color:#fff; padding:9px 20px; }
        .ovsug-cta:hover { background:#000; border-color:#000; }
        .ovsug-skel { display:flex; flex-direction:column; gap:10px; height:104px; }
        .ovsug-skel span { display:block; height:12px; border-radius:6px;
          background:#F1F1EF; }
        .ovsug-skel span:last-child { width:60%; }
        @media (max-width:620px) {
          .ovsug-card { padding:14px 15px; }
          .ovsug-actions { margin-left:0; } }
        @media (prefers-reduced-motion:reduce) {
          .ovsug-btn { transition:none; } }
      `}</style>
    </section>
  )
}
