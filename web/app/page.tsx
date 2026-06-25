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
import TrustBar from './components/landing/TrustBar'
import HowItWorks from './components/landing/HowItWorks'
import Differentiators from './components/landing/Differentiators'
import UseCases from './components/landing/UseCases'
import LuceoShowcase from './components/landing/LuceoShowcase'
import ParallaxColumns from './components/landing/ParallaxColumns'
import ClosingCTA from './components/landing/ClosingCTA'
import SiteFooter from './components/landing/SiteFooter'
import { ParallaxWindows } from './components/landing/Motion'
import { BRAINS, type Run } from '../lib/types'

// Composer state stashed across the Google OAuth round-trip so the prompt survives
// the redirect and the build resumes automatically on return.
const PENDING_KEY = 'ws_pending_build'

// Auto-cycling example prompts for the composer placeholder — makes the hero feel
// alive without touching the real value/state (decorative attribute only).
const EXAMPLE_PROMPTS = [
  'A 30-second explainer that makes our product feel inevitable.',
  'A Product Hunt launch cut that wins the day.',
  'A waitlist teaser that sells the promise before we ship.',
  'A landing-page hero loop scored to a beat.',
] as const

interface PendingBuild {
  url: string
  goal: string
  quality: 'standard' | 'premium'
  brain: string
}

