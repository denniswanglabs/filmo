'use client'
// ═══════════════════════ /login — THE DOOR ═══════════════════════════════════
//
// A FULL-BLEED SPLIT, not a card floating on an empty field. The page is one
// grid, edge to edge, 55/45: the left panel is the brand and the right panel is
// the whole sign-in flow. Nothing here is centred in a void — the door is the
// size of the doorway.
//
// LEFT — THE SCREENING ROOM. Ground is the landing's night (#0A0A0B) because
// the plate behind it is night: `public/landing/hero-poster.jpg` is a page we
// actually filmed, the same frame `landing2/PloyLanding` runs its hero on, and
// it is treated with that hero's exact grammar — `saturate(.72) contrast(.92)
// brightness(.44) blur(2px)` under a centre-weighted radial scrim. It is real
// material, muted until it is texture rather than a claim. NOT an invented 3D
// blob, and NOT `hero.mp4`: a still costs 208KB, is already in cache for anyone
// who arrived from the landing (which ships it as that video's poster), is
// never fetched at all on mobile, and cannot compete with the form for
// attention. The display face is PloyLanding's verbatim, so the door and the
// landing speak in one voice.
//
// RIGHT — THE STUDIO'S DAYLIGHT. #F1F1EF with a white card on it, because that
// is the ground of the screen a successful sign-in produces. Half the page is
// already the boot screen's colour before you press anything.
//
// THE LOCKUP IS THE BOOT SCREEN'S, TO THE PIXEL — 50px mark, 38px word, 11px
// gap, -.022em (`landing2/BootScreen`, `runs/[id]/loading.tsx`). Its ink flips
// to #F1F1EF on the night panel, which is not a new colour: it is exactly what
// `FilmoLoader.inkFor()` returns for a dark ground. Signing in dissolves into
// the boot screen rather than resizing into it. Below 900px the art is dropped
// and the same lockup reappears above the form in dark ink at FilmoLoader's
// sanctioned `compact` ratio (34/26/8).
//
// IT DOES NOT GET THE RAIL, AND THAT IS THE POINT. The rail is the product's
// navigation — Overview, Filmos, Assets, your account. Every one of those is a
// place inside a session that does not exist yet. A 72px column of destinations
// nobody can reach is furniture for a room you have not entered, so the door
// gets the brand and the form and nothing else.
//
// EVERY BEHAVIOUR HERE IS THE ONE THAT WAS HERE BEFORE. The already-signed-in
// redirect, the Google path, password sign-in and sign-up, the mode toggle, the
// failed-password nudge toward Google, the e-mail verification fallback, the
// loader that stands in for a form nobody signed-in should see, and every
// `autoComplete` the browser's password manager reads — all unchanged. Only the
// surface and the order are new: fields → primary → "or" → Google, which is the
// order of the sign-in this was modelled on.
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { insforge } from '../../lib/insforge'
import { useAuth } from '../../lib/auth'
import FilmoMark from '../components/landing2/FilmoMark'
import FilmoLoader, { GROUND_STUDIO } from '../components/FilmoLoader'

type Mode = 'signin' | 'signup'

