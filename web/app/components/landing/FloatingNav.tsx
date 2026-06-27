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

// Prefer a real display name (Google account) over the raw email; fall back to the
// email's local part (before @). Keeps the bar reading as a person, not an address.
function displayName(user: { email?: string; [k: string]: unknown }): string {
  const meta = user.user_metadata as Record<string, unknown> | undefined
  const name =
    (user.name as string) ||
    (user.full_name as string) ||
    (meta?.full_name as string) ||
    (meta?.name as string)
  if (typeof name === 'string' && name.trim()) return name.trim()
  const email = user.email || ''
  return email.split('@')[0] || email
}

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
        className={`pointer-events-auto flex w-full max-w-3xl items-center justify-between gap-3 rounded-full border px-4 py-2 transition-all duration-300 ${
          scrolled
            ? 'border-[#D4E2FB] bg-white/85 shadow-[0_12px_40px_-16px_rgba(30,58,120,0.22)] backdrop-blur-xl'
            : 'border-[#E2ECFB] bg-white/70 backdrop-blur-md'
        }`}
      >
        {/* Wordmark (left) — nudged down a hair so it sits optically centered in the pill. */}
        <Link href="/" className="shrink-0 text-base">
          <Wordmark tone="dark" inkClassName="text-[#0E1320]" className="translate-y-[1.5px]" />
        </Link>

        {/* Right cluster — "How it works" now sits with the auth + CTA on the right.
            ("Examples" was removed; the gallery still lives on the landing.) */}
        <div className="flex shrink-0 items-center gap-2 text-sm">
          <button
            type="button"
            onClick={() => router.push('/how-it-works')}
            className="hidden whitespace-nowrap rounded-full px-3 py-1.5 text-[#5A6472] transition hover:bg-[#EAF1FF] hover:text-[#0E1320] sm:inline-flex"
          >
            How it works
          </button>
          {loading ? (
            <span className="inline-block h-7 w-20 animate-pulse rounded-full bg-[#EAF1FF]" />
          ) : user ? (
            <>
              <span className="hidden max-w-[160px] truncate text-[#5A6472] lg:inline">
                {displayName(user)}
              </span>
              <button
                onClick={handleSignOut}
                className="whitespace-nowrap rounded-full border border-[#D4E2FB] px-3.5 py-1.5 text-[#5A6472] transition hover:bg-[#EAF1FF] hover:text-[#0E1320]"
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
                className="whitespace-nowrap rounded-full px-3.5 py-1.5 text-[#5A6472] transition hover:bg-[#EAF1FF] hover:text-[#0E1320]"
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
