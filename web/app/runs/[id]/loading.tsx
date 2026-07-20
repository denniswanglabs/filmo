// The run route's boot screen. App Router renders this automatically while the
// segment loads, so the gap between "clicked a film" and "the workspace is on
// screen" is a Filmo screen rather than a white flash or, worse, a workspace
// full of invented progress.
//
// Ported from the approved prototype (`landing-lab/studio.html`, `.boot` /
// `.bootmark`): the studio ground, the canonical mark, the word — and nothing
// else. No spinner, no percentage, no copy, because at this moment the app
// genuinely knows nothing yet and anything more would be an invention. Same
// rule the workspace itself now follows before its first poll answers.
//
// Two deliberate deviations from the prototype, both because this IS the page
// rather than an overlay on top of one:
//   • flow block filling the viewport instead of `position:fixed`. The route
//     template wraps children in a framer-motion transform on navigation, and
//     a transformed ancestor hijacks position:fixed (the same contract note
//     Workspace.tsx carries about portalling to document.body).
//   • no `.gone` fade class — React unmounts this boundary when the segment is
//     ready, so there is nothing here to dismiss by script.
//
// The mark is inlined rather than imported: `Brand.tsx`'s Wordmark is a client
// module (it pulls the auth context in with it) and is fixed at nav/default
// sizes with no breathe, so reusing it here would cost the route a client
// bundle and still not be the approved screen. The path below is the canonical
// one, copied verbatim — never redrawn, never approximated in CSS.
export default function RunLoading() {
  return (
    <div className="filmo-boot">
      <div className="filmo-bootmark">
        <svg viewBox="14 13 56 56" aria-hidden="true">
          <path
            fillRule="evenodd"
            fill="#3B82F6"
            d="M42 17 C56 15 67 27 65 41 C63 55 52 67 38 65 C25 63 16 51 19 37 C21 25 30 19 42 17 Z M47 28.5 A8.5 8.5 0 1 1 47 45.5 A8.5 8.5 0 1 1 47 28.5 Z"
          />
        </svg>
        <span>Filmo</span>
      </div>
      <style>{`
        .filmo-boot { min-height:100vh; width:100%; background:#F1F1EF;
          display:flex; align-items:center; justify-content:center; }
        .filmo-bootmark { display:flex; align-items:center; gap:11px;
          font:600 38px/1 Inter,ui-sans-serif,-apple-system,"Segoe UI",Roboto,sans-serif;
          letter-spacing:-.022em; color:#1B1B1A; }
        .filmo-bootmark svg { width:50px; height:50px; flex:0 0 auto;
          animation:filmo-bootbreathe 1.9s ease-in-out infinite; }
        @keyframes filmo-bootbreathe {
          0%,100% { opacity:.5; transform:scale(.93); }
          50% { opacity:1; transform:scale(1); } }
        @media (prefers-reduced-motion:reduce) {
          .filmo-bootmark svg { animation:none; opacity:1; } }
      `}</style>
    </div>
  )
}
