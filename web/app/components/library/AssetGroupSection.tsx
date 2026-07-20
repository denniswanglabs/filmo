'use client'
// ── ONE FILMO, AND THE RAW MATERIAL IT PRODUCED ─────────────────────────────
// The assets library groups its material under the film that made it. This is
// one such group: a header that is the filmo's identity, and its assets in a
// grid beneath. The header IS the run — click it to open the filmo the material
// came from, the same walk-back-to-provenance every tile offers, made once for
// the whole group.
//
// WHY BRAND NAME + DATE, NOT A BRAND MARK. The run page's RunMark draws a mark
// legibly — but it does so by probing the mark's own pixels on a canvas, routing
// through a MIME-fixing proxy, and deriving a ground per mark (see RunMark's own
// note on the Stripe black-square bug). That machinery lives in runs/[id], and a
// header is not worth importing it or re-deriving it: a mangled logo reads worse
// than clean type. So the identity is the brand, the host when it says something
// the brand does not, and the film's own date — every field a fact off the run.
import Link from 'next/link'
import AssetTile from './AssetTile'
import type { AssetGroup, AssetRow } from '../../actions'

// ⚠ TWIN of the ISO clock in FilmoCard / RecentFilmos / Workspace — same
// thresholds, same words, so one filmo never reads as two different ages across
// surfaces. On `createdAt` (the run's own ISO), not an asset's `ts`.
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

export default function AssetGroupSection({
  group, assets,
}: {
  group: AssetGroup
  /** The group's assets AFTER the active filter — a subset when a kind is
   *  selected, the whole group under "All". The caller drops empty groups, so
   *  this is never empty. */
  assets: AssetRow[]
}) {
  // The host earns a second line only when it is genuinely different from the
  // brand — "Linear · linear.app" is noise, exactly the FilmoCard rule.
  const host = group.host && group.host.toLowerCase() !== group.brand.toLowerCase()
    ? group.host : ''
  const when = relativeTime(group.createdAt)

  return (
    <section className="libgroup" aria-label={`Assets from ${group.brand}`}>
      <header className="libgroup-head">
        <Link
          className="libgroup-id"
          href={`/runs/${group.runId}`}
          title={`Open ${group.brand} — the filmo this material came from`}
        >
          <span className="libgroup-brand">{group.brand}</span>
          {host ? <span className="libgroup-host">{host}</span> : null}
        </Link>
        <span className="libgroup-meta">
          {when ? `${when} · ` : ''}{assets.length} {assets.length === 1 ? 'asset' : 'assets'}
        </span>
      </header>

      <ul className="lib-grid">
        {assets.map((a) => <AssetTile key={a.id} asset={a} />)}
      </ul>

      <style>{`
        .libgroup { margin:0 0 30px; }
        /* The header aligns to the film's identity on the left and its facts on
           the right; both stay on one line and neither pushes the other off. */
        .libgroup-head { display:flex; align-items:baseline;
          justify-content:space-between; gap:12px 16px; flex-wrap:wrap;
          margin:0 0 12px; padding-bottom:9px; border-bottom:1px solid #E6E6E3; }
        .libgroup-id { display:flex; align-items:baseline; gap:9px; min-width:0;
          text-decoration:none; color:inherit; border-radius:6px; }
        .libgroup-id:focus-visible { outline:2px solid #3B82F6; outline-offset:3px; }
        .libgroup-brand { font-size:16px; font-weight:650; letter-spacing:-.01em;
          color:#1B1B1A; min-width:0; white-space:nowrap; overflow:hidden;
          text-overflow:ellipsis; }
        .libgroup-id:hover .libgroup-brand { color:#000; }
        .libgroup-host { font-size:12.5px; color:#8A8A86; white-space:nowrap;
          flex:0 0 auto; }
        .libgroup-meta { font-size:12px; font-weight:600; letter-spacing:.04em;
          text-transform:uppercase; color:#8A8A86; white-space:nowrap;
          flex:0 0 auto; }
      `}</style>
    </section>
  )
}
