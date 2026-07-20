'use client'
// ── THE OVERVIEW'S RAIL ─────────────────────────────────────────────────────
// ⚠ TWIN: `runs/[id]/Workspace.tsx`. These two render the same rail and MUST
// show the same entries in the same order. They already drifted once — this
// file carried only Overview and New filmo while the studio also had Filmos
// and Assets, so the same product had two different navigations depending on
// which page you happened to be standing on, and Dennis found it immediately.
//
// The reasoning that produced the drift was that a rail names the places
// inside a surface, so different surfaces get different rails. That is wrong
// for THIS rail: it is the product's navigation, not the page's — the same
// argument Ploy's rail makes by being identical everywhere. Where you are
// changes what is highlighted, never what exists.
//
// The two files legitimately differ in ONE way and it is not the entry list:
// inside the studio, New filmo, Filmos and Film are SURFACES of the run you are
// already standing in (tabs — pressing one never leaves your film), while here
// there is no run to stay in, so the same entries are ROUTES: /new and /videos.
// Film is the exception that proves the rule — it names THIS run, and off a run
// there is no run for it to name, so it has no counterpart here. Same labels,
// same icons, same order; different mechanics. If you add an entry, add it in
// both.
//
// ── NEW FILMO: A ROUTE HERE, A TAB IN THE STUDIO (2026-07-19) ───────────────
// This entry used to link to `/?new=1` — the marketing landing, which then lays
// the composer over itself. From a rail that is otherwise pure navigation that
// is the wrong destination: you press a nav entry and arrive at the front door,
// with the rail gone and no way back to Overview / Filmos / Assets without
// abandoning what you came to do (Dennis, 2026-07-19: "take me directly to the
// chatbox, and not the landing page … i still want access to the overview,
// filmos and assets, so i can flip back and forth"). It points at `/new` now —
// the SAME composer with THIS rail beside it (app/new/page.tsx).
// `/?new=1` is untouched and still works: it is what "Build" means from the
// landing and from every empty-state CTA, and it stays the right door for
// someone with no overview to flip back to. A destination was added, not moved.
// Filmos already had exactly this shape — a route here, a tab in the studio —
// so New filmo joining it changes no entry, no label and no position.
//
// ── WHICH ENTRY IS LIT IS A PROP (2026-07-19) ───────────────────────────────
// This rail used to hardcode `on` + aria-current on Overview, because Overview
// was the only route that rendered it. /videos and /assets now render it too,
// and a rail that always claims you are on the Overview is worse than no
// marker at all — it is a wrong answer to "where am I". `current` therefore
// selects the lit entry and nothing else: the entry LIST and its ORDER are
// untouched and must stay that way (see the TWIN note above). It defaults to
// 'overview' so the Overview's own call site keeps working unchanged.
//
// ── AN ICON IS A CLAIM ABOUT THE ROOM (2026-07-19) ──────────────────────────
// Three of these glyphs described something other than what they open, and two
// of them were close to swapped:
//   · OVERVIEW wore a HOUSE, which says "home" — a position in a site map. This
//     page is not a homepage, it is everything you have at a glance, so it takes
//     the four-pane dashboard grid (the glyph Ploy uses for its own Overview,
//     and the one this rail was already spending on the wrong entry).
//   · FILMOS wore that grid. A grid says "dashboard", not "the films I made", so
//     the library of films now wears film. It gets the STRIP rather than the
//     Film tab's play-in-rect, because in the studio both entries stand in the
//     same rail: the play button means "watch THIS one", the strip means "the
//     body of work". Same visual language, two different claims, no collision.
//   · ASSETS wore a stacked diamond — the layers glyph, which claims nothing in
//     particular. Assets here are captures, marks, stills and recordings, i.e.
//     pictures, so it wears a stack of pictures.
// The plus on New filmo was already right and is untouched.
// Every glyph on this rail is inline, `viewBox="0 0 24 24"`, `strokeWidth="2"`,
// `fill="none"`, and identical to its twin in Workspace — a rail that shows one
// entry two ways in two places is the TWIN drift above wearing a costume.
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

/** The routes this rail can light — which, since the composer became `/new`, is
 *  every entry it carries. `new` was excluded while "New filmo" meant `/?new=1`:
 *  a rail cannot honestly mark you as standing on an entry when the click lands
 *  you on the marketing landing. Now it can, so it does. */
