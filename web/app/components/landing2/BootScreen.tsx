'use client'
import FilmoMark from './FilmoMark'

// ── THE BOOT SCREEN ─────────────────────────────────────────────────────────
// Shown while the studio is on its way. Plain ground, the mark, the word,
// nothing else — no spinner, no percentage, no copy to read. Its ground is the
// STUDIO's daylight (#F1F1EF, the same as Workspace's .wk-root), not the
// landing's night, so arriving at the studio is a dissolve instead of a cut.
//
// It covers TWO waits, which is why it lives here rather than inside the
// landing:
//   1. the click → the visitor committed, the network hasn't answered yet;
//   2. the FIRST PAINT for a visitor we believe is already signed in.
//
// (2) is handled from page.tsx rather than here: an inline script running ahead
// of the landing markup injects a stylesheet that hides the landing and forces
// this cover visible, so a signed-in visitor never watches the marketing page
// paint on its way out. React drops that stylesheet the moment it establishes
// the session is dead. The base styles below are the resting state — the cover
// stays down until either that script or the `on` prop raises it.
export default function BootScreen({ on }: { on: boolean }) {
  return (
    <>
      <style>{`
        .fl-boot { position:fixed; inset:0; z-index:999; background:#F1F1EF;
          display:flex; align-items:center; justify-content:center;
          opacity:0; visibility:hidden;
          transition:opacity .22s ease, visibility .22s; }
        .fl-boot.on { opacity:1; visibility:visible; }
        .fl-bootmark { display:flex; align-items:center; gap:11px;
          font:600 38px/1 Inter,ui-sans-serif,-apple-system,"Segoe UI",Roboto,sans-serif;
          letter-spacing:-.022em; color:#1B1B1A; }
        .fl-bootmark svg { width:50px; height:50px; flex:0 0 auto;
          animation:fl-bootbreathe 1.9s ease-in-out infinite; }
        @keyframes fl-bootbreathe {
          0%,100% { opacity:.5; transform:scale(.93) }
          50% { opacity:1; transform:scale(1) } }
        @media (prefers-reduced-motion:reduce) {
          .fl-boot { transition:none }
          .fl-bootmark svg { animation:none; opacity:1 } }
      `}</style>
      <div className={'fl-boot' + (on ? ' on' : '')} aria-hidden="true">
        <div className="fl-bootmark">
          <FilmoMark />
          <span>Filmo</span>
        </div>
      </div>
    </>
  )
}
