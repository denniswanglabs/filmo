import type { ReactNode } from 'react'
import { Reveal } from './Motion'

interface StackItem {
  glyph: ReactNode
  label: string
  sub: string
}

// Abstract inline glyphs (no partner logos): a chip, a card, a globe/cursor.
const ITEMS: StackItem[] = [
  {
    label: 'NVIDIA Nemotron',
    sub: 'reads & plans',
    glyph: (
      <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <rect x="7" y="7" width="10" height="10" rx="1.5" />
        <rect x="10" y="10" width="4" height="4" rx="0.5" />
        <path d="M9 4v3M12 4v3M15 4v3M9 17v3M12 17v3M15 17v3" />
        <path d="M4 9h3M4 12h3M4 15h3M17 9h3M17 12h3M17 15h3" />
      </svg>
    ),
  },
  {
    label: 'Stripe',
    sub: 'prices & bills, autonomously',
    glyph: (
      <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <rect x="3" y="6" width="18" height="12" rx="2" />
        <path d="M3 10h18" />
        <path d="M7 14h3" />
      </svg>
    ),
  },
  {
    label: 'Real-site capture',
    sub: 'your actual UI, not stock',
    glyph: (
      <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <circle cx="12" cy="12" r="9" />
        <path d="M3 12h18" />
        <path d="M12 3c2.5 2.4 3.9 5.6 3.9 9s-1.4 6.6-3.9 9c-2.5-2.4-3.9-5.6-3.9-9s1.4-6.6 3.9-9Z" />
      </svg>
    ),
  },
]

export default function TrustBar() {
  return (
    <section className="panel panel--lit px-5 py-12 sm:py-14">
      {/* Blue glass top edge — first panel to slide over the hero stage. */}
      <span aria-hidden="true" className="panel__edge" />
      <Reveal className="mx-auto flex max-w-5xl flex-col items-center gap-7 text-center lg:flex-row lg:justify-between lg:text-left">
        <p className="max-w-xs text-sm font-medium text-[#5A6472]">
          Grounded in your real product — and built on a serious stack
        </p>

        <ul className="flex flex-wrap items-center justify-center gap-x-10 gap-y-6">
          {ITEMS.map((item) => (
            <li key={item.label} className="flex items-center gap-3">
              <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-amber-soft text-[#2563EB]">
                <span className="h-5 w-5">{item.glyph}</span>
              </span>
              <span className="text-left">
                <span className="block text-sm font-semibold text-[#0E1320]">{item.label}</span>
                <span className="block text-xs text-[#5A6472]">{item.sub}</span>
              </span>
            </li>
          ))}
        </ul>
      </Reveal>
    </section>
  )
}