// 'none' is a real member, not an oversight. Some surfaces render this rail
// WITHOUT being one of its entries — /analytics is owner-only and deliberately
// has no rail item, but it is still an app surface and still needs the
// navigation beside it. Without 'none' such a page must either light a lie
// (omitting `current` defaults to 'overview', so the rail claims you are
// somewhere you are not) or cast its way out of the type, which is what
// /analytics was doing: `'analytics' as unknown as RailEntry`. A type that
// forces callers to lie is the bug, not the caller.
export type RailEntry = 'new' | 'overview' | 'filmos' | 'assets' | 'none'

export default function OverviewRail({ current = 'overview', getToken, onFeedback }: {
  /** The route the reader is standing on. Decides which entry is lit and which
   *  one carries aria-current; changes nothing else. */
  current?: RailEntry
  getToken: () => Promise<string | null>
  /** Opens the feedback sheet, which the page owns — the rail is the way in,
   *  not the surface. */
  onFeedback: () => void
}) {
  // One expression, used by every entry, so an entry can never be lit without
  // also announcing itself to a screen reader (or the reverse). New filmo joined
  // them when it became `/new` — it was the one entry that could not be lit, and
  // therefore the one entry that could quietly lose its aria-current.
  const at = (e: RailEntry) => ({
    className: 'ovrail-ic' + (current === e ? ' on' : ''),
    'aria-current': current === e ? ('page' as const) : undefined,
  })

  return (
    <nav className="ovrail" aria-label="Filmo">
      <div className="ovrail-brand" title="Filmo">
        <FilmoMark />
      </div>

      {/* The composer, as a place — `/new` is this rail beside the SAME
          NewFilmComposer the studio mounts (never a second copy of it: two
          composers that disagree about one createBuild parameter make two
          different films from the same URL, with no visible cause). `/?new=1`
          still exists and still means "go straight to the composer" for a
          visitor who has no rail to come back to; see the note at the top. */}
      <Link {...at('new')} href="/new" title="Start a new filmo">
        <svg viewBox="0 0 24 24" aria-hidden>
          <path d="M12 5v14M5 12h14" stroke="currentColor" strokeWidth="2" fill="none"
            strokeLinecap="round" />
        </svg>
        <i>New filmo</i>
      </Link>

      {/* Everything you have, at a glance — so, the dashboard grid, not a house.
          A house names a POSITION (home); the four panes name a VIEW. */}
      <Link {...at('overview')} href="/overview" title="Overview">
        <svg viewBox="0 0 24 24" aria-hidden>
          <rect x="3" y="4" width="8" height="7" rx="1.5" stroke="currentColor" strokeWidth="2" fill="none" />
          <rect x="13" y="4" width="8" height="7" rx="1.5" stroke="currentColor" strokeWidth="2" fill="none" />
          <rect x="3" y="13" width="8" height="7" rx="1.5" stroke="currentColor" strokeWidth="2" fill="none" />
          <rect x="13" y="13" width="8" height="7" rx="1.5" stroke="currentColor" strokeWidth="2" fill="none" />
        </svg>
        <i>Overview</i>
      </Link>

      {/* Every filmo this account has finished. Inside the studio this is a
          TAB (you stay in the run you are watching); from here there is no run
          to stay in, so it is the standalone library route. Same label, same
          icon, same place in the order — see the TWIN note at the top.
          The glyph is a FILM STRIP: the body of work. Its sibling in the studio,
          the Film tab, keeps the play-in-rect — that one means "watch this one",
          and the two must not wear the same picture while they share a rail. */}
      <Link {...at('filmos')} href="/videos" title="Filmos you've made">
        <svg viewBox="0 0 24 24" aria-hidden>
          <rect x="3" y="5" width="18" height="14" rx="2" stroke="currentColor" strokeWidth="2" fill="none" />
          <path d="M7.5 5v14M16.5 5v14M3 12h4.5M16.5 12H21" stroke="currentColor" strokeWidth="2" fill="none" />
        </svg>
        <i>Filmos</i>
      </Link>

      {/* The raw material: captures, marks, recordings, stills. A route in both
          rails — it spans every run, so it never belonged to one.
          Those things are PICTURES, so the glyph is a stack of them: one sheet
          behind, one framed image in front. The old stacked diamond said
          "layers", which is true of almost anything. */}
      <Link {...at('assets')} href="/assets" title="Everything captured and made for your filmos">
        <svg viewBox="0 0 24 24" aria-hidden>
          <path d="M17 20.5H5.5A2 2 0 0 1 3.5 18.5V7" stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round" />
          <rect x="7" y="3.5" width="14" height="14" rx="2" stroke="currentColor" strokeWidth="2" fill="none" />
          <circle cx="11.5" cy="8" r="1.5" stroke="currentColor" strokeWidth="2" fill="none" />
          <path d="m8 15.5 3.5-3.5 2 2 2.5-2.5 4 4" stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        <i>Assets</i>
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
