'use client'
import { useEffect, useRef } from 'react'
import Link from 'next/link'
import FilmoMark from '../components/landing2/FilmoMark'

/* ───────────────────────────────────────────────────────────────────────────
   /how-it-works — A CHAPTER OF THE LANDING, NOT A SECOND BROCHURE.

   The page this replaces was the old light-blue marketing shell (FloatingNav,
   panel--dark sections, ClosingCTA, SiteFooter) — a leftover from the landing
   Filmo no longer has. The landing is `landing2/PloyLanding` now: the dark of
   a screening room, a three-step display scale, eyebrow → display h2 → sub,
   steps on hairline rules, scroll-fill headings, and an inset-panel footer.
   This page is written in exactly that grammar — same tokens, same faces, same
   nav band, same footer — so walking `/` → `/how-it-works` reads as turning a
   page, not changing books.

   What it does NOT copy from the landing: the hero video stage and the
   browsing-loop browser. Those are the cover's showpieces; a chapter opens on
   type. Everything else — the tokens, the classes, the easing, the reveal
   behaviour, the reduced-motion kill — is the landing's verbatim, under a
   `.hw` scope so the two stylesheets cannot fight if both are ever mounted
   during a route transition.

   The copy states what the pipeline actually does (reads the buyer's pages,
   films them in a real browser, cuts on the site's own palette, reviews the
   film back, re-cuts by chat) and repeats the landing's own claims where they
   overlap — one book, one voice, no invented facts.
   ─────────────────────────────────────────────────────────────────────────── */

const STEPS = [
  {
    n: '01',
    title: 'It reads',
    body:
      'Homepage first, then the pages a buyer actually opens — pricing, customers, docs. Every line the film later says out loud came from one of them; nothing is invented on your behalf.',
  },
  {
    n: '02',
    title: 'It plans the cut',
    body:
      'From what it read it writes the storyboard: the beats, the words, the palette — all taken off your own pages. The plan is the film stated in advance, not a prompt thrown at a generator.',
  },
  {
    n: '03',
    title: 'It films',
    body:
      'A real browser glides through your product on camera. Not screenshots cross-fading — actual motion through the actual pages, recorded the way a customer would see them.',
  },
  {
    n: '04',
    title: 'It cuts',
    body:
      'Beats built on your own palette, narrated as it goes. Then a review pass watches the finished film back and fixes what doesn’t hold before you ever see it.',
  },
  {
    n: '05',
    title: 'You re-cut by saying so',
    body:
      'When the film lands you edit it in the studio by telling it what to change — tighten the open, swap a beat, re-voice a line — as often as your credits allow.',
  },
]

const HOLDS = [
  {
    title: 'Your words, not stock ones',
    body:
      'The palette, the copy and the footage all come off your site. The result looks like you — never like stock AI footage wearing your logo.',
  },
  {
    title: 'Real recordings, on camera',
    body:
      'The product is filmed in a live browser, so what moves on screen is your actual interface doing its actual job.',
  },
  {
    title: 'Reviewed before delivery',
    body:
      'A review pass watches the cut end to end and re-cuts what fails. What reaches you is the film that survived it.',
  },
  {
    title: 'A file that is yours',
    body:
      'Every film is a finished MP4 you download and use anywhere — your hero section, a launch post, an investor update.',
  },
]

