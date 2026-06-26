'use client'

// Hera-style floating pill nav for the DARK landing only. A centered, rounded,
// translucent-dark bar that floats over the stage and grows more opaque + blurred
// once the page is scrolled. Filmo wordmark (left), anchor links (center),
// Sign in / Build CTA (right). Wired to the existing auth (Sign in / Sign out),
// matching TopBar's behavior — but TopBar itself is untouched (it still serves
// /runs/[id] in light theme).

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useEffect, useState } from 'react'
import { useAuth } from '../../../lib/auth'
import { Wordmark } from '../Brand'

export default function FloatingNav() {
  const { user, loading, signOut } = useAuth()
  const router = useRouter()
  const [scrolled, setScrolled] = useState(false)

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 16)
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  async function handleSignOut() {
    await signOut()
    router.push('/login')
  }

  function jumpToComposer() {
    if (typeof document === 'undefined') return
    const start = document.getElementById('start')
    if (!start) {
      // Not on the landing (e.g. /how-it-works) — route to the composer there.
      router.push('/#start')
      return
    }
    start.scrollIntoView({ behavior: 'smooth' })
    document.getElementById('hero-url')?.focus()
  }

  return (
    <div className="pointer-events-none fixed inset-x-0 top-3 z-40 flex justify-center px-3 sm:top-4">
      <nav
        className={`pointer-events-auto grid w-full max-w-3xl grid-cols-[1fr_auto_1fr] items-center gap-3 rounded-full border px-4 py-2 transition-all duration-300 ${
          scrolled
            ? 'border-[#D4E2FB] bg-white/85 shadow-[0_12px_40px_-16px_rgba(30,58,120,0.22)] backdrop-blur-xl'
            : 'border-[#E2ECFB] bg-white/70 backdrop-blur-md'
        }`}
      >
        {/* Wordmark (left) */}
        <Link href="/" className="col-start-1 shrink-0 justify-self-start text-base">
          <Wordmark tone="dark" inkClassName="text-[#0E1320]" />
        </Link>

        {/* Center links — "How it works" routes to its own page. The "Examples"
            tab was removed: the gallery still lives on the landing, visitors just
            scroll to it. Hidden on small screens. */}
        <div className="col-start-2 hidden items-center gap-1 justify-self-center text-sm sm:flex">
          <button
            type="button"
            onClick={() => router.push('/how-it-works')}
            className="rounded-full px-3 py-1.5 text-[#5A6472] transition hover:bg-[#EAF1FF] hover:text-[#0E1320]"
          >
            How it works
          </button>
        </div>

        {/* Auth + CTA (right) */}
        <div className="col-start-3 flex shrink-0 items-center justify-self-end gap-2 text-sm">
          {loading ? (
            <span className="inline-block h-7 w-20 animate-pulse rounded-full bg-[#EAF1FF]" />
          ) : user ? (
            <>
              <span className="hidden max-w-[160px] truncate text-[#5A6472] lg:inline">
                {user.email}
              </span>
              <button
                onClick={handleSignOut}
                className="rounded-full border border-[#D4E2FB] px-3.5 py-1.5 text-[#5A6472] transition hover:bg-[#EAF1FF] hover:text-[#0E1320]"
              >
                Sign out
              </button>
              <button
                onClick={jumpToComposer}
                className="rounded-full bg-amber px-4 py-1.5 font-semibold text-white shadow-[0_8px_24px_-10px_rgba(59,130,246,0.6)] transition hover:opacity-90"
              >
                Build
              </button>
            </>
          ) : (
            <>
              <Link
                href="/login"
                className="rounded-full px-3.5 py-1.5 text-[#5A6472] transition hover:bg-[#EAF1FF] hover:text-[#0E1320]"
              >
                Sign in
              </Link>
              <button
                onClick={jumpToComposer}
                className="rounded-full bg-amber px-4 py-1.5 font-semibold text-white shadow-[0_8px_24px_-10px_rgba(59,130,246,0.6)] transition hover:opacity-90"
              >
                Build
              </button>
            </>
          )}
        </div>
      </nav>
    </div>
  )
}
