// ── THE LOADING SCREEN ──────────────────────────────────────────────────────
// The ONE loader. Every `loading.tsx` in the app renders this, and every
// in-component "we don't have the data yet" state that owns a whole surface
// renders it too. Nobody re-implements it, because the twelve bare `Loading…`
// paragraphs this replaced were exactly what re-implementation looks like once
// it has had a few months to spread.
//
// Ported from the approved prototype (`landing-lab/studio.html`, `.boot` /
// `.bootmark`) by way of `runs/[id]/loading.tsx`: a plain ground, the canonical
// mark, the word — and nothing else. No spinner, no percentage, no copy,
// because at this moment the app genuinely knows nothing yet and anything more
// would be an invention.
//
// THREE THINGS ABOUT IT ARE LOAD-BEARING.
//
// 1. IT IS A FLOW BLOCK, NEVER `position:fixed`. `app/template.tsx` wraps every
//    route in a framer-motion div that animates `y`, and a transformed ancestor
//    positions its fixed descendants against ITSELF rather than the viewport —
//    the same contract note Workspace.tsx and overview/page.tsx carry about
//    portalling to document.body. A fixed loader here would render in the wrong
//    place on every client-side navigation, which is precisely when a loader is
//    the only thing on screen. Fill the space instead; don't float over it.
//
// 2. THE GROUND IS THE CALLER'S, AND IT SHOULD MATCH THE DESTINATION. The
//    studio is `#F1F1EF`, the landing is night `#0A0A0B`, the light surfaces
//    are white. Handing a white loader to the dark landing turns a dissolve
//    into a flash, which is its own kind of jarring, so `ground` is the first
//    thing a caller controls. The default is the studio ground: pass nothing
//    and you get the screen this was extracted from.
//
// 3. THE MARK IS IMPORTED, NOT REDRAWN. `FilmoMark` is a bare server-safe path
//    (no 'use client'), so using it costs this component nothing and removes a
//    copy of the path rather than adding one. Never approximate the mark in
//    CSS — an approximation drifts the moment the real mark changes and nobody
//    notices for weeks.
//
// This file has no hooks and no 'use client', so it renders both as a server
// component (from a `loading.tsx`) and inside a client page's render.
import FilmoMark from './landing2/FilmoMark'

// ── THE THREE GROUNDS ───────────────────────────────────────────────────────
// Named rather than typed as a union so a surface with its own colour (the
// Workspace screen is #FAFAF8) can still pass a literal. Which one a route
// takes is a fact about that route's DESTINATION, so it is declared in that
// route's loading.tsx and nowhere else — and it has to be re-checked whenever
// the destination is re-skinned, which has already happened once: /videos,
// /assets, /analytics and /login all moved off white onto the studio ground
// when they were rebuilt onto the rail.

/** The studio's daylight — `.wk-root`, `.ov-root`, `.lib-root`, `.lgn-root`. */
export const GROUND_STUDIO = '#F1F1EF'
/** The landing's night — PloyLanding pins the body to this. */
export const GROUND_NIGHT = '#0A0A0B'
/** The white chrome: /how-it-works, /inside, and the editor's own canvas. */
export const GROUND_LIGHT = '#FFFFFF'

export type FilmoLoaderProps = {
  /** Surface colour behind the mark. Match the destination. Default `#F1F1EF`. */
  ground?: string
  /** Wordmark colour. Defaults to whichever of the two inks reads on `ground`. */
  ink?: string
  /** `compact` for lighter-weight surfaces (/login, /how-it-works). */
  size?: 'default' | 'compact'
  /**
   * How much room to claim.
   * `screen` — the whole viewport (route loaders, whole-page states).
   * `block`  — a generous region inside a page that already has chrome.
   * `auto`   — none of its own; the parent already sizes and centres it.
   */
  fit?: 'screen' | 'block' | 'auto'
  /** What a screen reader announces. The visible word is always "Filmo". */
  label?: string
}

// One of two inks, picked so the word is legible on whatever ground it was
// given. Only hex is understood; anything else (a gradient, `rgba(…)`, a var)
// falls back to the dark ink, which is correct for every light surface — and a
// caller using an exotic ground can always pass `ink` explicitly.
function inkFor(ground: string): string {
  const raw = ground.trim().replace(/^#/, '')
  const hex = raw.length === 3 ? raw.replace(/./g, (c) => c + c) : raw
  if (!/^[0-9a-fA-F]{6}$/.test(hex)) return '#1B1B1A'
  const n = Number.parseInt(hex, 16)
  const luminance =
    (0.2126 * ((n >> 16) & 255) + 0.7152 * ((n >> 8) & 255) + 0.0722 * (n & 255)) / 255
  return luminance > 0.5 ? '#1B1B1A' : '#F1F1EF'
}

export default function FilmoLoader({
  ground = GROUND_STUDIO,
  ink,
  size = 'default',
  fit = 'screen',
  label = 'Loading',
}: FilmoLoaderProps = {}) {
  const compact = size === 'compact'

  // Ground/ink/scale ride in as inline custom properties so the stylesheet
  // below stays identical for every caller — one rule set, many surfaces.
  const surface = {
    background: ground,
    color: ink ?? inkFor(ground),
    minHeight: fit === 'screen' ? '100vh' : fit === 'block' ? '46vh' : 0,
    '--filmo-boot-mark': compact ? '34px' : '50px',
    '--filmo-boot-type': compact ? '26px' : '38px',
    '--filmo-boot-gap': compact ? '8px' : '11px',
  } as React.CSSProperties

  return (
    <div className="filmo-boot" role="status" aria-live="polite" style={surface}>
      <div className="filmo-bootmark">
        <FilmoMark />
        {/* Hidden from the a11y tree so the live region announces the state
            ("Loading") rather than reading the brand name aloud. */}
        <span aria-hidden="true">Filmo</span>
      </div>
      <span className="filmo-bootsr">{label}</span>
      <style>{`
        .filmo-boot { width:100%; display:flex; align-items:center;
          justify-content:center; }
        .filmo-bootmark { display:flex; align-items:center;
          gap:var(--filmo-boot-gap,11px);
          font:600 var(--filmo-boot-type,38px)/1 Inter,ui-sans-serif,-apple-system,"Segoe UI",Roboto,sans-serif;
          letter-spacing:-.022em; }
        .filmo-bootmark svg { width:var(--filmo-boot-mark,50px);
          height:var(--filmo-boot-mark,50px); flex:0 0 auto;
          animation:filmo-bootbreathe 1.9s ease-in-out infinite; }
        @keyframes filmo-bootbreathe {
          0%,100% { opacity:.5; transform:scale(.93); }
          50% { opacity:1; transform:scale(1); } }
        @media (prefers-reduced-motion:reduce) {
          .filmo-bootmark svg { animation:none; opacity:1; } }
        .filmo-bootsr { position:absolute; width:1px; height:1px; padding:0;
          margin:-1px; overflow:hidden; clip:rect(0 0 0 0); white-space:nowrap;
          border:0; }
      `}</style>
    </div>
  )
}
