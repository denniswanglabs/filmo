'use client'
import { useEffect, useState, useCallback, useRef } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '../lib/auth'
import { createBuild } from './actions'
import { AuthGate } from './components/AuthGate'
import FloatingNav from './components/landing/FloatingNav'
import Examples from './components/landing/Examples'
import EditorDemo from './components/landing/EditorDemo'
import PatternLookbook from './components/landing/PatternLookbook'
import LuceoShowcase from './components/landing/LuceoShowcase'
import ReadyToCreate from './components/landing/ReadyToCreate'
import SiteFooter from './components/landing/SiteFooter'
import LandingBackdrop, { HeroBrandLayer } from './components/landing/LandingBackdrop'
import { HeroBelowFold, PinnedHero, scrollToHeroComposer } from './components/landing/Motion'
import VerticalCutReveal from './components/fancy/VerticalCutReveal'
import { BRAINS } from '../lib/types'

// Composer state stashed across the Google OAuth round-trip so the prompt survives
// the redirect and the build resumes automatically on return.
const PENDING_KEY = 'ws_pending_build'

interface PendingBuild {
  url: string
  brain: string
  // Opt-in: require a REAL Stripe TEST payment before the build proceeds. Default
  // false so the normal quick demo still auto-pays.
  requirePay: boolean
}

