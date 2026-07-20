'use client'
// ── THE OVERVIEW'S RAIL ─────────────────────────────────────────────────────
// The studio (`runs/[id]/Workspace.tsx`) owns its own rail and always has; this
// is deliberately NOT a second copy of it. A rail's entries name the places
// inside a surface, and the Overview has different places than a film does — so
// what the two share is the FURNITURE (72px, the mark on the ground, 22px
// icons, a 10px label, the account circle at the foot) rather than a list of
// destinations that would then have to be kept identical in two files forever.
//
// Two entries only, both of which are true from anywhere: where you are, and
// the one act that starts everything. Anything else — a film, the library —
// is reached from the page's own content, where the thing itself is.
import Link from 'next/link'
// ONE account circle for the whole product. It is the only place credits are
// shown (deliberately not on the stats strip: what you have left to spend is a
// different kind of number from what you have made), and it owns sign-out.
import AccountMenu from '../../runs/[id]/AccountMenu'

// The canonical mark. Same path as Workspace's FilmoMark and the Wordmark —
// copied rather than imported because Workspace's copy is a private function in
// a file this one must not touch, and a mark is safer duplicated than
// approximated.
function FilmoMark() {
  return (
    <svg viewBox="14 13 56 56" aria-hidden>
      <path fillRule="evenodd" fill="#3B82F6"
        d="M42 17 C56 15 67 27 65 41 C63 55 52 67 38 65 C25 63 16 51 19 37 C21 25 30 19 42 17 Z M47 28.5 A8.5 8.5 0 1 1 47 45.5 A8.5 8.5 0 1 1 47 28.5 Z" />
    </svg>
  )
}

export default function OverviewRail({ getToken, onFeedback }: {
  getToken: () => Promise<string | null>
  /** Opens the feedback sheet, which the page owns — the rail is the way in,
   *  not the surface. */
  onFeedback: () => void
}) {
  return (
    <nav className="ovrail" aria-label="Filmo">
      <div className="ovrail-brand" title="Filmo">
        <FilmoMark />
      </div>

      <Link className="ovrail-ic on" href="/overview" aria-current="page" title="Overview">
        <svg viewBox="0 0 24 24" aria-hidden>
          <path d="M3.5 10.4 12 3.8l8.5 6.6V19a1.5 1.5 0 0 1-1.5 1.5H5A1.5 1.5 0 0 1 3.5 19z"
            stroke="currentColor" strokeWidth="2" fill="none"
            strokeLinecap="round" strokeLinejoin="round" />
          <path d="M9.5 20.5v-6h5v6" stroke="currentColor" strokeWidth="2" fill="none"
            strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        <i>Overview</i>
      </Link>

      {/* `?new=1` is the product's existing word for "go straight to the
          composer" (see the note on readIntent in app/page.tsx). Using it means
          the Overview does not need a composer of its own — two composers that
          disagree about one createBuild parameter make two different films from
          the same URL, with no visible cause. */}
      <Link className="ovrail-ic" href="/?new=1" title="Start a new filmo">
        <svg viewBox="0 0 24 24" aria-hidden>
          <path d="M12 5v14M5 12h14" stroke="currentColor" strokeWidth="2" fill="none"
            strokeLinecap="round" />
        </svg>
        <i>New filmo</i>
      </Link>

      <div className="ovrail-space" />

      <AccountMenu getToken={getToken} onFeedback={onFeedback} />

      <style>{`
        .ovrail { flex:0 0 72px; display:flex; flex-direction:column;
          align-items:center; gap:18px; padding:16px 0;
          border-right:1px solid #E6E6E3; }
        .ovrail-brand { width:40px; height:40px; display:flex;
          align-items:center; justify-content:center; }
        .ovrail-brand svg { width:34px; height:34px; display:block; }
        .ovrail-ic { display:flex; flex-direction:column; align-items:center;
          gap:4px; color:#8A8A86; background:none; border:none; cursor:pointer;
          text-decoration:none; font:inherit; }
        .ovrail-ic svg { width:22px; height:22px; }
        .ovrail-ic i { font-style:normal; font-size:10px; }
        .ovrail-ic.on, .ovrail-ic:hover { color:#1B1B1A; }
        /* FOCUS MUST BE SEEN. Every control on this rail is chrome-less by
           design; that is a look, not a licence (same rule and same ring as
           Workspace's .wk-ic and AccountMenu's button). */
        .ovrail-ic:focus-visible { color:#1B1B1A; outline:2px solid #3B82F6;
          outline-offset:4px; border-radius:8px; }
        .ovrail-space { flex:1 1 auto; }
        /* Narrow viewports: the rail keeps every entry, it just stops spending
           72px of a 390px screen on them. */
        @media (max-width:760px) {
          .ovrail { flex-basis:56px; gap:14px; }
          .ovrail-brand { width:32px; height:32px; }
          .ovrail-brand svg { width:28px; height:28px; }
          .ovrail-ic svg { width:20px; height:20px; }
          .ovrail-ic i { font-size:9px; } }
      `}</style>
    </nav>
  )
}
