import type { ReactNode } from 'react'
import { Reveal, RevealGroup, RevealItem } from './Motion'

interface Feature {
  title: string
  body: string
  icon: ReactNode
}

// Shared SVG props — matches the spec icon recipe (no fill, currentColor stroke,
// 1.8 weight, round caps/joins). Color is inherited from the wrapping element.
const iconProps = {
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.8,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
}

const FEATURES: Feature[] = [
  {
    title: 'Grounded in your product',
    body: 'It reads your real page and captures your real UI. The result looks like you, not like stock AI footage.',
    // Eye / scan — reading the real page.
    icon: (
      <svg {...iconProps} aria-hidden="true">
        <path d="M2.5 12s3.5-6.5 9.5-6.5S21.5 12 21.5 12s-3.5 6.5-9.5 6.5S2.5 12 2.5 12Z" />
        <circle cx="12" cy="12" r="2.75" />
      </svg>
    ),
  },
  {
    title: 'The Conversion Read',
    body: 'Before it animates, it diagnoses how your page fails to convert — and writes the video to fix it.',
    // Gauge — scoring the page.
    icon: (
      <svg {...iconProps} aria-hidden="true">
        <path d="M3.5 16a8.5 8.5 0 0 1 17 0" />
        <path d="M12 16l4-4.5" />
        <circle cx="12" cy="16" r="1.1" />
      </svg>
    ),
  },
  {
    title: 'Structured, editable scenes',
    body: 'Every scene is real layout with readable text you can still change — not a one-shot you can’t touch.',
    // Layered rectangles — structured scenes.
    icon: (
      <svg {...iconProps} aria-hidden="true">
        <rect x="7" y="3.5" width="13" height="9" rx="1.6" />
        <path d="M16.5 16.5H5a1.5 1.5 0 0 1-1.5-1.5V7" />
        <path d="M10.5 8.5h6" />
      </svg>
    ),
  },
  {
    title: 'Prices & bills itself',
    body: 'The agent quotes the job and charges through Stripe autonomously — and declines its own over-budget spend.',
    // Card / coin — prices and bills.
    icon: (
      <svg {...iconProps} aria-hidden="true">
        <rect x="2.5" y="6" width="19" height="12" rx="2" />
        <path d="M2.5 10h19" />
        <path d="M6.5 14.5h3" />
      </svg>
    ),
  },
  {
    title: 'Ships a real MP4',
    body: 'A finished 1080p/AAC file, not a preview. Drop it straight onto Product Hunt or your hero section.',
    // Film / play — ships an MP4.
    icon: (
      <svg {...iconProps} aria-hidden="true">
        <rect x="3" y="5" width="18" height="14" rx="2" />
        <path d="M7.5 5v14M16.5 5v14" />
        <path d="M11 9.5l3 2.5-3 2.5V9.5Z" />
      </svg>
    ),
  },
  {
    title: 'Built on NVIDIA Nemotron',
    body: 'One planner reasons over the whole storyboard, so the cut is coherent end to end.',
    // Chip — the model.
    icon: (
      <svg {...iconProps} aria-hidden="true">
        <rect x="7" y="7" width="10" height="10" rx="1.6" />
        <path d="M10 3.5v3.5M14 3.5v3.5M10 17v3.5M14 17v3.5M3.5 10H7M3.5 14H7M17 10h3.5M17 14h3.5" />
      </svg>
    ),
  },
]

export default function Differentiators() {
  return (
    <section className="panel panel--lit px-5 py-20 sm:py-24">
      {/* Blue glass top edge — our signature on the rounded panel lip. */}
      <span aria-hidden="true" className="panel__edge" />
      <div className="mx-auto max-w-5xl">
        {/* Section header (centered) */}
        <Reveal className="mx-auto max-w-xl text-center">
          <span className="inline-block rounded-full border border-amber/30 bg-amber/10 px-3 py-1 text-xs font-medium text-[#6F9BFF]">
            Why Filmo
          </span>
          <h2 className="mt-4 text-3xl font-semibold tracking-tight text-[#F2F4F7] sm:text-4xl">
            Not another random-pixel generator.
          </h2>
          <p className="mx-auto mt-3 text-slate-400">
            Most AI video tools hallucinate footage. Filmo is grounded in
            your actual product — so the video is true, on-brand, and editable.
          </p>
        </Reveal>

        {/* Feature grid */}
        <RevealGroup className="mt-12 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map((f) => (
            <RevealItem
              key={f.title}
              className="rounded-2xl border border-white/10 bg-white/[0.04] p-6 shadow-[0_24px_60px_-30px_rgba(0,0,0,0.85)] ring-1 ring-inset ring-white/5 transition hover:border-white/20"
            >
              <span className="grid h-11 w-11 place-items-center rounded-xl bg-amber/15 text-[#6F9BFF]">
                <span className="h-6 w-6">{f.icon}</span>
              </span>
              <h3 className="mt-5 text-base font-semibold tracking-tight text-[#F2F4F7]">
                {f.title}
              </h3>
              <p className="mt-2 text-sm leading-relaxed text-slate-400">
                {f.body}
              </p>
            </RevealItem>
          ))}
        </RevealGroup>
      </div>
    </section>
  )
}
