'use client'
import { useEffect, useState, useCallback, useRef } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { insforge } from '../lib/insforge'
import { useAuth } from '../lib/auth'
import { createBuild } from './actions'
import { StatusChip } from './components/Brand'
import { AuthGate } from './components/AuthGate'
import FloatingNav from './components/landing/FloatingNav'
import Examples from './components/landing/Examples'
import EditorDemo from './components/landing/EditorDemo'
import LuceoShowcase from './components/landing/LuceoShowcase'
import ReadyToCreate from './components/landing/ReadyToCreate'
import PoweredBy from './components/landing/PoweredBy'
import SiteFooter from './components/landing/SiteFooter'
import { ParallaxWindows, ScrubbedHero } from './components/landing/Motion'
import { BRAINS, type Run } from '../lib/types'

// Composer state stashed across the Google OAuth round-trip so the prompt survives
// the redirect and the build resumes automatically on return.
const PENDING_KEY = 'ws_pending_build'

interface PendingBuild {
  url: string
  quality: 'standard' | 'premium'
  brain: string
  // Opt-in: require a REAL Stripe TEST payment before the build proceeds. Default
  // false so the normal quick demo still auto-pays.
  requirePay: boolean
}

export default function Home() {
  const router = useRouter()
  const { user, loading } = useAuth()

  // Composer state
  const [url, setUrl] = useState('')
  const [quality, setQuality] = useState<'standard' | 'premium'>('standard')
  // Default to the flagship paid Ultra; Super (free) stays selectable in the dropdown.
  const [brain, setBrain] = useState<string>('ultra-paid')
  // Opt-in human-pays toggle (default OFF → normal demo auto-pays).
  const [requirePay, setRequirePay] = useState(false)
  const [building, setBuilding] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Sign-in gate (opens when a logged-out visitor hits Build)
  const [gateOpen, setGateOpen] = useState(false)

  // Recents
  const [runs, setRuns] = useState<Run[] | null>(null)

  // "Remix" from the Examples gallery seeds the composer with that cut's source
  // URL, then scrolls the composer into view and focuses the URL input — same
  // landing pattern as FloatingNav.jumpToComposer.
  useEffect(() => {
    function onSeed(e: Event) {
      const detail = (e as CustomEvent<{ url?: string }>).detail
      if (!detail?.url) return
      setUrl(detail.url)
      const start = document.getElementById('start')
      start?.scrollIntoView({ behavior: 'smooth' })
      // Focus after the smooth scroll settles so it doesn't fight the animation.
      window.setTimeout(() => document.getElementById('hero-url')?.focus(), 400)
    }
    window.addEventListener('filmo:seed-composer', onSeed)
    return () => window.removeEventListener('filmo:seed-composer', onSeed)
  }, [])

  const loadRuns = useCallback(async () => {
    const { data, error } = await insforge.database
      .from('runs')
      .select(
        'id, brand, company_url, goal, quality, status, phase, price_cents, margin, final_url, created_at',
      )
      .order('created_at', { ascending: false })
      .limit(20)
    if (!error) setRuns((data as Run[]) ?? [])
  }, [])

  useEffect(() => {
    if (user) void loadRuns()
  }, [user, loadRuns])

  // Kick off a build and navigate to its run page.
  const runBuild = useCallback(
    async (userId: string, p: PendingBuild) => {
      setError(null)
      setBuilding(true)
      try {
        const { runId } = await createBuild({
          userId,
          url: p.url.trim(),
          quality: p.quality,
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
    [router],
  )

  const currentPending = useCallback(
    (): PendingBuild => ({ url, quality, brain, requirePay }),
    [url, quality, brain, requirePay],
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
    setQuality(p.quality ?? 'standard')
    setBrain(p.brain ?? 'ultra-paid')
    setRequirePay(p.requirePay ?? false)
    if (user) void runBuild(user.id, p)
  }, [loading, user, runBuild])

  function onBuild(e: React.FormEvent) {
    e.preventDefault()
    if (user) {
      void runBuild(user.id, currentPending())
    } else {
      // Logged out: stash the prompt and open the Gmail gate.
      stashPending()
      setGateOpen(true)
    }
  }

  const canBuild = url.trim().length > 3 && !building

  return (
    <div className="landing-dark min-h-screen">
      <FloatingNav />

      <section
        id="start"
        className="surface-dots-dark relative overflow-hidden border-b border-[#D4E2FB]/60"
      >
        {/* Soft light-blue aura grounds the light hero. */}
        <div aria-hidden="true" className="stage-aura pointer-events-none absolute inset-0 z-0" />
        {/* Decorative floating "windows" parallax layer — sits behind the composer
            (z-0, pointer-events none), never covers the headline or form. */}
        <ParallaxWindows />
        <main className="relative z-10 mx-auto max-w-3xl px-5 pb-20 pt-28 sm:pt-36">
          {/* Scroll-scrubbed pinned hero: the headline + REAL composer scrub in
              (scale/lift) and settle, pinned across the first viewport. The form
              stays fully functional — ScrubbedHero only wraps it in a transform.
              Reduced motion / SSR: renders untransformed in normal flow. */}
          <ScrubbedHero className="w-full">
            {/* Hero — left-aligned, indented to line up with the composer's
                inner labels (card uses p-6, so px-6 here shares that left edge). */}
            <div className="mb-8 px-6 text-left">
              <h1 className="text-5xl font-semibold leading-[1.03] tracking-tight text-[#0E1320] sm:text-[3.75rem]">
                Your AI Product
                <br />
                Launch Producer
              </h1>
              <p className="mt-4 max-w-xl text-lg text-[#5A6472]">
                Paste your URL. Filmo reads your real product, diagnoses how it converts, and
                ships a finished launch video — planned, priced, and produced on autopilot.
              </p>
            </div>

            {/* Composer card — white, light-blue accents, soft shadow */}
            <form
              onSubmit={onBuild}
              className="rounded-2xl border border-[#D4E2FB] bg-white p-6 shadow-[0_30px_80px_-30px_rgba(30,58,120,0.22)] ring-1 ring-inset ring-[#EAF1FF]"
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

            {/* Controls row */}
            <div className="mt-5 flex flex-wrap items-end justify-between gap-4">
              {/* Quality toggle */}
              <div>
                <span className="mb-1.5 block text-sm font-medium text-[#0E1320]">Quality</span>
                <div className="inline-flex rounded-lg border border-[#D4E2FB] bg-[#F8FAFF] p-0.5">
                  {(['standard', 'premium'] as const).map((q) => (
                    <button
                      key={q}
                      type="button"
                      onClick={() => setQuality(q)}
                      className={`rounded-[7px] px-4 py-1.5 text-sm font-medium capitalize transition ${
                        quality === q
                          ? 'bg-amber text-white shadow-sm'
                          : 'text-[#5A6472] hover:text-[#0E1320]'
                      }`}
                    >
                      {q}
                    </button>
                  ))}
                </div>
              </div>

              {/* Brain selector (operator-scale) */}
              <div className="text-right">
                <span className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-[#5A6472]">
                  Model
                </span>
                <select
                  value={brain}
                  onChange={(e) => setBrain(e.target.value)}
                  className="rounded-lg border border-[#D4E2FB] bg-[#F8FAFF] px-2.5 py-1.5 text-sm text-[#0E1320] outline-none focus:border-amber"
                >
                  {BRAINS.map((b) => (
                    <option key={b.value} value={b.value} className="bg-white text-[#0E1320]">
                      {b.label} ({b.note})
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {/* Opt-in human-pays toggle. OFF = the demo auto-pays (quick path). ON =
                the build creates a real Stripe TEST checkout the user pays (card 4242)
                before production runs. */}
            <label className="mt-4 flex cursor-pointer items-start gap-2.5 rounded-lg border border-[#D4E2FB] bg-[#F8FAFF] px-3.5 py-3 transition hover:border-[#B9D2F8]">
              <input
                type="checkbox"
                checked={requirePay}
                onChange={(e) => setRequirePay(e.target.checked)}
                className="mt-0.5 h-4 w-4 shrink-0 cursor-pointer accent-amber"
              />
              <span className="min-w-0">
                <span className="block text-sm font-medium text-[#0E1320]">
                  Require payment (Stripe test)
                </span>
                <span className="block text-xs text-[#5A6472]">
                  Pay with test card 4242 before the video renders. No real charge.
                </span>
              </span>
            </label>

            {error && <p className="mt-4 text-sm text-red-500">{error}</p>}

            <button
              disabled={!canBuild}
              className="mt-6 w-full rounded-xl bg-amber py-3 font-semibold text-white shadow-[0_10px_30px_-10px_rgba(59,130,246,0.6)] transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {building ? 'Starting build…' : 'Build'}
            </button>
              {!user && !loading && (
                <p className="mt-3 text-center text-xs text-[#5A6472]">
                  You&rsquo;ll sign in with Google to start — your prompt is saved.
                </p>
              )}
            </form>
          </ScrubbedHero>

          {/* Sponsor credit — Hermes Hackathon (Nous Research × NVIDIA × Stripe).
              Sits directly under the composer as a small trust strip. */}
          <div className="mt-8">
            <PoweredBy />
          </div>

          {/* Recents — only meaningful once signed in. */}
          {user && (
            <section className="mt-12">
              <div className="mb-3 flex items-center justify-between">
                <h2 className="text-sm font-semibold uppercase tracking-wide text-[#5A6472]">
                  Recents
                </h2>
                <button
                  onClick={() => void loadRuns()}
                  className="text-sm text-[#5A6472] transition hover:text-[#0E1320]"
                >
                  Refresh
                </button>
              </div>

              {runs == null ? (
                <p className="text-sm text-[#5A6472]">Loading runs…</p>
              ) : runs.length === 0 ? (
                <div className="rounded-xl border border-dashed border-[#D4E2FB] px-5 py-10 text-center text-sm text-[#5A6472]">
                  No builds yet. Your first one will show up here.
                </div>
              ) : (
                <ul className="space-y-2">
                  {runs.map((r) => (
                    <li key={r.id}>
                      <Link
                        href={`/runs/${r.id}`}
                        className="flex items-center justify-between gap-4 rounded-xl border border-[#D4E2FB] bg-white px-4 py-3 transition hover:border-[#B9D2F8] hover:bg-[#F8FAFF]"
                      >
                        <div className="min-w-0">
                          <p className="truncate font-medium text-[#0E1320]">
                            {r.brand || r.company_url}
                          </p>
                          <p className="truncate text-sm text-[#5A6472]">{r.goal || 'Brand video'}</p>
                        </div>
                        <StatusChip status={r.status} />
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          )}
        </main>
      </section>

      {/* Proof — real videos the pipeline produced. */}
      <Examples />
      {/* Product demo — a looping faux editor showing live text-size editing. */}
      <EditorDemo />
      {/* Built on Luceo Studio's launch films. */}
      <LuceoShowcase />
      {/* Closing CTA — deep-navy band, scrolls back to the composer. */}
      <ReadyToCreate />
      <SiteFooter />

      <AuthGate
        open={gateOpen}
        onClose={() => setGateOpen(false)}
        onBeforeRedirect={stashPending}
        onSignedIn={(u) => {
          setGateOpen(false)
          void runBuild(u.id, currentPending())
        }}
      />
    </div>
  )
}
