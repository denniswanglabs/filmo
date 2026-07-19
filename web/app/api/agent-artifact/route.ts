// Walkrec beta: same-origin proxy for agent artifacts (page shots, beat
// stills, clips, the live viewport frame) stored under the walk-videos
// bucket's agent/<run uuid>/ namespace.
//
// Capability-URL model (consistent with how final videos are shared): the
// run UUID in the path is the capability — this route validates the target
// is OUR storage host AND inside an agent/<uuid>/ namespace, then streams
// with the service key. No other storage path can be reached through it.
import { NextRequest } from 'next/server'
import { streamStorageObject } from '../_lib/storageStream'

export const dynamic = 'force-dynamic'

const IF_BASE = (process.env.INSFORGE_URL
  || process.env.NEXT_PUBLIC_INSFORGE_URL || '').replace(/\/$/, '')
const IF_KEY = process.env.INSFORGE_API_KEY || ''

const ALLOWED = new RegExp(
  '^/api/storage/buckets/[a-z0-9-]+/objects/agent/'
  + '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/')

export async function GET(req: NextRequest) {
  const u = req.nextUrl.searchParams.get('u') || ''
  let target: URL
  try {
    target = new URL(u)
  } catch {
    return new Response('bad url', { status: 400 })
  }
  if (!IF_BASE || !IF_KEY) return new Response('unconfigured', { status: 500 })
  // Uploaded object URLs percent-encode the key's slashes — validate the
  // DECODED path, fetch the original.
  let decodedPath = target.pathname
  try { decodedPath = decodeURIComponent(target.pathname) } catch { /* raw */ }
  if (target.origin !== new URL(IF_BASE).origin
      || !ALLOWED.test(decodedPath)) {
    return new Response('forbidden', { status: 403 })
  }
  // Storage serves binary/octet-stream (platform drops upload MIMEs), which
  // stalls <video> — the shared streamer stamps the MIME from the key's
  // extension and forwards Range. Live frames overwrite in place → no-store.
  return streamStorageObject(req, target, IF_KEY, 'no-store')
}
