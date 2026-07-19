'use client'
// /assets — everything Filmo has taken from your site or made from it.
//
// This is the provenance ledger made browsable. The product's whole claim is
// that nothing in a film is invented: every line comes from a page it read,
// every mark is one the site actually serves, every second of motion is real
// footage. That claim is only checkable if you can SEE the raw material, so
// this page shows it — captures, brand marks, recordings, scene stills, and
// the finished films — read server-side and owner-scoped (same gate as
// /videos: a stale token prompts sign-in, never a false-empty library).
import { useCallback, useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import { useAuth } from '../../lib/auth'
import { listAssets, type AssetKind, type AssetRow } from '../actions'
import FloatingNav from '../components/landing/FloatingNav'
import SiteFooter from '../components/landing/SiteFooter'
import LandingBackdrop from '../components/landing/LandingBackdrop'

// Type names are the user's words for the thing, not the pipeline's event
// kinds — "Page capture", not "read.page".
const KINDS: { key: AssetKind | 'all'; label: string; hint: string }[] = [
  { key: 'all', label: 'All assets', hint: '' },
  { key: 'film', label: 'Films', hint: 'The finished cut' },
  { key: 'recording', label: 'Recordings', hint: 'Real screen footage' },
  { key: 'capture', label: 'Page captures', hint: 'Pages Filmo read' },
  { key: 'scene', label: 'Scene stills', hint: 'Frames from each beat' },
  { key: 'mark', label: 'Brand marks', hint: 'Logos from the site' },
]

function when(ts: number): string {
  const mins = Math.round((Date.now() - ts * 1000) / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.round(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  const days = Math.round(hrs / 24)
  if (days < 7) return `${days}d ago`
  return new Date(ts * 1000).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

export default function AssetsPage() {
  const { user, loading, getToken } = useAuth()
  const [assets, setAssets] = useState<AssetRow[] | null>(null)
  const [authError, setAuthError] = useState(false)
  const [kind, setKind] = useState<AssetKind | 'all'>('all')

  const load = useCallback(async () => {
    const token = await getToken()
    let res
    try {
      res = await listAssets(token)
    } catch {
      return
    }
    if ('authError' in res) { setAuthError(true); return }
    setAuthError(false)
    setAssets(res.assets)
  }, [getToken])

  useEffect(() => { if (user) void load() }, [user, load])

  const counts = useMemo(() => {
    const c: Record<string, number> = { all: assets?.length || 0 }
    for (const a of assets || []) c[a.kind] = (c[a.kind] || 0) + 1
    return c
  }, [assets])

  const shown = useMemo(
    () => (assets || []).filter((a) => kind === 'all' || a.kind === kind),
    [assets, kind],
  )

  return (
    <div className="landing-dark min-h-screen">
      <LandingBackdrop />
      <div className="relative z-[1]">
        <FloatingNav />

        <header className="relative overflow-hidden">
          <div aria-hidden="true" className="stage-aura pointer-events-none absolute inset-0 z-0" />
          <div className="relative z-10 mx-auto max-w-3xl px-5 pb-8 pt-28 text-center sm:pt-36">
            <span className="eyebrow">Assets</span>
            <h1 className="section-title mt-4 sm:text-5xl sm:leading-[1.08]">
              Everything Filmo took from your site.
            </h1>
            <p className="section-lede mx-auto max-w-xl text-lg">
              The raw material behind your films — the pages it read, the marks it
              captured, the footage it recorded, and every scene it cut. Nothing in a
              film comes from anywhere else.
            </p>
          </div>
        </header>

        <main className="relative z-10 mx-auto max-w-5xl px-5 pb-20 pt-2">
          {loading ? (
            <p className="text-center text-sm text-[#5A6472]">Loading…</p>
          ) : !user || authError ? (
            <div className="mx-auto max-w-md rounded-2xl border border-[#D4E2FB] bg-white/95 px-6 py-12 text-center shadow-[0_30px_80px_-30px_rgba(30,58,120,0.22)] ring-1 ring-inset ring-[#EAF1FF] backdrop-blur-sm">
              <p className="text-lg font-semibold text-[#0E1320]">Please sign in to view your assets</p>
              <p className="mx-auto mt-2 max-w-xs text-sm text-[#5A6472]">
                Your assets live in your account, alongside the films made from them.
              </p>
              <Link
                href="/login"
                className="mt-6 inline-flex min-h-12 items-center justify-center rounded-full bg-amber px-6 py-2.5 text-base font-semibold text-white shadow-[0_8px_24px_-10px_rgba(59,130,246,0.6)] transition hover:opacity-90"
              >
                Sign in
              </Link>
            </div>
          ) : assets == null ? (
            <p className="text-center text-sm text-[#5A6472]">Loading assets…</p>
          ) : assets.length === 0 ? (
            <div className="rounded-xl border border-dashed border-[#D4E2FB] px-5 py-10 text-center text-sm text-[#5A6472]">
              Nothing here yet. Build a film and everything Filmo reads, captures, and
              records will collect here.
            </div>
          ) : (
            <div className="flex flex-col gap-6 sm:flex-row sm:items-start">
              {/* Type rail — each filter says what the type IS, so the library
                  doubles as an explanation of what the agent collects. */}
              <nav className="flex shrink-0 gap-2 overflow-x-auto sm:w-52 sm:flex-col sm:overflow-visible">
                {KINDS.filter((k) => k.key === 'all' || counts[k.key]).map((k) => (
                  <button
                    key={k.key}
                    onClick={() => setKind(k.key)}
                    className={`flex items-center justify-between gap-3 whitespace-nowrap rounded-xl px-3 py-2 text-left transition ${
                      kind === k.key
                        ? 'bg-white text-[#0E1320] shadow-[0_1px_2px_rgba(0,0,0,0.05)]'
                        : 'text-[#5A6472] hover:bg-white/60'
                    }`}
                  >
                    <span className="flex flex-col">
                      <span className="text-sm font-medium">{k.label}</span>
                      {k.hint && kind === k.key ? (
                        <span className="text-xs text-[#8A94A6]">{k.hint}</span>
                      ) : null}
                    </span>
                    <span className="text-xs tabular-nums text-[#8A94A6]">
                      {counts[k.key] || 0}
                    </span>
                  </button>
                ))}
              </nav>

              <section className="min-w-0 flex-1">
                <div className="mb-3 flex items-center justify-between">
                  <span className="eyebrow">
                    {shown.length} {shown.length === 1 ? 'asset' : 'assets'}
                  </span>
                  <button
                    onClick={() => void load()}
                    className="text-sm text-[#5A6472] transition hover:text-[#0E1320]"
                  >
                    Refresh
                  </button>
                </div>
                <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
                  {shown.map((a) => (
                    <li key={a.id}>
                      <Link
                        href={`/runs/${a.runId}`}
                        className="group block overflow-hidden rounded-xl border border-[#D4E2FB] bg-white transition hover:border-[#B9D2F8]"
                      >
                        <div className="flex aspect-video items-center justify-center overflow-hidden bg-[#0E1320]">
                          {a.video ? (
                            <video
                              src={`${a.url}#t=2`}
                              preload="metadata"
                              muted
                              playsInline
                              className="h-full w-full object-cover"
                            />
                          ) : (
                            // Marks are small and often transparent — they sit ON
                            // the dark tile rather than filling it.
                            <img
                              src={a.url}
                              alt=""
                              className={a.kind === 'mark'
                                ? 'max-h-[60%] max-w-[70%] object-contain'
                                : 'h-full w-full object-cover'}
                            />
                          )}
                        </div>
                        <div className="px-3 py-2">
                          <p className="truncate text-sm font-medium text-[#0E1320]">{a.name}</p>
                          <p className="truncate text-xs text-[#8A94A6]">
                            {a.brand} · {when(a.ts)}
                          </p>
                        </div>
                      </Link>
                    </li>
                  ))}
                </ul>
              </section>
            </div>
          )}
        </main>

        <SiteFooter />
      </div>
    </div>
  )
}
