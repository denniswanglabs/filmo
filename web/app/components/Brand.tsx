'use client'
// The two brand primitives every surface shares: the status chip (ONE meaning
// per status, product-wide) and the wordmark. `TopBar` — the old white
// marketing header — lived here too until 2026-07-20; its last four rooms
// (/inside, /inside/[runId], /runs/[id], /runs/[id]/edit) moved onto the rail
// (OverviewRail / Workspace's twin), and it was deleted rather than left as an
// importable way back to the old chrome.
import { STATUS_STYLES, STATUS_LABELS } from '../../lib/types'

export function StatusChip({ status }: { status: string }) {
  const style = STATUS_STYLES[status] || STATUS_STYLES.queued
  return (
    <span
      className={`shrink-0 rounded-full border px-2.5 py-1 text-xs font-medium capitalize ${style}`}
    >
      {STATUS_LABELS[status] || status}
    </span>
  )
}

export function Wordmark({
  className = '',
  tone = 'dark',
  inkClassName,
  size = 'default',
}: {
  className?: string
  /** 'dark' = dark ink for LIGHT backgrounds (default); 'light' = near-white ink for DARK backgrounds. */
  tone?: 'dark' | 'light'
  /** Optional exact text-color class for the word; overrides the tone default
   *  (used by callers that need a specific dark-ink hex, e.g. #0E1320). */
  inkClassName?: string
  /** 'nav' = larger icon + word for the floating landing nav. */
  size?: 'default' | 'nav'
}) {
  const inkClass = inkClassName ?? (tone === 'light' ? 'text-white' : 'text-ink')
  const iconClass = size === 'nav' ? 'h-9 w-9 sm:h-10 sm:w-10' : 'h-7 w-7'
  const textClass = size === 'nav' ? 'text-[2rem] sm:text-[2.25rem]' : 'text-[1.6rem]'
  return (
    <span className={`inline-flex items-center gap-1.5 font-semibold tracking-tight sm:gap-2 ${className}`}>
      {/* Soft organic mark — abstract, no tile/border (Filmo). Blue dot sits
          centered against the rounded blob; sized to match the enlarged word. */}
      <svg aria-hidden viewBox="14 13 56 56" className={`${iconClass} shrink-0`}>
        <path
          fillRule="evenodd"
          fill="#3B82F6"
          d="M42 17 C56 15 67 27 65 41 C63 55 52 67 38 65 C25 63 16 51 19 37 C21 25 30 19 42 17 Z M47 28.5 A8.5 8.5 0 1 1 47 45.5 A8.5 8.5 0 1 1 47 28.5 Z"
        />
      </svg>
      {/* Enlarged "Filmo" wordmark — explicit size so it stays balanced
          wherever Wordmark is reused (today: the AuthGate dialog). */}
      <span className={`${textClass} leading-none ${inkClass}`}>Filmo</span>
    </span>
  )
}
