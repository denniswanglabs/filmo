'use client'
// The feedback sheet behind the rail's envelope. Ported from the approved
// prototype (`landing-lab/studio.html`, the `#fbopen` button and its `.fb`
// sheet): the one dark surface in a light studio, so it reads as a different
// kind of act — talking to the people who made this, rather than working.
import { useCallback, useEffect, useRef, useState } from 'react'
import { sendFeedback } from '../../actions'

// ── SAVED IS NOT SENT ───────────────────────────────────────────────────────
// `sendFeedback` stores the note first and attempts delivery second, and it
// reports the two separately: `notified` is whether an inbox actually received
// it. No mail provider is configured on Vercel yet, so today `notified` is
// false on every send — and a screen that answered "Sent!" would be telling a
// user their note reached a person when it is sitting in a table nobody has
// opened. That is the exact lie this component exists to not tell.
//
// Three outcomes, three different sentences, and none of them borrows the
// other's confidence:
//   ok + notified    it reached an inbox. This is the only "sent".
//   ok + !notified   it is safely stored, and nobody has it yet. Say so.
//   !ok              the action's OWN message, verbatim — it knows why it
//                    refused (empty, too long, the insert failed) and this
//                    screen must not paraphrase a reason it is guessing at.
function outcomeNote(
  res: { ok: true; notified: boolean } | { ok: false; message: string },
): { text: string; bad?: boolean } {
  if (!res.ok) return { text: res.message, bad: true }
  if (res.notified) return { text: 'Sent — thank you. We read every one.' }
  return {
    text: 'Received and saved — thank you. It hasn’t reached an inbox yet, '
      + 'so it may be a while before you hear back.',
  }
}

