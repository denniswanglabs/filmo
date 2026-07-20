'use client'
// ── THE OVERVIEW'S RAIL ─────────────────────────────────────────────────────
// ⚠ TWIN: `runs/[id]/Workspace.tsx`. These two render the same rail and MUST
// show the SAME ENTRIES IN THE SAME ORDER: New filmo, Overview, Filmos, Assets.
// They already drifted once — this file carried only Overview and New filmo
// while the studio also had Filmos and Assets, so the same product had two
// different navigations depending on which page you happened to be standing on,
// and Dennis found it immediately.
//
// The reasoning that produced the drift was that a rail names the places
// inside a surface, so different surfaces get different rails. That is wrong
// for THIS rail: it is the product's navigation, not the page's — the same
// argument Ploy's rail makes by being identical everywhere. Where you are
// changes what is highlighted, never what exists.
//
// The two files legitimately differ in ONE way and it is not the entry list:
// inside the studio, New filmo is a SURFACE of the run you are already standing
// in (a tab — pressing it never leaves your film), while here there is no run to
// stay in, so it is a ROUTE, /new. Same label, same icon, same order; different
// mechanic. If you add an entry, add it in both.
//
// ── FOUR ENTRIES NOW, NOT FIVE-PLUS (2026-07-20) ────────────────────────────
// There used to be more here. A separate Film tab named THE current run (studio
// only), and a separate live-film entry sat at the foot of BOTH rails naming the
// runs happening in the background. Three slots — Film, Filmos, live-film — were
// three answers to one question, "your films", free to disagree; and the studio
// spent a whole rail row on a Film button the run did not need (Dennis,
// 2026-07-20: a current run "doesn't need a designated film button, it can be
// integrated into the filmo button"). So Filmos ABSORBED both. It is the library
// door AND the live indicator: it pulses while a film is filming, counts when two
// are, shows a ready mark until a delivered film is opened, and inside the studio
// it is the lit entry standing in for the film you are watching. The Film tab and
// the sibling live-film slot are gone from both rails.
//
// ── THE ONE ENTRY THAT CANNOT DRIFT ─────────────────────────────────────────
// "Add it in both" is the rule above, and it is a rule enforced by whoever
// remembers it — which is exactly how this rail drifted the first time, and how
// the Overview glyph ended up drawn from two different SVG paths that looked
// identical and had already diverged in source. The Filmos entry, now that it
// carries state, motion and four visual conditions, is therefore not added in
// both. It is WRITTEN ONCE, in components/rail/FilmosEntry, and imported here and
// by Workspace with only presentation flags differing, so there is no second copy
// that could disagree. Anything stateful added to this rail from now on should go
// the same way: the twin contract is far easier to keep when there is only one
// thing to keep.
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
//     the library of films wears a FILM STRIP — the body of work. It once had to
//     avoid the Film tab's play-in-rect, but that tab is gone (Filmos absorbed
//     it), so the strip stands alone; the live state rides as a small badge on it
//     rather than as a competing glyph, which is why the silhouette never changes.
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
// ── THE FILMOS ENTRY, LIBRARY AND LIVE INDICATOR IN ONE ─────────────────────
// IMPORTED, NOT COPIED — and this is the entry where that matters most. Every
// other entry on this rail is a static glyph and a href, so a drift between the
// twins is visible the moment someone looks at both. This one carries state,
// motion and four visual conditions; two copies of it would agree on the day
// they were written and quietly diverge on the first fix to either. It lives in
// components/rail/FilmosEntry and Workspace imports the SAME file — the two rails
// pass only presentation flags (`lit`, and the studio's accent `bar`).
// It takes `getToken` — which this rail already had — and fetches its own live
// state, so no page that renders this rail needed a new prop for it.
import FilmosEntry from '../rail/FilmosEntry'

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
      {/* THE MARK IS THE WAY HOME. Clicking it leaves for the landing at `/` —
          which stays the landing for signed-in visitors by standing rule, so
          this is a genuine exit, not a loop. Matches the /login lockup's pattern
          (Dennis, 2026-07-20). Keeps its size and colour; gains the standard
          focus ring, because a chrome-less mark that is now a link must still be
          findable by a keyboard. */}
      <Link className="ovrail-brand" href="/" aria-label="Back to the Filmo landing page">
        <FilmoMark />
      </Link>

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

      {/* Every filmo this account has, live or finished — the library door AND
          the live indicator, folded into one (see FilmosEntry). It links to
          /videos, wears the FILM STRIP, pulses while a film is filming, counts
          when several are, and shows a ready mark until a delivered film is
          opened. `lit` when the reader is on /videos; off-run it takes no accent
          bar, only the darker ink — so `bar` is omitted here. Same label, same
          icon, same place in the order as the studio's — see the TWIN note. */}
      <FilmosEntry lit={current === 'filmos'} getToken={getToken} />

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

      {/* The live-film indicator used to sit here, last, as its own entry that
          came and went. It is gone: its states fold INTO the Filmos entry above
          (pulse, count, ready mark), so a running film is shown where the library
          is rather than in a slot of its own — and the rail no longer reshuffles
          itself the moment a film starts, because nothing here appears or leaves. */}
      <div className="ovrail-space" />

      <AccountMenu getToken={getToken} onFeedback={onFeedback} />

      <style>{`
        .ovrail { flex:0 0 72px; display:flex; flex-direction:column;
          align-items:center; gap:18px; padding:16px 0;
          border-right:1px solid #E6E6E3; }
        .ovrail-brand { width:40px; height:40px; display:flex;
          align-items:center; justify-content:center; text-decoration:none;
          border-radius:10px; }
        .ovrail-brand svg { width:34px; height:34px; display:block; }
        /* The mark is a link now; chrome-less is a look, not a licence. */
        .ovrail-brand:focus-visible { outline:2px solid #3B82F6;
          outline-offset:4px; }
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