export default function LoginPage() {
  const router = useRouter()
  const { user, loading, refresh, signInWithGoogle } = useAuth()
  const [mode, setMode] = useState<Mode>('signin')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // Google-only accounts have no password in InsForge (and no reset flow) — a failed
  // password sign-in nudges toward Google. Provider isn't knowable client-side.
  const [showGoogleHint, setShowGoogleHint] = useState(false)
  // Verification fallback (only used if the project still requires email verification)
  const [needsCode, setNeedsCode] = useState(false)
  const [code, setCode] = useState('')

  // Already signed in → go home.
  useEffect(() => {
    if (!loading && user) router.replace('/')
  }, [loading, user, router])

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setShowGoogleHint(false)
    setBusy(true)
    try {
      if (mode === 'signup') {
        const { data, error } = await insforge.auth.signUp({
          email,
          password,
          name: name || email.split('@')[0],
        })
        if (error) throw new Error(error.message || 'Sign up failed')
        if (data?.requireEmailVerification) {
          setNeedsCode(true)
          return
        }
        // Verification off → session is live.
        await refresh()
        router.replace('/')
        return
      }
      // sign in
      const { error } = await insforge.auth.signInWithPassword({ email, password })
      if (error) {
        setShowGoogleHint(true)
        throw new Error(error.message || 'Sign in failed')
      }
      await refresh()
      router.replace('/')
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  async function onVerify(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setShowGoogleHint(false)
    setBusy(true)
    try {
      const { error } = await insforge.auth.verifyEmail({ email, otp: code })
      if (error) throw new Error(error.message || 'Invalid or expired code')
      await refresh()
      router.replace('/')
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  // ── NOBODY IS SHOWN A DOOR THEY ARE ALREADY THROUGH ─────────────────────────
  // While the session is resolving, and for the frame between "there is a user"
  // and the redirect above actually landing, this is the loader rather than a
  // sign-in form. The redirect is unchanged; what changed is that it no longer
  // flashes a form at somebody who is signed in. Never a bare "Loading…".
  if (loading || user) {
    return (
      <FilmoLoader
        ground={GROUND_STUDIO}
        size="compact"
        label={user ? 'Signing you in' : 'Loading'}
      />
    )
  }

  return (
    <main className="lgn-root">
      {/* ── LEFT: the brand, on real footage ─────────────────────────────── */}
      <aside className="lgn-art">
        {/* A page Filmo actually filmed, muted until it is texture. It is a CSS
            BACKGROUND rather than an <img>, and that is load-bearing — see the
            note on .lgn-plate. Purely decorative, so it carries no alt text and
            no place in the a11y tree. */}
        <div className="lgn-plate" aria-hidden="true" />
        <div className="lgn-scrim" aria-hidden="true" />

        <div className="lgn-lockup lgn-lockup-art">
          <FilmoMark />
          <span>Filmo</span>
        </div>

        <div className="lgn-say">
          <h2 className="lgn-display">
            The studio is open.
            <br />
            Give it a link.
          </h2>
          <p className="lgn-fine">
            Free while Filmo is in beta — 3,000 credits a day, no card to add.
          </p>
        </div>
      </aside>

      {/* ── RIGHT: the whole sign-in flow, on the studio's daylight ───────── */}
      <div className="lgn-form-col">
        <div className="lgn-cardwrap">
          {/* The art panel carries the lockup on a wide screen; below 900px it
              is gone, so the brand reappears here at FilmoLoader's `compact`
              ratio. Only ever one of the two is in the layout. */}
          <div className="lgn-lockup lgn-lockup-form">
            <FilmoMark />
            <span>Filmo</span>
          </div>

          <div className="lgn-card">
            {needsCode ? (
              <form onSubmit={onVerify} className="lgn-form">
                <div>
                  <h1 className="lgn-h1">Check your email</h1>
                  <p className="lgn-sub">
                    Enter the 6-digit code we sent to {maskEmail(email)}.
                  </p>
                </div>
                <input
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  autoFocus
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                  placeholder="123456"
                  aria-label="Six-digit verification code"
                  className="lgn-input lgn-code"
                />
                {error && (
                  <p className="lgn-error" role="alert">
                    {error}
                  </p>
                )}
                <button disabled={busy} className="lgn-primary">
                  {busy ? 'Verifying…' : 'Verify & continue'}
                </button>
              </form>
            ) : (
              <form onSubmit={onSubmit} className="lgn-form">
                <div>
                  <h1 className="lgn-h1">
                    {mode === 'signin' ? 'Welcome back' : 'Create your account'}
                  </h1>
                  <p className="lgn-sub">
                    {mode === 'signin'
                      ? 'Your films are where you left them.'
                      : 'Start turning URLs into finished videos.'}
                  </p>
                </div>

                {mode === 'signup' && (
                  <Field
                    label="Name"
                    value={name}
                    onChange={setName}
                    type="text"
                    placeholder="Ada Lovelace"
                    autoComplete="name"
                    optional
                  />
                )}
                <Field
                  label="Email"
                  value={email}
                  onChange={setEmail}
                  type="email"
                  placeholder="you@company.com"
                  autoComplete="email"
                  autoFocus
                  required
                />
                <Field
                  label="Password"
                  value={password}
                  onChange={setPassword}
                  type="password"
                  placeholder="••••••••"
                  autoComplete={mode === 'signin' ? 'current-password' : 'new-password'}
                  required
                />

                {error && (
                  <div role="alert">
                    <p className="lgn-error">{error}</p>
                    {showGoogleHint && (
                      <p className="lgn-hint">
                        Signed up with Google? Use Continue with Google below.
                      </p>
                    )}
                  </div>
                )}

                <button disabled={busy} className="lgn-primary">
                  {busy ? 'Working…' : mode === 'signin' ? 'Sign in' : 'Create account'}
                </button>

                <div className="lgn-or">
                  <i />
                  <span>or</span>
                  <i />
                </div>

                <button
                  type="button"
                  onClick={() => void signInWithGoogle(window.location.origin + '/')}
                  className="lgn-google"
                >
                  {/* Google's own mark, in Google's own colours — a brand asset the
                      sign-in guidelines require verbatim, not decoration. */}
                  <svg viewBox="0 0 18 18" aria-hidden>
                    <path fill="#4285F4" d="M17.64 9.2c0-.64-.06-1.25-.16-1.84H9v3.48h4.84a4.14 4.14 0 0 1-1.8 2.72v2.26h2.92c1.7-1.57 2.68-3.88 2.68-6.62z" />
                    <path fill="#34A853" d="M9 18c2.43 0 4.47-.8 5.96-2.18l-2.92-2.26c-.81.54-1.84.86-3.04.86-2.34 0-4.32-1.58-5.03-3.7H.96v2.33A9 9 0 0 0 9 18z" />
                    <path fill="#FBBC05" d="M3.97 10.72a5.4 5.4 0 0 1 0-3.44V4.95H.96a9 9 0 0 0 0 8.1l3.01-2.33z" />
                    <path fill="#EA4335" d="M9 3.58c1.32 0 2.5.46 3.44 1.35l2.58-2.58C13.47.9 11.43 0 9 0A9 9 0 0 0 .96 4.95l3.01 2.33C4.68 5.16 6.66 3.58 9 3.58z" />
                  </svg>
                  Continue with Google
                </button>
              </form>
            )}
          </div>

          {!needsCode && (
            <div className="lgn-foot">
              <p className="lgn-switch">
                {mode === 'signin' ? "Don't have an account?" : 'Already have an account?'}{' '}
                <button
                  type="button"
                  onClick={() => {
                    setMode(mode === 'signin' ? 'signup' : 'signin')
                    setError(null)
                    setShowGoogleHint(false)
                  }}
                >
                  {mode === 'signin' ? 'Create one' : 'Sign in'}
                </button>
              </p>
              {/* The "trouble signing in" slot, answered honestly. There is no
                  password-reset flow in InsForge for these accounts, so this
                  does NOT offer one — it states the actual cause of the one
                  failure this door produces: a Google account has no password
                  to type. Inventing a "Forgot password?" link here would be a
                  link to nothing. */}
              {mode === 'signin' && (
                <p className="lgn-trouble">
                  Trouble signing in? Accounts made with Google have no password — use
                  Continue with Google.
                </p>
              )}
            </div>
          )}
        </div>
      </div>

      <style>{`
        /* ── THE SPLIT ──────────────────────────────────────────────────────
           One grid, edge to edge. 55/45 is the proportion of the sign-in this
           was modelled on. minmax(0,…) on both tracks is what stops a wide
           child (the scaled plate) from widening a column, and with
           overflow-x:hidden on the root the page cannot scroll sideways at any
           width. min-height (not height) so a short viewport scrolls rather
           than clips. */
        .lgn-root { min-height:100vh; min-height:100svh; width:100%;
          display:grid; grid-template-columns:minmax(0,55fr) minmax(0,45fr);
          background:#F1F1EF; color:#1B1B1A;
          font:14px/1.5 Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
          overflow-x:hidden; }

        /* ── LEFT: the plate, the scrim, the brand, the words ─────────────── */
        .lgn-art { position:relative; overflow:hidden; background:#0A0A0B;
          min-width:0; display:flex; flex-direction:column;
          justify-content:space-between; padding:40px 46px 46px; }
        /* PloyLanding's hero treatment, and its scale(1.5) is the load-bearing
           part of it: the landing blows the plate up specifically so the page
           it filmed "stays live but unreadable — its own titles must never
           compete with ours." At 1.08 they very much did. Blown up and pushed
           to the 84% crop, the frame lands in that page's tile grid, which is
           geometry rather than anyone's headline: a real interface, legible as
           texture, advertising nobody. */
        /* NOTE ON THE FRAMING, because it is not obvious and cost a round:
           object-position's Y is a NO-OP here. The plate is 16:9 inside a tall
           column, so object-fit:cover scales it by HEIGHT and the overflow it
           has to distribute is horizontal — there is no vertical slack for a Y
           offset to move. All vertical framing therefore has to happen in the
           transform, which is what the translateY below is doing: it lifts the
           frame off that page's headline and buttons and down into its tile
           grid.

           (And nothing in this stylesheet may contain a BACKTICK — it lives in
           a template literal, so one closes the CSS early and the rest of the
           file parses as JSX. It has happened twice.) */
        /* WHY A BACKGROUND AND NOT AN <img>: so that a phone never pays for it.
           An <img loading="lazy"> inside a display:none panel still gets
           fetched — measured at 390px, the request went out — because lazy
           loading is an intersection heuristic, not a promise. A background
           declared inside a min-width media query is a promise: the rule does
           not match, so the URL is never resolved and no request is made. The
           panel's own #0A0A0B ground paints instantly either way, so nothing
           here is on the path to first paint. */
        .lgn-plate { position:absolute; inset:0; z-index:0;
          background-repeat:no-repeat; background-size:cover;
          background-position:50% 50%;
          /* THE TWO NUMBERS THAT MOVED OFF THE LANDING'S, AND WHY.
             blur: the landing reaches unreadability at 2px because its hero is
             ~2400px wide and every element is small in frame. This column is a
             third of that, so the same page lands proportionally much larger —
             at 2-3px its headline was plainly readable and competing with ours.
             brightness: .44 is right for the landing's footage and wrong for
             this plate, because this plate is a BLACK page whose only luminance
             IS its text. Darkening it to .44 left a flat black rectangle with
             no material in it at all. Brightening and blurring harder trades
             the other way and is what the treatment actually wants: high
             frequency (the type) is destroyed, low frequency (the grid, the
             tile edges, the glow of a lit screen) survives. The result is an
             out-of-focus monitor — which is the true thing to have behind a
             door into a screening room. */
          filter:saturate(.72) contrast(.9) brightness(.8) blur(7px);
          transform:scale(1.6) translate3d(0,-14%,0);
          animation:lgn-drift 34s ease-in-out infinite alternate; }
        /* The one line that decides whether a phone downloads 208KB. It is
           gated to the width at which the panel actually exists; below it the
           declaration never matches and the file is never requested. Keep this
           breakpoint and the display:none one in .lgn-art in step. */
        @media (min-width:901px) {
          .lgn-plate { background-image:url('/landing/hero-poster.jpg'); } }
        /* Slow enough to be life rather than movement — a still that breathes,
           not a pan. Nothing on a sign-in form should be racing. */
        @keyframes lgn-drift {
          from { transform:scale(1.6) translate3d(0,-14%,0); }
          to   { transform:scale(1.68) translate3d(-1.2%,-16%,0); } }

        /* Centre-weighted radial (the landing's own scrim), plus a bottom rise
           under the type block. Legibility where the words are; the footage
           keeps its brightness at the top edge. */
        .lgn-scrim { position:absolute; inset:0; z-index:1; background:
          radial-gradient(ellipse 76% 60% at 42% 62%,
            rgba(10,10,11,.66) 0%, rgba(10,10,11,.42) 46%, rgba(10,10,11,0) 78%),
          linear-gradient(to top, rgba(10,10,11,.88) 0%,
            rgba(10,10,11,.34) 34%, rgba(10,10,11,0) 64%); }

        .lgn-lockup-art, .lgn-say { position:relative; z-index:2; }

        /* Byte-for-byte the boot screen's lockup (landing2/BootScreen
           .fl-bootmark), minus its breathing animation — the door is arrived
           at, not waited on. */
        .lgn-lockup { display:flex; align-items:center; gap:11px;
          font:600 38px/1 Inter,ui-sans-serif,-apple-system,"Segoe UI",Roboto,sans-serif;
          letter-spacing:-.022em; }
        .lgn-lockup svg { width:50px; height:50px; flex:0 0 auto; }
        /* Not a new colour: exactly what FilmoLoader.inkFor() returns for a
           dark ground. */
        .lgn-lockup-art { color:#F1F1EF; }

        /* PloyLanding's display face and its d2 step. Three steps exist and
           nothing sits between them; on a column this wide, d2 is the one. */
        .lgn-display { margin:0; max-width:15ch; color:#F4F3F0;
          font-family:"Anton","Haettenschweiler","Impact","Arial Narrow Bold",sans-serif;
          font-weight:400; text-transform:uppercase; letter-spacing:-.005em;
          line-height:.87; font-size:76px;
          text-shadow:0 14px 70px rgba(0,0,0,.55); }
        .lgn-fine { margin:22px 0 0; max-width:56ch; font-size:13.5px;
          line-height:1.55; color:rgba(244,243,240,.66); }

        /* ── RIGHT: the form column ────────────────────────────────────────
           margin:auto centres the card without align-items:center's habit of
           clipping the top of anything taller than the column. */
        .lgn-form-col { display:flex; flex-direction:column; min-width:0;
          padding:48px 40px; }
        .lgn-cardwrap { margin:auto; width:100%; max-width:404px; }

        .lgn-lockup-form { display:none; margin:0 0 26px; color:#1B1B1A;
          gap:8px; font-size:26px; }
        .lgn-lockup-form svg { width:34px; height:34px; }

        .lgn-card { background:#fff; border:1px solid #E6E6E3; border-radius:16px;
          padding:28px 26px;
          box-shadow:0 1px 2px rgba(27,27,26,.04), 0 24px 48px -32px rgba(27,27,26,.28); }
        .lgn-form { display:flex; flex-direction:column; gap:16px; }
        .lgn-h1 { margin:0; font-size:22px; font-weight:650;
          letter-spacing:-.018em; color:#1B1B1A; }
        .lgn-sub { margin:6px 0 0; font-size:13.5px; line-height:1.55;
          color:#8A8A86; }

        /* ── CONTROLS ────────────────────────────────────────────────────────
           Every one of them states its own focus. The surface is quiet by
           design; that is a look, not a licence (the same rule and the same
           #3B82F6 ring the rail and the account card carry). */
        .lgn-google { display:flex; align-items:center; justify-content:center;
          gap:10px; width:100%; background:#fff; border:1px solid #E6E6E3;
          border-radius:10px; padding:11px 14px; cursor:pointer;
          font:600 14px/1.2 Inter,-apple-system,sans-serif; color:#1B1B1A;
          transition:background-color .15s, border-color .15s; }
        .lgn-google svg { width:18px; height:18px; flex:0 0 auto; }
        .lgn-google:hover { background:#FAFAF8; border-color:#C9C9C4; }
        .lgn-google:focus-visible { outline:2px solid #3B82F6; outline-offset:2px; }

        .lgn-or { display:flex; align-items:center; gap:12px; }
        .lgn-or i { flex:1 1 auto; height:1px; background:#E6E6E3; }
        .lgn-or span { font-size:11px; font-weight:600; letter-spacing:.08em;
          text-transform:uppercase; color:#B6B6B2; }

        .lgn-label { display:block; }
        .lgn-labeltext { display:flex; align-items:baseline; gap:6px;
          margin-bottom:6px; font-size:13px; font-weight:600; color:#1B1B1A; }
        .lgn-optional { font-size:11.5px; font-weight:400; color:#B6B6B2; }
        .lgn-input { width:100%; background:#fff; border:1px solid #E6E6E3;
          border-radius:10px; padding:10px 12px;
          font:14px/1.4 Inter,-apple-system,sans-serif; color:#1B1B1A;
          outline:none; transition:border-color .15s, box-shadow .15s; }
        .lgn-input::placeholder { color:#B6B6B2; }
        .lgn-input:hover { border-color:#C9C9C4; }
        .lgn-input:focus-visible { border-color:#3B82F6;
          box-shadow:0 0 0 3px rgba(59,130,246,.18); }
        .lgn-code { text-align:center; font-size:19px; letter-spacing:.3em;
          padding:11px 12px; }

        .lgn-primary { width:100%; border:1px solid #1B1B1A; background:#1B1B1A;
          color:#fff; border-radius:10px; padding:11px 16px; cursor:pointer;
          font:600 14px/1.2 Inter,-apple-system,sans-serif;
          transition:background-color .15s, border-color .15s, opacity .15s; }
        .lgn-primary:hover:not(:disabled) { background:#000; border-color:#000; }
        .lgn-primary:focus-visible { outline:2px solid #3B82F6; outline-offset:2px; }
        .lgn-primary:disabled { opacity:.55; cursor:default; }

        /* #DC2626 is the app's existing "something went wrong" ink
           (SuggestionCards .ovsug-note.bad) — not a new colour. */
        .lgn-error { margin:0; font-size:13px; line-height:1.5; color:#DC2626; }
        .lgn-hint { margin:5px 0 0; font-size:12.5px; line-height:1.5;
          color:#8A8A86; }

        .lgn-foot { margin:20px 0 0; text-align:center; }
        .lgn-switch { margin:0; font-size:13.5px; color:#8A8A86; }
        .lgn-switch button { border:none; background:none; padding:0;
          cursor:pointer; font:600 13.5px/1.5 Inter,-apple-system,sans-serif;
          color:#1B1B1A; border-radius:4px; }
        .lgn-switch button:hover { color:#3B82F6; }
        .lgn-switch button:focus-visible { outline:2px solid #3B82F6;
          outline-offset:3px; color:#3B82F6; }
        /* The app's muted ink, not the placeholder grey one step below it:
           #B6B6B2 on #F1F1EF is around 2:1 and this line is the answer to a
           real support case, so it has to be readable by the person having the
           problem. */
        .lgn-trouble { margin:12px auto 0; max-width:38ch; font-size:12.5px;
          line-height:1.55; color:#8A8A86; }

        /* ── THE COLLAPSE ───────────────────────────────────────────────────
           One column, form first, art dropped entirely — and because the plate
           is a lazy image inside a display:none panel, it is never even
           fetched at this width. The brand comes back above the card. */
        @media (max-width:900px) {
          .lgn-root { grid-template-columns:1fr; }
          .lgn-art { display:none; }
          .lgn-form-col { padding:40px 20px; }
          .lgn-lockup-form { display:flex; } }

        /* Between the collapse and the landing's own d2→d3 step, the art
           column is narrow enough that 76px would break mid-word. */
        @media (max-width:1100px) {
          .lgn-art { padding:34px 32px 36px; }
          .lgn-display { font-size:56px; } }

        @media (max-width:420px) {
          .lgn-card { padding:22px 18px; }
          .lgn-lockup-form { margin-bottom:22px; } }

        @media (prefers-reduced-motion:reduce) {
          .lgn-plate { animation:none; }
          .lgn-google, .lgn-primary, .lgn-input { transition:none; } }
      `}</style>
    </main>
  )
}

/**
 * `d•••••@company.com`. The verification card has to say WHICH inbox to open
 * without printing an address on screen for whoever is behind you — the same
 * rule the rest of the app's chrome follows. Enough to recognise your own
 * account, not enough to read out.
 */
function maskEmail(raw: string): string {
  const at = raw.lastIndexOf('@')
  if (at < 1) return 'your inbox'
  const local = raw.slice(0, at)
  const domain = raw.slice(at)
  return local[0] + '•'.repeat(Math.max(3, Math.min(local.length - 1, 6))) + domain
}

function Field({
  label,
  value,
  onChange,
  type,
  placeholder,
  required,
  optional,
  autoFocus,
  autoComplete,
}: {
  label: string
  value: string
  onChange: (v: string) => void
  type: string
  placeholder?: string
  required?: boolean
  optional?: boolean
  autoFocus?: boolean
  /** Handed to the browser's password manager. The user's own credential store
   *  filling its own fields is the only sanctioned path for a secret here. */
  autoComplete?: string
}) {
  return (
    <label className="lgn-label">
      <span className="lgn-labeltext">
        {label}
        {optional && <span className="lgn-optional">optional</span>}
      </span>
      <input
        className="lgn-input"
        type={type}
        value={value}
        required={required}
        autoFocus={autoFocus}
        autoComplete={autoComplete}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
      />
    </label>
  )
}
