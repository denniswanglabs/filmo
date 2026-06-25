import Link from 'next/link'
import { Wordmark } from '../Brand'

// Slim, honest footer: wordmark + tagline on the left, three real in-page anchors
// on the right, copyright underneath. No fake social links or marketing pages.
export default function SiteFooter() {
  return (
    <footer className="border-t border-black/5 bg-[#F7F8FA] px-5 py-12">
      <div className="mx-auto max-w-5xl">
        <div className="flex flex-col gap-6 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <Wordmark />
            <p className="mt-2 text-sm text-slate-500">Your product launch AI agent.</p>
          </div>
          <nav className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm">
            <a href="#how" className="text-slate-500 transition hover:text-ink">
              How it works
            </a>
            <a href="#examples" className="text-slate-500 transition hover:text-ink">
              Examples
            </a>
            <Link href="/login" className="text-slate-500 transition hover:text-ink">
              Sign in
            </Link>
          </nav>
        </div>
        <p className="mt-8 text-xs text-slate-400">© 2026 Filmo</p>
      </div>
    </footer>
  )
}
