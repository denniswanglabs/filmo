'use client'
import { useEffect, useRef, useState } from 'react'
import FilmoMark from './FilmoMark'

/* ───────────────────────────────────────────────────────────────────────────
   FILMO — the landing.

   A faithful port of the signed-off prototype (`landing-lab/index.html`),
   whose structure was learned from a teardown of ploy.ai and applied to our
   subject:
   · TWO-LAYER HERO — a clipping video box and a NON-clipping text layer that
     duplicates its exact height calc, so the radius can never cut the type.
   · Height is calc(100vh - 130px + 110px): deliberately taller than the fold
     so the page announces there is more below.
   · A CENTRE-WEIGHTED radial scrim, not a bottom gradient — legibility in the
     middle while the footage keeps its brightness at the edges.
   · A three-step display scale (112 / 76 / 56) and nothing in between.
   · Load stagger of 120/220/320ms across headline → lede → CTA.
   · Scroll-fill headings via background-clip:text driven by a --progress var.
   · Mobile trades the inset card for full-bleed and re-anchors type low-left.

   Where it departs on purpose: Ploy is a bright cream gallery with a film hung
   on the wall. Filmo MAKES films, so this is the dark of a screening room and
   the work is the only light source.

   PORTING NOTES — every rule is scoped under `.fl`. The prototype styled bare
   `nav` / `section` / `h2` / `footer`, which in a single-page document is fine
   and in an app is not: this stylesheet shares a document with AuthGate, and an
   unscoped `h2 { margin:18px 0 0 }` would silently restyle the sign-in dialog.
   The one deliberately global rule is `html{scroll-behavior:smooth}`, which the
   in-page anchors need; it unmounts with the route, so it never reaches
   /videos or the studio (globals.css leaves scroll-behavior alone on purpose,
   so Motion.tsx's scrollIntoView stays in control there).
   ─────────────────────────────────────────────────────────────────────────── */

// Load-stagger delay as a custom property. TS's CSSProperties has no index
// signature for custom properties, so the cast is the standard escape hatch.
const delay = (ms: number) => ({ '--d': `${ms}ms` }) as React.CSSProperties

const SITES = [
  { src: '/landing/insforge.jpg', host: 'insforge.dev' },
  { src: '/landing/stripe.jpg', host: 'stripe.com' },
  { src: '/landing/linear.jpg', host: 'linear.app' },
  { src: '/landing/vercel.jpg', host: 'vercel.com' },
]

// ── THE WORK FILM (the real delivered InsForge cut, 2026-07-20) ──────────────
// ONE film, and the copy beside it speaks in the singular to match it. This is
// the canonical stored deliverable of the most recent insforge.dev run
// (runs.final_url — NOT the old trimmed /landing/insforge.mp4 placeholder),
// streamed through /api/media, which stamps the MIME storage drops and forwards
// Range. It is a click-to-play poster, not an autoplaying video: the section
// adds one ≤200KB poster to the first paint (lazy, below the fold) and the
// film's megabytes move only when someone actually asks to watch it. Kept as a
// one-item list so the markup and the styling do not have to change if the
// gallery ever grows back.
const GALLERY = [
  {
    host: 'insforge.dev',
    descriptor: 'Agent-native backend platform',
    poster: '/landing/gallery/insforge.jpg',
    src: 'https://jd3mdkqr.ap-southeast.insforge.app/api/storage/buckets/walk-videos/objects/web-1784602257447-19ozq%2Ffinal.mp4?v=1784603379',
  },
]

// Storage serves binary/octet-stream, which <video> refuses to sniff, so a
// played URL rides the same proxy the studio uses (actions.ts proxyPlayableUrl /
// RunMark.tsx): same-origin, no auth, Range-correct.
const proxied = (u: string) => `/api/media?u=${encodeURIComponent(u)}`

// One gallery tile: a lazy poster that becomes its film on click. The click is a
// user gesture, so the film plays with its voiceover; until then it is a single
// <img>, never a buffering <video>.
function GalleryFilm({
  host,
  descriptor,
  poster,
  src,
}: {
  host: string
  descriptor: string
  poster: string
  src: string
}) {
  const [playing, setPlaying] = useState(false)
  return (
    <div className="film">
      {playing ? (
        <video src={proxied(src)} controls autoPlay playsInline preload="auto" />
      ) : (
        <button
          type="button"
          className="filmplay"
          onClick={() => setPlaying(true)}
          aria-label={`Play the ${host} film`}
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={poster} alt="" loading="lazy" />
          <span className="pbtn" aria-hidden="true">
            <svg viewBox="0 0 24 24">
              <path d="M8 5v14l11-7z" />
            </svg>
          </span>
        </button>
      )}
      <div className="cap">
        <b>{host}</b>
        <span>{descriptor}</span>
      </div>
    </div>
  )
}

