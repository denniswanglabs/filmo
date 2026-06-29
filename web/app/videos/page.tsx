'use client'
// /videos — the signed-in user's own builds, given a roomy full-page home.
// This is the SAME list that used to live under the home composer: identical
// `runs` query + identical run-card rendering, just relocated here and scoped
// (by RLS, via the user-scoped insforge client) to the signed-in user's runs.
// Signed-out visitors get a sign-in prompt — never any data.
import { useEffect, useState, useCallback } from 'react'
import Link from 'next/link'
import { insforge } from '../../lib/insforge'
import { useAuth } from '../../lib/auth'
import { StatusChip } from '../components/Brand'
import FloatingNav from '../components/landing/FloatingNav'
import SiteFooter from '../components/landing/SiteFooter'
import LandingBackdrop from '../components/landing/LandingBackdrop'
import { type Run } from '../../lib/types'

export default function VideosPage() {
  const { user, loading } = useAuth()

  // Recents — same shape + query as the old home list.
  const [runs, setRuns] = useState<Run[] | null>(null)

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

  return (
    <div className="landing-dark min-h-screen">
      <LandingBackdrop />
      <div className="relative z-[1]">
        <FloatingNav />

        {/* Page header — clears the floating nav, mirrors /how-it-works. */}
        <header className="relative overflow-hidden">
          <div aria-hidden="true" className="stage-aura pointer-events-none absolute inset-0 z-0" />
          <div className="relative z-10 mx-auto max-w-3xl px-5 pb-8 pt-28 text-center sm:pt-36">
            <span className="eyebrow">Your Videos</span>
            <h1 className="section-title mt-4 sm:text-5xl sm:leading-[1.08]">
              Your launch videos.
            </h1>
            <p className="section-lede mx-auto max-w-xl text-lg">
              Every build you&apos;ve started with Filmo, newest first. Open one to watch, edit, or
              download the finished cut.
            </p>
          </div>
        </header>

        <main className="relative z-10 mx-auto max-w-3xl px-5 pb-20 pt-2">
          {/* Auth resolving — neutral placeholder, never flash the signed-out prompt. */}
          {loading ? (
            <p className="text-center text-sm text-[#5A6472]">Loading…</p>
          ) : !user ? (
            // Signed out → sign-in prompt only. No data is queried or exposed.
            <div className="mx-auto max-w-md rounded-2xl border border-[#D4E2FB] bg-white/95 px-6 py-12 text-center shadow-[0_30px_80px_-30px_rgba(30,58,120,0.22)] ring-1 ring-inset ring-[#EAF1FF] backdrop-blur-sm">
              <p className="text-lg font-semibold text-[#0E1320]">Sign in to see your videos</p>
              <p className="mx-auto mt-2 max-w-xs text-sm text-[#5A6472]">
                Your launch videos live in your account. Sign in to pick up where you left off.
              </p>
              <Link
                href="/login"
                className="mt-6 inline-flex min-h-12 items-center justify-center rounded-full bg-amber px-6 py-2.5 text-base font-semibold text-white shadow-[0_8px_24px_-10px_rgba(59,130,246,0.6)] transition hover:opacity-90"
              >
                Sign in
              </Link>
            </div>
          ) : (
            // Signed in → the relocated recents list (identical query + cards).
            <section>
              <div className="mb-3 flex items-center justify-between">
                <span className="eyebrow">Recents</span>
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

        <SiteFooter />
      </div>
    </div>
  )
}
