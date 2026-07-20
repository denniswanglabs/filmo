'use client'
// The studio's own composer — the "New film" surface on the icon rail. Ported
// from the approved prototype (`landing-lab/studio.html`, `.empty` / `.composer`):
// one question set high on the stage, one line of explanation, and a single
// large input parked at the bottom rather than centred under the question.
//
// The rail is fixed furniture; only the stage changes. So this component owns
// the stage and nothing else — it never draws chrome, and it never navigates
// anywhere except to the run it just created.
import { useCallback, useState } from 'react'
import { useRouter } from 'next/navigation'
import { createBuild } from '../../actions'
import { AuthGate } from '../../components/AuthGate'

// ── TWO COMPOSERS, ONE FILM ─────────────────────────────────────────────────
// The landing (`web/app/page.tsx`) and this screen are two doors into the same
// factory. If they disagree about a single createBuild parameter then the same
// URL, typed by the same person, produces two different films and neither one
// is wrong — a defect with no visible cause and no one to blame. Every value
// the landing pins is therefore pinned here to the SAME value, and everything
// it leaves to the server is left to the server here too:
//   brain    'ultra-paid'  the paid flagship (CLAUDE.md: paid Nemotron, so a
//                          free-tier 429 can never decide a user's film). NOTE
//                          createBuild's own fallback for an absent brain is
//                          'super-free' — omitting it would silently downgrade.
//   mode     'mock'        real Remotion cards, $0 third-party spend.
//   payMode  'auto'        payments are dormant for the open beta.
//   look     'walkrec'     see below — this is the one value the two doors
//                          deliberately DISAGREE on, because they are doors
//                          into different rooms.
const BUILD_DEFAULTS = { brain: 'ultra-paid', mode: 'mock' as const, payMode: 'auto' as const }

// ── A SURFACE MAKES ITS OWN KIND OF FILM ────────────────────────────────────
// createBuild's rule is that a bare submit yields walkrec for the operator and
// classic for everyone else. That rule is right for the LANDING, where the
// visitor has expressed no preference and the server picks. It is wrong here.
//
// This screen is the walkrec studio: the rail, the thread, the beat board and
// the director all belong to that pipeline. A non-owner pressing "New film"
// inside it would get a classic run — which renders a completely different
// page — so the button would navigate you out of the room you were standing
// in, with nothing on screen explaining why.
//
// So this is not the composer overruling policy for everyone; the landing's
// behaviour is untouched. It is a surface declaring what it produces, the same
// way the director's re-cut job already hardcodes `look: 'walkrec'` rather than
// re-deriving it. A sticky 'engineered-night' still wins — that is a visitor
// asking for a specific look, which outranks the surface's default.
const STUDIO_LOOK = 'walkrec' as const

// The sticky look the landing writes when someone arrives with `?look=…`.
// Read with the landing's exact rule — a stored 'classic' is deliberately NOT
// restored, because the landing doesn't restore it either and the server's
// default is what should decide. Mirroring the quirk keeps the two doors
// identical; "fixing" it on one side is what makes them differ.
function stickyLook(): 'walkrec' | 'engineered-night' | undefined {
  try {
    const saved = localStorage.getItem('filmo-look')
    if (saved === 'walkrec' || saved === 'engineered-night') return saved
  } catch { /* private mode — the server default decides */ }
  return undefined
}

// ── A TYPED URL MUST SURVIVE SIGN-IN ────────────────────────────────────────
// Signing in with Google navigates the WHOLE BROWSER away and comes back to
// `/` — not here (AuthGate calls signInWithGoogle() with no redirectTo, which
// resolves to origin + '/'). So this screen cannot resume its own build: the
// landing does it, by reading this exact sessionStorage key on mount and
// firing createBuild for us. Stashing under the same key in the same shape is
// therefore the ONLY thing standing between a user and losing the URL they
// just typed to a redirect they didn't ask for.
//
// ⚠ The key and the shape are duplicated from `web/app/page.tsx` (PENDING_KEY /
// PendingBuild) because that module keeps them private and this task may not
// edit it. If either side moves, this stops resuming and fails SILENTLY — the
// user just lands on the landing with an empty box. Hoist them to a shared
// module the next time page.tsx is open.
const PENDING_KEY = 'ws_pending_build'

