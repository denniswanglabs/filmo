import { Reveal, RevealGroup, RevealItem } from './Motion'

interface Step {
  n: number
  title: string
  body: string
}

const STEPS: readonly Step[] = [
  {
    n: 1,
    title: 'Hermes reads your page',
    body: "The agent opens your real site and runs a Conversion Read on NVIDIA Nemotron, scoring six dimensions of how the page converts and pulling your real name, colors, logo, stats, and story. The diagnosis seeds the whole video.",
  },
  {
    n: 2,
    title: 'Hermes plans the cut',
    body: 'It has Nemotron write a scene-by-scene storyboard from your real facts — never invented copy — matching each scene to a hand-curated designer pattern harvested from real launch films.',
  },
  {
    n: 3,
    title: 'Hermes clears the payment',
    body: 'Hermes prices every job to turn a profit — capped at $10 — and takes payment on Stripe (test mode), no human in the loop.',
  },
  {
    n: 4,
    title: 'Hermes produces the video',
    body: 'It captures your real page and logo and renders the curated patterns with your real screenshot, logo, and an ElevenLabs voiceover.',
  },
  {
    n: 5,
    title: 'Hermes ships it',
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
            Filmo is a Hermes agent. Paste a URL and a goal — it reads, plans, pays its own
            way, produces, and ships, conducting every step itself.
          </p>
        </Reveal>

        {/* Steps grid */}
        <RevealGroup
          as="ol"
          className="mt-12 grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-5"
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

        {/* "The engine" — the sponsor stack that orchestrates the pipeline above.
            Accurate framing: Hermes is the agent HARNESS (orchestration runtime),
            Nemotron is the reasoning BRAIN, NemoClaw is the sandbox the production
            runs inside, Stripe is TEST-mode payment. No real-charge / metric claims. */}
        <Reveal className="mx-auto mt-12 max-w-3xl">
          <p className="rounded-2xl border border-[#D4E2FB] bg-white/70 px-6 py-5 text-center text-sm leading-relaxed text-[#5A6472]">
            <span className="font-semibold text-[#0E1320]">The engine.</span>{' '}
            Hermes (Nous) is the agent runtime orchestrating all of it — reasoning
            on <span className="font-medium text-[#0E1320]">NVIDIA Nemotron</span>,
            sealed inside <span className="font-medium text-[#0E1320]">NVIDIA NemoClaw</span>,
            paying through <span className="font-medium text-[#0E1320]">Stripe</span> (test
            mode). In the sandbox the agent can only pull the five tools we sanctioned —
            autonomy with a leash.
          </p>
        </Reveal>
      </div>
    </section>
  )
}
