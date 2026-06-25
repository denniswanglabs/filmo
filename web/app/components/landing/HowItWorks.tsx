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
    body: 'Walk Studio opens your real product and runs a Conversion Read — scoring promise, proof, specificity, and CTA.',
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

export default function HowItWorks() {
  return (
    <section id="how" className="bg-white px-5 py-20 sm:py-24">
      <div className="mx-auto max-w-5xl">
        {/* Section header (centered) */}
        <Reveal className="mx-auto max-w-xl text-center">
          <span className="inline-block rounded-full border border-amber/20 bg-amber/5 px-3 py-1 text-xs font-medium text-amber">
            How it works
          </span>
          <h2 className="mt-4 text-3xl font-semibold tracking-tight text-ink sm:text-4xl">
            From a link to a launch video.
          </h2>
          <p className="mx-auto mt-3 max-w-xl text-slate-500">
            No brief, no timeline, no editor. Paste your URL and Walk Studio does the rest.
          </p>
        </Reveal>

        {/* Steps grid */}
        <RevealGroup
          as="ol"
          className="mt-12 grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4"
        >
          {STEPS.map((step) => (
            <RevealItem
              as="li"
              key={step.n}
              className="rounded-2xl border border-black/5 bg-white p-6 shadow-[0_18px_50px_-20px_rgba(20,23,28,0.25)] transition hover:border-black/10 hover:shadow-sm"
            >
              <span className="grid h-9 w-9 place-items-center rounded-full bg-amber/10 text-sm font-semibold text-amber">
                {step.n}
              </span>
              <h3 className="mt-4 font-semibold tracking-tight text-ink">{step.title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-slate-500">{step.body}</p>
            </RevealItem>
          ))}
        </RevealGroup>
      </div>
    </section>
  )
}