// The same shape the server enforces (createBuild → 'Enter a valid website
// URL.'). Validate here FIRST: createBuild THROWS on a bad URL, and a thrown
// server action is an opaque "Server Components render … digest" 500 in
// production, so the message the user would see is no message at all.
function isValidBuildUrl(raw: string): boolean {
  return /^https?:\/\/[^\s]+\.[^\s]+/i.test((raw || '').trim())
}

// Typing "acme.com" is the same intent as typing "https://acme.com". Fill in
// the scheme rather than failing a URL the user got right.
function normalizeUrl(raw: string): string {
  const t = (raw || '').trim()
  if (!t) return ''
  return /^https?:\/\//i.test(t) ? t : `https://${t}`
}

export default function NewFilmComposer({ getToken }: {
  getToken: () => Promise<string | null>
}) {
  const router = useRouter()
  const [url, setUrl] = useState('')
  const [busy, setBusy] = useState(false)
  // ONE line under the input carries every thing this screen has to say, and
  // its tone says which kind of thing it is. `bad` is reserved for something
  // the user must act on; progress and reassurance stay quiet.
  const [note, setNote] = useState<{ text: string; bad?: boolean } | null>(null)
  const [gateOpen, setGateOpen] = useState(false)

  const start = useCallback(async () => {
    const target = normalizeUrl(url)
    if (!isValidBuildUrl(target)) {
      setNote({ text: 'Enter a valid website URL.', bad: true })
      return
    }
    setNote(null)
    setBusy(true)
    try {
      const accessToken = await getToken()
      // NO TOKEN IS NOT A NO-OP. createBuild needs one and throws without it,
      // so the honest response to a session that has quietly expired under a
      // still-signed-in-looking UI is to ask for a sign-in — never to swallow
      // the click and leave the user tapping a button that does nothing.
      if (!accessToken) {
        setBusy(false)
        stash(target)
        setNote({ text: 'Sign in to start filming — your link is saved.' })
        setGateOpen(true)
        return
      }
      const res = await createBuild({
        accessToken,
        url: target,
        look: stickyLook() || STUDIO_LOOK,
        ...BUILD_DEFAULTS,
      })
      // The beta cap answers with a structured { limit } rather than a run.
      // It is a real answer, not a broken session — say it and stop, don't
      // re-open the sign-in gate over it.
      if ('limit' in res) {
        setBusy(false)
        setNote({ text: res.message, bad: true })
        return
      }
      router.push(`/runs/${res.runId}`)
    } catch {
      // A thrown server action is OPAQUE here (the digest 500), so its real
      // message is unreadable. The dominant cause is a stale token: the UI
      // still looks signed in because the session was restored optimistically,
      // but the server's verifyUser rejected it. Offer the fix instead of the
      // scary error, and keep the URL so signing in doesn't cost it.
      setBusy(false)
      stash(target)
      setNote({ text: 'Your session expired — sign in again to start the film.', bad: true })
      setGateOpen(true)
    }
  }, [url, getToken, router])

  function stash(target: string) {
    try {
      sessionStorage.setItem(PENDING_KEY, JSON.stringify({
        url: target,
        brain: BUILD_DEFAULTS.brain,
        look: stickyLook() || STUDIO_LOOK,
        // Stashes written before payments were switched off carry requirePay:
        // true and would resurrect the checkout gate on resume. Always false.
        requirePay: false,
      }))
    } catch { /* private mode — the Google return just won't auto-resume */ }
  }

  const canSend = url.trim().length > 3 && !busy

  return (
    <div className="nf-stage">
      <div className="nf-head">
        <h1>What&rsquo;s your product URL?</h1>
        <p>Drop it below, and let Filmo handle your product launch from here.</p>
      </div>

      <form
        className="nf-composer"
        onSubmit={(e) => { e.preventDefault(); if (canSend) void start() }}
      >
        <input
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://your-product.com"
          aria-label="Product URL"
          autoComplete="off"
          spellCheck={false}
          autoFocus
        />
        <div className="nf-row">
          <span className={'nf-hint' + (note?.bad ? ' bad' : '')} role="status">
            {busy ? 'Starting the film…' : note?.text || ''}
          </span>
          <button
            type="submit"
            className="nf-send"
            disabled={!canSend}
            aria-label={busy ? 'Starting the film' : 'Start the film'}
          >
            &#8593;
          </button>
        </div>
      </form>

      {/* The product's real sign-in surface, not a second copy of it. It hands
          back a fresh token on the email path (onSignedIn → start again), and
          on the Google path it stashes first and the landing resumes. */}
      <AuthGate
        open={gateOpen}
        onClose={() => setGateOpen(false)}
        onBeforeRedirect={() => stash(normalizeUrl(url))}
        onSignedIn={() => { setGateOpen(false); void start() }}
      />

      <style>{`
        .nf-stage { flex:1 1 0; min-width:0; position:relative; display:flex;
          flex-direction:column; align-items:center; padding:0 24px; }
        .nf-head { margin-top:31vh; text-align:center; max-width:640px; }
        .nf-head h1 { margin:0; font-size:46px; font-weight:600;
          letter-spacing:-.03em; color:#1B1B1A; line-height:1.12; }
        .nf-head p { margin:18px auto 0; max-width:40ch; font-size:19px;
          line-height:1.5; color:#8A8A86; }
        @media (max-width:760px) {
          .nf-head h1 { font-size:34px; }
          .nf-head p { font-size:16px; } }
        /* Parked at the bottom, not centred under the question — the input is
           where the hand goes, the question is what the eye reads. */
        .nf-composer { position:absolute; left:50%; transform:translateX(-50%);
          bottom:34px; width:min(860px, calc(100% - 48px)); background:#fff;
          border:1px solid #E6E6E3; border-radius:18px; padding:18px 18px 14px;
          box-shadow:0 2px 4px rgba(0,0,0,.03), 0 18px 50px -30px rgba(0,0,0,.25);
          transition:border-color .18s, box-shadow .18s; }
        /* The input drops its own outline, so the BOX carries the focus state
           for it — a keyboard user must never lose track of where they are. */
        .nf-composer:focus-within { border-color:#C9D9F8;
          box-shadow:0 2px 4px rgba(0,0,0,.03), 0 22px 60px -30px rgba(59,130,246,.4); }
        /* Longhand on purpose: the shorthand \`font:16px/1.5 inherit\` is invalid
           CSS (a CSS-wide keyword can't be a shorthand component), so the whole
           declaration drops and the input silently falls back to the UA's
           13px Arial. Same reason the feedback textarea is written out. */
        .nf-composer input { width:100%; border:none; outline:none;
          background:none; font-size:16px; line-height:1.5; font-family:inherit;
          color:#1B1B1A; }
        .nf-composer input::placeholder { color:#B6B6B2; }
        .nf-row { display:flex; align-items:center; justify-content:space-between;
          gap:14px; margin-top:16px; }
        .nf-hint { font-size:12px; color:#B6B6B2; min-height:1em; min-width:0; }
        .nf-hint.bad { color:#DC2626; }
        .nf-send { width:38px; height:38px; flex:0 0 auto; border-radius:50%;
          border:none; background:#1B1B1A; color:#fff; cursor:pointer;
          font-size:16px; line-height:1; display:flex; align-items:center;
          justify-content:center;
          transition:transform .3s cubic-bezier(.22,1,.36,1), opacity .2s; }
        .nf-send:hover:not(:disabled) { transform:translateY(-2px); }
        .nf-send:disabled { opacity:.3; cursor:default; transform:none; }
        .nf-send:focus-visible { outline:2px solid #3B82F6; outline-offset:3px; }
        @media (prefers-reduced-motion:reduce) {
          .nf-composer, .nf-send { transition:none; }
          .nf-send:hover:not(:disabled) { transform:none; } }
      `}</style>
    </div>
  )
}
