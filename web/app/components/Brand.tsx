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

export function Wordmark({ className = '' }: { className?: string }) {
  return (
    <span className={`inline-flex items-center gap-2 font-semibold tracking-tight ${className}`}>
      {/* Canonical Walk Studio mark: cursor/arrow in a light-coral tile with ruler ticks */}
      <svg aria-hidden viewBox="0 0 84 84" className="h-7 w-7 shrink-0">
        <rect x="0" y="0" width="84" height="84" rx="22" fill="#FFF1EE" />
        <rect x="1" y="1" width="82" height="82" rx="21" fill="none" stroke="#F0BFB3" strokeWidth="1.5" />
        <g fill="#EAB6A9">
          <rect x="10" y="17" width="5.5" height="8" rx="2.75" />
          <rect x="10" y="38" width="5.5" height="8" rx="2.75" />
          <rect x="10" y="59" width="5.5" height="8" rx="2.75" />
          <rect x="68.5" y="17" width="5.5" height="8" rx="2.75" />
          <rect x="68.5" y="38" width="5.5" height="8" rx="2.75" />
          <rect x="68.5" y="59" width="5.5" height="8" rx="2.75" />
        </g>
        <path
          d="M32 20 L32 64 L42.8 53.4 L50.4 68.2 L57.6 64.6 L50 49.8 L62.8 49.8 Z"
          fill="#D6351C" stroke="#D6351C" strokeWidth="1.4" strokeLinejoin="round"
        />
      </svg>
      <span className="text-ink">
        Walk <span className="text-amber">Studio</span>
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
