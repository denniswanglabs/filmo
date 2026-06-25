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
    document.getElementById('start')?.scrollIntoView({ behavior: 'smooth' })
    document.getElementById('hero-url')?.focus()
  }

  return (
    <div className="pointer-events-none fixed inset-x-0 top-3 z-40 flex justify-center px-3 sm:top-4">
      <nav
        className={`pointer-events-auto flex w-full max-w-3xl items-center justify-between gap-3 rounded-full border px-3 py-2 pl-4 transition-all duration-300 ${
          scrolled
            ? 'border-white/12 bg-[#0b0c0e]/80 shadow-[0_12px_40px_-16px_rgba(0,0,0,0.8)] backdrop-blur-xl'
            : 'border-white/8 bg-white/[0.04] backdrop-blur-md'
        }`}
      >
        {/* Wordmark (left) */}
        <Link href="/" className="shrink-0 text-base">
          <Wordmark tone="light" />
        </Link>

        {/* Anchor links (center) — hidden on small screens */}
        <div className="hidden items-center gap-1 text-sm sm:flex">
          <a
            href="#how"
            className="rounded-full px-3 py-1.5 text-slate-300 transition hover:bg-white/5 hover:text-white"
          >
            How it works
          </a>
          <a
            href="#examples"
            className="rounded-full px-3 py-1.5 text-slate-300 transition hover:bg-white/5 hover:text-white"
          >
            Examples
          </a>
        </div>

        {/* Auth + CTA (right) */}
        <div className="flex shrink-0 items-center gap-2 text-sm">
          {loading ? (
            <span className="inline-block h-7 w-20 animate-pulse rounded-full bg-white/10" />
          ) : user ? (
            <>
              <span className="hidden max-w-[160px] truncate text-slate-400 lg:inline">
                {user.email}
              </span>
              <button
                onClick={handleSignOut}
                className="rounded-full border border-white/12 px-3.5 py-1.5 text-slate-200 transition hover:bg-white/5"
              >
                Sign out
              </button>
              <button
                onClick={jumpToComposer}
                className="rounded-full bg-amber px-4 py-1.5 font-semibold text-white transition hover:opacity-90"
              >
                Build
              </button>
            </>
          ) : (
            <>
              <Link
                href="/login"
                className="rounded-full px-3.5 py-1.5 text-slate-200 transition hover:bg-white/5"
              >
                Sign in
              </Link>
              <button
                onClick={jumpToComposer}
                className="rounded-full bg-amber px-4 py-1.5 font-semibold text-white transition hover:opacity-90"
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
