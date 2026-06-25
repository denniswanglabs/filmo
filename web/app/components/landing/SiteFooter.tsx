import Link from 'next/link'
import { Wordmark } from '../Brand'

// Slim, honest footer: wordmark + tagline on the left, three real in-page anchors
// on the right, copyright underneath. No fake social links or marketing pages.
export default function SiteFooter() {
  return (
    <footer className="border-t border-white/5 bg-[#0b0c0e] px-5 py-12">
      <div className="mx-auto max-w-5xl">
        <div className="flex flex-col gap-6 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <Wordmark tone="light" />
            <p className="mt-2 text-sm text-slate-400">Your product launch AI agent.</p>
          </div>
          <nav className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm">
            <a href="#how" className="text-slate-400 transition hover:text-white">
              How it works
            </a>
            <a href="#examples" className="text-slate-400 transition hover:text-white">
              Examples
            </a>
            <Link href="/login" className="text-slate-400 transition hover:text-white">
              Sign in
            </Link>
          </nav>
        </div>
        <p className="mt-8 text-xs text-slate-500">
          © 2026 Filmo · Built for the Hermes Hackathon — Nous Research × NVIDIA × Stripe
        </p>
      </div>
    </footer>
  )
}
