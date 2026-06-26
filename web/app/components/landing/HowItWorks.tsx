import { Reveal, RevealGroup, RevealItem } from './Motion'

interface Step {
  n: number
  title: string
  body: string
}

const STEPS: readonly Step[] = [
  {
    n: 1,
    title: 'Read your page',
    body: 'Filmo opens your real product and runs a Conversion Read — scoring promise, proof, specificity, and CTA.',
  },
  {
    n: 2,
    title: 'Plan the cut',
    body: 'Nemotron turns that diagnosis into a scene-by-scene launch storyboard, fixing what the page failed to say.',
  },
  {
    n: 3,
    title: 'Price & produce',
    body: 'It prices the job, captures your live UI, and animates structured, fully editable scenes.',
  },
  {
    n: 4,
    title: 'Ship the MP4',
    body: 'You get a finished 1080p video — ready for Product Hunt, X, or your hero section.',
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
          {showBadge && (
            <span className="inline-block rounded-full border border-amber-line bg-amber-soft px-3 py-1 text-xs font-medium text-[#2563EB]">
              How it works
            </span>
          )}
          <h2 className="mt-4 text-3xl font-semibold tracking-tight text-[#0E1320] sm:text-4xl">
            Four steps, fully autonomous.
          </h2>
          <p className="mx-auto mt-3 max-w-xl text-[#5A6472]">
            No brief, no timeline, no editor. Paste your URL and Filmo does the rest.
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
              className="rounded-2xl border border-[#D4E2FB] bg-white p-6 shadow-[0_24px_60px_-34px_rgba(30,58,120,0.22)] ring-1 ring-inset ring-[#EAF1FF] transition hover:border-[#B9D2F8]"
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
