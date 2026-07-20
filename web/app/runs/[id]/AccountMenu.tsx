'use client'
// ── THE FOOT OF THE RAIL: THE PERSON, NOT THE WORK ──────────────────────────
// Everything above this on the rail is a place in the studio. This is not a
// place — it is who is standing in it, what they have left to spend, and the
// two acts that belong to a person rather than to a filmo: telling us something
// is broken, and leaving. So it is a round initial pinned to the bottom-left
// (Ploy's shape), and one card that opens beside it.
//
// Ported from the approved prototype `landing-lab/studio.html` (.wsmenu /
// .credits / .crow / .clabel / .bar / .cnote), with ONE deliberate departure:
// the prototype parks the card in the DOM at opacity:0 and toggles a class.
// An invisible card whose buttons are still in the tab order is a keyboard trap
// with no visible cursor — three controls a sighted user cannot see and a
// keyboard user cannot escape. This renders the card only while it is open, so
// "closed" means gone rather than merely transparent.
import { useCallback, useEffect, useId, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '../../../lib/auth'
import { getCredits } from '../../actions'

// The operator account. Four copies of this string exist (actions.ts,
// Brand.tsx, FloatingNav.tsx, here) and only the SERVER's is a boundary —
// `getCredits` decides `unlimited` itself and this file never gets to vote.
// This copy decides one thing: which word the chrome prints.
const OWNER_EMAIL = 'denniswanglabs@gmail.com'

// ── AN EMAIL NEVER REACHES THE CHROME ───────────────────────────────────────
// Same rule and same order of preference as the landing nav and the run-page
// TopBar: the operator shows a first name so a screen-recording never exposes
// the handle, everyone else shows a real name when we have one and the
// local-part when we don't. The @domain has no path to the screen from here.
function displayName(user: { email?: string; [k: string]: unknown }): string {
  if ((user.email || '').toLowerCase() === OWNER_EMAIL) return 'Dennis'
  const meta = user.user_metadata as Record<string, unknown> | undefined
  const name =
    (user.name as string) ||
    (user.full_name as string) ||
    (meta?.full_name as string) ||
    (meta?.name as string)
  if (typeof name === 'string' && name.trim()) return name.trim()
  const email = user.email || ''
  return email.split('@')[0] || email
}

/** The shape `getCredits` returns on success — the server owns every number. */
type Credits = {
  dailyUsed: number; dailyCap: number
  lifetimeUsed: number; lifetimeCap: number
  videoCost: number; editCost: number; unlimited: boolean
}

const fmt = (n: number) => Math.max(0, Math.round(n)).toLocaleString()

// A neutral stand-in for a name we don't have. The workspace only mounts for a
// signed-in user, so this is defensive — but the defence has to be a shape that
// claims nothing, not a letter that claims the wrong thing. ('Account' would
// badge every nameless user 'A'.)
function AnonFace() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden>
      <circle cx="12" cy="9" r="3.4" stroke="currentColor" strokeWidth="2" fill="none" />
      <path d="M5.5 19.5a6.5 6.5 0 0 1 13 0" stroke="currentColor" strokeWidth="2"
        fill="none" strokeLinecap="round" />
    </svg>
  )
}

