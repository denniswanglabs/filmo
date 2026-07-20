'use client'
// ── THE STRIP: WHAT THIS ACCOUNT HAS ACTUALLY MADE ──────────────────────────
// Three readouts along the top of the Overview. Every one of them is a count of
// rows that exist (see the OVERVIEW block in app/actions.ts) — nothing here is
// estimated, and nothing here is a projection.
//
// The strip is a READOUT, not navigation: no cell is a link, so there is no
// question about which number is clickable and no chance of a number becoming
// a button whose destination disagrees with it.
//
// Credits are deliberately absent. "What you have left to spend" is a
// different kind of number from "what you have made", and it lives in the
// account circle where the spending decision is made.
import type { OverviewStats } from '../../actions'

const n = (v: number) => Math.max(0, Math.round(v)).toLocaleString()

// A measured total, rendered at the scale a person reads. The rounding here is
// display, not estimation — the exact seconds ride along in the title so the
// number is checkable rather than merely plausible.
function filmLength(seconds: number): string {
  if (seconds <= 0) return 'no film yet'
  if (seconds < 90) return `${Math.round(seconds)}s of film`
  if (seconds < 3600) return `${Math.round(seconds / 60)} min of film`
  const hrs = Math.floor(seconds / 3600)
  const mins = Math.round((seconds % 3600) / 60)
  return `${hrs}h ${mins}m of film`
}

function Cell({ value, label, sub, note, title }: {
  value: number
  label: string
  sub: string
  /** Only rendered when there is something the headline number does not say.
   *  An absent note means the numbers above it are complete. */
  note?: string
  title?: string
}) {
  return (
    <div className="ovstat-cell" title={title}>
      <div className="ovstat-value">{n(value)}</div>
      <div className="ovstat-label">{label}</div>
      <div className="ovstat-sub">{sub}</div>
      {note ? <div className="ovstat-note">{note}</div> : null}
    </div>
  )
}

export default function StatStrip({ stats }: { stats: OverviewStats | null }) {
  if (!stats) {
    // Unknown reads as neutral, never as zero: an account whose numbers have
    // not arrived has not made nothing.
    return (
      <div className="ovstat" aria-hidden>
        <div className="ovstat-cell"><div className="ovstat-skel" /></div>
        <div className="ovstat-cell"><div className="ovstat-skel" /></div>
        <div className="ovstat-cell"><div className="ovstat-skel" /></div>
        <style>{stripCss}</style>
      </div>
    )
  }

  // THE ONE PLACE THIS STRIP CAN UNDER-REPORT, SAID OUT LOUD. A film's length
  // is read off the rendered artifact and stored per run; a delivered run from
  // before that was stored has no length anywhere. Rather than estimate one
  // (or quietly present a partial sum as a total), the cell reports how many
  // films the total was measured across.
  const unmeasured = stats.filmos - stats.filmSecondsMeasuredOf

  return (
    <div className="ovstat">
      <Cell
        value={stats.filmos}
        label={stats.filmos === 1 ? 'filmo made' : 'filmos made'}
        sub={filmLength(stats.filmSeconds)}
        note={unmeasured > 0
          ? `measured on ${stats.filmSecondsMeasuredOf} of ${stats.filmos}`
          : undefined}
        title={stats.filmSeconds > 0
          ? `${stats.filmSeconds} seconds, measured across ${stats.filmSecondsMeasuredOf} `
            + `film${stats.filmSecondsMeasuredOf === 1 ? '' : 's'}`
          : undefined}
      />
      <Cell
        value={stats.pagesRead}
        label={stats.pagesRead === 1 ? 'page read' : 'pages read'}
        sub={`${n(stats.recordings)} recording${stats.recordings === 1 ? '' : 's'} captured`}
      />
      <Cell
        value={stats.assets}
        label="assets harvested"
        sub="captures, marks, footage, stills"
      />
      <style>{stripCss}</style>
    </div>
  )
}

const stripCss = `
  .ovstat { display:grid; grid-template-columns:repeat(3, minmax(0, 1fr));
    gap:1px; background:#E6E6E3; border:1px solid #E6E6E3; border-radius:14px;
    overflow:hidden; }
  .ovstat-cell { background:#fff; padding:16px 18px; min-width:0; }
  .ovstat-value { font-size:26px; font-weight:650; letter-spacing:-.02em;
    line-height:1.1; color:#1B1B1A; font-variant-numeric:tabular-nums; }
  .ovstat-label { margin-top:3px; font-size:12.5px; color:#1B1B1A; }
  .ovstat-sub { margin-top:2px; font-size:12.5px; color:#8A8A86;
    overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .ovstat-note { margin-top:4px; font-size:11px; color:#B6B6B2; }
  .ovstat-skel { height:52px; border-radius:8px; background:#F1F1EF; }
  /* A 390px screen cannot hold three columns of numbers without either
     shrinking them past reading size or scrolling the body sideways. It gets
     one column instead — the body never scrolls horizontally. */
  @media (max-width:620px) {
    .ovstat { grid-template-columns:minmax(0, 1fr); }
    .ovstat-cell { padding:13px 16px; }
    .ovstat-value { font-size:22px; } }
`
