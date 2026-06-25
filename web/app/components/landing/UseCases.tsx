import type { ReactNode } from 'react'
import { Reveal, RevealGroup, RevealItem } from './Motion'

interface UseCase {
  title: string
  line: string
  icon: ReactNode
}

const USE_CASES: UseCase[] = [
  {
    title: 'Product Hunt launch',
    line: 'A scroll-stopping cut built to win the day.',
    icon: (
      <path d="M12 2l2.4 6.9L21 9l-5 4.4L17.4 21 12 17.3 6.6 21 8 13.4 3 9l6.6-.1L12 2z" />
    ),
  },
  {
    title: 'Waitlist teaser',
    line: "Tease the promise before you've shipped.",
    icon: (
      <>
        <path d="M5 12h14" />
        <path d="M12 5v14" />
        <circle cx="12" cy="12" r="9" />
      </>
    ),
  },
  {
    title: 'Feature announcement',
    line: 'Make a new feature feel inevitable.',
    icon: (
      <>
        <path d="M3 11l18-7-7 18-2.5-7.5L3 11z" />
        <path d="M11.5 12.5L21 4" />
      </>
    ),
  },
  {
    title: 'Investor update',
    line: 'Show traction in 30 seconds.',
    icon: (
      <>
        <path d="M4 19V5" />
        <path d="M4 19h16" />
        <path d="M8 16l3-4 3 2 4-6" />
      </>
    ),
  },
  {
    title: 'Social cutdowns',
    line: 'Vertical and square edits for X, LinkedIn, IG.',
    icon: (
      <>
        <rect x="3" y="4" width="8" height="16" rx="1.5" />
        <rect x="14" y="7" width="7" height="10" rx="1.5" />
      </>
    ),
  },
  {
    title: 'Landing-page hero',
    line: 'The loop that lives at the top of your site.',
    icon: (
      <>
        <rect x="3" y="4" width="18" height="16" rx="2" />
        <path d="M3 9h18" />
        <path d="M10.5 12.5l4 2-4 2v-4z" />
      </>
    ),
  },
]

export default function UseCases() {
  return (
    <section className="panel panel--lit px-5 py-20 sm:py-24">
      {/* Blue glass top edge — our signature on the rounded panel lip. */}
      <span aria-hidden="true" className="panel__edge" />
      <div className="mx-auto max-w-5xl">
        <Reveal className="mx-auto max-w-xl text-center">
          <span className="inline-block rounded-full border border-amber-line bg-amber-soft px-3 py-1 text-xs font-medium text-[#2563EB]">
            What you can ship
          </span>
          <h2 className="mt-4 text-3xl font-semibold tracking-tight text-[#0E1320] sm:text-4xl">
            One link. Every launch asset.
          </h2>
          <p className="mx-auto mt-3 max-w-xl text-[#5A6472]">
            The same grounded engine, pointed at whatever you&rsquo;re launching.
          </p>
        </Reveal>

        <RevealGroup as="ul" className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {USE_CASES.map((u) => (
            <RevealItem
              as="li"
              key={u.title}
              className="rounded-xl border border-[#D4E2FB] bg-white p-5 ring-1 ring-inset ring-[#EAF1FF] transition hover:border-[#B9D2F8]"
            >
              <span className="grid h-9 w-9 place-items-center rounded-full bg-amber-soft text-[#2563EB]">
                <svg
                  viewBox="0 0 24 24"
                  className="h-5 w-5"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.8"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  aria-hidden="true"
                >
                  {u.icon}
                </svg>
              </span>
              <h3 className="mt-4 font-semibold tracking-tight text-[#0E1320]">{u.title}</h3>
              <p className="mt-1 text-sm text-[#5A6472]">{u.line}</p>
            </RevealItem>
          ))}
        </RevealGroup>
      </div>
    </section>
  )
}
