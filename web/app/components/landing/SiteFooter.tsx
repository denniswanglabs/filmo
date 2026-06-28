import Link from 'next/link'
import { Wordmark } from '../Brand'
import PoweredBy from './PoweredBy'

const SECTION_LINKS = [
  { href: '/#examples', label: 'Examples' },
  { href: '/#editor-demo', label: 'Editor' },
  { href: '/#lookbook', label: 'Patterns' },
  { href: '/how-it-works', label: 'How it works' },
] as const

export default function SiteFooter() {
  return (
    <footer className="border-t border-[#D4E2FB] bg-[#F5F8FF] px-5 py-12">
      <div className="mx-auto max-w-5xl">
        <div className="flex flex-col gap-6 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <Wordmark tone="dark" inkClassName="text-[#0E1320]" />
            <p className="mt-2 text-sm leading-relaxed text-[#5A6472]">
              AI launch videos from your URL.
            </p>
          </div>
          <nav className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm sm:gap-x-5">
            {SECTION_LINKS.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                className="inline-flex min-h-10 items-center text-[#5A6472] transition hover:text-[#0E1320]"
              >
                {link.label}
              </Link>
            ))}
          </nav>
        </div>

        <div className="mt-8 border-t border-[#D4E2FB] pt-6">
          <PoweredBy compact />
        </div>

        <p className="mt-6 text-pretty text-xs leading-relaxed text-[#8A94A6]">
          © 2026 Filmo · Built for the Hermes Hackathon — Nous Research × NVIDIA × Stripe
        </p>
      </div>
    </footer>
  )
}
