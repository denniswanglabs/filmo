'use client'
// ── THE POSTER INVARIANT, FOR THE LIBRARIES ─────────────────────────────────
// ⚠ TWIN of `runs/[id]/Workspace.tsx`'s FilmVideo, and it exists for the same
// reason: a film NEVER occupies the layout as an empty black box. Every
// <video> and every <img> on /videos and /assets goes through this one
// component, and `poster` is REQUIRED — not optional, not defaulted — so no
// future caller can add a film to a library without saying what frame it opens
// on. An optional prop would have been the same rule written as a suggestion.
//
// The fallback is decided by what the media is FOR. Everything here is a
// THUMBNAIL, something nobody plays in place, so a missing still is covered by
// seeking the file to 2 seconds. (Workspace's player role deliberately does
// NOT do that — a film you are about to watch must not start two seconds in.
// This surface has no player, so it has no such case.)
//
// ── ABSENCE MUST NOT PRODUCE A URL ──────────────────────────────────────────
// The second rule is subtler and has already cost this codebase a debugging
// session (see the note above `liveFrame` in Workspace). `${src}#t=2` on an
// EMPTY src does not yield an empty reference — it yields the relative URL
// `#t=2`, which the browser resolves against the current route, and the app
// answers that path with its own HTML at 200 OK. No 404, no console error: a
// <video> element quietly handed a web page, rendering as an empty black box
// that looks exactly like a film that has not decoded yet. `listAssets` can
// emit `url: ''` (its film rows are built with `proxyPlayableUrl(...) || ''`),
// so this is reachable, not theoretical. An absent source therefore never
// reaches a media element at all: it branches to a drawn placeholder that says
// what it is.

/** A frame drawn rather than loaded — what a tile shows when it has no file to
 *  point at. Same hand as the rail's icons: 24-box, 2px stroke, no fill. */
function NoFrame({ label }: { label: string }) {
  return (
    <div className="libthumb-none" title={label}>
      <svg viewBox="0 0 24 24" aria-hidden>
        <rect x="3" y="5" width="18" height="14" rx="2" stroke="currentColor"
          strokeWidth="2" fill="none" />
        <path d="m3.5 15.5 4.2-4.2a2 2 0 0 1 2.8 0l3 3" stroke="currentColor"
          strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round" />
        <circle cx="15.5" cy="9.5" r="1.4" stroke="currentColor" strokeWidth="2"
          fill="none" />
      </svg>
    </div>
  )
}

export default function MediaThumb({
  src, video, poster, fit, alt = '', onLoadedMetadata,
}: {
  /** May be empty. If it is, nothing is loaded — see the note above. */
  src: string
  /** Whether the file is footage. Decides the element, and only this decides
   *  it — never a guess from the file extension at the call site. */
  video: boolean
  /** A still already produced for this item, or '' when none is in hand. The
   *  library reads return rows, not frames, so today this is '' everywhere;
   *  the prop is required so that stops being true silently. */
  poster: string
  /** 'cover' fills the frame. 'contain' is for marks — they are small, often
   *  transparent, and sit ON the tile rather than filling it. */
  fit: 'cover' | 'contain'
  alt?: string
  onLoadedMetadata?: React.ReactEventHandler<HTMLVideoElement>
}) {
  return (
    <div className={'libthumb' + (fit === 'contain' ? ' contain' : '')}>
      {!src ? (
        <NoFrame label="No file was kept for this one" />
      ) : video ? (
        <video
          src={poster ? src : `${src}#t=2`}
          poster={poster || undefined}
          preload="metadata"
          muted
          playsInline
          onLoadedMetadata={onLoadedMetadata}
        />
      ) : (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={src} alt={alt} loading="lazy" decoding="async" />
      )}

      <style>{`
        /* The frame keeps its ratio whatever the grid row does — a tile that
           renders its picture but not its name is the same failure as a tile
           with no name at all, and the two halves are pinned so neither can
           squeeze the other out. */
        .libthumb { aspect-ratio:16/9; flex:0 0 auto; background:#1B1B1A;
          display:flex; align-items:center; justify-content:center;
          overflow:hidden; }
        .libthumb video, .libthumb img { width:100%; height:100%;
          object-fit:cover; display:block; }
        .libthumb.contain { background:#F5F5F3; }
        .libthumb.contain img { width:auto; height:auto; max-width:70%;
          max-height:62%; object-fit:contain; }
        .libthumb-none { display:flex; align-items:center; justify-content:center;
          width:100%; height:100%; color:#5A5A56; }
        .libthumb-none svg { width:26px; height:26px; }
      `}</style>
    </div>
  )
}