export default function Home() {
  const router = useRouter()
  const { user, loading } = useAuth()

  // Composer state
  const [goal, setGoal] = useState('')
  const [url, setUrl] = useState('')
  const [quality, setQuality] = useState<'standard' | 'premium'>('standard')
  const [brain, setBrain] = useState<string>('super-free')
  const [building, setBuilding] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Sign-in gate (opens when a logged-out visitor hits Build)
  const [gateOpen, setGateOpen] = useState(false)

  // Recents
  const [runs, setRuns] = useState<Run[] | null>(null)

  // Rotating placeholder index — purely decorative (does not affect the value).
  const [phIndex, setPhIndex] = useState(0)
  useEffect(() => {
    const id = setInterval(() => setPhIndex((i) => (i + 1) % EXAMPLE_PROMPTS.length), 3500)
    return () => clearInterval(id)
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
          goal: p.goal.trim() || undefined,
          quality: p.quality,
          brain: p.brain,
          mode: 'mock',
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
    (): PendingBuild => ({ url, goal, quality, brain }),
    [url, goal, quality, brain],
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
    setGoal(p.goal ?? '')
    setQuality(p.quality ?? 'standard')
    setBrain(p.brain ?? 'super-free')
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
        className="surface-dots-dark relative overflow-hidden border-b border-white/5"
      >
        {/* Blue aura grounds the dark hero. */}
        <div aria-hidden="true" className="stage-aura pointer-events-none absolute inset-0 z-0" />
        {/* Decorative floating "windows" parallax layer — sits behind the composer
            (z-0, pointer-events none), never covers the headline or form. */}
        <ParallaxWindows />
        <main className="relative z-10 mx-auto max-w-3xl px-5 pb-20 pt-28 sm:pt-36">
          {/* Hero */}
          <div className="mb-8 text-center">
            <span className="inline-block rounded-full border border-amber/30 bg-amber/10 px-3 py-1 text-xs font-medium text-[#6F9BFF]">
              Your Product Launch AI Agent
            </span>
            <h1 className="mt-4 text-4xl font-semibold tracking-tight text-[#F2F4F7] sm:text-5xl">
              Launch your product with a video that sells it.
            </h1>
            <p className="mx-auto mt-4 max-w-xl text-lg text-slate-400">
              Paste your URL. Filmo reads your real product, diagnoses how it converts, and
              ships a finished launch video — planned, priced, and produced on autopilot.
            </p>
          </div>

          {/* Composer card — dark glass */}
          <form
            onSubmit={onBuild}
            className="rounded-2xl border border-white/10 bg-white/[0.04] p-6 shadow-[0_30px_80px_-30px_rgba(0,0,0,0.9)] ring-1 ring-inset ring-white/5 backdrop-blur-xl"
          >
            <label className="block">
              <span className="mb-1.5 block text-sm font-medium text-slate-200">
                What should the video show?
              </span>
              <textarea
                value={goal}
                onChange={(e) => setGoal(e.target.value)}
                rows={2}
                placeholder={EXAMPLE_PROMPTS[phIndex]}
                className="w-full resize-none rounded-lg border border-white/10 bg-white/[0.03] px-3.5 py-3 text-slate-100 outline-none transition placeholder:text-slate-500 focus:border-amber"
              />
            </label>

            <label className="mt-4 block">
              <span className="mb-1.5 block text-sm font-medium text-slate-200">Company URL</span>
              <div className="flex items-center rounded-lg border border-white/10 bg-white/[0.03] transition focus-within:border-amber">
                <span className="select-none pl-3.5 pr-1 text-slate-500">https://</span>
                <input
                  id="hero-url"
                  value={url.replace(/^https?:\/\//, '')}
                  onChange={(e) => setUrl('https://' + e.target.value.replace(/^https?:\/\//, ''))}
                  placeholder="acme.com"
                  className="w-full rounded-lg bg-transparent py-3 pr-3.5 text-slate-100 outline-none placeholder:text-slate-500"
                />
              </div>
            </label>

            {/* Controls row */}
            <div className="mt-5 flex flex-wrap items-end justify-between gap-4">
              {/* Quality toggle */}
              <div>
                <span className="mb-1.5 block text-sm font-medium text-slate-200">Quality</span>
                <div className="inline-flex rounded-lg border border-white/10 bg-white/[0.03] p-0.5">
                  {(['standard', 'premium'] as const).map((q) => (
                    <button
                      key={q}
                      type="button"
                      onClick={() => setQuality(q)}
                      className={`rounded-[7px] px-4 py-1.5 text-sm font-medium capitalize transition ${
                        quality === q
                          ? 'bg-amber text-white shadow-sm'
                          : 'text-slate-400 hover:text-slate-100'
                      }`}
                    >
                      {q}
                    </button>
                  ))}
                </div>
              </div>

              {/* Brain selector (operator-scale) */}
              <div className="text-right">
                <span className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-slate-500">
                  Model
                </span>
                <select
                  value={brain}
                  onChange={(e) => setBrain(e.target.value)}
                  className="rounded-lg border border-white/10 bg-white/[0.03] px-2.5 py-1.5 text-sm text-slate-300 outline-none focus:border-amber"
                >
                  {BRAINS.map((b) => (
                    <option key={b.value} value={b.value} className="bg-[#15171b] text-slate-100">
                      {b.label} ({b.note})
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {error && <p className="mt-4 text-sm text-red-400">{error}</p>}

            <button
              disabled={!canBuild}
              className="mt-6 w-full rounded-xl bg-amber py-3 font-semibold text-white transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {building ? 'Starting build…' : 'Build'}
            </button>
            {!user && !loading && (
              <p className="mt-3 text-center text-xs text-slate-500">
                You&rsquo;ll sign in with Google to start — your prompt is saved.
              </p>
            )}
          </form>

          {/* Recents — only meaningful once signed in. */}
          {user && (
            <section className="mt-12">
              <div className="mb-3 flex items-center justify-between">
                <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
                  Recents
                </h2>
                <button
                  onClick={() => void loadRuns()}
                  className="text-sm text-slate-500 transition hover:text-slate-200"
                >
                  Refresh
                </button>
              </div>

              {runs == null ? (
                <p className="text-sm text-slate-500">Loading runs…</p>
              ) : runs.length === 0 ? (
                <div className="rounded-xl border border-dashed border-white/12 px-5 py-10 text-center text-sm text-slate-500">
                  No builds yet. Your first one will show up here.
                </div>
              ) : (
                <ul className="space-y-2">
                  {runs.map((r) => (
                    <li key={r.id}>
                      <Link
                        href={`/runs/${r.id}`}
                        className="flex items-center justify-between gap-4 rounded-xl border border-white/10 bg-white/[0.03] px-4 py-3 transition hover:border-white/20 hover:bg-white/[0.05]"
                      >
                        <div className="min-w-0">
                          <p className="truncate font-medium text-slate-100">
                            {r.brand || r.company_url}
                          </p>
                          <p className="truncate text-sm text-slate-500">{r.goal || 'Brand video'}</p>
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

      {/* Marketing — the product-launch-video-generator story (dark stage) */}
      <TrustBar />
      <HowItWorks />
      <Differentiators />
      {/* THE showpiece: parallax drifting columns of the real Luceo films. */}
      <ParallaxColumns />
      <UseCases />
      <LuceoShowcase />
      <ClosingCTA />
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
