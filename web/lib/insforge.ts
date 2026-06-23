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
