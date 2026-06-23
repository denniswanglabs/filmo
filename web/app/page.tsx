'use client'
import { useEffect, useState, useCallback } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { insforge } from '../lib/insforge'
import { useAuth } from '../lib/auth'
import { createBuild } from './actions'
import { TopBar, StatusChip } from './components/Brand'
import { BRAINS, type Run } from '../lib/types'

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

  // Recents
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

  // Gate on auth.
  useEffect(() => {
    if (!loading && !user) router.replace('/login')
  }, [loading, user, router])

  useEffect(() => {
    if (user) void loadRuns()
  }, [user, loadRuns])

  async function onBuild(e: React.FormEvent) {
    e.preventDefault()
    if (!user) return
    setError(null)
    setBuilding(true)
    try {
      const { runId } = await createBuild({
        userId: user.id,
        url: url.trim(),
        goal: goal.trim() || undefined,
        quality,
        brain,
        mode: 'mock',
      })
      router.push(`/runs/${runId}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
      setBuilding(false)
    }
  }

  if (loading || !user) {
    return (
      <div className="flex min-h-screen items-center justify-center text-slate-400">Loading…</div>
    )
  }

  const canBuild = url.trim().length > 3 && !building

  return (
    <>
      <TopBar />
      <main className="mx-auto max-w-3xl px-5 pb-24 pt-12">
        {/* Hero */}
        <div className="mb-8 text-center">
          <span className="inline-block rounded-full border border-amber/20 bg-amber/5 px-3 py-1 text-xs font-medium text-amber">
            URL in → finished video out
          </span>
          <h1 className="mt-4 text-3xl font-semibold tracking-tight text-ink sm:text-4xl">
            Make a brand video from a link.
          </h1>
          <p className="mx-auto mt-3 max-w-xl text-slate-500">
            Paste a company URL and tell Walk Studio what to show. It plans the cut, prices the job,
            produces it, and ships a finished MP4.
          </p>
        </div>

        {/* Composer card */}
        <form
          onSubmit={onBuild}
          className="rounded-2xl border border-black/5 bg-white p-6 shadow-[0_18px_50px_-20px_rgba(20,23,28,0.25)]"
        >
          <label className="block">
            <span className="mb-1.5 block text-sm font-medium text-ink">
              What should the video show?
            </span>
            <textarea
              value={goal}
              onChange={(e) => setGoal(e.target.value)}
              rows={2}
              placeholder="A 30-second explainer that makes our product feel inevitable."
              className="w-full resize-none rounded-lg border border-black/10 px-3.5 py-3 outline-none transition placeholder:text-slate-400 focus:border-amber"
            />
          </label>

          <label className="mt-4 block">
            <span className="mb-1.5 block text-sm font-medium text-ink">Company URL</span>
            <div className="flex items-center rounded-lg border border-black/10 transition focus-within:border-amber">
              <span className="select-none pl-3.5 pr-1 text-slate-400">https://</span>
              <input
                value={url.replace(/^https?:\/\//, '')}
                onChange={(e) => setUrl('https://' + e.target.value.replace(/^https?:\/\//, ''))}
                placeholder="acme.com"
                className="w-full rounded-lg py-3 pr-3.5 outline-none placeholder:text-slate-400"
              />
            </div>
          </label>

          {/* Controls row */}
          <div className="mt-5 flex flex-wrap items-end justify-between gap-4">
            {/* Quality toggle */}
            <div>
              <span className="mb-1.5 block text-sm font-medium text-ink">Quality</span>
              <div className="inline-flex rounded-lg border border-black/10 p-0.5">
                {(['standard', 'premium'] as const).map((q) => (
                  <button
                    key={q}
                    type="button"
                    onClick={() => setQuality(q)}
                    className={`rounded-[7px] px-4 py-1.5 text-sm font-medium capitalize transition ${
                      quality === q
                        ? 'bg-amber text-white shadow-sm'
                        : 'text-slate-500 hover:text-ink'
                    }`}
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>

            {/* Brain selector (operator-scale) */}
            <div className="text-right">
              <span className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-slate-400">
                Model
              </span>
              <select
                value={brain}
                onChange={(e) => setBrain(e.target.value)}
                className="rounded-lg border border-black/10 bg-white px-2.5 py-1.5 text-sm text-slate-600 outline-none focus:border-amber"
              >
                {BRAINS.map((b) => (
                  <option key={b.value} value={b.value}>
                    {b.label} ({b.note})
                  </option>
                ))}
              </select>
            </div>
          </div>

          {error && <p className="mt-4 text-sm text-red-600">{error}</p>}

          <button
            disabled={!canBuild}
            className="mt-6 w-full rounded-xl bg-amber py-3 font-semibold text-white transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {building ? 'Starting build…' : 'Build'}
          </button>
        </form>

        {/* Recents */}
        <section className="mt-12">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-400">Recents</h2>
            <button
              onClick={() => void loadRuns()}
              className="text-sm text-slate-400 transition hover:text-ink"
            >
              Refresh
            </button>
          </div>

          {runs == null ? (
            <p className="text-sm text-slate-400">Loading runs…</p>
          ) : runs.length === 0 ? (
            <div className="rounded-xl border border-dashed border-black/10 px-5 py-10 text-center text-sm text-slate-400">
              No builds yet. Your first one will show up here.
            </div>
          ) : (
            <ul className="space-y-2">
              {runs.map((r) => (
                <li key={r.id}>
                  <Link
                    href={`/runs/${r.id}`}
                    className="flex items-center justify-between gap-4 rounded-xl border border-black/5 bg-white px-4 py-3 transition hover:border-black/10 hover:shadow-sm"
                  >
                    <div className="min-w-0">
                      <p className="truncate font-medium text-ink">
                        {r.brand || r.company_url}
                      </p>
                      <p className="truncate text-sm text-slate-400">
                        {r.goal || 'Brand video'}
                      </p>
                    </div>
                    <StatusChip status={r.status} />
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>
      </main>
    </>
  )
}