export default function HowItWorksChapter() {
  const rootRef = useRef<HTMLDivElement>(null)
  const navRef = useRef<HTMLElement>(null)

  // Same reason as the landing: the ground has to reach past the page box, or a
  // rubber-band overscroll flashes the app's white <body> above the chapter.
  useEffect(() => {
    const body = document.body
    const prev = body.style.background
    body.style.background = '#0A0A0B'
    return () => {
      body.style.background = prev
    }
  }, [])

  // Section reveals — the landing's IntersectionObserver, verbatim.
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
    root.querySelectorAll('.hw-rise').forEach((el) => io.observe(el))
    return () => io.disconnect()
  }, [])

  // Scroll-fill headings + the nav's scrolled state — the landing's, verbatim.
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
    <div className="hw" ref={rootRef}>
      <style>{`
.hw {
  --ink:#F4F3F0;
  --ink-faded:rgba(244,243,240,.16);
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
  overflow-x:hidden;
  min-height:100vh;
}
.hw *{box-sizing:border-box}

/* The landing's display face and its three steps — nothing between them. */
.hw .display{font-family:"Anton","Haettenschweiler","Impact","Arial Narrow Bold",sans-serif;
  font-weight:400;text-transform:uppercase;letter-spacing:-.005em;line-height:.87}
.hw .d1{font-size:112px} .hw .d2{font-size:76px} .hw .d3{font-size:56px}
@media(max-width:1100px){ .hw .d1{font-size:76px} .hw .d2{font-size:56px} .hw .d3{font-size:44px} }
@media(max-width:640px){ .hw .d1{font-size:52px} .hw .d2{font-size:42px} .hw .d3{font-size:34px} }

/* ── nav — the landing's band: a REAL band, always. Opaque-enough ground +
   blur at rest, heavier with a hairline once the page moves, so content can
   never show through it or collide with it. Anchor jumps clear it via
   scroll-margin-top on the sections. ⚠ Same app-wide template.tsx transform
   caveat as the landing's nav — see PloyLanding's note. */
.hw nav{position:fixed;inset:0 0 auto 0;z-index:40;display:flex;align-items:center;
  justify-content:space-between;padding:18px var(--pad);
  background:rgba(10,10,11,.72);backdrop-filter:blur(18px) saturate(1.2);
  -webkit-backdrop-filter:blur(18px) saturate(1.2);
  border-bottom:1px solid transparent;transition:background .3s,border-color .3s}
.hw nav.scrolled{background:rgba(10,10,11,.92);border-bottom-color:var(--line)}
.hw .brand{display:flex;align-items:center;gap:15px;font-size:28.5px;font-weight:650;
  letter-spacing:-.02em;margin-left:10px;color:var(--ink);text-decoration:none;
  border-radius:8px}
.hw .brand svg{width:39px;height:39px;flex:0 0 auto;display:block}
.hw .brand:focus-visible{outline:2px solid var(--accent);outline-offset:4px}
.hw .navlinks{display:flex;gap:28px;font-size:15px;color:rgba(244,243,240,.72)}
.hw .navlinks a{color:inherit;text-decoration:none;transition:color .15s;border-radius:4px}
.hw .navlinks a:hover{color:var(--ink)}
.hw .navlinks a:focus-visible{outline:2px solid var(--accent);outline-offset:3px;color:var(--ink)}
.hw .cta{display:inline-flex;align-items:center;background:var(--ink);color:#0A0A0B;
  font:600 14px/1 ui-sans-serif,-apple-system,"Segoe UI",Roboto,sans-serif;
  letter-spacing:-.01em;padding:16px 24px;border-radius:100rem;
  text-decoration:none;border:none;cursor:pointer;
  transition:transform .45s cubic-bezier(.34,1.56,.64,1),background .2s}
.hw .cta:hover{transform:translateY(-2px);background:#fff}
.hw .cta:focus-visible{outline:2px solid var(--accent);outline-offset:3px}

/* ── the chapter head: typographic — the cover already ran the film. */
.hw header.hw-head{padding:196px var(--pad) 0;max-width:1180px;margin:0 auto}
.hw .eyebrow{font-size:11px;letter-spacing:.16em;text-transform:uppercase;color:var(--muted)}
.hw h1{margin:18px 0 0;max-width:14ch}
.hw .lede{margin:26px 0 0;max-width:52ch;font-size:17px;line-height:1.6;color:var(--muted)}
.hw .in-up{animation:hw-heroIn .72s var(--spring) both;animation-delay:var(--d,0ms)}
@keyframes hw-heroIn{from{opacity:0;transform:translateY(22px)}to{opacity:1;transform:none}}

/* ── sections — the landing's rhythm. */
.hw section{padding:150px var(--pad);max-width:1180px;margin:0 auto;scroll-margin-top:96px}
.hw h2{margin:18px 0 0;max-width:17ch}
.hw .sub{color:var(--muted);max-width:52ch;margin:18px 0 0;font-size:17px}
.hw .fill{color:transparent;background-color:var(--ink-faded);
  background-image:linear-gradient(90deg,var(--ink),var(--ink) var(--progress,0%),transparent var(--progress,0%));
  -webkit-background-clip:text;background-clip:text}
.hw .steps{display:grid;grid-template-columns:repeat(auto-fit,minmax(270px,1fr));gap:28px;margin-top:56px}
.hw .step{border-top:1px solid var(--line);padding-top:22px}
.hw .step .n{font-size:12px;color:var(--accent);letter-spacing:.1em}
.hw .step h3{margin:14px 0 8px;font-size:20px;font-weight:600}
.hw .step p{margin:0;color:var(--muted);font-size:15px;line-height:1.6}

.hw .close{text-align:center;padding:170px var(--pad)}
.hw .footwrap{padding:0 var(--pad) var(--pad)}
.hw footer{background:var(--ground-2);border-radius:20px;padding:48px 40px;
  display:flex;justify-content:space-between;gap:26px;flex-wrap:wrap;
  color:var(--muted);font-size:14px;box-shadow:inset 0 0 0 1px var(--line)}

@media(max-width:767px){
  .hw .navlinks{display:none}
  .hw header.hw-head{padding-top:150px}
  .hw section{padding:96px 20px}
}
@media(prefers-reduced-motion:reduce){.hw *{animation:none!important;transition:none!important}}
.hw .hw-rise{opacity:0;transform:translateY(20px);transition:opacity .8s var(--spring),transform .8s var(--spring)}
.hw .hw-rise.in{opacity:1;transform:none}
      `}</style>

      <nav ref={navRef}>
        {/* The brand walks you back to the cover. */}
        <Link className="brand" href="/">
          <FilmoMark />
          Filmo
        </Link>
        <div className="navlinks">
          <Link href="/#work">Work</Link>
          <Link href="/#studio">The studio</Link>
          <Link href="/#pricing">Pricing</Link>
        </div>
        {/* `/?new=1` is what "enter and build" means from marketing surfaces —
            the landing resolves it (composer signed in, sign-in gate first when
            not) — see readIntent in app/page.tsx. */}
        <Link className="cta" href="/?new=1">
          Enter the studio
        </Link>
      </nav>

      <header className="hw-head">
        <div className="eyebrow in-up" style={{ '--d': '80ms' } as React.CSSProperties}>
          How it works
        </div>
        <h1 className="display d1 in-up" style={{ '--d': '160ms' } as React.CSSProperties}>
          From a link
          <br />
          to a finished film.
        </h1>
        <p className="lede in-up" style={{ '--d': '260ms' } as React.CSSProperties}>
          You give Filmo a URL. It reads your product the way a customer would, films it in a
          real browser, and cuts a launch video in about an hour — every word in it taken from
          your own pages. This is the whole production, step by step.
        </p>
      </header>

      <section id="pipeline" className="hw-rise">
        <div className="eyebrow">The production</div>
        <h2 className="display d2 fill" data-fill>
          One agent runs the whole studio.
        </h2>
        <p className="sub">
          No brief, no storyboard call, no stock footage. Reading, planning, filming, cutting
          and reviewing are one continuous job, and you can watch every step of it happen live.
        </p>
        <div className="steps">
          {STEPS.map((s) => (
            <div className="step" key={s.n}>
              <div className="n">{s.n}</div>
              <h3>{s.title}</h3>
              <p>{s.body}</p>
            </div>
          ))}
        </div>
      </section>

      <section id="holds" className="hw-rise">
        <div className="eyebrow">Why it holds</div>
        <h2 className="display d2 fill" data-fill>
          True to your product, or it doesn&rsquo;t ship.
        </h2>
        <p className="sub">
          Most AI video invents footage. Filmo is grounded in your actual pages — which is what
          makes the film true, on-brand, and worth putting your name on.
        </p>
        <div className="steps">
          {HOLDS.map((h) => (
            <div className="step" key={h.title}>
              <h3 style={{ marginTop: 0 }}>{h.title}</h3>
              <p>{h.body}</p>
            </div>
          ))}
        </div>
      </section>

      <div className="close hw-rise">
        <h2 className="display d1" style={{ margin: '0 auto', maxWidth: '12ch' }}>
          Give it a link.
        </h2>
        <p className="sub" style={{ margin: '22px auto 34px' }}>
          Free while Filmo is in beta — 3,000 credits a day, no card to add.
        </p>
        <Link className="cta" href="/?new=1">
          Enter the studio
        </Link>
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
