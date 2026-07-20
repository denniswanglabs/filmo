'use client'

import { useEffect, useRef, useState } from 'react'

// ── THE MARK IS EITHER LEGIBLY THEIRS, OR VISIBLY NOT A LOGO ────────────────
// There is no third state where we show a mangled thing and let the reader
// assume that is their brand. This component is the whole contract; the header
// just hands it a URL.
//
// It exists because stripe.com rendered as a black rounded square holding a
// broken-image glyph (2026-07-19). The harvest was FINE — the stored asset is
// Stripe's real 60x25 wordmark SVG, 1.9KB, `aria-label="Stripe logo"`. Three
// presentation defects stacked on top of a good asset:
//
//   1. MIME. Storage serves every object as `binary/octet-stream`, and Chrome
//      will not sniff SVG — an <img> pointed straight at the bucket renders the
//      browser's broken-image icon. app/api/_lib/storageStream.ts already
//      declares this invariant ("the browser NEVER plays a storage URL
//      directly") but scoped it to <video>, so marks never got it. Same defect,
//      different tag.
//   2. GROUND. The tile was a fixed `#1B1B1A`. Stripe's ink is `#0a2540`.
//      That is a contrast ratio of 1.11:1 — invisible by composition, not a bad
//      harvest. A constant ground cannot be right for both a dark-ink and a
//      light-ink mark, so the ground is DERIVED FROM THE MARK below.
//   3. CROP. `object-fit: cover` on a square tile. A wordmark is not a square:
//      Stripe's is 2.4:1, so `cover` kept the middle 42% and threw away the
//      rest. A mark is never cropped here, only ever fitted.
//
// Why this went unseen: of 63 marks staged to date, 59 are opaque .ico/.png
// app-icons that carry their OWN background — they get sniffed fine and their
// ink never touches our tile, so both bugs stayed latent. All 4 transparent
// marks in the corpus are Stripe's, harvested as inline SVG. Stripe was simply
// the first brand to exercise the transparent path.

type Ground = { fill: string; border: string }

// The two candidate grounds. Two is provably enough: any ink luminance scores
// at least 3:1 against one of them, so the picker can never come up empty.
const LIGHT: Ground = { fill: '#FFFFFF', border: 'rgba(0,0,0,0.10)' }
const DARK: Ground = { fill: '#1B1B1A', border: 'rgba(255,255,255,0.12)' }
const L_LIGHT = 1
const L_DARK = 0.0109 // relative luminance of #1B1B1A

// A mark whose longest edge is under this is not a logo at any size we draw,
// it is a smear. Below the floor we say so rather than scaling it up.
const MIN_NATURAL_PX = 8

const chan = (v: number) => {
  const c = v / 255
  return c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4)
}
const lum = (r: number, g: number, b: number) =>
  0.2126 * chan(r) + 0.7152 * chan(g) + 0.0722 * chan(b)
const contrast = (a: number, b: number) =>
  (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05)

// Storage objects land on the CDN as `binary/octet-stream`. Route them through
// the app's own proxy, which stamps the real MIME off the extension. Anything
// that is not a storage object (a data: URI, a staged public path) is left
// alone. Bonus: the proxied URL is SAME-ORIGIN, so the canvas probe below can
// read pixels back without CORS or tainting.
function viaProxy(u: string): string {
  try {
    const parsed = new URL(u, window.location.origin)
    if (!parsed.pathname.includes('/api/storage/buckets/')) return u
  } catch {
    return u
  }
  return `/api/media?u=${encodeURIComponent(u)}`
}

type Probe = { ground: Ground; selfGrounded: boolean } | null

