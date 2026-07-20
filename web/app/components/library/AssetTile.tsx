'use client'
// ── ONE PIECE OF RAW MATERIAL ───────────────────────────────────────────────
// An asset tile answers three questions, and a tile that answers only the
// first is the same unfindable-library failure the filmo cards were built to
// avoid:
//   what is it   the name, plus a badge for its KIND — in the unfiltered view a
//                page capture, a scene still and a brand mark are all just
//                rectangles, and only the badge tells them apart
//   whose is it  the brand it was taken from
//   when         how long ago it was taken
//
// The badge is a text label. There are no emoji in this product.
//
// ── EVERY TILE LINKS TO ITS RUN ─────────────────────────────────────────────
// Preserved from the first version of this page, and it is the whole point of
// the surface. This library is the provenance ledger made browsable: the
// product's claim is that nothing in a film is invented, and that claim is only
// CHECKABLE if each artifact walks you back to the film it belongs to. A tile
// that opened a lightbox would look better and prove less.
import Link from 'next/link'
import MediaThumb from './MediaThumb'
import type { AssetKind, AssetRow } from '../../actions'

// The user's word for the thing, never the pipeline's event kind — "Page
// capture", not "read.page". Singular here because a badge labels one item;
// the filter strip's plurals label a set.
const KIND_BADGE: Record<AssetKind, string> = {
  film: 'Film',
  recording: 'Recording',
  capture: 'Page capture',
  scene: 'Scene still',
  mark: 'Brand mark',
}

// ⚠ TWIN of the clock in FilmoCard / RecentFilmos / Workspace, on `ts` seconds
// rather than an ISO string (this is what listAssets returns). Same thresholds,
// same words — one artifact must not read as two different ages on two
// different surfaces.
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

export default function AssetTile({ asset }: { asset: AssetRow }) {
  const sub = [asset.brand, relativeAge(asset.ts)].filter(Boolean).join(' · ')

  return (
    <li>
      <Link
        className="libasset"
        href={`/runs/${asset.runId}`}
        title={`${asset.name} — open the filmo this came from`}
      >
        {/* A brand mark is small and usually transparent, so it sits ON the
            tile instead of being cropped to fill it. Everything else is a
            frame and fills. No still exists for any of these rows, so poster
            is '' and MediaThumb's #t=2 fallback covers the footage. */}
        <MediaThumb
          src={asset.url}
          video={asset.video}
          poster=""
          fit={asset.kind === 'mark' ? 'contain' : 'cover'}
        />
        <div className="libasset-meta">
          <div className="libasset-name">{asset.name}</div>
          <div className="libasset-row">
            <span className="libasset-badge">{KIND_BADGE[asset.kind]}</span>
          </div>
          <div className="libasset-sub">{sub}</div>
        </div>
      </Link>

      <style>{`
        .libasset { display:flex; flex-direction:column; border-radius:12px;
          overflow:hidden; background:#fff; border:1px solid #E6E6E3;
          text-decoration:none; color:inherit; height:100%;
          transition:border-color .15s; }
        .libasset:hover { border-color:#C9C9C4; }
        .libasset:focus-visible { outline:2px solid #3B82F6; outline-offset:2px; }
        .libasset-meta { padding:10px 12px 12px; flex:0 0 auto; min-width:0; }
        /* Two lines, then ellipsis. A capture's name is a URL path and can be
           long; it may wrap, but it may not push the badge and the age past the
           tile's own overflow edge — which is the exact mechanism that turned
           the studio's library into blank rectangles. */
        .libasset-name { font-size:13px; font-weight:600; color:#1B1B1A;
          line-height:1.35; display:-webkit-box; -webkit-line-clamp:2;
          -webkit-box-orient:vertical; overflow:hidden; word-break:break-word; }
        .libasset-row { margin-top:6px; }
        .libasset-badge { display:inline-block; background:#F5F5F3;
          border:1px solid #EDEDEA; border-radius:99px; padding:2px 8px;
          font-size:10.5px; font-weight:600; letter-spacing:.03em;
          color:#6E6E6A; white-space:nowrap; }
        .libasset-sub { margin-top:5px; font-size:11.5px; color:#8A8A86;
          white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
        @media (prefers-reduced-motion:reduce) {
          .libasset { transition:none; } }
      `}</style>
    </li>
  )
}
