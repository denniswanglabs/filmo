'use client'
// The studio's own composer — the "New filmo" surface on the icon rail. Ported
// from the approved prototype (`landing-lab/studio.html`, `.empty` / `.composer`):
// one question set high on the stage, one line of explanation, and a single
// large input parked at the bottom rather than centred under the question.
//
// The rail is fixed furniture; only the stage changes. So this component owns
// the stage and nothing else — it never draws chrome, and it never navigates
// anywhere except to the run it just created.
//
// THIS COMPONENT IS THREE DOORS. It is mounted by `/new` (with the rail), by
// `/?new=1` through StudioEntry (without one, for an account that has no films
// yet), and by the studio's own rail as the `new` surface. All three therefore
// behave identically for free — which is the entire reason it was never copied.
//
// ── WHAT IT NO LONGER OWNS ──────────────────────────────────────────────────
// Starting a film. The build parameters, the sticky look, the URL
// normalisation, the pending-build stash, the wording of every refusal, the
// arrival cover and the navigation all moved to `components/StartFilm.tsx`,
// which the Overview's suggestion cards call too. What is left here is the
// stage, and the one thing a door genuinely owns: what it does when the answer
// is "sign in first". This one used to raise the modal AuthGate; now it goes to
// /login, the single sign-in surface (the modal is retired, 2026-07-20). The URL
// is already stashed by `startFilm` on the refusal, so `/` resumes the build
// after sign-in — the door keeps nothing of its own to lose.
import { useCallback, useState } from 'react'
import { useRouter } from 'next/navigation'
import { useStartFilm, type FilmStartRefusal } from '../../components/StartFilm'

export default function NewFilmComposer({ getToken }: {
  getToken: () => Promise<string | null>
}) {
  const router = useRouter()
  const [url, setUrl] = useState('')
  // ONE line under the input carries every thing this screen has to say, and
  // its tone says which kind of thing it is. `bad` is reserved for something
  // the user must act on; progress and reassurance stay quiet.
  const [note, setNote] = useState<{ text: string; bad?: boolean } | null>(null)

  // The door's own half of the contract: when the answer is "sign in first",
  // go to /login (the URL is already stashed by startFilm, so `/` resumes the
  // build after sign-in). Every other refusal — a credit cap, a backend blip —
  // is a real answer, not a broken session, so it stays here as a line under the
  // box and never sends the reader to the door.
  const onRefused = useCallback((r: FilmStartRefusal) => {
    if (r.kind === 'sign-in') {
      router.push('/login')
      return
    }
    setNote({ text: r.message, bad: true })
  }, [router])

  const { startFilm, starting, cover } = useStartFilm({ getToken, onRefused })

  const start = useCallback(async () => {
    setNote(null)
    await startFilm(url)
  }, [url, startFilm])

  const canSend = url.trim().length > 3 && !starting

  return (
    <div className="nf-stage">
      {/* Raised on the click, before the token and before the server — the
          reader is looking at the studio's ground while everything below is
          still in flight. Lowered again, onto this screen and its message, if
          the film cannot be started. */}
      {cover}

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
          // Never submit on the Enter that confirms an IME candidate. With a
          // Chinese IME even an ASCII URL is often composed (pinyin mode
          // intercepts letters), and some engines let that confirm-Enter reach
          // the form as an implicit submission — firing createBuild on half a
          // URL. isComposing is the standard signal; keyCode 229 is the same
          // fact from older WebKit. Same guard as the director box — the two
          // chat-shaped inputs honour one contract.
          onKeyDown={(e) => {
            if (e.key === 'Enter' && (e.nativeEvent.isComposing || e.keyCode === 229)) {
              e.preventDefault()
            }
          }}
          placeholder="https://your-product.com"
          aria-label="Product URL"
          autoComplete="off"
          spellCheck={false}
          autoFocus
        />
        <div className="nf-row">
          <span className={'nf-hint' + (note?.bad ? ' bad' : '')} role="status">
            {starting ? 'Starting the filmo…' : note?.text || ''}
          </span>
          <button
            type="submit"
            className="nf-send"
            disabled={!canSend}
            aria-label={starting ? 'Starting the filmo' : 'Start the filmo'}
          >
            &#8593;
          </button>
        </div>
      </form>

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
