// Shared streamer for media stored on InsForge object storage.
//
// INVARIANT (the defect class this kills): the browser NEVER plays a storage
// URL directly. InsForge's upload path drops content types (objects land on
// S3/CloudFront as `binary/octet-stream`, a nonstandard MIME Chrome's media
// stack refuses to sniff — <video> stalls at readyState 0 forever), so every
// media URL the app renders must pass through a proxy route built on this
// helper: it stamps the real MIME from the key's extension and forwards
// Range so seeking works against the CDN's 206 support.
import { NextRequest } from 'next/server'

const MIME: Record<string, string> = {
  '.mp4': 'video/mp4',
  '.webm': 'video/webm',
  '.mov': 'video/quicktime',
  '.m4a': 'audio/mp4',
  '.mp3': 'audio/mpeg',
  '.wav': 'audio/wav',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.png': 'image/png',
  '.gif': 'image/gif',
  '.webp': 'image/webp',
  '.svg': 'image/svg+xml',
  '.json': 'application/json',
}

export function mimeForPath(decodedPath: string): string {
  const m = decodedPath.toLowerCase().match(/\.[a-z0-9]+$/)
  return (m && MIME[m[0]]) || 'application/octet-stream'
}

// Streams the upstream object back, honoring Range. `cacheControl` lets the
// caller pick immutability (finals get an hour; live frames get no-store).
export async function streamStorageObject(
  req: NextRequest,
  target: URL,
  apiKey: string,
  cacheControl: string,
): Promise<Response> {
  const headers: Record<string, string> = { Authorization: `Bearer ${apiKey}` }
  const range = req.headers.get('range')
  if (range) headers.Range = range
  const upstream = await fetch(target.toString(), { headers, cache: 'no-store' })
  if (!upstream.ok && upstream.status !== 206) {
    return new Response('not found', { status: 404 })
  }
  let decodedPath = target.pathname
  try { decodedPath = decodeURIComponent(target.pathname) } catch { /* raw */ }
  const out = new Headers({
    'Content-Type': mimeForPath(decodedPath),
    'Cache-Control': cacheControl,
    'Accept-Ranges': upstream.headers.get('accept-ranges') || 'bytes',
  })
  for (const h of ['content-length', 'content-range', 'etag'] as const) {
    const v = upstream.headers.get(h)
    if (v) out.set(h, v)
  }
  return new Response(upstream.body, { status: upstream.status, headers: out })
}
