import { createClient, createAdminClient } from '@insforge/sdk'

// Browser/user client — anon key, RLS-scoped. Safe to use in client components.
export const insforge = createClient({
  baseUrl: process.env.NEXT_PUBLIC_INSFORGE_URL!,
  anonKey: process.env.NEXT_PUBLIC_INSFORGE_ANON_KEY!,
})

// Server-only admin client — full access, bypasses RLS. ONLY call inside server
// actions / route handlers (the INSFORGE_API_KEY is never exposed to the browser).
export function adminClient() {
  return createAdminClient({
    baseUrl: process.env.INSFORGE_URL!,
    apiKey: process.env.INSFORGE_API_KEY!,
  })
}

// ─────────────────────────── Server-side identity ───────────────────────────
// Verify a client-supplied access token against InsForge and return the AUTHORITATIVE
// user. The token is a signed JWT; passing it as `accessToken` puts the client in
// server mode so `getCurrentUser()` makes a network call to /api/auth/sessions/current
// that validates it server-side. This is the ONLY trustworthy identity source in a
// server action — NEVER trust a client-supplied user id (the admin client bypasses
// RLS, so a forged id would be a cross-tenant write / auth bypass). Returns null when
// the token is absent, malformed, or rejected.
export async function verifyUser(
  accessToken: string | null | undefined,
): Promise<{ id: string; email?: string } | null> {
  if (!accessToken || typeof accessToken !== 'string') return null
  try {
    const client = createClient({
      baseUrl: process.env.INSFORGE_URL || process.env.NEXT_PUBLIC_INSFORGE_URL!,
      anonKey: process.env.NEXT_PUBLIC_INSFORGE_ANON_KEY!,
      accessToken, // → server mode → getCurrentUser() verifies via network
    })
    const { data, error } = await client.auth.getCurrentUser()
    if (error) return null
    const u = (data?.user ?? null) as { id?: string; email?: string } | null
    return u?.id ? { id: u.id, email: u.email } : null
  } catch {
    return null
  }
}