// ── THE CTA IS STATE-AWARE (Ploy-style, 2026-07-20) ──────────────────────────
// A first-time visitor and a returning-but-signed-out one want different first
// words. A first-timer sees the pair Ploy leads with — a quiet "Log in" and a
// primary "Start free"; someone who has signed in here before (the durable
// `filmo_has_signed_in` flag, which outlives sign-out) sees the single "Enter
// the studio" this landing has always shown. `firstTime` is decided in page.tsx
// (it owns the flag read and the session) and handed down; this component only
// renders it. Every button lands on `/login` when signed out — "Start free"
// carries `?signup=1` so it opens on the create-account state.
export default function PloyLanding({
  firstTime,
  onEnter,
  onLogIn,
  onStartFree,
}: {
  /** No record of ever signing in AND signed out now → the two-button first-run CTA. */
  firstTime: boolean
  /** "Enter the studio" — the returning/signed-in primary. */
  onEnter: () => void
  /** "Log in" — the quiet first-run action (nav only, as Ploy places it). */
  onLogIn: () => void
  /** "Start free" — the first-run primary; replaces "Enter the studio" everywhere. */
  onStartFree: () => void
}) {
  // The repeated primary button (hero, pricing, close): its words and its
  // destination flip together, so a first-timer never sees "Enter the studio"
  // and a returning visitor never sees "Start free".
  const primaryLabel = firstTime ? 'Start free' : 'Enter the studio'
  const onPrimary = firstTime ? onStartFree : onEnter
  const rootRef = useRef<HTMLDivElement>(null)
  const navRef = useRef<HTMLElement>(null)
  const viewRef = useRef<HTMLDivElement>(null)
  const urlRef = useRef<HTMLSpanElement>(null)

  // The landing is a screening room, so the dark ground has to reach past the
  // page box: without this a rubber-band overscroll on macOS flashes the app's
  // white <body> above the hero. Restored on unmount so /videos and the studio
  // get their daylight back.
  useEffect(() => {
    const body = document.body
    const prev = body.style.background
    body.style.background = '#0A0A0B'
    return () => {
      body.style.background = prev
    }
  }, [])

  // ── The browsing loop ────────────────────────────────────────────────────
  // A real page panning under the recorder's frame — each one a site we
  // actually captured, cycling as a recording would. No mockups, and no brand
  // ornament riding over it: the frame shows the product working, nothing else.
  useEffect(() => {
    const view = viewRef.current
    const urlEl = urlRef.current
    if (!view || !urlEl) return
    const pages = Array.from(view.querySelectorAll<HTMLImageElement>('.fl-bpages img'))
    if (!pages.length) return

    // Reduced motion: the CSS below kills every transition, which would turn
    // the pan into a 5-second-interval JUMP — worse than no motion at all. So
    // the page still cycles (the content is the point) and the pan and the
    // wander simply don't run.
    const reduced =
      typeof window.matchMedia === 'function' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches

    let i = 0
    let step = 0
    let stopped = false
    let timer: ReturnType<typeof setTimeout> | undefined

    const show = () => {
      pages.forEach((p, n) => p.classList.toggle('on', n === i))
      urlEl.textContent = pages[i].dataset.host ?? ''
    }

    const glide = () => {
      if (stopped) return
      const p = pages[i]
      if (!reduced) {
        // Pan the page under the frame, as a slow scroll.
        const travel = Math.max(0, p.offsetHeight - view.offsetHeight)
        p.style.transition = 'transform 5.2s linear, opacity .9s ease'
        p.style.transform = `translateY(${-travel * (step ? 0.62 : 0.08)}px)`
      }
      step++
      if (step > 1) {
        step = 0
        timer = setTimeout(() => {
          if (stopped) return
          pages[i].style.transition = 'none'
          pages[i].style.transform = 'translateY(0)'
          i = (i + 1) % pages.length
          show()
          glide()
        }, 5200)
      } else {
        timer = setTimeout(glide, 5200)
      }
    }

    show()
    glide()
    return () => {
      stopped = true
      if (timer) clearTimeout(timer)
    }
  }, [])

  // Section reveals.
  useEffect(() => {
    const root = rootRef.current
    if (!root) return
    const io = new IntersectionObserver(
      (es) =>
        es.forEach((e) => {
          if (e.isIntersecting) {
            e.target.classList.add('in')
            io.unobserve(e.target)
          }
        }),
      { threshold: 0.12 },
    )
    root.querySelectorAll('.fl-rise').forEach((el) => io.observe(el))
    return () => io.disconnect()
  }, [])

  // Scroll-fill headings + the nav's scrolled state.
  useEffect(() => {
    const root = rootRef.current
    const nav = navRef.current
    if (!root || !nav) return
    const fills = Array.from(root.querySelectorAll<HTMLElement>('[data-fill]'))
    const onScroll = () => {
      for (const el of fills) {
        const r = el.getBoundingClientRect()
        const p = (window.innerHeight * 0.8 - r.top) / (window.innerHeight * 0.45)
        el.style.setProperty('--progress', `${Math.max(0, Math.min(1, p)) * 100}%`)
      }
      nav.classList.toggle('scrolled', window.scrollY > 20)
    }
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  return (
    <div className="fl" ref={rootRef} data-filmo-landing="">
      <style>{`
/* The in-page anchors need this; it unmounts with the route. */
html { scroll-behavior:smooth }

.fl {
  --ink:#F4F3F0;
  --ink-faded:rgba(244,243,240,.16);   /* the scroll-fill "empty" state */
  --ground:#0A0A0B;
  --ground-2:#111113;
  --muted:#8B8B90;
  --line:#232327;
  --accent:#4B8DF8;
  --pad:26px;
  --spring:cubic-bezier(.22,1,.36,1);
  background:var(--ground); color:var(--ink);
  font:16px/1.6 ui-sans-serif,-apple-system,"Segoe UI",Roboto,sans-serif;
  -webkit-font-smoothing:antialiased;
  /* Keeps the hero video's scale(1.5) from widening the page. Note this
     promotes overflow-y to auto (CSS computes the other axis to auto when one
     is not visible), so this box is technically a scroll container — harmless,
     because it is content-sized and never actually scrolls. overflow-x:clip
     avoids the promotion and was measured to be equivalent for the fixed nav,
     so either works; hidden is what the approved prototype used.
     If the nav ever appears to scroll away, this rule is NOT the cause — see
     the note on .fl nav below. */
  overflow-x:hidden;
  min-height:100vh;
}
.fl *{box-sizing:border-box}

/* Display face: a Druk/FK-Screamer-class condensed is the target to license;
   Impact is the universally present stand-in so the composition reads true. */
.fl .display{font-family:"Anton","Haettenschweiler","Impact","Arial Narrow Bold",sans-serif;
  font-weight:400;text-transform:uppercase;letter-spacing:-.005em;line-height:.87}
/* THREE STEPS, nothing between them. */
.fl .d1{font-size:112px} .fl .d2{font-size:76px} .fl .d3{font-size:56px}
@media(max-width:1100px){ .fl .d1{font-size:76px} .fl .d2{font-size:56px} .fl .d3{font-size:44px} }
@media(max-width:640px){ .fl .d1{font-size:52px} .fl .d2{font-size:42px} .fl .d3{font-size:34px} }

/* ── nav ───────────────────────────────────────────────────────────────────
   A REAL BAND, always. It carries an opaque-enough ground plus a blur at rest
   and goes heavier with a hairline once the page moves, so content can never
   show through it or collide with it at any scroll position. Anchor jumps clear
   it too: scroll-margin-top:96px on the sections parks them below the 83px
   band rather than under it.

   ⚠ KNOWN, APP-WIDE, NOT THIS FILE'S DOING: app/template.tsx wraps every route
   in a framer-motion div that animates translateY(6px → 0) over 280ms. A
   transformed ancestor becomes the containing block for its fixed descendants,
   so for those 280ms this nav (and the boot cover, and AuthGate) is fixed to the
   PAGE rather than the viewport. It settles the moment framer-motion writes
   transform:none, and route entry always happens at scrollY 0, so the visible
   consequence is a ≤6px offset nobody can see. It only becomes a real "the nav
   scrolled away" bug if that animation never finishes — which is what you are
   looking at if you ever see it. The existing FloatingNav on /videos, /assets
   and /how-it-works sits under the identical condition. */
.fl nav{position:fixed;inset:0 0 auto 0;z-index:40;display:flex;align-items:center;
  justify-content:space-between;padding:18px var(--pad);
  background:rgba(10,10,11,.72);backdrop-filter:blur(18px) saturate(1.2);
  -webkit-backdrop-filter:blur(18px) saturate(1.2);
  border-bottom:1px solid transparent;transition:background .3s,border-color .3s}
.fl nav.scrolled{background:rgba(10,10,11,.92);border-bottom-color:var(--line)}
.fl .brand{display:flex;align-items:center;gap:15px;font-size:28.5px;font-weight:650;
  letter-spacing:-.02em;margin-left:10px}
.fl .brand svg{width:39px;height:39px;flex:0 0 auto;display:block}
.fl .navlinks{display:flex;gap:28px;font-size:15px;color:rgba(244,243,240,.72)}
.fl .navlinks a{color:inherit;text-decoration:none;transition:color .15s}
.fl .navlinks a:hover{color:var(--ink)}
.fl .cta{display:inline-flex;align-items:center;background:var(--ink);color:#0A0A0B;
  font:600 14px/1 ui-sans-serif,-apple-system,"Segoe UI",Roboto,sans-serif;
  letter-spacing:-.01em;padding:16px 24px;border-radius:100rem;
  text-decoration:none;border:none;cursor:pointer;
  /* Spring easing with a slight overshoot — physics, no JS. */
  transition:transform .45s cubic-bezier(.34,1.56,.64,1),background .2s}
.fl .cta:hover{transform:translateY(-2px);background:#fff}
.fl .cta:focus-visible{outline:2px solid var(--accent);outline-offset:3px}
.fl .cta.ghost{background:transparent;color:var(--ink);box-shadow:inset 0 0 0 1px rgba(244,243,240,.28)}
.fl .cta.ghost:hover{background:rgba(244,243,240,.08)}
/* The first-run pair. "Log in" is a quiet text button (not a second pill), so
   the eye still lands on "Start free" and the two fit the nav at 390px. */
.fl .navcta{display:flex;align-items:center;gap:14px}
.fl .loginlink{background:none;border:none;cursor:pointer;
  color:rgba(244,243,240,.72);letter-spacing:-.01em;padding:8px 4px;
  font:600 14px/1 ui-sans-serif,-apple-system,"Segoe UI",Roboto,sans-serif;
  transition:color .15s}
.fl .loginlink:hover{color:var(--ink)}
.fl .loginlink:focus-visible{outline:2px solid var(--accent);outline-offset:3px;border-radius:6px}

/* ── hero: two layers, matching height calcs ──────────────────────────────── */
.fl .hero{position:relative;padding:88px var(--pad) 0}
.fl .stage,.fl .overlay{height:calc(100vh - 130px + 110px);min-height:660px;max-height:1020px}
.fl .stage{position:relative;border-radius:14px;overflow:hidden;background:#000;
  max-width:2400px;margin:0 auto}
.fl .stage video{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;
  /* Framed past the workspace's rail seam so the backdrop stays live but
     unreadable — its own titles must never compete with ours. */
  filter:saturate(.72) contrast(.92) brightness(.44) blur(2px);
  transform:scale(1.5) translateX(5%)}
.fl .scrim{position:absolute;inset:0;
  background:radial-gradient(ellipse 72% 58% at 50% 48%,
    rgba(10,10,11,.62) 0%, rgba(10,10,11,.4) 44%, rgba(10,10,11,0) 76%)}
.fl .overlay{position:absolute;left:var(--pad);right:var(--pad);top:88px;z-index:10;
  max-width:2400px;margin:0 auto;display:flex;flex-direction:column;align-items:center;
  justify-content:center;text-align:center;gap:26px;pointer-events:none;padding:0 20px}
.fl .overlay>*{pointer-events:auto}
.fl .overlay h1{margin:0;max-width:15ch;text-wrap:balance;text-shadow:0 14px 70px rgba(0,0,0,.55)}
.fl .lede{margin:0;max-width:42ch;font-size:17px;line-height:1.5;color:rgba(244,243,240,.82)}
.fl .herobtns{display:flex;gap:12px;flex-wrap:wrap;justify-content:center}
/* Load stagger: headline → lede → CTA. */
.fl .in-up{animation:fl-heroIn .72s var(--spring) both;animation-delay:var(--d,0ms)}
@keyframes fl-heroIn{from{opacity:0;transform:translateY(22px)}to{opacity:1;transform:none}}

/* ── sections ─────────────────────────────────────────────────────────────── */
.fl section{padding:150px var(--pad);max-width:1180px;margin:0 auto;scroll-margin-top:96px}
.fl .eyebrow{font-size:11px;letter-spacing:.16em;text-transform:uppercase;color:var(--muted)}
.fl h2{margin:18px 0 0;max-width:17ch}
.fl .sub{color:var(--muted);max-width:52ch;margin:18px 0 0;font-size:17px}
/* Scroll-fill: words sit at 16% ink and fill to full as --progress rises. */
.fl .fill{color:transparent;background-color:var(--ink-faded);
  background-image:linear-gradient(90deg,var(--ink),var(--ink) var(--progress,0%),transparent var(--progress,0%));
  -webkit-background-clip:text;background-clip:text}
.fl .films{display:grid;grid-template-columns:1fr;gap:16px;margin-top:48px;max-width:900px}
.fl .film{border-radius:12px;overflow:hidden;background:var(--ground-2);box-shadow:inset 0 0 0 1px var(--line)}
.fl .film video{display:block;width:100%;aspect-ratio:16/9;object-fit:cover;background:#000}
/* Click-to-play poster: a full-tile button, the film only loads on the click. */
.fl .filmplay{display:block;position:relative;width:100%;aspect-ratio:16/9;padding:0;border:0;
  cursor:pointer;background:#000;overflow:hidden}
.fl .filmplay img{display:block;width:100%;height:100%;object-fit:cover;
  transition:transform .5s var(--spring),filter .3s}
.fl .filmplay:hover img{transform:scale(1.03);filter:brightness(1.06)}
/* Glassmorphic play chip — blur + low-opacity ground + a bright hairline. */
.fl .filmplay .pbtn{position:absolute;inset:0;margin:auto;width:56px;height:56px;border-radius:50%;
  background:rgba(10,10,11,.5);backdrop-filter:blur(7px);-webkit-backdrop-filter:blur(7px);
  border:1px solid rgba(244,243,240,.42);display:flex;align-items:center;justify-content:center;
  transition:transform .3s var(--spring),background .2s}
.fl .filmplay:hover .pbtn{transform:scale(1.09);background:rgba(10,10,11,.68)}
.fl .filmplay .pbtn svg{width:20px;height:20px;margin-left:2px;fill:var(--ink)}
.fl .filmplay:focus-visible{outline:2px solid var(--accent);outline-offset:3px}
.fl .film .cap{padding:15px 17px}
.fl .film .cap b{display:block;font-size:14.5px;font-weight:600}
.fl .film .cap span{font-size:12.5px;color:var(--muted)}
.fl .browser{margin-top:48px;border-radius:14px;overflow:hidden;background:var(--ground-2);
  box-shadow:inset 0 0 0 1px var(--line),0 40px 90px -50px rgba(0,0,0,.8)}
.fl .bchrome{display:flex;align-items:center;gap:14px;padding:12px 16px;
  border-bottom:1px solid var(--line)}
.fl .bdots{display:flex;gap:6px}
.fl .bdots i{width:9px;height:9px;border-radius:50%;background:#2C2C31}
.fl .burl{flex:1;text-align:center;font-size:12.5px;color:var(--muted);
  background:#0E0E10;border-radius:7px;padding:5px 12px;max-width:420px;margin:0 auto;
  transition:opacity .3s}
.fl .brec{display:flex;align-items:center;gap:7px;font-size:11.5px;color:var(--muted)}
.fl .brec i{width:7px;height:7px;border-radius:50%;background:#EF4444;
  animation:fl-recpulse 1.4s ease-in-out infinite}
@keyframes fl-recpulse{0%,100%{opacity:1}50%{opacity:.25}}
.fl .bview{position:relative;height:min(58vh,520px);overflow:hidden;background:#0E0E10}
.fl .fl-bpages img{position:absolute;top:0;left:0;width:100%;opacity:0;
  transition:opacity .9s ease}
.fl .fl-bpages img.on{opacity:1}
.fl .steps{display:grid;grid-template-columns:repeat(auto-fit,minmax(270px,1fr));gap:28px;margin-top:56px}
.fl .step{border-top:1px solid var(--line);padding-top:22px}
.fl .step .n{font-size:12px;color:var(--accent);letter-spacing:.1em}
.fl .step h3{margin:14px 0 8px;font-size:20px;font-weight:600}
.fl .step p{margin:0;color:var(--muted);font-size:15px;line-height:1.6}
.fl .plan{max-width:420px;margin:44px auto 0;background:var(--ground-2);
  border-radius:18px;padding:34px 32px;box-shadow:inset 0 0 0 1px var(--line);text-align:left}
.fl .plan .rows{border-top:1px solid var(--line);padding-top:18px;display:grid;gap:11px;
  font-size:14.5px;color:var(--muted)}
.fl .close{text-align:center;padding:170px var(--pad)}
/* Bookend: the hero opens on an inset panel, the footer closes on one. */
.fl .footwrap{padding:0 var(--pad) var(--pad)}
.fl footer{background:var(--ground-2);border-radius:20px;padding:48px 40px;
  display:flex;justify-content:space-between;gap:26px;flex-wrap:wrap;
  color:var(--muted);font-size:14px;box-shadow:inset 0 0 0 1px var(--line)}

@media(max-width:767px){
  .fl .navlinks{display:none}
  /* Full-bleed, squared, type re-anchored low and LEFT. */
  .fl .hero{padding:0}
  .fl .stage,.fl .overlay{height:calc(98svh + 90px);min-height:620px}
  .fl .stage{border-radius:0}
  .fl .overlay{left:0;right:0;top:0;align-items:flex-start;text-align:left;
    justify-content:flex-end;padding:0 20px 130px;gap:20px}
  .fl .overlay h1{max-width:none}
  .fl .herobtns{width:100%}
  .fl section{padding:96px 20px}
}
@media(prefers-reduced-motion:reduce){.fl *{animation:none!important;transition:none!important}}
.fl .fl-rise{opacity:0;transform:translateY(20px);transition:opacity .8s var(--spring),transform .8s var(--spring)}
.fl .fl-rise.in{opacity:1;transform:none}
      `}</style>

      <nav ref={navRef}>
        <div className="brand">
          <FilmoMark />
          Filmo
        </div>
        <div className="navlinks">
          <a href="#work">Work</a>
          <a href="#how">How it works</a>
          <a href="#studio">The studio</a>
          <a href="#pricing">Pricing</a>
        </div>
        {firstTime ? (
          <div className="navcta">
            <button type="button" className="loginlink" onClick={onLogIn}>
              Log in
            </button>
            <button type="button" className="cta" onClick={onStartFree}>
              Start free
            </button>
          </div>
        ) : (
          <button type="button" className="cta" onClick={onEnter}>
            Enter the studio
          </button>
        )}
      </nav>

      <div className="hero">
        <div className="stage">
          <video
            src="/landing/hero.mp4"
            poster="/landing/hero-poster.jpg"
            autoPlay
            muted
            loop
            playsInline
            preload="auto"
          />
          <div className="scrim" />
        </div>
        <div className="overlay">
          <h1 className="display d1 in-up" style={delay(120)}>
            Your launch deserves a film,
            <br />
            not a screen recording.
          </h1>
          <p className="lede in-up" style={delay(220)}>
            Filmo reads your product, films it, and cuts a launch video in an hour — every word
            in it taken from your own pages.
          </p>
          <div className="herobtns in-up" style={delay(320)}>
            <button type="button" className="cta" onClick={onPrimary}>
              {primaryLabel}
            </button>
            <a className="cta ghost" href="#work">
              Watch what it made
            </a>
          </div>
        </div>
      </div>

      <section id="work" className="fl-rise">
        <div className="eyebrow">The work</div>
        <h2 className="display d2 fill" data-fill>
          Your product shipped. Its video didn&rsquo;t.
        </h2>
        <p className="sub">
          This started as a link and finished as a cut. No brief, no storyboard call, no stock
          footage — the palette, the words, and the footage all came off the site.
        </p>
        <div className="films">
          {GALLERY.map((f) => (
            <GalleryFilm key={f.host} {...f} />
          ))}
        </div>
      </section>

      <section id="how" className="fl-rise">
        <div className="eyebrow">How it works</div>
        <h2 className="display d2">It watches your product the way a customer would.</h2>
        <div className="steps">
          <div className="step">
            <div className="n">01</div>
            <h3>It reads</h3>
            <p>
              Homepage first, then the pages a buyer actually opens — pricing, customers, docs.
              Every line it later says out loud came from one of them.
            </p>
          </div>
          <div className="step">
            <div className="n">02</div>
            <h3>It films</h3>
            <p>
              A real browser glides through your product on camera. Not screenshots
              cross-fading — actual motion through the actual pages.
            </p>
          </div>
          <div className="step">
            <div className="n">03</div>
            <h3>It cuts</h3>
            <p>
              Beats built on your own palette, then a review pass that watches the film back and
              fixes what doesn&rsquo;t hold before you ever see it.
            </p>
          </div>
        </div>
      </section>

      <section id="studio" className="fl-rise">
        <div className="eyebrow">The studio</div>
        <h2 className="display d2">Watch it work. Then tell it what to change.</h2>
        <p className="sub">
          It reads the pages a buyer would open, films them on camera, and narrates every move as
          it goes. When the film lands you edit it by saying so.
        </p>

        <div className="browser">
          <div className="bchrome">
            <span className="bdots">
              <i />
              <i />
              <i />
            </span>
            <span className="burl" ref={urlRef}>
              insforge.dev
            </span>
            <span className="brec">
              <i />
              Recording
            </span>
          </div>
          <div className="bview" ref={viewRef}>
            <div className="fl-bpages">
              {SITES.map((s) => (
                // eslint-disable-next-line @next/next/no-img-element
                <img key={s.host} src={s.src} alt="" data-host={s.host} />
              ))}
            </div>
          </div>
        </div>
      </section>

      <section id="pricing" className="fl-rise" style={{ textAlign: 'center' }}>
        <div className="eyebrow">Pricing</div>
        <h2 className="display d2" style={{ marginLeft: 'auto', marginRight: 'auto' }}>
          Free while Filmo is in beta.
        </h2>
        {/* No film count and no end date, deliberately. A film and a re-cut spend
            from the same allowance at different rates, so any "about N films"
            is a promise the meter cannot keep. State the allowance; it is
            exactly true for everyone. */}
        <p className="sub" style={{ marginLeft: 'auto', marginRight: 'auto' }}>
          Every account gets <b style={{ color: 'var(--ink)' }}>3,000 credits a day</b>. Credits
          are metered on the work itself — a film costs more than a re-cut — they refresh every
          morning, and failed builds are refunded automatically. There&rsquo;s no card to add.
        </p>
        <div className="plan">
          <div style={{ fontSize: 15, fontWeight: 600 }}>Free</div>
          <div className="display d2" style={{ margin: '10px 0 4px' }}>
            $0
          </div>
          <div style={{ color: 'var(--muted)', fontSize: 14, marginBottom: 22 }}>
            No card required.
          </div>
          <div className="rows">
            <div>3,000 credits a day</div>
            <div>A film costs more than a re-cut</div>
            <div>Real screen recordings, on camera</div>
            <div>Re-cut by chat, as often as your credits allow</div>
            <div>Every film downloadable, yours to use</div>
          </div>
          <button
            type="button"
            className="cta"
            style={{ marginTop: 26, width: '100%', justifyContent: 'center' }}
            onClick={onPrimary}
          >
            {primaryLabel}
          </button>
        </div>
      </section>

      <div className="close fl-rise">
        <h2 className="display d1" style={{ margin: '0 auto', maxWidth: '12ch' }}>
          Give it a link.
        </h2>
        <p className="sub" style={{ margin: '22px auto 34px' }}>
          Free while Filmo is in beta — 3,000 credits a day, no card to add.
        </p>
        <button type="button" className="cta" onClick={onPrimary}>
          {primaryLabel}
        </button>
      </div>

      <div className="footwrap">
        <footer>
          <div>© 2026 Filmo — a Luceo Studio product</div>
          <div>Launch films from your URL</div>
        </footer>
      </div>
    </div>
  )
}
