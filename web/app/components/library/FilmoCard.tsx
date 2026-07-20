'use client'
// ── ONE FILMO, IN A LIBRARY OF FILMOS THAT LOOK ALIKE ───────────────────────
// ⚠ The reference for this card is the studio's own library tile
// (`runs/[id]/Workspace.tsx`, `.wk-filmcard`) and it is the reference for one
// specific reason: A ROW MUST DISCRIMINATE.
//
// Thirteen of an account's fourteen filmos can be the same brand, made the same
// afternoon, from the same URL. A card carrying only the brand and "Updated
// today" renders perfectly and is still useless — the reader cannot tell which
// one they want, so the library has failed at the only job a library has. That
// was a real complaint about a real page, not a hypothetical.
//
// So every card carries the four fields that actually VARY between neighbours:
//   status    the chip — queued / running / delivered / failed
//   pipeline  which of the two producers made it
//   runtime   the film's OWN measured length, read off the file
//   age       precise while it is recent, a date once it is not
// Any of them may be unknown; an unknown one DROPS OUT of the line rather than
// printing a placeholder, because "—" is a fact about our plumbing and the
// reader is looking for their film.
import { useState } from 'react'
import Link from 'next/link'
import { StatusChip } from '../Brand'
import MediaThumb from './MediaThumb'
import type { Run } from '../../../lib/types'

// ⚠ TWIN of the helpers in `components/overview/RecentFilmos.tsx` and
// `runs/[id]/Workspace.tsx`. Copied rather than imported, on the same terms the
// rest of this codebase copies its clock: the rule is four lines long, and the
// files that own the other copies are not this agent's to edit. What matters is
// that they AGREE — one filmo must never read as two different ages, or two
// different names, on two different surfaces.
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

/** The site, as a person would say it — the Overview's rule, exactly. */
export function siteName(r: Run): string {
  const raw = (r.company_url || '').trim()
  if (raw) {
    try {
      return new URL(/^https?:\/\//i.test(raw) ? raw : `https://${raw}`)
        .hostname.replace(/^www\./, '')
    } catch { /* fall through to the stored brand */ }
  }
  return r.brand || 'Untitled filmo'
}

/** The same words for the two pipelines that the Overview and the studio use. */
export const filmModeLabel = (mode: string | null | undefined) =>
  mode === 'walkrec' ? 'Agent tour' : 'Brand explainer'

// The filmo's own measured length, read off the tile's metadata load — never a
// guess, and never a duration computed from a plan. An unknown or streaming
// duration returns '' and the line simply loses a field.
function runtime(secs: number | undefined): string {
  if (!secs || !isFinite(secs) || secs <= 0) return ''
  const s = Math.round(secs)
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, '0')}s`
}

export default function FilmoCard({ run }: { run: Run }) {
  // Held per card rather than in a map on the page: one film's metadata
  // arriving must not re-render every other film in the library.
  const [secs, setSecs] = useState<number>()

  const name = siteName(run)
  // The brand is worth a second line only when it is genuinely different from
  // the host — "Linear · linear.app" is noise, not information.
  const brandAside = run.brand && run.brand.toLowerCase() !== name.toLowerCase()
    ? run.brand : ''

  const sub = [filmModeLabel(run.film_mode), runtime(secs), relativeTime(run.created_at)]
    .filter(Boolean).join(' · ')

  return (
    <li>
      <Link className="libfilmo" href={`/runs/${run.id}`}>
        {/* No still is in hand for a library row — the beat frames live in each
            run's own event stream and this list read returns run rows only. A
            run that never delivered has no film at all, and passes '' rather
            than a URL that does not exist. */}
        <MediaThumb src={run.final_url || ''} video poster="" fit="cover"
          onLoadedMetadata={(ev) => {
            const d = (ev.target as HTMLVideoElement).duration
            setSecs((prev) => (prev === d ? prev : d))
          }} />

        <div className="libfilmo-meta">
          <div className="libfilmo-head">
            <span className="libfilmo-name" title={brandAside ? `${name} · ${brandAside}` : name}>
              {name}
            </span>
            <StatusChip status={run.status} />
          </div>
          {brandAside ? <div className="libfilmo-brand">{brandAside}</div> : null}
          <div className="libfilmo-sub">{sub}</div>
          <span className="libfilmo-open">Open filmo</span>
        </div>
      </Link>

      <style>{`
        .libfilmo { display:flex; flex-direction:column; border-radius:14px;
          overflow:hidden; background:#fff; border:1px solid #E6E6E3;
          text-decoration:none; color:inherit; height:100%;
          transition:border-color .15s; }
        .libfilmo:hover { border-color:#C9C9C4; }
        .libfilmo:focus-visible { outline:2px solid #3B82F6; outline-offset:2px; }
        /* flex:0 0 auto on the label block, matching the thumb: neither half of
           a tile may be squeezed out by the other. */
        .libfilmo-meta { padding:14px 16px 16px; flex:0 0 auto; }
        .libfilmo-head { display:flex; align-items:flex-start;
          justify-content:space-between; gap:10px; }
        .libfilmo-name { font-size:15px; font-weight:650; color:#1B1B1A;
          min-width:0; white-space:nowrap; overflow:hidden;
          text-overflow:ellipsis; }
        .libfilmo-brand { margin-top:2px; font-size:12.5px; color:#6E6E6A;
          white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
        .libfilmo-sub { margin-top:3px; font-size:12.5px; color:#8A8A86;
          white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
        .libfilmo-open { display:block; margin-top:12px; text-align:center;
          font-size:13px; padding:7px 0; border:1px solid #E6E6E3;
          border-radius:99px; color:#1B1B1A; transition:background-color .15s; }
        .libfilmo:hover .libfilmo-open { background:#F5F5F3; }
        @media (prefers-reduced-motion:reduce) {
          .libfilmo, .libfilmo-open { transition:none; } }
      `}</style>
    </li>
  )
}
