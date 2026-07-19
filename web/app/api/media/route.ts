// Media proxy for delivered films (runs.final_url / runs.edited_url and any
// other walk-videos object the app plays). See app/api/_lib/storageStream.ts
// for the invariant: storage serves `binary/octet-stream`, so playback MUST
// come through here to get a real MIME + Range support.
//
// Capability-URL model: final/edited URLs are already handed to the owner as
// direct storage links (shareable by design). This route only agrees to fetch
// objects from OUR storage host + bucket namespace — nothing else is reachable.
import { NextRequest } from 'next/server'
import { streamStorageObject } from '../_lib/storageStream'

export const dynamic = 'force-dynamic'

const IF_BASE = (process.env.INSFORGE_URL
  || process.env.NEXT_PUBLIC_INSFORGE_URL || '').replace(/\/$/, '')
const IF_KEY = process.env.INSFORGE_API_KEY || ''

const ALLOWED = /^\/api\/storage\/buckets\/[a-z0-9-]+\/objects\/.+/

export async function GET(req: NextRequest) {
  const u = req.nextUrl.searchParams.get('u') || ''
  let target: URL
  try {
    target = new URL(u)
  } catch {
    return new Response('bad url', { status: 400 })
  }
  if (!IF_BASE || !IF_KEY) return new Response('unconfigured', { status: 500 })
  let decodedPath = target.pathname
  try { decodedPath = decodeURIComponent(target.pathname) } catch { /* raw */ }
  if (target.origin !== new URL(IF_BASE).origin || !ALLOWED.test(decodedPath)) {
    return new Response('forbidden', { status: 403 })
  }
  return streamStorageObject(req, target, IF_KEY, 'public, max-age=3600')
}
