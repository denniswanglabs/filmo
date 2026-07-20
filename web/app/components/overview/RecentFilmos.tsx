'use client'
// ── RECENTS — THE WORK, NEWEST FIRST ────────────────────────────────────────
// The right-hand column. This is not a second library; it is the shortest
// possible answer to "what was I doing", so it is a list of rows rather than a
// wall of thumbnails, and it ends with the way to the library proper.
//
// Read from `listMyRuns` — the SAME owner-scoped server action /videos uses, so
// a filmo can never appear here with one status and there with another.
import Link from 'next/link'
import { StatusChip } from '../Brand'
import type { Run } from '../../../lib/types'

// ── A ROW MUST DISCRIMINATE ─────────────────────────────────────────────────
// Thirteen of an account's fourteen filmos can be the same brand. A row that
// carried only the brand would render perfectly and still be unfindable, so
// every row also carries a precise age, the pipeline that made it, and its
// status — the three fields that actually VARY between neighbours.
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

// The same words for the two pipelines that the /videos cards and the studio's
// library use. One thing, one name.
const filmModeLabel = (mode: string | null | undefined) =>
  mode === 'walkrec' ? 'Agent tour' : 'Brand explainer'

/** The site, as a person would say it. */
function siteName(r: Run): string {
  const raw = (r.company_url || '').trim()
  if (raw) {
    try {
      return new URL(/^https?:\/\//i.test(raw) ? raw : `https://${raw}`)
        .hostname.replace(/^www\./, '')
    } catch { /* fall through to the stored brand */ }
  }
  return r.brand || 'Untitled filmo'
}

const RECENTS_SHOWN = 7

export default function RecentFilmos({ runs }: { runs: Run[] | null }) {
  return (
    <aside className="ovrec" aria-labelledby="ovrec-h">
      <div className="ovrec-head">
        <h2 className="ovrec-h" id="ovrec-h">Recents</h2>
        {runs && runs.length > RECENTS_SHOWN ? (
          <Link className="ovrec-all" href="/videos">All filmos</Link>
        ) : null}
      </div>

      {runs == null ? (
        <ul className="ovrec-list" aria-hidden>
          <li className="ovrec-skel" /><li className="ovrec-skel" />
          <li className="ovrec-skel" />
        </ul>
      ) : runs.length === 0 ? (
        <p className="ovrec-empty">
          Nothing filmed yet. Your filmos will collect here as you make them.
        </p>
      ) : (
        <ul className="ovrec-list">
          {runs.slice(0, RECENTS_SHOWN).map((r) => (
            <li key={r.id}>
              <Link className="ovrec-row" href={`/runs/${r.id}`}>
                <span className="ovrec-name">{siteName(r)}</span>
                <StatusChip status={r.status} />
                <span className="ovrec-sub">
                  {filmModeLabel(r.film_mode)} · {relativeTime(r.created_at)}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}

      <style>{`
        .ovrec { min-width:0; }
        .ovrec-head { display:flex; align-items:baseline;
          justify-content:space-between; gap:12px; margin-bottom:12px; }
        .ovrec-h { margin:0; font-size:12px; font-weight:600; letter-spacing:.08em;
          text-transform:uppercase; color:#8A8A86; }
        .ovrec-all { font-size:12.5px; color:#8A8A86; text-decoration:none;
          border-radius:6px; }
        .ovrec-all:hover { color:#1B1B1A; }
        .ovrec-all:focus-visible { outline:2px solid #3B82F6; outline-offset:3px;
          color:#1B1B1A; }
        .ovrec-list { list-style:none; margin:0; padding:0; display:flex;
          flex-direction:column; gap:8px; }
        .ovrec-row { display:grid; grid-template-columns:minmax(0,1fr) auto;
          gap:4px 10px; align-items:center; background:#fff;
          border:1px solid #E6E6E3; border-radius:12px; padding:12px 14px;
          text-decoration:none; color:inherit;
          transition:border-color .15s, background-color .15s; }
        .ovrec-row:hover { border-color:#C9C9C4; }
        .ovrec-row:focus-visible { outline:2px solid #3B82F6; outline-offset:2px; }
        .ovrec-name { font-size:14px; font-weight:600; color:#1B1B1A;
          min-width:0; white-space:nowrap; overflow:hidden;
          text-overflow:ellipsis; }
        /* The sub-line spans both columns so a long pipeline name can never
           push the chip off the row. */
        .ovrec-sub { grid-column:1 / -1; font-size:12px; color:#8A8A86;
          min-width:0; white-space:nowrap; overflow:hidden;
          text-overflow:ellipsis; }
        .ovrec-empty { margin:0; background:#fff; border:1px dashed #DDDDD9;
          border-radius:12px; padding:16px; font-size:13px; line-height:1.55;
          color:#8A8A86; }
        .ovrec-skel { height:62px; border-radius:12px; background:#fff;
          border:1px solid #E6E6E3; }
        @media (prefers-reduced-motion:reduce) {
          .ovrec-row { transition:none; } }
      `}</style>
    </aside>
  )
}
