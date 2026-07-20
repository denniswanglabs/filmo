'use client'
// ── THE SHELL BOTH LIBRARIES WEAR ───────────────────────────────────────────
// /videos and /assets are SIBLING surfaces. The rail lists them side by side,
// one line apart, so a reader crosses between them in a single click and any
// difference in chrome reads as a bug rather than a design. They used to have
// exactly that problem in the other direction: both wore the old blue landing
// shell (FloatingNav + SiteFooter + LandingBackdrop) while the Overview had
// already moved to the studio ground, so the product had two visual languages
// depending on which entry of the SAME rail you pressed.
//
// The fix is not "make the two pages look similar". It is this file: there is
// ONE shell, both pages render inside it, and matching is therefore not
// something anybody has to remember. A page supplies its title, its lede and
// its content; everything else — ground, rail, measure, head, the feedback
// sheet, and every shared class its children style themselves with — is here.
//
// THREE THINGS ARE LOAD-BEARING, and all three are borrowed from the Overview
// rather than reinvented (app/overview/page.tsx documents them at length):
//
// 1. IT IS A FIXED SHELL, PORTALLED. `app/template.tsx` wraps every route in a
//    framer-motion div, and a position:fixed child of a TRANSFORMED ancestor is
//    positioned against that ancestor, not the viewport. Rendering into
//    document.body is what makes `inset:0` mean the screen. The body then never
//    scrolls — the stage does — at 1440 or at 390.
//
// 2. THE RAIL IS THE PRODUCT'S NAVIGATION, NOT THE PAGE'S. It is imported, not
//    copied (see the TWIN note in OverviewRail): same entries, same order, on
//    every surface. Only `current` differs, and only to light the entry you are
//    standing on.
//
// 3. WHOEVER RENDERS THE RAIL OWNS THE FEEDBACK SHEET. The rail's account
//    circle is the way IN to feedback; the sheet itself has to belong to a
//    surface that outlives the click. That surface is this one, so neither page
//    has to wire it and neither page can forget to.
import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import FeedbackModal from '../../runs/[id]/FeedbackModal'
import OverviewRail, { type RailEntry } from '../overview/OverviewRail'

