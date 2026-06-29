// Download proxy for a run's delivered video.
//
// The video lives at a cross-origin InsForge storage URL (`runs.final_url`). A
// plain `<a download>` can't force a filename across origins, and a client-side
// fetch would hit CORS — so the Download button links here and this route does the
// work server-side: look up the run with the admin InsForge client, fetch the MP4,
// and stream it back as an attachment with a clean Filmo filename.
//
// Returns 404 when the run isn't delivered or has no final_url.
import { NextResponse } from 'next/server'
import { adminClient } from '../../../../../lib/insforge'

export const dynamic = 'force-dynamic'

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params
  if (!id) {
    return new NextResponse('Missing run id', { status: 400 })
  }

  // Admin client bypasses RLS so the route can resolve the run's final_url. We only
  // expose the bytes of a delivered video; no user data is returned.
  const db = adminClient()
  const { data, error } = await db.database
    .from('runs')
    .select('id, status, final_url')
    .eq('id', id)
    .maybeSingle()

  if (error || !data) {
    return new NextResponse('Run not found', { status: 404 })
  }

  const run = data as { id: string; status?: string | null; final_url?: string | null }
  if (run.status !== 'delivered' || !run.final_url) {
    return new NextResponse('No video available for this run', { status: 404 })
  }

  // Server-side fetch the MP4 from InsForge storage (no CORS, no exposed URL).
  let upstream: Response
  try {
    upstream = await fetch(run.final_url, { cache: 'no-store' })
  } catch {
    return new NextResponse('Failed to fetch the video', { status: 502 })
  }
  if (!upstream.ok || !upstream.body) {
    return new NextResponse('Failed to fetch the video', { status: 502 })
  }

  const headers = new Headers()
  headers.set('Content-Type', 'video/mp4')
  headers.set('Content-Disposition', `attachment; filename="filmo-${run.id}.mp4"`)
  const len = upstream.headers.get('content-length')
  if (len) headers.set('Content-Length', len)
  headers.set('Cache-Control', 'no-store')

  // Stream the upstream body straight through to the client.
  return new NextResponse(upstream.body, { status: 200, headers })
}