export default function FeedbackModal({ open, onClose, context, getToken }: {
  open: boolean
  onClose: () => void
  /** Where they were standing — a route, the run, the surface. Turns "this is
   *  broken" into something someone can actually go and look at. */
  context: string
  getToken: () => Promise<string | null>
}) {
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState<{ text: string; bad?: boolean } | null>(null)
  const areaRef = useRef<HTMLTextAreaElement>(null)
  // Where the keyboard was before this took over, so closing puts it back
  // instead of dropping the user at the top of the document.
  const returnTo = useRef<HTMLElement | null>(null)

  useEffect(() => {
    if (!open) return
    returnTo.current = document.activeElement as HTMLElement | null
    setNote(null)
    areaRef.current?.focus()
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('keydown', onKey)
      returnTo.current?.focus?.()
    }
  }, [open, onClose])

  const send = useCallback(async () => {
    const message = text.trim()
    if (!message || busy) return
    setBusy(true)
    setNote(null)
    try {
      // Signed-out senders are welcome — the action takes a null token and
      // files the note anonymously. An expired session is not a reason to
      // refuse to hear that something is broken.
      // ── DELIVER FROM THE BROWSER, STORE ON THE SERVER ───────────────────
      // Web3Forms refuses server-side calls on the free tier and its access
      // key is public by design (it can only mail the address it was issued
      // for), so the delivery attempt belongs here. Storage still happens
      // server-side and still happens FIRST in effect — a failed or blocked
      // delivery never costs anyone their note.
      //
      // ⚠ Web3Forms answers HTTP 200 on failure (`{"success": false}`), so
      // `res.ok` alone would let us tell the server an email went out that
      // never did. Only `success === true` counts as delivered.
      let clientNotified = false
      const key = process.env.NEXT_PUBLIC_FEEDBACK_ACCESS_KEY
      if (key) {
        try {
          const r = await fetch('https://api.web3forms.com/submit', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
            body: JSON.stringify({
              access_key: key,
              subject: 'Filmo feedback',
              from_name: 'Filmo',
              message: [context ? `Context: ${context}` : '', '', message]
                .filter(Boolean).join('\n'),
            }),
          })
          const out = await r.json().catch(() => null)
          clientNotified = r.ok && out?.success === true
        } catch { /* delivery is best-effort; the note is still stored below */ }
      }
      const res = await sendFeedback({
        message, accessToken: await getToken(), context, clientNotified,
      })
      setNote(outcomeNote(res))
      // Only clear what the server has actually accepted. On a refusal the
      // words stay in the box so a trim-and-resend doesn't mean retyping.
      if (res.ok) setText('')
    } catch {
      // A thrown server action is opaque in production, so we cannot know
      // whether the row landed. Claim nothing about where the note is.
      setNote({ text: 'That didn’t go through — try again in a moment.', bad: true })
    }
    setBusy(false)
  }, [text, busy, context, getToken])

  if (!open) return null

  return (
    <div
      className="fb-scrim"
      onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      <div className="fb-card" role="dialog" aria-modal="true" aria-labelledby="fb-title">
        <button className="fb-x" onClick={onClose} aria-label="Close feedback">
          &#215;
        </button>
        <h3 id="fb-title">Send feedback</h3>
        {/* The prototype's second sentence invited screenshots. `sendFeedback`
            takes { message, accessToken, context } and has nowhere to put a
            file, so both the invitation and the "+ Add screenshot" button are
            gone: an affordance with no field behind it is a promise the
            product can't keep, and it would swallow the evidence silently. */}
        <p className="fb-sub">Tell us what broke, what felt wrong, or what you wish it did.</p>
        <textarea
          ref={areaRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="What happened, and what did you expect instead?"
          aria-label="Your feedback"
        />
        <div className="fb-row">
          {/* Say what travels with the note rather than attaching it quietly. */}
          <span className="fb-ctx">Sent with the page you’re on, so we can look it up.</span>
          <button
            className="fb-send"
            onClick={() => void send()}
            disabled={!text.trim() || busy}
          >
            {busy ? 'Sending…' : 'Send'}
          </button>
        </div>
        <div className={'fb-note' + (note?.bad ? ' bad' : '')} role="status">
          {note?.text || ''}
        </div>
      </div>

      <style>{`
        .fb-scrim { position:fixed; inset:0; z-index:80; display:flex;
          align-items:center; justify-content:center; padding:20px;
          background:rgba(10,10,11,.55); backdrop-filter:blur(8px);
          animation:fb-fade .25s ease both; }
        .fb-card { position:relative; width:min(620px, 92vw); max-height:88vh;
          overflow-y:auto; background:#1C1C1E; color:#F4F3F0; border-radius:18px;
          padding:30px 32px 26px; box-shadow:0 40px 110px -30px rgba(0,0,0,.7);
          animation:fb-rise .35s cubic-bezier(.22,1,.36,1) both; }
        .fb-x { position:absolute; right:18px; top:16px; background:none;
          border:none; color:#8A8A90; font-size:22px; line-height:1;
          cursor:pointer; padding:4px 8px; border-radius:8px; }
        .fb-x:hover { color:#F4F3F0; }
        .fb-card h3 { margin:0 0 8px; font-size:23px; font-weight:650;
          letter-spacing:-.02em; }
        .fb-sub { margin:0 0 20px; font-size:14px; line-height:1.55;
          color:#A0A0A6; }
        /* Longhand: \`font:14.5px/1.55 inherit\` is invalid shorthand and would
           drop whole, leaving the box in the UA's default face. */
        .fb-card textarea { width:100%; min-height:150px; resize:vertical;
          background:#141416; border:1px solid #33333A; border-radius:10px;
          padding:14px 16px; color:#F4F3F0; font-size:14.5px; line-height:1.55;
          font-family:inherit; outline:none; display:block; }
        /* The textarea drops its outline, so its BORDER carries focus. */
        .fb-card textarea:focus { border-color:#4B8DF8; }
        .fb-card textarea::placeholder { color:#6E6E76; }
        .fb-row { display:flex; align-items:center; justify-content:space-between;
          gap:16px; margin-top:18px; }
        .fb-ctx { font-size:12.5px; line-height:1.45; color:#8A8A90; min-width:0; }
        .fb-send { flex:0 0 auto; background:#4B8DF8; border:none; color:#fff;
          border-radius:10px; padding:11px 24px; font-size:14px; font-weight:600;
          font-family:inherit; cursor:pointer;
          transition:transform .3s cubic-bezier(.22,1,.36,1), opacity .2s; }
        .fb-send:hover:not(:disabled) { transform:translateY(-1px); }
        .fb-send:disabled { opacity:.45; cursor:default; transform:none; }
        .fb-x:focus-visible, .fb-send:focus-visible { outline:2px solid #8FB6FF;
          outline-offset:3px; }
        .fb-note { margin-top:14px; font-size:12.5px; line-height:1.5;
          color:#A0A0A6; min-height:1em; }
        .fb-note.bad { color:#FF9B93; }
        @keyframes fb-fade { from { opacity:0; } to { opacity:1; } }
        @keyframes fb-rise {
          from { opacity:0; transform:translateY(12px); }
          to { opacity:1; transform:none; } }
        @media (prefers-reduced-motion:reduce) {
          .fb-scrim, .fb-card { animation:none; }
          .fb-send { transition:none; }
          .fb-send:hover:not(:disabled) { transform:none; } }
      `}</style>
    </div>
  )
}