export default function LibraryShell({
  current, title, lede, context, getToken, children,
}: {
  /** Which rail entry to light. */
  current: RailEntry
  title: string
  lede: React.ReactNode
  /** The route, verbatim, for the feedback sheet — "this is broken" is only
   *  actionable if it says where the reader was standing. */
  context: string
  getToken: () => Promise<string | null>
  children: React.ReactNode
}) {
  const [mounted, setMounted] = useState(false)
  const [fbOpen, setFbOpen] = useState(false)
  useEffect(() => setMounted(true), [])

  // The portal has nowhere to go until there is a document. The route-level
  // loading.tsx covers the gap before this paints.
  if (!mounted) return null

  return createPortal(
    <div className="lib-root">
      <OverviewRail current={current} getToken={getToken} onFeedback={() => setFbOpen(true)} />

      <main className="lib-stage">
        <div className="lib-inner">
          <header className="lib-head">
            <h1 className="lib-title">{title}</h1>
            <p className="lib-lede">{lede}</p>
          </header>
          {children}
        </div>
      </main>

      <FeedbackModal
        open={fbOpen}
        onClose={() => setFbOpen(false)}
        getToken={getToken}
        context={context}
      />

      <style>{`
        .lib-root { position:fixed; inset:0; display:flex; background:#F1F1EF;
          color:#1B1B1A; font:14px/1.5 Inter,-apple-system,sans-serif; z-index:50; }
        /* The stage scrolls, the shell does not. */
        .lib-stage { flex:1 1 0; min-width:0; min-height:0; overflow-y:auto;
          overflow-x:hidden; }
        .lib-inner { max-width:1120px; margin:0 auto; padding:38px 32px 56px; }
        .lib-head { margin-bottom:26px; }
        .lib-title { margin:0; font-size:32px; font-weight:600;
          letter-spacing:-.025em; line-height:1.15; color:#1B1B1A; }
        .lib-lede { margin:9px 0 0; max-width:62ch; font-size:14.5px;
          line-height:1.55; color:#8A8A86; }

        /* ── THE TOOLBAR: WHAT THIS VIEW IS SHOWING, AND HOW TO RE-READ IT ──
           A count that follows the filter, and the manual refresh both pages
           carried before this rebuild and still need — these lists are read
           once on mount, and a filmo that finished while you were looking at
           the page will not appear on its own. */
        .lib-toolbar { display:flex; align-items:center; justify-content:space-between;
          gap:12px; margin:0 0 12px; flex-wrap:wrap; }
        .lib-count { font-size:12px; font-weight:600; letter-spacing:.08em;
          text-transform:uppercase; color:#8A8A86; }
        .lib-refresh { border:1px solid #E6E6E3; background:#fff; border-radius:99px;
          padding:6px 14px; font:12.5px/1 Inter,-apple-system,sans-serif;
          color:#6E6E6A; cursor:pointer;
          transition:background-color .15s, border-color .15s, color .15s; }
        .lib-refresh:hover { background:#F5F5F3; border-color:#C9C9C4; color:#1B1B1A; }
        .lib-refresh:focus-visible { outline:2px solid #3B82F6; outline-offset:3px; }
        /* Lives here rather than on the one page that has a search box today,
           for the same reason everything else in this file does: if the other
           library grows one, it is already the same control. */
        .lib-search { flex:1 1 220px; min-width:0; max-width:340px;
          border:1px solid #E6E6E3; background:#fff; border-radius:99px;
          padding:8px 15px; font:13px/1.3 Inter,-apple-system,sans-serif;
          color:#1B1B1A; outline:none;
          transition:border-color .15s, box-shadow .15s; }
        .lib-search::placeholder { color:#B6B6B2; }
        .lib-search:hover { border-color:#C9C9C4; }
        .lib-search:focus-visible { border-color:#3B82F6;
          box-shadow:0 0 0 3px rgba(59,130,246,.18); }

        /* ── A TILE IS SIZED BY ITS CONTENT ─────────────────────────────────
           The max-content on auto rows below is not a nicety. Auto rows in a grid
           that has been given a definite height are free to compress BELOW
           their content: the studio's library did exactly that (rows fell
           331px → 187px), which pushed every card's label block past its own
           overflow:hidden edge. The labels were in the DOM, laid out, and
           invisible — the library read as a wall of blank black rectangles and
           inspecting the markup said it was fine. Rows size to content and the
           list scrolls; rows never shrink. */
        .lib-grid { list-style:none; margin:0; padding:0; display:grid;
          grid-template-columns:repeat(auto-fill, minmax(196px, 1fr));
          gap:16px; align-content:start; grid-auto-rows:max-content; }
        .lib-grid.lg { grid-template-columns:repeat(auto-fill, minmax(280px, 1fr));
          gap:18px; }

        /* ── THE GATES ──────────────────────────────────────────────────────
           Signed out, stale-token and read-failed all land here. None of them
           is an empty library, and none of them may be dressed as one. */
        .lib-gate { background:#fff; border:1px solid #E6E6E3; border-radius:14px;
          padding:26px; display:flex; flex-direction:column; gap:7px;
          align-items:flex-start; max-width:520px; }
        .lib-gate b { font-size:16px; font-weight:650; }
        .lib-gate span { font-size:13.5px; line-height:1.55; color:#6E6E6A; }
        .lib-gatebtn { margin-top:10px; display:inline-flex; align-items:center;
          justify-content:center; border:1px solid #1B1B1A; background:#1B1B1A;
          color:#fff; border-radius:99px; padding:9px 20px;
          font:13px/1 Inter,-apple-system,sans-serif; cursor:pointer;
          text-decoration:none; }
        .lib-gatebtn:hover { background:#000; border-color:#000; }
        .lib-gatebtn:focus-visible { outline:2px solid #3B82F6; outline-offset:3px; }

        /* An account with nothing in it is a first-class state, not an error:
           dashed rather than solid, and it says what would fill it. */
        .lib-empty { background:#fff; border:1px dashed #DDDDD9; border-radius:14px;
          padding:22px; display:flex; flex-direction:column; gap:7px;
          align-items:flex-start; }
        .lib-empty b { font-size:15px; font-weight:650; color:#1B1B1A; }
        .lib-empty span { font-size:13.5px; line-height:1.55; color:#6E6E6A;
          max-width:52ch; }
        .lib-emptycta { margin-top:8px; display:inline-flex; align-items:center;
          justify-content:center; background:#1B1B1A; border:1px solid #1B1B1A;
          color:#fff; border-radius:99px; padding:9px 20px;
          font:13px/1 Inter,-apple-system,sans-serif; text-decoration:none; }
        .lib-emptycta:hover { background:#000; border-color:#000; }
        .lib-emptycta:focus-visible { outline:2px solid #3B82F6; outline-offset:3px; }

        @media (max-width:760px) {
          .lib-inner { padding:26px 18px 44px; }
          .lib-title { font-size:26px; }
          .lib-lede { font-size:13.5px; }
          .lib-grid { grid-template-columns:repeat(auto-fill, minmax(150px, 1fr));
            gap:12px; }
          .lib-grid.lg { grid-template-columns:minmax(0, 1fr); gap:14px; } }
      `}</style>
    </div>,
    document.body,
  )
}
