'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useEffect, useState } from 'react'
import { useAuth } from '../../../lib/auth'
import { scrollToHeroComposer } from './Motion'
import { Wordmark } from '../Brand'

// The operator account — the only one that sees the owner-only Analytics link.
// Mirrors the run-page TopBar + the analytics server gate (the real boundary).
const OWNER_EMAIL = 'denniswanglabs@gmail.com'

const NAV_LINKS = [
  { href: '/#examples', label: 'Examples', kind: 'hash' as const },
  { href: '/#editor-demo', label: 'Editor', kind: 'hash' as const },
  { href: '/#lookbook', label: 'Patterns', kind: 'hash' as const },
  { href: '/how-it-works', label: 'How it works', kind: 'route' as const },
] as const

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

function scrollToHash(href: string) {
  const hash = href.split('#')[1]
  if (!hash) return
  const el = document.getElementById(hash)
  if (el) {
    el.scrollIntoView({ behavior: 'smooth', block: 'start' })
    return
  }
  window.location.href = href
}

interface FloatingNavProps {
  /** When logged in, nav Build stays disabled until URL is valid. Logged-out Build always opens auth. */
  buildEnabled?: boolean
  /** Hero-aligned Build: scroll to composer; logged-out visitors also open AuthGate via page.tsx. */
  onBuildClick?: () => void
}

export default function FloatingNav({ buildEnabled = true, onBuildClick }: FloatingNavProps) {
  const { user, loading, signOut } = useAuth()
  const router = useRouter()
  const [menuOpen, setMenuOpen] = useState(false)

  useEffect(() => {
    if (!menuOpen) return
    const close = () => setMenuOpen(false)
    window.addEventListener('scroll', close, { passive: true })
    return () => window.removeEventListener('scroll', close)
  }, [menuOpen])

  async function handleSignOut() {
    await signOut()
    router.push('/')
  }

  function handleBuildClick() {
    setMenuOpen(false)
    if (onBuildClick) {
      onBuildClick()
      return
    }
    if (typeof document === 'undefined') return
    const start = document.getElementById('start')
    if (!start) {
      router.push('/#start')
      return
    }
    scrollToHeroComposer('smooth')
  }

  function handleNavLink(link: (typeof NAV_LINKS)[number]) {
    if (link.kind === 'route') {
      router.push(link.href)
      return
    }
    scrollToHash(link.href)
  }

  const buildActive = user ? buildEnabled : true
  const buildClass = buildActive
    ? 'inline-flex min-h-12 items-center rounded-full bg-amber px-6 py-2.5 text-base font-semibold text-white shadow-[0_8px_24px_-10px_rgba(59,130,246,0.6)] transition hover:opacity-90'
    : 'inline-flex min-h-12 cursor-not-allowed items-center rounded-full border border-[#D4E2FB] bg-[#EAF1FF] px-6 py-2.5 text-base font-semibold text-[#9AA6B8]'

  return (
    <div className="pointer-events-none fixed inset-x-0 top-3 z-40 px-4 sm:top-5 sm:px-6">
      <nav className="pointer-events-auto relative mx-auto flex w-full max-w-6xl items-center justify-between py-2">
        {/* Left — brand */}
        <Link href="/" className="relative z-10 shrink-0">
          <Wordmark tone="dark" inkClassName="text-[#0E1320]" size="nav" />
        </Link>

        {/* Center — true viewport center (desktop). pointer-events on links only. */}
        <div className="pointer-events-none absolute left-1/2 hidden -translate-x-1/2 items-center gap-7 lg:flex xl:gap-9">
          {NAV_LINKS.map((link) => (
            <button
              key={link.href}
              type="button"
              onClick={() => handleNavLink(link)}
              className="pointer-events-auto whitespace-nowrap text-[17px] font-medium text-[#5A6472] transition hover:text-[#0E1320]"
            >
              {link.label}
            </button>
          ))}
        </div>

        {/* Right — auth + CTA (+ mobile menu). Always show Build (never hide behind auth loading). */}
        <div className="relative z-20 flex shrink-0 items-center justify-end gap-2 sm:gap-3">
          {/* Mobile / tablet menu — section anchors below lg. */}
          <div className="relative lg:hidden">
            <button
              type="button"
              aria-expanded={menuOpen}
              aria-label="Open menu"
              onClick={() => setMenuOpen((o) => !o)}
              className="inline-flex h-11 w-11 items-center justify-center text-[#5A6472] transition hover:text-[#0E1320]"
            >
              <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                {menuOpen ? (
                  <path d="M6 6 L18 18 M18 6 L6 18" strokeLinecap="round" />
                ) : (
                  <>
                    <path d="M4 7 H20" strokeLinecap="round" />
                    <path d="M4 12 H20" strokeLinecap="round" />
                    <path d="M4 17 H20" strokeLinecap="round" />
                  </>
                )}
              </svg>
            </button>
            {menuOpen && (
              <>
                <button
                  type="button"
                  aria-label="Close menu"
                  className="fixed inset-0 z-40 bg-[#0E1320]/12 backdrop-blur-[1px] lg:hidden"
                  onClick={() => setMenuOpen(false)}
                />
                <div className="absolute right-0 top-full z-50 mt-2 min-w-[11.5rem] overflow-hidden rounded-2xl border border-[#D4E2FB] bg-white py-1.5 shadow-[0_16px_48px_-12px_rgba(30,58,120,0.22)] ring-1 ring-inset ring-[#EAF1FF]">
                  {NAV_LINKS.map((link) => (
                    <button
                      key={link.href}
                      type="button"
                      onClick={() => {
                        setMenuOpen(false)
                        handleNavLink(link)
                      }}
                      className="block w-full px-4 py-2.5 text-left text-sm text-[#5A6472] transition hover:bg-[#F5F8FF] hover:text-[#0E1320]"
                    >
                      {link.label}
                    </button>
                  ))}
                  {/* Any signed-in user: their own videos — reachable on mobile too. */}
                  {!loading && user && (
                    <Link
                      href="/videos"
                      onClick={() => setMenuOpen(false)}
                      className="block w-full px-4 py-2.5 text-left text-sm text-[#5A6472] transition hover:bg-[#F5F8FF] hover:text-[#0E1320]"
                    >
                      Your Videos
                    </Link>
                  )}
                </div>
              </>
            )}
          </div>

          {!loading && user && (
            <>
              {/* Any signed-in user: their own videos. NOT owner-gated. */}
              <Link
                href="/videos"
                className="hidden whitespace-nowrap text-base font-medium text-[#5A6472] transition hover:text-amber sm:inline-flex"
              >
                Your Videos
              </Link>
              {/* Owner-only: link to the business analytics dashboard. Shown only when
                  the signed-in email matches the operator account. */}
              {typeof user.email === 'string' &&
              user.email.toLowerCase() === OWNER_EMAIL ? (
                <Link
                  href="/analytics"
                  className="hidden whitespace-nowrap text-base font-medium text-[#5A6472] transition hover:text-amber sm:inline-flex"
                >
                  Analytics
                </Link>
              ) : null}
              <span className="hidden max-w-[120px] truncate text-base text-[#5A6472] lg:inline xl:max-w-[160px]">
                {displayName(user)}
              </span>
              <button
                onClick={handleSignOut}
                className="hidden whitespace-nowrap text-base text-[#5A6472] transition hover:text-[#0E1320] sm:inline-flex"
              >
                Sign out
              </button>
            </>
          )}
          <button
            type="button"
            onClick={handleBuildClick}
            disabled={user ? !buildEnabled : false}
            className={buildClass}
          >
            Build
          </button>
        </div>
      </nav>
    </div>
  )
}
