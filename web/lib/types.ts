// Shared row types mirroring the InsForge `public` schema. Cast SDK results to these.

// `completed_with_warnings` = the orchestrator shipped a video but isolated one or
// more scene failures (orchestrator.py sets it; worker/run.js writes it verbatim).
// The web side treats it as delivered-with-a-warning: it HAS a final_url.
export type RunStatus = 'queued' | 'running' | 'delivered' | 'completed_with_warnings' | 'failed'
export type RunQuality = 'standard' | 'premium'
export type RunMode = 'mock' | 'real'

export interface Run {
  id: string
  user_id: string
  run_key: string
  brand: string | null
  company_url: string
  goal: string | null
  emphasis: string | null
  quality: RunQuality
  brain: string | null
  mode: RunMode
  status: RunStatus
  phase: string | null
  price_cents: number | null
  cogs_cents: number | null
  margin: number | null
  // Stripe TEST checkout URL, present during the human-pays flow while the run sits
  // at phase 'awaiting_payment'. The run page renders a Pay CTA when this is set.
  checkout_url?: string | null
  plan: unknown
  selection: unknown
  props?: unknown
  // Editor-saved props (in-browser edits), distinct from the clean worker-generated
  // `props`. Written by the saveEditedProps server action; lets the editor offer a
  // "revert to original" and keeps the original render-ready props intact.
  props_edited?: unknown
  final_url: string | null
  // The re-rendered ("Edited") video URL, produced by an editor Export → `rerender`
  // job. Kept separate from final_url so the original delivered cut is never lost.
  edited_url?: string | null
  created_at: string
  updated_at: string | null
  /** 'walkrec' = the agent-toured film (beta); 'classic' = the pattern-library cut. */
  film_mode?: string | null
}

export interface RunEvent {
  id: number
  run_id: string
  seq: number
  actor: 'hermes' | 'nemotron' | 'stripe' | string
  level: string | null
  msg: string
  created_at: string
}

// Ultra (paid 550B) is the default/first option — the flagship plan quality.
// Super (free 120B) stays selectable for a $0 run.
export const BRAINS = [
  { value: 'ultra-paid', label: 'Nemotron 3 Ultra', note: 'paid' },
  { value: 'super-free', label: 'Nemotron 3 Super', note: 'free' },
] as const

export function formatCents(cents: number | null | undefined): string {
  if (cents == null) return '--'
  return `$${(cents / 100).toFixed(2)}`
}

// Cent-precise dollar formatter for COGS / profit, where the real per-video model +
// voice cost can be a small fraction of a cent (e.g. 0.4¢ on the free Nemotron tier).
// Plain formatCents (.toFixed(2)) rounds those to "$0.00"; this shows enough decimals
// to reveal the true value while staying tidy for normal whole-cent amounts:
//   1234¢  -> $12.34   (whole cents → 2 dp)
//   0.42¢  -> $0.0042  (sub-cent → up to 6 dp, trailing zeros trimmed)
//   0¢     -> $0.00
export function formatCentsPrecise(cents: number | null | undefined): string {
  if (cents == null) return '--'
  const dollars = cents / 100
  // Whole-cent (or larger) amounts read best at the usual 2 dp.
  if (dollars === 0 || Math.abs(dollars) >= 0.01) return `$${dollars.toFixed(2)}`
  // Sub-cent: keep up to 6 decimals, drop trailing zeros (but never below 2 dp).
  const trimmed = dollars.toFixed(6).replace(/0+$/, '')
  const minTwo = trimmed.length - trimmed.indexOf('.') - 1 < 2 ? dollars.toFixed(2) : trimmed
  return `$${minTwo}`
}

export function formatMargin(margin: number | null | undefined): string {
  if (margin == null) return '--'
  // margin stored as a fraction (e.g. 0.62) or a percent (e.g. 62) — normalize.
  const pct = margin <= 1 ? margin * 100 : margin
  return `${Math.round(pct)}%`
}

export const STATUS_STYLES: Record<string, string> = {
  queued: 'bg-slate-100 text-slate-600 border-slate-200',
  running: 'bg-blue-50 text-amber border-amber/30',
  delivered: 'bg-nemo/10 text-nemo border-nemo/30',
  // Shipped, but with isolated scene failures — amber to flag the caveat.
  completed_with_warnings: 'bg-amber/10 text-amber border-amber/30',
  failed: 'bg-red-50 text-red-600 border-red-200',
}

// Human-readable chip labels. Most statuses display verbatim (the chip CSS-capitalizes
// them); the underscored `completed_with_warnings` would render as an ugly
// "Completed_with_warnings", so collapse it to a clean "Completed".
export const STATUS_LABELS: Record<string, string> = {
  completed_with_warnings: 'completed',
}

// Delivered-ish statuses: the run shipped a final video. `completed_with_warnings`
// is delivered with isolated scene failures, but it still HAS a final_url, so it
// renders the video player / download affordances exactly like `delivered`. Shared
// across the run page and the editor so the two never drift.
export const DELIVERED_STATUSES = new Set<string>(['delivered', 'completed_with_warnings'])

export function isDelivered(status: string | null | undefined): boolean {
  return status != null && DELIVERED_STATUSES.has(status)
}
