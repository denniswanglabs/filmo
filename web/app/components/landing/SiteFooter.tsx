import Link from 'next/link'
import { Wordmark } from '../Brand'
import PoweredBy from './PoweredBy'

// Slim, honest footer: wordmark + tagline on the left, three real in-page anchors
// on the right, copyright underneath. No fake social links or marketing pages.
export default function SiteFooter() {
  return (
    <footer className="border-t border-[#D4E2FB] bg-[#F5F8FF] px-5 py-12">
      <div className="mx-auto max-w-5xl">
        <div className="flex flex-col gap-6 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <Wordmark tone="light" />
            <p className="mt-2 text-sm text-[#5A6472]">Your product launch AI agent.</p>
          </div>
          <nav className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm">
            <Link href="/how-it-works" className="text-[#5A6472] transition hover:text-[#0E1320]">
              How it works
            </Link>
            <Link href="/#examples" className="text-[#5A6472] transition hover:text-[#0E1320]">
              Examples
            </Link>
            <Link href="/login" className="text-[#5A6472] transition hover:text-[#0E1320]">
              Sign in
            </Link>
          </nav>
        </div>

        {/* App-wide sponsor credit — Hermes Hackathon (Nous Research × NVIDIA × Stripe). */}
        <div className="mt-8 border-t border-[#D4E2FB] pt-6">
          <PoweredBy compact />
        </div>

        <p className="mt-6 text-xs text-[#8A94A6]">
          © 2026 Filmo · Built for the Hermes Hackathon — Nous Research × NVIDIA × Stripe
        </p>
      </div>
    </footer>
  )
}