// Read the mark's OWN pixels and decide what it can legibly sit on.
//   · fully opaque  -> it carries its own background; our ground never touches
//                      the ink, so the choice is cosmetic. Keep it light.
//   · transparent   -> average the ink, then pick whichever candidate ground
//                      it contrasts with better.
// Returns null when the mark drew nothing at all (a blank or broken asset),
// which the caller treats as "no mark".
function probeMark(img: HTMLImageElement): Probe {
  try {
    const N = 40
    const cv = document.createElement('canvas')
    cv.width = N
    cv.height = N
    const ctx = cv.getContext('2d', { willReadFrequently: true })
    if (!ctx) return { ground: LIGHT, selfGrounded: false }
    const nw = img.naturalWidth || 1
    const nh = img.naturalHeight || 1
    const s = Math.min(N / nw, N / nh)
    const w = Math.max(1, Math.round(nw * s))
    const h = Math.max(1, Math.round(nh * s))
    const ox = Math.floor((N - w) / 2)
    const oy = Math.floor((N - h) / 2)
    ctx.drawImage(img, ox, oy, w, h)
    const d = ctx.getImageData(ox, oy, w, h).data
    const total = w * h
    let opaque = 0
    let sum = 0
    let weight = 0
    for (let i = 0; i < d.length; i += 4) {
      const a = d[i + 3]
      if (a >= 250) opaque++
      if (a < 24) continue
      const wgt = a / 255
      sum += lum(d[i], d[i + 1], d[i + 2]) * wgt
      weight += wgt
    }
    // Nothing meaningful was painted — treat as no mark rather than as a brand.
    if (weight < 1) return null
    if (opaque / total > 0.9) return { ground: LIGHT, selfGrounded: true }
    const ink = sum / weight
    const ground =
      contrast(ink, L_LIGHT) >= contrast(ink, L_DARK) ? LIGHT : DARK
    return { ground, selfGrounded: false }
  } catch {
    // Tainted canvas or a decode we cannot inspect. The mark still displays;
    // we just fall back to the ground that suits the common case (dark ink on
    // transparent, which is how most marks are drawn).
    return { ground: LIGHT, selfGrounded: false }
  }
}

// Visibly Filmo's placeholder, not a claim about anyone's brand: a dashed slot
// with the standard absent-image glyph. Deliberately NOT a lettered badge —
// an initial in a tinted circle reads as a logo, and inventing a logo is the
// exact failure this component exists to prevent.
function AbsentMark({ label }: { label: string }) {
  return (
    <div className="wk-runmark wk-runmark-absent" role="img" aria-label={label}
      title={label}>
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <rect x="3.5" y="5.5" width="17" height="13" rx="2.5" fill="none"
          stroke="currentColor" strokeWidth="1.6" />
        <path d="M6 16.5l3.6-4 2.7 3 2.3-2.4 3.4 3.4" fill="none"
          stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"
          strokeLinejoin="round" />
      </svg>
    </div>
  )
}

export default function RunMark({ src, brand }: { src: string; brand?: string }) {
  const [probe, setProbe] = useState<Probe>(null)
  const [failed, setFailed] = useState(false)
  const imgRef = useRef<HTMLImageElement | null>(null)
  const url = src ? viaProxy(src) : ''

  // Re-probe whenever the mark changes; never leave a stale ground behind.
  useEffect(() => {
    setProbe(null)
    setFailed(false)
  }, [url])

  // NOT YET HARVESTED is not the same as HARVESTED AND UNUSABLE, and only the
  // second one is news. The mark lands a few seconds into every run; until then
  // the header carries the brand in its title alone, exactly as it always has.
  // Announcing "no mark" in that window would be the UI reporting a failure
  // that has not happened yet.
  if (!src) return null
  if (failed) {
    return <AbsentMark label={brand ? `No mark captured for ${brand}` : 'No mark captured'} />
  }

  const ground = probe?.ground ?? LIGHT

  return (
    <img
      ref={imgRef}
      className={'wk-runmark' + (probe ? '' : ' wk-runmark-probing')}
      src={url}
      alt=""
      style={{ background: ground.fill, borderColor: ground.border }}
      onLoad={(e) => {
        const img = e.currentTarget
        // A mark under the floor is not shrunk-but-fine, it is unusable.
        if (Math.max(img.naturalWidth, img.naturalHeight) < MIN_NATURAL_PX) {
          setFailed(true)
          return
        }
        const p = probeMark(img)
        if (!p) {
          setFailed(true)
          return
        }
        setProbe(p)
      }}
      // Broken MIME, 404, blocked fetch — anything that means we cannot show
      // their mark. Degrade to the placeholder instead of leaving the browser's
      // broken-image glyph sitting in a tile that looks like a logo slot.
      onError={() => setFailed(true)}
    />
  )
}
