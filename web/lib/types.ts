// Shared row types mirroring the InsForge `public` schema. Cast SDK results to these.

export type RunStatus = 'queued' | 'running' | 'delivered' | 'failed'
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

export const BRAINS = [
  { value: 'super-free', label: 'Nemotron 3 Super', note: 'free' },
  { value: 'ultra-paid', label: 'Nemotron 3 Ultra', note: 'paid' },
] as const

export function formatCents(cents: number | null | undefined): string {
  if (cents == null) return '--'
  return `$${(cents / 100).toFixed(2)}`
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
  failed: 'bg-red-50 text-red-600 border-red-200',
}
