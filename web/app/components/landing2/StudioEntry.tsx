'use client'
import NewFilmComposer from '../../runs/[id]/NewFilmComposer'

// ── THE STUDIO, WITH NOTHING IN IT YET ──────────────────────────────────────
// The studio is a room you enter through a film: `runs/[id]/page.tsx` hands
// Workspace a run, and Workspace's rail switches its stage between the film,
// the library, and the composer. A brand-new account has no film, so it has no
// run id, so it has no way in — and redirecting it to a run that doesn't exist
// would greet a first-time signup with "This run could not be found."
//
// So `/` renders the composer surface ITSELF for that account: the same
// component the rail mounts (never a second copy of it — two composers that
// disagree about one createBuild parameter make two different films from the
// same URL, with no visible cause), on the studio's own daylight ground,
// without the rail, because there is nothing yet for a rail to switch between.
//
// This is also why it is a RENDER and not a redirect: a user with zero runs has
// nowhere to be sent, and sending them anywhere that bounces them back is how
// you build an infinite loop out of an empty account.
export default function StudioEntry({
  getToken,
  notice,
}: {
  getToken: () => Promise<string | null>
  /** Carried over from a build that failed on the way in (a beta cap, an expired
   *  session). The composer owns its own hint line and can't be handed one, so
   *  the answer has to be said here rather than dropped on the floor. */
  notice?: string | null
}) {
  return (
    <div className="fl-studioentry">
      <style>{`
        /* Same ground and shape as Workspace's .wk-root, minus the rail. */
        .fl-studioentry { position:fixed; inset:0; display:flex;
          background:#F1F1EF; color:#1B1B1A;
          font-family:ui-sans-serif,-apple-system,"Segoe UI",Roboto,sans-serif; }
        .fl-studionote { position:absolute; left:50%; transform:translateX(-50%);
          top:22px; z-index:5; max-width:min(560px, calc(100% - 48px));
          background:#fff; border:1px solid #F0D2D2; border-radius:12px;
          padding:11px 16px; font-size:13.5px; line-height:1.5; color:#B4342F;
          box-shadow:0 2px 4px rgba(0,0,0,.03), 0 18px 50px -30px rgba(0,0,0,.25); }
      `}</style>
      {notice ? (
        <div className="fl-studionote" role="status">
          {notice}
        </div>
      ) : null}
      <NewFilmComposer getToken={getToken} />
    </div>
  )
}
