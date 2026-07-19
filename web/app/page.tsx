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
  look?: string
  // Stripe TEST payment gate. DORMANT since the open beta: always false → pay_mode
  // 'auto' (simulated payment, no checkout). The full Stripe path stays in the
  // codebase — flip the useState default back to true to re-enable it.
  requirePay: boolean
}

// Same shape the server action enforces (createBuild → 'Enter a valid website URL.').
// We validate client-side FIRST so an empty/garbage URL never reaches the server
// action: a thrown error inside a server action surfaces in production as the opaque
// "Server Components render … digest" 500. The classic trigger is the OAuth round-trip
// — a logged-out visitor opens the sign-in gate with an empty composer, we stash
// `{url:''}`, and on return the auto-resume would fire createBuild('') → throw → 500.
// Guarding here keeps that 500 (and its digest) from ever happening.
function isValidBuildUrl(raw: string): boolean {
  return /^https?:\/\/[^\s]+\.[^\s]+/i.test((raw || '').trim())
}

export default function Home() {
  const router = useRouter()
  const { user, loading, getToken } = useAuth()

  // Composer state
  const [url, setUrl] = useState('')
  // Default to the flagship paid Ultra; Super (free) stays selectable in the dropdown.
  const [brain, setBrain] = useState<string>('ultra-paid')
  // Visual style family — 'classic' light or the Engineered Night dark one-world look.
  const [look, setLook] = useState<string>('')
  // Walkrec beta entry: /?look=walkrec selects the agent-toured film mode and
  // the choice STICKS (localStorage) so every later plain visit keeps the new
  // pipeline; /?look=classic explicitly switches back and sticks the same way.
  useEffect(() => {
    try {
      const q = new URLSearchParams(window.location.search).get('look')
      if (q === 'walkrec' || q === 'classic' || q === 'engineered-night') {
        setLook(q)
        localStorage.setItem('filmo-look', q)
      } else {
        const saved = localStorage.getItem('filmo-look')
        if (saved === 'walkrec' || saved === 'engineered-night') setLook(saved)
      }
    } catch { /* ssr */ }
  }, [])
  // Payments are OFF for the open beta (no Stripe roadblock for new users) — every
  // build goes pay_mode 'auto'. The checkout UI + claimer gate remain in the codebase.
  const [requirePay] = useState(false)
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
      // Validate BEFORE touching the server action. createBuild throws on a bad URL,
      // and a thrown server-action error becomes an opaque production 500 (the digest
      // "Server Components render" error). Fail here with a friendly inline message.
      if (!isValidBuildUrl(p.url)) {
        setError('Enter a valid website URL.')
        return
      }
      setBuilding(true)
      try {
        const accessToken = await getToken()
        if (!accessToken) {
          setBuilding(false)
          setGateOpen(true)
          return
        }
        const res = await createBuild({
          accessToken,
          url: p.url.trim(),
          brain: p.brain,
          look: p.look === 'walkrec' ? 'walkrec'
            : p.look === 'engineered-night' ? 'engineered-night'
              : p.look === 'classic' ? 'classic' : undefined,
          mode: 'mock',
          payMode: p.requirePay ? 'human' : 'auto',
        })
        // Beta cap (non-owner accounts) returns a structured { limit } instead of a run —
        // show its message inline; it is NOT an auth/session error, so don't re-open the gate.
        if ('limit' in res) {
          setBuilding(false)
          setError(res.message)
          return
        }
        router.push(`/runs/${res.runId}`)
      } catch {
        // A thrown server-action error is OPAQUE in production (the "Server Components
        // render … digest" 500), so we can't read its real message. The dominant cause is
        // a stale/expired session token: the UI still looks signed-in (optimistic localStorage
        // restore), but the server's verifyUser rejected the token, so createBuild throws
        // "Please sign in to start a build." Re-open the sign-in gate so the user re-auths
        // cleanly — onSignedIn then re-runs the build with a FRESH token — instead of
        // surfacing the scary opaque server error in the composer.
        setBuilding(false)
        setError('Your session expired — please sign in again to start the build.')
        setGateOpen(true)
      }
    },
    [router, getToken],
  )

  const currentPending = useCallback(
    (): PendingBuild => ({ url, brain, look, requirePay }),
    [url, brain, look, requirePay],
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
    setLook(p.look === 'walkrec' ? 'walkrec'
      : p.look === 'engineered-night' ? 'engineered-night'
        : p.look === 'classic' ? 'classic' : '')
    // NOTE: deliberately NOT restoring p.requirePay — stashes from before payments
    // were turned off carry requirePay:true and would resurrect the checkout gate.
    // Auto-resume the build only when we returned signed-in AND the stashed URL is real.
    // A blank/garbage stash (e.g. the nav "Build" button opened the gate with an empty
    // composer) must NOT auto-fire createBuild — that would throw server-side and crash
    // the post-login landing with the opaque digest 500. We just restore the composer.
    if (user && isValidBuildUrl(p.url ?? '')) void runBuild(p)
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
        composer={
          <>
            {/* The composer bar — below the headline, Hera-style. One pill: URL
                input, advanced toggle, and Build as the arrow button inside it.
                PinnedHero keeps it on stage through the hero runway; the nav's
                Build scrolls back here from anywhere below. */}
            <div className="mx-auto mt-8 w-full max-w-xl text-left">
            <form
              onSubmit={onBuild}
              className="flex items-center gap-1 rounded-full border border-white/70 bg-white/90 py-1.5 pl-4 pr-1.5 shadow-[0_16px_48px_-18px_rgba(30,58,120,0.42)] backdrop-blur-xl"
            >
              <span className="select-none text-sm text-[#9AA6B8]">https://</span>
              <input
                id="hero-url"
                value={url.replace(/^https?:\/\//, '')}
                onChange={(e) => setUrl('https://' + e.target.value.replace(/^https?:\/\//, ''))}
                placeholder="acme.com"
                className="min-w-0 flex-1 bg-transparent py-2 text-[15px] text-[#0E1320] outline-none placeholder:text-[#9AA6B8]"
              />
              <button
                type="button"
                onClick={() => setAdvancedOpen((o) => !o)}
                aria-expanded={advancedOpen}
                aria-label="Advanced options"
                className={`grid h-9 w-9 shrink-0 place-items-center rounded-full transition ${
                  advancedOpen ? 'bg-[#EAF1FF] text-[#2563EB]' : 'text-[#8A94A6] hover:bg-black/[0.04] hover:text-[#0E1320]'
                }`}
              >
                <svg viewBox="0 0 24 24" className="h-4.5 w-4.5" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
                  <path d="M4 7h10M18 7h2M4 17h2M10 17h10" strokeLinecap="round" />
                  <circle cx="16" cy="7" r="2.2" />
                  <circle cx="8" cy="17" r="2.2" />
                </svg>
              </button>
              <button
                type="submit"
                disabled={!canBuild}
                aria-label={building ? 'Starting build' : 'Build'}
                className={`grid h-10 w-10 shrink-0 place-items-center rounded-full transition active:scale-95 ${
                  canBuild
                    ? 'bg-amber text-white shadow-[0_8px_22px_-8px_rgba(59,130,246,0.7)] hover:opacity-90'
                    : 'cursor-not-allowed bg-[#EAF1FF] text-[#9AA6B8]'
                } ${building ? 'animate-pulse' : ''}`}
              >
                <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="2.2" aria-hidden="true">
                  <path d="M12 19V5M6 11l6-6 6 6" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </button>
            </form>

            {advancedOpen && (
              <div className="mt-2 rounded-2xl border border-[#EAF1FF] bg-white/95 p-3.5 shadow-[0_16px_48px_-18px_rgba(30,58,120,0.35)] backdrop-blur-xl">
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
            )}

            {error && (
              <p className="mt-2 rounded-2xl border border-red-100 bg-white/95 px-4 py-2 text-center text-sm text-red-600 shadow-[0_12px_36px_-16px_rgba(30,58,120,0.3)] backdrop-blur-xl">
                {error}
              </p>
            )}
            </div>
            {!user && !loading && (
              <p className="mx-auto mt-3 text-center text-xs leading-relaxed text-[#8A94A6]">
                Sign in with Google to start — your prompt is saved.
              </p>
            )}
          </>
        }
        body={
          <>
            <p className="section-lede mx-auto mt-4 max-w-xl text-base sm:mt-5 sm:text-lg md:text-[1.125rem]">
              Paste your URL. Filmo reads your product, plans the cut, prices the job, and ships
              a finished launch video — on autopilot.
            </p>


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
