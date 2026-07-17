import { Reveal, RevealGroup, RevealItem } from './Motion'

interface Step {
  n: number
  title: string
  body: string
}

const STEPS: readonly Step[] = [
  {
    n: 1,
    title: 'Filmo reads your page',
    body: 'Filmo opens your real site and runs a Conversion Read — scoring six dimensions of how the page converts and pulling your real name, colors, logo, stats, and story. The diagnosis seeds the whole video.',
  },
  {
    n: 2,
    title: 'Filmo plans the cut',
    body: 'It writes a scene-by-scene storyboard from your real facts — never invented copy — matching each scene to a hand-curated designer pattern harvested from real launch films.',
  },
  {
    n: 3,
    title: 'Filmo produces the video',
    body: 'It captures your real page and logo and renders the curated patterns with your real screenshot and a studio voiceover.',
  },
  {
    n: 4,
    title: 'Filmo ships it',
    body: 'A finished 1080p MP4 — ready for Product Hunt, X, or your hero section, in minutes.',
  },
]

// `showBadge` lets the embedding page suppress the redundant "How it works" pill
// when the page header already shows one (the dedicated /how-it-works page).
// Defaults true so the standalone landing usage keeps its label.
export default function HowItWorks({ showBadge = true }: { showBadge?: boolean }) {
  return (
    <section id="how" className="panel panel--dark px-5 py-20 sm:py-24">
      {/* Blue glass top edge — our signature on the rounded panel lip. */}
      <span aria-hidden="true" className="panel__edge" />
      <div className="mx-auto max-w-5xl">
        {/* Section header (centered) */}
        <Reveal className="mx-auto max-w-xl text-center">
          {showBadge && <span className="eyebrow">How it works</span>}
          <h2 className="section-title mt-4">
            One agent runs the whole production.
          </h2>
          <p className="section-lede mx-auto max-w-xl">
            Paste a URL and a goal — Filmo reads your real site, plans the cut, produces
            it, and ships, running every step itself.
          </p>
        </Reveal>

        {/* Steps grid */}
        <RevealGroup
          as="ol"
          className="mt-12 grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4"
        >
          {STEPS.map((step, i) => (
            <RevealItem
              as="li"
              key={step.n}
              index={i}
              className="rounded-2xl border border-[#D4E2FB] bg-white p-6 shadow-[0_24px_60px_-34px_rgba(30,58,120,0.22)] ring-1 ring-inset ring-[#EAF1FF] transition hover:-translate-y-0.5 hover:border-[#B9D2F8] hover:shadow-[0_28px_70px_-34px_rgba(30,58,120,0.28)]"
            >
              <span className="grid h-9 w-9 place-items-center rounded-full bg-amber-soft text-sm font-semibold text-[#2563EB]">
                {step.n}
              </span>
              <h3 className="mt-4 font-semibold tracking-tight text-[#0E1320]">{step.title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-[#5A6472]">{step.body}</p>
            </RevealItem>
          ))}
        </RevealGroup>
      </div>
    </section>
  )
}
