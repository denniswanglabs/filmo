'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useEffect, useState } from 'react'
import { useAuth } from '../../../lib/auth'
import { getCredits } from '../../actions'
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
  // Operator account always shows a friendly first name so a screen-recording never
  // exposes the email handle ("Dennis", not "denniswanglabs").
  if ((user.email || '').toLowerCase() === OWNER_EMAIL) return 'Dennis'
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
  /** Hide the nav's own Build CTA (the landing docks a composer bar with the
      build arrow INSIDE it, so a second Build button is redundant there). */
  showBuild?: boolean
  /** Hero-aligned Build: scroll to composer; logged-out visitors also open AuthGate via page.tsx. */
  onBuildClick?: () => void
}

export default function FloatingNav({ buildEnabled = true, onBuildClick, showBuild = true }: FloatingNavProps) {
  const { user, loading, signOut, getToken } = useAuth()
  const [credits, setCredits] = useState<{
    dailyUsed: number; dailyCap: number
    lifetimeUsed: number; lifetimeCap: number
    videoCost: number; editCost: number; unlimited: boolean
  } | null>(null)
  const [creditsOpen, setCreditsOpen] = useState(false)
  useEffect(() => {
    if (!user) { setCredits(null); return }
    let stop = false
    ;(async () => {
      try {
        const t = await getToken()
        if (!t) return
        const c = await getCredits(t)
        if (!stop && !('error' in c)) setCredits(c)
      } catch { /* quiet */ }
    })()
    return () => { stop = true }
  }, [user, getToken])
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

  const isOwner =
    !loading &&
    !!user &&
    typeof user.email === 'string' &&
    user.email.toLowerCase() === OWNER_EMAIL

  return (
    <div className="pointer-events-none fixed inset-x-0 top-3 z-40 px-4 sm:top-5 sm:px-6">
      {/* Glass pill: low-opacity white + backdrop blur + hairline border, so the nav
          text always separates from content scrolling underneath it. */}
      <nav className="pointer-events-auto mx-auto flex w-full max-w-6xl items-center gap-3 rounded-full border border-white/70 bg-white/75 px-4 py-2 shadow-[0_10px_34px_-16px_rgba(30,58,120,0.35)] backdrop-blur-xl sm:px-5 lg:gap-4 xl:gap-6">
        {/* Left — brand */}
        <Link href="/" className="relative z-10 shrink-0">
          <Wordmark tone="dark" inkClassName="text-[#0E1320]" size="nav" />
        </Link>

        {/* Center — section/route links in normal flex flow (desktop). Owner sees the
            most items, so gaps/font tighten at lg and relax at xl; min-w-0 + scroll
            guarantees they never collide or overflow at any width. */}
        <div className="hidden min-w-0 flex-1 items-center justify-center gap-5 overflow-x-auto lg:flex xl:gap-8 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
          {NAV_LINKS.map((link) => (
            <button
              key={link.href}
              type="button"
              onClick={() => handleNavLink(link)}
              className="shrink-0 whitespace-nowrap text-[15px] font-medium text-[#5A6472] transition hover:text-[#0E1320] xl:text-[17px]"
            >
              {link.label}
            </button>
          ))}
          {/* Any signed-in user: their own videos. NOT owner-gated. */}
          {!loading && user && (
            <Link
              href="/videos"
              className="shrink-0 whitespace-nowrap text-[15px] font-medium text-[#5A6472] transition hover:text-amber xl:text-[17px]"
            >
              Your Videos
            </Link>
          )}
          {/* Any signed-in user: the raw material behind their films. */}
          {!loading && user && (
            <Link
              href="/assets"
              className="shrink-0 whitespace-nowrap text-[15px] font-medium text-[#5A6472] transition hover:text-amber xl:text-[17px]"
            >
              Assets
            </Link>
          )}
          {/* Owner-only: business analytics dashboard. */}
          {isOwner && (
            <Link
              href="/analytics"
              className="shrink-0 whitespace-nowrap text-[15px] font-medium text-[#5A6472] transition hover:text-amber xl:text-[17px]"
            >
              Analytics
            </Link>
          )}
        </div>

        {/* Spacer keeps the right group pinned right when the center row is hidden (below lg). */}
        <div className="flex-1 lg:hidden" />

        {/* Right — auth identity + CTA (+ mobile menu). Always show Build (never hide behind auth loading). */}
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
                  {!loading && user && (
                    <Link
                      href="/assets"
                      onClick={() => setMenuOpen(false)}
                      className="block w-full px-4 py-2.5 text-left text-sm text-[#5A6472] transition hover:bg-[#F5F8FF] hover:text-[#0E1320]"
                    >
                      Assets
                    </Link>
                  )}
                  {/* Owner-only analytics — reachable on mobile too. */}
                  {isOwner && (
                    <Link
                      href="/analytics"
                      onClick={() => setMenuOpen(false)}
                      className="block w-full px-4 py-2.5 text-left text-sm text-[#5A6472] transition hover:bg-[#F5F8FF] hover:text-[#0E1320]"
                    >
                      Analytics
                    </Link>
                  )}
                </div>
              </>
            )}
          </div>

          {!loading && user && (
            <>
              {/* Identity + sign out. The "Your Videos" / "Analytics" links live in the
                  center row (lg+) and in the mobile menu (below lg) — kept out of here so
                  the right group can never grow wide enough to collide with the center. */}
              {credits && !credits.unlimited && (
                <div className="relative hidden sm:block">
                  <button
                    onClick={() => setCreditsOpen((o) => !o)}
                    className="whitespace-nowrap rounded-full bg-[#EAF1FF] px-3 py-1 text-sm font-medium text-[#3B82F6] transition hover:bg-[#DCE9FF]"
                  >
                    {Math.max(0, credits.dailyCap - credits.dailyUsed)} credits
                  </button>
                  {creditsOpen && (
                    <div className="absolute right-0 top-10 z-50 w-64 rounded-2xl border border-[#E3E9F2] bg-white p-4 shadow-xl">
                      <div className="mb-3 flex items-baseline justify-between">
                        <span className="text-sm font-semibold text-[#0E1320]">Credit usage</span>
                        <span className="text-xs text-[#8A94A6]">Free while in beta</span>
                      </div>
                      <div className="mb-1 flex justify-between text-xs text-[#5A6472]">
                        <span>Daily</span>
                        <span className="tabular-nums">{credits.dailyUsed}/{credits.dailyCap} · rolling 24h</span>
                      </div>
                      <div className="mb-3 h-1.5 overflow-hidden rounded-full bg-[#EDF1F7]">
                        <div className="h-full rounded-full bg-[#3B82F6]"
                          style={{ width: `${Math.min(100, (credits.dailyUsed / credits.dailyCap) * 100)}%` }} />
                      </div>
                      <div className="mt-3 text-[11px] leading-snug text-[#8A94A6]">
                        Enough for about three films and ten edits a day. Credits refresh
                        every morning; failed builds are refunded.
                      </div>
                    </div>
                  )}
                </div>
              )}
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
          {showBuild && (
            <button
              type="button"
              onClick={handleBuildClick}
              disabled={user ? !buildEnabled : false}
              className={buildClass}
            >
              Build
            </button>
          )}
        </div>
      </nav>
    </div>
  )
}