export default function AccountMenu({ getToken, onFeedback }: {
  getToken: () => Promise<string | null>
  /** Opens the feedback sheet, which the workspace owns — this menu is the
   *  entry point, not the surface. */
  onFeedback: () => void
}) {
  const { user, signOut } = useAuth()
  const router = useRouter()
  const [open, setOpen] = useState(false)
  const [credits, setCredits] = useState<Credits | null>(null)
  // A balance we could not read is not a balance of zero. This flag exists so
  // the card can say so plainly instead of rendering an empty bar that looks
  // like a spent allowance.
  const [failed, setFailed] = useState(false)
  const wrapRef = useRef<HTMLDivElement>(null)
  const btnRef = useRef<HTMLButtonElement>(null)
  const menuId = useId()

  const name = user ? displayName(user) : ''
  const initial = name.trim().charAt(0).toUpperCase()

  // Closing by keyboard hands the caret back to the button that opened the
  // card; closing by clicking elsewhere must NOT, because the user has already
  // chosen where they want to be and yanking focus back to the rail would undo
  // the click they just made.
  const close = useCallback((refocus: boolean) => {
    setOpen(false)
    if (refocus) btnRef.current?.focus()
  }, [])

  // ── DISMISSIBLE, NOT INESCAPABLE ──────────────────────────────────────────
  // Escape closes it, a click anywhere outside closes it, and Tab walks
  // straight out of it: the card sits immediately after its trigger in the DOM,
  // so the tab order runs trigger → Feedback → Sign out → the rest of the page
  // with nothing looping it back. There is no focus trap and no aria-modal,
  // because this is a disclosure hanging off a button, not a dialog that owns
  // the screen.
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') close(true) }
    const onDown = (e: MouseEvent) => {
      if (!wrapRef.current?.contains(e.target as Node)) close(false)
    }
    window.addEventListener('keydown', onKey)
    window.addEventListener('mousedown', onDown)
    return () => {
      window.removeEventListener('keydown', onKey)
      window.removeEventListener('mousedown', onDown)
    }
  }, [open, close])

  // The balance is read when the card is first opened, not on every mount: the
  // rail is on screen for the whole life of a run and a credits read is a
  // round-trip nobody asked for until they look.
  useEffect(() => {
    if (!open || credits || failed) return
    let stop = false
    ;(async () => {
      try {
        const res = await getCredits((await getToken()) || '')
        if (stop) return
        if ('error' in res) setFailed(true)
        else setCredits(res)
      } catch {
        if (!stop) setFailed(true)
      }
    })()
    return () => { stop = true }
  }, [open, credits, failed, getToken])

  const left = credits ? Math.max(0, credits.dailyCap - credits.dailyUsed) : 0
  const pct = credits && credits.dailyCap > 0
    ? Math.max(0, Math.min(100, Math.round((left / credits.dailyCap) * 100)))
    : 0

  return (
    <div className="wkacct" ref={wrapRef}>
      <button
        ref={btnRef}
        className={'wkacct-btn' + (open ? ' on' : '')}
        onClick={() => (open ? close(true) : setOpen(true))}
        aria-expanded={open}
        aria-controls={menuId}
        title="Account, credits and feedback"
      >
        <span className="wkacct-face" aria-hidden>{initial || <AnonFace />}</span>
        <span className="wkacct-sr">{name ? `Account — ${name}` : 'Account'}</span>
      </button>

      {open ? (
        <div className="wkacct-menu" id={menuId} role="group" aria-label="Account">
          <div className="wkacct-head">
            <div className="wkacct-face big" aria-hidden>{initial || <AnonFace />}</div>
            <div className="wkacct-who">
              <b>{name || 'Your workspace'}</b>
              <span>Filmo Studio</span>
            </div>
          </div>

          <div className="credits">
            <div className="crow"><b>Credits</b><span className="free">Free while in beta</span></div>
            {credits ? (
              credits.unlimited ? (
                <>
                  <div className="clabel"><span>Unlimited</span><span>owner account</span></div>
                  <div className="bar"><i style={{ width: '100%' }} /></div>
                </>
              ) : (
                <>
                  <div className="clabel">
                    <span>{fmt(left)} left today</span>
                    <span>of {fmt(credits.dailyCap)}</span>
                  </div>
                  <div
                    className="bar"
                    role="progressbar"
                    aria-label="Credits left today"
                    aria-valuemin={0}
                    aria-valuemax={credits.dailyCap}
                    aria-valuenow={left}
                  >
                    <i style={{ width: `${pct}%` }} />
                  </div>
                </>
              )
            ) : failed ? (
              /* Honest about the gap rather than confident about a number we
                 do not have. An empty bar here would read as "you're out". */
              <div className="clabel"><span>Balance unavailable right now</span></div>
            ) : (
              <div className="wkacct-skel" aria-hidden />
            )}
            {/* The prototype's words, kept exactly: what the meter measures,
                when it turns over, and what happens when we waste your money.
                No film count, no end date — neither is a promise this product
                is in a position to make. */}
            <div className="cnote">
              Credits are metered on the work itself — a filmo costs more than a
              re-cut. They refresh every morning; failed builds are refunded.
            </div>
          </div>

          <div className="wkacct-acts">
            <button
              className="wkacct-item"
              onClick={() => {
                // Hand focus back to the trigger BEFORE the card unmounts, so
                // the sheet's own "return the keyboard where it was" capture
                // lands on a node that still exists.
                btnRef.current?.focus()
                setOpen(false)
                onFeedback()
              }}
            >
              <svg viewBox="0 0 24 24" aria-hidden>
                <rect x="2.5" y="5" width="19" height="14" rx="2.5" stroke="currentColor" strokeWidth="2" fill="none" />
                <path d="M3.5 7l8.5 6 8.5-6" stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              Send feedback
            </button>
            <button
              className="wkacct-item"
              onClick={async () => {
                setOpen(false)
                await signOut()
                router.push('/login')
              }}
            >
              <svg viewBox="0 0 24 24" aria-hidden>
                <path d="M10 4H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h4" stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round" />
                <path d="M16 8l4 4-4 4M20 12H9" stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              Sign out
            </button>
          </div>
        </div>
      ) : null}

      <style>{`
        /* Deliberately NOT a positioning context: the card hangs off the RAIL
           (.wk-iconrail is position:relative for exactly this, and says so),
           not off a 34px button whose width would then decide the card's x.
           If that ever regresses the card falls back to .wk-root — which is
           position:fixed at the viewport's top-left, where the rail also is —
           so the failure mode is a few pixels, not a card off-screen. */
        .wkacct { position:static; display:flex; justify-content:center; }
        .wkacct-btn { border:none; background:none; padding:0; cursor:pointer;
          border-radius:50%; display:block; }
        .wkacct-face { width:34px; height:34px; border-radius:50%;
          background:#1B1B1A; color:#fff; display:flex; align-items:center;
          justify-content:center; font:600 14px/1 Inter,-apple-system,sans-serif;
          letter-spacing:.01em; }
        .wkacct-face svg { width:20px; height:20px; }
        .wkacct-face.big { width:42px; height:42px; font-size:16.5px;
          flex-shrink:0; }
        .wkacct-btn:hover .wkacct-face, .wkacct-btn.on .wkacct-face {
          box-shadow:0 0 0 3px #E6E6E3; }
        /* The rail is chrome-less by design; that is a look, not a licence.
           Every control on it states its own focus (see the note beside
           .wk-ic:focus-visible in Workspace). */
        .wkacct-btn:focus-visible { outline:2px solid #3B82F6; outline-offset:4px; }
        /* The circle shows a letter; the button still has to SAY what it is. */
        .wkacct-sr { position:absolute; width:1px; height:1px; padding:0;
          margin:-1px; overflow:hidden; clip:rect(0 0 0 0); white-space:nowrap;
          border:0; }

        .wkacct-menu { position:absolute; left:80px; bottom:16px; z-index:70;
          width:330px; background:#fff; border-radius:16px; padding:16px;
          text-align:left; color:#1B1B1A;
          box-shadow:0 1px 2px rgba(0,0,0,.05), 0 30px 70px -25px rgba(0,0,0,.3);
          animation:wkacct-rise .22s cubic-bezier(.22,1,.36,1) both; }
        .wkacct-head { display:flex; gap:12px; align-items:center;
          padding:4px 4px 16px; }
        .wkacct-who { min-width:0; }
        .wkacct-who b { display:block; font-size:15.5px; font-weight:650;
          white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
        .wkacct-who span { font-size:13px; color:#8A8A86; }

        /* ── THE PROTOTYPE'S CLASS NAMES, NOT ITS GLOBAL REACH ────────────────
           These keep the prototype's names (.credits / .crow / .clabel / .bar
           / .cnote) so the port stays traceable to studio.html, but every one
           is scoped under .wkacct-menu. This is a plain <style> tag, not a
           module: an unscoped rule named .bar or .free is a global rule, and
           this component mounts inside an app whose other surfaces nobody is
           checking against a six-word vocabulary. Nothing collides today; the
           scope is what stops that from being load-bearing. */
        .wkacct-menu .credits { border:1px solid #E6E6E3; border-radius:12px;
          padding:16px; }
        .wkacct-menu .crow { display:flex; justify-content:space-between;
          align-items:baseline; margin-bottom:14px; }
        .wkacct-menu .crow b { font-size:15px; font-weight:650; }
        .wkacct-menu .free { font-size:12px; color:#3B82F6; font-weight:600; }
        .wkacct-menu .clabel { display:flex; justify-content:space-between;
          font-size:13px; color:#8A8A86; margin-bottom:6px; gap:10px; }
        .wkacct-menu .clabel span:first-child { color:#1B1B1A; font-weight:500; }
        .wkacct-menu .bar { height:6px; border-radius:3px; background:#EDEDEA;
          overflow:hidden; }
        .wkacct-menu .bar i { display:block; height:100%; border-radius:3px;
          background:#3B82F6; }
        /* Unknown reads as neutral, never as empty: the same rule the canvas
           follows before the run has reported in. */
        .wkacct-skel { height:6px; border-radius:3px; background:#EDEDEA; }
        .wkacct-menu .cnote { margin-top:14px; font-size:11.5px; line-height:1.45;
          color:#B6B6B2; }

        .wkacct-acts { margin-top:8px; }
        .wkacct-item { display:flex; align-items:center; gap:10px; width:100%;
          border:none; background:none; cursor:pointer; text-align:left;
          padding:10px 10px; border-radius:10px; color:#1B1B1A;
          font:13.5px/1.4 Inter,-apple-system,sans-serif; }
        .wkacct-item svg { width:18px; height:18px; flex-shrink:0; color:#8A8A86; }
        .wkacct-item:hover { background:#F5F5F3; }
        .wkacct-item:focus-visible { outline:2px solid #3B82F6; outline-offset:-2px; }

        @keyframes wkacct-rise {
          from { opacity:0; transform:translateY(6px) scale(.98); }
          to { opacity:1; transform:none; } }
        @media (prefers-reduced-motion:reduce) {
          .wkacct-menu { animation:none; } }
      `}</style>
    </div>
  )
}
