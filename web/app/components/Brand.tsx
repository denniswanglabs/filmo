'use client'
import Link from 'next/link'
import { useAuth } from '../../lib/auth'
import { useRouter } from 'next/navigation'
import { STATUS_STYLES } from '../../lib/types'

export function StatusChip({ status }: { status: string }) {
  const style = STATUS_STYLES[status] || STATUS_STYLES.queued
  return (
    <span
      className={`shrink-0 rounded-full border px-2.5 py-1 text-xs font-medium capitalize ${style}`}
    >
      {status}
    </span>
  )
}

export function Wordmark({
  className = '',
  tone = 'dark',
}: {
  className?: string
  /** 'dark' = ink text (light backgrounds, default); 'light' = near-white text (dark stage). */
  tone?: 'dark' | 'light'
}) {
  return (
    <span className={`inline-flex items-center gap-1.5 font-semibold tracking-tight ${className}`}>
      {/* Soft organic mark — abstract, no tile/border (Filmo). Blue dot sits
          centered against the rounded blob; sized to match the enlarged word. */}
      <svg aria-hidden viewBox="14 13 56 56" className="h-7 w-7 shrink-0">
        <path
          fillRule="evenodd"
          fill="#3B82F6"
          d="M42 17 C56 15 67 27 65 41 C63 55 52 67 38 65 C25 63 16 51 19 37 C21 25 30 19 42 17 Z M47 28.5 A8.5 8.5 0 1 1 47 45.5 A8.5 8.5 0 1 1 47 28.5 Z"
        />
      </svg>
      {/* Enlarged "Filmo" wordmark — explicit size so it reads large in the nav,
          and stays balanced wherever Wordmark is reused (/login, /runs TopBar). */}
      <span
        className={`text-[1.6rem] leading-none ${tone === 'light' ? 'text-[#0E1320]' : 'text-ink'}`}
      >
        Filmo
      </span>
    </span>
  )
}

export function TopBar() {
  const { user, loading, signOut } = useAuth()
  const router = useRouter()

  async function handleSignOut() {
    await signOut()
    router.push('/login')
  }

  return (
    <header className="sticky top-0 z-20 border-b border-black/5 bg-white/80 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-5xl items-center justify-between px-5">
        <Link href="/" className="text-base">
          <Wordmark />
        </Link>
        <div className="text-sm">
          {loading ? (
            <span className="inline-block h-4 w-20 animate-pulse rounded bg-black/5" />
          ) : user ? (
            <div className="flex items-center gap-3">
              <span className="hidden text-slate-500 sm:inline">{user.email}</span>
              <button
                onClick={handleSignOut}
                className="rounded-lg border border-black/10 px-3 py-1.5 text-slate-600 transition hover:bg-black/[0.03]"
              >
                Sign out
              </button>
            </div>
          ) : (
            <Link
              href="/login"
              className="rounded-lg bg-amber px-3 py-1.5 font-medium text-white transition hover:opacity-90"
            >
              Sign in
            </Link>
          )}
        </div>
      </div>
    </header>
  )
}
