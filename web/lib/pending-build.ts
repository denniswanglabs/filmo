// ── ONE PENDING BUILD, ONE DOOR ─────────────────────────────────────────────
// Signing in with Google navigates the WHOLE BROWSER away, and it always comes
// back to `/` — `/login`'s Google button calls signInWithGoogle(origin + '/').
// So a URL typed anywhere else in the product cannot resume its own build: the
// door stashes it here and routes to `/login` (the single sign-in surface since
// the modal was retired, 2026-07-20), and the landing (`web/app/page.tsx`) reads
// this key once auth resolves and fires createBuild on its behalf.
//
// THIS MODULE IS THE CONTRACT. It used to be two private copies — one in
// page.tsx, one in runs/[id]/NewFilmComposer.tsx — each carrying a comment
// warning that if either side moved, resume would stop working and fail
// SILENTLY: the user lands on `/` with an empty box, no error, and the URL they
// typed is simply gone. Both doors now import from here, so there is exactly one
// place to move and the compiler notices when it does.
export const PENDING_KEY = 'ws_pending_build'

export interface PendingBuild {
  url: string
  brain: string
  look?: string
  /**
   * Stripe TEST payment gate. DORMANT since the open beta: always false → pay_mode
   * 'auto' (simulated payment, no checkout). The full Stripe path stays in the
   * codebase. Stashes written BEFORE payments were switched off carry `true` and
   * would resurrect the checkout gate on resume, so the accessors below pin it to
   * false on the way in AND on the way out — a reader can never be handed one.
   */
  requirePay: boolean
}

/**
 * The same shape the server action enforces (createBuild → 'Enter a valid website
 * URL.'). Validate with this BEFORE touching the server action: createBuild THROWS
 * on a bad URL, and a thrown server action surfaces in production as the opaque
 * "Server Components render … digest" 500 — so the message the user would see is no
 * message at all. The classic trigger is a stash of `{url:''}` auto-firing on the
 * OAuth return.
 */
export function isValidBuildUrl(raw: string): boolean {
  return /^https?:\/\/[^\s]+\.[^\s]+/i.test((raw || '').trim())
}

/** Stash a build to be resumed by `/` after the Google round-trip. Never throws. */
export function writePendingBuild(p: PendingBuild): void {
  try {
    sessionStorage.setItem(PENDING_KEY, JSON.stringify({ ...p, requirePay: false }))
  } catch {
    /* private mode / storage disabled — the Google return just won't auto-resume */
  }
}

/** The stashed build, or null when there isn't a readable one. Never throws. */
export function readPendingBuild(): PendingBuild | null {
  let raw: string | null = null
  try {
    raw = sessionStorage.getItem(PENDING_KEY)
  } catch {
    return null
  }
  if (!raw) return null
  try {
    const p = JSON.parse(raw) as Partial<PendingBuild>
    if (!p || typeof p.url !== 'string') return null
    return {
      url: p.url,
      // An absent brain must NOT fall through to createBuild's own default:
      // that default is 'super-free', so a missing value silently downgrades a
      // paid-flagship build to the free tier (CLAUDE.md pins ultra-paid).
      brain: p.brain || 'ultra-paid',
      look: p.look,
      requirePay: false,
    }
  } catch {
    return null
  }
}

/** Drop the stash. Never throws. */
export function clearPendingBuild(): void {
  try {
    sessionStorage.removeItem(PENDING_KEY)
  } catch {
    /* ignore */
  }
}