export default function Home() {
  const router = useRouter()
  const { user, loading, getToken } = useAuth()

  // Composer state
  const [url, setUrl] = useState('')
  // Default to the flagship paid Ultra; Super (free) stays selectable in the dropdown.
  const [brain, setBrain] = useState<string>('ultra-paid')
  // Opt-in human-pays toggle (default OFF → normal demo auto-pays).
  const [requirePay, setRequirePay] = useState(false)
  const [advancedOpen, setAdvancedOpen] = useState(false)
  const [building, setBuilding] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Sign-in gate (opens when a logged-out visitor hits Build)
  const [gateOpen, setGateOpen] = useState(false)

  // "Remix" from the Examples gallery seeds the composer with that cut's source
  // URL, then scrolls the composer into view and focuses the URL input — same
  // landing pattern as FloatingNav.jumpToComposer.
  useEffect(() => {
    function onSeed(e: Event) {
      const detail = (e as CustomEvent<{ url?: string }>).detail
      if (!detail?.url) return
      setUrl(detail.url)
      scrollToHeroComposer('smooth')
    }
    window.addEventListener('filmo:seed-composer', onSeed)
    return () => window.removeEventListener('filmo:seed-composer', onSeed)
  }, [])

  // Kick off a build and navigate to its run page. Identity travels as the verified
  // access token (the server derives the owner from it), never a client-set user id.
  const runBuild = useCallback(
    async (p: PendingBuild) => {
      setError(null)
      setBuilding(true)
      try {
        const accessToken = await getToken()
        if (!accessToken) {
          setBuilding(false)
          setGateOpen(true)
          return
        }
        const { runId } = await createBuild({
          accessToken,
          url: p.url.trim(),
          brain: p.brain,
          mode: 'mock',
          payMode: p.requirePay ? 'human' : 'auto',
        })
        router.push(`/runs/${runId}`)
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err))
        setBuilding(false)
      }
    },
    [router, getToken],
  )

  const currentPending = useCallback(
    (): PendingBuild => ({ url, brain, requirePay }),
    [url, brain, requirePay],
  )

  function stashPending() {
    try {
      sessionStorage.setItem(PENDING_KEY, JSON.stringify(currentPending()))
    } catch {
      /* sessionStorage unavailable (private mode) — Google return just won't auto-resume */
    }
  }

  // Resume a build after returning from the Google OAuth redirect. Runs once auth
  // resolves: restores the typed prompt, and auto-builds if the user came back signed in.
  const resumedRef = useRef(false)
  useEffect(() => {
    if (loading || resumedRef.current) return
    let raw: string | null = null
    try {
      raw = sessionStorage.getItem(PENDING_KEY)
    } catch {
      /* ignore */
    }
    if (!raw) return
    resumedRef.current = true
    try {
      sessionStorage.removeItem(PENDING_KEY)
    } catch {
      /* ignore */
    }
    let p: PendingBuild
    try {
      p = JSON.parse(raw)
    } catch {
      return
    }
    // Restore the composer so the prompt isn't lost (covers a cancelled sign-in too).
    setUrl(p.url ?? '')
    setBrain(p.brain ?? 'ultra-paid')
    setRequirePay(p.requirePay ?? false)
    if (user) void runBuild(p)
  }, [loading, user, runBuild])

  function onBuild(e: React.FormEvent) {
    e.preventDefault()
    if (user) {
      void runBuild(currentPending())
    } else {
      // Logged out: stash the prompt and open the Gmail gate.
      stashPending()
      setGateOpen(true)
    }
  }

  function handleNavBuild() {
    scrollToHeroComposer('smooth')
    if (user) return
    stashPending()
    setGateOpen(true)
  }

  const canBuild = url.trim().length > 3 && !building
  const heroRef = useRef<HTMLElement>(null)

  return (
    <div className="landing-dark min-h-screen">
      <LandingBackdrop />
      <div className="relative z-[1]">
      <FloatingNav buildEnabled={canBuild} onBuildClick={handleNavBuild} />

      <PinnedHero
        ref={heroRef}
        id="start"
        className="mx-auto max-w-3xl"
        decoration={
          <>
            <div aria-hidden="true" className="stage-aura pointer-events-none absolute inset-0 z-0" />
            <HeroBrandLayer />
          </>
        }
        title={
          <div className="mx-auto flex max-w-full justify-center px-1 text-[clamp(2.25rem,8.5vw,3.25rem)] font-semibold leading-[1.04] tracking-tight text-[#0E1320] sm:px-0 sm:text-[clamp(3.25rem,6vw,4.5rem)] sm:leading-[1.03]">
            <VerticalCutReveal
              splitBy="lines"
              staggerDuration={0.14}
              transition={{ type: 'spring', stiffness: 200, damping: 24 }}
              containerClassName="items-center text-center"
            >
              {'Your AI Product\nLaunch Producer'}
            </VerticalCutReveal>
          </div>
        }
        body={
          <>
            <p className="section-lede mx-auto mt-4 max-w-xl text-base sm:mt-5 sm:text-lg md:text-[1.125rem]">
              Paste your URL. Filmo reads your product, plans the cut, prices the job, and ships
              a finished launch video — on autopilot.
            </p>

            {/* Composer card — centered block, left-aligned internals */}
            <form
              onSubmit={onBuild}
              className="mx-auto mt-8 w-full rounded-2xl border border-[#D4E2FB] bg-white/95 p-5 text-left shadow-[0_30px_80px_-30px_rgba(30,58,120,0.22)] ring-1 ring-inset ring-[#EAF1FF] backdrop-blur-sm sm:rounded-3xl sm:p-6"
            >
            <label className="block">
              <span className="mb-1.5 block text-sm font-medium text-[#0E1320]">Website URL</span>
              <div className="flex items-center rounded-lg border border-[#D4E2FB] bg-[#F8FAFF] transition focus-within:border-amber focus-within:bg-white">
                <span className="select-none pl-3.5 pr-1 text-[#9AA6B8]">https://</span>
                <input
                  id="hero-url"
                  value={url.replace(/^https?:\/\//, '')}
                  onChange={(e) => setUrl('https://' + e.target.value.replace(/^https?:\/\//, ''))}
                  placeholder="acme.com"
                  className="w-full rounded-lg bg-transparent py-3 pr-3.5 text-[#0E1320] outline-none placeholder:text-[#9AA6B8]"
                />
              </div>
            </label>

            <div className="mt-5 border-t border-[#EAF1FF] pt-4">
              <button
                type="button"
                onClick={() => setAdvancedOpen((o) => !o)}
                aria-expanded={advancedOpen}
                className="flex w-full items-center justify-between rounded-lg px-1 py-1 text-left text-sm font-medium text-[#5A6472] transition hover:text-[#0E1320]"
              >
                <span>Advanced</span>
                <svg
                  viewBox="0 0 24 24"
                  className={`h-4 w-4 transition-transform ${advancedOpen ? 'rotate-180' : ''}`}
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  aria-hidden="true"
                >
                  <path d="M6 9 L12 15 L18 9" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </button>

              {advancedOpen && (
                <div className="mt-3 space-y-3 rounded-lg border border-[#EAF1FF] bg-[#FAFCFF] p-3.5">
                  <div>
                    <span className="mb-1 block text-[11px] font-medium uppercase tracking-wide text-[#8A94A6]">
                      Model
                    </span>
                    <select
                      value={brain}
                      onChange={(e) => setBrain(e.target.value)}
                      className="w-full rounded-lg border border-[#D4E2FB] bg-white px-2.5 py-1.5 text-sm text-[#0E1320] outline-none focus:border-amber"
                    >
                      {BRAINS.map((b) => (
                        <option key={b.value} value={b.value} className="bg-white text-[#0E1320]">
                          {b.label} ({b.note})
                        </option>
                      ))}
                    </select>
                  </div>

                  <label className="flex cursor-pointer items-start gap-2.5">
                    <input
                      type="checkbox"
                      checked={requirePay}
                      onChange={(e) => setRequirePay(e.target.checked)}
                      className="mt-0.5 h-4 w-4 shrink-0 cursor-pointer accent-amber"
                    />
                    <span className="min-w-0">
                      <span className="block text-sm text-[#5A6472]">
                        Require payment (Stripe test)
                      </span>
                      <span className="block text-xs text-[#8A94A6]">
                        Pay with test card 4242 before render. No real charge.
                      </span>
                    </span>
                  </label>
                </div>
              )}
            </div>

            {error && <p className="mt-4 text-sm text-red-500">{error}</p>}

            <button
              type="submit"
              disabled={!canBuild}
              className={`mt-6 w-full rounded-xl py-3 font-semibold transition active:scale-[0.99] ${
                canBuild
                  ? 'bg-amber text-white shadow-[0_10px_30px_-10px_rgba(59,130,246,0.6)] hover:opacity-90'
                  : 'cursor-not-allowed border border-[#D4E2FB] bg-[#EAF1FF] text-[#9AA6B8] shadow-none'
              }`}
            >
              {building ? 'Starting build…' : 'Build'}
            </button>
              {!user && !loading && (
                <p className="mt-3 text-center text-xs leading-relaxed text-[#8A94A6]">
                  Sign in with Google to start — your prompt is saved.
                </p>
              )}
            </form>
          </>
        }
      />

      <HeroBelowFold heroRef={heroRef}>
      {/* Proof — real videos the pipeline produced. The featured player here is the
          big autoplaying demo (a real Filmo-produced launch cut). */}
      <Examples />
      {/* Product demo — a looping faux editor showing live text-size editing. */}
      <EditorDemo />
      {/* The curation moat — the hand-curated pattern library, read straight as
          one narrative beat with the Luceo films it's distilled from (below). */}
      <PatternLookbook />
      {/* Built on Luceo Studio's launch films. */}
      <LuceoShowcase />
      {/* Closing CTA — deep-navy band, scrolls back to the composer. */}
      <ReadyToCreate />
      <SiteFooter />
      </HeroBelowFold>
      </div>

      <AuthGate
        open={gateOpen}
        onClose={() => setGateOpen(false)}
        onBeforeRedirect={stashPending}
        onSignedIn={() => {
          setGateOpen(false)
          void runBuild(currentPending())
        }}
      />
    </div>
  )
}
